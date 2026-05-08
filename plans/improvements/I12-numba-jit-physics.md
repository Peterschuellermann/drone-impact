# I12 — Numba JIT Compilation of Physics Engines

## Problem

The physics engines (M1, M2, M3) are the dominant cost in single-drone analysis. M2 iterates ~300 timesteps and M3 ~1000 timesteps in Python `for` loops. Each timestep performs small NumPy operations with Python interpreter overhead between them — the GIL is held during this control flow, preventing the I11 ThreadPoolExecutor from achieving real parallelism.

Benchmarks from I11 show that per-point ThreadPoolExecutor produces **0.6–1.2x** speedup (worse to marginal) because threads contend on the GIL. The physics loops are the specific bottleneck: each `_score_point` call spends ~80% of its time in M2/M3 timestep loops that cannot release the GIL.

## Approach

Compile M1, M2, and M3 inner kernels with Numba `@njit`. The compiled code runs as native machine code with no GIL, no interpreter overhead, and no temporary array allocations per timestep. Use `parallel=True` with `prange` to parallelize across Monte Carlo samples within each kernel.

### Why Numba over alternatives

| Option | Speedup | Effort | Build complexity | Notes |
|---|---|---|---|---|
| **Numba `@njit`** | 10–50x | Medium | None (pip install) | Already a project dependency |
| C++ / pybind11 | 20–100x | High | CMake, cross-platform | Two languages, separate build |
| Cython | 10–50x | Medium-high | setuptools ext, .pyx | Build step, weaker IDE support |
| Rust / PyO3 | 20–100x | High | Cargo + maturin | New language |
| Vectorize across points | 2–5x | Medium | None | Doesn't fix the timestep loop |

Numba is already in `pyproject.toml` (`numba>=0.59`), produces comparable performance to C for array-heavy loops, requires no build step, and keeps all code in `.py` files.

## Design

### Kernel extraction pattern

Each physics function is split into:
1. **Wrapper** (pure Python): validates inputs, extracts config scalars, generates random draws, calls the kernel, returns the result.
2. **Kernel** (`@njit`): receives only scalars and arrays. No Python objects, no RNG calls, no dataclasses. Pure numerical computation.

```
simulate_m2(altitude, heading, speed, n_samples, config, rng)
    │
    ├── [Python] extract config scalars, pre-generate random arrays
    │
    └── _m2_kernel(pos_e, pos_n, alt, hdg, v_e, v_n, v_v, ...)   ← @njit(parallel=True)
            │
            └── for i in prange(n_samples):   ← parallel across samples
                    for t in range(n_steps):   ← sequential per sample
                        ...physics...
```

### RNG strategy

Numba does not support `np.random.Generator`. Instead, pre-generate all random draws in the Python wrapper and pass them as arrays to the kernel:

```python
# Wrapper (Python, holds GIL briefly):
heading_samples = rng.normal(heading_deg, sigma, n_samples)
t_power = rng.uniform(min_s, max_s, n_samples)
dhdg_all = rng.normal(0.0, sigma_turn, (n_steps, n_samples))

# Kernel (Numba, no GIL):
@njit(parallel=True, nogil=True, cache=True)
def _m2_kernel(heading_samples, t_power, dhdg_all, ...):
    ...
```

This preserves the existing `SeedSequence.spawn()` deterministic RNG from I11 and keeps the kernel purely deterministic given its inputs.

### Loop restructuring: sample-parallel instead of vectorized

The current code vectorizes across samples at each timestep (each step operates on `(N,)` arrays). For Numba `prange`, we restructure to an outer loop over samples and an inner loop over timesteps:

**Current (vectorized across samples, sequential over timesteps):**
```python
for t in range(n_steps):           # Python loop, N temporary arrays per step
    pos_east += alive * v * dt     # (N,) operation
```

**Numba (parallel across samples, sequential per-sample timesteps):**
```python
@njit(parallel=True)
def _m2_kernel(...):
    for i in prange(n_samples):        # parallel — each sample on its own core
        for t in range(n_steps):       # sequential — each sample's physics
            pos_east[i] += ...         # scalar operation, no temporaries
```

Benefits:
- Each sample's data fits in L1 cache (~48 bytes vs. N×48 bytes per step)
- Zero temporary array allocations
- Perfect parallelism — no synchronization between samples
- Each core processes `N / n_cores` samples independently

## Implementation

### Step 1: M1 kernel (simplest, proves the pattern)

**File:** `src/droneimpact/physics/m1.py`

M1 has no timestep loop — it's a one-shot vectorized computation. Still worth JIT-compiling to eliminate interpreter overhead and to validate the kernel extraction pattern.

