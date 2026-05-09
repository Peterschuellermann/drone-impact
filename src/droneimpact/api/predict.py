from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from droneimpact.api.schemas import (
    CandidateTrajectorySchema,
    PredictionMetadata,
    TargetPredictionRequest,
    TargetPredictionResponse,
    TargetSchema,
    WaypointSchema,
)
from droneimpact.prediction.targets import predict_targets

router = APIRouter(prefix="/predict")
logger = logging.getLogger(__name__)


@router.post("/targets", response_model=TargetPredictionResponse)
async def predict_targets_endpoint(request: Request, body: TargetPredictionRequest):
    strike_index = getattr(request.app.state, "strikes", None)
    if strike_index is None or strike_index.count == 0:
        raise HTTPException(status_code=400, detail="strike index not available")

    candidates, meta = predict_targets(
        lat=body.lat,
        lon=body.lon,
        heading_deg=body.heading_deg,
        speed_m_s=body.speed_m_s,
        altitude_m=body.altitude_m,
        strike_index=strike_index,
        max_range_m=body.max_range_m,
        max_targets=body.max_targets,
        min_hotspot_strikes=body.min_hotspot_strikes,
    )

    candidate_schemas = [
        CandidateTrajectorySchema(
            target=TargetSchema(
                lat=c.target.lat,
                lon=c.target.lon,
                name=c.target.location_name,
                historical_strikes=c.target.strike_count,
                category=c.target.category,
                radius_m=c.target.radius_m,
            ),
            probability=c.probability,
            heading_delta_deg=c.heading_delta_deg,
            distance_m=c.distance_m,
            waypoints=[
                WaypointSchema(
                    lat=wp.lat,
                    lon=wp.lon,
                    altitude_m=wp.altitude_m,
                    distance_from_start_m=wp.distance_from_start_m,
                    heading_deg=wp.heading_deg,
                    speed_m_s=wp.speed_m_s,
                )
                for wp in c.waypoints
            ],
        )
        for c in candidates
    ]

    return TargetPredictionResponse(
        candidates=candidate_schemas,
        metadata=PredictionMetadata(
            targets_considered=meta["targets_considered"],
            targets_reachable=meta["targets_reachable"],
            prediction_time_ms=meta["prediction_time_ms"],
        ),
    )
