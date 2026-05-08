# Assumptions and Open Questions

Every assumption made in v1, grouped by subsystem. For each we note the value used, why it might be wrong, and the specific question to ask an expert.

**Status tags:** `⚠ unverified` — no source; `✓ reasonable` — physically defensible but not calibrated; `? open question` — the right approach is unknown.

---

## Expert Types

Five expert types cover all the questions in this document:

| Tag | Who | What they know |
|---|---|---|
| **[Drone]** | UAV engineers, aerodynamicists, people who have studied the Shahed-136 airframe | Flight dynamics, glide ratio, guidance failure behaviour, structural break-up mechanics |
| **[Missile]** | Air defence systems engineers, weapon system analysts | P_kill by system and range, engagement envelopes, kill mechanism, proximity fuze behaviour, mode weight priors from weapon design |
| **[Blast]** | Terminal ballistics specialists, explosives engineers, EOD analysts | TNT equivalence, fragmentation characterisation, blast radii, casualty probability tables (STANAG/AEP-55) |
| **[Ukraine]** | Ukrainian military, intelligence analysts, UXO clearance teams, radar operators | Operational P_kill and P_detonate observations, intercept footage and track data, UXO compound analysis, population displacement data |
| **[Operator]** | Air defence commanders, doctrine advisors, IHL lawyers | How to weight infrastructure vs casualties, optimisation objective, multi-missile allocation doctrine |

The three expert types you already have cover most questions. **[Blast]** and **[Operator]** are the two additional types needed. Blast expertise is distinct from missile expertise — missile engineers know how a warhead is triggered, but terminal ballistics specialists know how the explosion and fragments behave once it goes off. Operator expertise is needed for all the "how should the system behave" questions that have no physics answer.

---

## Airframe Parameters (Shahed-136)

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Total mass | 200 kg | ⚠ unverified | OSINT estimates range 185–220 kg |
| Warhead mass | 45 kg | ⚠ unverified | Reports vary 40–50 kg |
| Cruise speed | 51.4 m/s (185 km/h) | ✓ reasonable | Consistent across multiple radar track reports |
| Glide ratio | 5.0 | ⚠ unverified | Delta-wing planform suggests 5–8; no test data. Directly sets M1 impact range — a ratio of 7 instead of 5 moves the impact centroid 800 m further downrange at 400 m AGL |
| Drag coefficient (tumbling) | 0.8 | ✓ reasonable | Typical for blunt tumbling objects; unverified for this airframe |
| Reference area | 3.5 m² | ⚠ unverified | Estimated from photographs; no engineering drawing |

**Expert questions:**
- What is the actual warhead fill mass and explosive compound (TNT, RDX, PETN, Composition B)? **[Blast] [Ukraine]**
- Do you have wreckage measurements giving wingspan and fuselage dimensions? **[Drone] [Ukraine]**
- Is there any video or radar data of intact glide-path incidents that would allow glide ratio to be estimated? **[Drone] [Ukraine]**

---

## Mode M1 — Propulsion Loss

The drone loses propulsion and glides unpowered. Impacts cluster in an ellipse along the heading axis, centred approximately `altitude × glide_ratio` downrange.

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Heading sigma | 5° | ⚠ unverified | Assumes aerodynamically stable glide; a damaged tail fin could cause much larger deviation |
| Glide ratio sigma | 0.8 | ⚠ unverified | Controls scatter in range; arbitrary |

**No wind modelled.** A crosswind systematically shifts the entire impact ellipse — this is a bias, not noise.

**Expert question:** Is there radar or video evidence of heading deviation after propulsion loss? Do impact locations cluster tightly along the last heading, or show significant scatter? **[Drone] [Ukraine]**

---

## Mode M2 — Loss of Control

The engine is still running but guidance has failed. The drone flies with a randomly drifting heading while slowly descending, producing the widest footprint of the three modes.

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Initial heading sigma | 30° | ⚠ unverified | Dominant driver of footprint width; entirely arbitrary |
| Turn rate sigma | 15°/s | ⚠ unverified | At this rate the drone could face any direction within ~10 s; probably too high |
| Descent rate | 1.5 m/s | ⚠ unverified | Depends on control surface position at moment of failure; could be 0.5–5 m/s |
| Max flight time | 300 s | ⚠ unverified | Arbitrary cap; at 1.5 m/s descent from 400 m AGL the drone hits the ground in ~267 s anyway |

