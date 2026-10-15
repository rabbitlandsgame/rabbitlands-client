#!/usr/bin/env python3
"""The registry contract that lets one garment fit sixteen different bodies.

Generated garments have original-art male/female body fits and retained-head variants. Their
shared skeleton needs no runtime girth or rest-height correction. The registry
also retains a legacy fit profile for existing procedural garments and props.

* ``bodyGirth`` and ``footAnchor`` describe current weighted body geometry.
* ``fitGroups`` select the shared male/female garment or the individual head
  variant. ``bodyTemplates`` prevent repeating a fit on identical body geometry.
* ``fitProfiles.legacy`` preserves the old measurements and scale for items
  outside the source-equipment rebuild.
* ``authoringRigs`` names the installed race body behind an ``authoredFor``
  label that is deliberately not a measured rig. The Human-only variants are
  authored for ``human_male``/``human_female``: with no girth or foot anchor
  under that label the client wears them exactly as fitted, while the checks
  here still measure them on the body they were fitted to.

A break in either one is silent in the editor and obvious on a player, so the
shape of the data is checked here rather than discovered in a screenshot.
"""
from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "godot-client"
EQUIPMENT = Path(os.environ.get("ELORIA_EQUIPMENT_REGISTRY", CLIENT / "data" / "actors" / "equipment.json"))
sys.path.insert(0, str(ROOT / "eloria-assets/tools"))
import equipment_authoring as ea
RACES = CLIENT / "assets" / "actors" / "native" / "races"

# Bones a garment can be bound to.  Every race has to be measured around all of
# them or the runtime has nothing to compare a wearer against.
REQUIRED_GIRTH_BONES = {
    "pelvis", "spine_01", "spine_02", "spine_03",
    "clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r",
    "thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r",
}


def scene_path(res_path: str) -> Path:
    return CLIENT / res_path.removeprefix("res://") if res_path.startswith("res://") else Path(res_path)


def authoring_rig(registry: dict, author: str) -> str:
    """The installed race body an ``authoredFor`` label was fitted on."""
    return str(registry.get("authoringRigs", {}).get(author, author))


class EquipmentFitTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(EQUIPMENT.read_text())
        cls.models = cls.registry["models"]
        cls.girth = cls.registry.get("bodyGirth", {})
        cls.groups = cls.registry.get("fitGroups", {})
        cls.races = sorted(path.stem for path in RACES.glob("*.glb"))

    def test_every_race_is_measured(self) -> None:
        self.assertTrue(self.races, "no race GLBs to measure")
        for race in self.races:
            self.assertIn(race, self.girth, f"{race} has no body measurements")
            missing = REQUIRED_GIRTH_BONES - set(self.girth[race])
            self.assertEqual(missing, set(), f"{race} is unmeasured around {missing}")
            for bone, radius in self.girth[race].items():
                self.assertGreater(float(radius), 0.0,
                                   f"{race}/{bone} measures no body at all")

    def test_generated_variants_use_two_bodies_and_individual_heads(self) -> None:
        import import_generated_equipment as batch
        templates = self.registry.get("bodyTemplates", {})
        self.assertEqual(set(self.races), set(templates))
        self.assertEqual({"luminous_male", "luminous_female"}, set(templates.values()))
        scenes = set()
        for piece in batch.roster():
            model = self.models[f"{piece.part}:{piece.visual}"]
            for race in self.races:
                resolved = dict(model)
                for group in self._named(self.groups[race]):
                    if group in model.get("variants", {}):
                        resolved.update(model["variants"][group])
                        break
                expected = race if piece.part == 3 else templates[race]
                self.assertEqual(expected, authoring_rig(self.registry, resolved["authoredFor"]),
                                 f"{race} {piece.slug}")
                scenes.add(resolved["scene"])
        self.assertEqual(1424, len(scenes))

    def test_measurements_are_plausible(self) -> None:
        # These sixteen approved bodies lie within this measured range.
        # A much larger value usually means a foot region included the tail
        # or an unweighted toe fell back to sampling the entire body.
        # Keep the authoring reference fixed when a playable body is replaced.
        reference = self.registry.get("authoredBodyGirth", self.girth).get("luminous_male", {})
        self.assertTrue(reference, "the reference rig is unmeasured")
        for race in self.races:
            for bone, radius in self.girth[race].items():
                base = float(reference.get(bone, 0.0))
                if base <= 0.0:
                    continue
                ratio = float(radius) / base
                self.assertGreater(ratio, 0.4, f"{race}/{bone} ratio {ratio:.2f}")
                self.assertLess(ratio, 2.0, f"{race}/{bone} ratio {ratio:.2f}")

    def test_replacement_bodies_have_current_measurements_and_separate_authors(self):
        for slug in self.registry.get('refittedBodies', []):
            with self.subTest(model=slug):
                rig = ea.load_rig(RACES/(slug+'.glb'))
                self.assertEqual(ea.body_girth(rig), self.girth[slug])
                self.assertEqual(ea.foot_anchor(rig), self.registry['footAnchor'][slug])
                self.assertNotEqual(self.girth[slug], self.registry['authoredBodyGirth'][slug])

    def test_skinned_models_name_the_rig_they_were_authored_on(self) -> None:
        # A label like human_male names an authoring set; authoringRigs maps
        # it to the installed body it was fitted on (the generated pieces'
        # base IS their canonical_human_male fit since the P7 cleanup).
        for key, model in self.models.items():
            if model.get("attach") != "skinned":
                continue
            author = model.get("authoredFor", "")
            self.assertTrue(author, f"{key} does not say what body it fits")
            self.assertIn(authoring_rig(self.registry, author), self.girth,
                          f"{key} was authored for the unmeasured rig {author}")

    @staticmethod
    def _named(groups) -> list[str]:
        """A race's fit groups, whether the registry names one or several."""
        return [groups] if isinstance(groups, str) else list(groups)

    def _all_groups(self) -> set[str]:
        return {group for value in self.groups.values()
                for group in self._named(value)}

    def _members(self, group: str) -> set[str]:
        return {race for race, value in self.groups.items()
                if group in self._named(value)}

    def test_fit_group_races_exist(self) -> None:
        for race, value in self.groups.items():
            self.assertIn(race, self.races,
                          f"fit groups {self._named(value)} name no race {race}")
            self.assertTrue(self._named(value),
                            f"{race} is listed with no fit group at all")

    def test_variants_are_present_and_authored_on_their_own_rig(self) -> None:
        seen_groups: set[str] = set()
        for key, model in self.models.items():
            for group, variant in (model.get("variants") or {}).items():
                seen_groups.add(group)
                self.assertIn(group, self._all_groups(),
                              f"{key} offers variant {group} that no race wears")
                path = scene_path(str(variant.get("scene", "")))
                self.assertTrue(path.is_file(), f"{key} variant {group}: {path} missing")
                author = str(variant.get("authoredFor", ""))
                rig = authoring_rig(self.registry, author)
                self.assertIn(rig, self.girth,
                              f"{key} variant {group} names unmeasured rig {author}")
                self.assertIn(rig, self._members(group),
                              f"{key} variant {group} is authored on {author},"
                              " which is not a member of that group")
        self.assertEqual(seen_groups, self._all_groups(),
                         "a fit group exists that no garment offers a variant for")

    def test_authoring_labels_are_worn_only_by_their_own_body(self) -> None:
        # An authoring label is unmeasured on purpose: the client finds no
        # girth or foot anchor for it and wears the piece exactly as fitted.
        # That is only right on the body it was fitted to, so the label must
        # stay out of every measurement table and its groups must hold that
        # one body alone.
        aliases = self.registry.get("authoringRigs", {})
        profiles = [self.registry, *self.registry.get("fitProfiles", {}).values()]
        tables = [profile.get(name, {}) for profile in profiles for name in
                  ("bodyGirth", "authoredBodyGirth", "footAnchor", "authoredFootAnchor")]
        for label, rig in aliases.items():
            self.assertIn(rig, self.races, f"authoring label {label} names no installed body {rig}")
            self.assertIn(rig, self.girth, f"authoring label {label} names the unmeasured body {rig}")
            self.assertNotIn(label, self.races, f"authoring label {label} shadows a race")
            for table in tables:
                self.assertNotIn(label, table, f"authoring label {label} is measured, so it is refitted")
        # A race rebased onto that body (sharedBodyShape.version >= 3 with it
        # as the template) carries it byte for byte below the neck, which
        # test_native_glb_assets proves, so it may wear the piece unfitted too.
        catalog = json.loads((CLIENT / "data" / "actors" / "native_asset_catalog.json").read_text())["races"]

        def shares_below_neck(slug: str, body: str) -> bool:
            shape = catalog.get(slug, {}).get("sharedBodyShape", {})
            return shape.get("version", 0) >= 3 and shape.get("template") == body
        for key, model in self.models.items():
            for group, variant in (model.get("variants") or {}).items():
                author = str(variant.get("authoredFor", ""))
                if author in aliases:
                    members = self._members(group)
                    self.assertIn(aliases[author], members, f"{key} variant {group} is not worn by its own body")
                    self.assertEqual(set(), {m for m in members - {aliases[author]} if not shares_below_neck(m, aliases[author])},
                                     f"{key} variant {group} is worn unfitted by another body")

    def test_every_group_member_can_reach_its_variants(self) -> None:
        # A race in a group must find a variant for every piece the group
        # declares, otherwise it silently falls back to the reference garment.
        by_group: dict[str, set[str]] = {}
        for model in self.models.values():
            for group, variant in (model.get("variants") or {}).items():
                by_group.setdefault(group, set()).add(str(variant["scene"]))
        for group, scenes in by_group.items():
            self.assertTrue(scenes, f"fit group {group} has no variants")
            for scene in scenes:
                self.assertTrue(scene_path(scene).is_file(), f"{scene} missing")


