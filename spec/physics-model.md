# Physics Model

## Shahed-136 Airframe Parameters

The Shahed-136 (Russian designation Geran-2) is an Iranian-designed loitering munition with a delta-wing airframe. The following parameters are derived from public reporting, open-source intelligence, and aerodynamic estimates for this class of vehicle.

| Parameter | Value | Source / Note |
|---|---|---|
| Total mass (m) | 200 kg | Widely reported; includes warhead |
| Warhead mass | 40–50 kg | Estimated; shaped-charge/fragmentation |
| Wing configuration | Clipped delta | Observed airframe geometry |
| Wingspan | ~2.5 m | OSINT measurements |
| Length | ~3.5 m | OSINT measurements |
| Reference wing area (S) | ~3.5 m² | Estimated from geometry |
| Cruise speed (v_cruise) | 51.4 m/s (185 km/h) | Reported operational speed |
| Cruise altitude | 100–1000 m AGL | Observed flight profiles |
| Engine | MADO MD-550 piston (50 hp) | Identified from recovered units |
| Lift-to-drag ratio (L/D) | ~5 (unpowered) | Estimate for delta-wing glider |
| Glide ratio | 5:1 | Derived from L/D |
| Stall speed | ~27 m/s (estimated) | Derived from wing loading and C_L_max ≈ 1.3 |
| Drag coefficient (C_d) | 0.04 cruise; 0.8 tumbling | Delta-wing clean config / tumbling flat-plate |
| Air density (ρ) at sea level | 1.225 kg/m³ | ISA standard; altitude-corrected in simulation |

**These are engineering estimates. The implementation should expose all parameters as configurable constants** so they can be refined when better data becomes available.

---

## Coordinate System

Physics is computed in a local **East-North-Up (ENU)** Cartesian frame:

- Origin: engagement point (the trajectory evaluation point)
- x-axis: East
- y-axis: North  
- z-axis: Up (altitude)

WGS84 ↔ ENU conversion uses the standard small-angle approximation valid for distances < 500 km. All internal calculations use metres and seconds.

---

## Trajectory Discretisation

Given the input state vector `(lat, lon, alt, heading, speed)`, the system generates evaluation points by stepping forward along the great-circle path:

```
for i in 0..N:
    P_i = great_circle_point(origin, bearing=heading, distance=i * spacing_m)
    P_i.altitude = alt   # straight and level in v1
```

For each `P_i`, an independent Monte Carlo simulation is run.

---

## Monte Carlo Simulation Architecture

For each evaluation point `P_i`:

1. Draw `N = 2,000` samples (configurable via `n_monte_carlo_samples`)
2. For each sample, draw outcome: `hit` (p=P_kill) or `miss` (p=1-P_kill)
3. If `hit`, draw mode from `{M1, M2, M3}` with weights `{w1, w2, w3}` (see [engagement model](engagement-model.md))
4. Simulate terminal trajectory for the drawn mode → get impact point `(x_impact, y_impact)` in ENU
5. Convert impact point to WGS84
6. Look up casualty score at impact location

Result: a distribution of impact points and an expected casualty count.

The simulation is **embarrassingly parallel** across evaluation points and across samples. No state is shared between samples.

---

## Terminal Trajectory Models

### M1 — Propulsion Loss (Controlled Glide)

The engine stops. Control surfaces remain active; the autopilot (if still functional) may attempt to maintain heading. The drone glides at approximately its L/D ratio.

**Assumptions:**
- Glide ratio = 5:1 (horizontal:vertical)
- Glide path angle γ = arctan(1/5) ≈ 11.3°
- Initial speed = v_cruise = 51.4 m/s
- Speed decays during glide due to drag; simplified to constant-speed glide (conservative)
- No wind in v1

**Energy-height glide range (horizontal):**

The drone's kinetic energy converts to additional altitude equivalent, extending glide range at higher speeds:
```
energy_height = altitude_AGL + v² / (2g)
R_glide = energy_height * (L/D)
```

