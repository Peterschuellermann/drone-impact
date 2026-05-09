"""Tests for demo scenario loading and validation."""

from __future__ import annotations

import math

import pytest

from droneimpact.config import AppConfig, load_config
from droneimpact.dashboard.utils import load_scenarios


# Target city centres for heading validation
TARGET_CITIES = {
    "Kyiv": (50.4501, 30.5234),
    "Kharkiv": (49.9935, 36.2304),
    "Mykolaiv": (46.975, 31.9946),
    "Dnipro": (48.4647, 35.0462),
    "Odesa": (46.4825, 30.7233),
}


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute initial bearing in degrees from (lat1, lon1) to (lat2, lon2)."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    )
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _angular_diff(a: float, b: float) -> float:
    """Smallest unsigned angle between two bearings in degrees."""
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


def _target_for_scenario(name: str) -> tuple[float, float] | None:
    """Extract the target city from a scenario name like 'X -> CityName'."""
    for city, coords in TARGET_CITIES.items():
        if city.lower() in name.lower():
            return coords
    return None


@pytest.fixture
def scenarios():
    return load_scenarios("config.yaml")


@pytest.fixture
def config_with_scenarios():
    return load_config("config.yaml")


def test_scenarios_load_from_config(scenarios):
    """All scenarios parse without error and there are at least 6."""
    assert len(scenarios) >= 6
    for s in scenarios:
        assert "name" in s
        assert "description" in s
        assert "trajectory" in s
        traj = s["trajectory"]
        assert "lat" in traj
        assert "lon" in traj
        assert "altitude_m" in traj
        assert "heading_deg" in traj
        assert "speed_m_s" in traj
        assert "max_range_m" in s


def test_scenarios_parse_into_config_model(config_with_scenarios):
    """Scenarios parse into ScenarioConfig models via AppConfig."""
    assert isinstance(config_with_scenarios, AppConfig)
    assert len(config_with_scenarios.scenarios) >= 6
    for sc in config_with_scenarios.scenarios:
        assert sc.name
        assert sc.trajectory.altitude_m > 0
        assert sc.trajectory.speed_m_s > 0


def test_scenario_coordinates_in_bounds(scenarios):
    """Start positions are within plausible geographic bounds (44-55 N, 22-41 E)."""
    for s in scenarios:
        traj = s["trajectory"]
        assert 44.0 <= traj["lat"] <= 55.0, (
            f"Scenario '{s['name']}' lat {traj['lat']} out of bounds"
        )
        assert 22.0 <= traj["lon"] <= 41.0, (
            f"Scenario '{s['name']}' lon {traj['lon']} out of bounds"
        )


def test_scenario_headings_toward_target(scenarios):
    """Each scenario heading roughly points toward the named target city (within +/- 30 degrees)."""
    for s in scenarios:
        target = _target_for_scenario(s["name"])
        if target is None:
            continue  # skip if target city not recognized
        traj = s["trajectory"]
        expected_bearing = _bearing(traj["lat"], traj["lon"], target[0], target[1])
        actual_heading = traj["heading_deg"]
        diff = _angular_diff(expected_bearing, actual_heading)
        assert diff <= 30.0, (
            f"Scenario '{s['name']}': heading {actual_heading} vs computed bearing "
            f"{expected_bearing:.1f} (diff {diff:.1f} > 30)"
        )


def test_scenario_names_unique(scenarios):
    """No duplicate scenario names."""
    names = [s["name"] for s in scenarios]
    assert len(names) == len(set(names)), f"Duplicate names found: {names}"


def test_load_scenarios_missing_file():
    """Returns empty list when config file does not exist."""
    result = load_scenarios("/nonexistent/path/config.yaml")
    assert result == []


def test_load_scenarios_no_scenarios_key(tmp_path):
    """Returns empty list when config has no scenarios key."""
    cfg_file = tmp_path / "no_scenarios.yaml"
    cfg_file.write_text("version: '1.0'\n")
    result = load_scenarios(str(cfg_file))
    assert result == []