class GarmentWindingTest(unittest.TestCase):
    """Every closed garment shell has to face outwards.

    A loft's winding follows the order of its rings, and it is easy to build a
    shell the wrong way round without noticing: the renderer culls back faces,
    so an inside-out garment does not disappear, it goes *transparent from the
    near side* and shows whatever is behind it.  That is how a closed boot came
    to look like an open-toed sandal with the wearer's foot inside it.

    The check is the divergence theorem: summed about its own centroid, a closed
    shell wound outwards encloses positive volume.  Capes are sheets and gloves
    have an open cuff, so neither encloses anything and both are excluded.
    """

    OPEN_REGIONS = {"cape", "hands"}

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(EQUIPMENT.read_text())

    def _scenes(self):
        for model in self.registry["models"].values():
            if model.get("attach") != "skinned":
                continue
            region = str(model.get("skinRegion", ""))
            if region in self.OPEN_REGIONS:
                continue
            yield scene_path(str(model["scene"]))
            for variant in (model.get("variants") or {}).values():
                yield scene_path(str(variant["scene"]))

    def test_closed_garments_are_wound_outwards(self) -> None:
        try:
            import numpy as np
        except ImportError:  # pragma: no cover - numpy is a build requirement
            self.skipTest("numpy is required to read garment geometry")
        seen = 0
        for path in sorted(set(self._scenes())):
            self.assertTrue(path.is_file(), f"{path} missing")
            closed_volume = 0.0
            for points, triangles in _mesh_primitives(path):
                for shell in _shells(points, triangles):
                    if not shell.closed:
                        continue
                    # Signed volume diagnoses orientation only for closed
                    # surfaces. An original open coat can have a negative
                    # origin-dependent integral while its lining faces out.
                    self.assertGreaterEqual(shell.volume, -1e-10,
                        f"{path.name} has an inverted closed shell ({shell.volume:g} m3)")
                    closed_volume += max(0., shell.volume)
            seen += 1
            self.assertGreater(closed_volume, 1e-9, f"{path.name} has no closed garment volume")
        self.assertGreater(seen, 10, "no closed garments were checked")


