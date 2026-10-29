#!/usr/bin/env bash
# Repository-relative locations (see paths.py): TOOLS is eloria-assets/tools/rl_heads.
TOOLS=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO=$(cd "$TOOLS/../../.." && pwd)
LOCAL=${RL_HEADS_LOCAL:-$REPO/.local/rl-heads}
# Before/after evidence renders for the open-headwear fit (windowed, serialised
# through gpu_lock). Usage: render_evidence.sh [set ...]
#   sets: open closed hair bust seq
# "off" renders set RL_HEADWEAR_FIT=0 (every head piece as shipped).
set -u
HERE=$TOOLS/headwear
source "$HERE/godot_env.sh"
EV=$LOCAL/evidence/headwear_audit/godot
OPEN=${OPEN:-111,112,114,119}
run() {  # run <name> <fit on|off> <args...>
  local name=$1 fit=$2; shift 2
  local out="$EV/$name"
  rm -rf "$out"
  if [ "$fit" = off ]; then export RL_HEADWEAR_FIT=0; else unset RL_HEADWEAR_FIT; fi
  timeout 900 bash "$GPU_LOCK" "$GODOT" --path "$PROJECT" --log-file "$LOGS/$name.log" \
    --script res://tests/integration/rl_head_renders.gd -- --out "$out" "$@" > /dev/null 2>&1
  echo "$name exit $? $(grep -cE 'SCRIPT ERROR|Parse Error|SHADER ERROR' "$LOGS/$name.log") script errors;" \
    "$(grep -o 'RL_HEAD_RENDERS_DONE.*' "$LOGS/$name.log" | awk '{print $NF}') stills"
}
VIEWS=front,profile,rear,three_quarter
for set in ${@:-open closed hair bust seq}; do
  case $set in
    open)
      for fit in off on; do
        run "open_${fit}" $fit --presets mira,rowan,legacy_female,legacy_male --headwear $OPEN --views $VIEWS --torso yes --size 400x400
        run "open_bald_${fit}" $fit --presets mira,rowan --hair none --headwear $OPEN --views $VIEWS --torso yes --size 400x400
      done ;;
    closed)
      for fit in off on; do
        run "closed_${fit}" $fit --presets mira,rowan,legacy_female,legacy_male --headwear 134,159,115,122,150,170 --views front,profile --torso yes --size 320x320
      done ;;
    hair)
      for fit in off on; do
        run "hair_legacy_long_${fit}" $fit --presets legacy_female,legacy_male --legacy_hair 2 --headwear ${HAIRSET:-111,112,119} --views $VIEWS --torso yes --size 400x400
        run "hair_legacy_parted_${fit}" $fit --presets legacy_female,legacy_male --legacy_hair 1 --headwear 111 --views $VIEWS --torso yes --size 400x400
        run "hair_cross_${fit}" $fit --presets ilse,bren,kellan --headwear ${HAIRSET:-111,112,119} --views front,profile,rear --torso yes --size 400x400
      done ;;
    bust)
      for fit in off on; do
        run "bust_${fit}" $fit --presets mira,rowan,legacy_male --headwear 111,112,114 --views bust,hair --torso yes --size 480x480
      done ;;
    seq)
      run "seq_111_mira" on --presets mira --headwear 111 --torso yes --sequence Walk --frames 12 --fps 12 --views three_quarter --size 400x400
      run "seq_111_rowan" on --presets rowan --headwear 111 --torso yes --sequence Walk --frames 12 --fps 12 --views rear --size 400x400 ;;
  esac
done
