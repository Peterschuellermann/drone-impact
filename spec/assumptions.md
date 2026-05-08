# Assumptions and Open Questions

This document tracks every assumption made in the v1 implementation and the questions that need answers to validate or replace them. Entries are grouped by subsystem.

**Status tags:** `⚠ unverified` — used a value with no source; `✓ reasonable` — physically defensible but not calibrated; `? open question` — the right approach is itself unknown.

---

## Airframe Parameters (Shahed-136)

| Parameter | Value | Status | Note |
|---|---|---|---|
| Total mass | 200 kg | ⚠ unverified | Open-source estimates range 185–220 kg |
| Warhead mass | 45 kg | ⚠ unverified | Some reports say 40 kg; others up to 50 kg |
| Cruise speed | 51.4 m/s (185 km/h) | ✓ reasonable | Consistent with multiple OSINT sources |
| Glide ratio | 5.0 | ⚠ unverified | Delta-wing planform suggests 5–8; no physical test data available |
| Drag coefficient (tumbling) | 0.8 | ✓ reasonable | Typical for blunt tumbling objects; unverified for this airframe |
| Reference area | 3.5 m² | ⚠ unverified | Estimated from wingspan; no engineering drawing available |

---

## Mode M1 — Propulsion Loss

| Parameter | Value | Status | Note |
|---|---|---|---|
| Heading sigma | 5° | ⚠ unverified | Controls footprint width; no intercept video data to calibrate against |
| Glide ratio sigma | 0.8 | ⚠ unverified | Controls footprint length; arbitrary |
| Glide ratio floor | 0.5 | ✓ reasonable | Physical lower bound; structurally intact airframe won't fall vertically |

**Structural assumption:** M1 assumes the airframe remains intact after propulsion loss and glides unpowered. A partial structural failure mid-glide is not modelled.

**No wind:** The glide path ignores wind. A crosswind systematically shifts the impact ellipse. This is not stochastic — it is a systematic bias whenever wind is non-zero.

---

## Mode M2 — Loss of Control

| Parameter | Value | Status | Note |
|---|---|---|---|
| Initial heading sigma | 30° | ⚠ unverified | Moment of guidance failure; no data |
| Turn rate sigma | 15°/s | ⚠ unverified | Brownian heading walk rate; arbitrary |
| Descent rate | 1.5 m/s | ⚠ unverified | Assumes engine still running but drone slowly losing altitude; no data |
| Max flight time | 300 s | ⚠ unverified | 5-minute cap; arbitrary |

**Structural assumption:** M2 assumes the engine continues running at cruise speed after guidance failure. In reality, some guidance failures also cause engine cutoff (overlaps with M1). The boundary between M1 and M2 is not crisp.

---

## Mode M3 — Break Apart

| Parameter | Value | Status | Note |
|---|---|---|---|
| Heading sigma at breakup | 20° | ⚠ unverified | Controls spread direction; no data |
| Speed sigma at breakup | 10 m/s | ⚠ unverified | Uncertainty in speed at moment of structural failure |
| Pitch distribution | uniform ±20° | ⚠ unverified | Fragments could have any pitch; ±20° is conservative |
| Fragment mass fraction | uniform 0.1–1.0 | ⚠ unverified | Very rough; real fragment distribution is not uniform |
| Drag sigma | 0.15 | ✓ reasonable | Variation in tumbling Cd; physically plausible |
| Air density | 1.225 kg/m³ (sea level) | ⚠ unverified | Constant; actual density decreases ~12% at 400m AGL. Affects fragment range by ~6% |

---

## Mode Weights (Conditional on Hit)

```
propulsion_loss: 0.40
loss_of_control: 0.35
break_apart:     0.25
```

**Status: ⚠ unverified — entirely estimated.**

These weights represent the probability of each terminal mode given that the missile hits. They are the single most physically uninformed numbers in the model. Calibrating them requires intercept video analysis or partner data from Ukrainian air defence. A 10-point shift in `break_apart` vs `propulsion_loss` changes the footprint shape significantly.

**? Open question:** Should mode weights vary by missile type or engagement geometry? An IRIS-T hit at close range (nearly head-on) likely produces a different fragmentation pattern than a Gepard burst from the side.

---

## Engagement Model

| Parameter | Value | Status | Note |
|---|---|---|---|
| P_kill | 0.50 | ⚠ unverified | Fixed regardless of system, range, aspect, or altitude |
| P_detonate | 1.0 (implicit) | ⚠ unverified | 100% detonation assumed; UA reports suggest ~15–25% of intercepted Shaheds do not detonate |
| Shots per engagement | 1 (implicit) | ? open question | Multi-shot doctrine not modelled |

**? Open question — P_kill by system:** Gepard (twin 35mm cannon) vs IRIS-T (IR missile) vs Buk-M1 have substantially different P_kill profiles. Gepard is highly effective at close range against slow targets; IRIS-T is effective at medium range. Using a flat 0.50 for all systems makes the recommendation system-agnostic in a way that may be incorrect.

**? Open question — engagement envelope:** The system currently recommends intercept points without checking whether they are within the missile system's range from a known launcher position. Recommendations may be physically unreachable.

**? Open question — miss branch physics:** When scoring what happens if the drone is not engaged, the model runs M1 (glide) from the last trajectory point. It should arguably run all three modes weighted by their probabilities, or use a different model (the drone completing its mission implies no structural failure).

---

## Casualty Model — Blast

