from __future__ import annotations

import logging
import multiprocessing as mp
import time
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from droneimpact.api.analyze import router as analyze_router
from droneimpact.api.batch import JobStore, _init_batch_worker, router as batch_router
from droneimpact.api.buildings import router as buildings_router
from droneimpact.api.cache import ResultCache, compute_fingerprint
from droneimpact.api.data import router as data_router
from droneimpact.api.health import router as health_router
from droneimpact.config import load_config
from droneimpact.data.buildings import BuildingIndex
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
    app.state.buildings = BuildingIndex.empty(cfg.casualty.sheltering)
    app.state.job_store = JobStore()
    app.state.batch_executor = None
    app.state.strikes = None

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

        if cfg.data.buildings_path and Path(cfg.data.buildings_path).exists():
            t3 = time.perf_counter()
            logger.info("Loading buildings from %s", cfg.data.buildings_path)
            app.state.buildings = BuildingIndex.load_from_file(
                cfg.data.buildings_path, cfg.casualty.sheltering
            )
            logger.info(
                "Buildings loaded in %.1f s (%d cells)",
                time.perf_counter() - t3,
                app.state.buildings.cell_count,
            )
        else:
            logger.info("No buildings data — sheltering disabled")

        app.state.data_loaded = True
        logger.info("All data loaded. Total startup: %.1f s", time.perf_counter() - t0)

    except Exception as e:
        logger.warning("Failed to load data: %s — starting in degraded mode", e)

    if cfg.data.strikes_path:
        from droneimpact.data.strikes import StrikeIndex
        logger.info("Loading strike index from %s", cfg.data.strikes_path)
        app.state.strikes = StrikeIndex.load_from_file(cfg.data.strikes_path)
        logger.info("Strike index: %d locations", app.state.strikes.count)

    from droneimpact.physics.warmup import warmup_jit
    logger.info("Warming up Numba JIT kernels...")
    t_jit = time.perf_counter()
    warmup_jit()
    logger.info("JIT warm-up complete in %.1f s", time.perf_counter() - t_jit)

    fingerprint = compute_fingerprint(cfg)
    cache = ResultCache(
        cache_dir=Path(cfg.cache.directory),
        fingerprint=fingerprint,
        max_entries=cfg.cache.max_entries,
        enabled=cfg.cache.enabled,
    )
    if cache.enabled:
        pruned = cache.prune_stale()
        if pruned:
            logger.info("Pruned %d stale cache entries", pruned)
        logger.info("Result cache enabled (fingerprint=%s, max=%d)", fingerprint, cfg.cache.max_entries)
    else:
        logger.info("Result cache disabled")
    app.state.result_cache = cache

    n_batch_workers = cfg.parallelism.effective_batch_workers
    if n_batch_workers > 1 and app.state.data_loaded:
        try:
            from droneimpact.api import AppState
            state_dict = AppState(
                config=app.state.config,
                dem=app.state.dem,
                population=app.state.population,
                infrastructure=app.state.infrastructure,
                buildings=app.state.buildings,
                data_loaded=True,
                population_cells=app.state.population_cells,
                strikes=app.state.strikes,
            )
            ctx = mp.get_context("spawn")
            executor = ProcessPoolExecutor(
                max_workers=n_batch_workers,
                mp_context=ctx,
                initializer=_init_batch_worker,
                initargs=(state_dict,),
            )
            app.state.batch_executor = executor
            logger.info("Batch ProcessPoolExecutor started with %d workers", n_batch_workers)
        except Exception as e:
            logger.warning("Failed to create batch executor: %s — batch will run sequentially", e)

    yield

    if app.state.batch_executor is not None:
        app.state.batch_executor.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="DroneImpact", version="1.2.0", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(analyze_router)
    app.include_router(batch_router)
    app.include_router(buildings_router)
    app.include_router(data_router)
    return app


app = create_app()
