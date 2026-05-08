# Assumptions and Open Questions

This document tracks every assumption made in the v1 implementation. For each value it explains what the parameter physically represents, how we arrived at the number, how sensitive the output is to errors in it, and the specific question an expert should be asked to validate or replace it.

**Status tags:** `⚠ unverified` — used a value with no source; `✓ reasonable` — physically defensible but not calibrated; `? open question` — the right approach is itself unknown.

---

## Airframe Parameters (Shahed-136)

### Total mass — 200 kg `⚠ unverified`

The total takeoff weight of the airframe including fuel, warhead, and structure. It appears directly in the M3 (break-apart) ballistic simulation: heavier fragments decelerate more slowly and travel further. Open-source OSINT and wreckage photographs suggest 185–220 kg. We used 200 kg as a round central estimate.

**Sensitivity:** A 10% error in total mass changes M3 fragment range by roughly 5% via the drag deceleration term. Moderate impact.

**Expert question:** Do you have access to recovered wreckage weighing data or technical intelligence estimates for the Shahed-136 airframe mass? We need total mass including full fuel load, and separately the dry mass (warhead + structure without fuel).

---

### Warhead mass — 45 kg `⚠ unverified`

The explosive payload mass. This is used to calculate the TNT equivalent charge, which then sets the blast lethal and injury radii via Hopkinson-Cranz scaling. Open-source reporting gives figures between 40 and 50 kg; we used 45 kg. The explosive fill type (TNT, RDX, PETN, Composition B) matters as much as the mass, because each type has a different energy-to-TNT conversion factor.

**Sensitivity:** Blast radii scale as W^(1/3), so a 30% error in fill mass produces only a 9% error in blast radius — blast is relatively robust to mass uncertainty. However, if the fill is PETN or HMX instead of TNT, the TNT equivalent doubles, which doubles the cube root and increases blast radii by ~26%.

**Expert question:** What is the warhead fill mass and explosive type? Has recovered unexploded ordnance (UXO) been analysed to determine the explosive compound? RDX/TNT mixtures (Composition B) and PETN have TNT equivalence factors of 1.3–1.7, which would substantially increase blast radii.

---

### Cruise speed — 51.4 m/s (185 km/h) `✓ reasonable`

How fast the drone was flying at the time of intercept. Speed appears directly in both M2 (distance covered while still powered and flying erratically) and M3 (initial kinetic energy and range of ballistic fragments). This figure is consistent across several published radar tracking reports and is treated as reliable.

**Sensitivity:** Speed scales the M2 footprint radius linearly. A ±10 m/s error produces ±15–20% change in M2 footprint area. For M3, kinetic energy scales as v², so a 20% speed error produces ~44% error in initial kinetic energy, though drag quickly dominates and the range error is smaller in practice (~10–15%).

**Expert question:** What speed do radar tracks consistently show for Shaheds at typical engagement altitudes (300–500 m AGL)? Is there evidence of speed variation between different production batches or attack profiles?

---

### Glide ratio — 5.0 `⚠ unverified`

For the M1 (propulsion loss) mode: the ratio of horizontal distance covered to altitude lost during unpowered glide. A ratio of 5.0 means that from 400 m AGL, a drone with failed propulsion glides approximately 2,000 m horizontally before impact. The Shahed-136 has a delta-wing planform, which typically achieves glide ratios of 5–8 for an intact airframe. We used 5.0 as a conservative lower bound, assuming some control surface damage at the moment of propulsion loss.

**Sensitivity:** This is the single most consequential parameter for M1. The M1 footprint extends from the intercept point to `altitude × glide_ratio` along the heading. At 400 m AGL, a glide ratio of 5.0 puts the centroid of impacts ~2,000 m downrange; a ratio of 7.0 puts it ~2,800 m downrange. That 800 m difference may move the impact zone from an open field to a residential area. A 40% error in glide ratio produces a 40% error in M1 range — this is a high-sensitivity parameter.

**Expert question:** Is there aerodynamic analysis of the Shahed-136 wing geometry, or any flight test data from recovered airframes? Video footage of propulsion-loss incidents (drone still structurally intact, engine stopped) would allow glide ratio to be estimated from altitude and horizontal distance at impact. Even two or three calibrated data points would significantly reduce this uncertainty.

---

### Drag coefficient (tumbling) — 0.8 `✓ reasonable`

For the M3 (break-apart) mode: how much aerodynamic drag the tumbling wreckage experiences. A smooth sphere has Cd ≈ 0.47; a flat plate perpendicular to flow has Cd ≈ 1.28; a blunt, irregularly tumbling object typically falls in the 0.7–1.0 range. We used 0.8 as a mid-range estimate. This affects how quickly M3 fragments decelerate and therefore how far they travel.

**Sensitivity:** Doubling Cd roughly halves fragment range. The uncertainty in Cd is smaller than in fragment mass (which varies by a factor of 10 in our model), so this is a second-order effect. The sigma on Cd (0.15) is probably more important than the mean value.

**Expert question:** Do you have forensic photographs of typical Shahed wreckage fragments? The shape determines Cd. Are most fragments roughly flat plate-like (higher drag, shorter range) or more cylindrical (lower drag, longer range)?

