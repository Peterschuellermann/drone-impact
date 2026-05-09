"""Tests for the ranked interception points feature (#30).

Validates that the engine returns a ranked list of up to 5 eligible
interception points, that rank 1 always equals the recommended engagement,
that the list is sorted by engagement_score ascending, and that all returned
points are eligible (i.e. not downstream of any high-risk point).
"""
from __future__ import annotations

import pytest

from droneimpact.config import AppConfig
from droneimpact.scoring.engine import ScoringEngine
from droneimpact.scoring.types import PointScore


# ---------------------------------------------------------------------------
# Helpers shared with test_safe_intercept.py
# ---------------------------------------------------------------------------

def _make_point_score(
    index: int,
    engagement_score: float,
    hit_branch_expected_casualties: float,
    distance_from_start_m: float = 0.0,
) -> PointScore:
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


def _make_config(high_risk_threshold: float = 0.5) -> AppConfig:
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRankedEngagementsBasic:
    """Engine returns a non-empty ranked list."""

    def test_ranked_engagements_present(self):
        config = _make_config()
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(i, float(10 - i), 0.1, float(i * 500))
            for i in range(8)
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 8,
        )

        assert len(result.ranked_engagements) > 0

    def test_ranked_engagements_max_five(self):
        """No more than 5 points are returned even with many eligible points."""
        config = _make_config()
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(i, float(i + 1), 0.1, float(i * 500))
            for i in range(20)
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 20,
        )

        assert len(result.ranked_engagements) <= 5

    def test_fewer_than_five_when_few_eligible(self):
        """When fewer than 5 eligible points exist, all eligible ones are returned."""
        config = _make_config()
        engine = ScoringEngine(config)

        # Only 2 eligible points before high-risk zone
        point_scores = [
            _make_point_score(0, 2.0, 0.1, 0.0),
            _make_point_score(1, 3.0, 0.1, 500.0),
            _make_point_score(2, 1.0, 1.0, 1000.0),   # high-risk, blocks rest
            _make_point_score(3, 0.5, 0.1, 1500.0),
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 4,
        )

        # Only points 0 and 1 are eligible
        assert len(result.ranked_engagements) == 2


class TestRankedEngagementsRank1MatchesRecommended:
    """ranked_engagements[0] always matches recommended_engagement."""

    def test_rank1_equals_recommended(self):
        config = _make_config()
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(0, 3.0, 0.1, 0.0),
            _make_point_score(1, 1.0, 0.2, 500.0),
            _make_point_score(2, 2.0, 0.3, 1000.0),
            _make_point_score(3, 4.0, 0.1, 1500.0),
            _make_point_score(4, 1.5, 0.1, 2000.0),
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 5,
        )

        ranked = result.ranked_engagements
        rec = result.recommended_engagement

        assert len(ranked) > 0
        assert ranked[0].rank == 1
        assert ranked[0].point_index == rec.point_index
        assert ranked[0].engagement_score == rec.engagement_score
        assert ranked[0].lat == rec.lat
        assert ranked[0].lon == rec.lon

    def test_rank1_equals_recommended_with_constraint(self):
        """Still holds when the safe intercept constraint is active."""
        config = _make_config(high_risk_threshold=0.5)
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(0, 3.0, 0.1, 0.0),
            _make_point_score(1, 2.0, 0.1, 500.0),
            _make_point_score(2, 5.0, 1.0, 1000.0),   # high-risk
            _make_point_score(3, 0.5, 0.1, 1500.0),   # blocked
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 4,
        )

        ranked = result.ranked_engagements
        rec = result.recommended_engagement

        assert ranked[0].point_index == rec.point_index
        assert ranked[0].engagement_score == rec.engagement_score


class TestRankedEngagementsSortedByScore:
    """ranked_engagements is sorted by engagement_score ascending."""

    def test_sorted_ascending(self):
        config = _make_config()
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(0, 5.0, 0.1, 0.0),
            _make_point_score(1, 2.0, 0.1, 500.0),
            _make_point_score(2, 4.0, 0.1, 1000.0),
            _make_point_score(3, 1.0, 0.1, 1500.0),
            _make_point_score(4, 3.0, 0.1, 2000.0),
            _make_point_score(5, 6.0, 0.1, 2500.0),
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 6,
        )

        ranked = result.ranked_engagements
        scores = [r.engagement_score for r in ranked]
        assert scores == sorted(scores), "ranked_engagements must be sorted by score ascending"

    def test_ranks_are_sequential(self):
        config = _make_config()
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(i, float(i + 1), 0.1, float(i * 500))
            for i in range(6)
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 6,
        )

        for expected_rank, re in enumerate(result.ranked_engagements, start=1):
            assert re.rank == expected_rank


