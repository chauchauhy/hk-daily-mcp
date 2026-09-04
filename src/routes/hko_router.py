## pylint disable=W0613,W1203,E1136,W0718
import logging

from fastapi import APIRouter

from utils import weather_service

router = APIRouter(prefix="/hko_router", tags=["hko_router"])

logger = logging.getLogger(__name__)

@router.get("/")
async def get_hko_router():
    return {"message": "This is the HKO Router endpoint"}

@router.get("/{lang}/flw")
async def get_hko_flw(lang: str = "tc"):
    logger.info(f"Fetching HKO FLW data for language: {lang}...")
    try:
        return await weather_service.get_weather_forecast(lang)
    except Exception as e:
        logger.error(f"Error in get_hko_flw: {str(e)}")
        return {"error": str(e)}

@router.get("/{lang}/rhrread/{address}")
async def get_nearby_weather_stations(address: str, lang: str = "tc", top_n: int = 1):
    logger.info(f"Finding nearby weather stations for address: {address}, language: {lang}")
    try:
        return await weather_service.get_nearby_weather(address, lang, top_n)
    except Exception as e:
        logger.error(f"Error in get_nearby_weather_stations: {str(e)}")
        return {"error": str(e)}
