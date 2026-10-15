"""Write consistent eye-level and isometric cameras for an authored gauntlet."""
import argparse
import json
from pathlib import Path


def views(manifest):
    spaces = manifest["spaces"]
    keys = ["staging", "undercut", "root-cellar", "sap-bridge", "stump-stair",
            "twin-hollows-hub", "twin-hollows-wet-hollow", "twin-hollows-dry-hollow",
            "lantern-walk", "boar-court", "vault"]
    # The Resin Road's room IDs are design data, not a new camera convention.
    out = []
    for key in keys:
        s = spaces[key]
        x, z = (s["x0"] + s["x1"]) / 2, (s["z0"] + s["z1"]) / 2
        y = s["floor"] + (3 if key == "sap-bridge" else 0)
        out.append({"id": key, "title": key.replace("-", " ").title(),
                    "eye": [x, y + 2.1, s["z0"] + 2.4],
                    "target": [x, y + 2, s["z1"] - 2], "fov": 66})
        if key in ("staging", "root-cellar", "twin-hollows-hub",
                   "twin-hollows-wet-hollow", "twin-hollows-dry-hollow",
                   "lantern-walk", "boar-court"):
            out.append({"id": key + "-iso", "title": key.replace("-", " ").title() + " / isometric",
                        "eye": [x + 15, y + 21, z - 18], "target": [x, y, z], "fov": 62})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    destination = args.package / "references/captures/index.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes((json.dumps(views(json.loads((args.package / "world.json").read_bytes())), indent=2) + "\n").encode())
