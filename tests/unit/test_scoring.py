import numpy as np
import pytest

from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.data.dem import DEMIndex
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex
from droneimpact.physics.trajectory import discretise_trajectory
from droneimpact.physics.types import StateVector
from droneimpact.scoring.engine import ScoringEngine, _enu_to_wgs84_fast
from tests.fixtures.population_small import make_test_population

BOUNDS = dict(west=30.0, south=47.0, east=32.0, north=49.0)


@pytest.fixture
def flat_dem():
    data = np.full((20, 20), 0.0, dtype=np.float32)
    return DEMIndex.from_array(data, **BOUNDS)


@pytest.fixture
def casualty_engine(config):
    cells = make_test_population(48.0, 31.0, pop_density=1000.0, radius_cells=5)
    pop = PopulationIndex.from_dict(cells)
    infra = InfrastructureIndex.from_features([], config.casualty.infrastructure)
    return CasualtyEngine(pop, infra, config.casualty)


@pytest.fixture
def short_trajectory():
    sv = StateVector(lat=48.1, lon=31.0, altitude_m=400.0, heading_deg=180.0, speed_m_s=51.4)
    return discretise_trajectory(sv, spacing_m=1000, max_range_m=5000)


@pytest.fixture
def scoring(config):
    return ScoringEngine(config)


def test_result_has_correct_trajectory_length(scoring, short_trajectory, flat_dem, casualty_engine):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(0)
    )
    assert len(result.trajectory_scores) == len(short_trajectory)


def test_recommended_is_argmin(scoring, short_trajectory, flat_dem, casualty_engine):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(0)
    )
    scores = [ps.engagement_score for ps in result.trajectory_scores]
    assert result.recommended_engagement.engagement_score == pytest.approx(min(scores), rel=0.001)


def test_all_engagement_scores_non_negative(scoring, short_trajectory, flat_dem, casualty_engine):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(1)
    )
    for ps in result.trajectory_scores:
        assert ps.engagement_score >= 0.0


def _enabled_mode_names(config) -> set[str]:
    e = config.engagement.mode_enable
    names = set()
    if e.propulsion_loss:
        names.add("propulsion_loss")
    if e.loss_of_control:
        names.add("loss_of_control")
    if e.break_apart:
        names.add("break_apart")
    return names


def test_mode_weights_in_breakdown(scoring, short_trajectory, flat_dem, casualty_engine, config):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(2)
    )
    expected = _enabled_mode_names(config)
    for ps in result.trajectory_scores:
        assert set(ps.breakdown.keys()) == expected


def test_reasoning_nonempty(scoring, short_trajectory, flat_dem, casualty_engine):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(3)
    )
    assert isinstance(result.recommended_engagement.reasoning, str)
    assert len(result.recommended_engagement.reasoning) > 5


def test_impact_distributions_count(scoring, short_trajectory, flat_dem, casualty_engine, config):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(4)
    )
    n_modes = len(_enabled_mode_names(config))
    assert len(result.impact_distributions) == len(short_trajectory) * n_modes


def test_impact_ellipse_semi_major_ge_semi_minor(scoring, short_trajectory, flat_dem, casualty_engine):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(5)
    )
    for dist in result.impact_distributions:
        e = dist.impact_ellipse
        assert e.semi_major_m >= e.semi_minor_m
        assert e.semi_major_m > 0


def test_metadata_fields(scoring, short_trajectory, flat_dem, casualty_engine, config):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(6)
    )
    assert result.metadata["n_trajectory_points"] == len(short_trajectory)
    assert result.metadata["n_monte_carlo_samples"] == config.physics.n_monte_carlo_samples
    assert result.metadata["simulation_time_ms"] > 0


def test_trajectory_distances_ordered(scoring, short_trajectory, flat_dem, casualty_engine):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(7)
    )
    dists = [ps.distance_from_start_m for ps in result.trajectory_scores]
    assert dists == sorted(dists)


def test_empty_trajectory_raises(scoring, flat_dem, casualty_engine):
    with pytest.raises(ValueError, match="trajectory must not be empty"):
        scoring.score_trajectory([], flat_dem, casualty_engine, (48.1, 31.0))


