"""Actor geometry cook driver (tools/actor_geometry_cache.py): scope, cache
reuse and invalidation, batching, catalogue writing, failure attribution,
reports and census prediction. Godot is replaced by a fake engine run; one
optional test cooks real files when RABBITLANDS_GODOT names an editor binary
(RABBITLANDS_GODOT_WRAPPER may prefix it, for example with a slot lock)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY = PROJECT.parent
sys.path.insert(0, str(PROJECT / "tools"))
import actor_geometry_cache as cache

ENGINE = "4.7.2.stable.official.ed1daf0bf"
NATIVE = "assets/actors/native/"


def write(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


class FakeEngine:
    """Stands in for Godot running cook.gd: reads the job, writes blobs, the
    report and a log, like the real script."""

    def __init__(self, *, engine: str = ENGINE, unchanged: tuple = (), script_error: tuple = (),
                 fail_batches: tuple = (), engine_errors: tuple = ()):
        self.engine = engine
        self.unchanged = set(unchanged)
        self.script_error = set(script_error)
        self.fail_batches = set(fail_batches)
        self.engine_errors = set(engine_errors)
        self.calls: list[list[str]] = []
        self.commands: list[list[str]] = []
        self.batch = 0

    def __call__(self, command, env, log, stdout, timeout):
        job = json.loads(Path(env["RABBITLANDS_ACTOR_GEOMETRY_JOB"]).read_text(encoding="utf-8"))
        self.commands.append(command)
        self.calls.append([item["path"] for item in job["files"]])
        index = self.batch
        self.batch += 1
        lines = []
        if index in self.fail_batches:
            log.write_text("SCRIPT ERROR: Parse Error: broken\n", encoding="utf-8")
            return 1
        root = Path(job["root"])
        report = {"schema": 1, "mode": job["mode"], "ok": True, "engine": self.engine, "policy": cache.POLICY,
                  "policy_settings": {"version": 1}, "entries": {}, "results": {}, "usec": 1}
        for item in job["files"]:
            path = item["path"]
            lines.append(cache.LOG_PREFIX + path)
            if path in self.engine_errors:
                lines.append("ERROR: Failed loading resource: texture.png.")
            if path in self.script_error:
                lines.append("SCRIPT ERROR: Invalid call. Nonexistent function.")
            if job["mode"] == "verify":
                report["results"][path] = {"status": "applied", "reason": "", "apply_usec": 1000, "levels": 2,
                                           "scene_levels": 2, "scene_mismatches": 0, "unseen_levels": 0}
                continue
            if path in self.unchanged:
                report["results"][path] = {"status": "unchanged", "meshes": [], "lod_levels": 0}
                continue
            blob = hashlib.sha256((path + item["file_sha256"] + repr(item["model_scale"])).encode()).digest() * 4
            digest = hashlib.sha256(blob).hexdigest()
            write(root / "blobs" / f"{digest}.rlgeo", blob)
            entry = {"source_sha256": item["file_sha256"], "source_bytes": item["bytes"],
                     "sidecar": f"blobs/{digest}.rlgeo", "sidecar_sha256": digest, "sidecar_bytes": len(blob),
                     "inputs": {"policy_digest": job["policy_digest"]}}
            report["entries"][path] = entry
            report["results"][path] = {
                "status": "cooked", "sidecar_sha256": digest, "sidecar_bytes": len(blob), "lod_levels": 3,
                "cook_usec": 2000, "parse_usec": 1000, "plan_usec": 500,
                "meshes": [{"name": "stem_Shell", "model_scale": item["model_scale"], "surfaces": [
                    {"triangles": 1000, "vertices": 900, "method": "chain",
                     "levels": [[500, 0.01, 0.002, 0], [250, 0.03, 0.05, 1]]},
                    {"triangles": 300, "vertices": 900, "method": "none", "reason": "per_face_tiles", "levels": []}]}]}
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        write(Path(job["report"]), json.dumps(report))
        return 0


class Fixture:
    def __init__(self, base: Path):
        self.project = base / "repo" / "godot-client"
        self.out = base / "out"
        write(self.project / "project.godot", "config_version=5\n")
        for relative in cache.POLICY_FILES:
            write(self.project / relative, f"# {relative}\n")
        self.files = [NATIVE + "equipment/sword.glb", NATIVE + "equipment/variants/human_male/coat.glb",
                      NATIVE + "creatures/fox.glb", NATIVE + "races/elf.gltf", NATIVE + "hair/bob.GLB"]
        for relative in self.files:
            write(self.project / relative, f"glTF {relative}")
        # A .gltf whose geometry lives in an external buffer (like the shared
        # Superhero_*_FullBody.gltf/.bin animation sources).
        write(self.project / (NATIVE + "races/elf.gltf"), json.dumps({
            "asset": {"version": "2.0"}, "buffers": [{"byteLength": 8, "uri": "elf%20body.bin"}],
            "images": [{"uri": "elf.png"}]}))
        write(self.project / (NATIVE + "races/elf body.bin"), b"geometry")
        write(self.project / (NATIVE + "rl_heads/rl_head_male.glb"), "head")
        write(self.project / (NATIVE + "equipment/textures/sword.png"), "png")
        write(self.project / (NATIVE + "creatures/retired_wolf.glb"), "retired")
        write(self.project / "data/assets/retired_procedural_models.json",
              json.dumps({"runtimePaths": ["actors/native/creatures/retired_wolf.glb"]}))
        self.set_scale(0.25)

    def set_scale(self, scale: float) -> None:
        write(self.project / cache.MODELS, json.dumps({"models": {
            "fox": {"scene": "res://" + NATIVE + "creatures/fox.glb", "import": {"scale": scale}},
            "fox_cub": {"scene": "res://" + NATIVE + "creatures/fox.glb", "import": {"scale": scale * 2}},
            "elf": {"scene": "res://" + NATIVE + "races/elf.gltf", "import": {"scale": 1.0}}}}))

    def cook(self, engine: FakeEngine, **options):
        return cache.cook(self.project, Path("godot.exe"), out=self.out, runner=engine, engine=ENGINE, **options)

    def catalog(self) -> dict:
        return json.loads((self.out / cache.POLICY / cache.CATALOG_FILE).read_text(encoding="utf-8"))


class ActorGeometryCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.fixture = Fixture(self.base)

    def tearDown(self):
        self.temp.cleanup()

    # --- scope -----------------------------------------------------------------

    def test_scope_matches_the_runtime_rule(self):
        # The same cases test_actor_geometry.gd checks for Format.in_scope.
        self.assertTrue(cache.in_scope(NATIVE + "equipment/variants/human_male/x.glb"))
        self.assertTrue(cache.in_scope(NATIVE + "hair/x.GLB"))
        self.assertTrue(cache.in_scope(NATIVE + "shared/x.gltf"))
        self.assertFalse(cache.in_scope(NATIVE + "rl_heads/rl_head_male.glb"))
        self.assertFalse(cache.in_scope("assets/world/interactives/storage_1.glb"))
        self.assertFalse(cache.in_scope(NATIVE + "../world/x.glb"))
        self.assertFalse(cache.in_scope(NATIVE + "equipment\\x.glb"))
        self.assertFalse(cache.in_scope(NATIVE + "equipment/x.png"))

    def test_scope_files_skip_heads_retired_and_other_files(self):
        files = cache.scope_files(self.fixture.project)
        self.assertEqual(files, sorted(self.fixture.files))

    def test_model_scale_is_the_smallest_import_scale(self):
        records = {row["path"]: row for row in cache.file_records(self.fixture.project, self.fixture.files)}
        self.assertEqual(records["res://" + NATIVE + "creatures/fox.glb"]["model_scale"], 0.25)
        self.assertEqual(records["res://" + NATIVE + "equipment/sword.glb"]["model_scale"], 1.0)
        sword = self.fixture.project / NATIVE / "equipment/sword.glb"
        self.assertEqual(records["res://" + NATIVE + "equipment/sword.glb"]["file_sha256"],
                         hashlib.sha256(sword.read_bytes()).hexdigest())

    def test_policy_digest_follows_engine_and_cook_files(self):
        project = self.fixture.project
        first = cache.policy_digest(project, ENGINE)
        self.assertNotEqual(first, cache.policy_digest(project, "4.7.3.stable.official.0123456789"))
        write(project / "tools/actor_geometry/lod_policy.gd", "# changed\n")
        self.assertNotEqual(first, cache.policy_digest(project, ENGINE))

    # --- cooking and reuse ----------------------------------------------------------

    def test_first_cook_writes_a_deterministic_catalogue(self):
        engine = FakeEngine(unchanged=("res://" + NATIVE + "hair/bob.GLB",))
        result = self.fixture.cook(engine, batch_size=2)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["statuses"], {"cooked": 4, "unchanged": 1})
        self.assertEqual([len(call) for call in engine.calls], [2, 2, 1], "batches hold at most --batch-size files")
        catalog_path = self.fixture.out / cache.POLICY / cache.CATALOG_FILE
        text = catalog_path.read_text(encoding="utf-8")
        catalog = json.loads(text)
        self.assertEqual((catalog["schema"], catalog["policy"], catalog["engine"], catalog["source_check"]),
                         (1, cache.POLICY, ENGINE, "file"))
        self.assertEqual(sorted(catalog["entries"]), sorted("res://" + item for item in self.fixture.files
                                                           if not item.endswith("bob.GLB")))
        self.assertEqual(text, json.dumps(catalog, sort_keys=True, separators=(",", ":")) + "\n",
                         "the catalogue is compact JSON with sorted keys")
        for entry in catalog["entries"].values():
            self.assertTrue(cache.blob_intact(self.fixture.out / cache.POLICY, entry))
        command = engine.commands[0]
        self.assertLess(command.index("--log-file"), command.index("--path"), "--log-file precedes --path")
        self.assertIn("--headless", command)
        self.assertEqual(command[-1], cache.COOK_SCRIPT)

    def test_a_second_cook_reuses_everything(self):
        self.fixture.cook(FakeEngine())
        before = (self.fixture.out / cache.POLICY / cache.CATALOG_FILE).read_bytes()
        engine = FakeEngine()
        result = self.fixture.cook(engine)
        self.assertEqual(engine.calls, [], "nothing is cooked again")
        self.assertEqual(result["reused"], 5)
        self.assertEqual((self.fixture.out / cache.POLICY / cache.CATALOG_FILE).read_bytes(), before)

    def test_changed_inputs_recook_only_what_they_touch(self):
        self.fixture.cook(FakeEngine())
        write(self.fixture.project / NATIVE / "equipment/sword.glb", "glTF sword, refitted")
        engine = FakeEngine()
        self.fixture.cook(engine)
        self.assertEqual(engine.calls, [["res://" + NATIVE + "equipment/sword.glb"]])
        self.fixture.set_scale(0.5)
        engine = FakeEngine()
        self.fixture.cook(engine)
        self.assertEqual(engine.calls, [["res://" + NATIVE + "creatures/fox.glb"]], "a new import scale recooks the model")
        write(self.fixture.project / "tools/actor_geometry/lod_policy.gd", "# policy v2\n")
        engine = FakeEngine()
        result = self.fixture.cook(engine)
        self.assertEqual(sum(len(call) for call in engine.calls), 5, "a policy change recooks everything")
        self.assertEqual(result["cooked_now"], 5)

    def test_an_external_buffer_change_recooks_its_gltf(self):
        self.fixture.cook(FakeEngine())
        key = "res://" + NATIVE + "races/elf.gltf"
        row = cache.load_summary(self.fixture.out)["files"][key]
        self.assertEqual(len(row.get("dependencies_sha256", "")), 64, "the .bin is part of the cache key")
        self.assertNotIn("dependencies_sha256", cache.load_summary(self.fixture.out)["files"][
            "res://" + NATIVE + "equipment/sword.glb"], "a self-contained file records no dependencies")
        write(self.fixture.project / NATIVE / "races/elf body.bin", b"refitted")
        engine = FakeEngine()
        self.fixture.cook(engine)
        self.assertEqual(engine.calls, [[key]], "only the .gltf that reads the changed buffer is cooked again")
        engine = FakeEngine()
        self.fixture.cook(engine)
        self.assertEqual(engine.calls, [], "the new buffer hash is remembered")

    def test_external_buffers_are_read_from_gltf_and_glb_json(self):
        document = {"asset": {"version": "2.0"}, "buffers": [
            {"byteLength": 4}, {"byteLength": 4, "uri": "data:application/octet-stream;base64,AAAAAA=="},
            {"byteLength": 4, "uri": "parts/a.bin"}], "images": [{"uri": "a.png"}]}
        payload = json.dumps(document).encode("utf-8")
        payload += b" " * (-len(payload) % 4)
        glb = b"glTF" + (2).to_bytes(4, "little") + (20 + len(payload)).to_bytes(4, "little") \
            + len(payload).to_bytes(4, "little") + b"JSON" + payload
        write(self.base / "x.glb", glb)
        write(self.base / "x.gltf", json.dumps(document))
        write(self.base / "broken.glb", b"glTF\x02\x00")
        self.assertEqual(cache.external_buffers(self.base / "x.glb"), ["parts/a.bin"])
        self.assertEqual(cache.external_buffers(self.base / "x.gltf"), ["parts/a.bin"])
        self.assertEqual(cache.external_buffers(self.base / "broken.glb"), [])
        missing = cache.dependencies_sha256(self.base / "x.glb")
        write(self.base / "parts/a.bin", b"bytes")
        self.assertNotEqual(cache.dependencies_sha256(self.base / "x.glb"), missing)

    def test_a_damaged_blob_is_recooked(self):
        self.fixture.cook(FakeEngine())
        key = "res://" + NATIVE + "races/elf.gltf"
        entry = self.fixture.catalog()["entries"][key]
        write(self.fixture.out / cache.POLICY / entry["sidecar"], b"tampered")
        engine = FakeEngine()
        self.fixture.cook(engine)
        self.assertEqual(engine.calls, [[key]])

    def test_removed_files_leave_the_catalogue_and_their_blobs(self):
        self.fixture.cook(FakeEngine())
        key = "res://" + NATIVE + "equipment/sword.glb"
        blob = self.fixture.out / cache.POLICY / self.fixture.catalog()["entries"][key]["sidecar"]
        (self.fixture.project / NATIVE / "equipment/sword.glb").unlink()
        stray = self.fixture.out / cache.POLICY / "blobs" / "notes.txt"
        write(stray, "kept")
        result = self.fixture.cook(FakeEngine())
        self.assertNotIn(key, self.fixture.catalog()["entries"])
        self.assertFalse(blob.exists())
        self.assertEqual(result["blobs_removed"], 1)
        self.assertTrue(stray.exists(), "only <sha256>.rlgeo blobs are collected")

    def test_a_partial_cook_keeps_the_other_entries(self):
        self.fixture.cook(FakeEngine())
        before = self.fixture.catalog()["entries"]
        engine = FakeEngine()
        self.fixture.cook(engine, paths=[NATIVE + "equipment/sword.glb"], force=True)
        self.assertEqual(engine.calls, [["res://" + NATIVE + "equipment/sword.glb"]])
        self.assertEqual(self.fixture.catalog()["entries"], before)
        with self.assertRaises(cache.CookError):
            self.fixture.cook(FakeEngine(), paths=[NATIVE + "rl_heads/rl_head_male.glb"])

    def test_script_errors_and_failed_batches_never_reach_the_catalogue(self):
        bad = "res://" + NATIVE + "creatures/fox.glb"
        noisy = "res://" + NATIVE + "races/elf.gltf"
        result = self.fixture.cook(FakeEngine(script_error=(bad,), engine_errors=(noisy,)))
        self.assertFalse(result["ok"])
        self.assertIn(bad, result["failed"])
        self.assertNotIn(bad, self.fixture.catalog()["entries"])
        self.assertIn(noisy, self.fixture.catalog()["entries"], "an engine error line is reported, not fatal")
        summary = cache.load_summary(self.fixture.out)
        self.assertEqual(summary["files"][bad]["reason"], "script_error")
        self.assertTrue(summary["files"][noisy]["engine_errors"][0].startswith("ERROR:"))
        result = cache.cook(self.fixture.project, Path("godot.exe"), out=self.base / "out2",
                            runner=FakeEngine(fail_batches=(0,)), engine=ENGINE, batch_size=3)
        self.assertFalse(result["ok"])
        summary = cache.load_summary(self.base / "out2")
        self.assertEqual(sorted(row["reason"] for row in summary["files"].values() if row["status"] == "failed"),
                         ["engine"] * 3)
        self.assertEqual(len(json.loads((self.base / "out2" / cache.POLICY / cache.CATALOG_FILE)
                                        .read_text(encoding="utf-8"))["entries"]), 2)

    def test_a_cook_on_another_engine_is_refused(self):
        with self.assertRaises(cache.CookError):
            self.fixture.cook(FakeEngine(engine="4.7.3.stable.official.0123456789"))

    def test_source_check_is_written_to_the_catalogue(self):
        self.fixture.cook(FakeEngine(), source_check="parsed")
        self.assertEqual(self.fixture.catalog()["source_check"], "parsed")
        with self.assertRaises(cache.CookError):
            self.fixture.cook(FakeEngine(), source_check="sometimes")

    def test_old_run_folders_are_pruned(self):
        for _ in range(cache.KEEP_RUNS + 3):
            self.fixture.cook(FakeEngine(), force=True)
        runs = [path for path in (self.fixture.out / "cook" / "jobs").iterdir() if path.is_dir()]
        self.assertEqual(len(runs), cache.KEEP_RUNS)

    def test_verify_counts_applied_files(self):
        self.fixture.cook(FakeEngine(unchanged=("res://" + NATIVE + "hair/bob.GLB",)))
        result = cache.verify(self.fixture.project, Path("godot.exe"), out=self.fixture.out, runner=FakeEngine())
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["statuses"], {"applied": 4})
        self.assertEqual(result["scene_levels"], 8)
        nothing = cache.verify(self.fixture.project, Path("godot.exe"), out=self.fixture.out, runner=FakeEngine(),
                               paths=[NATIVE + "hair/bob.GLB"])
        self.assertEqual(nothing["files"], 0)
        self.assertFalse(nothing["ok"], "verifying no file at all is not a pass")

    def test_one_driver_per_output_folder(self):
        self.fixture.cook(FakeEngine())
        with cache.driver_lock(self.fixture.out):
            engine = FakeEngine()
            with self.assertRaises(cache.CookError):
                self.fixture.cook(engine, force=True)
            with self.assertRaises(cache.CookError):
                cache.verify(self.fixture.project, Path("godot.exe"), out=self.fixture.out, runner=engine)
            self.assertEqual(engine.calls, [], "a second driver never starts Godot")
        result = self.fixture.cook(FakeEngine(), force=True)
        self.assertTrue(result["ok"], "the lock is released when the first driver ends")

    # --- output location -----------------------------------------------------------

    @unittest.skipIf(shutil.which("git") is None, "git is not installed")
    def test_output_inside_a_checkout_must_be_ignored(self):
        repository = self.base / "checkout"
        repository.mkdir()
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        with self.assertRaises(cache.CookError):
            cache.ensure_ignored(repository / ".local" / "actor-geometry")
        shutil.copyfile(REPOSITORY / ".gitignore", repository / ".gitignore")
        cache.ensure_ignored(repository / ".local" / "actor-geometry")

    # --- reports -----------------------------------------------------------------------

    def test_report_weights_coverage_by_triangles(self):
        self.fixture.cook(FakeEngine(unchanged=("res://" + NATIVE + "hair/bob.GLB",)))
        result = cache.report(self.fixture.out)
        self.assertEqual(result["statuses"], {"cooked": 4, "unchanged": 1})
        self.assertEqual(result["source_triangles"], 4 * 1300)
        self.assertAlmostEqual(result["coverage_triangles_2plus"], 1000 / 1300, places=4)
        self.assertEqual(result["reasons"]["per_face_tiles"], {"surfaces": 4, "triangles": 1200})
        self.assertEqual(result["classes"]["creatures"]["files"], 1)

    def test_compare_finds_differing_blobs(self):
        self.fixture.cook(FakeEngine())
        other = self.base / "out2"
        cache.cook(self.fixture.project, Path("godot.exe"), out=other, runner=FakeEngine(), engine=ENGINE)
        self.assertTrue(cache.compare(self.fixture.out / cache.POLICY, other / cache.POLICY)["identical"])
        blob = next((other / cache.POLICY / "blobs").glob("*.rlgeo"))
        blob.write_bytes(b"different")
        result = cache.compare(self.fixture.out / cache.POLICY, other / cache.POLICY)
        self.assertFalse(result["identical"])
        self.assertEqual(result["differing_blobs"], [blob.name])

    def test_level_selection_follows_godot(self):
        surface = {"triangles": 1000, "levels": [[500, 0.01, 0.0, 0], [250, 0.03, 0.0, 1]]}
        multiplier = cache.lod_multiplier(50.0, 16 / 9)
        # Level i draws once edge * scale * bias / (depth * multiplier) <= 1 / width.
        first = 0.01 * 1920 / multiplier
        self.assertEqual(cache.level_triangles(surface, first * 0.999, model_scale=1, lod_bias=1,
                                               multiplier=multiplier, width=1920), 1000)
        self.assertEqual(cache.level_triangles(surface, first * 1.001, model_scale=1, lod_bias=1,
                                               multiplier=multiplier, width=1920), 500)
        self.assertEqual(cache.level_triangles(surface, first * 1.001 * 0.35, model_scale=1, lod_bias=0.35,
                                               multiplier=multiplier, width=1920), 500, "lod_bias scales the depth")
        self.assertEqual(cache.level_triangles(surface, 1000.0, model_scale=1, lod_bias=1,
                                               multiplier=multiplier, width=1920), 250)

    def test_predict_maps_census_pieces_to_cooked_meshes(self):
        project = self.fixture.project
        write(project / "data/actors/equipment.json", json.dumps({"models": {
            "4:171": {"scene": "res://" + NATIVE + "equipment/sword.glb",
                      "variants": {"canonical_human_male": {"scene": "res://" + NATIVE + "equipment/variants/human_male/coat.glb"}}},
            "0:114": {"scene": "res://" + NATIVE + "equipment/sword.glb"}}}))
        self.fixture.cook(FakeEngine())
        census = {"camera": {"fieldOfView": 50.0}, "cells": [{
            "effectiveRuntime": {"effectiveSettings": {"rootSize": [1920, 1080]}},
            "census": {"afterSpawn": {"triangleCensus": [
                {"inFrustum": True, "distance": 100.0, "pieces": {
                    "eq4:171:Shell": {"tris": 1300},
                    "BodyRoot/Skeleton3D/EquipmentPart_0_Visual_114_hand_r/NativeEquipment/Shell": {"tris": 650},
                    "NativeModel/BodyRoot/Skeleton3D/RLHead/RLHead_lod2": {"tris": 1600},
                    "MapDot": {"tris": 768}}},
                {"inFrustum": False, "distance": 5.0, "pieces": {"eq4:171:Shell": {"tris": 1300}}}]}}}]}
        census_path = self.base / "census.json"
        write(census_path, json.dumps(census))
        result = cache.predict(self.fixture.out, project, census_path, biases=[1.0],
                               variant="canonical_human_male", body_scene="res://" + NATIVE + "races/elf.gltf")
        row = result["by_lod_bias"]["1.0"]
        # At 100 m both chained levels draw: the 1000-triangle surface shows 250.
        self.assertEqual(row["bodies"], 1)
        self.assertEqual(row["measured_triangles"], 1300 + 650 + 1600)
        self.assertEqual(row["predicted_triangles"], 550 + round(650 * 550 / 1300) + 1600)
        self.assertEqual(result["mapped_pieces"], {"Shell": 2})
        self.assertEqual(result["unmapped_pieces"], {"RLHead_lod2": 1})
        self.assertAlmostEqual(row["drawn_coverage_2plus"], (1000 + 500) / 3550, places=4)

    # --- engine runs ----------------------------------------------------------------------

    def test_engine_runs_are_bounded(self):
        log = self.base / "engine.log"
        stdout = self.base / "engine.out"
        began = time.monotonic()
        with self.assertRaises(cache.CookError):
            cache.run_engine([sys.executable, "-c", "import time; time.sleep(60)"], dict(os.environ),
                             log, stdout, timeout_seconds=60, slot_wait_seconds=1)
        writer = "import sys, time; open(sys.argv[1], 'w').write('started'); time.sleep(60)"
        with self.assertRaises(cache.CookError):
            cache.run_engine([sys.executable, "-c", writer, str(log)], dict(os.environ), log, stdout,
                             timeout_seconds=1, slot_wait_seconds=30)
        self.assertLess(time.monotonic() - began, 30, "both runs were stopped well before they finished")
        self.assertEqual(cache.run_engine([sys.executable, "-c", "pass"], dict(os.environ), log, stdout, 30), 0)

    def test_log_lines_are_attributed_to_the_announced_file(self):
        log = self.base / "godot.log"
        write(log, "Godot Engine v4.7.2\nERROR: early\n" + cache.LOG_PREFIX + "res://a.glb\nERROR: late\n"
              "   at: somewhere\nSCRIPT ERROR: Invalid call\n" + cache.LOG_PREFIX + "cook done: 1 files\n")
        scanned = cache.scan_log(log)
        self.assertEqual(scanned["errors"], {"": ["ERROR: early"], "res://a.glb": ["ERROR: late"]})
        self.assertEqual(scanned["script_errors"], {"res://a.glb": ["SCRIPT ERROR: Invalid call"]})

    # --- the real engine (optional) --------------------------------------------------------

    @unittest.skipUnless(os.environ.get("RABBITLANDS_GODOT"), "set RABBITLANDS_GODOT to cook with a real editor binary")
    def test_real_cook_and_verify(self):
        out = self.base / "real"
        paths = [NATIVE + "equipment/militia_arming_sword.glb", NATIVE + "creatures/amber_lantern_moth.glb"]
        options = {"out": out, "wrapper": os.environ.get("RABBITLANDS_GODOT_WRAPPER"), "paths": paths}
        result = cache.cook(PROJECT, Path(os.environ["RABBITLANDS_GODOT"]), **options)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["statuses"], {"cooked": 1, "unchanged": 1})
        verified = cache.verify(PROJECT, Path(os.environ["RABBITLANDS_GODOT"]), **options)
        self.assertTrue(verified["ok"], verified)
        self.assertEqual(verified["statuses"], {"applied": 1})
        self.assertEqual(verified["scene_mismatches"], [])


if __name__ == "__main__":
    unittest.main()
