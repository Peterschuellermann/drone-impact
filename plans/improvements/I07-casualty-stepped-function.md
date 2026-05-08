# I07 — Casualty Stepped Probability Function

## Problem

The current casualty model uses two radial zones per effect (blast: lethal + injury;
fragmentation: lethal + danger). The spec defines finer-grained stepped functions
with 4–5 radial bands per effect.

## Spec Reference

`spec/casualty-model.md`, lines 78–88 and 141–149:

**Blast:**
```
P_blast(r) =
  1.00   if r < 5 m
  0.50   if 5 ≤ r < 15 m
  0.10   if 15 ≤ r < 35 m
  0.01   if 35 ≤ r < 80 m
  0.00   if r ≥ 80 m
```

**Fragmentation:**
```
P_frag(r) =
  1.00   if r < 20 m
  0.30   if 20 ≤ r < 80 m
  0.10   if 80 ≤ r < 200 m
  0.02   if 200 ≤ r < 400 m
  0.00   if r ≥ 400 m
```

## Current Behaviour

Only two zones per effect. The current bugfix uses the union formula to combine
blast and frag correctly, but with only 4 zones total instead of the 8+ that the
spec describes.

## Proposed Changes

1. Define blast and frag stepped functions as configurable lists of
   `(radius_m, probability)` tuples in `config.yaml`.
2. For each impact point, query population at each band boundary radius.
3. Apply the combined probability `1 - (1-P_blast(r)) * (1-P_frag(r))` per band.
4. Sum across bands.

## Config Structure

```yaml
casualty:
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

## Performance Impact

More population queries per impact point (up to 8 unique radii instead of 4).
Since population query is O(k²) in H3 ring size, the cost increase is moderate.
Profile before and after.

## Testing

- Verify casualty output is strictly less than the two-zone model for the same
  population (finer bands reduce the average probability)
- Verify with uniform population: output matches hand-computed values

## Dependencies

None. Extends the union-formula fix from the current bugfix.
