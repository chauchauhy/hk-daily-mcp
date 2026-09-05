# pylint: disable=W0613,W1203,E1136,W0718
"""MTR next-train info (rt.data.gov.hk feed), no API key needed."""
import csv
import logging
from utils.env_load_util import EnvLoadUtil
from utils.httpx_util import get_global_httpx_util

logger = logging.getLogger(__name__)

LINE_NAMES = {
    "TWL": ["tsuen wan", "tsuen wan line"],
    "ISL": ["island", "island line", "hong kong island line"],
    "KTL": ["kwun tong", "kwun tong line"],
    "TKO": ["tseung kwan o", "tseung kwan o line"],
    "EAL": ["east rail", "east rail line"],
    "TML": ["tuen ma", "tuen ma line"],
    "TCL": ["tung chung", "tung chung line"],
    "AEL": ["airport express"],
    "SIL": ["south island", "south island line"],
    "DRL": ["disneyland resort", "disneyland", "disneyland resort line"],
}

_LINES_CACHE = None


def _load_lines_stations() -> list:
    """Bundled MTR line/station table (res/mtr_lines_and_stations.csv)."""
    global _LINES_CACHE
    if _LINES_CACHE is None:
        _LINES_CACHE = []
        file_path = EnvLoadUtil.res_path("mtr_lines_and_stations.csv")
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    _LINES_CACHE.append({
                        "line": (row.get("Line Code") or "").strip().upper(),
                        "station_code": (row.get("Station Code") or "").strip().upper(),
                        "name_en": (row.get("English Name") or "").strip(),
                        "name_tc": (row.get("Chinese Name") or "").strip(),
                    })
            logger.info(f"Loaded {len(_LINES_CACHE)} bundled MTR line/station rows")
        except Exception as e:
            logger.warning(f"Bundled MTR table unavailable ({file_path}): {str(e)}")
    return _LINES_CACHE


def _resolve_line(raw: str) -> str | None:
    text = str(raw).strip()
    if text.upper() in LINE_NAMES:
        return text.upper()
    lowered = text.lower().removesuffix(" line").strip()
    for code, names in LINE_NAMES.items():
        if lowered in names:
            return code
    return None


def _resolve_station(raw: str, line_code: str) -> dict | None:
    rows = [r for r in _load_lines_stations() if r["line"] == line_code]
    text = str(raw).strip()
    if not rows:
        return None
    for row in rows:
        if row["station_code"] == text.upper():
            return row
    for row in rows:
        if row["name_en"].lower() == text.lower() or row["name_tc"] == text:
            return row
    partial = [r for r in rows
               if text.lower() in r["name_en"].lower() or text in r["name_tc"]]
    if len(partial) == 1:
        return partial[0]
    return None


async def get_mtr_next_train(line: str, station: str) -> dict:
    line_code = _resolve_line(line)
    if line_code is None:
        return {
            "error": f"Unknown MTR line: {line}",
            "valid_lines": sorted(LINE_NAMES),
        }
    resolved = _resolve_station(station, line_code)
    if resolved is None:
        return {
            "error": f"Unknown station '{station}' on line {line_code}",
            "details": "Pass a 3-letter station code or the Chinese/English station name.",
        }
    sta_code = resolved["station_code"]
    logger.info(f"Fetching MTR next trains for {line_code}/{sta_code}...")

    try:
        url = EnvLoadUtil.MTR_SCHEDULE_URL.format(line=line_code, sta=sta_code)
        response = await get_global_httpx_util().get_all(url)
        if response.status_code != 200:
            logger.error(f"Failed to fetch MTR schedule. Status code: {response.status_code}")
            return {"error": "Failed to fetch MTR schedule"}
        data = response.json()
    except Exception as e:
        logger.error(f"Error in get_mtr_next_train: {str(e)}")
        return {"error": str(e)}

    section = (data.get("data") or {}).get(f"{line_code}-{sta_code}")
    if not section:
        return {
            "error": f"No schedule data for {line_code}/{sta_code}",
            "line": line_code,
            "station": sta_code,
        }

    def _clean(trains: list) -> list:
        cleaned = []
        for train in trains or []:
            cleaned.append({
                "seq": train.get("seq"),
                "dest": train.get("dest"),
                "plat": train.get("plat"),
                "time": train.get("time"),
                "ttnt": train.get("ttnt"),
                "valid": train.get("valid"),
            })
        return cleaned

    return {
        "line": line_code,
        "station": sta_code,
        "station_name_en": resolved["name_en"],
        "station_name_tc": resolved["name_tc"],
        "curr_time": section.get("curr_time"),
        "sys_time": section.get("sys_time"),
        "is_delay": data.get("isdelay"),
        "up": _clean(section.get("UP")),
        "down": _clean(section.get("DOWN")),
    }
