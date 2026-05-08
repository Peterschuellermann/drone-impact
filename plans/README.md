# Plans — Feature Backlog

Implementation agent: pick the first `[ ]` plan whose dependencies are all `[x]`, create a branch, and implement it. Mark `[~]` when started, `[x]` when merged.

## Version 1 — Physics Baseline

| Status | ID | Plan | Dependencies |
|---|---|---|---|
| [ ] | F01 | [Project Scaffold](F01-project-scaffold.md) | — |
| [ ] | F02 | [Coordinate Utilities + Trajectory Discretisation](F02-coordinate-utilities.md) | F01 |
| [ ] | F03 | [DEM Module](F03-dem-module.md) | F01 |
| [ ] | F04 | [Physics Engine — Mode M1 Propulsion Loss](F04-physics-m1.md) | F01, F02, F03 |
| [ ] | F05 | [Physics Engine — Mode M2 Loss of Control](F05-physics-m2.md) | F01, F02, F03 |
| [ ] | F06 | [Physics Engine — Mode M3 Break Apart](F06-physics-m3.md) | F01, F02, F03 |
| [ ] | F07 | [Population Data Layer](F07-population-layer.md) | F01 |
| [ ] | F08 | [Infrastructure Data Layer](F08-infrastructure-layer.md) | F01 |
| [ ] | F09 | [Casualty Engine](F09-casualty-engine.md) | F04, F05, F06, F07, F08 |
| [ ] | F10 | [Scoring Engine + Explainability](F10-scoring-engine.md) | F09 |
| [ ] | F11 | [Startup Data Loading + Health Endpoint](F11-startup-health.md) | F03, F07, F08 |
| [ ] | F12 | [Single-Drone REST API](F12-api-single-drone.md) | F10, F11 |
| [ ] | F13 | [Batch REST API + Async Job Management](F13-api-batch.md) | F12 |
| [ ] | F14 | [Performance Benchmarks](F14-performance-benchmarks.md) | F12, F13 |

## Version 2 — Environmental and Engagement Refinement

Planned after v1 is complete. See `/spec/roadmap.md`.

## Version 3 — Manoeuvre Prediction and Data-Driven Model

Planned after v2 is complete. See `/spec/roadmap.md`.

## Version 4 — Dashboard and Defence Planning

Planned after v3 is complete. See `/spec/roadmap.md`.
