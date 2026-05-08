# F08 — Infrastructure Data Layer

**Status:** pending  
**Branch:** `feature/F08-infrastructure-layer`  
**Dependencies:** F01

---

## Goal

Implement the critical infrastructure scoring module. When an impact point is near a hospital, power plant, water works, bridge, or school, the casualty estimate is multiplied by a penalty factor reflecting the strategic significance of damaging that infrastructure. This module loads infrastructure point/polygon data from an OSM GeoJSON file and provides fast nearest-object queries using an R-tree spatial index.

---

## Acceptance Criteria

- [ ] `InfrastructureIndex.load_from_file(path)` loads a GeoJSON file and builds per-category R-trees
- [ ] `InfrastructureIndex.from_features(features)` creates an index from a list of GeoJSON-style feature dicts — used in tests
- [ ] `InfrastructureIndex.penalty(lat, lon) -> float` returns the penalty multiplier (≥ 0.0) for a single point
- [ ] `InfrastructureIndex.penalty_batch(lats, lons) -> np.ndarray` returns `(N,)` penalties
- [ ] Points far from all infrastructure return penalty 0.0
- [ ] Multiple nearby facilities stack (highest penalty wins OR additive — see spec; implement additive)
- [ ] Penalty is bounded: max total penalty is configurable (`max_penalty` in config)
- [ ] `pytest tests/unit/test_infrastructure.py` passes without data files

---

## Penalty Model

From `/spec/casualty-model.md` and `config.yaml`:

```
penalty(point) = Σ_category [weight_cat * decay_fn(dist_to_nearest_cat)]
```

where:
- `weight_cat` is the category weight (e.g. power_plant=5.0, hospital=4.0)
- `decay_fn` is a linear decay from 1.0 at distance 0 to 0.0 at `penalty_radius_m` (500 m default)
- Only the nearest feature in each category contributes
- Final penalty is clipped to `config.casualty.infrastructure.max_penalty` (default: 10.0 — add this to config)

```python
decay(dist, radius) = max(0.0, 1.0 - dist / radius)
penalty = Σ_cat weight_cat * decay(nearest_dist_cat, penalty_radius_m)
penalty = min(penalty, max_penalty)
```

---

## Implementation Steps

### 1. src/droneimpact/data/infrastructure.py

**Supported categories:** `power_plant`, `hospital`, `water_works`, `bridge`, `school`

```python
from shapely.geometry import Point, shape
from shapely.strtree import STRtree
import numpy as np
import json
from pathlib import Path

CATEGORIES = ["power_plant", "hospital", "water_works", "bridge", "school"]

class InfrastructureIndex:
    def __init__(self, trees: dict[str, STRtree],
                 coords: dict[str, np.ndarray],
                 config: "InfraConfig"):
        # trees: category → STRtree of shapely geometries
        # coords: category → (M, 2) array of [lon, lat] for fast numpy distance
        self._trees  = trees
        self._coords = coords
        self._config = config

    @classmethod
    def load_from_file(cls, path: str | Path, config: "InfraConfig") -> "InfrastructureIndex":
        with open(path) as f:
            geojson = json.load(f)
        features = geojson.get("features", [])
        return cls.from_features(features, config)

    @classmethod
    def from_features(cls, features: list[dict],
                       config: "InfraConfig") -> "InfrastructureIndex":
        by_category: dict[str, list] = {cat: [] for cat in CATEGORIES}
        for feat in features:
            cat = feat.get("properties", {}).get("category")
            if cat in by_category:
                geom = shape(feat["geometry"])
                by_category[cat].append(geom.centroid)  # use centroid for polygons

        trees  = {}
        coords = {}
        for cat, geoms in by_category.items():
            if geoms:
                trees[cat]  = STRtree(geoms)
                coords[cat] = np.array([[g.x, g.y] for g in geoms])  # [lon, lat]
        return cls(trees, coords, config)

    def _nearest_distance_m(self, lon: float, lat: float, category: str) -> float:
        """Returns distance in metres to nearest feature of given category."""
        if category not in self._trees:
            return float("inf")
        pt = Point(lon, lat)
        nearest = self._trees[category].nearest(pt)
        if nearest is None:
            return float("inf")
        # Approximate metres conversion: 1° lat ≈ 111,000 m
        dlat = (nearest.y - lat) * 111_000
        dlon = (nearest.x - lon) * 111_000 * np.cos(np.radians(lat))
        return float(np.sqrt(dlat**2 + dlon**2))

    def penalty(self, lat: float, lon: float) -> float:
        total = 0.0
        radius = self._config.penalty_radius_m
        for cat in CATEGORIES:
            weight = getattr(self._config.weights, cat.replace(" ", "_"), 0.0)
            dist   = self._nearest_distance_m(lon, lat, cat)
            total += weight * max(0.0, 1.0 - dist / radius)
        return min(total, self._config.max_penalty)

    def penalty_batch(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        return np.array([self.penalty(lat, lon)
                         for lat, lon in zip(lats, lons)], dtype=np.float32)
```

