"""Tests for Numba JIT-compiled physics kernels.

Verifies that the Numba kernels produce identical results to the reference
(pure-Python/NumPy) implementation, and that JIT warm-up works correctly.
"""
import time

import numpy as np
import pytest

from droneimpact.physics.m1 import simulate_m1, _m1_kernel
from droneimpact.physics.m2 import simulate_m2, _m2_kernel
from droneimpact.physics.m3 import simulate_m3, _m3_kernel
from droneimpact.physics.warmup import warmup_jit


# ---------------------------------------------------------------------------
# Reference implementations (pre-Numba pure Python/NumPy)
# ---------------------------------------------------------------------------

def _simulate_m1_reference(altitude_agl_m, heading_deg, n_samples, config, rng):
    heading_samples = rng.normal(heading_deg, config.m1_sigma_heading_deg, n_samples)
    glide_samples = rng.normal(
        config.shahed136.glide_ratio, config.m1_sigma_glide_ratio, n_samples
    )
    glide_samples = np.maximum(glide_samples, 0.5)
    range_samples = altitude_agl_m * glide_samples
    heading_rad = np.radians(heading_samples)
    east = range_samples * np.sin(heading_rad)
    north = range_samples * np.cos(heading_rad)
    return np.stack([east, north], axis=1)


def _simulate_m3_reference(altitude_agl_m, heading_deg, speed_m_s, n_samples, config, rng):
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
    pos_east = np.zeros(n_samples)
    pos_north = np.zeros(n_samples)
    alt = np.full(n_samples, altitude_agl_m, dtype=np.float64)
    alive = alt > 0
    half_A_cd_over_m = 0.5 * shahed.fragment_reference_area_m2 * cd_samples / mass_samples
    scale_height = config.atmosphere_scale_height_m
    _RHO = 1.225
    _G = 9.81
    for _ in range(config.m3_max_steps):
        if not np.any(alive):
            break
        rho = _RHO * np.exp(-alt / scale_height)
        spd = np.sqrt(v_east**2 + v_north**2 + v_vert**2)
        a_drag = half_A_cd_over_m * rho * spd
        v_east -= alive * a_drag * v_east * dt
        v_north -= alive * a_drag * v_north * dt
        v_vert = v_vert + alive * (-_G - a_drag * v_vert) * dt
        pos_east += alive * v_east * dt
        pos_north += alive * v_north * dt
        alt += alive * v_vert * dt
        alive = alive & (alt > 0)
    return np.stack([pos_east, pos_north], axis=1)


# ---------------------------------------------------------------------------
# M1 equivalence
# ---------------------------------------------------------------------------

class TestM1Equivalence:
    def test_numba_matches_reference(self, config):
        n = 1000
        ref = _simulate_m1_reference(400.0, 45.0, n, config.physics, np.random.default_rng(42))
        new = simulate_m1(400.0, 45.0, n, config.physics, rng=np.random.default_rng(42))
        np.testing.assert_allclose(new, ref, atol=1e-10)

    def test_numba_matches_reference_high_variance(self, config):
        cfg = config.physics.model_copy(update={
            "m1_sigma_heading_deg": 30.0,
            "m1_sigma_glide_ratio": 3.0,
        })
        n = 2000
        ref = _simulate_m1_reference(200.0, 270.0, n, cfg, np.random.default_rng(99))
        new = simulate_m1(200.0, 270.0, n, cfg, rng=np.random.default_rng(99))
        np.testing.assert_allclose(new, ref, atol=1e-10)


# ---------------------------------------------------------------------------
# M3 equivalence
# ---------------------------------------------------------------------------

class TestM3Equivalence:
    def test_numba_matches_reference(self, config):
        n = 500
        ref = _simulate_m3_reference(400.0, 45.0, 51.4, n, config.physics, np.random.default_rng(42))
        new = simulate_m3(400.0, 45.0, 51.4, n, config.physics, rng=np.random.default_rng(42))
        np.testing.assert_allclose(new, ref, atol=1e-10)

    def test_numba_matches_reference_high_altitude(self, config):
        n = 500
        ref = _simulate_m3_reference(2000.0, 180.0, 51.4, n, config.physics, np.random.default_rng(7))
        new = simulate_m3(2000.0, 180.0, 51.4, n, config.physics, rng=np.random.default_rng(7))
        np.testing.assert_allclose(new, ref, atol=1e-10)


# ---------------------------------------------------------------------------
# M2 statistical equivalence (RNG consumption pattern changed, exact match not possible)
# ---------------------------------------------------------------------------

class TestM2Statistical:
    def test_mean_range_consistent(self, config):
        """M2 mean impact range should be statistically similar between runs."""
        n = 5000
        r1 = simulate_m2(400.0, 0.0, 51.4, n, config.physics, rng=np.random.default_rng(1))
        r2 = simulate_m2(400.0, 0.0, 51.4, n, config.physics, rng=np.random.default_rng(2))
        mean1 = float(np.sqrt((r1**2).sum(axis=1)).mean())
        mean2 = float(np.sqrt((r2**2).sum(axis=1)).mean())
        assert abs(mean1 - mean2) / max(mean1, mean2) < 0.15

    def test_deterministic_with_seed(self, config):
        n = 200
        p1 = simulate_m2(400.0, 45.0, 51.4, n, config.physics, rng=np.random.default_rng(42))
        p2 = simulate_m2(400.0, 45.0, 51.4, n, config.physics, rng=np.random.default_rng(42))
        np.testing.assert_allclose(p1, p2)

    def test_forward_displacement(self, config):
        n = 5000
        pts = simulate_m2(400.0, 0.0, 51.4, n, config.physics, rng=np.random.default_rng(42))
        assert pts[:, 1].mean() > 0


# ---------------------------------------------------------------------------
# Warm-up
# ---------------------------------------------------------------------------

class TestWarmup:
    def test_warmup_runs_without_error(self):
        warmup_jit()

    def test_warmup_second_call_fast(self):
        warmup_jit()
        t0 = time.perf_counter()
        warmup_jit()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert elapsed_ms < 50


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_m2_near_zero_altitude(self, config):
        pts = simulate_m2(0.1, 0.0, 51.4, 100, config.physics, rng=np.random.default_rng(1))
        assert pts.shape == (100, 2)
        assert np.all(np.isfinite(pts))
        ranges = np.sqrt((pts**2).sum(axis=1))
        assert ranges.mean() < 100.0

    def test_m3_minimum_mass(self, config):
        cfg = config.physics.model_copy(
            update={"shahed136": config.physics.shahed136.model_copy(
                update={"fragment_mass_mean_kg": 5.0, "fragment_mass_std_kg": 0.1}
            )}
        )
        pts = simulate_m3(400.0, 0.0, 51.4, 200, cfg, rng=np.random.default_rng(1))
        assert pts.shape == (200, 2)
        assert np.all(np.isfinite(pts))
        assert not np.any(np.isnan(pts))
