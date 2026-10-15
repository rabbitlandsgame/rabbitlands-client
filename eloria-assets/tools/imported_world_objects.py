#!/usr/bin/env python3
"""World-object models that were made outside the procedural generator.

Added 2026-10-02 for Eloria Client.

`build_native_world_object_glbs.py` writes `data/world/objects.json` whole,
from the procedural catalogue in `harvestables.py`. A model made anywhere else
- the Meshy harvest nodes reviewed for the south-west isle - would be lost the
next time that generator ran, because nothing in the catalogue describes it.
This table is what describes it. The generator measures each listed GLB where
it already sits under `assets/world/harvestables/`, writes its registry entry
beside the procedural ones, and points the resource label at it when the model
answers that label.

Reviewed interactive replacements are listed in `IMPORTED_INTERACTIVES`.
They retain the existing model id and role label, and the generator skips
writing their procedural fallback. Both tables are checked before writing.

The GLB is not written here. It is copied in, once, from the reviewed kit; the
registry records its sha256 so a file swapped in later without regenerating
the registry is caught by `tests/test_world_object_models.py` rather than
drawing a model the registry measured as something else.

Imported nodes are held to a wider triangle band than the procedural ones
(owner decision 2026-10-02, island content plan item 17): a modelled shrub
with fruit on it reads at the gameplay camera where a 424-triangle silhouette
loses its leaf cards. The generator refuses a listed GLB outside that band
before it writes anything, and the test holds the committed registry to it.

Imported nodes are also held to the procedural kit's brightness. Every
procedural node multiplies its texture by a palette colour (a baseColorFactor
of about 0.36-0.78); a model textured anywhere else has none unless it is
graded, and the first Meshy nodes drew 2-4 times brighter than the models they
replaced - chalk-white flint, white sage. Each row therefore names the
procedural model it was graded against, and the test keeps its mean surface
albedo inside `GRADE_RATIO_BAND` of that model's. The measurement needs
Pillow, so it lives with the test rather than the generator.
"""
from __future__ import annotations

import hashlib
import io
import json
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

#: Owner decision 2026-10-02 (island content plan, item 17): "raise it to about
#: 2,600 for imported nodes". The reviewed kits run 1,144-2,568.
IMPORTED_TRIANGLE_BAND = (90, 2600)
#: The band every procedural model stays in, including interactive props.
PROCEDURAL_TRIANGLE_BAND = (90, 424)
#: An imported node's mean surface albedo over its `graded_against` model's.
#: The ungraded Meshy nodes measured 1.9-3.7 against theirs; graded, 0.8-1.5.
GRADE_RATIO_BAND = (0.4, 1.6)


@dataclass(frozen=True)
class ImportedHarvestable:
    """One harvest-node model the procedural catalogue does not author.

    `answers_label` says whether the server's resource label resolves to this
    model. A label the procedural catalogue also serves (Flint, Sage, Resin)
    is then answered by the imported model on every map, which is the global
    swap the owner chose over a per-map override; the procedural model stays
    in the registry and on disk, because map packages bake its geometry into
    their own scenery. A model that does not answer its label is registered
    and measured but drawn nowhere until it does. Flipping the flag and
    regenerating the registry is the whole of a swap, or of undoing one.

    `graded_against` is the procedural model whose brightness this one was
    graded to: the model it replaces, or for a new label the nearest like
    node.
    """
    model_id: str
    label: str
    kind: str
    tier: str
    answers_label: bool
    graded_against: str
    source: str


