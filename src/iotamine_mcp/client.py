"""Thin wrapper around the real Iotamine REST API (iotamine_backend_django)
— every tool in iotamine_mcp.tools goes through this, and nothing here
duplicates any business logic the backend already owns. Auth is a plain
Iotamine API key (core.authentications.APIKeyAuthentication), sent the
same way any other REST client already sends one.
"""
import os
import threading
from collections import OrderedDict

import httpx
from mcp.server.mcpserver.exceptions import ToolError

DEFAULT_BASE_URL = "https://iotamine.com/api/"


class IotamineConfigError(Exception):
    """Raised at startup when IOTAMINE_API_KEY isn't set — a clear,
    early failure instead of every tool call failing with a confusing
    401 one at a time."""


class IotamineAPIError(ToolError):
    """Wraps a non-2xx response from the real API. Subclasses ToolError
    deliberately — anything else (plain Exception) reaches the model as
    an opaque "Error executing tool <name>" crash with no message at
    all, confirmed live: every tool in this whole package was doing
    exactly that for every real API error (401, 403, quota exceeded,
    VPS not found, ...) until this was caught. ToolError is what makes
    the SDK return a clean is_error=True result carrying `message`
    instead. `message` is the
    backend's own {"message": ...} (or {"error": ...}) body when it sent
    one — always shown to the model as-is rather than a generic
    "something went wrong", since it's already written to be a clear,
    actionable string (see e.g. core.views's own KYC/VPS error
    messages)."""

    def __init__(self, status_code, message):
        super().__init__(f"{status_code}: {message}")
        self.status_code = status_code
        self.message = message


def _extract_message(response):
    try:
        data = response.json()
    except ValueError:
        return response.text[:500] or f"HTTP {response.status_code}"
    if isinstance(data, dict):
        return data.get("message") or data.get("error") or data.get("detail") or str(data)
    return str(data)


class IotamineClient:
    """One instance per server process — httpx.Client is safe to reuse
    across calls, unlike creating a fresh connection per tool call."""

    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or os.environ.get("IOTAMINE_API_KEY")
        if not self.api_key:
            raise IotamineConfigError(
                "IOTAMINE_API_KEY is not set. Generate an API key from your Iotamine "
                "dashboard (Account -> API Keys) and set it as an environment variable "
                "in your MCP client's config for this server."
            )
        self.base_url = (base_url or os.environ.get("IOTAMINE_API_URL") or DEFAULT_BASE_URL).rstrip("/") + "/"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Api-Key {self.api_key}", "Accept": "application/json"},
            timeout=httpx.Timeout(connect=10, read=60, write=15, pool=10),
        )

    def close(self):
        self._client.close()

    def _request(self, method, path, *, params=None, json=None):
        try:
            response = self._client.request(method, path.lstrip("/"), params=params, json=json)
        except httpx.RequestError as exc:
            raise IotamineAPIError(None, f"Could not reach the Iotamine API: {exc}") from exc
        if response.status_code == 401:
            raise IotamineAPIError(401, "This API key is invalid, inactive, or IP-restricted. Check it on your Iotamine dashboard's API Keys page.")
        if response.status_code == 403:
            raise IotamineAPIError(403, _extract_message(response) or "This API key doesn't have permission for this action — it may be read-only (see APIKey.scope on your dashboard).")
        if not response.is_success:
            raise IotamineAPIError(response.status_code, _extract_message(response))
        if not response.content:
            return None
        return response.json()

    def _raw_request(self, method, path, *, params=None):
        """Like _request, but for the handful of endpoints that don't
        return JSON at all (UserDataExportView's CSV/zip). Returns
        (content_type, response) instead of a parsed body — same error
        handling (401/403/other) as _request, just no .json() call."""
        try:
            response = self._client.request(method, path.lstrip("/"), params=params)
        except httpx.RequestError as exc:
            raise IotamineAPIError(None, f"Could not reach the Iotamine API: {exc}") from exc
        if response.status_code == 401:
            raise IotamineAPIError(401, "This API key is invalid, inactive, or IP-restricted. Check it on your Iotamine dashboard's API Keys page.")
        if response.status_code == 403:
            raise IotamineAPIError(403, _extract_message(response) or "This API key doesn't have permission for this action — it may be read-only (see APIKey.scope on your dashboard).")
        if not response.is_success:
            raise IotamineAPIError(response.status_code, _extract_message(response))
        return response.headers.get("content-type", ""), response

    def get(self, path, params=None):
        return self._request("GET", path, params=params)

    def post(self, path, json=None):
        return self._request("POST", path, json=json)

    def patch(self, path, json=None):
        return self._request("PATCH", path, json=json)

    def put(self, path, json=None):
        return self._request("PUT", path, json=json)

    def delete(self, path, json=None):
        return self._request("DELETE", path, json=json)

    def get_list(self, path, params=None):
        """Normalizes the two list shapes the real API actually returns
        (see individual view comments — some endpoints always paginate,
        some only conditionally): a plain JSON array, or DRF's
        {count, next, previous, results} envelope. Callers always get a
        plain list back either way — an MCP tool has no use for a
        pagination cursor a model can't act on."""
        data = self.get(path, params=params)
        if isinstance(data, dict) and "results" in data:
            return data["results"]
        if isinstance(data, list):
            return data
        return [] if data is None else [data]


