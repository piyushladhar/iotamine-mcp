# iotamine-mcp

An [MCP](https://modelcontextprotocol.io) server for the [Iotamine](https://iotamine.com) cloud VPS
platform. Connect it to Claude Desktop, Claude Code, Cursor, or any other MCP-compatible client to
manage your account directly — the same actions available on the
[dashboard](https://iotamine.com/control).

This is a thin wrapper around the real Iotamine REST API — the exact same API the dashboard itself
uses. It doesn't duplicate any account logic, store any of your data, or run any service of its
own; it just translates MCP tool calls into ordinary API requests on your behalf, using your own
API key.

## Setup

### 1. Get an API key

From your [Iotamine dashboard](https://iotamine.com/control/api_keys) → API Keys → Create Key.
Choose a **scope**:

- **Read-only** — can look up anything (VPS list, stats, billing, invoices, ...) but can't change
  anything. Use this if you're not fully in control of what calls the tools — an AI assistant, a
  script you didn't write yourself.
- **Read & write** — can also do everything the read-only scope can, plus create/destroy/modify
  things. Required for any of the write tools below; a read-only key gets a clean, clear rejection
  if a write tool is called with it.

### 2. Install and run

Using [`uv`](https://docs.astral.sh/uv/) (recommended — no separate install step):

```bash
uvx iotamine-mcp
```

Or with `pip`:

```bash
pip install iotamine-mcp
iotamine-mcp
```

**First run on a fresh machine takes longer** — `uvx`/`pip` need to download the package and its
dependencies once. If you're wiring this into an MCP client (below) and it fails with a timeout
the very first time, run the command above directly in a terminal first, let it finish, then
retry from the client — every run after the first is near-instant.

**Already using an older version?** `uvx` caches its own resolution of "latest" — it won't
automatically notice a new release. Run `uvx --refresh iotamine-mcp` once in a terminal (or clear
`~/.cache/uv`) to pick up new tools, then restart your MCP client.

### 3. Add it to your MCP client

**Claude Code:**

```bash
claude mcp add iotamine uvx --args iotamine-mcp --env IOTAMINE_API_KEY="your-key-here"
```

**Claude Desktop:** Settings → Developer → Edit Config (or directly edit
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS,
`%APPDATA%\Claude\claude_desktop_config.json` on Windows,
`~/.config/Claude/claude_desktop_config.json` on Linux):

```json
{
  "mcpServers": {
    "iotamine": {
      "command": "uvx",
      "args": ["iotamine-mcp"],
      "env": {
        "IOTAMINE_API_KEY": "your-key-here"
      }
    }
  }
}
```

**Cursor:** same JSON shape, in `~/.cursor/mcp.json` (all projects) or `.cursor/mcp.json` in one
project — or via Settings → MCP → Add new MCP server.

Set `IOTAMINE_API_KEY` as an environment variable in your client's config, not hardcoded anywhere
else — the same rule any API key deserves. This is *not* the same thing as the "Connectors" picker
some clients show for remote/OAuth servers — that only accepts a server URL, and won't list this
package at all; the config-file route above is what actually runs it.

## Write tools require confirmation

Every tool that spends money, destroys something, or otherwise changes account state takes an
explicit `confirm: true` argument and refuses to run without it. This is deliberate — it means a
model has to be told (by you, or by its own judgment reading the tool's description) exactly what
it's about to do before it can actually do it. Always expect your assistant to explain the action
and its cost (if any) before it sets `confirm: true`.

## Tools

68 tools in total. Read-only ones work with either key scope; everything else needs a
`read_write`-scoped key.

**VPS — lifecycle**
`list_vps`, `get_vps`, `create_vps`, `destroy_vps`, `start_vps`, `stop_vps`, `poweroff_vps`,
`restart_vps`, `reinstall_vps`, `resize_vps`, `change_vps_hostname`, `change_vps_root_password`

**VPS — monitoring & management**
`get_vps_console`, `get_vps_stats`, `get_vps_bandwidth_history`, `get_vps_metrics_history`,
`get_bandwidth_overview`, `get_vps_billing`, `get_vps_pricing`, `get_vps_smtp_status`,
`get_vps_build_log`, `list_vps_available_os`

**VPS — backups**
`list_vps_backups`, `get_vps_backup_cost`, `create_vps_backup`, `delete_vps_backup`,
`restore_vps_backup`

**VPS — its own disks, IPs, reverse DNS, firewall**
`list_vps_disks`, `add_disk_to_vps`, `remove_disk_from_vps`, `list_attachable_ips_for_vps`,
`add_ip_to_vps`, `remove_ip_from_vps`, `set_vps_reverse_dns`, `list_firewall_rules`,
`update_firewall_rules`

**Standalone IP addresses**
`list_ip_addresses`, `get_ip_address`, `check_available_ips`, `purchase_ip`,
`list_attachable_vps_for_ip`, `attach_ip`, `detach_ip`, `release_ip`

**Standalone volumes**
`list_volumes`, `get_volume`, `list_available_volume_sizes`, `purchase_volume`,
`get_volume_task_status`, `list_attachable_vps_for_volume`, `list_available_os_for_volume`,
`install_os_on_volume`, `resize_volume`, `attach_volume`, `set_volume_as_boot`, `detach_volume`,
`release_volume`

**SSH keys**
`list_ssh_keys`, `create_ssh_key`, `delete_ssh_key`

**Billing & account**
`get_quota`, `get_account_balance`, `list_invoices`, `get_usage_billing`

**Catalogs**
`list_os_images`, `list_regions`

**Activity & data export**
`list_activity_logs`, `export_data`

## Configuration

| Environment variable | Required | Default |
|---|---|---|
| `IOTAMINE_API_KEY` | Yes | — |
| `IOTAMINE_API_URL` | No | `https://iotamine.com/api/` |

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
