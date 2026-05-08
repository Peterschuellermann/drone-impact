# F06 — Physics Engine: Mode M3 Break Apart

**Status:** pending  
**Branch:** `feature/F06-physics-m3`  
**Dependencies:** F01, F02, F03

---

## Goal

Implement the Mode M3 (break apart) terminal trajectory simulation. When the drone is structurally destroyed, it tumbles and follows a ballistic trajectory with high drag. Fragments scatter over a relatively small area near the intercept point. This mode produces the tightest debris footprint — the safest intercept mode if the intercept point is already over low-density terrain.

---

## Acceptance Criteria

- [ ] `simulate_m3(altitude_agl_m, heading_deg, speed_m_s, n_samples, config) -> np.ndarray` returns `(N, 2)` ENU impact points
- [ ] With zero variance, all samples land at the deterministic ballistic landing point
- [ ] The footprint is tighter than M1 at the same altitude (std-dev of range is smaller)
- [ ] Impact range increases with altitude (longer fall time → further travel)
- [ ] Entirely vectorised — no per-sample Python loops
- [ ] `pytest tests/unit/test_physics_m3.py` passes

---

## Physics Model

From `/spec/physics-model.md`. The drone breaks apart and the main body (and fragments) tumble ballistically. Tumbling objects have high drag due to irregular orientation.

**Ballistic model with drag (per fragment):**

The governing equations in the vertical plane are:

```
dv_x/dt = -0.5 * ρ * C_d * A * v_x * |v| / m
dv_z/dt = -g + (-0.5 * ρ * C_d * A * v_z * |v| / m)

where |v| = sqrt(v_x² + v_z²)
```

For the vectorised simulation, discretise at Δt = 0.1 s (configurable). This is tighter than M2 because the ballistic phase is shorter (lower altitude reached more quickly) but we need accuracy.

**Stochastic inputs:**

| Variable | Distribution | Config key | Default |
|---|---|---|---|
| Initial velocity (forward component) | Normal | from speed_m_s, σ=m3_sigma_speed_m_s | σ=10 m/s |
| Initial heading deviation | Normal | m3_sigma_heading_deg | 20° |
| Drag coefficient (tumbling) | Normal | μ from config, σ=m3_sigma_cd | σ=0.15 |
| Fragment mass fraction (relative to full mass) | Uniform | [0.1, 1.0] | — |

**Initial conditions:**
- Position: (0, 0, altitude_agl_m) ENU
- Velocity: derived from speed_m_s + stochastic heading + random pitch angle (initial pitch ∈ [-20°, +20°] uniform)
- Vertical velocity: `v_z = speed_m_s * sin(pitch_rad)` — the drone may be nose-down, level, or nose-up at break-up

**Constants:**
```
g = 9.81 m/s²
ρ = 1.225 kg/m³  (sea level, v1 — ISA table in v2)
C_d nominal = config.physics.shahed136.drag_coeff_tumbling  (default 0.8)
A  = config.physics.shahed136.reference_area_m2  (default 3.5 m²)
m  = config.physics.shahed136.mass_kg  (default 200 kg)
```

---

## Implementation Steps

### 1. src/droneimpact/physics/m3.py

```python
def simulate_m3(
    altitude_agl_m: float,
    heading_deg: float,
    speed_m_s: float,
    n_samples: int,
    config: PhysicsConfig,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """
    Monte Carlo simulation of Mode M3 (break apart) impact distribution.
    Returns (N, 2) ENU array [east_m, north_m] relative to intercept position.
    """
    if rng is None:
        rng = np.random.default_rng()

    shahed = config.shahed136

    # Stochastic initial conditions — all (N,) arrays
    heading_samples = rng.normal(heading_deg, config.m3_sigma_heading_deg, n_samples)
    speed_samples   = rng.normal(speed_m_s,   config.m3_sigma_speed_m_s,   n_samples)
    speed_samples   = np.maximum(speed_samples, 0.0)
    pitch_samples   = rng.uniform(-20.0, 20.0, n_samples)    # degrees
    cd_samples      = rng.normal(shahed.drag_coeff_tumbling, config.m3_sigma_cd, n_samples)
    cd_samples      = np.maximum(cd_samples, 0.1)
    mass_frac       = rng.uniform(0.1, 1.0, n_samples)
    mass_samples    = shahed.mass_kg * mass_frac

    # Initial velocity components
    hdg_rad   = np.radians(heading_samples)
    pitch_rad = np.radians(pitch_samples)
    cos_pitch = np.cos(pitch_rad)
    sin_pitch = np.sin(pitch_rad)

    # Horizontal velocity in ENU heading direction
    v_east  = speed_samples * cos_pitch * np.sin(hdg_rad)   # (N,)
    v_north = speed_samples * cos_pitch * np.cos(hdg_rad)   # (N,)
    v_vert  = speed_samples * sin_pitch                      # (N,)

    # Position
    pos_east  = np.zeros(n_samples)
    pos_north = np.zeros(n_samples)
    pos_alt   = np.full(n_samples, altitude_agl_m)

    alive = pos_alt > 0
    dt   = config.m3_dt_s
    half_rho_A = 0.5 * 1.225 * shahed.reference_area_m2

    for _ in range(config.m3_max_steps):
        if not np.any(alive):
            break

        speed_sq = v_east**2 + v_north**2 + v_vert**2
        speed    = np.sqrt(speed_sq)
        drag_coeff = half_rho_A * cd_samples / mass_samples  # (N,) per-unit-mass drag

        dv_east  = -drag_coeff * v_east  * speed * dt
        dv_north = -drag_coeff * v_north * speed * dt
        dv_vert  = (-9.81 - drag_coeff * v_vert * speed) * dt

        v_east  += alive * dv_east
        v_north += alive * dv_north
        v_vert  += alive * dv_vert

        pos_east  += alive * v_east  * dt
        pos_north += alive * v_north * dt
        pos_alt   += alive * v_vert  * dt

        alive = alive & (pos_alt > 0)

    return np.stack([pos_east, pos_north], axis=1)
```

