from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

import numpy as np

from droneimpact.api import get_app_state
from droneimpact.api.schemas import (
    EngagementZoneSchema,
    ImpactDistributionSchema,
    ImpactEllipseSchema,
    MetadataSchema,
    ModeBreakdown,
    PointImpactModeResult,
    PointImpactRequest,
    PointImpactResponse,
    RecommendedEngagementSchema,
    RiskZoneSchema,
    SingleDroneRequest,
    SingleDroneResponse,
    TrajectoryPointScore,
)
from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.physics.trajectory import discretise_trajectory
from droneimpact.physics.types import StateVector, TrajectoryPoint
from droneimpact.scoring.ellipse import compute_combined_danger_zone
from droneimpact.scoring.engine import ScoringEngine
from droneimpact.scoring.types import TrajectoryResult

router = APIRouter(prefix="/analyze")


@router.post("/single", response_model=SingleDroneResponse)
def analyze_single(body: SingleDroneRequest, request: Request) -> SingleDroneResponse:
    state = get_app_state(request)
    if not state.data_loaded:
        raise HTTPException(status_code=503, detail="Data not loaded. Check /health.")

    t_start = time.perf_counter()

    sv = StateVector(
        lat=body.trajectory.lat,
        lon=body.trajectory.lon,
        altitude_m=body.trajectory.altitude_m,
        heading_deg=body.trajectory.heading_deg,
        speed_m_s=body.trajectory.speed_m_s,
    )
    trajectory = discretise_trajectory(
        sv,
        spacing_m=body.evaluation_spacing_m,
        max_range_m=body.max_range_m,
    )

    casualty_engine = CasualtyEngine(
        population=state.population,
        infrastructure=state.infrastructure,
        config=state.config.casualty,
    )
    scoring_engine = ScoringEngine(config=state.config)

    result = scoring_engine.score_trajectory(
        trajectory=trajectory,
        dem=state.dem,
        casualty_engine=casualty_engine,
        intercept_point_origin=(sv.lat, sv.lon),
    )

    elapsed_ms = (time.perf_counter() - t_start) * 1000

    return _build_response(body, result, elapsed_ms, state)


@router.post("/point-impact", response_model=PointImpactResponse)
def analyze_point_impact(body: PointImpactRequest, request: Request) -> PointImpactResponse:
    """Compute impact distribution for a single trajectory point."""
    state = get_app_state(request)
    if not state.data_loaded:
        raise HTTPException(status_code=503, detail="Data not loaded. Check /health.")

    t_start = time.perf_counter()

    pt = TrajectoryPoint(
        index=0,
        lat=body.lat,
        lon=body.lon,
        altitude_m=body.altitude_m,
        distance_from_start_m=0.0,
        heading_deg=body.heading_deg,
        speed_m_s=body.speed_m_s,
    )

    agl = state.dem.msl_to_agl(pt.lat, pt.lon, pt.altitude_m)

    casualty_engine = CasualtyEngine(
        population=state.population,
        infrastructure=state.infrastructure,
        config=state.config.casualty,
    )
    scoring_engine = ScoringEngine(config=state.config)
    n_samples = state.config.physics.n_monte_carlo_samples
    rng = np.random.default_rng()

    ps, dists = scoring_engine._score_point(
        pt, agl, n_samples, casualty_engine,
        miss_casualties=0.0,
        rng=rng,
        compute_ellipses=True,
    )

    modes: dict[str, PointImpactModeResult] = {}
    ellipses = []
    for d in dists:
        ellipses.append(d.impact_ellipse)
        mode_score = ps.breakdown.get(d.mode)
        modes[d.mode] = PointImpactModeResult(
            weight=mode_score.weight if mode_score else 0.0,
            expected_casualties=mode_score.expected_casualties if mode_score else 0.0,
            cep_m=mode_score.cep_m if mode_score else 0.0,
            impact_ellipse=ImpactEllipseSchema(
                centre_lat=d.impact_ellipse.centre_lat,
                centre_lon=d.impact_ellipse.centre_lon,
                semi_major_m=d.impact_ellipse.semi_major_m,
                semi_minor_m=d.impact_ellipse.semi_minor_m,
                orientation_deg=d.impact_ellipse.orientation_deg,
            ),
        )

    combined = compute_combined_danger_zone(ellipses)

    elapsed_ms = (time.perf_counter() - t_start) * 1000

    return PointImpactResponse(
        modes=modes,
        combined_danger_zone=combined,
        metadata={
            "n_monte_carlo_samples": n_samples,
            "simulation_time_ms": elapsed_ms,
        },
    )


