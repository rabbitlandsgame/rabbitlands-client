"""Copy the RL head authoring scripts from the ignored local authoring area into
this folder (eloria-assets/tools/rl_heads/), with every machine-specific path
replaced by a repository-relative or environment-configurable one (paths.py).

    python sync_from_local.py [--source <.local/rl-heads/scripts>]

The source defaults to RL_HEADS_SCRIPTS, else <repo>/.local/rl-heads/scripts.
Inputs and outputs (MPFB data, the Blender profile, builds, evidence, Meshy
task ledgers) stay in the ignored local area and are never copied; neither is
anything holding a key. The run fails rather than writing a file that still
names a machine path, and never writes an empty file.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..', '..'))

# Where the scripts were authored (the prototype worktree) and the concept
# study renders they compare against: replaced by paths.REPO / paths.REFERENCE.
AUTHORED_WORKTREES = ['C:/rabbitlands/worktrees/client-rl-heads-claude-20261027',
                      '/c/rabbitlands/worktrees/client-rl-heads-claude-20261027']
REFERENCE_DIR = ('C:/rabbitlands/worktrees/client-leaderboard-human-studies-20261026/.local/concept-art/'
                 'leaderboard-humans-2026-10-26/output/Rabbit-Lands-Human-Player-Studies/characters/')
BLENDER_EXE = 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
GODOT_EXE = 'C:/rabbitlands/rabbitlands-client/godot-client/Godot_v4.7.2-stable_win64.exe'
GPU_LOCK = 'C:/rabbitlands/rabbitlands-client/.local/asset-authoring/workspace/work-output/gpu_lock.sh'
PYTHON_EXE = 'C:/Python/Python313/python.exe'

SKIP_FILES = {'sync_tools.py'}           # superseded by this script
SKIP_DIRS = {'__pycache__'}
SKIP_SUFFIXES = ('.pyc', '.npz', '.glb', '.png', '.blend', '.log')
# Specs the head build reads, copied beside the scripts (local -> tools/specs).
SPECS = {
    'specs/controls.json': 'specs/controls.json',
    'specs/brow_styles.json': 'specs/brow_styles.json',
    'specs/paint_female.json': 'specs/paint_female.json',
    'specs/paint_male.json': 'specs/paint_male.json',
    'ref/landmarks_ref.json': 'specs/landmarks_ref.json',
    'lab/mira6/spec.json': 'specs/likeness_female.json',
    'lab/rowan4/spec.json': 'specs/likeness_male.json',
}
FORBIDDEN = re.compile(r'(?i)(?<![A-Za-z])[a-z]:[/\\](?:rabbitlands|users|program files|python)|/c/rabbitlands|'
                       r'/e/rlw|client-rl-heads-claude|leaderboard-human-studies|meshy\.key|MESHY_API_KEY\s*=')

PATHS_PY = '''"""Where the RL head tools find their inputs, outputs and programs.

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
'''

SHELL_PRELUDE = '''# Repository-relative locations (see paths.py): TOOLS is eloria-assets/tools/rl_heads.
TOOLS=$(cd "$(dirname "${BASH_SOURCE[0]}")/%s" && pwd)
REPO=$(cd "$TOOLS/../../.." && pwd)
LOCAL=${RL_HEADS_LOCAL:-$REPO/.local/rl-heads}
'''


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise SystemExit(f'expected text not found (the script changed; update sync_from_local.py):\n{old}')
    return text.replace(old, new, 1)


def python_rewrite(rel: str, text: str) -> str:
    depth = rel.count('/')  # 0 for top-level scripts, 1 for hair/, headwear/, ...
    for wt in AUTHORED_WORKTREES:
        text = text.replace(f"'{wt}/.local/rl-heads/evidence/headwear_audit'", "paths.LOCAL + '/evidence/headwear_audit'")
        text = text.replace(f"{wt}/.local/rl-heads", "' + paths.LOCAL + '")
        text = text.replace(f"'{wt}'", 'paths.REPO')
        text = text.replace(wt, "' + paths.REPO + '")
    text = text.replace(f"'{REFERENCE_DIR}'", 'paths.REFERENCE')
    text = text.replace(REFERENCE_DIR, "' + paths.REFERENCE + '")
    text = text.replace(f"'{BLENDER_EXE}'", 'paths.BLENDER')
    text = text.replace("'' + ", '').replace(" + ''", '')
    # The local authoring area, reached from the scripts folder in the original layout.
    text = text.replace("R = os.path.dirname(HERE)", "R = paths.LOCAL")
    text = text.replace("R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))", "R = paths.LOCAL")
    text = text.replace("os.path.normpath(os.path.join(HERE, '..', 'mpfb_ext', 'data'))",
                        "os.path.join(paths.LOCAL, 'mpfb_ext', 'data')")
    text = text.replace("os.path.join(os.path.dirname(__file__), '..', 'mpfb_ext', 'data')",
                        "os.path.join(paths.LOCAL, 'mpfb_ext', 'data')")
    text = text.replace("os.path.normpath(os.path.join(HERE, '..', 'blender_profile', 'extensions', '.user', "
                        "'user_default', 'mpfb', 'data'))",
                        "os.path.join(paths.LOCAL, 'blender_profile', 'extensions', '.user', 'user_default', 'mpfb', 'data')")
    text = text.replace("os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ref', 'landmarks_ref.json')",
                        "os.path.join(paths.SPECS, 'landmarks_ref.json')")
    # Scripts and specs that sat beside the local area's scripts/ are here: the
    # tools folder and its specs/.
    text = text.replace("os.path.join(R, 'scripts', ", "os.path.join(paths.TOOLS, ")
    text = text.replace("os.path.join(R, 'specs', ", "os.path.join(paths.SPECS, ")
    if rel == 'fit/fitcommon.py':
        text = replace_once(text, "RL = os.path.normpath(os.path.join(HERE, '..', '..'))                  # .local/rl-heads\n"
                            "WT = os.path.normpath(os.path.join(RL, '..', '..'))                    # worktree root\n",
                            "TOOLS = os.path.normpath(os.path.join(HERE, '..'))                     # eloria-assets/tools/rl_heads\n"
                            "WT = os.path.normpath(os.path.join(TOOLS, '..', '..', '..'))           # repository root\n"
                            "RL = os.path.abspath(os.environ.get('RL_HEADS_LOCAL') or os.path.join(WT, '.local', 'rl-heads'))\n")
        text = replace_once(text, "HAIR_SCRIPTS = os.path.join(RL, 'scripts', 'hair')", "HAIR_SCRIPTS = os.path.join(TOOLS, 'hair')")
        text = replace_once(text, "CONTROLS_JSON = os.path.join(RL, 'specs', 'controls.json')",
                            "CONTROLS_JSON = os.path.join(TOOLS, 'specs', 'controls.json')")
    if rel == 'fit/synth/synthlib.py':
        text = replace_once(text, "RL = os.path.normpath(os.path.join(HERE, '..', '..', '..'))            # .local/rl-heads\n"
                            "HAIR = os.path.join(RL, 'scripts', 'hair')\n"
                            "SPECS = os.path.join(RL, 'specs')\n",
                            "TOOLS = os.path.normpath(os.path.join(HERE, '..', '..'))               # eloria-assets/tools/rl_heads\n"
                            "RL = os.path.abspath(os.environ.get('RL_HEADS_LOCAL') or\n"
                            "                     os.path.join(TOOLS, '..', '..', '..', '.local', 'rl-heads'))\n"
                            "HAIR = os.path.join(TOOLS, 'hair')\n"
                            "SPECS = os.path.join(TOOLS, 'specs')\n")
        text = replace_once(text, "WORKTREE = os.path.normpath(os.path.join(RL, '..', '..'))",
                            "WORKTREE = os.path.normpath(os.path.join(TOOLS, '..', '..', '..'))")
        text = replace_once(text, "FITTER = os.path.join(RL, 'scripts', 'fit', 'fit_reference.py')",
                            "FITTER = os.path.join(TOOLS, 'fit', 'fit_reference.py')")
    if rel == 'fit/gaptargets.py':
        text = replace_once(text, "sp = os.path.join(RL, 'scripts')", "sp = TOOLS")
        if 'TOOLS' not in text.split('def ')[0]:
            text = text.replace('from fitcommon import ', 'from fitcommon import TOOLS, ', 1) \
                if 'from fitcommon import ' in text else text
    text = text.replace("'assets', 'actors', 'rl_heads'", "'assets', 'actors', 'native', 'rl_heads'")
    # The RL head assets ship under assets/actors/native/ (tools/package_client.py).
    text = text.replace("/assets/actors/rl_heads/", "/assets/actors/native/rl_heads/")
    text = text.replace("/assets/actors/rl_head_textures/", "/assets/actors/native/rl_head_textures/")
    # The hair tools have their own hair/paths.py, imported as `paths` there.
    if 'paths.' in text and not rel.startswith('hair/') and not re.search(r'^\s*import paths\b', text, re.M):
        match = re.search(r'^(import |from )(?!__future__)', text, re.M)
        at = match.start() if match else 0
        up = '' if depth == 0 else ", " + ", ".join(["'..'"] * depth)
        prelude = ('import os as _o, sys as _s\n'
                   f"_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)){up})))"
                   '  # paths.py (Blender runs need this)\n'
                   'import paths  # repository-relative locations\n')
        text = text[:at] + prelude + text[at:]
    return text


def hair_paths_rewrite(text: str) -> str:
    # In the repository the hair tools sit at eloria-assets/tools/rl_heads/hair:
    # the authoring area and the worktree default to the repository's own.
    text = text.replace("(default: two levels above this file, i.e. .local/rl-heads when the\n"
                        "                 scripts live in .local/rl-heads/scripts/hair)",
                        "(default: <repo>/.local/rl-heads, or RL_HEADS_LOCAL)")
    text = text.replace("(default: two levels above RL_HEADS_ROOT)", "(default: this repository)")
    text = text.replace("RL_ROOT = os.path.abspath(os.environ.get('RL_HEADS_ROOT') or os.path.join(HERE, '..', '..'))",
                        "_REPO = os.path.normpath(os.path.join(HERE, '..', '..', '..', '..'))\n"
                        "RL_ROOT = os.path.abspath(os.environ.get('RL_HEADS_ROOT') or os.environ.get('RL_HEADS_LOCAL')\n"
                        "                          or os.path.join(_REPO, '.local', 'rl-heads'))")
    text = text.replace("WORKTREE = os.path.abspath(os.environ.get('RL_WORKTREE') or os.path.join(RL_ROOT, '..', '..'))",
                        "WORKTREE = os.path.abspath(os.environ.get('RL_WORKTREE') or _REPO)")
    assert '_REPO' in text, 'hair/paths.py layout changed; update hair_paths_rewrite'
    return text


def markdown_rewrite(rel: str, text: str) -> str:
    for wt in AUTHORED_WORKTREES:
        text = text.replace(f'`RL` = `{wt}/.local/rl-heads`.',
                            '`RL/scripts/` = `eloria-assets/tools/rl_heads/`; the inputs and outputs stay in the '
                            'ignored local authoring area `.local/rl-heads` (`RL_HEADS_LOCAL`).')
    text = text.replace('python RL/scripts/', 'python eloria-assets/tools/rl_heads/')
    text = text.replace("was supplied to these tools as an authoring input from the project's image generation, "
                        "reportedly through the Codex image connection; I have not verified a receipt. Record or "
                        "confirm its generation receipt before publishing the derived texture.",
                        "was generated with gpt-image-bridge (Codex image generation through the owner's "
                        "ChatGPT connection, authorised in the owner's brief) on 2026-10-27; its receipt "
                        "(SHA-256, time, prompt, size) is in `../generated_textures.json`.")
    text = text.replace('Everything here is local\nauthoring tooling under the ignored `.local/rl-heads/` tree.',
                        'The tools are committed here;\ntheir inputs and outputs stay in the ignored '
                        '`.local/rl-heads/` tree.')
    text = text.replace('All inputs live under the RL head authoring area, `RL_HEADS_ROOT` (default:\n'
                        'two levels above this folder, i.e. `.local/rl-heads`). None of them is committed.',
                        'All inputs live under the RL head authoring area, `RL_HEADS_ROOT` (default:\n'
                        "`RL_HEADS_LOCAL`, else the repository's `.local/rl-heads`). None of them is committed.")
    return text


def shell_rewrite(rel: str, text: str) -> str:
    up = '/'.join(['..'] * rel.count('/')) or '.'
    lines = text.split('\n')
    head = 1 if lines and lines[0].startswith('#!') else 0
    lines.insert(head, (SHELL_PRELUDE % up).rstrip('\n'))
    text = '\n'.join(lines)
    for wt in AUTHORED_WORKTREES:
        text = text.replace(f'{wt}/.local/rl-heads/scripts/', '$TOOLS/')
        text = text.replace(f'{wt}/.local/rl-heads/scripts', '$TOOLS')
        text = text.replace(f'{wt}/.local/rl-heads', '$LOCAL')
        text = text.replace(f'{wt}/godot-client', '$REPO/godot-client')
        text = text.replace(wt, '$REPO')
    text = text.replace('R=$LOCAL\n', 'R=$LOCAL\n')
    text = text.replace('$R/scripts/', '$TOOLS/').replace('$M/scripts/', '$(cygpath -m "$TOOLS")/')
    text = text.replace(f'"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe"', '"${BLENDER:-blender}"')
    text = text.replace(GODOT_EXE, '${GODOT:-godot}')
    text = text.replace(GPU_LOCK, '${RL_GPU_LOCK:-}')
    text = text.replace(PYTHON_EXE, '"${PYTHON:-python}"')
    return text


def generated_textures(path: str) -> str:
    """The generation receipts of the authoring textures in gen/ (provenance.json),
    without the local command lines: file, SHA-256, time, generator, prompt, size."""
    import json
    record = json.load(open(path, encoding='utf-8'))
    images = {}
    for name, entry in sorted(record.get('images', {}).items()):
        command = str(entry.get('command_with_prompt', ''))
        prompt = re.search(r'gpt-image-2 "((?:[^"\\]|\\.)*)"', command)
        size = re.search(r'--size (\d+x\d+)', command)
        images[name] = {'file': 'gen/' + os.path.basename(str(entry.get('file', name + '.png'))),
                        'sha256': entry.get('sha256'), 'generated_at': entry.get('generated_at'),
                        'prompt': prompt.group(1) if prompt else None, 'size': size.group(1) if size else None}
    return json.dumps({'generated_by': 'gpt-image-bridge (Codex image generation through the owner\'s ChatGPT '
                       'connection), authorised in the owner\'s brief for these textures',
                       'location': 'the ignored local authoring area, .local/rl-heads/gen/',
                       'images': images}, indent=1) + '\n'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--source', default=os.environ.get('RL_HEADS_SCRIPTS')
                        or os.path.join(REPO, '.local', 'rl-heads', 'scripts'))
    args = parser.parse_args()
    source = os.path.abspath(args.source)
    local = os.path.dirname(source)
    if not os.path.isdir(source):
        sys.exit(f'no authoring scripts at {source}')
    written = []
    for folder, dirs, files in os.walk(source):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name in SKIP_FILES or name.endswith(SKIP_SUFFIXES):
                continue
            src = os.path.join(folder, name)
            rel = os.path.relpath(src, source).replace(os.sep, '/')
            text = open(src, encoding='utf-8').read()
            if rel == 'hair/paths.py':
                text = hair_paths_rewrite(text)
            elif name.endswith('.py'):
                text = python_rewrite(rel, text)
            elif name.endswith('.sh'):
                text = shell_rewrite(rel, text)
            elif name.endswith('.md'):
                text = markdown_rewrite(rel, text)
            written.append((rel, text))
    for src_rel, dst_rel in SPECS.items():
        src = os.path.join(local, src_rel)
        if os.path.exists(src):
            written.append((dst_rel, open(src, encoding='utf-8').read()))
    # The head build specs (make_spec.py output, build_head.py input). Their
    # macro stack path is opened relative to the working directory: this folder.
    import json
    for sex, lab in (('female', 'mira6'), ('male', 'rowan4')):
        spec_path = os.path.join(local, 'specs', f'{sex}_v1.json')
        macro_path = os.path.join(local, 'specs', f'{sex}_v1.macro.json')
        if not (os.path.exists(spec_path) and os.path.exists(macro_path)):
            continue
        spec = json.load(open(spec_path, encoding='utf-8'))
        spec['macro'] = f'specs/{sex}_v1.macro.json'
        spec['source'] = f'specs/likeness_{sex}.json (lab/{lab}/spec.json)'
        written.append((f'specs/{sex}_v1.json', json.dumps(spec, indent=1) + '\n'))
        written.append((f'specs/{sex}_v1.macro.json', open(macro_path, encoding='utf-8').read()))
    written.append(('paths.py', PATHS_PY))
    provenance = os.path.join(local, 'gen', 'provenance.json')
    if os.path.exists(provenance):
        written.append(('generated_textures.json', generated_textures(provenance)))
    problems = []
    for rel, text in written:
        if not text.strip():
            problems.append(f'{rel}: empty')
        for match in FORBIDDEN.finditer(text):
            line = text.count('\n', 0, match.start()) + 1
            problems.append(f'{rel}:{line}: machine-specific or secret reference {match.group(0)!r}')
    if problems:
        sys.exit('refusing to sync:\n  ' + '\n  '.join(problems))
    keep = {'README.md', 'sync_from_local.py'}
    for entry in os.listdir(HERE):
        if entry in keep:
            continue
        path = os.path.join(HERE, entry)
        shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
    for rel, text in written:
        dst = os.path.join(HERE, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
    print(f'synced {len(written)} files from {source} to {HERE}')


if __name__ == '__main__':
    main()
