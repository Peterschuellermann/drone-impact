from __future__ import annotations

import numpy as np

from droneimpact.config import PhysicsConfig


def simulate_m1(
    altitude_agl_m: float,
    heading_deg: float,
    n_samples: int,
    config: PhysicsConfig,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """
    Monte Carlo simulation of Mode M1 (propulsion loss) impact distribution.

    The drone loses propulsion and glides unpowered. Stochastic heading deviation
    and glide ratio produce an elliptical footprint elongated along the heading axis.

    Returns (N, 2) ENU array [east_m, north_m] relative to intercept position.
    """
    if rng is None:
        rng = np.random.default_rng()

    heading_samples = rng.normal(heading_deg, config.m1_sigma_heading_deg, n_samples)
    glide_samples = rng.normal(
        config.shahed136.glide_ratio, config.m1_sigma_glide_ratio, n_samples
    )
    glide_samples = np.maximum(glide_samples, 0.5)  # physical floor

    range_samples = altitude_agl_m * glide_samples

    heading_rad = np.radians(heading_samples)
    east = range_samples * np.sin(heading_rad)
    north = range_samples * np.cos(heading_rad)

    return np.stack([east, north], axis=1)
