import numpy as np
import pytest

from droneimpact.physics.m1 import simulate_m1
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


def test_m2_wider_footprint_than_m1(config):
    n = 5000
    m1 = simulate_m1(400.0, 0.0, n, config.physics, rng=np.random.default_rng(42))
    m2 = simulate_m2(400.0, 0.0, 51.4, n, config.physics, rng=np.random.default_rng(42))
    m1_std = float(np.std(np.sqrt((m1 ** 2).sum(axis=1))))
    m2_std = float(np.std(np.sqrt((m2 ** 2).sum(axis=1))))
    assert m2_std > 2 * m1_std


def test_mean_forward_displacement(config):
    points = simulate_m2(300.0, 0.0, 51.4, 5000, config.physics, rng=np.random.default_rng(7))
    # Northward heading → mean north displacement should be positive
    assert points[:, 1].mean() > 0


def test_no_immediate_ground_hits(config):
    points = simulate_m2(400.0, 0.0, 51.4, 100, config.physics, rng=np.random.default_rng(1))
    ranges = np.sqrt((points ** 2).sum(axis=1))
    assert np.all(ranges > 1.0)


def test_deterministic_with_seed(config):
    p1 = simulate_m2(400.0, 45.0, 51.4, 50, config.physics, rng=np.random.default_rng(99))
    p2 = simulate_m2(400.0, 45.0, 51.4, 50, config.physics, rng=np.random.default_rng(99))
    assert np.allclose(p1, p2)
