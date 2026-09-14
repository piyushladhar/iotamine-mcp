"""Infrastructure inventory tools — everything else a VPS is built from
or attached to: OS images, regions, IPs, volumes, SSH keys.
"""
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)


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
    def list_ip_addresses() -> list:
        """List every standalone IP address on this account (attached
        to a VPS or not), independent of any VPS — see how a boot
        volume/IP can be detached and reattached on Iotamine."""
        return client.get_list("ip-addresses/", params={"page_size": 200})

    @mcp.tool(annotations=READ_ONLY)
    def list_volumes() -> list:
        """List every standalone storage volume on this account
        (attached to a VPS or not, boot or non-boot)."""
        return client.get_list("volumes/", params={"page_size": 200})

    @mcp.tool(annotations=READ_ONLY)
    def list_ssh_keys() -> list:
        """List every SSH public key saved on this account (title only
        — the public key material itself, never anything private)."""
        return client.get_list("sshkey/", params={"page_size": 200})
