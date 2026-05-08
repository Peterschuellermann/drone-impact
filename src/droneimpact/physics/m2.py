from __future__ import annotations

import numpy as np

from droneimpact.config import PhysicsConfig

_RHO = 1.225  # kg/m^3 sea-level air density
_G = 9.81     # m/s^2


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

    # Per-sample powered-phase duration
    t_power = rng.uniform(
        config.m2_power_duration_min_s,
        config.m2_power_duration_max_s,
        n_samples,
    )

    # Ballistic drag pre-factor (density applied per step)
    half_A_Cd_over_m = (
        0.5 * shahed.reference_area_m2
        * shahed.drag_coeff_tumbling / shahed.mass_kg
    )
    scale_height = config.atmosphere_scale_height_m

    # Initial conditions -- all (N,) arrays
    hdg = np.radians(
        rng.normal(heading_deg, config.m2_sigma_init_deg, n_samples)
    )
    pos_east = np.zeros(n_samples)
    pos_north = np.zeros(n_samples)
    alt = np.full(n_samples, altitude_agl_m, dtype=np.float64)

    # Velocity components for ballistic phase
    v_east = np.zeros(n_samples)
    v_north = np.zeros(n_samples)
    v_vert = np.zeros(n_samples)

    alive = alt > 0
    time_elapsed = np.zeros(n_samples)
    powered = np.ones(n_samples, dtype=bool)

    for _ in range(n_steps):
        if not np.any(alive):
            break

        time_elapsed += alive * dt

        # Determine which samples have exhausted their powered phase
        newly_ballistic = alive & powered & (time_elapsed > t_power)
        if np.any(newly_ballistic):
            # Initialise ballistic velocity from current powered-flight state
            v_east[newly_ballistic] = speed_m_s * np.sin(hdg[newly_ballistic])
            v_north[newly_ballistic] = speed_m_s * np.cos(hdg[newly_ballistic])
            v_vert[newly_ballistic] = -descent_rate
            powered[newly_ballistic] = False

        powered_alive = alive & powered
        ballistic_alive = alive & ~powered

        # --- Phase 1: powered flight ---
        if np.any(powered_alive):
            dhdg = rng.normal(0.0, sigma_turn_rad, n_samples)
            hdg += powered_alive * dhdg

            pos_east += powered_alive * speed_m_s * np.sin(hdg) * dt
            pos_north += powered_alive * speed_m_s * np.cos(hdg) * dt
            alt -= powered_alive * descent_rate * dt

        # --- Phase 2: ballistic tumble ---
        if np.any(ballistic_alive):
            rho = _RHO * np.exp(-alt / scale_height)
            spd = np.sqrt(v_east**2 + v_north**2 + v_vert**2)
            a_drag = half_A_Cd_over_m * rho * spd

            ba = ballistic_alive.astype(np.float64)
            v_east -= ba * a_drag * v_east * dt
            v_north -= ba * a_drag * v_north * dt
            v_vert += ba * (-_G - a_drag * v_vert) * dt

            pos_east += ba * v_east * dt
            pos_north += ba * v_north * dt
            alt += ba * v_vert * dt

        alive = alive & (alt > 0)

    return np.stack([pos_east, pos_north], axis=1)
