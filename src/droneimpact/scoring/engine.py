from __future__ import annotations

import time

import numpy as np

from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.config import AppConfig
from droneimpact.coords import enu_to_wgs84_batch
from droneimpact.data.dem import DEMIndex
from droneimpact.physics.m1 import simulate_m1
from droneimpact.physics.m2 import simulate_m2
from droneimpact.physics.m3 import simulate_m3
from droneimpact.physics.types import TrajectoryPoint
from droneimpact.scoring.ellipse import compute_cep, compute_impact_ellipse
from droneimpact.scoring.explain import explain
from droneimpact.scoring.types import (
    ImpactDistribution,
    ModeScore,
    PointScore,
    RecommendedEngagement,
    TrajectoryResult,
)


class ScoringEngine:
    def __init__(self, config: AppConfig):
        self._config = config

    def score_trajectory(
        self,
        trajectory: list[TrajectoryPoint],
        dem: DEMIndex,
        casualty_engine: CasualtyEngine,
        intercept_point_origin: tuple[float, float],
        rng: np.random.Generator | None = None,
    ) -> TrajectoryResult:
        t_start = time.perf_counter()

        if rng is None:
            rng = np.random.default_rng()

        phys = self._config.physics
        eng = self._config.engagement
        n = phys.n_monte_carlo_samples

        # Miss branch: expected casualties if drone completes trajectory
        last = trajectory[-1]
        last_agl = dem.msl_to_agl(last.lat, last.lon, last.altitude_m)
        miss_enu = simulate_m1(last_agl, last.heading_deg, n, phys, rng=rng)
        miss_wgs84 = enu_to_wgs84_batch(miss_enu, last.lat, last.lon)
        miss_casualties = casualty_engine.compute(
            np.column_stack([miss_wgs84[:, 0], miss_wgs84[:, 1]])
        )

        point_scores: list[PointScore] = []
        impact_dists: list[ImpactDistribution] = []

        for pt in trajectory:
            agl = dem.msl_to_agl(pt.lat, pt.lon, pt.altitude_m)

            # Run all three modes
            enu_m1 = simulate_m1(agl, pt.heading_deg, n, phys, rng=rng)
            enu_m2 = simulate_m2(agl, pt.heading_deg, pt.speed_m_s, n, phys, rng=rng)
            enu_m3 = simulate_m3(agl, pt.heading_deg, pt.speed_m_s, n, phys, rng=rng)

            # Convert ENU → WGS84
            wgs_m1 = _to_wgs84(enu_m1, pt)
            wgs_m2 = _to_wgs84(enu_m2, pt)
            wgs_m3 = _to_wgs84(enu_m3, pt)

            # Compute casualties per mode
            cas_m1 = casualty_engine.compute(wgs_m1)
            cas_m2 = casualty_engine.compute(wgs_m2)
            cas_m3 = casualty_engine.compute(wgs_m3)

            w = eng.mode_weights
            hit_casualties = (
                w.propulsion_loss * cas_m1
                + w.loss_of_control * cas_m2
                + w.break_apart * cas_m3
            )
            score = eng.p_kill * hit_casualties + (1.0 - eng.p_kill) * miss_casualties

            ps = PointScore(
                point_index=pt.index,
                lat=pt.lat,
                lon=pt.lon,
                altitude_m=pt.altitude_m,
                distance_from_start_m=pt.distance_from_start_m,
                expected_casualties=score,
                engagement_score=score,
                breakdown={
                    "propulsion_loss": ModeScore(w.propulsion_loss, cas_m1, compute_cep(enu_m1)),
                    "loss_of_control": ModeScore(w.loss_of_control, cas_m2, compute_cep(enu_m2)),
                    "break_apart": ModeScore(w.break_apart, cas_m3, compute_cep(enu_m3)),
                },
                miss_branch_expected_casualties=miss_casualties,
            )
            point_scores.append(ps)

            # Impact ellipses at every point (recommended point gets full detail)
            for mode_name, enu_pts in [
                ("propulsion_loss", enu_m1),
                ("loss_of_control", enu_m2),
                ("break_apart", enu_m3),
            ]:
                ellipse = compute_impact_ellipse(enu_pts, pt.lat, pt.lon)
                impact_dists.append(ImpactDistribution(pt.index, mode_name, ellipse))

        # Find recommended point
        best_idx = int(np.argmin([ps.engagement_score for ps in point_scores]))
        best = point_scores[best_idx]
        reasoning = explain(best, point_scores)

        recommended = RecommendedEngagement(
            point_index=best.point_index,
            lat=best.lat,
            lon=best.lon,
            altitude_m=best.altitude_m,
            distance_from_current_m=best.distance_from_start_m,
            expected_casualties=best.expected_casualties,
            engagement_score=best.engagement_score,
            reasoning=reasoning,
        )

        elapsed_ms = (time.perf_counter() - t_start) * 1000

        return TrajectoryResult(
            trajectory_scores=point_scores,
            recommended_engagement=recommended,
            impact_distributions=impact_dists,
            metadata={
                "n_trajectory_points": len(trajectory),
                "n_monte_carlo_samples": n,
                "simulation_time_ms": elapsed_ms,
            },
        )


def _to_wgs84(enu: np.ndarray, pt: TrajectoryPoint) -> np.ndarray:
    wgs = enu_to_wgs84_batch(enu, pt.lat, pt.lon)
    return np.column_stack([wgs[:, 0], wgs[:, 1]])  # [lat, lon]