---

### Reference area — 3.5 m² `⚠ unverified`

The cross-sectional area used in the drag force calculation: `F_drag = 0.5 × ρ × Cd × A × v²`. This is estimated from the Shahed-136 wingspan (~2.5 m) multiplied by a representative body depth (~0.4 m), giving ~1 m² for the body, plus ~2.5 m² for the wing presented edge-on while tumbling — a rough 3.5 m² aggregate. In reality, a tumbling object cycles through different orientations, so this is an effective average area.

**Sensitivity:** Reference area and Cd appear together as a product (`Cd × A`) in every drag calculation. Errors in one can be compensated by errors in the other. A factor-of-2 error in reference area would produce a large change in M3 fragment range. However, since reference area and Cd are correlated (both are uncertain in the same direction), the combined uncertainty is what matters.

**Expert question:** Do engineering drawings or precise wreckage measurements give the fuselage cross-section and wing chord? Even an estimate from high-resolution photographs would constrain this better than our current guess.

---

## Mode M1 — Propulsion Loss

In M1 the engine has stopped and the airframe glides unpowered. The drone maintains its last heading approximately but deviates due to aerodynamic imperfections or minor control surface damage. Impact points cluster in an ellipse elongated along the heading axis, centred approximately `altitude × glide_ratio` downrange.

### Heading sigma — 5° `⚠ unverified`

The standard deviation of the heading deviation during unpowered glide. A value of 5° means the heading varies by roughly ±10° (2-sigma), producing a narrow ellipse. This assumes the airframe is aerodynamically stable and the control surfaces are mostly intact. If the propulsion loss was caused by a hit that also damaged a tail fin, the drone could yaw significantly.

**Sensitivity:** Heading sigma directly controls the width of the M1 impact ellipse perpendicular to the heading axis. Doubling this to 10° doubles the footprint width, potentially moving the ellipse from over a field to spanning a road or village.

**Expert question:** Is there radar tracking data showing the heading behaviour of drones after propulsion loss — i.e., do they fly straight or drift? Video of M1-type incidents (propulsion hit, intact glide) would allow heading deviation to be measured from the last tracked position to the impact point.

---

### Glide ratio sigma — 0.8 `⚠ unverified`

The standard deviation of the glide ratio. With a mean of 5.0 and sigma of 0.8, approximately 68% of simulated glides fall between glide ratios of 4.2 and 5.8. This controls the scatter of impact points along the heading axis. A larger sigma means impacts are spread over a longer range band; a smaller sigma concentrates them.

**Sensitivity:** This parameter controls how elongated (vs concentrated) the M1 footprint is along the heading direction. It is less sensitive than the glide ratio mean itself — the mean shifts the whole ellipse, while the sigma only affects its length spread. A sigma of 1.5 instead of 0.8 would roughly double the length of the footprint.

**Expert question:** Do impact site records for M1-type incidents show consistent range from the intercept point, or significant scatter? If multiple M1-type impacts at similar altitude are documented, the range scatter directly gives this parameter.

---

## Mode M2 — Loss of Control

In M2 the engine is still running at cruise speed but guidance has failed. The drone continues flying but with a randomly drifting heading, slowly descending. This produces the widest footprint of the three modes, potentially covering several kilometres in any direction.

### Initial heading sigma — 30° `⚠ unverified`

At the instant guidance fails, the drone's heading may suddenly deviate from its prior course. A sigma of 30° means there is a ~5% chance the drone initially turns more than 60° off course. This could happen if guidance failure coincides with a control surface impulse (e.g., electronic warfare causes a sudden rudder command before lockup). The value 30° is arbitrary.

**Sensitivity:** This is a dominant driver of M2 footprint width. If the true sigma is 15°, the footprint covers a much narrower corridor; if it is 45°, the footprint approaches isotropic (equal probability in all directions). The choice between these has large operational consequences: a narrower footprint suggests engagement early in the trajectory is safer; an isotropic footprint makes early vs late engagement less different.

**Expert question:** Are there radar or optical tracking records of drones immediately after an electronic warfare or guidance failure event? The heading change in the first 5–10 seconds would constrain this parameter. Alternatively, ground crew or signals intelligence analysts familiar with Shahed guidance failures may know whether they tend to be sudden or gradual.

---

### Turn rate sigma — 15°/s `⚠ unverified`

Once flying uncontrolled, the drone's heading random-walks at this rate. At 15°/s, the heading diffuses by roughly 1 radian (57°) in about 4 seconds, meaning the drone could be pointing in almost any direction within ~10 seconds. This seems high — even a severely damaged drone has some aerodynamic restoring force. A more aerodynamically stable drone might show sigma closer to 5°/s.

**Sensitivity:** Over 300 seconds of uncontrolled flight (the M2 time cap), the total heading diffusion scales as sigma × sqrt(time). At 15°/s the footprint becomes nearly circular within ~30 seconds. Reducing this to 5°/s would produce a much more elongated footprint, more sensitive to initial heading direction.

**Expert question:** Is there any analysis of GPS-jammed or EW-affected drone flight paths? The angular rate of heading change in those tracks would directly calibrate this parameter. Ukrainian EW operators or analysts reviewing radar tracks of successful jamming events would be the right source.