#: Append only. Each row's GLB is `assets/world/harvestables/<model_id>.glb`.
#: The south-west isle's Meshy nodes as shipped by run 3 of the continent-v2
#: harvest work: graded in linear light for the Godot look against the model
#: named, 512 px textures.
IMPORTED_HARVESTABLES = (
    ImportedHarvestable(
        "isle_olive", "Olive", "crop", "common", True, "blueberries",
        "Meshy H1 with the local readability fix (olive clusters, a larger "
        "basket); leaves graded to 0.28, fruit and basket kept light; "
        "continent-v2 harvest ship run 3, 2026-10-02"),
    ImportedHarvestable(
        "isle_lemon", "Lemon", "crop", "common", True, "blueberries",
        "Meshy H2; leaves, crate and trunk graded to 0.55-0.60, lemons 0.85; "
        "continent-v2 harvest ship run 3, 2026-10-02"),
    ImportedHarvestable(
        "isle_flint", "Flint", "mineral", "common", True, "sunstone_flint",
        "Meshy H3 with flint nodules on the back face and a glassy sheen on "
        "the flint; warm baseColorFactor 0.31/0.25/0.19; continent-v2 harvest "
        "ship run 3, 2026-10-02"),
    ImportedHarvestable(
        "isle_sage", "Sage", "herb", "common", True, "wayside_sage",
        "Meshy H4 with its spikes desaturated toward lilac-grey; leaves "
        "graded to 0.22, spikes kept light; continent-v2 harvest ship run 3, "
        "2026-10-02"),
    ImportedHarvestable(
        "isle_resin", "Resin", "resin", "uncommon", True, "amber_resin",
        "Meshy H5; bark graded to 0.30, the cut top repainted weathered with "
        "amber beads and drips, the tapping panel painted on the back face; "
        "continent-v2 harvest ship run 3, 2026-10-02"),
    # Shell drift was generated as an upgrade for Shell, but the global swap
    # the owner approved names Flint, Sage and Resin only, and on maps whose
    # Shell nodes stand on grass its cream shells read far brighter than the
    # ground. It is registered and measured; every Shell node keeps
    # `shorebank_shell`.
    # Crop-row patch nodes for the Landfall liveliness pass (owner-approved 2026-10-14): a 3 m row segment
    # whose plants are every one harvestable, laid end to end into fenced fields. They answer no label on
    # their own; HARVEST_VARIANTS names them for maps whose packages describe their nodes.
    ImportedHarvestable(
        "cotton_row", "Cotton", "fibre", "common", False, "moorcotton",
        "Meshy P1 (task 01a13acd-85c0-7130-af9f-588ac415adf3): three waist-high cotton shrubs on a 3 m tilled "
        "ridge, +X along the row, butt ends square; leaves 0.84 and soil 1.14 of kit cabbage rows, bolls kept "
        "light; 512 px; work-output/lv/meshy/patches, 2026-10-14"),
    ImportedHarvestable(
        "hearthroot_row", "Hearthroot", "flora", "common", False, "hearthroot",
        "Meshy P2 (task 01a13ad1-61a9-7192-b2f7-acce56806459): four ruddy roots on a 3 m tilled ridge, leaves "
        "shrunk 0.82 and lifted 17 degrees so the roots read at the game camera; 512 px; "
        "work-output/lv/meshy/patches, 2026-10-14"),
    ImportedHarvestable(
        "isle_shell", "Shell", "mineral", "common", False, "shorebank_shell",
        "Meshy H6; sand plate cut to a 0.60 m radius with its rim lowered to "
        "the ground, sand graded to 0.55; continent-v2 harvest ship run 3, "
        "2026-10-02"),
    # Harvest patch nodes for Landfall (owner plan item H7, 2026-10-14): each model is a whole natural unit - a herb
    # clump, a wet mat, a hedge segment, a reed clump, a kelp strand, a shell drift, a salt pan, a seam face or a cut
    # bank - so every plant or stone of it is harvestable. Meshy Smart Topology generated above the archetype's
    # triangle cap, collapse-decimated to it, graded in linear light against the label's model; 512 px;
    # work-output/lv/meshy/patches2. They answer no label; HARVEST_VARIANTS names them for packages that describe
    # their nodes. footprints.json there gives each one's size, long axis and (seams, banks) the face side.
    ImportedHarvestable(
        "sage_clump_a", "Sage", "herb", "common", False, "wayside_sage",
        "Meshy patches2 (task 01a13b58-e040-76aa-b5b2-7229a9ef7b2d): a low 1.5 m dome of grey-green sage with "
        "lilac spikes and cut stubs; 796 tris; 1.00 of isle_sage; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "sage_clump_b", "Sage", "herb", "common", False, "wayside_sage",
        "Meshy patches2 (task 01a13b5b-47d4-723f-bd03-fb8d39141584): a 1.8 m long low drift of sage with "
        "seven lilac spikes; 796 tris; 1.00 of isle_sage; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "sage_clump_c", "Sage", "herb", "common", False, "wayside_sage",
        "Meshy patches2 (task 01a13b5f-a0d6-75bb-bd47-0d544b59946c): an open 1.3 m clump of sage, five stems, "
        "lilac spikes and cut stubs; 794 tris; 1.00 of isle_sage; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "watercress_mat_a", "Watercress", "flora", "common", False, "cenote_watercress",
        "Meshy patches2 (task 01a13b5b-4cf0-753b-9dfb-fc6f0cc250fd): a 1.5 m round watercress mat on mud; its "
        "open centre closed with a leaf dome (0-credit fix); 798 tris; 1.00 of cenote_watercress; 512 px; "
        "2026-10-14"),
    ImportedHarvestable(
        "watercress_mat_b", "Watercress", "flora", "common", False, "cenote_watercress",
        "Meshy patches2 (task 01a13b5b-51a5-766f-9f91-e4fe7c307360): a 1.7 m kidney-shaped watercress mat on "
        "mud; 794 tris; 1.00 of cenote_watercress; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "lavender_clump_a", "Lavender", "herb", "common", False, "lavender",
        "Meshy patches2 (task 01a13b5f-91f0-742e-a126-fc5eff86f480): a low 1.4 m lavender cushion under a "
        "purple crown; 795 tris; 1.00 of lavender; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "lavender_clump_b", "Lavender", "herb", "common", False, "lavender",
        "Meshy patches2 (task 01a13b5b-3ab2-7181-a8c4-d06c0e686202): a 1.8 x 0.6 m lavender row of purple "
        "spikes; 796 tris; 1.00 of lavender; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "rosemary_clump_a", "Rosemary", "herb", "common", False, "rosemary",
        "Meshy patches2 (task 01a13b5f-96a7-74a2-b8a0-f6cf9e5379a5): an upright 1.4 m rosemary bush; pale "
        "blue flowers painted on (0-credit); 796 tris; 1.00 of rosemary; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "rosemary_clump_b", "Rosemary", "herb", "common", False, "rosemary",
        "Meshy patches2 (task 01a13b5f-9b65-72cc-9b89-1bd422529987): a low sprawling 1.7 m rosemary mound; "
        "pale blue flowers painted on (0-credit); 796 tris; 1.00 of rosemary; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "bramble_hedge_a", "Bramble", "flora", "common", False, "barrow_bramble",
        "Meshy patches2 (task 01a13b5b-e507-70d2-9928-939dad7f680a): a 3.0 m bramble hedge segment, berries "
        "lifted to read; 1496 tris; 1.29 of barrow_bramble; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "bramble_hedge_b", "Bramble", "flora", "common", False, "barrow_bramble",
        "Meshy patches2 (task 01a13b5b-edba-772f-a407-3023c2fa987e): a 2.8 m bramble hedge segment with an "
        "arching cane; 1496 tris; 1.29 of barrow_bramble; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "bramble_hedge_c", "Bramble", "flora", "common", False, "barrow_bramble",
        "Meshy patches2 (task 01a13b5b-f21e-70b7-ac64-39041f70e1d1): a 3.0 m bramble hedge segment with "
        "berries and red unripe ones; 1496 tris; 1.30 of barrow_bramble; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "reed_clump_a", "Reed", "fibre", "common", False, "mirror_reed",
        "Meshy patches2 (task 01a13b5c-810d-736a-ae8b-589acee07501): a 1.8 m reed clump of six sheaves under "
        "tan plumes; 996 tris; 0.80 of mirror_reed; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "reed_clump_b", "Reed", "fibre", "common", False, "mirror_reed",
        "Meshy patches2 (task 01a13b5c-8572-758b-8148-62abf47feca7): a 1.6 m reed clump of cattails and "
        "plumes on an oval mud base; 996 tris; 0.80 of mirror_reed; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "reed_clump_c", "Reed", "fibre", "common", False, "mirror_reed",
        "Meshy patches2 (task 01a13b5c-8ac5-7730-bf3d-7a23549eb743): a 1.9 m narrow reed clump with plumes "
        "and cut stubs; 996 tris; 0.80 of mirror_reed; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "kelp_strand_a", "Kelp", "aquatic", "common", False, "tidewrack_kelp",
        "Meshy patches2 (task 01a13b5d-0420-7380-a0a4-05a672b53364): a 2.6 m washed-up kelp strand on damp "
        "sand; 995 tris; 1.45 of tidewrack_kelp; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "kelp_strand_b", "Kelp", "aquatic", "common", False, "tidewrack_kelp",
        "Meshy patches2 (task 01a13b5d-0844-761a-b10b-9311519f4420): two 2.4 m kelp strands crossed on damp "
        "sand; 996 tris; 1.45 of tidewrack_kelp; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "shell_drift_a", "Shell", "mineral", "common", False, "shorebank_shell",
        "Meshy patches2 (task 01a13b5d-6c58-72d1-a940-4b69d05df6e1): a 1.8 m crescent drift of shells on pale "
        "sand; 995 tris; 0.80 of shorebank_shell; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "shell_drift_b", "Shell", "mineral", "common", False, "shorebank_shell",
        "Meshy patches2 (task 01a13b5d-70a7-7087-aa52-dd31141c81f5): a 1.6 m heap of shells with a conch on "
        "top; 995 tris; 0.80 of shorebank_shell; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "salt_pan_a", "Salt", "mineral", "common", False, "glacier_salt",
        "Meshy patches2 (task 01a13b5d-0c3c-70c9-b540-f1f8c7278324): a 2 x 2 m mud-rimmed salt pan of white "
        "crust plates and two heaps; 996 tris; 0.80 of glacier_salt; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "salt_pan_b", "Salt", "mineral", "common", False, "glacier_salt",
        "Meshy patches2 (task 01a13b5d-105d-76d8-8ffd-7f63655fc92e): a 2 m round stone-rimmed salt pan with a "
        "central heap; 996 tris; 0.80 of glacier_salt; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "flint_seam_a", "Flint", "mineral", "common", False, "sunstone_flint",
        "Meshy patches2 (task 01a13b60-46fe-74a4-b3de-dc081bc328d4): a 2.6 m limestone seam face with two "
        "bands of flint nodules, worked face +Z; 2496 tris; 1.00 of isle_flint; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "flint_seam_b", "Flint", "mineral", "common", False, "sunstone_flint",
        "Meshy patches2 (task 01a13b60-4bda-7195-8d43-20a74710a6bd): a 1.8 m limestone seam face, nodules in "
        "bands and one cracked open, face +Z; 2496 tris; 1.00 of isle_flint; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "flint_boulder_a", "Flint", "mineral", "common", False, "sunstone_flint",
        "Meshy patches2 (task 01a13b5d-f05b-751c-a64a-718b0082a73c): a 1.4 m limestone boulder split on flint "
        "nodules; 2496 tris; 1.00 of isle_flint; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "quartz_seam_a", "Quartz", "crystal", "common", False, "pale_quartz",
        "Meshy patches2 (task 01a13b5d-f4c5-71b5-85ca-98131a2ebf28): a 2.2 m granite seam with crystal "
        "clusters along its +Z foot; 2496 tris; 0.60 of pale_quartz; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "quartz_seam_b", "Quartz", "crystal", "common", False, "pale_quartz",
        "Meshy patches2 (task 01a13b5e-69cf-73dd-b74c-6767dafc68e0): a 1.8 m granite seam with a diagonal "
        "crystal crack, face +Z; 2496 tris; 0.60 of pale_quartz; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "clay_bank_a", "Clay", "mineral", "common", False, "deep_lake_clay",
        "Meshy patches2 (task 01a13b5d-e702-71f8-8964-27f221af83bc): a 2.6 m cut clay bank, banded face +Z, "
        "turf top, cut blocks; 2496 tris; 1.20 of deep_lake_clay; 512 px; 2026-10-14"),
    ImportedHarvestable(
        "clay_bank_b", "Clay", "mineral", "common", False, "deep_lake_clay",
        "Meshy patches2 (task 01a13b5d-ebe1-720a-87c2-39a3f8ad1755): a 2.2 m cut clay bank, banded face +Z, "
        "clay lumps at its foot; 2495 tris; 1.20 of deep_lake_clay; 512 px; 2026-10-14"),
)


