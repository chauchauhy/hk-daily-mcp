# pylint: disable=W0613,W1203,E1136,W0718
import logging

from fastapi import APIRouter
from utils import kmb_service

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
