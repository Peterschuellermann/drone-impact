from __future__ import annotations

import json
import os

import httpx


def get_api_endpoint() -> str:
    if url := os.environ.get("DRONEIMPACT_API_URL"):
        return url.rstrip("/")
    return "http://localhost:8000"


def call_api(drone_state: dict) -> dict:
    endpoint = get_api_endpoint()
    response = httpx.post(
        f"{endpoint}/analyze/single",
        json={"trajectory": drone_state},
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()


def format_casualties(num: float) -> str:
    if num < 0.01:
        return "< 0.01"
    return f"{num:.2f}"


def format_distance(m: float) -> str:
    if m >= 1000:
        return f"{m / 1000:.1f} km"
    return f"{m:.0f} m"


def export_geojson(result: dict) -> str:
    features = []

    coords = [
        [pt["lon"], pt["lat"]] for pt in result["trajectory_scores"]
    ]
    features.append(
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"type": "trajectory"},
        }
    )

    for pt in result["trajectory_scores"]:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [pt["lon"], pt["lat"]],
                },
                "properties": {
                    "type": "evaluation_point",
                    "point_index": pt["point_index"],
                    "distance_from_current_m": pt["distance_from_current_m"],
                    "expected_casualties": pt["expected_casualties"],
                    "engagement_score": pt["engagement_score"],
                },
            }
        )

    rec = result["recommended_engagement"]
    features.append(
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [rec["lon"], rec["lat"]],
            },
            "properties": {
                "type": "recommended_engagement",
                "expected_casualties": rec["expected_casualties"],
                "engagement_score": rec["engagement_score"],
                "reasoning": rec["reasoning"],
            },
        }
    )

    collection = {"type": "FeatureCollection", "features": features}
    return json.dumps(collection, indent=2)
