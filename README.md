# iotamine-mcp

An [MCP](https://modelcontextprotocol.io) server for the [Iotamine](https://iotamine.com) cloud VPS
platform. Connect it to Claude Desktop, Claude Code, Cursor, or any other MCP-compatible client to
let it read your VPS instances, billing, quota, and infrastructure directly.

This is a thin, read-only wrapper around the real Iotamine REST API — the exact same API your
[dashboard](https://iotamine.com/control) already uses. It doesn't duplicate any account logic,
store any of your data, or run any service of its own; it just translates MCP tool calls into
ordinary API requests on your behalf, using your own API key.

**Every tool in this server is read-only.** Nothing here can start, stop, create, resize, or
destroy a VPS, or spend money. (Write actions are planned for a future release, gated behind a
separate `read_write`-scoped key — see [Scopes](#scopes) below.)

## Setup

### 1. Get an API key

From your [Iotamine dashboard](https://iotamine.com/control/api_keys) → API Keys → Create Key.
Leave the scope as **Read-only** — that's all this server needs.

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

### 3. Add it to your MCP client

**Claude Code:**

```bash
claude mcp add iotamine uvx --args iotamine-mcp --env IOTAMINE_API_KEY="your-key-here"
```

**Claude Desktop / Cursor** (`claude_desktop_config.json` or your client's equivalent):

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

Set `IOTAMINE_API_KEY` as an environment variable in your client's config, not hardcoded anywhere
else — the same rule any API key deserves.

## Tools

| Tool | What it returns |
|---|---|
| `list_vps` | Every VPS instance on the account |
| `get_vps` | Full detail for one VPS by id |
| `get_quota` | Resource limits, current usage, and tier |
| `get_account_balance` | Wallet balance and basic profile |
| `list_invoices` | Every invoice, most recent first |
| `get_usage_billing` | Current unbilled usage + historical billed cost |
| `list_os_images` | Available operating systems |
| `list_regions` | Available Points of Presence |
| `list_ip_addresses` | Every standalone IP address on the account |
| `list_volumes` | Every standalone storage volume on the account |
| `list_ssh_keys` | Every SSH key saved on the account |

## Scopes

An Iotamine API key has a `scope` — **read-only** (default) or **read & write**. This server only
ever needs a read-only key. If you paste a read & write key instead, nothing changes: every tool
here still only ever sends `GET` requests.

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
