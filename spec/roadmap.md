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
- No UI / dashboard (v2)
- No historical data DB

### Performance targets

- Single drone analysis: < 500 ms
- Batch of 50 drones: < 15 s
- Memory footprint: < 1 GB

---

## Version 2 — Dashboard & Operational Interface

**Goal:** Interactive dashboard for analysts and operators; real-time operational capabilities for live engagements.

### Planned features

**Streamlit analysis dashboard (F15)**
- Input form: drone state (lat/lon/altitude/heading/speed)
- Calls `/analyze/single` and displays all results interactively
- 2D map: trajectory line, evaluation point markers (sized by casualty risk), recommended engagement point, population density heatmap, optional infrastructure layer
- Impact scatter plot: Monte Carlo impact points coloured by mode (M1/M2/M3), CEP confidence ellipses
- Risk profile chart: expected casualties vs. distance along trajectory
- Statistics panel: mode breakdown, casualty estimates, P_kill, engagement score
- GeoJSON export of trajectory + impact points
- 5-minute response cache to avoid duplicate API calls during exploration
- Degrades gracefully if API is unreachable

**Trajectory animation**
- Replay simulated drone flights on map
- Colour-code trajectory by engagement score at each point
- Mark optimal engagement point with annotation

**Real-time integration**
- WebSocket endpoint for live drone track input
- Stream of engagement score updates as new position fixes arrive
- Alert when engagement score crosses threshold

**Multi-drone coordination**
- Handle swarm scenarios: multiple simultaneous drones
- Allocate available interceptors to minimise total expected casualties
- Assignment optimisation (linear assignment or greedy)

---

## Version 3 — Environmental and Engagement Refinement

**Goal:** Improve physical accuracy and operational realism; update dashboard to expose new parameters.

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

**Dashboard updates**
- Wind vector overlay on map (arrows showing wind direction and speed at drone altitude)
- Missile system selector in input form; display system-specific P_kill in statistics panel
- Time-of-day slider with live population density update on map
- Sheltering factor visualization: colour buildings by protection class on infrastructure layer

---

## Version 4 — Manoeuvre Prediction and Data-Driven Model

**Goal:** Remove the straight-line trajectory assumption; predict likely flight paths from historical data; add historical analysis and defence planning to the dashboard.

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

**Launcher position and engagement envelope**
- Add launcher position (lat/lon) and missile system type as optional inputs to the analyze endpoints
- Filter out trajectory evaluation points that are outside the system's max slant range
- Per-system engagement envelopes defined in config (range, altitude floor/ceiling)
- Requires the per-system P_kill and mode weight tables that v3 introduces; the envelope check is only meaningful once the system type is known

**DEM-aware terrain shadowing**
- Check line-of-sight from launcher position to drone at each evaluation point
- Points that are terrain-masked are flagged as unengageable and excluded from the recommendation
- Depends on launcher position input (above)

**Dashboard: historical data views**
- Map view of all historical impact events
- Filter by: date range, region, drone type, intercept status
- Heatmap of impact density
- Timeline of attack waves
- Replay historical drone flights on map with engagement score colour-coding

**Dashboard: defence location planning**
- Input: set of defended assets (locations + priorities)
- Output: recommended placement for air defence systems to maximise coverage of high-risk corridors
- Approach: coverage optimisation over historical trajectory distribution

---

## Open Research Questions

These require investigation before they can be specced into a version:

| Question | Priority | Notes |
|---|---|---|
| What is the actual Shahed glide ratio? | High | Critical for M1 footprint accuracy. Needs aerodynamics data or physical test |
| What fraction of intercepted Shaheds detonate on impact? | High | Affects v3 p_detonate parameter. Source: UA Air Force / OSINT |
| What are the conditional mode probabilities (p_M1, p_M2, p_M3 given hit)? | High | Currently estimated. Needs intercept video analysis or partner data |
| Can trajectory data be obtained from UA defence partners? | High | Blocks v4 data-driven model |
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
