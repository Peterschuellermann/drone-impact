# Casualty Model

## Overview

For each simulated impact point, the casualty model computes an **expected number of casualties** by combining:

1. **Blast effect** — overpressure wave causes structural collapse and direct injury
2. **Fragmentation effect** — high-velocity fragments cause lethal injury at distance
3. **Population density** — how many people are exposed at the impact location
4. **Critical infrastructure penalty** — proximity to high-value targets increases effective score

The output is a single scalar: **expected casualties per impact event**, which is then probability-weighted across Monte Carlo samples.

---

## Shahed-136 Warhead Parameters

| Parameter | Value | Note |
|---|---|---|
| Warhead type | Fragmentation / HEAT combination | Recovered unit analysis |
| Warhead mass | ~40–50 kg | Range; use 45 kg as central estimate |
| Explosive fill (TNT equivalent) | ~30 kg TNT | ~65–70 % of warhead mass, typical for this class |
| Casing mass | ~10 kg | Provides fragmentation |
| Fragment count (estimated) | ~2,000–3,000 | Varies by fuze design |
| Fragment mass (mean) | ~3–5 g | Estimated from casing geometry; count × mean ≤ casing mass |

**Implementation note:** These values are estimates from open-source reporting. Expose all warhead parameters as configurable constants so they can be updated as better data becomes available.

---

## Blast Model

### Approach: Hopkinson-Cranz Scaling

The Hopkinson-Cranz (cube-root) scaling law relates blast parameters to TNT equivalent charge weight W (kg) and distance R (m):

```
Z = R / W^(1/3)   [scaled distance, m/kg^(1/3)]
```

For W = 30 kg TNT:
```
W^(1/3) = 3.11 kg^(1/3)
```

Key overpressure thresholds and their casualty implications:

| Overpressure (kPa) | Scaled distance Z (m/kg^(1/3)) | R at W=30 kg | Effect |
|---|---|---|---|
| 690 | 0.5 | 1.6 m | Near-certain death |
| 140 | 1.0 | 3.1 m | Severe lung injury |
| 70 | 1.8 | 5.6 m | Threshold lung injury |
| 35 | 3.2 | 10.0 m | Eardrum rupture, thrown |
| 17 | 6.0 | 18.6 m | Structural window damage |
| 7 | 14 | 43.5 m | Minor structural damage |

*Scaled distance values from Kingery-Bulmash polynomial fit (standard reference in blast analysis).*

### Casualty Probability Function (Blast)

Use a piecewise radial function P_blast(r) for probability of casualty at distance r from impact:

```
P_blast(r) =
  1.0                              if r < R_certain    (= 5 m for 30 kg TNT)
  probit_blast(r)                  if R_certain ≤ r ≤ R_threshold
  0                                if r > R_threshold   (= 50 m for 30 kg TNT)
```

Where `probit_blast(r)` is derived from the Eisenberg (1975) probit function for blast lung injury:

```
Pr = 5 - 5.74 * ln(r / W^(1/3))
P  = Φ(Pr - 5)   [standard normal CDF]
```

**Implementation:** A stepped function with configurable bands:

```
P_blast(r) =
  1.00   if r < 5 m
  0.50   if 5 ≤ r < 15 m
  0.10   if 15 ≤ r < 35 m
  0.01   if 35 ≤ r < 80 m
  0.00   if r ≥ 80 m
```

These thresholds are configurable via `blast_bands` in `config.yaml`. See **Configurable Multi-Band Mechanism** below.

---

## Fragmentation Model

### Gurney Velocity

Fragment initial velocity estimated using the Gurney equation (cylindrical geometry):

```
v_frag = sqrt(2 * E_G) / sqrt(1 + M/(2C))

where:
  sqrt(2 * E_G) ≈ 2,440 m/s  (Gurney constant for TNT)
  M = M_casing = 10 kg
  C = M_explosive = 30 kg
  v_frag = 2,440 / sqrt(1 + 10/60) = 2,440 / 1.08 ≈ 2,260 m/s
```

High-velocity fragments are lethal at significant range.

### Lethal Fragment Range

Fragment kinetic energy drops due to aerodynamic drag as it travels distance r:

```
v(r) = v_frag * exp(-r / (2 * m_frag / (ρ * C_d_frag * A_frag)))
```

For a 4 g fragment with C_d ≈ 1.0, A ≈ 0.5 cm²:

