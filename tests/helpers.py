"""Shared test helpers: in-memory MCP client calls + a fake HTTP layer.

The service layer talks to third-party APIs through
``get_global_httpx_util().get_all(url)``; ``FakeHttpClient`` lets offline
tests return canned payloads without any network access.
"""
import json

from mcp import Client

from mcp_server import mcp


async def call_mcp(tool: str, args: dict):
    """Call an MCP tool through the in-memory client and parse its payload."""
    async with Client(mcp) as client:
        result = await client.call_tool(tool, args)
    assert not result.is_error
    return json.loads(result.content[0].text)


class FakeResponse:
    """Minimal stand-in for httpx.Response used by the service layer."""

    def __init__(self, status_code=200, text="", content=None, json_data=None):
        self.status_code = status_code
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")
        self._json_data = json_data

    def json(self):
        if self._json_data is None:
            raise ValueError("No JSON payload configured for this FakeResponse")
        return self._json_data


class FakeHttpClient:
    """Returns canned responses for get_all(); supports per-URL overrides."""

    def __init__(self, default=None):
        self.default = default if default is not None else FakeResponse(200)
        self.by_substring = {}

    def set_response(self, response, url_substring=None):
        """Install a response for a URL substring, or as the default."""
        if url_substring is None:
            self.default = response
        else:
            self.by_substring[url_substring] = response

    async def get_all(self, url, follow_redirects=False):
        for needle, response in self.by_substring.items():
            if needle in url:
                return response
        return self.default
