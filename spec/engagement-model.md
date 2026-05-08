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

The **recommended engagement point** is:
```
P* = argmin_{i} E_i
```

---

## Handling the "No Good Option" Case

It is possible that every engagement point has higher expected casualties from debris than from the drone completing its trajectory (e.g., the drone is already over a dense city and the entire remaining path is also dense). In this case:

- The system still returns the argmin (best available option)
- The response includes a flag: `"no_safe_engagement": true`
- The response includes `"baseline_casualties": C_terminal` so the operator can compare the recommended engagement against doing nothing

This flag should be treated as informational, not prescriptive. The operator has context the system does not (e.g., known target, other drones in flight).

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
| `n_monte_carlo_samples` | 10,000 | Samples per evaluation point per mode |
| `evaluation_spacing_m` | 500 | Distance between evaluation points |