At 300 m AGL, v=51.4 m/s → energy_height ≈ 435 m → 2,175 m range
At 500 m AGL, v=51.4 m/s → energy_height ≈ 635 m → 3,175 m range
At 500 m AGL, v=0 m/s → energy_height = 500 m → 2,500 m range (altitude-only fallback)

**Stochastic elements** (Monte Carlo perturbations per sample):
- Heading perturbation: σ_heading ~ N(0, 5°) — control surfaces may be partially damaged
- Glide ratio perturbation: σ_LoverD ~ N(5, 0.8) — structural damage affects aerodynamics
- Speed at intercept: σ_speed ~ N(v_input, 5 m/s) — speed uncertainty at intercept moment

**Impact point:**
```
x_impact = R_glide * sin(heading + δ_heading)
y_impact = R_glide * cos(heading + δ_heading)
```

**Expected footprint shape:** Elongated ellipse aligned with heading, semi-major axis ≈ 0.2 × R_glide, semi-minor axis ≈ 0.05 × R_glide.

---

### M2 — Loss of Control (Two-Phase Model)

Guidance or avionics are destroyed. The engine may continue running for a time before the drone transitions to a ballistic tumble. This is modelled as a two-phase simulation.

**Phase 1 — Powered drift:**
- Engine running at cruise speed with a constant descent rate (1.5 m/s)
- Heading drifts as Brownian motion: per-step perturbation ~ N(0, σ_turn × √dt), where σ_turn = 15°/s
- Initial heading perturbation: N(heading, 30°)
- Duration: T_power ~ Uniform(1, 10) s per sample

**Phase 2 — Ballistic tumble:**
- Engine off; velocity initialised from final powered-flight state
- Gravity and aerodynamic drag (using altitude-corrected air density) decelerate the fragment
- Uses the same drag model as M3: C_d × A / m from the Shahed-136 airframe params
- Terminates on ground impact (altitude ≤ 0)

**Integration:**
- Timestep: dt = 1.0 s (configurable via `m2_dt_s`)
- Maximum simulation time: 300 s (configurable via `m2_max_time_s`)
- All N samples are vectorised (batch array operations per timestep)
- First-order Euler integration; acceptable for the coarse stochastic model

**Stochastic elements:**
- Power duration: T_power ~ Uniform(m2_power_duration_min_s, m2_power_duration_max_s)
- Initial heading: N(heading, m2_sigma_init_deg)
- Heading drift: Brownian motion with σ_turn = m2_sigma_turn_deg_per_s

**Expected footprint shape:** Wide, roughly circular distribution. Radius is sensitive to altitude, speed, and powered-flight duration. At 400 m AGL and 51 m/s cruise, typical 90 % radius ≈ 1,500–2,500 m from engagement point.

This mode produces the most dispersed impact distribution and hence the highest uncertainty in casualty estimates.

---

### M3 — Break Apart (Ballistic Tumble)

Structural failure. The airframe disintegrates. The heaviest fragment (assumed to be the warhead/nose section, mass ≈ 50 kg) follows a ballistic trajectory with high drag (tumbling flat plate).

**Note:** The user has specified that individual fragments are NOT modelled separately. We model a single representative heavy fragment (the warhead section), which is the primary casualty risk.

**Equations of motion (ballistic with drag):**

```
m * dv/dt = -m*g*ẑ - 0.5 * ρ(z) * v² * C_d * A * v̂

where:
  C_d = 0.8  (tumbling flat plate)
  A   = 0.5 m²  (representative cross-section)
  m   = 50 kg   (warhead section)
  ρ(z) = 1.225 * exp(-z / 8500)  (exponential atmosphere model)
```

**Stochastic elements:**
- Initial velocity direction: ejection angle sampled from Uniform(heading-60°, heading+60°) — forward hemisphere
- Initial speed: sampled from N(v_cruise * 0.7, 10 m/s) — reduced due to structural impact
- Fragment mass: N(50, 10) kg

