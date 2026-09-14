"""Infrastructure catalog + SSH key tools. OS images and regions are the
read-only catalogs create_vps/purchase_volume draw ids from; standalone
IP addresses and volumes have their own fuller modules (network.py,
storage.py) now that they support the full attach/detach/purchase/
release lifecycle, not just listing.
"""
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


def register(mcp, client):
    @mcp.tool(annotations=READ_ONLY)
    def list_os_images() -> list:
        """List every operating system image available to deploy a VPS
        with (name, distro, virtualization type)."""
        return client.get_list("os/", params={"page_size": 200})

    @mcp.tool(annotations=READ_ONLY)
    def list_regions() -> list:
        """List every Point of Presence (region/data-center location)
        VPS instances can be deployed in."""
        return client.get_list("pop/", params={"page_size": 200})

    @mcp.tool(annotations=READ_ONLY)
    def list_ssh_keys() -> list:
        """List every SSH public key saved on this account (title only
        — the public key material itself, never anything private)."""
        return client.get_list("sshkey/", params={"page_size": 200})

    @mcp.tool(annotations=WRITE)
    def create_ssh_key(title: str, ssh_key: str, confirm: bool = False) -> dict:
        """Save a new SSH public key to this account, for installing
        onto future VPS instances via create_vps's own ssh_key
        parameter. Requires confirm=true. ssh_key is the public key
        material (e.g. the contents of id_ed25519.pub) — never a
        private key."""
        if not confirm:
            raise ToolError("Set confirm=true to save this SSH key.")
        return client.post("sshkey/", json={"title": title, "ssh_key": ssh_key})

    @mcp.tool(annotations=DESTRUCTIVE)
    def delete_ssh_key(ssh_key_id: str, confirm: bool = False) -> dict:
        """Permanently delete a saved SSH key from this account.
        Irreversible — requires confirm=true. Does not affect VPS
        instances it's already been installed onto, only future
        deploys."""
        if not confirm:
            raise ToolError("Set confirm=true to delete this SSH key.")
        client.delete(f"sshkey/{ssh_key_id}/")
        return {"status": "deleted", "ssh_key_id": ssh_key_id}