---

### Descent rate — 1.5 m/s `⚠ unverified`

With the engine running but guidance lost, the drone slowly loses altitude. 1.5 m/s descent means from 400 m AGL, the drone stays airborne for ~267 seconds before hitting the ground. This rate was estimated assuming the drone adopts a slightly nose-down attitude in the absence of control inputs. The true rate depends heavily on the control surface position at the moment of failure — a nose-up lock could produce level or climbing flight briefly; nose-down could produce 3–5 m/s descent.

**Sensitivity:** Descent rate directly controls how long M2 simulations run, which controls how far fragments can travel. Doubling the descent rate to 3 m/s halves the flight time and halves the maximum M2 footprint radius. This parameter is highly sensitive for high-altitude intercepts.

**Expert question:** Does guidance failure typically cause immediate engine cutoff (collapsing M2 into M1), or does the engine continue running? If the engine continues, what is the typical altitude loss rate observed in tracking data before impact?

---

## Mode M3 — Break Apart

In M3 the airframe suffers structural failure and fragments scatter ballistically from the intercept point. Each simulated fragment is given a random initial velocity derived from the drone's speed at breakup, then falls subject to drag and gravity. This produces a roughly elliptical but irregular debris field.

### Pitch distribution — uniform ±20° `⚠ unverified`

At the moment of structural failure, fragments can be thrown upward or downward relative to horizontal. We assume any pitch angle between −20° (diving) and +20° (climbing) is equally likely. This is a simplification — in practice, a mid-air collision or warhead proximity detonation would produce a directed fragmentation cone. A fragment thrown at +20° from 400 m AGL travels much further than one at −20°.

**Sensitivity:** The upward fragments (positive pitch) travel further than horizontal or downward fragments. The ±20° uniform range was chosen to avoid extreme long-range fragments while still capturing some scatter. If the real distribution were ±5° (near-horizontal), M3 ranges would concentrate more tightly. If ±45° were used, a small fraction of fragments would travel very far.

**Expert question:** Is there forensic data on fragment scatter geometry from recovered M3-type breakup sites? Do fragments tend to scatter horizontally (consistent with ±20°) or is there evidence of a significant upward or downward component? An explosives or terminal ballistics expert reviewing the intercept mechanism could advise on the expected pitch distribution.

---

### Fragment mass fraction — uniform 0.1 to 1.0 `⚠ unverified`

When the drone breaks apart, we simulate it as a single "effective fragment" whose mass is a random fraction of the total airframe mass. A fraction of 0.1 gives a 20 kg fragment; 1.0 gives the full 200 kg airframe. The uniform distribution is a placeholder — real structural breakup follows a Mott distribution (many small fragments, few large ones). We do not simulate multiple simultaneous fragments.

**Sensitivity:** Fragment mass directly affects how far a fragment travels against drag. A 20 kg fragment decelerates much more slowly than a 2 kg piece of fuselage. The largest fragments drive the outer edge of the M3 debris field. With a uniform 0.1–1.0 distribution, we produce some very large "fragments" that travel far; a realistic Mott distribution would concentrate most mass in small pieces with a long tail.

**Expert question:** Is there fragmentation analysis data from recovered Shahed wreckage — specifically the distribution of fragment masses? IMAS (International Mine Action Standards) or terminal ballistics experts characterise this using the Mott or Gurney equations. The most important quantity is the mass of the heaviest 10% of fragments, since those drive the outer lethal boundary.

---

### Air density — 1.225 kg/m³ (sea-level constant) `⚠ unverified`

The drag force in M3 is proportional to air density: `F_drag = 0.5 × ρ × Cd × A × v²`. We use sea-level density throughout, but Shahed intercepts typically occur at 300–600 m AGL. At 400 m, actual density is ~1.175 kg/m³ (about 4% less). This underestimates drag slightly, overestimating fragment range by ~2–3%. This is a small error compared to other uncertainties and is a straightforward code fix (no expert needed — use the ISA atmosphere table).

---

## Mode Weights — Conditional on Hit

```
propulsion_loss: 0.40
loss_of_control: 0.35
break_apart:     0.25
```

**Status: `⚠ unverified` — entirely estimated. These are among the most consequential numbers in the model.**

These weights represent the probability of each terminal mode, conditional on a successful intercept (the weapon hit the drone). They govern how the three simulation footprints are combined into the final casualty estimate. A shift of just 10 percentage points between modes changes the recommended engagement point because the spatial footprints are radically different:

- M1 (propulsion loss) produces a narrow ellipse 1–3 km downrange along the heading.
- M2 (loss of control) produces a large, roughly circular footprint centred near the intercept point.
- M3 (break apart) produces a compact debris field close to the intercept point.

The current 40/35/25 split was estimated based on the logic that cannon fire (the most common Ukrainian intercept method) tends to damage propulsion systems (favouring M1), while missile warheads with proximity fuze tend to cause structural damage (favouring M3). But there is no empirical data behind these fractions.

**Expert question:** From intercept footage analysis, radar track post-processing, or wreckage location relative to intercept point, what fraction of successful intercepts show each mode? Ukrainian air force intelligence analysts who systematically review intercept outcomes would be the key source. Even a rough order-of-magnitude split (e.g., "M1 is twice as common as M3") would meaningfully constrain the model.

