#!/usr/bin/env python3
"""Author a source-faithful Luminous-female trouser/boot hand-off.

This is an offline, review-bundle authoring tool.  It never installs an asset.
A fresh body copy plus Arcanist and Ranger equipment copies are emitted under
a caller-supplied non-production directory.

The separated high-poly female is used as *design authority*, not runtime
geometry.  Its two outer boots overlap its two lower-body layers by 2--5 mm.
The runtime assets keep their own silhouettes and skinning: their actual open
boot rim is measured, and the trouser hem is clipped 3 mm below that local rim.
The rim profile is followed around each calf, avoiding both the old 100+ mm
double layer and the exposed band caused by a single flat cut through a sloped
boot cuff.  Visible trouser cuts stay open and hidden inside the boot; a
generated lining cut at the cuff (the Ranger's boot-paired leg backing) is
sealed again in the cut plane, because a lining is one closed solid.  A final
body with a revised neck may be supplied only when its
whole-file hash is expected or an explicit canonical-provenance sidecar proves
that the pinned lower-body semantic surfaces were inherited unchanged.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import shutil
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import conform_equipment as ce
import equipment_authoring as ea


ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "godot-client"
DEFAULT_MANIFEST = ROOT / "eloria-assets/qa/luminous-female-cuff-fit.json"
PRODUCTION_ROOTS = (
    CLIENT / "assets/actors/native",
    CLIENT / "data/actors",
)
TARGET_STATURE_M = 1.67
HIDDEN_OVERLAP_M = .003
RADIAL_INSET_M = .0015
# Generated linings are closed solids (hip plus both leg tubes); the Ranger's
# boot-paired lining is cut at the cuff and must be sealed again in the cut
# plane.  The visible breeches keep their deliberately open, hidden cut.
SEALED_RANGER_LININGS = ("GeneratedLegBackingWithBoots",)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "eloria-luminous-female-cuff-fit-v2":
        raise ValueError(f"Unexpected cuff-fit manifest schema: {path}")
    return manifest


def _hash_field(value: str, hasher: "hashlib._Hash") -> None:
    raw = value.encode("utf-8")
    hasher.update(struct.pack("<I", len(raw)))
    hasher.update(raw)


def semantic_mesh_contract(document: dict, binary: bytes, name: str, *,
                           primitive_index: int | None = None) -> dict:
    """Hash one runtime primitive independently of GLB packing/layout."""
    item = named_mesh(document, name)
    if primitive_index is None:
        if len(item.get("primitives", [])) != 1:
            raise ValueError(
                f"Expected one primitive on {name!r}; select one explicitly")
        primitive_index = 0
    if not 0 <= primitive_index < len(item.get("primitives", [])):
        raise ValueError(
            f"Primitive {primitive_index} does not exist on {name!r}")
    primitive = item["primitives"][primitive_index]
    hasher = hashlib.sha256()
    _hash_field(name, hasher)
    hasher.update(struct.pack("<I", int(primitive.get("mode", 4))))
    material = int(primitive.get("material", -1))
    material_name = (document.get("materials", [])[material].get("name", "")
                     if 0 <= material < len(document.get("materials", [])) else "")
    _hash_field(material_name, hasher)
    contracts = {}
    accessors = [("INDICES", primitive["indices"])]
    accessors.extend(sorted(primitive["attributes"].items()))
    for semantic, accessor_index in accessors:
        spec = document["accessors"][accessor_index]
        values = np.ascontiguousarray(
            ea.accessor_array(document, binary, accessor_index))
        descriptor = {
            "componentType": int(spec["componentType"]),
            "type": str(spec["type"]),
            "normalized": bool(spec.get("normalized", False)),
            "shape": list(values.shape),
        }
        _hash_field(semantic, hasher)
        encoded = json.dumps(descriptor, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        hasher.update(struct.pack("<I", len(encoded)))
        hasher.update(encoded)
        hasher.update(struct.pack("<Q", values.nbytes))
        hasher.update(values.tobytes(order="C"))
        contracts[semantic] = descriptor
    positions = ea.accessor_array(
        document, binary, primitive["attributes"]["POSITION"])
    faces = ea.accessor_array(
        document, binary, primitive["indices"]).reshape(-1, 3)
    return {
        "sha256": hasher.hexdigest(),
        "vertices": int(len(positions)),
        "triangles": int(len(faces)),
        "material": material_name,
        "accessors": contracts,
    }


def semantic_mesh_contracts(path: Path, names) -> dict[str, dict]:
    document, binary = ea.read_glb(path)
    return {name: semantic_mesh_contract(document, binary, name)
            for name in names}


def _require_semantic_contracts(actual: dict[str, dict],
                                expected: dict[str, dict], label: str) -> None:
    if set(actual) != set(expected):
        raise ValueError(f"{label} semantic mesh roster changed")
    for name in sorted(expected):
        for field in ("sha256", "vertices", "triangles", "material"):
            if actual[name].get(field) != expected[name].get(field):
                raise ValueError(
                    f"{label} semantic surface {name!r} changed {field}: "
                    f"{actual[name].get(field)!r} != {expected[name].get(field)!r}")


def validate_body_provenance_record(provenance: dict, body_spec: dict, *,
                                    actual_hash: str) -> None:
    """Validate canonical lineage without requiring the historical body bytes."""
    accepted = {value.lower() for value in body_spec["acceptedSourceSHA256"]}
    if provenance.get("schema") != "eloria-canonical-body-provenance-v1":
        raise ValueError("Unexpected canonical body provenance schema")
    if provenance.get("canonicalRace") != body_spec["canonicalRace"]:
        raise ValueError("Canonical body provenance names the wrong race")
    if provenance.get("assetSHA256", "").lower() != actual_hash.lower():
        raise ValueError("Canonical body provenance asset hash mismatch")
    if provenance.get("canonicalSourceSHA256", "").lower() not in accepted:
        raise ValueError("Canonical body provenance source is not pinned")
    inherited = provenance.get("inheritedSemanticMeshes", {})
    expected_hashes = {
        name: value["sha256"]
        for name, value in body_spec["semanticMeshes"].items()
    }
    if inherited != expected_hashes:
        raise ValueError("Canonical body provenance surface roster changed")
    if not str(provenance.get("producer", "")).strip():
        raise ValueError("Canonical body provenance has no producer")


def validate_body_source(body: Path, body_spec: dict, *,
                         expected_sha256: str | None = None,
                         provenance_path: Path | None = None) -> dict:
    """Accept an exact body or a provenance-backed neck-only derivative."""
    body = body.resolve()
    actual_hash = digest(body)
    expected_surfaces = body_spec["semanticMeshes"]
    actual_surfaces = semantic_mesh_contracts(body, expected_surfaces)
    _require_semantic_contracts(actual_surfaces, expected_surfaces, "Body")
    accepted = {value.lower() for value in body_spec["acceptedSourceSHA256"]}
    if expected_sha256 is not None:
        expected_hash = expected_sha256.lower()
        if actual_hash != expected_hash:
            raise ValueError(
                f"Expected body SHA-256 {expected_hash}, got {actual_hash}")
        route = "caller-expected-sha256"
    elif actual_hash in accepted:
        route = "manifest-pinned-source"
    elif provenance_path is not None:
        provenance = json.loads(
            provenance_path.read_text(encoding="utf-8"))
        validate_body_provenance_record(
            provenance, body_spec, actual_hash=actual_hash)
        route = "explicit-canonical-provenance"
    else:
        raise ValueError(
            "Unpinned body: provide --expected-body-sha256 or "
            "--body-provenance after the final neck/body asset is reviewed")
    return {
        "path": str(body),
        "sha256": actual_hash,
        "validationRoute": route,
        "semanticMeshes": actual_surfaces,
    }


def validate_pinned_source(path: Path, spec: dict, label: str) -> dict:
    path = path.resolve()
    actual_hash = digest(path)
    if actual_hash != spec["sourceSHA256"]:
        raise ValueError(
            f"{label} SHA-256 changed: {actual_hash} != {spec['sourceSHA256']}")
    expected = {spec["mesh"]: spec["semanticMesh"]}
    actual = semantic_mesh_contracts(path, expected)
    _require_semantic_contracts(actual, expected, label)
    return {"path": str(path), "sha256": actual_hash,
            "semanticMeshes": actual}


def validate_pinned_asset(path: Path, spec: dict, label: str) -> dict:
    """Validate a whole pinned GLB and every semantic surface in its contract."""
    path = path.resolve()
    actual_hash = digest(path)
    if actual_hash != spec["sourceSHA256"]:
        raise ValueError(
            f"{label} SHA-256 changed: {actual_hash} != {spec['sourceSHA256']}")
    expected = spec["semanticMeshes"]
    actual = semantic_mesh_contracts(path, expected)
    _require_semantic_contracts(actual, expected, label)
    return {"path": str(path), "sha256": actual_hash,
            "semanticMeshes": actual}


def validate_equipment_bindings(document: dict, expected_bindings: dict) -> dict:
    """Return the selected live scenes, rejecting a missing or changed one."""
    actual_bindings = {}
    changed = []
    for slot, expected_scene in expected_bindings.items():
        try:
            scene = document["models"][slot]["variants"][
                "canonical_luminous_female"]["scene"]
        except (KeyError, TypeError) as error:
            raise ValueError(
                "Equipment preview binding is missing for "
                f"{slot}/canonical_luminous_female") from error
        actual_bindings[slot] = scene
        if scene != expected_scene:
            changed.append(f"{slot}: {scene!r} != {expected_scene!r}")
    if changed:
        raise ValueError(
            "Equipment preview bindings no longer match the cuff manifest: "
            + "; ".join(changed))
    return actual_bindings


def validate_equipment_config(path: Path, spec: dict) -> dict:
    """Validate only equipment bindings that affect this cuff authoring pass.

    ``sourceSHA256`` remains the immutable hash of the historical authoring
    snapshot.  The live equipment catalog may legitimately change elsewhere
    (for example, hand-socket tuning), so reruns pin the four Luminous-female
    leg and boot scenes instead of requiring byte identity for the whole file.
    """
    path = path.resolve()
    actual_hash = digest(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    actual_bindings = validate_equipment_bindings(
        document, spec["semanticBindings"])
    return {
        "path": str(path),
        "sha256": actual_hash,
        "historicalSHA256": spec["sourceSHA256"],
        "matchesHistoricalSHA256": actual_hash == spec["sourceSHA256"],
        "semanticBindings": actual_bindings,
    }


def validate_output_path(output: Path) -> Path:
    output = output.resolve()
    for production in PRODUCTION_ROOTS:
        production = production.resolve()
        if output == production or production in output.parents:
            raise ValueError(f"Refusing production output path: {output}")
    if output.exists():
        raise FileExistsError(f"Use a fresh review output: {output}")
    return output


def named_mesh(document: dict, name: str) -> dict:
    found = [value for value in document["meshes"] if value.get("name") == name]
    if len(found) != 1:
        raise ValueError(f"Expected exactly one mesh {name!r}, found {len(found)}")
    return found[0]


def mesh(document: dict, name: str) -> dict:
    found = named_mesh(document, name)
    if len(found.get("primitives", [])) != 1:
        raise ValueError(f"Expected one primitive on {name!r}")
    return found


def authority_report(path: Path, specification: dict) -> dict:
    if digest(path) != specification["sourceSHA256"]:
        raise ValueError(f"Unexpected component authority hash: {path}")
    document, binary = ea.read_glb(path)
    if len(document.get("meshes", [])) != specification["meshCount"]:
        raise ValueError("Separated female authority mesh roster changed")
    positions = []
    for item in document["meshes"]:
        primitive = item["primitives"][0]
        positions.append(ea.accessor_array(
            document, binary, primitive["attributes"]["POSITION"]).astype(float))
    overall_high = max(float(value[:, 1].max()) for value in positions)
    overall_low = min(float(value[:, 1].min()) for value in positions)
    target_stature = float(specification.get("targetStatureM", TARGET_STATURE_M))
    scale = target_stature / (overall_high - overall_low)
    # Reviewed semantic components: 0/3 are the separated outer boots; 1/2
    # are the two separated lower-body layers.  Bounds, not names, are the
    # durable evidence in the generator export (the meshes are unnamed).
    boot_bounds = [[float(positions[i][:, 1].min() * scale),
                     float(positions[i][:, 1].max() * scale)]
                   for i in specification["outerBootMeshIndices"]]
    lower_bounds = [[float(positions[i][:, 1].min() * scale),
                      float(positions[i][:, 1].max() * scale)]
                    for i in specification["lowerBodyMeshIndices"]]
    boot_top = min(value[1] for value in boot_bounds)
    overlaps = sorted(boot_top - value[0] for value in lower_bounds)
    if not (0.0015 <= overlaps[0] <= HIDDEN_OVERLAP_M
            <= overlaps[1] <= 0.0055):
        raise ValueError(f"Reviewed component overlap changed: {overlaps}")
    measured_overlap = [1000. * overlaps[0], 1000. * overlaps[1]]
    if not np.allclose(measured_overlap,
                       specification["hiddenOverlapRangeMm"], atol=1e-6):
        raise ValueError("Separated female authority overlap no longer matches manifest")
    return {
        "path": path.name,
        "sha256": digest(path),
        "normalizationScale": scale,
        "outerBootBoundsM": boot_bounds,
        "lowerBodyLayerBoundsM": lower_bounds,
        "hiddenOverlapRangeMm": measured_overlap,
        "selectedHiddenOverlapMm": 1000. * HIDDEN_OVERLAP_M,
    }


def component_labels(points: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    canonical, edges, count = ce._weld(points, faces)
    return canonical, ce._components(edges, count)[canonical]


def ordered_boundary(points: np.ndarray, faces: np.ndarray,
                     canonical: np.ndarray, labels: np.ndarray,
                     label: int) -> np.ndarray:
    selected = faces[np.all(labels[faces] == label, axis=1)]
    welded = canonical[selected]
    counts = Counter(tuple(sorted((int(a), int(b))))
                     for tri in welded
                     for a, b in ((tri[0], tri[1]), (tri[1], tri[2]),
                                  (tri[2], tri[0])))
    boundary = [edge for edge, count in counts.items() if count == 1]
    adjacency: dict[int, list[int]] = defaultdict(list)
    for a, b in boundary:
        adjacency[a].append(b)
        adjacency[b].append(a)
    first_original = {}
    for index, value in enumerate(canonical):
        first_original.setdefault(int(value), index)
    cycles = []
    seen = set()
    for start in sorted(adjacency):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        vertices = []
        while stack:
            here = stack.pop()
            vertices.append(here)
            for there in adjacency[here]:
                if there not in seen:
                    seen.add(there)
                    stack.append(there)
        if len(vertices) >= 6:
            cycles.append(vertices)
    if not cycles:
        raise ValueError("Main boot shell has no usable open cuff")
    # The top opening has the highest median Y.  A lower opening can be an
    # authored slit in the same connected shoe shell (the Arcanist right boot
    # has one); it is not the trouser hand-off.
    chosen = max(cycles, key=lambda values: float(np.median(
        points[[first_original[v] for v in values], 1])))
    # Walk the degree-two boundary so a median filter can reject a lone crest
    # without flattening the authored sloped rim.
    allowed = set(chosen)
    start = min(chosen)
    ordered = [start]
    previous = None
    current = start
    for _ in range(len(chosen) + 1):
        neighbours = sorted(v for v in adjacency[current] if v in allowed)
        candidates = [v for v in neighbours if v != previous]
        if not candidates:
            break
        following = candidates[0]
        if following == start:
            break
        ordered.append(following)
        previous, current = current, following
    if len(ordered) != len(chosen):
        # Non-manifold authoring is still measured deterministically.  Angular
        # ordering is sufficient for the local profile in that fallback.
        ordered = chosen
    return points[[first_original[value] for value in ordered]].copy()


@dataclass
class CuffProfile:
    side: str
    points: np.ndarray
    centre: np.ndarray
    angles: np.ndarray
    heights: np.ndarray
    radii: np.ndarray
    raw_heights: np.ndarray
    measurement: str = "open-boundary-local-profile"

    def cutoff(self, point: np.ndarray) -> float:
        angle = math.atan2(float(point[2] - self.centre[1]),
                           float(point[0] - self.centre[0]))
        return float(np.interp(angle, self.angles, self.heights)) - HIDDEN_OVERLAP_M

    def inner_radius(self, point: np.ndarray) -> float:
        angle = math.atan2(float(point[2] - self.centre[1]),
                           float(point[0] - self.centre[0]))
        return float(np.interp(angle, self.angles, self.radii))


def cuff_profiles(document: dict, binary: bytes, mesh_name: str) -> dict[str, CuffProfile]:
    primitive = mesh(document, mesh_name)["primitives"][0]
    points = ea.accessor_array(
        document, binary, primitive["attributes"]["POSITION"]).astype(float)
    faces = ea.accessor_array(document, binary, primitive["indices"]).reshape(-1, 3)
    canonical, labels = component_labels(points, faces)
    result = {}
    for side, sign in (("left", 1.), ("right", -1.)):
        candidates = []
        for label in np.unique(labels):
            own = labels == label
            if own.sum() < 100 or float(np.median(points[own, 0])) * sign <= 0:
                continue
            score = int(own.sum()) * float(np.ptp(points[own, 1]))
            candidates.append((score, int(label)))
        if not candidates:
            raise ValueError(f"No main boot shell for {side}")
        rim = ordered_boundary(points, faces, canonical, labels,
                               max(candidates)[1])
        centre = np.median(rim[:, [0, 2]], axis=0)
        angle = np.arctan2(rim[:, 2] - centre[1], rim[:, 0] - centre[0])
        order = np.argsort(angle, kind="stable")
        angle, raw = angle[order], rim[order, 1]
        radius = np.linalg.norm(rim[order][:, [0, 2]] - centre, axis=1)
        # An isolated decorative crest must not lift the trouser cut and expose
        # the calf beside it.  A three-sample circular median preserves a
        # genuinely sloped cuff and rejects only a one-vertex spike.
        smooth = np.median(np.column_stack((np.roll(raw, 1), raw,
                                            np.roll(raw, -1))), axis=1)
        smooth_radius = np.median(np.column_stack((np.roll(radius, 1), radius,
                                                   np.roll(radius, -1))), axis=1)
        periodic_angle = np.concatenate((angle[-1:] - 2 * np.pi, angle,
                                         angle[:1] + 2 * np.pi))
        periodic_height = np.concatenate((smooth[-1:], smooth, smooth[:1]))
        periodic_radius = np.concatenate((smooth_radius[-1:], smooth_radius,
                                          smooth_radius[:1]))
        result[side] = CuffProfile(side, rim, centre, periodic_angle,
                                   periodic_height, periodic_radius, raw)
    return result


def ranger_cuff_profiles(document: dict, binary: bytes,
                         mesh_name: str) -> tuple[dict[str, CuffProfile], dict]:
    """Measure the closed Ranger boot shafts without treating tabs as cuffs.

    The Ranger's main leather boot shells are closed at their upper ends, so
    their only topological boundary is down at the sole.  The class-fit v22
    review established the stable source measurement used here: select the
    substantial left/right leather shells, exclude every detached sole, strap
    and pull-tab island, then use each shell's 98th-percentile Y as its cuff.
    This reproduces the reviewed 228.851/225.998 mm cuff authority while the
    clipping implementation and safety audit remain independent of v22 bytes.
    """
    primitive = mesh(document, mesh_name)["primitives"][0]
    points = ea.accessor_array(
        document, binary, primitive["attributes"]["POSITION"]).astype(float)
    faces = ea.accessor_array(document, binary,
                              primitive["indices"]).reshape(-1, 3)
    _, labels = component_labels(points, faces)
    profiles: dict[str, CuffProfile] = {}
    authority = {
        "method": "main-shell-y-p98",
        "quantile": .98,
        "detachedComponentsExcluded": True,
        "sides": {},
    }
    for side, sign in (("left", 1.), ("right", -1.)):
        candidates = []
        for label in np.unique(labels):
            own = labels == label
            count = int(own.sum())
            extent = float(np.ptp(points[own, 1]))
            if (count < 500 or extent < .15
                    or float(np.median(points[own, 0])) * sign <= 0):
                continue
            candidates.append((count * extent, int(label)))
        if len(candidates) != 1:
            raise ValueError(
                f"Expected one substantial Ranger boot shell for {side}, "
                f"found {len(candidates)}")
        label = candidates[0][1]
        shell = points[labels == label]
        cuff_y = float(np.quantile(shell[:, 1], .98))
        centre = np.median(shell[:, [0, 2]], axis=0)
        top = shell[shell[:, 1] >= cuff_y - 1e-10]
        radius = float(np.median(np.linalg.norm(
            top[:, [0, 2]] - centre, axis=1)))
        profiles[side] = CuffProfile(
            side=side,
            points=top.copy(),
            centre=centre,
            angles=np.asarray([-math.pi, math.pi]),
            heights=np.asarray([cuff_y, cuff_y]),
            radii=np.asarray([radius, radius]),
            raw_heights=np.asarray([cuff_y]),
            measurement="closed-main-shell-y-p98",
        )
        authority["sides"][side] = {
            "componentLabel": label,
            "vertices": len(shell),
            "sourceYRangeM": [float(shell[:, 1].min()),
                               float(shell[:, 1].max())],
            "cuffY98M": cuff_y,
            "trouserCutYM": cuff_y - HIDDEN_OVERLAP_M,
        }
    return profiles, authority


def blend_skin(joints_a: np.ndarray, weights_a: np.ndarray,
               joints_b: np.ndarray, weights_b: np.ndarray,
               t: float) -> tuple[np.ndarray, np.ndarray]:
    totals: dict[int, float] = defaultdict(float)
    for joint, weight in zip(joints_a, weights_a):
        totals[int(joint)] += (1. - t) * float(weight)
    for joint, weight in zip(joints_b, weights_b):
        totals[int(joint)] += t * float(weight)
    chosen = sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))[:4]
    out_joints = np.zeros(4, dtype=np.uint16)
    out_weights = np.zeros(4, dtype=np.float64)
    for index, (joint, weight) in enumerate(chosen):
        out_joints[index], out_weights[index] = joint, weight
    total = float(out_weights.sum())
    if total <= 1e-12:
        raise ValueError("Interpolated cuff vertex has no skin influence")
    out_weights /= total
    return out_joints, out_weights


def clip_above_cuff(arrays: dict[str, np.ndarray], faces: np.ndarray,
                    profiles: dict[str, CuffProfile], *, cap: bool = False,
                    restrict_to_boot_interior: bool = False,
                    keep_above: bool = True,
                    boundary_offset_m: float = 0.
                    ) -> tuple[dict[str, np.ndarray], np.ndarray, dict]:
    if restrict_to_boot_interior and not keep_above:
        raise ValueError("Radial boot-interior clipping only supports keep-above")
    positions = arrays["POSITION"].astype(np.float64)
    normals = arrays["NORMAL"].astype(np.float64)
    uvs = arrays["TEXCOORD_0"].astype(np.float64)
    joints = arrays["JOINTS_0"].astype(np.uint16)
    weights = arrays["WEIGHTS_0"].astype(np.float64)
    faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    original_face_count = len(faces)
    # A garment face that bridges both calves below the cuffs cannot belong to
    # either boot.  It is the old front/back ownership split in topology form.
    # Drop only such low cross-body bridges; the separately-authored inseam
    # mesh remains untouched on equipment that carries one.
    bridge_ceiling = max(float(value.heights.max())
                         for value in profiles.values()) + .05
    crosses_sides = ((positions[faces, 0].min(axis=1) < -1e-5)
                     & (positions[faces, 0].max(axis=1) > 1e-5))
    low_bridge = (np.zeros(len(faces), dtype=bool)
                  if restrict_to_boot_interior or not keep_above
                  else crosses_sides
                  & (positions[faces, 1].min(axis=1) < bridge_ceiling))
    faces = faces[~low_bridge]

    def profile(point: np.ndarray) -> CuffProfile:
        return profiles["left" if point[0] >= 0 else "right"]

    def vertical_signed(point: np.ndarray) -> float:
        return float(point[1] - (profile(point).cutoff(point)
                                 + boundary_offset_m))

    def radial_signed(point: np.ndarray) -> float:
        cuff = profile(point)
        radius = float(np.linalg.norm(point[[0, 2]] - cuff.centre))
        # The radial transition is also hidden 1.5 mm inside the measured
        # cuff silhouette.  Geometry outside it is ornament/tabard, not the
        # under-boot leg shell, and must remain untouched.
        return radius - (cuff.inner_radius(point) - RADIAL_INSET_M)

    def signed(point: np.ndarray) -> float:
        vertical = vertical_signed(point)
        if not restrict_to_boot_interior:
            return vertical if keep_above else -vertical
        return max(vertical, radial_signed(point))

    signed_original = np.asarray([signed(point) for point in positions])
    out_p, out_n, out_uv = list(positions), list(normals), list(uvs)
    out_j, out_w = list(joints), list(weights)
    cache: dict[tuple[int, int], int] = {}

    def cross(a: int, b: int) -> int:
        key = tuple(sorted((int(a), int(b))))
        if key in cache:
            return cache[key]
        pa, pb = positions[a], positions[b]
        sa, sb = signed_original[a], signed_original[b]
        low, high = 0., 1.
        # Solve against the curved cuff profile rather than pretending its
        # height is constant across a triangle edge.
        for _ in range(36):
            t = (low + high) * .5
            value = signed(pa + (pb - pa) * t)
            if (value < 0) == (sa < 0):
                low = t
            else:
                high = t
        t = (low + high) * .5
        point = pa + (pb - pa) * t
        normal = normals[a] + (normals[b] - normals[a]) * t
        length = float(np.linalg.norm(normal))
        normal = normal / length if length > 1e-12 else normals[a]
        joint, weight = blend_skin(joints[a], weights[a], joints[b], weights[b], t)
        cache[key] = len(out_p)
        out_p.append(point)
        out_n.append(normal)
        out_uv.append(uvs[a] + (uvs[b] - uvs[a]) * t)
        out_j.append(joint)
        out_w.append(weight)
        return cache[key]

    kept = []
    kept_parent = []
    keep = signed_original >= -1e-10
    for face_index, triangle in enumerate(faces):
        polygon = []
        for a, b in zip(triangle, np.roll(triangle, -1)):
            a, b = int(a), int(b)
            if keep[a]:
                polygon.append(a)
            if keep[a] != keep[b]:
                polygon.append(cross(a, b))
        if len(polygon) >= 3:
            for column in range(1, len(polygon) - 1):
                kept.append((polygon[0], polygon[column], polygon[column + 1]))
                kept_parent.append(face_index)
    if not kept:
        raise ValueError("Cuff clip removed the entire trouser mesh")
    kept = np.asarray(kept, dtype=np.uint32)
    used = np.unique(kept)
    remap = np.full(len(out_p), np.iinfo(np.uint32).max, dtype=np.uint32)
    remap[used] = np.arange(len(used), dtype=np.uint32)
    compact = {
        "POSITION": np.asarray(out_p, dtype=np.float32)[used],
        "NORMAL": np.asarray(out_n, dtype=np.float32)[used],
        "TEXCOORD_0": np.asarray(out_uv, dtype=np.float32)[used],
        "JOINTS_0": np.asarray(out_j, dtype=np.uint16)[used],
        "WEIGHTS_0": np.asarray(out_w, dtype=np.float32)[used],
    }
    new_faces = remap[kept]
    source_face_points = positions[faces[np.asarray(kept_parent)]]
    output_face_points = compact["POSITION"][new_faces]
    source_cross = np.cross(source_face_points[:, 1] - source_face_points[:, 0],
                            source_face_points[:, 2] - source_face_points[:, 0])
    output_cross = np.cross(output_face_points[:, 1] - output_face_points[:, 0],
                            output_face_points[:, 2] - output_face_points[:, 0])
    source_length = np.linalg.norm(source_cross, axis=1)
    output_length = np.linalg.norm(output_cross, axis=1)
    oriented = (source_length > 1e-12) & (output_length > 1e-12)
    orientation_cosine = np.ones(len(new_faces))
    orientation_cosine[oriented] = np.einsum(
        "ij,ij->i", source_cross[oriented], output_cross[oriented]) / (
            source_length[oriented] * output_length[oriented])
    unsafe_orientation = oriented & (orientation_cosine <= 0.)
    if unsafe_orientation.any():
        raise ValueError("Cuff clip inverted an authored trouser triangle")
    new_rows = used >= len(positions)
    seam_points = compact["POSITION"][new_rows]
    seam_signed = np.asarray([signed(value) for value in seam_points])
    seam_error = np.abs(seam_signed)
    seam_vertical = np.asarray([vertical_signed(value) for value in seam_points])
    seam_radial = np.asarray([radial_signed(value) for value in seam_points])
    vertical_boundary = ((np.abs(seam_vertical) <= 1e-6)
                         & (seam_radial <= 1e-6))
    radial_boundary = (restrict_to_boot_interior
                       & (np.abs(seam_radial) <= 1e-6)
                       & (seam_vertical < 1e-6))
    overlap_mm = 1000. * (HIDDEN_OVERLAP_M - boundary_offset_m
                          - seam_vertical[vertical_boundary])
    radial_inset_mm = np.asarray(
        [1000. * (profile(value).inner_radius(value)
                  - np.linalg.norm(value[[0, 2]] - profile(value).centre))
         for value in seam_points[radial_boundary]])
    cap_vertices = 0
    cap_triangles = 0
    cap_minimum_up = 1.
    if cap:
        seam_indices = np.flatnonzero(new_rows)
        additions = {name: [] for name in compact}
        cap_faces = []
        for side, sign in (("left", 1.), ("right", -1.)):
            selected = seam_indices[compact["POSITION"][seam_indices, 0] * sign > 1e-5]
            if len(selected) < 3:
                raise ValueError(f"No clipped trouser ring to cap on {side}")
            # Collapse UV-split copies only for the new cap.  The side wall
            # keeps every authored UV vertex; the cap receives its own hard
            # normal and cannot alter the existing shading seam.
            quantized = np.round(compact["POSITION"][selected] / 1e-6).astype(np.int64)
            _, unique = np.unique(quantized, axis=0, return_index=True)
            ring = selected[np.sort(unique)]
            cuff = profiles[side]
            angles = np.arctan2(compact["POSITION"][ring, 2] - cuff.centre[1],
                                compact["POSITION"][ring, 0] - cuff.centre[0])
            ring = ring[np.argsort(angles, kind="stable")]
            outer_start = len(compact["POSITION"]) + len(additions["POSITION"])
            outer_positions = []
            # Fill to 1.5 mm inside the measured boot rim.  This covers the
            # hollow boot's jagged interior while remaining strictly inside
            # its silhouette and retaining the 3 mm vertical tuck.
            for index in ring:
                point = compact["POSITION"][index].astype(float).copy()
                radial = point[[0, 2]] - cuff.centre
                length = float(np.linalg.norm(radial))
                if length <= 1e-8:
                    raise ValueError("Cuff cap ring reaches its polar centre")
                target = max(length, cuff.inner_radius(point) - RADIAL_INSET_M)
                point[[0, 2]] = cuff.centre + radial * (target / length)
                point[1] = cuff.cutoff(point)
                outer_positions.append(point)
                additions["POSITION"].append(point)
                additions["NORMAL"].append(np.array([0., 1., 0.], dtype=np.float32))
                additions["TEXCOORD_0"].append(compact["TEXCOORD_0"][index])
                additions["JOINTS_0"].append(compact["JOINTS_0"][index])
                additions["WEIGHTS_0"].append(compact["WEIGHTS_0"][index])
            centre_position = np.asarray(outer_positions).mean(axis=0)
            centre_position[[0, 2]] = cuff.centre
            centre_uv = compact["TEXCOORD_0"][ring].mean(axis=0)
            totals: dict[int, float] = defaultdict(float)
            for index in ring:
                for joint, weight in zip(compact["JOINTS_0"][index],
                                         compact["WEIGHTS_0"][index]):
                    totals[int(joint)] += float(weight) / len(ring)
            chosen = sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))[:4]
            centre_joints = np.zeros(4, dtype=np.uint16)
            centre_weights = np.zeros(4, dtype=np.float32)
            for column, (joint, weight) in enumerate(chosen):
                centre_joints[column], centre_weights[column] = joint, weight
            centre_weights /= centre_weights.sum()
            additions["POSITION"].append(centre_position)
            additions["NORMAL"].append(np.array([0., 1., 0.], dtype=np.float32))
            additions["TEXCOORD_0"].append(centre_uv)
            additions["JOINTS_0"].append(centre_joints)
            additions["WEIGHTS_0"].append(centre_weights)
            centre_index = outer_start + len(ring)
            for column in range(len(ring)):
                outer = outer_start + column
                outer_next = outer_start + (column + 1) % len(ring)
                cap_faces.append((centre_index, outer_next, outer))
            cap_vertices += len(ring) + 1
            cap_triangles += len(ring)
        for name in compact:
            compact[name] = np.concatenate(
                (compact[name], np.asarray(additions[name], dtype=compact[name].dtype)), axis=0)
        cap_faces = np.asarray(cap_faces, dtype=np.uint32)
        cap_points = compact["POSITION"][cap_faces]
        cap_cross = np.cross(cap_points[:, 1] - cap_points[:, 0],
                             cap_points[:, 2] - cap_points[:, 0])
        downward = cap_cross[:, 1] < 0.
        cap_faces[downward, 1], cap_faces[downward, 2] = (
            cap_faces[downward, 2].copy(), cap_faces[downward, 1].copy())
        cap_points = compact["POSITION"][cap_faces]
        cap_cross = np.cross(cap_points[:, 1] - cap_points[:, 0],
                             cap_points[:, 2] - cap_points[:, 0])
        cap_length = np.linalg.norm(cap_cross, axis=1)
        cap_up = cap_cross[:, 1] / np.maximum(cap_length, 1e-12)
        cap_minimum_up = float(cap_up.min(initial=1.))
        if np.any(cap_length <= 1e-12) or cap_minimum_up <= 0.:
            raise ValueError("Cuff cap has a degenerate or inverted triangle")
        new_faces = np.vstack((new_faces, cap_faces))
    # Audit the deliberately open cut edge.  The new intersection vertices
    # must form manifold boundary chains/loops local to one leg; none may be
    # stranded or bridge the left/right ownership boundary.
    edge_counts = Counter(tuple(sorted((int(a), int(b))))
                          for tri in new_faces
                          for a, b in ((tri[0], tri[1]), (tri[1], tri[2]),
                                       (tri[2], tri[0])))
    seam_new = set(np.flatnonzero(new_rows).astype(int).tolist())
    open_seam_edges = [edge for edge, count in edge_counts.items()
                       if count == 1 and edge[0] in seam_new and edge[1] in seam_new]
    open_adjacency: dict[int, set[int]] = defaultdict(set)
    for a, b in open_seam_edges:
        open_adjacency[a].add(b)
        open_adjacency[b].add(a)
    open_vertices = set(open_adjacency)
    stranded = seam_new - open_vertices
    cross_side_open_edges = sum(
        1 for a, b in open_seam_edges
        if compact["POSITION"][[a, b], 0].min() < -1e-5
        and compact["POSITION"][[a, b], 0].max() > 1e-5)
    components = []
    visited: set[int] = set()
    for start in sorted(open_vertices):
        if start in visited:
            continue
        stack, component = [start], []
        visited.add(start)
        while stack:
            value = stack.pop()
            component.append(value)
            for neighbour in open_adjacency[value]:
                if neighbour not in visited:
                    visited.add(neighbour)
                    stack.append(neighbour)
        components.append(component)
    degrees = [len(open_adjacency[value]) for value in open_vertices]
    closed_loops = sum(1 for component in components
                       if all(len(open_adjacency[value]) == 2
                              for value in component))
    if not cap:
        if not open_seam_edges or stranded:
            raise ValueError("Open cuff boundary does not own every clipped vertex")
        if cross_side_open_edges:
            raise ValueError("Open cuff boundary bridges left and right legs")
        if max(degrees, default=0) > 2:
            raise ValueError("Open cuff boundary is non-manifold")
    open_boundary_audit = {
        "intentional": not cap,
        "boundaryEdges": len(open_seam_edges),
        "boundaryVertices": len(open_vertices),
        "components": len(components),
        "closedLoops": closed_loops,
        "openChains": len(components) - closed_loops,
        "minimumVertexDegree": min(degrees, default=0),
        "maximumVertexDegree": max(degrees, default=0),
        "strandedClippedVertices": len(stranded),
        "crossSideBoundaryEdges": cross_side_open_edges,
    }
    triangle_points = compact["POSITION"][new_faces]
    doubled_area = np.linalg.norm(np.cross(
        triangle_points[:, 1] - triangle_points[:, 0],
        triangle_points[:, 2] - triangle_points[:, 0]), axis=1)
    worst = np.argsort(seam_error)[-8:][::-1]
    report = {
        "sourceVertices": len(positions),
        "sourceTriangles": original_face_count,
        "outputVertices": len(compact["POSITION"]),
        "outputTriangles": len(new_faces),
        "newBoundaryVertices": int(new_rows.sum()),
        "removedTrianglesNet": int(original_face_count - len(new_faces)),
        "crossSideBridgeFacesRemoved": int(low_bridge.sum()),
        "maximumCutProfileErrorMm": float(1000. * seam_error.max(initial=0.)),
        "localHiddenOverlapMm": [float(overlap_mm.min(initial=1000. * HIDDEN_OVERLAP_M)),
                                  float(overlap_mm.max(initial=1000. * HIDDEN_OVERLAP_M))],
        "localOverlapInsideBootRimMm": [
            float(overlap_mm.min(initial=1000. * (
                HIDDEN_OVERLAP_M - boundary_offset_m))),
            float(overlap_mm.max(initial=1000. * (
                HIDDEN_OVERLAP_M - boundary_offset_m)))],
        "keptSide": "above" if keep_above else "below",
        "boundaryOffsetFromTrouserCutMm": 1000. * boundary_offset_m,
        "bootInteriorRestriction": restrict_to_boot_interior,
        "verticalBoundaryVertices": int(vertical_boundary.sum()),
        "radialBoundaryVertices": int(radial_boundary.sum()),
        "radialHiddenInsetMm": [
            float(radial_inset_mm.min(initial=1000. * RADIAL_INSET_M)),
            float(radial_inset_mm.max(initial=1000. * RADIAL_INSET_M))],
        "crossSideBoundaryVertices": int(np.count_nonzero(
            np.abs(seam_points[:, 0]) < 1e-5)),
        "openBoundaryAudit": open_boundary_audit,
        "capVertices": cap_vertices,
        "capTriangles": cap_triangles,
        "capMinimumUpwardCosine": cap_minimum_up,
        "minimumClippedOrientationCosine": float(
            orientation_cosine[oriented].min(initial=1.)),
        "unsafeOrientationTriangles": int(unsafe_orientation.sum()),
        "minimumTriangleAreaM2": float((.5 * doubled_area).min(initial=np.inf)),
        "degenerateTriangles": int(np.count_nonzero(doubled_area <= 1e-12)),
        "worstBoundaryPoints": [
            {"position": seam_points[index].astype(float).tolist(),
             "errorMm": float(1000. * seam_error[index])}
            for index in worst if seam_error[index] > 1e-6],
        "maximumWeightSumError": float(np.abs(
            compact["WEIGHTS_0"].sum(axis=1) - 1.).max(initial=0.)),
        "maximumInfluences": 4,
    }
    return compact, new_faces, report


def seal_cut_lining(arrays: dict[str, np.ndarray], faces: np.ndarray
                    ) -> tuple[dict[str, np.ndarray], np.ndarray, dict]:
    """Close the loops a cuff cut leaves open in a generated lining.

    A generated leg lining is one closed solid: the hip and both leg tubes in
    one shell (``test_equipment_fit`` requires it).  Clipping the lining at
    the boot cuff removes the tube ends and leaves every wall open at the cut
    plane.  The visible trousers keep their deliberately open cut, because a
    cap there would draw a dark disc between trouser and boot.  The lining is
    drawn inside the trousers, so its cut is closed where it lies: in the cut
    plane, 3 mm below the boot rim and inside the boot shaft.

    Vertices are welded by exact position.  Each open loop of the welded
    boundary is fanned from its centroid, and every cap triangle runs its
    boundary edge opposite to the wall face that owns it, so the lining keeps
    one consistent winding: outer walls cap downward and the inner walls of
    the double-walled lining cap upward.  Cap vertices are new rows carrying
    the boundary vertex's UV and skin and a vertical hard normal; no authored
    or clipped wall row changes.
    """
    positions = np.asarray(arrays["POSITION"])
    faces = np.asarray(faces, dtype=np.uint32).reshape(-1, 3)
    _, welded = np.unique(positions, axis=0, return_inverse=True)
    welded = welded.reshape(-1)
    representative: dict[int, int] = {}
    for row, value in enumerate(welded):
        representative.setdefault(int(value), row)
    directed = [(int(a), int(b))
                for tri in welded[faces]
                for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0]))]
    counts = Counter(tuple(sorted(edge)) for edge in directed)
    if any(count % 2 and count > 1 for count in counts.values()):
        raise ValueError("Lining cut has an odd non-manifold edge; cannot seal")
    boundary = [edge for edge in directed if counts[tuple(sorted(edge))] == 1]
    if not boundary:
        raise ValueError("Lining cut left no open boundary to seal")
    adjacency: dict[int, set[int]] = defaultdict(set)
    for a, b in boundary:
        adjacency[a].add(b)
        adjacency[b].add(a)
    loops: list[set[int]] = []
    seen: set[int] = set()
    for start in sorted(adjacency):
        if start in seen:
            continue
        stack, component = [start], set()
        seen.add(start)
        while stack:
            here = stack.pop()
            component.add(here)
            for there in adjacency[here]:
                if there not in seen:
                    seen.add(there)
                    stack.append(there)
        loops.append(component)
    additions = {name: [] for name in arrays}
    cap_faces = []
    loop_reports = []
    base = len(positions)
    for component in loops:
        ring = sorted(component)
        edges = [edge for edge in boundary if edge[0] in component]
        ring_points = np.asarray([positions[representative[value]] for value in ring],
                                 dtype=np.float64)
        heights = ring_points[:, 1]
        if float(np.ptp(heights)) > 1e-6:
            raise ValueError("Lining cut loop is not planar; cannot seal it flat")
        centre = ring_points.mean(axis=0)
        fan = np.asarray([
            np.cross(positions[representative[b]].astype(np.float64) - centre,
                     positions[representative[a]].astype(np.float64) - centre)
            for a, b in edges])
        facing = 1. if float(fan[:, 1].sum()) >= 0. else -1.
        start = base + len(additions["POSITION"])
        local = {value: start + column for column, value in enumerate(ring)}
        for value in ring:
            row = representative[value]
            additions["POSITION"].append(positions[row])
            additions["NORMAL"].append(np.array([0., facing, 0.], dtype=np.float32))
            additions["TEXCOORD_0"].append(arrays["TEXCOORD_0"][row])
            additions["JOINTS_0"].append(arrays["JOINTS_0"][row])
            additions["WEIGHTS_0"].append(arrays["WEIGHTS_0"][row])
        totals: dict[int, float] = defaultdict(float)
        for value in ring:
            row = representative[value]
            for joint, weight in zip(arrays["JOINTS_0"][row], arrays["WEIGHTS_0"][row]):
                totals[int(joint)] += float(weight) / len(ring)
        chosen = sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))[:4]
        centre_joints = np.zeros(4, dtype=np.uint16)
        centre_weights = np.zeros(4, dtype=np.float32)
        for column, (joint, weight) in enumerate(chosen):
            centre_joints[column], centre_weights[column] = joint, weight
        centre_weights /= centre_weights.sum()
        centre_index = start + len(ring)
        additions["POSITION"].append(centre.astype(np.float32))
        additions["NORMAL"].append(np.array([0., facing, 0.], dtype=np.float32))
        additions["TEXCOORD_0"].append(np.mean(
            [arrays["TEXCOORD_0"][representative[value]] for value in ring], axis=0))
        additions["JOINTS_0"].append(centre_joints)
        additions["WEIGHTS_0"].append(centre_weights)
        for a, b in edges:
            cap_faces.append((centre_index, local[b], local[a]))
        loop_reports.append({
            "boundaryEdges": len(edges),
            "boundaryVertices": len(ring),
            "cutPlaneYM": float(heights.mean()),
            "facing": "down" if facing < 0 else "up",
            "foldedFanTriangles": int(np.count_nonzero(fan[:, 1] * facing <= 0.)),
        })
    sealed = {name: np.concatenate(
        (np.asarray(arrays[name]),
         np.asarray(additions[name], dtype=np.asarray(arrays[name]).dtype)), axis=0)
        for name in arrays}
    sealed_faces = np.vstack((faces, np.asarray(cap_faces, dtype=np.uint32)))
    # Audit: the sealed lining has no open welded edge left, and nothing new
    # is degenerate or carries more than four normalised influences.
    _, rewelded = np.unique(sealed["POSITION"], axis=0, return_inverse=True)
    rewelded = rewelded.reshape(-1)[sealed_faces]
    after = Counter(tuple(sorted((int(a), int(b))))
                    for tri in rewelded
                    for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])))
    open_after = sum(1 for count in after.values() if count % 2)
    cap_points = sealed["POSITION"][np.asarray(cap_faces, dtype=np.int64)].astype(np.float64)
    doubled_area = np.linalg.norm(np.cross(cap_points[:, 1] - cap_points[:, 0],
                                           cap_points[:, 2] - cap_points[:, 0]), axis=1)
    if open_after:
        raise ValueError(f"Sealed lining still has {open_after} open edges")
    if np.any(doubled_area <= 1e-12):
        raise ValueError("Lining seal produced a degenerate triangle")
    report = {
        "method": "welded-boundary-loop-centroid-fan",
        "loops": len(loops),
        "boundaryEdges": len(boundary),
        "capVertices": int(len(additions["POSITION"])),
        "capTriangles": len(cap_faces),
        "downwardLoops": sum(1 for value in loop_reports if value["facing"] == "down"),
        "upwardLoops": sum(1 for value in loop_reports if value["facing"] == "up"),
        "foldedFanTriangles": sum(value["foldedFanTriangles"] for value in loop_reports),
        "openEdgesAfterSeal": open_after,
        "degenerateTriangles": 0,
        "minimumCapTriangleAreaM2": float(.5 * doubled_area.min()),
        "maximumWeightSumError": float(np.abs(
            sealed["WEIGHTS_0"].astype(np.float64).sum(axis=1) - 1.).max(initial=0.)),
        "cutPlaneYM": sorted({round(value["cutPlaneYM"], 9) for value in loop_reports}),
        "outputVertices": int(len(sealed["POSITION"])),
        "outputTriangles": int(len(sealed_faces)),
        "loopDetail": loop_reports,
    }
    return sealed, sealed_faces, report


def append_accessor(document: dict, payload: bytearray, values: np.ndarray,
                    component_type: int, accessor_type: str,
                    *, bounds: bool = False, normalized: bool = False) -> int:
    while len(payload) % 4:
        payload.append(0)
    values = np.ascontiguousarray(values)
    offset = len(payload)
    raw = values.tobytes()
    payload.extend(raw)
    document["bufferViews"].append({"buffer": 0, "byteOffset": offset,
                                    "byteLength": len(raw)})
    spec = {"bufferView": len(document["bufferViews"]) - 1,
            "componentType": component_type,
            "count": len(values), "type": accessor_type}
    if normalized:
        spec["normalized"] = True
    if bounds:
        reshaped = values.reshape(len(values), -1)
        spec["min"] = reshaped.min(axis=0).astype(float).tolist()
        spec["max"] = reshaped.max(axis=0).astype(float).tolist()
    document["accessors"].append(spec)
    return len(document["accessors"]) - 1


def write_glb(document: dict, binary: bytes, target: Path) -> None:
    document["buffers"][0]["byteLength"] = len(binary)
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    padded_binary = binary + b"\0" * (-len(binary) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(padded_binary)
    raw = bytearray(struct.pack("<III", 0x46546C67, 2, total))
    raw.extend(struct.pack("<II", len(encoded), 0x4E4F534A))
    raw.extend(encoded)
    raw.extend(struct.pack("<II", len(padded_binary), 0x004E4942))
    raw.extend(padded_binary)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


def clipped_copy(source: Path, target: Path, trouser_mesh: str,
                 boot_source: Path, boot_mesh: str, *, cap: bool = False,
                 restrict_to_boot_interior: bool = False,
                 preserve_additional_trouser_primitives: bool = False) -> dict:
    document, binary = ea.read_glb(source)
    boot_document, boot_binary = ea.read_glb(boot_source)
    profiles = cuff_profiles(boot_document, boot_binary, boot_mesh)
    item = named_mesh(document, trouser_mesh)
    additional_primitives = len(item.get("primitives", [])) - 1
    if additional_primitives and not preserve_additional_trouser_primitives:
        raise ValueError(
            f"Unexpected additional primitives on {trouser_mesh!r}")
    primitive = item["primitives"][0]
    arrays = {name: ea.accessor_array(document, binary, index)
              for name, index in primitive["attributes"].items()}
    expected = {"POSITION", "NORMAL", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0"}
    if set(arrays) != expected or primitive.get("targets"):
        raise ValueError(f"Unexpected trouser attributes: {sorted(arrays)}")
    weight_spec = document["accessors"][primitive["attributes"]["WEIGHTS_0"]]
    if weight_spec.get("normalized") and arrays["WEIGHTS_0"].dtype.kind in "ui":
        arrays["WEIGHTS_0"] = (arrays["WEIGHTS_0"].astype(np.float64)
                               / np.iinfo(arrays["WEIGHTS_0"].dtype).max)
    faces = ea.accessor_array(document, binary, primitive["indices"]).reshape(-1, 3)
    clipped, clipped_faces, clip_report = clip_above_cuff(
        arrays, faces, profiles, cap=cap,
        restrict_to_boot_interior=restrict_to_boot_interior)
    out_document = copy.deepcopy(document)
    out_binary = bytearray(binary)
    out_primitive = named_mesh(out_document, trouser_mesh)["primitives"][0]
    out_primitive["attributes"] = {
        "POSITION": append_accessor(out_document, out_binary,
                                     clipped["POSITION"].astype("<f4"),
                                     5126, "VEC3", bounds=True),
        "NORMAL": append_accessor(out_document, out_binary,
                                   clipped["NORMAL"].astype("<f4"),
                                   5126, "VEC3"),
        "TEXCOORD_0": append_accessor(out_document, out_binary,
                                       clipped["TEXCOORD_0"].astype("<f4"),
                                       5126, "VEC2"),
        "JOINTS_0": append_accessor(out_document, out_binary,
                                     clipped["JOINTS_0"].astype("<u2"),
                                     5123, "VEC4"),
        "WEIGHTS_0": append_accessor(out_document, out_binary,
                                      clipped["WEIGHTS_0"].astype("<f4"),
                                      5126, "VEC4"),
    }
    out_primitive["indices"] = append_accessor(
        out_document, out_binary, clipped_faces.reshape(-1).astype("<u4"),
        5125, "SCALAR")
    write_glb(out_document, bytes(out_binary), target)
    roundtrip, roundtrip_binary = ea.read_glb(target)
    revised_item = named_mesh(roundtrip, trouser_mesh)
    revised = revised_item["primitives"][0]
    if ea.accessor_array(roundtrip, roundtrip_binary,
                         revised["attributes"]["POSITION"]).shape != clipped["POSITION"].shape:
        raise ValueError("Candidate did not round-trip")
    if len(revised_item["primitives"]) != len(item["primitives"]):
        raise ValueError("Candidate changed the trouser primitive roster")
    profile_report = {}
    for side, value in profiles.items():
        profile_report[side] = {
            "rimVertices": len(value.points),
            "rawRimYRangeM": [float(value.raw_heights.min()),
                               float(value.raw_heights.max())],
            "smoothedRimYRangeM": [float(value.heights.min()),
                                    float(value.heights.max())],
        }
    return {
        "source": str(source), "sourceSHA256": digest(source),
        "bootSource": str(boot_source), "bootSourceSHA256": digest(boot_source),
        "output": str(target), "outputSHA256": digest(target),
        "trouserMesh": trouser_mesh, "bootMesh": boot_mesh,
        "targetPrimitiveIndex": 0,
        "preservedAdditionalPrimitives": additional_primitives,
        "drawsBefore": sum(len(value["primitives"]) for value in document["meshes"]),
        "drawsAfter": sum(len(value["primitives"]) for value in roundtrip["meshes"]),
        "materialsBefore": len(document.get("materials", [])),
        "materialsAfter": len(roundtrip.get("materials", [])),
        "jointsBefore": len(document["skins"][0]["joints"]),
        "jointsAfter": len(roundtrip["skins"][0]["joints"]),
        "profile": profile_report,
        "clip": clip_report,
    }


def _profile_report(profiles: dict[str, CuffProfile]) -> dict:
    result = {}
    for side, value in profiles.items():
        result[side] = {
            "measurement": value.measurement,
            "rimVertices": len(value.points),
            "rawRimYRangeM": [float(value.raw_heights.min()),
                               float(value.raw_heights.max())],
            "smoothedRimYRangeM": [float(value.heights.min()),
                                    float(value.heights.max())],
        }
    return result


def _clip_mesh_into_document(source_document: dict, source_binary: bytes,
                             output_document: dict, output_binary: bytearray,
                             mesh_name: str,
                             profiles: dict[str, CuffProfile], *,
                             keep_above: bool,
                             boundary_offset_m: float = 0.,
                             seal_cut: bool = False) -> dict:
    """Replace one primitive in an in-memory GLB copy with an audited clip.

    ``seal_cut`` closes the cut again in its own plane (see
    ``seal_cut_lining``); only a hidden generated lining may ask for it.
    """
    primitive = mesh(source_document, mesh_name)["primitives"][0]
    arrays = {name: ea.accessor_array(source_document, source_binary, index)
              for name, index in primitive["attributes"].items()}
    expected = {"POSITION", "NORMAL", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0"}
    if set(arrays) != expected or primitive.get("targets"):
        raise ValueError(f"Unexpected Ranger attributes on {mesh_name}: "
                         f"{sorted(arrays)}")
    weight_spec = source_document["accessors"][
        primitive["attributes"]["WEIGHTS_0"]]
    if weight_spec.get("normalized") and arrays["WEIGHTS_0"].dtype.kind in "ui":
        arrays["WEIGHTS_0"] = (arrays["WEIGHTS_0"].astype(np.float64)
                               / np.iinfo(arrays["WEIGHTS_0"].dtype).max)
    faces = ea.accessor_array(
        source_document, source_binary, primitive["indices"]).reshape(-1, 3)
    clipped, clipped_faces, clip_report = clip_above_cuff(
        arrays, faces, profiles, cap=False, keep_above=keep_above,
        boundary_offset_m=boundary_offset_m)
    if seal_cut:
        if not mesh_name.startswith("Generated"):
            raise ValueError(f"Only a hidden generated lining may be sealed: {mesh_name}")
        clipped, clipped_faces, clip_report["seal"] = seal_cut_lining(
            clipped, clipped_faces)
    out_primitive = mesh(output_document, mesh_name)["primitives"][0]
    out_primitive["attributes"] = {
        "POSITION": append_accessor(output_document, output_binary,
                                     clipped["POSITION"].astype("<f4"),
                                     5126, "VEC3", bounds=True),
        "NORMAL": append_accessor(output_document, output_binary,
                                   clipped["NORMAL"].astype("<f4"),
                                   5126, "VEC3"),
        "TEXCOORD_0": append_accessor(output_document, output_binary,
                                       clipped["TEXCOORD_0"].astype("<f4"),
                                       5126, "VEC2"),
        "JOINTS_0": append_accessor(output_document, output_binary,
                                     clipped["JOINTS_0"].astype("<u2"),
                                     5123, "VEC4"),
        "WEIGHTS_0": append_accessor(output_document, output_binary,
                                      clipped["WEIGHTS_0"].astype("<f4"),
                                      5126, "VEC4"),
    }
    out_primitive["indices"] = append_accessor(
        output_document, output_binary,
        clipped_faces.reshape(-1).astype("<u4"), 5125, "SCALAR")
    return clip_report


def _runtime_roster(document: dict) -> dict:
    return {
        "draws": sum(len(value["primitives"])
                     for value in document["meshes"]),
        "materials": len(document.get("materials", [])),
        "joints": len(document["skins"][0]["joints"]),
    }


def _ranger_boot_component_report(document: dict, binary: bytes,
                                  mesh_name: str,
                                  authority: dict) -> dict:
    primitive = mesh(document, mesh_name)["primitives"][0]
    points = ea.accessor_array(
        document, binary, primitive["attributes"]["POSITION"]).astype(float)
    faces = ea.accessor_array(document, binary,
                              primitive["indices"]).reshape(-1, 3)
    _, labels = component_labels(points, faces)
    main_labels = {int(value["componentLabel"])
                   for value in authority["sides"].values()}
    components = []
    for label in sorted(int(value) for value in np.unique(labels)):
        own = labels == label
        count = int(own.sum())
        low, high = float(points[own, 1].min()), float(points[own, 1].max())
        if label in main_labels:
            role = "main-leather-shell"
        elif high <= .05:
            role = "sole"
        elif count < 60 and low > .20:
            role = "pull-tab"
        else:
            role = "authored-strap"
        components.append({
            "label": label,
            "vertices": count,
            "yRangeM": [low, high],
            "role": role,
            "removed": False,
        })
    return {
        "componentCount": len(components),
        "components": components,
        "removedComponentLabels": [],
        "pruningRequired": False,
        "reason": ("all detached components are paired authored soles, straps "
                   "or pull tabs; none intrudes into the trouser cuff"),
    }


def ranger_cuffed_copies(legs_source: Path, boots_source: Path,
                         legs_target: Path, boots_target: Path) -> dict:
    """Author the Ranger's paired trousers/boots hand-off into review copies."""
    legs_document, legs_binary = ea.read_glb(legs_source)
    boots_document, boots_binary = ea.read_glb(boots_source)
    profiles, authority = ranger_cuff_profiles(
        boots_document, boots_binary, "Ankle Boots")

    out_legs = copy.deepcopy(legs_document)
    out_legs_binary = bytearray(legs_binary)
    legs_clips = {}
    for mesh_name in ("Sidelace Breeches", "GeneratedLegBackingWithBoots"):
        # The breeches keep an open cut hidden 3 mm inside the boot rim; the
        # paired lining is sealed in that plane so it stays a closed solid.
        legs_clips[mesh_name] = _clip_mesh_into_document(
            legs_document, legs_binary, out_legs, out_legs_binary,
            mesh_name, profiles, keep_above=True,
            seal_cut=mesh_name in SEALED_RANGER_LININGS)
    write_glb(out_legs, bytes(out_legs_binary), legs_target)

    out_boots = copy.deepcopy(boots_document)
    out_boots_binary = bytearray(boots_binary)
    # The paired backing fills to the authored boot rim.  The trousers end
    # 3 mm lower, yielding the hidden overlap; the visible Ankle Boots mesh is
    # copied byte-for-byte and none of its detached authored details is pruned.
    boots_clip = _clip_mesh_into_document(
        boots_document, boots_binary, out_boots, out_boots_binary,
        "GeneratedBootBackingWithLegs", profiles, keep_above=False,
        boundary_offset_m=HIDDEN_OVERLAP_M)
    write_glb(out_boots, bytes(out_boots_binary), boots_target)

    revised_legs, _ = ea.read_glb(legs_target)
    revised_boots, revised_boots_binary = ea.read_glb(boots_target)
    before_legs, after_legs = (_runtime_roster(legs_document),
                               _runtime_roster(revised_legs))
    before_boots, after_boots = (_runtime_roster(boots_document),
                                 _runtime_roster(revised_boots))
    if before_legs != after_legs or before_boots != after_boots:
        raise ValueError("Ranger cuff authoring changed a runtime roster")
    source_visible = semantic_mesh_contract(
        boots_document, boots_binary, "Ankle Boots")
    output_visible = semantic_mesh_contract(
        revised_boots, revised_boots_binary, "Ankle Boots")
    _require_semantic_contracts(
        {"Ankle Boots": output_visible}, {"Ankle Boots": source_visible},
        "Ranger visible boot")
    component_report = _ranger_boot_component_report(
        boots_document, boots_binary, "Ankle Boots", authority)
    return {
        "authority": authority,
        "profile": _profile_report(profiles),
        "legs": {
            "source": str(legs_source),
            "sourceSHA256": digest(legs_source),
            "output": str(legs_target),
            "outputSHA256": digest(legs_target),
            "runtimeRosterBefore": before_legs,
            "runtimeRosterAfter": after_legs,
            "clips": legs_clips,
        },
        "boots": {
            "source": str(boots_source),
            "sourceSHA256": digest(boots_source),
            "output": str(boots_target),
            "outputSHA256": digest(boots_target),
            "runtimeRosterBefore": before_boots,
            "runtimeRosterAfter": after_boots,
            "clip": boots_clip,
            "visibleMeshSource": source_visible,
            "visibleMeshOutput": output_visible,
            "componentDisposition": component_report,
        },
    }


