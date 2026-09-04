# pylint: disable=W0613,W1203,E1136,W0718
"""Shared KMB workflows used by both the FastAPI routers and the MCP tools."""
import logging

from utils import kmb_util
from utils.env_load_util import EnvLoadUtil

logger = logging.getLogger(__name__)


def _build_stop_info(stop, eta_response, route_filter: str = None) -> dict:
    """Build a stop info dict with ETA data, optionally filtered by route number."""
    stop_info = {
        "stop_id": stop.stop,
        "stop_name_en": stop.name_en,
        "stop_name_tc": stop.name_tc,
        "stop_name_sc": stop.name_sc,
        "latitude": stop.lat,
        "longitude": stop.long,
        "eta_data": [],
    }
    if eta_response and eta_response.data:
        for eta in eta_response.data:
            if route_filter is None or eta.route == route_filter:
                stop_info["eta_data"].append({
                    "route": eta.route,
                    "destination_en": eta.dest_en,
                    "destination_tc": eta.dest_tc,
                    "destination_sc": eta.dest_sc,
                    "eta": eta.eta,
                    "eta_seq": eta.eta_seq,
                    "direction": eta.dir,
                    "service_type": eta.service_type,
                    "remarks_en": eta.rmk_en,
                    "remarks_tc": eta.rmk_tc,
                    "remarks_sc": eta.rmk_sc,
                })
        logger.info(f"Stop {stop.stop}: Found {len(stop_info['eta_data'])} ETA entries")
    else:
        logger.info(f"Stop {stop.stop}: No ETA data available")
    return stop_info


async def fetch_all_kmb_routes():
    logger.info("Fetching all KMB router data...")
    try:
        data = await kmb_util.KMBRouterUtil.fetch_all_kmb_router()
        return data.model_dump(mode="json") if data is not None else None
    except Exception as e:
        logger.error(f"Error in fetch_all_kmb_routes: {str(e)}")
        return {"error": str(e)}


async def find_nearby_stops(lat: str, lon: str) -> dict:
    logger.info(f"Finding KMB stops near lat: {lat}, lon: {lon}...")
    try:
        nearby_stops = await kmb_util.KMBRouterUtil.load_near_stop_with_lat_lon(lat, lon)
        return {"nearby_stops": [stop.model_dump(mode="json") for stop in nearby_stops]}
    except Exception as e:
        logger.error(f"Error in find_nearby_stops: {str(e)}")
        return {"error": str(e)}


async def find_stops_by_address(address: str) -> list:
    logger.info(f"Finding KMB stops near address: {address}...")
    try:
        stops = await kmb_util.KMBRouterUtil.load_near_stop_with_address(address)
        return [stop.model_dump(mode="json") for stop in stops]
    except Exception as e:
        logger.error(f"Error in find_stops_by_address: {str(e)}")
        return {"error": str(e)}


async def get_stop_eta_workflow(address: str, route_filter: str = None) -> dict:
    """Shared ETA workflow: geocode address -> nearby stops -> ETAs."""
    lat_lon = await kmb_util.KMBRouterUtil.get_lat_lon_from_address(address)
    if "error" in lat_lon:
        logger.error(f"Geocoding failed for address: {address}")
        return {
            "error": "Address not found",
            "address": address,
            "details": "Could not geocode the provided address. Please check the address and try again.",
        }

    latitude, longitude = lat_lon["latitude"], lat_lon["longitude"]
    logger.info(f"Geocoded to: lat={latitude}, lon={longitude}")

    nearby_stops = await kmb_util.KMBRouterUtil.load_near_stop_with_lat_lon(str(latitude), str(longitude))
    if not nearby_stops:
        logger.warning(f"No nearby stops found for lat={latitude}, lon={longitude}")
        return {
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "nearby_stops_count": 0,
            "stops_with_eta": [],
            "message": "No bus stops found nearby. Try a different address or increase search radius.",
        }

    logger.info(f"Found {len(nearby_stops)} nearby stops. Fetching ETAs...")
    stops_with_eta = []
    for stop in nearby_stops:
        try:
            eta_response = await kmb_util.KMBRouterUtil.fetch_kmb_eta_stop_by_stop_id(stop.stop)
            stops_with_eta.append(_build_stop_info(stop, eta_response, route_filter))
        except Exception as eta_error:
            logger.error(f"Failed to fetch ETA for stop {stop.stop}: {str(eta_error)}")
            stops_with_eta.append({
                **_build_stop_info(stop, None),
                "error": f"Failed to fetch ETA: {str(eta_error)}",
            })

    logger.info(f"Workflow complete. Returning data for {len(stops_with_eta)} stops")
    return {
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "nearby_stops_count": len(nearby_stops),
        "stops_with_eta": stops_with_eta,
        "search_radius_degrees": float(EnvLoadUtil.load_env("KMB_NEAR_STOP_DISTANCE", "0.003")),
    }