```python
from numba import njit, prange

@njit(parallel=True, cache=True)
def _m1_kernel(
    heading_samples: np.ndarray,   # (N,)
    glide_samples: np.ndarray,     # (N,)
    altitude_agl_m: float,
) -> np.ndarray:
    n = heading_samples.shape[0]
    result = np.empty((n, 2), dtype=np.float64)
    for i in prange(n):
        glide = max(glide_samples[i], 0.5)
        range_m = altitude_agl_m * glide
        hdg_rad = np.radians(heading_samples[i])
        result[i, 0] = range_m * np.sin(hdg_rad)
        result[i, 1] = range_m * np.cos(hdg_rad)
    return result


def simulate_m1(altitude_agl_m, heading_deg, n_samples, config, rng=None):
    if rng is None:
        rng = np.random.default_rng()
    heading_samples = rng.normal(heading_deg, config.m1_sigma_heading_deg, n_samples)
    glide_samples = rng.normal(config.shahed136.glide_ratio, config.m1_sigma_glide_ratio, n_samples)
    return _m1_kernel(heading_samples, glide_samples, altitude_agl_m)
```

The wrapper API is unchanged — callers don't know it's JIT-compiled.

### Step 2: M2 kernel (highest impact — 300-step loop)

**File:** `src/droneimpact/physics/m2.py`

Pre-generate all random draws in the wrapper, pass as arrays:

```python
@njit(parallel=True, cache=True)
def _m2_kernel(
    hdg: np.ndarray,               # (N,) initial heading in radians
    t_power: np.ndarray,           # (N,) powered phase duration
    dhdg_all: np.ndarray,          # (n_steps, N) heading perturbations
    altitude_agl_m: float,
    speed_m_s: float,
    descent_rate: float,
    dt: float,
    n_steps: int,
    half_A_Cd_over_m: float,
    scale_height: float,
    rho_0: float,
    g: float,
) -> np.ndarray:
    n = hdg.shape[0]
    result = np.empty((n, 2), dtype=np.float64)

    for i in prange(n):
        pos_e = 0.0
        pos_n = 0.0
        alt = altitude_agl_m
        h = hdg[i]
        t_elapsed = 0.0
        powered = True

        v_e = 0.0
        v_n = 0.0
        v_v = 0.0

        for t in range(n_steps):
            if alt <= 0.0:
                break

            t_elapsed += dt

            if powered and t_elapsed > t_power[i]:
                v_e = speed_m_s * np.sin(h)
                v_n = speed_m_s * np.cos(h)
                v_v = -descent_rate
                powered = False

            if powered:
                h += dhdg_all[t, i]
                pos_e += speed_m_s * np.sin(h) * dt
                pos_n += speed_m_s * np.cos(h) * dt
                alt -= descent_rate * dt
            else:
                rho = rho_0 * np.exp(-alt / scale_height)
                spd = np.sqrt(v_e * v_e + v_n * v_n + v_v * v_v)
                a_drag = half_A_Cd_over_m * rho * spd

                v_e -= a_drag * v_e * dt
                v_n -= a_drag * v_n * dt
                v_v += (-g - a_drag * v_v) * dt

                pos_e += v_e * dt
                pos_n += v_n * dt
                alt += v_v * dt

        result[i, 0] = pos_e
        result[i, 1] = pos_n

    return result
```

The wrapper pre-generates `dhdg_all = rng.normal(0.0, sigma_turn_rad, (n_steps, n_samples))` and extracts all config scalars before calling the kernel.

### Step 3: M3 kernel (1000-step loop)

**File:** `src/droneimpact/physics/m3.py`

Same pattern as M2. Pre-generate stochastic initial conditions (heading, speed, pitch, Cd, mass) in the wrapper. The kernel does pure scalar physics per sample:

```python
@njit(parallel=True, cache=True)
def _m3_kernel(
    v_east: np.ndarray,            # (N,) initial velocity components
    v_north: np.ndarray,
    v_vert: np.ndarray,
    half_A_cd_over_m: np.ndarray,  # (N,) per-sample drag pre-factor
    altitude_agl_m: float,
    dt: float,
    max_steps: int,
    scale_height: float,
    rho_0: float,
    g: float,
) -> np.ndarray:
    n = v_east.shape[0]
    result = np.empty((n, 2), dtype=np.float64)

    for i in prange(n):
        pos_e = 0.0
        pos_n = 0.0
        alt = altitude_agl_m
        ve = v_east[i]
        vn = v_north[i]
        vv = v_vert[i]
        drag_factor = half_A_cd_over_m[i]

        for t in range(max_steps):
            if alt <= 0.0:
                break

            rho = rho_0 * np.exp(-alt / scale_height)
            spd = np.sqrt(ve * ve + vn * vn + vv * vv)
            a_drag = drag_factor * rho * spd

            ve -= a_drag * ve * dt
            vn -= a_drag * vn * dt
            vv += (-g - a_drag * vv) * dt

            pos_e += ve * dt
            pos_n += vn * dt
            alt += vv * dt

        result[i, 0] = pos_e
        result[i, 1] = pos_n

    return result
```

