# pylint: disable=W0613,W1203,E1136,W0718
"""Shared KMB workflows used by both the FastAPI routers and the MCP tools."""
import logging

from haversine import haversine, Unit

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


BOUND_WORD = {"O": "outbound", "I": "inbound"}


def _distance_km(coord_a: tuple, coord_b: tuple) -> float:
    """Great-circle distance in km between two (lat, lon) tuples."""
    return round(haversine(coord_a, coord_b, unit=Unit.KILOMETERS), 3)


def _route_lane_meta(lanes) -> dict:
    """Index KMB router lanes by (route, bound, service_type) for terminal names."""
    meta = {}
    for lane in lanes:
        meta[(lane.route.upper(), lane.bound, lane.service_type)] = lane
    return meta


async def _load_route_lane_meta() -> dict:
    """Fetch the KMB route list (live with offline fallback) and index it.

    Terminal names are enrichment only: on failure return {} so the route
    suggestions still come back, just without orig/dest terminal labels.
    """
    try:
        data = await kmb_util.KMBRouterUtil.fetch_all_kmb_router()
        return _route_lane_meta(data.data) if data is not None else {}
    except Exception as e:
        logger.error(f"Failed to load route lane meta: {str(e)}")
        return {}


def rank_direct_routes(origin_stops: list, dest_stops: list,
                       origin_ll: tuple, dest_ll: tuple,
                       lane_stops: dict, top_n: int = 5) -> list:
    """Find direct KMB lanes whose stop sequence joins an origin-area stop to a destination-area stop.

    origin_stops/dest_stops: KMB Stop objects within walking range of each address.
    lane_stops: {(route, bound, service_type): [RouteStop...]} ordered by seq.
    Returns a list ranked by (total walking km, stops between, route number).
    """
    origin_dists = {s.stop: _distance_km(origin_ll, (float(s.lat), float(s.long))) for s in origin_stops}
    dest_dists = {s.stop: _distance_km(dest_ll, (float(s.lat), float(s.long))) for s in dest_stops}

    candidates = []
    for (route, bound, service_type), stops in lane_stops.items():
        positions = {entry.stop: i for i, entry in enumerate(stops)}
        if not positions:
            continue
        best = None
        for origin_stop in origin_stops:
            origin_pos = positions.get(origin_stop.stop)
            if origin_pos is None:
                continue
            for dest_stop in dest_stops:
                dest_pos = positions.get(dest_stop.stop)
                if dest_pos is None:
                    continue
                # A lane is a valid direct connection only when the bus reaches
                # the origin-area stop BEFORE the destination-area stop. The
                # bound label ("O"/"I") is about which terminal the lane runs
                # toward, not whether it connects origin -> destination, so the
                # same position rule applies to both bounds.
                if origin_pos >= dest_pos:
                    continue
                walk_km = round(origin_dists[origin_stop.stop] + dest_dists[dest_stop.stop], 3)
                between = abs(dest_pos - origin_pos) - 1
                score = (walk_km, between)
                if best is None or score < best[0]:
                    best = (score, origin_stop, dest_stop, origin_pos, dest_pos)
        if best is None:
            continue
        (walk_km, between), origin_stop, dest_stop, origin_pos, dest_pos = best
        candidates.append({
            "route": route,
            "bound": bound,
            "direction": BOUND_WORD.get(bound, bound),
            "service_type": service_type,
            "boarding_stop": {
                "stop_id": origin_stop.stop,
                "stop_name_en": origin_stop.name_en,
                "stop_name_tc": origin_stop.name_tc,
                "stop_name_sc": origin_stop.name_sc,
                "latitude": origin_stop.lat,
                "longitude": origin_stop.long,
                "distance_km_from_origin": origin_dists[origin_stop.stop],
            },
            "alighting_stop": {
                "stop_id": dest_stop.stop,
                "stop_name_en": dest_stop.name_en,
                "stop_name_tc": dest_stop.name_tc,
                "stop_name_sc": dest_stop.name_sc,
                "latitude": dest_stop.lat,
                "longitude": dest_stop.long,
                "distance_km_from_destination": dest_dists[dest_stop.stop],
            },
            "stops_between": between,
            "walk_km_total": walk_km,
        })

    candidates.sort(key=lambda c: (c["walk_km_total"], c["stops_between"], c["route"]))
    return candidates[:top_n]


