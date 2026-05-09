from __future__ import annotations

import math
import time
from dataclasses import dataclass

from droneimpact.data.strikes import StrikeHotspot
from droneimpact.physics.trajectory import discretise_trajectory
from droneimpact.physics.types import StateVector, TrajectoryPoint


@dataclass
class CandidateTrajectory:
    target: StrikeHotspot
    probability: float
    heading_delta_deg: float
    distance_m: float
    waypoints: list[TrajectoryPoint]


_CATEGORY_WEIGHT = {
    "energy": 1.0,
    "military": 1.0,
    "industrial": 0.6,
    "residential": 0.4,
    "unknown": 0.3,
}

MAX_TURN_DEG = 150.0
HEAVY_PENALTY_DEG = 90.0


def _great_circle_bearing(lat1_deg, lon1_deg, lat2_deg, lon2_deg) -> float:
    """Initial bearing from point 1 to point 2 (compass degrees, 0=north, CW)."""
    lat1 = math.radians(lat1_deg); lat2 = math.radians(lat2_deg)
    dlon = math.radians(lon2_deg - lon1_deg)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(x, y)) % 360


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1; dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def predict_targets(
    lat: float,
    lon: float,
    heading_deg: float,
    speed_m_s: float,
    altitude_m: float,
    strike_index,
    max_range_m: float = 250_000,
    max_targets: int = 20,
    evaluation_spacing_m: float = 500.0,
    min_hotspot_strikes: int = 2,
) -> tuple[list[CandidateTrajectory], dict]:
    """Return (candidates ranked by probability, metadata dict)."""
    t_start = time.perf_counter()

    hotspots = strike_index.get_hotspots(min_strikes=min_hotspot_strikes)
    targets_considered = len(hotspots)

    reachable: list[tuple[StrikeHotspot, float, float, float]] = []

    for hotspot in hotspots:
        bearing = _great_circle_bearing(lat, lon, hotspot.lat, hotspot.lon)
        distance = _haversine_m(lat, lon, hotspot.lat, hotspot.lon)

        if distance > max_range_m:
            continue

        delta = abs(((bearing - heading_deg + 180) % 360) - 180)

        if delta > MAX_TURN_DEG:
            continue

        heading_score = math.cos(math.radians(delta) / 2)
        recurrence_score = float(hotspot.strike_count)
        distance_score = 1.0 - (distance / max_range_m)
        category_score = _CATEGORY_WEIGHT.get(hotspot.category, 0.3)

        reachable.append((hotspot, delta, distance, heading_score, recurrence_score, distance_score, category_score))

    targets_reachable = len(reachable)

    if not reachable:
        elapsed_ms = (time.perf_counter() - t_start) * 1000
        return [], {
            "targets_considered": targets_considered,
            "targets_reachable": 0,
            "prediction_time_ms": elapsed_ms,
        }

    max_strikes = max(r[4] for r in reachable)

    scored: list[tuple[float, StrikeHotspot, float, float]] = []
    for hotspot, delta, distance, heading_score, recurrence_score, distance_score, category_score in reachable:
        recurrence_norm = recurrence_score / max_strikes if max_strikes > 0 else 0.0
        raw = (0.40 * heading_score + 0.30 * recurrence_norm
               + 0.20 * distance_score + 0.10 * category_score)
        if delta > HEAVY_PENALTY_DEG:
            raw *= 0.3
        scored.append((raw, hotspot, delta, distance))

    total_raw = sum(s[0] for s in scored)
    scored_norm = [
        (raw / total_raw, hotspot, delta, distance)
        for raw, hotspot, delta, distance in scored
    ]

    scored_norm.sort(key=lambda x: -x[0])
    top = scored_norm[:max_targets]

    candidates: list[CandidateTrajectory] = []
    for probability, hotspot, delta, distance in top:
        target_heading = _great_circle_bearing(lat, lon, hotspot.lat, hotspot.lon)
        sv = StateVector(
            lat=lat,
            lon=lon,
            altitude_m=altitude_m,
            heading_deg=target_heading,
            speed_m_s=speed_m_s,
        )
        waypoints = discretise_trajectory(sv, evaluation_spacing_m, distance)
        candidates.append(CandidateTrajectory(
            target=hotspot,
            probability=probability,
            heading_delta_deg=delta,
            distance_m=distance,
            waypoints=waypoints,
        ))

    elapsed_ms = (time.perf_counter() - t_start) * 1000
    return candidates, {
        "targets_considered": targets_considered,
        "targets_reachable": targets_reachable,
        "prediction_time_ms": elapsed_ms,
    }