def pruned_arcanist_boot_copy(source: Path, target: Path) -> dict:
    """Drop only the two detached, inverted shin-guard islands.

    They are separate 200+ vertex components floating above the actual boot
    rim.  The main left/right boot shells, small authored straps, both hidden
    backing meshes, materials, skin and all draws remain byte-for-byte in
    their source accessors.
    """
    document, binary = ea.read_glb(source)
    item = mesh(document, "Warded Boots")
    primitive = item["primitives"][0]
    arrays = {name: ea.accessor_array(document, binary, index)
              for name, index in primitive["attributes"].items()}
    points = arrays["POSITION"].astype(float)
    faces = ea.accessor_array(document, binary, primitive["indices"]).reshape(-1, 3)
    _, labels = component_labels(points, faces)
    removed_labels = []
    component_report = []
    for label in np.unique(labels):
        own = labels == label
        low, high = float(points[own, 1].min()), float(points[own, 1].max())
        remove = int(own.sum()) >= 200 and low > .20 and high > .40
        component_report.append({"label": int(label), "vertices": int(own.sum()),
                                 "yRangeM": [low, high], "removed": remove})
        if remove:
            removed_labels.append(int(label))
    if len(removed_labels) != 2:
        raise ValueError(f"Expected two detached Arcanist guards, got {removed_labels}")
    keep_faces = ~np.any(np.isin(labels[faces], removed_labels), axis=1)
    kept = faces[keep_faces]
    used = np.unique(kept)
    remap = np.full(len(points), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    kept = remap[kept].astype(np.uint32)
    out_document = copy.deepcopy(document)
    out_binary = bytearray(binary)
    out_primitive = mesh(out_document, "Warded Boots")["primitives"][0]
    out_attributes = {}
    for semantic, accessor_index in primitive["attributes"].items():
        spec = document["accessors"][accessor_index]
        out_attributes[semantic] = append_accessor(
            out_document, out_binary, arrays[semantic][used],
            int(spec["componentType"]), str(spec["type"]),
            bounds=semantic == "POSITION",
            normalized=bool(spec.get("normalized", False)))
    out_primitive["attributes"] = out_attributes
    out_primitive["indices"] = append_accessor(
        out_document, out_binary, kept.reshape(-1).astype("<u4"), 5125, "SCALAR")
    write_glb(out_document, bytes(out_binary), target)
    revised_document, revised_binary = ea.read_glb(target)
    revised_primitive = mesh(revised_document, "Warded Boots")["primitives"][0]
    revised_faces = ea.accessor_array(
        revised_document, revised_binary, revised_primitive["indices"]).reshape(-1, 3)
    revised_points = ea.accessor_array(
        revised_document, revised_binary,
        revised_primitive["attributes"]["POSITION"]).astype(float)
    face_points = revised_points[revised_faces]
    doubled_area = np.linalg.norm(np.cross(
        face_points[:, 1] - face_points[:, 0],
        face_points[:, 2] - face_points[:, 0]), axis=1)
    if np.any(doubled_area <= 1e-12):
        raise ValueError("Pruned Arcanist boot contains a degenerate triangle")
    return {
        "source": str(source), "sourceSHA256": digest(source),
        "output": str(target), "outputSHA256": digest(target),
        "mesh": "Warded Boots", "components": component_report,
        "removedComponentLabels": removed_labels,
        "sourceVertices": len(points), "outputVertices": len(revised_points),
        "sourceTriangles": len(faces), "outputTriangles": len(revised_faces),
        "drawsBefore": sum(len(value["primitives"]) for value in document["meshes"]),
        "drawsAfter": sum(len(value["primitives"]) for value in revised_document["meshes"]),
        "materialsBefore": len(document.get("materials", [])),
        "materialsAfter": len(revised_document.get("materials", [])),
        "jointsBefore": len(document["skins"][0]["joints"]),
        "jointsAfter": len(revised_document["skins"][0]["joints"]),
        "minimumTriangleAreaM2": float((.5 * doubled_area).min()),
        "degenerateTriangles": 0,
        "orientation": "source faces and winding retained exactly",
    }


def copy_external_resources(source: Path, target: Path) -> list[str]:
    document, _ = ea.read_glb(source)
    copied = []
    for image in document.get("images", []):
        if "uri" not in image:
            continue
        old = (source.parent / image["uri"]).resolve()
        new = (target.parent / image["uri"]).resolve()
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(old, new)
        copied.append(new.name)
    return copied


def validate_clip_contract(report: dict, contract: dict, *,
                           boot_interior: bool) -> None:
    overlap = np.asarray(report["clip"]["localHiddenOverlapMm"], dtype=float)
    selected = float(contract["selectedHiddenOverlapMm"])
    if not np.allclose(overlap, selected, atol=5e-5):
        raise ValueError(f"Hidden cuff overlap changed: {overlap.tolist()}")
    clip = report["clip"]
    boundary = clip["openBoundaryAudit"]
    if (clip["capTriangles"] != contract["capTriangles"]
            or not boundary["intentional"]
            or boundary["strandedClippedVertices"]
            or boundary["crossSideBoundaryEdges"]
            or boundary["maximumVertexDegree"] > 2):
        raise ValueError("Open hidden cuff boundary contract failed")
    if (clip["degenerateTriangles"] or clip["unsafeOrientationTriangles"]
            or clip["maximumInfluences"] > contract["maximumInfluences"]):
        raise ValueError("Cuff geometry safety contract failed")
    if not (report["drawsBefore"] == report["drawsAfter"]
            and report["materialsBefore"] == report["materialsAfter"]
            and report["jointsBefore"] == report["jointsAfter"]):
        raise ValueError("Cuff authoring changed a runtime roster")
    if boot_interior:
        inset = np.asarray(clip["radialHiddenInsetMm"], dtype=float)
        if (not clip["bootInteriorRestriction"]
                or not np.allclose(
                    inset, float(contract["arcanistRadialInsetMm"]), atol=5e-5)):
            raise ValueError("Arcanist boot-interior restriction changed")
    elif clip["bootInteriorRestriction"]:
        raise ValueError("Base wardrobe unexpectedly used a radial restriction")


def validate_ranger_contract(report: dict, contract: dict) -> None:
    for mesh_name, clip in report["legs"]["clips"].items():
        overlap = np.asarray(clip["localOverlapInsideBootRimMm"], dtype=float)
        boundary = clip["openBoundaryAudit"]
        if (not np.allclose(
                overlap, contract["selectedHiddenOverlapMm"], atol=5e-5)
                or clip["keptSide"] != "above"
                or clip["boundaryOffsetFromTrouserCutMm"] != 0.
                or clip["capTriangles"] != contract["capTriangles"]
                or not boundary["intentional"]
                or boundary["strandedClippedVertices"]
                or boundary["crossSideBoundaryEdges"]
                or boundary["maximumVertexDegree"] > 2
                or clip["degenerateTriangles"]
                or clip["unsafeOrientationTriangles"]
                or clip["maximumInfluences"] > contract["maximumInfluences"]):
            raise ValueError(f"Ranger leg cuff contract failed on {mesh_name}")
        seal = clip.get("seal")
        if mesh_name in SEALED_RANGER_LININGS:
            if (seal is None
                    or seal["openEdgesAfterSeal"]
                    or seal["degenerateTriangles"]
                    or seal["capTriangles"] != seal["boundaryEdges"]
                    or seal["boundaryEdges"] != boundary["boundaryEdges"]
                    or seal["maximumWeightSumError"] > 1e-5):
                raise ValueError(f"Ranger lining seal contract failed on {mesh_name}")
        elif seal is not None:
            raise ValueError(f"Visible Ranger legwear must keep its open cut: {mesh_name}")
    boot_clip = report["boots"]["clip"]
    boundary = boot_clip["openBoundaryAudit"]
    if (not np.allclose(
            boot_clip["localOverlapInsideBootRimMm"], 0., atol=5e-5)
            or boot_clip["keptSide"] != "below"
            or not math.isclose(
                boot_clip["boundaryOffsetFromTrouserCutMm"],
                contract["selectedHiddenOverlapMm"])
            or boot_clip["capTriangles"] != contract["capTriangles"]
            or not boundary["intentional"]
            or boundary["strandedClippedVertices"]
            or boundary["crossSideBoundaryEdges"]
            or boundary["maximumVertexDegree"] > 2
            or boot_clip["degenerateTriangles"]
            or boot_clip["unsafeOrientationTriangles"]
            or boot_clip["maximumInfluences"] > contract["maximumInfluences"]):
        raise ValueError("Ranger boot backing cuff contract failed")
    if (report["legs"]["runtimeRosterBefore"]
            != report["legs"]["runtimeRosterAfter"]
            or report["boots"]["runtimeRosterBefore"]
            != report["boots"]["runtimeRosterAfter"]):
        raise ValueError("Ranger cuff changed a runtime roster")
    disposition = report["boots"]["componentDisposition"]
    if (disposition["pruningRequired"]
            or disposition["removedComponentLabels"]):
        raise ValueError("Ranger boot unexpectedly requires component pruning")


def validate_reviewed_outputs(body_validation: dict, body_target: Path,
                              arcanist_target: Path,
                              arcanist_boot_target: Path,
                              ranger_legs_target: Path,
                              ranger_boots_target: Path,
                              manifest: dict) -> dict:
    reviewed = manifest["reviewedOutputs"]
    body_surfaces = semantic_mesh_contracts(
        body_target, reviewed["body"]["semanticMeshes"])
    _require_semantic_contracts(
        body_surfaces, reviewed["body"]["semanticMeshes"], "Authored body")
    exact_reference = (
        body_validation["sha256"] == reviewed["body"]["sourceSHA256"])
    if (exact_reference
            and digest(body_target) != reviewed["body"]["outputSHA256"]):
        raise ValueError("Pinned body input no longer produces reviewed bytes")
    legs_spec = reviewed["arcanistLegs"]
    legs_surfaces = semantic_mesh_contracts(
        arcanist_target, {"Warded Legguards": legs_spec["semanticMesh"]})
    _require_semantic_contracts(
        legs_surfaces, {"Warded Legguards": legs_spec["semanticMesh"]},
        "Authored Arcanist legs")
    if digest(arcanist_target) != legs_spec["outputSHA256"]:
        raise ValueError("Arcanist leg input no longer produces reviewed bytes")
    boots_spec = reviewed["arcanistBoots"]
    boots_surfaces = semantic_mesh_contracts(
        arcanist_boot_target, {"Warded Boots": boots_spec["semanticMesh"]})
    _require_semantic_contracts(
        boots_surfaces, {"Warded Boots": boots_spec["semanticMesh"]},
        "Authored Arcanist boots")
    if digest(arcanist_boot_target) != boots_spec["outputSHA256"]:
        raise ValueError("Arcanist boot input no longer produces reviewed bytes")
    ranger_legs_spec = reviewed["rangerLegs"]
    ranger_legs_surfaces = semantic_mesh_contracts(
        ranger_legs_target, ranger_legs_spec["semanticMeshes"])
    _require_semantic_contracts(
        ranger_legs_surfaces, ranger_legs_spec["semanticMeshes"],
        "Authored Ranger legs")
    if digest(ranger_legs_target) != ranger_legs_spec["outputSHA256"]:
        raise ValueError("Ranger leg input no longer produces reviewed bytes")
    ranger_boots_spec = reviewed["rangerBoots"]
    ranger_boots_surfaces = semantic_mesh_contracts(
        ranger_boots_target, ranger_boots_spec["semanticMeshes"])
    _require_semantic_contracts(
        ranger_boots_surfaces, ranger_boots_spec["semanticMeshes"],
        "Authored Ranger boots")
    if digest(ranger_boots_target) != ranger_boots_spec["outputSHA256"]:
        raise ValueError("Ranger boot input no longer produces reviewed bytes")
    return {
        "bodyExactReviewedBytes": exact_reference,
        "bodySemanticMeshes": body_surfaces,
        "arcanistLegSemanticMeshes": legs_surfaces,
        "arcanistBootSemanticMeshes": boots_surfaces,
        "rangerLegSemanticMeshes": ranger_legs_surfaces,
        "rangerBootSemanticMeshes": ranger_boots_surfaces,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--body", type=Path, required=True)
    body_identity = parser.add_mutually_exclusive_group()
    body_identity.add_argument("--expected-body-sha256")
    body_identity.add_argument("--body-provenance", type=Path)
    parser.add_argument("--components", type=Path, required=True)
    parser.add_argument("--arcanist-legs", type=Path, required=True)
    parser.add_argument("--arcanist-boots", type=Path, required=True)
    parser.add_argument("--ranger-legs", type=Path, required=True)
    parser.add_argument("--ranger-boots", type=Path, required=True)
    parser.add_argument("--equipment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--resource-prefix", default="res://test-artifacts/luminous-cuff-fit",
        help="Godot res:// prefix corresponding to --output for preview configs")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    manifest = load_manifest(manifest_path)
    contract = manifest["contract"]
    if (not math.isclose(
            HIDDEN_OVERLAP_M * 1000., contract["selectedHiddenOverlapMm"])
            or not math.isclose(
                RADIAL_INSET_M * 1000., contract["arcanistRadialInsetMm"])):
        raise ValueError("Tool constants no longer match the pinned cuff manifest")
    body_source = args.body.resolve()
    components_source = args.components.resolve()
    arcanist_legs_source = args.arcanist_legs.resolve()
    arcanist_boots_source = args.arcanist_boots.resolve()
    ranger_legs_source = args.ranger_legs.resolve()
    ranger_boots_source = args.ranger_boots.resolve()
    equipment_source_path = args.equipment.resolve()
    body_validation = validate_body_source(
        body_source, manifest["inputs"]["body"],
        expected_sha256=args.expected_body_sha256,
        provenance_path=(args.body_provenance.resolve()
                         if args.body_provenance else None))
    authority_validation = authority_report(
        components_source, manifest["authority"])
    legs_validation = validate_pinned_source(
        arcanist_legs_source, manifest["inputs"]["arcanistLegs"],
        "Arcanist legs")
    boots_validation = validate_pinned_source(
        arcanist_boots_source, manifest["inputs"]["arcanistBoots"],
        "Arcanist boots")
    ranger_legs_validation = validate_pinned_asset(
        ranger_legs_source, manifest["inputs"]["rangerLegs"],
        "Ranger legs")
    ranger_boots_validation = validate_pinned_asset(
        ranger_boots_source, manifest["inputs"]["rangerBoots"],
        "Ranger boots")
    equipment_validation = validate_equipment_config(
        equipment_source_path, manifest["inputs"]["equipmentConfig"])
    output = validate_output_path(args.output)
    resource_prefix = args.resource_prefix.rstrip("/")
    if (not resource_prefix.startswith("res://")
            or ".." in resource_prefix.split("/")):
        raise ValueError(f"Unsafe Godot resource prefix: {resource_prefix}")
    body_target = output / "races/luminous_female.glb"
    arcanist_target = output / "equipment/variants/luminous_female/arcane_leg_armor_01.glb"
    arcanist_boot_target = output / "equipment/variants/luminous_female/arcane_fantasy_boots_01.glb"
    ranger_legs_target = output / "equipment/variants/luminous_female/rugged_ranger_legwear_04.glb"
    ranger_boots_target = output / "equipment/variants/luminous_female/frontier_boots_01.glb"
    # The 3 mm tuck is fully enclosed by the authored 360-degree boot cuff.
    # Keep the clipped trouser shell open: an added closure disc creates a
    # second surface inside the hollow boot and can show as dark rim wedges
    # under double-sided rendering.  The report audits the open boundary.
    body_report = clipped_copy(body_source, body_target,
                               "wardrobe_pants", body_source,
                               "wardrobe_boots", cap=False)
    arcanist_legs_report = clipped_copy(
        arcanist_legs_source, arcanist_target, "Warded Legguards",
        arcanist_boots_source, "Warded Boots",
        restrict_to_boot_interior=True)
    arcanist_legs_report["copiedExternalResources"] = copy_external_resources(
        arcanist_legs_source, arcanist_target)
    arcanist_boot_report = pruned_arcanist_boot_copy(
        arcanist_boots_source, arcanist_boot_target)
    arcanist_boot_report["copiedExternalResources"] = copy_external_resources(
        arcanist_boots_source, arcanist_boot_target)
    ranger_report = ranger_cuffed_copies(
        ranger_legs_source, ranger_boots_source,
        ranger_legs_target, ranger_boots_target)
    ranger_report["legs"]["copiedExternalResources"] = copy_external_resources(
        ranger_legs_source, ranger_legs_target)
    ranger_report["boots"]["copiedExternalResources"] = copy_external_resources(
        ranger_boots_source, ranger_boots_target)
    validate_clip_contract(body_report, contract, boot_interior=False)
    validate_clip_contract(arcanist_legs_report, contract, boot_interior=True)
    validate_ranger_contract(ranger_report, contract)
    if (arcanist_boot_report["degenerateTriangles"]
            or arcanist_boot_report["drawsBefore"]
            != arcanist_boot_report["drawsAfter"]
            or arcanist_boot_report["materialsBefore"]
            != arcanist_boot_report["materialsAfter"]
            or arcanist_boot_report["jointsBefore"]
            != arcanist_boot_report["jointsAfter"]
            or arcanist_boot_report["removedComponentLabels"]
            != manifest["reviewedOutputs"]["arcanistBoots"][
                "removedComponentLabels"]):
        raise ValueError("Arcanist boot prune contract failed")
    reviewed_outputs = validate_reviewed_outputs(
        body_validation, body_target, arcanist_target,
        arcanist_boot_target, ranger_legs_target,
        ranger_boots_target, manifest)
    equipment_source = json.loads(
        equipment_source_path.read_text(encoding="utf-8"))
    equipment = copy.deepcopy(equipment_source)
    equipment["models"]["4:179"]["variants"]["canonical_luminous_female"]["scene"] = (
        resource_prefix
        + "/equipment/variants/luminous_female/arcane_leg_armor_01.glb")
    equipment["models"]["6:192"]["variants"]["canonical_luminous_female"]["scene"] = (
        resource_prefix
        + "/equipment/variants/luminous_female/arcane_fantasy_boots_01.glb")
    equipment["models"]["4:230"]["variants"]["canonical_luminous_female"]["scene"] = (
        resource_prefix
        + "/equipment/variants/luminous_female/rugged_ranger_legwear_04.glb")
    equipment["models"]["6:224"]["variants"]["canonical_luminous_female"]["scene"] = (
        resource_prefix
        + "/equipment/variants/luminous_female/frontier_boots_01.glb")
    equipment_target = output / "equipment.json"
    equipment_target.write_text(json.dumps(equipment, indent=2) + "\n", encoding="utf-8")
    # Matched visual control: retain the production legwear and substitute
    # only the reviewed boot-shell repair.  This separates authored boot
    # silhouette details from anything introduced by the trouser cuff cut.
    control_equipment = copy.deepcopy(equipment_source)
    control_equipment["models"]["6:192"]["variants"]["canonical_luminous_female"]["scene"] = (
        resource_prefix
        + "/equipment/variants/luminous_female/arcane_fantasy_boots_01.glb")
    control_equipment_target = output / "control-original-legs-pruned-boots-equipment.json"
    control_equipment_target.write_text(
        json.dumps(control_equipment, indent=2) + "\n", encoding="utf-8")
    ranger_original_legs_control = copy.deepcopy(equipment_source)
    ranger_original_legs_control["models"]["6:224"]["variants"][
        "canonical_luminous_female"]["scene"] = (
            resource_prefix
            + "/equipment/variants/luminous_female/frontier_boots_01.glb")
    ranger_original_legs_control_target = (
        output / "control-ranger-original-legs-authored-boots-equipment.json")
    ranger_original_legs_control_target.write_text(
        json.dumps(ranger_original_legs_control, indent=2) + "\n",
        encoding="utf-8")
    ranger_original_boots_control = copy.deepcopy(equipment_source)
    ranger_original_boots_control["models"]["4:230"]["variants"][
        "canonical_luminous_female"]["scene"] = (
            resource_prefix
            + "/equipment/variants/luminous_female/rugged_ranger_legwear_04.glb")
    ranger_original_boots_control_target = (
        output / "control-ranger-authored-legs-original-boots-equipment.json")
    ranger_original_boots_control_target.write_text(
        json.dumps(ranger_original_boots_control, indent=2) + "\n",
        encoding="utf-8")
    report = {
        "schema": "eloria-luminous-cuff-fit-review-v1",
        "status": "reviewed-authoring-output-production-install-deferred",
        "manifest": str(manifest_path),
        "manifestSHA256": digest(manifest_path),
        "resourcePrefix": resource_prefix,
        "authority": authority_validation,
        "validatedInputs": {
            "body": body_validation,
            "arcanistLegs": legs_validation,
            "arcanistBoots": boots_validation,
            "rangerLegs": ranger_legs_validation,
            "rangerBoots": ranger_boots_validation,
            "equipmentConfig": equipment_validation,
        },
        "body": body_report,
        "arcanist": {
            "legs": arcanist_legs_report,
            "boots": arcanist_boot_report,
            "preservedMeshes": ["ReconstructedInseams", "GeneratedLegBacking",
                                 "GeneratedLegBackingWithBoots",
                                 "GeneratedBootBacking",
                                 "GeneratedBootBackingWithLegs"],
        },
        "ranger": ranger_report,
        "equipmentConfig": str(equipment_target),
        "equipmentConfigSHA256": digest(equipment_target),
        "matchedControlEquipmentConfig": str(control_equipment_target),
        "matchedControlEquipmentConfigSHA256": digest(control_equipment_target),
        "rangerOriginalLegsControlEquipmentConfig": str(
            ranger_original_legs_control_target),
        "rangerOriginalLegsControlEquipmentConfigSHA256": digest(
            ranger_original_legs_control_target),
        "rangerOriginalBootsControlEquipmentConfig": str(
            ranger_original_boots_control_target),
        "rangerOriginalBootsControlEquipmentConfigSHA256": digest(
            ranger_original_boots_control_target),
        "reviewedOutputValidation": reviewed_outputs,
        "runtimeCost": {
            "additionalDraws": contract["additionalDraws"],
            "additionalMaterials": contract["additionalMaterials"],
            "additionalBones": contract["additionalBones"],
            "perFrameOperations": contract["perFrameOperations"],
        },
    }
    report_target = output / "report.json"
    report_target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "report": str(report_target),
                      "bodySHA256": digest(body_target),
                      "arcanistLegsSHA256": digest(arcanist_target),
                      "arcanistBootsSHA256": digest(arcanist_boot_target),
                      "rangerLegsSHA256": digest(ranger_legs_target),
                      "rangerBootsSHA256": digest(ranger_boots_target)}, indent=2))


if __name__ == "__main__":
    main()
