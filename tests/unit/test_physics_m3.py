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