def _build_response(
    req: SingleDroneRequest,
    result: TrajectoryResult,
    elapsed_ms: float,
    state,
) -> SingleDroneResponse:
    rec = result.recommended_engagement
    recommended = RecommendedEngagementSchema(
        point_index=rec.point_index,
        lat=rec.lat,
        lon=rec.lon,
        altitude_m=rec.altitude_m,
        distance_from_current_m=rec.distance_from_current_m,
        expected_casualties=rec.expected_casualties,
        engagement_score=rec.engagement_score,
        reasoning=rec.reasoning,
    )

    scores = [
        TrajectoryPointScore(
            point_index=ps.point_index,
            lat=ps.lat,
            lon=ps.lon,
            altitude_m=ps.altitude_m,
            distance_from_current_m=ps.distance_from_start_m,
            heading_deg=ps.heading_deg,
            speed_m_s=ps.speed_m_s,
            expected_casualties=ps.expected_casualties,
            engagement_score=ps.engagement_score,
            breakdown={
                k: ModeBreakdown(
                    weight=v.weight,
                    expected_casualties=v.expected_casualties,
                    cep_m=v.cep_m,
                )
                for k, v in ps.breakdown.items()
            },
            miss_branch_expected_casualties=ps.miss_branch_expected_casualties,
            hit_branch_expected_casualties=ps.hit_branch_expected_casualties,
            high_risk=ps.high_risk,
        )
        for ps in result.trajectory_scores
    ]

    dists = [
        ImpactDistributionSchema(
            point_index=d.point_index,
            mode=d.mode,
            impact_ellipse=ImpactEllipseSchema(
                centre_lat=d.impact_ellipse.centre_lat,
                centre_lon=d.impact_ellipse.centre_lon,
                semi_major_m=d.impact_ellipse.semi_major_m,
                semi_minor_m=d.impact_ellipse.semi_minor_m,
                orientation_deg=d.impact_ellipse.orientation_deg,
            ),
        )
        for d in result.impact_distributions
    ]

    zones = None
    if result.engagement_zones:
        zones = [
            EngagementZoneSchema(
                classification=z.classification,
                start_index=z.start_index,
                end_index=z.end_index,
                start_distance_m=z.start_distance_m,
                end_distance_m=z.end_distance_m,
                start_lat=z.start_lat,
                start_lon=z.start_lon,
                end_lat=z.end_lat,
                end_lon=z.end_lon,
                peak_expected_casualties=z.peak_expected_casualties,
                mean_expected_casualties=z.mean_expected_casualties,
                population_in_zone=z.population_in_zone,
                reasons=z.reasons,
            )
            for z in result.engagement_zones
        ]

    risk_zones = [
        RiskZoneSchema(
            start_index=rz.start_index,
            end_index=rz.end_index,
            start_distance_m=rz.start_distance_m,
            end_distance_m=rz.end_distance_m,
            peak_expected_casualties=rz.peak_expected_casualties,
        )
        for rz in result.risk_zones
    ]

    unconstrained_optimum = None
    if result.unconstrained_optimum is not None:
        uo = result.unconstrained_optimum
        unconstrained_optimum = RecommendedEngagementSchema(
            point_index=uo.point_index,
            lat=uo.lat,
            lon=uo.lon,
            altitude_m=uo.altitude_m,
            distance_from_current_m=uo.distance_from_current_m,
            expected_casualties=uo.expected_casualties,
            engagement_score=uo.engagement_score,
            reasoning=uo.reasoning,
        )

    return SingleDroneResponse(
        drone_id=req.drone_id,
        computed_at_utc=datetime.now(timezone.utc).isoformat(),
        recommended_engagement=recommended,
        trajectory_scores=scores,
        impact_distributions=dists,
        metadata=MetadataSchema(
            n_trajectory_points=result.metadata["n_trajectory_points"],
            n_monte_carlo_samples=result.metadata["n_monte_carlo_samples"],
            simulation_time_ms=elapsed_ms,
            population_dataset=state.config.data.population_path,
            infrastructure_dataset=state.config.data.infrastructure_path,
            n_points_skipped=result.metadata.get("n_points_skipped"),
            n_points_dense=result.metadata.get("n_points_dense"),
        ),
        engagement_zones=zones,
        risk_zones=risk_zones,
        unconstrained_optimum=unconstrained_optimum,
    )
