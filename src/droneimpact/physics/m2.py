from __future__ import annotations

import numpy as np
from numba import njit, prange

from droneimpact.config import PhysicsConfig

_RHO = 1.225  # kg/m^3 sea-level air density
_G = 9.81     # m/s^2


@njit(parallel=True, cache=True)
def _m2_kernel(
    hdg: np.ndarray,
    t_power: np.ndarray,
    dhdg_all: np.ndarray,
    altitude_agl_m: float,
    speed_m_s: float,
    descent_rate: float,
    dt: float,
    n_steps: int,
    half_A_Cd_over_m: float,
    scale_height: float,
    rho_0: float,
    g: float,
) -> np.ndarray:
    n = hdg.shape[0]
    result = np.empty((n, 2), dtype=np.float64)

    for i in prange(n):
        pos_e = 0.0
        pos_n = 0.0
        alt = altitude_agl_m
        h = hdg[i]
        t_elapsed = 0.0
        powered = True

        v_e = 0.0
        v_n = 0.0
        v_v = 0.0

        for t in range(n_steps):
            if alt <= 0.0:
                break

            t_elapsed += dt

            if powered and t_elapsed > t_power[i]:
                v_e = speed_m_s * np.sin(h)
                v_n = speed_m_s * np.cos(h)
                v_v = -descent_rate
                powered = False

            if powered:
                h += dhdg_all[t, i]
                pos_e += speed_m_s * np.sin(h) * dt
                pos_n += speed_m_s * np.cos(h) * dt
                alt -= descent_rate * dt
            else:
                rho = rho_0 * np.exp(-alt / scale_height)
                spd = np.sqrt(v_e * v_e + v_n * v_n + v_v * v_v)
                a_drag = half_A_Cd_over_m * rho * spd

                v_e -= a_drag * v_e * dt
                v_n -= a_drag * v_n * dt
                v_v += (-g - a_drag * v_v) * dt

                pos_e += v_e * dt
                pos_n += v_n * dt
                alt += v_v * dt

        result[i, 0] = pos_e
        result[i, 1] = pos_n

    return result


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

    Two-phase model:
      Phase 1 (powered): engine running, heading drifts as Brownian motion,
        constant speed and descent rate. Duration T_power ~ Uniform(min, max).
      Phase 2 (ballistic tumble): engine off, gravity + aerodynamic drag
        decelerate the drone until ground impact.

    Returns (N, 2) ENU array [east_m, north_m] relative to intercept position.
    """
    if rng is None:
        rng = np.random.default_rng()

    dt = config.m2_dt_s
    n_steps = int(config.m2_max_time_s / dt)
    sigma_turn_rad = np.radians(config.m2_sigma_turn_deg_per_s) * np.sqrt(dt)
    descent_rate = config.m2_descent_rate_m_s

    shahed = config.shahed136

    t_power = rng.uniform(
        config.m2_power_duration_min_s,
        config.m2_power_duration_max_s,
        n_samples,
    )

    half_A_Cd_over_m = (
        0.5 * shahed.reference_area_m2
        * shahed.drag_coeff_tumbling / shahed.mass_kg
    )
    scale_height = config.atmosphere_scale_height_m

    hdg = np.radians(
        rng.normal(heading_deg, config.m2_sigma_init_deg, n_samples)
    )

    dhdg_all = rng.normal(0.0, sigma_turn_rad, (n_steps, n_samples))

    return _m2_kernel(
        hdg, t_power, dhdg_all,
        altitude_agl_m, speed_m_s, descent_rate, dt, n_steps,
        half_A_Cd_over_m, scale_height, _RHO, _G,
    )
