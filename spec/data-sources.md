# Data Sources

## Overview

This document catalogues the external data sources required for DroneImpact, their availability, format, coverage, and integration notes. Sources are divided into: **population and geography** (required for the casualty model), **historical drone impact data** (required for future ML validation and data-driven modes), and **infrastructure data** (required for scoring).

---

## Population and Geography

### 1. Kontur Population Dataset (PRIMARY — REQUIRED)

| Property | Detail |
|---|---|
| URL | https://data.humdata.org/dataset/kontur-population-dataset |
| Provider | Kontur |
| Format | GeoPackage (.gpkg) with H3 hexagonal cells |
| Resolution | H3 resolution 8 (~460 m cells) or resolution 9 (~170 m cells) |
| Update frequency | Periodic; aim for most recent version at deployment time |
| Coverage | Global |
| Licence | CC BY 4.0 |
| File size (Ukraine) | ~200–400 MB |

**Why this source:** Integrates Facebook/Meta mobility data and Microsoft building footprints on top of census baselines. The mobility signal partially captures wartime population displacement in Ukraine (millions of internal and external refugees). No static census product reflects post-2022 Ukrainian population distribution.

**Integration:**
- Download Ukraine country extract or clip global file to bounding box
- Load into H3 cell lookup: `h3_index → population_per_km²`
- For the casualty integration radius (≤ 400 m), at most ~6–8 H3 resolution-9 cells need to be queried per impact point
- Use H3 `k_ring(cell, radius_cells)` for fast neighbourhood queries

**Known limitations:**
- Meta mobility data has stronger coverage in urban areas; rural population estimates less reliable
- Dataset is not updated in real-time; population changes during active combat not reflected

---

### 2. SRTM Digital Elevation Model (REQUIRED)

| Property | Detail |
|---|---|
| Provider | NASA / USGS |
| Format | GeoTIFF, 1 arc-second (≈30 m at equator) |
| URL | https://earthexplorer.usgs.gov / https://opentopography.org |
| Alternative | Copernicus DEM GLO-30 (same resolution, better void filling) |
| Coverage | Global 60°S–60°N |
| Licence | Public domain |

**Integration:**
- Pre-tile to cover Ukraine + 50 km buffer (approx 44°N–53°N, 22°E–40°E)
- Cache in memory as a 2D array with bilinear interpolation for altitude queries
- Used to: (a) convert MSL altitude to AGL, (b) terminate simulated trajectories at ground contact

**Copernicus DEM GLO-30** is preferred over SRTM where available — it has better void filling and higher accuracy in flat terrain (relevant for southern Ukraine steppe).

---

### 3. WorldPop Ukraine (SECONDARY / VALIDATION)

| Property | Detail |
|---|---|
| URL | https://www.worldpop.org/geodata/listing?id=16 |
| Resolution | 100 m or 1 km raster |
| Year | 2020 (most recent available for Ukraine) |
| Licence | CC BY 4.0 |

Use for cross-validation of Kontur values in key cities. Note that the 2020 vintage predates the invasion and is not suitable as the primary source.

---

## Infrastructure Data

### 4. OpenStreetMap Ukraine Extract (REQUIRED)

| Property | Detail |
|---|---|
| Provider | Geofabrik (OSM mirror) |
| URL | https://download.geofabrik.de/europe/ukraine.html |
| Format | OSM PBF (.osm.pbf) |
| Update frequency | Daily |
| Licence | ODbL 1.0 |
| File size | ~600 MB (full Ukraine) |

**Required feature classes:**
- `power=plant`, `power=substation`, `power=line` — energy infrastructure
- `amenity=hospital`, `amenity=clinic` — medical
- `man_made=water_works`, `man_made=pumping_station` — water
- `waterway=dam` — flood risk
- `bridge=yes` on highways and railways
- `railway=station`, `railway=yard`
- `man_made=storage_tank` with `substance=fuel/oil/gas`
- `amenity=school`, `amenity=university`
- `landuse=military` — military installations (may affect engagement rules)

**Integration:**
- Process PBF with osmium or pyosmium → GeoJSON per feature class
- Build R-tree (shapely + rtree, or STRtree) for fast nearest-neighbour queries
- Index at startup; update weekly via new Geofabrik download

**OSM Ukraine Coverage Notes:**
- Major power stations, substations, and hospitals are well-mapped
- Small rural infrastructure (water pumping stations, small bridges) has variable coverage
- Military installations are partially omitted for security reasons (intentional in OSM policy)
- OSM data may lag real-time damage events by weeks to months

---

### 5. UNOSAT Ukraine Damage Assessments (SUPPLEMENTARY)

| Property | Detail |
|---|---|
| Provider | UNOSAT / UNITAR |
| URL | https://unosat.org/products/?tag=Ukraine |
| Format | GeoJSON, Shapefile |
| Content | Satellite-derived building damage assessments by city |
| Update | Irregular; depends on satellite revisit and analyst capacity |
| Licence | Creative Commons / humanitarian use |

Use to identify areas where OSM infrastructure may be destroyed and population data is stale. Apply damage-adjusted population factors to Kontur values in heavily damaged zones.

---

## Historical Drone Impact Data

This section is critical for future data-driven validation and ML model training. It covers all known public sources of Shahed / Geran-2 impact data.

**Current state:** No single authoritative, machine-readable dataset of Shahed impact locations with pre-impact trajectories exists in the public domain. Impact locations are available from multiple OSINT sources; trajectory data is sparse and inconsistently geolocated.

