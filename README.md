# daily-data-assistant

Hong Kong daily-information assistant: KMB bus ETAs, HKO weather,
MTR next-trains, ferry schedules, tides, public holidays, air quality
and keyword news — exposed as both a FastAPI REST API and an MCP server.

## Transports

- REST: `http://127.0.0.1:8000/router/...` (existing endpoints, unchanged)
- MCP over Streamable HTTP: `http://127.0.0.1:8000/mcp` (mounted on the same app)
- MCP over stdio: `python mcp_server.py` (run from `src/`)

## Setup

Requires Python ≥ 3.14 and `uv`.

- `uv sync`
- Copy `.env.sample` to `.env` and fill in values (`.env` is gitignored).
  Only `NEWS_API_KEY` is a real secret; every other feed is key-free.
  See `.env.sample` for the full key list.

## Run

All commands assume `uv sync` has been run once from the repo root.

**REST + MCP over HTTP** (single process, port 8000):

```bash
cd src
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

- REST endpoints: `http://127.0.0.1:8000/router/...`
- MCP endpoint (Streamable HTTP): `http://127.0.0.1:8000/mcp`

**MCP over stdio** (for Claude Desktop / local MCP hosts):

```bash
cd src
uv run python mcp_server.py
```

**Tests** (from the repo root):

```bash
uv run pytest
uv run pytest -m "not network"   # skip live-API smoke tests
```

## MCP tools (17)

- Transport: `kmb_get_all_routes`, `kmb_find_nearby_stops`,
  `kmb_find_nearby_stops_by_address`, `kmb_get_bus_eta`,
  `kmb_get_route_itinerary`, `mtr_get_next_train`, `ferry_get_schedule`
  (`hkkf` / `sunferry` live ETA, `starferry` static timetable)
- Weather & environment: `hko_get_weather_forecast`,
  `hko_get_nearby_weather` (temperature + humidity + rainfall + UV),
  `hko_get_9day_forecast`, `hko_get_weather_warnings`,
  `hko_get_special_weather_tips`, `hko_get_tide_predictions`,
  `hk_get_air_quality`
- Calendar & briefs: `hk_get_public_holidays`, `daily_summary`
  (legacy shape, frozen), `hk_daily_brief` (weather, holidays, tide and
  air quality by default; transport and news are opt-in)

## Layout

- `src/main.py` — FastAPI app, MCP mounted at `/mcp`
- `src/mcp_server.py` — MCP tools + stdio entrypoint
- `src/routes/` — REST routers (thin, delegate to services)
- `src/utils/*_service.py` — shared workflows used by REST and MCP
- `src/models/` — pydantic models for KMB/HKO payloads
- `res/` — bundled offline data (KMB stops/routes, HKO station coords,
  MTR line/station table)
- `tests/` — pytest suite using the in-memory MCP client
