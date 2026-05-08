import numpy as np
import pytest

from droneimpact.scoring.ellipse import compute_cep, compute_impact_ellipse


def test_cep_zero_variance():
    points = np.zeros((1000, 2))
    assert compute_cep(points) == 0.0


def test_cep_positive_spread():
    rng = np.random.default_rng(0)
    points = rng.normal(0, 100, (1000, 2))
    assert compute_cep(points) > 0.0


def test_cep_50_percent_within_radius():
    rng = np.random.default_rng(1)
    points = rng.normal(0, 100, (5000, 2))
    cep = compute_cep(points)
    ranges = np.sqrt((points ** 2).sum(axis=1))
    fraction_inside = (ranges <= cep).mean()
    assert 0.45 <= fraction_inside <= 0.55


def test_ellipse_circular_distribution():
    rng = np.random.default_rng(0)
    points = rng.normal(0, 100, (5000, 2))
    ellipse = compute_impact_ellipse(points, 48.0, 31.0)
    ratio = ellipse.semi_major_m / ellipse.semi_minor_m
    assert 0.5 < ratio < 3.0
    assert ellipse.semi_major_m > 0
    assert ellipse.semi_minor_m > 0


def test_ellipse_elongated_north_south():
    rng = np.random.default_rng(2)
    east = rng.normal(0, 50, 5000)
    north = rng.normal(0, 500, 5000)
    points = np.stack([east, north], axis=1)
    ellipse = compute_impact_ellipse(points, 48.0, 31.0)
    assert ellipse.semi_major_m > ellipse.semi_minor_m * 3


def test_ellipse_centre_near_origin():
    points = np.random.default_rng(3).normal(0, 100, (1000, 2))
    ellipse = compute_impact_ellipse(points, 48.0, 31.0)
    # Centre should be near the WGS84 origin (48.0, 31.0) for zero-mean points
    assert abs(ellipse.centre_lat - 48.0) < 0.01
    assert abs(ellipse.centre_lon - 31.0) < 0.01


def test_ellipse_orientation_in_range():
    points = np.random.default_rng(4).normal(0, 100, (1000, 2))
    ellipse = compute_impact_ellipse(points, 48.0, 31.0)
    assert 0.0 <= ellipse.orientation_deg < 360.0


def test_ellipse_single_point():
    points = np.array([[100.0, 200.0]])
    ellipse = compute_impact_ellipse(points, 48.0, 31.0)
    assert ellipse.semi_major_m == 0.0
    assert ellipse.semi_minor_m == 0.0


def test_ellipse_all_identical_points():
    points = np.full((500, 2), 50.0)
    ellipse = compute_impact_ellipse(points, 48.0, 31.0)
    assert ellipse.semi_major_m == 0.0
    assert ellipse.semi_minor_m == 0.0