---

### 6. ACLED — Armed Conflict Location and Event Data (HIGH PRIORITY)

| Property | Detail |
|---|---|
| URL | https://acleddata.com |
| Format | CSV / API |
| Coverage | Ukraine from 2022 |
| Relevant event types | `Air/Drone Strike`, `Remote Explosive/Landmine/IED` |
| Fields available | Date, latitude, longitude, event description, fatalities |
| Trajectory data | Not available |
| Licence | Free for non-commercial use; registration required |
| Update frequency | Weekly |

ACLED is the most structured and consistently updated source. It provides geolocated impact events but no pre-impact trajectory. Useful for: geographic distribution of impacts, temporal clustering, and casualty validation.

**Integration approach:** Download via ACLED API, filter to Ukraine drone events, store in PostGIS. Use as ground truth for casualty model validation.

---

### 7. Ukraine Front Line Monitoring / Deepstate Map (HIGH PRIORITY)

| Property | Detail |
|---|---|
| URL | https://deepstatemap.live |
| Content | Geolocated events including air strikes, drone impacts |
| Format | Web app (unofficial API / scraping required) |
| Trajectory data | Partially — some flight path reconstructions posted |
| Update frequency | Near-real-time |

The Deepstate Map is a Ukrainian-maintained OSINT aggregator with higher temporal resolution than ACLED. Some events include community-sourced trajectory reconstructions. Legal/ToS review required before automated scraping.

---

### 8. Liveuamap (MEDIUM PRIORITY)

| Property | Detail |
|---|---|
| URL | https://liveuamap.com |
| Content | Crowdsourced geolocated events, including drone sightings and impacts |
| Format | Web app; no public API |
| Trajectory data | Drone sighting sequences allow partial reconstruction |
| Notes | High noise; community-verified events preferred |

Drone sighting sequences (e.g., "spotted at A, then B, then impact at C") can be used to reconstruct partial trajectories for historical events. This requires significant data cleaning.

---

### 9. UA Air Force Official Reports (HIGH PRIORITY)

| Property | Detail |
|---|---|
| Provider | Ukrainian Air Force (Повітряні Сили ЗС України) |
| URL | Official Telegram channels, Ukrainian MoD press releases |
| Content | Nightly intercept reports: number launched, number intercepted, regions of activity |
| Format | Unstructured text (Telegram posts) |
| Trajectory data | Occasionally mentions launch origin and target region |
| Notes | Authoritative for intercept statistics; limited geospatial precision |

Extract via Telegram API or manual compilation. Useful for: intercept rate validation (ground truth for P_kill estimates), regional attack pattern analysis.

---

### 10. Bellingcat / OSINT Community Investigations (SUPPLEMENTARY)

| Property | Detail |
|---|---|
| URL | https://www.bellingcat.com |
| Content | Individual investigated incidents with precise geolocation |
| Format | Articles, GeoJSON published per investigation |
| Trajectory data | Occasionally reconstructed from video/witness accounts |
| Volume | Low (tens of incidents, not thousands) |

High-quality, precision-geolocated data. Suitable for model validation against specific known events.

---

### 11. FIRMS / NASA VIIRS Fire Data (SUPPLEMENTARY)

| Property | Detail |
|---|---|
| URL | https://firms.modaps.eosdis.nasa.gov |
| Content | Satellite-detected fire events |
| Format | CSV / GeoJSON via API |
| Use case | Drone impacts occasionally start fires detectable from orbit |
| Trajectory data | None |

Cross-reference fire events with ACLED air strike events to validate impact location precision.

---

## Data Freshness and Update Policy

| Dataset | Suggested update frequency | Method |
|---|---|---|
| Kontur population | Quarterly (or on new release) | Manual download |
| SRTM / Copernicus DEM | Once (rarely changes) | One-time download |
| OSM Ukraine extract | Weekly | Geofabrik daily delta or full re-download |
| ACLED events | Weekly | ACLED API |
| UA Air Force reports | Daily | Telegram channel monitor (future) |
| UNOSAT damage | On new publication | Manual |

---

## Data Pipeline Summary

```
[Kontur GPKG] ──────────────────────────┐
[SRTM/Copernicus GeoTIFF] ──────────────┤
[OSM PBF] ──→ [feature extraction] ─────┤──→ [Preprocess] ──→ [In-memory indices]
[ACLED CSV] ──→ [PostGIS impact DB] ─────┘                        ↓
                                                            [Simulation engine]
```

Preprocessing should be a separate offline step that produces serialised, indexed data products (H3-keyed population arrays, R-tree infrastructure index, DEM array). The simulation engine loads these at startup and does not query raw source files at runtime.

---

## Trajectory Data Gap

The most significant data gap is **trajectory data for historical Shahed impacts**. Most available data provides only:
- Impact location
- Approximate time
- Whether intercepted

Pre-impact trajectory data is rarely available in the public domain. Exceptions:
- Some intercepts are filmed from multiple angles and can be triangulated
- Some tracking radars have leaked positional data
- Flight reconstruction from sequential civilian sightings

For the v1 physics-only model, this gap is not blocking. For the future data-driven model, this data gap must be addressed. Potential approaches:
1. Partner with Ukrainian defence organisations for classified track data
2. Reconstruct trajectories backward from known impact points using the physics model (reverse simulation)
3. Use satellite imagery time-series to detect launch sites and infer launch vectors