class FootgearGroundTest(unittest.TestCase):
    """Footwear stands where the bare foot stands, near enough.

    The actor is placed on the ground by its body, not by what it is wearing,
    so anything a boot puts below the wearer's own sole is boot under the
    floor.  The shell this replaces hung three centimetres of heel down there,
    and because its sole was swept along each ring's own axis rather than in
    world space it arrived in disconnected pieces - parts of it floating above
    the toes while the back of it sank - which is what made the heel look lower
    than the foot it was on.

    What is checked here is how far the lowest point of a boot sits below the
    wearer's own sole, which is the half of it a number can settle.  Whether
    the sole arrives in one piece is a question about the shell's topology and
    is left to the authoring tool that builds it.
    """

    #: How far below the wearer's own sole a boot may reach, in metres. The
    #: shell this replaces reached 30 mm on a plantigrade foot and 36 on a
    #: digitigrade one; the authored sole now stands 4 mm proud of the plane
    #: the bare foot stands on.
    MAX_SINK = .008

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(EQUIPMENT.read_text())

    def _footgear(self):
        """Every footgear scene, with the rig it was authored on."""
        for model in self.registry["models"].values():
            if model.get("attach") != "skinned":
                continue
            if str(model.get("skinRegion", "")) != "boots":
                continue
            yield scene_path(str(model["scene"])), str(model.get("authoredFor", ""))
            for variant in (model.get("variants") or {}).values():
                yield (scene_path(str(variant["scene"])),
                       str(variant.get("authoredFor", "")))

    def test_footgear_stands_on_the_wearers_own_sole(self) -> None:
        try:
            import numpy as np
        except ImportError:  # pragma: no cover - numpy is a build requirement
            self.skipTest("numpy is required to read garment geometry")
        seen = 0
        for path, author in sorted(set(self._footgear())):
            self.assertTrue(path.is_file(), f"{path} missing")
            rig = _body_rig(authoring_rig(self.registry, author))
            doc, binary = ea.read_glb(path)
            names = [doc["nodes"][i]["name"] for i in doc["skins"][0]["joints"]]
            floors = {side: [] for side in ("l", "r")}
            art_floors = {side: [] for side in ("l", "r")}
            for mesh_index, mesh in enumerate(doc["meshes"]):
                for primitive in mesh["primitives"]:
                    attrs = primitive["attributes"]
                    points = ea.accessor_array(doc, binary, attrs["POSITION"])
                    joints = ea.accessor_array(doc, binary, attrs["JOINTS_0"])
                    weights = ea.accessor_array(doc, binary, attrs["WEIGHTS_0"]).astype(float)
                    used = np.unique(ea.accessor_array(doc, binary, primitive["indices"]))
                    for side in ("l", "r"):
                        chain = [i for i, name in enumerate(names) if name.endswith("_" + side)]
                        own = (weights[used] * np.isin(joints[used], chain)).sum(axis=1) > weights[used].sum(axis=1) * .5
                        if not own.any():
                            continue
                        floor = float(points[used[own], 1].min())
                        floors[side].append(floor)
                        if mesh_index == 0:
                            art_floors[side].append(floor)
            for side in ("l", "r"):
                self.assertTrue(art_floors[side], f"{path}: no {side} source foot")
                sole = ea.weighted_sole(rig, side)
                sink = sole - min(floors[side])
                self.assertLessEqual(sink, self.MAX_SINK,
                    f"{path} {side} reaches {sink*1000:.1f} mm below the weighted {author} sole")
                floating = min(art_floors[side]) - sole
                self.assertLessEqual(floating, .008,
                    f"{path} {side} floats {floating*1000:.1f} mm above the weighted {author} sole")
            seen += 1
        self.assertGreater(seen, 10, "no footgear was checked")


