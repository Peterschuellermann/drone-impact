# I03 — Job Store TTL and Eviction

## Problem

The `JobStore` in `api/batch.py` never evicts completed jobs. Every batch request
creates a `BatchJob` that is stored indefinitely, including the full result dict
with all Monte Carlo outputs per drone. Under sustained usage this is an unbounded
memory leak.

## Spec Reference

`spec/architecture.md`, line 184: "Completed jobs expire after 1 hour (TTL).
A background timer or lazy eviction on access is sufficient."

## Proposed Changes

1. Add `job_ttl_s: float = 3600.0` to `JobStore.__init__`.
2. Implement lazy eviction: in `get()` and `create()`, scan for and remove jobs
   where `completed_at is not None and time.time() - completed_at > ttl`.
3. To avoid scanning the entire dict on every call, track a `_last_eviction`
   timestamp and only scan when `time.time() - _last_eviction > 60`.
4. Alternative: use a background `asyncio.Task` started in the lifespan that
   runs every 60 seconds and evicts expired jobs.

## Testing

- Unit test: create a job, set its `completed_at` to the past, verify it's evicted
- Integration test: completed batch job disappears after TTL

## Dependencies

None.
