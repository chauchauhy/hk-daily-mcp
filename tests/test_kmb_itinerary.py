
import pytest

from mcp import Client

from mcp_server import mcp

from helpers import call_mcp as _call


@pytest.mark.anyio
async def test_itinerary_tool_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert "kmb_get_route_itinerary" in {t.name for t in tools.tools}




@pytest.mark.anyio
@pytest.mark.network
async def test_route_itinerary_smoke():
    payload = await _call("kmb_get_route_itinerary", {"route": "1", "bound": "outbound"})
    assert isinstance(payload, dict)
    assert "stops" in payload or "error" in payload
    if "stops" in payload:
        assert payload["route"] == "1"
        assert len(payload["stops"]) > 0
        first = payload["stops"][0]
        assert {"seq", "stop_id", "stop_name_en", "etas"} <= set(first)
        assert first["seq"] == 1


@pytest.mark.anyio
@pytest.mark.network
async def test_route_itinerary_invalid_bound():
    payload = await _call("kmb_get_route_itinerary", {"route": "1", "bound": "sideways"})
    assert isinstance(payload, dict)
    assert "error" in payload
