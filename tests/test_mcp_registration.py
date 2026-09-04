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
    "hko_get_9day_forecast",
    "hko_get_weather_warnings",
    "hko_get_special_weather_tips",
    "kmb_get_route_itinerary",
    "hk_get_public_holidays",
    "hko_get_tide_predictions",
    "hk_get_air_quality",
}


@pytest.mark.anyio
async def test_all_tools_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert EXPECTED_TOOLS == {t.name for t in tools.tools}
