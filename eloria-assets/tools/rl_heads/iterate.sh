#!/bin/bash
# Repository-relative locations (see paths.py): TOOLS is eloria-assets/tools/rl_heads.
TOOLS=$(cd "$(dirname "${BASH_SOURCE[0]}")/." && pwd)
REPO=$(cd "$TOOLS/../../.." && pwd)
LOCAL=${RL_HEADS_LOCAL:-$REPO/.local/rl-heads}
# iterate.sh <name> <character>   (spec at lab/<name>/spec.json)
R=$LOCAL
export BLENDER_USER_RESOURCES="$(cygpath -w $R/blender_profile)"
timeout 300 "${BLENDER:-blender}" -b --python "$(cygpath -w $TOOLS/head_lab.py)" -- "$(cygpath -w $R/lab/$1/spec.json)" "$(cygpath -w $R/lab/$1)" 2>&1 | grep -E 'Error|Traceback|line ' | grep -v mpfb.init | head
M=$(cygpath -m $R)
python $(cygpath -m "$TOOLS")/compare.py $M/lab/$1 $2 $M/lab/$1/compare_tight.png --box 60,70 --zoom 4 --views front,side > /dev/null
python $(cygpath -m "$TOOLS")/compare.py $M/lab/$1 $2 $M/lab/$1/compare.png > /dev/null
echo done $1
