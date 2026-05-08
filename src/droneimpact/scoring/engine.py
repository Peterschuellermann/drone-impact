from __future__ import annotations

import math
import time

import h3
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
    EngagementZone,
    ImpactDistribution,
    ModeScore,
    PointScore,
    RecommendedEngagement,
    RiskZone,
    TrajectoryResult,
)
from droneimpact.scoring.zones import classify_zones

SHORT_TRAJECTORY_THRESHOLD = 30

# --- Miss branch cache ---

_miss_cache: dict[tuple, float] = {}


def _miss_cache_key(
    lat: float, lon: float, agl: float, heading_deg: float,
    n_samples: int, agl_round: float, hdg_round: float,
) -> tuple:
    cell = h3.latlng_to_cell(lat, lon, 8)
    return (cell, round(agl / agl_round) * agl_round, round(heading_deg / hdg_round) * hdg_round, n_samples)


def clear_miss_cache() -> None:
    _miss_cache.clear()


# --- Coordinate helpers ---

def _enu_to_wgs84_fast(enu: np.ndarray, lat: float, lon: float) -> np.ndarray:
    cos_lat = np.cos(np.radians(lat))
    out_lat = lat + enu[:, 1] / 111_000.0
    out_lon = lon + enu[:, 0] / (111_000.0 * cos_lat)
    return np.column_stack([out_lat, out_lon])


def _max_frag_radius(config: AppConfig) -> float:
    radii: list[float] = []
    cas = config.casualty
    if cas.blast_bands:
        radii.extend(b.radius_m for b in cas.blast_bands)
    if cas.frag_bands:
        radii.extend(b.radius_m for b in cas.frag_bands)
    if not radii:
        radii.append(cas.fragmentation.danger_radius_m)
    return max(radii)


