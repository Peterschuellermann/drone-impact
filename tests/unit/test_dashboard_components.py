from __future__ import annotations

import json

import plotly.graph_objects as go
import pytest

from droneimpact.dashboard.components import (
    compute_fallout_bounds,
    make_impact_scatter,
    make_risk_profile,
    make_stats_panel,
    make_trajectory_map,
    parse_point_index_from_tooltip,
)
from droneimpact.dashboard.utils import export_geojson, format_casualties, format_distance


@pytest.fixture()
def sample_result() -> dict:
    return {
        "drone_id": "test-001",
        "computed_at_utc": "2025-01-01T00:00:00Z",
        "recommended_engagement": {
            "point_index": 1,
            "lat": 48.5,
            "lon": 35.1,
            "altitude_m": 500.0,
            "distance_from_current_m": 5000.0,
            "expected_casualties": 0.012,
            "engagement_score": 0.85,
            "reasoning": "Lowest expected casualties in low-density area",
        },
        "trajectory_scores": [
            {
                "point_index": 0,
                "lat": 48.5,
                "lon": 35.0,
                "altitude_m": 500.0,
                "distance_from_current_m": 0.0,
                "expected_casualties": 0.1,
                "engagement_score": 0.5,
                "breakdown": {
                    "propulsion_loss": {"weight": 0.4, "expected_casualties": 0.04, "cep_m": 200},
                    "loss_of_control": {"weight": 0.35, "expected_casualties": 0.03, "cep_m": 500},
                    "break_apart": {"weight": 0.25, "expected_casualties": 0.03, "cep_m": 150},
                },
                "miss_branch_expected_casualties": 0.05,
            },
            {
                "point_index": 1,
                "lat": 48.5,
                "lon": 35.1,
                "altitude_m": 500.0,
                "distance_from_current_m": 5000.0,
                "expected_casualties": 0.012,
                "engagement_score": 0.85,
                "breakdown": {
                    "propulsion_loss": {"weight": 0.4, "expected_casualties": 0.005, "cep_m": 200},
                    "loss_of_control": {"weight": 0.35, "expected_casualties": 0.004, "cep_m": 500},
                    "break_apart": {"weight": 0.25, "expected_casualties": 0.003, "cep_m": 150},
                },
                "miss_branch_expected_casualties": 0.02,
            },
            {
                "point_index": 2,
                "lat": 48.5,
                "lon": 35.2,
                "altitude_m": 500.0,
                "distance_from_current_m": 10000.0,
                "expected_casualties": 0.08,
                "engagement_score": 0.6,
                "breakdown": {
                    "propulsion_loss": {"weight": 0.4, "expected_casualties": 0.03, "cep_m": 200},
                    "loss_of_control": {"weight": 0.35, "expected_casualties": 0.03, "cep_m": 500},
                    "break_apart": {"weight": 0.25, "expected_casualties": 0.02, "cep_m": 150},
                },
                "miss_branch_expected_casualties": 0.04,
            },
        ],
        "impact_distributions": [
            {
                "point_index": 1,
                "mode": "propulsion_loss",
                "impact_ellipse": {
                    "centre_lat": 48.50,
                    "centre_lon": 35.10,
                    "semi_major_m": 300.0,
                    "semi_minor_m": 150.0,
                    "orientation_deg": 45.0,
                },
            },
            {
                "point_index": 1,
                "mode": "loss_of_control",
                "impact_ellipse": {
                    "centre_lat": 48.51,
                    "centre_lon": 35.11,
                    "semi_major_m": 800.0,
                    "semi_minor_m": 400.0,
                    "orientation_deg": 90.0,
                },
            },
        ],
        "metadata": {
            "n_trajectory_points": 3,
            "n_monte_carlo_samples": 10000,
            "simulation_time_ms": 123.4,
            "population_dataset": "./data/kontur_ukraine.gpkg",
            "infrastructure_dataset": "./data/ukraine_infra.geojson",
        },
    }


class TestTrajectoryMap:
    def test_returns_folium_map(self, sample_result):
        import folium
        m = make_trajectory_map(sample_result)
        assert isinstance(m, folium.Map)

    def test_map_renders_html(self, sample_result):
        m = make_trajectory_map(sample_result)
        html = m._repr_html_()
        assert "OpenStreetMap" in html or "leaflet" in html.lower()

    def test_empty_distributions(self, sample_result):
        sample_result["impact_distributions"] = []
        m = make_trajectory_map(sample_result)
        assert m is not None

    def test_selected_point_renders(self, sample_result):
        import folium
        m = make_trajectory_map(sample_result, selected_point_idx=0)
        assert isinstance(m, folium.Map)

    def test_selected_point_none_renders(self, sample_result):
        import folium
        m = make_trajectory_map(sample_result, selected_point_idx=None)
        assert isinstance(m, folium.Map)


