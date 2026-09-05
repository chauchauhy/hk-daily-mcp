
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
