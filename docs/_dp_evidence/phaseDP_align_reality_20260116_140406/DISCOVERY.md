# Discovery Notes

## Command Logs

1. `rg -n "DATA_PREPARE|data prepare|prepare_dataset|dataset_prepare|build_dataset|prepare.*dataset" src scripts tests` — surfaced UI hooks (`gui/services/data_prepare_service.py`, `gui/widgets/data_prepare_panel.py`) and the core handler path (`src/control/supervisor/handlers/build_data.py`). ([outputs/_dp_evidence/phaseDP_align_reality_20260116_140406/rg_outputs/rg1_prepare_entrypoints.txt](rg_outputs/rg1_prepare_entrypoints.txt))
2. `rg -n "JobType|RUN_.*PREPARE|RUN_.*DATA|submit\(|dispatch\(|handler" src/control` — confirmed `BuildDataHandler` is registered as a supervised job type. ([outputs/_dp_evidence/phaseDP_align_reality_20260116_140406/rg_outputs/rg2_job_types.txt](rg_outputs/rg2_job_types.txt))
3. `rg -n "FishBroData/raw|FishBroData|FISHBRO_DATA|raw_path|raw_file|dataset_path" src scripts tests` — located `prepare_orchestration` and other modules tracing `FishBroData/raw` as the canonical raw directory. ([outputs/_dp_evidence/phaseDP_align_reality_20260116_140406/rg_outputs/rg3_raw_paths.txt](rg_outputs/rg3_raw_paths.txt))
4. `rg -n "timeframe|timezone|session|calendar|trading hours|exchange|symbol" src` — enumerated time/session handling in registries and `core/resampler`. ([outputs/_dp_evidence/phaseDP_align_reality_20260116_140406/rg_outputs/rg4_time_config.txt](rg_outputs/rg4_time_config.txt))
5. `rg -n "prepared|outputs/datasets|datasets/|dataset_manifest|manifest.json|fingerprint|sha256|inputs_fingerprint" src scripts tests` — traced shared manifests, bars/features artifacts, and fingerprint writing. ([outputs/_dp_evidence/phaseDP_align_reality_20260116_140406/rg_outputs/rg5_prepared_manifest.txt](rg_outputs/rg5_prepared_manifest.txt))
6. `rg -n "write_.*manifest|write_.*fingerprint|artifact.*manifest|artifact.*fingerprint" src` — located the shared manifest/fingerprint writers in `control/shared_build.py`/`control/shared_manifest.py`. ([outputs/_dp_evidence/phaseDP_align_reality_20260116_140406/rg_outputs/rg6_manifest_writers.txt](rg_outputs/rg6_manifest_writers.txt))
7. `rg -n "DatasetLoader|load_dataset|open_dataset|get_dataset|resolve_dataset|dataset_id" src` — pulled the feature resolver, registry, and GUI worker code that resolve dataset IDs and load prepared features. ([outputs/_dp_evidence/phaseDP_align_reality_20260116_140406/rg_outputs/rg7_loader.txt](rg_outputs/rg7_loader.txt))
8. `rg -n "prepared|manifest.json|fingerprint|index|registry" src` — confirmed `shared_manifest`, fingerprint index helpers, and `config.registry` models define the prepared artifacts. ([outputs/_dp_evidence/phaseDP_align_reality_20260116_140406/rg_outputs/rg8_manifest_registry.txt](rg_outputs/rg8_manifest_registry.txt))
9. `rg -n "policy_check|policy_enforcement|PolicyEnforcement|reject|REJECTED" src/control src/gui` — captured pre/post-flight gate enforcement machinery. ([outputs/_dp_evidence/phaseDP_align_reality_20260116_140406/rg_outputs/rg9_policy_hooks.txt](rg_outputs/rg9_policy_hooks.txt))
10. `rg -n "/api/v1/.*explain|get_job_explain|ExplainAdapter|JobReason" src` — tracked the explain service that surfaces policy/job artifacts for clients. ([outputs/_dp_evidence/phaseDP_align_reality_20260116_140406/rg_outputs/rg10_explain.txt](rg_outputs/rg10_explain.txt))
11. `rg -n "GateSummary|Policy Enforcement" src/gui/services tests/gui` — surfaced the gate summary UI that references policy check artifacts. ([outputs/_dp_evidence/phaseDP_align_reality_20260116_140406/rg_outputs/rg11_gate_summary.txt](rg_outputs/rg11_gate_summary.txt))

## Evidence Excerpts

