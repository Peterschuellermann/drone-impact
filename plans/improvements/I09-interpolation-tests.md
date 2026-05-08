# I09 — Score Interpolation Test Coverage

## Problem

`ScoringEngine._interpolate_scores` is a static method that fills in engagement scores for unscored trajectory points using `np.interp`. It has zero test coverage. A bug here would silently produce incorrect trajectory scores for the two-pass scoring path.

## Spec Reference

The interpolation is an implementation detail of the two-pass optimisation (B01). It must satisfy:

1. Interpolated values lie between the scores of their nearest scored neighbours.
2. Scored points are returned unchanged.
3. Output length equals input trajectory length.

## Change

**File:** `tests/unit/test_scoring.py`

Add three unit tests calling `ScoringEngine._interpolate_scores` directly with synthetic data:

1. `test_interpolation_preserves_scored_points` — supply a dict of scored points, verify they appear unchanged in the output.
2. `test_interpolation_fills_gaps` — supply a 10-point trajectory with scores at indices 0, 5, 9. Verify indices 1-4 and 6-8 receive interpolated values between their neighbours.
3. `test_interpolation_output_length` — verify output length matches trajectory length for various sizes.

## Dependencies

None.
