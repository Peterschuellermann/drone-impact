# DroneImpact

A physics-based engagement advisor for air defence operators intercepting Shahed-136 (Geran-2) loitering munitions. Given a drone's current trajectory, the system computes expected civilian casualties for each possible intercept point and recommends the optimal engagement location.

## Problem

When an air defence unit shoots down a drone, the intercept location determines where wreckage and the warhead land. Intercepting over a populated area may cause more casualties than letting the drone continue to a less-populated corridor. DroneImpact quantifies this tradeoff for every point along the trajectory so operators can make informed engagement decisions.

## How It Works

1. The operator provides the drone's current state vector: latitude, longitude, altitude, heading, and speed.
2. The system discretises the trajectory into evaluation points (default: every 500 m).
3. For each point, a Monte Carlo simulation (10,000 samples) models three intercept outcomes:
   - **Propulsion loss** — engine destroyed, drone glides to impact
   - **Loss of control** — avionics destroyed, drone flies erratically
   - **Break apart** — structural failure, warhead tumbles ballistically
4. Each simulated impact point is scored against population density (Kontur dataset) and critical infrastructure proximity (OpenStreetMap).
5. The system returns a scored list of all evaluation points and recommends the one with the lowest expected casualties.

## Project Structure

```
droneimpact/
├── spec/           # Living system specification (physics, casualty, engagement models)
├── plans/          # Feature implementation plans
├── src/
│   └── droneimpact/    # Python package (FastAPI + NumPy/Numba simulation engine)
├── tests/
│   ├── unit/           # Isolated function-level tests
│   ├── integration/    # Component interaction tests
│   └── performance/    # Latency budget assertions
├── data/           # Runtime data files (gitignored — see Data Setup below)
├── config.yaml     # Tunable parameters (physics constants, mode weights, radii)
├── CLAUDE.md       # Agent development workflow
└── README.md       # This file
```

## API

### Single drone analysis

```
POST /analyze/single
```

```json
{
  "trajectory": {
    "lat": 48.3794,
    "lon": 31.1656,
    "altitude_m": 400,
    "heading_deg": 315.0,
    "speed_m_s": 51.4
  }
}
```

Returns a scored list of trajectory points with the recommended engagement point, per-mode casualty breakdowns, and a human-readable explanation.

### Batch analysis

```
POST /analyze/batch
```

Accepts up to 100 drones. Runs synchronously for small batches (up to 5) or returns a job ID for async processing.

### Health check

```
GET /health
```

Reports whether data indices are loaded and ready.

See [spec/inputs-outputs.md](spec/inputs-outputs.md) for full request/response schemas.

## Data Setup

DroneImpact requires three external datasets loaded at startup. These are not included in the repository.

| Dataset | Source | Purpose |
|---|---|---|
| [Kontur Population](https://data.humdata.org/dataset/kontur-population-dataset) | Kontur (CC BY 4.0) | Population density per H3 cell |
| [SRTM / Copernicus DEM](https://earthexplorer.usgs.gov) | NASA/USGS (public domain) | Terrain elevation for MSL-to-AGL conversion |
| [OpenStreetMap Ukraine](https://download.geofabrik.de/europe/ukraine.html) | Geofabrik (ODbL 1.0) | Critical infrastructure locations |

Place pre-processed files in `data/`:
```
data/kontur_ukraine.gpkg
data/ukraine_dem.tif
data/ukraine_infra.geojson
```

## Running

```bash
pip install -r requirements.txt
uvicorn src.droneimpact.main:app --host 0.0.0.0 --port 8080
```

Or with Docker:

```bash
docker build -t droneimpact .
docker run -p 8080:8080 droneimpact
```

## Testing

```bash
pytest                              # all tests
pytest tests/unit/                  # unit tests only
pytest --cov=src/droneimpact        # with coverage
pytest tests/performance/ --run-perf  # performance benchmarks (requires real data)
```

## Performance Targets

| Scenario | Limit |
|---|---|
| Single drone analysis | < 500 ms |
| Batch of 50 drones | < 15 s |
| Memory footprint (Ukraine data) | < 1 GB |

## Specification

The full system specification lives in [spec/](spec/):

- [Overview](spec/overview.md) — goals, glossary, stakeholders
- [Inputs & Outputs](spec/inputs-outputs.md) — API contracts and JSON schemas
- [Physics Model](spec/physics-model.md) — Shahed-136 aerodynamics, terminal trajectory models
- [Casualty Model](spec/casualty-model.md) — blast, fragmentation, population, infrastructure scoring
- [Engagement Model](spec/engagement-model.md) — P_kill, mode weights, scoring formula
- [Data Sources](spec/data-sources.md) — Kontur, SRTM, OSM, ACLED, historical data
- [Architecture](spec/architecture.md) — FastAPI, vectorised engine, tech stack
- [Roadmap](spec/roadmap.md) — v2 (wind, sheltering), v3 (trajectory prediction), v4 (dashboard)

## Licence

Not yet specified.
