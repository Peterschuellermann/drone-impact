import h3
import numpy as np
import pytest

from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.config import ShelteringClass, ShelteringConfig
from droneimpact.data.buildings import BuildingIndex
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex
from tests.fixtures.population_small import make_test_population

CENTRE = (48.0, 31.0)


def _make_infra(config, features=None):
    return InfrastructureIndex.from_features(
        features or [], config.casualty.infrastructure
    )


def _make_building_features(lat, lon, building_tag, count=20):
    return [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon + i * 0.0001, lat + i * 0.0001],
            },
            "properties": {"building": building_tag},
        }
        for i in range(count)
    ]


# --- BuildingIndex unit tests ---


class TestBuildingIndex:
    def test_empty_returns_zero_reductions(self):
        idx = BuildingIndex.empty(ShelteringConfig())
        lats = np.array([48.0, 49.0])
        lons = np.array([31.0, 32.0])
        blast_red, frag_red = idx.sheltering_factor_batch(lats, lons)
        assert blast_red.shape == (2,)
        assert frag_red.shape == (2,)
        np.testing.assert_array_equal(blast_red, 0.0)
        np.testing.assert_array_equal(frag_red, 0.0)

    def test_reinforced_concrete_reductions(self):
        cfg = ShelteringConfig()
        features = _make_building_features(*CENTRE, "apartments")
        idx = BuildingIndex.from_features(features, cfg)
        assert idx.cell_count > 0
        lats = np.array([CENTRE[0]])
        lons = np.array([CENTRE[1]])
        blast_red, frag_red = idx.sheltering_factor_batch(lats, lons)
        assert blast_red[0] == pytest.approx(0.80)
        assert frag_red[0] == pytest.approx(0.90)

    def test_masonry_reductions(self):
        cfg = ShelteringConfig()
        features = _make_building_features(*CENTRE, "residential")
        idx = BuildingIndex.from_features(features, cfg)
        lats = np.array([CENTRE[0]])
        lons = np.array([CENTRE[1]])
        blast_red, frag_red = idx.sheltering_factor_batch(lats, lons)
        assert blast_red[0] == pytest.approx(0.50)
        assert frag_red[0] == pytest.approx(0.70)

    def test_light_structure_reductions(self):
        cfg = ShelteringConfig()
        features = _make_building_features(*CENTRE, "house")
        idx = BuildingIndex.from_features(features, cfg)
        lats = np.array([CENTRE[0]])
        lons = np.array([CENTRE[1]])
        blast_red, frag_red = idx.sheltering_factor_batch(lats, lons)
        assert blast_red[0] == pytest.approx(0.10)
        assert frag_red[0] == pytest.approx(0.30)

    def test_unknown_tag_ignored(self):
        cfg = ShelteringConfig()
        features = _make_building_features(*CENTRE, "unknown_type")
        idx = BuildingIndex.from_features(features, cfg)
        assert idx.cell_count == 0

    def test_dominant_class_wins(self):
        """When multiple building types share a cell, the most common one wins."""
        cfg = ShelteringConfig()
        concrete = _make_building_features(*CENTRE, "apartments", count=15)
        masonry = _make_building_features(*CENTRE, "residential", count=5)
        idx = BuildingIndex.from_features(concrete + masonry, cfg)
        lats = np.array([CENTRE[0]])
        lons = np.array([CENTRE[1]])
        blast_red, frag_red = idx.sheltering_factor_batch(lats, lons)
        assert blast_red[0] == pytest.approx(0.80)
        assert frag_red[0] == pytest.approx(0.90)

    def test_no_data_cell_returns_zero(self):
        cfg = ShelteringConfig()
        features = _make_building_features(*CENTRE, "apartments")
        idx = BuildingIndex.from_features(features, cfg)
        lats = np.array([55.0])
        lons = np.array([40.0])
        blast_red, frag_red = idx.sheltering_factor_batch(lats, lons)
        assert blast_red[0] == 0.0
        assert frag_red[0] == 0.0

    def test_config_controls_reductions(self):
        cfg = ShelteringConfig(
            reinforced_concrete=ShelteringClass(
                osm_tags=["apartments"],
                blast_reduction=0.95,
                frag_reduction=0.99,
            ),
        )
        features = _make_building_features(*CENTRE, "apartments")
        idx = BuildingIndex.from_features(features, cfg)
        lats = np.array([CENTRE[0]])
        lons = np.array([CENTRE[1]])
        blast_red, frag_red = idx.sheltering_factor_batch(lats, lons)
        assert blast_red[0] == pytest.approx(0.95)
        assert frag_red[0] == pytest.approx(0.99)