def test_prescan_population_stored(scoring, short_trajectory, flat_dem, casualty_engine):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(0)
    )
    for ps in result.trajectory_scores:
        assert hasattr(ps, "population_within_frag_radius")
        assert isinstance(ps.population_within_frag_radius, float)


def test_zones_generated(scoring, short_trajectory, flat_dem, casualty_engine):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(0)
    )
    assert isinstance(result.engagement_zones, list)
    assert len(result.engagement_zones) >= 1


def test_zones_cover_trajectory(scoring, short_trajectory, flat_dem, casualty_engine):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(0)
    )
    zones = result.engagement_zones
    assert zones[0].start_index == 0
    assert zones[-1].end_index == result.trajectory_scores[-1].point_index


def test_miss_cache_hit(scoring, short_trajectory, flat_dem, casualty_engine):
    scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(0)
    )
    cache_size_after_first = len(scoring._miss_cache)
    scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(1)
    )
    assert len(scoring._miss_cache) == cache_size_after_first


# --- Interpolation tests (I09) ---

from droneimpact.physics.types import TrajectoryPoint
from droneimpact.scoring.types import ModeScore, PointScore


def _make_trajectory(n: int) -> list[TrajectoryPoint]:
    return [
        TrajectoryPoint(
            index=i, lat=48.0, lon=31.0, altitude_m=400.0,
            distance_from_start_m=i * 500.0,
        )
        for i in range(n)
    ]


def _make_point_score(pt: TrajectoryPoint, score: float) -> PointScore:
    return PointScore(
        point_index=pt.index, lat=pt.lat, lon=pt.lon,
        altitude_m=pt.altitude_m,
        distance_from_start_m=pt.distance_from_start_m,
        expected_casualties=score, engagement_score=score,
        breakdown={}, miss_branch_expected_casualties=0.0,
    )


def _make_full_point_scores(traj, scored):
    """Build a point_scores list with placeholders for unscored points."""
    result = []
    for i, pt in enumerate(traj):
        if i in scored:
            result.append(scored[i])
        else:
            result.append(_make_point_score(pt, 0.0))
    return result


def test_interpolation_preserves_scored_points():
    traj = _make_trajectory(5)
    scored = {i: _make_point_score(traj[i], float(i * 10)) for i in range(5)}
    point_scores = _make_full_point_scores(traj, scored)
    result = ScoringEngine._interpolate_gaps(traj, point_scores, scored)
    for i in range(5):
        assert result[i] is scored[i]


def test_interpolation_fills_gaps():
    traj = _make_trajectory(10)
    scored = {
        0: _make_point_score(traj[0], 10.0),
        5: _make_point_score(traj[5], 20.0),
        9: _make_point_score(traj[9], 30.0),
    }
    point_scores = _make_full_point_scores(traj, scored)
    result = ScoringEngine._interpolate_gaps(traj, point_scores, scored)
    for i in range(1, 5):
        assert 10.0 < result[i].engagement_score < 20.0
    for i in range(6, 9):
        assert 20.0 < result[i].engagement_score < 30.0


def test_interpolation_output_length():
    for n in [1, 5, 20, 100]:
        traj = _make_trajectory(n)
        scored = {
            0: _make_point_score(traj[0], 1.0),
            n - 1: _make_point_score(traj[n - 1], 2.0),
        }
        point_scores = _make_full_point_scores(traj, scored)
        result = ScoringEngine._interpolate_gaps(traj, point_scores, scored)
        assert len(result) == n


# --- Mode enable tests ---


def _all_modes_enabled(config):
    from droneimpact.config import ModeEnable
    return config.model_copy(update={
        "engagement": config.engagement.model_copy(update={
            "mode_enable": ModeEnable(propulsion_loss=True, loss_of_control=True, break_apart=True),
        }),
    })


