# F02 — Coordinate Utilities + Trajectory Discretisation

**Status:** pending  
**Branch:** `feature/F02-coordinate-utilities`  
**Dependencies:** F01

---

## Goal

Implement the coordinate conversion library and trajectory discretisation. These are used by every downstream physics and casualty computation. Accuracy here is critical: off-by-one errors in coordinate frames produce silently wrong casualty estimates.

---

## Acceptance Criteria

- [ ] `enu_to_wgs84(east, north, origin_lat, origin_lon)` round-trips back to origin within 1 cm for displacements up to 500 km
- [ ] `wgs84_to_enu(lat, lon, origin_lat, origin_lon)` is the exact inverse of `enu_to_wgs84`
- [ ] `discretise_trajectory(state_vector, spacing_m, max_range_m)` returns a list of `TrajectoryPoint` at the requested spacing, all on the straight-line path
- [ ] Altitude is propagated correctly (constant in v1 — no terrain following)
- [ ] Heading convention: 0° = north, 90° = east, 180° = south, 270° = west
- [ ] All functions are vectorised (accept and return NumPy arrays where inputs are arrays)
- [ ] `pytest tests/unit/test_coordinates.py` passes

---

## Data Structures

```python
@dataclass
class StateVector:
    lat: float         # WGS84 decimal degrees
    lon: float         # WGS84 decimal degrees
    altitude_m: float  # MSL metres
    heading_deg: float # true heading 0–360
    speed_m_s: float   # ground speed m/s

@dataclass
class TrajectoryPoint:
    index: int
    lat: float
    lon: float
    altitude_m: float
    distance_from_start_m: float
```

Define these in `src/droneimpact/physics/types.py` (not `coords.py`) since they are used by physics, scoring, and API layers.

---

## Implementation Steps

### 1. src/droneimpact/coords.py

**`wgs84_to_enu(lat, lon, origin_lat, origin_lon) -> tuple[float, float]`**

Use `pyproj.Transformer` with `EPSG:4326` → local ENU projection centred on `(origin_lat, origin_lon)`. Build the transformer once per call (cache with `functools.lru_cache` keyed on origin rounded to 4 decimal places, i.e. ~10 m grid). Returns `(east_m, north_m)`.

**`enu_to_wgs84(east_m, north_m, origin_lat, origin_lon) -> tuple[float, float]`**

Inverse of above.

**`wgs84_to_enu_batch(lats, lons, origin_lat, origin_lon) -> np.ndarray`**

Accepts `(N,)` arrays, returns `(N, 2)` array of `[east, north]`. This is the hot path used by the physics engine.

**`enu_to_wgs84_batch(east_north, origin_lat, origin_lon) -> np.ndarray`**

Accepts `(N, 2)` ENU array, returns `(N, 2)` WGS84 array of `[lat, lon]`.

**`bearing_to_enu_angle(heading_deg) -> float`**

Convert from compass bearing (CW from north) to standard math angle (CCW from east) in radians. This conversion is needed before any trig in ENU space.

```python
# heading 0° (north) → angle 90° (π/2 rad)
# heading 90° (east) → angle 0°
# heading 180° (south) → angle 270° (3π/2 rad)
enu_angle_rad = np.radians(90.0 - heading_deg)
```

### 2. src/droneimpact/physics/trajectory.py

**`discretise_trajectory(sv: StateVector, spacing_m: float, max_range_m: float) -> list[TrajectoryPoint]`**

Algorithm:
1. Compute the heading in ENU angle (use `bearing_to_enu_angle`).
2. Generate distances `[0, spacing_m, 2*spacing_m, ..., max_range_m]` as a NumPy array.
3. Compute ENU offsets: `east = dist * cos(enu_angle)`, `north = dist * sin(enu_angle)`.
4. Convert each ENU point back to WGS84 using `enu_to_wgs84_batch` with the start position as origin.
5. Build `TrajectoryPoint` list with sequential indices.

Altitude is constant (v1 — no terrain following, no descent model). `altitude_m` is copied from the state vector for every point.

**Return:** list of `TrajectoryPoint`, length = `ceil(max_range_m / spacing_m) + 1`.

---

## Tests

### tests/unit/test_coordinates.py

**Round-trip accuracy:**
```python
@pytest.mark.parametrize("heading,dist", [
    (0, 1000), (90, 50000), (180, 100000), (270, 500000)
])
def test_enu_wgs84_roundtrip(heading, dist):
    origin_lat, origin_lon = 48.3794, 31.1656  # central Ukraine
    east = dist * math.sin(math.radians(heading))
    north = dist * math.cos(math.radians(heading))
    lat, lon = enu_to_wgs84(east, north, origin_lat, origin_lon)
    e2, n2 = wgs84_to_enu(lat, lon, origin_lat, origin_lon)
    assert abs(e2 - east) < 0.01  # 1 cm
    assert abs(n2 - north) < 0.01
```

**Heading convention:**
```python
def test_north_heading_moves_north():
    lat, lon = enu_to_wgs84(0, 1000, 48.0, 31.0)
    assert lat > 48.0
    assert abs(lon - 31.0) < 0.001  # negligible east offset

def test_east_heading_moves_east():
    lat, lon = enu_to_wgs84(1000, 0, 48.0, 31.0)
    assert lon > 31.0
    assert abs(lat - 48.0) < 0.001
```

**Trajectory discretisation:**
```python
def test_trajectory_spacing():
    sv = StateVector(lat=48.0, lon=31.0, altitude_m=400, heading_deg=0, speed_m_s=51.4)
    points = discretise_trajectory(sv, spacing_m=500, max_range_m=5000)
    assert len(points) == 11  # 0, 500, 1000, ..., 5000
    for i, p in enumerate(points):
        assert abs(p.distance_from_start_m - i * 500) < 0.1

def test_trajectory_heading_north():
    sv = StateVector(lat=48.0, lon=31.0, altitude_m=400, heading_deg=0, speed_m_s=51.4)
    points = discretise_trajectory(sv, spacing_m=1000, max_range_m=2000)
    for p in points[1:]:
        assert p.lat > 48.0
        assert abs(p.lon - 31.0) < 0.01

def test_trajectory_altitude_constant():
    sv = StateVector(lat=48.0, lon=31.0, altitude_m=350, heading_deg=45, speed_m_s=51.4)
    points = discretise_trajectory(sv, spacing_m=1000, max_range_m=5000)
    for p in points:
        assert p.altitude_m == 350.0
```

**Batch functions produce same results as scalar versions:**
```python
def test_batch_matches_scalar():
    origin = (48.0, 31.0)
    lats = np.array([48.1, 48.2, 47.9])
    lons = np.array([31.1, 30.9, 31.2])
    batch = wgs84_to_enu_batch(lats, lons, *origin)
    for i in range(len(lats)):
        scalar = wgs84_to_enu(lats[i], lons[i], *origin)
        assert abs(batch[i, 0] - scalar[0]) < 0.001
        assert abs(batch[i, 1] - scalar[1]) < 0.001
```

---

## Notes

- `pyproj.Transformer.from_crs("EPSG:4326", ...)` returns `(lat, lon)` in some versions and `(x, y)` in others depending on `always_xy` flag. Always pass `always_xy=True` to ensure `(x=lon, y=lat)` order.
- For the LRU cache: round origin to 4 decimal places (~11 m) before caching. This bounds cache size while keeping projection errors well below 1 mm at 500 km range.
- Do not use `geopy` for coordinate conversions — it is not vectorised. `pyproj` is the right tool.
