"""Offline regression tests for the KMB route itinerary direction filter.

The live route-eta feed shares seq numbers across both bounds, so ETAs must
be filtered by direction (O/I) or opposite-bound buses leak into a stop.
These tests pin that behaviour with canned payloads (no network).
"""
import pytest

from models.kmb.stop.stop_response import Stop, StopListResponse
from utils import kmb_service, kmb_util


def _eta(seq, direction, dest):
    return {
        "co": "KMB", "route": "1", "dir": direction, "service_type": 1,
        "seq": seq, "dest_en": dest, "dest_tc": dest, "dest_sc": dest,
        "eta_seq": 1, "eta": "2026-09-05T12:00:00+08:00",
        "rmk_en": "", "rmk_tc": "", "rmk_sc": "",
        "data_timestamp": "2026-09-05T11:00:00+08:00",
    }


async def _fake_route_stops(route, bound, service_type=1):
    return {"data": [
        {"route": route, "bound": bound, "service_type": service_type, "seq": 1, "stop": "STOP1"},
        {"route": route, "bound": bound, "service_type": service_type, "seq": 2, "stop": "STOP2"},
        {"route": route, "bound": bound, "service_type": service_type, "seq": 3, "stop": "STOP3"},
    ]}


async def _fake_stop_list():
    return StopListResponse(type="", version="", generated_timestamp="", data=[
        Stop(stop="STOP1", name_en="Stop One", name_tc="一號站", name_sc="一号站",
             lat="22.30", long="114.10"),
        Stop(stop="STOP2", name_en="Stop Two", name_tc="二號站", name_sc="二号站",
             lat="22.31", long="114.11"),
        Stop(stop="STOP3", name_en="Stop Three", name_tc="三號站", name_sc="三号站",
             lat="22.32", long="114.12"),
    ])


async def _fake_route_eta(route, service_type=1):
    # seq 1 appears for BOTH bounds; seq 2 and 3 only for one bound each.
    return {"data": [
        _eta(1, "O", "Outbound Terminus"),
        _eta(1, "I", "Inbound Terminus"),
        _eta(2, "O", "Outbound Terminus"),
        _eta(3, "I", "Inbound Terminus"),
    ]}


@pytest.fixture
def fake_kmb(monkeypatch):
    monkeypatch.setattr(kmb_util.KMBRouterUtil, "fetch_kmb_route_stops", _fake_route_stops)
    monkeypatch.setattr(kmb_util.KMBRouterUtil, "fetch_kmb_stop", _fake_stop_list)
    monkeypatch.setattr(kmb_util.KMBRouterUtil, "fetch_kmb_route_eta", _fake_route_eta)


@pytest.mark.anyio
async def test_outbound_filters_inbound_etas(fake_kmb):
    payload = await kmb_service.get_route_itinerary("1", "outbound")
    assert "error" not in payload
    assert [stop["seq"] for stop in payload["stops"]] == [1, 2, 3]

    by_seq = {stop["seq"]: stop["etas"] for stop in payload["stops"]}
    assert len(by_seq[1]) == 1
    assert by_seq[1][0]["destination_en"] == "Outbound Terminus"
    assert len(by_seq[2]) == 1
    assert by_seq[2][0]["destination_en"] == "Outbound Terminus"
    assert by_seq[3] == []  # seq 3 carries only an inbound bus


@pytest.mark.anyio
async def test_inbound_filters_outbound_etas(fake_kmb):
    payload = await kmb_service.get_route_itinerary("1", "inbound")
    assert "error" not in payload
    by_seq = {stop["seq"]: stop["etas"] for stop in payload["stops"]}
    assert len(by_seq[1]) == 1
    assert by_seq[1][0]["destination_en"] == "Inbound Terminus"
    assert by_seq[2] == []
    assert by_seq[3][0]["destination_en"] == "Inbound Terminus"


@pytest.mark.anyio
async def test_invalid_bound_rejected():
    payload = await kmb_service.get_route_itinerary("1", "sideways")
    assert "error" in payload
