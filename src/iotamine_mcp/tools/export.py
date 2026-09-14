"""Data export tool — core.views.UserDataExportView. Self-service "a
copy of your own data," one category at a time, same as the dashboard's
own Export Data page.
"""
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from iotamine_mcp.client import IotamineAPIError

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)

CATEGORIES = {
    "profile", "activity", "invoices", "transactions", "usage",
    "ip_addresses", "volumes", "vms", "firewall_rules",
}


def register(mcp, client):
    @mcp.tool(annotations=READ_ONLY)
    def export_data(category: str, ids: list = None) -> str:
        """Export a copy of this account's own data as CSV, one
        category at a time. category must be one of: profile, activity,
        invoices, transactions, usage, ip_addresses, volumes, vms,
        firewall_rules. ids (optional, for invoices/transactions/usage/
        ip_addresses/volumes/vms only) narrows to specific row ids
        instead of exporting everything in that category.

        Note: 'invoices' is a zip archive (one folder per invoice) on
        the real dashboard, which can't be returned as text here — that
        one category should be downloaded from the dashboard's own
        Export Data page instead."""
        if category not in CATEGORIES:
            raise ToolError(f"category must be one of: {', '.join(sorted(CATEGORIES))}")
        params = {}
        if ids:
            params["ids"] = ",".join(str(i) for i in ids)
        content_type, response = client._raw_request("GET", f"users/export/{category}/", params=params)
        if "zip" in content_type:
            raise IotamineAPIError(None, "The 'invoices' category exports as a zip archive, which can't be returned as text here — download it from the dashboard's Export Data page instead.")
        return response.text