async def _attach_etas(route_suggestions: list) -> list:
    """Attach the next live ETAs at each suggested boarding stop for its route."""
    for suggestion in route_suggestions:
        stop_id = suggestion["boarding_stop"]["stop_id"]
        route = suggestion["route"]
        bound = suggestion["bound"]
        try:
            eta_response = await kmb_util.KMBRouterUtil.fetch_kmb_eta_stop_by_stop_id(stop_id)
            etas = []
            if eta_response and eta_response.data:
                for eta in eta_response.data:
                    if eta.route == route and eta.dir == bound:
                        etas.append({
                            "eta": eta.eta,
                            "eta_seq": eta.eta_seq,
                            "destination_en": eta.dest_en,
                            "destination_tc": eta.dest_tc,
                            "destination_sc": eta.dest_sc,
                            "remarks_en": eta.rmk_en,
                            "remarks_tc": eta.rmk_tc,
                            "remarks_sc": eta.rmk_sc,
                        })
            suggestion["next_buses"] = sorted(etas, key=lambda e: e.get("eta") or "")[:3]
        except Exception as eta_error:
            logger.error(f"Failed to fetch ETA for stop {stop_id} route {route}: {str(eta_error)}")
            suggestion["next_buses"] = []
    return route_suggestions


async def find_route_between_addresses(origin_address: str, destination_address: str,
                                       radius: float | None = None, top_n: int = 5,
                                       include_eta: bool = False) -> dict:
    """Find direct KMB routes connecting an origin address to a destination address.

    Workflow: geocode both addresses -> find stops within walking range of each
    -> join with the route-stop index -> rank lanes that travel past both stops.
    """
    origin_ll = await kmb_util.KMBRouterUtil.get_lat_lon_from_address(origin_address)
    if "error" in origin_ll:
        logger.error(f"Geocoding failed for origin address: {origin_address}")
        return {
            "error": "Origin address not found",
            "origin_address": origin_address,
            "details": "Could not geocode the origin address. Please check the address and try again.",
        }
    dest_ll = await kmb_util.KMBRouterUtil.get_lat_lon_from_address(destination_address)
    if "error" in dest_ll:
        logger.error(f"Geocoding failed for destination address: {destination_address}")
        return {
            "error": "Destination address not found",
            "destination_address": destination_address,
            "details": "Could not geocode the destination address. Please check the address and try again.",
        }

    search_radius = radius if radius is not None else float(
        EnvLoadUtil.load_env("KMB_ROUTE_PLAN_RADIUS", "0.005"))
    origin_stops = await kmb_util.KMBRouterUtil.load_near_stop_with_lat_lon(
        str(origin_ll["latitude"]), str(origin_ll["longitude"]), radius=search_radius)
    dest_stops = await kmb_util.KMBRouterUtil.load_near_stop_with_lat_lon(
        str(dest_ll["latitude"]), str(dest_ll["longitude"]), radius=search_radius)

    if not origin_stops or not dest_stops:
        logger.warning(f"No stops found near origin/destination (radius {search_radius})")
        return {
            "origin_address": origin_address,
            "destination_address": destination_address,
            "origin_latitude": origin_ll["latitude"],
            "origin_longitude": origin_ll["longitude"],
            "destination_latitude": dest_ll["latitude"],
            "destination_longitude": dest_ll["longitude"],
            "search_radius_degrees": search_radius,
            "routes_count": 0,
            "routes": [],
            "message": "No bus stops found near one or both addresses. Try a different address or a larger radius.",
        }

    index = await kmb_util.KMBRouterUtil.load_route_stop_index()
    if not index["lane_stops"]:
        logger.error("Route-stop index unavailable")
        return {
            "error": "Route stop index unavailable",
            "details": "The bundled KMB route-stop data could not be loaded. Try again later.",
        }

    suggestions = rank_direct_routes(
        origin_stops, dest_stops,
        (origin_ll["latitude"], origin_ll["longitude"]),
        (dest_ll["latitude"], dest_ll["longitude"]),
        index["lane_stops"], top_n=top_n)

    lane_meta = await _load_route_lane_meta()
    for suggestion in suggestions:
        lane = lane_meta.get((suggestion["route"], suggestion["bound"], suggestion["service_type"]))
        if lane is not None:
            suggestion["orig_en"] = lane.orig_en
            suggestion["orig_tc"] = lane.orig_tc
            suggestion["orig_sc"] = lane.orig_sc
            suggestion["dest_en"] = lane.dest_en
            suggestion["dest_tc"] = lane.dest_tc
            suggestion["dest_sc"] = lane.dest_sc

    if include_eta and suggestions:
        suggestions = await _attach_etas(suggestions)

    logger.info(f"Found {len(suggestions)} direct route(s) between the two addresses")
    return {
        "origin_address": origin_address,
        "destination_address": destination_address,
        "origin_latitude": origin_ll["latitude"],
        "origin_longitude": origin_ll["longitude"],
        "destination_latitude": dest_ll["latitude"],
        "destination_longitude": dest_ll["longitude"],
        "search_radius_degrees": search_radius,
        "routes_count": len(suggestions),
        "routes": suggestions,
        "message": "Direct KMB routes (no transfers) ranked by walking distance. "
                   "Boarding and alighting stops are the nearest to each address.",
    }
