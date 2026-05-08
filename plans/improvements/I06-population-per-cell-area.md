# I06 — Population Query Per-Cell Area Correction

## Problem

Two related issues in `data/population.py`:

### 1. Single cell area used for all cells

`load_from_file` computes each cell's density using its own area:
`density = pop / h3.cell_area(cell)`. But `query()` reconstructs total population
using a single `_cell_area_km2` from one sample cell:
`total_pop = sum(densities) * _cell_area_km2`.

H3 cell areas vary by ~5% across Ukraine's latitude range (44°–52°N). This
introduces a systematic error in population estimates.

### 2. `_k_for_radius` hexagon diameter approximation

`cell_diameter_m = sqrt(area) * 1000` treats the hex as a square. Hexagonal
geometry gives a different relationship between area and edge-to-edge width.
This can under- or over-estimate the k-ring size needed for a given radius.

## Proposed Changes

### Option A: Store population counts, not density

Change `load_from_file` to store raw population per cell. In `query()`, sum
population directly without needing to multiply by area. This eliminates the
area mismatch entirely.

### Option B: Use per-cell area in query

Store per-cell area alongside density. In `query()`, compute
`sum(density[c] * area[c] for c in neighbourhood)`.

### Option C (minimal): Use average area for the resolution

Replace the sample-cell area with the H3 resolution's average cell area.
This reduces the error from ~5% to ~1% with zero structural change.

### Fix `_k_for_radius`

Use `h3.average_hexagon_edge_length(resolution, unit='m')` to compute the
hex diameter: `diameter = edge_length * sqrt(3)`.

## Recommendation

Option A is simplest and most correct. Store population counts directly;
`query()` returns the sum without any area arithmetic.

## Testing

- Verify population query at high latitude (~52°N) matches low latitude (~44°N)
  for the same density
- Test `_k_for_radius` returns correct k for known radius/resolution combinations

## Dependencies

None.
