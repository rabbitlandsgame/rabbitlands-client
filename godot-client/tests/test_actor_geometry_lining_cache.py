"""Lining masks in the actor geometry cook driver (tools/actor_geometry_cache.py,
actor LODs C4): which garments carry linings, how a lining_visibility.py mask
file is found, validated against the garment and gated, the lining input the
cook receives, cache keys, catalogue provenance and the report. Godot is
replaced by the fake engine of test_actor_geometry_cache.py; one optional test
cooks a real garment with a synthesised mask when RABBITLANDS_GODOT names an
editor binary (RABBITLANDS_GODOT_WRAPPER may prefix it) and cook.gd runs the
lining stage."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import actor_geometry_cache as cache
from test_actor_geometry_cache import ENGINE, NATIVE, FakeEngine, Fixture, write

COAT = NATIVE + "equipment/variants/human_male/coat.glb"
COAT_KEY = "res://" + COAT
GREAVES = NATIVE + "equipment/variants/human_female/greaves.glb"
GREAVES_KEY = "res://" + GREAVES


def glb(document: dict) -> bytes:
    """A GLB holding only a JSON chunk (enough for the driver's JSON reads)."""
    text = json.dumps(document).encode("utf-8")
    text += b" " * (-len(text) % 4)
    return struct.pack("<III", 0x46546C67, 2, 20 + len(text)) + struct.pack("<II", len(text), 0x4E4F534A) + text


def garment(linings: dict[str, int], shell: int = 30) -> bytes:
    meshes = [{"name": "Shell", "primitives": [{"indices": 0}]}]
    accessors = [{"count": shell * 3}]
    for name, triangles in linings.items():
        meshes.append({"name": name, "primitives": [{"indices": len(accessors)}]})
        accessors.append({"count": triangles * 3})
    return glb({"asset": {"version": "2.0"}, "meshes": meshes, "accessors": accessors})


def bits(flags: list[bool]) -> str:
    raw = bytearray((len(flags) + 7) // 8)
    for index, flag in enumerate(flags):
        if flag:
            raw[index >> 3] |= 1 << (index & 7)
    return base64.b64encode(bytes(raw)).decode("ascii")


def mask_document(logical_path: str, sha256: str, linings: dict[str, int], *, removed: int = 5,
                  margin: float = 0.02, rule: str = "surface", directions: int = 128, poses: int = 44) -> dict:
    entries = {}
    for name, triangles in linings.items():
        keep = [index >= removed for index in range(triangles)]
        visible = [index >= removed + 2 for index in range(triangles)]
        entries[name] = {"mesh": name, "primitive": 0, "triangles": triangles, "keep": bits(keep),
                         "visible": bits(visible), "keep_upper": bits(keep), "visible_upper": bits(visible),
                         "check": [[0, 0.0, 1.0, 0.0], [triangles - 1, 0.1, 1.2, 0.0]]}
    return {"schema": 1, "policy": cache.MASK_POLICY, "source": {"path": logical_path, "sha256": sha256, "bytes": 1},
            "inputs": {"tool_sha256": "0" * 64}, "settings": {"directions": directions},
            "poses": [f"pose{index}" for index in range(poses)], "margin_m": margin, "margin_rule": rule,
            "occluders": [], "linings": entries}


class LiningEngine(FakeEngine):
    """The fake cook, plus what the hooked cook reports for lining rows
    (`lining_status`: what the stage reports for every lining it received)."""

    def __init__(self, lining_status: str = "masked", **options):
        super().__init__(**options)
        self.items: list[dict] = []
        self.lining_status = lining_status

    def __call__(self, command, env, log, stdout, timeout):
        job_path = Path(env["RABBITLANDS_ACTOR_GEOMETRY_JOB"])
        job = json.loads(job_path.read_text(encoding="utf-8"))
        self.items.extend(job["files"])
        code = super().__call__(command, env, log, stdout, timeout)
        report_path = Path(job["report"])
        if code == 0 and report_path.is_file() and job["mode"] == "cook":
            report = json.loads(report_path.read_text(encoding="utf-8"))
            for item in job["files"]:
                row = report["results"].get(item["path"])
                if row and item.get("lining"):
                    surfaces = []
                    for lining in item["lining"]["linings"]:
                        if self.lining_status != "masked":
                            surfaces.append({"triangles": lining["triangles"], "vertices": lining["triangles"] * 3,
                                             "method": "none", "reason": "per_face_tiles", "levels": [],
                                             "lining": {"status": self.lining_status,
                                                        "triangles": lining["triangles"]}})
                            continue
                        surfaces.append({"triangles": lining["triangles"], "vertices": lining["triangles"] * 3,
                                         "method": "none", "reason": "per_face_tiles", "levels": [],
                                         "base_triangles": lining["triangles"] - 5,
                                         "lining": {"status": "masked", "triangles": lining["triangles"],
                                                    "kept_triangles": lining["triangles"] - 5, "removed_triangles": 5,
                                                    "vertices": lining["triangles"] * 3}})
                    row.setdefault("meshes", []).append({"name": "coat_Generated", "model_scale": 1.0,
                                                         "surfaces": surfaces})
            report_path.write_text(json.dumps(report), encoding="utf-8")
        return code


class LiningCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temp.name))
        self.project = self.fixture.project
        self.masks = Path(self.temp.name) / "masks"
        write(self.project / COAT, garment({"GeneratedArmorBacking": 40}))
        write(self.project / GREAVES, garment({"GeneratedBootBacking": 24, "GeneratedBootBackingWithLegs": 20}))
        self.fixture.files = sorted(set(self.fixture.files) | {COAT, GREAVES})

    def tearDown(self):
        self.temp.cleanup()

    def sha(self, relative: str) -> str:
        return hashlib.sha256((self.project / relative).read_bytes()).hexdigest()

    def write_mask(self, relative: str, linings: dict[str, int], **options) -> Path:
        path = cache.mask_path(self.masks, relative)
        write(path, json.dumps(mask_document("res://" + relative, self.sha(relative), linings, **options),
                               sort_keys=True, indent=1) + "\n")
        return path

    def cook(self, engine, **options):
        return self.fixture.cook(engine, masks=options.pop("masks", self.masks), **options)

    # --- discovery ----------------------------------------------------------------

    def test_lining_primitives_come_from_the_gltf_json(self):
        document = {"meshes": [
            {"name": "Shell", "primitives": [{"indices": 0}]},
            {"name": "GeneratedLegBacking", "primitives": [{"indices": 1}, {"mode": 1, "indices": 0}]},
            {"name": "GeneratedLegBackingWithBoots", "primitives": [{"attributes": {"POSITION": 2}}]}],
            "accessors": [{"count": 9}, {"count": 300}, {"count": 61}]}
        self.assertEqual(cache.lining_primitives(document), [
            {"mesh": "GeneratedLegBacking", "primitive": 0, "triangles": 100},
            {"mesh": "GeneratedLegBackingWithBoots", "primitive": 0, "triangles": 20}])
        self.assertEqual(cache.lining_primitives(None), [])
        self.assertEqual(cache.lining_primitives(cache.gltf_document(self.project / GREAVES)), [
            {"mesh": "GeneratedBootBacking", "primitive": 0, "triangles": 24},
            {"mesh": "GeneratedBootBackingWithLegs", "primitive": 0, "triangles": 20}])

    def test_mask_files_follow_the_mask_tool_layout(self):
        self.assertEqual(cache.mask_path(Path("m"), COAT), Path("m") / "human_male" / "coat.lining.json")
        self.assertEqual(cache.default_masks(Path("out")), Path("out") / "lining-masks")

    # --- validation -----------------------------------------------------------------

    def test_a_bound_mask_becomes_the_lining_input(self):
        path = self.write_mask(COAT, {"GeneratedArmorBacking": 40})
        result = cache.read_mask(path, COAT_KEY, self.sha(COAT), [{"mesh": "GeneratedArmorBacking", "primitive": 0,
                                                                      "triangles": 40}])
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["mask_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(result["removable"], 5)
        lining = result["input"]
        self.assertEqual((lining["schema"], lining["mask_sha256"]), (cache.LINING_INPUT_SCHEMA, result["mask_sha256"]))
        self.assertEqual([sorted(entry) for entry in lining["linings"]], [sorted(cache.LINING_INPUT_KEYS)])
        entry = lining["linings"][0]
        self.assertEqual((entry["mesh"], entry["primitive"], entry["triangles"]), ("GeneratedArmorBacking", 0, 40))
        self.assertEqual(cache._mask_bits(entry["keep"], 40), sum(1 << index for index in range(5, 40)))

    def test_bitsets_follow_the_little_endian_bit_order(self):
        self.assertEqual(cache._mask_bits("BQ==", 8), 0b101)
        self.assertIsNone(cache._mask_bits("BQ==", 9), "the wrong length")
        self.assertIsNone(cache._mask_bits("/w==", 7), "a bit past the count")
        self.assertIsNone(cache._mask_bits("B*==", 8), "not base64")

    def test_masks_that_do_not_bind_or_pass_the_gate_are_refused(self):
        linings = [{"mesh": "GeneratedArmorBacking", "primitive": 0, "triangles": 40}]
        path = cache.mask_path(self.masks, COAT)
        good = mask_document(COAT_KEY, self.sha(COAT), {"GeneratedArmorBacking": 40})

        def check(document, status, reason=""):
            write(path, document if isinstance(document, str) else json.dumps(document))
            result = cache.read_mask(path, COAT_KEY, self.sha(COAT), linings)
            self.assertEqual(result["status"], status, result)
            self.assertTrue(result.get("reason", "").startswith(reason), result)
            self.assertNotIn("input", result)

        self.assertEqual(cache.read_mask(path, COAT_KEY, self.sha(COAT), linings), {"status": "missing"})
        check("{", "invalid", "json")
        check(dict(good, policy="other"), "invalid", "schema")
        check(dict(good, source=dict(good["source"], path="res://elsewhere.glb")), "invalid", "path")
        check(dict(good, source=dict(good["source"], sha256="0" * 64)), "stale", "source sha256")
        check(dict(good, margin_m=0.01), "gate", "margin")
        check(dict(good, margin_m=True), "gate", "margin")
        check(dict(good, margin_rule="centroid"), "gate", "margin")
        check(dict(good, settings={"directions": 64}), "gate", "directions")
        check(dict(good, poses=good["poses"][:27]), "gate", "poses")
        entry = good["linings"]["GeneratedArmorBacking"]
        for change, reason in (({"triangles": 39}, "lining GeneratedArmorBacking triangles"),
                               ({"triangles": 40.0}, "lining GeneratedArmorBacking triangles"),
                               ({"keep": bits([True] * 41)}, "lining GeneratedArmorBacking bits"),
                               ({"keep": "B*=="}, "lining GeneratedArmorBacking bits"),
                               ({"visible": bits([True] * 40)}, "lining GeneratedArmorBacking visible not kept"),
                               ({"check": [[40, 0.0, 0.0, 0.0]]}, "lining GeneratedArmorBacking check"),
                               ({"mesh": "GeneratedLegBacking"}, "lining GeneratedArmorBacking not in the garment")):
            check(dict(good, linings={"GeneratedArmorBacking": dict(entry, **change)}), "invalid", reason)

    def test_an_unreadable_mask_cooks_without_it(self):
        # lining_visibility.py writes its masks in place, at the end of a run.
        path = self.write_mask(COAT, {"GeneratedArmorBacking": 40})
        linings = [{"mesh": "GeneratedArmorBacking", "primitive": 0, "triangles": 40}]
        sha256 = self.sha(COAT)
        with mock.patch.object(Path, "read_bytes", side_effect=PermissionError("in use")):
            result = cache.read_mask(path, COAT_KEY, sha256, linings)
        self.assertEqual(result, {"status": "invalid", "reason": "read: PermissionError"})

    def test_a_mask_missing_one_twin_is_partial(self):
        both = [{"mesh": "GeneratedBootBacking", "primitive": 0, "triangles": 24},
                {"mesh": "GeneratedBootBackingWithLegs", "primitive": 0, "triangles": 20}]
        path = self.write_mask(GREAVES, {"GeneratedBootBacking": 24})
        result = cache.read_mask(path, GREAVES_KEY, self.sha(GREAVES), both)
        self.assertEqual(result["status"], "partial")
        self.assertIn("GeneratedBootBackingWithLegs/0", result["reason"])
        self.assertEqual([entry["mesh"] for entry in result["input"]["linings"]], ["GeneratedBootBacking"])

    # --- cooking ---------------------------------------------------------------------

    def test_the_cook_receives_the_lining_input_and_the_catalogue_records_the_mask(self):
        self.write_mask(COAT, {"GeneratedArmorBacking": 40})
        engine = LiningEngine()
        result = self.cook(engine)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["mask_statuses"], {"ok": 1, "missing": 1})
        items = {item["path"]: item for item in engine.items}
        self.assertEqual(items[COAT_KEY]["lining"]["linings"][0]["mesh"], "GeneratedArmorBacking")
        self.assertEqual(items[COAT_KEY]["mask_status"], "ok")
        self.assertNotIn("lining", items[GREAVES_KEY], "a garment without a mask cooks without lining input")
        self.assertEqual(items[GREAVES_KEY]["mask_status"], "missing")
        self.assertNotIn("mask_status", items["res://" + NATIVE + "equipment/sword.glb"], "no lining, no mask status")
        mask_sha = hashlib.sha256(cache.mask_path(self.masks, COAT).read_bytes()).hexdigest()
        entry = self.fixture.catalog()["entries"][COAT_KEY]
        self.assertEqual(entry["inputs"], {"policy_digest": entry["inputs"]["policy_digest"], "mask_sha256": mask_sha})
        row = cache.load_summary(self.fixture.out)["files"][COAT_KEY]
        self.assertEqual((row["mask_status"], row["mask_sha256"], row["lining_key"], row["mask_removable"]),
                         ("ok", mask_sha, cache.lining_key(mask_sha), 5))
        self.assertNotIn("mask_sha256",
                         self.fixture.catalog()["entries"]["res://" + NATIVE + "equipment/sword.glb"].get("inputs", {}))

    def test_mask_changes_recook_only_their_garment(self):
        self.cook(LiningEngine())
        path = self.write_mask(COAT, {"GeneratedArmorBacking": 40})
        engine = LiningEngine()
        self.cook(engine)
        self.assertEqual(engine.calls, [[COAT_KEY]], "a new mask recooks its garment only")
        engine = LiningEngine()
        self.cook(engine)
        self.assertEqual(engine.calls, [], "an unchanged mask reuses the sidecar")
        self.write_mask(COAT, {"GeneratedArmorBacking": 40}, removed=9)
        engine = LiningEngine()
        self.cook(engine)
        self.assertEqual(engine.calls, [[COAT_KEY]], "new mask bytes recook")
        saved = dict(cache.MASK_GATE)
        try:
            cache.MASK_GATE["min_poses"] = 40
            engine = LiningEngine()
            self.cook(engine)
            self.assertEqual(engine.calls, [[COAT_KEY]], "a new gate recooks the masked garments")
        finally:
            cache.MASK_GATE.clear()
            cache.MASK_GATE.update(saved)
        path.unlink()
        engine = LiningEngine()
        self.cook(engine)
        self.assertEqual(engine.calls, [[COAT_KEY]], "a removed mask recooks without it")
        self.assertNotIn("mask_sha256", self.fixture.catalog()["entries"][COAT_KEY].get("inputs", {}))

    def test_a_stale_mask_is_reported_and_not_used(self):
        self.write_mask(COAT, {"GeneratedArmorBacking": 40})
        write(self.project / COAT, garment({"GeneratedArmorBacking": 40}, shell=31))
        engine = LiningEngine()
        result = self.cook(engine)
        self.assertEqual(result["mask_statuses"], {"stale": 1, "missing": 1})
        self.assertNotIn("lining", {item["path"]: item for item in engine.items}[COAT_KEY])

    def test_the_catalogue_names_a_mask_only_for_a_sidecar_it_shaped(self):
        self.write_mask(COAT, {"GeneratedArmorBacking": 40})
        # A cook.gd without the lining stage (the HOOK not yet applied)
        # ignores the input: the sidecar is LOD policy v1's.
        result = self.cook(FakeEngine())
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["mask_statuses"], {"ok": 1, "missing": 1})
        self.assertNotIn("mask_sha256", self.fixture.catalog()["entries"][COAT_KEY].get("inputs", {}))
        # The stage ran but kept the v1 plan (below the gain gate).
        self.cook(LiningEngine("below_gain"), force=True)
        self.assertNotIn("mask_sha256", self.fixture.catalog()["entries"][COAT_KEY].get("inputs", {}))
        self.assertEqual(cache.report(self.fixture.out)["lining_masks"]["surfaces"], {"below_gain": 1})
        self.cook(LiningEngine(), force=True)
        self.assertIn("mask_sha256", self.fixture.catalog()["entries"][COAT_KEY]["inputs"])

    def test_reused_rows_follow_the_current_mask_status(self):
        self.cook(LiningEngine())
        self.assertEqual(cache.report(self.fixture.out)["lining_masks"]["files"], {"missing": 2})
        write(cache.mask_path(self.masks, COAT), "{")
        engine = LiningEngine()
        result = self.cook(engine)
        self.assertEqual(engine.calls, [], "an unusable mask has no lining key: the sidecar is reused")
        self.assertEqual(result["mask_statuses"], {"invalid": 1, "missing": 1})
        row = cache.load_summary(self.fixture.out)["files"][COAT_KEY]
        self.assertEqual((row["mask_status"], row["mask_reason"]), ("invalid", "json"))
        self.assertEqual(cache.report(self.fixture.out)["lining_masks"]["files"], {"invalid": 1, "missing": 1})
        self.cook(LiningEngine(), masks=None)
        self.assertEqual(cache.report(self.fixture.out)["lining_masks"]["files"], {})
        self.assertNotIn("mask_status", cache.load_summary(self.fixture.out)["files"][COAT_KEY])

    def test_cooking_without_masks_records_nothing_about_them(self):
        self.write_mask(COAT, {"GeneratedArmorBacking": 40})
        engine = LiningEngine()
        result = self.cook(engine, masks=None)
        self.assertEqual(result["mask_statuses"], {})
        self.assertFalse(any("lining" in item or "mask_status" in item for item in engine.items))

    def test_the_lining_stage_is_part_of_the_policy_digest(self):
        self.assertIn("tools/actor_geometry/lining_policy.gd", cache.POLICY_FILES)
        first = cache.policy_digest(self.project, ENGINE)
        write(self.project / "tools/actor_geometry/lining_policy.gd", "# lining stage v2\n")
        self.assertNotEqual(first, cache.policy_digest(self.project, ENGINE))

    # --- report and prediction ---------------------------------------------------------

    def test_the_report_counts_masked_linings(self):
        self.write_mask(COAT, {"GeneratedArmorBacking": 40})
        self.write_mask(GREAVES, {"GeneratedBootBacking": 24, "GeneratedBootBackingWithLegs": 20})
        self.cook(LiningEngine())
        masking = cache.report(self.fixture.out)["lining_masks"]
        self.assertEqual(masking["surfaces"], {"masked": 3})
        self.assertEqual(masking["removed_triangles"], 15)
        self.assertEqual(masking["kept_triangles"], 84 - 15)
        self.assertEqual(masking["files"], {"ok": 2})
        self.assertEqual(masking["removed_share"], round(15 / 84, 4))

    def test_prediction_draws_the_masked_base(self):
        surface = {"triangles": 1000, "base_triangles": 800, "levels": [[400, 0.01, 0.0, 0]]}
        options = {"model_scale": 1.0, "lod_bias": 1.0, "multiplier": 1.658, "width": 1920.0}
        self.assertEqual(cache.level_triangles(surface, 1.0, **options), 800, "inside the first band: the masked base")
        self.assertEqual(cache.level_triangles(surface, 50.0, **options), 400)
        self.assertEqual(cache.level_triangles({"triangles": 1000, "levels": []}, 1.0, **options), 1000)

    def test_plan_lists_mask_statuses(self):
        self.write_mask(COAT, {"GeneratedArmorBacking": 40})
        out = Path(self.temp.name) / "plan-out"
        args = ["plan", "--project", str(self.project), "--out", str(out), "--engine", ENGINE,
                "--masks", str(self.masks)]
        import contextlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(cache.main(args), 0)
        result = json.loads(buffer.getvalue())
        self.assertEqual(result["mask_statuses"], {"ok": 1, "missing": 1})
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(cache.main(args + ["--no-masks"]), 0)
        self.assertEqual(json.loads(buffer.getvalue())["mask_statuses"], {})

    # --- the real engine (optional) -------------------------------------------------------

    @unittest.skipUnless(os.environ.get("RABBITLANDS_GODOT"), "set RABBITLANDS_GODOT to cook with a real editor binary")
    def test_real_cook_masks_a_lining(self):
        cook_script = (PROJECT / "tools/actor_geometry/cook.gd").read_text(encoding="utf-8")
        if "LiningPolicy.apply" not in cook_script:
            self.skipTest("cook.gd does not run the lining stage yet (HOOK from actor LODs C4)")
        sys.path.insert(0, str(PROJECT.parent / "eloria-assets/tools"))
        import lining_visibility as visibility
        relative = NATIVE + "equipment/variants/human_male/amberwood_woodland_legguards_01.glb"
        source = PROJECT / relative
        document, blob = visibility.read_glb(source)
        linings = {}
        for part in visibility.garment_parts(document, blob):
            if part["lining"]:
                corners = visibility.triangle_corners(part["positions"], part["triangles"])
                keep = corners.mean(axis=1)[:, 0] ** 2 >= 0.06 ** 2  # drop the inner thigh band
                linings[part["mesh"]] = {"mesh": part["mesh"], "primitive": part["primitive"],
                                         "triangles": len(corners), "keep": visibility.pack_bits(keep),
                                         "visible": visibility.pack_bits(keep),
                                         "check": visibility.check_centroids(corners)}
        mask = mask_document("res://" + relative, cache.sha256_file(source), {})
        mask["linings"] = linings
        masks = Path(self.temp.name) / "real-masks"
        write(cache.mask_path(masks, relative), json.dumps(mask))
        out = Path(self.temp.name) / "real"
        options = {"out": out, "wrapper": os.environ.get("RABBITLANDS_GODOT_WRAPPER"), "paths": [relative]}
        result = cache.cook(PROJECT, Path(os.environ["RABBITLANDS_GODOT"]), masks=masks, **options)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["mask_statuses"], {"ok": 1})
        masking = cache.report(out)["lining_masks"]
        self.assertEqual(masking["surfaces"].get("masked"), 2, masking)
        self.assertGreater(masking["removed_triangles"], 0)
        verified = cache.verify(PROJECT, Path(os.environ["RABBITLANDS_GODOT"]), **options)
        self.assertTrue(verified["ok"], verified)
        self.assertEqual(verified["scene_mismatches"], [])


if __name__ == "__main__":
    unittest.main()
