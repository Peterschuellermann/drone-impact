from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from droneimpact.api import get_app_state

router = APIRouter(prefix="/data")
logger = logging.getLogger(__name__)


@router.get("/infrastructure")
def get_infrastructure(
    request: Request,
    south: float = Query(ge=-90, le=90),
    west: float = Query(ge=-180, le=180),
    north: float = Query(ge=-90, le=90),
    east: float = Query(ge=-180, le=180),
    categories: str | None = None,
) -> dict:
    state = get_app_state(request)
    if not state.data_loaded:
        raise HTTPException(status_code=503, detail="Data not loaded.")

    cat_filter = None
    if categories:
        cat_filter = [c.strip() for c in categories.split(",") if c.strip()]

    features = state.infrastructure.get_features_in_bbox(
        south, west, north, east, categories=cat_filter,
    )

    result: dict[str, list[list[float]]] = {}
    for cat, arr in features.items():
        result[cat] = arr.tolist()

    return {
        "features": result,
        "counts": state.infrastructure.feature_counts(),
        "bbox": [south, west, north, east],
    }
