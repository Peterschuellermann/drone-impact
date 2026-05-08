# Plans — Feature Backlog

Implementation agent: pick the first `[ ]` plan whose dependencies are all `[x]`, create a branch, and implement it. Mark `[~]` when started, `[x]` when merged.

## 1.0 — Physics Baseline

| Status | ID | Plan | Dependencies |
|---|---|---|---|
| [x] | F01 | [Project Scaffold](F01-project-scaffold.md) | — |
| [x] | F02 | [Coordinate Utilities + Trajectory Discretisation](F02-coordinate-utilities.md) | F01 |
| [x] | F03 | [DEM Module](F03-dem-module.md) | F01 |
| [x] | F04 | [Physics Engine — Mode M1 Propulsion Loss](F04-physics-m1.md) | F01, F02, F03 |
| [x] | F05 | [Physics Engine — Mode M2 Loss of Control](F05-physics-m2.md) | F01, F02, F03 |
| [x] | F06 | [Physics Engine — Mode M3 Break Apart](F06-physics-m3.md) | F01, F02, F03 |
| [x] | F07 | [Population Data Layer](F07-population-layer.md) | F01 |
| [x] | F08 | [Infrastructure Data Layer](F08-infrastructure-layer.md) | F01 |
| [x] | F09 | [Casualty Engine](F09-casualty-engine.md) | F04, F05, F06, F07, F08 |
| [x] | F10 | [Scoring Engine + Explainability](F10-scoring-engine.md) | F09 |
| [x] | F11 | [Startup Data Loading + Health Endpoint](F11-startup-health.md) | F03, F07, F08 |
| [x] | F12 | [Single-Drone REST API](F12-api-single-drone.md) | F10, F11 |
| [x] | F13 | [Batch REST API + Async Job Management](F13-api-batch.md) | F12 |
| [x] | F14 | [Performance Benchmarks](F14-performance-benchmarks.md) | F12, F13 |

## Bugfixes

| Status | ID | Plan | Dependencies |
|---|---|---|---|
| [x] | B01 | [Performance: Vectorise Population and Infrastructure Queries](bugfixes/B01-performance-population-query.md) | — |
| [x] | B02 | [Fix: API Handlers Block the Event Loop](bugfixes/B02-event-loop-blocking.md) | — |

## Improvements (Round 2)

| Status | ID | Plan | Dependencies |
|---|---|---|---|
| [x] | I08 | [M2 Altitude-Dependent Air Density](improvements/I08-m2-altitude-density.md) | — |
| [x] | I09 | [Score Interpolation Test Coverage](improvements/I09-interpolation-tests.md) | — |
| [x] | I10 | [Banded/Two-Zone Casualty Equivalence Test](improvements/I10-casualty-equivalence-test.md) | — |

## 1.1 — Dashboard & Deployment

| Status | ID | Plan | Dependencies |
|---|---|---|---|
| [x] | F15 | [Data Visualization Dashboard](F15-data-visualization-dashboard.md) | F12 |
| [x] | F16 | [Batch Visualization](F16-batch-visualization.md) | F15, F13 |
| [x] | F17 | [Trajectory Animation](F17-trajectory-animation.md) | F15 |
| [x] | F18 | [Docker Compose Deployment](F18-docker-compose.md) | F15 |

## 1.1b — Demo, Safety & Interactivity

| Status | ID | Plan | Dependencies |
|---|---|---|---|
| [x] | F19 | [Demo Scenarios](F19-demo-scenarios.md) | F12, F15 |
| [ ] | F20 | [Safe Intercept Constraint](F20-safe-intercept-constraint.md) | F10 |
| [ ] | F21 | [Fallout Area Visualization](F21-fallout-area-visualization.md) | F15, F20 |

## 1.2 — Environmental and Engagement Refinement

Planned after 1.1 is complete. Includes dashboard updates for new physics features. See `/spec/roadmap.md`.

## 1.3 — Manoeuvre Prediction and Data-Driven Model

Planned after 1.2 is complete. Includes historical data dashboard and defence planning. See `/spec/roadmap.md`.

## 1.4 — Real-Time Operations

Planned after 1.3 is complete. Real-time WebSocket integration and multi-drone coordination. See `/spec/roadmap.md`.
