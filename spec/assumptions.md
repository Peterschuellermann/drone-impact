# Assumptions and Open Questions

Every assumption made in v1, organised by who needs to answer it. Each section contains all the questions for that expert type and the parameters they depend on.

**Status tags:** `⚠ unverified` — no source; `✓ reasonable` — physically defensible but not calibrated; `? open question` — the right approach is unknown.

---

## Expert Types

| Tag | Who | What they know |
|---|---|---|
| **[Drone]** | UAV engineers, aerodynamicists, people who have studied the Shahed-136 airframe | Flight dynamics, glide ratio, guidance failure behaviour, structural break-up mechanics |
| **[Missile]** | Air defence systems engineers, weapon system analysts | P_kill by system and range, engagement envelopes, kill mechanism, proximity fuze behaviour, mode weight priors from weapon design |
| **[Blast]** | Terminal ballistics specialists, explosives engineers, EOD analysts | TNT equivalence, fragmentation characterisation, blast radii, casualty probability tables (STANAG/AEP-55) |
| **[Ukraine]** | Ukrainian military, intelligence analysts, UXO clearance teams, radar operators | Operational P_kill and P_detonate observations, intercept footage and track data, UXO compound analysis, population displacement |
| **[Operator]** | Air defence commanders, doctrine advisors, IHL lawyers | How to weight infrastructure vs casualties, optimisation objective, multi-missile allocation doctrine |

---

## [Drone] — UAV and Airframe Expert

### Airframe physical parameters

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Total mass | 200 kg | ⚠ unverified | OSINT estimates range 185–220 kg |
| Cruise speed | 51.4 m/s (185 km/h) | ✓ reasonable | Consistent across multiple radar track reports |
| Glide ratio | 5.0 | ⚠ unverified | Delta-wing planform suggests 5–8; no test data. A ratio of 7 instead of 5 moves the M1 impact centroid 800 m further downrange at 400 m AGL |
| Drag coefficient (tumbling) | 0.8 | ✓ reasonable | Typical for blunt tumbling objects; unverified for this airframe |
| Reference area | 3.5 m² | ⚠ unverified | Estimated from photographs; no engineering drawing |

### Mode M1 — propulsion loss

The drone glides unpowered. Impact ellipse is centred at `altitude × glide_ratio` downrange along the heading axis.

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Heading sigma | 5° | ⚠ unverified | Assumes stable glide; a damaged tail fin could cause much larger deviation |
| Glide ratio sigma | 0.8 | ⚠ unverified | Controls range scatter; arbitrary |

### Mode M2 — loss of control

Engine still running, guidance failed. Drone drifts with a randomly walking heading while slowly descending.

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Initial heading sigma | 30° | ⚠ unverified | Dominant driver of M2 footprint width; entirely arbitrary |
| Turn rate sigma | 15°/s | ⚠ unverified | At this rate the drone could face any direction within ~10 s; probably too high |
| Descent rate | 1.5 m/s | ⚠ unverified | Depends on control surface position at failure; could be 0.5–5 m/s |
| Max flight time | 300 s | ⚠ unverified | Arbitrary cap; at 1.5 m/s from 400 m AGL the drone hits the ground in ~267 s anyway |

**Structural assumption:** M2 assumes the engine keeps running after guidance failure. Many guidance failures also cut the engine, collapsing M2 into M1.

### Mode M3 — break apart (structural)

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Heading sigma at breakup | 20° | ⚠ unverified | Assumes symmetric breakup; asymmetric failure (one wing) would concentrate fragments |
| Speed sigma at breakup | 10 m/s | ⚠ unverified | Arbitrary uncertainty around cruise speed |
| Pitch distribution | uniform ±20° | ⚠ unverified | No data on whether fragments tend upward, downward, or horizontal |

### Trajectory

Straight line, constant altitude, constant speed and heading. Shaheds have reportedly made course corrections and used terrain masking.

**Questions for drone expert:**
- What are the actual airframe dimensions (wingspan, fuselage cross-section)? Do you have engineering drawings or precise wreckage measurements?
- Is there video or radar data of intact glide-path incidents that would allow glide ratio to be estimated from altitude and horizontal distance to impact?
- Does guidance failure typically cause engine shutdown, or does the engine keep running?
- After a propulsion hit, do impact locations cluster tightly along the last known heading, or show significant scatter?
- How much do Shaheds typically deviate from a straight-line approach? Are there radar tracks of the final 20–50 km of approach geometry?

---

## [Missile] — Air Defence Systems Expert

### P_kill and mode weights per system

`p_kill = 0.50` is currently the same for all systems. Kill mechanism determines mode weights: cannon perforation produces different terminal behaviour than a proximity-fuze warhead. The per-system estimates below are from open-source material — none validated against operational data.

