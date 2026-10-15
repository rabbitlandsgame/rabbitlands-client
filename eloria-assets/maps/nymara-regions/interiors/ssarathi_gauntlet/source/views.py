"""Repeatable eye-level and isometric views of Ssarathi's Coil Causeway."""
import argparse
import json
from pathlib import Path

def views(manifest):
    spaces = manifest["spaces"]
    keys = ["staging", "water-gate", "lily-causeway", "hatchery", "serpent-gallery",
            "two-mouths-hub", "two-mouths-wet-mouth", "two-mouths-carved-mouth",
            "sun-stair", "coiled-court", "vault"]
    out = []
    for key in keys:
        s = spaces[key]
        x, z = (s["x0"] + s["x1"]) / 2, (s["z0"] + s["z1"]) / 2
        y = s["floor"] + (3 if key == "lily-causeway" else 0)
        out.append({"id": key, "title": key.replace("-", " ").title(),
                    "eye": [x, y + 2.1, s["z0"] + 2.4],
                    "target": [x, y + 2, s["z1"] - 2], "fov": 66})
        if key not in ("lily-causeway", "serpent-gallery", "sun-stair", "vault"):
            out.append({"id": key + "-iso", "title": key.replace("-", " ").title() + " / isometric",
                        "eye": [x + 15, y + 21, z - 18], "target": [x, y, z], "fov": 62})
    s = spaces["hatchery"]
    out.extend([
        {"id": "hatchery-nests", "title": "Dry incubation beds", "fov": 62,
         "eye": [s["x0"] + 7.5, s["floor"] + 2.1, s["z0"] + 3.0],
         "target": [s["x0"] + 3.2, s["floor"] + .7, s["z0"] + 5.0]},
        {"id": "hatchery-pool", "title": "Lily trough and wall supply", "fov": 62,
         "eye": [s["x1"] - 7.5, s["floor"] + 2.1, s["z0"] + 8.0],
         "target": [s["x1"] - 1.3, s["floor"] + .6, (s["z0"] + s["z1"]) / 2]}
    ])
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    target = args.package / "references/captures/index.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(views(json.loads((args.package / "world.json").read_bytes())), indent=2) + "\n").encode())
