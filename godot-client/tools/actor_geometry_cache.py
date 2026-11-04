"""Cook package-time actor geometry (actor LODs) and keep its catalogue.

The runtime applier (src/actors/actor_geometry.gd) attaches LOD index chains
from per-file sidecars to the raw parse of an actor glTF. This driver decides
which actor files need (re)cooking, runs the headless Godot cook
(tools/actor_geometry/cook.gd, which parses each file exactly as the runtime
does and applies tools/actor_geometry/lod_policy.gd) in batches, and writes
the catalogue the applier reads. Docs: godot-client/docs/actor-geometry-lods.md.

  plan     list the actor glTFs in scope and say which need cooking
  cook     cook what changed and rewrite <out>/<policy>/catalog.json
  verify   apply every catalogued sidecar with the runtime applier to a fresh
           parse (and check the levels the RenderingServer holds)
  report   coverage, bytes, cook time and lining masks from the cook summary
  compare  byte-compare two catalogue roots (determinism)
  predict  drawn triangles a crowd triangle census would have with the chains

Scope: tracked .glb/.gltf files under godot-client/assets/actors/native/,
except rl_heads/ (authored LODs) and retired models. Default output:
<repository>/.local/actor-geometry/ (Git-ignored): the catalogue root
rl-actor-geometry-v1/ (catalog.json, blobs/) and the driver state cook/
(summary.json, per-run jobs, logs and an isolated Godot profile).

Lining masks (actor LODs C4): a garment whose glTF has Generated* lining
meshes is cooked with its mask file <masks>/<variant>/<stem>.lining.json
(eloria-assets/tools/lining_visibility.py; default <out>/lining-masks/) when
the mask is bound to the garment's exact bytes and meets MASK_GATE; the
headless lining stage (tools/actor_geometry/lining_policy.gd) then drops the
lining triangles the mask proves hidden. A garment without a usable mask
cooks as before and is reported (`mask_status`).

Race-refit budget (actor LODs C11): a race refit of a rigid socket model
(data/actors/equipment.json: a non-skinned model's canonical_<race>_<sex>
variant; in practice the helmets) is cooked with its Human source's triangle
count (the model's canonical_human_<sex> variant, read from the glTF JSON);
the headless budget stage (tools/actor_geometry/budget_policy.gd) caps a refit
drawing more than twice that with a simplified base. `--no-budget` cooks
without it.

A file is reused while its bytes, the external buffers it reads (a .gltf's
.bin), its model scale, its lining mask (and MASK_GATE), its budget reference
(the Human source's bytes and triangles) and the policy digest (engine build +
cook.gd + lod_policy.gd + lining_policy.gd + budget_policy.gd +
actor_geometry_format.gd) are unchanged and its sidecar is intact. This
cooks the source checkout (a developer root); cooking a package's build tree
is release packaging's job. Every Godot process runs headless with
an isolated APPDATA/LOCALAPPDATA; --wrapper prefixes each Godot command (for
example a machine-wide slot lock). cook and verify hold an OS lock on
<out>/cook/driver.lock, so a second driver on the same output folder stops
instead of collecting the first one's blobs.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import time
import urllib.parse

SCHEMA = 1
POLICY = "rl-actor-geometry-v1"
SOURCE_ROOT = "assets/actors/native/"
EXCLUDED_ROOTS = ("assets/actors/native/rl_heads/",)
GLTF_SUFFIXES = (".glb", ".gltf")
COOK_SCRIPT = "res://tools/actor_geometry/cook.gd"
POLICY_FILES = ("tools/actor_geometry/cook.gd", "tools/actor_geometry/lod_policy.gd",
                "tools/actor_geometry/lining_policy.gd", "tools/actor_geometry/budget_policy.gd",
                "src/actors/actor_geometry_format.gd")
RETIRED_INDEX = "data/assets/retired_procedural_models.json"
MODELS = "data/actors/models.json"
EQUIPMENT = "data/actors/equipment.json"
CATALOG_FILE = "catalog.json"
# "file": the runtime hashes each actor file against its entry at first parse
# (a developer root; about 4 ms per MB, so 0.2 s for a 57 MB creature);
# "parsed": the parsed index digests alone bind a sidecar (a root installed and
# verified together with the actor files).
SOURCE_CHECKS = ("file", "parsed")
DEFAULT_SOURCE_CHECK = "file"
BLOB_FOLDER = "blobs"
STATE_FOLDER = "cook"
SUMMARY_FILE = "summary.json"
LOCK_FILE = "driver.lock"
GLB_MAGIC = b"glTF"
GLB_JSON_CHUNK = 0x4E4F534A
DEFAULT_BATCH = 250
DEFAULT_TIMEOUT_SECONDS = 1200.0
DEFAULT_SLOT_WAIT_SECONDS = 4 * 60 * 60.0
MAX_JOBS = 4
# Per-run job folders (jobs, reports, Godot logs) kept under <out>/cook/jobs.
KEEP_RUNS = 8
ENGINE_PATTERN = re.compile(r"^\d+\.\d+\.\d+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+(\.[0-9a-f]{9})?$")
BLOB_PATTERN = re.compile(r"^[0-9a-f]{64}\.rlgeo$")
LOG_PREFIX = "actor geometry cook: "
# Godot prints engine errors as "ERROR: ..." and GDScript failures as
# "SCRIPT ERROR: ...". A script error makes the batch's results untrusted.
ERROR_LINE = re.compile(r"^(SCRIPT ERROR|ERROR):")
SCRIPT_ERROR_LINE = re.compile(r"^SCRIPT ERROR:|Parse Error")
# Projection.get_lod_multiplier() of the gameplay camera: 2 tan(hfov / 2).
DEFAULT_VFOV_DEGREES = 50.0
# Lining masks (lining_visibility.py output) and the lining stage's input.
MASK_SCHEMA = 1
MASK_POLICY = "rl-lining-visibility-v1"
MASK_FOLDER = "lining-masks"
MASK_SUFFIX = ".lining.json"
LINING_PREFIX = "Generated"
LINING_INPUT_SCHEMA = 1
LINING_INPUT_KEYS = ("mesh", "primitive", "triangles", "keep", "check")
# The least a mask must prove before the cook drops lining faces with it: the
# 2 cm surface margin (the lossless default measured in C3: 43 changed 3 mm
# pixels over 7,200 unsampled views), the full 128-direction sphere and the
# 44-pose set v1 (cheaper casts open visible holes).
MASK_GATE = {"min_margin_m": 0.02, "margin_rule": "surface", "min_directions": 128, "min_poses": 44}
MASK_STATUSES = ("ok", "partial", "missing", "stale", "gate", "invalid")
# Summary row fields that describe a file's lining mask.
MASK_FIELDS = ("mask_status", "mask_reason", "mask_sha256", "lining_key", "mask_removable")
# Race-refit budget (budget_policy.gd's input): equipment.json variant keys of
# a race and sex; the Human variant of the same sex is the source.
BUDGET_INPUT_SCHEMA = 1
BUDGET_VARIANT = re.compile(r"^canonical_([a-z0-9]+)_(male|female)$")
HUMAN_RACE = "human"
# BudgetPolicy.MAX_RATIO (budget_policy.gd decides; `plan` only counts the
# refits above it).
BUDGET_RATIO = 2.0
# Summary row fields that describe a file's budget reference.
BUDGET_FIELDS = ("budget_key", "budget_reference", "budget_reference_triangles", "budget_status")
# Statuses of a surface row's `budget` that mean the stage reduced its base.
BUDGET_REDUCED = ("capped", "partial")


class CookError(RuntimeError):
    pass


# --- scope ------------------------------------------------------------------

def project_path(project: Path) -> Path:
    project = Path(project).resolve()
    if not (project / "project.godot").is_file():
        raise CookError(f"No project.godot in {project}; pass the Godot project directory")
    return project


def default_out(project: Path) -> Path:
    return project.parent / ".local" / "actor-geometry"


def default_masks(out: Path) -> Path:
    """lining_visibility.py writes <client repo>/.local/actor-geometry/lining-masks/
    by default, i.e. <default out>/lining-masks."""
    return Path(out) / MASK_FOLDER


def in_scope(relative: str) -> bool:
    """Mirror of ActorGeometryFormat.in_scope for a project-relative path."""
    if not isinstance(relative, str) or not relative.startswith(SOURCE_ROOT) or "\\" in relative:
        return False
    parts = PurePosixPath(relative).parts
    if ".." in parts or "." in parts or relative != PurePosixPath(relative).as_posix():
        return False
    if any(relative.startswith(root) for root in EXCLUDED_ROOTS):
        return False
    return relative.lower().endswith(GLTF_SUFFIXES)


def logical(relative: str) -> str:
    return "res://" + relative


def relative_of(logical_path: str) -> str:
    if not logical_path.startswith("res://"):
        raise CookError(f"Not a res:// path: {logical_path}")
    return logical_path[len("res://"):]


def _git_tracked(project: Path) -> list[str] | None:
    try:
        result = subprocess.run(["git", "-C", str(project), "ls-files", "-z", "--", SOURCE_ROOT],
                                capture_output=True, check=False)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def retired_paths(project: Path) -> set[str]:
    path = project / RETIRED_INDEX
    if not path.is_file():
        return set()
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    return {"assets/" + item for item in document.get("runtimePaths", []) if isinstance(item, str)}


def scope_files(project: Path, *, tracked_only: bool = True) -> list[str]:
    """Project-relative actor glTFs the cook covers, sorted."""
    tracked = _git_tracked(project) if tracked_only else None
    if tracked is None:
        base = project / SOURCE_ROOT
        tracked = [path.relative_to(project).as_posix() for path in base.rglob("*") if path.is_file()]
    retired = retired_paths(project)
    return sorted({item for item in tracked if in_scope(item) and item not in retired
                   and (project / item).is_file()})


def model_scales(project: Path) -> dict[str, float]:
    """res:// scene -> the smallest catalogue import scale it is drawn at."""
    path = project / MODELS
    if not path.is_file():
        return {}
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    scales: dict[str, float] = {}
    for model in (document.get("models") or {}).values():
        if not isinstance(model, dict) or not isinstance(model.get("scene"), str):
            continue
        scale = (model.get("import") or {}).get("scale", 1.0)
        if not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0:
            continue
        scene = model["scene"]
        scales[scene] = min(float(scale), scales.get(scene, float(scale)))
    return scales


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def gltf_document(path: Path) -> dict | None:
    """The JSON document of a .gltf or .glb (the GLB's JSON chunk only), or
    None when it cannot be read."""
    try:
        if path.suffix.lower() == ".gltf":
            text = path.read_bytes()
        else:
            with path.open("rb") as stream:
                header = stream.read(20)
                if len(header) < 20 or header[:4] != GLB_MAGIC:
                    return None
                length, kind = struct.unpack_from("<II", header, 12)
                if kind != GLB_JSON_CHUNK:
                    return None
                text = stream.read(length)
        document = json.loads(text.decode("utf-8-sig"))
    except (OSError, ValueError, UnicodeDecodeError, struct.error):
        return None
    return document if isinstance(document, dict) else None


