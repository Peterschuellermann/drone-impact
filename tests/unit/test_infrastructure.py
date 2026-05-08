import numpy as np
import pytest

from droneimpact.data.infrastructure import InfrastructureIndex


def _feat(lon, lat, category):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"category": category},
    }


@pytest.fixture
def infra_config(config):
    return config.casualty.infrastructure


@pytest.fixture
def hospital_index(infra_config):
    return InfrastructureIndex.from_features([_feat(31.0, 48.0, "hospital")], infra_config)


@pytest.fixture
def multi_index(infra_config):
    features = [
        _feat(31.0, 48.0, "hospital"),
        _feat(31.001, 48.001, "power_plant"),
    ]
    return InfrastructureIndex.from_features(features, infra_config)


def test_no_infra_zero_penalty(infra_config):
    idx = InfrastructureIndex.from_features([], infra_config)
    assert idx.penalty(48.0, 31.0) == 0.0


def test_direct_hit_hospital(hospital_index, infra_config):
    p = hospital_index.penalty(48.0, 31.0)
    assert p == pytest.approx(infra_config.weights.hospital, rel=0.01)


def test_far_from_hospital_zero(hospital_index):
    p = hospital_index.penalty(48.1, 31.0)  # ~11 km away
    assert p == 0.0


def test_penalty_decreases_with_distance(hospital_index):
    near = hospital_index.penalty(48.001, 31.0)
    far = hospital_index.penalty(48.003, 31.0)
    assert near > far


def test_multiple_facilities_stack(multi_index):
    p = multi_index.penalty(48.0005, 31.0005)
    assert p > 0.0


def test_penalty_capped_at_max(infra_config):
    features = [_feat(31.0, 48.0, cat) for cat in
                ("power_plant", "hospital", "water_works", "bridge", "school")]
    idx = InfrastructureIndex.from_features(features, infra_config)
    p = idx.penalty(48.0, 31.0)
    assert p <= infra_config.max_penalty


def test_batch_matches_scalar(hospital_index):
    lats = np.array([48.0, 48.001, 47.99])
    lons = np.array([31.0, 31.001, 30.99])
    batch = hospital_index.penalty_batch(lats, lons)
    for i in range(len(lats)):
        assert batch[i] == pytest.approx(hospital_index.penalty(lats[i], lons[i]), abs=0.01)


def test_batch_returns_float32(hospital_index):
    lats = np.array([48.0, 48.01])
    lons = np.array([31.0, 31.01])
    result = hospital_index.penalty_batch(lats, lons)
    assert result.dtype == np.float32
    assert result.shape == (2,)


def test_wrong_category_ignored(infra_config):
    features = [_feat(31.0, 48.0, "unknown_category")]
    idx = InfrastructureIndex.from_features(features, infra_config)
    assert idx.penalty(48.0, 31.0) == 0.0


def test_penalty_uses_max_not_sum(infra_config):
    """Spec requires max over all infra objects, not sum."""
    features = [
        _feat(31.0, 48.0, "hospital"),      # weight 4.0
        _feat(31.0, 48.0, "power_plant"),    # weight 5.0
    ]
    idx = InfrastructureIndex.from_features(features, infra_config)
    p = idx.penalty(48.0, 31.0)
    assert p == pytest.approx(infra_config.weights.power_plant, rel=0.01)
