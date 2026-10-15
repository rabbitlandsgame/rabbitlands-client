#!/usr/bin/env python3
"""Compose the continent map from the regions' own tab maps, and write the
client's cartography.

    python eloria-assets/tools/build_continent_map.py [--check]

The region images come from the actual geometry under shared north-up lighting.
Their transparent footprints occupy the same translated metre coordinates as
the streamed exterior scenes. `continent-geography.json` owns those coordinates;
`continent-layout.json` supplies the atlas scale, canvas and sea colour.

Two files are written:

* `maps/nymara-regions/continent-map.webp`, the continent as one picture;
* `godot-client/data/maps/cartography.json`, what the client needs to use it -
  the polygon each region occupies on that picture (its click target), the
  region's own tab-map image, the pixels of it the live Tab map frames, and
  the world coordinates of that framing so the sidebar can name the tile
  under the cursor.

The framing follows `map_view.gd` exactly - `mapBounds`, then
`playableBounds`, then the server's addressable rectangle, then the mesh
bounds - so a preview shows what the player will see on arrival: Four Gates
without its backdrop rim, the Sunmane steppe without the landform past its
last tile.

`--check` builds everything in memory and exits non-zero when the checked-in
cartography or the continent picture is stale: a region redrew its minimap, a
region moved on the layout, or the JSON was edited by hand. It is what
`godot-client/tests/test_cartography.py` runs.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "godot-client" / "data" / "maps" / "registry.json"
LAYOUT = ROOT / "eloria-assets" / "maps" / "nymara-regions" / "continent-layout.json"
CONNECTIONS = LAYOUT.with_name("region-connections.json")
GEOGRAPHY = LAYOUT.with_name("continent-geography.json")
CONTINENT_IMAGE = ROOT / "eloria-assets" / "maps" / "nymara-regions" / "continent-map.webp"
CARTOGRAPHY = ROOT / "godot-client" / "data" / "maps" / "cartography.json"
RESOURCE_PREFIX = "res://../"
## The same encoding the region minimaps use.
WEBP_QUALITY = 92
SCHEMA_VERSION = 2


def resource_to_path(resource: str) -> Path:
    """`res://../eloria-assets/x` is the repository's `eloria-assets/x`."""
    if not resource.startswith(RESOURCE_PREFIX):
        raise SystemExit(f"not a repository resource path: {resource}")
    return ROOT / resource[len(RESOURCE_PREFIX):]


def path_to_resource(path: Path) -> str:
    return RESOURCE_PREFIX + path.resolve().relative_to(ROOT).as_posix()


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def geometry_contract(manifest: dict) -> dict:
    """Stable render inputs; derived minimap provenance must not hash itself."""
    minimap = manifest.get('minimap', {})
    return {'frame': {key:minimap.get(key) for key in
            ('worldMin', 'worldMax', 'imageSize', 'pixelsPerMetre')},
            'mapFrame': list(framing(manifest)),
            'continentGeography': manifest.get('continentGeography', {}),
            'glb': manifest.get('asset', {}).get('glb'),
            'externalResources': manifest.get('externalResources', {})}