def external_buffers(path: Path) -> list[str]:
    """URIs of the external (not data:) buffers a .gltf or .glb reads, in
    document order; [] when it has none or its JSON cannot be read (the
    cook then reports the parse)."""
    document = gltf_document(path)
    buffers = document.get("buffers") if isinstance(document, dict) else None
    uris = []
    for buffer in buffers if isinstance(buffers, list) else []:
        uri = buffer.get("uri") if isinstance(buffer, dict) else None
        if isinstance(uri, str) and uri and not uri.startswith("data:"):
            uris.append(uri)
    return uris


def dependencies_sha256(path: Path) -> str:
    """SHA-256 over the external buffers a glTF reads ("" when it reads none):
    geometry its own file hash does not cover (Superhero_*_FullBody.gltf/.bin)."""
    uris = external_buffers(path)
    if not uris:
        return ""
    digest = hashlib.sha256()
    for uri in uris:
        target = path.parent / urllib.parse.unquote(uri)
        digest.update(uri.encode("utf-8") + b"\0")
        digest.update((sha256_file(target) if target.is_file() else "missing").encode("ascii") + b"\n")
    return digest.hexdigest()


def file_records(project: Path, relatives: list[str], masks: Path | None = None,
                 budget: bool = True) -> list[dict]:
    """One job record per file. With `masks` (a lining mask folder), a garment
    with Generated* linings also gets `mask_status` and, when its mask is
    usable, the lining stage's input (`lining`, `mask_sha256`, `lining_key`).
    With `budget`, a race refit of a rigid socket model also gets the budget
    stage's input (`budget`, `budget_key`, `budget_reference`, ...)."""
    scales = model_scales(project)
    sources = budget_sources(project) if budget else {}
    references: dict[str, dict | None] = {}
    records = []
    for relative in relatives:
        path = project / relative
        key = logical(relative)
        record = {"path": key, "file_sha256": sha256_file(path), "bytes": path.stat().st_size,
                  "model_scale": float(scales.get(key, 1.0))}
        dependencies = dependencies_sha256(path)
        if dependencies:
            record["dependencies_sha256"] = dependencies
        if masks is not None:
            record.update(lining_fields(path, relative, record["file_sha256"], masks))
        if key in sources:
            record.update(budget_fields(project, sources[key], references))
        records.append(record)
    return records


# --- lining masks -------------------------------------------------------------------

def lining_primitives(document: dict | None) -> list[dict]:
    """[{mesh, primitive, triangles}] of the Generated* lining triangle
    primitives of a glTF document, in mesh order."""
    linings = []
    if not isinstance(document, dict):
        return linings
    accessors = document.get("accessors") if isinstance(document.get("accessors"), list) else []
    for mesh in document.get("meshes") if isinstance(document.get("meshes"), list) else []:
        name = mesh.get("name", "") if isinstance(mesh, dict) else ""
        if not isinstance(name, str) or not name.startswith(LINING_PREFIX):
            continue
        for index, primitive in enumerate(mesh.get("primitives") or []):
            if not isinstance(primitive, dict) or primitive.get("mode", 4) != 4:
                continue
            linings.append({"mesh": name, "primitive": index, "triangles": _primitive_triangles(accessors, primitive)})
    return linings


def _primitive_triangles(accessors: list, primitive: dict) -> int:
    """Triangles of one triangle-list primitive: its index count (or, without
    indices, its POSITION count) / 3."""
    accessor = primitive.get("indices")
    if accessor is None:
        accessor = (primitive.get("attributes") or {}).get("POSITION")
    count = accessors[accessor].get("count", 0) if isinstance(accessor, int) and 0 <= accessor < len(accessors) \
        and isinstance(accessors[accessor], dict) else 0
    return int(count) // 3 if isinstance(count, int) and not isinstance(count, bool) and count > 0 else 0


def gltf_triangles(document: dict | None) -> int:
    """Triangles of every triangle-list primitive of a glTF document (the
    runtime parse keeps each one), 0 when it has none or cannot be read."""
    if not isinstance(document, dict):
        return 0
    accessors = document.get("accessors") if isinstance(document.get("accessors"), list) else []
    total = 0
    for mesh in document.get("meshes") if isinstance(document.get("meshes"), list) else []:
        for primitive in (mesh.get("primitives") or []) if isinstance(mesh, dict) else []:
            if isinstance(primitive, dict) and primitive.get("mode", 4) == 4:
                total += _primitive_triangles(accessors, primitive)
    return total


def mask_path(masks: Path, relative: str) -> Path:
    """lining_visibility.py's mask file for a garment: <masks>/<variant>/<stem>.lining.json."""
    item = PurePosixPath(relative)
    return Path(masks) / item.parent.name / (item.stem + MASK_SUFFIX)


def _mask_bits(text, count: int) -> int | None:
    """A mask's base64 little-endian bitset as an int (bit i = triangle i), or
    None unless it holds exactly `count` bits."""
    if not isinstance(text, str) or count <= 0:
        return None
    try:
        raw = base64.b64decode(text.encode("ascii"), validate=True)
    except (ValueError, binascii.Error, UnicodeEncodeError):
        return None
    if len(raw) != (count + 7) // 8:
        return None
    value = int.from_bytes(raw, "little")
    return None if value >> count else value


def _check_rows(rows, triangles: int) -> bool:
    if not isinstance(rows, list) or not rows:
        return False
    for row in rows:
        if not isinstance(row, list) or len(row) != 4 or not isinstance(row[0], int) or isinstance(row[0], bool) \
                or not 0 <= row[0] < triangles:
            return False
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                   for value in row[1:]):
            return False
    return True


