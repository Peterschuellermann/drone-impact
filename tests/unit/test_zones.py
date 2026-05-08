import numpy as np
import pytest

from droneimpact.config import ScoringConfig
from droneimpact.scoring.types import PointScore
from droneimpact.scoring.zones import classify_zones


def _ps(index: int, score: float, population: float = 0.0) -> PointScore:
    return PointScore(
        point_index=index,
        lat=48.0 - index * 0.001,
        lon=31.0,
        altitude_m=400.0,
        distance_from_start_m=index * 500.0,
        expected_casualties=score,
        engagement_score=score,
        breakdown={},
        miss_branch_expected_casualties=0.0,
        population_within_frag_radius=population,
    )


@pytest.fixture
def scoring_cfg():
    return ScoringConfig()


def test_single_zone_all_clear(scoring_cfg):
    scores = [_ps(i, 0.01) for i in range(10)]
    zones = classify_zones(scores, scoring_cfg)
    assert len(zones) == 1
    assert zones[0].classification == "clear"
    assert zones[0].start_index == 0
    assert zones[0].end_index == 9


def test_mixed_zones(scoring_cfg):
    scores = [
        _ps(0, 0.01),
        _ps(1, 0.05),
        _ps(2, 0.5, population=30.0),
        _ps(3, 0.8, population=50.0),
        _ps(4, 1.5, population=100.0),
        _ps(5, 2.0, population=120.0),
        _ps(6, 0.3, population=20.0),
        _ps(7, 0.01),
    ]
    zones = classify_zones(scores, scoring_cfg)
    assert len(zones) >= 3

    classifications = [z.classification for z in zones]
    assert "clear" in classifications
    assert "no_go" in classifications


def test_zone_reasons_populated(scoring_cfg):
    scores = [_ps(0, 0.5, population=30.0), _ps(1, 1.5, population=100.0)]
    zones = classify_zones(scores, scoring_cfg)
    for z in zones:
        assert len(z.reasons) >= 1
        assert all(isinstance(r, str) for r in z.reasons)


def test_nogo_zone_peak(scoring_cfg):
    scores = [_ps(0, 1.5), _ps(1, 3.0), _ps(2, 2.0)]
    zones = classify_zones(scores, scoring_cfg)
    nogo = [z for z in zones if z.classification == "no_go"]
    assert len(nogo) == 1
    assert nogo[0].peak_expected_casualties == pytest.approx(3.0)


def test_zones_cover_full_trajectory(scoring_cfg):
    scores = [_ps(i, 0.01 if i < 5 else 1.5) for i in range(10)]
    zones = classify_zones(scores, scoring_cfg)
    assert zones[0].start_index == 0
    assert zones[-1].end_index == 9
    for i in range(len(zones) - 1):
        assert zones[i].end_index + 1 == zones[i + 1].start_index


def test_empty_scores():
    zones = classify_zones([], ScoringConfig())
    assert zones == []


def test_zone_population_summed(scoring_cfg):
    scores = [_ps(0, 1.5, population=50.0), _ps(1, 2.0, population=70.0)]
    zones = classify_zones(scores, scoring_cfg)
    nogo = [z for z in zones if z.classification == "no_go"]
    assert len(nogo) == 1
    assert nogo[0].population_in_zone == pytest.approx(120.0)