### Step 4: JIT warm-up at startup

**File:** `src/droneimpact/main.py`

Add a warm-up call during `lifespan` startup so the first real request doesn't pay the JIT compilation cost:

```python
from droneimpact.physics.warmup import warmup_jit

# After data loading, before yielding:
logger.info("Warming up Numba JIT kernels...")
t_jit = time.perf_counter()
warmup_jit()
logger.info("JIT warm-up complete in %.1f s", time.perf_counter() - t_jit)
```

**File:** `src/droneimpact/physics/warmup.py`

```python
def warmup_jit():
    """Call each kernel with tiny inputs to trigger JIT compilation."""
    from droneimpact.physics.m1 import _m1_kernel
    from droneimpact.physics.m2 import _m2_kernel
    from droneimpact.physics.m3 import _m3_kernel
    # small N=10 calls to trigger compilation
    ...
```

With `cache=True`, Numba writes compiled code to `__pycache__` — subsequent starts skip compilation entirely.

### Step 5: Enable ThreadPoolExecutor per-point

**File:** `config.yaml`

Change the default now that the GIL is released during physics computation:

```yaml
parallelism:
  point_workers: 0    # 0 = auto (cpu_count) — now effective with Numba nogil
  batch_workers: 0
  batch_parallel_threshold: 2
```

The existing I11 `_score_points_parallel` ThreadPoolExecutor infrastructure will now achieve real parallelism: each thread runs a `_score_point` → Numba kernel chain that releases the GIL.

## Tests

### Correctness: numerical equivalence

**File:** `tests/unit/test_numba_physics.py`

For each mode (M1, M2, M3):
1. Run the old pure-Python implementation (saved as `_simulate_m1_reference`, etc.) with seed=42, N=1000
2. Run the new Numba version with the same seed and N
3. Assert `np.allclose(old_result, new_result, atol=1e-10)`

This ensures the Numba rewrite produces identical results.

### Determinism

4. Run with `point_workers=1` and `point_workers=4`, same seed. Assert identical trajectory scores (same test as I11 but now with Numba-compiled physics).

### Performance

5. Benchmark M2 kernel: 2000 samples, assert < 5ms per call (vs ~30ms current)
6. Benchmark single-drone 500 pts with `point_workers=cpu_count`: assert < 500ms (the original spec target)
7. Benchmark single-drone 2000 pts: record time, compare to I11 baseline

### Warm-up

8. Assert that calling `warmup_jit()` twice: the second call takes < 10ms (cache hit)

### Edge cases

9. M2 with `altitude_agl_m=0.1`: all samples should land immediately (1–2 steps)
10. M3 with all samples `mass_kg=5.0` (minimum floor): should not produce NaN or inf

## Acceptance Criteria

- [ ] M1, M2, M3 use `@njit(parallel=True, cache=True)` kernels
- [ ] Public API (`simulate_m1/m2/m3`) is unchanged — wrappers handle config extraction and RNG
- [ ] Numerical equivalence tests pass (new vs reference implementation, atol=1e-10)
- [ ] All existing tests pass without modification
- [ ] JIT warm-up runs at server startup; subsequent starts use cached compilation
- [ ] `point_workers: 0` (auto) now produces measurable speedup for single-drone scoring
- [ ] Numba is already a dependency — no new packages added
- [ ] `__pycache__` JIT cache files are gitignored (already are via `*.pyc` patterns)

## Spec Updates

**File:** `spec/physics-model.md`

Note that physics kernels are Numba-compiled with `parallel=True` for multi-core sample parallelism.

**File:** `spec/architecture.md`

Update the parallelism section to reflect that per-point ThreadPoolExecutor is now effective (Numba releases GIL).

## Dependencies

I11 (parallel computation) — provides the ThreadPoolExecutor infrastructure and `point_workers` config.

## Files to Modify

- `src/droneimpact/physics/m1.py` — extract `_m1_kernel` with `@njit`
- `src/droneimpact/physics/m2.py` — extract `_m2_kernel` with `@njit(parallel=True)`
- `src/droneimpact/physics/m3.py` — extract `_m3_kernel` with `@njit(parallel=True)`
- `src/droneimpact/physics/warmup.py` — new, JIT warm-up function
- `src/droneimpact/main.py` — call `warmup_jit()` at startup
- `config.yaml` — change `point_workers` default to `0`
- `spec/physics-model.md` — document Numba compilation
- `spec/architecture.md` — update parallelism section

## Files to Add

- `tests/unit/test_numba_physics.py` — numerical equivalence + performance tests
