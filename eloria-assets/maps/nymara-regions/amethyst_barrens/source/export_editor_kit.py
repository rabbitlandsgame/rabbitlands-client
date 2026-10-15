"""Export the Amethyst Barrens kit pieces the generated models do not cover.

The rock, crystal, ground cover and most prospector props are generated models
seated by `prepare_meshy_kit.py`. This writes the rest as editor prototypes,
`godot-client/world_authoring/regions/amethyst_barrens/assets/prototypes/
kit-<name>.glb`: loose grey rubble with a glint of shard for the ground between
features, and a crystal-burning brazier, a workbench and a survey signpost for
the camps. Each is shaped like the migrated prototypes: one root named after the
file, one placement node, one mesh node per material, and the territory's shared
textures referenced by URI rather than embedded.

The rubble's stone is the territory's own storm rock lifted to a mid grey with a
trace of its violet veins; that texture is derived here and written beside the
others under its content digest.

A piece whose name holds a walk-through word (asset_catalog.gd
WALK_THROUGH_WORDS: "scree", "crystal", ...) starts walk-through in the
palette; the rest start solid.

Run from anywhere: `python export_editor_kit.py` (add `--check` to only verify
that the committed files match what this builds today).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "_toolkit"))

from amberwood import crystalcraft as CC  # noqa: E402
from amberwood import mesh as M  # noqa: E402
from amberwood import props as PROPS  # noqa: E402
from amberwood.noise import Rng  # noqa: E402
from amberwood.stonework import MeshGroup  # noqa: E402

CLIENT = HERE.parents[4]
PROTOTYPES = CLIENT / "godot-client/world_authoring/regions/amethyst_barrens/assets/prototypes"
TEXTURES = PROTOTYPES.parent / "textures"
TEXTURE_URI = "../textures/"

STORM_ROCK_BASE = "c7a5783de549df31ae6d34299e65553254f46b9ac19350dd079a3e9f179fcee4"
GREY = "barrens_grey_rock"
CRYSTAL = "amethyst_crystal"

# glTF material name -> (base colour, ORM, normal texture digests, base colour
# factor, metallic, roughness, emissive or None, double sided). The first
# entries are the migrated prototypes' own definitions; a base of None is one of
# the derived rock textures below.
MATERIALS = {
    CRYSTAL: ("6c72a20af3c3a103a45d58f1b58a483dd550705958963cc508ae7c187df5eaf3",
              "50c00d127d279501874ccb99fde85c0a2f5d72bd2f6ca72fecd220e0fd31c959",
              "1b416116cedf6854f49e1d4c7365f60e193d6384cf3875ff8de99ab9808f754e",
              (1.0, 1.0, 1.0, 1.0), 0.0, 0.1, (0.196, 0.088, 0.32), False),
    "timber_grey": ("9e840c611ba957b1cb1421eca2a4eab4884aea934ef633bb5ac65cacfe8df0be",
                    "06b2238495c21e9f2f051941c8bafb10fdcb9900dfa855367b918c6de44d770d",
                    "4680650bcb14d3a120707e93004c4fe7db2ebdc8d57e8c567d360d65ac0836a4",
                    (1.0, 1.0, 1.0, 1.0), 0.0, 0.96, None, False),
    "timber_dark": ("a58bcee53f47ac1441871efda0cbe0023f55771cbbd0ab783430391739669c6c",
                    "1e5f12e87291a8ad077f017e3a2715de967e545db77ca342953e258b04512621",
                    "af2a3dc164769a1f70404a3f45e183d4be6bd92ad95fe870f571ec719af81cc2",
                    (1.0, 1.0, 1.0, 1.0), 0.0, 0.94, None, False),
    "dark_iron": ("843382be4eda772daf6b622d49d8f700605171c95c22fdeddc1d4512134dab68",
                  "1d081298f165977ff2d99ff644947a7c1b6053edab80b38ed96c352e92ffea44",
                  "ab59855a4121a56093cf56b41b5461fd7cfa365951edab16f3204be26c52c09b",
                  (1.0, 1.0, 1.0, 1.0), 1.0, 0.72, None, False),
    GREY: (None, "e353fad467123931b67a85a250604c22f64dd5738be04a19aab7eb51246ed2ef",
           "962f4cd3b1ca9883a0f7dc6e150b9aa098e00140bc7788108f308abfe2ffccb0",
           (1.0, 1.0, 1.0, 1.0), 0.0, 0.92, None, False),
}
# How much of the storm rock's violet the derived rock keeps: (grey lift,
# chroma kept in the stone, chroma kept in the veins).
ROCK_TEXTURES = {GREY: (1.9, 0.10, 0.6)}
# The toolkit's material names -> this territory's.
TOOLKIT_MATERIALS = {
    "timber_warm": "timber_grey", "timber_grey": "timber_grey", "timber_dark": "timber_dark",
    "carved_wood": "timber_dark", "bark_dark": "timber_dark", "dark_iron": "dark_iron",
    "amber_resin": CRYSTAL, "amber_glass": CRYSTAL, "rubble_stone": GREY, "cliff_rock": GREY,
    "ashlar": GREY,
}


def rock_texture(name: str) -> bytes:
    """The storm rock lifted to a mid grey, its violet veins kept by `name`'s share."""
    lift, stone, vein = ROCK_TEXTURES[name]
    source = np.asarray(Image.open(TEXTURES / f"{STORM_ROCK_BASE}.png").convert("RGB"), dtype=np.float64)
    grey = source @ np.array([0.299, 0.587, 0.114])
    chroma = source - grey[..., None]
    veins = np.clip((np.linalg.norm(chroma, axis=-1) - 12.0) / 14.0, 0.0, 1.0)[..., None]
    lifted = grey[..., None] * lift + chroma * (stone * (1.0 - veins) + vein * veins)
    lifted *= np.array([0.98, 0.99, 1.02])
    out = io.BytesIO()
    Image.fromarray(np.clip(np.round(lifted), 0, 255).astype(np.uint8)).save(out, format="PNG")
    return out.getvalue()