**Config additions required:** Add `max_penalty: 10.0` to `casualty.infrastructure` in `config.yaml`.

---

## Tests

### tests/unit/test_infrastructure.py

**Fixture helpers:**
```python
def make_feature(lon, lat, category):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"category": category}
    }
```

```python
@pytest.fixture
def infra_config(config):
    return config.casualty.infrastructure

@pytest.fixture
def hospital_index(infra_config):
    features = [make_feature(31.0, 48.0, "hospital")]
    return InfrastructureIndex.from_features(features, infra_config)

@pytest.fixture
def multi_infra_index(infra_config):
    features = [
        make_feature(31.0, 48.0, "hospital"),
        make_feature(31.001, 48.001, "power_plant"),
    ]
    return InfrastructureIndex.from_features(features, infra_config)
```

```python
def test_no_infra_zero_penalty(infra_config):
    idx = InfrastructureIndex.from_features([], infra_config)
    assert idx.penalty(48.0, 31.0) == 0.0

def test_direct_hit_on_hospital(hospital_index):
    # At the hospital location, penalty should be near maximum for hospital weight
    p = hospital_index.penalty(48.0, 31.0)
    hospital_weight = hospital_index._config.weights.hospital
    assert p == pytest.approx(hospital_weight, rel=0.01)

def test_far_from_hospital_zero_penalty(hospital_index):
    # 5 km away
    p = hospital_index.penalty(48.05, 31.0)
    assert p == 0.0

def test_penalty_decreases_with_distance(hospital_index):
    p_near = hospital_index.penalty(48.001, 31.0)
    p_far  = hospital_index.penalty(48.003, 31.0)
    assert p_near > p_far

def test_multiple_facilities_stack(multi_infra_index):
    p_multi = multi_infra_index.penalty(48.0005, 31.0005)  # between hospital and power plant
    assert p_multi > 0.0  # non-zero

def test_penalty_capped_at_max(infra_config):
    # Create index with many overlapping high-weight facilities
    features = [make_feature(31.0, 48.0, cat) for cat in CATEGORIES]
    idx = InfrastructureIndex.from_features(features, infra_config)
    p = idx.penalty(48.0, 31.0)
    assert p <= infra_config.max_penalty

def test_batch_matches_scalar(hospital_index):
    lats = np.array([48.0, 48.01, 47.99])
    lons = np.array([31.0, 31.01, 30.99])
    batch = hospital_index.penalty_batch(lats, lons)
    for i in range(len(lats)):
        assert batch[i] == pytest.approx(hospital_index.penalty(lats[i], lons[i]), abs=0.01)
```

---

## Notes

- The distance formula in `_nearest_distance_m` uses the flat-earth approximation (valid for distances < 500 m by a wide margin for this use case). No need for haversine here.
- `STRtree.nearest` returns the nearest geometry object (shapely >= 2.0). In older versions, it returns an integer index. Pin `shapely>=2.0` in `pyproject.toml`.
- The batch version is a Python loop in F08 — the hot path optimisation belongs in F09.
- OSM infrastructure data for Ukraine will be extracted as a GeoJSON in the data pipeline (not part of this plan). The file format expected by `load_from_file` is a standard GeoJSON FeatureCollection with each feature having a `category` property matching one of the five categories.
