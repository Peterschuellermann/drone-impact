# F05 — Physics Engine: Mode M2 Loss of Control

**Status:** pending  
**Branch:** `feature/F05-physics-m2`  
**Dependencies:** F01, F02, F03

---

## Goal

Implement the Mode M2 (loss of control) terminal trajectory simulation. After guidance/avionics are destroyed, the Shahed engine continues running but the drone flies erratically — random oscillations in heading and pitch until fuel exhaustion or impact. This mode produces the widest and most uncertain debris footprint of the three intercept modes.

---

## Acceptance Criteria

- [ ] `simulate_m2(pos, altitude_agl_m, heading_deg, speed_m_s, n_samples, config) -> np.ndarray` returns `(N, 2)` ENU impact points
- [ ] The distribution is significantly wider than M1 (check: M2 std-dev of range > 2× M1 std-dev at same altitude and config)
- [ ] No sample produces an impact point behind the intercept position (mean northward displacement > 0 for northward heading)
- [ ] All computation is vectorised — no Python loops over samples or timesteps
- [ ] `pytest tests/unit/test_physics_m2.py` passes

---

## Physics Model

From `/spec/physics-model.md`. The drone is still powered but flying erratically. We simulate this as a discrete-timestep random walk in heading space, with the drone continuing to fly at cruise speed but with a randomly evolving heading.

**Simulation parameters (from config):**

| Parameter | Symbol | Config key | Value |
|---|---|---|---|
| Time step | Δt | `m2_dt_s` | 1.0 s |
| Max simulation time | T_max | `m2_max_time_s` | 300 s (5 min) |
| Heading diffusion rate | σ_turn | `m2_sigma_turn_deg_per_s` | 15°/s |
| Initial heading deviation | σ_init | `m2_sigma_init_deg` | 30° |
| Speed | v | from state vector | m/s |

**Algorithm (vectorised over all N samples simultaneously):**

```
For each sample i in [1..N]:
    heading_i[0] = heading_deg + N(0, σ_init)
    pos_east_i[0] = 0, pos_north_i[0] = 0
    altitude_i[0] = altitude_agl_m
    
    For t = 1 to T_max/Δt:
        δθ = N(0, σ_turn * sqrt(Δt))    ← Brownian motion in heading
        heading_i[t] = heading_i[t-1] + δθ
        
        pos_east_i[t]  = pos_east_i[t-1]  + v * sin(heading_i[t]) * Δt
        pos_north_i[t] = pos_north_i[t-1] + v * cos(heading_i[t]) * Δt
        
        altitude_i[t] = altitude_i[t-1] - descent_rate * Δt  ← gentle descent
        
        if altitude_i[t] <= 0:
            record impact at (east_i[t], north_i[t])
            break
```

**Vectorised form** — run all N samples as matrix operations:

```python
# headings: (N, T) — headings at each timestep for each sample
# positions: (N, T, 2) — east/north positions at each timestep
# termination: (N,) — timestep at which each sample hits ground

# Key: each timestep is a batch operation over all N samples simultaneously.
# headings[:, t] = headings[:, t-1] + rng.normal(0, sigma_turn_rad, N)
# positions[:, t, :] = positions[:, t-1, :] + velocity_vectors * dt
```

Use cumulative termination: once a sample hits the ground, its position is frozen (use `np.where` masking — do not break out of the loop per-sample).

**Descent rate:** The drone loses altitude gradually when control is lost. Use a configurable linear descent rate `m2_descent_rate_m_s: float = 1.5` m/s. This is an estimate.

---

## Implementation Steps

### 1. src/droneimpact/physics/m2.py

```python
def simulate_m2(
    altitude_agl_m: float,
    heading_deg: float,
    speed_m_s: float,
    n_samples: int,
    config: PhysicsConfig,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """
    Monte Carlo simulation of Mode M2 (loss of control) impact distribution.
    Returns (N, 2) ENU array [east_m, north_m] relative to intercept position.
    """
    ...
```

**Memory considerations:** At N=10,000 samples and T_max/Δt=300 timesteps, storing full trajectories requires 10,000 × 300 × 2 × 8 bytes = ~48 MB. This is acceptable but tight. Avoid storing full trajectory arrays if only the final position is needed — use a rolling position update instead:

