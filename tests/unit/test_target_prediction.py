from __future__ import annotations

import math

import pytest

from droneimpact.data.strikes import StrikeHotspot
from droneimpact.prediction.targets import (
    MAX_TURN_DEG,
    predict_targets,
)


def _make_hotspot(lat, lon, category, strike_count, location_name="Test") -> StrikeHotspot:
    return StrikeHotspot(
        lat=lat,
        lon=lon,
        strike_count=strike_count,
        category=category,
        location_name=location_name,
        radius_m=500.0,
    )


class _MockStrikeIndex:
    def __init__(self, hotspots: list[StrikeHotspot]):
        self._hotspots = hotspots
        self.count = len(hotspots)

    def get_hotspots(self, min_strikes: int = 1, cluster_radius_m: float = 500.0) -> list[StrikeHotspot]:
        return self._hotspots


def _make_index(hotspots: list[StrikeHotspot]) -> _MockStrikeIndex:
    return _MockStrikeIndex(hotspots)


def test_kyiv_ranks_top_from_bryansk():
    kyiv = _make_hotspot(50.45, 30.52, "energy", 47, "Kyiv")
    kharkiv = _make_hotspot(49.99, 36.23, "residential", 5, "Kharkiv")
    # NE of drone at (52, 33.5) heading 230° SW — bearing ~45° gives delta ~175° > MAX_TURN_DEG
    behind = _make_hotspot(53.5, 35.5, "energy", 10, "Behind")

    index = _make_index([kyiv, kharkiv, behind])
    candidates, meta = predict_targets(
        lat=52.0, lon=33.5, heading_deg=230.0, speed_m_s=185.0, altitude_m=100.0,
        strike_index=index,
        max_range_m=1_000_000,
        max_targets=20,
        min_hotspot_strikes=2,
    )

    names = [c.target.location_name for c in candidates]
    assert "Kyiv" in names[:3]

    behind_names = [c.target.location_name for c in candidates]
    assert "Behind" not in behind_names


def test_probabilities_sum_to_one():
    hotspots = [
        _make_hotspot(49.0, 30.0, "energy", 10, f"T{i}")
        for i in range(5)
    ]
    index = _make_index(hotspots)
    candidates, _ = predict_targets(
        lat=52.0, lon=33.5, heading_deg=230.0, speed_m_s=185.0, altitude_m=100.0,
        strike_index=index,
        max_range_m=1_000_000,
        min_hotspot_strikes=2,
    )
    assert len(candidates) > 0
    total = sum(c.probability for c in candidates)
    assert math.isclose(total, 1.0, abs_tol=1e-6)


def test_out_of_range_excluded():
    far = _make_hotspot(10.0, 10.0, "energy", 10, "FarAway")
    near = _make_hotspot(49.5, 31.0, "energy", 5, "Near")
    index = _make_index([far, near])
    candidates, _ = predict_targets(
        lat=52.0, lon=33.5, heading_deg=230.0, speed_m_s=185.0, altitude_m=100.0,
        strike_index=index,
        max_range_m=500_000,
        min_hotspot_strikes=2,
    )
    names = [c.target.location_name for c in candidates]
    assert "FarAway" not in names


def test_heading_alignment_dominant():
    straight_ahead = _make_hotspot(49.5, 31.5, "energy", 5, "StraightAhead")
    off_45 = _make_hotspot(49.8, 35.5, "energy", 5, "Off45")
    index = _make_index([straight_ahead, off_45])
    candidates, _ = predict_targets(
        lat=52.0, lon=33.5, heading_deg=220.0, speed_m_s=185.0, altitude_m=100.0,
        strike_index=index,
        max_range_m=1_000_000,
        min_hotspot_strikes=2,
    )
    assert len(candidates) >= 2
    names = [c.target.location_name for c in candidates]
    assert names[0] == "StraightAhead"


