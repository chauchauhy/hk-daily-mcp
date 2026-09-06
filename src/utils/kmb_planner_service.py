# pylint: disable=W0613,W1203,E1136,W0718
"""Deterministic shortest-path planner over the KMB network (no AI involved).

Builds a directed transit graph from the bundled data:
- ride edges: consecutive stops of every KMB lane (direction of travel only)
- walk edges: pairs of stops within a transfer walking distance
then runs Dijkstra from the stops nearest to the origin address to the stops
nearest to the destination address, with a per-transfer penalty so the result
prefers fewer bus changes. Returns the shortest journey as a list of legs
(walk + bus), exactly as the "shortest road" a person would take.
"""
import heapq
import logging

import numpy as np
from haversine import haversine, Unit
from scipy.spatial import KDTree

from utils import kmb_util
from utils.env_load_util import EnvLoadUtil

logger = logging.getLogger(__name__)

# Default transfer penalty applied when alighting a bus (in "walk km" terms),
# so a journey with one fewer transfer can win even if it rides slightly longer.
DEFAULT_TRANSFER_PENALTY_KM = 0.6
# Max distance two stops may be apart to be connected by a walking transfer edge.
DEFAULT_MAX_TRANSFER_WALK_KM = 0.15
# Walking is slower than riding (~4-5 km/h vs ~25 km/h), so 1 km on foot is
# charged as several km of "riding distance". Without this, Dijkstra happily
# walks long stop-to-stop chains instead of staying on the bus.
DEFAULT_WALK_COST_FACTOR = 3.0


def _distance_km(coord_a: tuple, coord_b: tuple) -> float:
    return round(haversine(coord_a, coord_b, unit=Unit.KILOMETERS), 3)


def _stop_meta(stops) -> dict:
    """index stop_id -> small dict (names + coords) for output legs."""
    meta = {}
    for stop in stops:
        meta[stop.stop] = {
            "stop_id": stop.stop,
            "stop_name_en": stop.name_en,
            "stop_name_tc": stop.name_tc,
            "stop_name_sc": stop.name_sc,
            "latitude": stop.lat,
            "longitude": stop.long,
        }
    return meta


def build_walk_edges(stops, max_walk_km: float = DEFAULT_MAX_TRANSFER_WALK_KM) -> dict:
    """Connect stops that are within max_walk_km of each other (transfer-by-foot edges).

    Returns {stop_id: [(other_stop_id, walk_km), ...]}. Undirected-ish: each
    pair is listed from both ends.
    """
    coords = np.array([[float(s.lat), float(s.long)] for s in stops])
    ids = [s.stop for s in stops]
    if not len(coords):
        return {}
    tree = KDTree(coords)
    radius_deg = max_walk_km / 111.0
    edges: dict[str, list] = {}
    for i, stop in enumerate(stops):
        neighbors = tree.query_ball_point(coords[i], radius_deg, p=np.inf)
        for j in neighbors:
            if j == i:
                continue
            walk_km = _distance_km(tuple(coords[i]), tuple(coords[j]))
            if walk_km <= max_walk_km:
                edges.setdefault(stop.stop, []).append((ids[j], walk_km))
    return edges


def build_ride_structures(lane_stops: dict, stop_coords: dict) -> tuple[dict, dict]:
    """Index the directed ride edges of every lane.

    Returns (next_on_lane, lanes_boarding):
    - next_on_lane: {(stop_id, lane_key): (next_stop_id, ride_km)}
    - lanes_boarding: {stop_id: [lane_key, ...]} for stops that have a next stop
    """
    next_on_lane: dict[tuple, tuple] = {}
    lanes_boarding: dict[str, list] = {}
    for lane_key, entries in lane_stops.items():
        for i in range(len(entries) - 1):
            a, b = entries[i], entries[i + 1]
            if a.stop not in stop_coords or b.stop not in stop_coords:
                continue
            ride_km = _distance_km(stop_coords[a.stop], stop_coords[b.stop])
            next_on_lane[(a.stop, lane_key)] = (b.stop, ride_km)
            lanes_boarding.setdefault(a.stop, []).append(lane_key)
    return next_on_lane, lanes_boarding


