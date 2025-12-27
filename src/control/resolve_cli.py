
"""
Resolve CLI：特徵解析命令列介面

命令：
fishbro resolve features --season 2026Q1 --dataset-id CME.MNQ --strategy-id S1 --req configs/strategies/S1/features.json

行為：
- 不允許 build → 只做檢查與載入
- 允許 build → 缺就 build，成功後載入，輸出 bundle 摘要（不輸出整個 array）

Exit code：
0：已滿足且載入成功
10：已 build（可選）
20：缺失且不允許 build / build_ctx 不足
1：其他錯誤
"""

from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
from typing import Optional

from contracts.strategy_features import (
    StrategyFeatureRequirements,
    load_requirements_from_json,
)
from control.feature_resolver import (
    resolve_features,
    MissingFeaturesError,
    ManifestMismatchError,
    BuildNotAllowedError,
    FeatureResolutionError,
)
from control.build_context import BuildContext


def main() -> int:
    """CLI 主函數"""
    parser = create_parser()
    args = parser.parse_args()
    
    try:
        return run_resolve(args)
    except KeyboardInterrupt:
        print("\n中斷執行", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"錯誤: {e}", file=sys.stderr)
        return 1


def create_parser() -> argparse.ArgumentParser:
    """建立命令列解析器"""
    parser = argparse.ArgumentParser(
        description="解析策略特徵依賴",
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
    
    # 需求來源（二選一）
    req_group = parser.add_mutually_exclusive_group(required=True)
    req_group.add_argument(
        "--strategy-id",
        help="策略 ID（用於自動尋找需求檔案）",
    )
    req_group.add_argument(
        "--req",
        type=Path,
        help="需求 JSON 檔案路徑",
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


def run_resolve(args) -> int:
    """執行解析邏輯"""
    # 1. 載入需求
    requirements = load_requirements(args)
    
    # 2. 準備 build_ctx（如果需要）
    build_ctx = prepare_build_context(args)
    
    # 3. 執行解析
    try:
        bundle = resolve_features(
            season=args.season,
            dataset_id=args.dataset_id,
            requirements=requirements,
            outputs_root=args.outputs_root,
            allow_build=args.allow_build,
            build_ctx=build_ctx,
        )
        
        # 4. 輸出結果
        output_result(bundle, args)
        
        # 判斷 exit code
        # 如果有 build，回傳 10；否則回傳 0
        # 目前我們無法知道是否有 build，所以暫時回傳 0
        return 0
        
    except MissingFeaturesError as e:
        print(f"缺少特徵: {e}", file=sys.stderr)
        return 20
    except BuildNotAllowedError as e:
        print(f"不允許 build: {e}", file=sys.stderr)
        return 20
    except ManifestMismatchError as e:
        print(f"Manifest 合約不符: {e}", file=sys.stderr)
        return 1
    except FeatureResolutionError as e:
        print(f"特徵解析失敗: {e}", file=sys.stderr)
        return 1


def load_requirements(args) -> StrategyFeatureRequirements:
    """載入策略特徵需求"""
    if args.req:
        # 從指定 JSON 檔案載入
        return load_requirements_from_json(str(args.req))
    elif args.strategy_id:
        # 自動尋找需求檔案
        # 優先順序：
        # 1. strategies/{strategy_id}/features.json
        # 2. configs/strategies/{strategy_id}/features.json
        # 3. 當前目錄下的 {strategy_id}_features.json
        
        possible_paths = [
            Path(f"configs/strategies/{args.strategy_id}/features.json"),
            Path(f"strategies/{args.strategy_id}/features.json"),  # legacy location
            Path(f"{args.strategy_id}_features.json"),
        ]
        
        for path in possible_paths:
            if path.exists():
                return load_requirements_from_json(str(path))
        
        raise FileNotFoundError(
            f"找不到策略 {args.strategy_id} 的需求檔案。"
            f"嘗試的路徑: {[str(p) for p in possible_paths]}"
        )
    else:
        # 這不應該發生，因為 argparse 確保了二選一
        raise ValueError("必須提供 --req 或 --strategy-id")


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


def output_result(bundle, args) -> None:
    """輸出解析結果"""
    if args.json:
        # JSON 格式輸出
        result = {
            "success": True,
            "bundle": bundle.to_dict(),
            "series_count": len(bundle.series),
            "series_keys": bundle.list_series(),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # 文字格式輸出
        print(f"✅ 特徵解析成功")
        print(f"   資料集: {bundle.dataset_id}")
        print(f"   季節: {bundle.season}")
        print(f"   特徵數量: {len(bundle.series)}")
        
        if args.verbose:
            print(f"   Metadata:")
            for key, value in bundle.meta.items():
                if key in ("files_sha256", "manifest_sha256"):
                    # 縮短 hash 顯示
                    if isinstance(value, str) and len(value) > 16:
                        value = f"{value[:8]}...{value[-8:]}"
                print(f"     {key}: {value}")
            
            print(f"   特徵列表:")
            for name, tf in bundle.list_series():
                series = bundle.get_series(name, tf)
                print(f"     {name}@{tf}m: {len(series.ts)} 筆資料")


if __name__ == "__main__":
    sys.exit(main())