def facet_outward(piece: M.Mesh) -> M.Mesh:
    """Flat-shade `piece`, turning any triangle that faces into the solid.

    `crystalcraft.facet` takes each face's normal from its winding, and the
    toolkit's cylinder winds its sides inward of the normals it was built with,
    which would leave a faceted column shaded black and culled from outside.
    """
    tris = piece.indices.reshape(-1, 3)
    built = piece.normals[tris].sum(axis=1)
    CC.facet(piece)
    faces = piece.normals.reshape(-1, 3, 3)[:, 0]
    inward = np.einsum("ij,ij->i", faces, built) < 0.0
    if inward.any():
        order = piece.indices.reshape(-1, 3)
        order[inward] = order[inward][:, ::-1]
        piece.normals.reshape(-1, 3, 3)[inward] *= -1.0
        piece.indices = order.reshape(-1)
    return piece


def rock(radius: float, seed: int, material: str = GREY, squash: float = 0.62,
         stretch: tuple[float, float] = (1.0, 1.0), detail: int = 1) -> M.Mesh:
    """One faceted lump of stone, flat-shaded like the crystal it carries."""
    lump = M.icosphere(radius, detail, material=material)
    lump.jitter(radius * 0.22, seed=seed)
    lump.scale(stretch[0], squash, stretch[1])
    facet_outward(lump)
    lump.project_uv_triplanar(0.32)
    return lump


def rubble_scree(radius: float, seed: int) -> list[M.Mesh]:
    """Broken grey stones lying flat, with a glint of shard here and there."""
    rng = Rng(seed + 2100)
    parts = []
    for index in range(int(rng.integers(8, 14))):
        angle = float(rng.uniform(0.0, math.tau))
        reach = radius * math.sqrt(float(rng.uniform(0.0, 1.0)))
        size = float(rng.uniform(0.2, 0.6))
        parts.append(rock(size, seed + index, material=GREY,
                          squash=float(rng.uniform(0.3, 0.5)),
                          stretch=(float(rng.uniform(0.8, 1.3)), float(rng.uniform(0.8, 1.3))),
                          detail=0 if size < 0.45 else 1)
                     .translate(math.cos(angle) * reach, size * 0.04, math.sin(angle) * reach))
    parts.append(CC.vein_scatter(radius=radius * 0.8, count=int(rng.integers(2, 4)),
                                 seed=seed + 50, material=CRYSTAL, height=0.35))
    return parts


