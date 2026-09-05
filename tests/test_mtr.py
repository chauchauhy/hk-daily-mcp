
import pytest

from mcp import Client

from mcp_server import mcp

from helpers import call_mcp as _call


@pytest.mark.anyio
async def test_mtr_tool_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert "mtr_get_next_train" in {t.name for t in tools.tools}




@pytest.mark.anyio
@pytest.mark.network
async def test_mtr_next_train_codes_smoke():
    payload = await _call("mtr_get_next_train", {"line": "TWL", "station": "TSW"})
    assert isinstance(payload, dict)
    assert "up" in payload or "error" in payload
    if "up" in payload:
        assert payload["line"] == "TWL"
        assert payload["station"] == "TSW"
        assert isinstance(payload["up"], list) and isinstance(payload["down"], list)
        if payload["up"]:
            assert {"dest", "plat", "time", "ttnt"} <= set(payload["up"][0])


@pytest.mark.anyio
@pytest.mark.network
async def test_mtr_next_train_names_smoke():
    payload = await _call("mtr_get_next_train", {"line": "Tsuen Wan", "station": "Tsim Sha Tsui"})
    assert isinstance(payload, dict)
    assert payload.get("line") == "TWL" and payload.get("station") == "TST"


@pytest.mark.anyio
@pytest.mark.network
async def test_mtr_next_train_invalid_line():
    payload = await _call("mtr_get_next_train", {"line": "NOWHERE", "station": "TSW"})
    assert isinstance(payload, dict)
    assert "error" in payload
