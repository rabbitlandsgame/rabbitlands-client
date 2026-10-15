"""image_policy.py: what the continent-v2 publisher changes in a source document's images before the chunk exporter
hashes them, for the GPU memory a streamed cell holds. The rules live in image_policy.json beside this file and name
images by the sha256 of their bytes, so a ground or kit that changes its texture leaves the rule behind instead of
silently inheriting it.

  resample   sha -> {size, derived}. The image is replaced by the derived file in the shared pool. The v2 ground
             albedos (forest, rock) are 1254 px, which no block-compressed format holds (4x4 blocks), so
             build_vram_textures.py leaves them RGBA8: 8 MiB each with mips, resident in almost every cell. The
             derived copy is resampled, wrapping at the edges (they tile), to the next multiple of 4 (1256 px) and is
             a new, v2-only image whose BC7 sidecar holds 2 MiB; the twelve territories' pool keeps the original bytes.
  keepUncompressed   sha -> {what, why, retiredDerived}. An image that ships with its own bytes, whatever it costs:
             no resample rule may name it (check reports one; apply, which every publish runs, refuses to publish
             with one, so a rule that comes back through a merge stops the publish). The castle plaza and court paving (e9adde18, 1254 px)
             is one by the owner's call of 2026-10-03: its BC7 copy blurred the hub, so the client uploads it RGBA8
             again. retiredDerived is the copy its old rule swapped in, which a republished cell no longer names.

The rule acts on the documents, before scene_io.Exporter.add sees them: the exporter hashes, counts
(sharedResourceResidentBytes) and writes every image a transferred material reaches while it adds roots, so a change
afterwards would leave the old image counted, listed and on disk.

A derived file is RECORDED, never recomputed at publish: `--record` writes it into the shared pool and its sha into
image_policy.json; the publisher only reads it (and refuses a pool copy that does not hash to the record), so a
republish on another machine with another numpy or zlib gives the same package.

    python -B eloria-assets/maps/continent-v2/_continent_v2/image_policy.py --check    # every rule holds
    python -B eloria-assets/maps/continent-v2/_continent_v2/image_policy.py --record   # (re)derive, rewrite the json
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
POLICY_FILE = HERE / "image_policy.json"
SHARED = HERE / "shared-assets"
SCHEMA = "eloria-continent-v2-image-policy-v1"
LANCZOS_A = 3


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_policy(path: Path = POLICY_FILE) -> dict:
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    if policy.get("schema") != SCHEMA:
        raise ValueError(f"{path}: schema {policy.get('schema')!r}, not {SCHEMA}")
    return policy


def _lanczos(x):
    x = np.asarray(x, np.float64)
    out = np.sinc(x) * np.sinc(x / LANCZOS_A)
    out[np.abs(x) >= LANCZOS_A] = 0.0
    return out


def _wrap_weights(source: int, target: int) -> np.ndarray:
    """(target, source) Lanczos-3 resampling weights for a texture that tiles: source indices wrap."""
    scale = source / target
    support = LANCZOS_A * max(1.0, scale)
    weights = np.zeros((target, source), np.float64)
    for i in range(target):
        centre = (i + 0.5) * scale - 0.5
        first, last = math.floor(centre - support), math.ceil(centre + support)
        taps = np.arange(first, last + 1)
        w = _lanczos((taps - centre) / max(1.0, scale))
        w /= w.sum()
        np.add.at(weights[i], taps % source, w)
    return weights


def resample_wrapped(data: bytes, size: tuple[int, int]) -> bytes:
    """The image resized to `size` (width, height), Lanczos-3, wrapping at every edge, every channel (alpha too:
    the ground albedos' alpha is a blend weight), as an optimised PNG."""
    from PIL import Image
    with Image.open(io.BytesIO(data)) as picture:
        mode = "RGBA" if picture.mode in ("RGBA", "LA", "PA") or "transparency" in picture.info else "RGB"
        array = np.asarray(picture.convert(mode)).astype(np.float64)
    rows = _wrap_weights(array.shape[0], int(size[1]))
    cols = _wrap_weights(array.shape[1], int(size[0]))
    out = np.empty((int(size[1]), int(size[0]), array.shape[2]), np.float64)
    for channel in range(array.shape[2]):
        out[..., channel] = rows @ array[..., channel] @ cols.T
    result = Image.fromarray(np.clip(np.rint(out), 0, 255).astype(np.uint8), mode)
    buffer = io.BytesIO()
    result.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def derived_bytes(rule: dict, shared: Path) -> bytes:
    """The recorded derived image, read from the shared pool and checked against its record."""
    path = Path(shared) / f"{rule['derived']}.png"
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing: run image_policy.py --record (it writes the derived images)")
    data = path.read_bytes()
    if sha256(data) != rule["derived"]:
        raise ValueError(f"{path} does not hash to its record")
    return data


def _image_shas(doc: dict, body: bytes) -> list[str | None]:
    shas = []
    for image in doc.get("images", []):
        view_index = image.get("bufferView")
        if view_index is None:
            shas.append(None)
            continue
        view = doc["bufferViews"][view_index]
        start = view.get("byteOffset", 0)
        shas.append(sha256(body[start:start + view["byteLength"]]))
    return shas


def apply(doc: dict, body: bytes, shared: Path, policy: dict | None = None) -> tuple[dict, bytes, dict]:
    """The policy applied to one source document (its glTF JSON and binary chunk), in place on `doc`; returns
    (doc, body, stats). A resampled image's derived bytes are appended to the binary as a new buffer view."""
    policy = load_policy() if policy is None else policy
    resample = policy.get("resample", {})
    kept = sorted(set(resample) & set(policy.get("keepUncompressed", {})))
    if kept:
        raise ValueError("image policy: a resample rule names an image the policy keeps uncompressed "
                         "(keepUncompressed): " + ", ".join(digest[:12] for digest in kept))
    stats = {"imagesResampled": 0, "resampledImages": []}
    extra = bytearray()
    for index, digest in enumerate(_image_shas(doc, body)):
        rule = resample.get(digest) if digest else None
        if rule is None:
            continue
        data = derived_bytes(rule, shared)
        base = len(body) + len(extra)
        pad = (-base) % 4
        extra.extend(b"\0" * pad)
        doc["bufferViews"].append({"buffer": 0, "byteOffset": base + pad, "byteLength": len(data)})
        extra.extend(data)
        image = doc["images"][index]
        image["bufferView"] = len(doc["bufferViews"]) - 1
        image["mimeType"] = "image/png"
        stats["imagesResampled"] += 1
        stats["resampledImages"].append(digest)
    if extra:
        body = bytes(body) + bytes(extra)
        if doc.get("buffers"):
            doc["buffers"][0]["byteLength"] = len(body)
    return doc, body, stats


def check(policy: dict, shared: Path) -> list[str]:
    """Problems with the policy against the pool: a derived image missing or not hashing to its record, a derived
    size that is not a multiple of 4, a resample rule for an image the policy keeps uncompressed."""
    problems = []
    for digest in sorted(set(policy.get("resample", {})) & set(policy.get("keepUncompressed", {}))):
        problems.append(f"resample {digest[:12]}: the policy keeps this image uncompressed (keepUncompressed)")
    for digest, rule in policy.get("resample", {}).items():
        if any(int(v) % 4 for v in rule["size"]):
            problems.append(f"resample {digest[:12]}: {rule['size']} is not a multiple of 4")
        try:
            derived_bytes(rule, shared)
        except (OSError, ValueError) as error:
            problems.append(f"resample {digest[:12]}: {error}")
    return problems


def record(policy: dict, shared: Path) -> dict:
    """Derives every resampled image from its source in the pool, writing the derived files into the pool; returns
    the policy with the derived shas."""
    from PIL import Image
    for digest, rule in policy.get("resample", {}).items():
        source = sorted(Path(shared).glob(digest + ".*"))[0]
        data = source.read_bytes()
        with Image.open(io.BytesIO(data)) as picture:
            rule["sourceSize"] = list(picture.size)
        if not rule.get("size"):
            rule["size"] = [4 * math.ceil(v / 4) for v in rule["sourceSize"]]
        derived = resample_wrapped(data, tuple(rule["size"]))
        rule["derived"] = sha256(derived)
        rule["derivedBytes"] = len(derived)
        (Path(shared) / f"{rule['derived']}.png").write_bytes(derived)
    return policy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--policy", type=Path, default=POLICY_FILE)
    parser.add_argument("--shared", type=Path, default=SHARED)
    parser.add_argument("--record", action="store_true", help="derive the resampled images and record them")
    parser.add_argument("--check", action="store_true", help="every rule holds against the pool")
    options = parser.parse_args()
    policy = load_policy(options.policy)
    if options.record:
        policy = record(policy, options.shared)
        options.policy.write_text(json.dumps(policy, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"recorded {len(policy.get('resample', {}))} resampled images in {options.policy}")
    problems = check(policy, options.shared)
    for problem in problems:
        print("PROBLEM", problem)
    print(f"image policy: {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
