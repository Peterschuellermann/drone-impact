from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import httpx
import yaml

logger = logging.getLogger(__name__)


def get_api_endpoint() -> str:
    if url := os.environ.get("DRONEIMPACT_API_URL"):
        return url.rstrip("/")
    return "http://localhost:8000"


def call_api(drone_state: dict, n_monte_carlo_samples: int | None = None) -> dict:
    endpoint = get_api_endpoint()
    body: dict = {"trajectory": drone_state}
    if n_monte_carlo_samples is not None:
        body["n_monte_carlo_samples"] = n_monte_carlo_samples
    response = httpx.post(
        f"{endpoint}/analyze/single",
        json=body,
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()


def call_point_impact_api(point_state: dict) -> dict:
    """Call the point-impact endpoint for a single trajectory point."""
    endpoint = get_api_endpoint()
    response = httpx.post(
        f"{endpoint}/analyze/point-impact",
        json=point_state,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


SYNC_THRESHOLD = 5


def call_batch_api(
    drones: list[dict],
    on_progress: callable | None = None,
    timeout_s: float = 120.0,
) -> dict:
    endpoint = get_api_endpoint()
    force_async = len(drones) > SYNC_THRESHOLD
    payload = {"drones": drones, "async": force_async}

    response = httpx.post(
        f"{endpoint}/analyze/batch",
        json=payload,
        timeout=timeout_s,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("status") != "processing":
        return data

    batch_id = data["batch_id"]
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(2.0)
        poll = httpx.get(
            f"{endpoint}/analyze/batch/{batch_id}",
            timeout=30.0,
        )
        poll.raise_for_status()
        poll_data = poll.json()
        if on_progress:
            on_progress(poll_data.get("status", "processing"))
        if poll_data.get("status") != "processing":
            return poll_data

    raise TimeoutError(f"Batch {batch_id} did not complete within {timeout_s}s")


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


def load_scenarios(config_path: str | Path = "config.yaml") -> list[dict]:
    """Load demo scenarios from config.

    Returns list of dicts with keys: name, description, trajectory, max_range_m.
    Each trajectory dict has: lat, lon, altitude_m, heading_deg, speed_m_s.
    Returns an empty list if the config file is missing or has no scenarios.
    """
    path = Path(config_path)
    if not path.exists():
        logger.warning("Config file %s not found, no scenarios loaded", path)
        return []

    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
    except Exception:
        logger.warning("Failed to parse config file %s", path, exc_info=True)
        return []

    scenarios_raw = raw.get("scenarios", [])
    if not scenarios_raw:
        return []

    scenarios = []
    for s in scenarios_raw:
        scenarios.append({
            "name": s["name"],
            "description": s.get("description", ""),
            "trajectory": {
                "lat": float(s["trajectory"]["lat"]),
                "lon": float(s["trajectory"]["lon"]),
                "altitude_m": float(s["trajectory"]["altitude_m"]),
                "heading_deg": float(s["trajectory"]["heading_deg"]),
                "speed_m_s": float(s["trajectory"]["speed_m_s"]),
            },
            "max_range_m": s.get("max_range_m", 250_000),
        })

    return scenarios