def test_high_recurrence_boosts_rank():
    high = _make_hotspot(49.5, 31.0, "energy", 50, "HighRecurrence")
    low = _make_hotspot(49.6, 31.1, "energy", 1, "LowRecurrence")
    index = _make_index([high, low])
    candidates, _ = predict_targets(
        lat=52.0, lon=33.5, heading_deg=220.0, speed_m_s=185.0, altitude_m=100.0,
        strike_index=index,
        max_range_m=1_000_000,
        min_hotspot_strikes=1,
    )
    assert len(candidates) >= 2
    assert candidates[0].target.location_name == "HighRecurrence"


def test_behind_target_excluded():
    # 160° turn needed — must be excluded since MAX_TURN_DEG = 150
    # Drone at (52, 33.5) heading 230. A target roughly NE (50° bearing) is ~180° away
    behind = _make_hotspot(54.0, 36.0, "energy", 10, "Behind160")
    index = _make_index([behind])
    candidates, meta = predict_targets(
        lat=52.0, lon=33.5, heading_deg=230.0, speed_m_s=185.0, altitude_m=100.0,
        strike_index=index,
        max_range_m=1_000_000,
        min_hotspot_strikes=2,
    )
    assert len(candidates) == 0


def test_waypoints_valid():
    hotspot = _make_hotspot(49.5, 31.0, "energy", 5, "T1")
    index = _make_index([hotspot])
    candidates, _ = predict_targets(
        lat=52.0, lon=33.5, heading_deg=220.0, speed_m_s=185.0, altitude_m=100.0,
        strike_index=index,
        max_range_m=1_000_000,
        min_hotspot_strikes=2,
    )
    assert len(candidates) == 1
    waypoints = candidates[0].waypoints
    assert len(waypoints) > 0
    for wp in waypoints:
        assert -90 <= wp.lat <= 90
        assert -180 <= wp.lon <= 180
        assert wp.distance_from_start_m >= 0
    distances = [wp.distance_from_start_m for wp in waypoints]
    assert distances == sorted(distances)


def test_max_targets_respected():
    hotspots = [
        _make_hotspot(49.0 + i * 0.05, 30.0 + i * 0.02, "energy", 5 + i, f"T{i}")
        for i in range(30)
    ]
    index = _make_index(hotspots)
    candidates, _ = predict_targets(
        lat=52.0, lon=33.5, heading_deg=220.0, speed_m_s=185.0, altitude_m=100.0,
        strike_index=index,
        max_range_m=1_000_000,
        max_targets=10,
        min_hotspot_strikes=2,
    )
    assert len(candidates) <= 10


def test_empty_strike_index():
    index = _make_index([])
    candidates, meta = predict_targets(
        lat=52.0, lon=33.5, heading_deg=220.0, speed_m_s=185.0, altitude_m=100.0,
        strike_index=index,
        max_range_m=1_000_000,
        min_hotspot_strikes=2,
    )
    assert candidates == []
    assert meta["targets_reachable"] == 0


def test_heavy_penalty_applied():
    # Target at ~95° delta (nearly perpendicular)
    # Drone heading 220°, so a target at bearing ~315° (NW) → delta ~95°
    penalised = _make_hotspot(53.5, 30.0, "energy", 5, "Penalised")
    # Target nearly straight ahead: bearing ~220° from (52, 33.5)
    straight = _make_hotspot(49.5, 31.0, "energy", 5, "Straight")
    index = _make_index([penalised, straight])
    candidates, _ = predict_targets(
        lat=52.0, lon=33.5, heading_deg=220.0, speed_m_s=185.0, altitude_m=100.0,
        strike_index=index,
        max_range_m=1_000_000,
        min_hotspot_strikes=2,
    )
    assert len(candidates) >= 2
    straight_prob = next(c.probability for c in candidates if c.target.location_name == "Straight")
    penalised_prob = next(c.probability for c in candidates if c.target.location_name == "Penalised")
    assert straight_prob > penalised_prob
