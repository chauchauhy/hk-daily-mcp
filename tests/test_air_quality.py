import json

import pytest

from mcp import Client

from mcp_server import mcp


@pytest.mark.anyio
async def test_air_quality_tool_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert "hk_get_air_quality" in {t.name for t in tools.tools}


async def _call(tool: str, args: dict):
    async with Client(mcp) as client:
        result = await client.call_tool(tool, args)
    assert not result.is_error
    return json.loads(result.content[0].text)


@pytest.mark.anyio
@pytest.mark.network
async def test_air_quality_all_smoke():
    payload = await _call("hk_get_air_quality", {})
    assert isinstance(payload, dict)
    assert "stations" in payload or "error" in payload
    if "stations" in payload:
        assert len(payload["stations"]) > 10
        first = payload["stations"][0]
        assert {"station", "aqhi", "band", "observed_at"} <= set(first)
        assert isinstance(first["aqhi"], int)


@pytest.mark.anyio
@pytest.mark.network
async def test_air_quality_single_smoke():
    payload = await _call("hk_get_air_quality", {"station": "Mong Kok"})
    assert isinstance(payload, dict)
    assert "stations" in payload or "error" in payload
    if "stations" in payload:
        assert len(payload["stations"]) == 1
        assert payload["stations"][0]["station"] == "Mong Kok"


@pytest.mark.anyio
@pytest.mark.network
async def test_air_quality_invalid_station():
    payload = await _call("hk_get_air_quality", {"station": "Nowhere"})
    assert isinstance(payload, dict)
    assert "error" in payload
