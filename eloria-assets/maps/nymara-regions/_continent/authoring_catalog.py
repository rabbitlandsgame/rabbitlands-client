"""Strict, portable registry for authored continent territories.

The catalog is shared by the Godot workspace and the Python build.  Entries
with no scene/spec pair remain procedural.  Authored entries must provide the
pair atomically so the build cannot mistake a half-migrated territory for an
authoritative source.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import hashlib
import math
from pathlib import Path
import re
import ownership_contract
from storage_bounds import authoring_storage, frame_values
from typing import Any


HERE = Path(__file__).resolve().parent
CLIENT = HERE.parents[3]
CATALOG_PATH = CLIENT / "godot-client/world_authoring/territories.json"
CATALOG_SCHEMA = "eloria-map-authoring-territories-v1"
SPEC_SCHEMA = "eloria-region-authoring-spec-v1"


class CatalogError(ValueError):
    """A territory catalog/spec cannot safely drive an authoring build."""


@dataclass(frozen=True)
class RegionContract:
    id: str
    label: str
    adapter: str
    scene_path: Path
    manifest_path: Path
    spec_path: Path
    snapshot_path: Path
    continent_translation: tuple[float, float, float]
    server_origin: tuple[int, int]
    server_cells: tuple[int, int]
    collision_origin_metres: tuple[float, float]
    terrain_origin: tuple[float, float]
    terrain_vertices: tuple[int, int]
    terrain_cell_metres: float
    owned_route_ids: tuple[str, ...]
    required_route_ids: tuple[str, ...]
    owned_plan_feature_ids: tuple[str, ...]
    runtime_binding_count: int
    runtime_point_count: int
    existing_marker_binding_count: int
    owned_ferry_connection_ids: tuple[str, ...] = ()
    ownership_binding: dict | None = None
    terrain_migration: dict | None = None
    server_tile_min: tuple[int, int] = (0, 0)
    server_storage_version: int | None = None
    spec_sha256: str | None = None
    server_frame: tuple | None = None


@dataclass(frozen=True)
class TerritoryEntry:
    id: str
    label: str
    manifest_path: Path
    scene_path: Path | None
    authoring_spec_path: Path | None

    @property
    def authored(self) -> bool:
        return self.scene_path is not None


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogError(f"{where} must be an object")
    return value


def _string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{where} must be a non-empty string")
    return value


def _array(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise CatalogError(f"{where} must be an array")
    return value


def _repo_path(value: Any, where: str, *, must_exist: bool = True) -> Path:
    text = _string(value, where).replace("\\", "/")
    if text.startswith("res://../"):
        relative = text[len("res://../"):]
    elif text.startswith("res://"):
        relative = "godot-client/" + text[len("res://"):]
    else:
        relative = text
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise CatalogError(f"{where} must be a portable path inside the client checkout")
    resolved = (CLIENT / candidate).resolve()
    try:
        resolved.relative_to(CLIENT.resolve())
    except ValueError as error:
        raise CatalogError(f"{where} escapes the client checkout") from error
    if must_exist and not resolved.is_file():
        raise CatalogError(f"{where} does not exist: {resolved}")
    return resolved


def _vector(value: Any, size: int, where: str) -> tuple[float, ...]:
    values = _array(value, where)
    if len(values) != size:
        raise CatalogError(f"{where} must contain {size} numbers")
    result = []
    for index, part in enumerate(values):
        if isinstance(part, bool) or not isinstance(part, (int, float)) or not math.isfinite(part):
            raise CatalogError(f"{where}[{index}] must be a finite number")
        result.append(float(part))
    return tuple(result)


def _integer_vector(value: Any, size: int, where: str) -> tuple[int, ...]:
    values = _array(value, where)
    if len(values) != size or any(isinstance(part, bool) or not isinstance(part, int)
                                  for part in values):
        raise CatalogError(f"{where} must contain {size} integers")
    return tuple(values)


def _nonnegative_integer(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CatalogError(f"{where} must be a non-negative integer")
    return value


def _sorted_ids(value: Any, where: str) -> tuple[str, ...]:
    result = tuple(_string(item, f"{where}[{index}]")
                   for index, item in enumerate(_array(value, where)))
    if result != tuple(sorted(set(result))):
        raise CatalogError(f"{where} must contain sorted unique ids")
    return result


def load_region_spec(path: Path, *, expected_id: str | None = None,
                     scene_path: Path | None = None,
                     manifest_path: Path | None = None,
                     require_scene: bool = True,
                     ownership_plan_path: Path | None = None) -> RegionContract:
    spec_bytes = path.read_bytes()
    document = _object(json.loads(spec_bytes), "region spec")
    if document.get("schema") != SPEC_SCHEMA:
        raise CatalogError(f"{path}: schema must be {SPEC_SCHEMA}")
    region_id = _string(document.get("regionId"), "regionId")
    if expected_id is not None and region_id != expected_id:
        raise CatalogError(f"{path}: regionId {region_id!r} does not match {expected_id!r}")
    label = _string(document.get("label"), "label")
    adapter = _string(document.get("adapter"), "adapter")
    paths = _object(document.get("paths"), "paths")
    declared_scene = _repo_path(paths.get("scene"), "paths.scene",
                                must_exist=require_scene)
    declared_manifest = _repo_path(paths.get("manifest"), "paths.manifest")
    if scene_path is not None and declared_scene != scene_path.resolve():
        raise CatalogError(f"{path}: paths.scene disagrees with the catalog")
    if manifest_path is not None and declared_manifest != manifest_path.resolve():
        raise CatalogError(f"{path}: paths.manifest disagrees with the catalog")
    snapshot = _repo_path(paths.get("snapshot"), "paths.snapshot", must_exist=False)
    expected_snapshot = declared_manifest.parent / "authoring/continent-authoring.json"
    if snapshot != expected_snapshot.resolve():
        raise CatalogError(f"{path}: paths.snapshot must be the manifest sibling authoring snapshot")
    server = _object(document.get("server"), "server")
    terrain = _object(document.get("terrain"), "terrain")
    authority = _object(document.get("authority"), "authority")
    gameplay = _object(document.get("gameplay"), "gameplay")
    vertices = _integer_vector(terrain.get("vertices"), 2, "terrain.vertices")
    cell_metres = _vector([terrain.get("cellMetres")], 1, "terrain.cellMetres")[0]
    if cell_metres <= 0 or min(vertices) < 2:
        raise CatalogError("terrain cellMetres must be positive and vertices at least two")
    migration_sources(document)
    try:
        ownership = ownership_contract.editor_binding(region_id, ownership_plan_path)
        ownership_contract.validate_authoring_frame(ownership, document)
        storage = authoring_storage(server)
    except ownership_contract.OwnershipContractError as error:
        raise CatalogError(f"{path}: {error}") from error
    if path.read_bytes() != spec_bytes:
        raise CatalogError("region authoring spec changed during validation; retry")
    return RegionContract(
        id=region_id, label=label, adapter=adapter,
        scene_path=declared_scene, manifest_path=declared_manifest,
        spec_path=path.resolve(), snapshot_path=snapshot,
        continent_translation=_vector(document.get("continentTranslation"), 3,
                                      "continentTranslation"),
        server_origin=_integer_vector(server.get("origin"), 2, "server.origin"),
        server_cells=_integer_vector(server.get("cells"), 2, "server.cells"),
        collision_origin_metres=_vector(server.get("collisionOriginMetres"), 2,
                                        "server.collisionOriginMetres"),
        terrain_origin=_vector(terrain.get("origin"), 2, "terrain.origin"),
        terrain_vertices=vertices, terrain_cell_metres=cell_metres,
        owned_route_ids=_sorted_ids(authority.get("ownedRouteIds"),
                                    "authority.ownedRouteIds"),
        required_route_ids=_sorted_ids(authority.get("requiredRouteIds"),
                                       "authority.requiredRouteIds"),
        owned_plan_feature_ids=_sorted_ids(authority.get("ownedPlanFeatureIds"),
                                           "authority.ownedPlanFeatureIds"),
        runtime_binding_count=_nonnegative_integer(
            gameplay.get("runtimeBindingCount"), "gameplay.runtimeBindingCount"),
        runtime_point_count=_nonnegative_integer(
            gameplay.get("runtimePointCount"), "gameplay.runtimePointCount"),
        existing_marker_binding_count=_nonnegative_integer(
            gameplay.get("existingMarkerBindingCount"),
            "gameplay.existingMarkerBindingCount"),
        owned_ferry_connection_ids=_sorted_ids(
            authority.get("ownedFerryConnectionIds", []),
            "authority.ownedFerryConnectionIds"),
        ownership_binding=ownership.get("binding"),
        terrain_migration=terrain.get("migration"),
        server_tile_min=(storage.min_x, storage.min_y),
        server_storage_version=server.get("serverStorageVersion"),
        spec_sha256=hashlib.sha256(spec_bytes).hexdigest(),
        server_frame=frame_values(server),
    )


def migration_sources(document, *, client=None):
    """Hash-bound shared-field provenance; source grids remain independently editable."""
    client = Path(client or CLIENT)
    terrain = document.get("terrain", {})
    migration = terrain.get("migration")
    if migration is None:
        return []
    migration = _object(migration, "terrain.migration")
    if migration.get("revision") != "global-lattice-envelope-v1":
        raise CatalogError("unsupported terrain migration revision")
    # Godot JSON preserves integer values as floats when copying parsed metadata.
    minimum = _vector(migration.get("globalVertexMin"), 2, "terrain.migration.globalVertexMin")
    if any(value != int(value) for value in minimum):
        raise CatalogError("terrain.migration.globalVertexMin must contain integer values")
    try:
        ownership_contract._sha(migration.get("previousGridSha256"), "terrain.migration.previousGridSha256")
        manifest_path = ownership_contract.contained_path(client, migration.get("sharedFieldPath"))
    except ownership_contract.OwnershipContractError as error:
        raise CatalogError(str(error)) from error
    records = []
    def verify(path, expected):
        try:
            ownership_contract._sha(expected, "terrain migration source hash")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise CatalogError(f"terrain migration source hash changed: {path}")
        except (OSError, ownership_contract.OwnershipContractError) as error:
            raise CatalogError(f"terrain migration source is missing/invalid: {error}") from error
        records.append({"path": path.relative_to(client).as_posix(), "sha256": expected})
    verify(manifest_path, migration.get("sharedFieldSha256"))
    manifest = _object(json.loads(manifest_path.read_bytes()), "shared terrain field")
    lattice = _object(manifest.get("lattice"), "shared terrain lattice")
    if manifest.get("schema") != "eloria-terrain-shared-field-v1" or lattice.get("order") != "row-major-x-fast" or lattice.get("spacing") != 2:
        raise CatalogError("unsupported shared terrain field schema/lattice")
    lattice_origin = _vector(lattice.get("originMetres"), 2, "lattice.originMetres")
    vertices = _integer_vector(lattice.get("vertices"), 2, "lattice.vertices")
    if min(vertices) < 2:
        raise CatalogError("shared terrain field needs positive dimensions")
    translation = _vector(document.get("continentTranslation"), 3, "continentTranslation")
    origin = _vector(terrain.get("origin"), 2, "terrain.origin")
    if any(origin[i] + translation[(0, 2)[i]] != lattice_origin[i] + minimum[i] * 2 for i in (0, 1)):
        raise CatalogError("terrain migration globalVertexMin differs from the saved grid identity")
    for key, encoding in (("heights", "float32-little-endian"), ("colors", "rgba8")):
        record = _object(manifest.get(key), f"shared terrain {key}")
        if record.get("encoding") != encoding:
            raise CatalogError(f"shared terrain {key} encoding is unsupported")
        try:
            path = ownership_contract.contained_path(client, record.get("path"))
        except ownership_contract.OwnershipContractError as error:
            raise CatalogError(str(error)) from error
        verify(path, record.get("sha256"))
        if path.stat().st_size != vertices[0] * vertices[1] * 4:
            raise CatalogError(f"shared terrain {key} byte count differs from lattice")
    if len({r["path"] for r in records}) != len(records):
        raise CatalogError("shared terrain source paths must be distinct")
    return sorted(records, key=lambda row: row["path"])


def _scene_region_id(path: Path) -> str:
    match = re.search(r'^region_id\s*=\s*"([^"]+)"\s*$',
                      path.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise CatalogError(f"{path}: scene root does not declare region_id")
    return match.group(1)


def load_catalog(path: Path = CATALOG_PATH) -> tuple[TerritoryEntry, ...]:
    document = _object(json.loads(path.read_text(encoding="utf-8")), "territory catalog")
    if document.get("schema") != CATALOG_SCHEMA:
        raise CatalogError(f"{path}: schema must be {CATALOG_SCHEMA}")
    records = _array(document.get("entries"), "entries")
    entries: list[TerritoryEntry] = []
    for index, raw in enumerate(records):
        record = _object(raw, f"entries[{index}]")
        region_id = _string(record.get("id"), f"entries[{index}].id")
        label = _string(record.get("label"), f"entries[{index}].label")
        manifest = _repo_path(record.get("manifestPath"),
                              f"entries[{index}].manifestPath")
        scene_value = record.get("scenePath")
        spec_value = record.get("authoringSpecPath")
        if (scene_value is None) != (spec_value is None):
            raise CatalogError(
                f"entries[{index}] must provide scenePath and authoringSpecPath atomically")
        scene = spec = None
        if scene_value is not None:
            scene = _repo_path(scene_value, f"entries[{index}].scenePath")
            spec = _repo_path(spec_value, f"entries[{index}].authoringSpecPath")
            if _scene_region_id(scene) != region_id:
                raise CatalogError(f"{scene}: scene region_id does not match {region_id}")
            contract = load_region_spec(spec, expected_id=region_id,
                                        scene_path=scene, manifest_path=manifest)
            if contract.label != label:
                raise CatalogError(f"{spec}: label disagrees with the catalog")
        manifest_document = _object(json.loads(manifest.read_text(encoding="utf-8")),
                                    f"{manifest}")
        manifest_id = _object(manifest_document.get("asset"), "manifest.asset").get("id")
        if manifest_id != region_id:
            raise CatalogError(f"{manifest}: asset.id does not match {region_id}")
        entries.append(TerritoryEntry(region_id, label, manifest, scene, spec))
    labels = [entry.label for entry in entries]
    ids = [entry.id for entry in entries]
    if labels != sorted(labels, key=str.casefold):
        raise CatalogError("entries must be sorted by label")
    if len(ids) != len(set(ids)):
        raise CatalogError("entries contains duplicate ids")
    return tuple(entries)


def authored_contracts(path: Path = CATALOG_PATH) -> tuple[RegionContract, ...]:
    return tuple(load_region_spec(entry.authoring_spec_path, expected_id=entry.id,
                                  scene_path=entry.scene_path,
                                  manifest_path=entry.manifest_path)
                 for entry in load_catalog(path) if entry.authored)
