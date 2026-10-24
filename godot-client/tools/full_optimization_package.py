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
                 check_budget=None, *, software_gpu_index=None, native_bootstrap=None):
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
        self.native_bootstrap = native_bootstrap
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
        if self.native_bootstrap is not None:
            receipt = release_native_runtime.prepare_from_prewarm(self.project.parent, self.commit, self.platform,
                self.cache, self.root / "runtime-payload", self.native_bootstrap, self.check_budget)
        else:
            receipt = release_native_runtime.prepare_runtime(self.project.parent, self.commit, self.platform,
                # Keep MSVC scratch outside the long per-commit log path.
                self.cache, self.root / "runtime-payload", self.cache.parent / ("work-" + self.platform), self.check_budget)
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

    def retire_intermediate_pck(self, installed):
        """The first pack's cook readers have exited; reserve a fresh final pack."""
        pack = self.stage / "app/RabbitLands.pck"
        catalog = self.project / "prepared-content/index.json"
        cook_receipt = self.receipt.get("prepared", {})
        require((self.stage / ".eloria-package").read_text().strip() == self.commit,
                "intermediate pack is outside this selected stage")
        require(cook_receipt.get("status") == "cooked_pending_final_export"
                and cook_receipt.get("selected_source_inputs_restored") is True
                and not (self.project / prepared.RUNTIME_IMPORT_MARKER).exists(),
                "intermediate pack still belongs to an unfinished runtime cook")
        require(installed.get("index_sha256") == native.sha256(catalog)
                and installed.get("index_sha256") == cook_receipt.get("index_sha256"),
                "installed prepared inputs differ before final export")
        require(pack.is_file() and not pack.is_symlink() and pack.resolve() == pack
                and "intermediate_export" not in self.receipt,
                "intermediate pack must be a fresh owned regular file")
        prepared_bytes = sum(path.stat().st_size for path in catalog.parent.rglob("*") if path.is_file())
        # Ordinary content is unchanged. Add the entire installed native tree,
        # catalog/path overhead and a conservative fixed metadata allowance.
        allocation = pack.stat().st_size + prepared_bytes + 64 * 1024**2
        self.receipt["intermediate_export"] = {"path": str(pack), "sha256": native.sha256(pack),
            "bytes": pack.stat().st_size, "final_export_reservation_bytes": allocation,
            "status": "verified_before_retirement"}
        self.save()
        self.check_budget("before intermediate PCK retirement")
        pack.unlink()
        self.receipt["intermediate_export"]["status"] = "retired_before_final_export"
        self.save()
        self.check_budget("before final prepared export", allocation)

    def retire_prepared_sources(self):
        """Release cook scratch only after the final exported runtime passes."""
        # The runner imports build_release before package_client. Keep this
        # runner-only helper lazy so the standalone packager can import first.
        from runner_retirement import regular_tree
        proof = self.proof()
        source = self.project / "prepared-content"
        generated = self.root / "prepared-work/generation/prepared-content"
        receipt_path = self.root / "prepared-source-retirement.json"
        require(not receipt_path.exists()
                and (self.stage / ".eloria-package").read_text().strip() == self.commit
                and Path(self.receipt["prepared"]["catalog"]).resolve() == generated / "index.json"
                and self.receipt["prepared"].get("selected_source_inputs_restored") is True,
                "prepared retirement requires this build's completed owned generation")
        for directory in (source, generated):
            require(directory.is_dir() and regular_tree(directory) == directory
                    and native.sha256(directory / "index.json") == proof["catalog_sha256"],
                    "prepared source retirement input differs from final verified catalog")
        pack = self.stage / "app/RabbitLands.pck"
        pack_hash = native.sha256(pack)
        rows = {label: {path.relative_to(directory).as_posix(): {"size": path.stat().st_size,
                            "sha256": native.sha256(path)}
                        for path in sorted(directory.rglob("*")) if path.is_file()}
                for label, directory in (("installed", source), ("generation", generated))}
        write_json(receipt_path, {"schema": 1, "status": "verified_before_retirement",
            "commit": self.commit, "catalog_sha256": proof["catalog_sha256"],
            "final_pck_sha256": pack_hash, "proof": proof, "files": rows})
        self.check_budget("prepared sources verified after final PCK qualification")
        shutil.rmtree(source)
        shutil.rmtree(generated)
        require(native.sha256(pack) == pack_hash and self.proof() == proof,
                "qualified package/proof changed during source retirement")
        retirement = json.loads(receipt_path.read_text())
        retirement["status"] = "retired_after_final_pck_and_ordinary_startup_checks"
        write_json(receipt_path, retirement)
        self.check_budget("prepared source scratch retired before archives and installer")

    def check_final_package(self):
        # Official release templates disable external --script/path overrides.
        # Run the verified editor beside the final PCK so exported loose-asset
        # resolution uses the same physical app directory as the shipped game.
        # The editor is temporary and must be gone before signing/packaging.
        before = self.stage_inventory()
        editor = self.stage / "app" / ("RabbitLands-release-guard-editor.exe" if self.platform == "windows"
                                       else "RabbitLands-release-guard-editor.x86_64")
        require(not editor.exists(), "final stage already contains a release guard editor")
        self.check_budget("before temporary final-PCK editor", self.godot.stat().st_size)
        try:
            try:
                os.link(self.godot, editor)
            except OSError:
                # Cross-volume builds still charge the complete copy first.
                shutil.copy2(self.godot, editor)
            require(native.sha256(editor) == native.sha256(self.godot), "temporary guard editor differs from verified tool")
            self._check_final_package(editor)
        finally:
            editor.unlink(missing_ok=True)
        require(before == self.stage_inventory(), "optimization runtime checks wrote into the final package")
        self.receipt["status"] = "verified_before_signing"
        self.save()

    def stage_inventory(self):
        return {str(path.relative_to(self.stage)): (path.stat().st_size, path.stat().st_mtime_ns)
                for path in self.stage.rglob("*") if path.is_file()}

    def _check_final_package(self, editor):
        index = self.project / "prepared-content/index.json"
        catalog = json.loads(index.read_text(encoding="utf-8"))
        require(self.receipt.get("prepared_export", {}).get("export"), "final PCK readback must precede runtime checks")
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
            self.run_engine([editor, "--main-pack", self.stage / "app/RabbitLands.pck",
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
