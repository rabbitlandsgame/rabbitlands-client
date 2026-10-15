"""Validated inputs exported by the Godot continent-authoring scenes.

The snapshot is an interchange format, not a regional package.  It is read
before shared-world composition and its referenced files are accepted only
when their recorded hashes still match.  Keeping validation here prevents a
partially exported scene from silently falling back to the retired regional
recipe.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from authoring_catalog import CATALOG_PATH, RegionContract, authored_contracts
from storage_bounds import authoring_storage, frame_values


HERE = Path(__file__).resolve().parent
REGIONS = HERE.parent
MAPS = REGIONS.parent
CLIENT = MAPS.parents[1]
SCHEMA = "eloria-continent-authoring-v1"
SUNMANE = "sunmane_steppe"
SUNMANE_TRANSLATION = (1200.0, 0.0, 720.0)
SUNMANE_SERVER_ORIGIN = (194, 292)
SUNMANE_SERVER_CELLS = (792, 792)
SUNMANE_TERRAIN_ORIGIN = (-194.0, -500.0)
SUNMANE_TERRAIN_VERTICES = (397, 397)
SUNMANE_REQUIRED_ROUTE_IDS = tuple(sorted((
    "mirrorhold--sunmane_steppe-sunmane_steppe",
    "amethyst_barrens--sunmane_steppe-sunmane_steppe",
    "sunmane_steppe--verdant_stair-sunmane_steppe",
    "door-sunmane_steppe-cave-wind_caves",
    "door-sunmane_steppe-cave-crystal_hollow",
    *(f"discovery-sunmane_steppe-{number}" for number in range(301, 314)),
    "discovery-sunmane_steppe-713",
)))
SUNMANE_REQUIRED_LINK_ROUTE_IDS = tuple(sorted((
    "mirrorhold--sunmane_steppe-sunmane_steppe",
    "amethyst_barrens--sunmane_steppe-sunmane_steppe",
    "sunmane_steppe--verdant_stair-sunmane_steppe",
    "door-sunmane_steppe-cave-wind_caves",
    "door-sunmane_steppe-cave-crystal_hollow",
)))
SUNMANE_PLAN_FEATURE_IDS = ("southern_river",)
SUNMANE_SNAPSHOT = REGIONS / SUNMANE / "authoring" / "continent-authoring.json"
# These three lake records in the byte-frozen published plan predate stable IDs.
# Editor IDs are new ownership names for their exact original records, not
# edits to historical plan bytes.  The values prevent a matching name on a
# different lake from acquiring an old saved claim.
NAMELESS_PUBLISHED_LAKES = {
    "Moor headwater tarn": ("moor_headwater_tarn", (255, 350), (25, 18), 27, 2.5),
    "Moorwater pool": ("moorwater_pool", (250, 470), (21, 32), 22, 2.3),
    "Mirror Lake": ("mirror_lake", (893.6788, 831.4641), (48, 33), 80, 4),
}
AUTHORING_FRAMEWORK_GLOBS = (
    "godot-client/src/dev/map_authoring_region/*.gd",
    "godot-client/src/dev/map_authoring_pilot/style/*.gd",
    "godot-client/src/dev/map_authoring_pilot/style/*.gdshader",
    "godot-client/src/dev/map_authoring_pilot/style/textures/*.png",
    "godot-client/src/dev/map_authoring_pilot/style/textures/*.provenance.json",
    "godot-client/addons/map_asset_palette/*.gd",
)


class AuthoringError(ValueError):
    """The scene export cannot safely become shared continent source."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuthoringError(f"{where} must be an object")
    return value