@dataclass(frozen=True)
class ImportedInteractive:
    """A reviewed replacement for an existing role's procedural prop.

    The stable model id and role label stay the same. The generator measures
    this GLB instead of overwriting it with the procedural fallback.
    """
    model_id: str
    label: str
    source: str


#: Model variants per harvest resource label (owner-approved 2026-10-14, the
#: harvest presentation: work-output/landfall-audit-2026-10-14/harvest/
#: FINDINGS.md 5.6). A label listed here is written to the registry's
#: `harvestables.variants` table, and the client stands
#: `variants[label][variant % len]` on a node - the variant its map package
#: states, or one its object id picks - instead of the label's one model, so a
#: field of crop-row segments is not one segment stamped in a lattice. Every id
#: must be a registered model (procedural or imported) of that label. Empty
#: until the patch models (row segments, clumps, hedge segments, seams) are
#: made; with it empty the registry carries no `variants` table at all.
HARVEST_VARIANTS: dict[str, tuple[str, ...]] = {
    "Cotton": ("cotton_row",),
    "Hearthroot": ("hearthroot_row",),
    # the patches2 harvest patch nodes (H7), each label's variants in a / b / c order (the label's own model is not
    # one of them, as for the crop rows)
    "Bramble": ("bramble_hedge_a", "bramble_hedge_b", "bramble_hedge_c"),
    "Clay": ("clay_bank_a", "clay_bank_b"),
    "Flint": ("flint_seam_a", "flint_seam_b", "flint_boulder_a"),
    "Kelp": ("kelp_strand_a", "kelp_strand_b"),
    "Lavender": ("lavender_clump_a", "lavender_clump_b"),
    "Quartz": ("quartz_seam_a", "quartz_seam_b"),
    "Reed": ("reed_clump_a", "reed_clump_b", "reed_clump_c"),
    "Rosemary": ("rosemary_clump_a", "rosemary_clump_b"),
    "Sage": ("sage_clump_a", "sage_clump_b", "sage_clump_c"),
    "Salt": ("salt_pan_a", "salt_pan_b"),
    "Shell": ("shell_drift_a", "shell_drift_b"),
    "Watercress": ("watercress_mat_a", "watercress_mat_b"),
}


