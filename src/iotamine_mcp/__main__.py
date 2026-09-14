import asyncio
import os
import sys

from iotamine_mcp.client import IotamineConfigError
from iotamine_mcp.server import build_http_server, build_server


def _run_stdio():
    try:
        mcp, client = build_server()
    except IotamineConfigError as exc:
        # A clear, early failure on stderr — most MCP clients don't
        # surface a crashed server's own stderr nicely, but anyone
        # running this by hand to debug it (the whole point of it being
        # a plain local process) still deserves a real message instead
        # of every tool call failing one at a time with a 401.
        print(f"iotamine-mcp: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        mcp.run(transport="stdio")
    finally:
        client.close()


async def _run_http_async():
    issuer_url = os.environ.get("IOTAMINE_OAUTH_ISSUER_URL")
    resource_server_url = os.environ.get("IOTAMINE_MCP_RESOURCE_URL")
    if not issuer_url or not resource_server_url:
        print(
            "iotamine-mcp: streamable-http mode needs both IOTAMINE_OAUTH_ISSUER_URL "
            "(the oauth_server's own origin, e.g. https://iotamine.com) and "
            "IOTAMINE_MCP_RESOURCE_URL (this server's own public /mcp URL, e.g. "
            "https://mcp.iotamine.com/mcp) set.",
            file=sys.stderr,
        )
        sys.exit(1)
    host = os.environ.get("IOTAMINE_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("IOTAMINE_MCP_PORT", "8000"))
    mcp, verifier, pool = build_http_server(
        base_url=os.environ.get("IOTAMINE_API_URL"),
        resource_server_url=resource_server_url,
        issuer_url=issuer_url,
    )
    try:
        await mcp.run_streamable_http_async(host=host, port=port)
    finally:
        await verifier.aclose()
        pool.close()


def _run_http():
    asyncio.run(_run_http_async())


def main():
    transport = os.environ.get("IOTAMINE_MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        _run_http()
    elif transport == "stdio":
        _run_stdio()
    else:
        print(f"iotamine-mcp: unknown IOTAMINE_MCP_TRANSPORT {transport!r} (expected stdio or streamable-http)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
