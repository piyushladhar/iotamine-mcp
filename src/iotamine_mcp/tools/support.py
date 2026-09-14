"""Support ticket tools — ticket.views.TicketViewSet/TicketReplyViewSet/
DepartmentViewSet. Not read-only-vs-write in the usual "spends money or
destroys something" sense — nothing here costs anything or is
irreversible, so create_ticket/reply_to_ticket don't require
confirm=true, unlike VPS/billing write tools.
"""
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


def register(mcp, client):
    @mcp.tool(annotations=READ_ONLY)
    def list_ticket_departments() -> list:
        """List support departments a ticket can be filed under — the
        department_id source for create_ticket."""
        return client.get_list("departments/", params={"page_size": 100})

    @mcp.tool(annotations=READ_ONLY)
    def list_tickets(search: str = "") -> list:
        """List this account's support tickets, most recently updated
        first. search (optional) matches subject/department/status."""
        params = {"page_size": 50}
        if search:
            params["search"] = search
        return client.get_list("tickets/", params=params)

    @mcp.tool(annotations=READ_ONLY)
    def get_ticket(ticket_id: str) -> dict:
        """Get full detail for one ticket, including its replies."""
        return client.get(f"tickets/{ticket_id}/")

    @mcp.tool(annotations=WRITE)
    def create_ticket(subject: str, message: str, department_id: int,
                       priority: str = "medium", vps_id: str = None) -> dict:
        """Open a new support ticket with an opening message. priority
        is one of: low, medium, high. vps_id (optional) links the
        ticket to a specific VPS (an id from list_vps) if the issue is
        about one."""
        if priority not in ("low", "medium", "high"):
            raise ToolError("priority must be one of: low, medium, high")
        payload = {"subject": subject, "priority": priority, "department_id": department_id}
        if vps_id:
            payload["vps_id"] = vps_id
        ticket = client.post("tickets/", json=payload)
        # The real API's own create() never turns a customer's own
        # opening `message` into the first reply (it only does that for
        # a superuser opening a ticket on someone else's behalf) — the
        # dashboard's own create flow is genuinely two calls, confirmed
        # by reading pages/tickets/create.vue directly, not assumed.
        # Mirrored here so create_ticket behaves the way it obviously
        # should from the caller's perspective: one call, message
        # attached.
        client.post(f"tickets/{ticket['id']}/replies/", json={"ticket": ticket["id"], "message": message})
        return client.get(f"tickets/{ticket['id']}/")

    @mcp.tool(annotations=READ_ONLY)
    def list_ticket_replies(ticket_id: str) -> list:
        """List every reply on a ticket (same data get_ticket's own
        "replies" field already includes — this is the paginated
        version, for a ticket with a long conversation)."""
        return client.get_list(f"tickets/{ticket_id}/replies/")

    @mcp.tool(annotations=WRITE)
    def reply_to_ticket(ticket_id: str, message: str) -> dict:
        """Post a reply on an existing ticket."""
        return client.post(f"tickets/{ticket_id}/replies/", json={"ticket": ticket_id, "message": message})