def harvest_variants(harvest: dict, table: dict[str, tuple[str, ...]] | None = None) -> dict[str, list[str]]:
    """The registry's `harvestables.variants` table: `table` (HARVEST_VARIANTS) checked against the generator's
    harvestable section, in label order. Raises ValueError for a label the registry does not resolve, an empty or
    repeated list, or an id that is not a registered model of that label."""
    table = HARVEST_VARIANTS if table is None else table
    models, resources = harvest["models"], harvest["resources"]
    written: dict[str, list[str]] = {}
    for label in sorted(table):
        ids = list(table[label])
        if label not in resources:
            raise ValueError(f"variants for {label!r}: no resource of that label in the registry")
        if not ids or len(set(ids)) != len(ids):
            raise ValueError(f"variants for {label!r}: empty or repeated {ids}")
        for model_id in ids:
            entry = models.get(model_id)
            if entry is None or entry.get("label") != label:
                raise ValueError(f"variants for {label!r}: {model_id!r} is not a registered {label} model")
        written[label] = ids
    return written


IMPORTED_INTERACTIVES = (
    ImportedInteractive(
        "storage", "Storage",
        "Meshy approved design A, ironbound oak chest; task "
        "01a12c60-047d-7302-bb96-2b0c795adb03, 2026-10-11; "
        "2k embedded PBR textures, grounded and sized to the storage body; "
        "eloria-assets/source/world_objects/storage/provenance.json"),
)


