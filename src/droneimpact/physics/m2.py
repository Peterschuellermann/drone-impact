from __future__ import annotations

import numpy as np

from droneimpact.config import PhysicsConfig


def simulate_m2(
    altitude_agl_m: float,
    heading_deg: float,
    speed_m_s: float,
    n_samples: int,
    config: PhysicsConfig,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """
    Monte Carlo simulation of Mode M2 (loss of control) impact distribution.

    The drone engine keeps running but guidance fails. Heading evolves as a
    Brownian motion while the drone descends at a fixed rate. This produces
    the widest debris footprint of the three intercept modes.

    Returns (N, 2) ENU array [east_m, north_m] relative to intercept position.
    """
    if rng is None:
        rng = np.random.default_rng()

    dt = config.m2_dt_s
    n_steps = int(config.m2_max_time_s / dt)
    sigma_turn_rad = np.radians(config.m2_sigma_turn_deg_per_s) * np.sqrt(dt)
    sigma_init_rad = np.radians(config.m2_sigma_init_deg)
    descent_rate = config.m2_descent_rate_m_s

    # Initial conditions — all (N,) arrays
    hdg = np.radians(
        rng.normal(heading_deg, config.m2_sigma_init_deg, n_samples)
    )
    pos = np.zeros((n_samples, 2))
    alt = np.full(n_samples, altitude_agl_m, dtype=np.float64)
    alive = alt > 0

    for _ in range(n_steps):
        if not np.any(alive):
            break

        dhdg = rng.normal(0.0, sigma_turn_rad, n_samples)
        hdg += dhdg

        pos[:, 0] += alive * speed_m_s * np.sin(hdg) * dt
        pos[:, 1] += alive * speed_m_s * np.cos(hdg) * dt
        alt -= alive * descent_rate * dt
        alive = alive & (alt > 0)

    return pos.copy()
