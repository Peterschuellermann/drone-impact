from __future__ import annotations

import numpy as np
from numba import njit, prange

from droneimpact.config import PhysicsConfig

_G = 9.81


@njit(parallel=True, cache=True)
def _m1_kernel(
    heading_samples: np.ndarray,
    glide_samples: np.ndarray,
    speed_samples: np.ndarray,
    altitude_agl_m: float,
) -> np.ndarray:
    n = heading_samples.shape[0]
    result = np.empty((n, 2), dtype=np.float64)
    for i in prange(n):
        glide = max(glide_samples[i], 0.5)
        speed = max(speed_samples[i], 0.0)
        energy_height = altitude_agl_m + (speed * speed) / (2.0 * _G)
        range_m = energy_height * glide
        hdg_rad = np.radians(heading_samples[i])
        result[i, 0] = range_m * np.sin(hdg_rad)
        result[i, 1] = range_m * np.cos(hdg_rad)
    return result


def simulate_m1(
    altitude_agl_m: float,
    heading_deg: float,
    speed_m_s: float,
    n_samples: int,
    config: PhysicsConfig,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """
    Monte Carlo simulation of Mode M1 (propulsion loss) impact distribution.

    The drone loses propulsion and glides unpowered. Uses the energy-height
    method: kinetic energy converts to additional altitude equivalent, extending
    glide range at higher speeds.

    Returns (N, 2) ENU array [east_m, north_m] relative to intercept position.
    """
    if rng is None:
        rng = np.random.default_rng()

    heading_samples = rng.normal(heading_deg, config.m1_sigma_heading_deg, n_samples)
    glide_samples = rng.normal(
        config.shahed136.glide_ratio, config.m1_sigma_glide_ratio, n_samples
    )
    speed_samples = rng.normal(speed_m_s, config.m1_sigma_speed_m_s, n_samples)

    return _m1_kernel(heading_samples, glide_samples, speed_samples, altitude_agl_m)
