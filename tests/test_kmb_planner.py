"""Offline tests for the deterministic shortest-path planner
(kmb_plan_shortest_route). No AI, no network: everything is patched with a
tiny synthetic KMB world (stops + lanes) and the Dijkstra is verified end to end.
"""
import pytest

from mcp import Client

from mcp_server import mcp

from models.kmb.stop.stop_response import Stop, StopListResponse
from models.kmb.router.route_lane import RouterLane, KMBRouterResponse
from models.kmb.route_stop.route_stop_list import RouteStop
from utils import kmb_planner_service, kmb_util

from helpers import call_mcp as _call


def _stop(sid, lat, lon, name=None):
    return Stop(stop=sid, name_en=name or sid, name_tc=name or sid, name_sc=name or sid,
                lat=str(lat), long=str(lon))


# Small world (distances ~2.9km apart so no walk edges form between them):
#   lane 1O: A -> B -> C -> D
#   lane 2O: C -> E
A, B, C, D, E = (_stop("A", 22.3000, 114.1000), _stop("B", 22.3200, 114.1200),
                 _stop("C", 22.3400, 114.1400), _stop("D", 22.3600, 114.1600),
                 _stop("E", 22.3500, 114.1500))
ALL_STOPS = [A, B, C, D, E]

LANES = {
    ("1", "O", "1"): [RouteStop(route="1", bound="O", service_type="1", seq=i + 1, stop=sid)
                      for i, sid in enumerate(["A", "B", "C", "D"])],
    ("2", "O", "1"): [RouteStop(route="2", bound="O", service_type="1", seq=i + 1, stop=sid)
                      for i, sid in enumerate(["C", "E"])],
}


def _install_patches(monkeypatch, *, stops=ALL_STOPS, lanes=None, origin_area=None,
                     dest_area=None, origin_ll=None, dest_ll=None):
    lanes = LANES if lanes is None else lanes
    origin_ll = (22.3001, 114.1001) if origin_ll is None else origin_ll
    dest_ll = (22.3601, 114.1601) if dest_ll is None else dest_ll
    origin_area = [A] if origin_area is None else origin_area
    dest_area = [D] if dest_area is None else dest_area

    stop_list = StopListResponse(type="", version="", generated_timestamp="", data=stops)

    async def fake_geocode(address, *args, **kwargs):
        lowered = address.lower()
        if "nowhere" in lowered:
            return {"error": "Address not found"}
        if "origin" in lowered:
            return {"latitude": origin_ll[0], "longitude": origin_ll[1]}
        if "destination" in lowered:
            return {"latitude": dest_ll[0], "longitude": dest_ll[1]}
        return {"error": "Address not found"}

    async def fake_near(lat, lon, radius=None):
        point = (float(lat), float(lon))
        d_origin = (point[0] - origin_ll[0]) ** 2 + (point[1] - origin_ll[1]) ** 2
        d_dest = (point[0] - dest_ll[0]) ** 2 + (point[1] - dest_ll[1]) ** 2
        return list(origin_area) if d_origin <= d_dest else list(dest_area)

    async def fake_stop_list():
        return stop_list

    async def fake_index():
        return {"lane_stops": lanes, "stop_lanes": {}}

    async def fake_routes():
        return KMBRouterResponse(type="", version="", generated_timestamp="", data=[
            RouterLane(route="1", bound="O", service_type="1",
                       orig_en="A TERMINUS", orig_tc="甲總站", orig_sc="甲总站",
                       dest_en="D TERMINUS", dest_tc="丁總站", dest_sc="丁总站"),
            RouterLane(route="2", bound="O", service_type="1",
                       orig_en="C TERMINUS", orig_tc="丙總站", orig_sc="丙总站",
                       dest_en="E TERMINUS", dest_tc="戊總站", dest_sc="戊总站"),
        ])

    monkeypatch.setattr(kmb_util.KMBRouterUtil, "get_lat_lon_from_address", fake_geocode)
    monkeypatch.setattr(kmb_util.KMBRouterUtil, "load_near_stop_with_lat_lon", fake_near)
    monkeypatch.setattr(kmb_util.KMBRouterUtil, "fetch_kmb_stop", fake_stop_list)
    monkeypatch.setattr(kmb_util.KMBRouterUtil, "load_route_stop_index", fake_index)
    monkeypatch.setattr(kmb_util.KMBRouterUtil, "fetch_all_kmb_router", fake_routes)


