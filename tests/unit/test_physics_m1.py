import numpy as np
import pytest

from droneimpact.physics.m1 import simulate_m1

CRUISE_SPEED = 51.4
_G = 9.81


def test_output_shape(config):
    points = simulate_m1(400.0, 0.0, CRUISE_SPEED, 500, config.physics)
    assert points.shape == (500, 2)
    assert points.dtype in (np.float64, np.float32)


def test_zero_variance_deterministic(config):
    cfg = config.physics.model_copy(
        update={"m1_sigma_heading_deg": 0.0, "m1_sigma_glide_ratio": 0.0, "m1_sigma_speed_m_s": 0.0}
    )
    points = simulate_m1(400.0, 0.0, CRUISE_SPEED, 500, cfg, rng=np.random.default_rng(42))
    assert np.allclose(points, points[0])
    energy_height = 400.0 + (CRUISE_SPEED ** 2) / (2.0 * _G)
    expected_range = energy_height * cfg.shahed136.glide_ratio
    actual_range = float(np.sqrt((points[0] ** 2).sum()))
    assert abs(actual_range - expected_range) < 0.01


def test_heading_north_impact_north(config):
    points = simulate_m1(400.0, 0.0, CRUISE_SPEED, 10000, config.physics, rng=np.random.default_rng(1))
    assert points[:, 1].mean() > 0
    assert abs(points[:, 0].mean() / points[:, 1].mean()) < 0.15


def test_heading_east_impact_east(config):
    points = simulate_m1(400.0, 90.0, CRUISE_SPEED, 10000, config.physics, rng=np.random.default_rng(2))
    assert points[:, 0].mean() > 0
    assert abs(points[:, 1].mean() / points[:, 0].mean()) < 0.15


def test_heading_south_impact_south(config):
    points = simulate_m1(400.0, 180.0, CRUISE_SPEED, 10000, config.physics, rng=np.random.default_rng(3))
    assert points[:, 1].mean() < 0


def test_mean_range_close_to_energy_height_times_glide(config):
    rng = np.random.default_rng(0)
    altitude = 500.0
    energy_height = altitude + (CRUISE_SPEED ** 2) / (2.0 * _G)
    expected_mean = energy_height * config.physics.shahed136.glide_ratio
    points = simulate_m1(altitude, 45.0, CRUISE_SPEED, 10000, config.physics, rng=rng)
    actual_mean = float(np.sqrt((points ** 2).sum(axis=1)).mean())
    assert abs(actual_mean - expected_mean) / expected_mean < 0.05


def test_no_negative_range(config):
    cfg = config.physics.model_copy(update={"m1_sigma_glide_ratio": 5.0})
    points = simulate_m1(50.0, 0.0, CRUISE_SPEED, 10000, cfg, rng=np.random.default_rng(99))
    ranges = np.sqrt((points ** 2).sum(axis=1))
    assert np.all(ranges >= 0)


def test_output_all_finite(config):
    points = simulate_m1(300.0, 270.0, CRUISE_SPEED, 1000, config.physics)
    assert np.all(np.isfinite(points))


def test_deterministic_with_seed(config):
    p1 = simulate_m1(400.0, 45.0, CRUISE_SPEED, 100, config.physics, rng=np.random.default_rng(7))
    p2 = simulate_m1(400.0, 45.0, CRUISE_SPEED, 100, config.physics, rng=np.random.default_rng(7))
    assert np.allclose(p1, p2)


def test_higher_speed_longer_range(config):
    cfg = config.physics.model_copy(
        update={"m1_sigma_heading_deg": 0.0, "m1_sigma_glide_ratio": 0.0, "m1_sigma_speed_m_s": 0.0}
    )
    slow = simulate_m1(400.0, 0.0, 30.0, 100, cfg, rng=np.random.default_rng(1))
    fast = simulate_m1(400.0, 0.0, 80.0, 100, cfg, rng=np.random.default_rng(1))
    slow_range = float(np.sqrt((slow[0] ** 2).sum()))
    fast_range = float(np.sqrt((fast[0] ** 2).sum()))
    assert fast_range > slow_range


def test_zero_speed_gives_altitude_only_range(config):
    cfg = config.physics.model_copy(
        update={"m1_sigma_heading_deg": 0.0, "m1_sigma_glide_ratio": 0.0, "m1_sigma_speed_m_s": 0.0}
    )
    points = simulate_m1(400.0, 0.0, 0.0, 100, cfg, rng=np.random.default_rng(1))
    expected_range = 400.0 * cfg.shahed136.glide_ratio
    actual_range = float(np.sqrt((points[0] ** 2).sum()))
    assert abs(actual_range - expected_range) < 0.01
