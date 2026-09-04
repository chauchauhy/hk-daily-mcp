# pylint: disable=W0613,W1203,E1136,W0718
"""Hong Kong public holidays (1823 government feed), no API key needed."""
import json
import logging

from utils.env_load_util import EnvLoadUtil
from utils.httpx_util import get_global_httpx_util

logger = logging.getLogger(__name__)

LANG_PATHS = {"en": "en", "tc": "tc", "sc": "sc"}


async def get_public_holidays(year: int, lang: str = "en") -> dict:
    path = LANG_PATHS.get(str(lang).lower())
    if path is None:
        return {
            "error": f"Unsupported language: {lang}",
            "details": f"lang must be one of {sorted(LANG_PATHS)}.",
        }
    try:
        year_int = int(year)
    except (TypeError, ValueError):
        return {"error": f"Invalid year: {year}", "details": "year must be a number, e.g. 2026."}

    logger.info(f"Fetching Hong Kong public holidays for {year_int} ({path})...")
    try:
        url = EnvLoadUtil.HOLIDAYS_URL.format(lang=path)
        response = await get_global_httpx_util().get_all(url)
        if response.status_code != 200:
            logger.error(f"Failed to fetch holidays. Status code: {response.status_code}")
            return {"error": "Failed to fetch public holidays"}
        # The feed starts with a UTF-8 BOM, which json.loads rejects.
        data = json.loads(response.content.decode("utf-8-sig"))
        events = data["vcalendar"][0]["vevent"]
    except Exception as e:
        logger.error(f"Error in get_public_holidays: {str(e)}")
        return {"error": str(e)}

    holidays = []
    available_years = set()
    for event in events:
        raw = event["dtstart"][0]  # YYYYMMDD
        available_years.add(raw[:4])
        if int(raw[:4]) == year_int:
            holidays.append({
                "date": f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}",
                "name": event.get("summary", ""),
            })
    holidays.sort(key=lambda h: h["date"])
    return {
        "year": year_int,
        "lang": path,
        "count": len(holidays),
        "available_years": sorted(available_years),
        "holidays": holidays,
    }
