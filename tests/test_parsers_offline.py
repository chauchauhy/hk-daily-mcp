"""Offline unit tests for the data parsers (no network, no MCP client).

Covers the parsing logic that the live smoke tests only exercise indirectly:
tide CSV, AQHI RSS, holiday JSON, Star Ferry CSV, Sun Ferry/operator aliases,
MTR line/station resolution, daily-summary helpers and the httpx utility.
"""
import json

import pytest

import utils.air_quality_service as aq_service
import utils.ferry_service as ferry_service
import utils.holiday_service as holiday_service
import utils.mtr_service as mtr_service
import utils.tide_service as tide_service
import utils.httpx_util as httpx_util
import utils.hko_util as hko_util
from utils.daily_summary_service import _calc_remaining_minutes

from helpers import FakeResponse


# ---------- httpx utility ----------

@pytest.mark.anyio
async def test_httpx_get_passes_params_without_headers():
    util = httpx_util.HttpxUtil(timeout=5)
    captured = {}

    async def fake_get(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(200)

    util.client.get = fake_get  # type: ignore[method-assign]
    try:
        response = await util._get("http://example.test", params={"a": "1"}, headers=None)
    finally:
        await util.close()
    assert response.status_code == 200
    assert captured["params"] == {"a": "1"}
    assert captured["follow_redirects"] is False
    assert "headers" not in captured


@pytest.mark.anyio
async def test_httpx_get_passes_headers_without_params():
    util = httpx_util.HttpxUtil(timeout=5)
    captured = {}

    async def fake_get(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(200)

    util.client.get = fake_get  # type: ignore[method-assign]
    try:
        await util._get("http://example.test", params=None, headers={"X-Test": "y"})
    finally:
        await util.close()
    assert captured["headers"] == {"X-Test": "y"}
    assert "params" not in captured


# ---------- tide CSV ----------

_TIDE_CSV = (
    "\ufeffMonth,Date,Time,Height(m),Time,Height(m)\n"
    "1,15,00:23,1.2,06:45,2.1\n"
    "1,15,12:00,0.9,18:30,1.8\n"
    "1,16,00:30,1.1,07:00,2.2\n"
)


@pytest.mark.anyio
async def test_tide_parses_rows_and_labels_high_low(fake_http):
    fake_http.set_response(FakeResponse(200, text=_TIDE_CSV))
    payload = await tide_service.get_tide_predictions("CCH", "2026-01-15")
    assert "error" not in payload
    assert payload["count"] == 4
    times = [e["time"] for e in payload["tides"]]
    assert times == ["00:23", "06:45", "12:00", "18:30"]
    types = [e["type"] for e in payload["tides"]]
    assert types == ["low", "high", "low", "high"]


@pytest.mark.anyio
async def test_tide_filters_other_dates(fake_http):
    fake_http.set_response(FakeResponse(200, text=_TIDE_CSV))
    payload = await tide_service.get_tide_predictions("CCH", "2026-01-16")
    assert payload["count"] == 2
    assert [e["time"] for e in payload["tides"]] == ["00:30", "07:00"]


@pytest.mark.anyio
async def test_tide_invalid_station_and_date():
    payload = await tide_service.get_tide_predictions("NOWHERE")
    assert "error" in payload and "valid_stations" in payload
    payload = await tide_service.get_tide_predictions("CCH", "01-15")
    assert "error" in payload


# ---------- AQHI RSS ----------

_AQHI_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>Mong Kok</title><description>Mong Kok - Roadside Stations: 6 Moderate - Fri, 04 Sep 2026 20:30</description></item>
<item><title>Central</title><description>Central - General Stations: 3 Low - Fri, 04 Sep 2026 20:30</description></item>
<item><title>Central</title><description>Central - Roadside Stations: 7 High - Fri, 04 Sep 2026 20:30</description></item>
</channel></rss>"""


@pytest.mark.anyio
async def test_aqhi_parses_all(fake_http):
    fake_http.set_response(FakeResponse(200, content=_AQHI_XML.encode("utf-8")))
    payload = await aq_service.get_air_quality("all")
    assert payload["count"] == 3
    assert {r["station"] for r in payload["stations"]} == {"Mong Kok", "Central"}
    first = payload["stations"][0]
    assert {"station", "station_type", "aqhi", "band", "observed_at"} <= set(first)
    assert isinstance(first["aqhi"], int)


@pytest.mark.anyio
async def test_aqhi_exact_and_partial_match(fake_http):
    fake_http.set_response(FakeResponse(200, content=_AQHI_XML.encode("utf-8")))
    exact = await aq_service.get_air_quality("Mong Kok")
    assert exact["count"] == 1 and exact["stations"][0]["station"] == "Mong Kok"
    partial = await aq_service.get_air_quality("Cent")
    assert "error" in partial and partial["error"] == "Ambiguous station: Cent"


@pytest.mark.anyio
async def test_aqhi_unknown_station(fake_http):
    fake_http.set_response(FakeResponse(200, content=_AQHI_XML.encode("utf-8")))
    payload = await aq_service.get_air_quality("Nowhere")
    assert "error" in payload and "valid_stations" in payload


# ---------- public holidays ----------

_HOLIDAYS = {
    "vcalendar": [{"vevent": [
        {"dtstart": ["20260101"], "summary": "The first day of January"},
        {"dtstart": ["20260217"], "summary": "Lunar New Year's Day"},
        {"dtstart": ["20270101"], "summary": "The first day of January"},
    ]}]
}


@pytest.mark.anyio
async def test_holidays_parses_and_filters_year(fake_http):
    content = b"\xef\xbb\xbf" + json.dumps(_HOLIDAYS).encode("utf-8")
    fake_http.set_response(FakeResponse(200, content=content))
    payload = await holiday_service.get_public_holidays(2026, "en")
    assert payload["year"] == 2026
    assert [h["name"] for h in payload["holidays"]] == [
        "The first day of January", "Lunar New Year's Day"]
    assert "2027" in payload["available_years"]


@pytest.mark.anyio
async def test_holidays_unknown_year(fake_http):
    content = b"\xef\xbb\xbf" + json.dumps(_HOLIDAYS).encode("utf-8")
    fake_http.set_response(FakeResponse(200, content=content))
    payload = await holiday_service.get_public_holidays(1999, "en")
    assert payload["holidays"] == []


@pytest.mark.anyio
async def test_holidays_invalid_lang_and_year():
    payload = await holiday_service.get_public_holidays(2026, "xx")
    assert "error" in payload
    payload = await holiday_service.get_public_holidays("not-a-year", "en")
    assert "error" in payload


# ---------- Star Ferry timetable CSV ----------

_STARFERRY_CSV = (
    "version,1\n"
    "Direction,Service Days,Hours,Frequency (min)\n"
    "Central - Tsim Sha Tsui,Mon-Sat,06:30-23:30,6-12\n"
    "Central - Tsim Sha Tsui,Sun & Public Holidays,06:30-23:30,6-12\n"
)


@pytest.mark.anyio
async def test_starferry_parses_timetable(fake_http):
    fake_http.set_response(FakeResponse(200, content=_STARFERRY_CSV.encode("utf-8-sig")))
    payload = await ferry_service.get_ferry_schedule("starferry", "central")
    assert payload["operator"] == "starferry"
    assert payload["count"] == 2
    assert payload["timetable"][0]["direction"] == "Central - Tsim Sha Tsui"
    assert "hours" in payload["timetable"][0]


@pytest.mark.anyio
async def test_starferry_unknown_route():
    payload = await ferry_service.get_ferry_schedule("starferry", "nowhere")
    assert "error" in payload


def test_sunferry_route_resolution():
    assert ferry_service._resolve_sunferry_route("CECC") == ["CECC"]
    assert ferry_service._resolve_sunferry_route("Central to Cheung Chau") == ["CECC"]
    assert ferry_service._resolve_sunferry_route("Nope") == []


def test_ferry_operator_aliases():
    assert ferry_service.OPERATOR_ALIASES["sun ferry"] == "sunferry"
    assert ferry_service.OPERATOR_ALIASES["star ferry"] == "starferry"
    assert "hkkf" in ferry_service.OPERATOR_ALIASES


# ---------- MTR resolution (bundled CSV, offline) ----------

def test_mtr_line_resolution():
    assert mtr_service._resolve_line("TWL") == "TWL"
    assert mtr_service._resolve_line("tsuen wan") == "TWL"
    assert mtr_service._resolve_line("Tsuen Wan Line") == "TWL"
    assert mtr_service._resolve_line("disneyland resort line") == "DRL"
    assert mtr_service._resolve_line("nowhere") is None


def test_mtr_station_resolution():
    by_code = mtr_service._resolve_station("TSW", "TWL")
    assert by_code is not None and by_code["station_code"] == "TSW"
    by_name = mtr_service._resolve_station("Tsim Sha Tsui", "TWL")
    assert by_name is not None and by_name["station_code"] == "TST"
    unknown = mtr_service._resolve_station("Atlantis", "TWL")
    assert unknown is None


# ---------- daily summary helpers ----------


def test_calc_remaining_minutes():
    assert _calc_remaining_minutes(None) is None
    assert _calc_remaining_minutes("garbage") is None
    assert _calc_remaining_minutes("2026-01-01T00:00:00+00:00") == 0  # long past -> 0
    future = "2099-01-01T00:00:00+00:00"
    minutes = _calc_remaining_minutes(future)
    assert minutes is not None and minutes > 0

# ---------- HKO nearby weather (bundle + geocode fallback, offline) ----------

_RHRREAD = {
    "rainfall": {
        "data": [{"unit": "mm", "place": "中西區", "max": 0, "main": "0"}],
        "startTime": "2026-09-05T10:00:00+08:00",
        "endTime": "2026-09-05T11:00:00+08:00",
    },
    "warningMessage": [],
    "icon": [50],
    "iconUpdateTime": "2026-09-05T11:30:00+08:00",
    "uvindex": {
        "data": [{"place": "King's Park", "value": 3.0, "desc": "中", "message": ""}],
        "recordDesc": "",
    },
    "updateTime": "2026-09-05T11:30:00+08:00",
    "temperature": {
        "data": [{"place": "King's Park", "value": 28, "unit": "C"}],
        "recordTime": "2026-09-05T11:30:00+08:00",
    },
    "tcmessage": "",
    "mintempFrom00To09": "",
    "rainfallFrom00To12": "",
    "rainfallLastMonth": "",
    "rainfallJanuaryToLastMonth": "",
    "humidity": {
        "recordTime": "2026-09-05T11:30:00+08:00",
        "data": [{"unit": "percent", "value": 70, "place": "Hong Kong Observatory"}],
    },
}


@pytest.mark.anyio
async def test_hko_nearby_weather_offline(fake_http, monkeypatch):
    """Bundle coords + to_thread geocode fallback produce distances offline."""
    monkeypatch.setattr(
        hko_util.HKORouterUtil, "_geocode_place",
        lambda self, place, region="Hong Kong": (22.3, 114.1))
    fake_http.set_response(FakeResponse(200, json_data=_RHRREAD))

    util = hko_util.get_global_hko_router_util()
    payload = await util.find_nearby_weather_stations("Tsim Sha Tsui", lang="en", top_n=1)

    assert "error" not in payload, payload
    assert payload["user_coordinates"] == {"lat": 22.3, "lon": 114.1}
    assert payload["nearby_stations"][0]["place"] == "King's Park"
    assert isinstance(payload["nearby_stations"][0]["distance_km"], float)
    assert payload["nearby_stations"][0]["distance_km"] >= 0
    assert payload["nearby_humidity"]["place"] == "Hong Kong Observatory"
    assert payload["nearby_rainfall"]["place"] == "中西區"
    assert payload["uvindex"]["data"][0]["value"] == 3.0
