"""Seat The Gull Skerries' kit in its territory kit: the isle kit's pieces it reuses.

The Gull Skerries (`gull_skerries`, the island group's third map: the south tip, its two islets and the west cliff
strip) are dressed with the south-west isle's own nature and coast pieces at the isle's rules (adjacent-map design
sections 10 and 15, phase 5: no new model). Each piece becomes a territory prototype
(`godot-client/world_authoring/regions/gull_skerries/assets/prototypes/kit-*.glb`), which the Territories palette
offers when The Gull Skerries is open. Every one is copied byte for byte from sw_isle's prepared kit
(`world_authoring/regions/sw_isle/assets/prototypes`, written by `sw_isle/source/prepare_meshy_kit.py`), with the
content-addressed textures it references, so a broadleaf tree, a coastal boulder or the N18 cliff face is the same
object on all three maps, and the 33 placements the D2b window shift handed over from sw_isle keep their exact
models. git and the client's shared image pool store the bytes once.

`python prepare_meshy_kit.py` writes the kit and `prepare-meshy-kit.json` (the SHA-256 of every input and output);
`--check` confirms the committed files are what the recorded inputs produce.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parents[4]
REGIONS = CLIENT / "godot-client/world_authoring/regions"
PROTOTYPES = REGIONS / "gull_skerries/assets/prototypes"
TEXTURES = PROTOTYPES.parent / "textures"
SOURCE_KIT = REGIONS / "sw_isle/assets/prototypes"
RECORD = HERE / "prepare-meshy-kit.json"

# Pieces copied from sw_isle's prepared kit, by use.
SHARED = [
    # trees: the isle's canopy mix (forest interior, steep forest, the coastal belt, backshore palms, lone trees)
    "sw-broadleaf-tree-a", "sw-broadleaf-tree-b", "beach-palm-tree-1", "beach-palm-tree-2", "beach-palm-tree-3",
    "beach-palm-tree-4", "fan-palm-tree-1", "olive-tree-2", "cypress-tree-1", "umbrella-pine-tree-1", "flame-tree-1",
    "tree-fern-1", "tree-fern-2", "flower-shrub-1", "flower-shrub-2", "flower-shrub-3",
    # ground cover
    "flower-meadow-1", "flower-meadow-2", "flower-meadow-3", "flower-meadow-4", "undergrowth-1", "undergrowth-2",
    "undergrowth-3", "undergrowth-4", "undergrowth-5", "jungle-undergrowth-1", "jungle-undergrowth-2",
    "beach-flower-mat-1", "dune-grass-1", "dune-grass-2",
    # coast and rock: cliff-foot rocks and boulders, sea stacks, beach wrack, and the N18 cliff face the window
    # shift handed over (its N19 corner for the skerries' rocky points)
    "coastal-rock-1", "coastal-rock-2", "coastal-rock-3", "coastal-boulders-1", "coastal-boulders-2",
    "coastal-boulders-3", "coastal-boulders-4", "sea-stack-1", "sea-stack-2", "beach-rocks-1", "driftwood-1",
    "driftwood-2", "kelp-wrack-1", "shell-scree-1", "sw-sea-cliff-face", "sw-sea-cliff-corner",
]


def shared(name: str) -> tuple[Path, bytes, dict[str, bytes]]:
    """A piece of the isle kit: its prepared prototype's bytes and the texture files it references."""
    source = SOURCE_KIT / f"kit-{name}.glb"
    payload = source.read_bytes()
    length = int.from_bytes(payload[12:16], "little")
    document = json.loads(payload[20:20 + length])
    textures = {}
    for image in document.get("images", []):
        uri = image.get("uri", "")
        match = re.fullmatch(r"\.\./textures/([0-9a-f]{64}\.(?:png|jpg))", uri)
        if not match:
            raise ValueError(f"{source.name}: image {uri!r} is not a content-addressed territory texture")
        textures[match.group(1)] = (source.parent.parent / "textures" / match.group(1)).read_bytes()
    return source, payload, textures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify, do not write")
    args = parser.parse_args()
    record = {"schema": "eloria-prepared-kit-v1", "tool": "prepare_meshy_kit.py", "models": {}}
    stale = []
    if not args.check:
        PROTOTYPES.mkdir(parents=True, exist_ok=True)
        TEXTURES.mkdir(parents=True, exist_ok=True)
    for name in sorted(SHARED):
        source, payload, textures = shared(name)
        entry = {"kind": "shared", "source": source.relative_to(CLIENT).as_posix(),
                 "input": hashlib.sha256(payload).hexdigest()}
        target = PROTOTYPES / f"kit-{name}.glb"
        entry.update({"output": hashlib.sha256(payload).hexdigest(), "textures": sorted(textures)})
        record["models"][name] = entry
        if args.check:
            if not target.exists() or target.read_bytes() != payload or any(
                    not (TEXTURES / file).exists() or (TEXTURES / file).read_bytes() != data
                    for file, data in textures.items()):
                stale.append(name)
            continue
        # unchanged files are not rewritten, so the editor does not re-import them
        if not target.exists() or target.read_bytes() != payload:
            target.write_bytes(payload)
            print(f"{target.name}: {len(payload) // 1024} KB, {len(textures)} texture(s)", flush=True)
        for file, data in textures.items():
            if not (TEXTURES / file).exists() or (TEXTURES / file).read_bytes() != data:
                (TEXTURES / file).write_bytes(data)
    if args.check:
        recorded = json.loads(RECORD.read_text(encoding="utf-8")) if RECORD.exists() else {}
        if recorded != record:
            stale.append(RECORD.name)
        expected = {f"kit-{name}.glb" for name in record["models"]}
        extra = sorted(p.name for p in PROTOTYPES.glob("*.glb") if p.name not in expected) \
            if PROTOTYPES.exists() else []
        if extra:
            stale.append("unrecorded prototypes " + ", ".join(extra))
        if stale:
            print("stale: " + ", ".join(stale))
            return 1
        print(f"{len(record['models'])} prototypes match the recorded inputs")
        return 0
    RECORD.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
