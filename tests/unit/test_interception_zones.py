"""Tests for probabilistic interception zone computation."""
from __future__ import annotations

import math

import pytest

from droneimpact.scoring.engine import ScoringEngine
from droneimpact.scoring.types import (
    ImpactDistribution,
    ImpactEllipse,
    InterceptionZone,
    PointScore,
)


def _make_point_score(
    index: int,
    lat: float = 48.0,
    lon: float = 35.0,
    distance_m: float = 0.0,
    hit_casualties: float = 0.0,
    engagement_score: float = 0.0,
    speed_m_s: float = 51.4,
    heading_deg: float = 270.0,
) -> PointScore:
    return PointScore(
        point_index=index,
        lat=lat,
        lon=lon,
        altitude_m=400.0,
        distance_from_start_m=distance_m,
        expected_casualties=engagement_score,
        engagement_score=engagement_score,
        breakdown={},
        miss_branch_expected_casualties=0.0,
        heading_deg=heading_deg,
        speed_m_s=speed_m_s,
        hit_branch_expected_casualties=hit_casualties,
    )


class TestClassifyRisk:
    def test_safe(self):
        assert ScoringEngine._classify_risk(0.05, 0.5) == "safe"

    def test_caution(self):
        assert ScoringEngine._classify_risk(0.15, 0.5) == "caution"

    def test_elevated(self):
        assert ScoringEngine._classify_risk(0.35, 0.5) == "elevated"

    def test_no_go(self):
        assert ScoringEngine._classify_risk(0.6, 0.5) == "no_go"

    def test_boundary_safe_caution(self):
        assert ScoringEngine._classify_risk(0.099, 0.5) == "safe"
        assert ScoringEngine._classify_risk(0.1, 0.5) == "caution"

    def test_boundary_caution_elevated(self):
        assert ScoringEngine._classify_risk(0.249, 0.5) == "caution"
        assert ScoringEngine._classify_risk(0.25, 0.5) == "elevated"

    def test_boundary_elevated_nogo(self):
        assert ScoringEngine._classify_risk(0.499, 0.5) == "elevated"
        assert ScoringEngine._classify_risk(0.5, 0.5) == "no_go"


class TestBuildCorridorPolygon:
    def test_single_point_returns_rectangle(self):
        points = [_make_point_score(0)]
        polygon = ScoringEngine._build_corridor_polygon(points, 100.0)
        assert len(polygon) == 4
        for pt in polygon:
            assert len(pt) == 2

    def test_two_points_returns_closed_polygon(self):
        points = [
            _make_point_score(0, lat=48.0, lon=35.0, distance_m=0),
            _make_point_score(1, lat=48.0, lon=35.01, distance_m=500),
        ]
        polygon = ScoringEngine._build_corridor_polygon(points, 200.0)
        assert len(polygon) == 4
        lats = [p[0] for p in polygon]
        assert max(lats) > 48.0
        assert min(lats) < 48.0

    def test_wider_radius_gives_wider_polygon(self):
        points = [
            _make_point_score(0, lat=48.0, lon=35.0, distance_m=0),
            _make_point_score(1, lat=48.0, lon=35.01, distance_m=500),
        ]
        narrow = ScoringEngine._build_corridor_polygon(points, 100.0)
        wide = ScoringEngine._build_corridor_polygon(points, 500.0)
        narrow_lats = [p[0] for p in narrow]
        wide_lats = [p[0] for p in wide]
        assert (max(wide_lats) - min(wide_lats)) > (max(narrow_lats) - min(narrow_lats))

    def test_polygon_has_correct_point_count(self):
        n = 10
        points = [
            _make_point_score(
                i, lat=48.0, lon=35.0 + i * 0.001, distance_m=i * 500,
            )
            for i in range(n)
        ]
        polygon = ScoringEngine._build_corridor_polygon(points, 300.0)
        assert len(polygon) == 2 * n