**Expected footprint shape:** Tight, roughly circular distribution close to the engagement point. High drag means short range. At 400 m AGL: typical 90 % radius ≈ 200–500 m.

---

### M4 — Miss (Drone Continues)

No simulation needed. The drone continues on its nominal straight-line trajectory. The terminal impact is the endpoint of the trajectory (max_range or when altitude reaches terrain elevation — whichever comes first).

This contributes to the engagement score via the `miss_branch_expected_casualties` term.

---

## Atmosphere Model

Air density varies with altitude. Using the simplified exponential model:

```
ρ(z) = ρ_0 * exp(-z / H)
where ρ_0 = 1.225 kg/m³, H = 8500 m (scale height)
```

This is sufficient for altitudes 0–5000 m. A standard ISA table lookup is an acceptable alternative.

---

## Digital Elevation Model (DEM)

The simulation terminates when the drone's computed altitude drops below the local terrain elevation. A DEM is required to:

1. Convert input `altitude_m` (MSL) to AGL
2. Determine terrain elevation along each simulated trajectory for ground-intercept detection

**Recommended DEM:** SRTM 1 Arc-Second (30 m resolution) or Copernicus DEM (GLO-30, 30 m). Both are freely available and cover Ukraine.

For v1, a coarser DEM (90 m / SRTM3) is acceptable if it reduces computational load. The DEM should be pre-tiled and cached in memory for the region of interest.

---

## Warhead Detonation Assumption

In all hit modes (M1, M2, M3), the warhead is assumed to **detonate on ground impact**. The probability of warhead detonation given impact is treated as 1.0 in v1.

Known limitation: A significant fraction of Shaheds that have been intercepted have reportedly not detonated (possibly safety mechanisms, fuze failure, or design intent). A `p_detonate` parameter should be added in v2.

---

## Performance Targets

| Operation | Target latency |
|---|---|
| Single drone, 2,000 samples, 50 evaluation points | < 500 ms |
| Batch of 50 drones (same params) | < 15 s |

Monte Carlo samples are independent — parallelise across both samples and trajectory points.

**Computation strategy:**
Physics kernels (M1, M2, M3) are compiled with Numba `@njit(parallel=True, cache=True)`. Each kernel receives pre-generated random arrays and config scalars — no Python objects cross the JIT boundary. The outer loop iterates over samples with `prange` for multi-core parallelism; the inner loop (M2/M3 timestep integration) runs as scalar operations per sample, fitting in L1 cache. This releases the GIL, enabling the per-point ThreadPoolExecutor to achieve real parallelism.

Compiled kernels are cached in `__pycache__` via Numba's `cache=True`. A warm-up call at server startup triggers compilation so the first request doesn't pay the JIT cost.

---

## Simplifications and Known Limitations

| Simplification | Impact | Resolution |
|---|---|---|
| No wind/weather | Impact distributions are centred on nominal trajectory; wind shifts actual distribution | Add in v2 |
| Constant cruise speed | Slight overestimate of glide range | Acceptable for v1 |
| Single fragment (M3) | Underestimates total M3 debris footprint area | Noted; spec'd out of scope |
| Fixed Shahed parameters | Cannot handle other drone types | Make airframe params configurable |
| Warhead always detonates | Overestimates casualties | Add p_detonate in v2 |
| Straight trajectory | Real drones manoeuvre | Add path prediction in v3 |
| DEM only (no buildings) | Cannot model shadowing by buildings | Low priority for open-country theatre |
| No sheltering / building protection | All population assumed exposed outdoors; overestimates casualties 2–5× in urban areas | Add building-type sheltering factor in v2 |
| No time-of-day factor | Population exposure varies dramatically (residential dense at night, commercial during day) | Add optional time-of-day input in v2 |
| M2 integration is 1st-order Euler at dt=1.0s | Larger timestep trades precision for speed; acceptable for stochastic model | Reduce dt if M2 footprints look unrealistic |