def read_mask(path: Path, logical_path: str, file_sha256: str, linings: list[dict]) -> dict:
    """Validates one mask file against its garment. Returns {status, reason?,
    input?, mask_sha256?, removable?}: status ok / partial (some linings have
    no mask entry) with the lining stage's input, or missing / stale (cast for
    other bytes) / gate (below MASK_GATE) / invalid without one."""
    if not path.is_file():
        return {"status": "missing"}
    try:
        data = path.read_bytes()
    except OSError as exc:
        # lining_visibility.py rewrites masks in place; a file it holds open
        # (or one that just vanished) cooks without a mask this time.
        return {"status": "invalid", "reason": f"read: {exc.__class__.__name__}"}
    digest = hashlib.sha256(data).hexdigest()
    try:
        mask = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"status": "invalid", "reason": "json", "mask_sha256": digest}
    if not isinstance(mask, dict) or mask.get("schema") != MASK_SCHEMA or mask.get("policy") != MASK_POLICY:
        return {"status": "invalid", "reason": "schema", "mask_sha256": digest}
    source = mask.get("source") if isinstance(mask.get("source"), dict) else {}
    if source.get("path") != logical_path:
        return {"status": "invalid", "reason": "path", "mask_sha256": digest}
    if source.get("sha256") != file_sha256:
        return {"status": "stale", "reason": "source sha256", "mask_sha256": digest}
    margin = mask.get("margin_m")
    if mask.get("margin_rule") != MASK_GATE["margin_rule"] or not isinstance(margin, (int, float)) \
            or isinstance(margin, bool) or not math.isfinite(margin) or margin < MASK_GATE["min_margin_m"] - 1e-9:
        return {"status": "gate", "reason": f"margin {mask.get('margin_rule')} {margin}", "mask_sha256": digest}
    directions = (mask.get("settings") or {}).get("directions") if isinstance(mask.get("settings"), dict) else None
    if not isinstance(directions, int) or directions < MASK_GATE["min_directions"]:
        return {"status": "gate", "reason": f"directions {directions}", "mask_sha256": digest}
    poses = mask.get("poses")
    if not isinstance(poses, list) or len(poses) < MASK_GATE["min_poses"]:
        return {"status": "gate", "reason": f"poses {len(poses) if isinstance(poses, list) else poses}",
                "mask_sha256": digest}
    entries = mask.get("linings") if isinstance(mask.get("linings"), dict) else None
    if not entries:
        return {"status": "invalid", "reason": "linings", "mask_sha256": digest}
    expected = {(item["mesh"], item["primitive"]): item["triangles"] for item in linings}
    found = []
    seen = set()
    for name, entry in sorted(entries.items()):
        if not isinstance(entry, dict) or not isinstance(entry.get("mesh"), str) \
                or not isinstance(entry.get("primitive"), int) or isinstance(entry.get("primitive"), bool):
            return {"status": "invalid", "reason": f"lining {name}", "mask_sha256": digest}
        key = (entry["mesh"], entry["primitive"])
        if key not in expected or key in seen:
            return {"status": "invalid", "reason": f"lining {name} not in the garment", "mask_sha256": digest}
        seen.add(key)
        triangles = entry.get("triangles")
        if not isinstance(triangles, int) or isinstance(triangles, bool) or triangles != expected[key]:
            return {"status": "invalid", "reason": f"lining {name} triangles", "mask_sha256": digest}
        keep = _mask_bits(entry.get("keep"), triangles)
        visible = _mask_bits(entry.get("visible"), triangles)
        if keep is None or visible is None:
            return {"status": "invalid", "reason": f"lining {name} bits", "mask_sha256": digest}
        if visible & ~keep:
            return {"status": "invalid", "reason": f"lining {name} visible not kept", "mask_sha256": digest}
        if not _check_rows(entry.get("check"), triangles):
            return {"status": "invalid", "reason": f"lining {name} check", "mask_sha256": digest}
        found.append({"mesh": key[0], "primitive": key[1], "triangles": triangles, "keep": entry["keep"],
                      "check": entry["check"], "removable": triangles - keep.bit_count()})
    removable = sum(item.pop("removable") for item in found)
    result = {"status": "ok" if len(found) == len(expected) else "partial", "mask_sha256": digest,
              "removable": removable,
              "input": {"schema": LINING_INPUT_SCHEMA, "mask_sha256": digest, "linings": found}}
    if result["status"] == "partial":
        result["reason"] = "linings without a mask: " + ", ".join(
            sorted(f"{mesh}/{primitive}" for mesh, primitive in set(expected) - seen))
    return result


