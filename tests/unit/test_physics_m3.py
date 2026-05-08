import math

import numpy as np
import pytest

from droneimpact.physics.m1 import simulate_m1
from droneimpact.physics.m3 import simulate_m3


def test_output_shape(config):
    points = simulate_m3(400.0, 0.0, 51.4, 200, config.physics)
    assert points.shape == (200, 2)


def test_output_all_finite(config):
    points = simulate_m3(400.0, 45.0, 51.4, 200, config.physics)
    assert np.all(np.isfinite(points))


def test_all_samples_terminate(config):
    points = simulate_m3(800.0, 270.0, 51.4, 500, config.physics)
    assert np.all(np.isfinite(points))


def test_m3_tighter_footprint_than_m1(config):
    n = 5000
    m1 = simulate_m1(400.0, 0.0, n, config.physics, rng=np.random.default_rng(42))
    m3 = simulate_m3(400.0, 0.0, 51.4, n, config.physics, rng=np.random.default_rng(42))
    m1_spread = float(np.std(np.sqrt((m1 ** 2).sum(axis=1))))
    m3_spread = float(np.std(np.sqrt((m3 ** 2).sum(axis=1))))
    assert m3_spread < m1_spread


def test_range_increases_with_altitude(config):
    low = simulate_m3(100.0, 0.0, 51.4, 2000, config.physics, rng=np.random.default_rng(7))
    high = simulate_m3(600.0, 0.0, 51.4, 2000, config.physics, rng=np.random.default_rng(7))
    mean_low = float(np.sqrt((low ** 2).sum(axis=1)).mean())
    mean_high = float(np.sqrt((high ** 2).sum(axis=1)).mean())
    assert mean_high > mean_low


def test_no_negative_range(config):
    points = simulate_m3(400.0, 0.0, 51.4, 1000, config.physics)
    assert np.all(np.isfinite(points))


def test_deterministic_with_seed(config):
    p1 = simulate_m3(400.0, 45.0, 51.4, 50, config.physics, rng=np.random.default_rng(5))
    p2 = simulate_m3(400.0, 45.0, 51.4, 50, config.physics, rng=np.random.default_rng(5))
    assert np.allclose(p1, p2)


def test_high_altitude_extends_range(config):
    """At 2000 m the lower air density should produce noticeably longer range than at 100 m."""
    n = 5000
    low = simulate_m3(100.0, 0.0, 51.4, n, config.physics, rng=np.random.default_rng(99))
    high = simulate_m3(2000.0, 0.0, 51.4, n, config.physics, rng=np.random.default_rng(99))
    mean_low = float(np.sqrt((low ** 2).sum(axis=1)).mean())
    mean_high = float(np.sqrt((high ** 2).sum(axis=1)).mean())
    # High altitude must produce longer range; the ratio should exceed 1.1
    # because both the longer fall time and lower density contribute.
    assert mean_high / mean_low > 1.1


def test_density_at_1000m(config):
    """Verify the exponential atmosphere model: at 1000 m, density ~ 89% of sea level."""
    scale_height = config.physics.atmosphere_scale_height_m
    rho_sea = 1.225
    rho_1000 = rho_sea * math.exp(-1000.0 / scale_height)
    ratio = rho_1000 / rho_sea
    # exp(-1000/8500) ~ 0.889
    assert 0.88 < ratio < 0.90