| Parameter | Value | Status | Note |
|---|---|---|---|
| TNT equivalent | 30 kg | ⚠ unverified | 45 kg warhead at ~65% TNT equivalent; formula is defensible but needs source |
| Lethal radius | 5 m | ⚠ unverified | Very conservative; Hopkinson-Cranz scaling for 30 kg TNT yields ~8–12 m for Ps = 100 kPa |
| Injury radius | 80 m | ✓ reasonable | Consistent with NATO STANAG estimates for similar charges |
| P_lethal within lethal zone | 0.90 | ⚠ unverified | |
| P_injury within injury zone | 0.30 | ⚠ unverified | |

**Structural assumption:** All population is modelled as fully exposed outdoors. Buildings are not modelled. This overestimates casualties by 2–5× in urban areas where most Shahed targets are located. Concrete structures reduce blast lethality by ~80%.

---

## Casualty Model — Fragmentation

| Parameter | Value | Status | Note |
|---|---|---|---|
| Lethal radius | 200 m | ⚠ unverified | Shahed-136 warhead fragmentation pattern not publicly documented |
| Danger radius | 400 m | ⚠ unverified | |
| P_frag_lethal within lethal zone | 0.50 | ⚠ unverified | |
| P_frag_danger within danger zone | 0.10 | ⚠ unverified | |

**Structural assumption:** Fragmentation is modelled as uniform in all directions. Real warhead fragmentation has directional concentration along the axis of detonation. Without intercept geometry this cannot be corrected, but the assumption of isotropy may overstate casualties in some directions.

**Structural assumption:** Fragmentation parameters apply to the warhead detonating on impact. For M3 (break apart), a mid-air structural failure may not detonate the warhead at all — fragmentation would then be purely from structural debris, with a much smaller lethal radius. This is not modelled.

---

## Infrastructure Penalty

| Parameter | Value | Status | Note |
|---|---|---|---|
| Penalty radius | 500 m | ⚠ unverified | Arbitrary; no physical basis |
| Max penalty multiplier | 10× | ⚠ unverified | A single impact near a power plant scores 11× the raw casualty figure — very large |
| Infrastructure weights | power_plant: 5, hospital: 4, water: 4, bridge: 3, school: 2 | ⚠ unverified | Relative priorities are reasonable but no calibration source |
| Penalty decay function | linear | ? open question | Linear decay from centroid to radius; step function or inverse-square would be more physically motivated |

**? Open question:** The infrastructure penalty inflates the *casualty score* rather than adding a separate strategic penalty. This means a hit near a power plant in a low-population area scores higher than a hit in a dense residential area with no infrastructure. Whether that is the right trade-off depends on doctrine and must be confirmed with operators.

---

## Population Model

| Parameter | Value | Status | Note |
|---|---|---|---|
| H3 resolution | 8 (~0.74 km² cells) | ✓ reasonable | Good balance between granularity and query speed |
| Data source | Kontur 2023 | ✓ reasonable | Best publicly available dataset; uses WorldPop + census |
| Population displacement | partial | ⚠ unverified | Kontur partially accounts for wartime displacement via 2022–2023 mobility data, but significant uncertainty remains in frontline areas |

**Structural assumption:** Population is static — no day/night variation. Most Shahed attacks occur at night when residential areas have higher occupancy and commercial/industrial areas are largely empty. This systematically misweights urban residential vs industrial targets.

**Structural assumption:** Population is uniformly distributed within each H3 cell (~860m diameter). In practice a single cell may contain a dense apartment block and an adjacent park — the model treats them identically.

---

## Trajectory Model

**Structural assumption — straight line:** The trajectory is a straight-line discretisation of the input state vector. Shaheds have reportedly followed terrain, circled targets, and made course corrections. None of this is modelled. For early-trajectory intercept recommendations this error is small; for late-trajectory points it may be significant.

**Structural assumption — constant altitude:** The input `altitude_m` is applied to all trajectory points. In reality the drone may be climbing, descending, or terrain-following. AGL altitude at each point is computed by subtracting the DEM elevation, so terrain is partially accounted for, but the drone's own altitude profile is assumed flat.

**Structural assumption — constant speed and heading:** Speed and heading are assumed constant throughout the trajectory. No acceleration, no turns.

---

## Scoring Logic

**? Open question — optimisation criterion:** The recommended engagement point is `argmin(expected_casualties)`. This is civilian-protection-first. An alternative is `argmin(expected_casualties | p_kill * engagement_score)` that also accounts for whether the intercept is likely to succeed. Should strategic value of the target factor into scoring?

**? Open question — risk aversion:** Expected value (mean) is used throughout. A risk-averse operator may prefer the point that minimises the 95th percentile or CVaR of casualties, not the mean. These give different recommendations when the casualty distribution is heavy-tailed.

**? Open question — multi-missile allocation:** The batch API scores drones independently. In a swarm, interceptors are a shared resource. Independent scoring ignores this — two recommendations may assign the same interceptor battery to two simultaneous drones.

---

## Priority Summary

The assumptions most likely to produce materially wrong recommendations, in rough priority order:

1. **P_detonate = 1.0** — if ~20% of intercepted Shaheds don't detonate, all casualty scores are overstated by ~20%
2. **P_kill = 0.50** — wrong for every specific system; makes all recommendations system-agnostic
3. **Mode weights** — the physics footprint shape changes dramatically between modes; wrong weights give wrong spatial recommendations
4. **No building sheltering** — 2–5× overestimate in urban areas; affects relative ranking of urban vs rural intercept points
5. **Glide ratio** — directly controls M1 footprint size; a ratio of 5.0 vs 7.0 changes impact range by 40%
6. **No engagement envelope** — recommendations may be physically unreachable
7. **Fragmentation radii** — poorly sourced; 200m lethal radius is large and drives many casualty scores
