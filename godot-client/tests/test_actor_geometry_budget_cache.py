"""Race-refit budget in the actor geometry cook driver (tools/actor_geometry_cache.py,
actor LODs C11): which actor glTFs are race refits of rigid socket models and
which Human source each is measured against (data/actors/equipment.json), the
budget input the cook receives, cache keys, catalogue provenance, the report
and `plan`. Godot is replaced by the fake engine of test_actor_geometry_cache.py;
one optional test cooks the real Votary Sun Headband when RABBITLANDS_GODOT
names an editor binary (RABBITLANDS_GODOT_WRAPPER may prefix it) and cook.gd
runs the budget stage."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import actor_geometry_cache as cache
from test_actor_geometry_cache import ENGINE, NATIVE, FakeEngine, Fixture, write
from test_actor_geometry_lining_cache import glb

VARIANTS = NATIVE + "equipment/variants/"
HUMAN_M = VARIANTS + "human_male/helm.glb"
HUMAN_F = VARIANTS + "human_female/helm.glb"
VOTARY_M = VARIANTS + "votary_male/helm.glb"
VOTARY_F = VARIANTS + "votary_female/helm.glb"
GLASS_M = VARIANTS + "glasswarden_male/helm.glb"
ORUN_F = VARIANTS + "orun_female/hood.glb"
HOOD = NATIVE + "equipment/hood.glb"
LEGS_H = VARIANTS + "human_male/legs.glb"
LEGS_V = VARIANTS + "votary_male/legs.glb"


def key(relative: str) -> str:
    return "res://" + relative


def mesh_glb(*primitives: tuple[int, int]) -> bytes:
    """A GLB JSON chunk with one mesh of these (mode, triangles) primitives."""
    accessors, items = [], []
    for mode, triangles in primitives:
        items.append({"indices": len(accessors), "mode": mode})
        accessors.append({"count": triangles * 3})
    return glb({"asset": {"version": "2.0"}, "meshes": [{"name": "Helm", "primitives": items}],
                "accessors": accessors})


def equipment() -> dict:
    return {"models": {
        # A helmet with a Human source per sex and three race refits.
        "3:1": {"scene": key(HUMAN_M), "attach": "socket", "variants": {
            "canonical_human_male": {"scene": key(HUMAN_M)},
            "canonical_human_female": {"scene": key(HUMAN_F)},
            "canonical_votary_male": {"scene": key(VOTARY_M)},
            "canonical_votary_female": {"scene": key(VOTARY_F)},
            # Wears the Human scene itself: not a refit.
            "canonical_greyhaven_male": {"scene": key(HUMAN_M)},
            "canonical_glasswarden_male": {"scene": key(GLASS_M)},
            "not_a_variant_key": {"scene": key(VARIANTS + "odd/helm.glb")}}},
        # No canonical_human_female variant: the model's scene is the source;
        # no `attach`: the runtime's default (socket).
        "3:2": {"scene": key(HOOD), "variants": {"canonical_orun_female": {"scene": key(ORUN_F)}}},
        # Skinned garments are not rigid socket meshes.
        "4:1": {"scene": key(LEGS_H), "attach": "skinned", "variants": {
            "canonical_human_male": {"scene": key(LEGS_H)}, "canonical_votary_male": {"scene": key(LEGS_V)}}},
    }}


class BudgetEngine(FakeEngine):
    """The fake cook, plus what the hooked cook reports for budget rows:
    `status` for every file that received budget input ("capped" draws half
    the triangles)."""

    def __init__(self, status: str = "capped", **options):
        super().__init__(**options)
        self.items: list[dict] = []
        self.status = status

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
                if not row or not item.get("budget"):
                    continue
                limit = 2 * item["budget"]["reference_triangles"]
                for mesh in row.get("meshes", []):
                    for surface in mesh["surfaces"]:
                        note = {"status": self.status, "reference": item["budget"]["reference"],
                                "reference_triangles": item["budget"]["reference_triangles"], "limit": limit,
                                "file_triangles": 1300, "triangles": surface["triangles"]}
                        if self.status in ("capped", "partial"):
                            note["base_triangles"] = surface["triangles"] // 2
                            surface["base_triangles"] = surface["triangles"] // 2
                        surface["budget"] = note
            report_path.write_text(json.dumps(report), encoding="utf-8")
        return code


class BudgetCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temp.name))
        self.project = self.fixture.project
        sizes = {HUMAN_M: 1285, HUMAN_F: 1300, VOTARY_M: 38558, VOTARY_F: 2000, GLASS_M: 1285, ORUN_F: 900,
                 HOOD: 400, LEGS_H: 3000, LEGS_V: 9000}
        for relative, triangles in sizes.items():
            write(self.project / relative, mesh_glb((4, triangles)))
        write(self.project / cache.EQUIPMENT, json.dumps(equipment()))
        self.fixture.files = sorted(set(self.fixture.files) | set(sizes))

    def tearDown(self):
        self.temp.cleanup()

    def sha(self, relative: str) -> str:
        return hashlib.sha256((self.project / relative).read_bytes()).hexdigest()

    def records(self, **options) -> dict:
        return {row["path"]: row for row in cache.file_records(self.project, self.fixture.files, **options)}

    # --- discovery ----------------------------------------------------------------

    def test_refits_are_socket_variants_against_the_human_variant_of_their_sex(self):
        sources = cache.budget_sources(self.project)
        self.assertEqual(sources, {key(GLASS_M): [key(HUMAN_M)], key(ORUN_F): [key(HOOD)],
                                   key(VOTARY_F): [key(HUMAN_F)], key(VOTARY_M): [key(HUMAN_M)]})
        self.assertNotIn(key(LEGS_V), sources, "a skinned garment's refit is not a rigid socket mesh")
        self.assertNotIn(key(HUMAN_M), sources, "a Human source is never capped")
        self.assertNotIn(key(VARIANTS + "odd/helm.glb"), sources, "only canonical_<race>_<sex> variants count")

    def test_a_scene_that_is_a_human_source_elsewhere_is_never_a_refit(self):
        document = equipment()
        document["models"]["3:3"] = {"scene": key(VOTARY_M), "attach": "socket"}
        write(self.project / cache.EQUIPMENT, json.dumps(document))
        self.assertNotIn(key(VOTARY_M), cache.budget_sources(self.project))

    def test_no_equipment_catalogue_means_no_refits(self):
        (self.project / cache.EQUIPMENT).unlink()
        self.assertEqual(cache.budget_sources(self.project), {})
        self.assertFalse(any("budget" in row for row in self.records().values()))

    def test_triangles_come_from_the_gltf_json(self):
        self.assertEqual(cache.gltf_triangles(cache.gltf_document(self.project / VOTARY_M)), 38558)
        write(self.project / HOOD, mesh_glb((4, 100), (1, 50), (4, 20)))
        self.assertEqual(cache.gltf_triangles(cache.gltf_document(self.project / HOOD)), 120,
                         "line primitives are not triangles")
        no_indices = glb({"asset": {"version": "2.0"}, "accessors": [{"count": 30}],
                          "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}]})
        write(self.project / HOOD, no_indices)
        self.assertEqual(cache.gltf_triangles(cache.gltf_document(self.project / HOOD)), 10,
                         "an unindexed primitive counts its POSITION corners")
        self.assertEqual(cache.gltf_triangles(None), 0)

    def test_a_refit_record_carries_the_budget_input(self):
        records = self.records()
        budget = records[key(VOTARY_M)]["budget"]
        self.assertEqual(budget, {"schema": 1, "reference": key(HUMAN_M), "reference_sha256": self.sha(HUMAN_M),
                                  "reference_triangles": 1285})
        self.assertEqual(records[key(VOTARY_M)]["budget_key"], cache.budget_key(budget))
        self.assertEqual((records[key(VOTARY_M)]["budget_reference"], records[key(VOTARY_M)]["budget_reference_triangles"],
                          records[key(VOTARY_M)]["budget_status"]), (key(HUMAN_M), 1285, "ok"))
        self.assertEqual(records[key(VOTARY_F)]["budget"]["reference_triangles"], 1300, "the female Human source")
        self.assertEqual(records[key(ORUN_F)]["budget"]["reference"], key(HOOD))
        for path in (HUMAN_M, HUMAN_F, LEGS_V, NATIVE + "equipment/sword.glb"):
            self.assertNotIn("budget", records[key(path)], path)
            self.assertNotIn("budget_status", records[key(path)], path)
        self.assertFalse(any("budget" in row for row in self.records(budget=False).values()))

    def test_an_unreadable_source_leaves_the_refit_without_input(self):
        write(self.project / HUMAN_F, b"not a glb")
        row = self.records()[key(VOTARY_F)]
        self.assertNotIn("budget", row)
        self.assertEqual(row["budget_status"], "no_reference")

    def test_several_sources_take_the_largest(self):
        seen: dict = {}
        fields = cache.budget_fields(self.project, [key(HUMAN_M), key(HUMAN_F)], seen)
        self.assertEqual((fields["budget_reference"], fields["budget_reference_triangles"]), (key(HUMAN_F), 1300))
        self.assertEqual(set(seen), {key(HUMAN_M), key(HUMAN_F)}, "each source is read once")

    def test_the_plan_ratio_mirrors_the_budget_policy(self):
        text = (PROJECT / "tools/actor_geometry/budget_policy.gd").read_text(encoding="utf-8")
        match = re.search(r"^const MAX_RATIO := ([0-9.]+)$", text, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(float(match.group(1)), cache.BUDGET_RATIO)

    # --- cooking ---------------------------------------------------------------------

    def test_the_cook_receives_the_budget_input_and_the_catalogue_records_the_source(self):
        engine = BudgetEngine()
        result = self.fixture.cook(engine)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["budget_statuses"], {"ok": 4})
        items = {item["path"]: item for item in engine.items}
        self.assertEqual(items[key(VOTARY_M)]["budget"]["reference"], key(HUMAN_M))
        self.assertNotIn("budget", items[key(HUMAN_M)])
        entry = self.fixture.catalog()["entries"][key(VOTARY_M)]
        self.assertEqual(entry["inputs"], {"policy_digest": entry["inputs"]["policy_digest"],
                                           "budget_reference": key(HUMAN_M),
                                           "budget_reference_sha256": self.sha(HUMAN_M)})
        self.assertNotIn("budget_reference", self.fixture.catalog()["entries"][key(HUMAN_M)].get("inputs", {}))
        row = cache.load_summary(self.fixture.out)["files"][key(VOTARY_M)]
        self.assertEqual((row["budget_reference"], row["budget_reference_triangles"], row["budget_status"]),
                         (key(HUMAN_M), 1285, "ok"))

    def test_the_catalogue_names_a_source_only_for_a_sidecar_it_shaped(self):
        # A cook.gd without the budget stage (the HOOK not yet applied).
        self.fixture.cook(FakeEngine())
        self.assertNotIn("budget_reference", self.fixture.catalog()["entries"][key(VOTARY_M)].get("inputs", {}))
        # The stage ran and found the refit within its budget.
        self.fixture.cook(BudgetEngine("within"), force=True)
        self.assertNotIn("budget_reference", self.fixture.catalog()["entries"][key(VOTARY_M)].get("inputs", {}))
        self.fixture.cook(BudgetEngine("partial"), force=True)
        self.assertIn("budget_reference", self.fixture.catalog()["entries"][key(VOTARY_M)]["inputs"])

    def test_source_changes_recook_only_its_refits(self):
        self.fixture.cook(BudgetEngine())
        engine = BudgetEngine()
        self.fixture.cook(engine)
        self.assertEqual(engine.calls, [], "nothing changed: everything is reused")
        write(self.project / HUMAN_M, mesh_glb((4, 1290)))
        engine = BudgetEngine()
        self.fixture.cook(engine)
        self.assertEqual(sorted(engine.calls[0]), sorted([key(HUMAN_M), key(VOTARY_M), key(GLASS_M)]),
                         "a new Human source recooks itself and its refits only")
        engine = BudgetEngine()
        self.fixture.cook(engine, budget=False)
        self.assertEqual(sorted(engine.calls[0]), sorted(key(path) for path in (VOTARY_M, VOTARY_F, GLASS_M, ORUN_F)),
                         "cooking without the budget recooks the refits")
        self.assertFalse(any("budget" in item for item in engine.items))
        row = cache.load_summary(self.fixture.out)["files"][key(VOTARY_M)]
        self.assertFalse(any(field in row for field in cache.BUDGET_FIELDS), "no budget fields without the budget")

    def test_reused_rows_follow_the_current_budget_status(self):
        self.fixture.cook(BudgetEngine())
        write(self.project / HUMAN_F, b"broken")
        engine = BudgetEngine()
        result = self.fixture.cook(engine)
        self.assertIn(key(VOTARY_F), engine.calls[0], "losing the source drops the budget key: recook")
        self.assertEqual(result["budget_statuses"], {"ok": 3, "no_reference": 1})
        self.assertEqual(cache.load_summary(self.fixture.out)["files"][key(VOTARY_F)]["budget_status"], "no_reference")

    def test_the_budget_stage_is_part_of_the_policy_digest(self):
        self.assertIn("tools/actor_geometry/budget_policy.gd", cache.POLICY_FILES)
        first = cache.policy_digest(self.project, ENGINE)
        write(self.project / "tools/actor_geometry/budget_policy.gd", "# budget stage v2\n")
        self.assertNotEqual(first, cache.policy_digest(self.project, ENGINE))

    # --- report, prediction and plan ------------------------------------------------------

    def test_the_report_counts_budgeted_refits(self):
        self.fixture.cook(BudgetEngine())
        budgeting = cache.report(self.fixture.out)["budget"]
        # Four refits, two surfaces each in the fake report (1,000 + 300 triangles).
        self.assertEqual(budgeting["surfaces"], {"capped": 8})
        self.assertEqual(budgeting["files"], {"capped": 4})
        self.assertEqual((budgeting["triangles"], budgeting["base_triangles"]), (4 * 1300, 4 * 650))

    def test_prediction_draws_the_capped_base(self):
        surface = {"triangles": 38558, "base_triangles": 4818, "levels": [[2408, 0.0140, 0.0419, 0]]}
        options = {"model_scale": 1.0, "lod_bias": 1.0, "multiplier": 1.658, "width": 1920.0}
        self.assertEqual(cache.level_triangles(surface, 3.0, **options), 4818, "close up: the capped base")
        self.assertEqual(cache.level_triangles(surface, 20.0, **options), 2408)

    def test_plan_lists_budget_statuses(self):
        out = Path(self.temp.name) / "plan-out"
        args = ["plan", "--project", str(self.project), "--out", str(out), "--engine", ENGINE, "--no-masks"]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(cache.main(args), 0)
        result = json.loads(buffer.getvalue())
        self.assertEqual(result["budget_statuses"], {"ok": 4})
        self.assertEqual(result["refits_over_budget"], 2,
                         "the Votary male helm (38,558 of 1,285) and the Orun hood (900 of 400) draw over 2x their source")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(cache.main(args + ["--no-budget"]), 0)
        self.assertEqual(json.loads(buffer.getvalue())["budget_statuses"], {})

    # --- the real engine (optional) -------------------------------------------------------

    @unittest.skipUnless(os.environ.get("RABBITLANDS_GODOT"), "set RABBITLANDS_GODOT to cook with a real editor binary")
    def test_real_cook_caps_the_votary_sun_headband(self):
        cook_script = (PROJECT / "tools/actor_geometry/cook.gd").read_text(encoding="utf-8")
        if "BudgetPolicy.apply" not in cook_script:
            self.skipTest("cook.gd does not run the budget stage yet (HOOK from actor LODs C11)")
        refit = NATIVE + "equipment/variants/votary_male/sunmane_steppe_headgear_06.glb"
        within = NATIVE + "equipment/variants/glasswarden_male/sunmane_steppe_headgear_06.glb"
        out = Path(self.temp.name) / "real"
        options = {"out": out, "wrapper": os.environ.get("RABBITLANDS_GODOT_WRAPPER"), "paths": [refit, within]}
        result = cache.cook(PROJECT, Path(os.environ["RABBITLANDS_GODOT"]), masks=None, **options)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["budget_statuses"], {"ok": 2})
        files = cache.load_summary(out)["files"]
        notes = [surface["budget"] for mesh in files[key(refit)]["meshes"] for surface in mesh["surfaces"]]
        self.assertEqual([note["status"] for note in notes], ["partial"], notes)
        self.assertLess(notes[0]["base_triangles"], 38558 // 4)
        self.assertEqual({surface["budget"]["status"] for mesh in files[key(within)]["meshes"]
                          for surface in mesh["surfaces"]}, {"within"})
        self.assertIn("budget_reference", self.fixture_catalog(out)["entries"][key(refit)]["inputs"])
        verified = cache.verify(PROJECT, Path(os.environ["RABBITLANDS_GODOT"]), **options)
        self.assertTrue(verified["ok"], verified)
        self.assertEqual(verified["scene_mismatches"], [])

    @staticmethod
    def fixture_catalog(out: Path) -> dict:
        return json.loads((out / cache.POLICY / cache.CATALOG_FILE).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
