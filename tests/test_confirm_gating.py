"""Every write/destructive tool's own confirm=true gate — tested
generically across the whole tool set rather than by hand per tool, so
adding a new write tool later can't silently ship without this
protection. The one thing that actually matters here: a call made
WITHOUT confirm=true must fail AND must never reach the real API
client — a model retrying blindly, or a buggy client that ignores the
error, must never accidentally trigger the real action.

Calls go through mcp_server.call_tool() directly (the same low-level
Python API used throughout test_tools.py) — by design (see
MCPServer.call_tool's own docstring) this *raises* ToolError/
UnexpectedToolError rather than returning a CallToolResult(is_error=True);
that conversion into a clean wire-level response happens one layer up,
in the real JSON-RPC request handler (_handle_call_tool) — confirmed
separately via a real stdio subprocess round trip, not assumed.

Why ToolError specifically matters, not just "any exception": a plain
Exception (e.g. a bare ValueError) gets re-wrapped by the SDK as
`UnexpectedToolError(f"Error executing tool {name}")` — the original
message is dropped entirely. A ToolError gets re-wrapped as
`ToolError(f"Error executing tool {name}: {exc}")` — the real message
survives. That's the actual, model-visible difference confirm-gate
rejections (and IotamineAPIError — see client.py) need ToolError for.
"""
import pytest
from mcp.server.mcpserver.exceptions import ToolError


def _dummy_value(schema):
    """A plausible dummy value for one JSON-schema property, just
    enough to satisfy a tool's required-argument validation without
    caring what it actually is — these calls are all expected to be
    rejected by the confirm=false gate before the value is ever used
    for anything real."""
    t = schema.get("type")
    if t == "string":
        return "x"
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return False
    if t == "array":
        return []
    if t == "object":
        return {}
    return "x"


def _args_with_confirm_false(tool):
    props = tool.input_schema.get("properties", {})
    required = set(tool.input_schema.get("required", []))
    args = {name: _dummy_value(schema) for name, schema in props.items() if name in required}
    args["confirm"] = False
    return args


@pytest.mark.asyncio
async def test_every_confirm_gated_tool_refuses_without_confirm_and_never_touches_the_client(mcp_server, fake_client):
    tools = await mcp_server.list_tools()
    gated = [t for t in tools if "confirm" in t.input_schema.get("properties", {})]
    # 28 today (every write/destructive tool except the 4 power actions —
    # start/stop/poweroff/restart are deliberately ungated, see vps.py's
    # own POWER_ACTION comment) — a floor, not an exact count, so this
    # doesn't need updating for every new tool, but still catches a
    # registration regression dropping a whole module silently.
    assert len(gated) >= 25

    for tool in gated:
        fake_client.reset_mock()
        with pytest.raises(ToolError, match="confirm=true"):
            await mcp_server.call_tool(tool.name, _args_with_confirm_false(tool))
        fake_client.get.assert_not_called()
        fake_client.post.assert_not_called()
        fake_client.patch.assert_not_called()
        fake_client.put.assert_not_called()
        fake_client.delete.assert_not_called()
        fake_client.get_list.assert_not_called()


@pytest.mark.asyncio
async def test_every_confirm_gated_tool_is_annotated_non_read_only(mcp_server):
    """A tool that requires confirmation to run is definitionally not
    read-only — this would catch a copy-paste mistake where a new write
    tool kept READ_ONLY annotations."""
    tools = await mcp_server.list_tools()
    for tool in tools:
        if "confirm" in tool.input_schema.get("properties", {}):
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is False, tool.name


@pytest.mark.asyncio
async def test_a_real_api_error_reaches_the_model_with_its_actual_message_not_a_generic_one(mcp_server, fake_client):
    """The concrete reason IotamineAPIError subclasses ToolError (see
    client.py's own comment) — verified here rather than just asserted
    in a comment: a plain Exception in this SDK gets its message
    silently dropped by the re-wrap in mcp.server.mcpserver.tools.base;
    a ToolError's message survives."""
    from iotamine_mcp.client import IotamineAPIError
    fake_client.get.side_effect = IotamineAPIError(401, "invalid key")
    with pytest.raises(ToolError) as exc_info:
        await mcp_server.call_tool("get_vps", {"vps_id": "x"})
    assert "invalid key" in str(exc_info.value)
