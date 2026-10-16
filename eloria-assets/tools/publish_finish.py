#!/usr/bin/env python3
"""Finish the map package a publisher has just written.

Added 2026-10-14 for Eloria Client; ported to Rabbit Lands 2026-10-16.

    import publish_finish
    publish_finish.finish([package_directory_or_glb, ...])

    python eloria-assets/tools/publish_finish.py <path> ...   # the same, by hand
    python eloria-assets/tools/publish_finish.py --restamp     # figures only, whole tree

Three passes decide what a published map costs to ship: shared_meshes.py
publishes a repeated prop once, shared_images.py does the same for an embedded
texture, and quantise_geometry.py stores a normal in a byte. Run over the whole
tree they recovered 2.9 GB. They were also run by hand, so everything
republished afterwards arrived with its props copied per placement, its
textures embedded and its normals at 32 bits, and the only thing that noticed
was the packager's duplicate-geometry line - 549 MB of it, a fortnight later.

This is those passes, scoped to the files one publisher wrote, for the
publisher to call itself.

Scoping changes one decision: which meshes are worth pooling. The tree-wide
pass pools a mesh that appears in two or more files anywhere; here a mesh is
pooled if the pool already holds it, or if it appears in two of the files just
written. A genuinely new prop published once now and once by another map later
stays embedded in both until the next tree-wide pass, so that pass is still
worth running - it just no longer has a fortnight of regression to undo.

Nothing is archived. The archive exists so a quantised file can be put back as
it was; a file a publisher has just written can be put back by running the
publisher again.

The last step is bookkeeping: the figures a manifest records about its own GLB.
`performance.glbBytes` and the parent's `streamingChunks` admission numbers are
both checked against the file on disk (audit_continent.py, and
_continent_v2/tests/test_publish_client_geometry.py), and a pass that shrinks a
GLB without restating them leaves the package failing its own contracts.

A pooled prop leaves its chunk's GLB, but not the GPU: the client draws it from
the pool while that chunk is resident. So a parent also states, per streamed
cell, the prototypes its chunk draws (`sharedMeshResidentBytes`, prototype ->
resident bytes, at the same factor as the cell's own geometry), and the stream
counts each one once while any resident cell names it, as it already does for
the shared images (godot-client/src/world/continent_chunk_stream.gd).
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for extra in (HERE, REPO / "godot-client" / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import quantise_geometry as QG  # noqa: E402
import shared_images as SI  # noqa: E402
import shared_meshes as SM  # noqa: E402

MAPS = SM.MAPS
POOL = SM.POOL
# What a byte of streamed chunk GLB is assumed to cost resident, where the
# package does not say: the nymara and Four Gates publishers write no
# publication record. They wrote 5 until 2026-10-16, when the village-mem
# method measured all twelve territories: a cell's pooled prototypes hold
# 0.91 x their GLB (none above 1.0) and its own meshes 0.31 x, so 5 counted
# props at about 5.5 x the truth and kept about 6 of the 16 cells in reach
# resident. Owner call 2026-10-16: 1.0, as continent-v2.
LEGACY_RESIDENT_FACTOR = 1.0


# --- the files a publisher wrote ---------------------------------------------

def glbs(paths) -> list[Path]:
    """Every shipped GLB under the given packages, or the given files."""
    found: list[Path] = []
    for raw in paths:
        path = Path(raw).resolve()
        if path.is_dir():
            found += SM.package_glbs(path)
        elif path.is_file() and path.suffix.lower() == ".glb":
            found.append(path)
    return sorted({path.resolve() for path in found})


def _index() -> dict:
    if not SM.INDEX.is_file():
        return {}
    return json.loads(SM.INDEX.read_text(encoding="utf-8")).get("prototypes", {})


def _save_index(index: dict) -> None:
    POOL.mkdir(parents=True, exist_ok=True)
    SM.INDEX.write_text(json.dumps({"schema": SM.SCHEMA, "prototypes": dict(sorted(index.items()))},
                                   indent=2) + "\n", encoding="utf-8")


def _document(path: Path) -> dict:
    """A GLB's JSON chunk, without reading its binary."""
    with path.open("rb") as handle:
        header = handle.read(20)
        if len(header) < 20 or struct.unpack_from("<I", header, 0)[0] != SM.GLB_MAGIC:
            return {}
        length, = struct.unpack_from("<I", header, 12)
        return json.loads(handle.read(length))


