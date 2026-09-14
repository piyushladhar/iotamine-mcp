import sys

from iotamine_mcp.client import IotamineConfigError
from iotamine_mcp.server import build_server


def main():
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


if __name__ == "__main__":
    main()
