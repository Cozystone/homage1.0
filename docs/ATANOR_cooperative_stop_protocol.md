# ATANOR Cooperative Stop Protocol

Status: future-safe protocol utility, not wired into the stopped 24h runner.

The standalone 24h runner `run_24h_candidate_20260621_195246.py` had
`NO_GRACEFUL_STOP_SUPPORT`. The API stop endpoint controlled a different
in-process daemon singleton, so the standalone process did not receive the API
request. The run was therefore closed by user-approved controlled process
termination and external partial finalization.

Future standalone runners should use a shared stop marker path:

```text
data/audits/24h_candidate_run/stop_requests/<run_id>.stop.json
```

The marker should contain:

- `run_id`
- `reason`
- `requested_at`
- `requested_by`
- optional `metadata`

Runner requirements:

1. Poll the marker between batches or every few seconds.
2. On marker detection, set `stop_reason=user_stop_requested`.
3. Flush candidate-store writers.
4. Write a native final report.
5. Clear or archive the consumed marker.
6. Do not mutate production or Local Brain during stop handling.

API requirements:

1. If an in-process daemon is active, call its native stop method.
2. If a standalone run is detected, write the stop marker instead of assuming the
   API singleton controls that process.
3. Report whether the stop is in-process or marker-based.

Current implementation:

- `packages/runtime_control/stop_marker.py` provides marker create/read/check
  and clear functions.
- It does not kill processes.
- It does not mutate stores.
- It is not yet wired into `packages/cloud_brain` because those files are
  currently mixed with unrelated work.
