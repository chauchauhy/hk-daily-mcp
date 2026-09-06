"""Offline tests for the direct-route finder (kmb_find_route_between_addresses).

Covers: indexing + matching of direct lanes, ranking by walking distance,
no-route and geocoding-failure paths, optional ETA attachment, and MCP
registration. All network calls are patched with canned payloads.
"""
import pytest

from mcp import Client

from mcp_server import mcp

from models.kmb.stop.stop_response import Stop, StopListResponse
from models.kmb.router.route_lane import RouterLane, KMBRouterResponse
from models.kmb.route_stop.route_stop_list import RouteStop
from models.kmb.stop_eta.kmb_stop_eta import KMBStopETAResponse, StopETAData
from utils import kmb_service, kmb_util

from helpers import call_mcp as _call

ORIGIN_COORDS = {"latitude": 22.30, "longitude": 114.10}
DEST_COORDS = {"latitude": 22.33, "longitude": 114.13}

ORIGIN_STOPS = [
    Stop(stop="STOP1", name_en="Origin Stop One", name_tc="起點一站", name_sc="起点一站",
         lat="22.301", long="114.101"),
    Stop(stop="STOP2", name_en="Origin Stop Two", name_tc="起點二站", name_sc="起点二站",
         lat="22.302", long="114.102"),
]
DEST_STOPS = [
    Stop(stop="STOP3", name_en="Destination Stop", name_tc="終點站", name_sc="终点站",
         lat="22.331", long="114.131"),
]


def _stop_list(stops):
    return StopListResponse(type="", version="", generated_timestamp="", data=stops)


def _lane_stops(entries):
    """Build a lane_stops index { (route,bound,st): [RouteStop...] } from tuples."""
    lanes = {}
    for (route, bound, service_type, seq, stop) in entries:
        lanes.setdefault((route, bound, service_type), []).append(
            RouteStop(route=route, bound=bound, service_type=service_type, seq=seq, stop=stop))
    for key in lanes:
        lanes[key].sort(key=lambda e: e.seq)
    return lanes


def _install_patches(monkeypatch, *, origin_stops=None, dest_stops=None, lanes=None, route_lanes=None):
    origin_stops = ORIGIN_STOPS if origin_stops is None else origin_stops
    dest_stops = DEST_STOPS if dest_stops is None else dest_stops
    lanes = _lane_stops([
        ("1A", "O", "1", 1, "STOP1"), ("1A", "O", "1", 2, "STOP2"), ("1A", "O", "1", 3, "STOP3"),
        ("1A", "I", "1", 1, "STOP3"), ("1A", "I", "1", 2, "STOP1"),        # return bound: must NOT match
        ("1", "O", "1", 1, "STOP1"), ("1", "O", "1", 2, "STOP2"),          # no destination stop
        ("2", "O", "1", 1, "STOP3"), ("2", "O", "1", 2, "STOP1"),          # reversed order
    ]) if lanes is None else lanes
    if route_lanes is None:
        route_lanes = KMBRouterResponse(type="", version="", generated_timestamp="", data=[
            RouterLane(route="1A", bound="O", service_type="1",
                       orig_en="TEST ORIGIN TERMINUS", orig_tc="測試總站", orig_sc="测试总站",
                       dest_en="TEST DEST TERMINUS", dest_tc="測試終點", dest_sc="测试终点"),
        ])

    async def fake_geocode(address, *args, **kwargs):
        lowered = address.lower()
        if "nowhere" in lowered:
            return {"error": "Address not found"}
        if "origin" in lowered:
            return dict(ORIGIN_COORDS)
        if "destination" in lowered:
            return dict(DEST_COORDS)
        return {"error": "Address not found"}

    async def fake_near(lat, lon, radius=None):
        lat_f = float(lat)
        return origin_stops if lat_f < 22.32 else dest_stops

    async def fake_index():
        return {"lane_stops": lanes, "stop_lanes": {}}

    async def fake_routes():
        return route_lanes

    monkeypatch.setattr(kmb_util.KMBRouterUtil, "get_lat_lon_from_address", fake_geocode)
    monkeypatch.setattr(kmb_util.KMBRouterUtil, "load_near_stop_with_lat_lon", fake_near)
    monkeypatch.setattr(kmb_util.KMBRouterUtil, "load_route_stop_index", fake_index)
    monkeypatch.setattr(kmb_util.KMBRouterUtil, "fetch_all_kmb_router", fake_routes)


@pytest.mark.anyio
async def test_direct_route_found(monkeypatch):
    _install_patches(monkeypatch)
    payload = await kmb_service.find_route_between_addresses("Origin Place", "Destination Place")
    assert "error" not in payload
    assert payload["routes_count"] == 1
    route = payload["routes"][0]
    assert route["route"] == "1A"
    assert route["bound"] == "O"
    assert route["direction"] == "outbound"
    assert route["boarding_stop"]["stop_id"] == "STOP1"
    assert route["alighting_stop"]["stop_id"] == "STOP3"
    assert route["stops_between"] == 1
    assert route["boarding_stop"]["distance_km_from_origin"] > 0
    assert route["orig_en"] == "TEST ORIGIN TERMINUS"
    assert route["dest_tc"] == "測試終點"
    assert payload["search_radius_degrees"] > 0


