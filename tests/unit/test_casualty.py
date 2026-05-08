import numpy as np
import pytest

from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex
from tests.fixtures.population_small import make_test_population

CENTRE = (48.0, 31.0)


def _make_infra(config, features=None):
    return InfrastructureIndex.from_features(
        features or [], config.casualty.infrastructure
    )


@pytest.fixture
def empty_engine(config):
    pop = PopulationIndex.from_dict({})
    infra = _make_infra(config)
    return CasualtyEngine(pop, infra, config.casualty)


@pytest.fixture
def populated_engine(config):
    cells = make_test_population(*CENTRE, pop_density=5000.0, radius_cells=5)
    pop = PopulationIndex.from_dict(cells)
    infra = _make_infra(config)
    return CasualtyEngine(pop, infra, config.casualty)


@pytest.fixture
def infra_engine(config):
    cells = make_test_population(*CENTRE, pop_density=5000.0, radius_cells=5)
    pop = PopulationIndex.from_dict(cells)
    features = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [31.0, 48.0]},
        "properties": {"category": "hospital"},
    }]
    infra = _make_infra(config, features)
    return CasualtyEngine(pop, infra, config.casualty)


def test_zero_pop_zero_casualties(empty_engine):
    pts = np.array([[48.0, 31.0], [48.01, 31.01]])
    assert empty_engine.compute(pts) == 0.0


def test_populated_area_positive_casualties(populated_engine):
    pts = np.tile(CENTRE, (100, 1)).astype(np.float64)
    assert populated_engine.compute(pts) > 0.0


def test_casualties_scale_with_population(config):
    low_cells = make_test_population(*CENTRE, pop_density=100.0, radius_cells=5)
    high_cells = make_test_population(*CENTRE, pop_density=10000.0, radius_cells=5)
    infra = _make_infra(config)
    eng_low = CasualtyEngine(PopulationIndex.from_dict(low_cells), infra, config.casualty)
    eng_high = CasualtyEngine(PopulationIndex.from_dict(high_cells), infra, config.casualty)
    pts = np.tile(CENTRE, (100, 1)).astype(np.float64)
    assert eng_high.compute(pts) > eng_low.compute(pts)


def test_infra_inflates_casualties(populated_engine, infra_engine):
    pts = np.tile(CENTRE, (200, 1)).astype(np.float64)
    base = populated_engine.compute(pts)
    with_infra = infra_engine.compute(pts)
    assert with_infra > base


def test_compute_per_point_shape(populated_engine):
    rng = np.random.default_rng(0)
    pts = rng.uniform(size=(200, 2)) * 0.05 + np.array(CENTRE)
    result = populated_engine.compute_per_point(pts)
    assert result.shape == (200,)
    assert np.all(result >= 0.0)


def test_compute_per_point_dtype(populated_engine):
    pts = np.tile(CENTRE, (10, 1)).astype(np.float64)
    result = populated_engine.compute_per_point(pts)
    assert result.dtype == np.float64


def test_far_from_population_zero(config):
    cells = make_test_population(*CENTRE, pop_density=5000.0, radius_cells=2)
    pop = PopulationIndex.from_dict(cells)
    infra = _make_infra(config)
    eng = CasualtyEngine(pop, infra, config.casualty)
    # Points far from the cluster
    pts = np.array([[55.0, 40.0], [55.01, 40.01]])
    assert eng.compute(pts) == 0.0
