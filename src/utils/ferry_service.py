# pylint: disable=W0613,W1203,E1136,W0718
"""Hong Kong ferry schedules: HKKF + Sun Ferry live ETAs, Star Ferry timetables."""
import csv
import io
import logging

from utils.env_load_util import EnvLoadUtil
from utils.httpx_util import get_global_httpx_util

logger = logging.getLogger(__name__)

OPERATOR_ALIASES = {
    "hkkf": "hkkf",
    "hong kong and kowloon ferry": "hkkf",
    "sunferry": "sunferry",
    "sun ferry": "sunferry",
    "starferry": "starferry",
    "star ferry": "starferry",
}

HKKF_DIRECTIONS = ("inbound", "outbound")

# From the Sun Ferry ETA API spec (route codes are directional).
SUNFERRY_ROUTES = {
    "CECC": "Central - Cheung Chau",
    "CCCE": "Cheung Chau - Central",
    "CEMW": "Central - Mui Wo",
    "MWCE": "Mui Wo - Central",
    "NPHH": "North Point - Hung Hom",
    "HHNP": "Hung Hom - North Point",
    "NPKC": "North Point - Kowloon City",
    "KCNP": "Kowloon City - North Point",
    "IIPECMUW": "Peng Chau - Mui Wo",
    "IIMUWPEC": "Mui Wo - Peng Chau",
    "IIMUWCMW": "Mui Wo - Chi Ma Wan",
    "IICMWMUW": "Chi Ma Wan - Mui Wo",
    "IICMWCHC": "Chi Ma Wan - Cheung Chau",
    "IICHCCMW": "Cheung Chau - Chi Ma Wan",
    "IICHCMUW": "Cheung Chau - Mui Wo",
    "IIMUWCHC": "Mui Wo - Cheung Chau",
}

STARFERRY_TIMETABLES = {
    "central": "https://www.starferry.com.hk/sites/default/files/upload/open_data/csv/ferry_sf_central_tsimshatsui_timetable_eng.csv",
    "wanchai": "https://www.starferry.com.hk/sites/default/files/upload/open_data/csv/ferry_sf_wanchai_tsimshatsui_timetable_eng.csv",
}


def _resolve_sunferry_route(raw: str) -> list:
    text = str(raw).strip().upper()
    if text in SUNFERRY_ROUTES:
        return [text]
    pair = str(raw).strip().lower().replace(" to ", "-").replace("->", "-").replace(" ", "")
    matched = [code for code, name in SUNFERRY_ROUTES.items()
               if name.lower().replace(" - ", "-").replace(" ", "") == pair]
    return matched


async def _hkkf_schedule(route: str, direction: str | None) -> dict:
    try:
        routes_resp = await get_global_httpx_util().get_all(
            f"{EnvLoadUtil.HKKF_BASE_URL}/opendata/route", follow_redirects=True)
        if routes_resp.status_code != 200:
            return {"error": "Failed to fetch HKKF routes"}
        routes = routes_resp.json()["data"]
    except Exception as e:
        logger.error(f"Error fetching HKKF routes: {str(e)}")
        return {"error": str(e)}

    route_id = None
    route_name = None
    if str(route).strip().isdigit():
        for r in routes:
            if r.get("route_id") == int(str(route).strip()):
                route_id, route_name = r["route_id"], r.get("route_name_en", "")
                break
    else:
        matched = [r for r in routes
                   if str(route).strip().lower() in (r.get("route_name_en", "") or "").lower()]
        if len(matched) == 1:
            route_id, route_name = matched[0]["route_id"], matched[0].get("route_name_en", "")
    if route_id is None:
        return {
            "error": f"Unknown HKKF route: {route}",
            "valid_routes": [r.get("route_name_en", "") for r in routes],
        }

    directions = [direction.lower()] if direction else list(HKKF_DIRECTIONS)
    if any(d not in HKKF_DIRECTIONS for d in directions):
        return {"error": f"Invalid direction: {direction}",
                "details": f"direction must be one of {list(HKKF_DIRECTIONS)}."}
    etas = []
    try:
        for d in directions:
            resp = await get_global_httpx_util().get_all(
                f"{EnvLoadUtil.HKKF_BASE_URL}/opendata/eta/{route_id}/{d}",
                follow_redirects=True)
            if resp.status_code != 200:
                logger.warning(f"HKKF eta {route_id}/{d} -> {resp.status_code}")
                continue
            for entry in resp.json().get("data", []):
                etas.append({
                    "direction": entry.get("direction", d),
                    "date": entry.get("date"),
                    "session_time": entry.get("session_time"),
                    "eta": entry.get("ETA"),
                })
    except Exception as e:
        logger.error(f"Error fetching HKKF ETA: {str(e)}")
        return {"error": str(e)}
    return {
        "operator": "hkkf",
        "route_id": route_id,
        "route_name_en": route_name,
        "count": len(etas),
        "etas": etas,
    }


