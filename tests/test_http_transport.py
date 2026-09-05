"""End-to-end checks for the mounted MCP Streamable HTTP transport.

These run fully in-process (via FastAPI TestClient) and need no network or
open port: they lock in the /mcp mount, the lifespan-run session manager,
the DNS-rebinding Host check, and the initialize -> tools/list handshake a
real MCP host would perform.

NOTE: the FastAPI lifespan runs ``mcp.session_manager.run()`` once, and the
MCP SDK refuses a second run on the same instance (real uvicorn starts the
app exactly once per process, which matches). Tests therefore share a single
module-scoped TestClient so the lifespan runs once.
"""
import json

import pytest
from fastapi.testclient import TestClient

from main import app
from mcp_server import __version__

from test_mcp_registration import EXPECTED_TOOLS

HOST_HEADERS = {"Host": "127.0.0.1:8000"}
MCP_ACCEPT = "application/json, text/event-stream"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _sse_payload(text: str) -> dict:
    """Extract the JSON-RPC message from an SSE (event: / data:) body."""
    if text.startswith("event:"):
        data = "".join(
            line[6:] for line in text.splitlines() if line.startswith("data:")
        )
        return json.loads(data)
    return json.loads(text)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_mcp_http_initialize_and_list_tools(client):
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "http-transport-test", "version": "0.0.1"},
        },
    }
    response = client.post(
        "/mcp",
        json=init,
        headers={**HOST_HEADERS, "Accept": MCP_ACCEPT, "Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text
    session_id = response.headers.get("mcp-session-id")
    assert session_id, "initialize must return an mcp-session-id"
    result = _sse_payload(response.text)["result"]
    assert result["serverInfo"]["name"] == "hk-daily-mcp"
    assert result["serverInfo"]["version"] == __version__

    list_resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers={
            **HOST_HEADERS,
            "Accept": MCP_ACCEPT,
            "Content-Type": "application/json",
            "mcp-session-id": session_id,
        },
    )
    assert list_resp.status_code == 200, list_resp.text
    tools = _sse_payload(list_resp.text)["result"]["tools"]
    assert {t["name"] for t in tools} == EXPECTED_TOOLS
