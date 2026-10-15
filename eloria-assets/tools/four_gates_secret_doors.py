#!/usr/bin/env python3
"""Write the Four Gates secret entrances into `four-gates/world.json`.

    python eloria-assets/tools/four_gates_secret_doors.py [--apply]

Four Gates is not rebuilt by the secrets pass (its build rewrites its
siblings), so the entrances the design table names are declared straight in
the city's manifest as `interactives` of kind `secret`, at the positions the
table gives, with the server tile the city's transform implies. The city's
own street furniture at each spot is the thing a player uses; the server tool
turns each record into a use-to-enter portal.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1]
TOOLKIT = ASSETS / "maps" / "nymara-regions" / "_toolkit"
MANIFEST = ASSETS / "maps" / "four-gates" / "world.json"
sys.path.insert(0, str(TOOLKIT))


def load_design():
    path = TOOLKIT / "designs" / "four_gates_secrets_design.py"
    spec = importlib.util.spec_from_file_location("four_gates_secrets_design", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    import secretrooms as SR
    design = load_design()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    transform = manifest["coordinateTransform"]
    origin = transform["serverOrigin"]
    ground = float(transform.get("walkingHeight", 0.0))
    kept = [e for e in manifest.get("interactives", []) if e.get("kind") != "secret"]
    written = []
    for secret in design.SECRETS:
        x, z = float(secret.at[0]) + secret.offset[0], float(secret.at[1]) + secret.offset[1]
        if secret.kind == "mouth":
            target_map, target_spawn = secret.links[0][0], secret.links[0][1]
        else:
            target_map, target_spawn = "four_gates_secrets", secret.id
        written.append({
            "id": f"secret-{secret.id}", "kind": "secret", "secret": secret.id,
            "name": secret.name, "label": SR.label_for(secret), "prop": secret.entrance,
            "key": secret.key, "destinationMap": target_map, "destinationSpawn": target_spawn,
            "position": [round(x, 2), round(ground, 2), round(z, 2)],
            "serverTile": [int(round(x + origin[0])), int(round(origin[1] - z))],
            "authority": "server",
            "note": "declared by tools/four_gates_secret_doors.py from the secrets design",
        })
    manifest["interactives"] = kept + written
    print(f"{len(written)} secret entrances for Four Gates")
    for entry in written:
        print(f"  {entry['id']:32s} tile {entry['serverTile']} -> {entry['destinationMap']}/{entry['destinationSpawn']}")
    if args.apply:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
