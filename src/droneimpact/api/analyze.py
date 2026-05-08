from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from droneimpact.api import get_app_state
from droneimpact.api.schemas import (
    EngagementZoneSchema,
    ImpactDistributionSchema,
    ImpactEllipseSchema,
    MetadataSchema,
    ModeBreakdown,
    RecommendedEngagementSchema,
    SingleDroneRequest,
    SingleDroneResponse,
    TrajectoryPointScore,
)
from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.physics.trajectory import discretise_trajectory
from droneimpact.physics.types import StateVector
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
    )
