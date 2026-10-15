"""Write nymara-regions/SECRETS.md from the twelve secrets design tables.

Run after a design changes: `python _toolkit/secrets_doc.py` from anywhere.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "_toolkit"))
import secretrooms as SR  # noqa: E402

REGIONS = ("amberwood", "mirrorhold", "amethyst_barrens", "crownwater", "westhaven", "grey_moors",
           "manymouth_delta", "verdant_stair", "whitehorn_range", "ssarathi_ruins", "sunmane_steppe",
           "four_gates")
KIND_WHAT = {
    "grotto": "richer harvest hollow", "garden": "harvest beds, harvest_speed x2",
    "cache": "storage chest + bench beside nodes", "vault": "experience x2, storage, bench",
    "pen": "training chamber, chosen spawn", "school": "fast_reading x3, lore plaques",
    "spring": "fast_regeneration x3", "range": "ranging gallery, slow targets, experience x2",
    "reliquary": "lore plaques, keyed", "nullwell": "no_magic, spawn", "focus": "cheap_magic x2",
    "tunnel": "passage under the border to a neighbour", "waystone": "hub: stones to other hubs",
    "eyrie": "cistern, mechanics plaques, fast_regeneration x2", "mouth": "far end of a neighbour's tunnel",
}


def load(region):
    path = ROOT / region / "source" / "secrets_design.py"
    if not path.is_file():
        path = ROOT / "_toolkit" / "designs" / f"{region}_secrets_design.py"
    spec = importlib.util.spec_from_file_location(f"{region}_design", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    return module


lines = ["# The secrets", "",
         "Every exterior map has a `<region>_secrets` map: its hidden rooms, entered by",
         "*using* a feature of the ground above (a loose stone, a hollow tree, a crack in",
         "the ice), some only with an item in the pack. Inside a secret the client draws",
         "only that secret; the rest of the map, the minimap and the full map stay black.",
         "The rooms come from `_toolkit/secretrooms.py`, the maps from",
         "`_toolkit/secrets_build.py`, the entrances from `_toolkit/secretdoors.py` (or",
         "Sunmane's own kit, or the hand-declared list for Four Gates), and the server's",
         "portals, interactives, spawns, nodes and areas from",
         "`eloria-assets/tools/secret_doors.py` through the continent portal tool and the",
         "content tool's `secrets` stage. `design` tables live in each region's",
         "`source/secrets_design.py`.", "",
         "## Kinds", "", "| kind | what it gives |", "|---|---|"]
for kind, what in KIND_WHAT.items():
    lines.append(f"| {kind} | {what} |")
lines += ["", "## Entrances", "", "| prop | what a player reads |", "|---|---|"]
for prop, text in SR.ENTRANCES.items():
    lines.append(f"| {prop} | {text} |")
total = 0
for region in REGIONS:
    design = load(region)
    lines += ["", f"## {design.NAME}", "", "| secret | kind | entrance | key | contents |", "|---|---|---|---|---|"]
    for s in design.SECRETS:
        total += 1
        where = s.at if isinstance(s.at, str) else (f"({s.at[0]:.0f}, {s.at[1]:.0f})" if s.at else "-")
        if s.door_map:
            where = f"{s.door_map}: {s.door_space}"
        parts = []
        if s.resources:
            parts.append("nodes: " + ", ".join(f"{r} x{n}" for r, n in s.resources))
        if s.creatures:
            parts.append("spawn: " + ", ".join(f"{c} x{n}" for c, n in s.creatures))
        if s.area:
            parts.append(f"area: {s.area[0]} x{s.area[1]}")
        elif s.kind in ("garden", "vault", "school", "spring", "range", "nullwell", "focus", "eyrie"):
            parts.append("area: default for its kind")
        if s.texts:
            parts.append(f"{len(s.texts)} plaques")
        if s.links:
            parts.append("links: " + ", ".join(l[0] for l in s.links))
        lines.append(f"| **{s.name}** (`{s.id}`) | {s.kind} | {s.entrance} at {where} | {s.key or '-'} | {'; '.join(parts) or '-'} |")
lines += ["", f"{total} secrets in all.", ""]
(ROOT / "SECRETS.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
print("SECRETS.md:", total, "secrets")
