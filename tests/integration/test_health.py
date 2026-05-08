import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from droneimpact.data.dem import DEMIndex
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex
from tests.fixtures.population_small import make_test_population


def _make_loaded_app(config, dem, population, infra):
    """Create a FastAPI app and inject pre-built data into its state, bypassing file I/O."""
    from fastapi import FastAPI
    from droneimpact.api.health import router as health_router

    app = FastAPI(title="DroneImpact-test", version="1.0.0")
    app.include_router(health_router)

    app.state.config = config
    app.state.dem = dem
    app.state.population = population
    app.state.infrastructure = infra
    app.state.data_loaded = True
    app.state.population_cells = population.cell_count

    return app


def _make_degraded_app(config):
    """Create a FastAPI app in degraded mode (no data loaded)."""
    from fastapi import FastAPI
    from droneimpact.api.health import router as health_router

    app = FastAPI(title="DroneImpact-test-degraded", version="1.0.0")
    app.include_router(health_router)

    app.state.config = config
    app.state.dem = None
    app.state.population = None
    app.state.infrastructure = None
    app.state.data_loaded = False
    app.state.population_cells = 0

    return app


@pytest.fixture
def mock_dem():
    return DEMIndex.from_array(np.full((5, 5), 100.0, dtype=np.float32),
                                30.0, 47.0, 32.0, 49.0)


@pytest.fixture
def mock_population():
    cells = make_test_population(48.0, 31.0, pop_density=1000.0)
    return PopulationIndex.from_dict(cells)


@pytest.fixture
def mock_infra(config):
    return InfrastructureIndex.from_features([], config.casualty.infrastructure)


@pytest.mark.asyncio
async def test_health_data_loaded(config, mock_dem, mock_population, mock_infra):
    app = _make_loaded_app(config, mock_dem, mock_population, mock_infra)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data_loaded"] is True
    assert body["population_cells"] > 0


@pytest.mark.asyncio
async def test_health_degraded(config):
    app = _make_degraded_app(config)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["data_loaded"] is False


@pytest.mark.asyncio
async def test_health_response_schema(config, mock_dem, mock_population, mock_infra):
    app = _make_loaded_app(config, mock_dem, mock_population, mock_infra)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    body = response.json()
    assert {"status", "data_loaded", "population_cells"} <= set(body.keys())


@pytest.mark.asyncio
async def test_health_population_cells_zero_in_degraded(config):
    app = _make_degraded_app(config)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.json()["population_cells"] == 0