| System | P_kill estimate | Mode weights | Max range | Altitude |
|---|---|---|---|---|
| Gepard SPAAG (35 mm) | 0.75–0.90 | M1: 0.55, M2: 0.25, M3: 0.20 | ~3.5 km | 0–3 km |
| IRIS-T SLM | 0.85–0.95 | M3: 0.55, M1: 0.30, M2: 0.15 | ~40 km | 0.01–20 km |
| Buk-M1 (9M38) | 0.45–0.65 | M3: 0.60, M1: 0.25, M2: 0.15 | ~35 km | 0.03–22 km |
| MANPAD (Stinger, Igla-S) | 0.50–0.70 | M1: 0.65, M2: 0.20, M3: 0.15 | ~5–8 km | 0.01–4.5 km |
| NASAMS (AMRAAM-ER) | 0.80–0.90 | M3: 0.50, M1: 0.30, M2: 0.20 | ~25–50 km | 0.03–15 km |
| ZSU-23-4 / ZU-23-2 | 0.35–0.55 | M1: 0.50, M2: 0.30, M3: 0.20 | ~2–2.5 km | 0–1.5 km |

**Buk-M1 note:** Designed for fast medium-altitude aircraft. Shahed's low RCS and low altitude likely degrade P_kill below design spec.

**MANPAD note:** IR seeker follows engine exhaust in tail-chase. Small warhead (~1–2 kg) hits engine/tail — this is why M1 (propulsion loss) dominates.

### Warhead design

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Fragmentation liner | unknown | ⚠ unverified | If the Shahed warhead has a pre-fragmented liner, lethal radius is ~200 m; if it is a simple blast charge, it is likely 50–100 m — a factor of 2–4× difference in casualty area |

**Questions for missile expert:**
- What P_kill do each of these systems achieve against a slow, low-altitude, low-RCS target like the Shahed-136? Are the ranges in the table above approximately correct?
- For each system, what terminal mode does the weapon tend to produce — intact glide (M1), powered erratic flight (M2), or mid-air break-up (M3)?
- Does the Shahed-136 warhead have a pre-fragmented liner or is it a simple blast charge?
- Are the engagement envelopes (max range, altitude floor/ceiling) in the table correct?

---

## [Blast] — Terminal Ballistics and Explosives Expert

### Warhead explosive properties

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Warhead fill mass | 45 kg | ⚠ unverified | Reports vary 40–50 kg |
| TNT equivalent | 30 kg | ⚠ unverified | Assumes 65% TNT equivalence. If fill is PETN or HMX (equivalence 1.6–1.7), actual TNTe is ~75 kg — 2.5× higher, increasing all blast radii by ~37% |

### Blast casualty model

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Lethal radius | 5 m | ⚠ unverified | Blast overpressure only (fragmentation is separate). Hopkinson-Cranz scaling gives ~4–12 m depending on lethality criterion |
| Injury radius | 80 m | ✓ reasonable | Represents secondary effects (glass, debris); consistent with NATO estimates for similar charges |
| P_lethal within lethal zone | 0.90 | ⚠ unverified | No calibration source |
| P_injury within injury zone | 0.30 | ⚠ unverified | No calibration source |

**All population assumed outdoors, fully exposed — no building sheltering.** Overestimates casualties 2–5× in urban areas. Planned fix in v2.

### Fragmentation casualty model

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Lethal radius | 200 m | ⚠ unverified | **Most consequential number in the casualty model.** An 81 mm mortar has a lethal radius of 35–50 m. 200 m requires a pre-fragmented liner. A simple blast charge is likely 50–100 m |
| Danger radius | 400 m | ⚠ unverified | Should scale with lethal radius once that is corrected |
| P_frag_lethal within lethal zone | 0.50 | ⚠ unverified | Flat across the zone; in reality density drops with range |
| P_frag_danger within danger zone | 0.10 | ⚠ unverified | Same limitation; no calibration source |
| Fragment mass distribution | uniform 0.1–1.0 × total mass | ⚠ unverified | Real distributions follow a Mott distribution (many small, few large); our uniform model overproduces large fragments |

**Fragmentation assumed uniform in all directions.** Real warheads concentrate fragments along the detonation axis. Mid-air break-up (M3) may not detonate the warhead at all, leaving only structural debris with a much smaller effective radius.

**Questions for blast expert:**
- What explosive fill compound is used in the Shahed-136 warhead? Has UXO analysis been conducted on recovered intact warheads?
- Does the warhead have a pre-fragmented liner? This is the single question that most improves the casualty model.
- What fragment velocity and spatial density have been measured from recovered detonation sites?
- Do STANAG 2895 or NATO AEP-55 tables for a comparable charge size match our blast radii and probability values?

---

## [Ukraine] — Operational and Intelligence Data

