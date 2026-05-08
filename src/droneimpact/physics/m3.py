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
    spread = config.m3_heading_spread_deg
    heading_samples = rng.uniform(heading_deg - spread, heading_deg + spread, n_samples)
    reduced_speed = speed_m_s * config.m3_speed_reduction_factor
    speed_samples = np.maximum(
        rng.normal(reduced_speed, config.m3_sigma_speed_m_s, n_samples), 0.0
    )
    pitch_range = config.m3_pitch_range_deg
    pitch_deg = rng.uniform(-pitch_range, pitch_range, n_samples)
    cd_samples = np.maximum(
        rng.normal(shahed.drag_coeff_tumbling, config.m3_sigma_cd, n_samples), 0.1
    )
    mass_samples = np.maximum(
        rng.normal(shahed.fragment_mass_mean_kg, shahed.fragment_mass_std_kg, n_samples),
        5.0,
    )

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

    # Pre-factor that is constant across timesteps; density is applied per step.
    half_A_cd_over_m = 0.5 * shahed.fragment_reference_area_m2 * cd_samples / mass_samples
    scale_height = config.atmosphere_scale_height_m

    for _ in range(config.m3_max_steps):
        if not np.any(alive):
            break

        # Altitude-dependent air density: exponential atmosphere model
        rho = _RHO * np.exp(-alt / scale_height)

        spd = np.sqrt(v_east ** 2 + v_north ** 2 + v_vert ** 2)

        a_drag = half_A_cd_over_m * rho * spd

        v_east -= alive * a_drag * v_east * dt
        v_north -= alive * a_drag * v_north * dt
        v_vert = v_vert + alive * (-_G - a_drag * v_vert) * dt

        pos_east += alive * v_east * dt
        pos_north += alive * v_north * dt
        alt += alive * v_vert * dt
        alive = alive & (alt > 0)

    return np.stack([pos_east, pos_north], axis=1)
