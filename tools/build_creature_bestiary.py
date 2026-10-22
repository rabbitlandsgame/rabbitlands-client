"""Build the standalone public bestiary from the current sibling server.

Portraits use the active client models and the maintained offline renderer.
Only public creature, map and loot definitions are read from the server.
Source models and runtime assets are never written.

    python tools/build_creature_bestiary.py
"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import hashlib
import io
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SERVER = ROOT.parent / "rabbitlands-server"
CACHE = ROOT / ".local/asset-authoring/working/bestiary-20261021/portraits"
TEMPLATE = ROOT / "tools/bestiary/template.html"
OUTPUT = ROOT / "docs/bestiary/creatures.html"
PORTRAIT_SIZE = 160
PORTRAIT_VERSION = "bestiary-portrait-v1"
FAMILY_NAMES = {
    "beast": "Wildlife", "humanoid": "Humanoids", "avian": "Birds",
    "construct": "Constructs", "aquatic": "Aquatic life", "undead": "Undead",
    "insect": "Insects", "canine": "Hounds & wolves", "crustacean": "Shellfish",
    "feline": "Big cats", "draconic": "Dragons & kin", "reptile": "Reptiles",
    "spirit": "Spirits", "cervine": "Deer & antelope", "plant": "Forest folk",
    "ursine": "Bears", "vulpine": "Foxes",
}


def load_catalog(server: Path) -> tuple[list[dict], list[dict]]:
    sys.path.insert(0, str(server))
    from eloria.creatures import load_creatures
    from eloria.drops import load_drops
    from eloria.maps import load_maps
    from eloria.spawns import load_spawns
    from eloria.recipes import load_recipes
    from eloria.stats import MAX_SKILL_LEVEL
    from tools.generate_drops import family_of, load_families

    profile = server / "config/eloria"
    creatures = load_creatures(profile / "creatures.txt")
    drops = load_drops(profile / "drops.txt")
    maps, _ = load_maps(str(profile / "maps.txt"))
    spawns = load_spawns(profile / "spawns.txt")
    summons = {r.summon for r in load_recipes(profile / "recipes.txt") if r.summon}
    families = load_families(profile / "drop_families.txt")
    extents = json.loads((server / "tools/creature_extents.json").read_text(encoding="utf-8"))["extents"]
    registry = json.loads((ROOT / "godot-client/data/actors/models.json").read_text())
    retired = set(json.loads((ROOT / "godot-client/data/assets/retired_procedural_models.json").read_text())["runtimePaths"])
    models = {}
    rows = []

    def map_name(key: str) -> str:
        return maps[key].name if key in maps else key.replace("_", " ").title()

    for key, c in sorted(creatures.items(), key=lambda pair: pair[1].name.casefold()):
        model_key = registry["actorTypes"][str(c.actor_type)]
        model = registry["models"][model_key]
        relative = model["scene"].removeprefix("res://")
        if relative.removeprefix("assets/") in retired:
            raise ValueError(f"Retired portrait source: {model_key}")
        source = ROOT / "godot-client" / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        if model_key not in models:
            models[model_key] = {"key": model_key, "path": str(source),
                                 "index": len(models)}
        placements = [s for s in spawns if s.creature == key]
        field = sorted({map_name(s.map_id) for s in placements
                        if not s.tame and not s.map_id.endswith("_secrets")})
        training = sorted({map_name(s.map_id) for s in placements
                           if not s.tame and s.map_id.endswith("_secrets")})
        tame = sorted({map_name(s.map_id) for s in placements if s.tame})
        aggressive = c.raw.get("aggressive", "0").casefold() in {"1", "true", "yes", "on"}
        group = "special" if c.boss or not field else "aggressive" if aggressive else "passive"
        availability = "Named boss" if c.boss else "Field creature" if field else "Livestock" if tame else "Encounter catalog"
        base = next((other.name for other in creatures.values()
                     if not other.boss and c.boss and other.actor_type == c.actor_type), "")
        family = family_of(c, families).name
        extent = extents.get(str(c.actor_type))
        size_factor = c.scale * float(model.get("import", {}).get("scale", 1.0))
        row = {
            "id": key, "name": c.name, "attack": c.attack, "defense": c.defense,
            "average": (c.attack + c.defense) / 2, "level": c.level,
            "health": c.material_points, "ether": c.ethereal_points,
            "damage": [c.effective_damage_min, c.effective_damage_max],
            "armor": [c.armor_min, c.armor_max], "attributes": c.attributes,
            "range": c.attack_range, "poison": c.poison_damage,
            "size": ({axis: round(float(extent[axis]) * size_factor, 2)
                      for axis in ("width", "depth", "height")} if extent else None),
            "footprint": [c.footprint.width, c.footprint.depth],
            "aggressive": aggressive, "boss": c.boss, "base": base,
            "family": FAMILY_NAMES.get(family, family.title()),
            "group": group, "availability": availability,
            "fieldMaps": field, "trainingMaps": training, "tameMaps": tame,
            "summonable": key in summons, "portrait": models[model_key]["index"],
            "endgame": not c.boss and min(c.attack, c.defense) >= MAX_SKILL_LEVEL,
            "aboveCap": min(c.attack, c.defense) > MAX_SKILL_LEVEL,
            "cutoffs": {name: int(c.raw[name]) for name in
                        ("ignore_defense", "ignore_attack", "ignore_combat") if name in c.raw},
            "drops": [{"item": d.item, "min": d.minimum, "max": d.maximum,
                       "chance": d.chance, "rare": d.rare} for d in drops[key]],
        }
        rows.append(row)
    return rows, list(models.values())


def render_portrait(model: dict) -> tuple[int, Path]:
    sys.path.insert(0, str(ROOT / "eloria-assets/tools"))
    import render_creature_qa as renderer
    path = Path(model["path"])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    signature = hashlib.sha256((digest + PORTRAIT_VERSION).encode()).hexdigest()[:24]
    target = CACHE / f"{signature}.webp"
    if not target.exists():
        document, binary = renderer.read_glb(path)
        names = {clip.get("name", "") for clip in document.get("animations", [])}
        clip = next((name for name in ("Idle_A", "Idle", "idle", "Fighting_Idle") if name in names), None)
        batches = renderer.gather(document, binary, clip=clip, time=.2)
        low, high = renderer.model_bounds(batches)
        centre = (low + high) / 2
        half = (high - low) * .57
        image = renderer.render(batches, PORTRAIT_SIZE, 35, 14,
                                (centre - half, centre + half))
        image.save(target, "WEBP", quality=83, method=6)
    return model["index"], target


def build_portraits(models: list[dict]) -> tuple[str, int, int]:
    from PIL import Image
    CACHE.mkdir(parents=True, exist_ok=True)
    columns = 16
    rows = math.ceil(len(models) / columns)
    atlas = Image.new("RGB", (columns * PORTRAIT_SIZE, rows * PORTRAIT_SIZE), "#353c39")
    # Lift studio exposure so dark coats remain legible at table-icon size.
    exposure = [round(255 * (value / 255) ** .82) for value in range(256)] * 3
    # The renderer is read-only and each worker has a distinct output hash.
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(render_portrait, model) for model in models]
        for count, job in enumerate(as_completed(jobs), 1):
            index, path = job.result()
            with Image.open(path) as image:
                atlas.paste(image.convert("RGB").point(exposure), ((index % columns) * PORTRAIT_SIZE,
                                   (index // columns) * PORTRAIT_SIZE))
            if count % 24 == 0 or count == len(models):
                print(f"Portraits {count}/{len(models)}", flush=True)
    encoded = io.BytesIO()
    atlas.save(encoded, "WEBP", quality=84, method=6)
    return base64.b64encode(encoded.getvalue()).decode(), columns, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, default=DEFAULT_SERVER)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()
    rows, models = load_catalog(args.server.resolve())
    atlas, columns, portrait_rows = build_portraits(models)
    if args.render_only:
        print(f"Cached {len(models)} current-model portraits.")
        return
    payload = {"date": args.date, "playerCap": 200, "columns": columns,
               "portraitRows": portrait_rows, "creatures": rows}
    # HTML-safe JSON also handles future authored names containing markup.
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = TEMPLATE.read_text(encoding="utf-8").replace("__CREATURE_DATA__", data).replace("__PORTRAIT_ATLAS__", atlas)
    if "__CREATURE_DATA__" in html or "__PORTRAIT_ATLAS__" in html:
        raise RuntimeError("Unresolved template marker")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8", newline="\n")
    print(f"{len(rows)} creatures, {len(models)} portraits -> {args.output}")
    print(f"Standalone HTML: {args.output.stat().st_size / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
