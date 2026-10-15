#!/usr/bin/env python3
"""Validate the committed Sunmane Steppe package.

Checks the runtime artefacts as a reviewer or CI job would find them, without
rebuilding: manifest schema conformance against the client's own schema, glTF
structure, the exact landmark inventory the written region description
specifies, coordinate and minimap transforms, collision and navigation
declarations, and the absence of the placeholder artefacts the previous
generator left behind.

    python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/validate_package.py
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
PACKAGE = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "godot-client" / "schemas" / "world-manifest-1.schema.json"

# Counts asserted by the written region description.
REQUIRED_LANDMARKS = {
    "round-tent": 12, "seasonal-market": 4, "banner-shrine": 8, "caravanserai": 4,
    "windmill": 6, "well": 4, "animal-pen": 6, "burial-mound": 6,
}

failures: list[str] = []
checks = 0


def check(condition: bool, message: str) -> bool:
    global checks
    checks += 1
    if not condition:
        failures.append(message)
    return bool(condition)


def read_glb(path: Path) -> tuple[dict, int]:
    raw = path.read_bytes()
    magic, version, total = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF":
        raise SystemExit("not a GLB: " + str(path))
    check(version == 2, "GLB container version is 2")
    check(total == len(raw), "GLB declared length matches the file size")
    json_length, json_type = struct.unpack_from("<II", raw, 12)
    check(json_type == 0x4E4F534A, "first chunk is JSON")
    document = json.loads(raw[20:20 + json_length])
    binary_length, binary_type = struct.unpack_from("<II", raw, 20 + json_length)
    check(binary_type == 0x004E4942, "second chunk is BIN")
    check(binary_length > 0, "GLB carries an embedded binary chunk")
    return document, len(raw)


def validate_against_schema(manifest: dict, schema: dict) -> None:
    """Minimal structural check against the client's world-manifest schema."""
    for key in schema.get("required", []):
        check(key in manifest, f"manifest has required key '{key}'")
    asset = manifest.get("asset", {})
    asset_schema = schema["properties"]["asset"]
    for key in asset_schema.get("required", []):
        check(key in asset, f"manifest asset has required key '{key}'")
    check(asset.get("units") == "meters", "asset units are metres")
    axes = asset.get("coordinateSystem", {})
    check(axes.get("upAxis") == "Y", "up axis is Y")
    check(axes.get("northAxis") in ("Z", "-Z", "X", "-X"), "north axis is declared")
    check(str(manifest.get("schemaVersion", "")).startswith("1."),
          "schemaVersion is a supported 1.x")
    for point in manifest.get("spawnPoints", []):
        check("id" in point and "position" in point,
              "each spawn point declares an id and a position")