@pytest.mark.anyio
async def test_wrong_direction_bound_excluded(monkeypatch):
    """A return-bound lane (destination stop before origin stop) is not a valid direct route."""
    _install_patches(monkeypatch)
    payload = await kmb_service.find_route_between_addresses("Origin Place", "Destination Place")
    assert payload["routes_count"] == 1
    assert all(r["bound"] == "O" for r in payload["routes"])


@pytest.mark.anyio
async def test_include_eta_attaches_next_buses(monkeypatch):
    _install_patches(monkeypatch)
    async def fake_eta(stop_id):
        return KMBStopETAResponse(type="", version="", generated_timestamp="", data=[
            StopETAData(co="KMB", route="1A", dir="O", service_type=1, seq=1,
                       dest_en="TEST DEST TERMINUS", dest_tc="測試終點", dest_sc="测试终点",
                       eta_seq=1, eta="2026-09-06T12:00:00+08:00",
                       rmk_en="", rmk_tc="", rmk_sc="", data_timestamp="2026-09-06T11:00:00+08:00"),
            # wrong route/direction must be filtered out
            StopETAData(co="KMB", route="9", dir="O", service_type=1, seq=1,
                       dest_en="OTHER", dest_tc="其他", dest_sc="其他",
                       eta_seq=1, eta="2026-09-06T12:05:00+08:00",
                       rmk_en="", rmk_tc="", rmk_sc="", data_timestamp="2026-09-06T11:00:00+08:00"),
        ])
    monkeypatch.setattr(kmb_util.KMBRouterUtil, "fetch_kmb_eta_stop_by_stop_id", fake_eta)
    payload = await kmb_service.find_route_between_addresses(
        "Origin Place", "Destination Place", include_eta=True)
    route = payload["routes"][0]
    assert len(route["next_buses"]) == 1
    assert route["next_buses"][0]["destination_en"] == "TEST DEST TERMINUS"


@pytest.mark.anyio
async def test_no_common_route(monkeypatch):
    _install_patches(monkeypatch, dest_stops=[
        Stop(stop="STOP9", name_en="Nowhere", name_tc="無", name_sc="无", lat="22.34", long="114.15"),
    ])
    payload = await kmb_service.find_route_between_addresses("Origin Place", "Destination Place")
    assert payload["routes_count"] == 0
    assert payload["routes"] == []
    assert "message" in payload


@pytest.mark.anyio
async def test_geocode_failure_origin(monkeypatch):
    _install_patches(monkeypatch)
    payload = await kmb_service.find_route_between_addresses("Nowhere Origin", "Destination Place")
    assert payload.get("error") == "Origin address not found"


@pytest.mark.anyio
async def test_geocode_failure_destination(monkeypatch):
    _install_patches(monkeypatch)
    payload = await kmb_service.find_route_between_addresses("Origin Place", "Nowhere Destination")
    assert payload.get("error") == "Destination address not found"


def test_rank_direct_routes_ranking():
    lanes = _lane_stops([
        ("2", "O", "1", 1, "STOPA"), ("2", "O", "1", 2, "STOPB"), ("2", "O", "1", 3, "STOPC"),
        ("1", "O", "1", 1, "STOPB"), ("1", "O", "1", 2, "STOPC"),
    ])
    # STOPA is right next to the origin; STOPB is far away. Route 2 serves STOPA,
    # route 1 only serves STOPB, so route 2 wins on walking distance.
    origin_stops = [
        Stop(stop="STOPA", name_en="A", name_tc="A", name_sc="A", lat="22.301", long="114.101"),
        Stop(stop="STOPB", name_en="B", name_tc="B", name_sc="B", lat="22.309", long="114.109"),
    ]
    dest_stops = [Stop(stop="STOPC", name_en="C", name_tc="C", name_sc="C", lat="22.311", long="114.121")]
    ranked = kmb_service.rank_direct_routes(
        origin_stops, dest_stops, (22.3001, 114.1001), (22.3101, 114.1201), lanes, top_n=5)
    # Route 2 joins A->C (short walk), route 1 joins B->C (long walk).
    assert [r["route"] for r in ranked] == ["2", "1"]
    assert ranked[0]["stops_between"] == 1
    assert ranked[1]["stops_between"] == 0
    # Ranking is by total walking distance first.
    assert ranked[0]["walk_km_total"] < ranked[1]["walk_km_total"]


@pytest.mark.anyio
async def test_route_between_tool_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert "kmb_find_route_between_addresses" in {t.name for t in tools.tools}


@pytest.mark.anyio
@pytest.mark.network
async def test_route_between_smoke():
    """Live smoke: Chuk Yuen Estate -> Tsim Sha Tsui Star Ferry is served by route 1."""
    payload = await _call("kmb_find_route_between_addresses", {
        "origin_address": "Chuk Yuen Estate, Sheung Fung Street, Kowloon",
        "destination_address": "Star Ferry Pier, Tsim Sha Tsui, Kowloon",
        "top_n": 3,
    })
    assert isinstance(payload, dict)
    if "routes" in payload:
        assert payload["routes_count"] == len(payload["routes"])
        for route in payload["routes"]:
            assert {"route", "bound", "boarding_stop", "alighting_stop"} <= set(route)
            assert route["boarding_stop"]["stop_id"]
            assert route["alighting_stop"]["stop_id"]


def test_rest_endpoint_registered():
    from main import app
    paths = [route.path for route in app.routes]
    assert any("/kmb_router/route_between/address/" in p for p in paths)
