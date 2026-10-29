#!/usr/bin/env bash
# Repository-relative locations (see paths.py): TOOLS is eloria-assets/tools/rl_heads.
TOOLS=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO=$(cd "$TOOLS/../../.." && pwd)
LOCAL=${RL_HEADS_LOCAL:-$REPO/.local/rl-heads}
# Fit every open piece in parallel (one process per piece), then merge into
# godot-client/data/actors/rl_head_headwear_fit.json.
cd $TOOLS/headwear
P=$LOCAL/evidence/headwear_audit/parts
mkdir -p "$P"
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4
for v in 111 112 114 119; do
  "${PYTHON:-python}" -u fit_open_headwear.py fit --pieces $v --out "$P/part_$v.json" "$@" > "$P/fit_$v.log" 2>&1 &
done
wait
"${PYTHON:-python}" -u fit_open_headwear.py merge --parts "$P/part_111.json,$P/part_112.json,$P/part_114.json,$P/part_119.json"