class TestComputeInterceptionZones:
    @pytest.fixture
    def engine(self):
        from droneimpact.config import AppConfig
        config = AppConfig.model_validate({
            "version": "1.0",
            "physics": {
                "n_monte_carlo_samples": 100,
                "evaluation_spacing_m": 500,
                "shahed136": {
                    "mass_kg": 200, "warhead_mass_kg": 45,
                    "cruise_speed_m_s": 51.4, "glide_ratio": 5.0,
                    "drag_coeff_tumbling": 0.8, "reference_area_m2": 3.5,
                },
                "m1_sigma_heading_deg": 5.0, "m1_sigma_glide_ratio": 0.8,
                "m1_sigma_speed_m_s": 5.0, "m2_sigma_init_deg": 30.0,
                "m2_sigma_turn_deg_per_s": 15.0, "m2_dt_s": 1.0,
                "m2_max_time_s": 300.0, "m2_descent_rate_m_s": 1.5,
                "m3_sigma_speed_m_s": 10.0, "m3_sigma_cd": 0.15,
                "m3_dt_s": 0.1, "m3_max_steps": 1000,
            },
            "engagement": {
                "p_kill": 0.5,
                "high_risk_threshold": 0.5,
                "mode_weights": {
                    "propulsion_loss": 0.4, "loss_of_control": 0.35, "break_apart": 0.25,
                },
            },
            "casualty": {
                "blast": {"tnt_equivalent_kg": 30, "lethal_radius_m": 5,
                          "injury_radius_m": 80, "p_lethal": 0.9, "p_injury": 0.3},
                "fragmentation": {"lethal_radius_m": 200, "danger_radius_m": 400,
                                  "p_frag_lethal": 0.5, "p_frag_danger": 0.1},
                "infrastructure": {
                    "penalty_radius_m": 500, "max_penalty": 10,
                    "weights": {"power_plant": 5, "hospital": 4, "water_works": 4,
                                "bridge": 3, "school": 2},
                },
            },
            "data": {
                "population_path": "data/pop.gpkg",
                "dem_path": "data/dem.tif",
                "infrastructure_path": "data/infra.geojson",
            },
            "scoring": {
                "interception_timing_uncertainty_s": 3.0,
                "drone_maneuverability_radius_m": 300.0,
                "interception_zone_min_points": 2,
            },
        })
        return ScoringEngine(config)

    def test_uniform_risk_produces_single_zone(self, engine):
        points = [
            _make_point_score(i, distance_m=i * 500, hit_casualties=0.01)
            for i in range(10)
        ]
        zones = engine._compute_interception_zones(points, [])
        assert len(zones) == 1
        assert zones[0].risk_class == "safe"

    def test_mixed_risk_produces_multiple_zones(self, engine):
        points = []
        for i in range(5):
            points.append(_make_point_score(i, distance_m=i * 500, hit_casualties=0.01))
        for i in range(5, 10):
            points.append(_make_point_score(i, distance_m=i * 500, hit_casualties=0.6))
        zones = engine._compute_interception_zones(points, [])
        assert len(zones) == 2
        assert zones[0].risk_class == "safe"
        assert zones[1].risk_class == "no_go"

    def test_zone_ids_are_sequential(self, engine):
        points = []
        for i in range(3):
            points.append(_make_point_score(i, distance_m=i * 500, hit_casualties=0.01))
        for i in range(3, 6):
            points.append(_make_point_score(i, distance_m=i * 500, hit_casualties=0.3))
        for i in range(6, 9):
            points.append(_make_point_score(i, distance_m=i * 500, hit_casualties=0.6))
        zones = engine._compute_interception_zones(points, [])
        for expected_id, z in enumerate(zones):
            assert z.zone_id == expected_id

    def test_intercept_probability_bounded(self, engine):
        points = [
            _make_point_score(i, distance_m=i * 500, hit_casualties=0.01)
            for i in range(20)
        ]
        zones = engine._compute_interception_zones(points, [])
        for z in zones:
            assert 0.0 < z.intercept_probability <= 1.0

    def test_longer_zone_has_higher_probability(self, engine):
        short_points = [
            _make_point_score(i, distance_m=i * 500, hit_casualties=0.01)
            for i in range(3)
        ]
        long_points = [
            _make_point_score(i, distance_m=i * 500, hit_casualties=0.01)
            for i in range(20)
        ]
        short_zones = engine._compute_interception_zones(short_points, [])
        long_zones = engine._compute_interception_zones(long_points, [])
        assert long_zones[0].intercept_probability > short_zones[0].intercept_probability

    def test_corridor_polygon_present(self, engine):
        points = [
            _make_point_score(i, lat=48.0, lon=35.0 + i * 0.005, distance_m=i * 500)
            for i in range(5)
        ]
        zones = engine._compute_interception_zones(points, [])
        assert len(zones[0].corridor_polygon) >= 4

    def test_fall_ellipses_propagated(self, engine):
        points = [
            _make_point_score(i, distance_m=i * 500, hit_casualties=0.01, engagement_score=float(i))
            for i in range(5)
        ]
        dists = [
            ImpactDistribution(
                point_index=0, mode="propulsion_loss",
                impact_ellipse=ImpactEllipse(
                    centre_lat=48.0, centre_lon=35.0,
                    semi_major_m=500, semi_minor_m=200,
                    orientation_deg=45.0,
                ),
            ),
        ]
        zones = engine._compute_interception_zones(points, dists)
        assert len(zones[0].fall_ellipses) == 1
        assert zones[0].fall_ellipses[0].mode == "propulsion_loss"

    def test_min_points_filter(self, engine):
        points = [
            _make_point_score(0, distance_m=0, hit_casualties=0.01),
            _make_point_score(1, distance_m=500, hit_casualties=0.6),
            _make_point_score(2, distance_m=1000, hit_casualties=0.01),
        ]
        zones = engine._compute_interception_zones(points, [])
        for z in zones:
            assert (z.end_index - z.start_index + 1) >= 2 or z.risk_class != "no_go"

    def test_uncertainty_radius_includes_speed(self, engine):
        slow_points = [
            _make_point_score(i, distance_m=i * 500, hit_casualties=0.01, speed_m_s=30.0)
            for i in range(5)
        ]
        fast_points = [
            _make_point_score(i, distance_m=i * 500, hit_casualties=0.01, speed_m_s=80.0)
            for i in range(5)
        ]
        slow_zones = engine._compute_interception_zones(slow_points, [])
        fast_zones = engine._compute_interception_zones(fast_points, [])
        assert fast_zones[0].uncertainty_radius_m > slow_zones[0].uncertainty_radius_m

    def test_best_point_index_is_lowest_score(self, engine):
        points = [
            _make_point_score(i, distance_m=i * 500, hit_casualties=0.01, engagement_score=10.0 - i)
            for i in range(5)
        ]
        zones = engine._compute_interception_zones(points, [])
        assert zones[0].best_point_index == 4
