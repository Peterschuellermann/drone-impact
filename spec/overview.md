# DroneImpact — Project Overview

## Goal

Given the current trajectory of a hostile drone, compute a scored list of engagement points along that trajectory, each representing the **expected civilian casualties if the drone were intercepted at that location**. Return the recommended engagement point (minimum expected casualties) alongside the full scored list.

The system supports **single-drone** and **batch** analysis. It is designed to be country-agnostic with Ukraine as the primary use case.

---

## Problem Statement

When an air defence unit intercepts a drone, the intercept location determines where wreckage (and potentially the warhead) lands. Intercepting over a populated area may cause more casualties than allowing the drone to continue to a less-populated corridor. This system quantifies that tradeoff for every point along the trajectory so that operators can make informed engagement decisions.

The initial focus is on **Shahed-136 / Geran-2** loitering munitions — the most common drone type observed in the Ukraine theatre.

---

## Scope — Version 1

| In scope | Out of scope |
|---|---|
| Straight-line trajectory assumption | Manoeuvre prediction / path replanning |
| Physics-based terminal trajectory simulation | ML / data-driven trajectory model |
| Three intercept damage modes + miss branch (see below) | Independent debris-fragment tracking |
| Population density + critical infrastructure scoring | Wind and weather effects |
| Fixed 50 % P_kill | Missile-type-specific P_kill |
| Single + batch REST API | Real-time tracker integration |
| Shahed-136 aerodynamic parameters | Other airframe types |
| Ukraine as primary data use case | Dashboard / UI |

Everything out of scope for v1 is tracked on the [roadmap](roadmap.md).

---

## Core Concepts

### Trajectory

A drone trajectory in v1 is a **straight-line path** derived from a single state vector:

```
(lat, lon, altitude_m, heading_deg, speed_m_s)
```

The system discretises this into a sequence of evaluation points at a configurable spacing (default: 500 m along-track).

### Intercept outcome modes

When a missile hits a drone, three damage modes are possible:

| ID | Label | Weight | Description |
|---|---|---|---|
| M1 | `propulsion_loss` | 0.40 | Engine stops; control surfaces remain active → controlled unpowered glide |
| M2 | `loss_of_control` | 0.35 | Guidance/avionics fail; drone is still powered but flies erratically |
| M3 | `break_apart` | 0.25 | Structural failure → tumbling ballistic trajectory |

Each mode produces a different **impact probability distribution** on the ground. Mode weights are conditional on a hit and sum to 1.0.

If the missile **misses** (probability = 1 − P_kill), the drone continues on its nominal trajectory. This "miss branch" is handled separately in the engagement score formula.

### Engagement score

For each trajectory point P_i, the engagement score is the expected number of casualties if the operator fires one missile at that point:

```
E[casualties | engage at P_i] =
    P_kill × Σ_k ( p(mode_k | hit) × E[casualties | impact distribution D_k(P_i)] )
  + (1 - P_kill) × E[casualties | drone reaches end of trajectory]
```

Where:
- `P_kill = 0.50` (fixed, v1)
- `p(mode_k | hit)` are the per-mode conditional probabilities (see [engagement model](engagement-model.md))
- `D_k(P_i)` is the impact footprint distribution for mode k when the drone is at P_i
- The "miss" branch assumes the drone flies its full remaining trajectory and detonates at the end

The **recommended engagement point** is `argmin E[casualties | engage at P_i]` across all trajectory points.

---

## Glossary

| Term | Definition |
|---|---|
| AGL | Above Ground Level |
| P_kill | Probability that a fired missile destroys the drone |
| CEP | Circular Error Probable — radius containing 50 % of impact points |
| TNT equivalent | Normalised explosive energy relative to TNT (1 kg TNT = 4.184 MJ) |
| WGS84 | World Geodetic System 1984 — standard GPS coordinate system |
| ENU | East-North-Up local coordinate frame |
| AUO | All-up-round — complete missile with warhead and motor |
| Monte Carlo | Repeated random sampling to compute probability distributions |
| Kontur | Kontur Population Dataset — recommended population source |
| OSM | OpenStreetMap |

---

## Stakeholders and Use Case

Primary user: **air defence operator or commander** who has detected an inbound Shahed and needs to decide when and where to engage it.

Secondary use case: **post-incident analysis** — running batch evaluations over recorded historical tracks to understand past engagement decisions.
