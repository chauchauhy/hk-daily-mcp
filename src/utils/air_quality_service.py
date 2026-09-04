# pylint: disable=W0613,W1203,E1136,W0718
"""Hong Kong Air Quality Health Index (HKEPD RSS feed), no API key needed."""
import logging
import re
import xml.etree.ElementTree as ET

from utils.env_load_util import EnvLoadUtil
from utils.httpx_util import get_global_httpx_util

logger = logging.getLogger(__name__)

# e.g. "Mong Kok - Roadside Stations: 6 Moderate - Fri, 04 Sep 2026 20:30"
_ITEM_RE = re.compile(
    r"^(?P<station>.+?)\s+-\s+(?P<station_type>.+?):\s+"
    r"(?P<aqhi>\d+\+?)\s+(?P<band>.+?)\s+-\s+(?P<observed>.+)$"
)


def _parse_item(title: str, description: str) -> dict | None:
    match = _ITEM_RE.match((description or "").strip())
    if not match:
        return None
    aqhi_raw = match.group("aqhi")
    return {
        "station": (title or match.group("station")).strip(),
        "station_type": match.group("station_type").strip(),
        "aqhi": int(aqhi_raw.rstrip("+")),
        "aqhi_raw": aqhi_raw,
        "band": match.group("band").strip(),
        "observed_at": match.group("observed").strip(),
    }


async def get_air_quality(station: str = "all") -> dict:
    logger.info(f"Fetching AQHI for station: {station}...")
    try:
        response = await get_global_httpx_util().get_all(EnvLoadUtil.AQHI_RSS_URL)
        if response.status_code != 200:
            logger.error(f"Failed to fetch AQHI. Status code: {response.status_code}")
            return {"error": "Failed to fetch air quality data"}
        root = ET.fromstring(response.content)
        readings = []
        for item in root.findall(".//item"):
            parsed = _parse_item(item.findtext("title"), item.findtext("description"))
            if parsed:
                readings.append(parsed)
    except Exception as e:
        logger.error(f"Error in get_air_quality: {str(e)}")
        return {"error": str(e)}

    if not readings:
        return {"error": "No air quality readings available"}

    query = str(station).strip()
    if query.lower() == "all":
        return {"station": "all", "count": len(readings), "stations": readings}

    exact = [r for r in readings if r["station"].lower() == query.lower()]
    if len(exact) == 1:
        return {"station": exact[0]["station"], "count": 1, "stations": exact}
    partial = [r for r in readings if query.lower() in r["station"].lower()]
    if len(partial) == 1:
        return {"station": partial[0]["station"], "count": 1, "stations": partial}
    if len(partial) > 1:
        return {
            "error": f"Ambiguous station: {station}",
            "matches": [r["station"] for r in partial],
        }
    return {
        "error": f"Unknown station: {station}",
        "valid_stations": [r["station"] for r in readings],
    }
