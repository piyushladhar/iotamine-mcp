"""Standalone volume tools — the "detachable storage" side of Iotamine's
own infrastructure model: a volume purchased independent of any VPS,
attachable/detachable/reattachable across VPS instances. Maps to
volume.views.VolumeViewSet.

Purchase/install_os/resize/detach/destroy on this API are asynchronous
(the real endpoint returns a task_id — see get_volume_task_status),
mirroring VPS create's own shape; nothing here blocks waiting for
completion.
"""
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


def register(mcp, client):
    @mcp.tool(annotations=READ_ONLY)
    def list_volumes() -> list:
        """List every standalone storage volume on this account
        (attached to a VPS or not, boot or non-boot)."""
        return client.get_list("volumes/", params={"page_size": 200})

    @mcp.tool(annotations=READ_ONLY)
    def get_volume(volume_id: str) -> dict:
        """Get full detail for one standalone volume by its id."""
        return client.get(f"volumes/{volume_id}/")

    @mcp.tool(annotations=READ_ONLY)
    def list_available_volume_sizes(pop: int) -> dict:
        """List the volume sizes/kinds purchasable in a given region
        (Point of Presence id from list_regions)."""
        return client.get("volumes/available/", params={"pop": pop})

    @mcp.tool(annotations=WRITE)
    def purchase_volume(pop: int, size_gb: int, kind: str = "data", vps_id: str = None, confirm: bool = False) -> dict:
        """Purchase a new standalone volume. Spends real money (checked
        against balance and quota) — requires confirm=true. kind is
        "data" or "boot" (a boot volume becomes a future VPS's boot
        disk, not attached to anything existing). In a region without
        fleet-volume support, a "data" volume must instead be pinned to
        an existing VPS at purchase time via vps_id (a "boot" volume
        isn't purchasable there at all — the real API's error message
        will say so if this applies).

        Asynchronous — returns a task_id immediately; poll
        get_volume_task_status for completion, then list_volumes to see
        the finished volume."""
        if not confirm:
            raise ToolError("Set confirm=true to purchase this volume — it spends real money.")
        payload = {"pop": pop, "size_gb": size_gb, "kind": kind}
        if vps_id:
            payload["vps_id"] = vps_id
        return client.post("volumes/purchase/", json=payload)

    @mcp.tool(annotations=READ_ONLY)
    def get_volume_task_status(task_id: str) -> dict:
        """Check the status of an async volume operation (purchase,
        attach, detach, destroy, install_os, resize) by the task_id
        those calls return."""
        return client.get(f"volumes/task-status/{task_id}/")

    @mcp.tool(annotations=READ_ONLY)
    def list_attachable_vps_for_volume(volume_id: str) -> list:
        """List this account's VPS instances eligible to attach this
        volume to (same region, stopped where required)."""
        return client.get_list(f"volumes/{volume_id}/attachable_vps/")

    @mcp.tool(annotations=READ_ONLY)
    def list_available_os_for_volume(volume_id: str) -> list:
        """List operating systems available to install onto this
        volume via install_os_on_volume."""
        return client.get_list(f"volumes/{volume_id}/available_os/")

    @mcp.tool(annotations=DESTRUCTIVE)
    def install_os_on_volume(volume_id: str, operating_system: int, ssh_public_key: str = "",
                              root_password: str = "", confirm: bool = False) -> dict:
        """Install a fresh OS onto this standalone volume, overwriting
        whatever's on it entirely. Irreversible — requires confirm=true.
        The volume must be detached from any VPS first (detach_volume).
        A Windows OS requires root_password; anything else needs at
        least one of ssh_public_key/root_password. Asynchronous — poll
        get_volume_task_status."""
        if not confirm:
            raise ToolError("Set confirm=true to install an OS on this volume — everything on it will be overwritten.")
        payload = {"operating_system": operating_system}
        if ssh_public_key:
            payload["ssh_public_key"] = ssh_public_key
        if root_password:
            payload["root_password"] = root_password
        return client.post(f"volumes/{volume_id}/install_os/", json=payload)

    @mcp.tool(annotations=WRITE)
    def resize_volume(volume_id: str, size_gb: int, confirm: bool = False) -> dict:
        """Resize a standalone volume (grow only). Spends real money —
        requires confirm=true. Asynchronous — poll
        get_volume_task_status."""
        if not confirm:
            raise ToolError("Set confirm=true to resize this volume — it spends real money.")
        return client.post(f"volumes/{volume_id}/resize/", json={"size_gb": size_gb})

    @mcp.tool(annotations=WRITE)
    def attach_volume(volume_id: str, vps_id: str, confirm: bool = False) -> dict:
        """Attach a standalone volume to a VPS (same region). Requires
        confirm=true. Asynchronous — poll get_volume_task_status."""
        if not confirm:
            raise ToolError("Set confirm=true to attach this volume.")
        return client.post(f"volumes/{volume_id}/attach/", json={"vps": vps_id})

    @mcp.tool(annotations=WRITE)
    def detach_volume(volume_id: str, confirm: bool = False) -> dict:
        """Detach a standalone volume from whatever VPS it's currently
        attached to (kept, not released — the volume itself still
        belongs to this account). Requires confirm=true. Asynchronous —
        poll get_volume_task_status."""
        if not confirm:
            raise ToolError("Set confirm=true to detach this volume.")
        return client.post(f"volumes/{volume_id}/detach/")

    @mcp.tool(annotations=WRITE)
    def set_volume_as_boot(volume_id: str, vps_id: str, confirm: bool = False) -> dict:
        """Set this volume as a VPS's boot disk. The VPS must already be
        stopped — the same requirement vps.py's change_vps_hostname
        documents (stop it first with stop_vps). Requires confirm=true."""
        if not confirm:
            raise ToolError("Set confirm=true to set this volume as a boot disk.")
        return client.post(f"volumes/{volume_id}/set_as_boot/", json={"vps": vps_id})

    @mcp.tool(annotations=DESTRUCTIVE)
    def release_volume(volume_id: str, confirm: bool = False) -> dict:
        """Permanently release (delete) a standalone volume — not just
        detach it. Irreversible — requires confirm=true. Asynchronous —
        poll get_volume_task_status."""
        if not confirm:
            raise ToolError("Set confirm=true to release this volume — this permanently deletes it.")
        return client.delete(f"volumes/{volume_id}/")