class LegwearSeamTest(unittest.TestCase):
    """Check source-art hems separately from the clothing transition lining.

    The old 166 mm lower bound described a procedural shin tube, not these
    full-length source designs. Bark's artwork already ended at 100 mm; its
    reported 49.6 mm "hem" was a backing triangle crossing the body-cover band.
    Check ground clearance, the canonical waist and matched boot overlap.
    """

    STRUCTURAL_SHELLS = 3

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(EQUIPMENT.read_text())

    def _legwear(self):
        for key, model in self.registry["models"].items():
            if not key.startswith("4:") or model.get("attach") != "skinned":
                continue
            for variant in [model, *(model.get("variants") or {}).values()]:
                yield key, scene_path(str(variant["scene"])), str(model.get("kind", "")), str(variant["authoredFor"])

    def test_hems_and_waists_meet_the_seams_they_are_cut_against(self) -> None:
        seen = 0
        for key, path, kind, author in sorted(set(self._legwear())):
            self.assertTrue(path.is_file(), f"{path} missing")
            points = _art_points(path)
            low, high = float(points[:, 1].min()), float(points[:, 1].max())
            rig = _body_rig(authoring_rig(self.registry, author))
            # Full-length legwear clears the actual feet. A tail minimum and a
            # copied backing triangle cannot define the visible garment hem.
            sole = max(ea.weighted_sole(rig, side) for side in ("l", "r"))
            self.assertGreaterEqual(low, sole + .020,
                f"{key} {path}: source hem at {low:.4f} intrudes into the foot")
            self.assertLessEqual(low, rig.origin("calf_l")[1] - .020,
                f"{key} {path}: source hem ends above the shin")
            self.assertGreaterEqual(high, rig.origin("spine_01")[1],
                f"{key} {path}: waistband does not reach the canonical waist")
            seen += 1
        self.assertGreater(seen, 50, "no leg garments were checked")

    def test_matched_source_sets_overlap_the_boot_cuffs(self) -> None:
        pairs = {"amberwood_woodland_legguards": "amberwood_woodland_boots",
                 "arcane_leg_armor": "arcane_fantasy_boots",
                 "legendary_leg_armor": "legendary_sabatons"}
        by_slug = {scene_path(model["scene"]).stem: model for model in self.registry["models"].values()}
        seen = 0
        for prefix, boot_prefix in pairs.items():
            for index in range(1, 9):
                legs = by_slug[f"{prefix}_{index:02d}"]
                boots = by_slug[f"{boot_prefix}_{index:02d}"]
                for group in [None, *(legs.get("variants") or {})]:
                    leg = legs if group is None else legs["variants"][group]
                    boot = boots if group is None else boots["variants"][group]
                    hem = _art_points(scene_path(leg["scene"]))[:, 1].min()
                    cuff = _art_points(scene_path(boot["scene"]))[:, 1].max()
                    self.assertLessEqual(hem, cuff + .008,
                        f"{prefix}_{index:02d} {group}: {1000*(hem-cuff):.1f} mm gap above matching boot")
                    seen += 1
        self.assertGreaterEqual(seen, 24)

    def test_the_shell_and_both_leg_tubes_are_closed(self) -> None:
        """Require enclosed hip and leg coverage in both lining combinations.

        Source-derived linings connect the hip and both legs in one solid;
        older procedural trousers use three overlapping closed solids.
        """
        try:
            import numpy as np
        except ImportError:  # pragma: no cover - numpy is a build requirement
            self.skipTest("numpy is required to read garment geometry")
        seen = 0
        for key, path, _kind, _author in sorted(set(self._legwear())):
            document, binary = ea.read_glb(path)
            linings = [mesh for mesh in document['meshes']
                       if mesh.get('name', '').startswith('GeneratedLegBacking')]
            if linings:
                self.assertEqual({m['name'] for m in linings},
                    {'GeneratedLegBacking', 'GeneratedLegBackingWithBoots'})
                # Source-derived trousers form a connected hip and two leg
                # tubes in one closed lining. Count anatomy, not the three
                # separate solids used by the old procedural construction.
                for mesh in linings:
                    spanning = False
                    for primitive in mesh['primitives']:
                        points = ea.accessor_array(document,binary,primitive['attributes']['POSITION'])
                        faces = ea.accessor_array(document,binary,primitive['indices']).reshape(-1,3)
                        for shell in _shells(points,faces):
                            if shell.closed and shell.volume > 1e-8:
                                lo,hi=shell.points.min(axis=0),shell.points.max(axis=0)
                                spanning |= bool(lo[0]<-.04 and hi[0]>.04 and lo[1]<.55 and hi[1]>.95)
                    self.assertTrue(spanning, f"{key}/{mesh['name']} lacks a closed hip and both legs")
            else:
                closed = _closed_component_count(path)
                self.assertGreaterEqual(closed, self.STRUCTURAL_SHELLS,
                    f"{key} lacks the hip shell and two tubes of its procedural construction")
            seen += 1
        self.assertGreater(seen, 50, "no legwear shells were checked")