class TestRankedEngagementsEligibility:
    """All ranked points must be eligible (no high-risk predecessor)."""

    def test_no_ranked_point_downstream_of_high_risk(self):
        config = _make_config(high_risk_threshold=0.5)
        engine = ScoringEngine(config)

        # Points 0-3 eligible, point 4 high-risk, points 5-9 blocked
        point_scores = [
            _make_point_score(0, 4.0, 0.1, 0.0),
            _make_point_score(1, 3.0, 0.1, 500.0),
            _make_point_score(2, 2.0, 0.2, 1000.0),
            _make_point_score(3, 1.0, 0.3, 1500.0),
            _make_point_score(4, 5.0, 1.0, 2000.0),   # high-risk
            _make_point_score(5, 0.1, 0.0, 2500.0),   # blocked — best score overall
            _make_point_score(6, 0.2, 0.0, 3000.0),   # blocked
            _make_point_score(7, 0.3, 0.0, 3500.0),   # blocked
            _make_point_score(8, 0.4, 0.0, 4000.0),   # blocked
            _make_point_score(9, 0.5, 0.0, 4500.0),   # blocked
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 10,
        )

        # Build set of eligible point indices (0-3)
        eligible_indices = {0, 1, 2, 3}
        for re in result.ranked_engagements:
            assert re.point_index in eligible_indices, (
                f"Ranked point {re.point_index} is not eligible (downstream of high-risk)"
            )

    def test_ranked_points_not_high_risk_themselves(self):
        """Ranked points must not have high_risk=True (they are eligible by definition)."""
        config = _make_config(high_risk_threshold=0.5)
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(0, 2.0, 0.1, 0.0),
            _make_point_score(1, 1.0, 0.2, 500.0),
            _make_point_score(2, 3.0, 0.8, 1000.0),  # high-risk — must not appear in ranked
            _make_point_score(3, 0.5, 0.1, 1500.0),  # blocked
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 4,
        )

        score_by_idx = {ps.point_index: ps for ps in result.trajectory_scores}
        for re in result.ranked_engagements:
            ps = score_by_idx.get(re.point_index)
            if ps is not None:
                assert not ps.high_risk, (
                    f"Ranked point {re.point_index} is marked high_risk but should be eligible"
                )


class TestRankedEngagementsFallbackReasoning:
    """Ranks 2+ include 'Fallback option if points 1–N are missed' prefix."""

    def test_rank1_reasoning_not_fallback(self):
        config = _make_config()
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(i, float(i + 1), 0.1, float(i * 500))
            for i in range(5)
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 5,
        )

        rank1 = result.ranked_engagements[0]
        assert "Fallback" not in rank1.reasoning

    def test_rank2_reasoning_has_fallback_prefix(self):
        config = _make_config()
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(i, float(i + 1), 0.1, float(i * 500))
            for i in range(5)
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 5,
        )

        if len(result.ranked_engagements) >= 2:
            rank2 = result.ranked_engagements[1]
            assert rank2.reasoning.startswith("Fallback option if points 1–1 are missed")

    def test_rank3_reasoning_references_prior_ranks(self):
        config = _make_config()
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(i, float(i + 1), 0.1, float(i * 500))
            for i in range(6)
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 6,
        )

        if len(result.ranked_engagements) >= 3:
            rank3 = result.ranked_engagements[2]
            assert "1–2" in rank3.reasoning


class TestRankedEngagementsAllHighRisk:
    """When no eligible points exist, ranked_engagements still has the fallback first point."""

    def test_all_high_risk_returns_first_point(self):
        config = _make_config(high_risk_threshold=0.5)
        engine = ScoringEngine(config)

        point_scores = [
            _make_point_score(0, 3.0, 1.0, 0.0),
            _make_point_score(1, 2.0, 0.8, 500.0),
            _make_point_score(2, 1.0, 0.6, 1000.0),
        ]

        result = engine._apply_safe_intercept_constraint(
            point_scores, [], 0.0, 100, 3,
        )

        assert len(result.ranked_engagements) == 1
        assert result.ranked_engagements[0].rank == 1
        assert result.ranked_engagements[0].point_index == 0