def lining_key(mask_sha256: str) -> str:
    """Cache key of a file's lining input: the mask bytes and the gate they passed."""
    return hashlib.sha256(json.dumps({"mask_sha256": mask_sha256, "gate": MASK_GATE, "schema": LINING_INPUT_SCHEMA},
                                     sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def lining_fields(path: Path, relative: str, file_sha256: str, masks: Path) -> dict:
    """The record fields of a garment's lining mask ({} when it has no lining)."""
    linings = lining_primitives(gltf_document(path))
    if not linings:
        return {}
    mask = read_mask(mask_path(masks, relative), logical(relative), file_sha256, linings)
    fields = {"mask_status": mask["status"]}
    if mask.get("reason"):
        fields["mask_reason"] = mask["reason"]
    if "input" in mask:
        fields.update(lining=mask["input"], mask_sha256=mask["mask_sha256"], lining_key=lining_key(mask["mask_sha256"]),
                      mask_removable=mask["removable"])
    return fields


def copy_mask_fields(row: dict, record: dict) -> dict:
    """Puts the record's current mask fields on a summary row (and drops any
    the record no longer has). Returns the row."""
    for key in MASK_FIELDS:
        row.pop(key, None)
        if key in record:
            row[key] = record[key]
    return row


def lining_masked(row: dict) -> bool:
    """True when the cook's lining stage masked at least one surface of the
    file. A cook.gd that does not run the stage reports no lining rows, and
    masks that stay below the gain gate leave the sidecar exactly as LOD policy
    v1 plans it; neither is shaped by the mask."""
    for mesh in row.get("meshes") or []:
        for surface in (mesh.get("surfaces") or []) if isinstance(mesh, dict) else []:
            lining = surface.get("lining") if isinstance(surface, dict) else None
            if isinstance(lining, dict) and lining.get("status") == "masked":
                return True
    return False


# --- race-refit budget ----------------------------------------------------------------

def budget_sources(project: Path) -> dict[str, list[str]]:
    """res:// race refit -> its Human source(s), from equipment.json: for every
    model that is not skinned (attached to a socket bone; the runtime's
    default), each canonical_<race>_<sex> variant against the model's
    canonical_human_<sex> variant (the model's own scene when it has none).
    A scene that is any model's Human source, or its own source, is never a
    refit. {} without equipment.json."""
    path = project / EQUIPMENT
    if not path.is_file():
        return {}
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    models = document.get("models") if isinstance(document, dict) else None
    humans: set[str] = set()
    pairs: dict[str, set[str]] = {}
    for model in (models or {}).values() if isinstance(models, dict) else []:
        if not isinstance(model, dict) or model.get("attach", "socket") == "skinned":
            continue
        if isinstance(model.get("scene"), str):
            humans.add(model["scene"])
        variants = model.get("variants") if isinstance(model.get("variants"), dict) else {}
        for key, variant in sorted(variants.items()):
            match = BUDGET_VARIANT.match(key) if isinstance(key, str) else None
            if not match or not isinstance(variant, dict) or not isinstance(variant.get("scene"), str):
                continue
            race, sex = match.groups()
            human = variants.get(f"canonical_{HUMAN_RACE}_{sex}")
            reference = human.get("scene") if isinstance(human, dict) and isinstance(human.get("scene"), str) \
                else model.get("scene")
            if not isinstance(reference, str):
                continue
            humans.add(reference)
            if race != HUMAN_RACE and variant["scene"] != reference:
                pairs.setdefault(variant["scene"], set()).add(reference)
    return {scene: sorted(references) for scene, references in sorted(pairs.items()) if scene not in humans}


def budget_fields(project: Path, references: list[str], seen: dict[str, dict | None]) -> dict:
    """The record fields of a race refit: the budget stage's input against its
    Human source (of several, the one with the most triangles: the least cut)
    and its cache key, or budget_status "no_reference" when no source can be
    read. `seen` memoizes each source's {sha256, triangles}."""
    best = None
    for reference in references:
        if reference not in seen:
            relative = reference[len("res://"):] if reference.startswith("res://") else ""
            path = project / relative
            triangles = gltf_triangles(gltf_document(path)) if relative and in_scope(relative) and path.is_file() else 0
            seen[reference] = {"sha256": sha256_file(path), "triangles": triangles} if triangles > 0 else None
        info = seen[reference]
        if info is not None and (best is None or info["triangles"] > best[1]["triangles"]):
            best = (reference, info)
    if best is None:
        return {"budget_status": "no_reference"}
    budget = {"schema": BUDGET_INPUT_SCHEMA, "reference": best[0], "reference_sha256": best[1]["sha256"],
              "reference_triangles": best[1]["triangles"]}
    return {"budget": budget, "budget_key": budget_key(budget), "budget_reference": best[0],
            "budget_reference_triangles": best[1]["triangles"], "budget_status": "ok"}


def budget_key(budget: dict) -> str:
    """Cache key of a file's budget input: its Human source's path, bytes and triangles."""
    return hashlib.sha256(json.dumps(budget, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def copy_budget_fields(row: dict, record: dict) -> dict:
    """Puts the record's current budget fields on a summary row (and drops any
    the record no longer has). Returns the row."""
    for key in BUDGET_FIELDS:
        row.pop(key, None)
        if key in record:
            row[key] = record[key]
    return row


def budget_reduced(row: dict) -> bool:
    """True when the cook's budget stage gave at least one surface of the file
    a reduced base (a cook.gd that does not run the stage reports no budget
    rows, and a refit within its budget keeps LOD policy v1's sidecar)."""
    for mesh in row.get("meshes") or []:
        for surface in (mesh.get("surfaces") or []) if isinstance(mesh, dict) else []:
            budget = surface.get("budget") if isinstance(surface, dict) else None
            if isinstance(budget, dict) and budget.get("status") in BUDGET_REDUCED:
                return True
    return False


# --- engine and policy -------------------------------------------------------

def wrapper_command(wrapper: str | None) -> list[str]:
    return shlex.split(wrapper) if wrapper else []


def engine_identity(godot: Path, wrapper: list[str]) -> str:
    """The engine build string (the runtime's Format.engine_identity())."""
    result = subprocess.run([*wrapper, str(godot), "--version"], capture_output=True, text=True,
                            timeout=DEFAULT_SLOT_WAIT_SECONDS, check=False)
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if ENGINE_PATTERN.match(line):
            return line
    raise CookError(f"Cannot read the engine version from {godot}: {result.stdout!r} {result.stderr!r}")


def policy_digest(project: Path, engine: str) -> str:
    inputs = {"policy": POLICY, "engine": engine,
              "files": {relative: sha256_file(project / relative) for relative in POLICY_FILES}}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# --- state ----------------------------------------------------------------------

def state_dir(out: Path) -> Path:
    return out / STATE_FOLDER


def root_dir(out: Path) -> Path:
    return out / POLICY


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CookError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CookError(f"Expected a JSON object: {path}")
    return value


def write_json_atomic(path: Path, value: dict, *, compact: bool = False) -> int:
    text = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) if compact
            else json.dumps(value, sort_keys=True, indent=1, ensure_ascii=False)) + "\n"
    data = text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)
    return len(data)


def load_summary(out: Path) -> dict:
    path = state_dir(out) / SUMMARY_FILE
    if not path.is_file():
        return {"schema": SCHEMA, "policy": POLICY, "files": {}, "runs": []}
    summary = read_json(path)
    if summary.get("schema") != SCHEMA or summary.get("policy") != POLICY or not isinstance(summary.get("files"), dict):
        return {"schema": SCHEMA, "policy": POLICY, "files": {}, "runs": []}
    summary.setdefault("runs", [])
    return summary


def load_catalog(root: Path) -> dict:
    path = root / CATALOG_FILE
    if not path.is_file():
        return {}
    catalog = read_json(path)
    if catalog.get("schema") != SCHEMA or catalog.get("policy") != POLICY or not isinstance(catalog.get("entries"), dict):
        return {}
    return catalog


def blob_intact(root: Path, entry: dict) -> bool:
    sidecar = entry.get("sidecar")
    digest = entry.get("sidecar_sha256")
    if not isinstance(sidecar, str) or not isinstance(digest, str) or sidecar != f"{BLOB_FOLDER}/{digest}.rlgeo":
        return False
    path = root / sidecar
    return path.is_file() and path.stat().st_size == entry.get("sidecar_bytes") and sha256_file(path) == digest


@contextlib.contextmanager
def driver_lock(out: Path):
    """Holds an OS lock on <out>/cook/driver.lock (released when the process
    ends, so a crash leaves nothing stale). A second cook or verify on the same
    output folder raises CookError instead of pruning the first one's run
    folders or collecting blobs its catalogue is about to reference."""
    path = state_dir(out) / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    locked = False
    try:
        try:
            if os.name == "nt":
                import msvcrt
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise CookError(f"Another actor geometry driver is using {out} ({path})") from exc
        yield path
    finally:
        if locked and os.name == "nt":
            import msvcrt
            stream.seek(0)
            with contextlib.suppress(OSError):
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        stream.close()


def ensure_ignored(out: Path) -> None:
    """Generated output must not become source files in a Git checkout."""
    out.mkdir(parents=True, exist_ok=True)
    top = subprocess.run(["git", "-C", str(out), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0:
        return
    probe = out / POLICY / CATALOG_FILE
    ignored = subprocess.run(["git", "-C", str(out), "check-ignore", "-q", "--no-index", "--", str(probe)])
    if ignored.returncode != 0:
        raise CookError(f"Output directory is not Git-ignored: {out}")


# --- planning ----------------------------------------------------------------------

def plan(project: Path, out: Path, digest: str, *, paths: list[str] | None = None, force: bool = False,
         records: list[dict] | None = None, masks: Path | None = None, budget: bool = True) -> dict:
    """Which in-scope files need cooking. Returns {records, stale, fresh, digest}.
    `masks` is the lining mask folder (None: cook without masks); `budget`
    False cooks race refits without the budget stage."""
    if records is None:
        relatives = scope_files(project)
        if paths:
            wanted = {_relative_argument(project, item) for item in paths}
            unknown = sorted(wanted - set(relatives))
            if unknown:
                raise CookError(f"Not in the cook scope: {', '.join(unknown)}")
            relatives = [item for item in relatives if item in wanted]
        records = file_records(project, relatives, masks, budget)
    summary = load_summary(out)
    catalog = load_catalog(root_dir(out))
    entries = catalog.get("entries", {}) if catalog.get("engine") else {}
    stale, fresh = [], []
    for record in records:
        row = summary["files"].get(record["path"])
        current = (not force and isinstance(row, dict) and row.get("policy_digest") == digest
                   and row.get("file_sha256") == record["file_sha256"]
                   and row.get("dependencies_sha256", "") == record.get("dependencies_sha256", "")
                   and row.get("model_scale") == record["model_scale"]
                   and row.get("lining_key", "") == record.get("lining_key", "")
                   and row.get("budget_key", "") == record.get("budget_key", "")
                   and row.get("status") in ("cooked", "unchanged"))
        if current and row.get("status") == "cooked":
            entry = entries.get(record["path"])
            current = isinstance(entry, dict) and entry.get("sidecar_sha256") == row.get("sidecar_sha256") \
                and blob_intact(root_dir(out), entry)
        if current and row.get("status") == "unchanged":
            current = record["path"] not in entries
        (fresh if current else stale).append(record)
    return {"records": records, "stale": stale, "fresh": [record["path"] for record in fresh], "digest": digest}


def _relative_argument(project: Path, value: str) -> str:
    if value.startswith("res://"):
        return value[len("res://"):]
    path = Path(value)
    if path.is_absolute():
        return path.resolve().relative_to(project).as_posix()
    return PurePosixPath(value.replace("\\", "/")).as_posix()


def batches(items: list, size: int) -> list[list]:
    size = max(1, int(size))
    return [items[start:start + size] for start in range(0, len(items), size)]


# --- engine runs --------------------------------------------------------------------

def _kill_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=30)
    except (OSError, subprocess.TimeoutExpired, ProcessLookupError):
        pass


def run_engine(command: list[str], env: dict, log: Path, stdout: Path, timeout_seconds: float,
               slot_wait_seconds: float = DEFAULT_SLOT_WAIT_SECONDS) -> int:
    """Runs one Godot process. The timeout starts when Godot opens its log (a
    wrapper may first wait for a slot); the wait for that is bounded too."""
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    with stdout.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, env=env, stdout=stream, stderr=subprocess.STDOUT, **options)
        began = time.monotonic()
        started = None
        try:
            while True:
                code = process.poll()
                if code is not None:
                    return code
                now = time.monotonic()
                if started is None and log.exists():
                    started = now
                if started is None and now - began > slot_wait_seconds:
                    raise CookError(f"Godot did not start within {slot_wait_seconds:g} s: {' '.join(command)}")
                if started is not None and now - started > timeout_seconds:
                    raise CookError(f"Godot exceeded {timeout_seconds:g} s; log {log}")
                time.sleep(0.5)
        except BaseException:
            _kill_tree(process)
            raise


def scan_log(log: Path) -> dict:
    """Engine error lines attributed to the file the cook announced before them."""
    errors: dict[str, list[str]] = {}
    script_errors: dict[str, list[str]] = {}
    current = ""
    if not log.is_file():
        return {"errors": errors, "script_errors": script_errors}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(LOG_PREFIX):
            candidate = line[len(LOG_PREFIX):].strip()
            if candidate.startswith("res://"):
                current = candidate
            continue
        if SCRIPT_ERROR_LINE.search(line):
            script_errors.setdefault(current, []).append(line[:400])
        elif ERROR_LINE.match(line):
            errors.setdefault(current, []).append(line[:400])
    return {"errors": errors, "script_errors": script_errors}


def prune_runs(jobs: Path, keep: Path, limit: int = KEEP_RUNS) -> list[str]:
    """Removes the oldest run folders beyond `limit` (never `keep`)."""
    runs = sorted((path for path in jobs.iterdir() if path.is_dir() and path != keep),
                  key=lambda path: (path.stat().st_mtime, path.name))
    removed = []
    for path in runs[:max(0, len(runs) - (limit - 1))]:
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path.name)
    return removed


