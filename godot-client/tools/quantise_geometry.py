#!/usr/bin/env python3
"""Store vertex data at the precision it needs, not at 32 bits everywhere.

Added 2026-10-13 for Eloria Client.

    python godot-client/tools/quantise_geometry.py --dry-run
    python godot-client/tools/quantise_geometry.py --archive ../archive/quantised-2026-10-13

Two passes, which differ in what they need from the engine:

  weights   WEIGHTS_0/1 become normalized unsigned bytes. The core glTF spec
            has always allowed that, so nothing has to support anything: a
            weight is a fraction of one, and 1/255 of a vertex's influence is
            far below what a skin shows. Each vertex's bytes are made to sum
            to exactly 255, because the spec requires the weights of a vertex
            to sum to one and a loader may trust it.

  phase 1   NORMAL and TANGENT become normalized signed bytes, and a morph
            target's POSITION deltas normalized signed shorts. These are
            KHR_mesh_quantization, which stock Godot 4.7.2 accepts once
            src/world/gltf_quantization.gd is registered (measured: a normal
            comes back within 0.37 degrees, a position bit-identical).

What is deliberately left at 32 bits:
  * base POSITION, which does not fit [-1, 1] and so needs the dequantisation
    transform on the node - a separate decision, with collision and grounding
    to measure first;
  * TEXCOORD, because map UVs tile past 1.0;
  * a morph POSITION accessor whose own deltas exceed +-1 (ten of 2,219 do,
    the worst at 1.55): the normalized form cannot hold them.

Everything is archived before it is written, the pass is idempotent (an
accessor that is already an integer type is left alone), and the sha256/bytes
build records follow the files.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

CLIENT = Path(__file__).resolve().parents[1]
REPO = CLIENT.parent
sys.path.insert(0, str(CLIENT / "tools"))
sys.path.insert(0, str(REPO / "eloria-assets" / "tools"))

import shared_meshes as SM  # noqa: E402
from shrink_actor_textures import records_from_manifest, repo_path, sha256, update_records  # noqa: E402

EXTENSION = "KHR_mesh_quantization"
FLOAT = 5126
BYTE = 5120
UNSIGNED_BYTE = 5121
SHORT = 5122
COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
ACTORS = CLIENT / "assets" / "actors" / "native"
MAPS = REPO / "eloria-assets" / "maps"


def float_accessor(document: dict, binary: bytes, index: int) -> np.ndarray | None:
    accessor = document["accessors"][index]
    if accessor.get("componentType") != FLOAT or "bufferView" not in accessor:
        return None
    width = COMPONENTS[accessor["type"]]
    view = document["bufferViews"][accessor["bufferView"]]
    stride = view.get("byteStride", 4 * width)
    if stride != 4 * width:
        return None
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    values = np.frombuffer(binary, np.float32, count=accessor["count"] * width, offset=start)
    return values.reshape(accessor["count"], width).astype(np.float64)


def quantise_weights(values: np.ndarray) -> np.ndarray:
    """Normalized bytes whose rows sum to exactly 255, as the spec asks."""
    scaled = np.clip(values, 0.0, 1.0) * 255.0
    out = np.floor(scaled).astype(np.int32)
    remainder = scaled - out
    for row in np.nonzero(out.sum(1) != 255)[0]:
        missing = 255 - int(out[row].sum())
        if missing > 0:  # hand the rounding loss to the largest fractions
            for column in np.argsort(-remainder[row])[:missing]:
                out[row, column] += 1
        else:
            for column in np.argsort(out[row])[::-1][:-missing]:
                if out[row, column] > 0:
                    out[row, column] -= 1
    return out.astype(np.uint8)


class Rewriter:
    """Appends quantised accessors to a document's binary chunk."""

    def __init__(self, document: dict, binary: bytes):
        self.document = document
        self.binary = bytearray(binary)
        self.saved = 0
        self.counts: dict[str, int] = {}

    def _append(self, data: bytes, stride: int) -> int:
        self.binary.extend(b"\0" * ((-len(self.binary)) % 4))
        self.document["bufferViews"].append(
            {"buffer": 0, "byteOffset": len(self.binary), "byteLength": len(data), "byteStride": stride})
        self.binary.extend(data)
        return len(self.document["bufferViews"]) - 1

    def replace(self, index: int, quantised: np.ndarray, component: int, kind: str, label: str) -> None:
        accessor = self.document["accessors"][index]
        width = COMPONENTS[accessor["type"]]
        element = quantised.dtype.itemsize * width
        stride = (element + 3) // 4 * 4
        rows = len(quantised)
        if stride != element:  # 4-byte element alignment, as glTF requires
            padded = np.zeros((rows, stride), np.uint8)
            padded[:, :element] = quantised.view(np.uint8).reshape(rows, element)
            data = padded.tobytes()
        else:
            data = np.ascontiguousarray(quantised).tobytes()
        before = accessor["count"] * width * 4
        accessor["bufferView"] = self._append(data, stride)
        accessor["componentType"] = component
        accessor["normalized"] = True
        accessor.pop("byteOffset", None)
        if "min" in accessor or "max" in accessor:
            accessor["min"] = quantised.min(axis=0).astype(float).tolist()
            accessor["max"] = quantised.max(axis=0).astype(float).tolist()
        self.saved += before - len(data)
        self.counts[label] = self.counts.get(label, 0) + 1
        _ = kind


