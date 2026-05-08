import numpy as np
import pytest

from droneimpact.data.population import PopulationIndex
from tests.fixtures.population_small import make_test_population


@pytest.fixture
def populated_index():
    cells = make_test_population(centre_lat=48.0, centre_lon=31.0,
                                  pop_density=5000.0, radius_cells=3)
    return PopulationIndex.from_dict(cells)


@pytest.fixture
def empty_index():
    return PopulationIndex.from_dict({})


def test_query_populated_area(populated_index):
    pop = populated_index.query(48.0, 31.0, radius_m=500)
    assert pop > 0.0


def test_query_empty_area(empty_index):
    pop = empty_index.query(48.0, 31.0, radius_m=500)
    assert pop == 0.0


def test_query_far_from_cluster(populated_index):
    pop = populated_index.query(55.0, 40.0, radius_m=500)
    assert pop == 0.0


def test_larger_radius_returns_more_population(populated_index):
    small = populated_index.query(48.0, 31.0, radius_m=200)
    large = populated_index.query(48.0, 31.0, radius_m=1000)
    assert large >= small


def test_query_batch_matches_scalar(populated_index):
    lats = np.array([48.0, 48.01, 47.99])
    lons = np.array([31.0, 31.01, 30.99])
    batch = populated_index.query_batch(lats, lons, radius_m=500)
    for i in range(len(lats)):
        scalar = populated_index.query(lats[i], lons[i], 500)
        assert batch[i] == pytest.approx(scalar, rel=0.01)


def test_cell_count(populated_index):
    assert populated_index.cell_count > 0


def test_empty_cell_count(empty_index):
    assert empty_index.cell_count == 0


def test_resolution(populated_index):
    assert populated_index.resolution == 8


def test_from_dict_preserves_density():
    cells = {"8928308280fffff": 1000.0}
    idx = PopulationIndex.from_dict(cells)
    assert idx.cell_count == 1


def test_batch_returns_float32_array(populated_index):
    lats = np.array([48.0, 48.01])
    lons = np.array([31.0, 31.01])
    result = populated_index.query_batch(lats, lons, radius_m=300)
    assert result.dtype == np.float32
    assert result.shape == (2,)
