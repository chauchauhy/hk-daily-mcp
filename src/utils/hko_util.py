# pylint: disable=W0603,E0402,W1203
import asyncio
import logging 
from haversine import haversine, Unit


from .env_load_util import EnvLoadUtil
from .httpx_util import get_global_httpx_util
from models.hko.data_type_enum import DataTypeEnum
from models.hko.flw.hko_flw_response import HkoFLWResponse
from models.hko.rhrread.hko_rhrread_response import HkORHRREADResponse
from geopy.geocoders import Nominatim

logger = logging.getLogger(__name__)


class HKORouterUtil:
    def __init__(self):
        self.geolocator = Nominatim(user_agent="bus_tracker_hko")
        self.place_coordinates_cache = {}

    @staticmethod
    async def fetch_hko_flw_data(lang: str = "tc") -> HkoFLWResponse:
        url = EnvLoadUtil.HKO_WEATHER_URL
        formatted_url = url.format(data_type=DataTypeEnum.FLW.value, lang=lang)
        httpx_util = get_global_httpx_util()
        response = await httpx_util.get_all(formatted_url)
        if response.status_code == 200:
            return HkoFLWResponse.model_validate(response.json())
        else:
            logger.error(f"Failed to fetch HKO FLW data. Status code: {response.status_code}")
            return None

    @staticmethod
    async def fetch_rhrread_data(lang: str = "tc") -> HkORHRREADResponse:
        url = EnvLoadUtil.HKO_WEATHER_URL
        formatted_url = url.format(data_type=DataTypeEnum.RHRREAD.value, lang=lang)
        httpx_util = get_global_httpx_util()
        response = await httpx_util.get_all(formatted_url)
        if response.status_code == 200:
            return HkORHRREADResponse.model_validate(response.json())
        else:
            logger.error(f"Failed to fetch HKO RHRREAD data. Status code: {response.status_code}")
            return None

    @staticmethod
    async def fetch_hk_weather_data(data_type: DataTypeEnum = DataTypeEnum.FLW, lang: str = "tc") -> dict:
        url = EnvLoadUtil.HKO_WEATHER_URL
        formatted_url = url.format(data_type=data_type.value, lang=lang)
        httpx_util = get_global_httpx_util()
        response = await httpx_util.get_all(formatted_url)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Failed to fetch HKO weather data for data_type {data_type}. Status code: {response.status_code}")
            return ""

    def _geocode_place(self, place_name: str, region: str = "Hong Kong") -> tuple:
        """
        Geocode a place name to get its latitude and longitude.
        Returns (lat, lon) tuple or None if geocoding fails.
        """
        # Check cache first
        cache_key = f"{place_name}, {region}"
        if cache_key in self.place_coordinates_cache:
            return self.place_coordinates_cache[cache_key]
        
        try:
            # Geocode with region context for better accuracy
            location = self.geolocator.geocode(f"{place_name}, {region}", timeout=10)
            if location:
                coords = (location.latitude, location.longitude)
                self.place_coordinates_cache[cache_key] = coords
                logger.info(f"Geocoded '{place_name}': {coords}")
                return coords
            else:
                logger.warning(f"Could not geocode place: {place_name}")
                return None
        except Exception as e:
            logger.error(f"Geocoding error for '{place_name}': {str(e)}")
            return None

    async def find_nearby_weather_stations(self, address: str, lang: str = "tc", top_n: int = 5, user_coords=None) -> dict:
        """
        Find the nearest weather stations to a given address.

        Args:
            address: User input address
            lang: Language for API request (default: "tc")
            top_n: Number of nearest stations to return (default: 5)
            user_coords: Optional pre-computed (lat, lon) tuple for the address.
                When provided, the address is not geocoded again.

        Returns:
            Dictionary containing the nearby weather stations and their data
        """
        # Step 1: Fetch RHRREAD data
        logger.info(f"Fetching RHRREAD data for language: {lang}")
        rhrread_data = await self.fetch_rhrread_data(lang=lang)
        
        if not rhrread_data:
            logger.error("Failed to fetch RHRREAD data")
            return {"error": "Failed to fetch weather data"}
        
        # Step 2: Extract all temperature station locations and geocode them
        logger.info("Extracting and geocoding temperature station locations...")
        stations_with_coords = []
        
        for temp_data in rhrread_data.temperature.data:
            cache_key = f"{temp_data.place}, Hong Kong"
            if cache_key not in self.place_coordinates_cache:
                await asyncio.sleep(1.1)
            coords = self._geocode_place(temp_data.place)
            if coords:
                stations_with_coords.append({
                    "place": temp_data.place,
                    "value": temp_data.value,
                    "unit": temp_data.unit,
                    "lat": coords[0],
                    "lon": coords[1]
                })
        
        if not stations_with_coords:
            logger.error("No stations could be geocoded")
            return {"error": "Could not geocode weather stations"}
        
        logger.info(f"Successfully geocoded {len(stations_with_coords)} stations")
        
        if user_coords:
            logger.info(f"Using pre-computed coordinates for '{address}': {user_coords}")
        else:
            logger.info(f"Geocoding user address: {address}")
            user_coords = self._geocode_place(address, region="Hong Kong")
            if not user_coords:
                logger.error(f"Could not geocode user address: {address}")
                return {"error": f"Could not geocode address: {address}"}
            logger.info(f"User address geocoded to: {user_coords}")
        # Step 4: Haversine
        logger.info("Calculating distances to all weather stations...")
        for station in stations_with_coords:
            station_coords = (station["lat"], station["lon"])
            distance = haversine(user_coords, station_coords, unit=Unit.METERS)
            station["distance_km"] = round(distance, 2)
        
        # Step 5: Sort by distance and get top N nearest stations
        stations_with_coords.sort(key=lambda x: x["distance_km"])
        nearby_stations = stations_with_coords[:top_n]
        
        logger.info(f"Found {len(nearby_stations)} nearby stations")
        
        return {
            "user_address": address,
            "user_coordinates": {
                "lat": user_coords[0],
                "lon": user_coords[1]
            },
            "record_time": rhrread_data.temperature.recordTime,
            "nearby_stations": nearby_stations
        }
        
_GLOBAL_HKO_ROUTER_UTIL_INSTANCE = None
def get_global_hko_router_util() -> HKORouterUtil:
    global _GLOBAL_HKO_ROUTER_UTIL_INSTANCE
    if _GLOBAL_HKO_ROUTER_UTIL_INSTANCE is None:
        _GLOBAL_HKO_ROUTER_UTIL_INSTANCE = HKORouterUtil()
    return _GLOBAL_HKO_ROUTER_UTIL_INSTANCE