def process(path: Path, weights: bool, phase1: bool) -> dict | None:
    document, binary = SM.read_glb(path)
    original = path.read_bytes()
    out = Rewriter(document, binary)
    needs_extension = False
    for mesh in document.get("meshes", []):
        for primitive in mesh["primitives"]:
            attributes = primitive["attributes"]
            if weights:
                for name in ("WEIGHTS_0", "WEIGHTS_1"):
                    index = attributes.get(name)
                    values = float_accessor(document, out.binary, index) if index is not None else None
                    if values is not None:
                        out.replace(index, quantise_weights(values), UNSIGNED_BYTE, "weights", name)
            if phase1:
                for name in ("NORMAL", "TANGENT"):
                    index = attributes.get(name)
                    values = float_accessor(document, out.binary, index) if index is not None else None
                    if values is None:
                        continue
                    # Normalized bytes hold [-1, 1], so a vector longer than
                    # that clips and comes back pointing somewhere else. glTF
                    # says these are unit length and most are, but some of the
                    # kit's are not, and those keep their floats.
                    lengths = np.linalg.norm(values[:, :3], axis=1)
                    lengths = lengths[np.isfinite(lengths) & (lengths > 0)]
                    if lengths.size and (lengths.max() > 1.001 or lengths.min() < 0.999):
                        continue
                    quantised = np.clip(np.rint(values * 127.0), -127, 127).astype(np.int8)
                    out.replace(index, quantised, BYTE, "normal", name)
                    needs_extension = True
                for target in primitive.get("targets", []):
                    index = target.get("POSITION")
                    values = float_accessor(document, out.binary, index) if index is not None else None
                    # A delta outside [-1, 1] has no normalized form; ten
                    # accessors in the tree are like that, the worst at 1.55.
                    if values is None or np.abs(values).max() > 1.0:
                        continue
                    quantised = np.clip(np.rint(values * 32767.0), -32767, 32767).astype(np.int16)
                    out.replace(index, quantised, SHORT, "morph", "MORPH_POSITION")
                    needs_extension = True
    if not out.counts:
        return None
    if needs_extension:
        for key in ("extensionsUsed", "extensionsRequired"):
            document[key] = sorted(set(document.get(key, [])) | {EXTENSION})
    document, packed = SM._prune(document, bytes(out.binary))
    data = SM.write_glb(document, packed)
    return {"path": path, "data": data, "old_sha": sha256(original), "old_bytes": len(original),
            "counts": out.counts}


def targets(sets: list[str]) -> list[Path]:
    found: list[Path] = []
    if "actors" in sets:
        found += sorted(ACTORS.rglob("*.glb"))
    if "maps" in sets:
        # Only what ships. A kit delivery under source/ is an authoring input,
        # read by the per-region prepare_meshy_kit scripts, which decode floats
        # and nothing else; quantising those would break the next kit run.
        skip = {"source", "sources", "references", "captures", "godot-captures", "qa", "work"}
        for path in sorted(MAPS.rglob("*.glb")):
            if path.name.startswith("world-lod"):
                continue
            if {part.lower() for part in path.relative_to(MAPS).parts[:-1]} & skip:
                continue
            found.append(path)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sets", default="actors,maps")
    parser.add_argument("--passes", default="weights,phase1", help="weights, phase1, or both")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    options = parser.parse_args()
    if not options.dry_run and not options.archive:
        parser.error("--archive is required unless --dry-run")
    sets = [s for s in options.sets.split(",") if s]
    passes = [p for p in options.passes.split(",") if p]

    results = []
    totals: dict[str, int] = {}
    files = targets(sets)
    for position, path in enumerate(files, 1):
        result = process(path, "weights" in passes, "phase1" in passes)
        if result:
            results.append(result)
            for label, count in result["counts"].items():
                totals[label] = totals.get(label, 0) + count
        if position % 500 == 0 or position == len(files):
            saved = sum(r["old_bytes"] - len(r["data"]) for r in results)
            print(f"  [{position}/{len(files)}] {len(results)} files, {saved / 1e6:.0f} MB smaller", flush=True)
    saved = sum(r["old_bytes"] - len(r["data"]) for r in results)
    print(f"{'would rewrite' if options.dry_run else 'rewrote'} {len(results)} of {len(files)} files, "
          f"{saved / 1e6:.0f} MB smaller; accessors: "
          + ", ".join(f"{label} {count}" for label, count in sorted(totals.items())))
    if options.dry_run or not results:
        return 0

    archive = options.archive.resolve()
    manifest_path = archive / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    earlier = {path: (entry.get("newSha256"), entry.get("newBytes")) for path, entry in manifest.items()}
    for result in results:
        target = archive / repo_path(result["path"])
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result["path"], target)
        if target.read_bytes() != result["path"].read_bytes() and repo_path(result["path"]) not in manifest:
            raise SystemExit(f"archive copy of {repo_path(result['path'])} does not match the file being replaced")
    for result in results:
        result["path"].write_bytes(result["data"])
        entry = manifest.setdefault(repo_path(result["path"]),
                                    {"sha256": result["old_sha"], "bytes": result["old_bytes"]})
        entry.update({"newSha256": sha256(result["data"]), "newBytes": len(result["data"])})
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    updated = update_records(*records_from_manifest(manifest, earlier))
    if any(str(MAPS) in str(result["path"]) for result in results):
        updated += SM.reconcile()
    print(f"updated {len(updated)} build records")
    for path in updated[:12]:
        print("  " + str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
