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


async def fetch_kmb_route(route_id: str) -> dict:
    """Fetch the KMB lanes serving a single route number (both bounds/service types)."""
    logger.info(f"Fetching KMB router data for route: {route_id}...")
    try:
        data = await kmb_util.KMBRouterUtil.fetch_all_kmb_router()
        if data is None:
            return {"error": "Failed to fetch KMB routes", "route": route_id}
        key = str(route_id).strip().upper()
        lanes = [lane for lane in data.data if lane.route.upper() == key]
        if not lanes:
            return {"error": f"Route not found: {route_id}", "route": route_id, "count": 0}
        return {
            "route": route_id,
            "count": len(lanes),
            "lanes": [lane.model_dump(mode="json") for lane in lanes],
        }
    except Exception as e:
        logger.error(f"Error in fetch_kmb_route: {str(e)}")
        return {"error": str(e), "route": route_id}


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


BOUND_ALIASES = {
    "inbound": "inbound", "in": "inbound", "i": "inbound",
    "outbound": "outbound", "out": "outbound", "o": "outbound",
}

# route-eta entries carry a dir flag; both directions share seq numbers, so
# ETAs must be filtered by direction or opposite-bound buses leak in.
BOUND_DIR = {"outbound": "O", "inbound": "I"}


async def get_route_itinerary(route: str, bound: str = "outbound", service_type: int = 1) -> dict:
    """Route itinerary: ordered stops of a route bound, each with live ETAs.

    Joins route-stop/{route}/{bound}/{service_type} (stop order) with
    route-eta/{route}/{service_type} (live ETAs keyed by stop seq) and the
    cached full stop list (names + coordinates).
    """
    normalized = BOUND_ALIASES.get(str(bound).lower())
    if normalized is None:
        return {
            "error": f"Invalid bound: {bound}",
            "route": route,
            "details": "bound must be 'inbound' or 'outbound'.",
        }
    logger.info(f"Fetching itinerary for route {route} {normalized} service_type {service_type}...")

    try:
        route_stops = await kmb_util.KMBRouterUtil.fetch_kmb_route_stops(route, normalized, service_type)
        if not route_stops or not route_stops.get("data"):
            return {
                "error": "Route stops not found",
                "route": route,
                "bound": normalized,
                "service_type": service_type,
                "details": "No stop list returned. Check the route number and service type.",
            }

        # Stop details come from the cached full stop list (no per-stop HTTP).
        stop_list = await kmb_util.KMBRouterUtil.fetch_kmb_stop()
        stop_by_id = {stop.stop: stop for stop in stop_list.data} if stop_list else {}

        route_etas = await kmb_util.KMBRouterUtil.fetch_kmb_route_eta(route, service_type) or {}
        dir_filter = BOUND_DIR[normalized]
        etas_by_seq: dict[int, list] = {}
        for entry in route_etas.get("data", []):
            if entry.get("dir") != dir_filter:
                continue
            try:
                seq_key = int(entry.get("seq", 0))
            except (TypeError, ValueError):
                continue
            etas_by_seq.setdefault(seq_key, []).append({
                "eta_seq": entry.get("eta_seq"),
                "eta": entry.get("eta"),
                "destination_en": entry.get("dest_en"),
                "destination_tc": entry.get("dest_tc"),
                "destination_sc": entry.get("dest_sc"),
                "remarks_en": entry.get("rmk_en"),
                "remarks_tc": entry.get("rmk_tc"),
                "remarks_sc": entry.get("rmk_sc"),
                "data_timestamp": entry.get("data_timestamp"),
            })

        stops = []
        for item in sorted(route_stops["data"], key=lambda x: int(x.get("seq", 0))):
            stop_id = item.get("stop")
            seq = int(item.get("seq", 0))
            detail = stop_by_id.get(stop_id)
            stops.append({
                "seq": seq,
                "stop_id": stop_id,
                "stop_name_en": detail.name_en if detail else None,
                "stop_name_tc": detail.name_tc if detail else None,
                "stop_name_sc": detail.name_sc if detail else None,
                "latitude": detail.lat if detail else None,
                "longitude": detail.long if detail else None,
                "etas": etas_by_seq.get(seq, []),
            })

        logger.info(f"Itinerary complete: route {route} {normalized}, {len(stops)} stops")
        return {
            "route": route,
            "bound": normalized,
            "service_type": service_type,
            "stops_count": len(stops),
            "stops": stops,
        }
    except Exception as e:
        logger.error(f"Error in get_route_itinerary: {str(e)}")
        return {"error": str(e), "route": route, "bound": normalized}