**? Open question:** Mode weights should vary by weapon system. A MANPAD hitting the engine exhaust (M1-dominant) behaves very differently from an IRIS-T proximity fuze (M3-dominant). See the Missile System section below.

---

## Engagement Model

### P_kill — 0.50 `⚠ unverified`

The probability that a single engagement attempt results in a confirmed kill. "Kill" here means the drone stops flying and falls — it does not imply warhead detonation, which is modelled separately (see P_detonate). P_kill = 0.50 means half of all engagement attempts in the model result in the drone falling; the other half result in the drone continuing on its trajectory.

This single parameter is currently the same for every missile system, every range, and every engagement geometry. In reality, a Gepard at 1 km range against a slow low-flying Shahed achieves very different P_kill than a Buk-M1 at 30 km. The 0.50 default was chosen as a neutral starting point in the absence of per-system data.

**Sensitivity:** P_kill directly scales how much the intercept recommendation matters. If P_kill is actually 0.9 (likely for Gepard at optimal range), then the miss branch (drone completes trajectory) is only 10% likely, and the recommendation is dominated by the terminal mode footprints. If P_kill is 0.3 (Buk-M1 struggling with low-RCS target), the miss branch dominates and the recommendation becomes nearly independent of intercept point. A wrong P_kill by ±0.3 changes the engagement score formula significantly.

**Expert question:** What is the confirmed intercept rate per engagement attempt for each system deployed in Ukraine against Shaheds? Are engagement logs maintained that record shots fired vs kills confirmed? Even approximate rates per system type (Gepard: ~80%, MANPAD: ~55%, Buk-M1: ~45%) would allow meaningful per-system recommendations.

---

### P_detonate — 1.0 (implicit, no detonation model) `⚠ unverified`

The model currently assumes that every intercepted Shahed detonates its warhead on impact with the ground. Ukrainian military reporting and media coverage consistently describe intercepted Shaheds landing without explosion — estimates range from 15% to 25% non-detonation. A non-detonating warhead means no blast zone, no warhead fragmentation, and only structural debris (M3-equivalent without the warhead contribution). Non-detonation dramatically reduces the civilian risk of an intercept.

**Sensitivity:** If P_detonate is actually 0.80, all casualty scores for intercepted drones are overstated by approximately 20%. More importantly, it affects which intercept points look safest: a low-population area with a non-detonating warhead should be preferred over a high-population area, but the model currently treats both equally.

**Expert question:** What is the Ukrainian air force's estimate of the fraction of intercepted Shaheds that detonate on impact? Is this tracked systematically, or is the figure anecdotal? Is there a known difference between warhead lots or attack profiles that affects detonation reliability?

---

## Casualty Model — Blast

### TNT equivalent — 30 kg `⚠ unverified`

The energy of the warhead detonation expressed in equivalent kilograms of TNT. This is derived as: `45 kg fill × 0.65 TNT equivalence factor ≈ 30 kg TNTe`. The 0.65 factor assumes the explosive is a TNT/RDX mixture (Composition B) at approximately 65% TNT potency. However:

- Pure TNT: 1.0 equivalence factor → 45 kg TNTe
- Composition B (RDX/TNT): 1.35 → 61 kg TNTe
- PETN: 1.66 → 75 kg TNTe
- HMX: 1.7 → 76 kg TNTe

If the fill is a higher-brisance explosive, the actual TNT equivalent could be 2–2.5× our estimate, which would increase blast radii by 25–37% (via cube-root scaling).

**Expert question:** What explosive compound is used in the Shahed-136 warhead? Has any UXO analysis been conducted on recovered intact warheads? The TNT equivalence factor is the most important multiplier in the entire blast sub-model.

---

### Lethal blast radius — 5 m `⚠ unverified`

The radius within which the blast overpressure is sufficient to kill an unprotected person standing in the open. This is computed separately from fragmentation; it represents direct overpressure injury only. Using Hopkinson-Cranz scaling for a 30 kg TNTe charge, the overpressure at 5 m is approximately 100–150 kPa — above the threshold for lethal pulmonary damage. At 80 m (our injury radius), overpressure drops to ~1–2 kPa, which is below the threshold for primary blast injury but can cause eardrum rupture and is consistent with glass breakage and secondary debris injuries.

The 5 m lethal radius seems physically reasonable for pure overpressure, but it is conservative — it does not account for the ground reflection wave, which can double the effective overpressure in the near field. A value of 8–12 m would be more consistent with NATO STANAG casualty estimation guidelines for charges of this size.

**Expert question:** What lethal overpressure threshold do you use in your casualty estimation framework — 100 kPa (lung damage) or 200 kPa (immediate death)? At 30 kg TNTe, the Hopkinson-Cranz formula gives a lethal radius of roughly 4–12 m depending on the criterion. Does this align with STANAG 2895 or equivalent NATO/UN casualty tables?

---

### Injury blast radius — 80 m `✓ reasonable`