# ---------------------------------------------------------------------------
# measuring a GLB
# ---------------------------------------------------------------------------

_FLOAT = 5126
_INDEX_TYPES = {5121: "<u1", 5123: "<u2", 5125: "<u4"}


def _read_glb(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    magic, version, _total = struct.unpack_from("<4sII", raw)
    if magic != b"glTF" or version != 2:
        raise ValueError(f"{path} is not a glTF 2 binary")
    length, kind = struct.unpack_from("<II", raw, 12)
    if kind != 0x4E4F534A:
        raise ValueError(f"{path}: first chunk is not JSON")
    document = json.loads(raw[20:20 + length].decode("utf-8"))
    binary = b""
    offset = 20 + length
    if offset + 8 <= len(raw):
        binary_length, binary_kind = struct.unpack_from("<II", raw, offset)
        if binary_kind == 0x004E4942:
            binary = raw[offset + 8:offset + 8 + binary_length]
    return document, binary


def _view(document: dict, accessor_index: int) -> tuple[dict, dict, int]:
    accessor = document["accessors"][accessor_index]
    view = document["bufferViews"][accessor["bufferView"]]
    if view.get("buffer", 0) != 0:
        raise ValueError("only the GLB's own binary chunk is supported")
    return accessor, view, view.get("byteOffset", 0) + accessor.get("byteOffset", 0)


def _floats(document: dict, binary: bytes, accessor_index: int, width: int) -> np.ndarray:
    accessor, view, start = _view(document, accessor_index)
    if accessor["componentType"] != _FLOAT:
        raise ValueError("expected a float accessor")
    stride = view.get("byteStride", 4 * width)
    rows = np.ndarray((accessor["count"], width), dtype="<f4", buffer=binary,
                      offset=start, strides=(stride, 4))
    return np.array(rows, dtype=np.float64)


def _indices(document: dict, binary: bytes, primitive: dict, count: int) -> np.ndarray:
    if "indices" not in primitive:
        return np.arange(count - count % 3, dtype=np.int64).reshape(-1, 3)
    accessor, _view_, start = _view(document, primitive["indices"])
    values = np.frombuffer(binary, dtype=_INDEX_TYPES[accessor["componentType"]],
                           count=accessor["count"], offset=start)
    return values.astype(np.int64).reshape(-1, 3)


def _local_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    x, y, z, w = node.get("rotation", (0.0, 0.0, 0.0, 1.0))
    rotation = np.array((
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y))))
    matrix = np.identity(4)
    matrix[:3, :3] = rotation * np.array(node.get("scale", (1.0, 1.0, 1.0)))
    matrix[:3, 3] = node.get("translation", (0.0, 0.0, 0.0))
    return matrix


