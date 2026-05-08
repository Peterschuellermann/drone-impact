import numpy as np
import pytest

from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.data.dem import DEMIndex
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex
from droneimpact.physics.trajectory import discretise_trajectory
from droneimpact.physics.types import StateVector
from droneimpact.scoring.engine import ScoringEngine
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


def test_mode_weights_in_breakdown(scoring, short_trajectory, flat_dem, casualty_engine):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(2)
    )
    for ps in result.trajectory_scores:
        assert set(ps.breakdown.keys()) == {"propulsion_loss", "loss_of_control", "break_apart"}


def test_reasoning_nonempty(scoring, short_trajectory, flat_dem, casualty_engine):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(3)
    )
    assert isinstance(result.recommended_engagement.reasoning, str)
    assert len(result.recommended_engagement.reasoning) > 5


def test_impact_distributions_count(scoring, short_trajectory, flat_dem, casualty_engine):
    result = scoring.score_trajectory(
        short_trajectory, flat_dem, casualty_engine, (48.1, 31.0),
        rng=np.random.default_rng(4)
    )
    # 3 modes × n_points
    assert len(result.impact_distributions) == len(short_trajectory) * 3


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


def test_interpolation_preserves_scored_points():
    traj = _make_trajectory(5)
    scored = {i: _make_point_score(traj[i], float(i * 10)) for i in range(5)}
    result = ScoringEngine._interpolate_scores(traj, scored, 0.0)
    for i in range(5):
        assert result[i] is scored[i]


def test_interpolation_fills_gaps():
    traj = _make_trajectory(10)
    scored = {
        0: _make_point_score(traj[0], 10.0),
        5: _make_point_score(traj[5], 20.0),
        9: _make_point_score(traj[9], 30.0),
    }
    result = ScoringEngine._interpolate_scores(traj, scored, 0.0)
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
        result = ScoringEngine._interpolate_scores(traj, scored, 0.0)
        assert len(result) == n
