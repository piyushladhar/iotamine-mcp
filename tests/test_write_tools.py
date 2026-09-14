"""Endpoint-mapping spot checks for the write/destructive tools and the
new read tool groups (network, storage, activity, export) — same style
as test_tools.py's original coverage, applied to the biggest-blast-
-radius additions (VPS lifecycle, IP/volume purchase) plus one
representative per remaining group."""
import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError


def _texts(result):
    return [json.loads(block.text) for block in result.content]


# ── VPS lifecycle ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_vps_posts_the_right_payload(mcp_server, fake_client):
    fake_client.post.return_value = {"id": "new-vps", "is_building": True}
    await mcp_server.call_tool("create_vps", {
        "hostname": "box1", "pop": 1, "cores": 2, "ram": 4, "disk": 40,
        "operating_system": 7, "confirm": True,
    })
    fake_client.post.assert_called_once_with("vps/", json={
        "hostname": "box1", "pop": 1, "cores": 2, "ram": 4, "disk": 40,
        "operating_system": 7, "traffic": 5, "disable_pwd_auth": False,
    })


@pytest.mark.asyncio
async def test_destroy_vps_sends_delete_with_release_ids(mcp_server, fake_client):
    fake_client.delete.return_value = None
    await mcp_server.call_tool("destroy_vps", {"vps_id": "v1", "confirm": True, "release_ip_ids": [1, 2]})
    fake_client.delete.assert_called_once_with("vps/v1/", json={"release_ip_ids": [1, 2]})


@pytest.mark.parametrize("tool_name,path", [
    ("start_vps", "vps/v1/start/"),
    ("stop_vps", "vps/v1/stop/"),
    ("poweroff_vps", "vps/v1/poweroff/"),
    ("restart_vps", "vps/v1/restart/"),
])
@pytest.mark.asyncio
async def test_power_actions_need_no_confirm_and_hit_the_right_endpoint(mcp_server, fake_client, tool_name, path):
    fake_client.get.return_value = {"message": "ok"}
    result = await mcp_server.call_tool(tool_name, {"vps_id": "v1"})
    fake_client.get.assert_called_once_with(path)
    assert _texts(result) == [{"message": "ok"}]


@pytest.mark.asyncio
async def test_reinstall_vps_maps_to_rebuild_with_matching_passwords(mcp_server, fake_client):
    fake_client.post.return_value = {"message": "rebuilding"}
    await mcp_server.call_tool("reinstall_vps", {"vps_id": "v1", "os_id": 5, "new_pass": "Sup3rSecret!", "confirm": True})
    fake_client.post.assert_called_once_with("vps/v1/rebuild/", json={"osid": 5, "new_pass": "Sup3rSecret!", "conf_pass": "Sup3rSecret!"})


@pytest.mark.asyncio
async def test_resize_vps_patches_only_the_given_fields(mcp_server, fake_client):
    fake_client.patch.return_value = {"cores": 4}
    await mcp_server.call_tool("resize_vps", {"vps_id": "v1", "cores": 4, "confirm": True})
    fake_client.patch.assert_called_once_with("vps/v1/", json={"cores": 4})


@pytest.mark.asyncio
async def test_resize_vps_rejects_when_neither_cores_nor_ram_given(mcp_server, fake_client):
    with pytest.raises(ToolError, match="cores or ram"):
        await mcp_server.call_tool("resize_vps", {"vps_id": "v1", "confirm": True})
    fake_client.patch.assert_not_called()


@pytest.mark.asyncio
async def test_change_vps_hostname_patches_hostname_only(mcp_server, fake_client):
    fake_client.patch.return_value = {"hostname": "new-name"}
    await mcp_server.call_tool("change_vps_hostname", {"vps_id": "v1", "hostname": "new-name", "confirm": True})
    fake_client.patch.assert_called_once_with("vps/v1/", json={"hostname": "new-name"})


@pytest.mark.asyncio
async def test_change_vps_root_password_patches_password_only(mcp_server, fake_client):
    fake_client.patch.return_value = {"message": "ok"}
    await mcp_server.call_tool("change_vps_root_password", {"vps_id": "v1", "new_password": "S3cret!!", "confirm": True})
    fake_client.patch.assert_called_once_with("vps/v1/", json={"password": "S3cret!!"})


@pytest.mark.asyncio
async def test_set_vps_reverse_dns_puts_to_the_ip_scoped_path(mcp_server, fake_client):
    fake_client.put.return_value = {"rdns": "host.example.com"}
    await mcp_server.call_tool("set_vps_reverse_dns", {"vps_id": "v1", "ip": "203.0.113.5", "rdns": "host.example.com", "confirm": True})
    fake_client.put.assert_called_once_with("vps/v1/ip_address/203.0.113.5/", json={"rdns": "host.example.com"})


@pytest.mark.asyncio
async def test_update_firewall_rules_posts_to_the_nested_route(mcp_server, fake_client):
    fake_client.post.return_value = {"status": "updated"}
    rules = [{"port": 22, "protocol": "tcp", "action": "allow"}]
    await mcp_server.call_tool("update_firewall_rules", {"vps_id": "v1", "rules": rules, "confirm": True})
    fake_client.post.assert_called_once_with("vps/v1/firewall_rules/updateRules/", json={"rules": rules})


