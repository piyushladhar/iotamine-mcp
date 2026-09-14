"""Bearer-token verification for streamable-http's multi-tenant mode.

The "access token" a client presents here is not a JWT or any kind of
self-contained credential — the OAuth authorization server (this
platform's separate iotamine_backend_django, oauth_server app) issues a
real core.models.APIKey row as the OAuth access_token (see that app's
TokenView), so verifying one is exactly the same check the backend
already makes on every other authenticated API call: does a cheap,
key-eligible GET succeed with it. Real scope enforcement (read_only vs
read_write) deliberately stays where it already lives —
core.authentications.APIKeyAuthentication, applied fresh to every
actual tool call the token goes on to make via IotamineClient — this
verifier only answers "is this a live, active credential at all", the
same narrow gatekeeping role a resource server's bearer check always
plays (RFC 9728 / the MCP authorization spec).
"""
import threading
import time

import httpx
from mcp.server.auth.provider import AccessToken, TokenVerifier

_CACHE_TTL_SECONDS = 60
"""How long a verified (or rejected) token is trusted before re-checking
against the backend — bounds the extra round-trip this adds to about
once per token per minute rather than once per tool call, while still
noticing a revoked key within a short, predictable window."""

_CACHE_MAX_ENTRIES = 4096


class IotamineTokenVerifier(TokenVerifier):
    """Verifies a bearer token by asking the real backend whether it's a
    live, active Iotamine API key — GET /users/me/ accepts
    APIKeyAuthentication and is cheap (no query params, no related
    lookups), so it doubles as a plain "is this key good" check without
    needing a dedicated verification endpoint."""

    def __init__(self, base_url, resource_server_url=None):
        self._resource_server_url = resource_server_url
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            timeout=httpx.Timeout(connect=10, read=15, write=10, pool=10),
        )
        self._lock = threading.Lock()
        self._cache = {}  # token -> (expires_at, AccessToken | None)

    async def aclose(self):
        await self._client.aclose()

    async def verify_token(self, token: str) -> AccessToken | None:
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(token)
            if cached is not None and cached[0] > now:
                return cached[1]
        result = await self._check(token)
        with self._lock:
            if len(self._cache) >= _CACHE_MAX_ENTRIES:
                # Cheap unbounded-growth guard against a public server
                # being made to hold one entry per garbage token forever
                # — a 4096-token working set is already far beyond this
                # server's expected concurrency, so just drop everything
                # and let each token re-populate on its next call.
                self._cache.clear()
            self._cache[token] = (now + _CACHE_TTL_SECONDS, result)
        return result

    async def _check(self, token: str) -> AccessToken | None:
        try:
            response = await self._client.get("users/me/", headers={"Authorization": f"Api-Key {token}"})
        except httpx.RequestError:
            # Backend unreachable — fail closed (reject), not open.
            return None
        if response.status_code != 200:
            return None
        return AccessToken(
            token=token,
            client_id="iotamine-api-key",
            scopes=[],
            resource=self._resource_server_url,
        )