def contract_digest(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(geometry_contract(manifest), sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def geometry_atlas(layout: dict) -> tuple[Path, dict] | None:
    """A direct master render supersedes patchwork imagery, with stale checks."""
    spec = layout.get('geometryAtlas')
    if not spec:
        return None
    image = resource_to_path(spec['image'])
    report = load_json(resource_to_path(spec['report']))
    if report.get('schemaVersion') != 1:
        raise ValueError('Unsupported master geometry atlas report')
    if report.get('layout') != {key:layout[key] for key in
                              ('originMetres', 'canvasMetres', 'metresPerPixel')}:
        raise ValueError('Master geometry atlas framing is stale; run _continent/atlas_export.py')
    if digest(image) != report['imageSha256']:
        raise ValueError('Master geometry atlas image changed after rendering')
    for resource, expected in report['inputs'].items():
        if digest(resource_to_path(resource)) != expected:
            raise ValueError(f'Master geometry atlas input is stale: {resource}')
    for resource, expected in report.get('optionalReviewInputs', {}).items():
        path = resource_to_path(resource)
        if path.exists() and digest(path) != expected:
            raise ValueError(f'Present review master geometry is stale: {resource}')
    for resource, expected in report['territoryContracts'].items():
        if contract_digest(load_json(resource_to_path(resource))) != expected:
            raise ValueError(f'Master geometry atlas territory framing is stale: {resource}')
    return image, report


def framing(manifest: dict) -> tuple[float, float, float, float]:
    """The X/Z rectangle the live Tab map frames, as (min_x, min_z, max_x, max_z).

    The precedence is `map_view.gd`'s `bounds_for`: a map that states its own
    extent is believed over the mesh, and the server's addressable rectangle
    stands in for the older packages that never declared one.
    """
    asset = manifest.get("asset", {})
    for key in ("mapBounds", "playableBounds"):
        bounds = asset.get(key, {})
        low, high = bounds.get("min"), bounds.get("max")
        if isinstance(low, list) and isinstance(high, list) and len(low) == 3 and len(high) == 3:
            if float(high[0]) > float(low[0]) and float(high[2]) > float(low[2]):
                return float(low[0]), float(low[2]), float(high[0]), float(high[2])
    addressable = manifest.get("coordinateTransform", {}).get("addressableWorldBounds", {})
    low, high = addressable.get("min"), addressable.get("max")
    if isinstance(low, list) and isinstance(high, list) and len(low) == 2 and len(high) == 2:
        return float(low[0]), float(low[1]), float(high[0]), float(high[1])
    bounds = asset.get("bounds", {})
    low, high = bounds.get("min"), bounds.get("max")
    if isinstance(low, list) and isinstance(high, list) and len(low) == 3 and len(high) == 3:
        return float(low[0]), float(low[2]), float(high[0]), float(high[2])
    raise SystemExit("manifest declares no bounds to frame")


def tab_map_crop(minimap: dict, frame: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    """The pixels of the minimap image that show `frame`, as (x, y, w, h)."""
    scale = float(minimap.get("pixelsPerMetre", 1.0))
    low = minimap["worldMin"]
    width, height = (int(value) for value in minimap["imageSize"])
    x0 = int(round((frame[0] - float(low[0])) * scale))
    y0 = int(round((frame[1] - float(low[1])) * scale))
    x1 = int(round((frame[2] - float(low[0])) * scale))
    y1 = int(round((frame[3] - float(low[1])) * scale))
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    if x1 <= x0 or y1 <= y0:
        raise SystemExit("the live map's framing lies outside the minimap image")
    return x0, y0, x1 - x0, y1 - y0


def crop_world(minimap: dict, crop: tuple[int, int, int, int]) -> tuple[list[float], list[float]]:
    """The world X/Z rectangle a pixel crop covers, so a pixel maps back to a tile."""
    scale = float(minimap.get("pixelsPerMetre", 1.0))
    low = minimap["worldMin"]
    x, y, w, h = crop
    return ([float(low[0]) + x / scale, float(low[1]) + y / scale],
            [float(low[0]) + (x + w) / scale, float(low[1]) + (y + h) / scale])


def registry_entries(registry: dict, layout: dict) -> list[tuple[str, dict]]:
    """The laid-out regions in the registry's order, each with its manifest path."""
    maps = registry.get("maps", {})
    missing = [key for key in layout["regions"] if key not in maps]
    if missing:
        raise SystemExit(f"layout names maps the registry does not have: {missing}")
    entries = []
    for key, entry in maps.items():
        if key in layout["regions"]:
            entries.append((key, entry))
    return entries


def atlas_point(point, layout):
    origin = layout.get('originMetres', [0, 0])
    return [round((float(point[i])-origin[i])/float(layout['metresPerPixel']), 3) for i in (0, 1)]


def atlas_connections(layout: dict) -> list[dict]:
    """Roads meet at their actual surveyed coordinates, ferries at their quays."""
    scale = float(layout['metresPerPixel'])
    geography = load_json(GEOGRAPHY) if GEOGRAPHY.exists() else None
    registry = load_json(REGISTRY)['maps']
    def endpoint(region, portal):
        if geography is None:
            return layout['regions'][region]
        manifest = load_json(resource_to_path(registry[region]['manifest']))
        entry = next(p for p in manifest.get('portals', []) + manifest.get('interactives', [])
                     if p.get('id') == portal)
        frame = next((s for s in manifest.get('streamingBorders', []) if s['portal'] == portal), None)
        point = frame['anchor'] if frame else entry['position']
        translation = geography['regions'][region]['translation']
        return [point[0] + translation[0], point[2] + translation[2]]
    result = []
    for link in load_json(CONNECTIONS)['connections']:
        a, b = link['from'], link['to']
        if a not in layout['regions'] or b not in layout['regions']:
            continue
        key = a + '--' + b
        points = [endpoint(a, link['from_portal']),
                  *layout.get('routeBends', {}).get(key, []), endpoint(b, link['to_portal'])]
        result.append({'from': a, 'to': b, 'type': link['type'],
                       'points': [atlas_point(p, layout) for p in points]})
    return result


def compose(layout: dict, registry: dict) -> tuple[dict, list[dict]]:
    """The cartography document, and what to paste where to draw the picture."""
    metres_per_pixel = float(layout["metresPerPixel"])
    canvas_w, canvas_h = (int(round(float(v) / metres_per_pixel)) for v in layout["canvasMetres"])
    regions: list[dict] = []
    tiles: list[dict] = []
    sources: dict[str, str] = {}
    geography = load_json(GEOGRAPHY) if GEOGRAPHY.exists() else None
    for key, entry in registry_entries(registry, layout):
        manifest_path = resource_to_path(entry["manifest"])
        manifest = load_json(manifest_path)
        minimap = manifest.get("minimap", {})
        image_name = minimap.get("image")
        if not image_name:
            raise SystemExit(f"{key}: package has no minimap image to draw the continent from")
        image_path = manifest_path.parent / image_name
        if not image_path.exists():
            raise SystemExit(f"{key}: {image_path} is missing")
        with Image.open(image_path) as image:
            if list(image.size) != [int(v) for v in minimap.get("imageSize", [])]:
                raise SystemExit(f"{key}: minimap.imageSize {minimap.get('imageSize')} "
                                 f"does not match the image, {list(image.size)}")
        frame = framing(manifest)
        crop = tab_map_crop(minimap, frame)
        world_min, world_max = crop_world(minimap, crop)
        placed = geography['regions'][key] if geography else None
        centre = ([placed['translation'][0] + (world_min[0] + world_max[0]) * .5,
                   placed['translation'][2] + (world_min[1] + world_max[1]) * .5]
                  if placed else layout["regions"][key])
        width_m = world_max[0] - world_min[0]
        height_m = world_max[1] - world_min[1]
        origin = layout.get('originMetres', [0, 0])
        rect = [int(round((float(centre[0]) - width_m * 0.5 - origin[0]) / metres_per_pixel)),
                int(round((float(centre[1]) - height_m * 0.5 - origin[1]) / metres_per_pixel)),
                max(1, int(round(width_m / metres_per_pixel))),
                max(1, int(round(height_m / metres_per_pixel)))]
        if rect[0] < 0 or rect[1] < 0 or rect[0] + rect[2] > canvas_w or rect[1] + rect[3] > canvas_h:
            raise SystemExit(f"{key}: lies outside the {canvas_w}x{canvas_h} canvas at {rect}")
        sources[key] = digest(image_path)
        regions.append({
            "name": str(manifest.get("asset", {}).get("name", key)),
            "serverMap": key,
            "continentRect": rect,
            "tabMap": {
                "texture": path_to_resource(image_path),
                "region": list(crop),
                "worldMin": world_min,
                "worldMax": world_max,
            },
        })
        geometry_path = manifest_path.parent / minimap.get('geometryImage', image_name)
        if geometry_path != image_path:
            sources[key + ':geometry'] = digest(geometry_path)
        polygon = placed.get('ownershipPolygon') if placed else None
        if polygon:
            polygon = [atlas_point(point, layout) for point in polygon]
            regions[-1]['continentPolygon'] = polygon
        if placed:
            # A concave ownership bbox can have its centre outside the region.
            # The protected native core is wholly inside its owned footprint.
            low, high = placed['nativePlayableBounds']
            label = [placed['translation'][0]+(low[0]+high[0])*.5,
                     placed['translation'][2]+(low[1]+high[1])*.5]
            regions[-1]['continentLabel'] = atlas_point(placed.get('atlasLabel', label), layout)
            regions[-1]['globalTranslation'] = placed['translation']
        tiles.append({"key": key, "image": geometry_path, "crop": crop, "rect": rect,
                      "polygon": polygon})
    for index, first in enumerate(regions) if geography is None else []:
        a = first["continentRect"]
        for second in regions[index + 1:]:
            b = second["continentRect"]
            if a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]:
                raise SystemExit(f"{first['serverMap']} and {second['serverMap']} overlap on the continent")
    cartography = {
        "schemaVersion": SCHEMA_VERSION,
        "generator": "eloria-assets/tools/build_continent_map.py",
        "note": ("Generated from actual region geometry with shared north-up lighting. "
                 "The atlas and streamed map crossings use continent-geography.json's "
                 "translations and owned polygons. Each tabMap frames the local minimap "
                 "the live client uses. Rebuild after geometry or geography changes."),
        "continent": {
            "name": str(layout.get("continent", "Nymara")),
            "texture": path_to_resource(CONTINENT_IMAGE),
            "imageSize": [canvas_w, canvas_h],
            "metresPerPixel": metres_per_pixel,
            "originMetres": layout.get('originMetres', [0, 0]),
            "sources": sources,
        },
        "regions": regions,
        "connections": atlas_connections(layout),
    }
    if geography:
        cartography['continent']['geographySha256'] = digest(GEOGRAPHY)
    master = geometry_atlas(layout)
    if master:
        cartography['continent']['masterGeometry'] = {
            'imageSha256': master[1]['imageSha256'],
            'masterSha256': master[1]['masterSha256'],
            'reportSha256': digest(resource_to_path(layout['geometryAtlas']['report']))}
    return cartography, tiles


def draw(layout: dict, cartography: dict, tiles: list[dict]) -> Image.Image:
    metres_per_pixel = float(layout["metresPerPixel"])
    width, height = cartography["continent"]["imageSize"]
    canvas = Image.new("RGB", (width, height), tuple(int(v) for v in layout["sea"]))
    master = geometry_atlas(layout)
    if master:
        with Image.open(master[0]) as image:
            if image.size != (width, height):
                raise ValueError('Master geometry atlas raster and layout dimensions differ')
            canvas = image.convert('RGB')
    lake = layout.get("lake") if not GEOGRAPHY.exists() else None
    if lake:
        cx, cy = (float(v) / metres_per_pixel for v in lake["centre"])
        radius = float(lake["radius"]) / metres_per_pixel
        ImageDraw.Draw(canvas).ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=tuple(int(v) for v in lake["colour"]))
    for tile in tiles if not master else []:
        x, y, w, h = tile["crop"]
        rect = tile["rect"]
        with Image.open(tile["image"]) as image:
            piece = image.convert("RGBA").crop((x, y, x + w, y + h))
            piece = piece.resize((rect[2], rect[3]), Image.LANCZOS)
        if tile.get('polygon'):
            from PIL import ImageChops
            mask = Image.new('L', piece.size)
            ImageDraw.Draw(mask).polygon([(px-rect[0], py-rect[1]) for px,py in tile['polygon']], fill=255)
            piece.putalpha(ImageChops.multiply(piece.getchannel('A'), mask))
        canvas.paste(piece, (rect[0], rect[1]), piece)
    pen = ImageDraw.Draw(canvas)
    for link in cartography['connections']:
        points = [tuple(p) for p in link['points']]
        if link['type'] != 'ferry':
            # The roads themselves are part of the geometry. A small crossing
            # mark records the graph without drawing a second invented road.
            if GEOGRAPHY.exists():
                cx, cy = points[0]
                pen.ellipse((cx-1.5, cy-1.5, cx+1.5, cy+1.5), fill=(218, 193, 137))
            else:
                pen.line(points, fill=(218, 193, 137), width=2)
        else:
            for a, b in zip(points, points[1:]):
                length = math.dist(a, b)
                for begin in range(0, int(length), 9):
                    end = min(begin+5, length)
                    at = lambda d: tuple(a[i]+(b[i]-a[i])*d/length for i in (0, 1))
                    pen.line([at(begin), at(end)], fill=(129, 204, 221), width=1)
    return canvas


def check() -> list[str]:
    """Everything that would change if the tool ran now. Empty means current."""
    problems: list[str] = []
    layout = load_json(LAYOUT)
    registry = load_json(REGISTRY)
    wanted, tiles = compose(layout, registry)
    if not CARTOGRAPHY.exists():
        return [f"{CARTOGRAPHY} is missing; run build_continent_map.py"]
    current = load_json(CARTOGRAPHY)
    if current != wanted:
        for key in sorted(set(current) | set(wanted)):
            if current.get(key) != wanted.get(key):
                problems.append(f"cartography.json '{key}' is stale; run build_continent_map.py")
    if not CONTINENT_IMAGE.exists():
        problems.append(f"{CONTINENT_IMAGE} is missing; run build_continent_map.py")
    else:
        with Image.open(CONTINENT_IMAGE) as image:
            if list(image.size) != wanted["continent"]["imageSize"]:
                problems.append(f"continent image is {list(image.size)}, cartography says "
                                f"{wanted['continent']['imageSize']}; run build_continent_map.py")
        encoded = io.BytesIO()
        draw(layout, wanted, tiles).save(encoded, 'WEBP', quality=WEBP_QUALITY, method=6)
        if CONTINENT_IMAGE.read_bytes() != encoded.getvalue():
            problems.append('continent picture content is stale; run build_continent_map.py')
    return problems


def build() -> None:
    layout = load_json(LAYOUT)
    registry = load_json(REGISTRY)
    cartography, tiles = compose(layout, registry)
    picture = draw(layout, cartography, tiles)
    CONTINENT_IMAGE.parent.mkdir(parents=True, exist_ok=True)
    picture.save(CONTINENT_IMAGE, "WEBP", quality=WEBP_QUALITY, method=6)
    CARTOGRAPHY.write_text(json.dumps(cartography, indent=2) + "\n", encoding="utf-8")
    print(f"continent {picture.size[0]}x{picture.size[1]} -> {CONTINENT_IMAGE.relative_to(ROOT)}")
    print(f"{len(cartography['regions'])} regions -> {CARTOGRAPHY.relative_to(ROOT)}")
    for region in cartography["regions"]:
        print(f"  {region['serverMap']:18s} at {region['continentRect']} "
              f"from {region['tabMap']['region']} of {Path(region['tabMap']['texture']).name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="report what is stale instead of writing anything")
    args = parser.parse_args(argv)
    if args.check:
        problems = check()
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
