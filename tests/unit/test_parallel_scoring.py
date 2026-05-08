import numpy as np
import pytest

from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.data.dem import DEMIndex
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex
from droneimpact.physics.trajectory import discretise_trajectory
from droneimpact.physics.types import StateVector
from droneimpact.scoring.engine import ScoringEngine, clear_miss_cache
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
def long_trajectory():
    sv = StateVector(lat=48.3, lon=31.0, altitude_m=400.0, heading_deg=180.0, speed_m_s=51.4)
    return discretise_trajectory(sv, spacing_m=500, max_range_m=25000)


def _run_scoring(config, trajectory, flat_dem, casualty_engine, point_workers, seed=42):
    clear_miss_cache()
    engine = ScoringEngine(config, max_point_workers=point_workers)
    return engine.score_trajectory(
        trajectory, flat_dem, casualty_engine, (trajectory[0].lat, trajectory[0].lon),
        rng=np.random.default_rng(seed),
    )


class TestParallelDeterminism:
    def test_short_trajectory_same_scores(self, config, short_trajectory, flat_dem, casualty_engine):
        r1 = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=1)
        r4 = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=4)

        assert len(r1.trajectory_scores) == len(r4.trajectory_scores)
        for s1, s4 in zip(r1.trajectory_scores, r4.trajectory_scores):
            assert s1.engagement_score == pytest.approx(s4.engagement_score, rel=1e-10)

    def test_long_trajectory_same_scores(self, config, long_trajectory, flat_dem, casualty_engine):
        r1 = _run_scoring(config, long_trajectory, flat_dem, casualty_engine, point_workers=1)
        r4 = _run_scoring(config, long_trajectory, flat_dem, casualty_engine, point_workers=4)

        assert len(r1.trajectory_scores) == len(r4.trajectory_scores)
        for s1, s4 in zip(r1.trajectory_scores, r4.trajectory_scores):
            assert s1.engagement_score == pytest.approx(s4.engagement_score, rel=1e-10)

    def test_recommended_point_matches(self, config, short_trajectory, flat_dem, casualty_engine):
        r1 = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=1)
        r4 = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=4)
        assert r1.recommended_engagement.point_index == r4.recommended_engagement.point_index

    def test_impact_distributions_match(self, config, short_trajectory, flat_dem, casualty_engine):
        r1 = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=1)
        r4 = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=4)
        assert len(r1.impact_distributions) == len(r4.impact_distributions)
        for d1, d4 in zip(r1.impact_distributions, r4.impact_distributions):
            assert d1.point_index == d4.point_index
            assert d1.mode == d4.mode
            assert d1.impact_ellipse.semi_major_m == pytest.approx(
                d4.impact_ellipse.semi_major_m, rel=1e-10,
            )

    def test_different_seeds_produce_different_results(self, config, short_trajectory, flat_dem, casualty_engine):
        r_a = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=4, seed=0)
        r_b = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=4, seed=99)
        scores_a = [ps.engagement_score for ps in r_a.trajectory_scores]
        scores_b = [ps.engagement_score for ps in r_b.trajectory_scores]
        assert scores_a != scores_b


class TestParallelCorrectness:
    def test_result_length(self, config, short_trajectory, flat_dem, casualty_engine):
        result = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=4)
        assert len(result.trajectory_scores) == len(short_trajectory)

    def test_non_negative_scores(self, config, short_trajectory, flat_dem, casualty_engine):
        result = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=4)
        for ps in result.trajectory_scores:
            assert ps.engagement_score >= 0.0

    def test_ordered_distances(self, config, short_trajectory, flat_dem, casualty_engine):
        result = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=4)
        dists = [ps.distance_from_start_m for ps in result.trajectory_scores]
        assert dists == sorted(dists)

    def test_zones_generated(self, config, short_trajectory, flat_dem, casualty_engine):
        result = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=4)
        assert isinstance(result.engagement_zones, list)
        assert len(result.engagement_zones) >= 1

    def test_worker_count_one_matches_sequential(self, config, short_trajectory, flat_dem, casualty_engine):
        r1 = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=1)
        r1b = _run_scoring(config, short_trajectory, flat_dem, casualty_engine, point_workers=1)
        for s1, s1b in zip(r1.trajectory_scores, r1b.trajectory_scores):
            assert s1.engagement_score == pytest.approx(s1b.engagement_score, rel=1e-10)


class TestRNGIndependence:
    def test_spawned_rngs_differ(self):
        base = np.random.SeedSequence(42)
        children = base.spawn(5)
        rngs = [np.random.default_rng(s) for s in children]
        samples = [rng.random(10) for rng in rngs]
        for i in range(len(samples)):
            for j in range(i + 1, len(samples)):
                assert not np.allclose(samples[i], samples[j])

    def test_spawn_is_deterministic(self):
        base1 = np.random.SeedSequence(42)
        base2 = np.random.SeedSequence(42)
        children1 = base1.spawn(3)
        children2 = base2.spawn(3)
        for c1, c2 in zip(children1, children2):
            rng1 = np.random.default_rng(c1)
            rng2 = np.random.default_rng(c2)
            assert np.array_equal(rng1.random(100), rng2.random(100))
