"""Tests for the safe intercept constraint (F20).

Uses synthetic PointScore objects to test the constraint logic
directly, without running Monte Carlo simulations.
"""
import numpy as np
import pytest

from droneimpact.scoring.engine import ScoringEngine
from droneimpact.scoring.explain import explain
from droneimpact.scoring.types import (
    ModeScore,
    PointScore,
    RecommendedEngagement,
    RiskZone,
    TrajectoryResult,
)


def _make_point_score(
    index: int,
    engagement_score: float,
    hit_branch_expected_casualties: float,
    distance_from_start_m: float = 0.0,
) -> PointScore:
    """Create a PointScore with controlled hit_branch and engagement_score."""
    return PointScore(
        point_index=index,
        lat=48.0,
        lon=31.0,
        altitude_m=400.0,
        distance_from_start_m=distance_from_start_m,
        expected_casualties=engagement_score,
        engagement_score=engagement_score,
        breakdown={},
        miss_branch_expected_casualties=0.0,
        hit_branch_expected_casualties=hit_branch_expected_casualties,
    )


def _make_config(high_risk_threshold: float = 0.5):
    """Build a minimal AppConfig with a given threshold."""
    from droneimpact.config import AppConfig

    return AppConfig.model_validate({
        "version": "1.0",
        "physics": {
            "n_monte_carlo_samples": 100,
            "evaluation_spacing_m": 500,
            "shahed136": {
                "mass_kg": 200.0,
                "warhead_mass_kg": 45.0,
                "cruise_speed_m_s": 51.4,
                "glide_ratio": 5.0,
                "drag_coeff_tumbling": 0.8,
                "reference_area_m2": 3.5,
            },
            "m1_sigma_heading_deg": 5.0,
            "m1_sigma_glide_ratio": 0.8,
            "m1_sigma_speed_m_s": 5.0,
            "m2_sigma_init_deg": 30.0,
            "m2_sigma_turn_deg_per_s": 15.0,
            "m2_dt_s": 1.0,
            "m2_max_time_s": 300.0,
            "m2_descent_rate_m_s": 1.5,
            "m3_sigma_speed_m_s": 10.0,
            "m3_sigma_cd": 0.15,
            "m3_dt_s": 0.1,
            "m3_max_steps": 1000,
            "atmosphere_scale_height_m": 8500.0,
        },
        "engagement": {
            "p_kill": 0.50,
            "high_risk_threshold": high_risk_threshold,
            "mode_weights": {
                "propulsion_loss": 0.40,
                "loss_of_control": 0.35,
                "break_apart": 0.25,
            },
        },
        "casualty": {
            "blast": {
                "tnt_equivalent_kg": 30.0,
                "lethal_radius_m": 5.0,
                "injury_radius_m": 80.0,
                "p_lethal": 0.9,
                "p_injury": 0.3,
            },
            "fragmentation": {
                "lethal_radius_m": 200.0,
                "danger_radius_m": 400.0,
                "p_frag_lethal": 0.5,
                "p_frag_danger": 0.1,
            },
            "infrastructure": {
                "penalty_radius_m": 500.0,
                "max_penalty": 10.0,
                "weights": {
                    "power_plant": 5.0,
                    "hospital": 4.0,
                    "water_works": 4.0,
                    "bridge": 3.0,
                    "school": 2.0,
                },
            },
        },
        "data": {
            "population_path": "./data/kontur_ukraine.gpkg",
            "dem_path": "./data/ukraine_dem.tif",
            "infrastructure_path": "./data/ukraine_infra.geojson",
        },
    })


