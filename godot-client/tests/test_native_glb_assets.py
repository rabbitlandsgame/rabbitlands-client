#!/usr/bin/env python3
"""Structural checks for the clean Nymara GLB asset library."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "godot-client"
sys.path.insert(0, str(CLIENT / "tools"))

import creature_facing  # noqa: E402  (needs the path above)

NYMARA_INVASION_MODELS = {
    400: ("mirrorfin_otter", "river_otter"),
    401: ("reedhorn_stag", "crown_antler_stag"),
    402: ("gate_turtle", "desert_tortoise"),
    403: ("lakeglass_drake", "sunscale_drake"),
    404: ("snowcrest_hare", "snow_hare"),
    405: ("glacier_ram", "whitehorn_ice_ram"),
    406: ("iceback_ursid", "crystal_polar_bear"),
    407: ("rimeclaw", "ice_snow_leopard"),
    408: ("crystal_mite", "crystal_carapace_beetle"),
    409: ("resonant_hound", "crystal_dire_wolf"),
    410: ("stormglass_grazer", "cobalt_ibex"),
    411: ("prism_wyrm", "emerald_canopy_dragon"),
    412: ("dunrunner", "golden_plains_horse"),
    413: ("steppe_aurochs", "golden_bison"),
    414: ("sunmane_cat", "stormmane_lion"),
    415: ("dustscale_drake", "fire_salamander"),
    416: ("amberhart", "autumn_antler_stag"),
    417: ("rootback_boar", "mossback_boar"),
    418: ("moor_wisp_hound", "mossbound_hound"),
    419: ("barrow_quillbeast", "porcupine"),
    420: ("canopy_glider", "leafwing_owl"),
    421: ("cenote_toader", "miretoad"),
    422: ("scalevine_stalker", "emerald_canopy_dragon"),
    423: ("sunscale_basilisk", "emerald_canopy_dragon"),
    424: ("mangrove_crab", "delta_mud_crab"),
    425: ("mudskipper_beast", "miretoad"),
    426: ("delta_crocodile", "saltmarsh_crocodile"),
    427: ("floodmaw", "saltmarsh_crocodile"),
}


def glb_chunks(path: Path) -> tuple[dict, bytes]:
    """The JSON document and the binary chunk of a GLB."""
    raw = path.read_bytes()
    size, _ = struct.unpack_from("<II", raw, 12)
    offset = 20 + size
    length, _ = struct.unpack_from("<II", raw, offset)
    return json.loads(raw[20:20 + size]), raw[offset + 8:offset + 8 + length]


def glb_document(path: Path) -> dict:
    raw = path.read_bytes()
    if raw[:4] != b"glTF":
        raise AssertionError(f"invalid GLB magic: {path}")
    version, total = struct.unpack_from("<II", raw, 4)
    if version != 2 or total != len(raw):
        raise AssertionError(f"invalid GLB header: {path}")
    size, kind = struct.unpack_from("<II", raw, 12)
    if kind != 0x4E4F534A:
        raise AssertionError(f"missing GLB JSON chunk: {path}")
    return json.loads(raw[20:20 + size])


def bone_translations(path: Path) -> dict[str, list[float]]:
    """Every skinned bone's rest translation, by name."""
    document = glb_document(path)
    return {document["nodes"][joint].get("name"):
            document["nodes"][joint].get("translation") or [0.0, 0.0, 0.0]
            for joint in document["skins"][0]["joints"]}


def accessor_rows(document: dict, binary: bytes, index: int) -> list[tuple]:
    """Decode ordinary glTF accessors with offsets relative to the BIN payload."""
    spec = document["accessors"][index]
    view = document["bufferViews"][spec["bufferView"]]
    code = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}[spec["componentType"]]
    count = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[spec["type"]]
    fmt = "<" + code * count
    stride = view.get("byteStride", struct.calcsize(fmt))
    start = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
    rows = [struct.unpack_from(fmt, binary, start + row * stride) for row in range(spec["count"])]
    if not spec.get("normalized"):
        return rows
    # A normalized accessor stores a fraction over its type's range; read as
    # integers a weight would be 0-255 and a normal 0-127.
    scale = {"b": 127.0, "B": 255.0, "h": 32767.0, "H": 65535.0}[code]
    floor = -1.0 if code in ("b", "h") else 0.0
    return [tuple(max(value / scale, floor) for value in row) for row in rows]


class NativeGlbAssetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads((CLIENT / "data/actors/native_asset_catalog.json").read_text())
        cls.models = json.loads((CLIENT / "data/actors/models.json").read_text())
        cls.equipment = json.loads((CLIENT / "data/actors/equipment.json").read_text())

    def test_catalog_is_complete(self) -> None:
        self.assertEqual(16, len(self.catalog["races"]))
        self.assertEqual(18, len(self.catalog["hair"]))
        # 32 first-pass creatures plus the wider concept-art roster.
        sys.path.insert(0, str(ROOT / "eloria-assets" / "tools"))
        import creature_roster
        self.assertEqual(32 + len(creature_roster.ROSTER),
                         len(self.catalog["creatures"]))
        # 60 culture and landmark pieces, plus the concept design sets. Counted
        # from the tables that declare them rather than restated, so adding a
        # design cannot leave this stale - which is how the creature count below
        # came to be compared against disk instead of a literal. (66 until
        # 2026-10, when the six regional capes became tints of the one shared
        # cape mesh.)
        import legwear_roster
        import torso_designs
        self.assertEqual(60 + len(torso_designs.DESIGNS) + len(legwear_roster.ROSTER),
                         len(self.catalog["equipment"]))
        # The generic tier claims the legacy visual-id space with one authored
        # mesh per material ladder rather than one per id. (43 until 2026-10,
        # when the fur cape became a tint of generic_cape.)
        self.assertEqual(42, len(self.catalog["genericEquipment"]))
        # Compare against what is actually on disk instead of a fixed number:
        # the catalogue's count had drifted stale when the ambient livestock
        # were added by a second generator without refreshing this block.
        on_disk = len(list((CLIENT / "assets/actors/native").rglob("*.glb")))
        self.assertEqual(on_disk, self.catalog["validation"]["files"])
        # The catalogue records POSIX-form paths on every platform, so compare
        # in that form: str() on a Windows path yields backslashes and made
        # this assertion fail on Windows builds alone.
        self.assertEqual(sorted(self.catalog["validation"]["results"]),
                         sorted(path.relative_to(ROOT).as_posix()
                                for path in (CLIENT / "assets/actors/native").rglob("*.glb")))

    def test_camp_livestock_claims_its_server_actor_types(self) -> None:
        """The Sunmane camps' horses are server creatures now, not scenery.

        They used to be client-only ambient herds with no actor type. The
        server stands them as tame livestock, so each carries the actor type
        eloria-server's creatures.txt allocates, and models.json has to agree
        in both directions or the wire would draw some other body. They keep
        their own catalogue section so the roster count above stays exact.
        """
        ambient = self.catalog.get("ambientCreatures", {})
        self.assertEqual({"sunmane_steppe_horse": 785, "sunmane_dun_mare": 786,
                          "sunmane_grey_pony": 787},
                         {slug: entry.get("actor_type") for slug, entry in ambient.items()})
        for slug, entry in ambient.items():
            with self.subTest(model=slug):
                self.assertIn(slug, self.models["models"])
                self.assertEqual(entry["actor_type"],
                                 self.models["models"][slug]["serverActorType"])
                self.assertEqual(slug, self.models["actorTypes"][str(entry["actor_type"])])
                path = ROOT / entry["path"]
                self.assertTrue(path.is_file(), entry["path"])
                document = glb_document(path)
                self.assertEqual(
                    7, len(document.get("animations", [])),
                    "ambient creatures carry the shared creature action set")
                ambient_bones = [document["nodes"][j].get("name")
                                 for j in document["skins"][0]["joints"]]
                for required in ("root", "body", "neck", "head"):
                    self.assertIn(required, ambient_bones)

    def test_player_rigs_share_one_skeleton_and_budget(self) -> None:
        """The sixteen races carry one rig, and no body rides a cape bone.

        This used to assert a joint count of 65.  The count was never the
        invariant: nothing in the client indexes a joint positionally -- every
        lookup is `find_bone` or `add_named_bind` by name -- and freezing it
        blocked the cape chains the cloth solver drives.  What has to hold is
        that the rigs are *one* rig, so the shared animation library and every
        skinned garment mean the same thing on all of them.
        """
        skeletons: dict[str, tuple] = {}
        for model_id, entry in self.catalog["races"].items():
            with self.subTest(model=model_id):
                self.assertEqual("skinned", entry["wardrobe"])
                self.assertEqual("retargeted", entry["anatomy"])
                # Keep the runtime vertex budget even with source UV seams.
                self.assertLess(entry["vertices"], 40_000)
                document = glb_document(ROOT / entry["path"])
                # The floor is the Meshy derivative's ~20k target. The Human
                # bodies regenerated on 2026-10-05 (packed by
                # pack_human_body.py) are their own Meshy runs: the male came
                # as a thickened shell and keeps 12,961 visible triangles once
                # the hidden inner wall is dropped (15,423 after the surface
                # borders are cut), so they keep a floor of their own.
                human_pack = "eloriaHumanPack" in document["asset"].get("extras", {})
                self.assertGreater(entry["triangles"], 14_000 if human_pack else 18_000)
                # A full retained Ssarathi tail is additional to the common
                # roughly-20k body/head. Count that actual surface separately.
                tail = sum(document["accessors"][p["indices"]]["count"] // 3
                           for m in document["meshes"] for p in m["primitives"]
                           if p.get("extras", {}).get("sourceRole") == "race_tail")
                self.assertEqual(tail, entry.get("retainedTailTriangles", 0))
                self.assertEqual(tail > 0, model_id.startswith("ssarathi_"))
                self.assertLess(tail, 9_000)
                # The detailed head gets its own regional budget on top of
                # the approved body; the optional tail is counted separately.
                budget = 50_000 if entry.get('highResolutionHead') else 36_000 if entry.get('sourceIntegration') else 25_000
                self.assertLess(entry["triangles"] - tail, budget)
                document = glb_document(ROOT / entry["path"])
                joints = document["skins"][0]["joints"]
                self.assertEqual(entry["joints"], len(joints))
                skeletons[model_id] = tuple(
                    document["nodes"][node].get("name") for node in joints)
                self.assertEqual(77, len(joints))
                mesh_names = {node["name"].lower() for node in document["nodes"] if "mesh" in node}
                required = {"eyes", "body", "scalp", "wardrobe_shirt", "wardrobe_pants", "wardrobe_boots"}
                if not model_id.startswith("mycelari_"):
                    required.add("eyebrows")
                self.assertTrue(required <= mesh_names)
        self.assertEqual(1, len(set(skeletons.values())),
                         "every race has to carry the same skeleton")
        names = list(next(iter(skeletons.values())))
        # The chains the cloth solver owns.  No clip in the shared library
        # names one, which is what makes them safe for a solver to drive.
        for chain in ("l", "c", "r"):
            self.assertEqual(
                [f"cape_{chain}_{link:02d}" for link in range(1, 5)],
                [name for name in names if name.startswith(f"cape_{chain}_")])
        # A cape bone may never move the body: it is driven by a solver, not
        # by a clip, so anything skinned to it would jitter free of the rig.
        first_cape = min(index for index, name in enumerate(names)
                         if name.startswith("cape_"))
        for model_id, entry in self.catalog["races"].items():
            document, binary = glb_chunks(ROOT / entry["path"])
            for mesh in document["meshes"]:
                if mesh["name"].startswith("Integrated_"):
                    continue
                for primitive in mesh["primitives"]:
                    spec = document["accessors"][primitive["attributes"]["JOINTS_0"]]
                    view = document["bufferViews"][spec["bufferView"]]
                    start = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
                    width = 2 if spec["componentType"] == 5123 else 1
                    raw = binary[start:start + spec["count"] * 4 * width]
                    highest = max(int.from_bytes(raw[i:i + width], "little")
                                  for i in range(0, len(raw), width))
                    with self.subTest(model=model_id, mesh=mesh["name"]):
                        self.assertLess(highest, first_cape)

    def test_race_rigs_stand_on_the_same_ground_plane(self) -> None:
        """Exact shared pelvis rest and grounded fitted source soles."""
        heights = []
        for model_id, entry in self.catalog["races"].items():
            with self.subTest(model=model_id):
                heights.append(entry["hipHeight"])
                self.assertLess(abs(entry["groundHeight"]), .003)
                document, binary = glb_chunks(ROOT / entry["path"])
                points, joints, weights = [], [], []
                for mesh in document['meshes']:
                    if mesh['name'] not in ('body', 'wardrobe_boots'):
                        continue
                    for primitive in mesh['primitives']:
                        attrs = primitive['attributes']
                        points.extend(accessor_rows(document, binary, attrs['POSITION']))
                        joints.extend(accessor_rows(document, binary, attrs['JOINTS_0']))
                        weights.extend(accessor_rows(document, binary, attrs['WEIGHTS_0']))
                names = [document["nodes"][j]["name"] for j in document["skins"][0]["joints"]]
                for side in ("l", "r"):
                    feet = {names.index("foot_" + side), names.index("ball_" + side)}
                    sole = [point[1] for point, jj, ww in zip(points, joints, weights)
                            if sum(w for j, w in zip(jj, ww) if j in feet) > .5]
                    self.assertTrue(sole)
                    # A low tail must not conceal floating feet in min(bounds).
                    self.assertLess(abs(min(sole)), .025)
        self.assertLess(max(heights) - min(heights), 1e-5)

    def test_shared_bodies_and_source_replacements_retain_distinct_heads(self) -> None:
        """Compare actual below-neck triangles and weights, excluding tails.

        Every race is rebased onto the Human (sharedBodyShape.version >= 3):
        it must carry the regenerated luminous_<sex> body byte for byte below
        the neck and pin that file's SHA, so any later Human edit forces the
        rebase to be rebuilt. Each race/sex keeps its own head above it.
        """
        from collections import Counter
        import hashlib
        import numpy as np
        sys.path.insert(0, str(ROOT / "eloria-assets/tools"))
        import equipment_authoring as ea
        from verify_shared_player_bodies import primitives, signatures, GEOMETRY_FIELDS

        def geometry(document, blob, lower, origin, axis):
            result = Counter()
            for name, role, attrs, faces in primitives(document, blob):
                if name not in ea.BODY_SURFACES or role in ("race_tail", "neck_join"):
                    continue
                height = (attrs["POSITION"] - origin) @ axis
                selected = (height[faces] < .075 - 1e-6).all(1) if lower else (height[faces] > .110 + 1e-6).all(1)
                result.update(signatures(attrs, faces[selected], GEOMETRY_FIELDS))
            return result
        expected = {}
        heads = set()
        for gender in ("male", "female"):
            human = "luminous_" + gender
            path = ROOT / self.catalog["races"][human]["path"]
            rig = ea.load_rig(path, ea.BODY_SURFACES)
            origin = rig.origin("neck_01")
            axis = rig.origin("Head") - origin
            axis /= np.linalg.norm(axis)
            d, binary = ea.read_glb(path)
            expected[gender] = geometry(d, binary, True, origin, axis)
            self.assertGreater(sum(expected[gender].values()), 10_000)
            human_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            for slug, entry in self.catalog["races"].items():
                if not slug.endswith("_" + gender):
                    continue
                with self.subTest(model=slug):
                    self.assertEqual(human, entry["bodyTemplate"])
                    self.assertEqual(entry["bodyTemplate"], self.models["models"][slug]["bodyTemplate"])
                    document, blob = ea.read_glb(ROOT / entry["path"])
                    if slug != human:
                        self.assertGreaterEqual(entry.get("sharedBodyShape", {}).get("version", 0), 3)
                        self.assertEqual(expected[gender], geometry(document, blob, True, origin, axis))
                        self.assertEqual(human_sha, entry["sharedBodyShape"]["templateSHA256"])
                        self.assertEqual(human_sha, document["asset"]["extras"]["sharedBodyShape"]["templateSHA256"])
                    self.assertIn(slug, self.equipment['refittedBodies'])
                    heads.add(tuple(sorted(geometry(document, blob, False, origin, axis).items())))
                    # Approved stature scales the whole actor and its equipment;
                    # shared authoring geometry does not require equal race heights.
                    self.assertAlmostEqual(entry["stature"], self.models["models"][slug]["import"]["scale"])
        self.assertNotEqual(expected["male"], expected["female"])
        self.assertEqual(16, len(heads), "each race/sex keeps its own head geometry")

    def test_race_rigs_keep_the_shared_animation_contract(self) -> None:
        """Name-only retargeting requires the actual library Rest_Pose."""
        library, binary = glb_chunks(CLIENT / "assets/actors/native/shared/Universal_Animation_Library.glb")
        clip = next(a for a in library["animations"] if a["name"] == "Rest_Pose")
        expected = {i: dict(n) for i, n in enumerate(library["nodes"])}
        for channel in clip["channels"]:
            sampler = clip["samplers"][channel["sampler"]]
            # Rest channels may begin at frame one. Sampling time zero clamps
            # to that first key; it must not fall back to the posed defaults.
            self.assertGreaterEqual(accessor_rows(library, binary, sampler["input"])[0][0], 0.0)
            expected[channel["target"]["node"]][channel["target"]["path"]] = accessor_rows(library, binary, sampler["output"])[0]
        by_name = {("Head" if n["name"] == "head" else n["name"]): n for n in expected.values()}
        reference = None
        for model_id, entry in sorted(self.catalog["races"].items()):
            document = glb_document(ROOT / entry["path"])
            joints = document["skins"][0]["joints"]
            rig = {document["nodes"][j]["name"]: document["nodes"][j] for j in joints}
            if reference is None:
                reference = rig
            for name, node in rig.items():
                with self.subTest(model=model_id, bone=name):
                    wanted = by_name.get(name, reference[name])
                    for key, default in [("translation", (0, 0, 0)), ("rotation", (0, 0, 0, 1)), ("scale", (1, 1, 1))]:
                        for actual, target in zip(node.get(key, default), wanted.get(key, default)):
                            self.assertAlmostEqual(actual, target, delta=1e-5)

    def test_race_features_carry_material_detail(self) -> None:
        """Source scale, stone and fungus detail survives in the body atlas."""
        for model_id, entry in self.catalog["races"].items():
            document = glb_document(ROOT / entry["path"])
            mesh = next(m for m in document["meshes"] if m["name"].lower() == "body")
            material = document["materials"][mesh["primitives"][0]["material"]]
            with self.subTest(model=model_id):
                self.assertIn("baseColorTexture", material["pbrMetallicRoughness"])
                self.assertEqual([0, 0, 0], material.get("emissiveFactor", [0, 0, 0]))
                self.assertEqual(entry["sourceSHA256"], document["asset"]["extras"]["sourceSHA256"])

    def test_wardrobe_carries_material_detail(self) -> None:
        """Garment tint has its own atlas; generated headwear is plain cloth."""
        for model_id, entry in self.catalog["races"].items():
            document = glb_document(ROOT / entry["path"])
            meshes = {m["name"].lower(): m for m in document["meshes"]}
            skin_material = meshes["body"]["primitives"][0]["material"]
            for name in ("wardrobe_shirt", "wardrobe_pants", "wardrobe_boots"):
                primitive = meshes[name]["primitives"][0]
                material = document["materials"][primitive["material"]]
                with self.subTest(model=model_id, mesh=name):
                    self.assertNotEqual(skin_material, primitive["material"])
                    self.assertIn("baseColorTexture", material["pbrMetallicRoughness"])
                    self.assertGreater(material["pbrMetallicRoughness"]["roughnessFactor"], 0.5)

    def test_human_cultures_retain_distinct_head_sources(self) -> None:
        """The shared bodies retain heads from ten distinct human source models."""
        human = {"luminous", "votary", "glasswarden", "orun", "greyhaven"}
        sources = [entry["sourceSHA256"] for slug, entry in self.catalog["races"].items() if slug.rsplit("_", 1)[0] in human]
        self.assertEqual(10, len(sources))
        self.assertEqual(10, len(set(sources)))

    def test_shared_necks_have_matching_shading_and_skinning(self) -> None:
        import numpy as np
        sys.path.insert(0, str(ROOT / "eloria-assets/tools"))
        import equipment_authoring as ea
        from verify_shared_player_bodies import primitives, neck_join_checks
        for slug, entry in self.catalog["races"].items():
            path = ROOT / entry["path"]
            d, b = ea.read_glb(path)
            with self.subTest(model=slug):
                if entry.get('sourceIntegration'):
                    # These bodies keep their source neck, with no artificial
                    # join. Welded copies must still deform together.
                    from fit_character_appearance import combined, weld, average
                    from shared_player_bodies import dense_weights
                    a, _ = combined([p for p in primitives(d, b) if p[0] in ea.BODY_SURFACES])
                    weights = dense_weights(a)
                    np.testing.assert_allclose(weights, average(weights, weld(a['POSITION'])), atol=2e-6)
                    self.assertEqual(0, entry['neckAdaptorTriangles'])
                    self.assertFalse(any(p[1] == 'neck_join' for p in primitives(d, b)))
                    continue
                self.assertIn("neckBase", d["asset"]["extras"]["sharedBodyShape"])
                plane = None
                if d["asset"].get("extras", {}).get("appearanceFit"):
                    rig = ea.load_rig(path, ea.BODY_SURFACES)
                    origin = rig.origin("neck_01")
                    axis = rig.origin("Head") - origin
                    axis /= np.linalg.norm(axis)
                    plane = (origin, axis, d["asset"]["extras"]["sharedBodyShape"]["upperCutM"])
                edges, a = neck_join_checks(list(primitives(d, b)), boundary_plane=plane)
                self.assertGreater(edges["geometricEdges"], 30)
                self.assertEqual(0, edges["unmatchedEdges"])
                self.assertEqual(0, a["unmatchedCopies"])
                self.assertGreater(a["boundaryCopies"], 30)
                self.assertLess(a["maxPositionDeltaM"], 1e-6)
                self.assertLess(a["maxNormalDelta"], 2e-6)
                self.assertLess(a["maxWeightL1Delta"], 2e-6)

    def test_race_eyes_are_not_all_the_human_one(self) -> None:
        """Tintable eyes use each body's original painted texture region."""
        eyes = {}
        for model_id, entry in self.catalog["races"].items():
            document, binary = glb_chunks(ROOT / entry["path"])
            mesh = next(m for m in document["meshes"] if m["name"].lower() == "eyes")
            primitive = mesh["primitives"][0]
            self.assertGreater(document["accessors"][primitive["indices"]]["count"], 0)
            material = document["materials"][primitive["material"]]
            index = material["pbrMetallicRoughness"]["baseColorTexture"]["index"]
            image = document["images"][document["textures"][index]["source"]]
            view = document["bufferViews"][image["bufferView"]]
            start = view.get("byteOffset", 0)
            eyes[model_id] = binary[start:start + view["byteLength"]]
        self.assertEqual(16, len(set(eyes.values())))

    def test_optional_headwear_fits_the_current_surface_contract(self) -> None:
        """All sources provide toggled headwear and a closed bald scalp."""
        for model_id, entry in self.catalog["races"].items():
            document = glb_document(ROOT / entry["path"])
            present = {n["name"].lower() for n in document["nodes"] if "mesh" in n}
            with self.subTest(model=model_id):
                self.assertTrue({"scalp", "wardrobe_head_band", "wardrobe_head_cap"} <= present)
                self.assertNotIn("hair", present)
                self.assertEqual(not model_id.startswith("mycelari_"), "eyebrows" in present)

    def test_native_hair_is_authored_geometry_in_head_local_space(self) -> None:
        for hair_id, entry in self.catalog["hair"].items():
            with self.subTest(hair=hair_id):
                document = glb_document(ROOT / entry["path"])
                self.assertEqual([], document.get("skins", []))
                self.assertGreater(entry["vertices"], 400)
                self.assertLess(entry["bounds"]["min"][1], .12)
                self.assertLess(entry["bounds"]["max"][1], .31)

    def test_creatures_have_new_rigs_and_embedded_clips(self) -> None:
        """Assert the runtime rig contract rather than a fixed bone count.

        The bone count is an authoring detail and grew when the creatures were
        rebuilt with articulated tails and a chest bone.  What the client
        actually depends on is the attachment bone names, a single root, and
        the exact clip names named by data/animations/creature.json - so those
        are what this test pins.
        """
        sys.path.insert(0, str(ROOT / "eloria-assets" / "tools"))
        import creature_roster
        # The concept-art roster occupies one contiguous block after every
        # range already in models.json; the server adopts these ids.
        expected_actor_types = set(range(204, 236)) | set(
            range(428, 428 + len(creature_roster.ROSTER)))
        actual_actor_types = {entry["actor_type"] for entry in self.catalog["creatures"].values()}
        self.assertEqual(expected_actor_types, actual_actor_types)
        animation_map = json.loads(
            (CLIENT / "data/animations/creature.json").read_text())
        required_clips = set(animation_map["actions"].values())
        for slug, entry in self.catalog["creatures"].items():
            with self.subTest(creature=slug):
                document = glb_document(ROOT / entry["path"])
                skin = document["skins"][0]
                bone_names = [document["nodes"][j].get("name") for j in skin["joints"]]
                self.assertEqual(len(bone_names), len(set(bone_names)),
                                 "bone names are unique")
                for required in ("root", "body", "neck", "head", "jaw"):
                    self.assertIn(required, bone_names)
                self.assertLessEqual(len(skin["joints"]), 64,
                                     "creature rigs stay within a sane bone budget")
                parented = {c for node in document["nodes"]
                            for c in node.get("children", [])}
                roots = [j for j in skin["joints"] if j not in parented]
                self.assertEqual(1, len(roots), "exactly one root bone")
                clips = {a["name"] for a in document["animations"]}
                self.assertTrue(required_clips.issubset(clips),
                                f"missing {sorted(required_clips - clips)}")
                self.assertEqual(slug, self.models["actorTypes"][str(entry["actor_type"])])

    def test_creature_glbs_pass_structural_validation(self) -> None:
        """Skinning, grounding and animation checks over the checked-in GLBs."""
        try:
            import numpy  # noqa: F401
        except ImportError:  # pragma: no cover - environment without numpy
            self.skipTest("numpy is required for skinned animation validation")
        sys.path.insert(0, str(ROOT / "eloria-assets" / "tools"))
        import validate_creature_glbs as validator

        animation_map = json.loads(
            (CLIENT / "data/animations/creature.json").read_text())
        required_clips = sorted(set(animation_map["actions"].values()))
        attachments = sorted({bone for model in self.models["models"].values()
                              if str(model.get("animationMap", "")).endswith("creature.json")
                              for bone in model.get("attachments", {}).values()})
        entries = dict(self.catalog["creatures"])
        entries.update(self.catalog.get("ambientCreatures", {}))
        for slug, entry in entries.items():
            with self.subTest(creature=slug):
                path = ROOT / entry["path"]
                document, binary = validator.read_glb(path)
                problems, _ = validator.check(document, binary, path,
                                              required_clips, attachments,
                                              bool(entry.get("hovers")))
                self.assertEqual([], problems)

    def test_nymara_invasion_actor_types_resolve_to_native_models(self) -> None:
        self.assertEqual(set(range(400, 428)), set(NYMARA_INVASION_MODELS))
        for actor_type, (creature_type, model_id) in NYMARA_INVASION_MODELS.items():
            with self.subTest(actor_type=actor_type, creature=creature_type):
                self.assertEqual(model_id, self.models["actorTypes"][str(actor_type)])
                model = self.models["models"][model_id]
                scene = CLIENT / model["scene"].removeprefix("res://")
                document = glb_document(scene)
                self.assertTrue(document.get("meshes"), model_id)
                self.assertTrue(document.get("animations"), model_id)

    def test_every_equipment_visual_is_registered(self) -> None:
        expected = {f"{entry['part']}:{entry['visual']}"
                    for entry in self.catalog["equipment"].values()}
        for entry in self.catalog["genericEquipment"].values():
            expected |= {f"{entry['part']}:{visual}" for visual in entry["visuals"]}
        # Footwear is its own section: sixty-four authored meshes, one visual id
        # each, rather than one mesh under a ladder of tints.
        expected |= {f"{entry['part']}:{entry['visual']}"
                     for entry in self.catalog.get("footwear", {}).values()}
        self.assertEqual(expected, set(self.equipment["models"]))
        for entry in self._all_equipment():
            glb_document(ROOT / entry["path"])

    def test_footwear_block_is_whole_and_does_not_collide(self) -> None:
        """The sixty-four designs occupy one clean run of the part-6 byte.

        ``ACTOR_WEAR_ITEM`` packs the visual into a single byte, and the same
        byte position in ``ADD_ACTOR`` carries the character's appearance boot
        index when nothing is equipped.  That index comes from a creation slider
        that tops out at 5 and from ``(seed // 23) % 5`` for NPCs, and the
        registry answers it out of the same table - which is why 6:0-6:12 are
        the generic boots and may not be reassigned.  This block starts far
        above anything the appearance byte can produce.
        """
        footwear = self.catalog.get("footwear", {})
        self.assertEqual(64, len(footwear), "sixty-four designs are expected")
        visuals = sorted(entry["visual"] for entry in footwear.values())
        self.assertEqual(list(range(128, 192)), visuals,
                         "the block is 6:128-6:191, unbroken")
        legacy = {int(key.split(":")[1]) for key in self.equipment["models"]
                  if key.startswith("6:")} - set(visuals)
        self.assertTrue(legacy <= set(range(0, 13)) | set(range(100, 107)),
                        f"an unexpected part 6 id survives: {sorted(legacy)}")
        for entry in footwear.values():
            self.assertEqual(6, entry["part"])
            self.assertTrue((ROOT / entry["path"]).is_file(), entry["path"])
            for variant in entry["variants"].values():
                path = (CLIENT / "assets" / "actors" / "native" / "equipment"
                        / f"{variant}.glb")
                self.assertTrue(path.is_file(), str(path))

    def _all_equipment(self):
        return (list(self.catalog["equipment"].values())
                + list(self.catalog["genericEquipment"].values())
                + list(self.catalog.get("footwear", {}).values()))

    def test_legacy_visual_ids_render_as_themselves(self) -> None:
        """The alias table existed only because the legacy tier had no models.

        Weapon 11, shield 5 and cape 11 were redirected to Four Gates guard gear.
        They are STAFF_4, SHIELD_BRONZE and CAPE_GOLD, so with the generic tier
        authored an alias would hijack three ids every actor can legitimately
        wear. Bespoke NPC gear comes from npcLooks, which names native ids.
        """
        self.assertEqual({}, self.equipment["aliases"])
        for legacy in ("0:11", "1:5", "2:11"):
            self.assertIn(legacy, self.equipment["models"])
        for native in ("0:112", "1:105", "2:105"):
            self.assertIn(native, self.equipment["models"])
        guard_look = self.models["npcLooks"]["301"]["equipmentVisuals"]
        self.assertEqual({"0": 112, "1": 105, "2": 105}, guard_look)

    def test_equipment_registry_is_schema_three(self) -> None:
        """Sockets and skinned garments replace the identity bone parenting.

        Schema 2 attached every piece to a raw bone with an identity transform.
        Bone rest bases are not axis aligned, so that alone put weapons through
        the actor sideways; the registry now has to carry a socket per rigid
        part and a skin region per garment.
        """
        self.assertEqual(3, self.equipment["schemaVersion"])
        rig = glb_document(CLIENT / "assets/actors/native/races/luminous_male.glb")
        joints = {rig["nodes"][node].get("name", "")
                  for node in rig["skins"][0]["joints"]}
        head = next(node for node in rig["nodes"] if node.get("name") == "Head")
        self.assertIn("canonicalHeadRestY", self.equipment)
        self.assertGreater(float(self.equipment["canonicalHeadRestY"]), 1.0)
        for part, socket in self.equipment["sockets"].items():
            with self.subTest(part=part):
                self.assertIn(socket["bone"], joints)
                self.assertEqual(3, len(socket["offset"]))
                self.assertEqual(3, len(socket["rotationDegrees"]))
        for region, bones in self.equipment["skinRegions"].items():
            with self.subTest(region=region):
                self.assertTrue(bones)
                self.assertTrue(set(bones) <= joints)
        del head

    def test_boots_follow_both_feet(self) -> None:
        """Boots used to hang off the pelvis, which parked them at the hips."""
        self.assertEqual("feet", self.equipment["parts"]["6"]["attachment"])
        feet = self.models["models"]["luminous_male"]["attachments"]["feet"]
        self.assertEqual(["foot_l", "foot_r"], feet)

    def test_socketed_props_and_skinned_garments_are_declared(self) -> None:
        garment_parts = {2, 4, 5, 6}
        for key, model in self.equipment["models"].items():
            part = int(key.split(":")[0])
            with self.subTest(model=key):
                # Gloves are worn on the weapon part but cover both hands, so
                # attachment is declared per model, not inferred from the part.
                if part in garment_parts:
                    self.assertEqual("skinned", model["attach"])
                if model["attach"] == "skinned":
                    self.assertIn(model["skinRegion"], self.equipment["skinRegions"])
                else:
                    socket = model.get("socket") or self.equipment["sockets"][str(part)]
                    self.assertTrue(socket["bone"])

    def test_garments_ship_skinned_to_the_shared_rig(self) -> None:
        """A garment bolted to one bone cannot bend; these carry skin weights."""
        rig = glb_document(CLIENT / "assets/actors/native/races/luminous_male.glb")
        expected = [rig["nodes"][node].get("name", "")
                    for node in rig["skins"][0]["joints"]]
        checked = 0
        for entry in self._all_equipment():
            if entry["attach"] != "skinned":
                continue
            with self.subTest(equipment=entry["id"]):
                document = glb_document(ROOT / entry["path"])
                skin = document["skins"][0]
                names = [document["nodes"][node].get("name", "")
                         for node in skin["joints"]]
                self.assertEqual(expected, names)
                for mesh in document["meshes"]:
                    for primitive in mesh["primitives"]:
                        self.assertIn("JOINTS_0", primitive["attributes"])
                        self.assertIn("WEIGHTS_0", primitive["attributes"])
                checked += 1
        # A floor rather than an exact count: the number of skinned garments
        # grows every time a design set lands, and a test that has to be edited
        # to add a garment teaches people to edit it without reading it.  What
        # matters is that the sweep ran and found them.  The floor is raised
        # when a set lands so it keeps meaning something - 47 before any of the
        # rebuilds, plus sixty-four footwear designs.
        self.assertGreaterEqual(checked, 47 + 64)

    def test_equipment_hides_name_real_body_surfaces(self) -> None:
        """A hide that names nothing would silently fail to cover anything."""
        rig = glb_document(CLIENT / "assets/actors/native/races/luminous_male.glb")
        surfaces = {mesh.get("name", "").lower() for mesh in rig["meshes"]}
        surfaces.add("hair")
        for part, config in self.equipment["parts"].items():
            for surface in config.get("hides", []):
                with self.subTest(part=part, surface=surface):
                    self.assertIn(surface.removesuffix("_trim").removesuffix("_seam"), surfaces)
        for key, model in self.equipment["models"].items():
            for surface in model.get("hides", []):
                with self.subTest(model=key, surface=surface):
                    self.assertIn(surface.removesuffix("_trim").removesuffix("_seam"), surfaces)
        self.assertEqual(["wardrobe_shirt", "wardrobe_shirt_trim"],
                         self.equipment["parts"]["5"]["hides"])

    def test_equipment_is_authored_at_body_scale(self) -> None:
        """The first pass shipped helmets and amulets at three to five times
        body scale, which swallowed the actor wearing them."""
        limits = {0: (.55, 2.00), 1: (.35, .95), 2: (.80, 1.60), 3: (.18, .60),
                  4: (.60, 1.30), 5: (.45, 1.60), 6: (.30, .70), 7: (.10, .40)}
        for entry in self._all_equipment():
            document = glb_document(ROOT / entry["path"])
            extents = []
            for accessor in document["accessors"]:
                if "min" in accessor and len(accessor["min"]) == 3:
                    extents.append(max(high - low for low, high
                                       in zip(accessor["min"], accessor["max"])))
            low, high = limits[entry["part"]]
            with self.subTest(equipment=entry["id"]):
                self.assertTrue(extents, entry["id"])
                self.assertGreaterEqual(max(extents), low)
                self.assertLessEqual(max(extents), high)

    def test_equipment_carries_material_detail(self) -> None:
        """Equipment shipped untextured beside a body with fifteen maps."""
        for entry in self._all_equipment():
            document = glb_document(ROOT / entry["path"])
            with self.subTest(equipment=entry["id"]):
                self.assertGreaterEqual(len(document.get("materials", [])), 2)
                self.assertTrue(document.get("images"))
                for material in document["materials"]:
                    self.assertIn("normalTexture", material)
                self.assertGreaterEqual(entry["triangles"], 240)

    def test_every_playable_actor_type_has_creation_option(self) -> None:
        options = self.models["creationOptions"]
        self.assertEqual(16, len(options))
        for option in options:
            actor_type = str(option["actorType"])
            self.assertEqual(option["model"], self.models["actorTypes"][actor_type])
            self.assertIn(option["model"], self.models["models"])

    def test_model_resources_stay_inside_godot_project(self) -> None:
        for model_id, entry in self.models["models"].items():
            with self.subTest(model=model_id):
                for field in ("scene", "animationLibrary", "animationMap"):
                    resource = entry.get(field)
                    if not resource:
                        continue
                    self.assertTrue(resource.startswith("res://"), resource)
                    relative = resource.removeprefix("res://")
                    self.assertNotIn("..", Path(relative).parts, resource)
                    path = CLIENT / relative
                    self.assertTrue(path.is_file(), resource)
                    if path.suffix == ".gltf":
                        document = json.loads(path.read_text())
                        for dependency in [
                            *(buffer["uri"] for buffer in document.get("buffers", []) if "uri" in buffer),
                            *(image["uri"] for image in document.get("images", []) if "uri" in image),
                        ]:
                            self.assertTrue((path.parent / dependency).is_file(), dependency)
                for resource in entry.get("hairStyles", []):
                    self.assertTrue(resource.startswith("res://"), resource)
                    self.assertTrue((CLIENT / resource.removeprefix("res://")).is_file(), resource)

    def test_runtime_does_not_synthesize_placeholder_hair(self) -> None:
        source = (CLIENT / "src/actors/replicated_actor_3d.gd").read_text()
        self.assertNotIn("func _hair_piece", source)
        self.assertIn('native_hair.name = "NativeHair"', source)
        self.assertIn('model_config.get("hairStyles"', source)

    def test_character_preview_uses_player_model_registry(self) -> None:
        source = (CLIENT / "src/app/main.gd").read_text()
        start = source.index("func _refresh_creation_preview()")
        end = source.index("func _on_login_pressed()", start)
        preview = source[start:end]
        self.assertIn('"kind": 1', preview)
        for option in self.models["creationOptions"]:
            self.assertEqual(
                option["model"],
                self.models["actorTypes"][str(option["actorType"])])

    def test_every_rig_declares_the_correction_its_facing_needs(self) -> None:
        """A model's forward-axis correction must match how its rig is built.

        Get it wrong and the body runs backwards: it slides along its heading
        tail first, which is what a blanket 180 default once did to every
        creature in the library.

        The races are one family, authored looking down +Z at the
        creation-preview camera, and their cape says which way that is. The
        creatures are not one family. 163 of them are built muzzle-first down
        -Z and need no turn; the other 57 - an auto-rigged batch with no jaw
        bone, which is why the jaw this test used to read raised KeyError on
        every one of them rather than checking anything - are authored the
        other way round and need the half turn. `tools/creature_facing.py`
        measures which, from landmarks whose order along a body is known.
        """
        set_by_eye = {
            # No head, tail, named legs or jaw: a shell with eight legs off a
            # single spine bone. Turned by eye from a front render, where 180
            # is the view with the claws and eyestalks in it.
            "crystal_shore_crab": 180,
            # A hovering flame on a Bone_NNN rig: every landmark it has
            # weighs under the threshold and they disagree by 180 degrees,
            # so the measurement is noise rather than a bearing. Set from
            # textured orthographic renders down both Z axes - the pale
            # front faces -Z and the dark back faces +Z, so it needs no
            # turn, and its narrow profiles rule out the quarter turns.
            "ember_leaf_spirit": 0,
        }
        # Hand-authored rigs keep the Bone_NNN naming Meshy gave them, so
        # creature_facing finds no landmark on any of them and measures
        # None. The landmarks are there; only the names are missing, and
        # the animation pipeline's own classifier labels them from
        # geometry. These are that classifier's landmarks put through this
        # tool's yaw maths unchanged - same pairs, same weighting, same
        # rounding - a route that reproduced creature_facing exactly on ten
        # of ten models the tool can read for itself. Not eyeballed:
        # measured, by the only reading of these rigs available.
        set_by_classifier = {
            "obsidian_bear": 180,
            "skystripe_antelope": 180,
            "giant_badger": 180,
            "crystalback_tortoise": 180,
            "azure_hyena": 180,
            # the procedural ram this replaced faced the other way, so its
            # entry carried 0 until the art changed under it
            "thunder_ram": 180,
            "ashen_wolf": 180,
            "cave_salamander": 180,
            "gloom_wyvern": 180,
            "barnacle_ogre": 180,
            # these two carry a constant facing correction in the
            # animation itself, which the delivery notes call out
            "sapphire_peafowl": 270,
            "mire_kelpie": 270,
        }
        declared = dict(set_by_eye)
        declared.update(set_by_classifier)
        # The compact expansion rigs omit jaw landmarks, and some bodies
        # have no directional bone pairs. Their authored axes are recorded
        # with the source hashes after checking textured client renders.
        expansion = json.loads((CLIENT / "data/actors/basic_creature_expansion.json").read_text())
        declared.update({entry["type"]: entry["forwardAxisCorrectionDegreesY"]
                         for entry in expansion["creatures"]})
        for model_id, entry in self.models["models"].items():
            scene = entry["scene"].removeprefix("res://")
            with self.subTest(model=model_id):
                correction = entry["import"]["forwardAxisCorrectionDegreesY"]
                if "/races/" in scene:
                    # The cape hangs off the back, so the back is whichever
                    # way its anchor points and the face is the other way.
                    facing = -bone_translations(CLIENT / scene)["cape_c_01"][2]
                    self.assertNotEqual(0.0, facing, "the rig states a facing")
                    self.assertEqual(180 if facing > 0 else 0, correction,
                                     "a rig already facing -Z must not be turned")
                    continue
                measured = creature_facing.correction(CLIENT / scene)
                if measured is None:
                    self.assertIn(model_id, declared,
                                  "a body no landmark speaks for needs a person "
                                  "to look at a render of it")
                    measured = declared[model_id]
                self.assertEqual(measured, correction,
                                 "the declared correction must be the one the "
                                 "body measures")

    def test_rebuilding_the_registry_keeps_what_the_catalogue_holds(self) -> None:
        """Rebuilding models.json must not revert what the file already says.

        eloria-assets/tools/build_native_nymara_glbs.py writes this file from
        its own tables, and those tables are neither the whole library nor the
        last word on the bodies in it.  Run with --models it used to rewrite
        every entry from scratch, which reverted five landed changes at once
        and did it silently, because a generated file rewritten wholesale
        looks exactly like the generator working:

          * 69 creature sizes back to 1.  The GLBs are all exported normalised
            to 1.7 m, so import.scale is the whole of what draws a fox smaller
            than a boar, and losing it put the roster back to one height.
          * 85 facings back to 0.  The creature rigs are two families authored
            facing opposite ways, and a body turned the wrong way runs
            backwards - a wolf attacking with the back of its head.
          * 55 reviewed creatures and their 73 actor types deleted outright.
          * 22 invasion actor types back to their pre-review stand-ins.
          * 16 NPC looks deleted and 56 wardrobes refilled from a stale table,
            which draws a placeholder blob on the bone.

        The rule, taken from the equipment side: the tool authors the lines it
        owns and keeps everything else the catalogue holds.  So a rebuild over
        this file is a no-op, and that is what this asserts.
        """
        try:
            import numpy  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError:  # pragma: no cover - environment without them
            self.skipTest("the actor library generator needs numpy and Pillow")
        sys.path.insert(0, str(ROOT / "eloria-assets" / "tools"))
        import build_native_nymara_glbs as generator

        registry = CLIENT / "data/actors/models.json"
        rebuilt = generator.build_model_registry()

        # The generator's own output, before the rule is applied. Asserted so
        # this test cannot pass by the tables happening to agree with the
        # file: it is the revert, and every check below is what stops it.
        self.assertNotEqual(self.models["models"], rebuilt["models"],
                            "the generator's tables no longer differ from the "
                            "catalogue, so this test is checking nothing")

        generator.carry_forward_registry(registry, rebuilt)

        for slug, entry in self.models["models"].items():
            with self.subTest(model=slug):
                self.assertIn(slug, rebuilt["models"],
                              "a model the generator does not define is still "
                              "a model the client has to draw")
                for field in ("scale", "forwardAxisCorrectionDegreesY"):
                    self.assertEqual(
                        entry["import"][field],
                        rebuilt["models"][slug]["import"][field],
                        f"{field} is measured off this body, not known here")
        for section in ("actorTypes", "npcLooks"):
            self.assertEqual(self.models[section], rebuilt[section],
                             f"{section} the catalogue holds must survive")

        # Byte for byte, not just entry for entry: an entry carried to the end
        # of the file instead of left where it sits reindents everything after
        # it, and a diff nobody can read is how the reverts went unnoticed.
        self.maxDiff = 2000
        self.assertEqual(registry.read_text(encoding="utf-8"),
                         json.dumps(rebuilt, indent=2) + "\n",
                         "a rebuild over this catalogue must change nothing")

    def test_a_model_the_catalogue_has_never_held_is_seeded(self) -> None:
        """The other half of the rule: a new body still gets its defaults.

        Preserving what the catalogue holds is only correct if a body the
        catalogue does not hold is still written. Every model in this file is
        already in it, so nothing exercises that path against the shipped
        registry - which is exactly how a merge that quietly dropped new
        models would ship. Run it against a catalogue with one entry removed
        instead, and the entry must come back at the generator's seed.
        """
        try:
            import numpy  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError:  # pragma: no cover - environment without them
            self.skipTest("the actor library generator needs numpy and Pillow")
        sys.path.insert(0, str(ROOT / "eloria-assets" / "tools"))
        import build_native_nymara_glbs as generator

        seeded = "dire_wolf"
        self.assertIn(seeded, self.models["models"], "a creature this builds")
        thinned = json.loads(json.dumps(self.models))
        del thinned["models"][seeded]
        del thinned["actorTypes"][str(409)]

        with tempfile.TemporaryDirectory() as directory:
            catalogue = Path(directory) / "models.json"
            catalogue.write_text(json.dumps(thinned, indent=2) + "\n",
                                 encoding="utf-8")
            rebuilt = generator.build_model_registry()
            generator.carry_forward_registry(catalogue, rebuilt)

        self.assertEqual(rebuilt["models"][seeded]["import"]["scale"], 1,
                         "a body the catalogue has never held is seeded at 1")
        self.assertEqual(
            rebuilt["models"][seeded]["import"]["forwardAxisCorrectionDegreesY"],
            0, "and at the generator's facing, which the facing test checks")
        self.assertEqual("dire_wolf", rebuilt["actorTypes"]["409"],
                         "an actor type it has never held is written too")
        # Seeding one entry must not disturb the entries either side of it.
        for slug in ("amethyst_scorpion", "abyssal_armored_fish"):
            with self.subTest(model=slug):
                self.assertEqual(self.models["models"][slug],
                                 rebuilt["models"][slug])

    def test_reseeding_the_registry_still_keeps_models_it_cannot_define(self) -> None:
        """--reseed discards tuning, never the library.

        It is the way back after editing a seed the generator owns - a race's
        ANATOMY stature - and it says how many entries it reverts, because a
        silent revert is the thing the rule exists to stop. What it must not
        do is take the reviewed creatures with it: the generator has no table
        for them, so dropping them is not a revert to anything.
        """
        try:
            import numpy  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError:  # pragma: no cover - environment without them
            self.skipTest("the actor library generator needs numpy and Pillow")
        sys.path.insert(0, str(ROOT / "eloria-assets" / "tools"))
        import build_native_nymara_glbs as generator

        registry = CLIENT / "data/actors/models.json"
        rebuilt = generator.build_model_registry()
        undefined = set(self.models["models"]) - set(rebuilt["models"])
        self.assertTrue(undefined, "the reviewed creatures are in this file")

        generator.carry_forward_registry(registry, rebuilt, reseed=True)
        self.assertLessEqual(undefined, set(rebuilt["models"]),
                             "reseeding a value must not delete a body")
        self.assertEqual(self.models["actorTypes"].keys(),
                         rebuilt["actorTypes"].keys(),
                         "nor the actor types that spawn one")
        reseeded = [slug for slug in rebuilt["models"]
                    if slug not in undefined
                    and rebuilt["models"][slug]["import"]["scale"]
                    != self.models["models"][slug]["import"]["scale"]]
        self.assertTrue(reseeded, "and it does take the generator's numbers")

    def test_concept_npc_roster_uses_player_models_and_native_gear(self) -> None:
        self.assertEqual(62, len(self.models["npcLooks"]))
        for actor_type, look in self.models["npcLooks"].items():
            with self.subTest(actor_type=actor_type):
                self.assertEqual(look["model"], self.models["actorTypes"][actor_type])
                self.assertIn(look["model"], self.models["models"])
                for part, visual in look["equipmentVisuals"].items():
                    self.assertIn(f"{part}:{visual}", self.equipment["models"])


if __name__ == "__main__":
    unittest.main()