@lru_cache(maxsize=16)
def _body_rig(author):
    return ea.load_rig(RACES / f"{author}.glb", ea.BODY_SURFACES)


def _art_points(path):
    import numpy as np
    document, binary = ea.read_glb(path)
    return np.concatenate([ea.accessor_array(document, binary, primitive["attributes"]["POSITION"])[
        np.unique(ea.accessor_array(document, binary, primitive["indices"]))]
        for primitive in document["meshes"][0]["primitives"]])


def _shells(points, triangles):
    """Connected shell topology, efficiently welding UV-split source art."""
    import numpy as np
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from garment_coverage import Shell
    _, welded = np.unique(np.round(points, 5), axis=0, return_inverse=True)
    faces = welded[triangles]
    edges=np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]])
    graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),
                    shape=(int(welded.max())+1,)*2).tocsr()
    _, labels=connected_components(graph,directed=False)
    groups=labels[faces[:,0]]
    result=[]
    for group in np.unique(groups):
        selected=triangles[groups==group]
        used,inverse=np.unique(selected,return_inverse=True)
        p=points[used].astype(float);f=inverse.reshape(-1,3)
        wf=welded[selected]
        ee=np.sort(np.vstack([wf[:,[0,1]],wf[:,[1,2]],wf[:,[2,0]]]),axis=1)
        _, counts=np.unique(ee,axis=0,return_counts=True)
        closed=bool((counts%2==0).all())
        q=p-p.mean(axis=0)
        volume=float(np.einsum('ij,ij->i',q[f[:,0]],np.cross(q[f[:,1]],q[f[:,2]])).sum()/6.)
        result.append(Shell(p,f,closed,volume))
    return result


def _closed_component_count(path: Path) -> int:
    return sum(shell.closed for p,f in _mesh_primitives(path) for shell in _shells(p,f))


def _mesh_primitives(path: Path):
    """POSITION and index arrays of every primitive in a GLB."""
    import struct
    import numpy as np

    raw = path.read_bytes()
    json_size = struct.unpack_from("<I", raw, 12)[0]
    document = json.loads(raw[20:20 + json_size])
    offset = 20 + json_size
    binary_size = struct.unpack_from("<I", raw, offset)[0]
    binary = raw[offset + 8:offset + 8 + binary_size]
    dtypes = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2",
              5125: "<u4", 5126: "<f4"}
    widths = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

    def read(index: int) -> "np.ndarray":
        spec = document["accessors"][index]
        view = document["bufferViews"][spec["bufferView"]]
        dtype = np.dtype(dtypes[spec["componentType"]])
        width = widths[spec["type"]]
        start = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
        stride = view.get("byteStride", dtype.itemsize * width)
        shape = (spec["count"],) if width == 1 else (spec["count"], width)
        strides = (stride,) if width == 1 else (stride, dtype.itemsize)
        return np.ndarray(shape, dtype=dtype, buffer=binary, offset=start,
                          strides=strides).copy()

    for mesh in document.get("meshes", []):
        for primitive in mesh["primitives"]:
            yield (read(primitive["attributes"]["POSITION"]).astype(float),
                   read(primitive["indices"]).astype(np.int64).reshape(-1, 3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
