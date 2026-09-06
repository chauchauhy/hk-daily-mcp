"""Regenerate res/route_stop_data.json from the live KMB open-data feed.

The route-stop snapshot is the join table used by the route finder
(kmb_find_route_between_addresses): it records, for every KMB lane
(route + bound + service type), the ordered list of stops it serves.
The project ships the generated file in res/ as the offline fallback.

Usage (from the repo root):
    uv run python scripts/build_kmb_route_stop_snapshot.py

Fetches the full route list, then route-stop/{route}/{bound}/{service_type}
for every lane (concurrently), and writes res/route_stop_data.json.
"""
import asyncio
import json
import os
from datetime import datetime, timezone

import httpx

BASE = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))
RES = os.path.join(BASE, "res")
ROUTE_URL = "https://data.etabus.gov.hk/v1/transport/kmb/route/"
ROUTE_STOP_URL = "https://data.etabus.gov.hk/v1/transport/kmb/route-stop/{route}/{direction}/{service_type}"
OUT_FILE = os.path.join(RES, "route_stop_data.json")

BOUND_WORD = {"O": "outbound", "I": "inbound"}
CONCURRENCY = 20
MAX_RETRIES = 3


def norm_bound(raw) -> str:
    """Normalize a bound value ('inbound'/'outbound'/'I'/'O' or dir flag) to O/I."""
    if not isinstance(raw, str):
        return "O"
    value = raw.strip().lower()
    if value in ("i", "inbound"):
        return "I"
    if value in ("o", "outbound"):
        return "O"
    upper = raw.strip().upper()
    return upper if upper in ("O", "I") else "O"


async def fetch_lane(client: httpx.AsyncClient, lane: dict, sem: asyncio.Semaphore,
                     results: list, errors: list) -> None:
    route = str(lane["route"]).strip()
    bound = norm_bound(lane.get("bound"))
    service_type = str(lane.get("service_type", "1")).strip()
    url = ROUTE_STOP_URL.format(route=route, direction=BOUND_WORD[bound], service_type=service_type)
    async with sem:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.get(url, timeout=20)
                if response.status_code != 200:
                    errors.append((url, response.status_code))
                    return
                payload = response.json()
                for item in payload.get("data", []):
                    results.append({
                        "co": str(item.get("co") or "KMB"),
                        "route": str(item.get("route") or route),
                        "bound": norm_bound(item.get("bound") or item.get("dir") or bound),
                        "service_type": str(item.get("service_type") or service_type),
                        "seq": int(item.get("seq", 0)),
                        "stop": str(item.get("stop", "")),
                    })
                return
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                if attempt == MAX_RETRIES:
                    errors.append((url, f"exc: {exc}"))
                else:
                    await asyncio.sleep(1)


async def main() -> int:
    async with httpx.AsyncClient() as client:
        route_response = await client.get(ROUTE_URL, timeout=30)
        if route_response.status_code != 200:
            print(f"Failed to fetch route list: {route_response.status_code}")
            return 1
        lanes = route_response.json().get("data", [])

    print(f"Fetched {len(lanes)} KMB lanes; fetching route-stop lists (concurrency={CONCURRENCY})...")
    sem = asyncio.Semaphore(CONCURRENCY)
    results: list[dict] = []
    errors: list[tuple] = []

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(fetch_lane(client, lane, sem, results, errors) for lane in lanes))

    # Deterministic output: sort by route, bound, service_type, seq.
    results.sort(key=lambda r: (r["route"], r["bound"], r["service_type"], r["seq"]))

    payload = {
        "type": "RouteStopList",
        "version": "1.0",
        "generated_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "+08:00"),
        "data": results,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    lanes_covered = {(r["route"], r["bound"], r["service_type"]) for r in results}
    print(f"Wrote {OUT_FILE}: {len(results)} route-stop entries across {len(lanes_covered)} lanes.")
    if errors:
        print(f"Warnings: {len(errors)} lanes failed ({errors[:5]}...).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