async def _sunferry_schedule(route: str) -> dict:
    codes = _resolve_sunferry_route(route)
    if not codes:
        return {
            "error": f"Unknown Sun Ferry route: {route}",
            "valid_routes": [f"{c} ({n})" for c, n in SUNFERRY_ROUTES.items()],
        }
    vessels = []
    try:
        for code in codes:
            resp = await get_global_httpx_util().get_all(
                EnvLoadUtil.SUNFERRY_ETA_URL.format(route_code=code))
            if resp.status_code != 200:
                logger.warning(f"Sun Ferry eta {code} -> {resp.status_code}")
                continue
            for entry in resp.json().get("data", []):
                vessels.append({
                    "route_code": entry.get("routecode", code),
                    "route_en": entry.get("route_en", SUNFERRY_ROUTES[code]),
                    "depart_time": entry.get("depart_time"),
                    "eta": entry.get("eta"),
                    "vessel_lat": entry.get("lat"),
                    "vessel_lng": entry.get("lng"),
                    "remarks_en": entry.get("rmk_en"),
                })
    except Exception as e:
        logger.error(f"Error fetching Sun Ferry ETA: {str(e)}")
        return {"error": str(e)}
    return {
        "operator": "sunferry",
        "route_codes": codes,
        "count": len(vessels),
        "vessels": vessels,
    }


async def _starferry_schedule(route: str) -> dict:
    key = str(route).strip().lower().replace(" ", "")
    if "wanchai" in key or "wan chai" in str(route).strip().lower():
        key = "wanchai"
    elif "central" in key:
        key = "central"
    url = STARFERRY_TIMETABLES.get(key)
    if url is None:
        return {
            "error": f"Unknown Star Ferry route: {route}",
            "valid_routes": ["central (Central - Tsim Sha Tsui)",
                             "wanchai (Wan Chai - Tsim Sha Tsui)"],
        }
    logger.info(f"Fetching Star Ferry timetable: {key}...")
    try:
        resp = await get_global_httpx_util().get_all(url)
        if resp.status_code != 200:
            return {"error": "Failed to fetch Star Ferry timetable"}
        rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
        header_idx = next((i for i, r in enumerate(rows)
                           if r and r[0].strip().lower() == "direction"), None)
        if header_idx is None:
            return {"error": "Unrecognized Star Ferry timetable format"}
        timetable = []
        for row in rows[header_idx + 1:]:
            if len(row) < 4 or not row[0].strip():
                continue
            timetable.append({
                "direction": row[0].strip(),
                "service_days": row[1].strip(),
                "hours": row[2].strip(),
                "frequency_min": row[3].strip(),
            })
    except Exception as e:
        logger.error(f"Error fetching Star Ferry timetable: {str(e)}")
        return {"error": str(e)}
    return {
        "operator": "starferry",
        "route": key,
        "count": len(timetable),
        "timetable": timetable,
    }


async def get_ferry_schedule(operator: str, route: str, direction: str | None = None) -> dict:
    op = OPERATOR_ALIASES.get(str(operator).strip().lower())
    if op is None:
        return {
            "error": f"Unknown ferry operator: {operator}",
            "valid_operators": ["hkkf", "sunferry", "starferry"],
        }
    logger.info(f"Fetching ferry schedule: {op} / {route} / {direction}...")
    if op == "hkkf":
        return await _hkkf_schedule(route, direction)
    if op == "sunferry":
        return await _sunferry_schedule(route)
    return await _starferry_schedule(route)
