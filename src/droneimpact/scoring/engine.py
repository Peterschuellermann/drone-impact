from __future__ import annotations

import time

import numpy as np

from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.config import AppConfig
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

COARSE_FRACTION = 0.1
N_REFINE_CANDIDATES = 3
COARSE_STRIDE_TARGET = 30
REFINE_NEIGHBOR_RADIUS = 2


def _enu_to_wgs84_fast(enu: np.ndarray, lat: float, lon: float) -> np.ndarray:
    cos_lat = np.cos(np.radians(lat))
    out_lat = lat + enu[:, 1] / 111_000.0
    out_lon = lon + enu[:, 0] / (111_000.0 * cos_lat)
    return np.column_stack([out_lat, out_lon])


class ScoringEngine:
    def __init__(self, config: AppConfig):
        self._config = config

    def _score_point(
        self,
        pt: TrajectoryPoint,
        agl: float,
        n_samples: int,
        casualty_engine: CasualtyEngine,
        miss_casualties: float,
        rng: np.random.Generator,
        compute_ellipses: bool = False,
    ) -> tuple[PointScore, list[ImpactDistribution]]:
        phys = self._config.physics
        eng = self._config.engagement

        enu_m1 = simulate_m1(agl, pt.heading_deg, n_samples, phys, rng=rng)
        enu_m2 = simulate_m2(agl, pt.heading_deg, pt.speed_m_s, n_samples, phys, rng=rng)
        enu_m3 = simulate_m3(agl, pt.heading_deg, pt.speed_m_s, n_samples, phys, rng=rng)

        wgs_m1 = _enu_to_wgs84_fast(enu_m1, pt.lat, pt.lon)
        wgs_m2 = _enu_to_wgs84_fast(enu_m2, pt.lat, pt.lon)
        wgs_m3 = _enu_to_wgs84_fast(enu_m3, pt.lat, pt.lon)

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

        dists: list[ImpactDistribution] = []
        if compute_ellipses:
            for mode_name, enu_pts in [
                ("propulsion_loss", enu_m1),
                ("loss_of_control", enu_m2),
                ("break_apart", enu_m3),
            ]:
                ellipse = compute_impact_ellipse(enu_pts, pt.lat, pt.lon)
                dists.append(ImpactDistribution(pt.index, mode_name, ellipse))

        return ps, dists

    def score_trajectory(
        self,
        trajectory: list[TrajectoryPoint],
        dem: DEMIndex,
        casualty_engine: CasualtyEngine,
        intercept_point_origin: tuple[float, float],
        rng: np.random.Generator | None = None,
    ) -> TrajectoryResult:
        t_start = time.perf_counter()

        if not trajectory:
            raise ValueError("trajectory must not be empty")

        if rng is None:
            rng = np.random.default_rng()

        phys = self._config.physics
        n_samples = phys.n_monte_carlo_samples
        n_coarse = max(50, int(n_samples * COARSE_FRACTION))

        # Miss branch: expected casualties if drone completes trajectory
        last = trajectory[-1]
        last_agl = dem.msl_to_agl(last.lat, last.lon, last.altitude_m)
        miss_enu = simulate_m1(last_agl, last.heading_deg, n_samples, phys, rng=rng)
        miss_wgs84 = _enu_to_wgs84_fast(miss_enu, last.lat, last.lon)
        miss_casualties = casualty_engine.compute(miss_wgs84)

        n_pts = len(trajectory)
        use_two_pass = n_pts > COARSE_STRIDE_TARGET

        if not use_two_pass:
            return self._score_all_points(
                trajectory, dem, casualty_engine, miss_casualties, n_samples, rng,
                t_start, compute_ellipses=True,
            )

        # --- Two-pass scoring ---

        # Pass 1: coarse scan — every stride-th point with reduced samples
        stride = max(1, n_pts // COARSE_STRIDE_TARGET)
        coarse_indices = list(range(0, n_pts, stride))
        if (n_pts - 1) not in coarse_indices:
            coarse_indices.append(n_pts - 1)

        coarse_scores: dict[int, PointScore] = {}
        for i in coarse_indices:
            pt = trajectory[i]
            agl = dem.msl_to_agl(pt.lat, pt.lon, pt.altitude_m)
            ps, _ = self._score_point(
                pt, agl, n_coarse, casualty_engine, miss_casualties, rng,
            )
            coarse_scores[i] = ps

        # Find the best coarse region
        sorted_by_score = sorted(coarse_scores.items(), key=lambda kv: kv[1].engagement_score)
        candidate_centres = [idx for idx, _ in sorted_by_score[:N_REFINE_CANDIDATES]]

        # Pass 2: refine — full MC around each candidate
        refine_set: set[int] = set()
        for c in candidate_centres:
            for j in range(max(0, c - REFINE_NEIGHBOR_RADIUS), min(n_pts, c + REFINE_NEIGHBOR_RADIUS + 1)):
                refine_set.add(j)

        refined_scores: dict[int, PointScore] = {}
        impact_dists: list[ImpactDistribution] = []
        for i in sorted(refine_set):
            pt = trajectory[i]
            agl = dem.msl_to_agl(pt.lat, pt.lon, pt.altitude_m)
            ps, dists = self._score_point(
                pt, agl, n_samples, casualty_engine, miss_casualties, rng,
                compute_ellipses=True,
            )
            refined_scores[i] = ps
            impact_dists.extend(dists)

        # Build full trajectory scores: use refined where available, coarse otherwise.
        # For points that were neither coarse nor refined, interpolate from neighbors.
        all_scored = {**coarse_scores, **refined_scores}
        point_scores = self._interpolate_scores(
            trajectory, all_scored, miss_casualties,
        )

        # Recommendation comes from refined points only
        best_refined = min(refined_scores.values(), key=lambda ps: ps.engagement_score)
        reasoning = explain(best_refined, point_scores)

        recommended = RecommendedEngagement(
            point_index=best_refined.point_index,
            lat=best_refined.lat,
            lon=best_refined.lon,
            altitude_m=best_refined.altitude_m,
            distance_from_current_m=best_refined.distance_from_start_m,
            expected_casualties=best_refined.expected_casualties,
            engagement_score=best_refined.engagement_score,
            reasoning=reasoning,
        )

        elapsed_ms = (time.perf_counter() - t_start) * 1000

        return TrajectoryResult(
            trajectory_scores=point_scores,
            recommended_engagement=recommended,
            impact_distributions=impact_dists,
            metadata={
                "n_trajectory_points": n_pts,
                "n_monte_carlo_samples": n_samples,
                "simulation_time_ms": elapsed_ms,
            },
        )

    def _score_all_points(
        self,
        trajectory: list[TrajectoryPoint],
        dem: DEMIndex,
        casualty_engine: CasualtyEngine,
        miss_casualties: float,
        n_samples: int,
        rng: np.random.Generator,
        t_start: float,
        compute_ellipses: bool = True,
    ) -> TrajectoryResult:
        point_scores: list[PointScore] = []
        impact_dists: list[ImpactDistribution] = []

        for pt in trajectory:
            agl = dem.msl_to_agl(pt.lat, pt.lon, pt.altitude_m)
            ps, dists = self._score_point(
                pt, agl, n_samples, casualty_engine, miss_casualties, rng,
                compute_ellipses=compute_ellipses,
            )
            point_scores.append(ps)
            impact_dists.extend(dists)

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
                "n_monte_carlo_samples": n_samples,
                "simulation_time_ms": elapsed_ms,
            },
        )

    @staticmethod
    def _interpolate_scores(
        trajectory: list[TrajectoryPoint],
        scored: dict[int, PointScore],
        miss_casualties: float,
    ) -> list[PointScore]:
        n = len(trajectory)
        scored_indices = sorted(scored.keys())
        scores_arr = np.array([scored[i].engagement_score for i in scored_indices])

        all_indices = np.arange(n)
        interp_scores = np.interp(all_indices, scored_indices, scores_arr)

        result: list[PointScore] = []
        for i in range(n):
            if i in scored:
                result.append(scored[i])
            else:
                pt = trajectory[i]
                result.append(PointScore(
                    point_index=pt.index,
                    lat=pt.lat,
                    lon=pt.lon,
                    altitude_m=pt.altitude_m,
                    distance_from_start_m=pt.distance_from_start_m,
                    expected_casualties=float(interp_scores[i]),
                    engagement_score=float(interp_scores[i]),
                    breakdown={},
                    miss_branch_expected_casualties=miss_casualties,
                ))
        return result