def dijkstra_plan(origin_costs: dict, dest_stop_ids: set,
                  next_on_lane: dict, lanes_boarding: dict, walk_edges: dict,
                  transfer_penalty_km: float = DEFAULT_TRANSFER_PENALTY_KM,
                  walk_cost_factor: float = DEFAULT_WALK_COST_FACTOR):
    """Shortest bus journey from origin stops to a destination stop.

    State = (stop_id, lane_key | None); lane None means "not on a bus"
    (either walked here or just alighted). Returns (best_state, prev) where
    prev maps state -> (previous_state, edge_kind, detail) and edge kinds are
    'start' | 'walk' | 'board' | 'ride' | 'alight'.
    """
    inf = float("inf")
    dist = {}
    prev = {}
    heap = []
    tie = 0
    for stop_id, cost in origin_costs.items():
        state = (stop_id, None)
        dist[state] = cost
        prev[state] = (None, "start", None)
        heapq.heappush(heap, (cost, stop_id, tie, None))  # tie before lane: lanes may be tuples/None
        tie += 1

    best = None
    while heap:
        d, stop_id, _, lane = heapq.heappop(heap)
        state = (stop_id, lane)
        if d > dist.get(state, inf):
            continue
        if lane is None and stop_id in dest_stop_ids:
            best = state
            break
        if lane is None:
            # walking transfer edges (weighted by walk_cost_factor: slow)
            for other_id, walk_km in walk_edges.get(stop_id, ()):
                next_state = (other_id, None)
                nd = d + walk_km * walk_cost_factor
                if nd < dist.get(next_state, inf):
                    dist[next_state] = nd
                    prev[next_state] = (state, "walk", (stop_id, other_id))
                    heapq.heappush(heap, (nd, other_id, tie, None))
                    tie += 1
            # boarding (free): hop on any lane whose next stop exists
            for lane_key in lanes_boarding.get(stop_id, ()):
                next_state = (stop_id, lane_key)
                if d < dist.get(next_state, inf):
                    dist[next_state] = d
                    prev[next_state] = (state, "board", lane_key)
                    heapq.heappush(heap, (d, stop_id, tie, lane_key))
                    tie += 1
        else:
            # ride to the next stop of this lane
            nxt = next_on_lane.get((stop_id, lane))
            if nxt is not None:
                next_stop_id, ride_km = nxt
                next_state = (next_stop_id, lane)
                nd = d + ride_km
                if nd < dist.get(next_state, inf):
                    dist[next_state] = nd
                    prev[next_state] = (state, "ride", (next_stop_id, ride_km))
                    heapq.heappush(heap, (nd, next_stop_id, tie, lane))
                    tie += 1
            # alight (pays the transfer penalty)
            next_state = (stop_id, None)
            nd = d + transfer_penalty_km
            if nd < dist.get(next_state, inf):
                dist[next_state] = nd
                prev[next_state] = (state, "alight", lane)
                heapq.heappush(heap, (nd, stop_id, tie, None))
                tie += 1
    return best, prev


def _chain_from_prev(best_state, prev) -> list:
    chain = []
    state = best_state
    while state is not None:
        p, kind, extra = prev[state]
        chain.append((state, kind, extra))
        state = p
    chain.reverse()
    return chain


