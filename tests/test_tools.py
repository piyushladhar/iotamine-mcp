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


@pytest.mark.asyncio
async def test_every_registered_tool_is_marked_read_only(mcp_server):
    """The whole point of Phase 1 shipping read-only-only: nothing here
    should ever be annotated otherwise, or a client that trusts
    readOnlyHint could let a model call it without confirmation."""
    tools = await mcp_server.list_tools()
    assert len(tools) == 11
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert not tool.annotations.destructive_hint