At 80 m from a 30 kg TNTe detonation, direct overpressure is very low (< 2 kPa). This radius does not represent primary blast injury but rather secondary effects: broken glass fragments, displaced masonry, and blast-propelled debris. The 80 m figure is broadly consistent with NATO and UN casualty estimation guidelines for charges in the 20–50 kg TNTe range. We treat this parameter as reasonable, though it is not sourced from a specific publication.

**Expert question:** Is there an existing STANAG or NATO AASTP reference for the secondary injury radius of a ~30 kg TNTe charge in an urban environment? We would like to anchor this to a published standard rather than an estimate.

---

### P_lethal (within lethal zone) — 0.90 `⚠ unverified`

Within the 5 m lethal radius, we assume 90% of exposed persons are killed. This is a lethality-given-exposure factor. The remaining 10% accounts for people behind solid cover, in basements, or otherwise shielded within the zone. The value seems high but is physically plausible for the near-field overpressure.

### P_injury (within injury zone) — 0.30 `⚠ unverified`

Within the 5–80 m injury zone, we assume 30% of exposed persons sustain injury. This accounts for the fact that not every person is facing toward the blast or in a position to be hit by secondary debris. The 30% figure is an estimate with no calibration source.

**Expert question (both):** Do you use standard casualty fraction tables for shaped charges? The US Army TM 5-855-1 or NATO AEP-55 contain empirical P_lethal and P_injury tables as a function of scaled distance. We would like to replace our estimates with tabulated values from an authoritative source.

---

## Casualty Model — Fragmentation

### Lethal fragmentation radius — 200 m `⚠ unverified`

The radius within which a person in the open has elevated probability of lethal fragment impact. This is the most consequential single number in the entire casualty model — it determines the area over which the Monte Carlo impact points are assessed for casualties.

For context: an 81 mm mortar round has a fragmentation lethal radius of ~35–50 m; a 155 mm artillery shell ~50–100 m. A 45 kg warhead is substantially larger, but 200 m would require high-velocity pre-formed fragments (like a Claymore mine, which uses ~700 steel balls) and/or a warhead specifically designed for wide-area fragmentation. If the Shahed warhead is a simple blast charge without a pre-fragmented liner, the effective fragmentation lethal radius may be 50–100 m rather than 200 m.

The current 200 m figure means that within each Monte Carlo simulation, population within a 200 m radius of each impact point is counted as potentially lethal. Halving this to 100 m would reduce casualty estimates by approximately 75% (area scales as r²).

**Expert question:** Is there forensic evidence of Shahed-136 warhead fragmentation — specifically fragment velocity, mass, and density at distance? Has any terminal ballistics analysis been conducted on detonated warheads? The key question is: does the warhead have a pre-fragmented liner or is it a simple blast charge? This single data point would allow us to anchor the fragmentation radius to empirical or physical data rather than a guess.

---

### Danger fragmentation radius — 400 m `⚠ unverified`

The outer boundary of significant fragmentation risk. In this zone (200–400 m), fragments are assumed to have lost enough velocity to be non-lethal but can still cause serious injury. At 400 m, even a fast fragment (initial velocity ~800 m/s) has been significantly decelerated. Whether any fragments remain dangerous at 400 m depends on their initial velocity and mass distribution.

**Expert question:** Same as for lethal radius. If the lethal radius is revised, the danger radius should scale proportionally.

---

### P_frag_lethal — 0.50 within the lethal zone `⚠ unverified`

The probability that a person standing anywhere within the 200 m lethal zone is hit by a lethal fragment. A flat 50% probability across the entire zone is a significant simplification — in reality, fragment density declines rapidly with distance. A person at 10 m from detonation has a much higher probability of lethal hit than one at 190 m. We apply the same 50% to both.

**Expert question:** Fragment density as a function of range is given by `N(r) = N_total / (4π r²)` for an isotropic distribution, modified by the Mott fragment distribution. An explosives or terminal ballistics engineer could provide a fragmentation characterisation (number of lethal fragments vs range) that would replace this flat probability with a physically grounded decay function.

---

### P_frag_danger — 0.10 within the danger zone `⚠ unverified`

The probability of injury for a person anywhere within the 200–400 m danger annulus. Same limitation as P_frag_lethal above — this should ideally be a function of range, not a flat probability.

---

## Infrastructure Penalty

### Penalty radius — 500 m `⚠ unverified`

Within 500 m of a critical infrastructure node (power plant, hospital, etc.), the casualty score is multiplied by the infrastructure weight. The 500 m radius has no physical basis — it does not correspond to a blast radius (which is much smaller) nor a known operational "safety margin." It was chosen to create a visible buffer zone around infrastructure.

**Expert question (doctrine):** What radius do operators consider operationally significant for near-miss impacts on critical infrastructure? For example, is a Shahed impact 300 m from a power plant substation considered a threat to that substation (from blast, fragments, or fire)? This question is about operational doctrine rather than physics.

---

### Max penalty multiplier — 10× `⚠ unverified`

A hit within 500 m of a power plant multiplies the total casualty score by up to 11× (1 + weight of 10). This means we model proximity to a power plant as equivalent to 11× the direct civilian casualties in a bare field. This multiplier is very large and untethered to any physical consequence. It essentially encodes the doctrine that infrastructure protection outweighs direct casualty minimisation by a factor of 10.

