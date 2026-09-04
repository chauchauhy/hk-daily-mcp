import pytest

from mcp import Client

from mcp_server import mcp

EXPECTED_TOOLS = {
    "kmb_get_all_routes",
    "kmb_find_nearby_stops",
    "kmb_find_nearby_stops_by_address",
    "kmb_get_bus_eta",
    "hko_get_weather_forecast",
    "hko_get_nearby_weather",
    "daily_summary",
}


@pytest.mark.anyio
async def test_all_tools_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert EXPECTED_TOOLS == {t.name for t in tools.tools}
