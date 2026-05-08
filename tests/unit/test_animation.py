from __future__ import annotations

import folium
import pytest

from droneimpact.dashboard.components import (
    make_coloured_trajectory,
    prepare_animation_frames,
)


@pytest.fixture()
def sample_result() -> dict:
    return {
        "recommended_engagement": {
            "point_index": 1,
            "lat": 48.5,
            "lon": 35.1,
            "altitude_m": 500.0,
            "distance_from_current_m": 5000.0,
            "expected_casualties": 0.012,
            "engagement_score": 0.85,
            "reasoning": "Lowest casualties",
        },
        "trajectory_scores": [
            {
                "point_index": 0, "lat": 48.5, "lon": 35.0,
                "altitude_m": 500.0, "distance_from_current_m": 0.0,
                "expected_casualties": 0.1, "engagement_score": 0.5,
                "breakdown": {}, "miss_branch_expected_casualties": 0.0,
            },
            {
                "point_index": 1, "lat": 48.5, "lon": 35.1,
                "altitude_m": 500.0, "distance_from_current_m": 5000.0,
                "expected_casualties": 0.012, "engagement_score": 0.85,
                "breakdown": {}, "miss_branch_expected_casualties": 0.0,
            },
            {
                "point_index": 2, "lat": 48.5, "lon": 35.2,
                "altitude_m": 500.0, "distance_from_current_m": 10000.0,
                "expected_casualties": 0.08, "engagement_score": 0.6,
                "breakdown": {}, "miss_branch_expected_casualties": 0.0,
            },
        ],
        "impact_distributions": [],
        "metadata": {
            "n_trajectory_points": 3,
            "n_monte_carlo_samples": 100,
            "simulation_time_ms": 50.0,
            "population_dataset": "test",
            "infrastructure_dataset": "test",
        },
    }


class TestPrepareAnimationFrames:
    def test_frame_count(self, sample_result):
        frames = prepare_animation_frames(sample_result, speed_m_s=51.4)
        assert len(frames) == 3

    def test_first_frame_time_zero(self, sample_result):
        frames = prepare_animation_frames(sample_result, speed_m_s=51.4)
        assert frames[0]["time_s"] == 0.0

    def test_time_increases(self, sample_result):
        frames = prepare_animation_frames(sample_result, speed_m_s=51.4)
        times = [f["time_s"] for f in frames]
        assert times == sorted(times)
        assert times[-1] > 0

    def test_recommended_flag(self, sample_result):
        frames = prepare_animation_frames(sample_result, speed_m_s=51.4)
        recommended = [f for f in frames if f["is_recommended"]]
        assert len(recommended) == 1
        assert recommended[0]["point_index"] == 1

    def test_colour_is_hex(self, sample_result):
        frames = prepare_animation_frames(sample_result, speed_m_s=51.4)
        for f in frames:
            assert f["colour"].startswith("#")
            assert len(f["colour"]) == 7

    def test_empty_trajectory(self):
        result = {
            "recommended_engagement": {"point_index": 0},
            "trajectory_scores": [],
        }
        frames = prepare_animation_frames(result)
        assert frames == []

    def test_fields_present(self, sample_result):
        frames = prepare_animation_frames(sample_result)
        required = {"lat", "lon", "altitude_m", "distance_from_current_m",
                     "expected_casualties", "engagement_score", "is_recommended",
                     "colour", "time_s", "point_index"}
        for f in frames:
            assert required <= set(f.keys())


class TestColouredTrajectory:
    def test_returns_folium_map(self, sample_result):
        m = make_coloured_trajectory(sample_result)
        assert isinstance(m, folium.Map)

    def test_renders_html(self, sample_result):
        m = make_coloured_trajectory(sample_result)
        html = m._repr_html_()
        assert len(html) > 100

    def test_empty_trajectory(self):
        result = {
            "recommended_engagement": {
                "lat": 48.5, "lon": 35.0, "point_index": 0,
            },
            "trajectory_scores": [],
            "impact_distributions": [],
        }
        m = make_coloured_trajectory(result)
        assert isinstance(m, folium.Map)