# --- CasualtyEngine sheltering integration tests ---


class TestShelteringIntegration:
    def test_sheltering_reduces_casualties(self, config):
        """Urban sheltering should significantly reduce casualties."""
        cells = make_test_population(*CENTRE, pop_density=5000.0, radius_cells=5)
        pop = PopulationIndex.from_dict(cells)
        infra = _make_infra(config)
        pts = np.tile(CENTRE, (100, 1)).astype(np.float64)

        eng_no_shelter = CasualtyEngine(pop, infra, config.casualty)
        base = eng_no_shelter.compute(pts)

        features = _make_building_features(*CENTRE, "apartments", count=50)
        buildings = BuildingIndex.from_features(features, config.casualty.sheltering)
        eng_sheltered = CasualtyEngine(pop, infra, config.casualty, buildings=buildings)
        sheltered = eng_sheltered.compute(pts)

        assert sheltered < base
        reduction_pct = 1.0 - sheltered / base
        assert reduction_pct > 0.40

    def test_missing_building_data_no_change(self, config):
        """Without building data, casualties match the unsheltered baseline."""
        cells = make_test_population(*CENTRE, pop_density=5000.0, radius_cells=5)
        pop = PopulationIndex.from_dict(cells)
        infra = _make_infra(config)
        pts = np.tile(CENTRE, (100, 1)).astype(np.float64)

        eng_default = CasualtyEngine(pop, infra, config.casualty)
        eng_empty = CasualtyEngine(
            pop, infra, config.casualty,
            buildings=BuildingIndex.empty(config.casualty.sheltering),
        )

        assert eng_default.compute(pts) == pytest.approx(eng_empty.compute(pts))

    def test_light_shelter_less_than_concrete(self, config):
        """Light structures provide less protection than reinforced concrete."""
        cells = make_test_population(*CENTRE, pop_density=5000.0, radius_cells=5)
        pop = PopulationIndex.from_dict(cells)
        infra = _make_infra(config)
        pts = np.tile(CENTRE, (100, 1)).astype(np.float64)

        concrete_feats = _make_building_features(*CENTRE, "apartments", count=50)
        concrete_idx = BuildingIndex.from_features(concrete_feats, config.casualty.sheltering)
        eng_concrete = CasualtyEngine(pop, infra, config.casualty, buildings=concrete_idx)

        light_feats = _make_building_features(*CENTRE, "house", count=50)
        light_idx = BuildingIndex.from_features(light_feats, config.casualty.sheltering)
        eng_light = CasualtyEngine(pop, infra, config.casualty, buildings=light_idx)

        assert eng_light.compute(pts) > eng_concrete.compute(pts)

    def test_sheltered_per_point_shape(self, config):
        cells = make_test_population(*CENTRE, pop_density=5000.0, radius_cells=5)
        pop = PopulationIndex.from_dict(cells)
        infra = _make_infra(config)
        features = _make_building_features(*CENTRE, "apartments", count=50)
        buildings = BuildingIndex.from_features(features, config.casualty.sheltering)
        eng = CasualtyEngine(pop, infra, config.casualty, buildings=buildings)

        pts = np.tile(CENTRE, (50, 1)).astype(np.float64)
        result = eng.compute_per_point(pts)
        assert result.shape == (50,)
        assert result.dtype == np.float64
        assert np.all(result >= 0.0)
