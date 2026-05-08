# F07 — Population Data Layer

**Status:** pending  
**Branch:** `feature/F07-population-layer`  
**Dependencies:** F01

---

## Goal

Implement the population data layer. For each Monte Carlo impact point, the casualty engine needs to know the population density in the vicinity. This module loads the Kontur population dataset (H3-indexed at resolution 8, ~460 m hex cells) into memory and provides fast batch lookups.

The module must work in tests without any real Kontur data files — tests use a synthetic in-memory population grid.

---

## Acceptance Criteria

- [ ] `PopulationIndex.load_from_file(path)` loads a Kontur GPKG file into a dictionary keyed by H3 cell ID
- [ ] `PopulationIndex.from_dict(cell_dict)` creates an index from a `{h3_cell_str: population_per_km2}` dict — used in tests
- [ ] `PopulationIndex.query(lat, lon, radius_m) -> float` returns total exposed population within `radius_m` of a point
- [ ] `PopulationIndex.query_batch(lats, lons, radius_m) -> np.ndarray` is vectorised and returns the same values as `query` per-point
- [ ] Resolution is configurable (default: H3 resolution 8); index resolution is stored and exposed
- [ ] Querying a location with no population returns 0.0 (not an error)
- [ ] `pytest tests/unit/test_population.py` passes without data files

---

## Implementation Steps

### 1. src/droneimpact/data/population.py

**H3 background:** Each cell at resolution 8 covers ~0.74 km². A H3 k-ring of radius k around a centre cell covers (3k²+3k+1) cells. For a 400 m radius query:
- Resolution 8 cell diameter: ~460 m
- k=1 ring: 7 cells, covering radius ~460 m — sufficient for the blast radius
- k=2 ring: 19 cells, covering radius ~920 m — use for fragmentation radius

The module accepts `radius_m` and computes the appropriate k value.

```python
import h3
import numpy as np
from pathlib import Path

class PopulationIndex:
    def __init__(self, cell_data: dict[str, float], resolution: int = 8):
        # cell_data: {h3_cell_str: population_per_km2}
        self._data = cell_data
        self._resolution = resolution
        self._cell_area_km2 = h3.cell_area(
            next(iter(cell_data)) if cell_data else h3.geo_to_h3(0, 0, resolution),
            unit="km^2"
        )

    @classmethod
    def load_from_file(cls, path: str | Path, resolution: int = 8) -> "PopulationIndex":
        """
        Load Kontur GPKG file. Expected schema:
        - geometry: H3 hex polygon (WKB)
        - h3: H3 cell ID string (resolution 8)
        - population: population count in cell
        """
        import fiona
        cell_data: dict[str, float] = {}
        with fiona.open(path) as src:
            for feature in src:
                h3_id = feature["properties"]["h3"]
                pop   = feature["properties"]["population"]
                if pop and pop > 0:
                    area_km2 = h3.cell_area(h3_id, unit="km^2")
                    cell_data[h3_id] = pop / area_km2  # convert to density
        return cls(cell_data, resolution)

    @classmethod
    def from_dict(cls, cell_dict: dict[str, float], resolution: int = 8) -> "PopulationIndex":
        return cls(cell_dict, resolution)

    def _k_for_radius(self, radius_m: float) -> int:
        cell_diameter_m = self._cell_area_km2 ** 0.5 * 1000  # approximate
        return max(1, int(np.ceil(radius_m / cell_diameter_m)))

    def query(self, lat: float, lon: float, radius_m: float) -> float:
        centre_cell = h3.geo_to_h3(lat, lon, self._resolution)
        k = self._k_for_radius(radius_m)
        neighbourhood = h3.k_ring(centre_cell, k)
        total_pop_density = sum(self._data.get(cell, 0.0) for cell in neighbourhood)
        # Convert density back to count over the queried area
        area_km2 = len(neighbourhood) * self._cell_area_km2
        return total_pop_density * self._cell_area_km2  # population count in ring

    def query_batch(self, lats: np.ndarray, lons: np.ndarray, radius_m: float) -> np.ndarray:
        """
        Returns (N,) array of population counts within radius_m of each point.
        """
        return np.array([self.query(lat, lon, radius_m)
                         for lat, lon in zip(lats, lons)], dtype=np.float32)

    @property
    def resolution(self) -> int:
        return self._resolution

    @property
    def cell_count(self) -> int:
        return len(self._data)
```

**Performance note:** The `query_batch` implementation above uses a Python loop, which is fine for now. The hot path (10,000 Monte Carlo samples) will be optimised in F09 (Casualty Engine) by pre-computing H3 cell lookups for all samples simultaneously. F07 only needs to be correct, not maximally fast.

**`fiona` dependency:** Add `fiona>=1.9` to `pyproject.toml` deps.

---

## Tests

### tests/fixtures/

Create `tests/fixtures/population_small.py` (not a data file — a Python helper that generates synthetic population data as a dict):

```python
def make_test_population(centre_lat=48.0, centre_lon=31.0,
                          pop_density=5000.0, radius_cells=2) -> dict[str, float]:
    """Creates a synthetic population cluster around a centre point."""
    import h3
    centre = h3.geo_to_h3(centre_lat, centre_lon, 8)
    cells = h3.k_ring(centre, radius_cells)
    return {cell: pop_density for cell in cells}
```

### tests/unit/test_population.py

```python
@pytest.fixture
def populated_index():
    cells = make_test_population(centre_lat=48.0, centre_lon=31.0,
                                  pop_density=5000.0, radius_cells=3)
    return PopulationIndex.from_dict(cells)

def test_query_populated_area(populated_index):
    pop = populated_index.query(48.0, 31.0, radius_m=500)
    assert pop > 0.0

def test_query_empty_area():
    empty = PopulationIndex.from_dict({})
    pop = empty.query(48.0, 31.0, radius_m=500)
    assert pop == 0.0

def test_query_outside_populated_area(populated_index):
    # Far from the populated cluster
    pop = populated_index.query(55.0, 40.0, radius_m=500)
    assert pop == 0.0

def test_query_batch_matches_scalar(populated_index):
    lats = np.array([48.0, 48.01, 47.99])
    lons = np.array([31.0, 31.01, 30.99])
    batch = populated_index.query_batch(lats, lons, radius_m=500)
    for i in range(len(lats)):
        scalar = populated_index.query(lats[i], lons[i], radius_m=500)
        assert batch[i] == pytest.approx(scalar, rel=0.01)

def test_query_larger_radius_returns_more_population(populated_index):
    small = populated_index.query(48.0, 31.0, radius_m=200)
    large = populated_index.query(48.0, 31.0, radius_m=1000)
    assert large >= small

def test_cell_count(populated_index):
    assert populated_index.cell_count > 0

def test_resolution(populated_index):
    assert populated_index.resolution == 8
```

---

## Notes

- Kontur uses H3 resolution 8 in their public dataset. Do not assume resolution 9 (used in some older Kontur exports).
- `h3.geo_to_h3(lat, lon, resolution)` — note argument order is `(lat, lon)` NOT `(lon, lat)`.
- The Kontur GPKG for Ukraine is ~200 MB on disk. Loading it with `fiona` at startup will take several seconds; this is acceptable.
- `fiona` may need GDAL binaries. In Docker, these are available in `python:3.11-slim` via `pip install fiona` (uses pre-built wheels). Test in Docker if there are import issues.
- Population density is stored as `population / cell_area_km2`. The `query` method reconstructs population counts by multiplying density back by area. This avoids storing raw counts when the cell area varies slightly by latitude.