# --- the three passes --------------------------------------------------------

def share(files: list[Path], index: dict, dry_run: bool) -> dict:
    """Point these files at the pool, and pool what they repeat between them."""
    where: dict[str, set] = defaultdict(set)
    sizes: dict[str, int] = {}
    for glb in files:
        document, binary = SM.read_glb(glb)
        cache: dict = {}
        for mesh in range(len(document.get("meshes", []))):
            identity, size = SM.mesh_identity(document, binary, mesh, glb, cache)
            where[identity].add(glb)
            sizes[identity] = size
    shared = {identity: {} for identity in where
              if identity in index or (len(where[identity]) > 1 and sizes[identity] >= SM.MIN_BYTES)}
    moved = saved = touched = 0
    for glb in files:
        result = SM.apply_to_file(glb, shared, index, dry_run)
        if result["moved"]:
            touched += 1
            moved += result["moved"]
            saved += result["bytes"]
    return {"files": touched, "meshes": moved, "bytes": saved, "prototypes": len(shared)}


def externalise(files: list[Path], index: dict, dry_run: bool) -> dict:
    """Move embedded textures into the image pool, package or prototype alike."""
    moved = saved = touched = 0
    for glb in files:
        result = SI.externalise(glb, dry_run)
        if not result["moved"]:
            continue
        touched += 1
        moved += result["moved"]
        saved += result["bytes"]
        if glb.parent == POOL:
            entry = index.setdefault(glb.stem, {})
            entry["images"] = dict(sorted({**entry.get("images", {}), **result["uris"]}.items()))
            if not dry_run:
                entry["sha256"] = SM.sha256(glb.read_bytes())
                entry["bytes"] = glb.stat().st_size
        else:
            SI.record_manifest(glb, result["uris"], dry_run)
    return {"files": touched, "images": moved, "bytes": saved}


def quantise(files: list[Path], dry_run: bool) -> dict:
    """Normals, tangents and morph deltas at the precision they need."""
    touched = saved = 0
    counts: dict[str, int] = {}
    for glb in files:
        result = QG.process(glb, False, True)
        if not result:
            continue
        touched += 1
        saved += result["old_bytes"] - len(result["data"])
        for label, count in result["counts"].items():
            counts[label] = counts.get(label, 0) + count
        if not dry_run:
            SM.write_package_glb(glb, result["data"])
    return {"files": touched, "bytes": saved, "accessors": counts}


# --- the figures a manifest records about its own GLB ------------------------

def resident_factor(package: Path, declared: float | None = None) -> float:
    """What the package says a byte of GLB costs resident, else the legacy 5.

    A publisher that has not written its publication record yet passes the
    figure it is about to write: on a territory's first publish there is
    nothing on disk to read it from, and guessing the legacy 5 would overstate
    a continent-v2 chunk fivefold.
    """
    if declared is not None:
        return float(declared)
    record = package / "publication.json"
    if record.is_file():
        try:
            declared = json.loads(record.read_text(encoding="utf-8")).get("geometryResidentFactor")
        except ValueError:
            declared = None
        if isinstance(declared, (int, float)):
            return float(declared)
    return LEGACY_RESIDENT_FACTOR


def _load(path: Path) -> tuple[dict, str] | None:
    try:
        text = path.read_bytes().decode("utf-8")
        manifest = json.loads(text)
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return (manifest, text) if isinstance(manifest, dict) else None


def _own_figures(manifest: dict, path: Path) -> bool:
    """Restate what this manifest says about the GLB it names. True if changed."""
    performance = manifest.get("performance")
    glb = path.parent / str(manifest.get("asset", {}).get("glb", "world.glb"))
    if not isinstance(performance, dict) or "glbBytes" not in performance or not glb.is_file():
        return False
    figures = {"glbBytes": glb.stat().st_size}
    if "nodes" in performance or "meshes" in performance:
        document = _document(glb)
        figures["nodes"] = len(document.get("nodes", []))
        figures["meshes"] = len(document.get("meshes", []))
    changed = False
    for key, value in figures.items():
        if key in performance and performance[key] != value:
            performance[key] = value
            changed = True
    return changed


SHARED_MESHES_KEY = "sharedMeshResidentBytes"


