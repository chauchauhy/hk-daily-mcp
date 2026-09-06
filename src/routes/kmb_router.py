# pylint: disable=W0613,W1203,E1136,W0718
import logging

from fastapi import APIRouter
from utils import kmb_planner_service, kmb_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kmb_router", tags=["kmb_router"])


@router.get("/")
async def get_kmb_router():
    return {"message": "This is the KMB Router endpoint"}

@router.get("/route/{route_id}")
async def get_kmb_router_by_route_id(route_id: str):
    """Return the KMB lanes serving a route number (e.g. 1, 1A, N368)."""
    logger.info(f"Fetching KMB router data for route_id: {route_id}...")
    try:
        return await kmb_service.fetch_kmb_route(route_id)
    except Exception as e:
        return {"error": str(e)}


@router.get("/near_stop/ll/{lat}/{lon}")
async def get_near_stop(lat: str, lon: str):
    logger.info(f"Fetching KMB stop data near lat: {lat}, lon: {lon}...")
    try:
        return await kmb_service.find_nearby_stops(lat, lon)
    except Exception as e:
        logger.error(f"Error in get_near_stop: {str(e)}")
        return {"error": str(e)}

@router.get("/near_stop/address/{address}")
async def get_ll_from_address(address: str):
    logger.info(f"Fetching latitude and longitude for address: {address}...")
    try:
        return await kmb_service.find_stops_by_address(address)
    except Exception as e:
        logger.error(f"Error in get_ll_from_address: {str(e)}")
        return {"error": str(e)}

@router.get("/eta/address/{address}")
async def get_eta_by_address(address: str):
    """Geocode address -> find nearby stops -> return ETAs for all routes."""
    logger.info(f"Starting ETA lookup workflow for address: {address}")
    try:
        return await kmb_service.get_stop_eta_workflow(address)
    except Exception as e:
        logger.error(f"Error in get_eta_by_address workflow: {str(e)}")
        return {"error": str(e), "address": address, "details": "An error occurred during the ETA lookup workflow"}


@router.get("/eta/address/{address}/{route_number}")
async def get_eta_by_address_and_route(address: str, route_number: str):
    """Geocode address -> find nearby stops -> return ETAs filtered by route number."""
    logger.info(f"Starting ETA lookup workflow for address: {address}, route: {route_number}")
    try:
        return await kmb_service.get_stop_eta_workflow(address, route_filter=route_number)
    except Exception as e:
        logger.error(f"Error in get_eta_by_address workflow: {str(e)}")
        return {"error": str(e), "address": address, "details": "An error occurred during the ETA lookup workflow"}


@router.get("/shortest_route/address/{origin_address}/{destination_address}")
async def get_shortest_route(origin_address: str, destination_address: str,
                             radius: float | None = None,
                             max_transfer_walk_km: float = 0.15,
                             transfer_penalty_km: float = 0.6):
    """Plan the shortest KMB journey (walk + bus, transfers allowed) between two addresses."""
    logger.info(f"Planning shortest KMB route between: {origin_address} -> {destination_address}")
    try:
        return await kmb_planner_service.plan_shortest_route(
            origin_address, destination_address, radius=radius,
            max_transfer_walk_km=max_transfer_walk_km,
            transfer_penalty_km=transfer_penalty_km)
    except Exception as e:
        logger.error(f"Error in get_shortest_route: {str(e)}")
        return {"error": str(e), "origin_address": origin_address, "destination_address": destination_address,
                "details": "An error occurred during the shortest-route workflow"}


@router.get("/route_between/address/{origin_address}/{destination_address}")
async def get_route_between_addresses(origin_address: str, destination_address: str,
                                      radius: float | None = None, top_n: int = 5,
                                      include_eta: bool = False):
    """Find direct KMB routes connecting an origin address to a destination address."""
    logger.info(f"Finding KMB routes between: {origin_address} -> {destination_address}")
    try:
        return await kmb_service.find_route_between_addresses(
            origin_address, destination_address, radius=radius, top_n=top_n, include_eta=include_eta)
    except Exception as e:
        logger.error(f"Error in get_route_between_addresses: {str(e)}")
        return {"error": str(e), "origin_address": origin_address, "destination_address": destination_address,
                "details": "An error occurred during the route lookup workflow"}