class TestNoHighRiskZones:
    """When all points are below threshold, constrained == unconstrained."""

    def test_no_high_risk_zones_recommendation_unchanged(self):
        config = _make_config(high_risk_threshold=0.5)
        engine = ScoringEngine(config)

        # All points have hit_branch < 0.5 (threshold)
        point_scores = [
            _make_point_score(0, engagement_score=2.0, hit_branch_expected_casualties=0.1, distance_from_start_m=0.0),
            _make_point_score(1, engagement_score=1.5, hit_branch_expected_casualties=0.2, distance_from_start_m=500.0),
            _make_point_score(2, engagement_score=1.0, hit_branch_expected_casualties=0.3, distance_from_start_m=1000.0),
            _make_point_score(3, engagement_score=1.8, hit_branch_expected_casualties=0.1, distance_from_start_m=1500.0),
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 4,
        )

        # Point 2 has the lowest engagement_score (1.0), should be recommended
        assert result.recommended_engagement.point_index == 2
        # No constraint was applied
        assert result.unconstrained_optimum is None
        assert result.risk_zones == []


class TestHighRiskZoneBlocks:
    """When a point is high-risk, downstream points are blocked."""

    def test_high_risk_zone_blocks_downstream_recommendation(self):
        config = _make_config(high_risk_threshold=0.5)
        engine = ScoringEngine(config)

        # Points 0-4: low risk, moderate scores
        # Point 5: HIGH RISK (hit_branch = 1.0 > 0.5 threshold)
        # Points 6-9: low risk, but one has a much better score
        point_scores = [
            _make_point_score(0, engagement_score=3.0, hit_branch_expected_casualties=0.1, distance_from_start_m=0.0),
            _make_point_score(1, engagement_score=2.5, hit_branch_expected_casualties=0.2, distance_from_start_m=500.0),
            _make_point_score(2, engagement_score=2.0, hit_branch_expected_casualties=0.3, distance_from_start_m=1000.0),
            _make_point_score(3, engagement_score=2.2, hit_branch_expected_casualties=0.1, distance_from_start_m=1500.0),
            _make_point_score(4, engagement_score=2.8, hit_branch_expected_casualties=0.2, distance_from_start_m=2000.0),
            _make_point_score(5, engagement_score=5.0, hit_branch_expected_casualties=1.0, distance_from_start_m=2500.0),
            _make_point_score(6, engagement_score=1.5, hit_branch_expected_casualties=0.1, distance_from_start_m=3000.0),
            _make_point_score(7, engagement_score=0.5, hit_branch_expected_casualties=0.1, distance_from_start_m=3500.0),
            _make_point_score(8, engagement_score=1.0, hit_branch_expected_casualties=0.1, distance_from_start_m=4000.0),
            _make_point_score(9, engagement_score=1.2, hit_branch_expected_casualties=0.1, distance_from_start_m=4500.0),
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 10,
        )

        # Point 7 has the lowest score (0.5) but is past the high-risk zone
        # Constrained recommendation should be from points 0-4
        # Point 2 has the lowest score among eligible (2.0)
        assert result.recommended_engagement.point_index == 2
        assert result.recommended_engagement.engagement_score == 2.0


class TestConstrainedFlag:
    """Verify unconstrained_optimum is set when the constraint changes the pick."""

    def test_constrained_flag_set_when_recommendation_differs(self):
        config = _make_config(high_risk_threshold=0.5)
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(0, engagement_score=3.0, hit_branch_expected_casualties=0.1, distance_from_start_m=0.0),
            _make_point_score(1, engagement_score=2.0, hit_branch_expected_casualties=0.1, distance_from_start_m=500.0),
            _make_point_score(2, engagement_score=5.0, hit_branch_expected_casualties=1.0, distance_from_start_m=1000.0),
            _make_point_score(3, engagement_score=0.5, hit_branch_expected_casualties=0.1, distance_from_start_m=1500.0),
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 4,
        )

        # Constrained picks point 1 (best before high-risk zone)
        assert result.recommended_engagement.point_index == 1
        # Unconstrained would pick point 3 (lowest overall)
        assert result.unconstrained_optimum is not None
        assert result.unconstrained_optimum.point_index == 3
        assert result.unconstrained_optimum.engagement_score == 0.5


