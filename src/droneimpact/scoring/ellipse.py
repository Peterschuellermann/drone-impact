from __future__ import annotations

import math

import numpy as np
from shapely.geometry import MultiPoint

from droneimpact.coords import enu_to_wgs84
from droneimpact.scoring.types import ImpactEllipse

# Chi-squared 90th percentile with df=2
_CHI2_90 = 4.6052


def compute_cep(enu_points: np.ndarray) -> float:
    """Radius containing 50% of impact points (Circular Error Probable)."""
    centroid = enu_points.mean(axis=0)
    ranges = np.sqrt(((enu_points - centroid) ** 2).sum(axis=1))
    return float(np.percentile(ranges, 50))


def compute_impact_ellipse(
    enu_points: np.ndarray,
    origin_lat: float,
    origin_lon: float,
) -> ImpactEllipse:
    """90% confidence ellipse for the ENU impact distribution."""
    if enu_points.shape[0] < 2 or np.allclose(enu_points, enu_points[0]):
        mean_enu = enu_points.mean(axis=0)
        centre_lat, centre_lon = enu_to_wgs84(
            float(mean_enu[0]), float(mean_enu[1]), origin_lat, origin_lon
        )
        return ImpactEllipse(
            centre_lat=centre_lat,
            centre_lon=centre_lon,
            semi_major_m=0.0,
            semi_minor_m=0.0,
            orientation_deg=0.0,
        )

    cov = np.cov(enu_points.T)  # (2, 2)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)

    # Ensure eigenvalues are non-negative (numerical safety)
    eigenvalues = np.maximum(eigenvalues, 0.0)

    semi_major = math.sqrt(eigenvalues[-1] * _CHI2_90)
    semi_minor = math.sqrt(eigenvalues[0] * _CHI2_90)

    # Orientation: angle of major eigenvector from north (clockwise, degrees)
    major_vec = eigenvectors[:, -1]  # [east, north] components
    orientation_deg = math.degrees(math.atan2(major_vec[0], major_vec[1])) % 360

    # Centre is the mean of the distribution, converted to WGS84
    mean_enu = enu_points.mean(axis=0)
    centre_lat, centre_lon = enu_to_wgs84(
        float(mean_enu[0]), float(mean_enu[1]), origin_lat, origin_lon
    )

    return ImpactEllipse(
        centre_lat=centre_lat,
        centre_lon=centre_lon,
        semi_major_m=semi_major,
        semi_minor_m=semi_minor,
        orientation_deg=orientation_deg,
    )


def ellipse_boundary_points(
    ellipse: ImpactEllipse,
    n_points: int = 72,
) -> list[tuple[float, float]]:
    """Sample points on the boundary of a 90% confidence ellipse.

    Returns a list of (lon, lat) tuples suitable for GeoJSON coordinates.
    The ellipse orientation is measured clockwise from north.
    """
    if ellipse.semi_major_m <= 0 or ellipse.semi_minor_m <= 0:
        return [(ellipse.centre_lon, ellipse.centre_lat)] * n_points

    lat_per_m = 1.0 / 111_320.0
    lon_per_m = 1.0 / (111_320.0 * math.cos(math.radians(ellipse.centre_lat)))

    orient_rad = math.radians(ellipse.orientation_deg)

    points: list[tuple[float, float]] = []
    for i in range(n_points):
        angle = 2.0 * math.pi * i / n_points
        # Parametric ellipse in local ENU frame (east, north)
        e = ellipse.semi_major_m * math.cos(angle)
        n = ellipse.semi_minor_m * math.sin(angle)
        # Rotate by orientation (clockwise from north -> standard math rotation)
        # orientation_deg is angle of major axis from north, clockwise
        # Major axis direction in ENU: east = sin(orient), north = cos(orient)
        re = e * math.sin(orient_rad) + n * math.cos(orient_rad)
        rn = e * math.cos(orient_rad) - n * math.sin(orient_rad)
        lat = ellipse.centre_lat + rn * lat_per_m
        lon = ellipse.centre_lon + re * lon_per_m
        points.append((lon, lat))

    return points


def compute_combined_danger_zone(ellipses: list[ImpactEllipse]) -> dict:
    """Compute GeoJSON polygon from convex hull of all ellipse boundaries.

    Samples 72 points on each ellipse boundary, computes the convex hull
    using shapely, and returns a GeoJSON Polygon dict.
    """
    all_points: list[tuple[float, float]] = []
    for ell in ellipses:
        all_points.extend(ellipse_boundary_points(ell, n_points=72))

    if len(all_points) < 3:
        return {"type": "Polygon", "coordinates": []}

    mp = MultiPoint(all_points)
    hull = mp.convex_hull

    if hull.geom_type == "Point":
        coord = list(hull.coords[0])
        return {"type": "Polygon", "coordinates": [[coord, coord, coord, coord]]}
    elif hull.geom_type == "LineString":
        coords = [list(c) for c in hull.coords]
        coords.append(coords[0])
        return {"type": "Polygon", "coordinates": [coords]}

    coords = [list(c) for c in hull.exterior.coords]
    return {"type": "Polygon", "coordinates": [coords]}
