"""Builds the MCP server: one MCPServer instance, one client (a real
IotamineClient for stdio, a ScopedClient for streamable-http's
multi-tenant mode), every tools.* module registers its own tools
against both. No tool logic lives in this file — see iotamine_mcp/tools/
for that."""
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer

from iotamine_mcp.auth import IotamineTokenVerifier
from iotamine_mcp.client import ClientPool, DEFAULT_BASE_URL, IotamineClient, ScopedClient
from iotamine_mcp.tools import activity, billing, export, infra, maintenance, network, storage, support, vps

INSTRUCTIONS = (
    "Tools for managing your Iotamine cloud VPS account — the same actions available on "
    "the dashboard: VPS lifecycle (create/destroy/start/stop/poweroff/restart/reinstall/"
    "resize/hostname/password), console access, monitoring and backups, standalone IP "
    "addresses and storage volumes (purchase/attach/detach/release), SSH keys, firewall "
    "rules, activity logs, data export, transactions, maintenance notices, and support "
    "tickets. Read-only tools never change anything. Every write tool that costs money, is "
    "destructive, or otherwise changes account state requires an explicit confirm=true "
    "argument — always tell the user exactly what will happen (and its cost, if any) "
    "before setting it. Data comes directly from the same API https://iotamine.com's own "
    "dashboard uses."
)


def _register_all(mcp, client):
    vps.register(mcp, client)
    billing.register(mcp, client)
    infra.register(mcp, client)
    network.register(mcp, client)
    storage.register(mcp, client)
    activity.register(mcp, client)
    export.register(mcp, client)
    support.register(mcp, client)
    maintenance.register(mcp, client)


def build_server(client=None):
    """stdio — one process, one account. Unchanged from before
    streamable-http support existed: IOTAMINE_API_KEY (or an explicit
    `client`) is read once at startup and used for every tool call."""
    mcp = MCPServer(name="iotamine", title="Iotamine Cloud", instructions=INSTRUCTIONS)
    client = client or IotamineClient()
    _register_all(mcp, client)
    return mcp, client


def build_http_server(base_url=None, resource_server_url=None, issuer_url=None):
    """streamable-http — one process, many accounts. Each request's own
    bearer token (the OAuth access_token a client obtained from
    iotamine_backend_django's oauth_server, which — see auth.py — is a
    real Iotamine API key) is verified before any tool call is even
    dispatched, and every tool call it goes on to make runs as that
    caller specifically, never a shared/global identity.

    base_url: the real Iotamine REST API tools ultimately call
      (defaults to client.DEFAULT_BASE_URL, same as stdio).
    resource_server_url: this MCP server's own public URL (e.g.
      https://mcp.iotamine.com/mcp) — advertised in the 401
      WWW-Authenticate header and RFC 9728 protected-resource metadata
      so a client knows where to go get a token.
    issuer_url: the OAuth authorization server's URL (e.g.
      https://iotamine.com) — the oauth_server Django app.

    Returns (mcp, verifier, pool) — verifier and pool both need
    closing (verifier.aclose(), pool.close()) on shutdown.
    """
    resolved_base_url = base_url or DEFAULT_BASE_URL
    verifier = IotamineTokenVerifier(resolved_base_url, resource_server_url=resource_server_url)
    auth_settings = AuthSettings(
        issuer_url=issuer_url,
        resource_server_url=resource_server_url,
        # Real scope enforcement (read_only vs read_write) happens on
        # every actual API call via core.authentications
        # .APIKeyAuthentication — this gate only asks "is the token
        # live at all", so it has no scopes of its own to require.
        required_scopes=None,
        # Our tokens don't embed a `resource`/audience claim the way a
        # JWT-based verifier's would — nothing here to validate against
        # resource_server_url beyond "is this key active" (see auth.py).
        validate_token_resource=False,
    )
    mcp = MCPServer(
        name="iotamine",
        title="Iotamine Cloud",
        instructions=INSTRUCTIONS,
        token_verifier=verifier,
        auth=auth_settings,
    )
    pool = ClientPool(base_url=resolved_base_url)
    client = ScopedClient(default=None, pool=pool)
    _register_all(mcp, client)
    return mcp, verifier, pool
