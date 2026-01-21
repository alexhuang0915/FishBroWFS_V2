# Explain SSOT Report

## What Explain SSOT is / is not
- Explain SSOT surfaces the canonical reason why a job ended in its terminal state without adding new enforcement; it reuses the supervisor DB and the policy_check artifact as the single source of truth.
- Explain SSOT is read-only and always returns URLs to pre-existing artifacts or logs; it never writes policy logic or enforces new actions.

## Taxonomy table
| Reason | Decision Layer | Human Tag | Recoverable | Action Hint |
| --- | --- | --- | --- | --- |
| Policy preflight rejection | POLICY | VIOLATION | true | Adjust parameters to allowed values and resubmit. |
| Policy postflight failure | POLICY | VIOLATION | true | Adjust parameters to allowed values and resubmit. |
| Policy success with PASS | POLICY | UNKNOWN | false | No action required; consider re-running if audit evidence is required. |
| Input malformed / missing data | INPUT | MALFORMED | true | Fix missing/invalid fields and resubmit. |
| Artifact corruption / missing outputs | ARTIFACT | CORRUPTED | true | Re-run upstream job or inspect artifacts; ensure required outputs exist. |
| System infra failure (handler exception) | SYSTEM | INFRA_FAILURE | true | Retry later; if persistent, contact system owner. |
| Governance freeze (season/state) | GOVERNANCE | FROZEN | false | Wait until governance window opens (e.g. unfreeze) then resubmit. |
| Unknown success w/out policy evidence | UNKNOWN | UNKNOWN | false | No action required; consider re-running if audit evidence is required. |

## Caching behavior
- Explain responses are memoized per job using a 2-second TTL keyed by `job_id`, `state`, and `updated_at`; any state transition busts the cache automatically.
- Cache metadata is emitted in `debug.cache` so callers can see hits, misses, and the remaining TTL in a deterministic way.

## Tests performed
- `pytest -q tests/control -q` → `356 passed, 7 skipped, 6 xfailed in 26.70s`.
- `make check` → `1558 passed, 49 skipped, 3 deselected, 11 xfailed in 39.13s` (includes hardening and product suites).
