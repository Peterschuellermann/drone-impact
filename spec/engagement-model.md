# Engagement Model

## Overview

The engagement model defines the probabilistic framework for a missile intercept event. It bridges the physics simulation (what happens to the drone after being hit) and the casualty model (what happens on the ground).

---

## P_kill

**Definition:** The probability that a single fired missile destroys the drone.

**v1 value: 0.50 (fixed)**

This is a simplification. Real P_kill depends on:
- Missile type and seeker (IR, radar, optical)
- Engagement geometry (aspect angle, range)
- Drone radar cross-section and thermal signature
- Countermeasures (ECM, low-altitude terrain masking)
- Operator skill

P_kill will become a configurable or missile-type-specific input in a future version. The constant 0.50 is intentionally conservative and in line with publicly reported effectiveness estimates for short-range air defence systems engaging Shaheds.

---

## Intercept Outcome Distribution

Given that the missile hits (P_kill event), three physical modes are possible. The mode probabilities are **conditional on a hit** and must sum to 1.

### Mode Weights (v1 defaults)

| Mode | ID | Weight (p_k | hit) | Rationale |
|---|---|---|---|
| Propulsion loss | M1 | 0.40 | Most common: engine/fuel system damage without airframe destruction |
| Loss of control | M2 | 0.35 | Avionics/guidance damage; engine may continue briefly |
| Break apart | M3 | 0.25 | Direct structural hit; less common for proximity-fuzed interceptors |

**These weights are estimates.** No authoritative public dataset of Shahed intercept outcomes exists. They should be exposed as configurable parameters. Future versions may derive them from historical intercept data.

### Mode Selection in Monte Carlo

For each Monte Carlo sample where the outcome is `hit`:

```python
mode = random.choice(['M1', 'M2', 'M3'], p=[0.40, 0.35, 0.25])
```

The simulation then applies the appropriate terminal trajectory model from the [physics model](physics-model.md).

---

## The Miss Branch

If the missile misses (probability = 1 - P_kill = 0.50), the drone continues its current trajectory. In v1 (straight-line trajectory):

- The drone continues until it reaches the end of the evaluated trajectory or until terrain elevation equals drone altitude
- The "target" impact is the final point on the trajectory
- `E[casualties | miss]` = the casualty score at the terminal trajectory point

**Implementation note:** In v1 (straight-line trajectory, single shot), the miss terminal point is the same regardless of which evaluation point the operator fires at — the drone always continues to the same endpoint. Therefore `C_terminal` is a **constant across all evaluation points**. It affects the absolute engagement score (and whether the "no good option" flag is set), but it does not affect which point is optimal. Compute it once and reuse it.

**Limitation:** The terminal point is defined by `max_range_m` (an input parameter) or terrain intercept — it does not model the drone's actual fuel range or intended target. Operators should set `max_range_m` to a tactically meaningful distance.

**Implication for the optimiser:** The recommended engagement point is not always the earliest possible point. If a later section of the trajectory passes over much higher population density, it may be worth engaging earlier despite higher debris risk, because a successful hit over open ground eliminates the warhead threat entirely.

---

## Engagement Score Formula

For each evaluation point P_i:

```
E_i = P_kill × Σ_{k∈{M1,M2,M3}} p_k × C_k(P_i)
    + (1 - P_kill) × C_terminal

where:
  C_k(P_i)    = expected casualties from mode k terminal debris, engaging at P_i
  C_terminal  = expected casualties if drone completes trajectory (hits target)
  P_kill      = 0.50
  p_M1        = 0.40, p_M2 = 0.35, p_M3 = 0.25
```

**Expanded:**
```
E_i = 0.50 × (0.40 × C_M1(P_i) + 0.35 × C_M2(P_i) + 0.25 × C_M3(P_i))
    + 0.50 × C_terminal
```

The **recommended engagement point** is selected using the safe intercept constraint (see below).

### Response Fields

Two distinct casualty metrics are returned per evaluation point:

- **`expected_casualties`**: Hit-branch casualties only — the weighted mean casualties from debris if the intercept succeeds at this point. This reflects the ground risk at this specific location.
- **`engagement_score`**: The full decision metric E_i (hit + miss branches). Used to rank and recommend engagement points.

