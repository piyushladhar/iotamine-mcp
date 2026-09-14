"""Standalone IP address tools — the "detachable networking" side of
Iotamine's own infrastructure model, mirroring storage.py's volumes
exactly. Maps to ip_address.views.IPAddressViewSet.
"""
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


def register(mcp, client):
    @mcp.tool(annotations=READ_ONLY)
    def list_ip_addresses() -> list:
        """List every standalone IP address on this account (attached
        to a VPS or not)."""
        return client.get_list("ip-addresses/", params={"page_size": 200})

    @mcp.tool(annotations=READ_ONLY)
    def get_ip_address(ip_id: str) -> dict:
        """Get full detail for one standalone IP address by its id."""
        return client.get(f"ip-addresses/{ip_id}/")

    @mcp.tool(annotations=READ_ONLY)
    def check_available_ips(pop: int) -> dict:
        """How many standalone IP addresses can be purchased in a given
        region (Point of Presence id from list_regions) right now, and
        at what price."""
        return client.get("ip-addresses/available/", params={"pop": pop})

    @mcp.tool(annotations=WRITE)
    def purchase_ip(pop: int, quantity: int, confirm: bool = False) -> list:
        """Purchase one or more new standalone IP addresses in a region
        (Point of Presence id from list_regions). At most 20 at a time.
        Spends real money (checked against balance and quota) —
        requires confirm=true. Synchronous — the purchased addresses
        are returned directly, no task to poll."""
        if not confirm:
            raise ToolError("Set confirm=true to purchase IP address(es) — it spends real money.")
        return client.post("ip-addresses/purchase/", json={"pop": pop, "quantity": quantity})

    @mcp.tool(annotations=READ_ONLY)
    def list_attachable_vps_for_ip(ip_id: str) -> list:
        """List this account's VPS instances eligible to attach this IP
        to (same region as the IP)."""
        return client.get_list(f"ip-addresses/{ip_id}/attachable_vps/")

    @mcp.tool(annotations=WRITE)
    def attach_ip(ip_id: str, vps_id: str, confirm: bool = False) -> dict:
        """Attach a standalone IP address to a VPS (same region).
        Requires confirm=true."""
        if not confirm:
            raise ToolError("Set confirm=true to attach this IP address.")
        return client.post(f"ip-addresses/{ip_id}/attach/", json={"vps": vps_id})

    @mcp.tool(annotations=WRITE)
    def detach_ip(ip_id: str, confirm: bool = False) -> dict:
        """Detach a standalone IP address from whatever VPS it's
        currently attached to (kept, not released). Requires
        confirm=true."""
        if not confirm:
            raise ToolError("Set confirm=true to detach this IP address.")
        return client.post(f"ip-addresses/{ip_id}/detach/")

    @mcp.tool(annotations=DESTRUCTIVE)
    def release_ip(ip_id: str, confirm: bool = False) -> dict:
        """Permanently release (delete) a standalone IP address — not
        just detach it. Irreversible — requires confirm=true."""
        if not confirm:
            raise ToolError("Set confirm=true to release this IP address — this permanently deletes it.")
        return client.delete(f"ip-addresses/{ip_id}/")
