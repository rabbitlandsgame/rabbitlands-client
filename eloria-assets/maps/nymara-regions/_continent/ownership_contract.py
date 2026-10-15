"""Opt-in canonical ownership, independent of terrain sampling and map storage.

The plan selects a hash-pinned source file. Without that selection the existing
Voronoi partition remains authoritative. Polygon boundary ties use lexical IDs;
the plan's region order still controls indices in sampled ownership arrays.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import stat

import numpy as np

SOURCE_ROOT = Path(__file__).resolve().parent
SCHEMA = "eloria-continent-ownership-v1"
NYMARA_REVISION = "user-boundary-redesign-v4-marked-amberwood-amethyst"
NYMARA_CORRECTED_REVISION = NYMARA_REVISION + "-topology-correction-v1"
NYMARA_IDS = frozenset(("amberwood", "amethyst_barrens", "crownwater", "four_gates",
    "grey_moors", "manymouth_delta", "mirrorhold", "ssarathi_ruins", "sunmane_steppe",
    "verdant_stair", "westhaven", "whitehorn_range"))
# Only GEOS floating-point arithmetic noise is tolerated; no snapping, buffering,
# polygon repair, rasterization, or rounding may change the canonical vertices.
AREA_EPSILON = 1e-7


class OwnershipContractError(ValueError):
    pass


def _fail(message):
    raise OwnershipContractError(message)


def _object_pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            _fail(f"ownership contract: duplicate JSON key {name!r}")
        result[name] = value
    return result


def _vector(value, count, label, *, integer=False):
    if not isinstance(value, list) or len(value) != count or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or
            not math.isfinite(v) or (integer and not isinstance(v, int)) for v in value):
        _fail(f"{label}: expected {count} finite {'integer ' if integer else ''}coordinates")
    return value


def _sha(value, label):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        _fail(f"{label}: expected lowercase SHA-256")
    return value


@dataclass(frozen=True)
class OwnershipContract:
    revision: str
    bounds: tuple
    region_ids: tuple
    sha256: str
    _document: dict
    _geometries: dict

    def polygons(self):
        """Fresh canonical arrays, retaining input order, numbers and vertices."""
        return {r: copy.deepcopy(self._document["regions"][r]["ownershipPolygon"])
                for r in self.region_ids}

    def frame(self, region):
        return copy.deepcopy(self._document["regions"][region]["coordinateFrame"])

    def storage(self, region):
        return copy.deepcopy(self._document["regions"][region]["baselineStorage"])

    def metadata(self):
        return copy.deepcopy(self._document["design"])

    def validate_plan(self, plan, ids=None):
        rows = plan.get("regions", [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) or
                not isinstance(row.get("id"), str) or not row["id"] for row in rows):
            _fail("ownership plan regions must be objects with nonempty string IDs")
        names = [row.get("id") for row in rows]
        if len(names) != len(set(names)) or set(names) != set(self.region_ids):
            _fail("ownership contract regions must match the plan exactly, without duplicates")
        if list(self.bounds) != plan.get("bounds"):
            _fail("ownership contract domain must equal the plan bounds")
        for row in rows:
            translation = self.frame(row["id"])["continentTranslation"]
            if row.get("center") != [translation[0], translation[2]]:
                _fail(f"{row['id']}: plan center changes the frozen continent translation")
        if ids is not None and (len(ids) != len(set(ids)) or set(ids) != set(names)):
            _fail("ownership indices must name every plan region exactly once")

    def sample(self, x, z, ids):
        """Exact polygon point ownership; shared edges choose the lexical ID.

        Output indices refer to ``ids``, not the tie order. Points outside the
        closed domain have owner -1. This is distinct from cell quantization.
        """
        from shapely import intersects_xy
        if len(ids) != len(set(ids)) or set(ids) != set(self.region_ids):
            _fail("ownership indices must name every contract region exactly once")
        x, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(z, float))
        if not np.isfinite(x).all() or not np.isfinite(z).all():
            _fail("ownership sample coordinates must be finite")
        result = np.full(x.shape, -1, dtype=np.int32)
        inside = (x >= self.bounds[0]) & (x <= self.bounds[2]) & (z >= self.bounds[1]) & (z <= self.bounds[3])
        for region in sorted(self.region_ids):
            selected = inside & (result == -1) & intersects_xy(self._geometries[region], x, z)
            result[selected] = ids.index(region)
        if np.any(inside & (result == -1)):
            _fail("ownership partition leaves an in-domain sample unowned")
        return result


@lru_cache(maxsize=8)
def _parse(data: bytes) -> OwnershipContract:
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union
    from shapely.validation import explain_validity
    try:
        document = json.loads(data, object_pairs_hook=_object_pairs,
                              parse_constant=lambda v: _fail(f"non-finite JSON value {v}"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise OwnershipContractError(f"ownership contract is not valid JSON: {error}") from error
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        _fail(f"ownership contract schema must be {SCHEMA}")
    revision = document.get("revision")
    if not isinstance(revision, str) or not revision.strip():
        _fail("ownership contract revision is required")
    if document.get("boundaryRule") != "lexical-region-id":
        _fail("ownership boundaryRule must be lexical-region-id")
    bounds = _vector(document.get("bounds"), 4, "ownership bounds")
    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        _fail("ownership bounds must have positive area")
    records = document.get("regions")
    if not isinstance(records, dict) or not records or any(not isinstance(k, str) or not k for k in records):
        _fail("ownership regions must be a nonempty ID-keyed object")
    source = document.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("revision"), str):
        _fail("ownership source revision is required")
    _sha(source.get("manifestSha256"), "ownership source.manifestSha256")
    if not isinstance(document.get("design"), dict):
        _fail("ownership design metadata must be an object")
    geometries = {}
    domain = box(*bounds)
    for region, record in records.items():
        if not isinstance(record, dict):
            _fail(f"{region}: region contract must be an object")
        points = record.get("ownershipPolygon")
        if not isinstance(points, list) or len(points) < 3:
            _fail(f"{region}: ownershipPolygon requires at least three vertices")
        for point in points:
            _vector(point, 2, f"{region}.ownershipPolygon")
        if len({tuple(p) for p in points}) != len(points):
            _fail(f"{region}: ownershipPolygon has repeated vertices (omit closing vertex)")
        geometry = Polygon(points)
        if not geometry.is_valid or geometry.area <= 0:
            _fail(f"{region}: invalid ownership polygon: {explain_validity(geometry)}")
        if not domain.covers(geometry):
            _fail(f"{region}: ownership polygon lies outside the declared domain")
        frame, storage = record.get("coordinateFrame"), record.get("baselineStorage")
        if not isinstance(frame, dict) or not isinstance(storage, dict):
            _fail(f"{region}: coordinateFrame and baselineStorage are required")
        _vector(frame.get("continentTranslation"), 3, f"{region}.continentTranslation")
        _vector(frame.get("origin"), 3, f"{region}.origin")
        _vector(frame.get("serverOrigin"), 2, f"{region}.serverOrigin", integer=True)
        metres = _vector([frame.get("metresPerTile")], 1, f"{region}.metresPerTile")[0]
        if metres != 1 or frame.get("invertServerY") is not True:
            _fail(f"{region}: canonical continent frame requires one metre tiles and inverted server Y")
        cells = _vector(storage.get("serverCells"), 2, f"{region}.serverCells", integer=True)
        if min(cells) <= 0:
            _fail(f"{region}: baseline serverCells must be positive")
        _vector(storage.get("serverTileMin"), 2, f"{region}.serverTileMin", integer=True)
        _vector(storage.get("collisionOriginMetres"), 2, f"{region}.collisionOriginMetres")
        geometries[region] = geometry
    union = unary_union(list(geometries.values()))
    gap = domain.difference(union).area
    overlap = sum(p.area for p in geometries.values()) - union.area
    if gap > AREA_EPSILON or overlap > AREA_EPSILON:
        _fail(f"ownership polygons must partition the domain: gap={gap:.9g}, overlap={overlap:.9g} square metres")
    # A topology correction changes the source revision, not its design rules.
    # Keep lineage-based checks even if a caller renames the outer revision.
    correction = document.get("correction", {})
    if not isinstance(correction, dict):
        _fail("ownership correction provenance must be an object")
    if revision == NYMARA_CORRECTED_REVISION:
        if correction.get("originalRevision") != NYMARA_REVISION or document["design"].get("revision") != NYMARA_REVISION:
            _fail("Nymara topology correction must retain original design lineage")
        for key in ("originalSourceSha256", "originalMasterManifestSha256", "approvedCandidateSha256", "candidateReportSha256"):
            _sha(correction.get(key), f"ownership correction.{key}")
        if correction["originalMasterManifestSha256"] != source["manifestSha256"]:
            _fail("Nymara topology correction master provenance differs from source")
    if (revision in (NYMARA_REVISION, NYMARA_CORRECTED_REVISION)
            or document["design"].get("revision") == NYMARA_REVISION
            or correction.get("originalRevision") == NYMARA_REVISION):
        if bounds != [0, 0, 1500, 1680] or set(records) != NYMARA_IDS:
            _fail("Nymara v4 requires exactly twelve regions over [0,0,1500,1680]")
        design = document["design"]
        circle = design.get("fourGatesCircle")
        expected = {"centre": [520.0, 820.0], "radiusMetres": 200.0,
                    "bounds": [320.0, 620.0, 720.0, 1020.0], "vertexCount": 384}
        if circle != expected or len(records["four_gates"]["ownershipPolygon"]) != 384:
            _fail("Nymara v4 Four Gates circle metadata/384 vertices changed")
        points = records["four_gates"]["ownershipPolygon"]
        if any(abs(math.hypot(x-520, z-820)-200) > .00071 for x, z in points):
            _fail("Nymara v4 Four Gates vertices do not match its millimetre-rounded circle")
        for region, key in (("amberwood", "amberwoodMarkedInclusion"),
                            ("amethyst_barrens", "amethystBarrensMarkedInclusion")):
            marked = design.get(key)
            if not isinstance(marked, list) or len(marked) < 3:
                _fail(f"Nymara v4 requires {key}")
            for point in marked:
                _vector(point, 2, key)
            shape = Polygon(marked)
            if not shape.is_valid:
                _fail(f"Nymara v4 {key} is not a valid marked polygon")
            # The authoritative master generator transfers both marked zones
            # before transferring Four Gates last. Its immutable circle has
            # precedence; demanding the full enclosure would contradict the
            # original master as well as its approved topology correction.
            required = shape.intersection(domain).difference(geometries["four_gates"])
            if required.difference(geometries[region]).area > .01:
                _fail(f"Nymara v4 {key} is not included in {region}")
    return OwnershipContract(revision, tuple(bounds), tuple(records), hashlib.sha256(data).hexdigest(),
                             document, geometries)


def load_contract(path: Path) -> OwnershipContract:
    """Read bytes on every call; cached parsing cannot hide same-size/mtime edits."""
    try:
        return _parse(Path(path).read_bytes())
    except OSError as error:
        raise OwnershipContractError(f"cannot read ownership contract {path}: {error}") from error


def contained_path(root, name):
    """Portable source path: no traversal, drive/URI or link/reparse indirection."""
    if (not isinstance(name, str) or not name or ":" in name or
            name.startswith(("/", "\\")) or
            any(part in ("", ".", "..") for part in name.replace("\\", "/").split("/"))):
        _fail("ownership path must name a contained relative source without traversal")
    root = Path(root).absolute()
    path = root / name.replace("\\", "/")
    for component in (path, *path.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            _fail(f"ownership source rejects symlink/junction/reparse indirection: {component}")
    if not path.resolve().is_relative_to(root.resolve()):
        _fail("ownership path escapes its source root")
    return path


def source_path(plan, source_root=None):
    """Return the selected repo-contained source, or None for the legacy plan."""
    if "ownership_contract" not in plan:
        return None
    selection = plan["ownership_contract"]
    if not isinstance(selection, dict) or set(selection) != {"path", "sha256", "revision"}:
        _fail("plan.ownership_contract requires exactly path, sha256 and revision")
    path = contained_path(source_root or SOURCE_ROOT, selection["path"])
    if path.suffix != ".json":
        _fail("plan.ownership_contract.path must name a contained JSON source")
    return path


def for_plan(plan, ids=None, *, source_root=None):
    path = source_path(plan, source_root)
    if path is None:
        return None
    selection = plan["ownership_contract"]
    expected = _sha(selection["sha256"], "plan.ownership_contract.sha256")
    contract = load_contract(path)
    if contract.sha256 != expected or contract.revision != selection["revision"]:
        _fail("ownership source hash/revision differs from the explicit plan selection")
    contract.validate_plan(plan, ids)
    return contract


def source_dependencies(plan):
    """Hash-bound optional inputs for composition certificates, never outputs."""
    contract = for_plan(plan)
    return {} if contract is None else {source_path(plan): contract.sha256}


def editor_binding(region, plan_path=None):
    """Strict, stateless bake binding; also usable in relocated fixture checkouts.

    The editor previews scalar arrays but delegates geometry/design validation
    here. No certificate is cached or accepted as a replacement for these bytes.
    """
    plan_path = Path(plan_path or SOURCE_ROOT / "diagonal-plan.json").absolute()
    root = plan_path.parent
    client = root.parents[3]
    expected = contained_path(client, "eloria-assets/maps/nymara-regions/_continent/diagonal-plan.json")
    if plan_path != expected or not contained_path(client, "godot-client/project.godot").is_file():
        _fail("ownership plan requires the client checkout repository markers")
    try:
        plan_bytes = plan_path.read_bytes()
        plan = json.loads(plan_bytes, object_pairs_hook=_object_pairs)
    except (OSError, ValueError) as error:
        raise OwnershipContractError(f"cannot read ownership plan: {error}") from error
    if not isinstance(plan, dict):
        _fail("ownership plan must be an object")
    contract = for_plan(plan, source_root=root)
    if contract is None:
        return {}
    if region not in contract.region_ids:
        _fail(f"{region}: region is absent from selected ownership source")
    path = source_path(plan, root)
    binding = {"path": path.relative_to(client).as_posix(), "sha256": contract.sha256,
               "revision": contract.revision, "regionId": region,
               "planPath": plan_path.relative_to(client).as_posix(),
               "planSha256": hashlib.sha256(plan_bytes).hexdigest()}
    if plan_path.read_bytes() != plan_bytes or hashlib.sha256(path.read_bytes()).hexdigest() != contract.sha256:
        _fail("ownership inputs changed during validation; retry the bake")
    polygon = contract.polygons()[region]
    dependencies = [{"path": binding["path"], "sha256": binding["sha256"]},
                    {"path": binding["planPath"], "sha256": binding["planSha256"]}]
    baseline = contained_path(root, "ownership/plan-feature-baseline-v1.json")
    if not baseline.is_file():
        _fail("selected editor ownership requires the certified plan-feature baseline")
    if baseline.is_file():
        baseline_bytes = baseline.read_bytes()
        original = dict(plan)
        original.pop("ownership_contract")
        if original != json.loads(baseline_bytes, object_pairs_hook=_object_pairs):
            _fail("original plan content differs from its certified feature baseline; only ownership_contract may change")
        dependencies.append({"path": baseline.relative_to(client).as_posix(),
                             "sha256": hashlib.sha256(baseline_bytes).hexdigest()})
    for dependency in dependencies:
        if hashlib.sha256(contained_path(client, dependency["path"]).read_bytes()).hexdigest() != dependency["sha256"]:
            _fail("ownership inputs changed during validation; retry the bake")
    return {"binding": binding, "coordinateFrame": contract.frame(region),
            "baselineStorage": contract.storage(region),
            "ownershipPolygonSha256": hashlib.sha256(json.dumps(polygon,
                separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
            "repositoryDependencies": sorted(dependencies, key=lambda item: item["path"])}


def validate_authoring_frame(binding, document):
    from storage_bounds import StorageBounds, authoring_storage
    if not binding:
        try:
            authoring_storage(document.get("server"))
        except ValueError as error:
            _fail(str(error))
        return
    frame, storage = binding["coordinateFrame"], binding["baselineStorage"]
    server = document.get("server", {})
    if (not isinstance(server, dict) or document.get("regionId") != binding["binding"]["regionId"] or
            document.get("continentTranslation") != frame["continentTranslation"] or
            server.get("origin") != frame["serverOrigin"] or
            server.get("metresPerTile", 1) != frame["metresPerTile"] or
            server.get("localOrigin", [0, 0, 0]) != frame["origin"] or
            server.get("invertServerY", True) is not frame["invertServerY"] or
            ("walkingHeight" in frame and server.get("walkingHeight") != frame["walkingHeight"])):
        _fail("authoring frame differs from selected frozen ownership source")
    if frame["origin"] != [0, 0, 0] or frame["invertServerY"] is not True:
        _fail("authoring requires unchanged local origin and inverted server Y")
    try:
        live = authoring_storage(server)
    except ValueError as error:
        _fail(str(error))
    # baselineStorage predates versioned live storage and intentionally has no
    # serverStorageVersion. Never reinterpret or rewrite those historical bytes.
    try:
        baseline = StorageBounds(*storage["serverCells"], *storage["serverTileMin"])
    except (ValueError, TypeError) as error:
        _fail(f"invalid ownership baseline storage: {error}")
    if not live.contains_bounds(baseline):
        _fail("authoring storage must contain the entire frozen ownership baseline")


if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Strict ownership validation for editor baking")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--region", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(editor_binding(args.region, args.plan), separators=(",", ":")))
    except (OwnershipContractError, OSError, ValueError) as error:
        print(f"Ownership validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
