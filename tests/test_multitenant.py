"""streamable-http's multi-tenant mode: ClientPool, ScopedClient, and
IotamineTokenVerifier. The end-to-end proof that two different bearer
tokens genuinely reach the real backend as two different accounts (not
mocked here) was done live against a running dev server — see the
session notes; this file covers the pieces in isolation."""
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from iotamine_mcp.auth import IotamineTokenVerifier
from iotamine_mcp.client import ClientPool, IotamineClient, ScopedClient


# ── ClientPool ─────────────────────────────────────────────────────

def test_pool_returns_the_same_client_instance_for_the_same_token():
    pool = ClientPool(base_url="http://example.test/api/")
    a = pool.get("token-a")
    b = pool.get("token-a")
    assert a is b
    pool.close()


def test_pool_returns_different_clients_for_different_tokens():
    pool = ClientPool(base_url="http://example.test/api/")
    a = pool.get("token-a")
    b = pool.get("token-b")
    assert a is not b
    assert a.api_key == "token-a"
    assert b.api_key == "token-b"
    pool.close()


def test_pool_evicts_the_oldest_entry_once_past_max_size():
    pool = ClientPool(base_url="http://example.test/api/", max_size=2)
    first = pool.get("token-1")
    pool.get("token-2")
    pool.get("token-3")  # pushes token-1 out
    again = pool.get("token-1")
    assert again is not first  # rebuilt, not reused — it was evicted
    pool.close()


def test_pool_close_closes_every_cached_client():
    pool = ClientPool(base_url="http://example.test/api/")
    client = pool.get("token-a")
    client.close = MagicMock()
    pool.close()
    client.close.assert_called_once()


# ── ScopedClient ───────────────────────────────────────────────────

def test_scoped_client_falls_through_to_default_with_no_access_token(monkeypatch):
    """stdio's exact situation: get_access_token() is always None outside
    an HTTP request, so every call must resolve to `default`."""
    monkeypatch.setattr("mcp.server.auth.middleware.auth_context.get_access_token", lambda: None)
    default = MagicMock()
    scoped = ScopedClient(default=default, pool=ClientPool())
    scoped.get("vps/")
    default.get.assert_called_once_with("vps/")


def test_scoped_client_resolves_a_per_token_client_from_the_pool(monkeypatch):
    fake_token = MagicMock(token="real-key-123")
    monkeypatch.setattr("mcp.server.auth.middleware.auth_context.get_access_token", lambda: fake_token)
    pool = MagicMock()
    resolved = MagicMock()
    pool.get.return_value = resolved
    scoped = ScopedClient(default=None, pool=pool)
    scoped.get("vps/")
    pool.get.assert_called_once_with("real-key-123")
    resolved.get.assert_called_once_with("vps/")


def test_scoped_client_two_tokens_never_cross_talk(monkeypatch):
    """The actual isolation guarantee this whole mechanism exists for:
    two different callers in the same process must never resolve to
    each other's client."""
    pool = ClientPool(base_url="http://example.test/api/")
    scoped = ScopedClient(default=None, pool=pool)

    monkeypatch.setattr("mcp.server.auth.middleware.auth_context.get_access_token", lambda: MagicMock(token="token-a"))
    client_a = scoped._resolve()

    monkeypatch.setattr("mcp.server.auth.middleware.auth_context.get_access_token", lambda: MagicMock(token="token-b"))
    client_b = scoped._resolve()

    assert client_a is not client_b
    assert client_a.api_key == "token-a"
    assert client_b.api_key == "token-b"
    pool.close()


def test_scoped_client_raises_a_clear_error_with_no_token_and_no_default(monkeypatch):
    from mcp.server.mcpserver.exceptions import ToolError

    monkeypatch.setattr("mcp.server.auth.middleware.auth_context.get_access_token", lambda: None)
    scoped = ScopedClient(default=None, pool=ClientPool())
    with pytest.raises(ToolError, match="No authenticated Iotamine account"):
        scoped.get("vps/")


# ── IotamineTokenVerifier ──────────────────────────────────────────

@respx.mock
async def test_verifier_accepts_a_token_the_backend_confirms():
    respx.get("http://example.test/api/users/me/").mock(return_value=httpx.Response(200, json={"id": 1}))
    verifier = IotamineTokenVerifier("http://example.test/api/", resource_server_url="http://mcp.example.test/mcp")
    result = await verifier.verify_token("good-key")
    await verifier.aclose()
    assert result is not None
    assert result.token == "good-key"
    assert result.resource == "http://mcp.example.test/mcp"


@respx.mock
async def test_verifier_rejects_a_token_the_backend_401s():
    respx.get("http://example.test/api/users/me/").mock(return_value=httpx.Response(401))
    verifier = IotamineTokenVerifier("http://example.test/api/")
    result = await verifier.verify_token("bad-key")
    await verifier.aclose()
    assert result is None


@respx.mock
async def test_verifier_fails_closed_when_the_backend_is_unreachable():
    respx.get("http://example.test/api/users/me/").mock(side_effect=httpx.ConnectError("refused"))
    verifier = IotamineTokenVerifier("http://example.test/api/")
    result = await verifier.verify_token("some-key")
    await verifier.aclose()
    assert result is None


@respx.mock
async def test_verifier_caches_a_result_instead_of_re_checking_every_call():
    route = respx.get("http://example.test/api/users/me/").mock(return_value=httpx.Response(200, json={"id": 1}))
    verifier = IotamineTokenVerifier("http://example.test/api/")
    await verifier.verify_token("good-key")
    await verifier.verify_token("good-key")
    await verifier.aclose()
    assert route.call_count == 1


@respx.mock
async def test_verifier_sends_the_token_as_an_api_key_header():
    route = respx.get("http://example.test/api/users/me/").mock(return_value=httpx.Response(200, json={"id": 1}))
    verifier = IotamineTokenVerifier("http://example.test/api/")
    await verifier.verify_token("my-token")
    await verifier.aclose()
    assert route.calls.last.request.headers["Authorization"] == "Api-Key my-token"