def run_batches(project: Path, godot: Path, wrapper: list[str], out: Path, mode: str, files: list[dict],
                *, root: Path, digest: str = "", batch_size: int = DEFAULT_BATCH, jobs: int = 1,
                timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, raw_digests: bool = False,
                scene_check: bool = True, runner=None) -> dict:
    """Runs the cook script over `files` in batches; merges their reports."""
    if not 1 <= jobs <= MAX_JOBS:
        raise CookError(f"--jobs must be 1-{MAX_JOBS}")
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}-{time.time_ns() % 1_000_000_000:09d}"
    run_dir = state_dir(out) / "jobs" / f"{stamp}-{mode}"
    run_dir.mkdir(parents=True)
    prune_runs(state_dir(out) / "jobs", keep=run_dir)
    profile = state_dir(out) / "profile"
    profile.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, APPDATA=str(profile), LOCALAPPDATA=str(profile),
               XDG_DATA_HOME=str(profile), XDG_CONFIG_HOME=str(profile))
    env.pop("RABBITLANDS_ACTOR_GEOMETRY_ROOT", None)
    env["RABBITLANDS_ACTOR_GEOMETRY"] = "off" if mode == "cook" else "sidecar"
    groups = batches(files, batch_size)

    def one(index: int) -> dict:
        job = run_dir / f"job-{index:03d}.json"
        report = run_dir / f"report-{index:03d}.json"
        log = run_dir / f"godot-{index:03d}.log"
        stdout = run_dir / f"stdout-{index:03d}.log"
        write_json_atomic(job, {"schema": SCHEMA, "mode": mode, "root": root.resolve().as_posix(),
                                "report": report.resolve().as_posix(), "policy_digest": digest,
                                "raw_digests": raw_digests, "scene_check": scene_check,
                                "files": groups[index]})
        command = [*wrapper, str(godot), "--headless", "--log-file", str(log), "--path", str(project),
                   "--script", COOK_SCRIPT]
        began = time.monotonic()
        code = (runner or run_engine)(command, dict(env, RABBITLANDS_ACTOR_GEOMETRY_JOB=str(job)),
                                      log, stdout, timeout_seconds)
        result = {"index": index, "code": code, "seconds": round(time.monotonic() - began, 1),
                  "log": str(log), "files": [item["path"] for item in groups[index]]}
        result.update(scan_log(log))
        if report.is_file():
            result["report"] = read_json(report)
        return result

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(one, range(len(groups))))
    merged = {"engine": "", "entries": {}, "results": {}, "batches": [], "errors": {}, "script_errors": {},
              "policy_settings": {}, "run_dir": str(run_dir)}
    for result in results:
        report = result.get("report")
        ok = result["code"] == 0 and isinstance(report, dict) and report.get("ok") is True \
            and report.get("mode") == mode
        merged["batches"].append({"index": result["index"], "code": result["code"], "ok": ok,
                                  "seconds": result["seconds"], "files": len(result["files"]),
                                  "log": result["log"]})
        for path, lines in result["errors"].items():
            merged["errors"].setdefault(path, []).extend(lines)
        for path, lines in result["script_errors"].items():
            merged["script_errors"].setdefault(path, []).extend(lines)
        if ok:
            merged["engine"] = merged["engine"] or str(report.get("engine", ""))
            merged["policy_settings"] = report.get("policy_settings", {})
        for path in result["files"]:
            row = (report or {}).get("results", {}).get(path) if ok else None
            if not isinstance(row, dict) or path in result["script_errors"] or "" in result["script_errors"]:
                row = {"status": "failed", "reason": "engine" if not ok else "script_error"}
            elif path in (report or {}).get("entries", {}):
                merged["entries"][path] = report["entries"][path]
            merged["results"][path] = row
    return merged


# --- catalogue -------------------------------------------------------------------------

def write_catalog(root: Path, engine: str, entries: dict, source_check: str = DEFAULT_SOURCE_CHECK) -> int:
    if source_check not in SOURCE_CHECKS:
        raise CookError(f"source_check must be one of {', '.join(SOURCE_CHECKS)}")
    catalog = {"schema": SCHEMA, "policy": POLICY, "engine": engine, "source_check": source_check,
               "entries": {key: entries[key] for key in sorted(entries)}}
    return write_json_atomic(root / CATALOG_FILE, catalog, compact=True)


def collect_garbage(root: Path, entries: dict) -> list[str]:
    """Removes blobs/<sha256>.rlgeo files no entry references (and stale temporaries)."""
    referenced = {PurePosixPath(entry["sidecar"]).name for entry in entries.values()}
    removed = []
    folder = root / BLOB_FOLDER
    if not folder.is_dir():
        return removed
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        if (BLOB_PATTERN.match(path.name) and path.name not in referenced) or path.name.endswith(".tmp"):
            path.unlink()
            removed.append(path.name)
    return removed


# --- commands --------------------------------------------------------------------------

def cook(project: Path, godot: Path, *, out: Path | None = None, wrapper: str | None = None,
         paths: list[str] | None = None, force: bool = False, batch_size: int = DEFAULT_BATCH,
         jobs: int = 1, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, raw_digests: bool = False,
         runner=None, engine: str | None = None, source_check: str = DEFAULT_SOURCE_CHECK,
         masks: Path | None | bool = True, budget: bool = True) -> dict:
    """`masks`: the lining mask folder, True for the default (<out>/lining-masks),
    or None/False to cook without lining masks. `budget` False cooks race
    refits without the budget stage."""
    project = project_path(project)
    if source_check not in SOURCE_CHECKS:
        raise CookError(f"source_check must be one of {', '.join(SOURCE_CHECKS)}")
    out = Path(out).resolve() if out else default_out(project)
    masks = resolve_masks(out, masks)
    ensure_ignored(out)
    with driver_lock(out):
        return _cook(project, godot, out, wrapper=wrapper, paths=paths, force=force, batch_size=batch_size,
                     jobs=jobs, timeout_seconds=timeout_seconds, raw_digests=raw_digests, runner=runner,
                     engine=engine, source_check=source_check, masks=masks, budget=budget)


def resolve_masks(out: Path, masks: Path | None | bool) -> Path | None:
    if masks is True:
        return default_masks(out)
    if masks is None or masks is False:
        return None
    return Path(masks).resolve()


def _cook(project: Path, godot: Path, out: Path, *, wrapper: str | None, paths: list[str] | None, force: bool,
          batch_size: int, jobs: int, timeout_seconds: float, raw_digests: bool, runner, engine: str | None,
          source_check: str, masks: Path | None = None, budget: bool = True) -> dict:
    command = wrapper_command(wrapper)
    began = time.monotonic()
    engine = engine or engine_identity(godot, command)
    digest = policy_digest(project, engine)
    planned = plan(project, out, digest, paths=paths, force=force, masks=masks, budget=budget)
    summary = load_summary(out)
    catalog = load_catalog(root_dir(out))
    old_entries = catalog.get("entries", {}) if catalog.get("engine") == engine else {}
    scope = {record["path"] for record in planned["records"]}
    merged = {"entries": {}, "results": {}, "batches": [], "errors": {}, "script_errors": {},
              "engine": engine, "policy_settings": {}, "run_dir": ""}
    if planned["stale"]:
        merged = run_batches(project, godot, command, out, "cook", planned["stale"], root=root_dir(out),
                             digest=digest, batch_size=batch_size, jobs=jobs, timeout_seconds=timeout_seconds,
                             raw_digests=raw_digests, runner=runner)
        if merged["engine"] and merged["engine"] != engine:
            raise CookError(f"The cook ran on {merged['engine']}, not {engine}")
    entries = {}
    if paths:
        # A partial cook keeps every other current entry.
        entries = {key: value for key, value in old_entries.items() if key not in scope}
    for path in planned["fresh"]:
        if path in old_entries:
            entries[path] = old_entries[path]
    records = {record["path"]: record for record in planned["records"]}
    files = summary["files"] if paths else {key: value for key, value in summary["files"].items() if key in scope}
    for path in planned["fresh"]:
        # A reused row keeps its sidecar (same lining key), but an unusable
        # mask's status may have moved on (missing -> invalid, no masks now).
        if isinstance(files.get(path), dict):
            files[path] = copy_budget_fields(copy_mask_fields(dict(files[path]), records[path]), records[path])
    for path, row in merged["results"].items():
        record = records[path]
        row = dict(row, file_sha256=record["file_sha256"], model_scale=record["model_scale"],
                   bytes=record["bytes"], policy_digest=digest)
        row.pop("dependencies_sha256", None)
        if record.get("dependencies_sha256"):
            row["dependencies_sha256"] = record["dependencies_sha256"]
        copy_mask_fields(row, record)
        copy_budget_fields(row, record)
        if merged["errors"].get(path):
            row["engine_errors"] = merged["errors"][path][:8]
        if row.get("status") == "cooked" and path in merged["entries"]:
            entry = merged["entries"][path]
            if record.get("mask_sha256") and lining_masked(row):
                # Provenance only (the sidecar's own hash binds what is drawn),
                # and only for a sidecar the mask actually shaped.
                entry = dict(entry, inputs=dict(entry.get("inputs") or {}, mask_sha256=record["mask_sha256"]))
            if record.get("budget") and budget_reduced(row):
                # Provenance only, and only for a sidecar the budget shaped.
                entry = dict(entry, inputs=dict(entry.get("inputs") or {},
                                                budget_reference=record["budget"]["reference"],
                                                budget_reference_sha256=record["budget"]["reference_sha256"]))
            entries[path] = entry
        else:
            entries.pop(path, None)
            if row.get("status") == "cooked":
                row["status"] = "failed"
                row["reason"] = "no_entry"
        files[path] = row
    catalog_bytes = write_catalog(root_dir(out), engine, entries, source_check)
    removed = collect_garbage(root_dir(out), entries)
    wall = round(time.monotonic() - began, 1)
    statuses: dict[str, int] = {}
    mask_statuses: dict[str, int] = {}
    budget_statuses: dict[str, int] = {}
    for path in planned["records"]:
        status = files.get(path["path"], {}).get("status", "missing")
        statuses[status] = statuses.get(status, 0) + 1
        if "mask_status" in path:
            mask_statuses[path["mask_status"]] = mask_statuses.get(path["mask_status"], 0) + 1
        if "budget_status" in path:
            budget_statuses[path["budget_status"]] = budget_statuses.get(path["budget_status"], 0) + 1
    run = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "engine": engine, "policy_digest": digest,
           "scope": len(planned["records"]), "cooked_now": len(planned["stale"]), "reused": len(planned["fresh"]),
           "partial": bool(paths), "force": force, "wall_seconds": wall, "batches": merged["batches"],
           "statuses": statuses, "catalog_bytes": catalog_bytes, "blobs_removed": len(removed),
           "masks": str(masks) if masks else "", "mask_statuses": mask_statuses,
           "budget": budget, "budget_statuses": budget_statuses,
           "unattributed_errors": merged["errors"].get("", [])[:8], "run_dir": merged["run_dir"]}
    summary.update({"schema": SCHEMA, "policy": POLICY, "engine": engine, "policy_digest": digest,
                    "settings": merged["policy_settings"] or summary.get("settings", {}), "files": files})
    summary["runs"] = (summary.get("runs") or [])[-19:] + [run]
    write_json_atomic(state_dir(out) / SUMMARY_FILE, summary)
    return {"ok": statuses.get("failed", 0) == 0 and not merged["script_errors"], "root": str(root_dir(out)),
            "entries": len(entries), **{key: run[key] for key in ("scope", "cooked_now", "reused", "wall_seconds",
                                                                   "statuses", "catalog_bytes", "blobs_removed",
                                                                   "mask_statuses", "budget_statuses")},
            "failed": sorted(path for path, row in files.items() if row.get("status") == "failed")[:20],
            "script_errors": {key: value[:3] for key, value in merged["script_errors"].items()}}


