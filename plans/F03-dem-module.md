# F03 — DEM Module

**Status:** pending  
**Branch:** `feature/F03-dem-module`  
**Dependencies:** F01

---

## Goal

Implement the Digital Elevation Model (DEM) module. The physics engine needs Above-Ground-Level (AGL) altitude for each evaluation point and each Monte Carlo impact point. AGL = MSL altitude − terrain elevation. The DEM module provides terrain elevation lookups from a pre-loaded GeoTIFF (SRTM data).

The module must work correctly in tests without actual DEM data files on disk, using a synthetic in-memory fixture instead.

---

## Acceptance Criteria

- [ ] `DEMIndex.get_elevation(lat, lon) -> float` returns terrain elevation in metres MSL
- [ ] `DEMIndex.get_elevation_batch(lats, lons) -> np.ndarray` is vectorised and returns the same results as calling `get_elevation` per-point
- [ ] `DEMIndex.msl_to_agl(lat, lon, altitude_msl) -> float` returns non-negative AGL (clamped at 0 for points at or below terrain)
- [ ] Bilinear interpolation is used for sub-pixel accuracy
- [ ] `DEMIndex.load_from_file(path)` loads a real GeoTIFF; returns a working index
- [ ] `DEMIndex.from_array(data, bounds, crs)` creates an index from a NumPy array — used in tests
- [ ] Out-of-bounds coordinates raise `DEMOutOfBoundsError` with a message containing the offending lat/lon
- [ ] `pytest tests/unit/test_dem.py` passes without any data files on disk

---

## Implementation Steps

### 1. src/droneimpact/data/dem.py

**`DEMOutOfBoundsError(ValueError)`** — raised when a coordinate falls outside the DEM extent.

**`DEMIndex`** class:

```python
class DEMIndex:
    def __init__(self, data: np.ndarray, transform, crs):
        # data: (rows, cols) float32 array of elevation in metres
        # transform: rasterio Affine transform (pixel → geographic coords)
        # crs: coordinate reference system (should be EPSG:4326)
        ...

    @classmethod
    def load_from_file(cls, path: str | Path) -> "DEMIndex":
        """Load GeoTIFF from disk. Reads entire raster into memory as float32."""
        with rasterio.open(path) as src:
            data = src.read(1).astype(np.float32)
            return cls(data, src.transform, src.crs)

    @classmethod
    def from_array(cls, data: np.ndarray, west: float, south: float,
                   east: float, north: float) -> "DEMIndex":
        """Create from NumPy array with geographic bounds. Used in tests."""
        transform = rasterio.transform.from_bounds(west, south, east, north,
                                                    data.shape[1], data.shape[0])
        return cls(data, transform, "EPSG:4326")

    def _latlon_to_pixel(self, lat: float, lon: float) -> tuple[float, float]:
        """Convert lat/lon to fractional pixel (row, col). Raises DEMOutOfBoundsError."""
        ...

    def get_elevation(self, lat: float, lon: float) -> float:
        """Bilinear interpolation at (lat, lon)."""
        ...

    def get_elevation_batch(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        """Vectorised bilinear interpolation. Returns (N,) float32 array."""
        ...

    def msl_to_agl(self, lat: float, lon: float, altitude_msl: float) -> float:
        return max(0.0, altitude_msl - self.get_elevation(lat, lon))

    def msl_to_agl_batch(self, lats: np.ndarray, lons: np.ndarray,
                          altitude_msl: float) -> np.ndarray:
        """Returns (N,) array of AGL altitudes, clamped at 0."""
        terrain = self.get_elevation_batch(lats, lons)
        return np.maximum(0.0, altitude_msl - terrain)
```

**Bilinear interpolation algorithm** (implement manually in NumPy for the batch case — do not use `scipy.interpolate.RegularGridInterpolator` as it is too slow for 10,000 samples):

```
Given fractional pixel (r, c):
  r0, c0 = floor(r), floor(c)
  r1, c1 = r0+1, c0+1
  dr = r - r0, dc = c - c0
  
  value = (1-dr)*(1-dc)*data[r0,c0]
        + (1-dr)*dc    *data[r0,c1]
        + dr    *(1-dc)*data[r1,c0]
        + dr    *dc    *data[r1,c1]
```

For the batch version, vectorise this over all N samples simultaneously using NumPy indexing and broadcasting. Clip pixel coordinates to valid array bounds before indexing (handle edge pixels gracefully).

---

## Tests

### tests/unit/test_dem.py

**Fixture: 10×10 synthetic DEM**

```python
@pytest.fixture
def flat_dem():
    data = np.full((10, 10), 100.0, dtype=np.float32)  # flat 100m terrain
    return DEMIndex.from_array(data, west=30.0, south=47.0, east=32.0, north=49.0)

@pytest.fixture
def sloped_dem():
    # Elevation increases from south (0m) to north (900m)
    rows = np.linspace(0, 900, 10, dtype=np.float32)
    data = np.tile(rows[:, None], (1, 10))
    return DEMIndex.from_array(data, west=30.0, south=47.0, east=32.0, north=49.0)
```

**Tests:**
```python
def test_flat_dem_elevation(flat_dem):
    assert flat_dem.get_elevation(48.0, 31.0) == pytest.approx(100.0, abs=0.1)

def test_flat_dem_agl(flat_dem):
    assert flat_dem.msl_to_agl(48.0, 31.0, 500.0) == pytest.approx(400.0, abs=0.1)

def test_agl_clamped_at_zero(flat_dem):
    assert flat_dem.msl_to_agl(48.0, 31.0, 50.0) == 0.0  # below terrain

def test_bilinear_interpolation(sloped_dem):
    # At south edge (row=0), elevation should be ~0m
    # At north edge (row=last), elevation should be ~900m
    south_elev = sloped_dem.get_elevation(47.0, 31.0)
    north_elev = sloped_dem.get_elevation(49.0, 31.0)
    assert south_elev < 50.0
    assert north_elev > 850.0

def test_batch_matches_scalar(flat_dem):
    lats = np.array([47.5, 48.0, 48.5])
    lons = np.array([30.5, 31.0, 31.5])
    batch = flat_dem.get_elevation_batch(lats, lons)
    for i in range(len(lats)):
        assert batch[i] == pytest.approx(flat_dem.get_elevation(lats[i], lons[i]), abs=0.001)

def test_out_of_bounds_raises(flat_dem):
    with pytest.raises(DEMOutOfBoundsError):
        flat_dem.get_elevation(55.0, 31.0)  # outside DEM bounds

def test_batch_agl_clamped(sloped_dem):
    lats = np.array([47.05, 47.1, 47.2])
    lons = np.array([31.0, 31.0, 31.0])
    agl = sloped_dem.msl_to_agl_batch(lats, lons, 0.0)  # altitude below terrain
    assert np.all(agl == 0.0)
```

---

## Notes

- SRTM data has 1 arc-second (~30 m) resolution. The Ukraine bounding box (44°N–53°N, 22°E–41°E) is roughly 19°×19°, which at 30 m resolution is ~2,280×2,280 pixels = ~20 MB as float32. This is well within budget.
- NoData pixels (ocean, water bodies) in SRTM are typically coded as -32768. Replace with 0 on load: `data = np.where(data == -32768, 0.0, data)`.
- The DEM is loaded in F11 (startup). F03 only implements the module; it does not wire it into the startup sequence.
- rasterio is the DEM loading dependency. It is already in the project deps from F01.
