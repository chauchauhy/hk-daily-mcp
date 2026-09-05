
import pytest

from mcp import Client

from mcp_server import mcp

from helpers import call_mcp as _call


@pytest.mark.anyio
async def test_ferry_tool_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert "ferry_get_schedule" in {t.name for t in tools.tools}




@pytest.mark.anyio
@pytest.mark.network
async def test_hkkf_eta_smoke():
    payload = await _call("ferry_get_schedule", {"operator": "hkkf", "route": "2"})
    assert isinstance(payload, dict)
    assert "etas" in payload or "error" in payload
    if "etas" in payload:
        assert len(payload["etas"]) > 0
        assert {"direction", "eta"} <= set(payload["etas"][0])


@pytest.mark.anyio
@pytest.mark.network
async def test_sunferry_eta_smoke():
    payload = await _call("ferry_get_schedule", {"operator": "sunferry", "route": "CECC"})
    assert isinstance(payload, dict)
    assert "vessels" in payload or "error" in payload
    if "vessels" in payload:
        assert len(payload["vessels"]) > 0
        assert {"depart_time", "eta"} <= set(payload["vessels"][0])


@pytest.mark.anyio
@pytest.mark.network
async def test_starferry_timetable_smoke():
    payload = await _call("ferry_get_schedule", {"operator": "starferry", "route": "central"})
    assert isinstance(payload, dict)
    assert "timetable" in payload or "error" in payload
    if "timetable" in payload:
        assert len(payload["timetable"]) > 0
        assert {"direction", "hours"} <= set(payload["timetable"][0])


@pytest.mark.anyio
@pytest.mark.network
async def test_ferry_invalid_operator():
    payload = await _call("ferry_get_schedule", {"operator": "nowhere", "route": "1"})
    assert isinstance(payload, dict)
    assert "error" in payload
