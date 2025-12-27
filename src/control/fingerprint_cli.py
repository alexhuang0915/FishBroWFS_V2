
"""
Fingerprint scan-only diff CLI

提供 scan-only 命令，用於比較 TXT 檔案與現有指紋索引，產生 diff 報告。
此命令純粹掃描與比較，不觸發任何 build 或 WFS 行為。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from contracts.fingerprint import FingerprintIndex
from control.fingerprint_store import (
    fingerprint_index_path,
    load_fingerprint_index_if_exists,
    write_fingerprint_index,
)
from core.fingerprint import (
    build_fingerprint_index_from_raw_ingest,
    compare_fingerprint_indices,
)
from data.raw_ingest import ingest_raw_txt


def scan_fingerprint(
    season: str,
    dataset_id: str,
    txt_path: Path,
    outputs_root: Optional[Path] = None,
    save_new_index: bool = False,
    verbose: bool = False,
) -> dict:
    """
    掃描 TXT 檔案並與現有指紋索引比較
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        txt_path: TXT 檔案路徑
        outputs_root: 輸出根目錄
        save_new_index: 是否儲存新的指紋索引
        verbose: 是否輸出詳細資訊
    
    Returns:
        diff 報告字典
    """
    # 檢查檔案是否存在
    if not txt_path.exists():
        raise FileNotFoundError(f"TXT 檔案不存在: {txt_path}")
    
    # 載入現有指紋索引（如果存在）
    index_path = fingerprint_index_path(season, dataset_id, outputs_root)
    old_index = load_fingerprint_index_if_exists(index_path)
    
    if verbose:
        if old_index:
            print(f"找到現有指紋索引: {index_path}")
            print(f"  範圍: {old_index.range_start} 到 {old_index.range_end}")
            print(f"  天數: {len(old_index.day_hashes)}")
        else:
            print(f"沒有現有指紋索引: {index_path}")
    
    # 讀取 TXT 檔案並建立新的指紋索引
    if verbose:
        print(f"讀取 TXT 檔案: {txt_path}")
    
    raw_result = ingest_raw_txt(txt_path)
    
    if verbose:
        print(f"  讀取 {raw_result.rows} 行")
        if raw_result.policy.normalized_24h:
            print(f"  已正規化 24:00:00 時間")
    
    # 建立新的指紋索引
    new_index = build_fingerprint_index_from_raw_ingest(
        dataset_id=dataset_id,
        raw_ingest_result=raw_result,
        build_notes=f"scanned from {txt_path.name}",
    )
    
    if verbose:
        print(f"建立新的指紋索引:")
        print(f"  範圍: {new_index.range_start} 到 {new_index.range_end}")
        print(f"  天數: {len(new_index.day_hashes)}")
        print(f"  index_sha256: {new_index.index_sha256[:16]}...")
    
    # 比較索引
    diff_report = compare_fingerprint_indices(old_index, new_index)
    
    # 如果需要，儲存新的指紋索引
    if save_new_index:
        if verbose:
            print(f"儲存新的指紋索引到: {index_path}")
        
        write_fingerprint_index(new_index, index_path)
        diff_report["new_index_saved"] = True
        diff_report["new_index_path"] = str(index_path)
    else:
        diff_report["new_index_saved"] = False
    
    return diff_report


def format_diff_report(diff_report: dict, verbose: bool = False) -> str:
    """
    格式化 diff 報告
    
    Args:
        diff_report: diff 報告字典
        verbose: 是否輸出詳細資訊
    
    Returns:
        格式化字串
    """
    lines = []
    
    # 基本資訊
    lines.append("=== Fingerprint Scan Report ===")
    
    if diff_report.get("is_new", False):
        lines.append("狀態: 全新資料集（無現有指紋索引）")
    elif diff_report.get("no_change", False):
        lines.append("狀態: 無變更（指紋完全相同）")
    elif diff_report.get("append_only", False):
        lines.append("狀態: 僅尾部新增（可增量）")
    else:
        lines.append("狀態: 資料變更（需全量重算）")
    
    lines.append("")
    
    # 範圍資訊
    if diff_report["old_range_start"]:
        lines.append(f"舊範圍: {diff_report['old_range_start']} 到 {diff_report['old_range_end']}")
    lines.append(f"新範圍: {diff_report['new_range_start']} 到 {diff_report['new_range_end']}")
    
    # 變更資訊
    if diff_report.get("append_only", False):
        append_range = diff_report.get("append_range")
        if append_range:
            lines.append(f"新增範圍: {append_range[0]} 到 {append_range[1]}")
    
    if diff_report.get("earliest_changed_day"):
        lines.append(f"最早變更日: {diff_report['earliest_changed_day']}")
    
    # 儲存狀態
    if diff_report.get("new_index_saved", False):
        lines.append(f"新指紋索引已儲存: {diff_report.get('new_index_path', '')}")
    
    # 詳細輸出
    if verbose:
        lines.append("")
        lines.append("--- 詳細報告 ---")
        lines.append(json.dumps(diff_report, indent=2, ensure_ascii=False))
    
    return "\n".join(lines)


def main() -> int:
    """
    CLI 主函數
    
    命令：fishbro fingerprint scan --season 2026Q1 --dataset-id XXX --txt-path /path/to/file.txt
    """
    parser = argparse.ArgumentParser(
        description="掃描 TXT 檔案並與指紋索引比較（scan-only diff）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # 子命令（未來可擴展）
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # scan 命令
    scan_parser = subparsers.add_parser(
        "scan",
        help="掃描 TXT 檔案並比較指紋"
    )
    
    scan_parser.add_argument(
        "--season",
        required=True,
        help="季節標記，例如 '2026Q1'"
    )
    
    scan_parser.add_argument(
        "--dataset-id",
        required=True,
        help="資料集 ID，例如 'CME.MNQ.60m.2020-2024'"
    )
    
    scan_parser.add_argument(
        "--txt-path",
        type=Path,
        required=True,
        help="TXT 檔案路徑"
    )
    
    scan_parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="輸出根目錄"
    )
    
    scan_parser.add_argument(
        "--save",
        action="store_true",
        help="儲存新的指紋索引（否則僅比較）"
    )
    
    scan_parser.add_argument(
        "--verbose",
        action="store_true",
        help="輸出詳細資訊"
    )
    
    scan_parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式輸出報告"
    )
    
    # 如果沒有提供命令，顯示幫助
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    
    args = parser.parse_args()
    
    if args.command != "scan":
        print(f"錯誤: 不支援的命令: {args.command}", file=sys.stderr)
        parser.print_help()
        return 1
    
    try:
        # 執行掃描
        diff_report = scan_fingerprint(
            season=args.season,
            dataset_id=args.dataset_id,
            txt_path=args.txt_path,
            outputs_root=args.outputs_root,
            save_new_index=args.save,
            verbose=args.verbose,
        )
        
        # 輸出結果
        if args.json:
            print(json.dumps(diff_report, indent=2, ensure_ascii=False))
        else:
            report_text = format_diff_report(diff_report, args.verbose)
            print(report_text)
        
        # 根據結果返回適當的退出碼
        if diff_report.get("no_change", False):
            return 0  # 無變更
        elif diff_report.get("append_only", False):
            return 10  # 可增量（使用非零值表示需要處理）
        else:
            return 20  # 需全量重算
        
    except FileNotFoundError as e:
        print(f"錯誤: 檔案不存在 - {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"錯誤: 資料驗證失敗 - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"錯誤: 執行失敗 - {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())


