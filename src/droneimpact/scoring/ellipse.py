from __future__ import annotations

import math

import numpy as np

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
