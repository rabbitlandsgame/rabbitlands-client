"""Fail-closed desktop optimization assembly before release signing/upload."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import client_runtime_package as native
import prepared_content_package as prepared
import release_native_runtime
import release_prepared_content
import release_software_graphics as graphics

POLICY = "rl-full-optimization-package-v1"
FEATURES = dict(client_runtime="rust", remote_presentation="rust", rust_effects="heat_bolt",
                resource_admission="rust", prepared_content="auto", prepared_node_policy="lazy-source-v1")
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ERROR = re.compile(r"(?m)^(?:USER )?(?:SCRIPT ERROR:|SHADER ERROR:|ERROR:|FATAL(?: ERROR)?:)|"
                   r"ObjectDB instances (?:were )?leaked|RID allocations.*leaked|"
                   r"Resources still in use at exit|Pages in use exist at exit|Leaked instance")


def require(value, message):
    if not value:
        raise ValueError(message)


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def clean_environment(base=None):
    result = dict(os.environ if base is None else base)
    for key in list(result):
        if key.startswith(("RABBITLANDS_", "ELORIA_NATIVE_", "ELORIA_CROWD_", "ELORIA_LOOK")) \
                or key in {"GH_TOKEN", "GITHUB_TOKEN", "CLIENT_UPDATE_SIGNING_KEY",
                           "ACTIONS_ID_TOKEN_REQUEST_TOKEN"}:
            result.pop(key)
    return result


def validate_startup(text):
    lines = [line.removeprefix("RABBITLANDS_OPTIMIZATION_STARTUP ") for line in text.splitlines()
             if line.startswith("RABBITLANDS_OPTIMIZATION_STARTUP ")]
    require(len(lines) == 1, "ordinary final package must emit exactly one optimization startup receipt")
    value = json.loads(lines[0])
    require(value["profile"]["features"] == FEATURES, "ordinary release did not select all six human-testing defaults")
    require(value["runtime"]["mode"] == "rust" and value["runtime"]["native_available"] is True,
            "ordinary final package silently fell back from its native runtime")
    require(value["remote"]["backend"] == "rust", "ordinary final package did not activate native remote presentation")
    require(value["admission"]["mode"] == "rust" and value["admission"]["worker_limit"] == 1,
            "ordinary final package did not activate bounded native resource admission")
    require(value["prepared"] == {"catalog_present": True, "mode": "auto", "node_policy": "lazy-source-v1"},
            "ordinary final package lacks its prepared catalog/default policy")
    require(value["effects"]["requested"] == "heat_bolt", "ordinary final package did not select Rust heat flights")
    # No spell has been cast at login. Actual compiled spell lifecycle and all
    # five supported mounted profiles are checked separately against the source.
    return value


def validate_proof(proof, commit, platform):
    require(isinstance(proof, dict) and proof.get("policy") == POLICY
            and proof.get("status") == "verified_before_signing" and proof.get("commit") == commit
            and proof.get("platform") == platform and proof.get("features") == FEATURES,
            "release lacks verified full optimization proof for " + platform)
    for field in ("receipt_sha256", "native_source_digest", "catalog_sha256", "coverage_sha256"):
        require(re.fullmatch(r"[0-9a-f]{64}", str(proof.get(field, ""))), "invalid optimization proof " + field)
    require(type(proof.get("entries")) is int and proof["entries"] > 0, "optimization proof has no prepared entries")
    return proof


def stop_owned(child):
    if child.poll() is None:
        if os.name == "nt":
            child.terminate()  # Godot has threads, not descendant compiler processes.
        else:
            os.killpg(child.pid, signal.SIGTERM)  # Includes only our xvfb-run session.
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                child.kill()
            else:
                os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=10)


class FullOptimizationBuild:
    def __init__(self, project, stage, godot, platform, commit, work_root, native_cache,
                 check_budget=None, *, software_gpu_index=0):
        self.project, self.stage, self.godot = map(lambda value: Path(value).resolve(), (project, stage, godot))
        self.platform, self.commit = platform, commit
        self.root, self.cache = Path(work_root).resolve(), Path(native_cache).resolve()
        require(platform in {"windows", "linux"}, "full optimization releases require native Windows or Linux")
        require(not self.root.exists(), "optimization work directory must be fresh")
        require(not self.root.is_relative_to(self.project) and not self.root.is_relative_to(self.stage),
                "optimization work must be outside source and final stage")
        self.root.mkdir(parents=True)
        self.receipt = {"schema": 1, "policy": POLICY, "status": "incomplete", "commit": commit,
                        "platform": platform, "features": FEATURES, "native_checks": [], "prepared_checks": []}
        self.budget_callback = check_budget
        self.graphics = graphics.prepare_graphics(platform, self.godot.parent, self.godot.parent,
                                                  self.check_budget, gpu_index=software_gpu_index)
        self.save()

    def check_budget(self, phase, upcoming_bytes=0):
        if self.budget_callback is not None:
            self.budget_callback("optimizations: " + phase, upcoming_bytes)
        else:
            require(shutil.disk_usage(self.root).free >= 2_000_000_000 + upcoming_bytes,
                    "optimization build must preserve its disk reserve")

    def save(self):
        write_json(self.root / "full-optimizations.json", self.receipt)

    def prepare_native(self):
        receipt = release_native_runtime.prepare_runtime(self.project.parent, self.commit, self.platform,
            self.cache, self.root / "runtime-payload", self.root / "native-work", self.check_budget)
        self.receipt["native"] = receipt
        payload = Path(receipt["payload"])
        native.stage_payload(payload, self.project.parent, self.project, self.platform)
        (self.project / "bin/client_runtime/.gdignore").write_text("", encoding="utf-8")
        self.save()
        return payload

    def run_engine(self, argv, environment, log, timeout_seconds, *, rendered=True):
        require(1 <= timeout_seconds <= 3600, "bounded owned engine timeout required")
        log = Path(log)
        log.parent.mkdir(parents=True, exist_ok=True)
        require(not log.exists(), "engine evidence log must be fresh")
        command = [str(value) for value in argv]
        position = command.index("--") if "--" in command else len(command)
        command[position:position] = ["--log-file", str(log)]
        env = clean_environment()
        env.update(environment)
        if rendered:
            command = graphics.cook_command(self.graphics, command)
            env = graphics.child_environment(self.graphics, env)
        launch = log.with_suffix(".launch.log")
        started = time.monotonic()
        with launch.open("x", encoding="utf-8") as stream:
            working_directory = self.stage / "app" if (self.stage / "app").is_dir() else self.project
            child = subprocess.Popen(command, env=env, cwd=working_directory, stdout=stream,
                stderr=subprocess.STDOUT, start_new_session=os.name != "nt")
            try:
                while child.poll() is None:
                    require(time.monotonic() - started <= timeout_seconds, "owned optimization check timed out: " + log.name)
                    self.check_budget("running " + log.name)
                    require(sum(path.stat().st_size for path in (log, launch) if path.exists()) <= 128 << 20,
                            "owned optimization check exceeded its diagnostic limit")
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                require(child.returncode == 0, "owned optimization check failed: " + log.name)
            finally:
                stop_owned(child)
        texts = [path.read_text(encoding="utf-8-sig", errors="replace") for path in (log, launch) if path.is_file()]
        require(texts, "owned optimization check produced no diagnostics")
        for text in texts:
            require(ERROR.search(ANSI.sub("", text)) is None, "engine/script/leak diagnostic in " + log.name)
        self.check_budget("completed " + log.name)
        return texts[0]

    def user_environment(self, name):
        root = self.root / "users" / name
        root.mkdir(parents=True, exist_ok=False)
        return {key: str(root) for key in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME")}

    def check_native(self):
        checks = [("profile", "test_optimization_profile.gd", []),
            ("remote", "test_remote_presentation.gd", ["--expect-native", "--optimization-profile=legacy"]),
            ("admission", "test_native_resource_admission.gd", ["--optimization-profile=legacy"]),
            ("spell", "test_rust_spell_flights.gd", ["--expect-native", "--optimization-profile=legacy"])]
        checks += [("upper-" + mount, "test_rust_mounted_upper.gd", ["--mount=" + mount, "--optimization-profile=legacy"])
                   for mount in ("moor_pony", "golden_plains_horse", "crystalback_tortoise", "rabbit", "jadefeather_raptor")]
        for name, script, user_args in checks:
            log = self.root / "native-checks" / (name + ".log")
            text = self.run_engine([self.godot, "--path", self.project, "--script", "res://tests/" + script,
                                    "--", *user_args], self.user_environment(name), log, 300)
            require("SKIP" not in text, "native release qualification skipped actual work: " + name)
            markers = {"profile": "optimization profile: PASS", "remote": "remote presentation tests: PASS",
                       "admission": "native resource admission tests: PASS", "spell": "Rust spell flights: PASS"}
            if name.startswith("upper-"):
                require("RUST_MOUNTED_PROFILE " + name.removeprefix("upper-") in text
                        and re.search(r"(?m)^RUST_MOUNTED_POSE_CHECKS [1-9][0-9]* failures=0\s*$", text),
                        "native mounted check omitted positive completion: " + name)
            else:
                require(markers[name] in text, "native check omitted positive completion: " + name)
            self.receipt["native_checks"].append({"name": name, "log": str(log), "exit": 0,
                "script_sha256": native.sha256(self.project / "tests" / script)})
            self.save()

    def prepare_content(self):
        def cook(invocation):
            self.run_engine(invocation["argv"], invocation["environment"], invocation["log"], invocation["timeout_seconds"])
        result = release_prepared_content.prepare_generation(self.project, self.stage,
            platform=self.platform, godot=self.godot, run_cook=cook, check_budget=self.check_budget,
            work_root=self.root / "prepared-work")
        result["graphics"] = [graphics.validate_observation(self.graphics, row["renderer"]) for row in result["variants"]]
        self.receipt["prepared"] = result
        self.save()
        return Path(result["catalog"])

    def record_export(self, receipt):
        receipt["catalog_sha256"] = native.sha256(self.project / "prepared-content/index.json")
        self.receipt["prepared_export"] = receipt
        self.save()

    def check_final_package(self):
        index = self.project / "prepared-content/index.json"
        catalog = json.loads(index.read_text(encoding="utf-8"))
        require(self.receipt.get("prepared_export", {}).get("export"), "final PCK readback must precede runtime checks")
        before = {str(path.relative_to(self.stage)): (path.stat().st_size, path.stat().st_mtime_ns)
                  for path in self.stage.rglob("*") if path.is_file()}
        for quality, required in self.receipt["prepared"]["required_entries"].items():
            selected = [row for row in catalog["entries"] if row["texture_skip"] == ("full", "half", "quarter").index(quality)]
            require({(row["kind"], row["source"], row.get("node_policy", "retain")) for row in selected}
                    == {tuple(row) for row in required}, "final catalog quality coverage differs from the committed plan")
            environment = self.user_environment("prepared-" + quality)
            user_base = Path(environment["APPDATA"])
            expected_user = user_base / ("Godot" if self.platform == "windows" else "godot") / "app_userdata/Eloria"
            job = {"schema_version": 1, "platform": self.platform, "expected_stage_root": str(self.stage),
                "expected_stage_app": str(self.stage / "app"), "catalog_sha256": native.sha256(index),
                "expected_catalog_entries": len(catalog["entries"]), "texture_quality": quality,
                "expected_entries": len(selected), "expected_user_directory": str(expected_user),
                "required_entries": [{**{key: row[key] for key in ("kind", "source", "entry_id", "source_digest", "texture_token")},
                                      "node_policy": row.get("node_policy", "retain")}
                                     for row in selected], "report": str(self.root / ("prepared-check-" + quality + ".json"))}
            path = self.root / ("prepared-check-" + quality + "-job.json")
            write_json(path, job)
            log = self.root / "prepared-checks" / (quality + ".log")
            self.run_engine([self.godot, "--path", self.stage / "app", "--main-pack", self.stage / "app/RabbitLands.pck",
                "--script", self.project / "tools/check_prepared_release.gd", "--", path],
                environment, log, 600)
            evidence = json.loads(Path(job["report"]).read_text())
            graphics.validate_observation(self.graphics, evidence.get("graphics"))
            ids = evidence.get("entry_ids", [])
            def same_path(value, expected):
                if not isinstance(value, str):
                    return False
                return Path(value).resolve() == Path(expected).resolve()
            require(evidence.get("schema_version") == 1 and evidence.get("status") == "pass"
                    and evidence.get("failures") == [] and evidence.get("texture_quality") == quality
                    and same_path(evidence.get("stage_app"), self.stage / "app")
                    and same_path(evidence.get("project_root"), self.stage / "app")
                    and evidence.get("catalog_entries") == len(catalog["entries"])
                    and evidence.get("catalog_sha256") == job["catalog_sha256"]
                    and isinstance(ids, list) and len(ids) == len(selected)
                    and set(ids) == {row["entry_id"] for row in selected}
                    and evidence.get("nodes_before") == evidence.get("nodes_after"),
                    "actual final PCK acquisition did not cover every exact prepared entry")
            self.receipt["prepared_checks"].append(evidence)
            self.save()
        after = {str(path.relative_to(self.stage)): (path.stat().st_size, path.stat().st_mtime_ns)
                 for path in self.stage.rglob("*") if path.is_file()}
        require(before == after, "optimization runtime checks wrote into the final package")
        self.receipt["status"] = "verified_before_signing"
        self.save()

    def record_startup(self, log):
        self.receipt["ordinary_startup"] = validate_startup(Path(log).read_text(encoding="utf-8-sig"))
        self.save()

    def proof(self):
        require(self.receipt["status"] == "verified_before_signing" and self.receipt.get("ordinary_startup"),
                "full optimization package has incomplete pre-publication proof")
        value = {"policy": POLICY, "status": self.receipt["status"], "commit": self.commit,
                "platform": self.platform, "receipt_sha256": native.sha256(self.root / "full-optimizations.json"),
                "native_source_digest": self.receipt["native"]["source"]["source_digest"],
                "catalog_sha256": self.receipt["prepared_export"]["catalog_sha256"],
                "coverage_sha256": hashlib.sha256(json.dumps(self.receipt["prepared"]["required_entries"],
                    sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                "entries": self.receipt["prepared"]["entries"], "features": FEATURES}
        return validate_proof(value, self.commit, self.platform)
