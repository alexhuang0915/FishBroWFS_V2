#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/fishbro/FishBroWFS_V2"
EVI="$ROOT/outputs/_dp_evidence/phase_z_cleanup"

# Load keep entries into array
readarray -t keep_outputs < "$EVI/02_keepset_outputs.txt"
readarray -t keep_config < "$EVI/03_keepset_config.txt"

is_kept() {
  local p="$1"
  local -n keep_arr="$2"
  for k in "${keep_arr[@]}"; do
    [[ -z "$k" ]] && continue
    # exact match
    [[ "$p" == "$k" ]] && return 0
    # p is a subdirectory of k
    [[ "$p" == "$k/"* ]] && return 0
    # k is a subdirectory of p (p is parent of kept entry)
    [[ "$k" == "$p/"* ]] && return 0
  done
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

# Use arrays for keep sets
build_deleteset "$ROOT/outputs" keep_outputs "$EVI/04_deleteset_outputs.txt"
build_deleteset "$ROOT/config" keep_config "$EVI/05_deleteset_config.txt"

echo "DELETESET built:"
wc -l "$EVI/04_deleteset_outputs.txt" "$EVI/05_deleteset_config.txt"