def _pool_index(directory: Path, indexes: dict) -> dict:
    """The index.json beside a pool's prototypes, read once per directory."""
    key = str(directory)
    if key not in indexes:
        try:
            indexes[key] = json.loads((directory / "index.json").read_text(encoding="utf-8")).get("prototypes", {})
        except (OSError, ValueError, AttributeError):
            indexes[key] = {}
    return indexes[key]


def prototype_figures(child: dict, child_path: Path, resident: float, indexes: dict) -> dict:
    """What the prototypes a chunk draws cost resident: identity -> bytes.

    The identity is the prototype file's stem, the key the client's
    ExternalMeshPool shares a mesh by, so the stream can count it once across
    every resident cell. Its size is the one the pool's index records (kept in
    step with the file by shared_meshes.reconcile, which finish() runs first),
    or the file's own where the index lacks it, at the cell's resident factor.
    A reference to no file draws nothing in the client and costs nothing.
    """
    figures = {}
    named = child.get(SM.MANIFEST_KEY)
    for uri in named if isinstance(named, dict) else {}:
        target = (child_path.parent / uri).resolve()
        identity = target.stem
        size = _pool_index(target.parent, indexes).get(identity, {}).get("bytes")
        if not isinstance(size, int):
            if not target.is_file():
                continue
            size = target.stat().st_size
        figures[identity] = max(figures.get(identity, 0), max(1, math.ceil(resident * size)))
    return dict(sorted(figures.items()))


def _set_prototypes(cell: dict, figures: dict) -> bool:
    """Write a cell's prototype figures beside its image figures. True if changed."""
    if not figures:
        return cell.pop(SHARED_MESHES_KEY, None) is not None
    if cell.get(SHARED_MESHES_KEY) == figures:
        return False
    if SHARED_MESHES_KEY not in cell and "sharedResourceResidentBytes" in cell:
        items = list(cell.items())
        cell.clear()
        for key, value in items:
            cell[key] = value
            if key == "sharedResourceResidentBytes":
                cell[SHARED_MESHES_KEY] = figures
    else:
        cell[SHARED_MESHES_KEY] = figures
    return True


def restamp(manifests, dry_run: bool = False, factor: float | None = None) -> list[str]:
    """Put every recorded GLB figure back in step with the file on disk.

    A manifest states its own GLB's size, and a parent states each streamed
    chunk's - with the resident-byte estimate the client admits chunks by. Both
    are read back and checked, so a pass that shrinks a GLB owes them an update.
    The pass that shrinks it most moves props into the pool, so a cell also
    states what its pooled prototypes cost (`sharedMeshResidentBytes`), and its
    standalone estimate counts them: geometry + images + prototypes.
    """
    updated: list[str] = []
    indexes: dict = {}
    for raw in manifests:
        path = Path(raw)
        loaded = _load(path)
        if loaded is None:
            continue
        manifest, text = loaded
        changed = _own_figures(manifest, path)
        stream = manifest.get("streamingChunks")
        cells = stream.get("chunks") if isinstance(stream, dict) else None
        resident = resident_factor(path.parent, factor)
        for cell in cells or []:
            child_path = (path.parent / str(cell.get("manifest", ""))).resolve()
            child = _load(child_path)
            if child is None:
                continue
            glb = child_path.parent / str(child[0].get("asset", {}).get("glb", "world.glb"))
            if not glb.is_file():
                continue
            size = glb.stat().st_size
            geometry = math.ceil(resident * size)
            prototypes = prototype_figures(child[0], child_path, resident, indexes)
            changed = _set_prototypes(cell, prototypes) or changed
            shared = (cell.get("sharedResourceResidentBytes") or {}).values()
            for key, value in (("glbBytes", size), ("geometryResidentBytes", geometry),
                               ("estimatedResidentBytes", geometry + sum(shared) + sum(prototypes.values()))):
                if key in cell and cell[key] != value:
                    cell[key] = value
                    changed = True
            if _own_figures(child[0], child_path):
                updated.append(SM.repo_relative(child_path))
                if not dry_run:
                    SM.write_manifest(child_path, child[0], child[1])
        if changed:
            updated.append(SM.repo_relative(path))
            if not dry_run:
                SM.write_manifest(path, manifest, text)
        if cells and _restate_publication(path.parent / "publication.json", cells, dry_run):
            updated.append(SM.repo_relative(path.parent / "publication.json"))
    return updated


