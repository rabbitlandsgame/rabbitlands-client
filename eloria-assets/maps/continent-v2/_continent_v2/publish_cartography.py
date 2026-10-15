"""publish_cartography.py: the rebuilt continent's tab maps, for the game client's map window.

  python -B eloria-assets/maps/continent-v2/_continent_v2/publish_cartography.py [--check] [--checkout <worktree>]

The client's Tab map and minimap lay a region's own picture under the map cameras when cartography names it (main.gd
_install_map_picture, src/world/map_picture.gd), and draw the neighbours' pictures beside it; without one they show
the live world, and a chunk-streamed isle holds only the chunks round the player. The twelve-territory continent's
cartography is godot-client/data/maps/cartography.json, which eloria-assets/tools/build_continent_map.py derives for
the regions continent-layout.json lays out on that continent's picture. That tool cannot take the continent-v2
territories, and is not edited for them: it lays out only the twelve, and its own bytes are an input the continent's
master atlas certifies (nymara-regions/_continent/cartography/continent-atlas.json), so any edit makes test_cartography
fail until the whole master is rendered again from continent.glb.

So this tool writes their rows to a file of their own, godot-client/data/maps/cartography-continent-v2.json, in the
same shape as cartography.json's regions, and main.gd appends them after that file's rows. One row per territory the
server serves on the continent-v2 frame (registry status continent-v2-served, continentGeography.frame continent-v2),
in registry order:
  name            the package's asset name (the catalog label the registry row carries)
  serverMap       the map id
  frame           "continent-v2": the client compares and draws outlines only within one frame
  tabMap          the package's minimap.webp (render_minimap.py draws it from the chunks), framed as the live Tab map
                  frames the territory (build_continent_map.framing, tab_map_crop, crop_world: imported, never copied)
  continentPolygon, continentLabel   the ownership polygon and its area centroid, in cartography.json's pixel
                  lattice (its continent originMetres and metresPerPixel), so main.gd turns them into the map's metres
                  as it turns every other row's
  globalTranslation   the registry row's continent translation
No row has a continentRect: the isles are not on the twelve-territory continent's picture.
The separate overview object places all regions, including every ownership component, on a Landfall picture
composed from their existing minimaps. Its image-local polygons and row identities drive the clickable overview.

--check exits 1 when the file differs from what this tool writes (godot-client/tests/test_continent_v2_cartography.py
runs it): a picture was redrawn, a frame or polygon moved, cartography.json's lattice changed, or the file was edited
by hand.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import io
import math

from PIL import Image, ImageChops, ImageDraw
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import ownership

DEFAULT_CHECKOUT = Path(__file__).resolve().parents[4]
TOOL = "eloria-assets/maps/continent-v2/_continent_v2/publish_cartography.py"
REGISTRY = "godot-client/data/maps/registry.json"
CARTOGRAPHY = "godot-client/data/maps/cartography.json"
OUTPUT = "godot-client/data/maps/cartography-continent-v2.json"
OVERVIEW = "eloria-assets/maps/continent-v2/_continent_v2/cartography/landfall-map.webp"
FRAME = "continent-v2"
SERVED_STATUSES = {"continent-v2-served"}
SCHEMA = "eloria-cartography-continent-v2-v1"


class CartographyError(ValueError):
    """A served territory this tool cannot give a tab map."""


def read_json(path: Path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def legacy_tool(checkout: Path):
    """eloria-assets/tools/build_continent_map.py of the checkout, imported (its framing rules are map_view.gd's)."""
    source = Path(checkout) / "eloria-assets" / "tools" / "build_continent_map.py"
    spec = importlib.util.spec_from_file_location("build_continent_map_for_v2", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def polygon_centroid(points) -> list[float]:
    """The area centroid of a simple polygon: the label point of a territory."""
    area = cx = cz = 0.0
    for (x0, z0), (x1, z1) in zip(points, list(points[1:]) + list(points[:1])):
        cross = float(x0) * float(z1) - float(x1) * float(z0)
        area += cross
        cx += (float(x0) + float(x1)) * cross
        cz += (float(z0) + float(z1)) * cross
    if abs(area) < 1e-9:
        raise CartographyError("an ownership polygon without area")
    return [cx / (3.0 * area), cz / (3.0 * area)]


def served(registry: dict) -> list[tuple[str, dict]]:
    return [(key, entry) for key, entry in registry.get("maps", {}).items()
            if isinstance(entry, dict) and entry.get("status") in SERVED_STATUSES
            and (entry.get("continentGeography") or {}).get("frame") == FRAME]


def compose(checkout: Path = DEFAULT_CHECKOUT) -> dict:
    checkout = Path(checkout)
    tool = legacy_tool(checkout)
    registry = read_json(checkout / REGISTRY)
    continent = read_json(checkout / CARTOGRAPHY)["continent"]
    lattice = {"originMetres": continent["originMetres"], "metresPerPixel": continent["metresPerPixel"]}
    regions, sources = [], {}
    underground_path = checkout / 'eloria-assets/maps/continent-v2/_continent_v2/content/underground.json'
    underground = read_json(underground_path)['sections'] if underground_path.is_file() else []
    water_rgb = None
    for key, entry in served(registry):
        manifest_path = tool.resource_to_path(entry["manifest"])
        manifest = read_json(manifest_path)
        minimap = manifest.get("minimap") or {}
        if not minimap.get("image"):
            raise CartographyError(f"{key}: the package has no map picture; run _continent_v2/render_minimap.py "
                                   f"--region {key} --apply")
        image_path = manifest_path.parent / minimap["image"]
        if not image_path.is_file():
            raise CartographyError(f"{key}: {image_path} is missing")
        colour = minimap.get("cartographyRender", {}).get("waterRGB", [79, 150, 157])
        if water_rgb is not None and colour != water_rgb:
            raise CartographyError(f"{key}: overview minimaps use different ocean colours")
        water_rgb = colour
        translation = [float(v) for v in entry["continentGeography"]["translation"]]
        geography = manifest.get("continentGeography") or {}
        if [float(v) for v in geography.get("translation", [])] != translation:
            raise CartographyError(f"{key}: the package's continent translation is not its registry row's")
        crop = tool.tab_map_crop(minimap, tool.framing(manifest))
        world_min, world_max = tool.crop_world(minimap, crop)
        polygons = ownership.rings(geography)
        shape = ownership.geometry(polygons)
        centroid = shape.centroid
        sources[key] = hashlib.sha256(image_path.read_bytes()).hexdigest()
        regions.append({
            "name": str(manifest.get("asset", {}).get("name", key)),
            "serverMap": key,
            "frame": FRAME,
            "tabMap": {"texture": tool.path_to_resource(image_path), "region": list(crop),
                       "worldMin": world_min, "worldMax": world_max},
            "continentPolygon": [tool.atlas_point(point, lattice) for point in polygons[0]],
            "continentPolygons": [[tool.atlas_point(point, lattice) for point in ring] for ring in polygons],
            "continentLabel": tool.atlas_point([centroid.x,centroid.y], lattice),
            "globalTranslation": translation,
            "serviceMarkers": [{"label": mark["label"], "name": mark["name"], "category": mark["category"],
                                "position": [mark["position"][0], mark["position"][2]],
                                "height": mark["position"][1], "serverTile": mark["serverTile"]}
                               for mark in manifest.get("serviceMarkers", [])],
            "storageMarkers": [{"label": mark.get("name", mark.get("label", "Storage")),
                                "position": [mark["position"][0], mark["position"][2]],
                                "serverTile": mark["serverTile"], "objectId": mark["objectId"]}
                               for mark in manifest.get("interactives", []) if mark.get("type") == "storage"],
            "entranceMarkers": [{"label": section['name'],
                                 "position": [section['entrance']['position'][0], section['entrance']['position'][2]],
                                 "height": section['entrance']['position'][1],
                                 "serverTile": section['entrance']['tile'], "objectId": section['entrance']['object']}
                                for section in underground if section['entrance']['map'] == key],
        })
    data = {"schema": SCHEMA, "generator": TOOL,
            "note": ("The continent-v2 territories' tab maps, appended by the client after cartography.json's regions. "
                     "Generated: run the generator after a map picture, a frame or a polygon changes."),
            "frame": FRAME, "lattice": lattice, "sources": sources, "regions": regions}
    data["overview"] = overview_layout(data)
    data["overview"]["waterRGB"] = water_rgb
    data["overview"]["sha256"] = hashlib.sha256(overview_bytes(checkout, data)).hexdigest()
    return data


def overview_layout(data: dict) -> dict:
    """A separate north-up group atlas; legacy pixel coordinates stay unchanged."""
    scale = float(data["lattice"]["metresPerPixel"])
    origin = data["lattice"]["originMetres"]
    points = [p for row in data["regions"] for ring in row["continentPolygons"] for p in ring]
    if not points:
        raise CartographyError("the Landfall overview has no served regions")
    padding = 32  # 64m at the existing two-metre lattice.
    low = [math.floor(min(p[i] for p in points)) - padding for i in (0, 1)]
    high = [math.ceil(max(p[i] for p in points)) + padding for i in (0, 1)]
    regions = []
    for row in data["regions"]:
        rings = [[[round(p[i] - low[i], 3) for i in (0, 1)] for p in ring]
                 for ring in row["continentPolygons"]]
        flat = [p for ring in rings for p in ring]
        minimum = [min(p[i] for p in flat) for i in (0, 1)]
        maximum = [max(p[i] for p in flat) for i in (0, 1)]
        regions.append({"serverMap": row["serverMap"], "name": row["name"],
                        "rect": [*minimum, *[maximum[i] - minimum[i] for i in (0, 1)]],
                        "polygons": rings,
                        "label": [round(row["continentLabel"][i] - low[i], 3) for i in (0, 1)]})
    return {"name": "Landfall", "frame": FRAME,
            "texture": "res://../" + OVERVIEW,
            "imageSize": [high[i] - low[i] for i in (0, 1)],
            "originMetres": [origin[i] + low[i] * scale for i in (0, 1)],
            "metresPerPixel": scale, "regions": regions}


def overview_bytes(checkout: Path, data: dict) -> bytes:
    """Compose existing minimap crops, masked by every component; no GPU render."""
    tool = legacy_tool(checkout)
    overview = data["overview"]
    scale = overview["metresPerPixel"]
    origin = overview["originMetres"]
    canvas = Image.new("RGB", tuple(overview["imageSize"]), tuple(overview["waterRGB"]))
    for row, region in zip(data["regions"], overview["regions"]):
        tab = row["tabMap"]
        translation = row["globalTranslation"]
        low = [tab["worldMin"][i] + translation[i * 2] for i in (0, 1)]
        high = [tab["worldMax"][i] + translation[i * 2] for i in (0, 1)]
        rect_low = [round((low[i] - origin[i]) / scale) for i in (0, 1)]
        rect_high = [round((high[i] - origin[i]) / scale) for i in (0, 1)]
        with Image.open(tool.resource_to_path(tab["texture"])) as image:
            x, y, w, h = tab["region"]
            piece = image.convert("RGBA").crop((x, y, x + w, y + h))
            piece = piece.resize(tuple(rect_high[i] - rect_low[i] for i in (0, 1)), Image.Resampling.LANCZOS)
        mask = Image.new("L", piece.size)
        pen = ImageDraw.Draw(mask)
        for ring in region["polygons"]:
            pen.polygon([(p[0] - rect_low[0], p[1] - rect_low[1]) for p in ring], fill=255)
        piece.putalpha(ImageChops.multiply(piece.getchannel("A"), mask))
        canvas.paste(piece, tuple(rect_low), piece)
    output = io.BytesIO()
    canvas.save(output, "WEBP", lossless=True, method=6)
    return output.getvalue()


def encode(data: dict) -> bytes:
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


def check(checkout: Path = DEFAULT_CHECKOUT) -> list[str]:
    try:
        wanted = compose(checkout)
    except CartographyError as error:
        return [str(error)]
    path = Path(checkout) / OUTPUT
    if not path.is_file():
        return [f"{OUTPUT} is missing; run {TOOL}"]
    current = read_json(path)
    problems = [f"{OUTPUT} '{key}' is stale; run {TOOL}" for key in sorted(set(current) | set(wanted))
            if current.get(key) != wanted.get(key)]
    image_path = Path(checkout) / OVERVIEW
    if not image_path.is_file() or hashlib.sha256(image_path.read_bytes()).hexdigest() != wanted["overview"]["sha256"]:
        problems.append(f"{OVERVIEW} is missing or stale; run {TOOL}")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 when the file is not what this tool writes")
    ap.add_argument("--checkout", type=Path, default=DEFAULT_CHECKOUT)
    args = ap.parse_args(argv)
    if args.check:
        problems = check(args.checkout)
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    try:
        data = compose(args.checkout)
    except CartographyError as error:
        print(f"refused: {error}")
        return 1
    image_path = args.checkout / OVERVIEW
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(overview_bytes(args.checkout, data))
    (args.checkout / OUTPUT).write_bytes(encode(data))
    for region in data["regions"]:
        print(f"  {region['serverMap']:14s} {region['tabMap']['region']} of {Path(region['tabMap']['texture']).name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
