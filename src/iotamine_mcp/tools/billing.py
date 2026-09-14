"""Billing/account read tools — quota, balance, invoices, usage."""
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)


def register(mcp, client):
    @mcp.tool(annotations=READ_ONLY)
    def get_quota() -> dict:
        """This account's resource limits (VPS count / vCPU / RAM / disk
        / IP caps), current usage against each, and its current tier —
        core.quotas's balance-driven tier system, exactly what the
        dashboard's own Tier page shows."""
        return client.get("account/quota/")

    @mcp.tool(annotations=READ_ONLY)
    def get_account_balance() -> dict:
        """This account's current wallet balance, currency, and basic
        profile (name, email, country, verification status)."""
        return client.get("users/me/")

    @mcp.tool(annotations=READ_ONLY)
    def list_invoices() -> list:
        """List every invoice on this account (paid, unpaid, and
        cancelled), most recent first — amount, status, due date, and
        line items."""
        return client.get_list("invoices/", params={"page_size": 100})

    @mcp.tool(annotations=READ_ONLY)
    def get_usage_billing() -> dict:
        """Current unbilled usage (a live snapshot) plus historical
        already-billed cost broken down by Compute/Storage/Network/Other
        — the same data the dashboard's own Usage Billing page shows."""
        return client.get("usage-billing/overview/")
