# pylint: disable=W0603,E0402

import asyncio

import httpx
from .env_load_util import EnvLoadUtil 

class HttpxUtil:

    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def post(self, url: str, data: dict = None, headers: dict = None) -> httpx.Response:
        response = await self.client.post(url, json=data, headers=headers)
        return response
    
    async def get_all(self, url: str) -> httpx.Response:
        response = await self._get(url, params=None, headers=None)
        return response

    async def _get(self, url: str, params: dict = None, headers: dict = None) -> httpx.Response:
        response: httpx.Response = None
        if params is None or headers is None:
            response = await self.client.get(url)
        else:
            response = await self.client.get(url, params=params, headers=headers)
        return response
    
    async def close(self):
        await self.client.aclose()


_GOLBAL_HTTPX_UTIL_INSTANCE = None
_GOLBAL_HTTPX_UTIL_LOOP = None
def get_global_httpx_util() -> HttpxUtil:
    # The AsyncClient binds to the event loop that first uses it, so keep
    # one instance per running loop (server reloads and test runners that
    # create a loop per test would otherwise reuse a stale, closed loop).
    global _GOLBAL_HTTPX_UTIL_INSTANCE, _GOLBAL_HTTPX_UTIL_LOOP
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None
    if _GOLBAL_HTTPX_UTIL_INSTANCE is None or _GOLBAL_HTTPX_UTIL_LOOP is not running_loop:
        timeout = int(EnvLoadUtil.load_env("DEFAULT_HTTPX_TIMEOUT", 60))
        _GOLBAL_HTTPX_UTIL_INSTANCE = HttpxUtil(timeout=timeout)
        _GOLBAL_HTTPX_UTIL_LOOP = running_loop
    return _GOLBAL_HTTPX_UTIL_INSTANCE