**Structural assumption:** M2 assumes the engine keeps running after guidance failure. In reality many guidance failures also cut the engine, collapsing M2 into M1.

**Expert question:** Does guidance failure typically cause engine shutdown too? Are there radar tracks showing heading behaviour in the seconds after a suspected guidance failure or jamming event? **[Drone] [Ukraine]**

---

## Mode M3 — Break Apart

Structural failure scatters fragments ballistically from the intercept point. Each fragment is assigned a random mass, heading, pitch, and drag.

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Heading sigma at breakup | 20° | ⚠ unverified | Assumes roughly symmetric breakup; asymmetric failure (one wing) would concentrate fragments |
| Speed sigma at breakup | 10 m/s | ⚠ unverified | Arbitrary uncertainty around cruise speed |
| Pitch distribution | uniform ±20° | ⚠ unverified | No data on whether fragments tend upward, downward, or horizontal |
| Fragment mass fraction | uniform 0.1–1.0 | ⚠ unverified | Real fragment distributions follow a Mott distribution (many small, few large); our uniform distribution overproduces large fragments |
| Air density | 1.225 kg/m³ | ⚠ unverified | Sea-level constant; at 400 m AGL actual density is ~4% lower. Minor; straightforward fix |

**Expert question:** Is there forensic analysis of fragment scatter from M3-type breakup sites — mass distribution, scatter direction, fragment shapes? The fragment mass distribution is the key unknown; it sets how far the outer edge of the debris field extends. **[Blast] [Ukraine]**

---

## Mode Weights — Conditional on Hit

```
propulsion_loss: 0.40   loss_of_control: 0.35   break_apart: 0.25
```

**Status: `⚠ unverified` — entirely estimated. Most consequential unknown in the model.**

These weights determine how the three footprints are combined. A 10-point shift between modes changes the recommended intercept point because the footprints are spatially very different: M1 is a narrow ellipse 1–3 km downrange, M2 is a large circle near the intercept point, M3 is a compact debris field at the intercept point. The current 40/35/25 split is a guess based on the logic that cannon fire (common in Ukraine) favours propulsion damage (M1).

**Expert question:** From reviewing intercept footage or radar tracks, what fraction of confirmed kills show each terminal behaviour — intact glide (M1), powered erratic flight (M2), or mid-air break-up (M3)? Even a rough split would significantly constrain the model. **[Ukraine] [Missile]**

---

## Engagement Model

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| P_kill | 0.50 | ⚠ unverified | Fixed for all systems, ranges, and aspects. Gepard at close range against a slow target likely achieves >0.8; Buk-M1 against Shahed's low RCS may be <0.5 |
| P_detonate | 1.0 (implicit) | ⚠ unverified | UA reporting suggests 15–25% of intercepted Shaheds do not detonate. Non-detonation eliminates blast and warhead fragmentation entirely |
| Shots per engagement | 1 (implicit) | ? open question | Multi-shot doctrine not modelled |

**Expert questions:**
- What confirmed intercept rate per engagement attempt is observed per system type? **[Missile] [Ukraine]**
- What fraction of intercepted Shaheds land without detonation — is this tracked systematically? **[Ukraine] [Blast]**
- What is the doctrine for number of shots per engagement — single shot, or salvo? **[Operator] [Ukraine]**

---

## Casualty Model — Blast

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| TNT equivalent | 30 kg | ⚠ unverified | Assumes 45 kg fill at 65% TNT equivalence. If the fill is PETN or HMX (equivalence 1.6–1.7), the actual TNTe is ~75 kg — 2.5× higher, increasing blast radii by ~37% |
| Lethal radius | 5 m | ⚠ unverified | Blast overpressure only (fragmentation is separate). Hopkinson-Cranz scaling gives ~4–12 m depending on lethality criterion used |
| Injury radius | 80 m | ✓ reasonable | Represents secondary effects (glass, debris) rather than primary overpressure; consistent with NATO estimates for similar charges |
| P_lethal within lethal zone | 0.90 | ⚠ unverified | No calibration source |
| P_injury within injury zone | 0.30 | ⚠ unverified | No calibration source |

