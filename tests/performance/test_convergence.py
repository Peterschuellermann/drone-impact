"""
Monte Carlo convergence tests — run in normal CI (no --run-perf flag needed).
Uses synthetic in-memory population; no real data files required.
"""
import numpy as np
import pytest

from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.coords import enu_to_wgs84_batch
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex
from droneimpact.physics.m1 import simulate_m1
from tests.fixtures.population_small import make_test_population

ORIGIN = (48.0, 31.0)


@pytest.fixture(scope="module")
def casualty_engine_convergence(config):
    cells = make_test_population(*ORIGIN, pop_density=5000.0, radius_cells=10)
    pop = PopulationIndex.from_dict(cells)
    infra = InfrastructureIndex.from_features([], config.casualty.infrastructure)
    return CasualtyEngine(pop, infra, config.casualty)


def _compute_expected_casualties(n: int, config, casualty_engine) -> float:
    rng = np.random.default_rng(42)
    enu = simulate_m1(400.0, 0.0, 51.4, n, config.physics, rng=rng)
    wgs84 = enu_to_wgs84_batch(enu, *ORIGIN)
    pts = np.column_stack([wgs84[:, 0], wgs84[:, 1]])
    return casualty_engine.compute(pts)


def test_monte_carlo_convergence(config, casualty_engine_convergence):
    results = {
        n: _compute_expected_casualties(n, config, casualty_engine_convergence)
        for n in [100, 1_000, 10_000]
    }

    # N=10k and N=1k should agree within 15%
    baseline = results[10_000]
    mid = results[1_000]
    if baseline > 1e-9:
        rel_diff = abs(baseline - mid) / baseline
        assert rel_diff < 0.15, (
            f"Monte Carlo not converging: N=1k gave {mid:.4f}, N=10k gave {baseline:.4f} "
            f"(rel diff {rel_diff:.1%})"
        )

    # All values should be non-negative
    for n, val in results.items():
        assert val >= 0.0, f"Negative E[casualties] at N={n}: {val}"

    print(
        f"\nConvergence: N=100={results[100]:.4f}, "
        f"N=1k={results[1_000]:.4f}, N=10k={results[10_000]:.4f}"
    )


def test_m1_distribution_non_degenerate(config):
    """Impact distribution has non-zero spread (not all points at same location)."""
    enu = simulate_m1(400.0, 45.0, 51.4, 1000, config.physics, rng=np.random.default_rng(7))
    spread = np.std(np.sqrt((enu ** 2).sum(axis=1)))
    assert spread > 10.0, f"M1 spread too small: {spread:.1f} m (expected > 10 m)"


def test_zero_altitude_near_zero_range(config):
    """Near-zero AGL altitude and zero speed → near-zero impact range for M1."""
    cfg = config.physics.model_copy(update={"m1_sigma_speed_m_s": 0.0})
    enu = simulate_m1(1.0, 0.0, 0.0, 1000, cfg, rng=np.random.default_rng(0))
    mean_range = float(np.sqrt((enu ** 2).sum(axis=1)).mean())
    expected_max = 1.0 * config.physics.shahed136.glide_ratio * 3
    assert mean_range < expected_max, (
        f"M1 range at 1m AGL too large: {mean_range:.1f} m (expected < {expected_max:.1f} m)"
    )