def drawn_primitives(document: dict):
    """(primitive, world matrix) for every primitive the default scene draws.

    A mesh the scene instances twice is yielded twice, as it draws twice.
    """
    scene = document.get("scenes", [{}])[document.get("scene", 0)]
    pending = [(index, np.identity(4)) for index in scene.get("nodes", [])]
    while pending:
        index, parent = pending.pop()
        node = document["nodes"][index]
        world = parent @ _local_matrix(node)
        pending.extend((child, world) for child in node.get("children", []))
        if "mesh" not in node:
            continue
        for primitive in document["meshes"][node["mesh"]]["primitives"]:
            if primitive.get("mode", 4) != 4:
                raise ValueError("only triangle lists are supported")
            yield primitive, world


def triangle_count(path: Path) -> int:
    """Triangles the default scene draws: the one count the registry and its
    test both use, for procedural and imported models alike."""
    document, _binary = _read_glb(path)
    total = 0
    for primitive, _world in drawn_primitives(document):
        if "indices" in primitive:
            total += document["accessors"][primitive["indices"]]["count"] // 3
        else:
            total += document["accessors"][primitive["attributes"]["POSITION"]]["count"] // 3
    return total


def measure_glb(path: Path) -> dict:
    """The registry's measurements of one GLB, taken the way the client sees it.

    Counts are summed over every primitive the default scene draws, and the
    height is the top of the posed geometry, node transforms applied, above
    the origin the client stands on the tile.
    """
    document, binary = _read_glb(path)
    vertices = 0
    alpha_tested = False
    top = -np.inf
    for primitive, world in drawn_primitives(document):
        position = primitive["attributes"]["POSITION"]
        vertices += document["accessors"][position]["count"]
        material = document.get("materials", [])[primitive["material"]] \
            if "material" in primitive else {}
        alpha_tested = alpha_tested or material.get("alphaMode") == "MASK"
        points = _floats(document, binary, position, 3)
        posed = points @ world[:3, :3].T + world[:3, 3]
        top = max(top, float(posed[:, 1].max()))
    if not np.isfinite(top):
        raise ValueError(f"{path}: the default scene draws no mesh")
    return {"vertices": int(vertices),
            "triangles": triangle_count(path),
            "alphaTested": bool(alpha_tested),
            "height": round(top, 3),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def surface_albedo(path: Path) -> float:
    """Mean linear luminance of the base colour over the drawn surface.

    Texture (sRGB decoded to linear) times baseColorFactor, sampled at seven
    points of every triangle and weighted by the triangle's area - what a
    viewer sees of the model, not the texture's unused padding. Needs Pillow.
    """
    from PIL import Image  # the generator does not need it; the test does

    document, binary = _read_glb(path)
    luma = np.array((0.2126, 0.7152, 0.0722))
    samples = np.array(((1 / 3, 1 / 3, 1 / 3), (.6, .2, .2), (.2, .6, .2), (.2, .2, .6),
                        (.45, .45, .1), (.1, .45, .45), (.45, .1, .45)))
    images: dict[int, np.ndarray] = {}
    weighted = area_total = 0.0
    for primitive, world in drawn_primitives(document):
        material = document.get("materials", [])[primitive["material"]] \
            if "material" in primitive else {}
        pbr = material.get("pbrMetallicRoughness", {})
        factor = np.array(pbr.get("baseColorFactor", (1.0, 1.0, 1.0, 1.0))[:3])
        attributes = primitive["attributes"]
        points = _floats(document, binary, attributes["POSITION"], 3)
        points = points @ world[:3, :3].T + world[:3, 3]
        triangles = _indices(document, binary, primitive, len(points))
        corners = points[triangles]
        areas = 0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0],
                                              corners[:, 2] - corners[:, 0]), axis=1)
        texture = pbr.get("baseColorTexture")
        if texture is None or "TEXCOORD_0" not in attributes:
            value = np.full(len(triangles), float(factor @ luma))
        else:
            source = document["textures"][texture["index"]]["source"]
            if source not in images:
                view = document["bufferViews"][document["images"][source]["bufferView"]]
                start = view.get("byteOffset", 0)
                pixels = Image.open(io.BytesIO(binary[start:start + view["byteLength"]]))
                srgb = np.asarray(pixels.convert("RGB"), dtype=np.float64) / 255.0
                images[source] = np.where(srgb <= 0.04045, srgb / 12.92,
                                          ((srgb + 0.055) / 1.055) ** 2.4)
            # the factor multiplies each linear channel before luminance
            plane = (images[source] * factor) @ luma
            height, width = plane.shape
            uv = _floats(document, binary, attributes["TEXCOORD_0"], 2)[triangles]
            value = np.zeros(len(triangles))
            for weights in samples:
                at = (uv * weights[None, :, None]).sum(axis=1)
                x = np.floor((at[:, 0] % 1.0) * width).astype(int).clip(0, width - 1)
                y = np.floor((at[:, 1] % 1.0) * height).astype(int).clip(0, height - 1)
                value += plane[y, x]
            value /= len(samples)
        weighted += float((value * areas).sum())
        area_total += float(areas.sum())
    return weighted / area_total


