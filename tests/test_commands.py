import json
from unittest.mock import patch

import pytest


def _one(result):
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_run_command_starts_then_waits_for_the_result(mcp_server, fake_client):
    fake_client.post.return_value = {"id": "c1", "status": "queued"}
    fake_client.get.side_effect = [{"id": "c1", "status": "running", "output": "Reading"},
                                   {"id": "c1", "status": "succeeded", "exit_code": 0, "output": "done\n"}]
    with patch("iotamine_mcp.tools.commands.time.sleep"):
        result = _one(await mcp_server.call_tool("run_command", {"vps_id": "v1", "command": "apt-get -y install nginx",
                                                                   "timeout_seconds": 900}))
    fake_client.post.assert_called_once_with("vps/v1/commands/", json={"command": "apt-get -y install nginx", "timeout_seconds": 900})
    fake_client.get.assert_called_with("vps/v1/commands/c1/")
    assert (result["status"], result["exit_code"], result["output"]) == ("succeeded", 0, "done\n")
    assert "next_step" not in result


@pytest.mark.asyncio
async def test_a_long_command_returns_while_running_with_a_next_step(mcp_server, fake_client):
    fake_client.post.return_value = {"id": "c1", "status": "queued"}
    fake_client.get.return_value = {"id": "c1", "status": "running", "output": "50%"}
    clock = iter(range(0, 1000, 5))
    with patch("iotamine_mcp.tools.commands.time.sleep"), \
         patch("iotamine_mcp.tools.commands.time.monotonic", side_effect=lambda: next(clock)):
        result = _one(await mcp_server.call_tool("run_command", {"vps_id": "v1", "command": "sleep 600", "wait_seconds": 30}))
    assert result["status"] == "running"
    assert "get_command_result" in result["next_step"]


@pytest.mark.asyncio
async def test_wait_seconds_zero_returns_immediately_and_env_cwd_pass_through(mcp_server, fake_client):
    fake_client.post.return_value = {"id": "c1", "status": "queued"}
    await mcp_server.call_tool("run_command", {"vps_id": "v1", "command": "make", "wait_seconds": 0,
                                               "working_directory": "/srv/app", "environment": {"CI": "1"}})
    body = fake_client.post.call_args[1]["json"]
    assert (body["working_directory"], body["environment"]) == ("/srv/app", {"CI": "1"})
    fake_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_long_output_keeps_the_end_and_says_so(mcp_server, fake_client):
    fake_client.get.return_value = {"id": "c1", "status": "failed", "exit_code": 1, "output": "x" * 5000 + "ERROR: boom"}
    result = _one(await mcp_server.call_tool("get_command_result", {"vps_id": "v1", "command_id": "c1", "max_output_chars": 1000}))
    assert result["output"].endswith("ERROR: boom") and len(result["output"]) == 1000
    assert result["output_omitted_chars"] == 4011


@pytest.mark.asyncio
async def test_get_command_result_passes_the_offset(mcp_server, fake_client):
    fake_client.get.return_value = {"id": "c1", "status": "running", "output": "new"}
    await mcp_server.call_tool("get_command_result", {"vps_id": "v1", "command_id": "c1", "output_offset": 120})
    fake_client.get.assert_called_once_with("vps/v1/commands/c1/", params={"output_offset": 120})


@pytest.mark.asyncio
async def test_cancel_list_and_files(mcp_server, fake_client):
    fake_client.post.return_value = {"ok": True}
    await mcp_server.call_tool("cancel_command", {"vps_id": "v1", "command_id": "c1"})
    fake_client.post.assert_called_with("vps/v1/commands/c1/cancel/", json={})
    await mcp_server.call_tool("write_file", {"vps_id": "v1", "path": "/etc/app.conf", "content": "a=1\n", "mode": "600"})
    fake_client.post.assert_called_with("vps/v1/files/write/", json={"path": "/etc/app.conf", "create_dirs": False,
                                                                     "content": "a=1\n", "mode": "600"})
    await mcp_server.call_tool("write_file", {"vps_id": "v1", "path": "/bin/tool", "content": "AAEC", "content_is_base64": True})
    assert fake_client.post.call_args[1]["json"]["content_base64"] == "AAEC"
    await mcp_server.call_tool("read_file", {"vps_id": "v1", "path": "/etc/hostname"})
    fake_client.post.assert_called_with("vps/v1/files/read/", json={"path": "/etc/hostname"})
    fake_client.get.return_value = {"results": []}
    await mcp_server.call_tool("list_commands", {"vps_id": "v1", "status": "failed"})
    fake_client.get.assert_called_with("vps/v1/commands/", params={"page": 1, "status": "failed"})


@pytest.mark.asyncio
async def test_commands_and_file_writes_are_marked_destructive(mcp_server):
    tools = {t.name: t for t in await mcp_server.list_tools()}
    for name in ("run_command", "write_file"):
        assert tools[name].annotations.destructive_hint is True
    for name in ("get_command_result", "list_commands", "read_file"):
        assert tools[name].annotations.read_only_hint is True


@pytest.mark.asyncio
async def test_every_command_tool_tells_the_model_how_to_get_access(mcp_server):
    tools = {t.name: t for t in await mcp_server.list_tools()}
    for name in ("run_command", "get_command_result", "cancel_command", "list_commands", "read_file", "write_file"):
        assert "Allow commands" in tools[name].description, name
        assert "Read, write & run commands" in tools[name].description, name
        assert "don't try another way in" in tools[name].description, name
