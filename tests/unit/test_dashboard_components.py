from __future__ import annotations

import json

import folium
import plotly.graph_objects as go
import pytest

from droneimpact.dashboard.components import (
    _bearing,
    _probability_colour,
    add_direction_arrows,
    compute_fallout_bounds,
    make_coloured_trajectory,
    make_impact_scatter,
    make_multi_trajectory_map,
    make_risk_profile,
    make_stats_panel,
    make_trajectory_map,
    parse_point_index_from_tooltip,
)
from droneimpact.dashboard.utils import (
    compute_bearing,
    export_geojson,
    format_casualties,
    format_distance,
)


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


class TestBearing:
    def test_east(self):
        b = _bearing(0.0, 0.0, 0.0, 1.0)
        assert abs(b - 90.0) < 0.1

    def test_north(self):
        b = _bearing(0.0, 0.0, 1.0, 0.0)
        assert abs(b) < 0.1

    def test_south(self):
        b = _bearing(1.0, 0.0, 0.0, 0.0)
        assert abs(b - 180.0) < 0.1

    def test_west(self):
        b = _bearing(0.0, 1.0, 0.0, 0.0)
        assert abs(b - 270.0) < 0.1


class TestDirectionArrows:
    def test_no_arrows_for_few_points(self):
        m = folium.Map()
        add_direction_arrows(m, [[48.5, 35.0]])
        add_direction_arrows(m, [[48.5, 35.0], [48.6, 35.0]])
        html = m._repr_html_()
        assert "RegularPolygonMarker" not in html

    def test_arrows_added_for_multiple_points(self):
        m = folium.Map()
        points = [[48.5 + i * 0.01, 35.0] for i in range(20)]
        add_direction_arrows(m, points)
        html = m._repr_html_()
        assert "regularPolygonMarker" in html.lower() or "L.RegularPolygonMarker" in html

    def test_arrow_count_bounded(self):
        m = folium.Map()
        points = [[48.5 + i * 0.001, 35.0] for i in range(100)]
        group = folium.FeatureGroup()
        add_direction_arrows(m, points, group=group)
        children = list(group._children.values())
        arrow_count = sum(
            1 for c in children
            if isinstance(c, folium.RegularPolygonMarker)
        )
        assert 2 <= arrow_count <= 12

    def test_trajectory_map_contains_arrows(self, sample_result):
        m = make_trajectory_map(sample_result)
        html = m._repr_html_()
        assert "RegularPolygonMarker" in html or "regularPolygonMarker" in html.lower()

    def test_coloured_trajectory_contains_arrows(self, sample_result):
        m = make_coloured_trajectory(sample_result)
        html = m._repr_html_()
        assert "RegularPolygonMarker" in html or "regularPolygonMarker" in html.lower()


def _make_candidate(
    name: str,
    lat: float,
    lon: float,
    probability: float,
    distance_m: float,
    heading_delta_deg: float = 10.0,
    historical_strikes: int = 5,
    category: str = "energy",
) -> dict:
    return {
        "target": {
            "lat": lat,
            "lon": lon,
            "name": name,
            "category": category,
            "historical_strikes": historical_strikes,
        },
        "probability": probability,
        "distance_m": distance_m,
        "heading_delta_deg": heading_delta_deg,
        "waypoints": [
            {"lat": 51.0, "lon": 33.0},
            {"lat": 50.5, "lon": 32.5},
        ],
    }


@pytest.fixture()
def sample_candidates() -> list[dict]:
    return [
        _make_candidate("Kyiv — energy", 50.45, 30.52, 0.40, 185_000, 12.3, 47),
        _make_candidate("Odesa — port", 46.47, 30.73, 0.25, 280_000, 45.0, 22),
        _make_candidate("Kharkiv — grid", 49.99, 36.23, 0.15, 120_000, 78.0, 15),
        _make_candidate("Dnipro — industrial", 48.46, 35.04, 0.10, 200_000, 55.0, 8),
        _make_candidate("Zaporizhzhia — plant", 47.84, 35.14, 0.06, 250_000, 62.0, 3),
        _make_candidate("Mykolaiv — base", 46.97, 31.99, 0.04, 300_000, 90.0, 2),
    ]


