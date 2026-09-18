"""Billing/account tools — quota, balance, invoices, usage, wallet
transactions. Read-only except pay_invoice_from_credit, the one
customer-reachable write action on core.views.InvoiceViewSet
(send_reminder/cancel/reactivate/update/destroy all require a staff
capability or superuser and are correctly absent here — a customer's
own API key can never satisfy those regardless of what this server
exposes). get_pdf isn't wrapped either: it returns a raw PDF binary,
not JSON, with nothing a text-only tool result can usefully do with it
— point the user at the dashboard's own invoice page for a real
download.
"""
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


def register(mcp, client):
    @mcp.tool(annotations=READ_ONLY)
    def get_quota() -> dict:
        """This account's resource limits (VPS count / vCPU / RAM / disk
        / IP caps), current usage against each, and its current tier —
        core.quotas's balance-driven tier system, exactly what the
        dashboard's own Tier page shows. Check this (and get_account_
        balance) before recommending create_vps/purchase_ip/
        purchase_volume/resize_vps/add_disk_to_vps/add_ip_to_vps — the
        real API rejects any of those cleanly if either is insufficient,
        but knowing in advance means a recommendation can say why rather
        than the user hitting a rejection blind."""
        return client.get("account/quota/")

    @mcp.tool(annotations=READ_ONLY)
    def get_account_balance() -> dict:
        """This account's current wallet balance, currency, and basic
        profile (name, email, country, verification status). The
        balance is real money already paid in (a prepaid wallet, not a
        credit line) — every hourly VPS/IP/volume charge is deducted
        from it continuously, and it's what pay_invoice_from_credit
        draws against."""
        return client.get("users/me/")

    @mcp.tool(annotations=READ_ONLY)
    def list_invoices() -> list:
        """List every invoice on this account (paid, unpaid, and
        cancelled — see get_invoice_summary for the lifetime totals
        behind each status), most recent first — amount, status, due
        date, and full line items (no separate single-invoice tool
        exists; this already carries everything one would return).
        billing_info on each invoice is that invoice's own frozen
        billing name/address/tax ID as of the day it was issued — never
        the account's current profile, even if it's changed since; use
        get_account_balance for the current one."""
        return client.get_list("invoices/", params={"page_size": 100})

    @mcp.tool(annotations=READ_ONLY)
    def get_invoice_summary() -> dict:
        """Lifetime Paid/Unpaid/Cancelled invoice totals, grouped by
        currency (almost always just one) — the always-on KPI strip the
        dashboard's own invoice list shows above the (filterable,
        paginated) table list_invoices mirrors. Independent of any
        status filter; this is the account's full history regardless."""
        return client.get("invoices/summary/")

    @mcp.tool(annotations=WRITE)
    def pay_invoice_from_credit(invoice_id: str, confirm: bool = False) -> dict:
        """Pay an unpaid invoice using this account's own wallet
        balance (get_account_balance) — no external payment gateway
        involved, so this is the one invoice-payment path that can
        complete in a single tool call. Requires confirm=true, and
        always tell the user the amount being deducted first. The real
        API refuses this (400/403) when: the invoice is already paid or
        cancelled; the balance is insufficient (top up first — that
        itself needs a real payment gateway checkout this server can't
        drive, so point the user to the dashboard's Billing page for
        it); or the invoice is itself a Cloud Credit Purchase (a wallet
        top-up invoice can't be paid out of the very balance it exists
        to add — that would be circular)."""
        if not confirm:
            raise ToolError("Set confirm=true to pay this invoice from your account balance.")
        return client.post(f"invoices/{invoice_id}/pay/", json={"gateway": "credit"})

    @mcp.tool(annotations=READ_ONLY)
    def get_usage_billing() -> dict:
        """Current unbilled usage (a live snapshot) plus historical
        already-billed cost broken down by Compute/Storage/Network/Other
        — the same data the dashboard's own Usage Billing page shows."""
        return client.get("usage-billing/overview/")

    @mcp.tool(annotations=READ_ONLY)
    def get_usage_billing_line_items(status: str = "unbilled") -> list:
        """Row-by-row usage detail backing get_usage_billing's own
        summary — one row per VPS/volume/IP/bandwidth charge. status is
        "unbilled" (default, a live snapshot) or "billed" (everything
        already charged)."""
        return client.get_list("usage-billing/line-items/", params={"status": status})

    @mcp.tool(annotations=READ_ONLY)
    def list_transactions() -> list:
        """List every entry in this account's wallet ledger, most
        recent first — every balance_before/balance_after change, not
        just top-ups. transaction_type is one of: usage (a metered
        charge deducted), payment (a gateway payment credited), invoice
        (an invoice paid from this balance — see pay_invoice_from_
        credit), funds (a wallet top-up credited — historically also
        labeled "Add Funds"/"Cloud Credit Purchase" on the invoice that
        created it), refund, or adjustment (a manual staff correction).
        status is pending/completed/failed/reversed — a transaction
        that's still pending or has failed hasn't actually moved the
        balance yet."""
        return client.get_list("transactions/", params={"page_size": 100})

    @mcp.tool(annotations=READ_ONLY)
    def get_transaction(transaction_id: str) -> dict:
        """Get full detail for one transaction by its id — see
        list_transactions for what transaction_type/status mean."""
        return client.get(f"transactions/{transaction_id}/")
