"""Shared pytest fixtures for offline service tests."""
import pytest

import utils.air_quality_service
import utils.ferry_service
import utils.hko_util
import utils.holiday_service
import utils.kmb_util
import utils.mtr_service
import utils.tide_service

from helpers import FakeHttpClient

# Modules that import get_global_httpx_util into their own namespace; each
# must be patched where it is looked up.
_HTTPX_CONSUMERS = (
    utils.tide_service,
    utils.holiday_service,
    utils.air_quality_service,
    utils.ferry_service,
    utils.mtr_service,
    utils.hko_util,
    utils.kmb_util,
)


@pytest.fixture
def fake_http(monkeypatch):
    """Swap the global httpx client for a canned-response fake.

    Usage: ``fake_http.set_response(FakeResponse(...), url_substring)``
    before calling the service under test.
    """
    client = FakeHttpClient()
    for module in _HTTPX_CONSUMERS:
        monkeypatch.setattr(module, "get_global_httpx_util", lambda: client)
    return client
