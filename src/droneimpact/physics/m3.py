from __future__ import annotations

import numpy as np
from numba import njit, prange

from droneimpact.config import PhysicsConfig

_RHO = 1.225  # kg/m^3 sea-level air density
_G = 9.81     # m/s^2


@njit(parallel=True, cache=True)
def _m3_kernel(
    v_east: np.ndarray,
    v_north: np.ndarray,
    v_vert: np.ndarray,
    half_A_cd_over_m: np.ndarray,
    altitude_agl_m: float,
    dt: float,
    max_steps: int,
    scale_height: float,
    rho_0: float,
    g: float,
) -> np.ndarray:
    n = v_east.shape[0]
    result = np.empty((n, 2), dtype=np.float64)

    for i in prange(n):
        pos_e = 0.0
        pos_n = 0.0
        alt = altitude_agl_m
        ve = v_east[i]
        vn = v_north[i]
        vv = v_vert[i]
        drag_factor = half_A_cd_over_m[i]

        for t in range(max_steps):
            if alt <= 0.0:
                break

            rho = rho_0 * np.exp(-alt / scale_height)
            spd = np.sqrt(ve * ve + vn * vn + vv * vv)
            a_drag = drag_factor * rho * spd

            ve -= a_drag * ve * dt
            vn -= a_drag * vn * dt
            vv += (-g - a_drag * vv) * dt

            pos_e += ve * dt
            pos_n += vn * dt
            alt += vv * dt

        result[i, 0] = pos_e
        result[i, 1] = pos_n

    return result


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

    hdg_rad = np.radians(heading_samples)
    pitch_rad = np.radians(pitch_deg)
    cos_pitch = np.cos(pitch_rad)
    sin_pitch = np.sin(pitch_rad)

    v_east = speed_samples * cos_pitch * np.sin(hdg_rad)
    v_north = speed_samples * cos_pitch * np.cos(hdg_rad)
    v_vert = speed_samples * sin_pitch

    half_A_cd_over_m = 0.5 * shahed.fragment_reference_area_m2 * cd_samples / mass_samples

    return _m3_kernel(
        v_east, v_north, v_vert, half_A_cd_over_m,
        altitude_agl_m, dt, config.m3_max_steps,
        config.atmosphere_scale_height_m, _RHO, _G,
    )