def verify(project: Path, godot: Path, *, out: Path | None = None, wrapper: str | None = None,
           paths: list[str] | None = None, sample: int = 0, batch_size: int = DEFAULT_BATCH, jobs: int = 1,
           timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, scene_check: bool = True, runner=None) -> dict:
    project = project_path(project)
    out = Path(out).resolve() if out else default_out(project)
    with driver_lock(out):
        return _verify(project, godot, out, wrapper=wrapper, paths=paths, sample=sample, batch_size=batch_size,
                       jobs=jobs, timeout_seconds=timeout_seconds, scene_check=scene_check, runner=runner)


def _verify(project: Path, godot: Path, out: Path, *, wrapper: str | None, paths: list[str] | None, sample: int,
            batch_size: int, jobs: int, timeout_seconds: float, scene_check: bool, runner) -> dict:
    catalog = load_catalog(root_dir(out))
    if not catalog:
        raise CookError(f"No catalogue in {root_dir(out)}")
    keys = sorted(catalog["entries"])
    if paths:
        wanted = {logical(_relative_argument(project, item)) for item in paths}
        keys = [key for key in keys if key in wanted]
    if sample > 0:
        keys = keys[::max(1, len(keys) // sample)][:sample]
    merged = run_batches(project, godot, wrapper_command(wrapper), out, "verify", [{"path": key} for key in keys],
                         root=root_dir(out), batch_size=batch_size, jobs=jobs, timeout_seconds=timeout_seconds,
                         scene_check=scene_check, runner=runner)
    statuses: dict[str, int] = {}
    reasons: dict[str, int] = {}
    usec = []
    scene_levels = 0
    unseen_levels = 0
    mismatched = []
    for path, row in merged["results"].items():
        statuses[row.get("status", "?")] = statuses.get(row.get("status", "?"), 0) + 1
        if row.get("reason"):
            reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
        if row.get("status") == "applied":
            usec.append(int(row.get("apply_usec", 0)))
        scene_levels += int(row.get("scene_levels", 0))
        unseen_levels += int(row.get("unseen_levels", 0))
        if int(row.get("scene_mismatches", 0)) != 0:
            mismatched.append(path)
    usec.sort()
    # Verifying nothing (an empty catalogue, --paths without entries) is not a pass.
    result = {"ok": bool(keys) and statuses.get("applied", 0) == len(keys) and not mismatched
              and not merged["script_errors"],
              "files": len(keys), "statuses": statuses, "reasons": reasons, "scene_levels": scene_levels,
              "unseen_levels": unseen_levels,
              "scene_mismatches": mismatched[:20], "run_dir": merged["run_dir"],
              "apply_usec": {"median": usec[len(usec) // 2] if usec else 0,
                             "p95": usec[min(len(usec) - 1, int(len(usec) * 0.95))] if usec else 0,
                             "max": usec[-1] if usec else 0},
              "not_applied": sorted(path for path, row in merged["results"].items()
                                    if row.get("status") != "applied")[:20],
              "script_errors": {key: value[:3] for key, value in merged["script_errors"].items()}}
    write_json_atomic(Path(merged["run_dir"]) / "verify.json", dict(result, results=merged["results"]))
    return result


def _surface_rows(summary: dict):
    for path, row in sorted(summary.get("files", {}).items()):
        for mesh in row.get("meshes", []) or []:
            for surface in mesh.get("surfaces", []):
                yield path, mesh, surface


def _folder(path: str) -> str:
    parts = relative_of(path)[len(SOURCE_ROOT):].split("/")
    return parts[0] if len(parts) > 1 else "."


def report(out: Path) -> dict:
    """Coverage, bytes and cook time from the summary of the last cook."""
    summary = load_summary(out)
    files = summary.get("files", {})
    if not files:
        raise CookError(f"No cook summary in {state_dir(out)}")
    statuses: dict[str, int] = {}
    classes: dict[str, dict] = {}
    for path, row in files.items():
        statuses[row.get("status", "?")] = statuses.get(row.get("status", "?"), 0) + 1
        bucket = classes.setdefault(_folder(path), {"files": 0, "sidecars": 0, "sidecar_bytes": 0, "triangles": 0,
                                                    "triangles_2plus": 0, "triangles_1plus": 0})
        bucket["files"] += 1
        if row.get("status") == "cooked":
            bucket["sidecars"] += 1
            bucket["sidecar_bytes"] += int(row.get("sidecar_bytes", 0))
    methods: dict[str, int] = {}
    reasons: dict[str, dict] = {}
    linings = {"surfaces": 0, "triangles": 0, "triangles_2plus": 0}
    masking = {"surfaces": {}, "triangles": 0, "kept_triangles": 0, "removed_triangles": 0,
               "removable_below_gain": 0, "compacted_surfaces": 0, "vertices": 0, "compacted_vertices": 0,
               "rejected": {}}
    budgeting = {"surfaces": {}, "reasons": {}, "triangles": 0, "base_triangles": 0, "files": {}}
    levels_hist: dict[int, int] = {}
    uncovered = []
    total = covered2 = covered1 = 0
    for path, mesh, surface in _surface_rows(summary):
        triangles = int(surface.get("triangles", 0))
        levels = len(surface.get("levels", []))
        bucket = classes[_folder(path)]
        bucket["triangles"] += triangles
        total += triangles
        if levels >= 1:
            covered1 += triangles
            bucket["triangles_1plus"] += triangles
        if levels >= 2:
            covered2 += triangles
            bucket["triangles_2plus"] += triangles
        method = surface.get("method", "?")
        methods[method] = methods.get(method, 0) + 1
        levels_hist[levels] = levels_hist.get(levels, 0) + 1
        if surface.get("reason"):
            reason = reasons.setdefault(surface["reason"], {"surfaces": 0, "triangles": 0})
            reason["surfaces"] += 1
            reason["triangles"] += triangles
        if "Generated" in str(mesh.get("name", "")):
            linings["surfaces"] += 1
            linings["triangles"] += triangles
            linings["triangles_2plus"] += triangles if levels >= 2 else 0
        lining = surface.get("lining")
        if isinstance(lining, dict):
            status = str(lining.get("status", "?"))
            masking["surfaces"][status] = masking["surfaces"].get(status, 0) + 1
            masking["triangles"] += triangles
            if status == "masked":
                masking["kept_triangles"] += int(lining.get("kept_triangles", triangles))
                masking["removed_triangles"] += int(lining.get("removed_triangles", 0))
                masking["vertices"] += int(lining.get("vertices", 0))
                compacted = lining.get("compacted")
                if isinstance(compacted, dict):
                    masking["compacted_surfaces"] += 1
                    masking["compacted_vertices"] += int(lining.get("vertices", 0)) - int(compacted.get("kept_vertices", 0))
            elif status == "below_gain":
                masking["removable_below_gain"] += int(lining.get("removable_triangles", 0))
            elif status == "rejected":
                reason = str(lining.get("reason", "?"))
                masking["rejected"][reason] = masking["rejected"].get(reason, 0) + 1
        budget = surface.get("budget")
        if isinstance(budget, dict):
            status = str(budget.get("status", "?"))
            budgeting["surfaces"][status] = budgeting["surfaces"].get(status, 0) + 1
            if budget.get("reason"):
                reason = str(budget["reason"])
                budgeting["reasons"][reason] = budgeting["reasons"].get(reason, 0) + 1
            if status in BUDGET_REDUCED:
                budgeting["triangles"] += triangles
                budgeting["base_triangles"] += int(budget.get("base_triangles", triangles))
        if levels < 2 and triangles >= 2000:
            uncovered.append((triangles, path, mesh.get("name", ""), surface.get("reason") or f"{levels} level"))
    for bucket in classes.values():
        bucket["coverage_2plus"] = round(bucket["triangles_2plus"] / max(bucket["triangles"], 1), 4)
    usec = {key: sum(int(row.get(key, 0)) for row in files.values()) for key in ("cook_usec", "parse_usec", "plan_usec")}
    blob_bytes = sum(int(row.get("sidecar_bytes", 0)) for row in files.values() if row.get("status") == "cooked")
    catalog_path = root_dir(out) / CATALOG_FILE
    uncovered.sort(reverse=True)
    mask_files: dict[str, int] = {}
    for row in files.values():
        if row.get("mask_status"):
            mask_files[row["mask_status"]] = mask_files.get(row["mask_status"], 0) + 1
    masking["files"] = mask_files
    for row in files.values():
        statuses_of = {str(surface.get("budget", {}).get("status", "")) for mesh in row.get("meshes") or []
                       for surface in mesh.get("surfaces", []) if isinstance(surface.get("budget"), dict)}
        if statuses_of:
            status = next((name for name in ("capped", "partial", "kept", "rejected", "within") if name in statuses_of), "?")
            budgeting["files"][status] = budgeting["files"].get(status, 0) + 1
        elif row.get("budget_status") == "no_reference":
            budgeting["files"]["no_reference"] = budgeting["files"].get("no_reference", 0) + 1
    masking["removed_share"] = round(masking["removed_triangles"] / max(masking["triangles"], 1), 4)
    return {"engine": summary.get("engine"), "policy_digest": summary.get("policy_digest"),
            "lining_masks": masking, "budget": budgeting,
            "files": len(files), "statuses": statuses, "classes": classes,
            "surfaces": sum(methods.values()), "methods": methods, "reasons": reasons,
            "levels_per_surface": {str(key): levels_hist[key] for key in sorted(levels_hist)},
            "source_triangles": total,
            "coverage_triangles_2plus": round(covered2 / max(total, 1), 4),
            "coverage_triangles_1plus": round(covered1 / max(total, 1), 4),
            "linings": dict(linings, coverage_2plus=round(linings["triangles_2plus"] / max(linings["triangles"], 1), 4)),
            "sidecar_bytes": blob_bytes,
            "catalog_bytes": catalog_path.stat().st_size if catalog_path.is_file() else 0,
            "cook_seconds": round(usec["cook_usec"] / 1e6, 1), "parse_seconds": round(usec["parse_usec"] / 1e6, 1),
            "plan_seconds": round(usec["plan_usec"] / 1e6, 1),
            "last_run": {key: value for key, value in (summary.get("runs") or [{}])[-1].items() if key != "batches"},
            "largest_without_two_levels": [list(item) for item in uncovered[:15]]}


def compare(root_a: Path, root_b: Path) -> dict:
    """Byte comparison of two catalogue roots."""
    root_a, root_b = Path(root_a), Path(root_b)
    catalog_a, catalog_b = load_catalog(root_a), load_catalog(root_b)
    entries_a, entries_b = catalog_a.get("entries", {}), catalog_b.get("entries", {})
    differing = sorted(key for key in set(entries_a) | set(entries_b) if entries_a.get(key) != entries_b.get(key))
    blobs_a = {path.name: path for path in (root_a / BLOB_FOLDER).glob("*.rlgeo")} if (root_a / BLOB_FOLDER).is_dir() else {}
    blobs_b = {path.name: path for path in (root_b / BLOB_FOLDER).glob("*.rlgeo")} if (root_b / BLOB_FOLDER).is_dir() else {}
    blob_differences = sorted(name for name in set(blobs_a) | set(blobs_b)
                              if name not in blobs_a or name not in blobs_b
                              or blobs_a[name].read_bytes() != blobs_b[name].read_bytes())
    same_catalog = (root_a / CATALOG_FILE).is_file() and (root_b / CATALOG_FILE).is_file() and \
        (root_a / CATALOG_FILE).read_bytes() == (root_b / CATALOG_FILE).read_bytes()
    return {"identical": same_catalog and not differing and not blob_differences and bool(entries_a),
            "catalog_bytes_identical": same_catalog, "entries": [len(entries_a), len(entries_b)],
            "blobs": [len(blobs_a), len(blobs_b)], "differing_entries": differing[:20],
            "differing_blobs": blob_differences[:20]}


# --- census prediction ------------------------------------------------------------------

def lod_multiplier(vfov_degrees: float, aspect: float) -> float:
    return 2.0 * math.tan(math.radians(vfov_degrees) / 2.0) * aspect


def level_triangles(surface: dict, depth: float, *, model_scale: float, lod_bias: float, multiplier: float,
                    width: float, threshold_px: float = 1.0) -> int:
    """Triangles Godot draws for one surface at this camera depth: the last LOD
    level whose edge * scale * bias / (depth * multiplier) <= threshold / width
    (the masked base of a lining when the lining stage changed it)."""
    drawn = int(surface.get("base_triangles", surface.get("triangles", 0)))
    for triangles, edge, *_ in surface.get("levels", []):
        if depth <= 0 or float(edge) * model_scale * lod_bias / (depth * multiplier) > threshold_px / width:
            break
        drawn = int(triangles)
    return drawn


def _equipment_scenes(project: Path) -> dict[str, dict]:
    document = json.loads((project / "data/actors/equipment.json").read_text(encoding="utf-8-sig"))
    return document.get("models", {})


PIECE_SKINNED = re.compile(r"^eq(\d+):(\d+):(.+)$")
PIECE_SOCKET = re.compile(r"EquipmentPart_(\d+)_Visual_(\d+)_[^/]*/NativeEquipment/(.+)$")
BODY_PIECE_PREFIX = "NativeModel/BodyRoot/Skeleton3D/"


def predict(out: Path, project: Path, census_path: Path, *, biases: list[float], variant: str,
            body_scene: str, width: float | None = None, aspect: float | None = None,
            vfov_degrees: float | None = None) -> dict:
    """Predicted drawn triangles of the in-frustum bodies of a crowd triangle
    census (the wave-2 design census format) once the cooked chains apply.
    Pieces are mapped to cooked meshes through equipment.json (part:id, the
    given race variant) and the body scene; a piece is scaled by its measured
    share of the mesh's base triangles (cover cuts). Unmapped pieces (RL heads,
    runtime-built skins, creatures, overhead quads) stay as measured; map dots
    are left out (full-map camera only)."""
    project = project_path(project)
    summary = load_summary(out)
    meshes: dict[str, dict] = {}
    for path, row in summary.get("files", {}).items():
        for mesh in row.get("meshes", []) or []:
            meshes[f"{path}|{mesh.get('name')}"] = mesh
    census = read_json(Path(census_path))
    cell = (census.get("cells") or [{}])[0]
    actors = (((cell.get("census") or {}).get("afterSpawn") or {}).get("triangleCensus") or [])
    if not actors:
        raise CookError(f"No triangleCensus in {census_path}")
    root_size = ((cell.get("effectiveRuntime") or {}).get("effectiveSettings") or {}).get("rootSize") \
        or (census.get("effectiveSettings") or {}).get("rootSize") or [1280, 720]
    width = float(width or root_size[0])
    aspect = float(aspect or (root_size[0] / max(root_size[1], 1)))
    vfov = float(vfov_degrees or (census.get("camera") or {}).get("fieldOfView") or DEFAULT_VFOV_DEGREES)
    multiplier = lod_multiplier(vfov, aspect)
    equipment = _equipment_scenes(project)

    def scene_for(part: str, item: str) -> str | None:
        model = equipment.get(f"{part}:{item}")
        if not isinstance(model, dict):
            return None
        chosen = (model.get("variants") or {}).get(variant) or model
        return chosen.get("scene")

    def find_mesh(scene: str | None, name: str) -> dict | None:
        if not scene:
            return None
        for key, mesh in meshes.items():
            path, mesh_name = key.split("|", 1)
            if path == scene and (mesh_name == name or mesh_name.endswith("_" + name)):
                return mesh
        return None

    stems: dict[str, str] = {}
    for path in summary.get("files", {}):
        stems.setdefault(PurePosixPath(path).stem, path)

    def mesh_for(key: str) -> dict | None:
        skinned = PIECE_SKINNED.match(key)
        socket = PIECE_SOCKET.search(key)
        if skinned:
            return find_mesh(scene_for(skinned.group(1), skinned.group(2)), skinned.group(3))
        if socket:
            return find_mesh(scene_for(socket.group(1), socket.group(2)), socket.group(3))
        if key.startswith(BODY_PIECE_PREFIX) and "/" not in key[len(BODY_PIECE_PREFIX):]:
            # Parts of the race body itself (body, classic head parts at Low).
            return find_mesh(body_scene, key[len(BODY_PIECE_PREFIX):])
        # A presentation prop keeps its glTF root name: .../<file stem>/<mesh>.
        segments = key.split("/")
        if len(segments) >= 2 and segments[-2] in stems:
            return find_mesh(stems[segments[-2]], segments[-1])
        return None

    results = {}
    mapped_names: dict[str, int] = {}
    unmapped_names: dict[str, int] = {}
    for bias in biases:
        measured = predicted = 0
        covered = 0.0
        bodies = 0
        for actor in actors:
            if not actor.get("inFrustum"):
                continue
            bodies += 1
            depth = float(actor.get("distance", 0.0))
            for key, piece in (actor.get("pieces") or {}).items():
                tris = int(piece.get("tris", 0))
                if key.startswith("MapDot"):
                    continue
                measured += tris
                mesh = mesh_for(key)
                label = key.split(":")[-1].split("/")[-1]
                if mesh is None:
                    predicted += tris
                    unmapped_names[label] = unmapped_names.get(label, 0) + (1 if bias == biases[0] else 0)
                    continue
                mapped_names[label] = mapped_names.get(label, 0) + (1 if bias == biases[0] else 0)
                base = sum(int(surface.get("triangles", 0)) for surface in mesh.get("surfaces", []))
                chained = sum(int(surface.get("triangles", 0)) for surface in mesh.get("surfaces", [])
                              if len(surface.get("levels", [])) >= 2)
                drawn = sum(level_triangles(surface, depth, model_scale=float(mesh.get("model_scale", 1.0)),
                                            lod_bias=bias, multiplier=multiplier, width=width)
                            for surface in mesh.get("surfaces", []))
                predicted += round(tris * drawn / base) if base > 0 else tris
                covered += tris * chained / base if base > 0 else 0.0
        results[str(bias)] = {"bodies": bodies, "measured_triangles": measured, "predicted_triangles": predicted,
                              "change": round(predicted / measured - 1.0, 4) if measured else 0.0,
                              # Share of the drawn triangles on surfaces with >= 2 cooked levels.
                              "drawn_coverage_2plus": round(covered / measured, 4) if measured else 0.0}
    return {"census": str(census_path), "width": width, "aspect": round(aspect, 4), "vfov": vfov,
            "lod_multiplier": round(multiplier, 4), "variant": variant, "body": body_scene,
            "by_lod_bias": results, "mapped_pieces": mapped_names, "unmapped_pieces": unmapped_names}


# --- command line ------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    def common(sub, engine_run: bool) -> None:
        sub.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
        sub.add_argument("--out", type=Path, help="state + catalogue folder (default <repo>/.local/actor-geometry)")
        if engine_run:
            sub.add_argument("--godot", type=Path, required=True)
            sub.add_argument("--wrapper", help="command prefix for every Godot run, e.g. a slot lock")
            sub.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
            sub.add_argument("--jobs", type=int, default=1)
            sub.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
            sub.add_argument("--paths", nargs="*", help="cook/verify only these files")

    planner = commands.add_parser("plan", help="list the scope and what needs cooking")
    common(planner, False)
    planner.add_argument("--engine", required=True, help="engine build string (godot --version)")
    planner.add_argument("--force", action="store_true")
    cooker = commands.add_parser("cook", help="cook what changed and rewrite the catalogue")
    common(cooker, True)
    cooker.add_argument("--force", action="store_true", help="recook every file in scope")
    for sub in (planner, cooker):
        sub.add_argument("--masks", type=Path, help="lining mask folder (default <out>/lining-masks)")
        sub.add_argument("--no-masks", action="store_true", help="cook without lining masks")
        sub.add_argument("--no-budget", action="store_true", help="cook race refits without the budget stage")
    cooker.add_argument("--raw-digests", action="store_true", help="record generate_lods digests (parity checks)")
    cooker.add_argument("--source-check", choices=SOURCE_CHECKS, default=DEFAULT_SOURCE_CHECK,
                        help="how the runtime binds sidecars to actor files (default: file)")
    verifier = commands.add_parser("verify", help="apply the catalogue with the runtime applier")
    common(verifier, True)
    verifier.add_argument("--sample", type=int, default=0)
    verifier.add_argument("--no-scene-check", action="store_true")
    reporter = commands.add_parser("report", help="coverage, bytes and time of the last cook")
    common(reporter, False)
    comparer = commands.add_parser("compare", help="byte-compare two catalogue roots")
    comparer.add_argument("root_a", type=Path)
    comparer.add_argument("root_b", type=Path)
    predictor = commands.add_parser("predict", help="predicted drawn triangles for a triangle census")
    common(predictor, False)
    predictor.add_argument("--census", type=Path, required=True)
    predictor.add_argument("--lod-bias", type=float, action="append", help="repeatable (default 1.0 0.65 0.35)")
    predictor.add_argument("--variant", default="canonical_human_male")
    predictor.add_argument("--body", default="res://assets/actors/native/races/luminous_male.glb")
    predictor.add_argument("--width", type=float)
    args = parser.parse_args(argv)
    try:
        out = getattr(args, "out", None)
        if args.command == "plan":
            project = project_path(args.project)
            out = Path(out).resolve() if out else default_out(project)
            masks = resolve_masks(out, None if args.no_masks else (args.masks or True))
            planned = plan(project, out, policy_digest(project, args.engine), force=args.force, masks=masks,
                           budget=not args.no_budget)
            mask_statuses: dict[str, int] = {}
            budget_statuses: dict[str, int] = {}
            over_budget = 0
            for record in planned["records"]:
                if "mask_status" in record:
                    mask_statuses[record["mask_status"]] = mask_statuses.get(record["mask_status"], 0) + 1
                if "budget_status" in record:
                    budget_statuses[record["budget_status"]] = budget_statuses.get(record["budget_status"], 0) + 1
                if record.get("budget"):
                    triangles = gltf_triangles(gltf_document(project / relative_of(record["path"])))
                    over_budget += int(triangles > BUDGET_RATIO * record["budget"]["reference_triangles"])
            result = {"scope": len(planned["records"]), "stale": len(planned["stale"]),
                      "fresh": len(planned["fresh"]), "policy_digest": planned["digest"],
                      "masks": str(masks) if masks else "", "mask_statuses": mask_statuses,
                      "budget_statuses": budget_statuses, "refits_over_budget": over_budget,
                      "stale_paths": [record["path"] for record in planned["stale"]][:50]}
        elif args.command == "cook":
            result = cook(args.project, args.godot, out=out, wrapper=args.wrapper, paths=args.paths,
                          force=args.force, batch_size=args.batch_size, jobs=args.jobs,
                          timeout_seconds=args.timeout_seconds, raw_digests=args.raw_digests,
                          source_check=args.source_check,
                          masks=None if args.no_masks else (args.masks or True), budget=not args.no_budget)
        elif args.command == "verify":
            result = verify(args.project, args.godot, out=out, wrapper=args.wrapper, paths=args.paths,
                            sample=args.sample, batch_size=args.batch_size, jobs=args.jobs,
                            timeout_seconds=args.timeout_seconds, scene_check=not args.no_scene_check)
        elif args.command == "report":
            project = project_path(args.project)
            result = report(Path(out).resolve() if out else default_out(project))
        elif args.command == "compare":
            result = compare(args.root_a, args.root_b)
        else:
            project = project_path(args.project)
            result = predict(Path(out).resolve() if out else default_out(project), project, args.census,
                             biases=args.lod_bias or [1.0, 0.65, 0.35], variant=args.variant,
                             body_scene=args.body, width=args.width)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok", True) and result.get("identical", True) else 1
    except (CookError, OSError, ValueError) as exc:
        print(f"actor geometry cache: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
