"""Point the Human equipment variants at the textures the shipped equipment already carries.

    python eloria-assets/tools/share_human_equipment_textures.py

refit_human_bodies.py fits from the original Meshy sources, so a variant's art
texture is the full-resolution original of an image the shipped piece already
references as a 1024 px JPEG (the shipped set was shrunk after packing).  For
each image of each `variants/human_*/<slug>.glb`:

* if one of the piece's shipped textures is the same picture (64 px
  thumbnails within 3/255 mean difference), the variant names that file;
* otherwise (the "Fitted cloth" lining, sampled from the new body's shirt) it
  is re-encoded the shipped way - at most 1024 px, JPEG quality 85,
  content-addressed `textures/canonical_<sha>.jpg`.

A piece's shipped textures are the git-tracked `textures/` files named by any
scene the registry gives the piece (its base `scene` and every variant), read
from the working tree and from HEAD.  Since the P7 cleanup (2026-10) the base
scene of every generated piece IS its `variants/human_male` file, and the
old-male base scenes this tool used to match against are gone; reading HEAD
keeps the textures a reinstall has just overwritten in the working tree.  Only
textures at most 1024 px (the shipped size) are candidates, so a full-resolution
image is never "shared" with itself.  Run this after install_human_equipment.py
and before committing: after a commit a piece can only match shipped textures
its other scenes still name, and is otherwise re-encoded (a correct 1024 px
file, but a duplicate of the shipped one).

Only the JSON image entries change; geometry, skin and materials are untouched.
Textures no equipment GLB references any more are deleted if git does not
track them.
"""
from __future__ import annotations

import hashlib
import io
import json
import struct
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
EQUIPMENT = ROOT / 'godot-client/assets/actors/native/equipment'
#: The shipped equipment texture size (shrink_actor_textures.py's equipment cap).
SHIPPED_MAX = 1024


def read(path: Path):
    data = path.read_bytes()
    n = struct.unpack('<I', data[12:16])[0]
    return json.loads(data[20:20 + n]), data[20 + n:]


def write(path: Path, doc: dict, rest: bytes):
    text = json.dumps(doc, separators=(',', ':')).encode()
    text += b' ' * ((4 - len(text) % 4) % 4)
    out = bytearray(struct.pack('<III', 0x46546C67, 2, 0))
    out += struct.pack('<II', len(text), 0x4E4F534A) + text + rest
    struct.pack_into('<I', out, 8, len(out))
    path.write_bytes(bytes(out))


def thumb(path: Path):
    return np.asarray(Image.open(path).convert('RGB').resize((64, 64), Image.BILINEAR)).astype(np.float32)


def _header(data: bytes) -> dict:
    n = struct.unpack('<I', data[12:16])[0]
    return json.loads(data[20:20 + n])


def scene_textures(scene: str, tracked: set[str]) -> list[Path]:
    """Tracked textures one registry scene names, in the working tree and at HEAD."""
    rel = 'godot-client/' + scene.removeprefix('res://')
    path = ROOT / rel
    documents = []
    if path.exists():
        documents.append(_header(path.read_bytes()))
    head = subprocess.run(['git', 'show', f'HEAD:{rel}'], cwd=ROOT, capture_output=True)
    if head.returncode == 0 and head.stdout[:4] == b'glTF':
        documents.append(_header(head.stdout))
    found = []
    for document in documents:
        for image in document.get('images', []):
            if 'uri' not in image:
                continue
            texture = (path.parent / image['uri']).resolve()
            if texture.exists() and texture.relative_to(ROOT.resolve()).as_posix() in tracked:
                found.append(texture)
    return found


def piece_scenes(registry: dict) -> dict[str, list[str]]:
    """Every scene the registry gives a piece, keyed by each of those scenes."""
    scenes = {}
    for model in registry['models'].values():
        named = [model.get('scene', '')] + [v.get('scene', '') for v in model.get('variants', {}).values()]
        named = list(dict.fromkeys(s for s in named if s.startswith('res://')))
        for scene in named:
            scenes.setdefault(scene, [])
            scenes[scene] += [s for s in named if s not in scenes[scene]]
    return scenes


def main() -> int:
    tracked = set(subprocess.check_output(['git', 'ls-files', 'godot-client/assets/actors/native/equipment/textures'],
                                          cwd=ROOT, text=True).split())
    registry = json.loads((ROOT / 'godot-client/data/actors/equipment.json').read_text(encoding='utf-8'))
    pieces = piece_scenes(registry)
    shared = reencoded = 0
    referenced = set()
    for folder in ('human_male', 'human_female'):
        for path in sorted((EQUIPMENT / 'variants' / folder).glob('*.glb')):
            doc, rest = read(path)
            scene = 'res://' + path.relative_to(ROOT / 'godot-client').as_posix()
            candidates = [t for s in pieces.get(scene, [scene]) for t in scene_textures(s, tracked)]
            thumbs = [(p, thumb(p)) for p in dict.fromkeys(candidates)
                      if max(Image.open(p).size) <= SHIPPED_MAX]
            changed = False
            for image in doc.get('images', []):
                current = (path.parent / image['uri']).resolve()
                t = thumb(current)
                match = min(((np.abs(t - bt).mean(), p) for p, bt in thumbs), default=(1e9, None))
                if match[0] < 3.0:
                    target = match[1]
                    shared += 1
                else:
                    im = Image.open(current).convert('RGB')
                    if max(im.size) > 1024:
                        im = im.resize((1024, 1024) if im.width == im.height else
                                       tuple(round(s * 1024 / max(im.size)) for s in im.size), Image.LANCZOS)
                    buf = io.BytesIO(); im.save(buf, 'JPEG', quality=85, optimize=True)
                    data = buf.getvalue()
                    target = EQUIPMENT / 'textures' / ('canonical_' + hashlib.sha256(data).hexdigest() + '.jpg')
                    if not target.exists():
                        target.write_bytes(data)
                    reencoded += 1
                uri = Path('../../textures') / target.name
                referenced.add(target.name)
                if image.get('uri') != uri.as_posix():
                    image['uri'] = uri.as_posix(); image['mimeType'] = 'image/jpeg' if target.suffix == '.jpg' else 'image/png'
                    changed = True
            if changed:
                write(path, doc, rest)
    # Race variants and the other equipment GLBs keep their textures too.
    for path in EQUIPMENT.rglob('*.glb'):
        for image in read(path)[0].get('images', []):
            if 'uri' in image:
                referenced.add((path.parent / image['uri']).resolve().name)
    removed = 0
    for tex in (EQUIPMENT / 'textures').glob('canonical_*'):
        if tex.suffix == '.import':
            continue
        rel = tex.relative_to(ROOT).as_posix()
        if rel in tracked or tex.name in referenced:
            continue
        # untracked and unreferenced by any equipment GLB: a leftover of the raw install
        still_used = False
        if not still_used:
            tex.unlink(); removed += 1
            imp = tex.with_name(tex.name + '.import')
            if imp.exists():
                imp.unlink()
    print(json.dumps({'shared': shared, 'reencoded': reencoded, 'removed_textures': removed}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
