import json

import pytest

from mcp import Client

from mcp_server import mcp

NEW_TOOLS = {
    "hko_get_9day_forecast",
    "hko_get_weather_warnings",
    "hko_get_special_weather_tips",
}


@pytest.mark.anyio
async def test_new_tools_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert NEW_TOOLS <= {t.name for t in tools.tools}


def test_station_coords_bundle_loads():
    with open("res/hko_station_coords.json", encoding="utf-8") as f:
        bundle = json.load(f)
    assert len(bundle) >= 30
    assert "King's Park" in bundle
    lat, lon = bundle["King's Park"]
    assert 22.0 < lat < 22.6 and 113.8 < lon < 114.5


async def _call(tool: str, args: dict):
    # Dict-returning tools arrive as JSON text content (no structured_content
    # for bare-dict returns), so parse what a real client would see.
    async with Client(mcp) as client:
        result = await client.call_tool(tool, args)
    assert not result.is_error
    return json.loads(result.content[0].text)


@pytest.mark.anyio
@pytest.mark.network
async def test_9day_forecast_smoke():
    payload = await _call("hko_get_9day_forecast", {})
    assert isinstance(payload, dict)
    assert "generalSituation" in payload or "error" in payload


@pytest.mark.anyio
@pytest.mark.network
async def test_weather_warnings_smoke():
    payload = await _call("hko_get_weather_warnings", {})
    assert isinstance(payload, dict)
    assert ("summary" in payload and "details" in payload) or "error" in payload


@pytest.mark.anyio
@pytest.mark.network
async def test_special_weather_tips_smoke():
    payload = await _call("hko_get_special_weather_tips", {})
    assert isinstance(payload, dict)
    assert "swt" in payload or "error" in payload


@pytest.mark.anyio
@pytest.mark.network
async def test_nearby_weather_enriched_smoke():
    payload = await _call("hko_get_nearby_weather", {"address": "Tsim Sha Tsui, Hong Kong"})
    assert isinstance(payload, dict)
    assert "nearby_stations" in payload or "error" in payload
    if "nearby_stations" in payload:
        assert "nearby_humidity" in payload
        assert "nearby_rainfall" in payload
        assert "uvindex" in payload
