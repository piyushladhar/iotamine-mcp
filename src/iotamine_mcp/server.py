"""Builds the MCP server: one MCPServer instance, one IotamineClient,
every tools.* module registers its own tools against both. No tool
logic lives in this file — see iotamine_mcp/tools/ for that."""
from mcp.server.mcpserver import MCPServer

from iotamine_mcp.client import IotamineClient
from iotamine_mcp.tools import billing, infra, vps

INSTRUCTIONS = (
    "Tools for managing your Iotamine cloud VPS account: listing and inspecting VPS "
    "instances, checking quota/balance/invoices/usage, and viewing OS images, regions, "
    "IP addresses, volumes, and SSH keys. Every tool in this server is read-only — "
    "nothing here can start, stop, create, resize, or destroy anything, or spend money. "
    "Data comes directly from the same API https://iotamine.com's own dashboard uses."
)


def build_server(client=None):
    mcp = MCPServer(name="iotamine", title="Iotamine Cloud", instructions=INSTRUCTIONS)
    client = client or IotamineClient()
    vps.register(mcp, client)
    billing.register(mcp, client)
    infra.register(mcp, client)
    return mcp, client
