import numpy as np
import pytest
from shapely.geometry import Point, shape

from droneimpact.scoring.ellipse import (
    compute_combined_danger_zone,
    compute_impact_ellipse,
    ellipse_boundary_points,
)
from droneimpact.scoring.types import ImpactEllipse


def _make_ellipse(
    centre_lat: float = 48.0,
    centre_lon: float = 31.0,
    semi_major_m: float = 1000.0,
    semi_minor_m: float = 500.0,
    orientation_deg: float = 45.0,
) -> ImpactEllipse:
    return ImpactEllipse(
        centre_lat=centre_lat,
        centre_lon=centre_lon,
        semi_major_m=semi_major_m,
        semi_minor_m=semi_minor_m,
        orientation_deg=orientation_deg,
    )


# --- ellipse_boundary_points tests ---


def test_ellipse_boundary_points_count():
    """Verify default 72 points returned."""
    ellipse = _make_ellipse()
    pts = ellipse_boundary_points(ellipse)
    assert len(pts) == 72


def test_ellipse_boundary_points_custom_count():
    """Verify custom point count."""
    ellipse = _make_ellipse()
    pts = ellipse_boundary_points(ellipse, n_points=36)
    assert len(pts) == 36


def test_ellipse_boundary_points_are_lon_lat_tuples():
    """Each point is a (lon, lat) tuple."""
    ellipse = _make_ellipse()
    pts = ellipse_boundary_points(ellipse)
    for lon, lat in pts:
        assert isinstance(lon, float)
        assert isinstance(lat, float)
        assert -180 <= lon <= 180
        assert -90 <= lat <= 90


def test_ellipse_boundary_points_near_centre():
    """All boundary points should be within a reasonable distance of the centre."""
    ellipse = _make_ellipse(semi_major_m=1000.0, semi_minor_m=500.0)
    pts = ellipse_boundary_points(ellipse)
    for lon, lat in pts:
        # Rough check: within ~0.02 degrees (~2 km) of centre
        assert abs(lat - ellipse.centre_lat) < 0.02
        assert abs(lon - ellipse.centre_lon) < 0.03


def test_ellipse_boundary_points_degenerate():
    """Zero-size ellipse returns n copies of the centre."""
    ellipse = _make_ellipse(semi_major_m=0.0, semi_minor_m=0.0)
    pts = ellipse_boundary_points(ellipse, n_points=10)
    assert len(pts) == 10
    for lon, lat in pts:
        assert lon == ellipse.centre_lon
        assert lat == ellipse.centre_lat


# --- compute_combined_danger_zone tests ---


def test_combined_danger_zone_valid_polygon():
    """Verify the danger zone is a valid GeoJSON polygon."""
    ellipses = [
        _make_ellipse(orientation_deg=0),
        _make_ellipse(orientation_deg=120),
        _make_ellipse(orientation_deg=240),
    ]
    result = compute_combined_danger_zone(ellipses)
    assert result["type"] == "Polygon"
    assert "coordinates" in result
    coords = result["coordinates"]
    assert len(coords) == 1  # single ring
    assert len(coords[0]) >= 4  # at least 3 points + closing


def test_combined_danger_zone_contains_ellipse_centres():
    """The convex hull should contain all ellipse centres."""
    e1 = _make_ellipse(centre_lat=48.0, centre_lon=31.0)
    e2 = _make_ellipse(centre_lat=48.01, centre_lon=31.01)
    e3 = _make_ellipse(centre_lat=47.99, centre_lon=30.99)
    ellipses = [e1, e2, e3]
    result = compute_combined_danger_zone(ellipses)

    polygon = shape(result)
    for ell in ellipses:
        pt = Point(ell.centre_lon, ell.centre_lat)
        assert polygon.contains(pt) or polygon.touches(pt), (
            f"Danger zone does not contain centre ({ell.centre_lat}, {ell.centre_lon})"
        )


def test_combined_danger_zone_single_ellipse():
    """A single ellipse should produce a valid polygon."""
    ellipse = _make_ellipse()
    result = compute_combined_danger_zone([ellipse])
    assert result["type"] == "Polygon"
    coords = result["coordinates"]
    assert len(coords) == 1
    assert len(coords[0]) >= 4


def test_combined_danger_zone_from_real_distributions():
    """Use actual simulated distributions to verify end-to-end."""
    rng = np.random.default_rng(42)

    e1 = compute_impact_ellipse(rng.normal(0, 800, (500, 2)), 48.0, 31.0)
    e2 = compute_impact_ellipse(rng.normal(0, 1500, (500, 2)), 48.0, 31.0)
    e3 = compute_impact_ellipse(rng.normal(0, 300, (500, 2)), 48.0, 31.0)

    result = compute_combined_danger_zone([e1, e2, e3])
    assert result["type"] == "Polygon"
    polygon = shape(result)
    assert polygon.is_valid
    assert polygon.area > 0
