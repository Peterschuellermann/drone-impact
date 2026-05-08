# Roadmap

## Version 1 — Physics Baseline (Current Spec)

**Goal:** Working physics-based engagement advisor for straight-line Shahed trajectories.

### Included

- Single state-vector input (lat/lon/altitude/heading/speed)
- Straight-line trajectory assumption; no manoeuvre prediction
- Monte Carlo physics simulation for three intercept modes (M1 propulsion loss, M2 loss of control, M3 break apart)
- Fixed P_kill = 0.50
- Warhead blast + fragmentation casualty model (Shahed-136 parameters)
- Population scoring via Kontur dataset
- Critical infrastructure scoring via OSM
- Scored trajectory list + recommended engagement point (argmin expected casualties)
- Explainability output (structured rule-based rationale)
- Single drone + batch API (up to 50 drones)
- Country-agnostic data layer (Ukraine pre-loaded)
- No wind/weather
- No UI / dashboard
- No historical data DB

### Performance targets

- Single drone analysis: < 500 ms
- Batch of 50 drones: < 15 s
- Memory footprint: < 1 GB

---

## Version 2 — Environmental and Engagement Refinement

**Goal:** Improve physical accuracy and operational realism.

### Planned features

**Wind and weather integration**
- Add wind vector (u, v components at altitude) as optional input
- Wind affects all three terminal trajectory modes (glide path, erratic drift, fragment range)
- Data source: ECMWF ERA5 reanalysis (historical) + NWP forecast feed (operational)
- v1 simulations are run without wind and the result is deterministic → stochastic; wind adds a systematic offset to impact distributions

**Warhead detonation probability**
- Add `p_detonate` parameter (default 0.85 — estimate based on intercept reports)
- Significant fraction of intercepted Shaheds have reportedly not detonated; this currently overstates casualty risk
- Requires literature/OSINT research to calibrate

**Variable P_kill**
- Add missile type as optional input: `"missile_type": "gepard" | "iris_t" | "buk_m1" | "manpad" | ...`
- P_kill varies by system, slant range, and aspect angle
- Lookup table per system from declassified or open-source performance data

**Launcher position as input**
- Engagement geometry check: verify that the drone at evaluation point P_i is within the missile system's engagement envelope before scoring
- Filter out evaluation points that are out of range

**DEM-aware terrain shadowing**
- Check line-of-sight from launcher to drone at each evaluation point
- Points that are terrain-masked are flagged as unengageable

**Building sheltering factor**
- Add building-type sheltering model to casualty calculation
- Concrete structures reduce blast lethality by ~80%; wooden structures provide significant fragmentation protection
- Data source: OSM building type tags (`building=residential`, `building=apartments`, etc.)
- Multiply exposed population by a protection factor per building class
- Current model (all population exposed outdoors) overestimates casualties 2–5× in urban areas

**Time-of-day population adjustment**
- Add optional `local_time` input to adjust population exposure
- Residential areas are denser at night; commercial/industrial areas during the day
- Apply day/night weighting factors derived from land-use classification (OSM)
- Most Shahed attacks occur at night — this significantly affects which areas have higher exposure

**Improved atmosphere model**
- Replace exponential approximation with ISA standard atmosphere table
- Add temperature/pressure variation with altitude for accurate air density

---

## Version 3 — Manoeuvre Prediction and Data-Driven Model

**Goal:** Remove the straight-line trajectory assumption; predict likely flight paths from historical data.

### Planned features

**Historical impact database**
- Ingest ACLED, UA Air Force reports, OSINT sources into PostGIS
- Store: impact location, timestamp, reported trajectory (where available), intercept status
- Schema supports: partial trajectories, confidence levels, source citations

**Trajectory reconstruction pipeline**
- Backward simulation from known impact points using v1 physics (reverse Monte Carlo)
- Yields plausible launch vectors and in-flight positions for events without tracked trajectories
- Validates v1 physics model against known outcomes

**Data-driven waypoint prediction**
- Learn typical Shahed approach corridors from historical data
- Model: given current position and heading, what is the probability distribution over future waypoints?
- Approach: kernel density estimation over historical trajectories (non-parametric, interpretable) as a first step; upgrade to learned models if sufficient data

**Manoeuvre-aware scoring**
- Instead of a single trajectory vector, accept a probability distribution over future paths
- For each candidate path, run the v1 physics simulation
- Weight path scores by path probability
- Output: uncertainty band on the engagement score reflecting trajectory uncertainty

**Path prediction API**
- New endpoint: `POST /predict/trajectory`
- Input: current state vector
- Output: set of candidate trajectories with probabilities

---

## Version 4 — Dashboard and Defence Planning

**Goal:** Visual interface for operators and analysts; shift from single-drone advisory to systemic defence planning.

### Planned features

**Historical data dashboard**
- Map view of all historical impact events
- Filter by: date range, region, drone type, intercept status
- Heatmap of impact density
- Timeline of attack waves

**Trajectory playback**
- Replay historical or simulated drone flights on map
- Colour-code trajectory by engagement score at each point
- Mark optimal engagement point with annotation

**Defence location planning module**
- Input: set of defended assets (locations + priorities)
- Output: recommended placement for air defence systems to maximise coverage of high-risk corridors
- Approach: coverage optimisation over historical trajectory distribution

**Real-time integration**
- WebSocket endpoint for live drone track input
- Stream of engagement score updates as new position fixes arrive
- Alert when engagement score crosses threshold

**Multi-drone coordination**
- Handle swarm scenarios: multiple simultaneous drones
- Allocate available interceptors to minimise total expected casualties
- Assignment optimisation (linear assignment or greedy)

---

## Open Research Questions

These require investigation before they can be specced into a version:

| Question | Priority | Notes |
|---|---|---|
| What is the actual Shahed glide ratio? | High | Critical for M1 footprint accuracy. Needs aerodynamics data or physical test |
| What fraction of intercepted Shaheds detonate on impact? | High | Affects v2 p_detonate parameter. Source: UA Air Force / OSINT |
| What are the conditional mode probabilities (p_M1, p_M2, p_M3 given hit)? | High | Currently estimated. Needs intercept video analysis or partner data |
| Can trajectory data be obtained from UA defence partners? | High | Blocks v3 data-driven model |
| Does Shahed use terrain-following? | Medium | If yes, altitude is not constant — changes v1 trajectory model |
| What is the Shahed-136 warhead fragmentation pattern? | Medium | Currently using generic estimates; unit-specific data would improve accuracy |
| How much has wartime displacement shifted Ukrainian population? | Medium | Affects casualty model accuracy; Kontur partially accounts for it |
| Are there other loitering munition types in the theatre? | Low | Scope expansion beyond Shahed-136 |

---

## What Stays Constant Across Versions

The following design decisions are intentional and should not be revisited without strong reason:

- **API contract stability:** `POST /analyze/single` and `POST /analyze/batch` JSON schemas are frozen; new versions add new endpoints rather than changing existing ones
- **Monte Carlo approach:** The probabilistic sampling architecture scales well and is extensible; do not replace with closed-form approximations even if available
- **Physics parameters are configurable:** All airframe and warhead parameters live in config, not code
- **Explainability is non-negotiable:** Every recommendation must have a structured, data-derived rationale
- **Country-agnostic data layer:** New countries = new data files, not new code