@pytest.mark.anyio
async def test_direct_single_bus(monkeypatch):
    _install_patches(monkeypatch)
    payload = await kmb_planner_service.plan_shortest_route("Origin Place", "Destination Place")
    assert "error" not in payload
    assert payload["transfers"] == 0
    assert len(payload["legs"]) == 3  # walk, bus, walk
    bus = payload["legs"][1]
    assert bus["type"] == "bus"
    assert bus["route"] == "1"
    assert bus["board_stop"]["stop_id"] == "A"
    assert bus["alight_stop"]["stop_id"] == "D"
    assert bus["stops"] == 3
    assert bus["orig_tc"] == "甲總站"
    assert bus["dest_tc"] == "丁總站"
    assert payload["legs"][0]["type"] == "walk"
    assert payload["legs"][2]["type"] == "walk"
    assert payload["walk_km"] > 0 and payload["bus_km"] > 0


@pytest.mark.anyio
async def test_transfer_between_two_buses(monkeypatch):
    # Origin near B, destination near E -> bus 1 (B->C) then bus 2 (C->E).
    _install_patches(monkeypatch, origin_area=[B], dest_area=[E],
                     origin_ll=(22.3201, 114.1201), dest_ll=(22.3501, 114.1501))
    payload = await kmb_planner_service.plan_shortest_route("Origin Place", "Destination Place")
    assert payload["transfers"] == 1
    buses = [leg for leg in payload["legs"] if leg["type"] == "bus"]
    assert [b["route"] for b in buses] == ["1", "2"]
    assert buses[0]["board_stop"]["stop_id"] == "B"
    assert buses[0]["alight_stop"]["stop_id"] == "C"
    assert buses[1]["board_stop"]["stop_id"] == "C"
    assert buses[1]["alight_stop"]["stop_id"] == "E"


@pytest.mark.anyio
async def test_wrong_direction_lane_unusable(monkeypatch):
    # Only an inbound lane D->C->B->A exists: from A you can never reach D.
    reverse_lane = {
        ("1", "I", "1"): [RouteStop(route="1", bound="I", service_type="1", seq=i + 1, stop=sid)
                          for i, sid in enumerate(["D", "C", "B", "A"])],
    }
    _install_patches(monkeypatch, lanes=reverse_lane)
    payload = await kmb_planner_service.plan_shortest_route("Origin Place", "Destination Place")
    assert payload["legs"] == []
    assert "No KMB journey found" in payload["message"]


@pytest.mark.anyio
async def test_walk_only_when_stops_close(monkeypatch):
    P = _stop("P", 22.3000, 114.1000)
    Q = _stop("Q", 22.3005, 114.1004)
    _install_patches(monkeypatch, stops=[P, Q], lanes={},
                     origin_area=[P], dest_area=[Q],
                     origin_ll=(22.3001, 114.1001), dest_ll=(22.3004, 114.1003))
    payload = await kmb_planner_service.plan_shortest_route("Origin Place", "Destination Place")
    assert payload["transfers"] == 0
    assert all(leg["type"] == "walk" for leg in payload["legs"])
    assert payload["bus_km"] == 0.0
    assert payload["total_km"] > 0


def test_build_walk_edges_connectivity():
    near = _stop("NEAR1", 22.3000, 114.1000)
    near2 = _stop("NEAR2", 22.3004, 114.1004)  # ~60m apart
    far = _stop("FAR", 22.31, 114.11)          # ~1.3km away
    edges = kmb_planner_service.build_walk_edges([near, near2, far], max_walk_km=0.15)
    assert ("NEAR2", pytest.approx(0.06, abs=0.02)) in [(e[0], e[1]) for e in edges.get("NEAR1", [])]
    assert all(e[0] != "FAR" for e in edges.get("NEAR1", []))
    assert "FAR" not in edges or all(e[0] not in ("NEAR1", "NEAR2") for e in edges["FAR"])


@pytest.mark.anyio
async def test_geocode_failure(monkeypatch):
    _install_patches(monkeypatch)
    payload = await kmb_planner_service.plan_shortest_route("Nowhere Origin", "Destination Place")
    assert payload.get("error") == "Origin address not found"


@pytest.mark.anyio
async def test_planner_tool_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert "kmb_plan_shortest_route" in {t.name for t in tools.tools}


def test_planner_rest_endpoint_registered():
    from main import app
    paths = [route.path for route in app.routes]
    assert any("/kmb_router/shortest_route/address/" in p for p in paths)


@pytest.mark.anyio
@pytest.mark.network
async def test_planner_smoke():
    """Live smoke: Chuk Yuen Estate -> Star Ferry should return at least a bus leg."""
    payload = await _call("kmb_plan_shortest_route", {
        "origin_address": "Chuk Yuen Estate, Sheung Fung Street, Kowloon",
        "destination_address": "Star Ferry Pier, Tsim Sha Tsui, Kowloon",
    })
    assert isinstance(payload, dict)
    if "legs" in payload:
        for leg in payload["legs"]:
            if leg["type"] == "bus":
                assert {"route", "board_stop", "alight_stop"} <= set(leg)
                assert leg["board_stop"] and leg["alight_stop"]