class TestProbabilityColour:
    def test_high_probability_is_reddish(self):
        c = _probability_colour(1.0)
        assert c.startswith("#")
        r = int(c[1:3], 16)
        assert r > 200

    def test_low_probability_is_bluish(self):
        c = _probability_colour(0.0)
        assert c.startswith("#")
        b = int(c[5:7], 16)
        assert b > 200

    def test_returns_valid_hex(self):
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            c = _probability_colour(p)
            assert len(c) == 7
            assert c.startswith("#")
            int(c[1:], 16)


class TestMultiTrajectoryMap:
    def test_returns_folium_map(self, sample_candidates):
        m = make_multi_trajectory_map(52.0, 33.5, sample_candidates)
        assert isinstance(m, folium.Map)

    def test_renders_html(self, sample_candidates):
        m = make_multi_trajectory_map(52.0, 33.5, sample_candidates)
        html = m._repr_html_()
        assert "leaflet" in html.lower() or "OpenStreetMap" in html

    def test_has_layer_control(self, sample_candidates):
        m = make_multi_trajectory_map(52.0, 33.5, sample_candidates)
        html = m._repr_html_()
        assert "LayerControl" in html or "layerControl" in html.lower() or "layer" in html.lower()

    def test_drone_marker_present(self, sample_candidates):
        m = make_multi_trajectory_map(52.0, 33.5, sample_candidates)
        html = m._repr_html_()
        assert "Drone position" in html

    def test_target_names_in_tooltips(self, sample_candidates):
        m = make_multi_trajectory_map(52.0, 33.5, sample_candidates)
        html = m._repr_html_()
        assert "Kyiv" in html
        assert "Odesa" in html

    def test_probability_labels_present(self, sample_candidates):
        m = make_multi_trajectory_map(52.0, 33.5, sample_candidates)
        html = m._repr_html_()
        assert "40%" in html
        assert "25%" in html

    def test_scored_result_adds_marker(self, sample_candidates, sample_result):
        m = make_multi_trajectory_map(
            52.0, 33.5, sample_candidates,
            scored_result=sample_result,
            scored_candidate_idx=0,
        )
        html = m._repr_html_()
        assert "RECOMMENDED" in html

    def test_empty_candidates(self):
        m = make_multi_trajectory_map(52.0, 33.5, [])
        assert isinstance(m, folium.Map)

    def test_single_candidate(self):
        c = _make_candidate("Solo target", 50.0, 30.0, 1.0, 100_000)
        m = make_multi_trajectory_map(52.0, 33.5, [c])
        html = m._repr_html_()
        assert "Solo target" in html

    def test_first_five_shown_by_default(self, sample_candidates):
        m = make_multi_trajectory_map(52.0, 33.5, sample_candidates)
        children = list(m._children.values())
        feature_groups = [c for c in children if isinstance(c, folium.FeatureGroup)]
        shown = [fg for fg in feature_groups if fg.show]
        hidden = [fg for fg in feature_groups if not fg.show]
        assert len(shown) == 5
        assert len(hidden) == 1


class TestComputeBearing:
    def test_east(self):
        assert abs(compute_bearing(0.0, 0.0, 0.0, 1.0) - 90.0) < 0.1

    def test_north(self):
        assert abs(compute_bearing(0.0, 0.0, 1.0, 0.0)) < 0.1

    def test_south(self):
        assert abs(compute_bearing(1.0, 0.0, 0.0, 0.0) - 180.0) < 0.1

    def test_west(self):
        assert abs(compute_bearing(0.0, 1.0, 0.0, 0.0) - 270.0) < 0.1

    def test_matches_internal_bearing(self):
        for lat1, lon1, lat2, lon2 in [
            (52.0, 33.5, 50.45, 30.52),
            (48.0, 35.0, 46.47, 30.73),
            (0.0, 0.0, 45.0, 90.0),
        ]:
            assert abs(compute_bearing(lat1, lon1, lat2, lon2) - _bearing(lat1, lon1, lat2, lon2)) < 0.001