**All population is assumed outdoors and fully exposed — no building sheltering.** This overestimates casualties by 2–5× in urban areas. Planned fix in v2.

**Expert questions:**
- What explosive fill compound is used in the Shahed-136 warhead? Has UXO analysis been conducted on recovered intact warheads? **[Blast] [Ukraine]**
- Do you use STANAG 2895 or NATO AEP-55 casualty tables for similar charges? If so, what blast radii and probability values do they give? **[Blast]**

---

## Casualty Model — Fragmentation

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Lethal radius | 200 m | ⚠ unverified | **Most consequential number in the casualty model.** For comparison, an 81 mm mortar has a lethal radius of 35–50 m. 200 m would require a pre-fragmented liner with high-velocity fragments. A simple blast charge without pre-formed fragments is likely 50–100 m |
| Danger radius | 400 m | ⚠ unverified | Should scale with lethal radius once that is corrected |
| P_frag_lethal within lethal zone | 0.50 | ⚠ unverified | Flat across the zone; in reality density drops with range. No calibration source |
| P_frag_danger within danger zone | 0.10 | ⚠ unverified | Same limitation |

**Fragmentation is modelled as uniform in all directions.** Real warhead fragmentation concentrates along the axis of detonation. Mid-air break-up (M3) may not detonate the warhead at all, making fragmentation from structural debris only — much smaller radius.

**Expert questions:**
- Does the Shahed-136 warhead have a pre-fragmented liner, or is it a simple blast charge? **[Blast] [Missile]**
- What fragment velocity and density have been measured from recovered detonation sites? **[Blast] [Ukraine]**

---

## Infrastructure Penalty

| Parameter | Value | Status | Why it might be wrong |
|---|---|---|---|
| Penalty radius | 500 m | ⚠ unverified | No physical basis; represents an operational "concern zone" not a blast radius |
| Max penalty multiplier | 10× | ⚠ unverified | Encodes the doctrine that proximity to a power plant outweighs 10× the direct civilian casualties. May be far too large or too small depending on doctrine |
| Weights (power_plant: 5, hospital: 4, water: 4, bridge: 3, school: 2) | — | ⚠ unverified | Reasonable humanitarian ranking but no calibration source |
| Decay function | linear | ? open question | Arbitrary; step function or inverse-square may be more physically appropriate |

**Expert questions:**
- How should infrastructure proximity be weighted against direct civilian casualties? Is there a doctrinal standard (e.g., IHL proportionality) that anchors these multipliers? **[Operator]**
- Do the relative category weights (power plant > hospital > water > bridge > school) match Ukrainian military priorities? **[Ukraine] [Operator]**

---

## Population Model

| Parameter | Value | Status | Note |
|---|---|---|---|
| H3 resolution | 8 (~0.74 km² cells) | ✓ reasonable | Good granularity/speed balance |
| Data source | Kontur 2023 | ✓ reasonable | Best public dataset; incorporates wartime mobility data |
| Displacement | partial | ⚠ unverified | Significant uncertainty in frontline and occupied oblasts |
| Day/night variation | none | ⚠ unverified | Most Shahed attacks occur at night; residential areas have higher night occupancy than the static model reflects |

**Expert question:** Is there a more current population estimate for Ukraine accounting for post-2022 displacement, particularly in eastern and southern oblasts? **[Ukraine]**

---

## Trajectory Model

**Straight line, constant altitude, constant speed and heading.** Shaheds have reportedly made course corrections, circled targets, and used terrain masking. For early-trajectory intercept recommendations the error is small; for late-trajectory points it may move the recommendation by several kilometres.

**Expert question:** How much do Shaheds typically deviate from a straight-line approach? Are there radar tracks showing the final 20–50 km of approach geometry? **[Drone] [Ukraine]**

---

## Scoring Logic

**? Optimisation criterion:** Recommended point is `argmin(expected casualties)` — civilian protection only. No account of P_kill, strategic target value, or interceptor availability. **[Operator]**