**Sensitivity:** This multiplier can completely dominate the score in low-population areas near infrastructure. A field with 1 expected casualty near a power plant scores 11, while a residential street with 10 expected casualties and no nearby infrastructure scores 10. The recommendation system would prefer the residential street — which may or may not match operator intent.

**Expert question (doctrine):** How should infrastructure proximity be weighted against direct civilian casualties in engagement scoring? Is there a doctrinal formula (e.g., "a power plant outage affecting X people for Y days is equivalent to Z direct casualties") that would anchor this multiplier to an operational standard?

---

### Infrastructure weights `⚠ unverified`

| Category | Weight | Rationale |
|---|---|---|
| power_plant | 5.0 | Grid disruption affects millions; heating in winter is life-threatening |
| hospital | 4.0 | Immediate impact on medical capacity; irreplaceable in wartime |
| water_works | 4.0 | Water supply disruption; potential disease risk |
| bridge | 3.0 | Military logistics and civilian movement |
| school | 2.0 | Civilian shelter; symbolically significant |

These weights determine the relative priority of infrastructure types when both are near an intercept point. They reflect a reasonable humanitarian ranking but have no calibration source.

**Expert question (doctrine):** Do these relative priorities match Ukrainian military engagement doctrine? Should bridges receive higher weight given their military logistics significance? Should schools and shelters be equivalent to hospitals in wartime? A doctrine or legal expert (IHL) familiar with proportionality assessments could advise on the appropriate weighting.

---

## Population Model

### H3 resolution — 8 (~0.74 km² cells) `✓ reasonable`

The Kontur population data is stored at H3 resolution 8, where each hexagonal cell covers approximately 0.74 km² (~860 m diameter). Population queries sum over the cells within a given radius, with the number of rings determined by the radius divided by the approximate cell diameter. This resolution is a reasonable balance between spatial granularity and computational speed.

**Limitation:** A single H3 cell at resolution 8 may span a dense apartment block and an adjacent park, or straddle a road. Population is treated as uniformly distributed across the cell. For very small blast radii (5 m), the within-cell uniformity assumption is the dominant source of spatial error in the casualty estimate.

---

### Kontur 2023 dataset `✓ reasonable`

Kontur combines WorldPop satellite-derived estimates with national census data to produce a 400 m resolution global population map. For Ukraine, the 2022–2023 version partially incorporates wartime mobility data (estimated from mobile network data), partially capturing the large population displacement caused by the conflict.

**Known limitation:** Population counts in active conflict zones (frontline areas, occupied territories) are highly uncertain. Kontur 2023 may significantly underestimate or overestimate population in areas where displacement is ongoing. The dataset should be treated as approximate in eastern and southern oblasts.

**Expert question:** Is there a more current or accurate population dataset for Ukraine that accounts for post-2022 displacement? UNHCR, IOM, or Ukrainian state statistics agencies may have more recent estimates for specific regions.

---

### Population is static — no day/night variation `⚠ unverified`

The model uses a single population count for all times of day and week. In reality, population distribution shifts significantly between day and night: residential areas have higher occupancy at night (people are home sleeping), while commercial and industrial areas are largely empty. Most Shahed attacks occur between midnight and 06:00 local time. This means our model may underweight residential areas (higher night occupancy) and overweight commercial/industrial areas (lower night occupancy) relative to actual attack timing.

**Expert question:** Do you have or know of time-of-day population distribution data for Ukrainian cities? OSM land-use classification combined with standard activity profiles could provide rough day/night weighting factors. OSINT-based estimates from urban planners or humanitarian organisations might also be available.

---

## Trajectory Model

### Straight-line trajectory `? open question`

The trajectory is discretised as a straight line from the input state vector. Shahed-136 drones have reportedly followed circuitous routes, made course corrections mid-flight, and used terrain masking. For the purpose of intercept recommendations, this means:

- Early trajectory points (far from target): the straight-line assumption is likely good — the drone has not yet begun manoeuvring.
- Late trajectory points (close to target): the drone may be in a final approach phase that deviates from the extrapolated straight line.

The model has no mechanism to predict or account for these deviations.

**Expert question:** How much do Shaheds typically deviate from a straight-line approach? Are there radar track records showing the final 20–50 km of approach geometry? A rough estimate of typical course deviation (e.g., "within ±15° of the final heading for the last 30 km") would let us quantify how much this simplification affects recommendation accuracy.

---

### Constant altitude `⚠ unverified`

The input `altitude_m` is applied uniformly to all trajectory points. The DEM elevation is subtracted at each point to compute AGL altitude, so terrain variation is partially captured. However, the drone's own altitude profile is assumed flat — no climbing, no descending, no terrain-following.

**Expert question:** Do radar tracks show consistent altitude maintenance, gradual descent, or terrain-following behaviour during approach? Even a rough altitude trend (e.g., "descends from 500 m to 200 m over the final 30 km") would improve the M1 footprint accuracy significantly for late-trajectory engagement points.

---

## Scoring Logic

### Objective function — argmin(expected casualties) `? open question`

