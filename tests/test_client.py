import httpx
import pytest
import respx

from iotamine_mcp.client import IotamineAPIError, IotamineClient, IotamineConfigError


def test_missing_api_key_raises_a_clear_config_error(monkeypatch):
    monkeypatch.delenv("IOTAMINE_API_KEY", raising=False)
    with pytest.raises(IotamineConfigError, match="IOTAMINE_API_KEY"):
        IotamineClient()


def test_default_base_url_is_the_real_production_api():
    client = IotamineClient(api_key="k")
    assert client.base_url == "https://iotamine.com/api/"
    client.close()


def test_base_url_override_via_env(monkeypatch):
    monkeypatch.setenv("IOTAMINE_API_URL", "http://127.0.0.1:8003/api")
    client = IotamineClient(api_key="k")
    assert client.base_url == "http://127.0.0.1:8003/api/"
    client.close()


@respx.mock
def test_get_sends_the_api_key_header():
    route = respx.get("https://iotamine.com/api/vps/").mock(
        return_value=httpx.Response(200, json=[])
    )
    client = IotamineClient(api_key="my-secret-key")
    client.get("vps/")
    client.close()
    assert route.called
    assert route.calls.last.request.headers["Authorization"] == "Api-Key my-secret-key"


@respx.mock
def test_401_raises_a_clear_invalid_key_message():
    respx.get("https://iotamine.com/api/vps/").mock(return_value=httpx.Response(401))
    client = IotamineClient(api_key="bad-key")
    with pytest.raises(IotamineAPIError) as exc_info:
        client.get("vps/")
    client.close()
    assert exc_info.value.status_code == 401
    assert "API Keys page" in exc_info.value.message


@respx.mock
def test_403_surfaces_the_backends_real_message():
    respx.post("https://iotamine.com/api/sshkey/").mock(
        return_value=httpx.Response(403, json={"message": "This API key is read-only. Generate a read & write key to perform this action."})
    )
    client = IotamineClient(api_key="ro-key")
    with pytest.raises(IotamineAPIError) as exc_info:
        client.post("sshkey/", json={"title": "x"})
    client.close()
    assert exc_info.value.status_code == 403
    assert "read-only" in exc_info.value.message


@respx.mock
def test_network_failure_is_wrapped_not_raised_raw():
    respx.get("https://iotamine.com/api/vps/").mock(side_effect=httpx.ConnectError("refused"))
    client = IotamineClient(api_key="k")
    with pytest.raises(IotamineAPIError) as exc_info:
        client.get("vps/")
    client.close()
    assert "Could not reach" in exc_info.value.message


@respx.mock
def test_get_list_unwraps_a_paginated_envelope():
    respx.get("https://iotamine.com/api/invoices/").mock(
        return_value=httpx.Response(200, json={"count": 2, "next": None, "previous": None, "results": [{"id": 1}, {"id": 2}]})
    )
    client = IotamineClient(api_key="k")
    result = client.get_list("invoices/")
    client.close()
    assert result == [{"id": 1}, {"id": 2}]


@respx.mock
def test_get_list_passes_through_a_plain_array():
    respx.get("https://iotamine.com/api/vps/").mock(
        return_value=httpx.Response(200, json=[{"id": "a"}, {"id": "b"}])
    )
    client = IotamineClient(api_key="k")
    result = client.get_list("vps/")
    client.close()
    assert result == [{"id": "a"}, {"id": "b"}]
