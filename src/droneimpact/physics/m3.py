from __future__ import annotations

import numpy as np

from droneimpact.config import PhysicsConfig

_RHO = 1.225  # kg/m³ sea-level air density
_G = 9.81     # m/s²


def simulate_m3(
    altitude_agl_m: float,
    heading_deg: float,
    speed_m_s: float,
    n_samples: int,
    config: PhysicsConfig,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """
    Monte Carlo simulation of Mode M3 (break apart) impact distribution.

    Structural failure causes the drone to tumble ballistically with high drag.
    Fragment mass fraction, drag coefficient, initial heading, speed, and pitch
    are all stochastic inputs.

    Returns (N, 2) ENU array [east_m, north_m] relative to intercept position.
    """
    if rng is None:
        rng = np.random.default_rng()

    shahed = config.shahed136
    dt = config.m3_dt_s

    # Stochastic initial conditions — all (N,) arrays
    heading_samples = rng.normal(heading_deg, config.m3_sigma_heading_deg, n_samples)
    speed_samples = np.maximum(
        rng.normal(speed_m_s, config.m3_sigma_speed_m_s, n_samples), 0.0
    )
    pitch_deg = rng.uniform(-20.0, 20.0, n_samples)
    cd_samples = np.maximum(
        rng.normal(shahed.drag_coeff_tumbling, config.m3_sigma_cd, n_samples), 0.1
    )
    mass_frac = rng.uniform(0.1, 1.0, n_samples)
    mass_samples = shahed.mass_kg * mass_frac

    # Initial velocity components
    hdg_rad = np.radians(heading_samples)
    pitch_rad = np.radians(pitch_deg)
    cos_pitch = np.cos(pitch_rad)
    sin_pitch = np.sin(pitch_rad)

    v_east = speed_samples * cos_pitch * np.sin(hdg_rad)
    v_north = speed_samples * cos_pitch * np.cos(hdg_rad)
    v_vert = speed_samples * sin_pitch

    pos_east = np.zeros(n_samples)
    pos_north = np.zeros(n_samples)
    alt = np.full(n_samples, altitude_agl_m, dtype=np.float64)
    alive = alt > 0

    half_rho_A = 0.5 * _RHO * shahed.reference_area_m2
    drag_per_mass = half_rho_A * cd_samples / mass_samples  # (N,) coefficient

    for _ in range(config.m3_max_steps):
        if not np.any(alive):
            break

        spd = np.sqrt(v_east ** 2 + v_north ** 2 + v_vert ** 2)

        a_drag = drag_per_mass * spd  # per-axis drag acceleration magnitude / velocity component

        v_east -= alive * a_drag * v_east * dt
        v_north -= alive * a_drag * v_north * dt
        v_vert = v_vert + alive * (-_G - a_drag * v_vert) * dt

        pos_east += alive * v_east * dt
        pos_north += alive * v_north * dt
        alt += alive * v_vert * dt
        alive = alive & (alt > 0)

    return np.stack([pos_east, pos_north], axis=1)
