# F11 — Startup Data Loading + Health Endpoint

**Status:** pending  
**Branch:** `feature/F11-startup-health`  
**Dependencies:** F03, F07, F08

---

## Goal

Wire together the data loading sequence into a FastAPI application lifecycle. At startup, load DEM, population, and infrastructure data into memory. Expose the loaded indices as application state accessible to route handlers. Add a `/health` endpoint that reports loading status.

---

## Acceptance Criteria

- [ ] FastAPI app loads DEM, Kontur, and OSM data at startup using `lifespan` context manager
- [ ] `GET /health` returns `{ "status": "ok", "data_loaded": true, "population_cells": N }` after successful load
- [ ] `GET /health` returns `{ "status": "degraded", "data_loaded": false }` if data files are missing
- [ ] App state (loaded indices) is accessible in route handlers via `request.app.state`
- [ ] Startup completes without raising exceptions when data files are present
- [ ] Startup logs progress and timing for each data file loaded
- [ ] `pytest tests/integration/test_health.py` passes (uses mock data, no real files required)

---

## Implementation Steps

### 1. src/droneimpact/main.py (replace stub from F01)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from droneimpact.config import load_config
from droneimpact.data.dem import DEMIndex
from droneimpact.data.population import PopulationIndex
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.api.health import router as health_router
import logging
import time

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    app.state.config = cfg
    app.state.data_loaded = False
    app.state.population_cells = 0

    try:
        t0 = time.perf_counter()

        logger.info("Loading DEM from %s", cfg.data.dem_path)
        app.state.dem = DEMIndex.load_from_file(cfg.data.dem_path)
        logger.info("DEM loaded in %.1f s", time.perf_counter() - t0)

        t1 = time.perf_counter()
        logger.info("Loading population from %s", cfg.data.population_path)
        app.state.population = PopulationIndex.load_from_file(cfg.data.population_path)
        app.state.population_cells = app.state.population.cell_count
        logger.info("Population loaded in %.1f s (%d cells)",
                    time.perf_counter() - t1, app.state.population_cells)

        t2 = time.perf_counter()
        logger.info("Loading infrastructure from %s", cfg.data.infrastructure_path)
        app.state.infrastructure = InfrastructureIndex.load_from_file(
            cfg.data.infrastructure_path, cfg.casualty.infrastructure)
        logger.info("Infrastructure loaded in %.1f s", time.perf_counter() - t2)

        app.state.data_loaded = True
        logger.info("All data loaded. Total startup: %.1f s", time.perf_counter() - t0)

    except FileNotFoundError as e:
        logger.warning("Data file missing: %s — starting in degraded mode", e)
        # App starts but data_loaded = False; /health will report degraded

    yield
    # Cleanup (none required for in-memory data)


def create_app() -> FastAPI:
    app = FastAPI(title="DroneImpact", version="1.0.0", lifespan=lifespan)
    app.include_router(health_router)
    return app

app = create_app()
```

### 2. src/droneimpact/api/health.py

```python
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    data_loaded: bool
    population_cells: int = 0

@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    data_loaded = getattr(request.app.state, "data_loaded", False)
    pop_cells   = getattr(request.app.state, "population_cells", 0)
    return HealthResponse(
        status="ok" if data_loaded else "degraded",
        data_loaded=data_loaded,
        population_cells=pop_cells,
    )
```

### 3. src/droneimpact/api/__init__.py

Add an `AppState` typed accessor to avoid `getattr` scattered through route handlers:

```python
from dataclasses import dataclass
from droneimpact.data.dem import DEMIndex
from droneimpact.data.population import PopulationIndex
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.config import AppConfig

@dataclass
class AppState:
    config: AppConfig
    dem: DEMIndex
    population: PopulationIndex
    infrastructure: InfrastructureIndex
    data_loaded: bool
    population_cells: int

def get_app_state(request) -> AppState:
    return AppState(
        config=request.app.state.config,
        dem=request.app.state.dem,
        population=request.app.state.population,
        infrastructure=request.app.state.infrastructure,
        data_loaded=request.app.state.data_loaded,
        population_cells=request.app.state.population_cells,
    )
```

---

## Tests

### tests/integration/test_health.py

Use `httpx.AsyncClient` + `ASGITransport` to call the FastAPI app without a real server. Patch data loading to avoid needing real files.

```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock
import numpy as np

@pytest.fixture
def mock_dem():
    return DEMIndex.from_array(np.full((5, 5), 100.0), 30.0, 47.0, 32.0, 49.0)

@pytest.fixture
def mock_population(config):
    from tests.fixtures.population_small import make_test_population
    cells = make_test_population(48.0, 31.0, pop_density=1000.0)
    return PopulationIndex.from_dict(cells)

@pytest.fixture
def mock_infra(config):
    return InfrastructureIndex.from_features([], config.casualty.infrastructure)

@pytest.mark.asyncio
async def test_health_data_loaded(mock_dem, mock_population, mock_infra):
    with patch("droneimpact.main.DEMIndex.load_from_file", return_value=mock_dem), \
         patch("droneimpact.main.PopulationIndex.load_from_file", return_value=mock_population), \
         patch("droneimpact.main.InfrastructureIndex.load_from_file", return_value=mock_infra):
        from droneimpact.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data_loaded"] is True
    assert body["population_cells"] > 0

@pytest.mark.asyncio
async def test_health_degraded_when_files_missing():
    with patch("droneimpact.main.DEMIndex.load_from_file",
               side_effect=FileNotFoundError("dem file not found")):
        from droneimpact.main import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["data_loaded"] is False
```

---

## Notes

- FastAPI's `lifespan` context manager (introduced in Starlette 0.20 / FastAPI 0.93) is the modern replacement for `@app.on_event("startup")`. Use lifespan.
- The `create_app()` factory function enables creating fresh app instances in tests (avoiding import-time singleton issues).
- Logging goes to stdout in JSON format in production (add `python-json-logger` to deps). For v1, plain format is fine.
- When `data_loaded = False`, the health endpoint should return HTTP 200 (not 503) — the service is up, just degraded. The API endpoints will return 503 when called in degraded mode (implemented in F12).
