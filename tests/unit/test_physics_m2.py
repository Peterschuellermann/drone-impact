import numpy as np
import pytest

from droneimpact.physics.m2 import simulate_m2


def test_output_shape(config):
    points = simulate_m2(400.0, 0.0, 51.4, 100, config.physics)
    assert points.shape == (100, 2)


def test_output_all_finite(config):
    points = simulate_m2(400.0, 45.0, 51.4, 200, config.physics)
    assert np.all(np.isfinite(points))


def test_all_samples_terminate(config):
    points = simulate_m2(50.0, 45.0, 51.4, 200, config.physics)
    assert points.shape == (200, 2)
    assert np.all(np.isfinite(points))


def test_m2_has_meaningful_spread(config):
    """M2 footprint has non-trivial spread from heading drift and ballistic tumble."""
    n = 5000
    m2 = simulate_m2(400.0, 0.0, 51.4, n, config.physics, rng=np.random.default_rng(42))
    m2_std = float(np.std(np.sqrt((m2 ** 2).sum(axis=1))))
    # With 1-10s powered phase + ballistic tumble from 400m, spread should be
    # well above zero (heading drift causes lateral dispersion).
    assert m2_std > 50.0


def test_mean_forward_displacement(config):
    points = simulate_m2(300.0, 0.0, 51.4, 5000, config.physics, rng=np.random.default_rng(7))
    # Northward heading -> mean north displacement should be positive
    assert points[:, 1].mean() > 0


def test_no_immediate_ground_hits(config):
    points = simulate_m2(400.0, 0.0, 51.4, 100, config.physics, rng=np.random.default_rng(1))
    ranges = np.sqrt((points ** 2).sum(axis=1))
    assert np.all(ranges > 1.0)


def test_deterministic_with_seed(config):
    p1 = simulate_m2(400.0, 45.0, 51.4, 50, config.physics, rng=np.random.default_rng(99))
    p2 = simulate_m2(400.0, 45.0, 51.4, 50, config.physics, rng=np.random.default_rng(99))
    assert np.allclose(p1, p2)


def test_m2_mean_range_bounded(config):
    """With powered phase limited to 1-10s, mean range at 400m AGL should be
    well under the old model's ~13km. The two-phase model with coarse dt=1s
    gives a mean range around 5-6km (powered drift + ballistic descent)."""
    n = 5000
    points = simulate_m2(400.0, 0.0, 51.4, n, config.physics, rng=np.random.default_rng(42))
    mean_range = float(np.sqrt((points ** 2).sum(axis=1)).mean())
    assert mean_range < 8000.0


def test_m2_zero_power_resembles_ballistic(config):
    """With T_power forced to 0, M2 should produce a compact ballistic footprint
    similar to a purely ballistic trajectory (no powered flight component)."""
    n = 5000
    cfg_zero_power = config.physics.model_copy(update={
        "m2_power_duration_min_s": 0.0,
        "m2_power_duration_max_s": 0.0,
    })
    points = simulate_m2(
        400.0, 0.0, 51.4, n, cfg_zero_power, rng=np.random.default_rng(42)
    )
    mean_range = float(np.sqrt((points ** 2).sum(axis=1)).mean())
    # With zero powered phase, the drone immediately enters ballistic tumble
    # from ~51 m/s cruise. Range should be modest (under 1500m from 400m AGL).
    assert mean_range < 1500.0
    # Should still have non-trivial range (not all hitting at origin)
    assert mean_range > 10.0


def test_m2_longer_power_gives_larger_range(config):
    """Longer powered phase should produce larger footprint."""
    n = 5000
    cfg_short = config.physics.model_copy(update={
        "m2_power_duration_min_s": 1.0,
        "m2_power_duration_max_s": 1.0,
    })
    cfg_long = config.physics.model_copy(update={
        "m2_power_duration_min_s": 10.0,
        "m2_power_duration_max_s": 10.0,
    })
    short_pts = simulate_m2(
        400.0, 0.0, 51.4, n, cfg_short, rng=np.random.default_rng(42)
    )
    long_pts = simulate_m2(
        400.0, 0.0, 51.4, n, cfg_long, rng=np.random.default_rng(42)
    )
    short_range = float(np.sqrt((short_pts ** 2).sum(axis=1)).mean())
    long_range = float(np.sqrt((long_pts ** 2).sum(axis=1)).mean())
    assert long_range > short_range
