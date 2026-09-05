
import pytest

from mcp import Client

from mcp_server import mcp

from helpers import call_mcp as _call


@pytest.mark.anyio
async def test_holiday_tide_tools_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools.tools}
    assert {"hk_get_public_holidays", "hko_get_tide_predictions"} <= names




@pytest.mark.anyio
@pytest.mark.network
async def test_public_holidays_smoke():
    payload = await _call("hk_get_public_holidays", {"year": 2026})
    assert isinstance(payload, dict)
    assert "holidays" in payload or "error" in payload
    if "holidays" in payload:
        assert payload["year"] == 2026
        assert len(payload["holidays"]) > 0
        first = payload["holidays"][0]
        assert {"date", "name"} <= set(first)
        names = [h["name"] for h in payload["holidays"]]
        assert any("Lunar New Year" in n for n in names)


@pytest.mark.anyio
@pytest.mark.network
async def test_public_holidays_unknown_year():
    payload = await _call("hk_get_public_holidays", {"year": 1999})
    assert isinstance(payload, dict)
    assert payload.get("holidays") == []


@pytest.mark.anyio
@pytest.mark.network
async def test_tide_predictions_smoke():
    payload = await _call("hko_get_tide_predictions", {"station": "CCH", "date": "2026-01-15"})
    assert isinstance(payload, dict)
    assert "tides" in payload or "error" in payload
    if "tides" in payload:
        assert len(payload["tides"]) > 0
        for event in payload["tides"]:
            assert {"time", "height_m", "type"} <= set(event)
            assert event["type"] in ("high", "low")


@pytest.mark.anyio
@pytest.mark.network
async def test_tide_predictions_invalid_station():
    payload = await _call("hko_get_tide_predictions", {"station": "NOWHERE"})
    assert isinstance(payload, dict)
    assert "error" in payload