def _array(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise AuthoringError(f"{where} must be an array")
    return value


def _string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthoringError(f"{where} must be a non-empty string")
    return value


def _number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise AuthoringError(f"{where} must be a finite number")
    return float(value)


def _vector(value: Any, size: int, where: str) -> tuple[float, ...]:
    values = _array(value, where)
    if len(values) != size:
        raise AuthoringError(f"{where} must contain {size} numbers")
    return tuple(_number(part, f"{where}[{index}]") for index, part in enumerate(values))


def _integer_vector(value: Any, size: int, where: str) -> tuple[int, ...]:
    values = _array(value, where)
    if len(values) != size or any(isinstance(part, bool) or not isinstance(part, int) for part in values):
        raise AuthoringError(f"{where} must contain {size} integers")
    return tuple(values)


def _ordered_unique(records: Iterable[dict[str, Any]], where: str) -> None:
    ids = [_string(record.get("id"), f"{where}[{index}].id") for index, record in enumerate(records)]
    if len(ids) != len(set(ids)):
        raise AuthoringError(f"{where} contains duplicate stable ids")
    if ids != sorted(ids):
        raise AuthoringError(f"{where} must be sorted by stable id")


def _contained(base: Path, relative: Any, where: str) -> Path:
    name = Path(_string(relative, where))
    if name.is_absolute():
        raise AuthoringError(f"{where} must be relative")
    result = (base / name).resolve()
    try:
        result.relative_to(base.resolve())
    except ValueError as error:
        raise AuthoringError(f"{where} escapes {base}") from error
    return result


def _source_path(relative: Any, where: str) -> Path:
    name = Path(_string(relative, where))
    if name.is_absolute():
        raise AuthoringError(f"{where} must be relative to the client checkout")
    result = (CLIENT / name).resolve()
    try:
        result.relative_to(CLIENT.resolve())
    except ValueError as error:
        raise AuthoringError(f"{where} escapes the client checkout") from error
    return result


def _verify_hash(path: Path, expected: Any, where: str) -> None:
    digest = _string(expected, where).lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise AuthoringError(f"{where} must be a lowercase SHA-256 digest")
    if not path.is_file():
        raise AuthoringError(f"{path}: required authored source is missing")
    actual = sha256(path)
    if actual != digest:
        raise AuthoringError(f"{path}: authored source changed after snapshot export")


def _validate_sources(document: dict[str, Any], snapshot: Path, production: bool) -> dict[str, str]:
    sources = _object(document.get("sources"), "sources")
    scene = _object(sources.get("scene"), "sources.scene")
    scene_path = _source_path(scene.get("path"), "sources.scene.path")
    _verify_hash(scene_path, scene.get("sha256"), "sources.scene.sha256")
    result = {scene_path.relative_to(CLIENT).as_posix(): sha256(scene_path)}
    dependencies = [_object(value, f"sources.dependencies[{index}]")
                    for index, value in enumerate(
                        _array(sources.get("dependencies"), "sources.dependencies"))]
    dependency_paths = []
    for index, entry in enumerate(dependencies):
        relative = _string(entry.get("path"), f"sources.dependencies[{index}].path")
        path = _source_path(relative, f"sources.dependencies[{index}].path")
        _verify_hash(path, entry.get("sha256"), f"sources.dependencies[{index}].sha256")
        dependency_paths.append(relative.replace("\\", "/"))
        result[path.relative_to(CLIENT).as_posix()] = sha256(path)
    if dependency_paths != sorted(dependency_paths) or len(dependency_paths) != len(set(dependency_paths)):
        raise AuthoringError("sources.dependencies must be unique and sorted by path")
    if not production and "runtimeBindingSeed" not in sources:
        return result
    runtime_seed = _object(sources.get("runtimeBindingSeed"), "sources.runtimeBindingSeed")
    seed_relative = _string(runtime_seed.get("path"), "sources.runtimeBindingSeed.path").replace("\\", "/")
    seed_path = _source_path(seed_relative, "sources.runtimeBindingSeed.path")
    _verify_hash(seed_path, runtime_seed.get("sha256"), "sources.runtimeBindingSeed.sha256")
    if seed_relative not in dependency_paths:
        raise AuthoringError("sources.runtimeBindingSeed must also be a hash-bound dependency")
    dependency_digest = next(entry["sha256"] for entry in dependencies
                             if entry["path"].replace("\\", "/") == seed_relative)
    if dependency_digest != runtime_seed["sha256"]:
        raise AuthoringError("sources.runtimeBindingSeed disagrees with its dependency digest")
    return result


def _height_sidecar(terrain: dict[str, Any], snapshot: Path, field: str,
                    width: int, height: int) -> Path:
    record = _object(terrain.get(field), f"terrain.{field}")
    if record.get("encoding") != "float32-le":
        raise AuthoringError(f"terrain.{field}.encoding must be float32-le")
    path = _contained(snapshot.parent, record.get("path"), f"terrain.{field}.path")
    _verify_hash(path, record.get("sha256"), f"terrain.{field}.sha256")
    expected = width * height * np.dtype("<f4").itemsize
    if path.stat().st_size != expected:
        raise AuthoringError(f"terrain {field} has {path.stat().st_size} bytes; expected {expected}")
    values = np.fromfile(path, dtype="<f4")
    if not np.isfinite(values).all():
        raise AuthoringError(f"terrain {field} contains a non-finite height")
    return path


def _validate_terrain(document: dict[str, Any], snapshot: Path, production: bool,
                      source_sha256: dict[str, str],
                      contract: RegionContract | None = None) -> tuple[Path, Path, int, int]:
    terrain = _object(document.get("terrain"), "terrain")
    origin = _vector(terrain.get("origin"), 2, "terrain.origin")
    if production and contract is not None and origin != contract.terrain_origin:
        raise AuthoringError(
            f"{contract.id}: terrain.origin must be {list(contract.terrain_origin)}")
    cell_metres = _number(terrain.get("cellMetres"), "terrain.cellMetres")
    expected_cell_metres = contract.terrain_cell_metres if contract is not None else 2.0
    if cell_metres != expected_cell_metres:
        raise AuthoringError(
            f"terrain.cellMetres must match the region contract value {expected_cell_metres}")
    if _number(terrain.get("previewUvMetresInverse"),
               "terrain.previewUvMetresInverse") <= 0.0:
        raise AuthoringError("terrain.previewUvMetresInverse must be positive")
    width = terrain.get("width")
    height = terrain.get("height")
    if (isinstance(width, bool) or not isinstance(width, int) or width < 2 or
            isinstance(height, bool) or not isinstance(height, int) or height < 2):
        raise AuthoringError("terrain width and height must be integers of at least two")
    if production and contract is not None and (width, height) != contract.terrain_vertices:
        raise AuthoringError(
            f"{contract.id}: terrain width and height must cover the full "
            f"{contract.terrain_vertices[0]}x{contract.terrain_vertices[1]} shared envelope")
    _validate_surface(terrain.get("baseSurface"), source_sha256, "terrain.baseSurface")
    blend_enabled = terrain["baseSurface"].get("biomeBlendEnabled", False)
    if not isinstance(blend_enabled, bool):
        raise AuthoringError("terrain.baseSurface.biomeBlendEnabled must be boolean")
    biome_palette = _array(terrain.get("biomePalette", []), "terrain.biomePalette")
    if len(biome_palette) > 1:
        raise AuthoringError("terrain.biomePalette supports one secondary surface in v1")
    if biome_palette:
        entry = _object(biome_palette[0], "terrain.biomePalette[0]")
        identity = _string(entry.get("id"), "terrain.biomePalette[0].id")
        if ":" in identity:
            raise AuthoringError("terrain.biomePalette[0].id must be a local stable id")
        if entry.get("role") not in ("woodland", "heath", "wetland", "rock", "snow",
                                     "sand", "limestone", "steppe", "badland", "grassland",
                                     "tree_density"):
            raise AuthoringError("terrain.biomePalette[0].role is unsupported")
        _validate_surface(entry.get("surface"), source_sha256,
                          "terrain.biomePalette[0].surface")
    base_path = _height_sidecar(terrain, snapshot, "baseHeights", width, height)
    resolved_path = _height_sidecar(terrain, snapshot, "resolvedHeights", width, height)
    colors = terrain.get("baseColors")
    if colors is not None:
        colors = _object(colors, "terrain.baseColors")
        if colors.get("encoding") != "rgba8-srgb":
            raise AuthoringError("terrain.baseColors.encoding must be rgba8-srgb")
        color_path = _contained(snapshot.parent, colors.get("path"),
                                "terrain.baseColors.path")
        _verify_hash(color_path, colors.get("sha256"), "terrain.baseColors.sha256")
        expected_colors = width * height * 4
        if color_path.stat().st_size != expected_colors:
            raise AuthoringError(
                f"terrain baseColors has {color_path.stat().st_size} bytes; "
                f"expected {expected_colors}")
    includes = _array(terrain["resolvedHeights"].get("includes"),
                      "terrain.resolvedHeights.includes")
    if includes != ["patches", "road-earthworks", "river-cuts"]:
        raise AuthoringError(
            "terrain.resolvedHeights.includes must be patches, road-earthworks, river-cuts in evaluation order")
    patches = [_object(value, f"terrain.patches[{index}]")
               for index, value in enumerate(_array(terrain.get("patches", []), "terrain.patches"))]
    _ordered_unique(patches, "terrain.patches")
    for index, patch in enumerate(patches):
        where = f"terrain.patches[{index}]"
        if patch.get("shape") not in ("ellipse", "rectangle"):
            raise AuthoringError(f"{where}.shape must be ellipse or rectangle")
        if patch.get("operation") not in ("add", "set"):
            raise AuthoringError(f"{where}.operation must be add or set")
        _vector(patch.get("matrix"), 16, f"{where}.matrix")
        size = _vector(patch.get("size"), 2, f"{where}.size")
        if min(size) <= 0.0:
            raise AuthoringError(f"{where}.size must be positive")
        if _number(patch.get("feather"), f"{where}.feather") < 0.0:
            raise AuthoringError(f"{where}.feather must be non-negative")
        _number(patch.get("height"), f"{where}.height")
        if not isinstance(patch.get("enabled"), bool):
            raise AuthoringError(f"{where}.enabled must be boolean")
    return base_path, resolved_path, width, height


def _validate_ground_regions(document: dict[str, Any], source_sha256: dict[str, str]) -> None:
    regions = [_object(value, f"groundRegions[{index}]")
               for index, value in enumerate(
                   _array(document.get("groundRegions"), "groundRegions"))]
    _ordered_unique(regions, "groundRegions")
    for index, region in enumerate(regions):
        where = f"groundRegions[{index}]"
        if not isinstance(region.get("enabled"), bool):
            raise AuthoringError(f"{where}.enabled must be boolean")
        if region.get("shape") not in ("ellipse", "rectangle"):
            raise AuthoringError(f"{where}.shape must be ellipse or rectangle")
        _vector(region.get("matrix"), 16, f"{where}.matrix")
        size = _vector(region.get("size"), 2, f"{where}.size")
        if min(size) <= 0.0:
            raise AuthoringError(f"{where}.size must be positive")
        for field in ("blendWidth", "opacity", "priority"):
            _number(region.get(field), f"{where}.{field}")
        if "clipPolygon" in region:
            from shapely.geometry import Polygon
            ring = _array(region["clipPolygon"], f"{where}.clipPolygon")
            if not 3 <= len(ring) <= 64:
                raise AuthoringError(f"{where}.clipPolygon needs 3 through 64 points")
            points = [_vector(p, 2, f"{where}.clipPolygon[{i}]") for i,p in enumerate(ring)]
            polygon = Polygon(points)
            if not polygon.is_valid or polygon.area <= 0 or len(set(map(tuple,points))) != len(points):
                raise AuthoringError(f"{where}.clipPolygon must be a finite simple nonzero-area ring")
            matrix = np.asarray(region['matrix']).reshape(4,4,order='F')
            if np.abs(matrix[[0,1,1,2],[1,0,2,1]]).max() > 1e-6 or abs(np.linalg.det(matrix[np.ix_([0,2],[0,2])])) <= 1e-6:
                raise AuthoringError(f"{where}: clipped ground requires a nonsingular horizontal transform")
        if "uvAnchorContinent" in region:
            _vector(region["uvAnchorContinent"], 2, f"{where}.uvAnchorContinent")
        if "sourceLayerOrdinal" in region:
            ordinal=region["sourceLayerOrdinal"]
            if type(ordinal) is not int or not 0 <= ordinal <= 126:
                raise AuthoringError(f"{where}.sourceLayerOrdinal must be an integer from 0 through 126")
        _validate_surface(region.get("surface"), source_sha256, f"{where}.surface")


def _validate_pbr(pbr: Any, source_sha256: dict[str, str], where: str) -> None:
    pbr = _object(pbr, where)
    _vector(pbr.get("albedoColor"), 4, f"{where}.albedoColor")
    _vector(pbr.get("uvScale"), 3, f"{where}.uvScale")
    _vector(pbr.get("uvOffset"), 3, f"{where}.uvOffset")
    for field in ("normalScale", "roughness", "metallic"):
        _number(pbr.get(field), f"{where}.{field}")
    for field in ("triplanar", "worldTriplanar"):
        if not isinstance(pbr.get(field), bool):
            raise AuthoringError(f"{where}.{field} must be boolean")
    if pbr["triplanar"] or pbr["worldTriplanar"]:
        raise AuthoringError(
            f"{where}: triplanar surfaces cannot be represented losslessly in production GLB; "
            "use an explicit UV-based source material")
    for field in ("albedoTexture", "normalTexture", "ormTexture"):
        relative = pbr.get(field)
        if relative is None:continue
        path = _source_path(relative, f"{where}.{field}")
        key = path.relative_to(CLIENT).as_posix()
        if key not in source_sha256:
            raise AuthoringError(f"{where}.{field} is not a hash-bound scene dependency")


def _validate_surface(surface: Any, source_sha256: dict[str, str], where: str) -> None:
    record = _object(surface, where)
    preset = _string(record.get("preset"), f"{where}.preset")
    _number(record.get("rotationDegrees"), f"{where}.rotationDegrees")
    mode=record.get("materialMode")
    if mode not in ("surface", "road", "water"):
        raise AuthoringError(f"{where}.materialMode is unsupported")
    if "biomeBlendEnabled" in record and not isinstance(record["biomeBlendEnabled"], bool):
        raise AuthoringError(f"{where}.biomeBlendEnabled must be boolean")
    biome_packs = {"Moor peat heather", "Delta silt", "Coastal limestone gravel",
                   "Alpine scree lichen", "Forest floor moss", "Alpine snow crust",
                   "Weathered limestone masonry", "Jade masonry", "Marine timber",
                   "Reed thatch"}
    if preset != "Custom":
        if preset not in _PRESET_MATERIALS and preset != "Water" and preset not in biome_packs:
            raise AuthoringError(f"{where}.preset {preset!r} is unsupported")
        if preset in biome_packs and "pbrOverrides" not in record:
            raise AuthoringError(f"{where}.pbrOverrides is required for texture-pack presets")
        if "pbr" in record:
            raise AuthoringError(f"{where}.pbr is valid only for Custom surfaces")
        pbr_override=record.get("pbrOverrides")
        if pbr_override is not None:
            if mode!="surface":raise AuthoringError(f"{where}.pbrOverrides requires surface materialMode")
            _validate_pbr(pbr_override,source_sha256,f"{where}.pbrOverrides")
        road=record.get("roadOverrides")
        if road is not None:
            if preset!="Worn earth" or mode!="road":
                raise AuthoringError(f"{where}.roadOverrides requires the Worn earth road preset")
            road=_object(road,f"{where}.roadOverrides")
            required={"wornTint","roughnessMultiplier","normalStrength","edgeFeather","textureScale"}
            if set(road)!=required:
                raise AuthoringError(f"{where}.roadOverrides must contain {sorted(required)}")
            tint=_vector(road["wornTint"],4,f"{where}.roadOverrides.wornTint")
            if min(tint)<0 or max(tint)>1:raise AuthoringError(f"{where}.roadOverrides.wornTint must be within zero and one")
            for field in ("roughnessMultiplier","normalStrength","edgeFeather","textureScale"):
                value=_number(road[field],f"{where}.roadOverrides.{field}")
                if value<0:raise AuthoringError(f"{where}.roadOverrides.{field} must be non-negative")
            if road["edgeFeather"]>1:raise AuthoringError(f"{where}.roadOverrides.edgeFeather must not exceed one")
            if road["textureScale"]<=0:raise AuthoringError(f"{where}.roadOverrides.textureScale must be positive")
        return
    if "roadOverrides" in record or "pbrOverrides" in record:
        raise AuthoringError(f"{where}: Custom surfaces use pbr, not preset overrides")
    _validate_pbr(record.get("pbr"),source_sha256,f"{where}.pbr")


def _validate_paths(document: dict[str, Any], source_sha256: dict[str, str]) -> None:
    paths = [_object(value, f"paths[{index}]")
             for index, value in enumerate(_array(document.get("paths"), "paths"))]
    _ordered_unique(paths, "paths")
    replacements = []
    for index, path in enumerate(paths):
        where = f"paths[{index}]"
        if path.get("kind") not in ("road", "river"):
            raise AuthoringError(f"{where}.kind must be road or river")
        if path.get("routingRole") not in ("required", "decorative"):
            raise AuthoringError(f"{where}.routingRole must be required or decorative")
        replacement = path.get("replacesRouteId")
        if replacement is not None:
            replacements.append(_string(replacement, f"{where}.replacesRouteId"))
        plan_feature = path.get("replacesPlanFeatureId")
        if plan_feature is not None:
            _string(plan_feature, f"{where}.replacesPlanFeatureId")
        if path["kind"] == "river" and replacement is not None:
            raise AuthoringError(f"{where}: a river cannot replace a composer road route")
        if path["kind"] == "road" and plan_feature is not None:
            raise AuthoringError(f"{where}: a road cannot replace a planned water feature")
        _object(path.get("properties"), f"{where}.properties")
        _validate_surface(path.get("surface"), source_sha256, f"{where}.surface")
        points = [_object(value, f"{where}.points[{point}]")
                  for point, value in enumerate(_array(path.get("points"), f"{where}.points"))]
        if len(points) < 2:
            raise AuthoringError(f"{where}.points needs at least two controls")
        for point, value in enumerate(points):
            _vector(value.get("position"), 3, f"{where}.points[{point}].position")
            if _number(value.get("width"), f"{where}.points[{point}].width") <= 0.0:
                raise AuthoringError(f"{where}.points[{point}].width must be positive")
    if len(replacements) != len(set(replacements)):
        raise AuthoringError("paths may replace a composer route only once")


def _validate_water_regions(document: dict[str, Any]) -> None:
    records = [_object(value, f"waterRegions[{index}]")
               for index, value in enumerate(
                   _array(document.get("waterRegions", []), "waterRegions"))]
    _ordered_unique(records, "waterRegions")
    for index, record in enumerate(records):
        where = f"waterRegions[{index}]"
        if record.get("shape") != "ellipse":
            raise AuthoringError(f"{where}.shape must be ellipse")
        replacement = record.get("replacesPlanFeatureId")
        if replacement is not None:
            _string(replacement, f"{where}.replacesPlanFeatureId")
        _string(record.get("name"), f"{where}.name")
        _vector(record.get("center"), 2, f"{where}.center")
        radii = _vector(record.get("radii"), 2, f"{where}.radii")
        if min(radii) <= 0.0:
            raise AuthoringError(f"{where}.radii must be positive")
        _number(record.get("level"), f"{where}.level")
        if _number(record.get("depth"), f"{where}.depth") < 0.0:
            raise AuthoringError(f"{where}.depth must be non-negative")


def _validate_replacements(document: dict[str, Any], production: bool,
                           contract: RegionContract | None = None) -> None:
    replacements = _object(document.get("replacements"), "replacements")
    route_ids = [_string(value, f"replacements.routeIds[{index}]")
                 for index, value in enumerate(
                     _array(replacements.get("routeIds"), "replacements.routeIds"))]
    feature_ids = [_string(value, f"replacements.planFeatureIds[{index}]")
                   for index, value in enumerate(
                       _array(replacements.get("planFeatureIds"), "replacements.planFeatureIds"))]
    ferry_ids = [_string(value, f"replacements.ferryConnectionIds[{index}]")
                 for index, value in enumerate(_array(
                     replacements.get("ferryConnectionIds", []),
                     "replacements.ferryConnectionIds"))]
    for name, values in (("routeIds", route_ids), ("planFeatureIds", feature_ids),
                         ("ferryConnectionIds", ferry_ids)):
        if values != sorted(values) or len(values) != len(set(values)):
            raise AuthoringError(f"replacements.{name} must be unique and sorted")
    paths = document["paths"]
    declared_routes = {path["replacesRouteId"] for path in paths
                       if path.get("replacesRouteId") is not None}
    feature_claims = [path["replacesPlanFeatureId"] for path in paths
                      if path.get("replacesPlanFeatureId") is not None]
    feature_claims.extend(
        region["replacesPlanFeatureId"]
        for region in document.get("waterRegions", [])
        if region.get("replacesPlanFeatureId") is not None)
    if len(feature_claims) != len(set(feature_claims)):
        raise AuthoringError("a planned water feature may be claimed by only one saved control")
    declared_features = set(feature_claims)
    if declared_routes - set(route_ids):
        raise AuthoringError("a path replaces a route the persistent registry does not own")
    if declared_features - set(feature_ids):
        raise AuthoringError("a path replaces a plan feature the persistent registry does not own")
    if production and contract is not None:
        required = set(contract.owned_route_ids)
        if set(route_ids) != required:
            missing = sorted(required - set(route_ids))
            extra = sorted(set(route_ids) - required)
            raise AuthoringError(
                f"{contract.id}: route replacement registry differs from its owned routes; "
                f"missing={missing}, extra={extra}")
        absent = sorted(set(contract.required_route_ids) - declared_routes)
        if absent:
            prefix = "required authored Sunmane routes" if contract.id == SUNMANE \
                else f"{contract.id}: required authored routes"
            raise AuthoringError(f"{prefix} are absent: {absent}")
        if tuple(feature_ids) != contract.owned_plan_feature_ids:
            raise AuthoringError(
                f"{contract.id}: plan feature registry must be "
                f"{list(contract.owned_plan_feature_ids)}")
        if tuple(ferry_ids) != contract.owned_ferry_connection_ids:
            raise AuthoringError(
                f"{contract.id}: ferry connection registry must be "
                f"{list(contract.owned_ferry_connection_ids)}")


def _validate_bridges(document: dict[str, Any], source_sha256: dict[str, str]) -> None:
    bridges = [_object(value, f"bridges[{index}]")
               for index, value in enumerate(_array(document.get("bridges"), "bridges"))]
    _ordered_unique(bridges, "bridges")
    for index, bridge in enumerate(bridges):
        where = f"bridges[{index}]"
        _vector(bridge.get("start"), 3, f"{where}.start")
        _vector(bridge.get("end"), 3, f"{where}.end")
        if bridge.get("collisionRole") != "walk_surface":
            raise AuthoringError(f"{where}.collisionRole must be walk_surface")
        for field in ("width", "arch", "waterClearance"):
            if _number(bridge.get(field), f"{where}.{field}") < 0.0:
                raise AuthoringError(f"{where}.{field} must be non-negative")
        _validate_surface(bridge.get("deckSurface"), source_sha256, f"{where}.deckSurface")
        _validate_surface(bridge.get("supportSurface"), source_sha256, f"{where}.supportSurface")


def _resolve_baked_path(entry: dict[str, Any], snapshot: Path) -> Path:
    relative = _string(_object(entry.get("bakedSource"), "object.bakedSource").get("path"),
                       "object.bakedSource.path")
    if relative.replace("\\", "/").startswith("godot-client/"):
        return _source_path(relative, "object.bakedSource.path")
    return _contained(snapshot.parent, relative, "object.bakedSource.path")


def _validate_objects(document: dict[str, Any], source_sha256: dict[str, str],
                      snapshot: Path, production: bool) -> None:
    objects = [_object(value, f"objects[{index}]")
               for index, value in enumerate(_array(document.get("objects"), "objects"))]
    _ordered_unique(objects, "objects")
    for index, entry in enumerate(objects):
        where = f"objects[{index}]"
        _string(entry.get("nodeName"), f"{where}.nodeName")
        _string(entry.get("assetId"), f"{where}.assetId")
        _vector(entry.get("matrix"), 16, f"{where}.matrix")
        if entry.get("collisionRole") not in ("none", "solid", "walk_surface"):
            raise AuthoringError(f"{where}.collisionRole is unsupported")
        scene_path = _string(entry.get("scenePath"), f"{where}.scenePath")
        if not scene_path.startswith("res://"):
            raise AuthoringError(f"{where}.scenePath must be a res:// source asset")
        source = _source_path("godot-client/" + scene_path.removeprefix("res://"), f"{where}.scenePath")
        relative = source.relative_to(CLIENT).as_posix()
        if relative not in source_sha256:
            raise AuthoringError(f"{where}.scenePath is not a hash-bound scene dependency")
        source_node = entry.get("sourceNode")
        if source_node is not None and not isinstance(source_node, str):
            raise AuthoringError(f"{where}.sourceNode must be a string")
        baked = _object(entry.get("bakedSource"), f"{where}.bakedSource")
        baked_path = _resolve_baked_path(entry, snapshot)
        _verify_hash(baked_path, baked.get("sha256"), f"{where}.bakedSource.sha256")
        baked_relative = baked_path.relative_to(CLIENT).as_posix()
        if baked.get("path", "").replace("\\", "/").startswith("godot-client/") and baked_relative not in source_sha256:
            raise AuthoringError(f"{where}.bakedSource.path is not a hash-bound scene dependency")
        if baked_path.suffix.lower() != ".glb":
            raise AuthoringError(f"{where}.bakedSource.path must be a static GLB")
        _string(baked.get("sourceNode"), f"{where}.bakedSource.sourceNode")
        metadata = _object(entry.get("metadata", {}), f"{where}.metadata")
        crossing = metadata.get("authoredCrossing")
        if crossing is not None:
            crossing = _object(crossing, f"{where}.metadata.authoredCrossing")
            _string(crossing.get("id"), f"{where}.metadata.authoredCrossing.id")
            _string(crossing.get("walkNode"),
                    f"{where}.metadata.authoredCrossing.walkNode")
            endpoints = _array(crossing.get("localEndpoints"),
                               f"{where}.metadata.authoredCrossing.localEndpoints")
            if len(endpoints) != 2:
                raise AuthoringError(
                    f"{where}.metadata.authoredCrossing.localEndpoints needs two points")
            for endpoint, point in enumerate(endpoints):
                _vector(point, 3,
                        f"{where}.metadata.authoredCrossing.localEndpoints[{endpoint}]")
        ferry = metadata.get("authoredFerryQuay")
        if ferry is not None:
            ferry = _object(ferry, f"{where}.metadata.authoredFerryQuay")
            if entry["collisionRole"] != "walk_surface":
                raise AuthoringError(f"{where}: an authored ferry quay needs walk_surface")
            _string(ferry.get("walkNode"), f"{where}.metadata.authoredFerryQuay.walkNode")
            _vector(ferry.get("localLanding"), 3,
                    f"{where}.metadata.authoredFerryQuay.localLanding")
            connections = [_string(value, f"{where}.metadata.authoredFerryQuay.connectionIds")
                           for value in _array(ferry.get("connectionIds"),
                                               f"{where}.metadata.authoredFerryQuay.connectionIds")]
            if not connections or connections != sorted(set(connections)) or \
                    not set(connections) <= set(document.get("replacements", {}).get(
                        "ferryConnectionIds", [])):
                raise AuthoringError(
                    f"{where}: authored ferry quay connections must be sorted claims in "
                    "persistent ferry replacements")
        overrides = [_object(value, f"{where}.materialOverrides[{override}]")
                     for override, value in enumerate(_array(
                         entry.get("materialOverrides", []), f"{where}.materialOverrides"))]
        for override, material in enumerate(overrides):
            material_where = f"{where}.materialOverrides[{override}]"
            if not isinstance(material.get("meshNodePath"), str):
                raise AuthoringError(f"{material_where}.meshNodePath must be a string")
            if "bakedMeshNodeIndex" in material:
                bound_index = material["bakedMeshNodeIndex"]
                if type(bound_index) is not int or bound_index < 0:
                    raise AuthoringError(f"{material_where}.bakedMeshNodeIndex must be a non-negative integer")
            surface_index = material.get("surfaceIndex")
            if isinstance(surface_index, bool) or not isinstance(surface_index, int) or surface_index < 0:
                raise AuthoringError(f"{material_where}.surfaceIndex must be a non-negative integer")
            _validate_surface(material.get("surface"), source_sha256, f"{material_where}.surface")


def _validate_v2_arrival(document, contract):
    """Optional v2 default metadata is validated lazily; legacy adapters keep their authored marker requirements."""
    if contract is None or contract.adapter != 'continent-v2-meshy-v1':
        if document.get('generatedArrival') is not None or document.get('sources',{}).get('generatedArrival') is not None:
            raise AuthoringError('generated arrival requires a registered continent-v2 authoring contract')
        return False
    import importlib.util
    import sys
    from types import SimpleNamespace
    checkout=contract.spec_path.resolve().parents[4]
    sources=document.get('sources',{})
    expected_spec={'path':contract.spec_path.relative_to(checkout).as_posix(),'sha256':sha256(contract.spec_path)}
    if sources.get('authoringSpec') != expected_spec or (contract.spec_sha256 is not None and contract.spec_sha256 != expected_spec['sha256']):
        raise AuthoringError('generated arrival authoring spec source changed; rebake')
    spec=json.loads(contract.spec_path.read_text(encoding='utf-8'))
    reference=spec.get('gameplay',{}).get('generatedArrival')
    if any(r.get('default') for r in document.get('gameplay',{}).get('spawnPoints',[])) and sources.get('generatedArrival') is not None:
        raise AuthoringError('authored and generated source bindings cannot mix')
    if reference is not None and reference not in sources.get('dependencies',[]):
        raise AuthoringError('generated arrival must be a hash-bound normal dependency')
    directory=checkout/'eloria-assets/maps/continent-v2/_continent_v2'
    # Explicit local imports avoid changing the legacy module's global import graph.
    def module(name,path):
        description=importlib.util.spec_from_file_location(name,path)
        result=importlib.util.module_from_spec(description);description.loader.exec_module(result)
        return result
    previous=sys.modules.get('ownership')
    try:
        sys.modules['ownership']=module('_eloria_v2_arrival_ownership',directory/'ownership.py')
        resolver=module('_eloria_v2_arrival_resolver',directory/'arrivals.py')
    finally:
        if previous is None:sys.modules.pop('ownership',None)
        else:sys.modules['ownership']=previous
    origin=tuple(contract.server_origin);cells=tuple(contract.server_cells);translation=tuple(contract.continent_translation)
    def tile(x,z):
        value=tuple(server_tile([x,0.,z],SimpleNamespace(contract=SimpleNamespace(server_origin=origin))))
        if not (0<=value[0]<cells[0] and 0<=value[1]<cells[1]):raise ValueError('arrival is outside storage')
        return value
    frame=SimpleNamespace(region=contract.id,origin=origin,cells=cells,translation=translation,tile=tile,
                          to_continent=lambda x,z:(x+translation[0],z+translation[2]))
    try:resolver.resolve(document,frame,checkout)
    except (ValueError,KeyError,OSError,TypeError) as error:raise AuthoringError(f'invalid continent-v2 arrival: {error}') from error
    return True


def _validate_gameplay(document: dict[str, Any], production: bool,
                       contract: RegionContract | None = None) -> None:
    gameplay = _object(document.get("gameplay"), "gameplay")
    assets = {entry["id"]: entry["nodeName"] for entry in document["objects"]}
    required = ("spawnPoints", "portals", "interactives", "landmarks", "harvestables",
                "npcMarkers", "ambientPopulation")
    if production or "runtimePoints" in gameplay:
        required += ("runtimePoints",)
    marker_ids: dict[str, set[str]] = {}
    for section in required:
        records = [_object(value, f"gameplay.{section}[{index}]")
                   for index, value in enumerate(_array(gameplay.get(section), f"gameplay.{section}"))]
        if section == "landmarks" and document.get("regionId") == "manymouth_delta":
            ids = [_string(record.get("id"), f"gameplay.{section}[{index}].id")
                   for index, record in enumerate(records)]
            if ids != sorted(ids) or any(ids.count(identity) > (2 if identity == "stelae-court" else 1)
                                          for identity in set(ids)):
                raise AuthoringError("Manymouth landmarks must retain sorted unique published identities")
            pair = [record.get("node") for record in records
                    if record["id"] == "stelae-court"]
            allowed_pair = {"Landmark_StelaeCourt", "Lore_stelae_court"}
            if len(pair) != len(set(pair)) or any(node not in allowed_pair for node in pair):
                raise AuthoringError("Manymouth's published stelae-court pair must keep distinct source nodes")
        else:
            _ordered_unique(records, f"gameplay.{section}")
        marker_ids[section] = {record["id"] for record in records}
        for index, record in enumerate(records):
            where = f"gameplay.{section}[{index}]"
            if "matrix" in record:
                _vector(record["matrix"], 16, f"{where}.matrix")
            elif "position" in record:
                _vector(record["position"], 3, f"{where}.position")
            else:
                raise AuthoringError(f"{where} needs a position or matrix")
            asset_id = record.get("assetId")
            if asset_id is not None:
                asset_id = _string(asset_id, f"{where}.assetId")
                if asset_id not in assets:
                    raise AuthoringError(f"{where}.assetId does not identify an authored asset")
                node = record.get("node")
                if node is not None and node != assets[asset_id]:
                    raise AuthoringError(f"{where}.node disagrees with its authored assetId")
    v2_arrival_valid = _validate_v2_arrival(document, contract)
    if not gameplay["spawnPoints"] and not v2_arrival_valid:
        raise AuthoringError("gameplay.spawnPoints must retain an authored spawn")
    if not gameplay["portals"] and not v2_arrival_valid:
        raise AuthoringError("gameplay.portals must retain authored links")
    if not production and "runtimeBindings" not in gameplay:
        if v2_arrival_valid:
            raise AuthoringError("registered v2 gameplay must explicitly record runtimeBindings")
        return
    bindings = [_object(value, f"gameplay.runtimeBindings[{index}]")
                for index, value in enumerate(_array(
                    gameplay.get("runtimeBindings"), "gameplay.runtimeBindings"))]
    _ordered_unique(bindings, "gameplay.runtimeBindings")
    roles = {"door", "return", "interactive", "npc", "harvest", "spawn", "territory"}
    referenced_runtime_points: set[str] = set()
    existing_marker_bindings = 0
    for index, binding in enumerate(bindings):
        where = f"gameplay.runtimeBindings[{index}]"
        source = _object(binding.get("source"), f"{where}.source")
        source_path = _string(source.get("path"), f"{where}.source.path").replace("\\", "/")
        if source_path.startswith("/") or ".." in Path(source_path).parts:
            raise AuthoringError(f"{where}.source.path must be a contained relative profile path")
        line = source.get("line")
        if isinstance(line, bool) or not isinstance(line, int) or line <= 0:
            raise AuthoringError(f"{where}.source.line must be a positive integer")
        _integer_vector(source.get("oldTile"), 2, f"{where}.source.oldTile")
        if "recordId" in source:
            _string(source["recordId"], f"{where}.source.recordId")
        marker = _object(binding.get("marker"), f"{where}.marker")
        section = _string(marker.get("section"), f"{where}.marker.section")
        identity = _string(marker.get("id"), f"{where}.marker.id")
        if section not in marker_ids or identity not in marker_ids[section]:
            raise AuthoringError(f"{where}.marker does not resolve exactly in gameplay.{section}")
        if binding.get("role") not in roles:
            raise AuthoringError(f"{where}.role is unsupported")
        if binding.get("roads") not in ("marker", "entrance"):
            raise AuthoringError(f"{where}.roads must be marker or entrance")
        target_offset = _vector(binding.get("targetOffset"), 3, f"{where}.targetOffset")
        if target_offset[1] != 0.0:
            raise AuthoringError(f"{where}.targetOffset vertical component must be zero")
        if section == "runtimePoints":
            if target_offset != (0.0, 0.0, 0.0):
                raise AuthoringError(f"{where}.targetOffset must be zero for a dedicated runtime point")
            referenced_runtime_points.add(identity)
        else:
            existing_marker_bindings += 1
        provenance = _object(binding.get("provenance"), f"{where}.provenance")
        for field in ("sourceReportSha256", "sourceProfileSha256"):
            if field == "sourceProfileSha256" and field not in provenance:
                continue
            digest = _string(provenance.get(field), f"{where}.provenance.{field}")
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise AuthoringError(f"{where}.provenance.{field} must be a lowercase SHA-256 digest")
    unbound_v2_controls = v2_arrival_valid and not bindings and all(
        getattr(contract, field, None) == 0 for field in (
            "runtime_binding_count", "existing_marker_binding_count")) and (
        len(gameplay.get("runtimePoints", [])) == getattr(contract, "runtime_point_count", None))
    if (production or v2_arrival_valid) and contract is not None:
        if len(bindings) != contract.runtime_binding_count:
            raise AuthoringError(
                f"{contract.id}: gameplay.runtimeBindings must cover all "
                f"{contract.runtime_binding_count} runtime records")
        if len(gameplay["runtimePoints"]) != contract.runtime_point_count:
            raise AuthoringError(
                f"{contract.id}: gameplay.runtimePoints must retain all "
                f"{contract.runtime_point_count} dedicated runtime controls")
        if referenced_runtime_points != marker_ids.get("runtimePoints", set()) and not unbound_v2_controls:
            raise AuthoringError(
                f"{contract.id}: every dedicated runtime point must be referenced by a binding")
        if existing_marker_bindings != contract.existing_marker_binding_count:
            raise AuthoringError(
                f"{contract.id}: runtime binding offsets disagree with the region contract")
    seed_source = document["sources"].get("runtimeBindingSeed")
    if seed_source is None:
        # New v2 maps retain dedicated scene controls without inheriting server
        # profile bindings; their exact saved count remains contract-checked.
        if unbound_v2_controls:
            return
        raise AuthoringError("sources.runtimeBindingSeed is required for authored runtime bindings")
    seed_path = _source_path(seed_source["path"], "sources.runtimeBindingSeed.path")
    seed = _object(json.loads(seed_path.read_text(encoding="utf-8")), "runtime binding seed")
    region_id = _string(document.get("regionId"), "regionId")
    if (seed.get("schema") != "eloria-runtime-binding-seed-v1" or
            seed.get("regionId") != region_id):
        raise AuthoringError("runtime binding seed schema or region is unsupported")
    provenance = _object(seed.get("provenance"), "runtime binding seed.provenance")
    profile_hashes = {
        entry["path"].replace("\\", "/").split("legacy-server-profile/", 1)[-1]: entry["sha256"]
        for entry in _array(provenance.get("profileFiles"), "runtime binding seed.provenance.profileFiles")}
    expected = []
    for index, value in enumerate(_array(seed.get("bindings"), "runtime binding seed.bindings")):
        record = dict(_object(value, f"runtime binding seed.bindings[{index}]"))
        record.pop("initialPosition", None)
        source = _object(record.get("source"), f"runtime binding seed.bindings[{index}].source")
        record["provenance"] = {"sourceReportSha256": provenance["sourceReportSha256"]}
        profile_digest = profile_hashes.get(source.get("path", "").replace("\\", "/"))
        if profile_digest is not None:
            record["provenance"]["sourceProfileSha256"] = profile_digest
        expected.append(record)
    if bindings != expected:
        raise AuthoringError("gameplay.runtimeBindings do not exactly match the hash-bound seed")


def _validate_seams(document: dict[str, Any]) -> None:
    seams = _object(document.get("seams"), "seams")
    digest = _string(seams.get("ownershipPolygonSha256"), "seams.ownershipPolygonSha256")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise AuthoringError("seams.ownershipPolygonSha256 must be a lowercase SHA-256 digest")
    anchors = [_object(value, f"seams.anchors[{index}]")
               for index, value in enumerate(_array(seams.get("anchors"), "seams.anchors"))]
    _ordered_unique(anchors, "seams.anchors")
    for index, anchor in enumerate(anchors):
        _vector(anchor.get("anchor"), 3, f"seams.anchors[{index}].anchor")


@dataclass(frozen=True)
class Snapshot:
    path: Path
    document: dict[str, Any]
    source_sha256: dict[str, str]
    base_heights_path: Path
    resolved_heights_path: Path
    terrain_width: int
    terrain_height: int
    contract: RegionContract | None = None

    @property
    def digest(self) -> str:
        return sha256(self.path)

    @property
    def translation(self) -> np.ndarray:
        return np.asarray(self.document["continentTranslation"], dtype=np.float64)

    def continent_point(self, local: Iterable[float]) -> np.ndarray:
        point = np.asarray(tuple(local), dtype=np.float64)
        if point.shape != (3,) or not np.isfinite(point).all():
            raise AuthoringError("local point must contain three finite numbers")
        return point + self.translation

    def base_heights(self) -> np.ndarray:
        return np.fromfile(self.base_heights_path, dtype="<f4").reshape(
            self.terrain_height, self.terrain_width).astype(np.float64)

    def effective_heights(self) -> np.ndarray:
        """Read the exact final height grid shown by the editor preview."""
        return np.fromfile(self.resolved_heights_path, dtype="<f4").reshape(
            self.terrain_height, self.terrain_width).astype(np.float64)

    def base_colors(self) -> np.ndarray | None:
        """Return optional exact sRGB RGBA8 vertex colors for this terrain."""
        record = self.document["terrain"].get("baseColors")
        if record is None:
            return None
        path = _contained(self.path.parent, record["path"], "terrain.baseColors.path")
        return np.fromfile(path, dtype=np.uint8).reshape(
            self.terrain_height, self.terrain_width, 4)

    def replacement_paths(self) -> dict[str, dict[str, Any]]:
        """Exact composer route identities owned by this authored scene."""
        return {path["replacesRouteId"]: path for path in self.document["paths"]
                if path.get("replacesRouteId") is not None}

    def bound_sources(self) -> dict[str, str]:
        """Every raw source or sidecar whose bytes certify this snapshot."""
        result = dict(self.source_sha256)
        spec_record = self.document.get("sources", {}).get("authoringSpec")
        if spec_record is not None:
            import ownership_contract
            spec_path = ownership_contract.contained_path(CLIENT, spec_record["path"])
            if sha256(spec_path) != spec_record["sha256"]:
                raise AuthoringError("authoring spec changed after snapshot load; rebake before composition")
        if self.contract is not None:
            # Catalog membership and the strict region contract decide which
            # scene is authoritative and how its local frame enters the shared
            # continent. They are composition inputs even though the Godot
            # scene does not depend on them as res:// resources.
            for path in (self.contract.spec_path, CATALOG_PATH):
                current = sha256(path)
                if path == self.contract.spec_path and self.contract.spec_sha256 is not None and current != self.contract.spec_sha256:
                    raise AuthoringError("authoring spec changed after catalog load; reload before composition")
                result[path.relative_to(CLIENT).as_posix()] = current
        for field in ("baseHeights", "resolvedHeights", "baseColors"):
            if field not in self.document["terrain"]:
                continue
            path = _contained(self.path.parent, self.document["terrain"][field]["path"],
                              f"terrain.{field}.path")
            result[path.relative_to(CLIENT).as_posix()] = sha256(path)
        result[self.path.relative_to(CLIENT).as_posix()] = self.digest
        for entry in self.document["objects"]:
            path = _resolve_baked_path(entry, self.path)
            result[path.relative_to(CLIENT).as_posix()] = sha256(path)
        for pattern in AUTHORING_FRAMEWORK_GLOBS:
            matches = sorted(CLIENT.glob(pattern))
            if not matches:
                raise AuthoringError(f"authoring framework source glob has no files: {pattern}")
            for path in matches:
                result[path.relative_to(CLIENT).as_posix()] = sha256(path)
        return dict(sorted(result.items()))


def apply_plan(plan: dict[str, Any], snapshot: Snapshot) -> dict[str, Any]:
    """Suppress owned procedural water and install authored water paths.

    The persistent registry is applied independently of surviving path nodes,
    so deleting the authored river deletes it rather than reviving the old
    planned channel.
    """
    import copy
    result = copy.deepcopy(plan)
    sites = _object(result.setdefault("connection_sites", {}), "plan.connection_sites")
    for anchor in snapshot.document["seams"]["anchors"]:
        identity = anchor["id"]
        point = snapshot.continent_point(anchor["anchor"])[[0, 2]].tolist()
        registered = sites.get(identity)
        if registered is not None and not np.allclose(
                np.asarray(registered, dtype=np.float64), point, atol=1e-6, rtol=0.0):
            raise AuthoringError(
                f"{identity}: saved seam anchor conflicts with registered connection site "
                f"{registered}; update the shared connection contract explicitly")
        sites[identity] = point
    owned = set(snapshot.document["replacements"]["planFeatureIds"])
    # A saved full-grid terrain surface can own a named procedural island
    # without a live water/path control.  Suppress that exact old landform by
    # its stable source ID before World samples the plan, even if the author
    # later lowers or deletes the island in the scene. Crownwater's ferry
    # exclusion is recovered separately from saved crossing/quay assets.
    result["islands"] = [entry for entry in result.get("islands", [])
                         if entry.get("crownSourceIsland") not in owned]
    prior = {entry.get("id"): entry for entry in result.get("rivers", [])
             if entry.get("id") in owned}
    def lake_identity(entry: dict[str, Any]) -> str | None:
        if entry.get("id"):
            return str(entry["id"])
        source = NAMELESS_PUBLISHED_LAKES.get(entry.get("name"))
        if source is None:
            return None
        identity, center, radii, level, depth = source
        if tuple(entry.get("center", ())) != center or \
                tuple(entry.get("radii", ())) != radii or \
                entry.get("level") != level or entry.get("depth") != depth:
            raise AuthoringError(f"{identity}: idless published lake source record changed")
        return identity

    lake_ids = [lake_identity(entry) for entry in result.get("lakes", [])]
    if len([identity for identity in lake_ids if identity is not None]) != \
            len({identity for identity in lake_ids if identity is not None}):
        raise AuthoringError("published lake source identities are duplicated")
    prior_lakes = {lake_identity(entry): entry for entry in result.get("lakes", [])
                   if lake_identity(entry) in owned}
    result["rivers"] = [entry for entry in result.get("rivers", [])
                        if entry.get("id") not in owned]
    result["lakes"] = [entry for entry in result.get("lakes", [])
                       if lake_identity(entry) not in owned]
    for path in snapshot.document["paths"]:
        if path["kind"] != "river":
            continue
        replacement = path.get("replacesPlanFeatureId")
        properties = path.get("properties", {})
        widths = np.asarray([float(point["width"]) * 0.5 for point in path["points"]])
        required = ("channelDepth", "valleyWidth", "bankHeight")
        missing = [field for field in required if field not in properties]
        if missing:
            raise AuthoringError(f"{path['id']}: river properties missing {missing}")
        identity = replacement or path["id"]
        record = {
            "id": identity,
            "name": str(properties.get("name", identity)),
            "authoredSampled": True,
            "width": float(widths.max()),
            "widths": widths.tolist(),
            "depth": _number(properties["channelDepth"], f"{path['id']}.properties.channelDepth"),
            "valley_width": _number(properties["valleyWidth"], f"{path['id']}.properties.valleyWidth"),
            "bank_height": _number(properties["bankHeight"], f"{path['id']}.properties.bankHeight"),
            "points": [[float(global_point[0]), float(global_point[2]), float(global_point[1]),
                        float(width)]
                       for global_point, width in zip(
                           (snapshot.continent_point(point["position"]) for point in path["points"]), widths)],
        }
        # Topology fields are explicit authored properties.  The existing
        # feature is consulted only to validate migration completeness, never
        # copied as a mutable fallback.
        topology = [field for field in ("mouth", "joins", "joins_from", "delta")
                    if field in properties]
        if not topology:
            old = prior.get(replacement)
            expected = [field for field in ("mouth", "joins", "joins_from")
                        if old is not None and field in old]
            if expected:
                raise AuthoringError(
                    f"{path['id']}: river properties must freeze one of {expected} from the retired plan feature")
        for field in topology:
            record[field] = copy.deepcopy(properties[field])
        for field in ("bankShelfWidth", "bankShelfHeight", "cutsRelief"):
            if field in properties:
                target = {"bankShelfWidth": "bank_shelf_width",
                          "bankShelfHeight": "bank_shelf_height",
                          "cutsRelief": "cuts_relief"}[field]
                record[target] = copy.deepcopy(properties[field])
        result["rivers"].append(record)
    for water in snapshot.document.get("waterRegions", []):
        replacement = water.get("replacesPlanFeatureId")
        identity = replacement or water["id"]
        if water["shape"] != "ellipse":
            raise AuthoringError(f"{water['id']}: unsupported water region shape")
        center = np.asarray(water["center"], dtype=np.float64) + snapshot.translation[[0, 2]]
        record = {
            "id": identity,
            "name": water["name"] or identity,
            "center": center.tolist(),
            "radii": [float(value) for value in water["radii"]],
            "level": float(water["level"]) + float(snapshot.translation[1]),
            # Reference metadata for the retired procedural bed.  Authored
            # resolved terrain remains the actual lake bed authority.
            "depth": float(water["depth"]),
            "authored": True,
            "resolvedBedAuthority": "saved-terrain",
        }
        old = prior_lakes.get(replacement)
        if replacement is not None and old is None:
            raise AuthoringError(
                f"{water['id']}: claimed lake {replacement!r} is absent from the plan")
        result["lakes"].append(record)
    return result


def apply_plans(plan: dict[str, Any], snapshots: Iterable[Snapshot]) -> dict[str, Any]:
    """Apply persistent authored feature registries with duplicate-claim checks."""
    ordered = tuple(snapshots)
    claims: dict[str, str] = {}
    for snapshot in ordered:
        region = snapshot.document["regionId"]
        for identity in snapshot.document["replacements"]["planFeatureIds"]:
            previous = claims.get(identity)
            if previous is not None:
                raise AuthoringError(
                    f"planned feature {identity!r} is claimed by both "
                    f"{previous} and {region}")
            claims[identity] = region
    result = plan
    for snapshot in ordered:
        result = apply_plan(result, snapshot)
    return result


def _register_road_fields(world: Any, road: dict[str, Any]) -> None:
    """Register an exact saved centreline without recomputing its Y profile."""
    points = np.asarray(road["points"], dtype=np.float64)
    widths = np.asarray(road.get("widths", [float(road["width"])] * len(points)), dtype=np.float64)
    if len(widths) != len(points):
        raise AuthoringError(f"{road['id']}: road widths must match road points")
    for segment, (a, b) in enumerate(zip(points, points[1:])):
        horizontal_a, horizontal_b = a[[0, 2]], b[[0, 2]]
        segment_width=max(float(widths[segment]),float(widths[segment+1]))
        shoulder = max(16.0, segment_width * 4.0)
        low = np.minimum(horizontal_a, horizontal_b) - segment_width - shoulder
        high = np.maximum(horizontal_a, horizontal_b) + segment_width + shoulder
        ix0 = max(0, int((low[0] - world.x0) / 2.0))
        ix1 = min(len(world.x), int((high[0] - world.x0) / 2.0) + 2)
        iz0 = max(0, int((low[1] - world.z0) / 2.0))
        iz1 = min(len(world.z), int((high[1] - world.z0) / 2.0) + 2)
        sl = np.s_[iz0:iz1, ix0:ix1]
        delta = horizontal_b - horizontal_a
        amount = np.clip(((world.gx[sl] - horizontal_a[0]) * delta[0] +
                          (world.gz[sl] - horizontal_a[1]) * delta[1]) /
                         max(float(delta @ delta), 1e-9), 0.0, 1.0)
        distance = np.hypot(world.gx[sl] - horizontal_a[0] - amount * delta[0],
                            world.gz[sl] - horizontal_a[1] - amount * delta[1])
        width = widths[segment] * (1.0 - amount) + widths[segment + 1] * amount
        world.road_distance[sl] = np.minimum(world.road_distance[sl], distance / width)
        target = a[1] * (1.0 - amount) + b[1] * amount
        closer = distance < world.road_nearest[sl]
        world.road_target[sl] = np.where(closer, target, world.road_target[sl])
        world.road_nearest[sl] = np.minimum(world.road_nearest[sl], distance)


def replace_routes(world: Any, snapshot: Snapshot) -> dict[str, Any]:
    """Replace every scene-owned composer route, then rebuild road rasters."""
    owned = set(snapshot.document["replacements"]["routeIds"])
    procedural_count = sum(road["id"] in owned for road in world.roads)
    authored = []
    road_paths={path.get("replacesRouteId") or path["id"]:path
                for path in snapshot.document["paths"] if path["kind"]=="road"}
    for identity in sorted(road_paths):
        path = road_paths[identity]
        widths = np.asarray([float(point["width"]) * 0.5 for point in path["points"]])
        points = [snapshot.continent_point(point["position"]).tolist() for point in path["points"]]
        authored.append({"id": identity, "points": points, "width": float(widths.max()),
                         "widths": widths.tolist(),
                         "authoringId": path["id"]})
    by_id = {road["id"]: road for road in authored}
    rebuilt=[];seen=set()
    for road in world.roads:
        identity=road["id"]
        if identity in owned:
            if identity in by_id and identity not in seen:
                rebuilt.append(by_id[identity]);seen.add(identity)
        else:rebuilt.append(road)
    rebuilt.extend(by_id[identity] for identity in sorted(by_id) if identity not in seen)
    world.roads = rebuilt
    world.road_distance = np.full_like(world.height, np.inf)
    world.road_nearest = np.full_like(world.height, np.inf)
    world.road_target = world.height.copy()
    for road in world.roads:
        _register_road_fields(world, road)
    # These claims belonged to the retired procedural Sunmane alignments.  An
    # authored bridge is exported directly from its saved endpoints, so the
    # claimed-site fitter must neither grade its terrain nor regenerate it.
    suppressed=[]
    retained=[]
    region = snapshot.document["regionId"]
    for site in getattr(world, "crossing_sites", ()):
        if site.get("region") == region:
            suppressed.append(int(site["id"]))
        else:
            retained.append(site)
    if suppressed:
        world.crossing_sites=retained
        world.crossing_site_use={key:value for key,value in world.crossing_site_use.items()
                                 if key not in suppressed}
        world.crossing_site_roads={key:value for key,value in world.crossing_site_roads.items()
                                   if key not in suppressed}
        world.crossing_version=getattr(world,"crossing_version",0)+1
    return {"ownedRouteIds": sorted(owned), "authoredRoutes": len(authored),
            "removedProceduralRoutes": int(procedural_count),
            "suppressedProceduralBridgeSiteIds":suppressed}


def marker_position(record: dict[str, Any]) -> list[float]:
    """Return the local translation stored by a gameplay marker."""
    if "matrix" in record:
        matrix = _vector(record["matrix"], 16, "gameplay marker matrix")
        return [matrix[12], matrix[13], matrix[14]]
    return list(_vector(record.get("position"), 3, "gameplay marker position"))


def server_tile(position: Iterable[float], snapshot: Snapshot | None = None) -> list[int]:
    """Derive the published tile from a territory-local marker position."""
    x, _, z = _vector(list(position), 3, "gameplay marker position")
    origin = (snapshot.contract.server_origin if snapshot is not None and snapshot.contract
              is not None else SUNMANE_SERVER_ORIGIN)
    return [math.floor(x + origin[0]), math.floor(origin[1] - z)]


def authored_gameplay(snapshot: Snapshot) -> dict[str, Any]:
    """Build complete manifest sections; absence means deletion, never fallback."""
    result: dict[str, Any] = {}
    for name, records in snapshot.document["gameplay"].items():
        if name == "runtimeBindings":
            continue
        authored = []
        for source in records:
            import copy
            entry = {key: copy.deepcopy(value) for key, value in source.items()
                     if key not in ("id", "position", "matrix", "extras")}
            extras = _object(source.get("extras", {}), f"gameplay.{name}.{source['id']}.extras")
            forbidden = {"id", "position", "serverTile", "matrix", "center"} & extras.keys()
            if forbidden:
                raise AuthoringError(
                    f"gameplay.{name}.{source['id']}.extras cannot replace {sorted(forbidden)}")
            overlap = set(entry) & set(extras)
            if overlap:
                raise AuthoringError(
                    f"gameplay.{name}.{source['id']}.extras duplicates top-level fields {sorted(overlap)}")
            entry.update(copy.deepcopy(extras))
            position = marker_position(source)
            entry.update(id=source["id"], position=position,
                         serverTile=server_tile(position, snapshot))
            if name in ("harvestables", "ambientPopulation"):
                entry["center"] = list(position)
            authored.append(entry)
        result[name] = authored
    return result


def apply_runtime_bindings(content: Any, snapshot: Snapshot) -> dict[str, Any]:
    """Install exact profile-record identities backed by saved gameplay markers.

    These bindings deliberately do not populate the old tile-only override.
    Multiple profile records can share an old tile while remaining separately
    authored, and every contract lookup must therefore name its binding id.
    """
    gameplay = snapshot.document["gameplay"]
    sections = {name: {record["id"]: record for record in records}
                for name, records in gameplay.items()
                if name != "runtimeBindings"}
    region = snapshot.document["regionId"]
    points: dict[tuple[str, str], np.ndarray] = dict(
        getattr(content, "authored_runtime_points", {}))
    records: dict[str, dict[str, Any]] = {}
    source_index: dict[tuple[str, int, tuple[int, int]], str] = {}
    source_lines: dict[tuple[str, int], list[str]] = {}
    source_tiles: dict[tuple[str, tuple[int, int]], list[str]] = {}
    entrance_tiles = set(getattr(content, "entrance_road_tiles", ()))
    for binding in gameplay["runtimeBindings"]:
        identity = binding["id"]
        marker = binding["marker"]
        local = np.asarray(marker_position(sections[marker["section"]][marker["id"]]),
                           dtype=np.float64)
        offset = np.asarray(binding["targetOffset"], dtype=np.float64)
        # Endpoint offsets are horizontal semantic differences (for example a
        # cave doorway and its return square). Marker Y remains the saved scene
        # authority while every linked endpoint translates with marker edits.
        local[[0, 2]] += offset[[0, 2]]
        point = snapshot.continent_point(local)
        points[(region, identity)] = point
        records[identity] = binding
        source = binding["source"]
        source_key = (source["path"].replace("\\", "/"), int(source["line"]),
                      tuple(map(int, source["oldTile"])))
        if source_key in source_index:
            raise AuthoringError(f"duplicate runtime source identity {source_key}")
        source_index[source_key] = identity
        line_key = (source_key[0], source_key[1])
        source_lines.setdefault(line_key, []).append(identity)
        source_tiles.setdefault((source_key[0], source_key[2]), []).append(identity)
        if binding["roads"] == "entrance":
            entrance_tiles.add((region, tuple(map(int, source["oldTile"]))))
    content.authored_runtime_points = points
    by_region = dict(getattr(content, "runtime_bindings_by_region", {}))
    by_region[region] = records
    content.runtime_bindings_by_region = by_region
    flat = dict(getattr(content, "runtime_bindings", {}))
    duplicates = set(flat) & set(records)
    if duplicates:
        raise AuthoringError(
            f"{region}: runtime binding ids collide across authored regions: {sorted(duplicates)}")
    flat.update(records)
    content.runtime_bindings = flat
    merged_sources = dict(getattr(content, "runtime_binding_sources", {}))
    for key, identity in source_index.items():
        if key in merged_sources:
            raise AuthoringError(f"{region}: duplicate runtime source identity {key}")
        merged_sources[key] = identity
    content.runtime_binding_sources = merged_sources
    merged_lines = {key: list(values) for key, values in
                    getattr(content, "runtime_binding_source_lines", {}).items()}
    for key, values in source_lines.items():
        merged_lines.setdefault(key, []).extend(values)
    content.runtime_binding_source_lines = {
        key: tuple(sorted(values)) for key, values in merged_lines.items()}
    merged_tiles = {key: list(values) for key, values in
                    getattr(content, "runtime_binding_source_tiles", {}).items()}
    for key, values in source_tiles.items():
        merged_tiles.setdefault(key, []).extend(values)
    content.runtime_binding_source_tiles = {
        key: tuple(sorted(values)) for key, values in merged_tiles.items()}
    content.entrance_road_tiles = entrance_tiles
    return {"bindings": len(records), "runtimePoints": len(gameplay["runtimePoints"])}


def apply_gameplay(template: dict[str, Any], snapshot: Snapshot) -> dict[str, Any]:
    """Replace all scene-owned Sunmane gameplay sections by stable ID."""
    import copy
    result = copy.deepcopy(template)
    authored = authored_gameplay(snapshot)
    for section in ("spawnPoints", "portals", "interactives", "landmarks",
                    "harvestables", "npcMarkers"):
        result[section] = authored[section]
    # ``spawns`` is the legacy alias still read by a few consumers.
    result["spawns"] = copy.deepcopy(authored["spawnPoints"])
    note = result.get("ambientPopulation", {}).get("note")
    result["ambientPopulation"] = {"groups": authored["ambientPopulation"]}
    if note is not None:
        result["ambientPopulation"]["note"] = note
    return result


def required_terrain_vertices(owner: np.ndarray, region_index: int,
                              vertex_shape: tuple[int, int]) -> np.ndarray:
    """Full in-world incident-owned-vertex mask plus one 3x3 seam ring."""
    from scipy.ndimage import binary_dilation
    cells = owner == region_index
    if cells.shape == vertex_shape:
        owned = cells  # Small legacy fixtures may provide vertex ownership.
    elif cells.shape == (vertex_shape[0] - 1, vertex_shape[1] - 1):
        owned = np.zeros(vertex_shape, dtype=bool)
        owned[:-1, :-1] |= cells
        owned[1:, :-1] |= cells
        owned[:-1, 1:] |= cells
        owned[1:, 1:] |= cells
    else:
        raise AuthoringError(f"shared ownership shape {cells.shape} does not match terrain {vertex_shape}")
    return binary_dilation(owned, structure=np.ones((3, 3), dtype=bool))


def validate_required_coverage(required: np.ndarray, ix: np.ndarray, iz: np.ndarray,
                               region: str, world_origin=(0.0, 0.0), cell=2.0) -> None:
    """Reject missing required global vertices before local-envelope clipping."""
    missing = required.copy()
    columns = ix[(ix >= 0) & (ix < required.shape[1])]
    rows = iz[(iz >= 0) & (iz < required.shape[0])]
    missing[np.ix_(rows, columns)] = False
    if missing.any():
        row, column = np.argwhere(missing)[0]
        point = [world_origin[0] + int(column) * cell, world_origin[1] + int(row) * cell]
        raise AuthoringError(f"{region}: authored envelope omits {int(missing.sum())} required ownership/ring vertices; first global vertex {point}")


def apply_terrain(world: Any, snapshot: Snapshot) -> dict[str, Any]:
    """Install the scene preview's final vertices on the shared grid.

    Each authored envelope may overlap neighbouring ownership. It is clipped
    by its territory's owned vertices plus one shared-grid ring so later
    partitioning reads the same seam vertices from both sides.
    """
    origin = np.asarray(snapshot.document["terrain"]["origin"], dtype=np.float64)
    global_origin = origin + snapshot.translation[[0, 2]]
    heights = snapshot.effective_heights()
    cell = float(snapshot.document["terrain"]["cellMetres"])
    if cell != 2.0:
        raise AuthoringError(
            f"{snapshot.document['regionId']}: authored terrain cellMetres must match the shared two-metre grid")
    x = global_origin[0] + np.arange(snapshot.terrain_width) * cell
    z = global_origin[1] + np.arange(snapshot.terrain_height) * cell
    ix = np.rint((x - world.x0) / cell).astype(int)
    iz = np.rint((z - world.z0) / cell).astype(int)
    aligned_x = world.x0 + ix * cell
    aligned_z = world.z0 + iz * cell
    if not np.allclose(aligned_x, x, rtol=0.0, atol=1e-9) or not np.allclose(aligned_z, z, rtol=0.0, atol=1e-9):
        raise AuthoringError("authored terrain is not aligned to the shared two-metre grid")
    keep_x = (ix >= 0) & (ix < world.height.shape[1])
    keep_z = (iz >= 0) & (iz < world.height.shape[0])
    if not keep_x.any() or not keep_z.any():
        raise AuthoringError("authored terrain does not intersect the shared continent")
    source = heights[np.ix_(keep_z, keep_x)]
    target = np.ix_(iz[keep_z], ix[keep_x])
    authority = np.ones(source.shape, dtype=bool)
    region = snapshot.document["regionId"]
    if hasattr(world, "owner") and hasattr(world, "ids") and region in world.ids:
        required = required_terrain_vertices(world.owner, world.ids.index(region), world.height.shape)
        if getattr(world, "ownership_contract", None) is not None:
            validate_required_coverage(required, ix, iz, region, (world.x0, world.z0), cell)
        authority = required[target]
    current = world.height[target]
    previous_authority = getattr(world, "authored_terrain_authority", None)
    previous_height = getattr(world, "authored_terrain_height", None)
    if previous_authority is not None:
        overlap = previous_authority[target] & authority
        mismatch = overlap & (np.abs(previous_height[target] - source) > 1e-5)
        if mismatch.any():
            existing = sorted(name for name, mask in
                              getattr(world, "authored_terrain_region_masks", {}).items()
                              if (mask[target] & mismatch).any())
            raise AuthoringError(
                f"{region}: authored terrain conflicts with {existing} on "
                f"{int(mismatch.sum())} shared ownership-ring vertices")
    world.height[target] = np.where(authority, source, current)
    # Road grading may fit neighbouring approaches to these vertices, but it
    # must not temporarily grade them and rely on a later restore.  That can
    # make a terminal look feasible during settlement and leave a cliff when
    # the exact editor preview is reinstated.  Keep the full-grid mask/value
    # pair on the world so every road pass treats the same saved vertices as
    # fixed ground.
    if previous_authority is None:
        world.authored_terrain_authority = np.zeros_like(world.height, dtype=bool)
    # Snapshot samples are f32 by contract; retaining them as f32 avoids a
    # second continent-sized f64 height allocation while preserving every
    # authoritative bit.
        world.authored_terrain_height = np.zeros_like(world.height, dtype=np.float32)
        world.authored_terrain_region_masks = {}
    world.authored_terrain_authority[target] |= authority
    stored = world.authored_terrain_height[target]
    world.authored_terrain_height[target] = np.where(authority, source, stored)
    region_mask = np.zeros_like(world.height, dtype=bool)
    region_mask[target] = authority
    world.authored_terrain_region_masks[region] = region_mask
    return {"sourceVertices": int(heights.size),
            "appliedVertices": int(authority.sum()),
            "globalBounds": [[float(x[0]), float(z[0])], [float(x[-1]), float(z[-1])]]}


def source_asset_path(scene_path: str) -> Path:
    if not scene_path.startswith("res://"):
        raise AuthoringError("authored object scenePath must start with res://")
    return _source_path("godot-client/" + scene_path.removeprefix("res://"), "object.scenePath")


def baked_asset_path(entry: dict[str, Any], snapshot: Snapshot) -> Path:
    return _resolve_baked_path(entry, snapshot.path)


_PRESET_MATERIALS = {
    "Grass": ("ground", (0.78, 0.86, 0.72, 1.0), 1.0, 0.0, 0.75, 0.24),
    "Worn earth": ("ground", (0.60, 0.48, 0.31, 1.0), 1.0, 0.0, 0.72, 0.24),
    "Soil": ("ground", (0.43, 0.30, 0.18, 1.0), 1.0, 0.0, 0.72, 0.24),
    "Sand": ("ground", (0.86, 0.72, 0.47, 1.0), 0.96, 0.0, 0.48, 0.20),
    "Desert": ("desert", (0.90, 0.82, 0.68, 1.0), 1.0, 0.0, 0.50, 0.20),
    "Timber": ("timber", (0.65, 0.64, 0.59, 1.0), 0.86, 0.0, 0.8, 0.5),
    "Stone": ("stone", (0.48, 0.56, 0.56, 1.0), 1.0, 0.0, 0.72, 0.8),
    "Thatch": ("thatch", (1.0, 0.94, 0.76, 1.0), 0.92, 0.0, 0.7, 0.56),
    "Textile": ("textile", (0.58, 0.45, 0.25, 1.0), 0.86, 0.0, 0.65, 2.0),
    "Canvas": ("canvas", (0.78, 0.77, 0.65, 1.0), 0.88, 0.0, 0.65, 1.2),
    "Metal": ("metal", (1.0, 1.0, 1.0, 1.0), 0.44, 1.0, 0.75, 2.0),
    "Leather": ("leather", (0.28, 0.25, 0.19, 1.0), 0.70, 0.0, 0.7, 1.0),
    "Hide": ("hide", (0.92, 0.88, 0.78, 1.0), 0.86, 0.0, 0.6, 1.1),
    "Bone": ("bone", (0.90, 0.86, 0.72, 1.0), 0.52, 0.0, 0.65, 1.67),
    "Crystal": ("crystal", (0.72, 0.56, 0.86, 1.0), 0.18, 0.0, 0.8, 0.9),
    "Cavern": ("cavern", (0.66, 0.62, 0.56, 1.0), 0.93, 0.0, 0.72, 0.23),
    "Slate": (None, (0.095, 0.17, 0.20, 1.0), 0.55, 0.0, 1.0, 0.8),
}


def gltf_base_color(color: Iterable[float]) -> tuple[float, float, float, float]:
    """Convert a Godot/editor sRGB colour to glTF's linear baseColorFactor."""
    value = tuple(float(component) for component in color)
    if len(value) != 4:
        raise AuthoringError("an authored base colour must contain RGBA")
    def linear(component: float) -> float:
        return component / 12.92 if component <= 0.04045 else ((component + 0.055) / 1.055) ** 2.4
    return linear(value[0]), linear(value[1]), linear(value[2]), value[3]


def _embedded_texture(document: dict[str, Any], body: bytearray, path: Path,
                      memo: dict[Path, int]) -> int:
    if path in memo:
        return memo[path]
    suffix = path.suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg"):
        raise AuthoringError(f"{path}: authored PBR textures must be PNG or JPEG for GLB export")
    while len(body) % 4:
        body.append(0)
    data = path.read_bytes()
    view = len(document.setdefault("bufferViews", []))
    document["bufferViews"].append({"buffer": 0, "byteOffset": len(body), "byteLength": len(data)})
    body.extend(data)
    image = len(document.setdefault("images", []))
    document["images"].append({"name": path.stem, "bufferView": view,
                                "mimeType": "image/png" if suffix == ".png" else "image/jpeg"})
    samplers = document.setdefault("samplers", [])
    if not samplers:
        samplers.append({"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497})
    texture = len(document.setdefault("textures", []))
    document["textures"].append({"source": image, "sampler": 0})
    memo[path] = texture
    return texture


def _material_record(document: dict[str, Any], body: bytearray, surface: dict[str, Any],
                     textures: dict[Path, int]) -> int:
    preset = surface["preset"]
    rotation = math.radians(float(surface.get("rotationDegrees", 0.0)))
    pbr_source=surface.get("pbr") if preset=="Custom" else surface.get("pbrOverrides")
    if pbr_source is not None:
        pbr = _object(pbr_source, "authored surface PBR")
        color = tuple(_vector(pbr.get("albedoColor"), 4, "custom surface.pbr.albedoColor"))
        roughness = _number(pbr.get("roughness"), "custom surface.pbr.roughness")
        metallic = _number(pbr.get("metallic"), "custom surface.pbr.metallic")
        normal_scale = _number(pbr.get("normalScale"), "custom surface.pbr.normalScale")
        uv = _vector(pbr.get("uvScale"), 3, "custom surface.pbr.uvScale")
        offset = _vector(pbr.get("uvOffset"), 3, "custom surface.pbr.uvOffset")
        maps = {"albedo": pbr.get("albedoTexture"), "normal": pbr.get("normalTexture"),
                "orm": pbr.get("ormTexture")}
    else:
        if preset not in _PRESET_MATERIALS:
            raise AuthoringError(f"unsupported authored surface preset {preset!r}")
        family, color, roughness, metallic, normal_scale, density = _PRESET_MATERIALS[preset]
        uv = (density, density, density)
        offset = (0.0, 0.0, 0.0)
        texture_root = CLIENT / "godot-client/src/dev/map_authoring_pilot/style/textures"
        detail_family="ground" if preset=="Desert" else family
        maps = ({"albedo": texture_root / f"{family}-basecolor.png",
                 "normal": texture_root / f"{detail_family}-normal.png",
                 "orm": texture_root / f"{detail_family}-orm.png"} if family else {})
    # Godot's oriented shader evaluates R * (UV * scale + offset). KHR applies
    # offset + R * (UV * scale), so rotate the stored offset as well.
    rotated_offset = (math.cos(rotation)*offset[0]-math.sin(rotation)*offset[1],
                      math.sin(rotation)*offset[0]+math.cos(rotation)*offset[1])
    transform = {"offset": [float(rotated_offset[0]), float(rotated_offset[1])], "rotation": rotation,
                 "scale": [float(uv[0]), float(uv[1])]}
    def texture_info(value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        path = Path(value) if isinstance(value, Path) else _source_path(value, "custom surface texture")
        info = {"index": _embedded_texture(document, body, path, textures)}
        if rotation or not np.allclose(uv[:2], (1.0, 1.0)) or not np.allclose(offset[:2], (0.0, 0.0)):
            info["extensions"] = {"KHR_texture_transform": transform}
            extensions = document.setdefault("extensionsUsed", [])
            if "KHR_texture_transform" not in extensions:
                extensions.append("KHR_texture_transform")
        return info
    albedo, normal, orm = (texture_info(maps.get(name)) for name in ("albedo", "normal", "orm"))
    record = {"name": f"Authored_{preset}_{len(document.setdefault('materials', [])):04d}",
              "pbrMetallicRoughness": {"baseColorFactor": list(gltf_base_color(color)),
                                       "roughnessFactor": float(roughness),
                                       "metallicFactor": float(metallic)},
              "doubleSided": True}
    if color[3]<1.:record["alphaMode"]="BLEND"
    if albedo is not None:record["pbrMetallicRoughness"]["baseColorTexture"] = albedo
    if orm is not None:
        record["pbrMetallicRoughness"]["metallicRoughnessTexture"] = orm
        record["occlusionTexture"] = dict(orm)
    if normal is not None:
        record["normalTexture"] = dict(normal, scale=float(normal_scale))
    document["materials"].append(record)
    return len(document["materials"]) - 1


def _apply_material_overrides(document: dict[str, Any], body: bytes, root: int | list[int],
                              overrides: list[dict[str, Any]]) -> tuple[dict[str, Any], bytes]:
    if not overrides:
        return document, body
    import copy
    document = copy.deepcopy(document); binary = bytearray(body);texture_memo={}
    def resolve(path: str) -> int:
        parts = [part for part in path.replace("\\", "/").split("/") if part and part != "."]
        current = root
        # Match Godot get_node: paths are relative to the selected Content root.
        for part in parts:
            matches = [child for child in document["nodes"][current].get("children", [])
                       if document["nodes"][child].get("name") == part]
            if len(matches) != 1:
                raise AuthoringError(f"material override path {path!r} does not identify one mesh node")
            current = matches[0]
        return current
    # Indexed bindings belong to the already hash-verified bakedSource document.
    roots = [root] if isinstance(root, int) else root
    reachable = set()
    pending = list(roots)
    while pending:
        node = pending.pop()
        if node not in reachable:
            reachable.add(node)
            pending.extend(document["nodes"][node].get("children", []))
    cloned_meshes={}
    for override in overrides:
        if "bakedMeshNodeIndex" in override:
            node = override["bakedMeshNodeIndex"]
            if type(node) is not int or node < 0 or node not in reachable:
                raise AuthoringError("material override bakedMeshNodeIndex is outside the selected source subtree")
        elif not isinstance(root, int):
            raise AuthoringError("multi-root material overrides require bakedMeshNodeIndex")
        else:
            node = resolve(override["meshNodePath"])
        if "mesh" not in document["nodes"][node]:
            raise AuthoringError(f"material override target {override['meshNodePath']!r} has no mesh")
        if node not in cloned_meshes:
            old_mesh=document["nodes"][node]["mesh"]
            mesh=copy.deepcopy(document["meshes"][old_mesh])
            document.setdefault("meshes",[]).append(mesh)
            cloned_meshes[node]=len(document["meshes"])-1
            document["nodes"][node]["mesh"]=cloned_meshes[node]
        primitive = int(override["surfaceIndex"])
        parts = document["meshes"][document["nodes"][node]["mesh"]]["primitives"]
        if primitive >= len(parts):
            raise AuthoringError(
                f"material override target {override['meshNodePath']!r} has no surface {primitive}")
        parts[primitive]["material"] = _material_record(document, binary, override["surface"], texture_memo)
    if document.get("buffers"):
        document["buffers"] = [dict(document["buffers"][0], byteLength=len(binary))]
    return document, bytes(binary)


def _embed_external_images(document: dict[str, Any], body: bytes, source_path: Path,
                           snapshot: Snapshot) -> tuple[dict[str, Any], bytes]:
    """Embed certified relative GLB images before lossless transplantation."""
    external=[image for image in document.get("images",[]) if "uri" in image]
    if not external:return document,body
    import copy
    document=copy.deepcopy(document);binary=bytearray(body)
    for image in document.get("images",[]):
        uri=image.get("uri")
        if uri is None:continue
        if ":" in uri or uri.startswith(("/","\\")):
            raise AuthoringError(f"{source_path}: external image URI must be a relative file path")
        path=(source_path.parent/uri).resolve()
        try:path.relative_to(CLIENT.resolve())
        except ValueError as error:
            raise AuthoringError(f"{source_path}: external image escapes the client checkout") from error
        key=path.relative_to(CLIENT).as_posix()
        if snapshot.source_sha256.get(key)!=sha256(path):
            raise AuthoringError(f"{source_path}: external image {key} is not hash-bound by the snapshot")
        while len(binary)%4:binary.append(0)
        data=path.read_bytes();view=len(document.setdefault("bufferViews",[]))
        document["bufferViews"].append({"buffer":0,"byteOffset":len(binary),"byteLength":len(data)})
        binary.extend(data);image.pop("uri",None);image["bufferView"]=view
        image.setdefault("mimeType","image/png" if path.suffix.lower()==".png" else "image/jpeg")
    if document.get("buffers"):
        document["buffers"]=[dict(document["buffers"][0],byteLength=len(binary))]
    return document,bytes(binary)


def transformed_authored_crossings(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve saved asset-local crossing endpoints with the asset matrix.

    The visual and ``Walk_`` subtree is exported under this same matrix.  By
    keeping endpoints local until this boundary, an editor move/turn/scale can
    never leave crossing support metadata at the old world-space position.
    """
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in objects:
        crossing = entry.get("metadata", {}).get("authoredCrossing")
        if crossing is None:
            continue
        identity = crossing["id"]
        if identity in seen:
            raise AuthoringError(f"duplicate authored crossing id {identity!r}")
        seen.add(identity)
        matrix = np.asarray(entry["matrix"], dtype=float).reshape(4, 4, order="F")
        endpoints = []
        for point in crossing["localEndpoints"]:
            transformed = matrix @ np.asarray([*point, 1.0], dtype=float)
            if not np.isfinite(transformed).all() or abs(float(transformed[3])) < 1e-12:
                raise AuthoringError(f"{entry['id']}: invalid authored crossing transform")
            endpoints.append((transformed[:3] / transformed[3]).tolist())
        result.append({
            "id": identity,
            "endpoints": endpoints,
            "assetId": entry["id"],
            "node": entry["nodeName"],
            "walkNode": crossing["walkNode"],
            "authority": "saved-asset",
        })
    result.sort(key=lambda value: value["id"])
    return result


def build_retained_library(snapshot: Snapshot, root: Path) -> dict[str, str]:
    """Build Content's retained-source bridge from declared GLB subtrees.

    This replaces Sunmane's retired Python regional recipe.  It never reads a
    composed ``world.glb``: only the hash-bound source assets named by scene
    controls are transplanted under their saved matrices.
    """
    import scene_io as S

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    exporter = S.Exporter(root / "library.glb")
    loaded: dict[Path, tuple[dict[str, Any], bytes]] = {}
    retained_documents: list[tuple[dict[str, Any], bytes]] = []
    placements = []
    for entry in snapshot.document["objects"]:
        source_path = baked_asset_path(entry, snapshot)
        if source_path not in loaded:
            loaded[source_path] = _embed_external_images(*S.GR.load(source_path),source_path,snapshot)
        document, body = loaded[source_path]
        source_node = entry["bakedSource"]["sourceNode"]
        if source_node == ".":
            matches = list(document["scenes"][document.get("scene", 0)].get("nodes", []))
        else:
            matches = [index for index, node in enumerate(document.get("nodes", []))
                       if node.get("name") == source_node]
        if not matches or (source_node != "." and len(matches) != 1):
            raise AuthoringError(
                f"{entry['id']}: baked sourceNode {source_node!r} resolves to {len(matches)} roots in {source_path}")
        root_index = matches[0]
        object_document, object_body = _apply_material_overrides(
            document, body, root_index if len(matches) == 1 else matches,
            entry.get("materialOverrides", []))
        if object_document is not document:
            # Exporter memoizes by object identity.  Keep private override
            # documents alive until write so CPython cannot reuse their ids.
            retained_documents.append((object_document, object_body))
        if len(matches) == 1:
            matrices = {root_index: entry["matrix"]}
            root_names = {root_index: entry["nodeName"]}
        else:
            # A saved AssetControl instances the complete imported scene under
            # its own transform.  Preserve every declared scene root (including
            # companion visual/walk subtrees) under that same transform instead
            # of dropping all but the first root or overwriting their relative
            # transforms.
            matrices = {index: entry["matrix"] for index in matches}
            root_names = {matches[0]: entry["nodeName"]}
            for ordinal, index in enumerate(matches[1:], start=1):
                original = object_document["nodes"][index].get("name") or f"root-{ordinal}"
                root_names[index] = f"{entry['nodeName']}__companion_{ordinal}_{original}"
        exporter.add(object_document, object_body, matches, matrices=matrices,
                     root_names=root_names)
        metadata = dict(entry.get("metadata", {}))
        forbidden = {"node", "groupedNodes", "position", "collides", "walk_surface"} & metadata.keys()
        if forbidden:
            raise AuthoringError(f"{entry['id']}: object metadata cannot replace {sorted(forbidden)}")
        matrix = entry["matrix"]
        metadata.update(node=entry["nodeName"], groupedNodes=list(root_names.values()),
                        position=[matrix[12], matrix[13], matrix[14]],
                        kind=metadata.get("kind", "prop"),
                        collides=entry["collisionRole"] == "solid",
                        walk_surface=entry["collisionRole"] == "walk_surface",
                        authoringId=entry["id"])
        placements.append(metadata)
    exporter.write()
    metadata = {
        "region": snapshot.document["regionId"],
        "continentAuthoring": {"schema": SCHEMA, "snapshotSha256": snapshot.digest,
                               "coordinateSpace": "territory-local"},
        "placements": placements,
        "crossings": transformed_authored_crossings(snapshot.document["objects"]),
    }
    library_json = root / "library.json"
    library_json.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8", newline="\n")
    terrain = snapshot.document["terrain"]
    x = float(terrain["origin"][0]) + np.arange(snapshot.terrain_width) * float(terrain["cellMetres"])
    z = float(terrain["origin"][1]) + np.arange(snapshot.terrain_height) * float(terrain["cellMetres"])
    foundation = root / "foundation-samples.npz"
    np.savez_compressed(foundation, x=x, z=z, height=snapshot.effective_heights())
    return {name: sha256(root / name) for name in
            ("library.glb", "library.json", "foundation-samples.npz")}


def ownership_polygon_sha256(world: Any, region: str = SUNMANE) -> str:
    points = world.polygons[region]
    encoded = json.dumps(points, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_ownership(world: Any, snapshot: Snapshot) -> None:
    region = snapshot.document["regionId"]
    selected = getattr(world, "ownership_contract", None)
    binding = snapshot.document.get("ownershipSource")
    if selected is not None:
        if not isinstance(binding, dict) or binding.get("sha256") != selected.sha256 or binding.get("revision") != selected.revision or binding.get("regionId") != region:
            raise AuthoringError(f"{region}: selected ownership source changed; rebake before composition")
    elif binding is not None:
        raise AuthoringError(f"{region}: snapshot selects ownership but composed world does not")
    expected = snapshot.document["seams"]["ownershipPolygonSha256"]
    actual = ownership_polygon_sha256(world, region)
    if actual != expected:
        raise AuthoringError(
            f"{region}: ownership polygon changed after scene export; rebake before composition")


def verify_seam_anchors(world: Any, snapshot: Snapshot) -> None:
    """Keep the shared connection frame fixed to the saved scene seam controls."""
    region = snapshot.document["regionId"]
    authored={entry["id"]:entry for entry in snapshot.document["seams"]["anchors"]}
    # Ferry neighbours have no road seam station or anchor. Their landing frames
    # are checked by ferry fitting; only walk links belong to saved seam controls.
    neighbours=[link for link in world.connections if region in link.get("regions",())]
    unknown={link.get("type") for link in neighbours if link.get("type", "walk") not in ("walk", "ferry")}
    if unknown:
        raise AuthoringError(f"{region}: unknown seam connection types {sorted(map(str, unknown))}")
    actual={link["id"]:link for link in neighbours if link.get("type", "walk") == "walk"}
    if set(actual)!=set(authored):
        raise AuthoringError(
            f"{region}: seam links differ from the saved scene: "
            f"expected {sorted(authored)}, got {sorted(actual)}")
    for identity,entry in authored.items():
        expected=snapshot.continent_point(entry["anchor"])
        value=np.asarray(actual[identity]["anchor"],float)
        if value.shape == (2,):
            actual_xz=value
        elif value.shape == (3,):
            actual_xz=value[[0,2]]
        else:
            raise AuthoringError(f"{identity}: shared seam anchor must contain XZ or XYZ")
        if not np.allclose(actual_xz,expected[[0,2]],rtol=0,atol=1e-6):
            raise AuthoringError(f"{identity}: continent seam anchor moved after scene export")


def _contract_for(region_id: str, contract: RegionContract | None) -> RegionContract:
    if contract is not None:
        if contract.id != region_id:
            raise AuthoringError(
                f"snapshot.regionId {region_id!r} disagrees with contract {contract.id!r}")
        return contract
    matches = [value for value in authored_contracts() if value.id == region_id]
    if len(matches) != 1:
        raise AuthoringError(
            f"{region_id}: expected exactly one authored region contract, found {len(matches)}")
    return matches[0]


def load_snapshots(*, production: bool = True) -> tuple[Snapshot, ...]:
    """Load every complete authored territory in deterministic catalog order."""
    contracts = authored_contracts()
    snapshots = tuple(load_snapshot(contract.snapshot_path, production=production,
                                    contract=contract)
                      for contract in contracts)
    regions = [snapshot.document["regionId"] for snapshot in snapshots]
    if len(regions) != len(set(regions)):
        raise AuthoringError(f"authored territory catalog contains duplicate regions: {regions}")
    return snapshots


def validate_snapshot_ownership(document, plan_path=None):
    import ownership_contract as ownership
    from authoring_catalog import migration_sources, CatalogError
    try:
        expected = ownership.editor_binding(document["regionId"], plan_path)
        ownership.validate_authoring_frame(expected, document)
    except ownership.OwnershipContractError as error:
        raise AuthoringError(str(error)) from error
    actual = document.get("ownershipSource")
    if not expected and actual is not None:
        raise AuthoringError("snapshot ownership selection is stale; rebake against the current plan")
    dependencies = document.get("sources", {}).get("repositoryDependencies")
    client = Path(plan_path).parents[4] if plan_path is not None else None
    try:
        required = migration_sources(document, client=client)
    except (CatalogError, ValueError, OSError) as error:
        raise AuthoringError(str(error)) from error
    if expected:
        required += expected["repositoryDependencies"]
    required.sort(key=lambda row: row["path"])
    if (dependencies or []) != required:
        raise AuthoringError("snapshot repository dependencies changed; rebake before composition")
    if not expected:
        if actual is not None:
            raise AuthoringError("snapshot ownership selection is stale; rebake against the current plan")
        return
    if actual != expected["binding"]:
        raise AuthoringError("snapshot ownership source/dependencies changed; rebake before composition")
    if document.get("seams", {}).get("ownershipPolygonSha256") != expected["ownershipPolygonSha256"]:
        raise AuthoringError("snapshot selected polygon hash differs; rebake before composition")


def load_snapshot(path: Path | str = SUNMANE_SNAPSHOT, *, production: bool = True,
                  contract: RegionContract | None = None,
                  ownership_plan_path: Path | None = None) -> Snapshot:
    path = Path(path).resolve()
    if not path.is_file():
        raise AuthoringError(f"{path}: required authoring snapshot is missing")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AuthoringError(f"{path}: invalid UTF-8 JSON: {error}") from error
    document = _object(document, "snapshot")
    if document.get("schema") != SCHEMA:
        raise AuthoringError(f"snapshot.schema must be {SCHEMA!r}")
    region_id = _string(document.get("regionId"), "snapshot.regionId")
    validate_snapshot_ownership(document, ownership_plan_path)
    active_contract = _contract_for(region_id, contract) if production else contract
    spec_source = validate_snapshot_storage_source(document, active_contract,
        client=Path(ownership_plan_path).parents[4] if ownership_plan_path is not None else CLIENT)
    if active_contract is not None and document.get("terrain", {}).get("migration") != active_contract.terrain_migration:
        raise AuthoringError("snapshot terrain migration provenance differs from its region spec; rebake")
    if active_contract is not None and active_contract.id != region_id:
        raise AuthoringError(
            f"snapshot.regionId {region_id!r} disagrees with contract {active_contract.id!r}")
    if document.get("coordinateSpace") != "territory-local":
        raise AuthoringError("snapshot.coordinateSpace must be territory-local")
    if document.get("axes") != {"x": "east", "y": "up", "z": "south"}:
        raise AuthoringError("snapshot.axes must declare x east, y up and z south")
    translation = _vector(document.get("continentTranslation"), 3, "continentTranslation")
    if active_contract is not None and translation != active_contract.continent_translation:
        raise AuthoringError(
            f"{region_id}: continentTranslation must be "
            f"{list(active_contract.continent_translation)}")
    server = _object(document.get("server"), "server")
    if _number(server.get("metresPerTile"), "server.metresPerTile") != 1.0:
        raise AuthoringError("server.metresPerTile must be one")
    origin = _integer_vector(server.get("origin"), 2, "server.origin")
    cells = _integer_vector(server.get("cells"), 2, "server.cells")
    collision_origin = _vector(server.get("collisionOriginMetres"), 2,
                               "server.collisionOriginMetres")
    if active_contract is not None:
        if origin != active_contract.server_origin:
            raise AuthoringError(
                f"{region_id}: server.origin must be {list(active_contract.server_origin)}")
        if cells != active_contract.server_cells:
            raise AuthoringError(
                f"{region_id}: server.cells must be {list(active_contract.server_cells)}")
        if collision_origin != active_contract.collision_origin_metres:
            raise AuthoringError(
                f"{region_id}: server.collisionOriginMetres must be "
                f"{list(active_contract.collision_origin_metres)}")
    authority = _object(document.get("authority"), "authority")
    required_authority = ("terrain", "water", "paths", "objects", "gameplay")
    if any(authority.get(section) is not True for section in required_authority):
        raise AuthoringError(
            f"{region_id}: authority must explicitly cover terrain, water, paths, objects and gameplay")
    _validate_replacements(document, production, active_contract)
    source_sha256 = _validate_sources(document, path, production)
    source_sha256.update(spec_source)
    for dependency in document.get("sources", {}).get("repositoryDependencies", []):
        source_sha256[dependency["path"]] = dependency["sha256"]
    base, resolved, width, height = _validate_terrain(
        document, path, production, source_sha256, active_contract)
    _validate_ground_regions(document, source_sha256)
    _validate_paths(document, source_sha256)
    _validate_water_regions(document)
    _validate_bridges(document, source_sha256)
    _validate_objects(document, source_sha256, path, production)
    _validate_gameplay(document, production, active_contract)
    _validate_seams(document)
    for relative, expected_sha in spec_source.items():
        import ownership_contract
        root = Path(ownership_plan_path).parents[4] if ownership_plan_path is not None else CLIENT
        if sha256(ownership_contract.contained_path(root, relative)) != expected_sha:
            raise AuthoringError("authoring spec changed during snapshot validation; rebake")
    return Snapshot(path, document, source_sha256, base, resolved, width, height,
                    active_contract)


def validate_snapshot_storage_source(document, contract=None, *, client=None):
    """Bind versioned storage to exact saved source bytes, without rebasing tiles.

    Old zero-min snapshots may omit this additive binding. New exports bind a
    registered spec even in legacy mode; explicit storage always requires one.
    """
    import ownership_contract as ownership
    try:
        bounds = authoring_storage(document.get("server"))
        if contract is not None:
            if (bounds.width, bounds.height) != contract.server_cells or (
                    bounds.min_x, bounds.min_y) != contract.server_tile_min:
                raise ValueError("snapshot storage differs from its region spec; rebake")
            if contract.server_frame is not None and frame_values(document["server"]) != contract.server_frame:
                raise ValueError("snapshot immutable frame differs from its region spec; rebake")
        record = document.get("sources", {}).get("authoringSpec")
        if record is None:
            if "serverStorageVersion" in document["server"] or (contract is not None and contract.server_storage_version is not None):
                raise ValueError("versioned snapshot storage requires sources.authoringSpec; rebake")
            return {}
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            raise ValueError("sources.authoringSpec requires exactly path and sha256")
        relative = f"godot-client/world_authoring/regions/{document['regionId']}/region-authoring-spec.json"
        if record["path"] != relative:
            raise ValueError("snapshot authoringSpec must name its registered regional source")
        path = ownership.contained_path(Path(client or CLIENT), relative)
        payload = path.read_bytes()
        ownership._sha(record["sha256"], "sources.authoringSpec.sha256")
        if hashlib.sha256(payload).hexdigest() != record["sha256"] or (
                contract is not None and contract.spec_sha256 is not None and contract.spec_sha256 != record["sha256"]):
            raise ValueError("snapshot authoring spec hash changed; rebake")
        spec = json.loads(payload)
        if (spec.get("schema") != "eloria-region-authoring-spec-v1" or
                spec.get("regionId") != document["regionId"] or
                authoring_storage(spec.get("server")) != bounds or
                frame_values(spec["server"]) != frame_values(document["server"]) or
                spec.get("continentTranslation") != document.get("continentTranslation")):
            raise ValueError("snapshot storage/frame differs from bound authoring spec; rebake")
        return {relative: record["sha256"]}
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise AuthoringError(str(error)) from error
