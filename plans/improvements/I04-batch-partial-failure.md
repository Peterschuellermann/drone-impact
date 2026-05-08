# I04 — Batch Partial Failure Status

## Problem

`_execute_batch` catches all exceptions per drone and appends them to `errors`,
but always returns `status: "complete"` — even if every single drone failed.
A client receiving `{"status": "complete", "results": [], "errors": [50 errors]}`
may interpret this as success.

## Proposed Changes

1. After processing all drones, set status based on results:
   - `"complete"` — all drones succeeded (errors list empty)
   - `"partial"` — some drones succeeded, some failed
   - `"failed"` — all drones failed (results list empty)
2. Log individual drone exceptions with tracebacks (currently only `str(exc)` is
   captured, losing the stack trace).
3. Update the API spec to document the three status values.

## Testing

- Test: batch with one invalid drone (out-of-bounds coords) returns `"partial"`
- Test: batch where all drones fail returns `"failed"`
- Test: fully successful batch returns `"complete"`

## Dependencies

None.
