#!/usr/bin/env python3
"""Record stable palette identities and roles from the pinned source kit placements.

Shared libraries outlive their retired map scenes. A model absent from an opened
new scene must still use its original catalog identity and collision role.
Replay from Git history, never from mutable or retired working-tree scenes.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import freeze_continent_v2_terrain as F

OUTPUT = "godot-client/world_authoring/continent-v2/shared-kit-catalog.json"


def most_common(counts):
    return min(counts, key=lambda value: (-counts[value], value))


def build(reader):
    catalog = json.loads(reader.read(F.CATALOG_PATH))
    models = defaultdict(lambda: {"ids": Counter(), "roles": Counter()})
    count = 0
    for entry in catalog["entries"]:
        path = F.git_path(entry["scenePath"])
        scene = F.parse_scene(reader.read(path))
        for node_path, section in scene.nodes.items():
            if not node_path.startswith("AuthoredAssets/"):
                continue
            props = section.properties
            if "catalog_asset_id" not in props or "scene_path" not in props:
                continue
            model = json.loads(props["scene_path"])
            identity = json.loads(props["catalog_asset_id"])
            role = json.loads(props.get("collision_role", '"solid"'))
            if not model.startswith("res://world_authoring/") or not identity or role not in ("solid", "none"):
                raise ValueError(f"invalid shared kit binding: {path}:{node_path}")
            models[model]["ids"][identity] += 1
            models[model]["roles"][role] += 1
            count += 1
    if not models:
        raise ValueError("source catalog contains no authored kit models")
    return F.json_bytes({
        "schema": "eloria-shared-kit-catalog-v1", "sourceCommit": reader.commit,
        "sourceFiles": {path: {"sha256": F.sha256(blob), "bytes": len(blob)}
                        for path, blob in sorted(reader.files.items())},
        "sourcePlacements": count,
        "models": {path: {"catalogAssetId": most_common(record["ids"]),
                          "collisionRole": most_common(record["roles"])}
                   for path, record in sorted(models.items())},
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=F.CHECKOUT)
    parser.add_argument("--source-ref", default=F.SOURCE_REF)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    reader = F.GitInputs(args.checkout, args.source_ref)
    blob = build(reader)
    path = args.checkout / OUTPUT
    if args.check:
        if not path.is_file() or path.read_bytes() != blob:
            raise SystemExit("shared kit catalog is missing or stale")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    print(json.dumps({"mode": "check" if args.check else "write", "sha256": F.sha256(blob),
                      "models": len(json.loads(blob)["models"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
