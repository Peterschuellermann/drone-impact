from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response

from droneimpact.api.schemas import StrikeFeature, StrikeFeatureCollection

router = APIRouter(prefix="/data")
logger = logging.getLogger(__name__)


@router.get("/strikes", response_model=StrikeFeatureCollection)
async def get_strikes(
    request: Request,
    south: float | None = None,
    west: float | None = None,
    north: float | None = None,
    east: float | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> Response:
    bbox_params = [south, west, north, east]
    n_provided = sum(p is not None for p in bbox_params)

    if n_provided == 0:
        return StrikeFeatureCollection(
            type="FeatureCollection",
            features=[],
            metadata={"total": 0, "bbox": None, "filtered": 0},
        )

    if n_provided != 4:
        raise HTTPException(
            status_code=400,
            detail="bbox requires all four parameters: south, west, north, east",
        )

    strikes_index = getattr(request.app.state, "strikes", None)

    if strikes_index is None:
        logger.warning("Strike index not loaded — returning empty FeatureCollection")
        response = StrikeFeatureCollection(
            type="FeatureCollection",
            features=[],
            metadata={"total": 0, "bbox": [west, south, east, north], "filtered": 0},
        )
        return Response(
            content=response.model_dump_json(),
            media_type="application/json",
            headers={"X-Warning": "strike-index-not-loaded"},
        )

    results = strikes_index.query_bbox(south, west, north, east)

    if category is not None:
        results = [s for s in results if s.category == category]
    if date_from is not None:
        results = [s for s in results if s.date >= date_from]
    if date_to is not None:
        results = [s for s in results if s.date <= date_to]

    features = [
        StrikeFeature(
            type="Feature",
            geometry={"type": "Point", "coordinates": [s.lon, s.lat]},
            properties={
                "id": s.id,
                "date": s.date,
                "source": s.source,
                "location_name": s.location_name,
                "category": s.category,
                "description": s.description,
                "confidence": s.confidence,
            },
        )
        for s in results
    ]

    return StrikeFeatureCollection(
        type="FeatureCollection",
        features=features,
        metadata={
            "total": strikes_index.count,
            "bbox": [west, south, east, north],
            "filtered": len(features),
        },
    )