```python
pos   = np.zeros((n_samples, 2))       # current position, updated in-place
hdg   = rng.normal(heading_deg, sigma_init_deg, n_samples)  # (N,)
alt   = np.full(n_samples, altitude_agl_m)                  # (N,)
alive = np.ones(n_samples, dtype=bool)                       # (N,)

for _ in range(n_timesteps):
    if not np.any(alive):
        break
    dhdg = rng.normal(0, sigma_turn_rad * sqrt_dt, n_samples)  # (N,)
    hdg += dhdg
    hdg_rad = np.radians(hdg)
    pos[:, 0] += alive * speed_m_s * np.sin(hdg_rad) * dt
    pos[:, 1] += alive * speed_m_s * np.cos(hdg_rad) * dt
    alt        -= alive * descent_rate * dt
    alive       = alive & (alt > 0)
```

This uses O(N) memory regardless of T_max.

**Config additions required:** Add to `config.yaml` under `physics:`:
```yaml
m2_sigma_init_deg: 30.0
m2_sigma_turn_deg_per_s: 15.0
m2_dt_s: 1.0
m2_max_time_s: 300.0
m2_descent_rate_m_s: 1.5
```

---

## Tests

### tests/unit/test_physics_m2.py

**Output shape:**
```python
def test_m2_output_shape(config):
    points = simulate_m2(altitude_agl_m=400.0, heading_deg=0.0,
                          speed_m_s=51.4, n_samples=100, config=config.physics)
    assert points.shape == (100, 2)
```

**M2 wider footprint than M1:**
```python
def test_m2_wider_than_m1(config):
    rng = np.random.default_rng(42)
    m1 = simulate_m1(altitude_agl_m=400.0, heading_deg=0.0,
                     n_samples=5000, config=config.physics, rng=np.random.default_rng(42))
    m2 = simulate_m2(altitude_agl_m=400.0, heading_deg=0.0,
                     speed_m_s=51.4, n_samples=5000, config=config.physics,
                     rng=np.random.default_rng(42))
    m1_std = np.sqrt(np.var(m1[:, 0]) + np.var(m1[:, 1]))
    m2_std = np.sqrt(np.var(m2[:, 0]) + np.var(m2[:, 1]))
    assert m2_std > 2 * m1_std
```

**Mean displacement in heading direction:**
```python
def test_m2_mean_forward_displacement(config):
    rng = np.random.default_rng(7)
    points = simulate_m2(altitude_agl_m=300.0, heading_deg=0.0,
                          speed_m_s=51.4, n_samples=5000, config=config.physics, rng=rng)
    assert points[:, 1].mean() > 0  # mean north displacement for northward heading
```

**No samples hit the ground immediately (at altitude > 0):**
```python
def test_m2_no_immediate_ground_hit(config):
    rng = np.random.default_rng(1)
    points = simulate_m2(altitude_agl_m=400.0, heading_deg=0.0,
                          speed_m_s=51.4, n_samples=100, config=config.physics, rng=rng)
    # All impact points should be more than 0m from origin
    ranges = np.sqrt((points**2).sum(axis=1))
    assert np.all(ranges > 10.0)
```

**All samples terminate (no infinite loop):**
```python
def test_m2_all_terminate(config):
    rng = np.random.default_rng(99)
    points = simulate_m2(altitude_agl_m=50.0, heading_deg=45.0,
                          speed_m_s=51.4, n_samples=200, config=config.physics, rng=rng)
    assert points.shape == (200, 2)
    assert np.all(np.isfinite(points))
```

---

## Notes

- The M2 simulation is the most computationally expensive of the three modes. At N=10,000 and T=300 timesteps, it performs 3M float operations per evaluation point. Ensure the loop body contains no per-sample Python conditionals — only array operations.
- `sqrt_dt = np.sqrt(dt)` should be computed once before the loop, not inside it.
- The M2 model is an approximation. The conditional mode probabilities (M1/M2/M3) and the σ_turn parameter are estimated — see open questions in `/spec/roadmap.md`.