class TestParsePointIndex:
    def test_valid_tooltip(self):
        tooltip = "Point 5 | Dist: 2500 m | Casualties: 0.012 | Score: 0.850"
        assert parse_point_index_from_tooltip(tooltip) == 5

    def test_zero_index(self):
        assert parse_point_index_from_tooltip("Point 0 | Dist: 0 m") == 0

    def test_none_input(self):
        assert parse_point_index_from_tooltip(None) is None

    def test_non_point_tooltip(self):
        assert parse_point_index_from_tooltip("Start") is None

    def test_recommended_tooltip(self):
        assert parse_point_index_from_tooltip("RECOMMENDED | Casualties: 0.01") is None

    def test_empty_string(self):
        assert parse_point_index_from_tooltip("") is None


class TestFalloutBounds:
    def test_bounds_structure(self):
        bounds = compute_fallout_bounds(48.5, 35.0, {"modes": {}})
        assert len(bounds) == 2
        assert len(bounds[0]) == 2
        assert len(bounds[1]) == 2
        assert bounds[0][0] < bounds[1][0]
        assert bounds[0][1] < bounds[1][1]

    def test_bounds_expand_with_ellipses(self):
        small = compute_fallout_bounds(48.5, 35.0, {"modes": {}})
        large = compute_fallout_bounds(48.5, 35.0, {
            "modes": {
                "propulsion_loss": {
                    "impact_ellipse": {
                        "centre_lat": 48.5,
                        "centre_lon": 35.0,
                        "semi_major_m": 5000.0,
                    },
                },
            },
        })
        small_span = (small[1][0] - small[0][0]) * (small[1][1] - small[0][1])
        large_span = (large[1][0] - large[0][0]) * (large[1][1] - large[0][1])
        assert large_span > small_span


class TestImpactScatter:
    def test_returns_plotly_figure(self, sample_result):
        fig = make_impact_scatter(sample_result)
        assert isinstance(fig, go.Figure)

    def test_has_traces(self, sample_result):
        fig = make_impact_scatter(sample_result)
        assert len(fig.data) > 0

    def test_no_distributions(self, sample_result):
        sample_result["impact_distributions"] = []
        fig = make_impact_scatter(sample_result)
        assert len(fig.data) >= 1


class TestRiskProfile:
    def test_returns_plotly_figure(self, sample_result):
        fig = make_risk_profile(sample_result)
        assert isinstance(fig, go.Figure)

    def test_has_two_traces(self, sample_result):
        fig = make_risk_profile(sample_result)
        assert len(fig.data) == 2

    def test_x_axis_label(self, sample_result):
        fig = make_risk_profile(sample_result)
        title = fig.layout.xaxis.title
        assert title.text == "Distance (km)" or title == "Distance (km)"


class TestStatsPanel:
    def test_returns_markdown(self, sample_result):
        md = make_stats_panel(sample_result)
        assert "### Recommended Engagement" in md

    def test_contains_mode_breakdown(self, sample_result):
        md = make_stats_panel(sample_result)
        assert "Propulsion Loss" in md
        assert "Loss of Control" in md

    def test_contains_simulation_info(self, sample_result):
        md = make_stats_panel(sample_result)
        assert "10000" in md
        assert "123" in md


class TestFormatHelpers:
    def test_format_casualties_normal(self):
        assert format_casualties(0.1234) == "0.12"

    def test_format_casualties_tiny(self):
        assert format_casualties(0.001) == "< 0.01"

    def test_format_distance_meters(self):
        assert format_distance(500.0) == "500 m"

    def test_format_distance_km(self):
        assert format_distance(5000.0) == "5.0 km"


class TestExportGeoJSON:
    def test_valid_geojson(self, sample_result):
        geojson_str = export_geojson(sample_result)
        data = json.loads(geojson_str)
        assert data["type"] == "FeatureCollection"

    def test_has_trajectory_and_points(self, sample_result):
        data = json.loads(export_geojson(sample_result))
        types = {f["properties"]["type"] for f in data["features"]}
        assert "trajectory" in types
        assert "evaluation_point" in types
        assert "recommended_engagement" in types

    def test_feature_count(self, sample_result):
        data = json.loads(export_geojson(sample_result))
        # 1 trajectory line + 3 evaluation points + 1 recommended
        assert len(data["features"]) == 5
