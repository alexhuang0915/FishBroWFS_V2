# DP4.5 hygiene sweep

## Scope A — .rooignore policy
- **Decision**: Option A (revert). `.rooignore` is restored to HEAD so the outputs tree (including `_dp_evidence`) is fully blocked without special inclusions. This keeps the root filter consistent with the Constitution.

## Scope B — evidence de-tracking
- Removed the accidental tracked artifacts from `outputs/_dp_evidence/root_hygiene/` and `outputs/_dp_evidence/test_artifacts/` via `git rm --cached`; they now live on disk only and are covered by the updated ignore rules.
- Paths now ignored: `outputs/_dp_evidence/root_hygiene/`, `outputs/_dp_evidence/test_artifacts/` (and anything below `outputs/_dp_evidence/` going forward). See `rg_git_status_before.txt`/`rg_git_status_after.txt` for the precise diff snapshots.

## Scope C — evidence naming and duplication notes
- DP4 evidence currently spans two bundles: `outputs/_dp_evidence/phaseDP4_1_4_3_20260116T133519/` (historical) and `outputs/_dp_evidence/phaseDP4_4_deflake_20260116T135041/` (canonical, contains the deduplication work for this phase). We will treat `phaseDP4_4_deflake_20260116T135041` as the canonical DP4 instance; the others remain on disk for auditing but are no longer part of `git status`.
- This sweep introduces `outputs/_dp_evidence/phaseDP4_5_hygiene_20260116T140306/` (this directory) as the official hygiene bundle for DP4.5.

## Tests and verification
- `make check` (see `rg_make_check.txt` for the full log).

## Working-tree confirmation
- Working tree is clean after the hygiene edits; see `SYSTEM_FULL_SNAPSHOT.md` for `git rev-parse HEAD` + the clean `git status --porcelain` message.