### 1. Data Prepare entrypoint (`src/control/supervisor/handlers/build_data.py`, lines 14-125)
```python
class BuildDataHandler(BaseJobHandler):
    """BUILD_DATA handler for preparing data (bars and features)."""
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate BUILD_DATA parameters."""
        # Required: dataset_id
        if "dataset_id" not in params:
            raise ValueError("dataset_id is required")
        
        if not isinstance(params["dataset_id"], str):
            raise ValueError("dataset_id must be a string")
        
        # Validate timeframe_min if provided
        if "timeframe_min" in params:
            timeframe = params["timeframe_min"]
            if not isinstance(timeframe, int):
                raise ValueError("timeframe_min must be an integer")
            if timeframe <= 0:
                raise ValueError("timeframe_min must be positive")
        
        # Validate force_rebuild if provided
        if "force_rebuild" in params:
            if not isinstance(params["force_rebuild"], bool):
                raise ValueError("force_rebuild must be a boolean")
        
        # Validate mode if provided
        if "mode" in params:
            mode = params["mode"]
            if mode not in ["BARS_ONLY", "FEATURES_ONLY", "FULL"]:
                raise ValueError("mode must be one of: 'BARS_ONLY', 'FEATURES_ONLY', 'FULL'")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute BUILD_DATA job."""
        dataset_id = params["dataset_id"]
        timeframe_min = params.get("timeframe_min", 60)
        force_rebuild = params.get("force_rebuild", False)
        mode = params.get("mode", "FULL")
        
        # Check for abort before starting
        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "BUILD_DATA",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "dataset_id": dataset_id,
                "timeframe_min": timeframe_min
            }
        
        # Try to use the legacy prepare_with_data2_enforcement function
        try:
            return self._execute_via_function(params, context)
        except ImportError as e:
            logger.warning(f"Failed to import prepare_with_data2_enforcement: {e}")
            # Fallback to CLI invocation
            return self._execute_via_cli(params, context)
```
*Note: proves `BUILD_DATA` is the canonical prepare handler, validating dataset+timeframe inputs before invoking orchestration or the CLI fallback.*

### 2. Prepare output writer (`src/control/shared_build.py`, lines 230-289)
```python
    # 7. 儲存指紋索引（如果要求）
    if save_fingerprint:
        write_fingerprint_index(new_index, index_path)
    
    # 8. 建立 shared manifest（包含 bars_manifest_sha256 和 features_manifest_sha256）
    manifest_data = _build_manifest_data(
        season=season,
        dataset_id=dataset_id,
        txt_path=txt_path,
        old_index=old_index,
        new_index=new_index,
        diff=diff,
        mode=mode,
        generated_at_utc=generated_at_utc,
        bars_manifest_sha256=bars_manifest_sha256,
        features_manifest_sha256=features_manifest_sha256,
    )
    
    # 9. 寫入 shared manifest（atomic + self hash）
    manifest_path = _shared_manifest_path(season, dataset_id, outputs_root)
    final_manifest = write_shared_manifest(manifest_data, manifest_path)
    
    # 10. 建立 build report
    report = {
        "success": True,
        "mode": mode,
        "season": season,
        "dataset_id": dataset_id,
        "diff": diff,
        "fingerprint_saved": save_fingerprint,
        "fingerprint_path": str(index_path) if save_fingerprint else None,
        "manifest_path": str(manifest_path),
        "manifest_sha256": final_manifest.get("manifest_sha256"),
        "build_bars": build_bars,
        "build_features": build_features,
    }
```
*Note: proves the shared build path writes atomic fingerprint indexes, builds canonical manifests, and records manifest hashes/report metadata for prepared outputs.*

### 3. Dataset Loader (`src/control/feature_resolver.py`, lines 59-163)
```python
def resolve_features(
    *,
    season: str,
    dataset_id: str,
    requirements: StrategyFeatureRequirements,
    outputs_root: Path = Path("outputs"),
    allow_build: bool = False,
    build_ctx: Optional[BuildContext] = None,
) -> Tuple[FeatureBundle, bool]:
    """Ensure required features exist in shared cache and load them."""
    if not season:
        raise ValueError("season 不能為空")
    if not dataset_id:
        raise ValueError("dataset_id 不能為空")
    manifest_path = features_manifest_path(outputs_root, season, dataset_id)
    if not manifest_path.exists():
        missing_all = [(ref.name, ref.timeframe_min) for ref in requirements.required]
        return _handle_missing_features(
            season=season,
            dataset_id=dataset_id,
            missing=missing_all,
            allow_build=allow_build,
            build_ctx=build_ctx,
            outputs_root=outputs_root,
            requirements=requirements,
        )
    manifest = load_features_manifest(manifest_path)
    _validate_manifest_contracts(manifest)
    missing = _check_missing_features(manifest, requirements)
    if missing:
        return _handle_missing_features(
            season=season,
            dataset_id=dataset_id,
            missing=missing,
            allow_build=allow_build,
            build_ctx=build_ctx,
            outputs_root=outputs_root,
            requirements=requirements,
        )
    return _load_feature_bundle(
        season=season,
        dataset_id=dataset_id,
        requirements=requirements,
        manifest=manifest,
        outputs_root=outputs_root,
    )
```
*Note: proves the loader exclusively reads `outputs/shared/{season}/{dataset_id}/features`, respects manifest contracts, and auto-builds missing bundles via `build_shared` when governance allows.*

