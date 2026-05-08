from __future__ import annotations

import math

import numpy as np

from droneimpact.coords import enu_to_wgs84_batch
from droneimpact.physics.types import StateVector, TrajectoryPoint


def discretise_trajectory(
    sv: StateVector,
    spacing_m: float,
    max_range_m: float,
) -> list[TrajectoryPoint]:
    n_points = int(math.ceil(max_range_m / spacing_m)) + 1
    distances = np.arange(n_points, dtype=np.float64) * spacing_m  # (N,)

    # Heading: compass degrees (CW from north) → ENU angle (CCW from east)
    enu_angle_rad = math.radians(90.0 - sv.heading_deg)
    east = distances * math.cos(enu_angle_rad)   # (N,)
    north = distances * math.sin(enu_angle_rad)  # (N,)

    enu = np.stack([east, north], axis=1)  # (N, 2)
    wgs84 = enu_to_wgs84_batch(enu, sv.lat, sv.lon)  # (N, 2) [lat, lon]

    return [
        TrajectoryPoint(
            index=i,
            lat=float(wgs84[i, 0]),
            lon=float(wgs84[i, 1]),
            altitude_m=sv.altitude_m,
            distance_from_start_m=float(distances[i]),
            heading_deg=sv.heading_deg,
            speed_m_s=sv.speed_m_s,
        )
        for i in range(n_points)
    ]