def glow_brazier(seed: int) -> list[M.Mesh]:
    """An iron brazier burning crystal, the camps' night light."""
    return list(PROPS.brazier(seed=seed).parts)


def workbench(seed: int) -> list[M.Mesh]:
    """A trestle bench with the vice and chisels crystal is dressed with."""
    return list(PROPS.workbench(seed=seed).parts)


def signpost(seed: int) -> list[M.Mesh]:
    """A two-armed survey signpost."""
    return list(PROPS.signpost(seed=seed, arms=2).parts)


PIECES = {
    "kit-rubble-scree-0": lambda: rubble_scree(1.8, seed=0),
    "kit-rubble-scree-1": lambda: rubble_scree(2.6, seed=1),
    "kit-rubble-scree-2": lambda: rubble_scree(3.4, seed=2),
    "kit-glow-brazier": lambda: glow_brazier(seed=0),
    "kit-prospector-workbench": lambda: workbench(seed=0),
    "kit-survey-signpost": lambda: signpost(seed=0),
}


class _Glb:
    """The migrated prototypes' GLB layout, written directly."""

    def __init__(self) -> None:
        self.doc: dict = {"asset": {"version": "2.0", "generator": "Eloria Amethyst editor kit"},
                          "accessors": [], "bufferViews": [], "meshes": [], "materials": [],
                          "textures": [], "images": [], "nodes": [],
                          "samplers": [{"magFilter": 9729, "minFilter": 9987,
                                        "wrapS": 10497, "wrapT": 10497}]}
        self.buffer = bytearray()
        self._materials: dict[str, int] = {}
        self._images: dict[str, int] = {}

    def _accessor(self, values: np.ndarray, kind: str, component: int, target: int,
                  bounds: bool = False) -> int:
        while len(self.buffer) % 4:
            self.buffer.append(0)
        raw = values.tobytes()
        self.doc["bufferViews"].append({"buffer": 0, "byteOffset": len(self.buffer),
                                        "byteLength": len(raw), "target": target})
        self.buffer += raw
        accessor = {"bufferView": len(self.doc["bufferViews"]) - 1, "componentType": component,
                    "count": int(len(values)), "type": kind}
        if bounds:
            accessor["min"] = [float(v) for v in values.min(axis=0)]
            accessor["max"] = [float(v) for v in values.max(axis=0)]
        self.doc["accessors"].append(accessor)
        return len(self.doc["accessors"]) - 1

    def _texture(self, digest: str, name: str) -> int:
        if digest not in self._images:
            self.doc["images"].append({"uri": TEXTURE_URI + digest + ".png", "name": name})
            self.doc["textures"].append({"sampler": 0, "source": len(self.doc["images"]) - 1})
            self._images[digest] = len(self.doc["textures"]) - 1
        return self._images[digest]

    def material(self, name: str, digests: dict[str, str]) -> int:
        if name in self._materials:
            return self._materials[name]
        base, orm, normal, factor, metallic, roughness, emissive, double = MATERIALS[name]
        base = base or digests[name]
        orm_index = self._texture(orm, f"{name}_orm")
        material = {"name": name, "pbrMetallicRoughness": {
            "baseColorFactor": list(factor), "metallicFactor": metallic,
            "roughnessFactor": roughness,
            "baseColorTexture": {"index": self._texture(base, f"{name}_basecolor")},
            "metallicRoughnessTexture": {"index": orm_index}},
            "occlusionTexture": {"index": orm_index},
            "normalTexture": {"index": self._texture(normal, f"{name}_normal")}}
        if emissive:
            material["emissiveFactor"] = list(emissive)
        if double:
            material["doubleSided"] = True
        self.doc["materials"].append(material)
        self._materials[name] = len(self.doc["materials"]) - 1
        return self._materials[name]

    def mesh(self, name: str, piece: M.Mesh, material: int) -> int:
        positions = np.ascontiguousarray(piece.positions, dtype="<f4")
        normals = piece.normals / np.maximum(np.linalg.norm(piece.normals, axis=1, keepdims=True), 1e-9)
        indices = piece.indices.astype("<u2" if len(positions) <= 65535 else "<u4")
        self.doc["meshes"].append({"name": name, "primitives": [{
            "attributes": {
                "POSITION": self._accessor(positions, "VEC3", 5126, 34962, bounds=True),
                "NORMAL": self._accessor(np.ascontiguousarray(normals, dtype="<f4"), "VEC3", 5126, 34962),
                "TEXCOORD_0": self._accessor(np.ascontiguousarray(piece.uvs, dtype="<f4"), "VEC2",
                                             5126, 34962)},
            "indices": self._accessor(np.ascontiguousarray(indices), "SCALAR",
                                      5123 if indices.dtype == np.dtype("<u2") else 5125, 34963),
            "mode": 4, "material": material}]})
        return len(self.doc["meshes"]) - 1

    def payload(self) -> bytes:
        while len(self.buffer) % 4:
            self.buffer.append(0)
        self.doc["buffers"] = [{"byteLength": len(self.buffer)}]
        text = json.dumps(self.doc, separators=(",", ":")).encode("utf-8")
        while len(text) % 4:
            text += b" "
        total = 12 + 8 + len(text) + 8 + len(self.buffer)
        return (struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(text), 0x4E4F534A)
                + text + struct.pack("<II", len(self.buffer), 0x004E4942) + bytes(self.buffer))