class TestRiskZonesDetected:
    """Verify contiguous high-risk segments are correctly identified."""

    def test_risk_zones_detected(self):
        config = _make_config(high_risk_threshold=0.5)
        engine = ScoringEngine(config)

        # Two high-risk zones: points 2-3 and point 6
        point_scores = [
            _make_point_score(0, engagement_score=1.0, hit_branch_expected_casualties=0.1, distance_from_start_m=0.0),
            _make_point_score(1, engagement_score=1.0, hit_branch_expected_casualties=0.2, distance_from_start_m=500.0),
            _make_point_score(2, engagement_score=3.0, hit_branch_expected_casualties=0.8, distance_from_start_m=1000.0),
            _make_point_score(3, engagement_score=4.0, hit_branch_expected_casualties=1.2, distance_from_start_m=1500.0),
            _make_point_score(4, engagement_score=1.0, hit_branch_expected_casualties=0.3, distance_from_start_m=2000.0),
            _make_point_score(5, engagement_score=1.0, hit_branch_expected_casualties=0.2, distance_from_start_m=2500.0),
            _make_point_score(6, engagement_score=2.0, hit_branch_expected_casualties=0.9, distance_from_start_m=3000.0),
            _make_point_score(7, engagement_score=1.0, hit_branch_expected_casualties=0.1, distance_from_start_m=3500.0),
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 8,
        )

        assert len(result.risk_zones) == 2

        # First zone: points 2-3
        zone1 = result.risk_zones[0]
        assert zone1.start_index == 2
        assert zone1.end_index == 3
        assert zone1.start_distance_m == 1000.0
        assert zone1.end_distance_m == 1500.0
        assert zone1.peak_expected_casualties == 1.2

        # Second zone: point 6
        zone2 = result.risk_zones[1]
        assert zone2.start_index == 6
        assert zone2.end_index == 6
        assert zone2.start_distance_m == 3000.0
        assert zone2.end_distance_m == 3000.0
        assert zone2.peak_expected_casualties == 0.9


class TestAllPointsHighRisk:
    """Fallback: when no safe point exists, recommend the first point."""

    def test_all_points_high_risk_uses_first_point(self):
        config = _make_config(high_risk_threshold=0.5)
        engine = ScoringEngine(config)

        # All points exceed threshold
        point_scores = [
            _make_point_score(0, engagement_score=3.0, hit_branch_expected_casualties=1.0, distance_from_start_m=0.0),
            _make_point_score(1, engagement_score=2.0, hit_branch_expected_casualties=0.8, distance_from_start_m=500.0),
            _make_point_score(2, engagement_score=1.0, hit_branch_expected_casualties=0.6, distance_from_start_m=1000.0),
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 3,
        )

        # No eligible points, fallback to first point
        assert result.recommended_engagement.point_index == 0
        # Unconstrained would pick point 2 (lowest score)
        assert result.unconstrained_optimum is not None
        assert result.unconstrained_optimum.point_index == 2


class TestThresholdConfigurable:
    """Changing high_risk_threshold changes which points are flagged."""

    def test_threshold_configurable(self):
        # With threshold=0.5, point 2 (hit_branch=0.6) is high-risk
        # With threshold=1.0, point 2 (hit_branch=0.6) is NOT high-risk
        point_scores_data = [
            (0, 2.0, 0.1, 0.0),
            (1, 1.5, 0.3, 500.0),
            (2, 3.0, 0.6, 1000.0),  # Only high-risk at threshold=0.5
            (3, 0.5, 0.2, 1500.0),  # Best score, past point 2
        ]

        # Strict threshold: point 2 is high-risk, point 3 is blocked
        config_strict = _make_config(high_risk_threshold=0.5)
        engine_strict = ScoringEngine(config_strict)
        scores_strict = [_make_point_score(*d) for d in point_scores_data]
        result_strict = engine_strict._apply_safe_intercept_constraint(
            scores_strict, [], 0.0, 100, 4,
        )
        # Constrained: picks from 0-1, best is point 1 (score=1.5)
        assert result_strict.recommended_engagement.point_index == 1
        assert result_strict.unconstrained_optimum is not None

        # Permissive threshold: no point is high-risk
        config_permissive = _make_config(high_risk_threshold=1.0)
        engine_permissive = ScoringEngine(config_permissive)
        scores_permissive = [_make_point_score(*d) for d in point_scores_data]
        result_permissive = engine_permissive._apply_safe_intercept_constraint(
            scores_permissive, [], 0.0, 100, 4,
        )
        # Unconstrained: picks point 3 (score=0.5)
        assert result_permissive.recommended_engagement.point_index == 3
        assert result_permissive.unconstrained_optimum is None