**? Mean vs risk-averse metrics:** Expected value (mean) is used throughout. A risk-averse operator might prefer the 95th percentile or CVaR. These can recommend different intercept points when the casualty distribution is heavy-tailed. **[Operator]**

**? Multi-missile allocation:** Batch API scores drones independently. In a swarm, two recommendations may assign the same interceptor to two simultaneous targets. **[Operator] [Ukraine]**

---

## Missile System Assumptions

`p_kill = 0.50` is currently the same for all systems. The per-system estimates below are working values from open-source material — none validated against operational data. Kill mechanism determines mode weights: cannon fire perforating the airframe produces different terminal behaviour than a proximity-fuze warhead.

### Gepard SPAAG (twin 35 mm)
Fires high-rate bursts at close range. Engine and tail are typical aim points in tail-chase geometry. Small-calibre rounds favour propulsion damage (M1) over full structural break-up (M3).

| P_kill | Mode weights | Max range | Altitude |
|---|---|---|---|
| 0.75–0.90 | M1: 0.55, M2: 0.25, M3: 0.20 | ~3.5 km | 0–3 km |

### IRIS-T SLM
Proximity-fuze blast-fragmentation warhead detonates 2–5 m from target. Higher energy than cannon; more likely to cause structural damage.

| P_kill | Mode weights | Max range | Altitude |
|---|---|---|---|
| 0.85–0.95 | M3: 0.55, M1: 0.30, M2: 0.15 | ~40 km | 0.01–20 km |

### Buk-M1 (9M38)
Large ~70 kg warhead; designed for fast medium-altitude aircraft. Shahed's low RCS and low altitude degrade radar guidance, reducing P_kill below design spec.

| P_kill | Mode weights | Max range | Altitude |
|---|---|---|---|
| 0.45–0.65 | M3: 0.60, M1: 0.25, M2: 0.15 | ~35 km | 0.03–22 km |

### MANPAD (Stinger, Igla-S, Mistral)
IR seeker follows engine exhaust in tail-chase. Small warhead (~1–2 kg) hits engine/tail. Propulsion loss strongly dominant.

| P_kill | Mode weights | Max range | Altitude |
|---|---|---|---|
| 0.50–0.70 | M1: 0.65, M2: 0.20, M3: 0.15 | ~5–8 km | 0.01–4.5 km |

### NASAMS (AIM-120 AMRAAM-ER)
Active radar homing; ~23 kg proximity warhead. All-weather, all-lighting. Similar kill mechanism to IRIS-T.

| P_kill | Mode weights | Max range | Altitude |
|---|---|---|---|
| 0.80–0.90 | M3: 0.50, M1: 0.30, M2: 0.20 | ~25–50 km | 0.03–15 km |

### ZSU-23-4 Shilka / ZU-23-2
23 mm cannon. Similar mechanism to Gepard but smaller calibre. ZU-23-2 is manually aimed — P_kill is highly operator-dependent.

| P_kill | Mode weights | Max range | Altitude |
|---|---|---|---|
| 0.35–0.55 | M1: 0.50, M2: 0.30, M3: 0.20 | ~2–2.5 km | 0–1.5 km |

**Cross-system expert questions:**
- What confirmed intercept rates per engagement attempt are observed for each system against Shaheds? **[Missile] [Ukraine]**
- What terminal mode does each system typically produce — video or track analysis would directly calibrate the mode weights. **[Ukraine] [Missile]**
- Does multi-shot doctrine apply for each system — salvos of 2 missiles or multiple bursts? **[Operator] [Ukraine]**

---

## Priority Summary

Ranked by impact on recommendation quality:

1. **P_detonate = 1.0** — 15–25% non-detonation rate would reduce all casualty scores proportionally
2. **P_kill = 0.50** — wrong for every system; fix with per-system engagement data
3. **Mode weights (40/35/25)** — wrong spatial footprint shape; calibrate with intercept video/track review
4. **No building sheltering** — 2–5× overestimate in urban areas (v2)
5. **Glide ratio = 5.0** — 40% range error if actual ratio is 7.0
6. **Fragmentation lethal radius = 200 m** — may be 2–4× too large without a pre-fragmented warhead
7. **TNT equivalent = 30 kg** — could be 50–75 kg TNTe with a higher-brisance fill