# ---------------------------------------------------------------------------
# the registry half
# ---------------------------------------------------------------------------

def check_rows(procedural_ids: set[str]) -> None:
    """Refuse a table the generator cannot honour, before it writes a file.

    An imported id may not shadow a procedural one: the generator writes the
    procedural GLB at that path and would overwrite the committed import.
    """
    seen: set[str] = set()
    for row in IMPORTED_HARVESTABLES:
        if row.model_id in procedural_ids:
            raise ValueError(f"imported model {row.model_id} shadows a procedural model")
        if row.model_id in seen:
            raise ValueError(f"imported model {row.model_id} is listed twice")
        if row.graded_against not in procedural_ids:
            raise ValueError(f"{row.model_id} is graded against {row.graded_against}, "
                             "which is not a procedural harvest model")
        seen.add(row.model_id)


def imported_entries(client_root: Path, harvestable_dir: str) -> dict[str, dict]:
    """model id -> registry entry, for every row of the table, in table order."""
    entries: dict[str, dict] = {}
    low, high = IMPORTED_TRIANGLE_BAND
    for row in IMPORTED_HARVESTABLES:
        path = client_root / harvestable_dir / f"{row.model_id}.glb"
        if not path.is_file():
            raise FileNotFoundError(
                f"{path} is listed in IMPORTED_HARVESTABLES but is not on disk; "
                "copy the reviewed GLB in before regenerating the registry")
        measured = measure_glb(path)
        if not low <= measured["triangles"] <= high:
            raise ValueError(f"{path}: {measured['triangles']} triangles is outside "
                             f"the imported band {low}-{high}")
        entries[row.model_id] = {
            "scene": f"res://{harvestable_dir}/{row.model_id}.glb",
            "label": row.label, "kind": row.kind, "tier": row.tier,
            **measured,
            "imported": True,
            "source": row.source,
        }
    return entries