_MAX_CACHED_CLIENTS = 512
"""Bound on ClientPool's size — see ClientPool docstring."""


class ClientPool:
    """Bounded per-token IotamineClient cache for streamable-http's
    multi-tenant mode: one real client (and its pooled httpx connection)
    per distinct bearer token, reused across a session's many tool calls
    instead of rebuilt — and reconnected — on every single one. Unused
    in stdio mode, which only ever has the one process-wide client.

    Bounded (not a plain dict) so a public server can't be made to grow
    this forever by cycling through tokens — the oldest-used entry is
    evicted (and its connection closed) once the cap is hit.
    """

    def __init__(self, base_url=None, max_size=_MAX_CACHED_CLIENTS):
        self._base_url = base_url
        self._max_size = max_size
        self._lock = threading.Lock()
        self._by_token = OrderedDict()

    def get(self, token):
        with self._lock:
            client = self._by_token.get(token)
            if client is not None:
                self._by_token.move_to_end(token)
                return client
            client = IotamineClient(api_key=token, base_url=self._base_url)
            self._by_token[token] = client
            if len(self._by_token) > self._max_size:
                _, evicted = self._by_token.popitem(last=False)
                evicted.close()
            return client

    def close(self):
        with self._lock:
            for client in self._by_token.values():
                client.close()
            self._by_token.clear()


class ScopedClient:
    """Drop-in stand-in for a real IotamineClient — build_server() hands
    this to every tools.*.register() call exactly like a real one, so
    none of the tool functions closed over it (they all just call
    client.get(...)/post(...)/etc.) need to know or care which mode the
    server is running in.

    Every attribute access resolves, at call time, to whichever client
    is "current" for this request:

    - stdio: always `default` — the single process-wide client built
      from IOTAMINE_API_KEY at startup. This is the only mode that
      existed before streamable-http support, and its behavior here is
      unchanged: get_access_token() is always None outside an HTTP
      request, so resolve() always falls through to `default`.
    - streamable-http: the SDK's bearer-auth layer (see auth.py's
      IotamineTokenVerifier, wired up in server.py) has already
      verified the caller's token before any tool runs and stashed it
      in a contextvar; resolve() turns that into (and caches, via
      `pool`) a real per-token IotamineClient — so two concurrent
      requests from two different Iotamine accounts each transparently
      talk to the backend as themselves, never as each other.
    """

    def __init__(self, default, pool):
        self._default = default
        self._pool = pool

    def _resolve(self):
        from mcp.server.auth.middleware.auth_context import get_access_token

        token = get_access_token()
        if token is not None:
            return self._pool.get(token.token)
        if self._default is not None:
            return self._default
        # http mode with no default client configured (build_http_server's
        # normal case) reaching here means RequireAuthMiddleware let an
        # unauthenticated request through to a tool call — shouldn't
        # happen, but fail with a clear message rather than an opaque
        # AttributeError off of None.
        raise ToolError("No authenticated Iotamine account for this request — the connection's bearer token is missing or was not verified.")

    def __getattr__(self, name):
        return getattr(self._resolve(), name)