### 4. Dataset registry model (`src/config/registry/datasets.py`, lines 45-180)
```python
class DatasetSpec(BaseModel):
    """Specification for a single dataset."""
    id: str = Field(...)
    instrument_id: str = Field(...)
    timeframe: int = Field(...)
    date_range: str = Field(...)
    storage_type: StorageType = Field(...)
    uri: str = Field(...)
    timezone: str = Field(...)
    calendar: CalendarType = Field(...)
    description: Optional[str] = Field(None)
    bar_count: Optional[int] = Field(None)
    size_mb: Optional[float] = Field(None)
    checksum: Optional[str] = Field(None)
    model_config = ConfigDict(frozen=True)
    @field_validator('uri')
    def validate_uri_template(cls, v: str) -> str:
        if '{season}' not in v:
            raise ValueError("URI must contain {season} placeholder for season substitution")
        return v

class DatasetRegistry(BaseModel):
    version: str = Field(...)
    datasets: List[DatasetSpec] = Field(...)
    default: str = Field(...)
    @field_validator('datasets')
    def validate_datasets(cls, v: List[DatasetSpec]) -> List[DatasetSpec]:
        if not v:
            raise ValueError("datasets cannot be empty")
        ids = [ds.id for ds in v]
        if len(ids) != len(set(ids)):
            duplicates = [id for id in ids if ids.count(id) > 1]
            raise ValueError(f"Duplicate dataset IDs: {duplicates}")
        return v
```
*Note: proves dataset metadata (id, timeframe, timezone, URI) is centralized via a typed registry consumed by CLI/GUI layers.*

### 5. Policy hook (`src/control/policy_enforcement.py`, lines 75-190)
```python
def evaluate_preflight(spec: JobSpec) -> PolicyResult:
    if spec.job_type in {JobType.RUN_RESEARCH_V2, JobType.RUN_RESEARCH_WFS}:
        season = _extract_param(spec, "season")
        if not season:
            return _forbidden(...)
        timeframe = _extract_param(spec, "timeframe")
        if not timeframe:
            return _forbidden(...)
    return _allowed("preflight")

def evaluate_postflight(job_id: str, result: Dict[str, Any]) -> PolicyResult:
    outputs_root = get_outputs_root()
    job_dir = outputs_root / "jobs" / job_id
    declared = result.get("output_files", [])
    if declared:
        if not job_dir.exists():
            return _forbidden(...)
        missing = []
        for rel in declared:
            candidate = (job_dir / Path(rel)).resolve()
            try:
                candidate.relative_to(job_dir.resolve())
            except Exception:
                return _forbidden(...)
            if not candidate.exists():
                missing.append(str(rel))
        if missing:
            return _forbidden(...)
    return _allowed("postflight")
```
*Note: proves both preflight (season/timeframe presence) and postflight (artifact existence) gates write canonical `policy_check.json` artifacts.*

### 6. Raw data resolver (`src/control/prepare_orchestration.py`, lines 175-207)
```python
def _find_txt_path_for_feed(feed_id: str) -> Optional[Path]:
    workspace_root = Path(__file__).parent.parent.parent.parent
    raw_dir = workspace_root / "FishBroData" / "raw"
    if not raw_dir.exists():
        return None
    patterns = [
        f"{feed_id} HOT-Minute-Trade.txt",
        f"{feed_id}_SUBSET.txt",
        f"{feed_id}.txt",
    ]
    for pattern in patterns:
        candidate = raw_dir / pattern
        if candidate.exists():
            return candidate
    for item in raw_dir.iterdir():
        if not item.is_file():
            continue
        if feed_id in item.name:
            return item
    return None
```
*Note: proves ingestion logic resolves TXT files under `FishBroData/raw` as the source data inputs.*