The recommended engagement point is the one minimising expected civilian casualties. This is a purely humanitarian optimisation. It does not account for the probability of the intercept succeeding, the strategic value of the protected target, or the availability of interceptors.

**Expert question (doctrine):** Should the recommendation system factor in the probability that the intercept succeeds (P_kill), the military value of the protected target, or resource constraints? Or is civilian protection the sole criterion? The answer determines whether we recommend the "safest miss" or the "best kill probability."

---

### Expected value (mean) vs risk-averse metrics `? open question`

The casualty estimate is the mean over 10,000 Monte Carlo samples. A risk-averse operator may care more about the 95th percentile or Conditional Value at Risk (CVaR) — i.e., what happens in bad cases rather than on average. When the casualty distribution is heavy-tailed (a few samples with very high casualties), the mean and the 95th percentile can recommend different intercept points.

**Expert question:** When you evaluate engagement options, do you use expected (average) casualties or a worst-case / high-confidence metric? In other words, do you prefer a point with low average casualties but occasional very bad outcomes, or a point with slightly higher average but bounded worst case?

---

## Missile System Assumptions

The current model uses a single flat `p_kill = 0.50` for all systems. When per-system support is added, each system will need its own P_kill estimate, mode weight profile, and engagement envelope. The values below are working estimates from open-source and declassified material — none have been validated against operational data.

**Kill mechanism governs mode weights.** A cannon burst perforating the airframe produces different terminal behaviour than a proximity-fuze warhead detonating nearby. Mode weights must therefore vary by weapon system.

---

### Gepard SPAAG (twin 35 mm Oerlikon)

**Kill mechanism:** The Gepard fires short bursts of 35 mm rounds at high rate. Against a Shahed at 1–3 km, multiple rounds perforate the airframe. The engine and tail assembly are typical aim points in a tail-chase engagement. Rounds large enough to destroy the engine directly produce M1 (propulsion loss, intact glide). Rounds that damage control surfaces without stopping the engine produce M2 (loss of control, powered drift). Direct structural penetration of the fuselage can produce M3, but 35 mm rounds are small enough that full structural break-up is less common than for missile warheads.

| Parameter | Estimate | Derivation |
|---|---|---|
| P_kill per engagement | 0.75–0.90 | Multiple rounds per burst against slow target; anecdotal UA unit reports |
| Mode weights | M1: 0.55, M2: 0.25, M3: 0.20 | Engine/tail hit dominant in tail-chase; small-calibre rounds unlikely to cause full breakup |
| Max slant range | ~3.5 km | Published Gepard 1A2 spec |
| Altitude envelope | 0–3 km | |

**Expert question:** What fraction of Gepard-intercepted Shaheds show each terminal mode — i.e., do they mostly glide down intact (M1), fly uncontrolled for a while (M2), or break apart (M3)? Video review of intercept engagements would directly calibrate the mode weights for this system.

---

### IRIS-T SLM

**Kill mechanism:** The IRIS-T uses an infrared-homing missile with a blast-fragmentation warhead and proximity fuze that detonates 2–5 m from the target. The warhead blast at this stand-off distance is sufficient to cause structural damage to the airframe. Propulsion loss (M1) can still occur if the blast severs the engine or fuel line. Full break-apart (M3) is more likely than for cannon rounds because the warhead energy is higher.

| Parameter | Estimate | Derivation |
|---|---|---|
| P_kill per engagement | 0.85–0.95 | High single-shot Pk designed for low-speed, low-altitude targets |
| Mode weights | M3: 0.55, M1: 0.30, M2: 0.15 | Proximity blast tends toward structural damage; propulsion loss secondary |
| Max slant range | ~40 km | Published IRIS-T SLM spec |
| Altitude envelope | 0.01–20 km | |

**Expert question:** What does post-engagement tracking show for IRIS-T kills — does the drone typically fragment in the air (M3), glide down (M1), or continue flying erratically (M2)? German or Ukrainian IRIS-T operators would have this data.

---

### Buk-M1 (9M38 missile)

**Kill mechanism:** The Buk fires a large radar-homing missile with a ~70 kg blast-fragmentation warhead and proximity fuze. The warhead is much larger than IRIS-T and designed for fast medium-altitude aircraft. Against a slow, low-flying Shahed, the radar may struggle with the low radar cross-section (RCS), degrading guidance accuracy and P_kill. When a kill is achieved, the large warhead likely causes near-complete structural destruction (M3 dominant).

| Parameter | Estimate | Derivation |
|---|---|---|
| P_kill per engagement | 0.45–0.65 | Designed for larger, faster targets; Shahed low RCS degrades radar guidance |
| Mode weights | M3: 0.60, M1: 0.25, M2: 0.15 | Large warhead → structural destruction; some propulsion-loss glides still possible |
| Max slant range | ~35 km | Published Buk-M1 spec |
| Altitude envelope | 0.03–22 km | Low-altitude performance (below 100 m) is degraded |

**Expert question:** What P_kill has been observed for Buk-M1 engagements against Shaheds in Ukraine? The low RCS and low-altitude flight profile are both challenging for the Buk radar. Engagement logs would give the empirical kill rate.

---

### MANPAD (Stinger, Igla-S, Mistral)

