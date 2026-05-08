# F04 — Physics Engine: Mode M1 Propulsion Loss

**Status:** pending  
**Branch:** `feature/F04-physics-m1`  
**Dependencies:** F01, F02, F03

---

## Goal

Implement the Mode M1 (propulsion loss) terminal trajectory simulation. When a Shahed-136 loses propulsion at a given position and altitude, it transitions to an unpowered glide. The drone retains active control surfaces (guidance may still be live or may have failed — spec treats this as a stochastic glide with heading uncertainty). The simulation returns a distribution of ground impact points via Monte Carlo sampling.

---

## Acceptance Criteria

- [ ] `simulate_m1(pos, altitude_agl_m, heading_deg, n_samples, config) -> np.ndarray` returns `(N, 2)` array of ENU impact points
- [ ] With zero variance (σ_heading=0, σ_glide_ratio=0), all N samples land at the same deterministic point
- [ ] With non-zero variance, the output distribution is approximately elliptical, elongated along the heading axis
- [ ] Mean impact distance from intercept point equals `altitude_agl_m * config.physics.shahed136.glide_ratio`
- [ ] The function operates entirely in vectorised NumPy (no Python loops over samples)
- [ ] Numba JIT compilation is wired up via `@numba.njit` on inner numeric functions if they exist; the main function itself stays in NumPy
- [ ] `pytest tests/unit/test_physics_m1.py` passes

---

## Physics Model

From `/spec/physics-model.md`. At intercept point P, the drone is at altitude `h_agl` (AGL) with nominal heading `θ`.

**Stochastic inputs (drawn per sample):**

| Variable | Distribution | Parameters |
|---|---|---|
| Heading deviation | Normal | `μ=0`, `σ=5°` |
| Glide ratio | Normal | `μ=5.0`, `σ=0.8` |

Both σ values come from `config` — do not hard-code.

**Impact position (ENU, relative to intercept point):**

```
heading_i = θ + δθ_i          (θ in compass degrees)
range_i   = h_agl * glide_i

east_i  = range_i * sin(heading_i)
north_i = range_i * cos(heading_i)
```

Note: `sin`/`cos` operate on angles in radians after conversion.

**Output:** `(N, 2)` float64 array, columns `[east_m, north_m]` in ENU centred on intercept point.

---

## Implementation Steps

### 1. src/droneimpact/physics/m1.py

```python
import numpy as np
from droneimpact.config import PhysicsConfig

def simulate_m1(
    altitude_agl_m: float,
    heading_deg: float,
    n_samples: int,
    config: PhysicsConfig,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """
    Monte Carlo simulation of Mode M1 (propulsion loss) impact distribution.

    Returns (N, 2) ENU impact point array [east_m, north_m] relative to
    intercept position (origin = drone position at time of intercept).
    """
    if rng is None:
        rng = np.random.default_rng()

    shahed = config.shahed136
    sigma_heading = config.m1_sigma_heading_deg   # add this to config
    sigma_glide   = config.m1_sigma_glide_ratio   # add this to config

    heading_samples = rng.normal(heading_deg, sigma_heading, n_samples)  # (N,)
    glide_samples   = rng.normal(shahed.glide_ratio, sigma_glide, n_samples)  # (N,)
    glide_samples   = np.maximum(glide_samples, 0.5)  # physical floor

    range_samples = altitude_agl_m * glide_samples  # (N,)

    heading_rad = np.radians(heading_samples)
    east  = range_samples * np.sin(heading_rad)   # (N,)
    north = range_samples * np.cos(heading_rad)   # (N,)

    return np.stack([east, north], axis=1)  # (N, 2)
```

**Config additions required:** Add `m1_sigma_heading_deg: float = 5.0` and `m1_sigma_glide_ratio: float = 0.8` under `physics:` in `config.yaml` and in `PhysicsConfig`. Update F01's config schema accordingly (this is an additive change).

**`rng` parameter:** Accepting a `numpy.random.Generator` enables deterministic test seeds. Production calls pass `None` (random seed).

### 2. src/droneimpact/physics/__init__.py

Export `simulate_m1` from the `physics` package.

---

## Tests

### tests/unit/test_physics_m1.py

**Zero-variance determinism:**
```python
def test_m1_zero_variance_deterministic(config):
    config.physics.m1_sigma_heading_deg = 0.0
    config.physics.m1_sigma_glide_ratio = 0.0
    rng = np.random.default_rng(42)
    points = simulate_m1(altitude_agl_m=400.0, heading_deg=0.0,
                          n_samples=1000, config=config.physics, rng=rng)
    # All points must be identical
    assert np.allclose(points, points[0])
    # Must land at expected range
    expected_range = 400.0 * config.physics.shahed136.glide_ratio
    east, north = points[0]
    actual_range = np.sqrt(east**2 + north**2)
    assert abs(actual_range - expected_range) < 0.01
```

**Heading north → impact north of origin:**
```python
def test_m1_heading_north(config):
    rng = np.random.default_rng(42)
    points = simulate_m1(altitude_agl_m=400.0, heading_deg=0.0,
                          n_samples=10000, config=config.physics, rng=rng)
    mean_north = points[:, 1].mean()
    mean_east  = points[:, 0].mean()
    assert mean_north > 0
    assert abs(mean_east / mean_north) < 0.1  # mostly northward
```

**Heading east → impact east of origin:**
```python
def test_m1_heading_east(config):
    rng = np.random.default_rng(42)
    points = simulate_m1(altitude_agl_m=400.0, heading_deg=90.0,
                          n_samples=10000, config=config.physics, rng=rng)
    mean_east  = points[:, 0].mean()
    mean_north = points[:, 1].mean()
    assert mean_east > 0
    assert abs(mean_north / mean_east) < 0.1
```

**Mean range ~ altitude × glide_ratio:**
```python
def test_m1_mean_range(config):
    rng = np.random.default_rng(0)
    altitude = 500.0
    expected_mean_range = altitude * config.physics.shahed136.glide_ratio
    points = simulate_m1(altitude_agl_m=altitude, heading_deg=45.0,
                          n_samples=10000, config=config.physics, rng=rng)
    ranges = np.sqrt((points**2).sum(axis=1))
    assert abs(ranges.mean() - expected_mean_range) / expected_mean_range < 0.05  # 5%

```

**Output shape:**
```python
def test_m1_output_shape(config):
    points = simulate_m1(altitude_agl_m=300.0, heading_deg=180.0,
                          n_samples=500, config=config.physics)
    assert points.shape == (500, 2)
    assert points.dtype in [np.float64, np.float32]
```

**Glide ratio floor prevents negative ranges:**
```python
def test_m1_no_negative_range(config):
    rng = np.random.default_rng(99)
    # Very low altitude, high variance — would produce negative ranges without floor
    config.physics.m1_sigma_glide_ratio = 5.0
    points = simulate_m1(altitude_agl_m=50.0, heading_deg=0.0,
                          n_samples=10000, config=config.physics, rng=rng)
    ranges = np.sqrt((points**2).sum(axis=1))
    assert np.all(ranges >= 0)
```

### conftest.py

Create `tests/conftest.py` with a `config` fixture that loads `config.yaml` and returns an `AppConfig`. This fixture is shared across all test files.

---

## Notes

- `np.random.default_rng()` is the modern NumPy API. Do not use `np.random.seed()` or `np.random.randn()` — these are legacy.
- The 5% tolerance on mean range accounts for Monte Carlo variance at N=10,000. At N=1,000 this test might be flaky — use N=10,000.
- Glide ratio variance σ=0.8 is an estimate. It is configurable; tests should read it from config rather than hard-coding.