def test_disabled_mode_excluded_from_breakdown(config, short_trajectory, flat_dem, casualty_engine):
    base = _all_modes_enabled(config)
    disabled_cfg = base.model_copy(update={
        "engagement": base.engagement.model_copy(update={
            "mode_enable": base.engagement.mode_enable.model_copy(
                update={"loss_of_control": False}
            ),
        }),
    })
    scoring = ScoringEngine(disabled_cfg)
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(0),
    )
    for ps in result.trajectory_scores:
        assert "loss_of_control" not in ps.breakdown
        assert set(ps.breakdown.keys()) == {"propulsion_loss", "break_apart"}


def test_disabled_mode_renormalizes_weights(config, short_trajectory, flat_dem, casualty_engine):
    base = _all_modes_enabled(config)
    disabled_cfg = base.model_copy(update={
        "engagement": base.engagement.model_copy(update={
            "mode_enable": base.engagement.mode_enable.model_copy(
                update={"loss_of_control": False}
            ),
        }),
    })
    scoring = ScoringEngine(disabled_cfg)
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(0),
    )
    ps = result.trajectory_scores[0]
    total = sum(v.weight for v in ps.breakdown.values())
    assert total == pytest.approx(1.0, abs=1e-6)


def test_disabled_mode_fewer_impact_distributions(config, short_trajectory, flat_dem, casualty_engine):
    base = _all_modes_enabled(config)
    disabled_cfg = base.model_copy(update={
        "engagement": base.engagement.model_copy(update={
            "mode_enable": base.engagement.mode_enable.model_copy(
                update={"loss_of_control": False}
            ),
        }),
    })
    scoring = ScoringEngine(disabled_cfg)
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(0),
    )
    assert len(result.impact_distributions) == len(short_trajectory) * 2


# --- Interpolation boundary tests ---


def test_interpolation_skips_empty_population_points():
    """Points with zero population should keep miss-only score, not get interpolated."""
    traj = _make_trajectory(10)
    scored = {
        0: _make_point_score(traj[0], 10.0),
        5: _make_point_score(traj[5], 20.0),
        9: _make_point_score(traj[9], 30.0),
    }
    point_scores = _make_full_point_scores(traj, scored)

    pop = np.zeros(10, dtype=np.float32)
    pop[0] = 100.0
    pop[5] = 200.0
    pop[9] = 150.0

    result = ScoringEngine._interpolate_gaps(traj, point_scores, scored, pop, 0.0)

    for i in [1, 2, 3, 4, 6, 7, 8]:
        assert result[i].engagement_score == 0.0, (
            f"Point {i} has zero population but got interpolated score "
            f"{result[i].engagement_score}"
        )

    for i in [0, 5, 9]:
        assert result[i] is scored[i]


def test_interpolation_still_fills_populated_gaps():
    """Points with nonzero population between scored points should still be interpolated."""
    traj = _make_trajectory(5)
    scored = {
        0: _make_point_score(traj[0], 10.0),
        4: _make_point_score(traj[4], 20.0),
    }
    point_scores = _make_full_point_scores(traj, scored)

    pop = np.array([100.0, 80.0, 60.0, 40.0, 100.0], dtype=np.float32)

    result = ScoringEngine._interpolate_gaps(traj, point_scores, scored, pop, 0.0)

    for i in [1, 2, 3]:
        assert 10.0 < result[i].engagement_score < 20.0, (
            f"Populated point {i} should be interpolated but got {result[i].engagement_score}"
        )


def test_interpolation_propagates_hit_branch_expected_casualties():
    """Interpolated gap points must have hit_branch_expected_casualties set."""
    traj = _make_trajectory(5)
    scored = {
        0: _make_point_score(traj[0], 10.0),
        4: _make_point_score(traj[4], 20.0),
    }
    scored[0].hit_branch_expected_casualties = 2.0
    scored[4].hit_branch_expected_casualties = 6.0
    point_scores = _make_full_point_scores(traj, scored)

    pop = np.array([100.0, 80.0, 60.0, 40.0, 100.0], dtype=np.float32)
    result = ScoringEngine._interpolate_gaps(traj, point_scores, scored, pop, 0.0)

    for i in [1, 2, 3]:
        assert result[i].hit_branch_expected_casualties > 0.0, (
            f"Point {i} should have interpolated hit_branch_expected_casualties"
        )
    assert result[2].hit_branch_expected_casualties == pytest.approx(4.0)


