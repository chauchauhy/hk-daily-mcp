## pylint disable=W0613,W1203,E1136,W0718
import re
import asyncio
import logging
import requests
from datetime import datetime, timezone

from fastapi import APIRouter

from utils.env_load_util import EnvLoadUtil
from utils import kmb_util
from utils.hko_util import get_global_hko_router_util

router = APIRouter(prefix="/openclaw_router", tags=["openclaw_router"])
logger = logging.getLogger(__name__)

def _clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'[^\w\s]', ' ', text).strip()


def _calc_remaining_minutes(eta_str: str) -> int | None:
    if not eta_str:
        return None
    try:
        eta_dt = datetime.fromisoformat(eta_str)
        now = datetime.now(timezone.utc)
        if eta_dt.tzinfo is None:
            eta_dt = eta_dt.replace(tzinfo=timezone.utc)
        remaining = int((eta_dt - now).total_seconds() / 60)
        return max(0, remaining)
    except Exception:
        return None


def _get_news_summary(keyword: str) -> list:
    newsapi_key = EnvLoadUtil.load_env("NEWS_API_KEY")
    if not newsapi_key:
        logger.error("NEWS_API_KEY is not set or empty in .env")
        return []
    
    url = ('https://newsapi.org/v2/everything?'
       'q={keyword}&'
       'sortBy=publishedAt&'
       'language=en&'
       'apiKey={newsapi_key}').format(keyword=keyword, newsapi_key=newsapi_key)
    
    try:
        response = requests.get(url)
        news_data = response.json()
        
        logger.info(f"Raw response status: {news_data.get('status')}")
        logger.info(f"Total results: {news_data.get('totalResults')}")
        logger.info(f"Articles count: {len(news_data.get('articles', []))}")

        result = []
        for article in news_data.get('articles', [])[:10]:
            description = article.get('description') or ""
            logger.info(f"Article desc length: {len(description)} | title: {article.get('title','')[:40]}")
            if len(description) > 30:
                result.append({
                    "source": _clean_text(article['source']['name']),
                    "title": _clean_text(article['title']),
                    "description": _clean_text(description),
                    "publishedAt": article['publishedAt'],
                })
        
        logger.info(f"Returning {len(result)} news articles")
        return result
                
    except Exception as e:
        logger.error(f"Error fetching news summary: {str(e)}")
        return []


async def _weather_task(address: str, lang: str, user_coords: tuple | None) -> dict:
    try:
        hko_util = get_global_hko_router_util()
        weather_data = await hko_util.find_nearby_weather_stations(
            address, lang=lang, user_coords=user_coords
        )
        if weather_data is None or "error" not in weather_data:
            return {
                "record_time": weather_data.get("record_time"),
                "nearby_stations": [
                    {
                        "place": s["place"],
                        "temperature": s["value"],
                        "unit": s["unit"],
                        "distance_m": s["distance_km"],
                    }
                    for s in weather_data.get("nearby_stations", [])
                ],
            }
        return weather_data
    except Exception as e:
        logger.error(f"Weather fetch failed: {str(e)}")
        return {"error": str(e)}


async def _transport_task(lat: float, lon: float, route_filter: str) -> dict:
    try:
        nearby_stops = await kmb_util.KMBRouterUtil.load_near_stop_with_lat_lon(
            str(lat), str(lon)
        )
        if not nearby_stops:
            return {
                "route": route_filter,
                "stops": [],
                "search_radius_degrees": float(EnvLoadUtil.load_env("KMB_NEAR_STOP_DISTANCE", "0.003")),
            }

        # Fetch all stop ETAs concurrently instead of sequentially
        eta_responses = await asyncio.gather(
            *[kmb_util.KMBRouterUtil.fetch_kmb_eta_stop_by_stop_id(stop.stop) for stop in nearby_stops],
            return_exceptions=True,
        )

        stops_summary = []
        for stop, eta_response in zip(nearby_stops, eta_responses):
            if isinstance(eta_response, Exception):
                logger.error(f"ETA fetch failed for stop {stop.stop}: {str(eta_response)}")
                continue
            eta_entries = []
            if eta_response and eta_response.data:
                for eta in eta_response.data:
                    if eta.route == route_filter:
                        eta_entries.append({
                            "route": eta.route,
                            "destination_tc": eta.dest_tc,
                            "destination_en": eta.dest_en,
                            "eta_seq": eta.eta_seq,
                            "remaining_minutes": _calc_remaining_minutes(eta.eta),
                        })
            if eta_entries:
                stops_summary.append({
                    "stop_id": stop.stop,
                    "stop_name_tc": stop.name_tc,
                    "stop_name_en": stop.name_en,
                    "eta": eta_entries,
                })

        return {
            "route": route_filter,
            "search_radius_degrees": float(EnvLoadUtil.load_env("KMB_NEAR_STOP_DISTANCE", "0.003")),
            "stops": stops_summary,
        }
    except Exception as e:
        logger.error(f"Transport fetch failed: {str(e)}")
        return {"error": str(e)}


@router.get("/")
async def get_hko_router():
    return {"message": "This is the openclaw_router endpoint"}


@router.get("/dailySummary/{lang}/{keyword}/{address}/{router}")
async def get_daily_summary(lang: str, keyword: str,address: str, router: str):
    logger.info(f"Fetching daily summary for language: {lang}, address: {address}, router: {router}, keyword: {keyword}...")

    # Geocode once — shared by weather and transport; failures yield empty sections, not 500
    try:
        lat_lon = await kmb_util.KMBRouterUtil.get_lat_lon_from_address(address)
    except Exception as e:
        logger.error(f"Geocoding raised unexpectedly for '{address}': {str(e)}")
        lat_lon = {"error": str(e)}

    if "error" in lat_lon:
        logger.warning(f"Geocoding failed for '{address}', weather will attempt its own geocode")
        lat, lon, user_coords = None, None, None
    else:
        lat, lon = lat_lon["latitude"], lat_lon["longitude"]
        user_coords = (lat, lon)

    weather_result, transport_result, news_result = await asyncio.gather(
        _weather_task(address, lang, user_coords),
        _transport_task(lat, lon, router) if user_coords else asyncio.sleep(0, result={"error": "Geocoding failed"}),
        asyncio.to_thread(_get_news_summary, keyword),
        return_exceptions=True,
    )

    if isinstance(weather_result, Exception):
        weather_result = {"error": str(weather_result)}
    if isinstance(transport_result, Exception):
        transport_result = {"error": str(transport_result)}
    if isinstance(news_result, Exception):
        logger.error(f"News task raised an exception: {str(news_result)}")
        news_result = []

    return {
        "address": address,
        "lang": lang,
        "weather": weather_result,
        "transport": transport_result,
        "news": news_result,
    }