def _restate_publication(record_path: Path, cells: list, dry_run: bool) -> bool:
    """The per-cell estimate a continent-v2 publication record copies from its
    manifest (publish_client.py `estimatedResidentMiB`). True if changed."""
    loaded = _load(record_path) if record_path.is_file() else None
    recorded = loaded[0].get("estimatedResidentMiB") if loaded else None
    if not isinstance(recorded, dict):
        return False
    changed = False
    for cell in cells:
        identity = cell.get("id")
        if identity in recorded and "estimatedResidentBytes" in cell:
            value = round(cell["estimatedResidentBytes"] / 1048576, 1)
            if recorded[identity] != value:
                recorded[identity] = value
                changed = True
    if changed and not dry_run:
        SM.write_manifest(record_path, loaded[0], loaded[1])
    return changed


def package_manifests(files: list[Path]) -> list[Path]:
    """The manifests that speak for these files: their own, and their parents'."""
    found = set()
    for glb in files:
        manifest = SM.manifest_for(glb)
        if manifest:
            found.add(manifest.resolve())
        # <package>/chunks/<name>/world.glb is spoken for by <package>/world.json
        if len(glb.parents) > 2:
            parent = glb.parents[2] / "world.json"
            if parent.is_file():
                found.add(parent.resolve())
    return sorted(found)


# --- what a publisher calls --------------------------------------------------

def finish(paths, *, dry_run: bool = False, quantise_pass: bool = True,
           factor: float | None = None, log=print) -> dict:
    """Run the three passes over the files under `paths`, then restate figures.

    `factor` is the resident bytes a byte of GLB is taken to cost, for a
    publisher whose publication record is not on disk yet.
    """
    files = glbs(paths)
    if not files:
        log("publish finish: no shipped GLB under " + ", ".join(str(p) for p in paths))
        return {}
    index = _index()
    before = set(POOL.glob("*.glb"))
    shared = share(files, index, dry_run)
    fresh = sorted(set(POOL.glob("*.glb")) - before)
    images = externalise(files + fresh, index, dry_run)
    if not dry_run:
        _save_index(index)
    quantised = quantise(files + fresh, dry_run) if quantise_pass else {"files": 0, "bytes": 0, "accessors": {}}
    manifests = package_manifests(files)
    reconciled = SM.reconcile(dry_run, prototypes={path.stem for path in fresh}, manifests=manifests)
    restated = restamp(manifests, dry_run, factor)
    verb = "would finish" if dry_run else "finished"
    log(f"{verb} {len(files)} files: "
        f"{shared['meshes']} meshes pooled ({len(fresh)} new prototypes), "
        f"{images['images']} images externalised, {quantised['files']} files quantised; "
        f"{(shared['bytes'] + images['bytes'] + quantised['bytes']) / 1e6:.0f} MB smaller")
    if reconciled or restated:
        log(f"  restated {len(set(restated))} manifests and {len(reconciled)} prototype hashes")
    return {"files": len(files), "shared": shared, "images": images, "quantised": quantised,
            "prototypes": [path.name for path in fresh], "reconciled": reconciled,
            "restamped": sorted(set(restated))}


def every_manifest() -> list[Path]:
    skip = {"source", "sources", "references", "captures", "godot-captures", "qa", "work"}
    return [path for path in sorted(MAPS.rglob("world.json"))
            if not {part.lower() for part in path.relative_to(MAPS).parts[:-1]} & skip]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="*", type=Path, help="packages or GLBs a publisher wrote")
    parser.add_argument("--restamp", action="store_true",
                        help="only restate recorded GLB figures, over every package")
    parser.add_argument("--no-quantise", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    options = parser.parse_args()
    if options.restamp:
        updated = restamp(every_manifest(), options.dry_run)
        print(f"{'would restate' if options.dry_run else 'restated'} {len(set(updated))} manifests")
        for path in sorted(set(updated))[:12]:
            print("  " + path)
        return 0
    if not options.paths:
        parser.error("give the paths a publisher wrote, or --restamp")
    finish(options.paths, dry_run=options.dry_run, quantise_pass=not options.no_quantise)
    return 0


if __name__ == "__main__":
    sys.exit(main())