class TestCityBoundarySharpness:
    """End-to-end test: scores should not plateau beyond actual population extent."""

    @pytest.fixture
    def long_trajectory(self):
        sv = StateVector(
            lat=49.0, lon=31.0, altitude_m=50.0,
            heading_deg=180.0, speed_m_s=51.4,
        )
        return discretise_trajectory(sv, spacing_m=1000, max_range_m=119_000)

    @pytest.fixture
    def wide_dem(self):
        data = np.full((20, 20), 0.0, dtype=np.float32)
        return DEMIndex.from_array(data, west=30.0, south=47.0, east=32.0, north=50.0)

    @pytest.fixture
    def city_casualty_engine(self, long_trajectory, config):
        mid = long_trajectory[60]
        cells = make_test_population(
            mid.lat, mid.lon, pop_density=50000.0, radius_cells=1,
        )
        pop = PopulationIndex.from_dict(cells)
        infra = InfrastructureIndex.from_features([], config.casualty.infrastructure)
        return CasualtyEngine(pop, infra, config.casualty)

    def test_score_drops_outside_city(
        self, config, long_trajectory, wide_dem, city_casualty_engine,
    ):
        """Scores should drop sharply outside the population cluster."""
        engine = ScoringEngine(config)
        result = engine.score_trajectory(
            long_trajectory, wide_dem, city_casualty_engine, (49.0, 31.0),
            rng=np.random.default_rng(42),
        )

        all_vals = [ps.engagement_score for ps in result.trajectory_scores]
        peak_idx = int(np.argmax(all_vals))
        peak_score = all_vals[peak_idx]
        assert peak_score > 0

        for offset in [10, 15, 20]:
            for idx in [peak_idx - offset, peak_idx + offset]:
                if 0 <= idx < len(all_vals):
                    assert all_vals[idx] < peak_score * 0.25, (
                        f"Point {idx} ({offset}km from peak) has score "
                        f"{all_vals[idx]:.6f}, expected < 25% of peak {peak_score:.6f}"
                    )


def test_find_risk_zones_with_non_contiguous_indices():
    """Risk zone detection must not crash when adaptive resolution skips indices."""
    traj = _make_trajectory(6)
    # Simulate adaptive resolution: only indices 0, 2, 4, 5 are scored
    scored_indices = [0, 2, 4, 5]
    point_scores = []
    for i in scored_indices:
        ps = _make_point_score(traj[i], 0.0)
        # Indices 2 and 4 are high-risk (skipping index 3)
        ps.hit_branch_expected_casualties = 5.0 if i in (2, 4) else 0.0
        point_scores.append(ps)

    engine = ScoringEngine.__new__(ScoringEngine)
    zones = engine._find_risk_zones(point_scores, threshold=1.0)
    assert len(zones) == 1
    assert zones[0].start_index == 2
    assert zones[0].end_index == 4
    assert zones[0].start_distance_m == traj[2].distance_from_start_m
    assert zones[0].end_distance_m == traj[4].distance_from_start_m


class TestEnuToWgs84NanFiltering:
    def test_nan_rows_filtered(self):
        enu = np.array([[100.0, 200.0], [np.nan, 300.0], [400.0, np.nan]])
        result = _enu_to_wgs84_fast(enu, 48.0, 31.0)
        assert result.shape[0] == 1
        assert np.isfinite(result).all()

    def test_inf_rows_filtered(self):
        enu = np.array([[100.0, 200.0], [np.inf, 300.0]])
        result = _enu_to_wgs84_fast(enu, 48.0, 31.0)
        assert result.shape[0] == 1

    def test_valid_rows_preserved(self):
        enu = np.array([[0.0, 0.0], [1000.0, 1000.0]])
        result = _enu_to_wgs84_fast(enu, 48.0, 31.0)
        assert result.shape[0] == 2
