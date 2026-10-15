#!/usr/bin/env python3
"""Contracts of race bodies rebased onto the Human body (sharedBodyShape v3).

eloria-assets/tools/rebase_race_body.py keeps the installed v2 race head and
grafts it onto luminous_<sex>.glb below the neck. These checks run on every
catalogue race whose sharedBodyShape.version is 3 or more, with numpy/scipy
only (CI installs no trimesh, so the tool itself is never imported here).
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "godot-client"
sys.path.insert(0, str(ROOT / "eloria-assets/tools"))
import equipment_authoring as ea  # noqa: E402
from verify_shared_player_bodies import primitives, neck_join_checks  # noqa: E402

LUMA = np.array([.2126, .7152, .0722])


def welded(points: np.ndarray) -> np.ndarray:
    pairs = cKDTree(points).query_pairs(1e-6, output_type="ndarray")
    n = len(points)
    return connected_components(coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n)).tocsr(),
                                directed=False)[1]


def dense(a: dict, rows: np.ndarray) -> np.ndarray:
    out = np.zeros((len(rows), 77))
    for column in range(4):
        out[np.arange(len(rows)), a["JOINTS_0"][rows, column].astype(int)] += a["WEIGHTS_0"][rows, column]
    return out


def frame(document: dict) -> tuple[list, list, np.ndarray, np.ndarray]:
    skin = document["skins"][0]
    names = [document["nodes"][j]["name"] for j in skin["joints"]]
    world = np.array(ea.global_matrices(document))[skin["joints"]]
    origin = world[names.index("neck_01")][:3, 3]
    axis = world[names.index("Head")][:3, 3] - origin
    return names, world, origin, axis / np.linalg.norm(axis)


def image_size(document: dict, binary: bytes, material: int) -> tuple[int, int]:
    texture = document["materials"][material]["pbrMetallicRoughness"]["baseColorTexture"]["index"]
    view = document["bufferViews"][document["images"][document["textures"][texture]["source"]]["bufferView"]]
    start = view.get("byteOffset", 0)
    return Image.open(io.BytesIO(binary[start:start + view["byteLength"]])).size


def face_density(document: dict, binary: bytes, roles=None) -> float:
    """Median px/cm of front-facing face triangles (Head weight > .5,
    centroid 3 cm in front of the Head joint, normal z > .5)."""
    names, world, _, _ = frame(document)
    head, index = world[names.index("Head")][:3, 3], names.index("Head")
    values = []
    for mesh in document["meshes"]:
        if mesh["name"] not in ("body", "eyes", "eyebrows", "scalp"):
            continue
        for primitive in mesh["primitives"]:
            if roles and primitive.get("extras", {}).get("sourceRole") not in roles:
                continue
            a = {k: ea.accessor_array(document, binary, v) for k, v in primitive["attributes"].items()}
            f = ea.accessor_array(document, binary, primitive["indices"]).astype(int).reshape(-1, 3)
            p = a["POSITION"].astype(float)
            weight = np.where(a["JOINTS_0"].astype(int) == index, a["WEIGHTS_0"], 0.).sum(1)
            normal = np.cross(p[f[:, 1]] - p[f[:, 0]], p[f[:, 2]] - p[f[:, 0]])
            area = np.linalg.norm(normal, axis=1) / 2 * 1e4
            normal /= np.maximum(2 * area[:, None] / 1e4, 1e-12)
            uv = a["TEXCOORD_0"].astype(float)
            e1, e2 = uv[f[:, 1]] - uv[f[:, 0]], uv[f[:, 2]] - uv[f[:, 0]]
            uv_area = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2
            w, h = image_size(document, binary, primitive["material"])
            keep = ((weight[f].mean(1) > .5) & (p[f].mean(1)[:, 2] > head[2] + .03) & (normal[:, 2] > .5)
                    & (area > 1e-6))
            values.append(np.sqrt(uv_area[keep] * w * h / area[keep]))
    return float(np.median(np.concatenate(values)))


class RaceRebaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads((CLIENT / "data/actors/native_asset_catalog.json").read_text())
        cls.models = json.loads((CLIENT / "data/actors/models.json").read_text())["models"]
        cls.rebased = {slug: entry for slug, entry in cls.catalog["races"].items()
                       if entry.get("sharedBodyShape", {}).get("version", 0) >= 3}
        cls.documents = {slug: ea.read_glb(ROOT / entry["path"]) for slug, entry in cls.rebased.items()}

    def test_glb_block_matches_the_catalogue_and_the_template(self) -> None:
        for slug, entry in self.rebased.items():
            d, _ = self.documents[slug]
            spec = d["asset"]["extras"]["sharedBodyShape"]
            with self.subTest(model=slug):
                self.assertEqual(entry["sharedBodyShape"], spec)
                template = CLIENT / "assets/actors/native/races" / (spec["template"] + ".glb")
                self.assertEqual(hashlib.sha256(template.read_bytes()).hexdigest(), spec["templateSHA256"])
                self.assertEqual("neck-plane", spec["bodyCutMode"])
                self.assertNotIn("sourceIntegration", entry)

    def test_human_derived_surfaces_keep_byte_joints(self) -> None:
        for slug in self.rebased:
            d, _ = self.documents[slug]
            for mesh in d["meshes"]:
                for primitive in mesh["primitives"]:
                    role = primitive.get("extras", {}).get("sourceRole")
                    if role in ("shared_body", "shared_neck"):
                        with self.subTest(model=slug, mesh=mesh["name"]):
                            self.assertEqual(5121, d["accessors"][primitive["attributes"]["JOINTS_0"]]["componentType"])

    def test_two_bridge_surfaces_and_a_watertight_join(self) -> None:
        for slug in self.rebased:
            d, b = self.documents[slug]
            body = next(m for m in d["meshes"] if m["name"] == "body")
            with self.subTest(model=slug):
                roles = [p.get("extras", {}).get("sourceRole") for p in body["primitives"]]
                # A Ssarathi carries its tail as a fifth body surface.
                self.assertEqual(["shared_body", "race_head", "neck_join", "shared_neck"]
                                 + (["race_tail"] if slug.startswith("ssarathi_") else []), roles)
                self.assertEqual(2, sum(d["materials"][p["material"]].get("name") == "Shared neck bridge"
                                        for m in d["meshes"] for p in m["primitives"]))
                edges, a = neck_join_checks(list(primitives(d, b)))
                self.assertGreater(edges["geometricEdges"], 50)
                self.assertEqual(0, edges["unmatchedEdges"])
                self.assertEqual(0, a["unmatchedCopies"])
                self.assertGreater(a["boundaryCopies"], 30)
                self.assertLess(a["maxPositionDeltaM"], 1e-6)
                self.assertLess(a["maxNormalDelta"], 2e-6)
                self.assertLess(a["maxWeightL1Delta"], 2e-6)

    def test_every_rim_copy_shades_and_deforms_alike(self) -> None:
        """All coincident copies on both cut planes, not just one match each."""
        for slug in self.rebased:
            d, b = self.documents[slug]
            spec = d["asset"]["extras"]["sharedBodyShape"]
            _, _, origin, axis = frame(d)
            parts = list(primitives(d, b))
            for height, roles in ((spec["lowerCutM"], ("shared_body", "shared_neck", "neck_join")),
                                  (spec["upperCutM"], ("race_head", "neck_join"))):
                p, n, w = [], [], []
                for _, role, a, f in parts:
                    if role not in roles:
                        continue
                    used = np.unique(f)
                    rows = used[np.abs((a["POSITION"][used].astype(float) - origin) @ axis - height) < 3e-6]
                    p.append(a["POSITION"][rows].astype(float)); n.append(a["NORMAL"][rows].astype(float))
                    w.append(dense(a, rows))
                p, n, w = np.concatenate(p), np.concatenate(n), np.concatenate(w)
                labels = welded(p)
                first = np.zeros(labels.max() + 1, int)
                first[labels[::-1]] = np.arange(len(labels))[::-1]
                with self.subTest(model=slug, plane=height):
                    self.assertGreater(len(np.unique(labels)), 30)
                    self.assertLessEqual(float(np.linalg.norm(n - n[first[labels]], axis=1).max()), 2e-6)
                    self.assertLessEqual(float(np.abs(w - w[first[labels]]).sum(1).max()), 2e-6)

    def test_head_and_bridge_have_no_loose_fragments(self) -> None:
        for slug in self.rebased:
            d, b = self.documents[slug]
            points, faces, offset = [], [], 0
            for _, role, a, f in primitives(d, b):
                if role in ("race_head", "neck_join"):
                    points.append(a["POSITION"].astype(float)); faces.append(f + offset); offset += len(a["POSITION"])
            p, f = np.concatenate(points), np.concatenate(faces)
            used, inverse = np.unique(f, return_inverse=True)
            ids = welded(p[used])[inverse.reshape(-1, 3)]
            e = np.concatenate([ids[:, [0, 1]], ids[:, [1, 2]]])
            k = ids.max() + 1
            component = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(k, k)).tocsr(),
                                             directed=False)[1][ids[:, 0]]
            with self.subTest(model=slug):
                self.assertGreaterEqual(int(np.bincount(component).min()), 20)
                self.assertLessEqual(d["asset"]["extras"]["sharedBodyShape"]["cleanup"]["hiddenHeadFraction"], .02)

    def test_face_texels_are_at_least_as_dense_as_the_human_face(self) -> None:
        for slug in self.rebased:
            d, b = self.documents[slug]
            template = ea.read_glb(CLIENT / "assets/actors/native/races" / (d["asset"]["extras"]["sharedBodyShape"]["template"] + ".glb"))
            with self.subTest(model=slug):
                self.assertGreaterEqual(face_density(d, b, ("race_head",)), face_density(*template))
                self.assertGreaterEqual(d["asset"]["extras"]["sharedBodyShape"]["headAtlas"]["pxPerCm"], 12)

    def test_adjacent_skin_surfaces_dye_alike(self) -> None:
        """Equal texels either side of a body seam must take the same dye."""
        for slug in self.rebased:
            refs = self.models[slug]["skinPalette"]["references"]["body"]
            linear = [float(np.where(np.array(r) <= .04045, np.array(r) / 12.92,
                                     ((np.array(r) + .055) / 1.055) ** 2.4) @ LUMA) for r in refs]
            d, _ = self.documents[slug]
            body = next(m for m in d["meshes"] if m["name"] == "body")
            roles = [p.get("extras", {}).get("sourceRole") for p in body["primitives"]]
            with self.subTest(model=slug):
                self.assertEqual(len(roles), len(refs))
                for a, b in (("shared_body", "shared_neck"), ("shared_neck", "neck_join"), ("neck_join", "race_head")):
                    self.assertLessEqual(abs(linear[roles.index(a)] / linear[roles.index(b)] - 1), .02)
                # The calibration tool owns the unification and says why.
                seams = self.models[slug]["skinPalette"].get("bodySeams", {})
                if seams.get("unified"):
                    self.assertIn("reason", seams)
                    self.assertEqual(len(roles), len(seams["calibrated"]))

    def test_bridge_texture_carries_skin_grain(self) -> None:
        """A one-colour-per-column bridge fill renders as vertical streaks."""
        for slug in self.rebased:
            d, b = self.documents[slug]
            body = next(m for m in d["meshes"] if m["name"] == "body")
            bridge = next(p for p in body["primitives"] if p.get("extras", {}).get("sourceRole") == "neck_join")
            texture = d["materials"][bridge["material"]]["pbrMetallicRoughness"]["baseColorTexture"]["index"]
            view = d["bufferViews"][d["images"][d["textures"][texture]["source"]]["bufferView"]]
            start = view.get("byteOffset", 0)
            image = np.asarray(Image.open(io.BytesIO(b[start:start + view["byteLength"]])).convert("RGB")) / 255.
            v = ea.accessor_array(d, b, bridge["attributes"]["TEXCOORD_0"])[:, 1].astype(float)
            rows = image[int(np.ceil(v.min() * image.shape[0])) + 2:int(np.floor(v.max() * image.shape[0])) - 2] @ LUMA
            detail = rows - gaussian_filter(rows, 6., mode=("nearest", "wrap"))
            ratio = (np.diff(detail, axis=1) ** 2).mean() / (np.diff(detail, axis=0) ** 2).mean()
            with self.subTest(model=slug):
                self.assertLess(ratio, 1.5)


    def test_catalogue_entry_matches_the_installed_glb(self) -> None:
        """A reinstall must not leave a stale catalogue sha256 or counts."""
        for slug, entry in self.rebased.items():
            d, _ = self.documents[slug]
            surfaces = [p for m in d["meshes"] for p in m["primitives"]]
            with self.subTest(model=slug):
                self.assertEqual(hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest(), entry["sha256"])
                self.assertEqual(sum(d["accessors"][p["attributes"]["POSITION"]]["count"] for p in surfaces),
                                 entry["vertices"])
                self.assertEqual(sum(d["accessors"][p["indices"]]["count"] // 3 for p in surfaces), entry["triangles"])

    def test_bridge_has_no_groove_inside_both_rims(self) -> None:
        """No neck-bridge vertex lies more than 1 mm inside both rims at its
        azimuth (a waist where the Human nape is wider than the head rim)."""
        for slug in self.rebased:
            d, b = self.documents[slug]
            spec = d["asset"]["extras"]["sharedBodyShape"]
            _, _, origin, axis = frame(d)
            points = next(a["POSITION"].astype(float)[np.unique(f)] for _, role, a, f in primitives(d, b)
                          if role == "neck_join")
            rel = points - origin
            travel = rel @ axis
            radial = rel - travel[:, None] * axis
            radius = np.linalg.norm(radial, axis=1)
            theta = np.arctan2(radial @ np.cross(axis, [1., 0., 0.]), radial[:, 0])
            lower = np.abs(travel - spec["lowerCutM"]) < 3e-6
            upper = np.abs(travel - spec["upperCutM"]) < 3e-6

            def rim(on: np.ndarray) -> np.ndarray:
                order = np.argsort(theta[on])
                return np.interp(theta, theta[on][order], radius[on][order], period=2 * np.pi)
            inner = ~lower & ~upper
            with self.subTest(model=slug):
                self.assertGreater(int(lower.sum()), 30)
                self.assertGreater(int(upper.sum()), 30)
                dip = np.minimum(rim(lower), rim(upper))[inner] - radius[inner]
                self.assertLessEqual(float(dip.max()), .001)

if __name__ == "__main__":
    unittest.main()
