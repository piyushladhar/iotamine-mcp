"""VPS tools — everything a customer can do to a VPS from the
dashboard: list/inspect, the full power lifecycle, create/destroy,
reinstall, resize, hostname/password change, console, monitoring,
backups, and its own attached disks/IPs/reverse-DNS.

Every write tool here maps straight to vps.views.VPSViewSet — nothing
re-derives or duplicates what that view already validates (balance,
quota, allowed cores/ram/disk values, "must be stopped first" for
hostname/password changes, etc.). A rejection from the real API comes
back to the model as IotamineAPIError with the backend's own message,
not a generic failure.
"""
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
# Power actions are real state changes but not destructive (nothing is
# lost, and they're trivially reversible — start what you stopped) —
# idempotent_hint=False since calling start_vps on an already-running
# VPS isn't a no-op from the caller's perspective the way a GET is.
POWER_ACTION = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


def register(mcp, client):
    # ── Inventory ──────────────────────────────────────────────
    @mcp.tool(annotations=READ_ONLY)
    def list_vps() -> list:
        """List every VPS instance on this Iotamine account — hostname,
        status, specs (cores/ram/disk/traffic), IP addresses, OS, node
        location, and machine_status (Running/Stopped/Building/...) for
        each one."""
        return client.get_list("vps/", params={"all": "true"})

    @mcp.tool(annotations=READ_ONLY)
    def get_vps(vps_id: str) -> dict:
        """Get full detail for one VPS instance by its id (a UUID, as
        returned by list_vps's own "id" field)."""
        return client.get(f"vps/{vps_id}/")

    # ── Create / destroy ───────────────────────────────────────
    @mcp.tool(annotations=WRITE)
    def create_vps(hostname: str, pop: int, cores: int, ram: int,
                    disk: int = None, operating_system: int = None,
                    existing_ip: str = None, existing_boot_volume: str = None,
                    password: str = "", ssh_key: int = None,
                    disable_pwd_auth: bool = False, confirm: bool = False) -> dict:
        """Deploy a new VPS. Spends real money — requires confirm=true,
        and should only be called after explicitly telling the user
        what will be provisioned and its estimated cost (see "Cost"
        below — get this right; it's a common mistake to quote only
        compute and forget the IP).

        pop: a Point of Presence id from list_regions.
        cores/ram/disk: must match one of the allowed values the real
        API enforces — see get_quota or just try a value; a rejection
        names the allowed set.

        Boot disk — exactly one of these two:
        - disk + operating_system: provisions a fresh disk (disk in GB)
          with a fresh OS install (operating_system an id from
          list_os_images). Both required together.
        - existing_boot_volume: boots from a standalone volume this
          account already owns instead (an id from list_volumes, kind
          "boot", not already attached to anything — check first).
          disk/operating_system are ignored if this is given; the
          volume already has its own OS. Costs nothing extra — the
          volume's own cost, if any, was already paid when it was
          purchased.

        IP address — one of these two:
        - Omit existing_ip: a brand-new IP is automatically purchased
          and assigned as part of deployment. This is NOT free — it's
          the pop's own ip_price, billed the same as calling
          purchase_ip separately.
        - existing_ip: attach a standalone IP this account already owns
          instead (an id from list_ip_addresses, not already attached
          to anything — check first). No new IP purchased, no extra
          cost.

        ssh_key: an id from list_ssh_keys, to install onto the new VPS.

        Cost: call list_regions first and use the matching pop's own
        rates. cpu_price/ram_price/disk_price are hourly; ip_price is a
        MONTHLY figure — divide by 720 (30 * 24) before adding it to an
        hourly total, or it'll be off by ~720x (a real mistake this
        tool's docs used to make). Total hourly cost = cores * cpu_price
        + ram * ram_price + (disk * disk_price, only if provisioning a
        fresh disk — 0 if existing_boot_volume is given) + (ip_price /
        720, only if existing_ip is NOT given — 0 if it is). Quote this
        full total, not just compute, before asking for confirmation —
        and say plainly that the IP portion is a recurring monthly
        charge, not a one-time fee.

        Provisioning is asynchronous — this call returns immediately
        with the new VPS's id and is_building=true; poll get_vps for it
        to finish."""
        if not confirm:
            raise ToolError("Set confirm=true to deploy this VPS — this spends real money.")
        payload = {
            "hostname": hostname, "pop": pop, "cores": cores, "ram": ram,
            "traffic": 5, "disable_pwd_auth": disable_pwd_auth,
        }
        if existing_boot_volume:
            payload["existing_boot_volume"] = existing_boot_volume
        else:
            if disk is None or operating_system is None:
                raise ToolError("disk and operating_system are both required unless existing_boot_volume is given.")
            payload["disk"] = disk
            payload["operating_system"] = operating_system
        if existing_ip:
            payload["existing_ip"] = existing_ip
        if password:
            payload["password"] = password
        if ssh_key:
            payload["ssh_key"] = ssh_key
        return client.post("vps/", json=payload)

    @mcp.tool(annotations=DESTRUCTIVE)
    def destroy_vps(vps_id: str, confirm: bool = False, release_ip_ids: list = None, release_disk_ids: list = None) -> dict:
        """Permanently destroy a VPS and, by default, its boot disk.
        Irreversible — requires confirm=true. release_ip_ids/
        release_disk_ids (lists of ids, optional) additionally release
        any attached standalone IPs/volumes instead of just detaching
        them (kept, unreleased, by default — see list_vps's own ip/disk
        fields for their ids)."""
        if not confirm:
            raise ToolError("Set confirm=true to destroy this VPS — this is irreversible.")
        payload = {}
        if release_ip_ids:
            payload["release_ip_ids"] = release_ip_ids
        if release_disk_ids:
            payload["release_disk_ids"] = release_disk_ids
        client.delete(f"vps/{vps_id}/", json=payload or None)
        return {"status": "destroyed", "vps_id": vps_id}

    # ── Power ──────────────────────────────────────────────────
    @mcp.tool(annotations=POWER_ACTION)
    def start_vps(vps_id: str) -> dict:
        """Start a stopped VPS."""
        return client.get(f"vps/{vps_id}/start/")

    @mcp.tool(annotations=POWER_ACTION)
    def stop_vps(vps_id: str) -> dict:
        """Gracefully stop (ACPI shutdown) a running VPS — gives the
        guest OS a chance to shut down cleanly. Use poweroff_vps for a
        hard power-off instead."""
        return client.get(f"vps/{vps_id}/stop/")

    @mcp.tool(annotations=POWER_ACTION)
    def poweroff_vps(vps_id: str) -> dict:
        """Hard power-off a VPS — equivalent to pulling the plug, no
        chance for the guest OS to shut down cleanly. Use stop_vps for a
        graceful shutdown instead."""
        return client.get(f"vps/{vps_id}/poweroff/")

    @mcp.tool(annotations=POWER_ACTION)
    def restart_vps(vps_id: str) -> dict:
        """Restart a running VPS."""
        return client.get(f"vps/{vps_id}/restart/")

    # ── Reinstall / resize / hostname / password ──────────────
    @mcp.tool(annotations=DESTRUCTIVE)
    def reinstall_vps(vps_id: str, os_id: int, new_pass: str, confirm: bool = False) -> dict:
        """Wipes the VPS's boot disk and reinstalls a fresh OS onto it —
        irreversible, everything currently on the disk is lost. The VPS
        must already be stopped, same reason as change_vps_hostname
        (stop it first with stop_vps). Requires confirm=true. os_id: an
        id from list_vps_available_os for this specific VPS (not every
        OS is available on every node)."""
        if not confirm:
            raise ToolError("Set confirm=true to reinstall this VPS — all data on its boot disk will be lost.")
        return client.post(f"vps/{vps_id}/rebuild/", json={"osid": os_id, "new_pass": new_pass, "conf_pass": new_pass})

    @mcp.tool(annotations=WRITE)
    def resize_vps(vps_id: str, cores: int = None, ram: int = None, confirm: bool = False) -> dict:
        """Resize a VPS's CPU/RAM. An increase is checked against
        balance and quota by the real API (fails cleanly if either is
        insufficient); a decrease is always allowed. Requires
        confirm=true for any change. Only pass the value(s) you want to
        change — omit the other."""
        if not confirm:
            raise ToolError("Set confirm=true to resize this VPS.")
        payload = {}
        if cores is not None:
            payload["cores"] = cores
        if ram is not None:
            payload["ram"] = ram
        if not payload:
            raise ToolError("Pass at least one of cores or ram.")
        return client.patch(f"vps/{vps_id}/", json=payload)

    @mcp.tool(annotations=WRITE)
    def change_vps_hostname(vps_id: str, hostname: str, confirm: bool = False) -> dict:
        """Change a VPS's hostname. The VPS must already be stopped —
        this rewrites files on the offline disk image, which isn't safe
        while it's running (stop it first with stop_vps). Requires
        confirm=true."""
        if not confirm:
            raise ToolError("Set confirm=true to change this VPS's hostname.")
        return client.patch(f"vps/{vps_id}/", json={"hostname": hostname})

    @mcp.tool(annotations=WRITE)
    def change_vps_root_password(vps_id: str, new_password: str, confirm: bool = False) -> dict:
        """Change a VPS's root/administrator password. The VPS must
        already be stopped, same reason as change_vps_hostname. Requires
        confirm=true."""
        if not confirm:
            raise ToolError("Set confirm=true to change this VPS's root password.")
        return client.patch(f"vps/{vps_id}/", json={"password": new_password})

    # ── Console / monitoring ───────────────────────────────────
    @mcp.tool(annotations=READ_ONLY)
    def get_vps_console(vps_id: str) -> dict:
        """Get a one-time console (VNC) connection URL and password for
        this VPS — grants live console access, treat the returned
        credentials as sensitive."""
        return client.get(f"vps/{vps_id}/vnc/")

    @mcp.tool(annotations=READ_ONLY)
    def get_vps_stats(vps_id: str) -> dict:
        """Real-time resource stats for a running VPS — CPU, RAM, disk,
        and network usage right now."""
        return client.get(f"vps/{vps_id}/stats/")

    @mcp.tool(annotations=READ_ONLY)
    def get_vps_bandwidth_history(vps_id: str) -> dict:
        """Historical bandwidth usage for one VPS."""
        return client.get(f"vps/{vps_id}/bandwidth_history/")

    @mcp.tool(annotations=READ_ONLY)
    def get_vps_metrics_history(vps_id: str) -> dict:
        """Historical CPU/RAM/disk metrics for one VPS (for graphing
        usage over time, not just the current snapshot get_vps_stats
        gives)."""
        return client.get(f"vps/{vps_id}/metrics_history/")

    @mcp.tool(annotations=READ_ONLY)
    def get_bandwidth_overview() -> dict:
        """Account-wide bandwidth usage overview across every VPS."""
        return client.get("vps/bandwidth_overview/")

    @mcp.tool(annotations=READ_ONLY)
    def get_bandwidth_overview_daily(start: str = None, end: str = None, vps_id: str = None) -> dict:
        """Day-by-day bandwidth (rx/tx GB) over a date range — the
        Bandwidth Usage page's own chart, and the way to actually answer
        "which VPS used the most bandwidth [last week/month]" rather
        than get_bandwidth_overview's current-snapshot total. start/end
        are YYYY-MM-DD (default: the 1st of this month through today;
        range capped at 366 days). vps_id (optional, an id from
        list_vps) narrows to one VPS; omitted, every VPS this account
        owns is summed into a daily fleet total (returned in "daily")
        plus each VPS's own period total for ranking (returned in
        "per_vps", sorted highest-usage first) — not a full per-VPS
        daily series for every VPS at once, so pass vps_id if that level
        of detail is actually needed for one specific VPS."""
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if vps_id:
            params["vps_id"] = vps_id
        return client.get("vps/bandwidth_overview_daily/", params=params)

    @mcp.tool(annotations=READ_ONLY)
    def get_vps_billing(vps_id: str) -> dict:
        """Billing breakdown for one specific VPS."""
        return client.get(f"vps/{vps_id}/billing/")

    @mcp.tool(annotations=READ_ONLY)
    def get_vps_pricing(vps_id: str) -> dict:
        """Current per-unit pricing for this VPS's region — useful
        before calling resize_vps to preview cost. cpu_price/ram_price/
        disk_price are hourly; ip_price is a monthly figure (divide by
        720 for hourly-equivalent) — see list_regions's own note, same
        fields, same units."""
        return client.get(f"vps/{vps_id}/getpricing/")

    @mcp.tool(annotations=READ_ONLY)
    def get_vps_smtp_status(vps_id: str) -> dict:
        """Whether outbound SMTP ports are blocked on this VPS (a
        common anti-abuse policy) — {"supported": false} if this
        VPS's node doesn't support the check at all."""
        return client.get(f"vps/{vps_id}/smtp_status/")

    @mcp.tool(annotations=READ_ONLY)
    def get_vps_build_log(vps_id: str) -> dict:
        """Provisioning log for a VPS that's still building, or was
        recently built — useful for diagnosing a stuck/failed deploy."""
        return client.get(f"vps/{vps_id}/build_log/")

    @mcp.tool(annotations=READ_ONLY)
    def list_vps_available_os(vps_id: str) -> list:
        """List the operating systems available to reinstall onto this
        specific VPS (via reinstall_vps) — not every OS is available on
        every node, unlike list_os_images' full catalog."""
        return client.get_list(f"vps/{vps_id}/available_os/")

    # ── Backups ────────────────────────────────────────────────
    @mcp.tool(annotations=READ_ONLY)
    def list_vps_backups(vps_id: str) -> list:
        """List every backup taken of this VPS."""
        return client.get_list(f"vps/{vps_id}/listbackup/")

    @mcp.tool(annotations=READ_ONLY)
    def get_vps_backup_cost(vps_id: str) -> dict:
        """Cost of taking a new backup of this VPS, before calling
        create_vps_backup."""
        return client.get(f"vps/{vps_id}/getbackupcost/")

    @mcp.tool(annotations=WRITE)
    def create_vps_backup(vps_id: str, confirm: bool = False) -> dict:
        """Take a new backup of this VPS. May incur a cost — check
        get_vps_backup_cost first. Requires confirm=true."""
        if not confirm:
            raise ToolError("Set confirm=true to create a backup — this may incur a cost.")
        return client.post(f"vps/{vps_id}/createbackup/")

    @mcp.tool(annotations=DESTRUCTIVE)
    def delete_vps_backup(vps_id: str, backup_id: str, confirm: bool = False) -> dict:
        """Permanently delete one backup of this VPS. Irreversible —
        requires confirm=true."""
        if not confirm:
            raise ToolError("Set confirm=true to delete this backup — this is irreversible.")
        return client.post(f"vps/{vps_id}/deletebackup/", json={"backup_id": backup_id})

    @mcp.tool(annotations=DESTRUCTIVE)
    def restore_vps_backup(vps_id: str, backup_id: str, confirm: bool = False) -> dict:
        """Restore this VPS from a backup — overwrites its current disk
        state entirely with the backup's. Irreversible (anything
        written since the backup was taken is lost) — requires
        confirm=true."""
        if not confirm:
            raise ToolError("Set confirm=true to restore this backup — anything on the VPS since it was taken will be lost.")
        return client.post(f"vps/{vps_id}/restorebackup/", json={"backup_id": backup_id})

    # ── This VPS's own disks / IPs / reverse DNS ──────────────
    @mcp.tool(annotations=READ_ONLY)
    def list_vps_disks(vps_id: str) -> list:
        """List the disks currently attached to this VPS."""
        return client.get_list(f"vps/{vps_id}/list_disk/")

    @mcp.tool(annotations=WRITE)
    def add_disk_to_vps(vps_id: str, size: int, confirm: bool = False) -> dict:
        """Add a new disk of the given size (GB) directly to this VPS.
        Spends real money — requires confirm=true. For a standalone,
        independently-manageable volume instead, see purchase_volume."""
        if not confirm:
            raise ToolError("Set confirm=true to add this disk — it spends real money.")
        return client.post(f"vps/{vps_id}/add_disk/", json={"size": size})

    @mcp.tool(annotations=DESTRUCTIVE)
    def remove_disk_from_vps(vps_id: str, disk_uuid: str, confirm: bool = False) -> dict:
        """Permanently remove a disk from this VPS. Irreversible —
        requires confirm=true."""
        if not confirm:
            raise ToolError("Set confirm=true to remove this disk — this is irreversible.")
        client.delete(f"vps/{vps_id}/delete_disk/{disk_uuid}")
        return {"status": "removed", "disk_uuid": disk_uuid}

    @mcp.tool(annotations=READ_ONLY)
    def list_attachable_ips_for_vps(vps_id: str) -> list:
        """List this account's standalone IP addresses eligible to
        attach to this specific VPS (same region, not already
        attached)."""
        return client.get_list(f"vps/{vps_id}/attachable_ips/")

    @mcp.tool(annotations=WRITE)
    def add_ip_to_vps(vps_id: str, confirm: bool = False) -> dict:
        """Purchase and attach a brand-new IP address directly to this
        VPS. This is an ONGOING monthly charge (see check_available_ips'
        own monthly_price, and its note on converting to an hourly
        rate), not a one-time fee — requires confirm=true. To attach an
        IP you already own instead, see attach_ip."""
        if not confirm:
            raise ToolError("Set confirm=true to add a new IP to this VPS — it spends real money.")
        return client.post(f"vps/{vps_id}/add_ip/")

    @mcp.tool(annotations=DESTRUCTIVE)
    def remove_ip_from_vps(vps_id: str, ip_addr: str, confirm: bool = False) -> dict:
        """Permanently remove (release) an IP address from this VPS.
        Irreversible — requires confirm=true. To detach without
        releasing it, see detach_ip instead."""
        if not confirm:
            raise ToolError("Set confirm=true to remove this IP — this releases it entirely.")
        client.delete(f"vps/{vps_id}/delete_ip/{ip_addr}")
        return {"status": "removed", "ip": ip_addr}

    @mcp.tool(annotations=WRITE)
    def set_vps_reverse_dns(vps_id: str, ip: str, rdns: str, confirm: bool = False) -> dict:
        """Set the reverse-DNS (PTR) record for one of this VPS's IP
        addresses. Requires confirm=true."""
        if not confirm:
            raise ToolError("Set confirm=true to change this IP's reverse-DNS record.")
        return client.put(f"vps/{vps_id}/ip_address/{ip}/", json={"rdns": rdns})

    # ── Firewall ───────────────────────────────────────────────
    @mcp.tool(annotations=READ_ONLY)
    def list_firewall_rules(vps_id: str) -> list:
        """List the firewall rules currently applied to this VPS."""
        return client.get_list(f"vps/{vps_id}/firewall_rules/")

    @mcp.tool(annotations=WRITE)
    def update_firewall_rules(vps_id: str, rules: list, confirm: bool = False) -> dict:
        """Replace this VPS's entire firewall rule set with the given
        list. Requires confirm=true — this can lock out access
        (including SSH) if the rules are wrong; double-check with the
        user before calling. Each rule should match the shape returned
        by list_firewall_rules."""
        if not confirm:
            raise ToolError("Set confirm=true to update firewall rules — a mistake here can lock out access to this VPS.")
        return client.post(f"vps/{vps_id}/firewall_rules/updateRules/", json={"rules": rules})