def build_legs(chain, origin_costs, dest_ll, stop_meta, stop_coords, lane_meta,
               origin_address, destination_address) -> list[dict]:
    """Fold the raw state chain into user-facing legs (walk + bus)."""
    legs = []
    bus = None

    def close_bus():
        nonlocal bus
        board_stop = bus["board"]
        alight_stop = bus["alight"]
        route, bound, service_type = bus["lane"]
        lane = lane_meta.get(bus["lane"])
        bus_leg = {
            "type": "bus",
            "route": route,
            "bound": bound,
            "direction": "outbound" if bound == "O" else "inbound",
            "service_type": service_type,
            "board_stop": stop_meta.get(board_stop),
            "alight_stop": stop_meta.get(alight_stop),
            "stops": len(bus["rides"]),
            "km": round(bus["km"], 3),
        }
        if lane is not None:
            bus_leg["orig_en"] = lane.orig_en
            bus_leg["orig_tc"] = lane.orig_tc
            bus_leg["orig_sc"] = lane.orig_sc
            bus_leg["dest_en"] = lane.dest_en
            bus_leg["dest_tc"] = lane.dest_tc
            bus_leg["dest_sc"] = lane.dest_sc
        legs.append(bus_leg)
        bus = None

    for state, kind, extra in chain:
        stop_id, lane = state
        if kind == "start":
            legs.append({
                "type": "walk",
                "from": "origin_address",
                "from_name": origin_address,
                "to_stop": stop_meta.get(stop_id),
                "km": round(origin_costs[stop_id], 3),
            })
        elif kind == "board":
            bus = {"lane": extra, "board": stop_id, "alight": None, "rides": [], "km": 0.0}
        elif kind == "ride":
            next_stop_id, ride_km = extra
            bus["rides"].append(next_stop_id)
            bus["km"] += ride_km
            bus["alight"] = next_stop_id
        elif kind == "alight":
            bus["alight"] = stop_id
            close_bus()
        elif kind == "walk":
            a, b = extra
            legs.append({
                "type": "walk",
                "from_stop": stop_meta.get(a),
                "to_stop": stop_meta.get(b),
                "km": _distance_km(stop_coords[a], stop_coords[b]),
            })

    # closing walk leg from the last stop in the chain to the destination address
    last_stop_id = chain[-1][0][0]
    legs.append({
        "type": "walk",
        "from_stop": stop_meta.get(last_stop_id),
        "to": "destination_address",
        "to_name": destination_address,
        "km": _distance_km(stop_coords[last_stop_id], dest_ll),
    })
    return legs


