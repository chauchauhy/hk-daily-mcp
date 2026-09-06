
import pytest

from mcp import Client

from mcp_server import mcp

from helpers import call_mcp as _call


@pytest.mark.anyio
async def test_brief_tool_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert "hk_daily_brief" in {t.name for t in tools.tools}




@pytest.mark.anyio
@pytest.mark.network
async def test_brief_default_domains_smoke():
    payload = await _call("hk_daily_brief", {"address": "Tsim Sha Tsui, Hong Kong"})
    assert isinstance(payload, dict)
    assert "domains" in payload or "error" in payload
    if "domains" in payload:
        for domain in ("weather", "holidays", "tide", "air_quality"):
            assert domain in payload, f"missing domain: {domain}"
        assert "transport" not in payload
        assert "news" not in payload
        assert isinstance(payload["weather"], dict)


@pytest.mark.anyio
@pytest.mark.network
async def test_brief_transport_opt_in_smoke():
    payload = await _call(
        "hk_daily_brief",
        {"address": "Tsim Sha Tsui, Hong Kong", "domains": ["transport"], "route": "1"},
    )
    assert isinstance(payload, dict)
    assert "transport" in payload or "error" in payload


@pytest.mark.anyio
@pytest.mark.network
async def test_brief_invalid_domain():
    payload = await _call("hk_daily_brief", {"address": "Tsim Sha Tsui", "domains": ["nope"]})
    assert isinstance(payload, dict)
    assert "error" in payload


@pytest.mark.anyio
async def test_brief_transport_without_destination(monkeypatch):
    """transport domain without a destination keeps the legacy shape (no routing keys)."""
    async def fake_eta(address, route_filter=None):
        return {"address": address, "stops_with_eta": []}
    async def fake_direct(*args, **kwargs):
        raise AssertionError("direct_routes must not run without destination")
    async def fake_plan(*args, **kwargs):
        raise AssertionError("shortest_route must not run without destination")
    monkeypatch.setattr("utils.daily_summary_service.kmb_service.get_stop_eta_workflow", fake_eta)
    monkeypatch.setattr("utils.daily_summary_service.kmb_service.find_route_between_addresses", fake_direct)
    monkeypatch.setattr("utils.daily_summary_service.kmb_planner_service.plan_shortest_route", fake_plan)
    from utils import daily_summary_service
    brief = await daily_summary_service.get_daily_brief(
        "Origin Place", domains=["transport"])
    assert brief["transport"]["address"] == "Origin Place"
    assert "direct_routes" not in brief
    assert "shortest_route" not in brief
    assert "destination" not in brief


@pytest.mark.anyio
async def test_brief_transport_with_destination(monkeypatch):
    """transport + destination adds direct_routes and shortest_route sections."""
    from utils import daily_summary_service
    async def fake_eta(address, route_filter=None):
        return {"address": address, "stops_with_eta": []}
    async def fake_direct(origin, dest, **kwargs):
        return {"origin_address": origin, "destination_address": dest, "routes": [{"route": "1"}]}
    async def fake_plan(origin, dest, **kwargs):
        return {"origin_address": origin, "destination_address": dest, "legs": [{"type": "bus", "route": "1"}]}
    monkeypatch.setattr("utils.daily_summary_service.kmb_service.get_stop_eta_workflow", fake_eta)
    monkeypatch.setattr("utils.daily_summary_service.kmb_service.find_route_between_addresses", fake_direct)
    monkeypatch.setattr("utils.daily_summary_service.kmb_planner_service.plan_shortest_route", fake_plan)
    brief = await daily_summary_service.get_daily_brief(
        "Origin Place", domains=["transport"], destination_address="Dest Place")
    assert brief["destination"] == "Dest Place"
    assert brief["direct_routes"]["destination_address"] == "Dest Place"
    assert brief["shortest_route"]["legs"][0]["route"] == "1"
    assert brief["transport"]["address"] == "Origin Place"


@pytest.mark.anyio
async def test_brief_integration_real_services_offline(monkeypatch):
    """Wire real service functions under the offline fake HTTP layer.

    Uses the same fake_http fixture as the rest of the suite: geocoding and
    KMB feeds are canned, so we exercise the real integration path (including
    the Dijkstra planner) with no network.
    """
    from utils import daily_summary_service
    async def fake_geocode(address, *args, **kwargs):
        return {"latitude": 22.30, "longitude": 114.10}
    async def fake_near(lat, lon, radius=None):
        return []
    async def fake_index():
        return {"lane_stops": {}, "stop_lanes": {}}
    monkeypatch.setattr(
        "utils.daily_summary_service.kmb_util.KMBRouterUtil.get_lat_lon_from_address", fake_geocode)
    monkeypatch.setattr(
        "utils.daily_summary_service.kmb_util.KMBRouterUtil.load_near_stop_with_lat_lon", fake_near)
    monkeypatch.setattr(
        "utils.daily_summary_service.kmb_util.KMBRouterUtil.load_route_stop_index", fake_index)
    brief = await daily_summary_service.get_daily_brief(
        "Origin Place", domains=["transport"], destination_address="Dest Place")
    # empty nearby stops -> graceful sections, still present
    assert brief["transport"]["stops_with_eta"] == []
    assert "direct_routes" in brief
    assert "shortest_route" in brief


@pytest.mark.anyio
@pytest.mark.network
async def test_brief_transport_with_destination_smoke():
    payload = await _call("hk_daily_brief", {
        "address": "Chuk Yuen Estate, Wong Tai Sin, Kowloon",
        "domains": ["transport"],
        "destination_address": "Star Ferry Pier, Tsim Sha Tsui, Kowloon",
    })
    assert isinstance(payload, dict)
    assert "transport" in payload or "error" in payload
    if "transport" in payload:
        assert payload["destination"] == "Star Ferry Pier, Tsim Sha Tsui, Kowloon"
        assert "direct_routes" in payload
        assert "shortest_route" in payload
