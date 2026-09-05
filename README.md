# hk-daily-mcp

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.14-blue.svg)

**Hong Kong daily information as MCP tools** — KMB bus ETAs, HKO weather,
MTR next trains, ferry schedules, tides, public holidays, air quality (AQHI)
and keyword news. Exposed both as an MCP server (17 tools over stdio or
Streamable HTTP) and a FastAPI REST API — no API keys required except
optionally for news.

## Features

- **17 MCP tools** across transport, weather & environment, calendar and daily
  briefs (see [MCP tools](#mcp-tools-17)).
- **Two transports**: MCP over stdio (for Claude Desktop / local hosts) and
  MCP over Streamable HTTP mounted on the same FastAPI app.
- **Keyless by default** — every feed is public open data; only the news
  domain needs an optional `NEWS_API_KEY`.
- **Offline fallback** — bundled `res/` snapshots (KMB routes/stops, HKO
  station coords, MTR line/station table) keep tools working when a live API
  is down.
- **Broad client compatibility** — negotiates MCP protocol versions from
  `2024-11-05` to `2026-07-28` automatically.
- **REST + MCP in one process** — `GET /mcp` (HTTP transport) and
  `GET /health` on the same server.

## Quickstart

Requires Python >= 3.14 and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/chauchauhy/hk-daily-mcp.git
cd hk-daily-mcp

uv sync                       # installs deps + dev tools (pytest, ruff)
cp .env.sample .env           # optional; only NEWS_API_KEY is a secret
```

**Run REST + MCP over HTTP** (single process, port 8000):

```bash
cd src
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

- REST endpoints: `http://127.0.0.1:8000/router/...`
- MCP endpoint (Streamable HTTP): `http://127.0.0.1:8000/mcp`
- Health check: `http://127.0.0.1:8000/health`

**Run the MCP server over stdio** (for Claude Desktop / local MCP hosts):

```bash
cd src
uv run python mcp_server.py
```

## Connect from an MCP host

Works with any MCP-compatible host (Claude Desktop, OpenClaw, Hermes Agent,
other MCP clients) over stdio or Streamable HTTP.

**stdio** — add to the host's MCP config (e.g. `claude_desktop_config.json`),
pointing `cwd` at this repo's `src/` directory:

```json
{
  "mcpServers": {
    "hk-daily-mcp": {
      "command": "uv",
      "args": ["run", "python", "mcp_server.py"],
      "cwd": "/absolute/path/to/hk-daily-mcp/src"
    }
  }
}
```

**Streamable HTTP** — start the REST + MCP server once (see Quickstart) and
point the host at `http://127.0.0.1:8000/mcp`. Note that `/mcp` returns a
307 redirect to `/mcp/`; the official MCP SDK client and most hosts follow
it automatically — use `/mcp/` directly if your client does not follow
redirects.

The server is localhost-only by design: the SDK auto-enables DNS-rebinding
protection, so requests from Host/Origin values other than `127.0.0.1`,
`localhost` or `::1` are rejected (421/403).

## MCP tools (17)

| Tool | Description |
|---|---|
| `kmb_get_all_routes` | All KMB bus routes |
| `kmb_find_nearby_stops` | KMB stops near a lat/lon pair |
| `kmb_find_nearby_stops_by_address` | Geocode an address, find KMB stops near it |
| `kmb_get_bus_eta` | Live ETAs for stops near an address (optionally filtered by route) |
| `kmb_get_route_itinerary` | Ordered stops of a route bound, each with live ETAs |
| `mtr_get_next_train` | Live MTR next-train arrivals (codes or names) |
| `ferry_get_schedule` | Ferry schedules: HKKF/Sun Ferry live ETA, Star Ferry timetable |
| `hko_get_weather_forecast` | HKO local weather forecast |
| `hko_get_nearby_weather` | Nearest HKO stations: temperature + humidity + rainfall + UV |
| `hko_get_9day_forecast` | HKO 9-day forecast |
| `hko_get_weather_warnings` | Active HKO weather warnings (typhoon, rainstorm…) |
| `hko_get_special_weather_tips` | HKO special weather tips |
| `hko_get_tide_predictions` | High/low tide times and heights for a station/date |
| `hk_get_air_quality` | AQHI by monitoring station ('all' or a station/district) |
| `hk_get_public_holidays` | Hong Kong public holidays for a year |
| `daily_summary` | Legacy summary (weather + KMB ETAs + keyword news); frozen shape |
| `hk_daily_brief` | Broad briefing: weather, holidays, tide, AQHI by default; transport/news opt-in |

## REST API

The same workflows are available as REST endpoints under `/router/...`
(e.g. `/router/kmb_router/eta/address/{address}`, `/router/hko_router/{lang}/flw`).
`GET /health` returns `{"status": "ok", "version": "0.1.0"}`.

## Data sources & licenses

The service reads from public Hong Kong data feeds (no API keys required
except NewsAPI):

- KMB bus routes / stops / ETAs — `data.etabus.gov.hk` (open data)
- MTR next-train schedules — `rt.data.gov.hk`
- HKO weather, tides — `data.weather.gov.hk`
- Air Quality Health Index (AQHI) — `aqhi.gov.hk` (EPD)
- Public holidays — `www.1823.gov.hk`
- Ferries — `hkkfeta.com`, `sunferry.com.hk`, `starferry.com.hk`
- News — NewsAPI (`NEWS_API_KEY`, optional)

The bundled offline snapshots under `res/` (KMB routes/stops, HKO station
coordinates, MTR line/station table) are derived from those same open feeds
and are used as a fallback when a live API is unavailable.

## Project layout

- `src/main.py` — FastAPI app, MCP mounted at `/mcp`, `/health`
- `src/mcp_server.py` — MCP tools + stdio entrypoint
- `src/routes/` — REST routers (thin, delegate to services)
- `src/utils/*_service.py` — shared workflows used by REST and MCP
- `src/models/` — pydantic models for KMB/HKO payloads
- `res/` — bundled offline data (KMB stops/routes, HKO station coords,
  MTR line/station table)
- `tests/` — pytest suite including in-process HTTP transport tests

## Contributing

Issues and pull requests are welcome. To get started:

- Requires `uv` and Python >= 3.14 (`.python-version` pins 3.14 for uv).
- `uv sync` installs deps + dev tools (pytest, ruff).
- Run the offline suite: `uv run pytest -m "not network"` (no network, no keys).
- Run the live smoke tests (optional, hits real APIs): `uv run pytest -m network`.
- Keep it green: `uv run ruff check src tests` before pushing; CI runs the
  offline suite + ruff on every push/PR.

**Adding a new MCP tool:** add a shared workflow function in
`src/utils/*_service.py`, expose it with `@mcp.tool()` in `src/mcp_server.py`,
then add a registration test (`tests/test_*_registration`) and a
`@pytest.mark.network` smoke test — mirror the existing tools.

## License

[MIT](LICENSE)
