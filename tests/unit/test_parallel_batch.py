import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pytest

from droneimpact.api import AppState
from droneimpact.api.batch import (
    BatchRequest,
    _analyze_one,
    _execute_batch,
    _init_batch_worker,
)
from droneimpact.api.schemas import SingleDroneRequest, TrajectoryInput
from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.data.dem import DEMIndex
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex
from tests.fixtures.population_small import make_test_population

BOUNDS = dict(west=28.0, south=46.0, east=36.0, north=52.0)


def _make_state(config):
    dem = DEMIndex.from_array(
        np.full((20, 20), 0.0, dtype=np.float32),
        **BOUNDS,
    )
    cells = make_test_population(48.0, 31.0, pop_density=1000.0, radius_cells=5)
    population = PopulationIndex.from_dict(cells)
    infrastructure = InfrastructureIndex.from_features([], config.casualty.infrastructure)
    return AppState(
        config=config,
        dem=dem,
        population=population,
        infrastructure=infrastructure,
        data_loaded=True,
        population_cells=population.cell_count,
    )


def _make_drone_req(lat=48.1, drone_id=None):
    return SingleDroneRequest(
        drone_id=drone_id,
        trajectory=TrajectoryInput(
            lat=lat, lon=31.0, altitude_m=400.0,
            heading_deg=180.0, speed_m_s=51.4,
        ),
        max_range_m=5000,
        evaluation_spacing_m=1000,
    )


class TestBatchSequentialVsParallel:
    def test_batch_results_match(self, config):
        state = _make_state(config)
        drones = [_make_drone_req(lat=48.1 + i * 0.01, drone_id=f"d-{i}") for i in range(3)]
        batch_req = BatchRequest(drones=drones)

        seq_result = _execute_batch(batch_req, state, executor=None)
        assert seq_result["status"] == "complete"
        assert len(seq_result["results"]) == 3

        ctx = mp.get_context("fork")
        executor = ProcessPoolExecutor(
            max_workers=2, mp_context=ctx,
            initializer=_init_batch_worker, initargs=(state,),
        )
        try:
            par_result = _execute_batch(batch_req, state, executor=executor)
        finally:
            executor.shutdown(wait=True)

        assert par_result["status"] == "complete"
        assert len(par_result["results"]) == 3

        seq_scores = sorted(
            r["recommended_engagement"]["engagement_score"] for r in seq_result["results"]
        )
        par_scores = sorted(
            r["recommended_engagement"]["engagement_score"] for r in par_result["results"]
        )
        for s, p in zip(seq_scores, par_scores):
            assert s == pytest.approx(p, rel=1e-6)


class TestBatchErrorIsolation:
    def test_partial_failure(self, config):
        state = _make_state(config)
        good_drone = _make_drone_req(lat=48.1, drone_id="good")
        bad_drone = _make_drone_req(lat=48.1, drone_id="bad")
        bad_drone.trajectory.altitude_m = -1000.0

        batch_req = BatchRequest(drones=[good_drone, bad_drone])
        result = _execute_batch(batch_req, state, executor=None)
        assert len(result["results"]) >= 1


class TestBatchBelowThreshold:
    def test_below_threshold_uses_sequential(self, config):
        cfg = config.model_copy(update={
            "parallelism": config.parallelism.model_copy(update={"batch_parallel_threshold": 10}),
        })
        state = _make_state(cfg)
        drones = [_make_drone_req(lat=48.1 + i * 0.01, drone_id=f"d-{i}") for i in range(3)]
        batch_req = BatchRequest(drones=drones)

        ctx = mp.get_context("fork")
        executor = ProcessPoolExecutor(
            max_workers=2, mp_context=ctx,
            initializer=_init_batch_worker, initargs=(state,),
        )
        try:
            result = _execute_batch(batch_req, state, executor=executor)
        finally:
            executor.shutdown(wait=True)

        assert result["status"] == "complete"
        assert len(result["results"]) == 3
