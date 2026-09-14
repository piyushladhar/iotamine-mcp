"""VPS read tools — thin passthroughs to vps.views.VPSViewSet. Response
shapes are whatever VPSSerializer already returns; nothing here
re-derives or reshapes them, so they never drift out of sync with the
real API.
"""
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)


def register(mcp, client):
    @mcp.tool(annotations=READ_ONLY)
    def list_vps() -> list:
        """List every VPS instance on this Iotamine account — hostname,
        status, specs (cores/ram/disk/traffic), IP addresses, OS, node
        location, and machine_status (Running/Stopped/Building/...) for
        each one."""
        return client.get_list("vps/", params={"all": "true"})

    @mcp.tool(annotations=READ_ONLY)
    def get_vps(vps_id: str) -> dict:
        """Get full detail for one VPS instance by its id (a UUID, as
        returned by list_vps's own "id" field)."""
        return client.get(f"vps/{vps_id}/")
