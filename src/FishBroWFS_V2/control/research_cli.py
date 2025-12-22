
# src/FishBroWFS_V2/control/research_cli.py
"""
Research CLI：研究執行命令列介面

命令：
fishbro research run \
  --season 2026Q1 \
  --dataset-id CME.MNQ \
  --strategy-id S1 \
  --allow-build \
  --txt-path /home/fishbro/FishBroData/raw/CME.MNQ-HOT-Minute-Trade.txt \
  --mode incremental \
  --json

Exit code：
0：成功
20：缺 features 且不允許 build
1：其他錯誤
"""

from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
from typing import Optional

from FishBroWFS_V2.control.research_runner import (
    run_research,
    ResearchRunError,
)
from FishBroWFS_V2.control.build_context import BuildContext


def main() -> int:
    """CLI 主函數"""
    parser = create_parser()
    args = parser.parse_args()
    
    try:
        return run_research_cli(args)
    except KeyboardInterrupt:
        print("\n中斷執行", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"錯誤: {e}", file=sys.stderr)
        return 1


def create_parser() -> argparse.ArgumentParser:
    """建立命令列解析器"""
    parser = argparse.ArgumentParser(
        description="執行研究（載入策略、解析特徵、執行 WFS）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # 必要參數
    parser.add_argument(
        "--season",
        required=True,
        help="季節標記，例如 2026Q1",
    )
    parser.add_argument(
        "--dataset-id",
        required=True,
        help="資料集 ID，例如 CME.MNQ",
    )
    parser.add_argument(
        "--strategy-id",
        required=True,
        help="策略 ID",
    )
    
    # build 相關參數
    parser.add_argument(
        "--allow-build",
        action="store_true",
        help="允許自動 build 缺失的特徵",
    )
    parser.add_argument(
        "--txt-path",
        type=Path,
        help="原始 TXT 檔案路徑（只有 allow-build 才需要）",
    )
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="build 模式（只在 allow-build 時使用）",
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="輸出根目錄",
    )
    parser.add_argument(
        "--build-bars-if-missing",
        action="store_true",
        default=True,
        help="如果 bars cache 不存在，是否建立 bars",
    )
    parser.add_argument(
        "--no-build-bars-if-missing",
        action="store_false",
        dest="build_bars_if_missing",
        help="不建立 bars cache（即使缺失）",
    )
    
    # WFS 配置（可選）
    parser.add_argument(
        "--wfs-config",
        type=Path,
        help="WFS 配置 JSON 檔案路徑（可選）",
    )
    
    # 輸出選項
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式輸出結果",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="輸出詳細資訊",
    )
    
    return parser


def run_research_cli(args) -> int:
    """執行研究邏輯"""
    # 1. 準備 build_ctx（如果需要）
    build_ctx = prepare_build_context(args)
    
    # 2. 載入 WFS 配置（如果有）
    wfs_config = load_wfs_config(args)
    
    # 3. 執行研究
    try:
        report = run_research(
            season=args.season,
            dataset_id=args.dataset_id,
            strategy_id=args.strategy_id,
            outputs_root=args.outputs_root,
            allow_build=args.allow_build,
            build_ctx=build_ctx,
            wfs_config=wfs_config,
        )
        
        # 4. 輸出結果
        output_result(report, args)
        
        # 判斷 exit code
        # 如果有 build，回傳 10；否則回傳 0
        if report.get("build_performed", False):
            return 10
        else:
            return 0
        
    except ResearchRunError as e:
        # 檢查是否為缺失特徵且不允許 build 的錯誤
        err_msg = str(e).lower()
        if "缺失特徵且不允許建置" in err_msg or "missing features" in err_msg:
            print(f"缺失特徵且不允許建置: {e}", file=sys.stderr)
            return 20
        else:
            print(f"研究執行失敗: {e}", file=sys.stderr)
            return 1


def prepare_build_context(args) -> Optional[BuildContext]:
    """準備 BuildContext"""
    if not args.allow_build:
        return None
    
    if not args.txt_path:
        raise ValueError("--allow-build 需要 --txt-path")
    
    # 驗證 txt_path 存在
    if not args.txt_path.exists():
        raise FileNotFoundError(f"TXT 檔案不存在: {args.txt_path}")
    
    # 轉換 mode 為大寫
    mode = args.mode.upper()
    if mode not in ("FULL", "INCREMENTAL"):
        raise ValueError(f"無效的 mode: {args.mode}，必須為 'incremental' 或 'full'")
    
    return BuildContext(
        txt_path=args.txt_path,
        mode=mode,
        outputs_root=args.outputs_root,
        build_bars_if_missing=args.build_bars_if_missing,
    )


def load_wfs_config(args) -> Optional[dict]:
    """載入 WFS 配置"""
    if not args.wfs_config:
        return None
    
    config_path = args.wfs_config
    if not config_path.exists():
        raise FileNotFoundError(f"WFS 配置檔案不存在: {config_path}")
    
    try:
        content = config_path.read_text(encoding="utf-8")
        return json.loads(content)
    except Exception as e:
        raise ValueError(f"無法載入 WFS 配置 {config_path}: {e}")


def output_result(report: dict, args) -> None:
    """輸出研究結果"""
    if args.json:
        # JSON 格式輸出
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        # 文字格式輸出
        print(f"✅ 研究執行成功")
        print(f"   策略: {report['strategy_id']}")
        print(f"   資料集: {report['dataset_id']}")
        print(f"   季節: {report['season']}")
        print(f"   使用特徵: {len(report['used_features'])} 個")
        print(f"   是否執行了建置: {report['build_performed']}")
        
        if args.verbose:
            print(f"   WFS 摘要:")
            for key, value in report['wfs_summary'].items():
                print(f"     {key}: {value}")
            
            print(f"   特徵列表:")
            for feat in report['used_features']:
                print(f"     {feat['name']}@{feat['timeframe_min']}m")


if __name__ == "__main__":
    sys.exit(main())