def main() -> int:
    manifest = json.loads((PACKAGE / "world.json").read_text())
    schema = json.loads(SCHEMA.read_text())
    validate_against_schema(manifest, schema)

    glb_path = PACKAGE / manifest["asset"]["glb"]
    check(glb_path.exists(), "world.glb referenced by the manifest exists")
    document, glb_bytes = read_glb(glb_path)

    # --- self-containment ------------------------------------------------
    check(len(document.get("buffers", [])) == 1, "GLB has exactly one buffer")
    check("uri" not in document["buffers"][0],
          "the buffer is embedded, not an external file")
    for index, image in enumerate(document.get("images", [])):
        check("uri" not in image, f"image {index} is embedded, not an external file")
        check("bufferView" in image, f"image {index} references a buffer view")
    check(not document.get("extensionsRequired"),
          "no required glTF extensions beyond core 2.0")

    # --- node inventory ---------------------------------------------------
    names = [node.get("name", "") for node in document["nodes"]]
    name_set = set(names)
    check(len(names) == len(name_set), "every node name is unique")

    terrain_nodes = [name for name in names if name.startswith("Terrain_")]
    check(len(terrain_nodes) >= 64,
          f"terrain chunks carry the navigation prefix ({len(terrain_nodes)} found)")
    prefixes = manifest["navigation"]["surfaceNodePrefixes"]
    check(prefixes == ["Terrain_", "Walk_"], "navigation surface prefix matches the node names")

    for node_name in manifest["collision"]["nodeNames"]:
        check(node_name in name_set,
              f"declared collision node exists in the GLB: {node_name}")

    # --- landmark inventory from the written description -------------------
    counts: dict[str, int] = {}
    for landmark in manifest["landmarks"]:
        counts[landmark["kind"]] = counts.get(landmark["kind"], 0) + 1
        check(landmark["node"] in name_set,
              f"landmark node exists in the GLB: {landmark['node']}")
    for kind, expected in REQUIRED_LANDMARKS.items():
        check(counts.get(kind, 0) == expected,
              f"region description count for {kind}: expected {expected}, "
              f"found {counts.get(kind, 0)}")
    check(counts.get("great-hall", 0) == 1, "the central hall is present exactly once")
    check(counts.get("gate", 0) == 4, "four gate bays are present")

    # --- no leftovers from the previous placeholder pass --------------------
    foreign = [name for name in names if any(
        token in name for token in ("manymouth", "crownwater", "amethyst", "whitehorn",
                                    "westhaven", "amberwood", "mirrorhold", "ssarathi",
                                    "verdant", "grey_moor"))]
    check(not foreign,
          f"no other region's landmark names remain in this map: {foreign[:4]}")

    # --- coordinates --------------------------------------------------------
    transform = manifest["coordinateTransform"]
    check(transform["metresPerTile"] == 1.0, "one metre per server tile")
    check(transform["serverOrigin"] == [58.0, 58.0],
          "server origin is the region arrival datum (58, 58)")
    check(transform["invertServerY"] is True, "server Y is inverted for -Z north")
    bounds = manifest["asset"]["bounds"]
    for tile, label in (((6, 58), "west walk portal"), ((110, 58), "east walk portal"),
                        ((58, 100), "north interior entrance")):
        world_x = (tile[0] - 58.0)
        world_z = -(tile[1] - 58.0)
        check(bounds["min"][0] <= world_x <= bounds["max"][0]
              and bounds["min"][2] <= world_z <= bounds["max"][2],
              f"{label} falls inside the declared map bounds")

    walking_height = transform["walkingHeight"]
    check(walking_height > bounds["min"][1],
          "the grounding fallback height sits above the lowest terrain")

    # --- server addressability -----------------------------------------------
    # Server tiles are non-negative, and server X 0 is Godot X -58 here, so
    # anything further west could never be walked to. Scenery may sit out
    # there; nothing a player interacts with may.
    def tile_ok(tile) -> bool:
        return tile[0] >= 0 and tile[1] >= 0 and tile[0] <= 191 and tile[1] <= 191

    for entry in manifest["interactives"]:
        check(tile_ok(entry["serverTile"]),
              f"interactive is addressable by the server: {entry['id']} at "
              f"{entry['serverTile']}")
    interactive_nodes = {entry["node"] for entry in manifest["interactives"]}
    for entry in manifest["landmarks"]:
        check("reachable" in entry,
              f"landmark declares whether it is reachable: {entry['id']}")
        check(bool(entry.get("reachable")) == tile_ok(entry["serverTile"]),
              f"landmark reachability matches its tile: {entry['id']} at "
              f"{entry['serverTile']}")
        if not entry.get("reachable"):
            # Scenery beyond the band closes the horizon. It may not carry an
            # interaction, because a player could never stand at it.
            check(entry["id"] not in interactive_nodes,
                  f"unreachable scenery carries no interaction: {entry['id']}")
    for group in manifest["ambientPopulation"]["groups"]:
        check(tile_ok(group["serverTile"]),
              f"ambient group is addressable: {group['id']}")
    runtime_records = (manifest["runtimePopulation"]["npcs"]
                       + manifest["runtimePopulation"]["resources"]
                       + manifest["runtimePopulation"]["creatures"])
    for entry in runtime_records:
        check(tile_ok(entry["serverTile"]),
              f"server-owned placement is addressable: "
              f"{entry.get('id', entry.get('model'))} at {entry['serverTile']}")

    # --- minimap ------------------------------------------------------------
    minimap = manifest["minimap"]
    image_path = PACKAGE / minimap["image"]
    check(image_path.exists(), "minimap image exists")
    span = bounds["max"][0] - bounds["min"][0]
    expected_scale = minimap["imageSize"][0] / span
    check(math.isclose(minimap["pixelsPerMetre"], expected_scale, rel_tol=1e-4),
          "minimap pixels-per-metre matches the bounds and image size")
    # The region is not centred on the world origin, so the offset is checked by
    # mapping the declared bounds onto the image rather than assuming symmetry.
    for key, image_axis, world_axis, label in (("pixelX", 0, 0, "east-west"),
                                               ("pixelY", 1, 2, "north-south")):
        axis = minimap["transform"][key]
        low = bounds["min"][world_axis]
        high = bounds["max"][world_axis]
        pixels = minimap["imageSize"][image_axis]
        check(math.isclose(axis["scale"], pixels / (high - low), rel_tol=1e-4),
              f"minimap {label} scale matches the bounds and image size")
        check(abs(low * axis["scale"] + axis["offset"]) < 0.01
              and abs(high * axis["scale"] + axis["offset"] - pixels) < 0.01,
              f"minimap {label} transform maps the declared bounds onto the image")

    # --- population ----------------------------------------------------------
    ambient = manifest.get("ambientPopulation", {}).get("groups", [])
    check(len(ambient) >= 10, "ambient livestock groups are declared")
    animals = sum(int(group["count"]) for group in ambient)
    check(animals >= 60, f"the region is populated with livestock ({animals} animals)")
    catalog = json.loads(
        (ROOT / "godot-client" / "data" / "actors" / "models.json").read_text())
    for group in ambient:
        check(group["model"] in catalog["models"],
              f"ambient model is registered in the client catalogue: {group['model']}")
    runtime = manifest.get("runtimePopulation", {})
    check(len(runtime.get("npcs", [])) >= 8, "server-owned NPC posts are recorded")
    check(len(runtime.get("resources", [])) >= 8, "harvestable resources are recorded")

    # --- environment ----------------------------------------------------------
    environment = manifest.get("environment", {})
    for key in ("sky", "sun", "fog", "ambient", "tonemap", "water"):
        check(key in environment, f"environment declares {key}")
    check("golden-hour" in environment.get("variants", {}),
          "a golden-hour presentation variant is declared")

    print(f"world.glb {glb_bytes / 1048576:.2f} MiB, "
          f"{len(document['meshes'])} meshes, {len(document['nodes'])} nodes, "
          f"{len(document['materials'])} materials, "
          f"{len(document.get('textures', []))} textures")
    print(f"{checks - len(failures)}/{checks} checks passed")
    for failure in failures:
        print("FAIL:", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
