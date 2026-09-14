"""Activity log tool — core.views.ActivityViewSet."""
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)


def register(mcp, client):
    @mcp.tool(annotations=READ_ONLY)
    def list_activity_logs(search: str = "") -> list:
        """List this account's activity log — every action taken on
        the account or its VPS instances (sign-ins, VM power/create/
        destroy, IP/volume changes, SSH key changes, ...), newest first.
        search (optional) matches action/description/IP address."""
        params = {"page_size": 50}
        if search:
            params["search"] = search
        return client.get_list("activity/", params=params)