class ScoringEngine:
    def __init__(self, config: AppConfig):
        self._config = config
        self._prescan_radius = _max_frag_radius(config)

    # --- Core per-point scoring ---

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
            hit_branch_expected_casualties=hit_casualties,
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

    # --- Miss branch with caching ---

    def _compute_miss_casualties(
        self,
        last: TrajectoryPoint,
        dem: DEMIndex,
        casualty_engine: CasualtyEngine,
        n_samples: int,
        rng: np.random.Generator,
    ) -> float:
        phys = self._config.physics
        scoring_cfg = self._config.scoring
        last_agl = dem.msl_to_agl(last.lat, last.lon, last.altitude_m)

        key = _miss_cache_key(
            last.lat, last.lon, last_agl, last.heading_deg, n_samples,
            scoring_cfg.miss_cache_agl_round_m, scoring_cfg.miss_cache_heading_round_deg,
        )
        cached = _miss_cache.get(key)
        if cached is not None:
            return cached

        miss_enu = simulate_m1(last_agl, last.heading_deg, n_samples, phys, rng=rng)
        miss_wgs84 = _enu_to_wgs84_fast(miss_enu, last.lat, last.lon)
        miss_casualties = casualty_engine.compute(miss_wgs84)
        _miss_cache[key] = miss_casualties
        return miss_casualties

    # --- Population pre-scan ---

    @staticmethod
    def _population_prescan(
        trajectory: list[TrajectoryPoint],
        casualty_engine: CasualtyEngine,
        radius_m: float,
    ) -> np.ndarray:
        lats = np.array([pt.lat for pt in trajectory])
        lons = np.array([pt.lon for pt in trajectory])
        return casualty_engine.population.query_batch(lats, lons, radius_m)

    # --- Dense point interpolation for high-risk stretches ---

    @staticmethod
    def _build_dense_points(
        trajectory: list[TrajectoryPoint],
        high_risk_mask: np.ndarray,
        dense_spacing_m: float,
    ) -> list[TrajectoryPoint]:
        dense_points: list[TrajectoryPoint] = []
        n = len(trajectory)

        for i in range(n - 1):
            if not high_risk_mask[i] and not high_risk_mask[i + 1]:
                continue

            pt_a = trajectory[i]
            pt_b = trajectory[i + 1]
            gap_m = pt_b.distance_from_start_m - pt_a.distance_from_start_m
            n_interp = int(gap_m / dense_spacing_m) - 1
            if n_interp <= 0:
                continue

            for k in range(1, n_interp + 1):
                frac = k / (n_interp + 1)
                dense_points.append(TrajectoryPoint(
                    index=pt_a.index,
                    lat=pt_a.lat + frac * (pt_b.lat - pt_a.lat),
                    lon=pt_a.lon + frac * (pt_b.lon - pt_a.lon),
                    altitude_m=pt_a.altitude_m + frac * (pt_b.altitude_m - pt_a.altitude_m),
                    distance_from_start_m=pt_a.distance_from_start_m + frac * gap_m,
                    heading_deg=pt_a.heading_deg,
                    speed_m_s=pt_a.speed_m_s,
                ))

        return dense_points

    # --- Risk zone detection (F20) ---

    def _find_risk_zones(
        self, point_scores: list[PointScore], threshold: float,
    ) -> list[RiskZone]:
        zones: list[RiskZone] = []
        in_zone = False
        start_idx = 0
        peak = 0.0

        for ps in point_scores:
            is_high = ps.hit_branch_expected_casualties > threshold
            if is_high and not in_zone:
                in_zone = True
                start_idx = ps.point_index
                peak = ps.hit_branch_expected_casualties
            elif is_high and in_zone:
                peak = max(peak, ps.hit_branch_expected_casualties)
            elif not is_high and in_zone:
                end_idx = ps.point_index - 1
                start_dist = next(
                    p.distance_from_start_m for p in point_scores if p.point_index == start_idx
                )
                end_dist = next(
                    p.distance_from_start_m for p in point_scores if p.point_index == end_idx
                )
                zones.append(RiskZone(
                    start_index=start_idx,
                    end_index=end_idx,
                    start_distance_m=start_dist,
                    end_distance_m=end_dist,
                    peak_expected_casualties=peak,
                ))
                in_zone = False

        if in_zone:
            last = point_scores[-1]
            start_dist = next(
                p.distance_from_start_m for p in point_scores if p.point_index == start_idx
            )
            zones.append(RiskZone(
                start_index=start_idx,
                end_index=last.point_index,
                start_distance_m=start_dist,
                end_distance_m=last.distance_from_start_m,
                peak_expected_casualties=peak,
            ))

        return zones

    # --- Safe intercept constraint (F20) ---

    def _apply_safe_intercept_constraint(
        self,
        point_scores: list[PointScore],
        impact_dists: list[ImpactDistribution],
        t_start: float,
        n_samples: int,
        n_pts: int,
        pop_at_points: np.ndarray | None = None,
    ) -> TrajectoryResult:
        threshold = self._config.engagement.high_risk_threshold
        scoring_cfg = self._config.scoring

        for ps in point_scores:
            ps.high_risk = ps.hit_branch_expected_casualties > threshold

        risk_zones = self._find_risk_zones(point_scores, threshold)

        eligible: list[PointScore] = []
        blocked = False
        for ps in point_scores:
            if ps.high_risk:
                blocked = True
            if not blocked:
                eligible.append(ps)

        if not eligible:
            eligible = [point_scores[0]]

        best_constrained = min(eligible, key=lambda ps: ps.engagement_score)
        best_unconstrained = min(point_scores, key=lambda ps: ps.engagement_score)
        is_constrained = best_constrained.point_index != best_unconstrained.point_index

        zones = classify_zones(point_scores, scoring_cfg)
        reasoning = explain(best_constrained, point_scores, zones, is_constrained=is_constrained)

        recommended = RecommendedEngagement(
            point_index=best_constrained.point_index,
            lat=best_constrained.lat,
            lon=best_constrained.lon,
            altitude_m=best_constrained.altitude_m,
            distance_from_current_m=best_constrained.distance_from_start_m,
            expected_casualties=best_constrained.expected_casualties,
            engagement_score=best_constrained.engagement_score,
            reasoning=reasoning,
        )

        unconstrained_optimum = None
        if is_constrained:
            unconstrained_reasoning = explain(best_unconstrained, point_scores, zones)
            unconstrained_optimum = RecommendedEngagement(
                point_index=best_unconstrained.point_index,
                lat=best_unconstrained.lat,
                lon=best_unconstrained.lon,
                altitude_m=best_unconstrained.altitude_m,
                distance_from_current_m=best_unconstrained.distance_from_start_m,
                expected_casualties=best_unconstrained.expected_casualties,
                engagement_score=best_unconstrained.engagement_score,
                reasoning=unconstrained_reasoning,
            )

        elapsed_ms = (time.perf_counter() - t_start) * 1000

        metadata: dict = {
            "n_trajectory_points": n_pts,
            "n_monte_carlo_samples": n_samples,
            "simulation_time_ms": elapsed_ms,
        }

        return TrajectoryResult(
            trajectory_scores=point_scores,
            recommended_engagement=recommended,
            impact_distributions=impact_dists,
            metadata=metadata,
            engagement_zones=zones,
            risk_zones=risk_zones,
            unconstrained_optimum=unconstrained_optimum,
        )

    # --- Main entry point ---

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
        scoring_cfg = self._config.scoring
        n_samples = phys.n_monte_carlo_samples

        miss_casualties = self._compute_miss_casualties(
            trajectory[-1], dem, casualty_engine, n_samples, rng,
        )

        pop_at_points = self._population_prescan(
            trajectory, casualty_engine, self._prescan_radius,
        )

        n_pts = len(trajectory)

        if n_pts <= SHORT_TRAJECTORY_THRESHOLD:
            return self._score_all_points(
                trajectory, dem, casualty_engine, miss_casualties, n_samples, rng,
                t_start, pop_at_points, compute_ellipses=True,
            )

        # --- Adaptive resolution for long trajectories ---

        empty_thresh = scoring_cfg.population_empty_threshold
        high_thresh = scoring_cfg.population_high_risk_threshold

        classifications = np.zeros(n_pts, dtype=np.int8)
        classifications[pop_at_points > empty_thresh] = 1
        classifications[pop_at_points >= high_thresh] = 2

        high_risk_mask = classifications == 2

        dense_points = self._build_dense_points(
            trajectory, high_risk_mask, scoring_cfg.dense_spacing_m,
        )

        scored_originals: dict[int, PointScore] = {}
        impact_dists: list[ImpactDistribution] = []
        n_points_skipped = 0
        n_points_dense = len(dense_points)

        for i, pt in enumerate(trajectory):
            if classifications[i] == 0:
                n_points_skipped += 1
                continue
            agl = dem.msl_to_agl(pt.lat, pt.lon, pt.altitude_m)
            compute_ell = classifications[i] == 2
            ps, dists = self._score_point(
                pt, agl, n_samples, casualty_engine, miss_casualties, rng,
                compute_ellipses=compute_ell,
            )
            ps.population_within_frag_radius = float(pop_at_points[i])
            scored_originals[i] = ps
            impact_dists.extend(dists)

        best_dense_per_original: dict[int, float] = {}
        for dpt in dense_points:
            agl = dem.msl_to_agl(dpt.lat, dpt.lon, dpt.altitude_m)
            ps, _ = self._score_point(
                dpt, agl, n_samples, casualty_engine, miss_casualties, rng,
            )
            orig_idx = dpt.index
            if orig_idx in scored_originals:
                current_best = best_dense_per_original.get(orig_idx)
                if current_best is None or ps.engagement_score < current_best:
                    best_dense_per_original[orig_idx] = ps.engagement_score

        for orig_idx, dense_score in best_dense_per_original.items():
            if orig_idx in scored_originals:
                orig = scored_originals[orig_idx]
                if dense_score < orig.engagement_score:
                    scored_originals[orig_idx] = PointScore(
                        point_index=orig.point_index,
                        lat=orig.lat,
                        lon=orig.lon,
                        altitude_m=orig.altitude_m,
                        distance_from_start_m=orig.distance_from_start_m,
                        expected_casualties=dense_score,
                        engagement_score=dense_score,
                        breakdown=orig.breakdown,
                        miss_branch_expected_casualties=orig.miss_branch_expected_casualties,
                        population_within_frag_radius=orig.population_within_frag_radius,
                        hit_branch_expected_casualties=orig.hit_branch_expected_casualties,
                    )

        miss_only_score = (1.0 - self._config.engagement.p_kill) * miss_casualties
        point_scores: list[PointScore] = []
        for i, pt in enumerate(trajectory):
            if i in scored_originals:
                point_scores.append(scored_originals[i])
            else:
                point_scores.append(PointScore(
                    point_index=pt.index,
                    lat=pt.lat,
                    lon=pt.lon,
                    altitude_m=pt.altitude_m,
                    distance_from_start_m=pt.distance_from_start_m,
                    expected_casualties=miss_only_score,
                    engagement_score=miss_only_score,
                    breakdown={},
                    miss_branch_expected_casualties=miss_casualties,
                    population_within_frag_radius=float(pop_at_points[i]),
                ))

        point_scores = self._interpolate_gaps(trajectory, point_scores, scored_originals)

        return self._apply_safe_intercept_constraint(
            point_scores, impact_dists, t_start, n_samples, n_pts, pop_at_points,
        )

    # --- Short trajectory path ---

    def _score_all_points(
        self,
        trajectory: list[TrajectoryPoint],
        dem: DEMIndex,
        casualty_engine: CasualtyEngine,
        miss_casualties: float,
        n_samples: int,
        rng: np.random.Generator,
        t_start: float,
        pop_at_points: np.ndarray,
        compute_ellipses: bool = True,
    ) -> TrajectoryResult:
        point_scores: list[PointScore] = []
        impact_dists: list[ImpactDistribution] = []

        for i, pt in enumerate(trajectory):
            agl = dem.msl_to_agl(pt.lat, pt.lon, pt.altitude_m)
            ps, dists = self._score_point(
                pt, agl, n_samples, casualty_engine, miss_casualties, rng,
                compute_ellipses=compute_ellipses,
            )
            ps.population_within_frag_radius = float(pop_at_points[i])
            point_scores.append(ps)
            impact_dists.extend(dists)

        return self._apply_safe_intercept_constraint(
            point_scores, impact_dists, t_start, n_samples, len(trajectory), pop_at_points,
        )

    @staticmethod
    def _interpolate_gaps(
        trajectory: list[TrajectoryPoint],
        point_scores: list[PointScore],
        scored: dict[int, PointScore],
    ) -> list[PointScore]:
        if not scored or len(scored) == len(trajectory):
            return point_scores

        scored_indices = sorted(scored.keys())
        scores_arr = np.array([scored[i].engagement_score for i in scored_indices])
        all_indices = np.arange(len(trajectory))
        interp_scores = np.interp(all_indices, scored_indices, scores_arr)

        result: list[PointScore] = []
        for i, ps in enumerate(point_scores):
            if i in scored:
                result.append(ps)
            else:
                result.append(PointScore(
                    point_index=ps.point_index,
                    lat=ps.lat,
                    lon=ps.lon,
                    altitude_m=ps.altitude_m,
                    distance_from_start_m=ps.distance_from_start_m,
                    expected_casualties=float(interp_scores[i]),
                    engagement_score=float(interp_scores[i]),
                    breakdown=ps.breakdown,
                    miss_branch_expected_casualties=ps.miss_branch_expected_casualties,
                    population_within_frag_radius=ps.population_within_frag_radius,
                ))
        return result
