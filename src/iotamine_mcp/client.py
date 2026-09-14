"""Thin wrapper around the real Iotamine REST API (iotamine_backend_django)
— every tool in iotamine_mcp.tools goes through this, and nothing here
duplicates any business logic the backend already owns. Auth is a plain
Iotamine API key (core.authentications.APIKeyAuthentication), sent the
same way any other REST client already sends one.
"""
import os

import httpx

DEFAULT_BASE_URL = "https://iotamine.com/api/"


class IotamineConfigError(Exception):
    """Raised at startup when IOTAMINE_API_KEY isn't set — a clear,
    early failure instead of every tool call failing with a confusing
    401 one at a time."""


class IotamineAPIError(Exception):
    """Wraps a non-2xx response from the real API. `message` is the
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

    def get(self, path, params=None):
        return self._request("GET", path, params=params)

    def post(self, path, json=None):
        return self._request("POST", path, json=json)

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
