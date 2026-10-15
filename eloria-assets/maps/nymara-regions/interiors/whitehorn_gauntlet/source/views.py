"""Repeatable eye-level and isometric views of Whitehorn's Ice Stair."""
import argparse
import json
from pathlib import Path

def views(manifest):
    spaces = manifest["spaces"]
    keys = ["staging", "cascade-cave", "first-riser", "icefall-span", "snowline-hall",
            "twin-crevasses-hub", "twin-crevasses-blue-crevasse", "twin-crevasses-white-crevasse",
            "last-riser", "rime-court", "vault"]
    out = []
    for key in keys:
        s = spaces[key]
        x, z = (s["x0"] + s["x1"]) / 2, (s["z0"] + s["z1"]) / 2
        y = s["floor"] + (3 if key == "icefall-span" else 0)
        out.append({"id": key, "title": key.replace("-", " ").title(),
                    "eye": [x, y + 2.1, s["z0"] + 2.4],
                    "target": [x, y + 2, s["z1"] - 2], "fov": 66})
        if key not in ("icefall-span", "first-riser", "last-riser", "vault"):
            out.append({"id": key + "-iso", "title": key.replace("-", " ").title() + " / isometric",
                        "eye": [x + 15, y + 21, z - 18], "target": [x, y, z], "fov": 62})
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    target = args.package / "references/captures/index.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(views(json.loads((args.package / "world.json").read_bytes())), indent=2) + "\n").encode())
