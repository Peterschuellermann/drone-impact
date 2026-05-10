"""Tests for infrastructure bbox query and map overlay."""
from __future__ import annotations

import folium
import numpy as np
import pytest

from droneimpact.config import InfraConfig, InfraWeights
from droneimpact.dashboard.components import INFRA_STYLES, add_infrastructure_layer
from droneimpact.data.infrastructure import InfrastructureIndex


def _make_infra_config() -> InfraConfig:
    return InfraConfig(
        penalty_radius_m=500.0,
        max_penalty=10.0,
        weights=InfraWeights(
            power_plant=5.0, hospital=4.0, water_works=4.0,
            bridge=3.0, school=2.0,
        ),
    )


def _make_features(
    category: str,
    coords: list[tuple[float, float]],
) -> list[dict]:
    return [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"category": category},
        }
        for lat, lon in coords
    ]


class TestGetFeaturesInBbox:
    @pytest.fixture
    def index(self):
        features = (
            _make_features("hospital", [(48.0, 35.0), (48.5, 35.5), (49.0, 36.0)])
            + _make_features("school", [(48.1, 35.1), (50.0, 37.0)])
            + _make_features("bridge", [(48.2, 35.2)])
        )
        return InfrastructureIndex.from_features(features, _make_infra_config())

    def test_returns_all_in_bbox(self, index):
        result = index.get_features_in_bbox(47.0, 34.0, 50.0, 37.0)
        total = sum(len(v) for v in result.values())
        assert total == 6

    def test_filters_by_bbox(self, index):
        result = index.get_features_in_bbox(47.5, 34.5, 48.6, 35.6)
        hospitals = result.get("hospital", np.empty((0, 2)))
        assert len(hospitals) == 2
        for lat, lon in hospitals:
            assert 47.5 <= lat <= 48.6
            assert 34.5 <= lon <= 35.6

    def test_filters_by_category(self, index):
        result = index.get_features_in_bbox(47.0, 34.0, 50.0, 37.0, categories=["hospital"])
        assert "hospital" in result
        assert "school" not in result
        assert "bridge" not in result

    def test_empty_bbox_returns_empty(self, index):
        result = index.get_features_in_bbox(0.0, 0.0, 0.1, 0.1)
        assert len(result) == 0

    def test_returns_lat_lon_order(self, index):
        result = index.get_features_in_bbox(47.0, 34.0, 50.0, 37.0)
        for cat, arr in result.items():
            assert arr.shape[1] == 2
            for lat, lon in arr:
                assert 47.0 <= lat <= 50.0
                assert 34.0 <= lon <= 37.0

    def test_unknown_category_ignored(self, index):
        result = index.get_features_in_bbox(47.0, 34.0, 50.0, 37.0, categories=["dam"])
        assert len(result) == 0


class TestFeatureCounts:
    def test_counts_match(self):
        features = (
            _make_features("hospital", [(48.0, 35.0), (48.5, 35.5)])
            + _make_features("school", [(48.1, 35.1)])
        )
        index = InfrastructureIndex.from_features(features, _make_infra_config())
        counts = index.feature_counts()
        assert counts["hospital"] == 2
        assert counts["school"] == 1

    def test_categories_property(self):
        features = _make_features("bridge", [(48.0, 35.0)])
        index = InfrastructureIndex.from_features(features, _make_infra_config())
        assert "bridge" in index.categories


class TestAddInfrastructureLayer:
    def test_returns_map(self):
        m = folium.Map(location=[48.0, 35.0], zoom_start=8)
        infra_data = {
            "features": {"hospital": [[48.0, 35.0], [48.1, 35.1]]},
        }
        result = add_infrastructure_layer(m, infra_data)
        assert isinstance(result, folium.Map)

    def test_renders_html(self):
        m = folium.Map(location=[48.0, 35.0], zoom_start=8)
        infra_data = {
            "features": {"hospital": [[48.0, 35.0]]},
        }
        add_infrastructure_layer(m, infra_data, enabled_categories=["hospital"])
        html = m._repr_html_()
        assert "Hospital" in html

    def test_empty_features_no_error(self):
        m = folium.Map(location=[48.0, 35.0], zoom_start=8)
        result = add_infrastructure_layer(m, {"features": {}})
        assert isinstance(result, folium.Map)

    def test_only_enabled_categories_rendered(self):
        m = folium.Map(location=[48.0, 35.0], zoom_start=8)
        infra_data = {
            "features": {
                "hospital": [[48.0, 35.0]],
                "school": [[48.1, 35.1]],
            },
        }
        add_infrastructure_layer(m, infra_data, enabled_categories=["hospital"])
        html = m._repr_html_()
        assert "Hospital" in html
        assert "School" not in html

    def test_infra_styles_has_all_categories(self):
        from droneimpact.data.infrastructure import CATEGORIES
        for cat in CATEGORIES:
            assert cat in INFRA_STYLES