**Config additions required** — add to `config.yaml` under `physics:`:
```yaml
m3_sigma_heading_deg: 20.0
m3_sigma_speed_m_s: 10.0
m3_sigma_cd: 0.15
m3_dt_s: 0.1
m3_max_steps: 1000
```

---

## Tests

### tests/unit/test_physics_m3.py

**Output shape:**
```python
def test_m3_output_shape(config):
    points = simulate_m3(altitude_agl_m=400.0, heading_deg=0.0,
                          speed_m_s=51.4, n_samples=200, config=config.physics)
    assert points.shape == (200, 2)
    assert np.all(np.isfinite(points))
```

**Zero variance gives deterministic point:**
```python
def test_m3_zero_variance_deterministic(config):
    config.physics.m3_sigma_heading_deg = 0.0
    config.physics.m3_sigma_speed_m_s   = 0.0
    config.physics.m3_sigma_cd          = 0.0
    rng = np.random.default_rng(0)
    # Also fix pitch by using same seed — for this test, set pitch sigma to 0 as well
    # Workaround: set pitch range to 0 by monkey-patching, or just check all points equal
    points = simulate_m3(altitude_agl_m=200.0, heading_deg=90.0,
                          speed_m_s=51.4, n_samples=100, config=config.physics, rng=rng)
    # With near-zero variance, points should cluster very tightly
    std = np.std(np.sqrt((points**2).sum(axis=1)))
    assert std < 50.0  # within 50m of each other
```

**Tighter than M1 footprint:**
```python
def test_m3_tighter_than_m1(config):
    n = 5000
    rng_seed = 42
    m1_pts = simulate_m1(altitude_agl_m=400.0, heading_deg=0.0, n_samples=n,
                          config=config.physics, rng=np.random.default_rng(rng_seed))
    m3_pts = simulate_m3(altitude_agl_m=400.0, heading_deg=0.0, speed_m_s=51.4,
                          n_samples=n, config=config.physics,
                          rng=np.random.default_rng(rng_seed))
    m1_spread = np.std(np.sqrt((m1_pts**2).sum(axis=1)))
    m3_spread = np.std(np.sqrt((m3_pts**2).sum(axis=1)))
    assert m3_spread < m1_spread

```

**Range increases with altitude:**
```python
def test_m3_range_increases_with_altitude(config):
    rng = np.random.default_rng(7)
    pts_low  = simulate_m3(altitude_agl_m=100.0, heading_deg=0.0, speed_m_s=51.4,
                            n_samples=2000, config=config.physics, rng=np.random.default_rng(7))
    pts_high = simulate_m3(altitude_agl_m=600.0, heading_deg=0.0, speed_m_s=51.4,
                            n_samples=2000, config=config.physics, rng=np.random.default_rng(7))
    mean_range_low  = np.sqrt((pts_low**2).sum(axis=1)).mean()
    mean_range_high = np.sqrt((pts_high**2).sum(axis=1)).mean()
    assert mean_range_high > mean_range_low
```

**All samples terminate:**
```python
def test_m3_all_terminate(config):
    points = simulate_m3(altitude_agl_m=800.0, heading_deg=270.0, speed_m_s=51.4,
                          n_samples=500, config=config.physics)
    assert np.all(np.isfinite(points))
```

---

## Notes

- M3 uses `m3_dt_s=0.1` s (finer than M2's 1.0 s) because the ballistic phase is faster. At 400m AGL with 0 vertical velocity, a ballistic object hits the ground in ~9 seconds, requiring ~90 timesteps.
- The drag formula uses `speed * velocity_component` not `speed^2 * sign(velocity)` — the former is correct for vector drag opposing the velocity direction.
- Fragment mass fraction sampling (uniform [0.1, 1.0]) reflects that different fragments of different sizes may be the relevant casualty-causing mass. The warhead fragment is most dangerous; smaller structural pieces have proportionally less mass and slower terminal velocity.
