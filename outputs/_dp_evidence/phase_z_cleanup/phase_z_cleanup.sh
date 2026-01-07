#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/fishbro/FishBroWFS_V2"
EVI="$ROOT/outputs/_dp_evidence/phase_z_cleanup"

is_kept() {
  local p="$1"; local keeps="$2"
  while IFS= read -r k; do
    [[ -z "$k" ]] && continue
    [[ "$p" == "$k" ]] && return 0
    [[ "$p" == "$k/"* ]] && return 0
  done < "$keeps"
  return 1
}

build_deleteset() {
  local base="$1" keeps="$2" out="$3"
  : > "$out"
  # collect candidates (depth 1..4 to be thorough but bounded)
  mapfile -t candidates < <(find "$base" -mindepth 1 -maxdepth 4 2>/dev/null | sort -u)
  for p in "${candidates[@]}"; do
    if ! is_kept "$p" "$keeps"; then
      echo "$p" >> "$out"
    fi
  done
  sort -u "$out" -o "$out"
}

build_deleteset "$ROOT/outputs" "$EVI/02_keepset_outputs.txt" "$EVI/04_deleteset_outputs.txt"
build_deleteset "$ROOT/config"  "$EVI/03_keepset_config.txt"  "$EVI/05_deleteset_config.txt"

echo "DELETESET built:"
wc -l "$EVI/04_deleteset_outputs.txt" "$EVI/05_deleteset_config.txt"