**Kill mechanism:** Man-portable IR-homing missiles follow the heat signature of the Shahed engine in a tail-chase geometry. The small warhead (1–2 kg) typically detonates in or near the engine exhaust, causing propulsion loss. Because the hit is concentrated at the tail, full structural break-apart is uncommon; the more typical outcome is propulsion loss with an intact airframe gliding down (M1). Loss of control (M2) can occur if the hit also damages the tail control surfaces.

| Parameter | Estimate | Derivation |
|---|---|---|
| P_kill per engagement | 0.50–0.70 | Single small warhead; requires tail-chase geometry |
| Mode weights | M1: 0.65, M2: 0.20, M3: 0.15 | Engine/tail hit dominant; small warhead unlikely to cause structural break-up |
| Max slant range | ~5–8 km (system-dependent) | |
| Altitude envelope | 0.01–4.5 km | |

**Expert question:** IR seekers can be confused by solar background, ground heat, or flares. What degradation in P_kill is observed in summer daylight engagements versus night? Are MANPAD operators reporting IR lock difficulties against Shaheds specifically?

---

### NASAMS (AIM-120 AMRAAM-ER)

**Kill mechanism:** Active radar-homing missile with a blast-fragmentation warhead (~23 kg) and proximity fuze. Similar kill mechanism to IRIS-T but with active radar homing (not IR), which is less weather-dependent and works in all lighting conditions. The warhead size is between IRIS-T and Buk-M1.

| Parameter | Estimate | Derivation |
|---|---|---|
| P_kill per engagement | 0.80–0.90 | High single-shot Pk; active radar guidance not limited by IR conditions |
| Mode weights | M3: 0.50, M1: 0.30, M2: 0.20 | Proximity warhead → structural damage dominant |
| Max slant range | ~25 km (AMRAAM) / ~50 km (AMRAAM-ER) | |
| Altitude envelope | 0.03–15 km | |

**Expert question:** AMRAAM was designed for air-to-air engagements against fast jets. Against a slow, low-RCS target like the Shahed, the active seeker may behave differently. What P_kill is observed operationally for NASAMS against Shaheds in Ukraine?

---

### ZSU-23-4 Shilka / ZU-23-2

**Kill mechanism:** 23 mm cannon systems, similar in principle to Gepard but smaller calibre. The ZSU-23-4 has radar fire control; the ZU-23-2 is manually aimed, making P_kill highly operator-dependent. Like the Gepard, cannon hits tend toward propulsion damage (M1) or control loss (M2) rather than full structural break-apart (M3).

| Parameter | Estimate | Derivation |
|---|---|---|
| P_kill per engagement | 0.35–0.55 | Smaller calibre than Gepard; ZU-23-2 manual aim adds variance |
| Mode weights | M1: 0.50, M2: 0.30, M3: 0.20 | Smaller calibre than Gepard; less structural damage per round |
| Max slant range | ~2–2.5 km | Published ZSU-23-4 spec |
| Altitude envelope | 0–1.5 km | |

**Expert question:** What P_kill is observed for ZU-23-2 and ZSU-23-4 engagements against Shaheds in practice? Manual aiming accuracy varies significantly with operator training and target visibility.

---

### Cross-system open questions

**? P_kill varies with range and aspect.** All estimates above assume optimal engagement geometry. P_kill at near-maximum range is substantially lower than at optimal range. A range-degraded P_kill curve (expressed as a lookup table: slant range × aspect angle → P_kill) would require more detailed data but would significantly improve recommendation accuracy near the edges of the engagement envelope.

**? Multi-shot doctrine.** Some systems fire multiple bursts (Gepard, ZSU) or two-missile salvos (IRIS-T, Buk) for high-value targets. Our single-shot P_kill values are for one engagement attempt. If doctrine calls for a salvo, the effective P_kill is approximately `1 - (1 - P_kill_single)²`.

**? Mode weights depend on hit location.** A cannon burst hitting the nose vs the tail produces different terminal outcomes. Mode weights are averages over the typical hit distribution for each weapon's engagement geometry — a tail-chase cannon weapon versus a head-aspect missile will hit very different parts of the airframe.

---

## Priority Summary

The assumptions most likely to produce materially wrong recommendations, in rough priority order:

1. **P_detonate = 1.0** — if ~20% of intercepted Shaheds don't detonate, all casualty scores are overstated by ~20%; revisit with UA air force reporting
2. **P_kill = 0.50** — wrong for every specific system; makes all recommendations system-agnostic; fix with per-system engagement data
3. **Mode weights (40/35/25)** — the physics footprint shape changes dramatically between modes; wrong weights give wrong spatial recommendations; calibrate with intercept video/track analysis
4. **No building sheltering** — 2–5× overestimate in urban areas; fix with OSM building type data (planned for v2)
5. **Glide ratio = 5.0** — controls M1 footprint range linearly; 5.0 vs 7.0 = 40% different impact range; calibrate with recovered glide-path data
6. **Fragmentation lethal radius = 200 m** — the largest single driver of casualty area; may be 2–4× too large without a pre-fragmented warhead liner
7. **TNT equivalent = 30 kg** — depends on explosive fill type; could be 50–75 kg TNTe if a higher-brisance compound is used; affects all blast radii
