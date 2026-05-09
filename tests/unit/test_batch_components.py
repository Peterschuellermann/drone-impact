from __future__ import annotations

import folium
import pytest

from droneimpact.dashboard.batch_input import parse_csv
from droneimpact.dashboard.components import make_batch_map, make_drone_overview_map, make_priority_table


def _make_drone_result(drone_id: str, lat: float, lon: float, casualties: float) -> dict:
    return {
        "drone_id": drone_id,
        "computed_at_utc": "2025-01-01T00:00:00Z",
        "recommended_engagement": {
            "point_index": 0,
            "lat": lat,
            "lon": lon,
            "altitude_m": 500.0,
            "distance_from_current_m": 5000.0,
            "expected_casualties": casualties,
            "engagement_score": 0.8,
            "reasoning": "Test",
        },
        "trajectory_scores": [
            {
                "point_index": 0,
                "lat": lat,
                "lon": lon,
                "altitude_m": 500.0,
                "distance_from_current_m": 0.0,
                "expected_casualties": casualties,
                "engagement_score": 0.8,
                "breakdown": {
                    "propulsion_loss": {"weight": 0.4, "expected_casualties": 0.01, "cep_m": 200},
                },
                "miss_branch_expected_casualties": 0.01,
            },
        ],
        "impact_distributions": [],
        "metadata": {
            "n_trajectory_points": 1,
            "n_monte_carlo_samples": 100,
            "simulation_time_ms": 50.0,
            "population_dataset": "test",
            "infrastructure_dataset": "test",
        },
    }


@pytest.fixture()
def batch_result_3() -> dict:
    return {
        "batch_id": "test-batch",
        "status": "complete",
        "results": [
            _make_drone_result("alpha", 48.5, 35.0, 0.05),
            _make_drone_result("bravo", 48.6, 35.1, 0.12),
            _make_drone_result("charlie", 48.7, 35.2, 0.003),
        ],
        "errors": [],
    }


@pytest.fixture()
def batch_result_50() -> dict:
    return {
        "batch_id": "test-batch-50",
        "status": "complete",
        "results": [
            _make_drone_result(f"drone-{i}", 48.5 + i * 0.01, 35.0 + i * 0.01, 0.01 * i)
            for i in range(50)
        ],
        "errors": [],
    }


class TestBatchMap:
    def test_returns_folium_map(self, batch_result_3):
        m = make_batch_map(batch_result_3)
        assert isinstance(m, folium.Map)

    def test_empty_results(self):
        m = make_batch_map({"results": [], "errors": []})
        assert isinstance(m, folium.Map)

    def test_renders_html(self, batch_result_3):
        m = make_batch_map(batch_result_3)
        html = m._repr_html_()
        assert len(html) > 100

    def test_50_drones(self, batch_result_50):
        m = make_batch_map(batch_result_50)
        assert isinstance(m, folium.Map)


class TestPriorityTable:
    def test_sorted_by_casualties_desc(self, batch_result_3):
        rows = make_priority_table(batch_result_3)
        casualties = [r["expected_casualties"] for r in rows]
        assert casualties == sorted(casualties, reverse=True)

    def test_row_count(self, batch_result_3):
        rows = make_priority_table(batch_result_3)
        assert len(rows) == 3

    def test_has_required_fields(self, batch_result_3):
        rows = make_priority_table(batch_result_3)
        for row in rows:
            assert "drone_id" in row
            assert "expected_casualties" in row
            assert "engagement_score" in row
            assert "recommended_distance_m" in row

    def test_50_drones(self, batch_result_50):
        rows = make_priority_table(batch_result_50)
        assert len(rows) == 50


class TestCsvParsing:
    def test_valid_csv(self):
        text = (
            "drone_id,lat,lon,altitude_m,heading_deg,speed_m_s\n"
            "d1,48.5,35.0,500,270,51.4\n"
            "d2,48.6,35.1,600,180,60\n"
        )
        drones, errors = parse_csv(text)
        assert len(drones) == 2
        assert not errors
        assert drones[0]["drone_id"] == "d1"
        assert drones[0]["trajectory"]["lat"] == 48.5

    def test_missing_columns(self):
        text = "drone_id,lat,lon\n1,48.5,35.0\n"
        drones, errors = parse_csv(text)
        assert len(drones) == 0
        assert len(errors) == 1
        assert "Missing" in errors[0]

    def test_bad_value(self):
        text = (
            "drone_id,lat,lon,altitude_m,heading_deg,speed_m_s\n"
            "d1,abc,35.0,500,270,51.4\n"
        )
        drones, errors = parse_csv(text)
        assert len(drones) == 0
        assert len(errors) == 1

    def test_empty_csv(self):
        drones, errors = parse_csv("")
        assert len(drones) == 0
        assert len(errors) == 1

    def test_no_drone_id_column(self):
        text = (
            "lat,lon,altitude_m,heading_deg,speed_m_s\n"
            "48.5,35.0,500,270,51.4\n"
        )
        drones, errors = parse_csv(text)
        assert len(drones) == 1
        assert drones[0]["drone_id"] == "drone-1"


def _make_input_drone(drone_id: str, lat: float, lon: float) -> dict:
    return {
        "drone_id": drone_id,
        "trajectory": {
            "lat": lat, "lon": lon, "altitude_m": 400.0,
            "heading_deg": 230.0, "speed_m_s": 51.4,
        },
    }


class TestDroneOverviewMap:
    def test_returns_folium_map(self):
        drones = [_make_input_drone("d1", 52.0, 33.5)]
        m = make_drone_overview_map(drones)
        assert isinstance(m, folium.Map)

    def test_empty_drones(self):
        m = make_drone_overview_map([])
        assert isinstance(m, folium.Map)

    def test_drone_labels_in_html(self):
        drones = [
            _make_input_drone("alpha", 52.0, 33.5),
            _make_input_drone("bravo", 51.8, 33.8),
        ]
        m = make_drone_overview_map(drones)
        html = m._repr_html_()
        assert "alpha" in html
        assert "bravo" in html

    def test_selected_drone_bold(self):
        drones = [
            _make_input_drone("alpha", 52.0, 33.5),
            _make_input_drone("bravo", 51.8, 33.8),
        ]
        m = make_drone_overview_map(drones, selected_idx=0)
        html = m._repr_html_()
        assert "bold" in html

    def test_multiple_drones(self):
        drones = [_make_input_drone(f"d{i}", 50 + i * 0.1, 33.0) for i in range(10)]
        m = make_drone_overview_map(drones)
        assert isinstance(m, folium.Map)

    def test_tooltips_contain_parameters(self):
        drones = [_make_input_drone("test-drone", 52.0, 33.5)]
        m = make_drone_overview_map(drones)
        html = m._repr_html_()
        assert "test-drone" in html
        assert "400" in html
        assert "230" in html


class TestBatchMapSelection:
    def test_selected_drone_renders(self, batch_result_3):
        m = make_batch_map(batch_result_3, selected_drone_idx=1)
        assert isinstance(m, folium.Map)

    def test_none_selection_works(self, batch_result_3):
        m = make_batch_map(batch_result_3, selected_drone_idx=None)
        assert isinstance(m, folium.Map)
