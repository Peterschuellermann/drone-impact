# Inputs and Outputs

## Coordinate System

All coordinates use **WGS84** (EPSG:4326) for input/output. Internal physics simulations use a local **ENU (East-North-Up)** Cartesian frame centred on the engagement point to avoid spherical geometry in hot loops. Conversion to/from WGS84 happens at the simulation boundary.

Altitudes are **metres above mean sea level (MSL)** in the API. The physics engine converts to AGL using a DEM (Digital Elevation Model).

---

## Single-Drone Input

```json
{
  "drone_id": "string (optional, for correlation)",
  "trajectory": {
    "lat": 48.3794,
    "lon": 31.1656,
    "altitude_m": 400,
    "heading_deg": 315.0,
    "speed_m_s": 51.4
  },
  "max_range_m": 250000,
  "evaluation_spacing_m": 500,
  "include_heatmap": false
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `drone_id` | string | No | Caller-assigned identifier, echoed in response |
| `lat` | float | Yes | WGS84 latitude, decimal degrees |
| `lon` | float | Yes | WGS84 longitude, decimal degrees |
| `altitude_m` | float | Yes | Altitude MSL in metres |
| `heading_deg` | float | Yes | True heading, 0–360°, clockwise from north |
| `speed_m_s` | float | Yes | Ground speed in m/s |
| `max_range_m` | int | No | Maximum distance to evaluate along trajectory. Default: 250,000 m (250 km) |
| `evaluation_spacing_m` | int | No | Distance between consecutive evaluation points. Default: 500 m |
| `include_heatmap` | bool | No | If true, include per-cell impact probability GeoJSON in response. Default: false |

### Validation Rules

- `altitude_m` must be > 0 and ≤ 10,000
- `speed_m_s` must be in [20, 300]
- `heading_deg` must be in [0, 360)
- lat/lon must be finite and within plausible geographic bounds
- `evaluation_spacing_m` must be in [100, 5000]

---

## Batch Input

```json
{
  "batch_id": "string (optional)",
  "drones": [ /* array of single-drone input objects */ ],
  "async": true
}
```

| Field | Type | Description |
|---|---|---|
| `batch_id` | string | Optional caller-assigned ID for the batch job |
| `drones` | array | Up to 100 single-drone input objects |
| `async` | bool | If true, return a job ID immediately and process in background. Default: false for ≤ 5 drones, true for > 5 |

---

## Single-Drone Output

```json
{
  "drone_id": "string",
  "computed_at_utc": "2024-03-15T14:22:00Z",
  "recommended_engagement": {
    "point_index": 12,
    "lat": 48.4521,
    "lon": 31.0234,
    "altitude_m": 400,
    "distance_from_current_m": 6000,
    "expected_casualties": 0.031,
    "engagement_score": 0.031,
    "reasoning": "Low population density; debris falls in open field. Engaging later risks overflying Mykolaiv suburbs."
  },
  "trajectory_scores": [
    {
      "point_index": 0,
      "lat": 48.3794,
      "lon": 31.1656,
      "altitude_m": 400,
      "distance_from_current_m": 0,
      "expected_casualties": 0.18,
      "breakdown": {
        "p_kill": 0.50,
        "modes": {
          "propulsion_loss": { "weight": 0.40, "expected_casualties": 0.12, "cep_m": 850 },
          "loss_of_control": { "weight": 0.35, "expected_casualties": 0.25, "cep_m": 2100 },
          "break_apart":     { "weight": 0.25, "expected_casualties": 0.08, "cep_m": 320 }
        },
        "miss_branch_expected_casualties": 1.42
      }
    }
  ],
  "impact_distributions": [
    {
      "point_index": 0,
      "mode": "propulsion_loss",
      "impact_ellipse": {
        "centre_lat": 48.3821,
        "centre_lon": 31.1589,
        "semi_major_m": 1200,
        "semi_minor_m": 400,
        "orientation_deg": 315
      },
      "heatmap_geojson": { /* optional GeoJSON FeatureCollection of probability cells */ }
    }
  ],
  "metadata": {
    "n_trajectory_points": 45,
    "n_monte_carlo_samples": 10000,
    "simulation_time_ms": 284,
    "population_dataset": "kontur-2023-h3-r8",
    "infrastructure_dataset": "osm-ukraine-2024-03"
  }
}
```

### Output Field Descriptions

| Field | Description |
|---|---|
| `recommended_engagement` | The single trajectory point minimising expected casualties |
| `trajectory_scores` | One entry per evaluation point, ordered by distance from current position |
| `expected_casualties` | Expected number of casualties (weighted mean across outcome modes and Monte Carlo samples) |
| `engagement_score` | Alias for `expected_casualties` — the primary optimisation target |
| `breakdown.modes` | Per-mode contribution to the expected casualty count |
| `breakdown.miss_branch_expected_casualties` | Expected casualties if the drone is not intercepted and completes its trajectory |
| `impact_ellipse` | 90 % confidence ellipse for debris impact distribution for this mode |
| `heatmap_geojson` | Optional per-cell impact probability (H3 resolution 9, ~150 m cells). Returned only if `include_heatmap: true` in request |
| `reasoning` | Short human-readable explanation of why this point is recommended (generated from rules, not LLM) |

---

## Batch Output

```json
{
  "batch_id": "string",
  "status": "complete | processing | failed",
  "completed_at_utc": "2024-03-15T14:22:05Z",
  "results": [ /* array of single-drone output objects */ ],
  "errors": [
    { "drone_id": "X", "error": "altitude_m out of range" }
  ]
}
```

For async jobs, the endpoint returns `{ "batch_id": "...", "status": "processing" }` immediately. Poll `GET /batch/{batch_id}` for results.

---

## Units Reference

| Quantity | Unit |
|---|---|
| Distance | Metres |
| Altitude | Metres MSL |
| Speed | m/s |
| Heading / Bearing | Degrees true, 0–360 clockwise from north |
| Probability | Dimensionless [0, 1] |
| Expected casualties | Dimensionless expected count (not necessarily integer) |
| Time | UTC ISO 8601 |

---

## What Is Not an Input (v1)

The following are intentionally excluded from the v1 API:

- **Missile launcher position** — not required; engagement geometry not modelled
- **Missile type** — P_kill is fixed at 0.50
- **Wind / weather** — reserved for v2 (see [roadmap](roadmap.md))
- **Drone type** — fixed as Shahed-136 in v1; will become an input in a future version