class TestHitBranchExcludesMissTerm:
    """high_risk flag is based on hit-branch casualties only, not full engagement score."""

    def test_hit_branch_excludes_miss_term(self):
        config = _make_config(high_risk_threshold=0.5)
        engine = ScoringEngine(config)

        # Point has high engagement_score (due to miss term) but low hit_branch
        # Should NOT be flagged as high-risk
        point_scores = [
            _make_point_score(0, engagement_score=5.0, hit_branch_expected_casualties=0.1, distance_from_start_m=0.0),
            _make_point_score(1, engagement_score=4.0, hit_branch_expected_casualties=0.2, distance_from_start_m=500.0),
            _make_point_score(2, engagement_score=3.0, hit_branch_expected_casualties=0.3, distance_from_start_m=1000.0),
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 3,
        )

        # No points flagged as high-risk (all hit_branch < 0.5)
        for ps in result.trajectory_scores:
            assert not ps.high_risk

        # No risk zones
        assert result.risk_zones == []

        # No constraint applied (all eligible)
        assert result.unconstrained_optimum is None

        # Point 2 has the lowest engagement_score, should be recommended
        assert result.recommended_engagement.point_index == 2


class TestExplainConstrained:
    """Reasoning text mentions the constraint when it changes the recommendation."""

    def test_explain_constrained(self):
        ps = _make_point_score(0, 2.0, 0.1)
        all_scores = [ps, _make_point_score(1, 3.0, 0.1)]

        reasoning = explain(ps, all_scores, is_constrained=True)
        assert "high-risk zone" in reasoning
        assert "overflying" in reasoning

    def test_explain_unconstrained(self):
        ps = _make_point_score(0, 0.0001, 0.0)
        all_scores = [ps, _make_point_score(1, 0.0002, 0.0)]

        reasoning = explain(ps, all_scores, is_constrained=False)
        assert "high-risk zone" not in reasoning


class TestRiskZoneEdgeCases:
    """Edge cases for risk zone detection."""

    def test_trailing_risk_zone(self):
        """Risk zone at the end of the trajectory is properly closed."""
        config = _make_config(high_risk_threshold=0.5)
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(0, 1.0, 0.1, 0.0),
            _make_point_score(1, 1.0, 0.1, 500.0),
            _make_point_score(2, 3.0, 0.8, 1000.0),
            _make_point_score(3, 4.0, 1.0, 1500.0),
        ]

        zones = engine._find_risk_zones(point_scores, 0.5)
        assert len(zones) == 1
        assert zones[0].start_index == 2
        assert zones[0].end_index == 3
        assert zones[0].peak_expected_casualties == 1.0

    def test_no_risk_zones(self):
        """No risk zones when all points are below threshold."""
        config = _make_config(high_risk_threshold=0.5)
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(0, 1.0, 0.1, 0.0),
            _make_point_score(1, 1.0, 0.2, 500.0),
            _make_point_score(2, 1.0, 0.3, 1000.0),
        ]

        zones = engine._find_risk_zones(point_scores, 0.5)
        assert zones == []

    def test_single_point_risk_zone(self):
        """A single high-risk point forms a zone of length 1."""
        config = _make_config(high_risk_threshold=0.5)
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(0, 1.0, 0.1, 0.0),
            _make_point_score(1, 3.0, 0.8, 500.0),
            _make_point_score(2, 1.0, 0.1, 1000.0),
        ]

        zones = engine._find_risk_zones(point_scores, 0.5)
        assert len(zones) == 1
        assert zones[0].start_index == 1
        assert zones[0].end_index == 1
