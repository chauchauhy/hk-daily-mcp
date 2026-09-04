# pylint: disable=W0613,W1203,E1136,W0718
"""HKO tide predictions (high/low tide times and heights), no API key needed."""
import csv
import io
import logging
from datetime import date as date_cls
from datetime import datetime

from utils.env_load_util import EnvLoadUtil
from utils.httpx_util import get_global_httpx_util

logger = logging.getLogger(__name__)

STATION_CODES = {
    "CCH", "QUB", "TPK", "WAG", "CLK", "KCT",
    "KLW", "MWC", "SPW", "TAO", "TBT", "TMW",
}

STATION_ALIASES = {
    "cheung chau": "CCH",
    "quarry bay": "QUB",
    "tai po kau": "TPK",
    "taipo": "TPK",
    "waglan": "WAG",
    "waglan island": "WAG",
    "chek lap kok": "CLK",
}


def _resolve_station(station: str) -> str | None:
    code = str(station).strip().upper()
    if code in STATION_CODES:
        return code
    return STATION_ALIASES.get(str(station).strip().lower())


async def get_tide_predictions(station: str = "CCH", date: str | None = None) -> dict:
    """High/low tides for a station on a date (YYYY-MM-DD, default today)."""
    code = _resolve_station(station)
    if code is None:
        return {
            "error": f"Unknown tide station: {station}",
            "valid_stations": sorted(STATION_CODES),
        }

    if date is None:
        target = date_cls.today()
    else:
        try:
            target = datetime.strptime(str(date).strip(), "%Y-%m-%d").date()
        except ValueError:
            return {"error": f"Invalid date: {date}", "details": "date must be YYYY-MM-DD."}

    logger.info(f"Fetching tide predictions for {code} on {target.isoformat()}...")
    try:
        url = EnvLoadUtil.HKO_TIDE_URL.format(station=code, year=target.year)
        response = await get_global_httpx_util().get_all(url)
        if response.status_code != 200:
            logger.error(f"Failed to fetch tides. Status code: {response.status_code}")
            return {"error": "Failed to fetch tide predictions"}
        text = response.text.lstrip("﻿")
        rows = csv.reader(io.StringIO(text))
        next(rows, None)  # header: Month,Date,Time,Height(m),...
        events = []
        for row in rows:
            if len(row) < 4:
                continue
            try:
                if int(row[0]) != target.month or int(row[1]) != target.day:
                    continue
            except ValueError:
                continue
            cells = row[2:]
            for i in range(0, len(cells) - 1, 2):
                time_str, height_str = cells[i].strip(), cells[i + 1].strip()
                if not time_str or not height_str:
                    continue
                try:
                    events.append({"time": time_str, "height_m": float(height_str)})
                except ValueError:
                    continue
    except Exception as e:
        logger.error(f"Error in get_tide_predictions: {str(e)}")
        return {"error": str(e)}

    # Tides strictly alternate high/low; label each by neighbor comparison.
    for i, event in enumerate(events):
        neighbors = []
        if i > 0:
            neighbors.append(events[i - 1]["height_m"])
        if i < len(events) - 1:
            neighbors.append(events[i + 1]["height_m"])
        if neighbors and all(event["height_m"] > n for n in neighbors):
            event["type"] = "high"
        elif neighbors and all(event["height_m"] < n for n in neighbors):
            event["type"] = "low"
        else:
            event["type"] = "unknown"

    return {
        "station": code,
        "date": target.isoformat(),
        "count": len(events),
        "tides": events,
    }