This section collects questions that can only be answered from observed operational data in Ukraine — intercept footage, radar tracks, UXO analysis, and military reporting.

### Observed intercept outcomes

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| P_kill (all systems) | 0.50 | ⚠ unverified | Flat across all systems and ranges; operationally observed rates per system would replace this |
| P_detonate | 1.0 (implicit) | ⚠ unverified | UA reporting suggests 15–25% of intercepted Shaheds do not detonate, eliminating blast and warhead fragmentation entirely |
| Mode weights | M1: 0.40, M2: 0.35, M3: 0.25 | ⚠ unverified | Entirely estimated; intercept footage review would directly calibrate this |

### UXO and wreckage data

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Warhead explosive compound | assumed TNT-like | ⚠ unverified | Compound determines TNT equivalence factor; affects all blast and fragmentation radii |
| Fragment velocity and density | not measured | ⚠ unverified | Required to validate the 200 m fragmentation lethal radius |
| Airframe dimensions | estimated from photographs | ⚠ unverified | Engineering measurements from wreckage would constrain drag and glide ratio |

### Population data

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Population dataset | Kontur 2023 | ✓ reasonable | Partially incorporates wartime mobility data but significant uncertainty remains in frontline and occupied oblasts |
| Day/night variation | none | ⚠ unverified | Most attacks occur at night when residential occupancy is higher and industrial areas are largely empty |

**Questions for Ukraine expert:**
- What fraction of intercepted Shaheds land without detonation? Is this tracked systematically by the air force?
- From intercept footage or radar tracks: what fraction of confirmed kills show intact glide (M1), powered erratic flight (M2), or mid-air break-up (M3)? Even a rough split helps.
- What operationally observed P_kill per engagement attempt is seen for each system type?
- Has UXO compound analysis been done on recovered intact Shahed warheads?
- What fragment velocity and density has been observed at detonation sites?
- Is there a more current population dataset for Ukraine accounting for post-2022 displacement, particularly in eastern and southern oblasts?
- Are there radar tracks showing Shahed flight path deviations in the final 20–50 km of approach?

---

## [Operator] — Doctrine and Engagement Advisor

These questions have no physics answer — they depend on operational doctrine and how commanders want the system to behave.

### Infrastructure weighting

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Penalty radius | 500 m | ⚠ unverified | No physical basis; represents an operational concern zone |
| Max penalty multiplier | 10× | ⚠ unverified | Encodes the doctrine that proximity to a power plant outweighs 10× the direct civilian casualties — may be far too large or too small |
| Category weights (power_plant: 5, hospital: 4, water: 4, bridge: 3, school: 2) | — | ⚠ unverified | Reasonable humanitarian ranking but no calibration source |

### Scoring objective

| Assumption | Current behaviour | Why it might be wrong |
|---|---|---|
| Optimisation criterion | `argmin(expected casualties)` — civilian protection only | Does not account for P_kill, strategic target value, or interceptor availability |
| Risk metric | Mean casualties over Monte Carlo samples | Risk-averse operators may prefer 95th percentile or CVaR; these can recommend different intercept points |
| Multi-drone allocation | Drones scored independently | In a swarm, two recommendations may assign the same interceptor battery to two simultaneous targets |
| Shots per engagement | Single shot assumed | Multi-shot salvos are not modelled |

**Questions for operator:**
- How should infrastructure proximity be weighted against direct civilian casualties? Is there an IHL proportionality standard that should anchor the multipliers?
- Do the infrastructure category weights (power plant > hospital > water > bridge > school) match Ukrainian military doctrine?
- Should the system optimise for mean expected casualties, or a high-confidence worst-case metric?
- What is the standard engagement doctrine — single shot, or salvo? Does it differ by system?
- In a multi-drone scenario, should the system allocate interceptors across drones, or score each drone independently?

---

## Priority Summary

Ranked by impact on recommendation quality:

1. **P_detonate = 1.0** — 15–25% non-detonation rate would reduce all casualty scores proportionally **[Ukraine]**
2. **P_kill = 0.50** — wrong for every system; fix with per-system engagement data **[Missile] [Ukraine]**
3. **Mode weights (40/35/25)** — wrong spatial footprint shape; calibrate with intercept video/track review **[Ukraine] [Missile]**
4. **No building sheltering** — 2–5× overestimate in urban areas (planned v2) **[Blast]**
5. **Glide ratio = 5.0** — 40% range error if actual ratio is 7.0 **[Drone] [Ukraine]**
6. **Fragmentation lethal radius = 200 m** — may be 2–4× too large without a pre-fragmented warhead liner **[Blast] [Missile]**
7. **TNT equivalent = 30 kg** — could be 50–75 kg TNTe with a higher-brisance fill **[Blast] [Ukraine]**
