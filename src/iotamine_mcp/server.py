"""Builds the MCP server: one MCPServer instance, one IotamineClient,
every tools.* module registers its own tools against both. No tool
logic lives in this file — see iotamine_mcp/tools/ for that."""
from mcp.server.mcpserver import MCPServer

from iotamine_mcp.client import IotamineClient
from iotamine_mcp.tools import activity, billing, export, infra, network, storage, vps

INSTRUCTIONS = (
    "Tools for managing your Iotamine cloud VPS account — the same actions available on "
    "the dashboard: VPS lifecycle (create/destroy/start/stop/poweroff/restart/reinstall/"
    "resize/hostname/password), console access, monitoring and backups, standalone IP "
    "addresses and storage volumes (purchase/attach/detach/release), SSH keys, firewall "
    "rules, activity logs, and data export. Read-only tools never change anything. Every "
    "write tool that costs money, is destructive, or otherwise changes account state "
    "requires an explicit confirm=true argument — always tell the user exactly what will "
    "happen (and its cost, if any) before setting it. Data comes directly from the same "
    "API https://iotamine.com's own dashboard uses."
)


def build_server(client=None):
    mcp = MCPServer(name="iotamine", title="Iotamine Cloud", instructions=INSTRUCTIONS)
    client = client or IotamineClient()
    vps.register(mcp, client)
    billing.register(mcp, client)
    infra.register(mcp, client)
    network.register(mcp, client)
    storage.register(mcp, client)
    activity.register(mcp, client)
    export.register(mcp, client)
    return mcp, client