async def plan_shortest_route(origin_address: str, destination_address: str,
                              radius: float | None = None,
                              max_transfer_walk_km: float = DEFAULT_MAX_TRANSFER_WALK_KM,
                              transfer_penalty_km: float = DEFAULT_TRANSFER_PENALTY_KM,
                              walk_cost_factor: float = DEFAULT_WALK_COST_FACTOR) -> dict:
    """Shortest KMB journey (walk + bus, transfers allowed) between two addresses.

    Fully deterministic: geocodes both addresses, builds the transit graph from
    the bundled route-stop data, and runs Dijkstra. No AI or routing API used.
    """
    origin_ll = await kmb_util.KMBRouterUtil.get_lat_lon_from_address(origin_address)
    if "error" in origin_ll:
        return {"error": "Origin address not found", "origin_address": origin_address,
                "details": "Could not geocode the origin address. Please check the address and try again."}
    dest_ll = await kmb_util.KMBRouterUtil.get_lat_lon_from_address(destination_address)
    if "error" in dest_ll:
        return {"error": "Destination address not found", "destination_address": destination_address,
                "details": "Could not geocode the destination address. Please check the address and try again."}

    search_radius = radius if radius is not None else float(
        EnvLoadUtil.load_env("KMB_ROUTE_PLAN_RADIUS", "0.005"))
    origin_stops = await kmb_util.KMBRouterUtil.load_near_stop_with_lat_lon(
        str(origin_ll["latitude"]), str(origin_ll["longitude"]), radius=search_radius)
    dest_stops = await kmb_util.KMBRouterUtil.load_near_stop_with_lat_lon(
        str(dest_ll["latitude"]), str(dest_ll["longitude"]), radius=search_radius)
    if not origin_stops or not dest_stops:
        return {
            "origin_address": origin_address, "destination_address": destination_address,
            "origin_latitude": origin_ll["latitude"], "origin_longitude": origin_ll["longitude"],
            "destination_latitude": dest_ll["latitude"], "destination_longitude": dest_ll["longitude"],
            "search_radius_degrees": search_radius,
            "legs": [], "total_km": 0.0, "transfers": 0,
            "message": "No bus stops found near one or both addresses. Try a different address or a larger radius.",
        }

    stop_list = await kmb_util.KMBRouterUtil.fetch_kmb_stop()
    if stop_list is None or not stop_list.data:
        return {"error": "KMB stop data unavailable", "details": "Cannot plan a route without stop data."}
    stops = stop_list.data
    stop_coords = {s.stop: (float(s.lat), float(s.long)) for s in stops}
    stop_meta_map = _stop_meta(stops)

    index = await kmb_util.KMBRouterUtil.load_route_stop_index()
    lane_stops = index["lane_stops"]  # may be empty -> walk-only planning

    next_on_lane, lanes_boarding = build_ride_structures(lane_stops, stop_coords)
    walk_edges = build_walk_edges(stops, max_transfer_walk_km)

    origin_costs_raw = {s.stop: _distance_km(
        (origin_ll["latitude"], origin_ll["longitude"]), (float(s.lat), float(s.long))) for s in origin_stops}
    origin_costs = {stop_id: cost * walk_cost_factor for stop_id, cost in origin_costs_raw.items()}
    dest_stop_ids = {s.stop for s in dest_stops}

    best_state, prev = dijkstra_plan(origin_costs, dest_stop_ids, next_on_lane,
                                     lanes_boarding, walk_edges, transfer_penalty_km,
                                     walk_cost_factor=walk_cost_factor)
    if best_state is None:
        return {
            "origin_address": origin_address, "destination_address": destination_address,
            "search_radius_degrees": search_radius,
            "legs": [], "total_km": 0.0, "transfers": 0,
            "message": "No KMB journey found between these two addresses (could not reach the destination area).",
        }

    lane_meta = {}
    try:
        data = await kmb_util.KMBRouterUtil.fetch_all_kmb_router()
        if data is not None:
            for lane in data.data:
                lane_meta[(lane.route.upper(), lane.bound, lane.service_type)] = lane
    except Exception as e:  # terminal names are enrichment only
        logger.error(f"Failed to load route lane meta for planner: {str(e)}")

    chain = _chain_from_prev(best_state, prev)
    legs = build_legs(chain, origin_costs_raw,
                      (dest_ll["latitude"], dest_ll["longitude"]),
                      stop_meta_map, stop_coords, lane_meta,
                      origin_address, destination_address)

    bus_legs = [leg for leg in legs if leg["type"] == "bus"]
    total_km = round(sum(leg["km"] for leg in legs), 3)
    bus_km = round(sum(leg["km"] for leg in bus_legs), 3)
    walk_km = round(total_km - bus_km, 3)
    transfers = max(0, len(bus_legs) - 1)

    logger.info(f"Planned shortest route: {len(legs)} legs, {bus_km} km bus, {walk_km} km walk, {transfers} transfer(s)")
    return {
        "origin_address": origin_address,
        "destination_address": destination_address,
        "origin_latitude": origin_ll["latitude"], "origin_longitude": origin_ll["longitude"],
        "destination_latitude": dest_ll["latitude"], "destination_longitude": dest_ll["longitude"],
        "search_radius_degrees": search_radius,
        "total_km": total_km,
        "bus_km": bus_km,
        "walk_km": walk_km,
        "transfers": transfers,
        "legs": legs,
        "message": "Deterministic shortest journey (Dijkstra over the KMB network, no AI). "
                   "Bus legs are directed by actual route order; transfers allow changes; "
                   "walking is time-weighted so bus rides are preferred over long walks.",
    }