# ── Standalone IP addresses ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_purchase_ip_posts_pop_and_quantity(mcp_server, fake_client):
    fake_client.post.return_value = [{"id": 1, "ip": "203.0.113.5"}]
    await mcp_server.call_tool("purchase_ip", {"pop": 3, "quantity": 2, "confirm": True})
    fake_client.post.assert_called_once_with("ip-addresses/purchase/", json={"pop": 3, "quantity": 2})


@pytest.mark.asyncio
async def test_attach_ip_posts_vps_id(mcp_server, fake_client):
    fake_client.post.return_value = {"vps": "v1"}
    await mcp_server.call_tool("attach_ip", {"ip_id": "ip1", "vps_id": "v1", "confirm": True})
    fake_client.post.assert_called_once_with("ip-addresses/ip1/attach/", json={"vps": "v1"})


@pytest.mark.asyncio
async def test_release_ip_sends_delete(mcp_server, fake_client):
    fake_client.delete.return_value = None
    await mcp_server.call_tool("release_ip", {"ip_id": "ip1", "confirm": True})
    fake_client.delete.assert_called_once_with("ip-addresses/ip1/")


# ── Standalone volumes ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_purchase_volume_posts_pop_size_and_kind(mcp_server, fake_client):
    fake_client.post.return_value = {"task_id": 42, "status": "pending"}
    await mcp_server.call_tool("purchase_volume", {"pop": 3, "size_gb": 40, "confirm": True})
    fake_client.post.assert_called_once_with("volumes/purchase/", json={"pop": 3, "size_gb": 40, "kind": "data"})


@pytest.mark.asyncio
async def test_attach_volume_posts_vps(mcp_server, fake_client):
    fake_client.post.return_value = {"task_id": 43}
    await mcp_server.call_tool("attach_volume", {"volume_id": "vol1", "vps_id": "v1", "confirm": True})
    fake_client.post.assert_called_once_with("volumes/vol1/attach/", json={"vps": "v1"})


@pytest.mark.asyncio
async def test_release_volume_sends_delete(mcp_server, fake_client):
    fake_client.delete.return_value = {"task_id": 44}
    await mcp_server.call_tool("release_volume", {"volume_id": "vol1", "confirm": True})
    fake_client.delete.assert_called_once_with("volumes/vol1/")


# ── SSH keys ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_ssh_key_posts_title_and_key(mcp_server, fake_client):
    fake_client.post.return_value = {"id": 9, "title": "laptop"}
    await mcp_server.call_tool("create_ssh_key", {"title": "laptop", "ssh_key": "ssh-ed25519 AAAA", "confirm": True})
    fake_client.post.assert_called_once_with("sshkey/", json={"title": "laptop", "ssh_key": "ssh-ed25519 AAAA"})


@pytest.mark.asyncio
async def test_delete_ssh_key_sends_delete(mcp_server, fake_client):
    fake_client.delete.return_value = None
    await mcp_server.call_tool("delete_ssh_key", {"ssh_key_id": "9", "confirm": True})
    fake_client.delete.assert_called_once_with("sshkey/9/")


# ── Activity + export ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_activity_logs_default_and_search(mcp_server, fake_client):
    fake_client.get_list.return_value = [{"action": "SIGN_IN"}]
    await mcp_server.call_tool("list_activity_logs", {})
    fake_client.get_list.assert_called_once_with("activity/", params={"page_size": 50})

    fake_client.reset_mock()
    fake_client.get_list.return_value = []
    await mcp_server.call_tool("list_activity_logs", {"search": "VM_START"})
    fake_client.get_list.assert_called_once_with("activity/", params={"page_size": 50, "search": "VM_START"})


@pytest.mark.asyncio
async def test_export_data_returns_csv_text_verbatim(mcp_server, fake_client):
    import httpx
    fake_client._raw_request.return_value = ("text/csv", httpx.Response(200, text="id,name\n1,foo\n"))
    result = await mcp_server.call_tool("export_data", {"category": "activity"})
    fake_client._raw_request.assert_called_once_with("GET", "users/export/activity/", params={})
    assert result.content[0].text == "id,name\n1,foo\n"


@pytest.mark.asyncio
async def test_export_data_rejects_an_unknown_category(mcp_server, fake_client):
    with pytest.raises(ToolError, match="category must be one of"):
        await mcp_server.call_tool("export_data", {"category": "not-a-real-one"})
    fake_client._raw_request.assert_not_called()


@pytest.mark.asyncio
async def test_export_data_refuses_the_zip_shaped_invoices_category(mcp_server, fake_client):
    import httpx
    fake_client._raw_request.return_value = ("application/zip", httpx.Response(200, content=b"PK\x03\x04"))
    with pytest.raises(ToolError, match="zip archive"):
        await mcp_server.call_tool("export_data", {"category": "invoices"})
