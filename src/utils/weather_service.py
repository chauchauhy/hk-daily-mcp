# pylint: disable=W0613,W1203,E1136,W0718
"""Shared HKO weather workflows used by both the FastAPI routers and the MCP tools."""
import logging

from models.hko.data_type_enum import DataTypeEnum
from utils import hko_util
from utils.hko_util import HKORouterUtil

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


async def get_9day_forecast(lang: str = "tc") -> dict:
    logger.info(f"Fetching HKO 9-day forecast for language: {lang}...")
    try:
        data = await HKORouterUtil.fetch_hk_weather_data(DataTypeEnum.FND, lang)
        return data if data else {"error": "Failed to fetch 9-day forecast"}
    except Exception as e:
        logger.error(f"Error in get_9day_forecast: {str(e)}")
        return {"error": str(e)}


async def get_weather_warnings(lang: str = "tc") -> dict:
    logger.info(f"Fetching HKO weather warnings for language: {lang}...")
    try:
        summary = await HKORouterUtil.fetch_hk_weather_data(DataTypeEnum.WARNSUM, lang)
        details = await HKORouterUtil.fetch_hk_weather_data(DataTypeEnum.WARNINGINFO, lang)
        if not summary and not details:
            return {"error": "Failed to fetch weather warnings"}
        return {"summary": summary or {}, "details": details or {}}
    except Exception as e:
        logger.error(f"Error in get_weather_warnings: {str(e)}")
        return {"error": str(e)}


async def get_special_weather_tips(lang: str = "tc") -> dict:
    logger.info(f"Fetching HKO special weather tips for language: {lang}...")
    try:
        data = await HKORouterUtil.fetch_hk_weather_data(DataTypeEnum.SWT, lang)
        return data if data else {"error": "Failed to fetch special weather tips"}
    except Exception as e:
        logger.error(f"Error in get_special_weather_tips: {str(e)}")
        return {"error": str(e)}
