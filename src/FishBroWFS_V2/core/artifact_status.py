"""Status determination for artifact validation.

Defines OK/MISSING/INVALID/DIRTY states with human-readable error messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pydantic import ValidationError


class ArtifactStatus(str, Enum):
    """Artifact validation status."""
    OK = "OK"
    MISSING = "MISSING"  # File does not exist
    INVALID = "INVALID"  # Pydantic validation error
    DIRTY = "DIRTY"  # config_hash mismatch


@dataclass(frozen=True)
class ValidationResult:
    """
    Result of artifact validation.
    
    Contains status and human-readable error message.
    """
    status: ArtifactStatus
    message: str = ""
    error_details: Optional[str] = None  # Detailed error for debugging


def _format_pydantic_error(e: ValidationError) -> str:
    """Format Pydantic ValidationError into readable string with field paths."""
    parts: list[str] = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err.get("loc", []))
        msg = err.get("msg", "")
        typ = err.get("type", "")
        if loc:
            parts.append(f"{loc}: {msg} ({typ})")
        else:
            parts.append(f"{msg} ({typ})")
    return "；".join(parts) if parts else str(e)


def _extract_missing_field_names(e: ValidationError) -> list[str]:
    """Extract missing field names from ValidationError."""
    missing: set[str] = set()
    for err in e.errors():
        typ = str(err.get("type", "")).lower()
        msg = str(err.get("msg", "")).lower()
        if "missing" in typ or "required" in msg:
            loc = err.get("loc", ())
            # loc 可能像 ("rows", 0, "net_profit") 或 ("config_hash",)
            if loc:
                leaf = str(loc[-1])
                # 避免 leaf 是 index
                if not leaf.isdigit():
                    missing.add(leaf)
            # 也把完整路徑收進來（可讀性更好）
            loc_str = ".".join(str(x) for x in loc if not isinstance(x, int))
            if loc_str:
                missing.add(loc_str.split(".")[-1])  # leaf 再保險一次
    return sorted(missing)


def validate_manifest_status(
    file_path: str,
    manifest_data: Optional[dict] = None,
    expected_config_hash: Optional[str] = None,
) -> ValidationResult:
    """
    Validate manifest.json status.
    
    Args:
        file_path: Path to manifest.json
        manifest_data: Parsed manifest data (if available)
        expected_config_hash: Expected config_hash (for DIRTY check)
        
    Returns:
        ValidationResult with status and message
    """
    from pathlib import Path
    from FishBroWFS_V2.core.schemas.manifest import RunManifest
    
    path = Path(file_path)
    
    # Check if file exists
    if not path.exists():
        return ValidationResult(
            status=ArtifactStatus.MISSING,
            message=f"manifest.json 不存在: {file_path}",
        )
    
    # Try to parse with Pydantic
    if manifest_data is None:
        import json
        try:
            with path.open("r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except json.JSONDecodeError as e:
            return ValidationResult(
                status=ArtifactStatus.INVALID,
                message=f"manifest.json JSON 格式錯誤: {e}",
                error_details=str(e),
            )
    
    try:
        manifest = RunManifest(**manifest_data)
    except Exception as e:
        # Extract missing field from Pydantic error
        error_msg = str(e)
        missing_fields = []
        if "field required" in error_msg.lower():
            # Try to extract field name from error
            import re
            matches = re.findall(r"Field required.*?['\"]([^'\"]+)['\"]", error_msg)
            if matches:
                missing_fields = matches
        
        if missing_fields:
            msg = f"manifest.json 缺少欄位: {', '.join(missing_fields)}"
        else:
            msg = f"manifest.json 驗證失敗: {error_msg}"
        
        return ValidationResult(
            status=ArtifactStatus.INVALID,
            message=msg,
            error_details=error_msg,
        )
    
    # Check config_hash if expected is provided
    if expected_config_hash is not None and manifest.config_hash != expected_config_hash:
        return ValidationResult(
            status=ArtifactStatus.DIRTY,
            message=f"manifest.config_hash={manifest.config_hash} 但預期值為 {expected_config_hash}",
        )
    
    return ValidationResult(status=ArtifactStatus.OK, message="manifest.json 驗證通過")


def validate_winners_v2_status(
    file_path: str,
    winners_data: Optional[dict] = None,
    expected_config_hash: Optional[str] = None,
    manifest_config_hash: Optional[str] = None,
) -> ValidationResult:
    """
    Validate winners_v2.json status.
    
    Args:
        file_path: Path to winners_v2.json
        winners_data: Parsed winners data (if available)
        expected_config_hash: Expected config_hash (for DIRTY check)
        manifest_config_hash: config_hash from manifest (for DIRTY check)
        
    Returns:
        ValidationResult with status and message
    """
    from pathlib import Path
    from FishBroWFS_V2.core.schemas.winners_v2 import WinnersV2
    
    path = Path(file_path)
    
    # Check if file exists
    if not path.exists():
        return ValidationResult(
            status=ArtifactStatus.MISSING,
            message=f"winners_v2.json 不存在: {file_path}",
        )
    
    # Try to parse with Pydantic
    if winners_data is None:
        import json
        try:
            with path.open("r", encoding="utf-8") as f:
                winners_data = json.load(f)
        except json.JSONDecodeError as e:
            return ValidationResult(
                status=ArtifactStatus.INVALID,
                message=f"winners_v2.json JSON 格式錯誤: {e}",
                error_details=str(e),
            )
    
    try:
        winners = WinnersV2(**winners_data)
        
        # Validate rows if present (Pydantic already validates required fields)
        # Additional checks for None values (defensive)
        for idx, row in enumerate(winners.rows):
            if row.net_profit is None:
                return ValidationResult(
                    status=ArtifactStatus.INVALID,
                    message=f"winners_v2.json 第 {idx} 行 net_profit 是必填欄位",
                    error_details=f"row[{idx}].net_profit is None",
                )
            if row.max_drawdown is None:
                return ValidationResult(
                    status=ArtifactStatus.INVALID,
                    message=f"winners_v2.json 第 {idx} 行 max_drawdown 是必填欄位",
                    error_details=f"row[{idx}].max_drawdown is None",
                )
            if row.trades is None:
                return ValidationResult(
                    status=ArtifactStatus.INVALID,
                    message=f"winners_v2.json 第 {idx} 行 trades 是必填欄位",
                    error_details=f"row[{idx}].trades is None",
                )
    except ValidationError as e:
        missing_fields = _extract_missing_field_names(e)
        missing_txt = f"缺少欄位: {', '.join(missing_fields)}；" if missing_fields else ""
        error_details = str(e) + "\nmissing_fields=" + ",".join(missing_fields) if missing_fields else str(e)
        return ValidationResult(
            status=ArtifactStatus.INVALID,
            message=f"winners_v2.json {missing_txt}schema 驗證失敗：{_format_pydantic_error(e)}",
            error_details=error_details,
        )
    except Exception as e:
        # Fallback for non-Pydantic errors
        return ValidationResult(
            status=ArtifactStatus.INVALID,
            message=f"winners_v2.json 驗證失敗: {e}",
            error_details=str(e),
        )
    
    # Check config_hash if expected/manifest is provided
    if expected_config_hash is not None:
        if winners.config_hash != expected_config_hash:
            return ValidationResult(
                status=ArtifactStatus.DIRTY,
                message=f"winners_v2.config_hash={winners.config_hash} 但預期值為 {expected_config_hash}",
            )
    
    if manifest_config_hash is not None:
        if winners.config_hash != manifest_config_hash:
            return ValidationResult(
                status=ArtifactStatus.DIRTY,
                message=f"winners_v2.config_hash={winners.config_hash} 但 manifest.config_hash={manifest_config_hash}",
            )
    
    return ValidationResult(status=ArtifactStatus.OK, message="winners_v2.json 驗證通過")


def validate_governance_status(
    file_path: str,
    governance_data: Optional[dict] = None,
    expected_config_hash: Optional[str] = None,
    manifest_config_hash: Optional[str] = None,
) -> ValidationResult:
    """
    Validate governance.json status.
    
    Args:
        file_path: Path to governance.json
        governance_data: Parsed governance data (if available)
        expected_config_hash: Expected config_hash (for DIRTY check)
        manifest_config_hash: config_hash from manifest (for DIRTY check)
        
    Returns:
        ValidationResult with status and message
    """
    from pathlib import Path
    from FishBroWFS_V2.core.schemas.governance import GovernanceReport
    
    path = Path(file_path)
    
    # Check if file exists
    if not path.exists():
        return ValidationResult(
            status=ArtifactStatus.MISSING,
            message=f"governance.json 不存在: {file_path}",
        )
    
    # Try to parse with Pydantic
    if governance_data is None:
        import json
        try:
            with path.open("r", encoding="utf-8") as f:
                governance_data = json.load(f)
        except json.JSONDecodeError as e:
            return ValidationResult(
                status=ArtifactStatus.INVALID,
                message=f"governance.json JSON 格式錯誤: {e}",
                error_details=str(e),
            )
    
    try:
        governance = GovernanceReport(**governance_data)
    except Exception as e:
        # Extract missing field from Pydantic error
        error_msg = str(e)
        missing_fields = []
        if "field required" in error_msg.lower():
            import re
            matches = re.findall(r"Field required.*?['\"]([^'\"]+)['\"]", error_msg)
            if matches:
                missing_fields = matches
        
        if missing_fields:
            msg = f"governance.json 缺少欄位: {', '.join(missing_fields)}"
        else:
            msg = f"governance.json 驗證失敗: {error_msg}"
        
        return ValidationResult(
            status=ArtifactStatus.INVALID,
            message=msg,
            error_details=error_msg,
        )
    
    # Check config_hash if expected/manifest is provided
    if expected_config_hash is not None:
        if governance.config_hash != expected_config_hash:
            return ValidationResult(
                status=ArtifactStatus.DIRTY,
                message=f"governance.config_hash={governance.config_hash} 但預期值為 {expected_config_hash}",
            )
    
    if manifest_config_hash is not None:
        if governance.config_hash != manifest_config_hash:
            return ValidationResult(
                status=ArtifactStatus.DIRTY,
                message=f"governance.config_hash={governance.config_hash} 但 manifest.config_hash={manifest_config_hash}",
            )
    
    return ValidationResult(status=ArtifactStatus.OK, message="governance.json 驗證通過")