---

## Safe Intercept Constraint

The scoring engine applies a safety constraint to the recommendation: the recommended engagement point must not require the drone to overfly a high-risk trajectory section.

### Hit-Branch Expected Casualties

For each evaluation point, the **hit-branch expected casualties** isolates the debris risk from the miss-branch constant:

```
hit_casualties(P_i) = Σ_{k∈{M1,M2,M3}} p_k × C_k(P_i)
```

This value is stored per point as `hit_branch_expected_casualties`.

### High-Risk Threshold

A trajectory point is flagged `high_risk: true` when:

```
hit_branch_expected_casualties > engagement.high_risk_threshold
```

The threshold is configurable via `engagement.high_risk_threshold` (default: 0.5 expected casualties). The threshold applies to hit-branch casualties only, not the full engagement score, because the miss-branch term is constant across all points and would bias the threshold.

### Constrained Recommendation

The eligible set for recommendation consists of all points where **no preceding point** (lower index along the trajectory) is high-risk. Once a high-risk point is encountered, all subsequent points are blocked from recommendation, because reaching them requires the drone to overfly the high-risk area.

```
P*_constrained = argmin_{i ∈ eligible} E_i
P*_unconstrained = argmin_{i} E_i
```

If `P*_constrained != P*_unconstrained`, the response includes both:
- `recommended_engagement` -- the constrained recommendation (safe)
- `unconstrained_optimum` -- the unconstrained argmin (for operator awareness)

When no eligible points exist (the first trajectory point itself is high-risk), the engine falls back to recommending the first point.

### Risk Zones

The response includes `risk_zones`: a list of contiguous trajectory segments where `hit_branch_expected_casualties > threshold`. Each zone reports `start_index`, `end_index`, `start_distance_m`, `end_distance_m`, and `peak_expected_casualties`.

### Engagement Score Values Unchanged

The constraint is a **filter on the recommendation**, not a change to the engagement score formula. All `engagement_score` values in the response remain unchanged. Operators see the full risk picture and can override the constrained recommendation when they have additional context.

---

## Handling the "No Good Option" Case

It is possible that every engagement point has higher expected casualties from debris than from the drone completing its trajectory (e.g., the drone is already over a dense city and the entire remaining path is also dense). In this case:

- The system still returns the argmin (best available option)
- The miss branch expected casualties are included per-point in the response (`miss_branch_expected_casualties`)
- Engagement zones classify dangerous stretches as `no_go`, giving operators structured visibility into which areas are unsafe

The operator has context the system does not (e.g., known target, other drones in flight).

---

## Adaptive Resolution (Long Trajectories)

For trajectories longer than 30 points, the scoring engine uses an adaptive resolution strategy to balance computation cost and accuracy:

1. **Population pre-scan**: Query population at `max_frag_radius` around each trajectory point using `PopulationIndex.query_batch()`. Cost: ~7 H3 cell lookups per point, negligible vs MC simulation.

2. **Point classification** based on pre-scan population:
   - `empty`: population = 0 → skip MC; score = `(1-p_kill) × miss_casualties`
   - `low`: 0 < population < `population_high_risk_threshold` (default 50) → full MC at original spacing
   - `high`: population ≥ threshold → dense evaluation at ~50m spacing (every ~1 second of flight time)

3. **Dense evaluation**: Additional points are interpolated at `dense_spacing_m` (default 50m) between original trajectory points in high-risk stretches. The `recommended_engagement` always snaps to the nearest original trajectory point.

4. **Gap interpolation**: Skipped (empty) points receive interpolated scores. Output always has exactly `len(trajectory)` entries.

Short trajectories (≤30 points) bypass adaptive resolution and run full MC on all points.

### Scoring Configuration

