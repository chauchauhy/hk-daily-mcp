# pylint: disable=W0603,E0402,W1203
import logging 
import json 
import ssl
from scipy.spatial import KDTree
import numpy as np
import certifi

from geopy.geocoders import Nominatim

from .env_load_util import EnvLoadUtil
from .httpx_util import get_global_httpx_util



from models.kmb.stop_eta.kmb_stop_eta import KMBStopETAResponse
from models.kmb.stop.stop_response import StopListResponse
from models.kmb.router.route_lane import KMBRouterResponse

logger = logging.getLogger(__name__)

class KMBRouterUtil:

    def __init__(self):
        self._stop_cache = {
            "tree": None,
            "stops": None,
        }

    def _reset_cache(self):
        self._stop_cache["tree"] = None
        self._stop_cache["stops"] = None

    def set_stop_cache(self, stop_list: StopListResponse):
        self._stop_cache["stops"] = stop_list
        coordinates = np.array([[float(stop.lat), float(stop.long)] for stop in stop_list.data])
        self._stop_cache["tree"] = KDTree(coordinates)

    def get_cached_stop_dict(self) -> dict:
        return self._stop_cache

    @staticmethod
    async def fetch_all_kmb_router() -> KMBRouterResponse:
        url = EnvLoadUtil.ALL_KMB_ROUTER_URL
        httpx_util = get_global_httpx_util()
        response = await httpx_util.get_all(url)
        try:
            return KMBRouterResponse.model_validate(response.json())
        except Exception:
            logger.error(f"Failed to parse KMB router data. Status code: {response.status_code}. Loading from file.")
            return await KMBRouterUtil.load_kmb_router_data_from_file()

        
    @staticmethod
    async def load_kmb_router_data_from_file() -> KMBRouterResponse:
        try:
            file_path = EnvLoadUtil.res_path(EnvLoadUtil.load_env("KMB_ROUTE_DATA", "route_data.json"))
            with open(file_path, "r", encoding="utf-8") as f:
                router_data = KMBRouterResponse(**json.load(f))
                logger.info(f"Successfully loaded KMB router data from file. Total routes: {len(router_data.data)}")
                return router_data
        except Exception as e:
            logger.error(f"Failed to load KMB router data from file. Error: {str(e)}")
            return None
        
    @staticmethod
    async def fetch_kmb_eta_stop_by_stop_id(stop_id: str) -> KMBStopETAResponse:
        url = EnvLoadUtil.KMB_ROUTER_ETA_URL
        formatted_url = url.format(stop_id=stop_id)
        logger.info(f"Fetching KMB ETA data for stop_id: {stop_id} using URL: {formatted_url}")
        httpx_util = get_global_httpx_util()
        eta_response: KMBStopETAResponse = None
        response = await httpx_util.get_all(formatted_url)
        eta_response = KMBStopETAResponse(**response.json()) if response.status_code == 200 else None
        return eta_response

    @staticmethod
    async def fetch_kmb_route_stops(route: str, bound: str, service_type: int = 1) -> dict | None:
        """Fetch the ordered stop list of a route bound. bound: inbound|outbound."""
        url = EnvLoadUtil.KMB_ETA_ROUTE_URL
        formatted_url = url.format(route=route, direction=bound, service_type=service_type)
        logger.info(f"Fetching KMB route stops: {formatted_url}")
        httpx_util = get_global_httpx_util()
        response = await httpx_util.get_all(formatted_url)
        if response.status_code == 200:
            return response.json()
        logger.error(f"Failed to fetch KMB route stops. Status code: {response.status_code}")
        return None

    @staticmethod
    async def fetch_kmb_route_eta(route: str, service_type: int = 1) -> dict | None:
        """Fetch live ETAs for every stop of a route (entries keyed by stop seq)."""
        url = EnvLoadUtil.KMB_ROUTE_ETA_URL
        formatted_url = url.format(route=route, service_type=service_type)
        logger.info(f"Fetching KMB route ETAs: {formatted_url}")
        httpx_util = get_global_httpx_util()
        response = await httpx_util.get_all(formatted_url)
        if response.status_code == 200:
            return response.json()
        logger.error(f"Failed to fetch KMB route ETAs. Status code: {response.status_code}")
        return None
    
    @staticmethod
    async def fetch_kmb_stop() -> StopListResponse:
        url = EnvLoadUtil.KMB_STOP_URL
        httpx_util = get_global_httpx_util()
        response = await httpx_util.get_all(url)
        stop_list: StopListResponse = None
        if response.status_code == 200:
            stop_list = StopListResponse(**response.json())
            logger.info(f"Successfully fetched KMB stop data. Total stops: {len(stop_list.data)}")
        else:
            logger.error(f"Failed to fetch KMB stop data. Status code: {response.status_code} loading from file.")
            stop_list = await KMBRouterUtil.load_stop_data_from_file()
        if stop_list is None:
            return StopListResponse(type="", version="", generated_timestamp="", data=[])
        
        util_instance = get_global_kmb_util()
        util_instance.set_stop_cache(stop_list)

        return stop_list
        
    @staticmethod
    async def load_stop_data_from_file() -> StopListResponse:
        try:
            file_path = EnvLoadUtil.res_path(EnvLoadUtil.load_env("KMB_STOP_DATA", "stop_data.json"))
            with open(file_path, "r", encoding="utf-8") as f:
                stop_list = StopListResponse(**json.load(f))
                logger.info(f"Successfully loaded KMB stop data from file. Total stops: {len(stop_list.data)}")
                return stop_list
        except Exception as e:
            logger.error(f"Failed to load KMB stop data from file. Error: {str(e)}")
            return None
    
    @staticmethod
    async def load_near_stop_with_lat_lon(lat: str, lon: str) -> list:
        util_instance = get_global_kmb_util()
        if not util_instance._stop_cache["stops"]:
            logger.info("No stop data in cache, fetching from API...")
            if await util_instance.fetch_kmb_stop() is None:
                logger.error("Failed to fetch stop data, cannot find nearby stops.")
                return []
            
        cached_stop_list: StopListResponse = util_instance.get_cached_stop_dict().get("stops")
        
        query_point = [float(lat), float(lon)]
        tree: KDTree = util_instance.get_cached_stop_dict().get("tree")
        distance = float(EnvLoadUtil.load_env("KMB_NEAR_STOP_DISTANCE", 0.003))
        indices = tree.query_ball_point(query_point, distance, p=np.inf)
        
        nearby_stops = [cached_stop_list.data[i] for i in indices]
        
        logger.info(f"Found {len(nearby_stops)} stops near lat: {lat}, lon: {lon}")
        return nearby_stops
    
    @staticmethod
    def _geocode_address(address: str) -> Nominatim | None:
        try:
            # certifi CA bundle: the system Python CA store may miss issuers
            # that certifi carries (e.g. Nominatim's chain on some machines).
            geolocator = Nominatim(
                user_agent="daily_data_assistant",
                timeout=10,
                ssl_context=ssl.create_default_context(cafile=certifi.where()),
            )
            logger.info(f"Geocoding address: {address}")
            location = geolocator.geocode(address, timeout=10)
            logger.info(f"Geocoding result: lat={location.latitude if location else 'N/A'}, lon={location.longitude if location else 'N/A'}")
            return location
        except Exception as e:
            logger.error(f"Geocoding failed for '{address}': {str(e)}")
            return None

    @staticmethod
    async def load_near_stop_with_address(address: str) -> list:
        location = KMBRouterUtil._geocode_address(address)
        if location is None:
            logger.error(f"Failed to geocode address: {address}. No location found.")
            return []
        
        return await KMBRouterUtil.load_near_stop_with_lat_lon(str(location.latitude), str(location.longitude))

    @staticmethod
    async def get_lat_lon_from_address(address: str) -> dict:
        location = KMBRouterUtil._geocode_address(address)
        return {"latitude": location.latitude, "longitude": location.longitude} if location else {"error": "Address not found"}

_GOLBAL_KMB_UTIL_INSTANCE = None
def get_global_kmb_util() -> KMBRouterUtil:
    global _GOLBAL_KMB_UTIL_INSTANCE
    if _GOLBAL_KMB_UTIL_INSTANCE is None:
        _GOLBAL_KMB_UTIL_INSTANCE = KMBRouterUtil()
    return _GOLBAL_KMB_UTIL_INSTANCE
