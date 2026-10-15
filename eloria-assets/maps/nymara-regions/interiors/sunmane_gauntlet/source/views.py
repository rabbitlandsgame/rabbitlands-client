"""Repeatable player-height and isometric views of the Red Canyon."""
import argparse
import json
from pathlib import Path

def views(manifest):
    out = []
    for key in ("staging", "wind-cut", "horse-cave", "ridge-path", "scree-stair",
                "forked-wash-hub", "forked-wash-shade-fork", "forked-wash-sun-fork",
                "long-wash", "sun-court", "vault"):
        s = manifest["spaces"][key]
        x, z = (s["x0"] + s["x1"]) / 2, (s["z0"] + s["z1"]) / 2
        y = s["floor"] + (3 if key == "ridge-path" else 0)
        out.append({"id": key, "title": key.replace("-", " ").title(),
                    "eye": [x, y + 2.1, s["z0"] + 2.4],
                    "target": [x, y + 2, s["z1"] - 2], "fov": 66})
        if key not in ("ridge-path", "long-wash", "vault"):
            out.append({"id": key + "-iso", "title": key.replace("-", " ").title() + " / isometric",
                        "eye": [x + 16, y + 23, z - 18], "target": [x, y, z], "fov": 62})
    for key, name, title, eye, target in [
        ("ridge-path", "ridge-support", "Stone spine across the dry ravine", (16, 5.2, 2), (9, 2.4, 14)),
        ("horse-cave", "herd-shelter", "Shelter beneath the undercut bank", (14, 2.3, 3), (3, 2, 12)),
        ("sun-court", "split-crown", "Split crown above the final court", (16, 3, 9), (16, 12, 28))
    ]:
        s = manifest["spaces"][key]
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
