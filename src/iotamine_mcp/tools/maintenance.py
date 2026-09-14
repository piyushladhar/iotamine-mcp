"""Maintenance event tool — maintenance.views.MaintenanceEventViewSet.
Read-only from here (creating/managing a maintenance notice is a
staff-only capability, not something a customer's own key can do
regardless)."""
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)


def register(mcp, client):
    @mcp.tool(annotations=READ_ONLY)
    def list_maintenance_events() -> list:
        """List maintenance events relevant to this account — anything
        affecting a VPS/region this account has infrastructure in, plus
        anything scoped account-wide. Includes recently-completed events
        (within the last 24h), not just currently-active ones."""
        return client.get_list("maintenance-events/", params={"page_size": 50})
