from unittest.mock import MagicMock

import pytest

from iotamine_mcp.server import build_server


@pytest.fixture
def fake_client():
    """A MagicMock standing in for IotamineClient — every tool test
    asserts against how it was called, not real HTTP (test_client.py's
    respx-based tests already cover the real request/response shapes)."""
    return MagicMock()


@pytest.fixture
def mcp_server(fake_client):
    mcp, _ = build_server(client=fake_client)
    return mcp
