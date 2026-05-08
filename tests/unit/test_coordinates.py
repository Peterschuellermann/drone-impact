import math

import numpy as np
import pytest

from droneimpact.coords import (
    enu_to_wgs84,
    enu_to_wgs84_batch,
    wgs84_to_enu,
    wgs84_to_enu_batch,
)
from droneimpact.physics.trajectory import discretise_trajectory
from droneimpact.physics.types import StateVector

ORIGIN = (48.3794, 31.1656)  # central Ukraine


@pytest.mark.parametrize("heading,dist", [
    (0, 1000),
    (90, 50000),
    (180, 100000),
    (270, 500000),
])
def test_enu_wgs84_roundtrip(heading, dist):
    east = dist * math.sin(math.radians(heading))
    north = dist * math.cos(math.radians(heading))
    lat, lon = enu_to_wgs84(east, north, *ORIGIN)
    e2, n2 = wgs84_to_enu(lat, lon, *ORIGIN)
    assert abs(e2 - east) < 0.01
    assert abs(n2 - north) < 0.01


def test_north_heading_moves_north():
    lat, lon = enu_to_wgs84(0, 1000, *ORIGIN)
    assert lat > ORIGIN[0]
    assert abs(lon - ORIGIN[1]) < 0.001


def test_east_heading_moves_east():
    lat, lon = enu_to_wgs84(1000, 0, *ORIGIN)
    assert lon > ORIGIN[1]
    assert abs(lat - ORIGIN[0]) < 0.001


def test_south_heading_moves_south():
    lat, lon = enu_to_wgs84(0, -1000, *ORIGIN)
    assert lat < ORIGIN[0]


def test_west_heading_moves_west():
    lat, lon = enu_to_wgs84(-1000, 0, *ORIGIN)
    assert lon < ORIGIN[1]


def test_batch_matches_scalar():
    lats = np.array([48.1, 48.2, 47.9])
    lons = np.array([31.1, 30.9, 31.2])
    batch = wgs84_to_enu_batch(lats, lons, *ORIGIN)
    for i in range(len(lats)):
        scalar = wgs84_to_enu(lats[i], lons[i], *ORIGIN)
        assert abs(batch[i, 0] - scalar[0]) < 0.001
        assert abs(batch[i, 1] - scalar[1]) < 0.001


def test_enu_to_wgs84_batch_matches_scalar():
    east_north = np.array([[500.0, 300.0], [-200.0, 1000.0], [0.0, 0.0]])
    batch = enu_to_wgs84_batch(east_north, *ORIGIN)
    for i in range(len(east_north)):
        scalar = enu_to_wgs84(east_north[i, 0], east_north[i, 1], *ORIGIN)
        assert abs(batch[i, 0] - scalar[0]) < 1e-8
        assert abs(batch[i, 1] - scalar[1]) < 1e-8


def test_trajectory_spacing():
    sv = StateVector(lat=48.0, lon=31.0, altitude_m=400, heading_deg=0, speed_m_s=51.4)
    points = discretise_trajectory(sv, spacing_m=500, max_range_m=5000)
    assert len(points) == 11  # 0, 500, ..., 5000
    for i, p in enumerate(points):
        assert abs(p.distance_from_start_m - i * 500) < 0.1


def test_trajectory_heading_north():
    sv = StateVector(lat=48.0, lon=31.0, altitude_m=400, heading_deg=0, speed_m_s=51.4)
    points = discretise_trajectory(sv, spacing_m=1000, max_range_m=3000)
    for p in points[1:]:
        assert p.lat > 48.0
        assert abs(p.lon - 31.0) < 0.01


def test_trajectory_heading_east():
    sv = StateVector(lat=48.0, lon=31.0, altitude_m=400, heading_deg=90, speed_m_s=51.4)
    points = discretise_trajectory(sv, spacing_m=1000, max_range_m=3000)
    for p in points[1:]:
        assert p.lon > 31.0
        assert abs(p.lat - 48.0) < 0.01


def test_trajectory_altitude_constant():
    sv = StateVector(lat=48.0, lon=31.0, altitude_m=350, heading_deg=45, speed_m_s=51.4)
    points = discretise_trajectory(sv, spacing_m=1000, max_range_m=5000)
    for p in points:
        assert p.altitude_m == 350.0


def test_trajectory_first_point_at_origin():
    sv = StateVector(lat=48.0, lon=31.0, altitude_m=400, heading_deg=270, speed_m_s=51.4)
    points = discretise_trajectory(sv, spacing_m=500, max_range_m=2000)
    assert points[0].lat == pytest.approx(48.0, abs=1e-6)
    assert points[0].lon == pytest.approx(31.0, abs=1e-6)
    assert points[0].distance_from_start_m == 0.0


def test_trajectory_indices_sequential():
    sv = StateVector(lat=48.0, lon=31.0, altitude_m=400, heading_deg=0, speed_m_s=51.4)
    points = discretise_trajectory(sv, spacing_m=1000, max_range_m=5000)
    for i, p in enumerate(points):
        assert p.index == i
