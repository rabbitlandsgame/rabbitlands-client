#!/usr/bin/env bash
# Repository-relative locations (see paths.py): TOOLS is eloria-assets/tools/rl_heads.
TOOLS=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO=$(cd "$TOOLS/../../.." && pwd)
LOCAL=${RL_HEADS_LOCAL:-$REPO/.local/rl-heads}
# Isolated Godot profile for the headwear audit (absolute paths: a relative one
# makes Godot create stray folders).
BASE=$LOCAL/godot-user/headwear_audit
export APPDATA=$BASE/appdata LOCALAPPDATA=$BASE/localappdata TEMP=$BASE/temp TMP=$BASE/temp
GODOT=${GODOT:-godot}
PROJECT=$REPO/godot-client
LOGS=$LOCAL/evidence/headwear_audit/logs
mkdir -p "$LOGS" "$BASE/appdata" "$BASE/localappdata" "$BASE/temp"
GPU_LOCK=${RL_GPU_LOCK:-}
