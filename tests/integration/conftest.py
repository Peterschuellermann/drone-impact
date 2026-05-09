import numpy as np
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from droneimpact.api.analyze import router as analyze_router
from droneimpact.api.batch import JobStore, router as batch_router
from droneimpact.api.health import router as health_router
from droneimpact.data.buildings import BuildingIndex
from droneimpact.data.dem import DEMIndex
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex
from tests.fixtures.population_small import make_test_population


def build_test_app(config):
    """Build a FastAPI app with pre-loaded synthetic data injected into state."""
    app = FastAPI(title="DroneImpact-test")
    app.include_router(health_router)
    app.include_router(analyze_router)
    app.include_router(batch_router)

    dem = DEMIndex.from_array(
        np.full((20, 20), 0.0, dtype=np.float32),
        west=28.0, south=46.0, east=36.0, north=52.0,
    )
    cells = make_test_population(48.0, 31.0, pop_density=1000.0, radius_cells=5)
    population = PopulationIndex.from_dict(cells)
    infrastructure = InfrastructureIndex.from_features([], config.casualty.infrastructure)

    app.state.config = config
    app.state.dem = dem
    app.state.population = population
    app.state.infrastructure = infrastructure
    app.state.buildings = BuildingIndex.empty(config.casualty.sheltering)
    app.state.data_loaded = True
    app.state.population_cells = population.cell_count
    app.state.job_store = JobStore()

    return app


@pytest.fixture
def test_app(config):
    return build_test_app(config)


@pytest.fixture
async def client(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        yield c
