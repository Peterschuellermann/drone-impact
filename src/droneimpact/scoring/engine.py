from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor

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
    InterceptionZone,
    ModeScore,
    PointScore,
    RankedEngagement,
    RecommendedEngagement,
    RiskZone,
    TrajectoryResult,
)
from droneimpact.scoring.zones import classify_zones

SHORT_TRAJECTORY_THRESHOLD = 30

# --- Miss branch cache ---


def _miss_cache_key(
    lat: float, lon: float, agl: float, heading_deg: float,
    n_samples: int, agl_round: float, hdg_round: float,
) -> tuple:
    cell = h3.latlng_to_cell(lat, lon, 8)
    return (cell, round(agl / agl_round) * agl_round, round(heading_deg / hdg_round) * hdg_round, n_samples)


def clear_miss_cache() -> None:
    """No-op. Miss cache is now per-ScoringEngine instance."""
    pass


# --- Coordinate helpers ---

def _enu_to_wgs84_fast(enu: np.ndarray, lat: float, lon: float) -> np.ndarray:
    valid = np.isfinite(enu).all(axis=1)
    enu = enu[valid]
    cos_lat = np.cos(np.radians(lat))
    out_lat = lat + enu[:, 1] / 111_000.0
    out_lon = lon + enu[:, 0] / (111_000.0 * cos_lat)
    wgs = np.column_stack([out_lat, out_lon])
    valid = np.isfinite(wgs).all(axis=1) & (np.abs(wgs[:, 0]) <= 90) & (np.abs(wgs[:, 1]) <= 180)
    return wgs[valid]


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
    def __init__(self, config: AppConfig, max_point_workers: int | None = None):
        self._config = config
        self._prescan_radius = _max_frag_radius(config)
        self._miss_cache: dict[tuple, float] = {}
        if max_point_workers is not None:
            self._max_workers = max_point_workers
        else:
            self._max_workers = config.parallelism.effective_point_workers

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
        enable = eng.mode_enable
        w = eng.mode_weights

        modes: list[tuple[str, float, callable, tuple]] = []
        if enable.propulsion_loss:
            modes.append(("propulsion_loss", w.propulsion_loss,
                          simulate_m1, (agl, pt.heading_deg, pt.speed_m_s, n_samples, phys)))
        if enable.loss_of_control:
            modes.append(("loss_of_control", w.loss_of_control,
                          simulate_m2, (agl, pt.heading_deg, pt.speed_m_s, n_samples, phys)))
        if enable.break_apart:
            modes.append(("break_apart", w.break_apart,
                          simulate_m3, (agl, pt.heading_deg, pt.speed_m_s, n_samples, phys)))

        total_weight = sum(mw for _, mw, _, _ in modes)

        breakdown: dict[str, ModeScore] = {}
        dists: list[ImpactDistribution] = []
        hit_casualties = 0.0

        for mode_name, raw_weight, sim_fn, sim_args in modes:
            enu = sim_fn(*sim_args, rng=rng)
            wgs = _enu_to_wgs84_fast(enu, pt.lat, pt.lon)
            cas = casualty_engine.compute(wgs)
            eff_weight = raw_weight / total_weight if total_weight > 0 else 0.0
            hit_casualties += eff_weight * cas
            breakdown[mode_name] = ModeScore(eff_weight, cas, compute_cep(enu))
            if compute_ellipses:
                ellipse = compute_impact_ellipse(enu, pt.lat, pt.lon)
                dists.append(ImpactDistribution(pt.index, mode_name, ellipse))

        engagement_score = eng.p_kill * hit_casualties + (1.0 - eng.p_kill) * miss_casualties

        ps = PointScore(
            point_index=pt.index,
            lat=pt.lat,
            lon=pt.lon,
            altitude_m=pt.altitude_m,
            distance_from_start_m=pt.distance_from_start_m,
            expected_casualties=hit_casualties,
            engagement_score=engagement_score,
            breakdown=breakdown,
            miss_branch_expected_casualties=miss_casualties,
            heading_deg=pt.heading_deg,
            speed_m_s=pt.speed_m_s,
            hit_branch_expected_casualties=hit_casualties,
        )

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
        cached = self._miss_cache.get(key)
        if cached is not None:
            return cached

        miss_enu = simulate_m1(last_agl, last.heading_deg, last.speed_m_s, n_samples, phys, rng=rng)
        miss_wgs84 = _enu_to_wgs84_fast(miss_enu, last.lat, last.lon)
        miss_casualties = casualty_engine.compute(miss_wgs84)
        self._miss_cache[key] = miss_casualties
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
        start_dist = 0.0
        peak = 0.0
        prev_ps: PointScore | None = None

        for ps in point_scores:
            is_high = ps.hit_branch_expected_casualties > threshold
            if is_high and not in_zone:
                in_zone = True
                start_idx = ps.point_index
                start_dist = ps.distance_from_start_m
                peak = ps.hit_branch_expected_casualties
            elif is_high and in_zone:
                peak = max(peak, ps.hit_branch_expected_casualties)
            elif not is_high and in_zone:
                assert prev_ps is not None
                zones.append(RiskZone(
                    start_index=start_idx,
                    end_index=prev_ps.point_index,
                    start_distance_m=start_dist,
                    end_distance_m=prev_ps.distance_from_start_m,
                    peak_expected_casualties=peak,
                ))
                in_zone = False
            prev_ps = ps

        if in_zone:
            last = point_scores[-1]
            zones.append(RiskZone(
                start_index=start_idx,
                end_index=last.point_index,
                start_distance_m=start_dist,
                end_distance_m=last.distance_from_start_m,
                peak_expected_casualties=peak,
            ))

        return zones

    # --- Interception zones ---

    @staticmethod
    def _classify_risk(
        hit_casualties: float,
        threshold: float,
    ) -> str:
        if hit_casualties < threshold * 0.2:
            return "safe"
        elif hit_casualties < threshold * 0.5:
            return "caution"
        elif hit_casualties < threshold:
            return "elevated"
        return "no_go"

    @staticmethod
    def _build_corridor_polygon(
        points: list[PointScore],
        radius_m: float,
    ) -> list[list[float]]:
        if len(points) < 2:
            lat, lon = points[0].lat, points[0].lon
            lat_per_m = 1.0 / 111_000.0
            lon_per_m = 1.0 / (111_000.0 * max(math.cos(math.radians(lat)), 0.01))
            dlat = radius_m * lat_per_m
            dlon = radius_m * lon_per_m
            return [
                [lat - dlat, lon - dlon],
                [lat - dlat, lon + dlon],
                [lat + dlat, lon + dlon],
                [lat + dlat, lon - dlon],
            ]

        left_side: list[list[float]] = []
        right_side: list[list[float]] = []

        for i, ps in enumerate(points):
            if i < len(points) - 1:
                dx = points[i + 1].lon - ps.lon
                dy = points[i + 1].lat - ps.lat
            else:
                dx = ps.lon - points[i - 1].lon
                dy = ps.lat - points[i - 1].lat

            length = math.hypot(dx, dy)
            if length < 1e-12:
                if left_side:
                    left_side.append(left_side[-1])
                    right_side.append(right_side[-1])
                continue

            nx, ny = -dy / length, dx / length

            lat_per_m = 1.0 / 111_000.0
            lon_per_m = 1.0 / (111_000.0 * max(math.cos(math.radians(ps.lat)), 0.01))

            left_side.append([
                ps.lat + ny * radius_m * lat_per_m,
                ps.lon + nx * radius_m * lon_per_m,
            ])
            right_side.append([
                ps.lat - ny * radius_m * lat_per_m,
                ps.lon - nx * radius_m * lon_per_m,
            ])

        return left_side + list(reversed(right_side))

    def _compute_interception_zones(
        self,
        point_scores: list[PointScore],
        impact_dists: list[ImpactDistribution],
    ) -> list[InterceptionZone]:
        scoring_cfg = self._config.scoring
        eng_cfg = self._config.engagement
        threshold = eng_cfg.high_risk_threshold
        min_pts = scoring_cfg.interception_zone_min_points

        classified = [
            (ps, self._classify_risk(ps.hit_branch_expected_casualties, threshold))
            for ps in point_scores
        ]

        segments: list[list[tuple[PointScore, str]]] = []
        current_seg: list[tuple[PointScore, str]] = [classified[0]]

        for ps, cls in classified[1:]:
            if cls != current_seg[0][1]:
                segments.append(current_seg)
                current_seg = [(ps, cls)]
            else:
                current_seg.append((ps, cls))
        segments.append(current_seg)

        dist_by_point: dict[int, list[ImpactDistribution]] = {}
        for d in impact_dists:
            dist_by_point.setdefault(d.point_index, []).append(d)

        zones: list[InterceptionZone] = []
        zone_id = 0

        for seg in segments:
            if len(seg) < min_pts:
                continue

            risk_class = seg[0][1]
            seg_points = [ps for ps, _ in seg]

            avg_speed = sum(ps.speed_m_s for ps in seg_points) / len(seg_points)
            uncertainty_r = (
                scoring_cfg.drone_maneuverability_radius_m
                + avg_speed * scoring_cfg.interception_timing_uncertainty_s
            )

            corridor = self._build_corridor_polygon(seg_points, uncertainty_r)

            length_m = seg_points[-1].distance_from_start_m - seg_points[0].distance_from_start_m
            timing_window_m = avg_speed * scoring_cfg.interception_timing_uncertainty_s
            n_shots = max(1, length_m / timing_window_m) if timing_window_m > 0 else 1
            intercept_prob = 1.0 - (1.0 - eng_cfg.p_kill) ** n_shots

            scores = [ps.engagement_score for ps in seg_points]
            casualties = [ps.hit_branch_expected_casualties for ps in seg_points]
            best_ps = min(seg_points, key=lambda p: p.engagement_score)

            fall_ellipses = dist_by_point.get(best_ps.point_index, [])

            zones.append(InterceptionZone(
                zone_id=zone_id,
                risk_class=risk_class,
                start_index=seg_points[0].point_index,
                end_index=seg_points[-1].point_index,
                start_lat=seg_points[0].lat,
                start_lon=seg_points[0].lon,
                end_lat=seg_points[-1].lat,
                end_lon=seg_points[-1].lon,
                start_distance_m=seg_points[0].distance_from_start_m,
                end_distance_m=seg_points[-1].distance_from_start_m,
                length_m=length_m,
                corridor_polygon=corridor,
                uncertainty_radius_m=uncertainty_r,
                intercept_probability=intercept_prob,
                mean_engagement_score=float(np.mean(scores)),
                best_engagement_score=best_ps.engagement_score,
                best_point_index=best_ps.point_index,
                peak_expected_casualties=max(casualties),
                mean_expected_casualties=float(np.mean(casualties)),
                fall_ellipses=fall_ellipses,
            ))
            zone_id += 1

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

        # Sort eligible points by engagement_score ascending to get ranked list
        eligible_sorted = sorted(eligible, key=lambda ps: ps.engagement_score)
        top_eligible = eligible_sorted[:5]

        best_constrained = top_eligible[0]
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

        # Build ranked engagements list (rank 1 = best, up to top 5)
        ranked_engagements: list[RankedEngagement] = []
        for rank, ps in enumerate(top_eligible, start=1):
            if rank == 1:
                pt_reasoning = reasoning
            else:
                base_reasoning = explain(ps, point_scores, zones, is_constrained=False)
                pt_reasoning = (
                    f"Fallback option if points 1–{rank - 1} are missed. {base_reasoning}"
                )
            ranked_engagements.append(RankedEngagement(
                rank=rank,
                point_index=ps.point_index,
                lat=ps.lat,
                lon=ps.lon,
                altitude_m=ps.altitude_m,
                distance_from_current_m=ps.distance_from_start_m,
                expected_casualties=ps.expected_casualties,
                engagement_score=ps.engagement_score,
                reasoning=pt_reasoning,
            ))

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

        interception_zones = self._compute_interception_zones(point_scores, impact_dists)

        return TrajectoryResult(
            trajectory_scores=point_scores,
            recommended_engagement=recommended,
            impact_distributions=impact_dists,
            metadata=metadata,
            engagement_zones=zones,
            risk_zones=risk_zones,
            unconstrained_optimum=unconstrained_optimum,
            ranked_engagements=ranked_engagements,
            interception_zones=interception_zones,
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

        n_points_skipped = 0
        n_points_dense = len(dense_points)

        # Build work items for original non-empty points
        orig_work: list[tuple[int, TrajectoryPoint, float, bool]] = []
        for i, pt in enumerate(trajectory):
            if classifications[i] == 0:
                n_points_skipped += 1
                continue
            agl = dem.msl_to_agl(pt.lat, pt.lon, pt.altitude_m)
            compute_ell = classifications[i] == 2
            orig_work.append((i, pt, agl, compute_ell))

        # Build work items for dense interpolated points
        dense_work: list[tuple[int, TrajectoryPoint, float, bool]] = []
        for dpt in dense_points:
            agl = dem.msl_to_agl(dpt.lat, dpt.lon, dpt.altitude_m)
            dense_work.append((dpt.index, dpt, agl, False))

        base_seed = rng.bit_generator.seed_seq

        # Score original + dense in parallel
        orig_results = self._score_points_parallel(
            orig_work, n_samples, casualty_engine, miss_casualties, base_seed,
        )
        dense_seed = base_seed.spawn(1)[0]
        dense_results = self._score_points_parallel(
            dense_work, n_samples, casualty_engine, miss_casualties, dense_seed,
        )

        scored_originals: dict[int, PointScore] = {}
        impact_dists: list[ImpactDistribution] = []
        for i, ps, dists in orig_results:
            ps.population_within_frag_radius = float(pop_at_points[i])
            scored_originals[i] = ps
            impact_dists.extend(dists)

        best_dense_per_original: dict[int, PointScore] = {}
        for orig_idx, ps, _ in dense_results:
            if orig_idx in scored_originals:
                current_best = best_dense_per_original.get(orig_idx)
                if current_best is None or ps.engagement_score < current_best.engagement_score:
                    best_dense_per_original[orig_idx] = ps

        for orig_idx, dense_ps in best_dense_per_original.items():
            if orig_idx in scored_originals:
                orig = scored_originals[orig_idx]
                if dense_ps.engagement_score < orig.engagement_score:
                    scored_originals[orig_idx] = PointScore(
                        point_index=orig.point_index,
                        lat=orig.lat,
                        lon=orig.lon,
                        altitude_m=orig.altitude_m,
                        distance_from_start_m=orig.distance_from_start_m,
                        expected_casualties=dense_ps.expected_casualties,
                        engagement_score=dense_ps.engagement_score,
                        breakdown=orig.breakdown,
                        miss_branch_expected_casualties=orig.miss_branch_expected_casualties,
                        heading_deg=orig.heading_deg,
                        speed_m_s=orig.speed_m_s,
                        population_within_frag_radius=orig.population_within_frag_radius,
                        hit_branch_expected_casualties=dense_ps.hit_branch_expected_casualties,
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
                    expected_casualties=0.0,
                    engagement_score=miss_only_score,
                    breakdown={},
                    miss_branch_expected_casualties=miss_casualties,
                    heading_deg=pt.heading_deg,
                    speed_m_s=pt.speed_m_s,
                    population_within_frag_radius=float(pop_at_points[i]),
                ))

        point_scores = self._interpolate_gaps(
            trajectory, point_scores, scored_originals,
            pop_at_points, empty_thresh,
        )

        result = self._apply_safe_intercept_constraint(
            point_scores, impact_dists, t_start, n_samples, n_pts, pop_at_points,
        )
        result.metadata["n_points_skipped"] = n_points_skipped
        result.metadata["n_points_dense"] = n_points_dense
        return result

    # --- Parallel scoring helpers ---

    def _score_points_parallel(
        self,
        work_items: list[tuple[int, TrajectoryPoint, float, bool]],
        n_samples: int,
        casualty_engine: CasualtyEngine,
        miss_casualties: float,
        base_seed: np.random.SeedSequence,
    ) -> list[tuple[int, PointScore, list[ImpactDistribution]]]:
        child_seeds = base_seed.spawn(len(work_items))
        point_rngs = [np.random.default_rng(s) for s in child_seeds]

        def _do_one(idx: int) -> tuple[int, PointScore, list[ImpactDistribution]]:
            i, pt, agl, compute_ell = work_items[idx]
            ps, dists = self._score_point(
                pt, agl, n_samples, casualty_engine, miss_casualties,
                point_rngs[idx], compute_ellipses=compute_ell,
            )
            return i, ps, dists

        results: list[tuple[int, PointScore, list[ImpactDistribution]]] = []

        if self._max_workers <= 1 or len(work_items) <= 1:
            for idx in range(len(work_items)):
                results.append(_do_one(idx))
        else:
            n_workers = min(self._max_workers, len(work_items))
            with ThreadPoolExecutor(max_workers=n_workers) as pool:
                results = list(pool.map(_do_one, range(len(work_items))))

        return results

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
        work_items = []
        for i, pt in enumerate(trajectory):
            agl = dem.msl_to_agl(pt.lat, pt.lon, pt.altitude_m)
            work_items.append((i, pt, agl, compute_ellipses))

        base_seed = rng.bit_generator.seed_seq
        scored = self._score_points_parallel(
            work_items, n_samples, casualty_engine, miss_casualties, base_seed,
        )

        point_scores: list[PointScore] = [None] * len(trajectory)  # type: ignore[list-item]
        impact_dists: list[ImpactDistribution] = []
        for i, ps, dists in scored:
            ps.population_within_frag_radius = float(pop_at_points[i])
            point_scores[i] = ps
            impact_dists.extend(dists)

        return self._apply_safe_intercept_constraint(
            point_scores, impact_dists, t_start, n_samples, len(trajectory), pop_at_points,
        )

    @staticmethod
    def _interpolate_gaps(
        trajectory: list[TrajectoryPoint],
        point_scores: list[PointScore],
        scored: dict[int, PointScore],
        pop_at_points: np.ndarray | None = None,
        empty_threshold: float = 0.0,
    ) -> list[PointScore]:
        if not scored or len(scored) == len(trajectory):
            return point_scores

        scored_indices = sorted(scored.keys())
        scores_arr = np.array([scored[i].engagement_score for i in scored_indices])
        hit_cas_arr = np.array([scored[i].hit_branch_expected_casualties for i in scored_indices])
        all_indices = np.arange(len(trajectory))
        interp_scores = np.interp(all_indices, scored_indices, scores_arr)
        interp_hit_cas = np.interp(all_indices, scored_indices, hit_cas_arr)

        result: list[PointScore] = []
        for i, ps in enumerate(point_scores):
            if i in scored:
                result.append(ps)
            elif pop_at_points is not None and pop_at_points[i] <= empty_threshold:
                result.append(ps)
            else:
                result.append(PointScore(
                    point_index=ps.point_index,
                    lat=ps.lat,
                    lon=ps.lon,
                    altitude_m=ps.altitude_m,
                    distance_from_start_m=ps.distance_from_start_m,
                    expected_casualties=float(interp_hit_cas[i]),
                    engagement_score=float(interp_scores[i]),
                    breakdown=ps.breakdown,
                    miss_branch_expected_casualties=ps.miss_branch_expected_casualties,
                    heading_deg=ps.heading_deg,
                    speed_m_s=ps.speed_m_s,
                    population_within_frag_radius=ps.population_within_frag_radius,
                    hit_branch_expected_casualties=float(interp_hit_cas[i]),
                ))
        return result
