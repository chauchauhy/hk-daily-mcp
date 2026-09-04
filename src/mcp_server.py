"""MCP server for daily-data-assistant.

Exposes the same KMB / HKO / daily-summary workflows as the FastAPI routers
as MCP tools. Transport wiring:

- Streamable HTTP: mounted on the FastAPI app in main.py at /mcp
  (``mcp_http_app`` below, built with ``streamable_http_path="/"`` so the
  endpoint is exactly /mcp).
- stdio: ``python mcp_server.py`` (run from the src/ directory).

NOTE (stdio discipline): stdout is reserved for the MCP protocol. This module
and every tool handler must only log (stderr) — never print().
"""
import logging

from mcp.server import MCPServer

from utils import daily_summary_service, kmb_service, weather_service

logger = logging.getLogger(__name__)

mcp = MCPServer("daily-data-assistant")


@mcp.tool()
async def kmb_get_all_routes() -> dict | None:
    """Fetch all KMB bus routes."""
    return await kmb_service.fetch_all_kmb_routes()


@mcp.tool()
async def kmb_find_nearby_stops(lat: float, lon: float) -> dict:
    """Find KMB bus stops near a latitude/longitude pair."""
    return await kmb_service.find_nearby_stops(str(lat), str(lon))


@mcp.tool()
async def kmb_find_nearby_stops_by_address(address: str) -> list:
    """Geocode an address and find KMB bus stops near it."""
    return await kmb_service.find_stops_by_address(address)


@mcp.tool()
async def kmb_get_bus_eta(address: str, route_number: str | None = None) -> dict:
    """Geocode an address, find nearby KMB stops and return live ETAs.

    When route_number is given, ETAs are filtered to that route.
    """
    return await kmb_service.get_stop_eta_workflow(address, route_filter=route_number)


@mcp.tool()
async def kmb_get_route_itinerary(route: str, bound: str = "outbound", service_type: int = 1) -> dict:
    """Return the ordered stops of a KMB route bound, each with live ETAs.

    bound is 'inbound' or 'outbound'.
    """
    return await kmb_service.get_route_itinerary(route, bound, service_type)


@mcp.tool()
async def hko_get_weather_forecast(lang: str = "tc") -> dict | None:
    """Fetch the HKO local weather forecast (general situation, forecast, outlook)."""
    return await weather_service.get_weather_forecast(lang)


@mcp.tool()
async def hko_get_nearby_weather(address: str, lang: str = "tc", top_n: int = 1) -> dict:
    """Find the nearest HKO weather stations to an address with current readings."""
    return await weather_service.get_nearby_weather(address, lang, top_n)


@mcp.tool()
async def daily_summary(lang: str, keyword: str, address: str, route: str) -> dict:
    """Build a daily summary: nearby weather, KMB transport ETAs and keyword news."""
    return await daily_summary_service.get_daily_summary(lang, keyword, address, route)


@mcp.tool()
async def hko_get_9day_forecast(lang: str = "tc") -> dict:
    """Fetch the HKO 9-day weather forecast."""
    return await weather_service.get_9day_forecast(lang)


@mcp.tool()
async def hko_get_weather_warnings(lang: str = "tc") -> dict:
    """Fetch active HKO weather warnings (e.g. typhoon, rainstorm signals) with details."""
    return await weather_service.get_weather_warnings(lang)


@mcp.tool()
async def hko_get_special_weather_tips(lang: str = "tc") -> dict:
    """Fetch HKO special weather tips."""
    return await weather_service.get_special_weather_tips(lang)


# Starlette app served by the host (mounted at /mcp in main.py).
mcp_http_app = mcp.streamable_http_app(streamable_http_path="/")


if __name__ == "__main__":
    mcp.run(transport="stdio")