| Parameter | Default | Description |
|---|---|---|
| `population_empty_threshold` | 0.0 | Population below this is treated as empty |
| `population_high_risk_threshold` | 50.0 | Population above this triggers dense evaluation |
| `dense_spacing_m` | 50.0 | Spacing for interpolated points in high-risk zones |
| `miss_cache_agl_round_m` | 10.0 | AGL rounding for miss cache key |
| `miss_cache_heading_round_deg` | 1.0 | Heading rounding for miss cache key |
| `zone_caution_threshold` | 0.1 | Expected casualties threshold for caution zone |
| `zone_nogo_threshold` | 1.0 | Expected casualties threshold for no-go zone |
| `interception_timing_uncertainty_s` | 3.0 | Timing uncertainty window (seconds) applied when mapping an engagement point to an interception zone |
| `drone_maneuverability_radius_m` | 300.0 | Lateral radius (metres) within which the drone could maneuver before intercept, expanding the effective interception zone |
| `interception_zone_min_points` | 2 | Minimum number of consecutive trajectory points required to form an interception zone |

### Miss Branch Cache

The miss branch (drone continues on trajectory) is cached at module level, keyed on `(H3 cell at resolution 8, rounded AGL, rounded heading, n_samples, p_kill, miss_cache_agl_round_m)`. Two endpoints in the same H3 cell (~460m precision) with similar AGL and heading produce identical miss casualties. The cache is a plain dict, GIL-safe for FastAPI's threadpool. `clear_miss_cache()` is exposed for tests.

---

## Engagement Zones

The scoring engine classifies contiguous trajectory stretches into **engagement zones**:

| Classification | Condition | Meaning |
|---|---|---|
| `clear` | expected casualties < `zone_caution_threshold` | Safe to engage |
| `caution` | casualties ≥ caution, < no-go threshold | Engage with awareness of risk |
| `no_go` | casualties ≥ `zone_nogo_threshold` | Avoid engagement in this stretch |

Each zone includes:
- Start/end point index, distance, and lat/lon
- Peak and mean expected casualties
- Total population within fragmentation radius
- Structured reasons list (e.g., "Dense population: up to 120 persons within frag radius")

Zones are always computed (cheap — one walk over the scored point list) and included in the API response. The `explain()` function references no-go zone counts when generating the recommended engagement reasoning.

---

## Single-Shot Assumption

v1 assumes **one engagement opportunity**: fire once at the chosen point. There is no modelling of:
- Sequential engagement attempts
- Multiple missile salvoes
- Handoff between air defence systems

This simplification is appropriate for v1. A multi-shot optimisation would require dynamic programming over the trajectory, treating each evaluation point as a decision node in a Markov chain.

---

## Future: Variable P_kill

When missile type becomes an input, P_kill should be a function of:

| Parameter | Effect on P_kill |
|---|---|
| Missile type | Baseline effectiveness by system |
| Slant range | Drops off at max range; also drops at very close range (fuze arming) |
| Aspect angle | Head-on vs tail-chase performance varies by seeker |
| Altitude | Some systems have altitude floors |

Suggested approach: lookup table per missile type, indexed by (range, aspect angle bins), with values from manufacturer specifications or declassified test data.

---

## Future: Multiple Engagements (Sequential)

With N missiles across the trajectory, the optimal policy is computed by backward induction:

```
V(P_last) = E[casualties | engage at P_last]

V(P_i) = min(
  E_i,                         # engage now
  V(P_{i+1})                   # wait and engage later
)
```

This gives the Bellman-optimal engagement policy when you have more than one missile available.

---

## Parameters Summary

All of the following must be exposed as configurable constants in the implementation:

| Parameter | v1 Default | Description |
|---|---|---|
| `p_kill` | 0.50 | Probability of kill per shot |
| `p_mode_propulsion_loss` | 0.40 | P(M1 \| hit) |
| `p_mode_loss_of_control` | 0.35 | P(M2 \| hit) |
| `p_mode_break_apart` | 0.25 | P(M3 \| hit) |
| `n_monte_carlo_samples` | 2,000 | Samples per evaluation point per mode |
| `evaluation_spacing_m` | 500 | Distance between evaluation points |
| `high_risk_threshold` | 0.50 | Hit-branch expected casualties above which a point is high-risk |
| `mode_enable.*` | all `true` | Per-mode toggle; disabled modes are excluded and remaining weights renormalized |
