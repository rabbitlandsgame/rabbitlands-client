"""Where the RL head tools find their inputs, outputs and programs.

Nothing here names a machine: every location is relative to this repository
or set by an environment variable.

  RL_HEADS_LOCAL      the ignored authoring area (default <repo>/.local/rl-heads):
                      MPFB data (mpfb_ext/), the Blender profile with MPFB
                      (blender_profile/), builds (build/), lab specs (lab/),
                      generated textures (gen/), references (ref/), evidence/
  RL_HEADS_REFERENCE  the concept study renders the likeness tools compare with
                      (default <local>/ref/studies/)
  BLENDER             Blender 5.x executable (default: `blender` on PATH)
  GODOT               Godot 4.7 executable (default: `godot` on PATH)
  RL_GPU_LOCK         optional wrapper serialising GPU renders (run through bash)
"""
import os as _os
import shutil as _shutil

TOOLS = _os.path.dirname(_os.path.abspath(__file__))
REPO = _os.path.normpath(_os.path.join(TOOLS, '..', '..', '..'))
CLIENT = _os.path.join(REPO, 'godot-client')
LOCAL = _os.path.abspath(_os.environ.get('RL_HEADS_LOCAL') or _os.path.join(REPO, '.local', 'rl-heads'))
REFERENCE = _os.environ.get('RL_HEADS_REFERENCE') or (_os.path.join(LOCAL, 'ref', 'studies') + '/')
BLENDER = _os.environ.get('BLENDER') or _shutil.which('blender') or 'blender'
GODOT = _os.environ.get('GODOT') or _shutil.which('godot') or 'godot'
GPU_LOCK = _os.environ.get('RL_GPU_LOCK', '')
SPECS = _os.path.join(TOOLS, 'specs')