```
E_lethal_threshold ≈ 79 J  (NATO standard for incapacitation)
R_lethal_fragment ≈ 100–400 m  depending on fragment mass and shape
```

Use **R_frag_lethal = 200 m** as the central estimate for v1.

### Casualty Probability Function (Fragmentation)

Fragment density falls off as 1/r² (spherical spreading) but is not uniform — fragments are distributed preferentially in the plane perpendicular to the warhead axis. For a ground-impact event, assume roughly uniform azimuthal distribution.

```
P_frag(r) =
  N_frags * A_person * p_hit_per_frag(r) / (4π r²)

where:
  A_person ≈ 0.5 m²  (presented area)
  p_hit_per_frag(r) = probability a single fragment reaching r is lethal
```

**Simplified radial function for v1:**

```
P_frag(r) =
  1.00   if r < 20 m
  0.30   if 20 ≤ r < 80 m
  0.10   if 80 ≤ r < 200 m
  0.02   if 200 ≤ r < 400 m
  0.00   if r ≥ 400 m
```

---

## Configurable Multi-Band Mechanism

Both blast and fragmentation use a **configurable band system** in `config.yaml`. Each band defines a radius and a casualty probability:

```yaml
blast_bands:
  - {radius_m: 5, probability: 1.00}
  - {radius_m: 15, probability: 0.50}
  - {radius_m: 35, probability: 0.10}
  - {radius_m: 80, probability: 0.01}

frag_bands:
  - {radius_m: 20, probability: 1.00}
  - {radius_m: 80, probability: 0.30}
  - {radius_m: 200, probability: 0.10}
  - {radius_m: 400, probability: 0.02}
```

When bands are configured, the `CasualtyEngine._compute_banded()` method:

1. Collects all unique radii from both band sets
2. Queries cumulative population at each radius via `PopulationIndex.query_batch()`
3. For each annular ring, computes the mid-point distance to determine which band applies
4. Combines blast and fragmentation probabilities via the union formula: `P = 1 - (1-P_blast)(1-P_frag)`
5. Sums `ring_population × P_combined` across all rings
6. Applies infrastructure penalty multiplier

If bands are not configured, the engine falls back to a legacy four-zone model using `blast.lethal_radius_m`, `blast.injury_radius_m`, `fragmentation.lethal_radius_m`, and `fragmentation.danger_radius_m`.

The `CasualtyEngine` also exposes a `population` property providing direct access to the `PopulationIndex` for use by the scoring engine's population pre-scan.

---

## Combined Casualty Probability

At distance r from impact point:

```
P_casualty(r) = 1 - (1 - P_blast(r)) * (1 - P_frag(r))
```

This is the union probability assuming blast and fragmentation are independent events.

The **effective lethal radius** (where P_casualty = 0.5) is approximately **25–40 m** for 30 kg TNT equivalent with fragmentation. The **effective injury radius** (P_casualty = 0.05) is approximately **300–400 m**.

---

## Population Density Data

### Primary Source: Kontur Population Dataset

**Dataset:** Kontur Population Dataset  
**URL:** https://data.humdata.org/dataset/kontur-population-dataset  
**Resolution:** H3 hexagonal grid, resolution 8 (~460 m cells) and resolution 9 (~170 m cells)  
**Update cadence:** Released periodically; use most recent available  
**Coverage:** Global  
**Methodology:** Combines Meta (Facebook) population mobility data, Microsoft building footprints, and census data  
**Ukraine relevance:** Partially accounts for wartime displacement patterns via mobility data  

**Why Kontur over WorldPop:**
- WorldPop uses census-based models that pre-date the 2022 invasion
- Kontur's mobility data partially captures the significant displacement of ~8 million Ukrainians
- H3 indexing allows O(1) population lookups by cell

**Limitation:** No dataset perfectly captures the wartime population distribution. Kontur is the best available public option as of 2024. The implementation should make the population source swappable.

### Supplementary: UNOSAT Population Figures

UNOSAT (UN Satellite Centre) publishes damage and displacement assessments for Ukraine. These can be used to apply **displacement adjustment factors** to Kontur values for heavily damaged areas.

### Data Preparation

Pre-process population data into an **H3 spatial index at resolution 9** (~170 m cells):

```
pop_count[h3_cell] = persons_in_cell
```

For a given impact point, compute expected exposed population by summing over cells within the casualty radius:

