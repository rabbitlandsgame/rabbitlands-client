"""Where the hair tools find their inputs and tools (no machine-specific paths).

Environment variables (all optional):
  RL_HEADS_ROOT  the RL head authoring area holding build/, gen/, ref/, blender_profile/
                 (default: <repo>/.local/rl-heads, or RL_HEADS_LOCAL)
  RL_WORKTREE    the client repository root (godot-client/, eloria-assets/)
                 (default: this repository)
  RL_MPFB_GROUPS path of MPFB's socketobject/_extra_vertex_groups.py
                 (default: RL_HEADS_ROOT/blender_profile/extensions/user_default/mpfb/...)
  BLENDER        Blender executable for preview.py (default: `blender` on PATH)
  RL_GPU_LOCK    optional wrapper script that serialises GPU renders on a shared
                 machine (run through bash); unset = render directly
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.normpath(os.path.join(HERE, '..', '..', '..', '..'))
RL_ROOT = os.path.abspath(os.environ.get('RL_HEADS_ROOT') or os.environ.get('RL_HEADS_LOCAL')
                          or os.path.join(_REPO, '.local', 'rl-heads'))
WORKTREE = os.path.abspath(os.environ.get('RL_WORKTREE') or _REPO)

BUILD = os.path.join(RL_ROOT, 'build')
HEADS = os.path.join(BUILD, 'v1')                          # rl_head_<sex>.glb / .npz
HAIR_OUT = os.path.join(BUILD, 'hair')
BEARD_OUT = os.path.join(BUILD, 'beards')
HAIR_TEX = os.path.join(HAIR_OUT, 'textures')
BEARD_TEX = os.path.join(BEARD_OUT, 'textures')
GEN = os.path.join(RL_ROOT, 'gen')                          # gen/hair_lock_v1.png
REF = os.path.join(RL_ROOT, 'ref')
MPFB_GROUPS = os.environ.get('RL_MPFB_GROUPS') or os.path.join(
    RL_ROOT, 'blender_profile', 'extensions', 'user_default', 'mpfb', 'entities', 'socketobject', '_extra_vertex_groups.py')
GLBKIT_DIR = os.path.join(WORKTREE, 'eloria-assets', 'tools', 'tpose_bodies', 'vendor')


def body_glb(sex):
    """The shipped Human body the head module sits on."""
    return os.path.join(WORKTREE, 'godot-client', 'assets', 'actors', 'native', 'races', f'luminous_{sex}.glb')


def blender():
    return os.environ.get('BLENDER') or shutil.which('blender') or 'blender'


def gpu_lock():
    p = os.environ.get('RL_GPU_LOCK')
    return p if p and os.path.exists(p) else None


def bash():
    return shutil.which('bash')
