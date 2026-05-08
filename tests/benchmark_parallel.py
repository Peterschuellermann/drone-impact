"""
Benchmark: sequential vs parallel scoring and batch processing.

Run from repo root:
    python tests/benchmark_parallel.py

Uses synthetic data — no real data files required.
"""
import multiprocessing as mp
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from droneimpact.api import AppState
from droneimpact.api.batch import (
    BatchRequest,
    _execute_batch,
    _init_batch_worker,
)
from droneimpact.api.schemas import SingleDroneRequest, TrajectoryInput
from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.config import ModeEnable, load_config
from droneimpact.data.dem import DEMIndex
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex
from droneimpact.physics.trajectory import discretise_trajectory
from droneimpact.physics.types import StateVector
from droneimpact.scoring.engine import ScoringEngine, clear_miss_cache

NUM_CPU = os.cpu_count() or 1


def make_test_population(pop_density=3000.0):
    import h3
    all_cells: dict[str, float] = {}
    for lat_offset in range(0, 30):
        lat = 48.1 - lat_offset * 0.1
        centre = h3.latlng_to_cell(lat, 31.0, 8)
        disk = h3.grid_disk(centre, 3)
        for cell in disk:
            if cell not in all_cells:
                all_cells[cell] = pop_density * h3.cell_area(cell, unit="km^2")
    return all_cells


def setup(n_mc=500, all_modes=False):
    config = load_config("config.yaml")
    updates = {"n_monte_carlo_samples": n_mc}
    config = config.model_copy(update={
        "physics": config.physics.model_copy(update=updates),
    })
    if all_modes:
        config = config.model_copy(update={
            "engagement": config.engagement.model_copy(update={
                "mode_enable": ModeEnable(propulsion_loss=True, loss_of_control=True, break_apart=True),
            }),
        })

    dem = DEMIndex.from_array(
        np.full((100, 100), 100.0, dtype=np.float32),
        west=25.0, south=42.0, east=40.0, north=55.0,
    )
    cells = make_test_population()
    population = PopulationIndex.from_dict(cells)
    infrastructure = InfrastructureIndex.from_features([], config.casualty.infrastructure)

    state = AppState(
        config=config, dem=dem, population=population,
        infrastructure=infrastructure, data_loaded=True,
        population_cells=population.cell_count,
    )
    return config, dem, population, infrastructure, state


def benchmark_single_drone(config, dem, casualty_engine, spacing_m, max_range_m, point_workers, n_trials=3):
    sv = StateVector(lat=48.1, lon=31.0, altitude_m=400.0, heading_deg=180.0, speed_m_s=51.4)
    trajectory = discretise_trajectory(sv, spacing_m=spacing_m, max_range_m=max_range_m)
    n_pts = len(trajectory)

    clear_miss_cache()
    engine = ScoringEngine(config, max_point_workers=point_workers)

    engine.score_trajectory(trajectory, dem, casualty_engine, (sv.lat, sv.lon),
                            rng=np.random.default_rng(0))

    times = []
    for trial in range(n_trials):
        clear_miss_cache()
        t0 = time.perf_counter()
        engine.score_trajectory(trajectory, dem, casualty_engine, (sv.lat, sv.lon),
                                rng=np.random.default_rng(trial + 1))
        times.append(time.perf_counter() - t0)

    return n_pts, np.mean(times) * 1000, np.std(times) * 1000


def benchmark_batch(state, n_drones, use_executor, n_trials=3):
    drones = [
        SingleDroneRequest(
            drone_id=f"drone-{i:03d}",
            trajectory=TrajectoryInput(
                lat=48.1 + i * 0.01, lon=31.0, altitude_m=400.0,
                heading_deg=180.0, speed_m_s=51.4,
            ),
            max_range_m=5000,
            evaluation_spacing_m=1000,
        )
        for i in range(n_drones)
    ]
    batch_req = BatchRequest(drones=drones)

    executor = None
    if use_executor:
        ctx = mp.get_context("fork")
        executor = ProcessPoolExecutor(
            max_workers=min(NUM_CPU, n_drones),
            mp_context=ctx,
            initializer=_init_batch_worker,
            initargs=(state,),
        )

    try:
        _execute_batch(batch_req, state, executor=executor)

        times = []
        for _ in range(n_trials):
            t0 = time.perf_counter()
            result = _execute_batch(batch_req, state, executor=executor)
            times.append(time.perf_counter() - t0)
            assert result["status"] == "complete"
    finally:
        if executor:
            executor.shutdown(wait=True)

    return np.mean(times) * 1000, np.std(times) * 1000


def fmt(mean_ms, std_ms):
    return f"{mean_ms:8.1f} ± {std_ms:5.1f} ms"


def main():
    print(f"\nCPU count: {NUM_CPU}")
    print()

    # ── Per-point parallelism (ThreadPool) ────────────────────────────────
    print("=" * 90)
    print("PER-POINT PARALLELISM (ThreadPoolExecutor)")
    print("  Config: 2 modes (M1+M2), 500 MC samples, populated trajectory")
    print("=" * 90)

    config, dem, pop, infra, state = setup(n_mc=500, all_modes=False)
    ce = CasualtyEngine(pop, infra, config.casualty)

    for spacing, max_range, label in [(500, 250_000, "500 pts"), (125, 250_000, "2000 pts")]:
        print(f"\n  {label}:")
        for w in [1, 2, 4]:
            n_pts, mean_ms, std_ms = benchmark_single_drone(config, dem, ce, spacing, max_range, w)
            print(f"    {w:2d} worker(s): {fmt(mean_ms, std_ms)}  ({n_pts} actual pts)")

    # Now with all 3 modes
    print(f"\n  3 modes (M1+M2+M3), 500 MC samples:")
    config3, dem3, pop3, infra3, state3 = setup(n_mc=500, all_modes=True)
    ce3 = CasualtyEngine(pop3, infra3, config3.casualty)

    for spacing, max_range, label in [(500, 250_000, "500 pts"), (125, 250_000, "2000 pts")]:
        print(f"\n  {label}:")
        for w in [1, 2, 4]:
            n_pts, mean_ms, std_ms = benchmark_single_drone(config3, dem3, ce3, spacing, max_range, w)
            print(f"    {w:2d} worker(s): {fmt(mean_ms, std_ms)}  ({n_pts} actual pts)")

    # ── Batch parallelism (ProcessPool) ───────────────────────────────────
    print()
    print("=" * 90)
    print("BATCH PARALLELISM (ProcessPoolExecutor)")
    print("  Config: 2 modes (M1+M2), 500 MC samples, 5 km per drone @ 1 km spacing")
    print("=" * 90)

    config, dem, pop, infra, state = setup(n_mc=500, all_modes=False)

    for n_drones in [5, 10, 20, 50]:
        t_seq, s_seq = benchmark_batch(state, n_drones, False)
        t_par, s_par = benchmark_batch(state, n_drones, True)
        speedup = t_seq / t_par if t_par > 0 else 0
        print(f"  {n_drones:3d} drones | seq: {fmt(t_seq, s_seq)} | par: {fmt(t_par, s_par)} | {speedup:.1f}x")

    print()
    print("=" * 90)
    print("CONCLUSION")
    print("=" * 90)
    print("  Per-point ThreadPool: GIL overhead negates parallelism. Default point_workers=1.")
    print("  Batch ProcessPool: Near-linear speedup. Default batch_workers=cpu_count.")
    print()


if __name__ == "__main__":
    main()
