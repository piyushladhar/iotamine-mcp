import json

import pytest


def _texts(result):
    """Every tool test just needs to see what got returned, not fight
    the SDK's own content-block framing (a list-returning tool comes
    back as one TextContent block per item; a dict-returning tool comes
    back as one block holding the whole object)."""
    return [json.loads(block.text) for block in result.content]


@pytest.mark.asyncio
async def test_list_vps_calls_the_right_endpoint_with_all_true(mcp_server, fake_client):
    fake_client.get_list.return_value = [{"id": "v1"}]
    result = await mcp_server.call_tool("list_vps", {})
    fake_client.get_list.assert_called_once_with("vps/", params={"all": "true"})
    assert _texts(result) == [{"id": "v1"}]


@pytest.mark.asyncio
async def test_get_vps_passes_the_id_into_the_path(mcp_server, fake_client):
    fake_client.get.return_value = {"id": "v1", "hostname": "box"}
    result = await mcp_server.call_tool("get_vps", {"vps_id": "v1"})
    fake_client.get.assert_called_once_with("vps/v1/")
    assert _texts(result) == [{"id": "v1", "hostname": "box"}]


@pytest.mark.asyncio
async def test_get_quota(mcp_server, fake_client):
    fake_client.get.return_value = {"tier": "Tier 2"}
    result = await mcp_server.call_tool("get_quota", {})
    fake_client.get.assert_called_once_with("account/quota/")
    assert _texts(result) == [{"tier": "Tier 2"}]


@pytest.mark.asyncio
async def test_get_account_balance_hits_users_me(mcp_server, fake_client):
    fake_client.get.return_value = {"balance": "42.00"}
    result = await mcp_server.call_tool("get_account_balance", {})
    fake_client.get.assert_called_once_with("users/me/")
    assert _texts(result) == [{"balance": "42.00"}]


@pytest.mark.asyncio
async def test_list_invoices(mcp_server, fake_client):
    fake_client.get_list.return_value = [{"id": 1}]
    result = await mcp_server.call_tool("list_invoices", {})
    fake_client.get_list.assert_called_once_with("invoices/", params={"page_size": 100})
    assert _texts(result) == [{"id": 1}]


@pytest.mark.asyncio
async def test_get_usage_billing(mcp_server, fake_client):
    fake_client.get.return_value = {"unbilled": 5.0}
    result = await mcp_server.call_tool("get_usage_billing", {})
    fake_client.get.assert_called_once_with("usage-billing/overview/")
    assert _texts(result) == [{"unbilled": 5.0}]


@pytest.mark.parametrize("tool_name,path", [
    ("list_os_images", "os/"),
    ("list_regions", "pop/"),
    ("list_ip_addresses", "ip-addresses/"),
    ("list_volumes", "volumes/"),
    ("list_ssh_keys", "sshkey/"),
])
@pytest.mark.asyncio
async def test_infra_list_tools_hit_the_right_endpoint(mcp_server, fake_client, tool_name, path):
    fake_client.get_list.return_value = [{"id": 1}]
    result = await mcp_server.call_tool(tool_name, {})
    fake_client.get_list.assert_called_once_with(path, params={"page_size": 200})
    assert _texts(result) == [{"id": 1}]


READ_ONLY_TOOL_NAMES = {
    "list_vps", "get_vps", "get_vps_console", "get_vps_stats", "get_vps_bandwidth_history",
    "get_vps_metrics_history", "get_bandwidth_overview", "get_vps_billing", "get_vps_pricing",
    "get_vps_smtp_status", "get_vps_build_log", "list_vps_available_os", "list_vps_backups",
    "get_vps_backup_cost", "list_vps_disks", "list_attachable_ips_for_vps", "list_firewall_rules",
    "get_quota", "get_account_balance", "list_invoices", "get_invoice_summary", "get_usage_billing",
    "list_os_images", "list_regions", "list_ssh_keys",
    "list_ip_addresses", "get_ip_address", "check_available_ips", "list_attachable_vps_for_ip",
    "list_volumes", "get_volume", "list_available_volume_sizes", "get_volume_task_status",
    "list_attachable_vps_for_volume", "list_available_os_for_volume",
    "list_activity_logs", "export_data",
    "get_usage_billing_line_items", "list_transactions", "get_transaction",
    "list_maintenance_events", "get_bandwidth_overview_daily",
    "list_ticket_departments", "list_tickets", "get_ticket", "list_ticket_replies",
}


@pytest.mark.asyncio
async def test_every_tool_is_annotated_and_the_read_only_set_is_exactly_right(mcp_server):
    """Nothing here should ever go unannotated (a client can't make a
    confirm/no-confirm UI decision without an annotation to read), and
    the read-only set must be exact in both directions: nothing that
    actually writes is marked readOnlyHint=true (a client could let a
    model call it with zero confirmation), and nothing read-only is
    marked otherwise (which would make a client demand confirmation
    for a plain lookup)."""
    tools = await mcp_server.list_tools()
    assert len(tools) == 83
    by_name = {t.name: t for t in tools}
    assert set(by_name) >= READ_ONLY_TOOL_NAMES
    for tool in tools:
        assert tool.annotations is not None, tool.name
        expected_read_only = tool.name in READ_ONLY_TOOL_NAMES
        assert tool.annotations.read_only_hint is expected_read_only, tool.name
        if expected_read_only:
            assert not tool.annotations.destructive_hint, tool.name
