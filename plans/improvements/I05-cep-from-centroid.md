# I05 — CEP Measured from Distribution Centroid

## Problem

`compute_cep` in `scoring/ellipse.py` measures distances from the ENU origin (0, 0).
This is the intercept point, not the centroid of the impact distribution. For physics
modes where the debris travels forward (M1 glide, M2 powered flight), the distribution
mean is offset from the origin. The CEP then measures "how far from intercept" rather
than "how dispersed the distribution is."

The standard military definition of CEP measures dispersion from the mean/aim point.

## Current Behaviour

```python
ranges = np.sqrt((enu_points ** 2).sum(axis=1))
```

For M1 at 400 m AGL heading north, the mean impact is ~2000 m north. CEP ≈ 2000 m
(dominated by the offset), masking the actual spread (~400 m).

## Proposed Change

```python
centroid = enu_points.mean(axis=0)
ranges = np.sqrt(((enu_points - centroid) ** 2).sum(axis=1))
```

## Considerations

- The offset from origin is still valuable information — it tells the operator
  "debris will land ~2 km away." Consider adding a separate `mean_range_m` field
  alongside `cep_m` to preserve this.
- If consumers of the API already interpret `cep_m` as "distance from intercept
  point," changing the definition will break their expectations. Document the change
  clearly.

## Testing

- Update `test_cep_50_percent_within_radius` to use centroid-based ranges
- Add test: offset distribution (mean at 1000 m north) should have CEP < 500 m

## Dependencies

None.
