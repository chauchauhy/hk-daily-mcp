# pylint: disable=W0613,W1203,E1136,W0718
"""Shared HKO weather workflows used by both the FastAPI routers and the MCP tools."""
import logging

from utils import hko_util

logger = logging.getLogger(__name__)


async def get_weather_forecast(lang: str = "tc"):
    logger.info(f"Fetching HKO weather forecast for language: {lang}...")
    try:
        data = await hko_util.HKORouterUtil.fetch_hko_flw_data(lang)
        return data.model_dump(mode="json") if data is not None else None
    except Exception as e:
        logger.error(f"Error in get_weather_forecast: {str(e)}")
        return {"error": str(e)}


async def get_nearby_weather(address: str, lang: str = "tc", top_n: int = 1, user_coords=None) -> dict:
    logger.info(f"Finding nearby weather stations for address: {address}, language: {lang}")
    try:
        util = hko_util.get_global_hko_router_util()
        return await util.find_nearby_weather_stations(
            address=address, lang=lang, top_n=top_n, user_coords=user_coords
        )
    except Exception as e:
        logger.error(f"Error in get_nearby_weather: {str(e)}")
        return {"error": str(e)}
