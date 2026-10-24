"""Fake-only full desktop release gates; never launch an engine or publish."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import full_optimization_package as full

COMMIT = "a" * 40
PROFILE = {"profile": {"features": dict(full.FEATURES)},
           "runtime": {"mode": "rust", "native_available": True},
           "remote": {"backend": "rust"}, "admission": {"mode": "rust", "worker_limit": 1},
           "prepared": {"catalog_present": True, "mode": "auto", "node_policy": "lazy-source-v1"},
           "effects": {"requested": "heat_bolt"}}


def startup(value=None):
    return "RABBITLANDS_OPTIMIZATION_STARTUP " + json.dumps(PROFILE if value is None else value) + "\n"


def observation(platform="windows"):
    return {"policy": full.graphics.OBSERVATION_POLICY, "platform": platform,
            "rendering_method": "forward_plus" if platform == "windows" else "gl_compatibility",
            "rendering_driver": "d3d12" if platform == "windows" else "opengl3",
            "adapter_type": 4 if platform == "windows" else 0,
            "adapter_name": "Microsoft Basic Render Driver" if platform == "windows" else "llvmpipe (fixture)",
            "software_adapter": True, "detected_format_mask": 7, "resource_buffer_probe": True}


@pytest.fixture
def context(tmp_path, monkeypatch):
    repository = tmp_path / "source"
    project, stage = repository / "godot-client", tmp_path / "package"
    (project / "tools").mkdir(parents=True)
    (project / "tests").mkdir()
    (stage / "app").mkdir(parents=True)
    (stage / "app/RabbitLands.pck").write_bytes(b"final-pck-fixture")
    for name in ("test_optimization_profile.gd", "test_remote_presentation.gd", "test_native_resource_admission.gd",
                 "test_rust_spell_flights.gd", "test_rust_mounted_upper.gd"):
        (project / "tests" / name).write_bytes(b"# committed test fixture\n")
    (project / "tools/check_prepared_release.gd").write_bytes(b"# external final-PCK guard\n")
    godot = tmp_path / "tools/godot"
    godot.parent.mkdir()
    godot.write_bytes(b"verified-editor-fixture")
    graphics = {"platform": "windows", "rendering_method": "forward_plus", "rendering_driver": "d3d12",
                "display_driver": "windows", "gpu_index": 0, "command_prefix": [], "env": {}}
    monkeypatch.setattr(full.graphics, "prepare_graphics", lambda *args, **kwargs: graphics)
    budget = []
    build = full.FullOptimizationBuild(project, stage, godot, "windows", COMMIT,
        tmp_path / "optimization", tmp_path / "native-cache", lambda *args: budget.append(args))
    rows, required = [], {}
    for skip, quality in enumerate(("full", "half", "quarter")):
        group = []
        for kind, policy in (("scene", "retain"), ("world", "lazy-source-v1")):
            row = {"kind": kind, "source": "eloria-assets/" + kind + ".json", "node_policy": policy,
                   "texture_skip": skip, "source_digest": "b" * 64,
                   "entry_id": hashlib.sha256((quality + kind).encode()).hexdigest(),
                   "texture_token": "vram|" + quality + "|7|actual"}
            rows.append(row)
            group.append((kind, row["source"], policy))
        required[quality] = group
    index = project / "prepared-content/index.json"
    index.parent.mkdir()
    index.write_text(json.dumps({"entries": rows}))
    build.receipt.update(native={"source": {"source_digest": "c" * 64}},
                         prepared={"entries": len(rows), "required_entries": required},
                         prepared_export={"export": {"status": "complete"},
                                          "catalog_sha256": full.native.sha256(index)})
    build.save()
    return build, rows, budget


def final_engine(build, rows, reports, *, mutation=None):
    def run(argv, environment, log, timeout_seconds, **kwargs):
        editor = guard_editor(build)
        assert Path(argv[0]) == editor
        assert editor.is_file() and editor.read_bytes() == build.godot.read_bytes()
        assert argv[argv.index("--main-pack") + 1] == build.stage / "app/RabbitLands.pck"
        assert "--path" not in argv
        script = Path(argv[argv.index("--script") + 1])
        assert script == build.project / "tools/check_prepared_release.gd"
        assert not script.is_relative_to(build.stage)
        job = json.loads(Path(argv[-1]).read_text())
        quality = job["texture_quality"]
        selected = [row for row in rows if row["texture_skip"] == ("full", "half", "quarter").index(quality)]
        assert job["expected_stage_root"] == str(build.stage)
        assert job["expected_stage_app"] == str(build.stage / "app")
        assert job["catalog_sha256"] == full.native.sha256(build.project / "prepared-content/index.json")
        assert job["required_entries"] == [{key: row[key] for key in
            ("kind", "source", "node_policy", "entry_id", "source_digest", "texture_token")} for row in selected]
        assert not Path(job["report"]).is_relative_to(build.stage)
        assert not Path(job["expected_user_directory"]).is_relative_to(build.stage)
        assert not Path(job["report"]).exists()
        assert all(Path(value).is_relative_to(build.root / "users") for value in environment.values())
        report = {"schema_version": 1, "status": "pass", "failures": [],
                  "catalog_sha256": job["catalog_sha256"], "catalog_entries": len(rows),
                  "entry_ids": [row["entry_id"] for row in selected], "entries": selected,
                  "texture_quality": quality, "stage_app": str(build.stage / "app"),
                  "project_root": str(build.stage / "app"), "graphics": observation(build.platform),
                  "resources": {"mesh_surfaces": 3, "multimesh_instances": 2, "textures": 2,
                                "animation_keys": 4, "skeleton_bones": 5, "collision_shapes": 1},
                  "nodes_before": 1, "nodes_after": 1,
                  "prepared": {"hits": len(selected), "consumed_entries": selected}}
        if mutation:
            mutation(report, build)
        Path(job["report"]).write_text(json.dumps(report))
        reports.append(job)
        return "PREPARED_RELEASE_CHECK " + json.dumps({"status": report["status"]})
    return run


def guard_editor(build):
    return build.stage / "app" / ("RabbitLands-release-guard-editor.exe" if build.platform == "windows"
                                   else "RabbitLands-release-guard-editor.x86_64")


def test_ordinary_startup_requires_exact_six_features_and_actual_backends():
    assert full.validate_startup(startup()) == PROFILE
    for path, value in (("runtime", {"mode": "legacy", "native_available": False}),
                        ("remote", {"backend": "legacy"}),
                        ("admission", {"mode": "rust", "worker_limit": 2}),
                        ("prepared", {"catalog_present": False, "mode": "auto", "node_policy": "retain"}),
                        ("effects", {"requested": "legacy"})):
        candidate = copy.deepcopy(PROFILE)
        candidate[path] = value
        with pytest.raises(ValueError):
            full.validate_startup(startup(candidate))
    changed = copy.deepcopy(PROFILE)
    changed["profile"]["features"]["prepared_content"] = "raw"
    with pytest.raises(ValueError):
        full.validate_startup(startup(changed))


@pytest.mark.parametrize("text", ["", "ordinary game opened\n", startup() + startup()])
def test_missing_or_duplicate_startup_receipt_is_not_proof(text):
    with pytest.raises(ValueError):
        full.validate_startup(text)


def test_final_pck_checks_all_qualities_exact_identities_and_isolated_jobs(context, monkeypatch):
    build, rows, _ = context
    reports = []
    before = build.stage_inventory()
    monkeypatch.setattr(build, "run_engine", final_engine(build, rows, reports))
    build.check_final_package()
    assert not guard_editor(build).exists()
    assert build.stage_inventory() == before
    assert [job["texture_quality"] for job in reports] == ["full", "half", "quarter"]
    assert len(build.receipt["prepared_checks"]) == 3
    assert build.receipt["status"] == "verified_before_signing"
    with pytest.raises(ValueError, match="incomplete"):
        build.proof()  # Final PCK success cannot substitute for ordinary startup.
    log = build.root / "ordinary.log"
    log.write_text(startup())
    build.record_startup(log)
    proof = build.proof()
    assert proof["catalog_sha256"] == full.native.sha256(build.project / "prepared-content/index.json")
    assert proof["receipt_sha256"] == full.native.sha256(build.root / "full-optimizations.json")
    assert proof["commit"] == COMMIT and proof["platform"] == "windows"


@pytest.mark.parametrize("problem", ["no-export", "wrong-coverage", "failed-report", "wrong-catalog", "missing-entry", "extra-entry", "stage-write",
    "reported-failures", "duplicate-entry", "wrong-quality", "wrong-stage"])
def test_final_pck_failure_never_makes_a_publishable_proof(context, monkeypatch, problem):
    build, rows, _ = context
    if problem == "no-export":
        build.receipt.pop("prepared_export")
    elif problem == "wrong-coverage":
        build.receipt["prepared"]["required_entries"]["full"] = []
    def mutation(report, owner):
        if problem == "failed-report":
            report["status"] = "failed"
        elif problem == "wrong-catalog":
            report["catalog_sha256"] = "f" * 64
        elif problem == "missing-entry":
            report["entry_ids"].pop()
        elif problem == "extra-entry":
            report["entry_ids"].append("f" * 64)
        elif problem == "stage-write":
            (owner.stage / "app/unexpected-user-file").write_bytes(b"must not ship")
        elif problem == "reported-failures":
            report["failures"] = ["actual resource mismatch"]
        elif problem == "duplicate-entry":
            report["entry_ids"].append(report["entry_ids"][0])
        elif problem == "wrong-quality":
            report["texture_quality"] = "different-job"
        elif problem == "wrong-stage":
            report["project_root"] = str(owner.project)
    monkeypatch.setattr(build, "run_engine", final_engine(build, rows, [], mutation=mutation))
    with pytest.raises(ValueError):
        build.check_final_package()
    assert not guard_editor(build).exists()
    assert build.receipt["status"] != "verified_before_signing"
    with pytest.raises(ValueError):
        build.proof()


def test_existing_guard_editor_is_preserved_and_never_launched(context, monkeypatch):
    build, _, _ = context
    editor = guard_editor(build)
    editor.write_bytes(b"not owned by this invocation")
    monkeypatch.setattr(build, "run_engine", lambda *a, **k: pytest.fail("existing editor must not launch"))
    with pytest.raises(ValueError, match="already contains"):
        build.check_final_package()
    assert editor.read_bytes() == b"not owned by this invocation"
    assert build.receipt["status"] != "verified_before_signing"


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_cross_volume_guard_copy_is_budgeted_verified_and_removed(context, monkeypatch, platform):
    build, rows, budget = context
    build.platform = platform
    actual = observation(platform)
    build.graphics.update(platform=platform, rendering_method=actual["rendering_method"],
                          rendering_driver=actual["rendering_driver"])
    copies = []
    original = full.shutil.copy2
    def copy(source, target):
        assert any("before temporary final-PCK editor" in phase and size == build.godot.stat().st_size
                   for phase, size in budget)
        assert Path(source) == build.godot and Path(target) == guard_editor(build)
        copies.append((source, target))
        return original(source, target)
    monkeypatch.setattr(full.os, "link", lambda *a, **k: (_ for _ in ()).throw(OSError("cross-volume fixture")))
    monkeypatch.setattr(full.shutil, "copy2", copy)
    monkeypatch.setattr(build, "run_engine", final_engine(build, rows, []))
    build.check_final_package()
    assert len(copies) == 1
    assert not guard_editor(build).exists()
    assert build.godot.read_bytes() == b"verified-editor-fixture"


def test_guard_copy_reservation_failure_prevents_materialization(context, monkeypatch):
    build, _, _ = context
    def exhausted(phase, upcoming_bytes):
        assert "before temporary final-PCK editor" in phase
        assert upcoming_bytes == build.godot.stat().st_size
        raise ValueError("fixture copy budget exhausted")
    build.budget_callback = exhausted
    monkeypatch.setattr(full.os, "link", lambda *a, **k: pytest.fail("budget refusal must precede linking"))
    monkeypatch.setattr(full.shutil, "copy2", lambda *a, **k: pytest.fail("budget refusal must precede copying"))
    with pytest.raises(ValueError, match="budget exhausted"):
        build.check_final_package()
    assert not guard_editor(build).exists()


def test_corrupt_temporary_guard_copy_never_launches_and_is_removed(context, monkeypatch):
    build, _, _ = context
    monkeypatch.setattr(full.os, "link", lambda *a, **k: (_ for _ in ()).throw(OSError("cross-volume fixture")))
    monkeypatch.setattr(full.shutil, "copy2", lambda source, target: Path(target).write_bytes(b"changed editor bytes"))
    monkeypatch.setattr(build, "run_engine", lambda *a, **k: pytest.fail("unverified editor must not launch"))
    with pytest.raises(ValueError, match="differs from verified tool"):
        build.check_final_package()
    assert not guard_editor(build).exists()
    assert build.godot.read_bytes() == b"verified-editor-fixture"


def test_final_engine_failure_cleans_temporary_editor_before_propagating(context, monkeypatch):
    build, _, _ = context
    def failed(argv, *args, **kwargs):
        assert Path(argv[0]) == guard_editor(build) and guard_editor(build).is_file()
        raise ValueError("fixture final-PCK engine failure")
    monkeypatch.setattr(build, "run_engine", failed)
    with pytest.raises(ValueError, match="final-PCK engine failure"):
        build.check_final_package()
    assert not guard_editor(build).exists()
    assert build.receipt["status"] != "verified_before_signing"


def test_native_payload_is_verified_before_staging_and_source_scan_is_guarded(context, monkeypatch):
    build, _, _ = context
    events = []
    payload = build.root / "fixture-payload"
    payload.mkdir()
    def prepare(repository, commit, platform, cache, out, work, check):
        assert repository == build.project.parent and commit == COMMIT and platform == "windows"
        events.append("verified-native")
        return {"payload": str(payload), "source": {"source_digest": "c" * 64}}
    def stage(source, repository, project, platform):
        assert events == ["verified-native"]
        assert source == payload and repository == build.project.parent
        events.append("stage-native")
        (project / "bin/client_runtime").mkdir(parents=True)
    monkeypatch.setattr(full.release_native_runtime, "prepare_runtime", prepare)
    monkeypatch.setattr(full.native, "stage_payload", stage)
    assert build.prepare_native() == payload
    assert events == ["verified-native", "stage-native"]
    assert (build.project / "bin/client_runtime/.gdignore").read_bytes() == b""


def test_failed_native_verification_never_stages_or_reaches_proof(context, monkeypatch):
    build, _, _ = context
    build.receipt.pop("native")
    monkeypatch.setattr(full.release_native_runtime, "prepare_runtime", lambda *a, **k: (_ for _ in ()).throw(ValueError("native identity mismatch")))
    monkeypatch.setattr(full.native, "stage_payload", lambda *a, **k: pytest.fail("failed payload must not be staged"))
    with pytest.raises(ValueError, match="native identity"):
        build.prepare_native()
    assert "native" not in build.receipt
    with pytest.raises(ValueError):
        build.proof()


def native_completion(argv):
    script = str(argv[argv.index("--script") + 1]).rsplit("/", 1)[-1]
    if script == "test_rust_mounted_upper.gd":
        mount = next(str(value).removeprefix("--mount=") for value in argv if str(value).startswith("--mount="))
        return "RUST_MOUNTED_PROFILE " + mount + "\nRUST_MOUNTED_POSE_CHECKS 42 failures=0\n"
    return {"test_optimization_profile.gd": "optimization profile: PASS\n",
            "test_remote_presentation.gd": "remote presentation tests: PASS\n",
            "test_native_resource_admission.gd": "native resource admission tests: PASS\n",
            "test_rust_spell_flights.gd": "Rust spell flights: PASS GD geometry cases=150 C++ cases=120\n"}[script]


def test_native_checks_require_actual_contract_and_all_five_supported_mounts(context, monkeypatch):
    build, _, _ = context
    calls = []
    def run(argv, *args, **kwargs):
        calls.append(argv)
        return native_completion(argv)
    monkeypatch.setattr(build, "run_engine", run)
    build.check_native()
    assert len(calls) == 9 and len(build.receipt["native_checks"]) == 9
    mounts = [str(value).removeprefix("--mount=") for argv in calls for value in argv if str(value).startswith("--mount=")]
    assert mounts == ["moor_pony", "golden_plains_horse", "crystalback_tortoise", "rabbit", "jadefeather_raptor"]
    assert all("--optimization-profile=legacy" in argv for argv in calls[1:])


@pytest.mark.parametrize("output", ["", "clean startup only\n", "SKIP actual work\n"])
def test_native_zero_exit_without_completion_never_proves_checks(context, monkeypatch, output):
    build, _, _ = context
    monkeypatch.setattr(build, "run_engine", lambda *args, **kwargs: output)
    with pytest.raises(ValueError):
        build.check_native()
    assert not build.receipt["native_checks"]


def test_mounted_positive_completion_requires_nonzero_work(context, monkeypatch):
    build, _, _ = context
    def run(argv, *args, **kwargs):
        return native_completion(argv).replace("CHECKS 42", "CHECKS 0")
    monkeypatch.setattr(build, "run_engine", run)
    with pytest.raises(ValueError, match="mounted"):
        build.check_native()
    assert all(not row["name"].startswith("upper-") for row in build.receipt["native_checks"])


def test_cook_proof_is_checked_before_accepting_generated_catalog(context, monkeypatch):
    build, _, _ = context
    calls = []
    monkeypatch.setattr(build, "run_engine", lambda *a, **k: calls.append(a))
    def prepare(project, stage, **kwargs):
        kwargs["run_cook"]({"argv": [build.godot, "--script", "cook.gd"], "environment": {"FIXTURE": "yes"},
                            "log": build.root / "cook.log", "timeout_seconds": 300})
        return {"catalog": str(build.project / "prepared-content/index.json"),
                "variants": [{"renderer": observation()}]}
    monkeypatch.setattr(full.release_prepared_content, "prepare_generation", prepare)
    assert build.prepare_content() == build.project / "prepared-content/index.json"
    assert len(calls) == 1
    assert build.receipt["prepared"]["graphics"][0]["status"] == "verified"


@pytest.mark.parametrize("failure", ["generation", "wrong-adapter", "missing-buffer"])
def test_cook_failure_cannot_be_recorded_as_accepted(context, monkeypatch, failure):
    build, _, _ = context
    build.receipt.pop("prepared")
    def prepare(*args, **kwargs):
        if failure == "generation":
            raise ValueError("failed fresh cook")
        value = observation()
        value["adapter_name" if failure == "wrong-adapter" else "resource_buffer_probe"] = "Hardware GPU" if failure == "wrong-adapter" else False
        return {"catalog": "must-not-return", "variants": [{"renderer": value}]}
    monkeypatch.setattr(full.release_prepared_content, "prepare_generation", prepare)
    with pytest.raises(ValueError):
        build.prepare_content()
    assert "prepared" not in build.receipt
    with pytest.raises(ValueError):
        build.proof()


def test_package_call_order_dominates_the_first_signing_and_upload_boundary():
    """Guard the actual public entrypoint, not a test-only copy of its pipeline."""
    source = Path(full.__file__).with_name("package_client.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_main")
    public = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    assert any(isinstance(node, ast.Call) and ast.unparse(node.func) == "_main" for node in ast.walk(public))
    calls = {}
    for node in ast.walk(main):
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            calls.setdefault(name, []).append(node.lineno)
    sequence = ["optimization.prepare_native", "optimization.check_native", "optimization.prepare_content",
                "optimization.record_export", "optimization.record_startup", "optimization.check_final_package",
                "optimization.proof", "client_release.publish_artifacts"]
    assert all(name in calls for name in sequence)
    assert [min(calls[name]) for name in sequence] == sorted(min(calls[name]) for name in sequence)
    # Archive/install paths are downstream of the same pre-publication gates.
    for name in ("make_zip", "make_tarball", "make_online_installer", "make_installer"):
        assert min(calls["optimization.proof"]) < min(calls[name])


@pytest.mark.parametrize("field,value", [("status", "pending"), ("commit", "b" * 40),
    ("platform", "linux"), ("entries", 0), ("entries", True), ("receipt_sha256", "not-sha"),
    ("native_source_digest", ""), ("coverage_sha256", "f" * 63)])
def test_unverified_or_wrong_identity_proof_is_rejected(field, value):
    proof = {"policy": full.POLICY, "status": "verified_before_signing", "commit": COMMIT,
             "platform": "windows", "features": dict(full.FEATURES), "entries": 6,
             **{name: "c" * 64 for name in ("receipt_sha256", "native_source_digest", "catalog_sha256", "coverage_sha256")}}
    proof[field] = value
    with pytest.raises(ValueError):
        full.validate_proof(proof, COMMIT, "windows")


def test_engine_failure_stops_only_owned_child_and_filters_secrets(context, monkeypatch):
    build, _, _ = context
    stopped, environments = [], []
    class Child:
        pid, returncode = 12345, None
        def poll(self):
            return self.returncode
        def wait(self, timeout):
            raise subprocess.TimeoutExpired("fixture-owned", timeout)
    child = Child()
    def popen(command, **kwargs):
        environments.append(kwargs["env"])
        assert "--rendering-driver" in command and "d3d12" in command
        return child
    monkeypatch.setenv("CLIENT_UPDATE_SIGNING_KEY", "fixture-private-key")
    monkeypatch.setenv("GITHUB_TOKEN", "fixture-token")
    monkeypatch.setenv("RABBITLANDS_REMOTE_PRESENTATION", "inherited-setting")
    monkeypatch.setattr(full.subprocess, "Popen", popen)
    monkeypatch.setattr(full, "stop_owned", lambda owner: stopped.append(owner))
    monkeypatch.setattr(full.time, "monotonic", iter((0, 500)).__next__)
    with pytest.raises(ValueError, match="timed out"):
        build.run_engine([build.godot, "--script", "fixture.gd"], {"RABBITLANDS_CLIENT_RUNTIME": "rust"},
                         build.root / "owned.log", 1)
    assert stopped == [child]
    assert all(key not in environments[0] for key in ("CLIENT_UPDATE_SIGNING_KEY", "GITHUB_TOKEN", "RABBITLANDS_REMOTE_PRESENTATION"))
    assert environments[0]["RABBITLANDS_CLIENT_RUNTIME"] == "rust"


@pytest.mark.parametrize("bad_log", ["ERROR: render failure\n", "SCRIPT ERROR: failed\n", "ObjectDB instances leaked at exit\n"])
def test_exit_zero_with_engine_or_shutdown_error_rejects(context, monkeypatch, bad_log):
    build, _, _ = context
    class Child:
        pid, returncode = 12345, 0
        def poll(self):
            return 0
    def popen(command, **kwargs):
        Path(command[command.index("--log-file") + 1]).write_text(bad_log)
        return Child()
    monkeypatch.setattr(full.subprocess, "Popen", popen)
    with pytest.raises(ValueError, match="diagnostic"):
        build.run_engine([build.godot, "--script", "fixture.gd"], {}, build.root / "error.log", 30)


def test_timeout_cleanup_targets_the_owned_process_handle_only(monkeypatch):
    actions = []
    class Child:
        pid, code = 67890, None
        def poll(self):
            return self.code
        def terminate(self):
            actions.append(("terminate", self.pid))
        def wait(self, timeout):
            if timeout == 5:
                raise subprocess.TimeoutExpired("owned-fixture", timeout)
            self.code = 0
            actions.append(("wait", self.pid))
        def kill(self):
            actions.append(("kill", self.pid))
    child = Child()
    with monkeypatch.context() as patch:
        patch.setattr(full.os, "name", "nt")
        full.stop_owned(child)
    assert actions == [("terminate", 67890), ("kill", 67890), ("wait", 67890)]