```
E[exposed] = Σ_{cells c within R_max} P_casualty(dist(impact, c)) * pop_count[c]
```

Where `R_max = 400 m` (beyond which P_casualty ≈ 0).

For performance, pre-build a lookup: for each cell in the dataset, pre-compute its H3 index. Use H3's `k_ring` function to enumerate all cells within a given radius without a spatial scan.

---

## Critical Infrastructure Scoring

Critical infrastructure proximity adds a **multiplicative penalty** to the casualty score. The rationale: destroying a power plant may cause cascading harm far exceeding the direct blast casualties.

### Infrastructure Categories and Weights

| Category | OSM Tags | Penalty Multiplier |
|---|---|---|
| Power plant / substation | `power=plant`, `power=substation` | 5.0× |
| Hospital / medical | `amenity=hospital`, `amenity=clinic` | 4.0× |
| Water treatment / pumping | `man_made=water_works`, `man_made=pumping_station` | 4.0× |
| Bridge (road/rail) | `bridge=yes` + `highway` or `railway` | 3.0× |
| Railway station / yard | `railway=station`, `railway=yard` | 2.5× |
| Dam | `waterway=dam` | 3.5× |
| Fuel storage | `man_made=storage_tank` + `substance=fuel` | 2.5× |
| School | `amenity=school` | 2.0× |

### Penalty Application

The infrastructure penalty is distance-decayed:

```
infra_penalty(impact_point) = max over all infra objects i of:
  weight_i * max(0, 1 - dist(impact_point, i) / R_infra)

where R_infra = 500 m  (penalty drops to 0 beyond 500 m)
```

The final casualty score for an impact event:

```
score = E[exposed] * (1 + infra_penalty(impact_point))
```

### Infrastructure Data Source

**Source:** OpenStreetMap Ukraine extract  
**Download:** Geofabrik daily extracts — https://download.geofabrik.de/europe/ukraine.html  
**Format:** OSM PBF → extract relevant features → GeoJSON  

Pre-process infrastructure objects into a spatial index (R-tree or H3-based) at startup.

Note: OSM coverage of Ukraine's infrastructure is reasonably complete for major facilities but may miss smaller installations. Cross-reference with public datasets from USAID/UNOSAT where available.

---

## Expected Casualties Calculation (Full)

For a single Monte Carlo sample with impact at point `p`:

```
E[casualties | impact at p] =
    E[exposed_population | p]          # population integration over P_casualty(r)
    * (1 + infra_penalty(p))           # infrastructure multiplier
    * p_detonate                       # probability warhead detonates (= 1.0 in v1)
```

Aggregated across N Monte Carlo samples for evaluation point P_i and mode M_k:

```
E[casualties | mode k, engage at P_i] = (1/N) * Σ_{n=1}^{N} E[casualties | impact at p_n]
```

Total expected casualties if engaging at P_i:

```
E[casualties | engage at P_i] =
    P_kill * Σ_k w_k * E[casualties | mode k, engage at P_i]
  + (1 - P_kill) * E[casualties | drone reaches target]
```

---

## Explainability

For the recommended engagement point, the system should generate a plain-text explanation structured as:

1. **Terrain type at impact zone** (urban/suburban/rural/agricultural — derived from OSM land use)
2. **Population density tier** (high/medium/low/negligible — binned from Kontur value)
3. **Nearest critical infrastructure** (name, type, distance)
4. **Dominant outcome mode** (which of M1/M2/M3 contributes most to expected casualties)
5. **Comparison to worst point** (e.g., "engaging here produces 85% fewer expected casualties than engaging over Mykolaiv city centre")

This is generated programmatically from the data, not by an LLM.

---

## Known Limitations (v1)

| Limitation | Impact | Resolution |
|---|---|---|
| No building sheltering | All population assumed exposed outdoors; overestimates casualties 2–5× in urban areas | Add building-type protection factor in v2 |
| No time-of-day adjustment | Population exposure treated as static; night attacks over residential areas and day attacks over commercial areas not differentiated | Add optional `local_time` input in v2 |
| No fire / secondary effects | Shahed impacts frequently cause fires (major casualty source in residential buildings); not modelled | Low priority for v1; consider for v3 |
| No building collapse model | Blast overpressure can collapse structures and trap occupants; only direct blast injury modelled | Consider for v2 alongside sheltering |
