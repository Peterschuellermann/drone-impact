from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from droneimpact.api.analyze import router as analyze_router
from droneimpact.api.batch import JobStore, router as batch_router
from droneimpact.api.health import router as health_router
from droneimpact.config import load_config
from droneimpact.data.dem import DEMIndex
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    app.state.config = cfg
    app.state.data_loaded = False
    app.state.population_cells = 0
    app.state.dem = None
    app.state.population = None
    app.state.infrastructure = None
    app.state.job_store = JobStore()

    try:
        t0 = time.perf_counter()

        logger.info("Loading DEM from %s", cfg.data.dem_path)
        app.state.dem = DEMIndex.load_from_file(cfg.data.dem_path)
        logger.info("DEM loaded in %.1f s", time.perf_counter() - t0)

        t1 = time.perf_counter()
        logger.info("Loading population from %s", cfg.data.population_path)
        app.state.population = PopulationIndex.load_from_file(cfg.data.population_path)
        app.state.population_cells = app.state.population.cell_count
        logger.info(
            "Population loaded in %.1f s (%d cells)",
            time.perf_counter() - t1,
            app.state.population_cells,
        )

        t2 = time.perf_counter()
        logger.info("Loading infrastructure from %s", cfg.data.infrastructure_path)
        app.state.infrastructure = InfrastructureIndex.load_from_file(
            cfg.data.infrastructure_path, cfg.casualty.infrastructure
        )
        logger.info("Infrastructure loaded in %.1f s", time.perf_counter() - t2)

        app.state.data_loaded = True
        logger.info("All data loaded. Total startup: %.1f s", time.perf_counter() - t0)

    except Exception as e:
        logger.warning("Failed to load data: %s — starting in degraded mode", e)

    yield


def create_app() -> FastAPI:
    app = FastAPI(title="DroneImpact", version="1.0.0", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(analyze_router)
    app.include_router(batch_router)
    return app


app = create_app()