def _by_material(parts: list[M.Mesh]) -> dict[str, M.Mesh]:
    """Every part under this territory's material, merged into one mesh each."""
    grouped: dict[str, list[M.Mesh]] = {}
    for part in parts:
        for piece in (part.parts if isinstance(part, MeshGroup) else [part]):
            if piece.triangle_count == 0:
                continue
            name = TOOLKIT_MATERIALS.get(piece.material, piece.material)
            if name not in MATERIALS:
                raise ValueError(f"no territory material for {piece.material}")
            grouped.setdefault(name, []).append(piece.with_material(name))
    return {name: M.merge(pieces, name) for name, pieces in sorted(grouped.items())}


def build(stem: str, digests: dict[str, str]) -> bytes:
    writer = _Glb()
    placement = "Kit_" + stem.removeprefix("kit-").replace("-", "_")
    children = []
    for name, piece in _by_material(PIECES[stem]()).items():
        mesh = writer.mesh(f"{placement}__{name}", piece, writer.material(name, digests))
        writer.doc["nodes"].append({"name": f"{placement}__{name}", "mesh": mesh})
        children.append(len(writer.doc["nodes"]) - 1)
    writer.doc["nodes"].append({"name": placement, "children": children})
    holder = len(writer.doc["nodes"]) - 1
    writer.doc["nodes"].append({"name": stem, "children": [holder], "translation": [0.0, 0.0, 0.0]})
    writer.doc["scenes"] = [{"nodes": [len(writer.doc["nodes"]) - 1]}]
    writer.doc["scene"] = 0
    return writer.payload()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify, do not write")
    args = parser.parse_args()
    stale = []
    digests = {}
    for name in ROCK_TEXTURES:
        png = rock_texture(name)
        digest = hashlib.sha256(png).hexdigest()
        digests[name] = digest
        target = TEXTURES / f"{digest}.png"
        if not target.exists():
            if args.check:
                stale.append(target.name)
            else:
                target.write_bytes(png)
                print(f"wrote {target.name} ({name})")
    for stem in PIECES:
        payload = build(stem, digests)
        target = PROTOTYPES / f"{stem}.glb"
        if args.check:
            if not target.exists() or target.read_bytes() != payload:
                stale.append(stem)
            continue
        if not target.exists() or target.read_bytes() != payload:
            target.write_bytes(payload)
            print(f"wrote {target.name} ({len(payload)} bytes)")
    if stale:
        print("stale: " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
