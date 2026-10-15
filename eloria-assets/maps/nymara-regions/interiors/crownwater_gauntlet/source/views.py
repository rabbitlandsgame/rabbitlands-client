"""Repeatable views of Crownwater's Drowned Arcades."""
import argparse
import json
from pathlib import Path

def views(manifest):
    spaces = manifest["spaces"]
    keys = ["staging", "customs-arcade", "bell-walk", "cistern", "long-arcade",
            "two-sluices-hub", "two-sluices-north-sluice", "two-sluices-south-sluice",
            "campanile-stair", "bell-court", "vault"]
    out = []
    for key in keys:
        s = spaces[key]
        x, z = (s["x0"] + s["x1"]) / 2, (s["z0"] + s["z1"]) / 2
        y = s["floor"] + (3 if key == "bell-walk" else 0)
        out.append({"id": key, "title": key.replace("-", " ").title(),
                    "eye": [x, y + 2.1, s["z0"] + 2.4],
                    "target": [x, y + 2, s["z1"] - 2], "fov": 66})
        if key not in ("bell-walk", "long-arcade", "campanile-stair", "vault"):
            out.append({"id": key + "-iso", "title": key.replace("-", " ").title() + " / isometric",
                        "eye": [x + 15, y + 21, z - 18], "target": [x, y, z], "fov": 62})
    for key, name, title, eye, target in [
        ("customs-arcade", "cargo-bay", "Raised cargo inspection bay", (6, 2.4, 3), (2.4, 1.1, 8)),
        ("cistern", "sluice-machinery", "Cistern sluice and screw lift", (9, 2.6, 6), (2.0, 1.8, 11)),
        ("bell-court", "great-bell", "Bell above the court", (16, 3.5, 18), (16, 6.5, 28)),
        ("bell-walk", "causeway-arches", "Masonry supporting the Bell Walk", (15, 4.8, 2), (9, 2.2, 13))
    ]:
        s = spaces[key]
        out.append({"id": name, "title": title, "fov": 62,
                    "eye": [s["x0"] + eye[0], s["floor"] + eye[1], s["z0"] + eye[2]],
                    "target": [s["x0"] + target[0], s["floor"] + target[1], s["z0"] + target[2]]})
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    target = args.package / "references/captures/index.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(views(json.loads((args.package / "world.json").read_bytes())), indent=2) + "\n").encode())