def merge_imported(harvest: dict, client_root: Path, harvestable_dir: str) -> dict:
    """Add the imported models to the generator's harvestable section in place."""
    models, resources = harvest["models"], harvest["resources"]
    check_rows(set(models))
    for model_id, entry in imported_entries(client_root, harvestable_dir).items():
        models[model_id] = entry
    for row in IMPORTED_HARVESTABLES:
        if row.answers_label:
            replaced = resources.get(row.label)
            if replaced is not None:
                models[row.model_id]["replaces"] = replaced
            resources[row.label] = row.model_id
    variants = harvest_variants(harvest)
    if variants:
        harvest["variants"] = variants
    return harvest


def imported_interactive_entries(client_root: Path, interactive_dir: str,
                                procedural_roles: dict[str, str]) -> dict[str, dict]:
    """Validate and measure replacements before the generator writes GLBs."""
    entries: dict[str, dict] = {}
    low, high = IMPORTED_TRIANGLE_BAND
    for row in IMPORTED_INTERACTIVES:
        if procedural_roles.get(row.model_id) != row.label:
            raise ValueError(f"{row.model_id}: imported interactive must replace "
                             "an existing model with the same role label")
        if row.model_id in entries:
            raise ValueError(f"imported interactive {row.model_id} is listed twice")
        path = client_root / interactive_dir / f"{row.model_id}.glb"
        if not path.is_file():
            raise FileNotFoundError(
                f"{path} is listed in IMPORTED_INTERACTIVES but is not on disk; "
                "copy the reviewed GLB in before regenerating the registry")
        measured = measure_glb(path)
        if not low <= measured["triangles"] <= high:
            raise ValueError(f"{path}: {measured['triangles']} triangles is outside "
                             f"the imported band {low}-{high}")
        entries[row.model_id] = {
            "scene": f"res://{interactive_dir}/{row.model_id}.glb",
            "label": row.label, **measured,
            "imported": True, "source": row.source,
        }
    return entries
