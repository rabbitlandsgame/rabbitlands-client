"""Evidence validation, identity capture and process-owned benchmark locking.

This module never starts Godot. Keep validation usable from small Python tests.
Identity capture runs outside timed engine samples and records its exact scope.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import socket
import tempfile
import time
from typing import Any


class EvidenceError(ValueError):
    pass


OLD_CELLS = [name for count in (100, 160, 200, 300)
             for name in (f"s3-market-{count}", f"s2-invasion-{count}")]
OLD_CELLS += ["combat-100", "combat-160", "aoi-160", "empty"]
PHASE1_CELLS = ["s3-market-160", "s2-invasion-160", "mixed-mounted-160",
                "combat-160", "empty", "traversal-southern-cold", "traversal-southern-warm"]
ALL_CELLS = OLD_CELLS + ["mixed-mounted-160", "authored-herd",
                         "traversal-southern-cold", "traversal-southern-warm"]
ERROR_PATTERN = re.compile(r"SCRIPT ERROR|Parse Error|Failed to load|Error loading|ERROR:", re.I)
OVERRIDE_PREFIXES = ("ELORIA_LOOK", "ELORIA_CROWD_", "ELORIA_NATIVE_", "RABBITLANDS_CROWD_")
OVERRIDE_NAMES = {"ELORIA_VRAM_TEXTURES", "ELORIA_NO_MAP_CACHE", "ELORIA_SAFE_MODE", "RABBITLANDS_CLIENT_RUNTIME"}
PERFORMANCE_GRAPHICS = {
    "quality": "low", "appearance": "painted_ground", "fps_limit": 30,
    "render_scale": .75, "map_texture_quality": "half", "crowd_bodies": 60,
    "swaying_capes": 0, "shadows": False, "particles": True,
    "decorative_grass": False, "name_distance": 20.0,
}
RUST_MOUNT_PROFILES = frozenset({"moor_pony", "golden_plains_horse", "crystalback_tortoise",
                               "rabbit", "jadefeather_raptor"})
MIXED_MOUNT_PROFILES = RUST_MOUNT_PROFILES | {"giant_rat"}


def configure_settings_profile(args, system: str | None = None) -> None:
    """Resolve omitted arguments, rejecting overrides that would mislabel a preset."""
    profile = getattr(args, "settings_profile", "default")
    if profile not in ("default", "performance"):
        raise EvidenceError("unknown settings profile")
    if profile == "performance":
        if (platform.system() if system is None else system) != "Windows":
            raise EvidenceError("Performance settings seeding currently supports Windows only")
        for field, absent, expected in (("quality", "", "low"), ("fps_cap", None, 30),
                                        ("body_cap", None, 60)):
            value = getattr(args, field)
            if value != absent and value != expected:
                raise EvidenceError(f"Performance profile conflicts with --{field.replace('_', '-')}; requires {expected}")
            setattr(args, field, expected)
        if args.tuning:
            raise EvidenceError("Performance profile does not allow crowd tuning overrides")
    elif args.fps_cap is None:
        args.fps_cap = 60  # Preserve the existing default profile.
    cells = selected_cells(args.cells, bool(args.replay))
    if "mixed-mounted-160" in cells and args.body_cap is not None and 0 < args.body_cap < 80:
        raise EvidenceError("mixed-mounted-160 requires 80 mounted bodies; the requested body cap is below 80")


def seed_settings_profile(profile: str, client: Path, user_root: Path,
                          environment: dict[str, str], system: str | None = None) -> dict | None:
    """Write only fresh, generated preferences before Godot caches texture quality.

    Windows custom user:// uses APPDATA. Other platforms are rejected explicitly
    until their isolation and custom-directory behavior are supported and tested.
    """
    if profile == "default":
        return None
    if profile != "performance" or (platform.system() if system is None else system) != "Windows":
        raise EvidenceError("Performance settings seeding currently supports Windows only")
    root = user_root.resolve()
    appdata = environment.get("APPDATA")
    if not appdata or Path(appdata).resolve() != root:
        raise EvidenceError("Performance profile requires the fresh isolated APPDATA directory")
    # Verify the repository's declared custom path instead of assuming the
    # engine's default application-name directory or copying a user's config.
    application, section = {}, ""
    for line in (client / "project.godot").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif section == "application" and "=" in line and not line.startswith(";"):
            key, value = line.split("=", 1)
            application[key.strip()] = value.strip()
    custom = "config/custom_user_dir_name"
    if application.get("config/use_custom_user_dir") != "true" \
            or application.get(custom) != '"Godot/app_userdata/Eloria"' \
            or any(key.startswith(custom + ".") and key != custom + ".linuxbsd" for key in application):
        raise EvidenceError("Performance profile does not support this project's custom user directory settings")
    user_dir = root / "Godot/app_userdata/Eloria"
    path = user_dir / "eloria_hud.cfg"
    content = "[graphics]\n\n" + "".join(
        f"{key}={json.dumps(value, ensure_ascii=False, allow_nan=False)}\n"
        for key, value in PERFORMANCE_GRAPHICS.items())
    user_dir.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    except FileExistsError as exc:
        raise EvidenceError("settings seed already exists; no existing preferences were overwritten") from exc
    return {"profile": profile, "path": str(path), "userDataDir": str(user_dir),
            "content": content, "sha256": sha256_file(path), "bytes": path.stat().st_size,
            "scope": "generated initial settings before startup; no inherited user config"}


def finite_tree(value: Any, label: str = "report") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise EvidenceError(f"{label}: non-finite number")
    if isinstance(value, dict):
        for key, item in value.items():
            finite_tree(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            finite_tree(item, f"{label}[{index}]")


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise EvidenceError("required JSON report or manifest is missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"),
                           parse_constant=lambda _value: (_ for _ in ()).throw(
                               EvidenceError("JSON contains a non-finite number")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid JSON ({type(exc).__name__})") from exc
    if not isinstance(value, dict):
        raise EvidenceError("JSON root must be an object")
    finite_tree(value)
    return value


def selected_cells(profile: str, replay: bool = False) -> list[str]:
    if replay:
        return []  # The recording determines its map; validate exactly one replay cell later.
    profiles = {"phase4": OLD_CELLS, "quick": ["s3-market-160", "s2-invasion-160"],
                "phase1": PHASE1_CELLS, "all": ALL_CELLS}
    names = list(profiles[profile]) if profile in profiles else profile.split(",")
    if not names or any(not item or item not in ALL_CELLS for item in names):
        raise EvidenceError("unknown or empty benchmark cell selector")
    if len(set(names)) != len(names):
        raise EvidenceError("duplicate benchmark cell selector")
    return names


def _number(value: Any, label: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or value < minimum:
        raise EvidenceError(f"{label}: expected finite number >= {minimum}")
    return float(value)


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EvidenceError(f"{label}: expected integer >= {minimum}")
    return value


def _object(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label}: expected object")
    return value


def validate_startup_ack(data: dict, request: dict) -> dict:
    """Bind a small startup acknowledgement to this exact launched workload."""
    finite_tree(data)
    if type(data.get("schemaVersion")) is not int or data["schemaVersion"] != 1 \
            or data.get("benchmark") != "crowd_presentation":
        raise EvidenceError("startup acknowledgement has the wrong benchmark/schema")
    if type(data.get("pid")) is not int or data["pid"] != request["pid"]:
        raise EvidenceError("startup acknowledgement PID differs from launched process")
    if data.get("startToken") != request["start_token"] or data.get("executionMode") != request["executable_mode"]:
        raise EvidenceError("startup acknowledgement token/execution mode differs from requested workload")
    executable = data.get("executablePath")
    if not isinstance(executable, str) or not Path(executable).is_absolute() \
            or os.path.normcase(str(Path(executable).resolve())) \
            != os.path.normcase(str(Path(request["executable"]).resolve())):
        raise EvidenceError("startup acknowledgement executable differs from launched executable")
    user_dir = data.get("userDataDir")
    if not isinstance(user_dir, str) or not Path(user_dir).is_absolute() \
            or not Path(user_dir).resolve().is_relative_to(Path(request["user_root"]).resolve()):
        raise EvidenceError("startup acknowledgement user data escaped the isolated run directory")
    if request.get("settings_seed_user_dir") and os.path.normcase(str(Path(user_dir).resolve())) \
            != os.path.normcase(str(Path(request["settings_seed_user_dir"]).resolve())):
        raise EvidenceError("startup acknowledgement did not use the exact seeded user directory")
    return data


def validate_distribution(value: Any, label: str, count: int | None = None) -> dict:
    value = _object(value, label)
    n = _integer(value.get("count"), f"{label}.count", 1)
    if count is not None and n != count:
        raise EvidenceError(f"{label}: sample count differs from frames")
    ordered = [_number(value.get(key), f"{label}.{key}")
               for key in ("p5", "p50", "p95", "p99", "max")]
    if ordered != sorted(ordered):
        raise EvidenceError(f"{label}: unordered percentiles")
    if _number(value.get("mean"), f"{label}.mean") > ordered[-1] + .001:
        raise EvidenceError(f"{label}: mean exceeds maximum")
    return value


def validate_runtime(runtime: dict, request: dict, renderer: str, quality: str,
                     body_cap: int, label: str) -> dict:
    settings = _object(runtime.get("effectiveSettings"), label + ".effectiveSettings")
    backends = _object(runtime.get("activeBackends"), label + ".activeBackends")
    expected = {"quality": quality, "bodyCap": body_cap, "frameCap": request["fps_cap"],
                "renderer": renderer, "rootSize": list(request["resolution"])}
    if request.get("settings_profile") == "performance":
        expected.update(quality="low", bodyCap=60, renderScale=.75,
                        textureQuality="half", textureSkip=1, appearance="painted_ground")
    if request.get("minimap") in ("show", "hide"):
        expected["minimap"] = request["minimap"] == "show"
    for key, value in expected.items():
        if settings.get(key) != value:
            raise EvidenceError(f"{label}: effective {key} differs from requested/actual metadata")
    if _number(settings.get("renderScale"), label + ".renderScale", .01) > 1.0:
        raise EvidenceError(f"{label}: invalid render scale")
    if settings.get("textureQuality") not in ("full", "half", "quarter") \
            or settings.get("textureSkip") not in (0, 1, 2):
        raise EvidenceError(f"{label}: missing/invalid actual texture settings")
    world_size = settings.get("worldViewportSize")
    if not isinstance(world_size, list) or len(world_size) != 2:
        raise EvidenceError(f"{label}: actual world viewport size missing")
    for component in world_size:
        _integer(component, label + ".worldViewportSize", 1)
    if not isinstance(settings.get("minimap"), bool) or not isinstance(settings.get("appearance"), str):
        raise EvidenceError(f"{label}: missing actual appearance/minimap settings")
    if backends.get("nativeReducer") is not (request.get("native_reducer", "off") == "on"):
        raise EvidenceError(f"{label}: actual native reducer differs from request")
    requested_runtime = request.get("client_runtime", "legacy")
    # Older legacy checkpoints predate this optional service. Native requests
    # require its actual instantiated backend at every observed boundary.
    if "clientRuntime" in backends or requested_runtime != "legacy":
        runtime = _object(backends.get("clientRuntime"), label + ".clientRuntime")
        expected_presentation = "mixed" if requested_runtime == "rust" else "legacy"
        if runtime.get("requested") != requested_runtime or runtime.get("mode") != requested_runtime \
                or runtime.get("presentation_backend") != expected_presentation or runtime.get("mismatches") != 0:
            raise EvidenceError(f"{label}: actual client runtime differs or fell back")
        if requested_runtime in ("compare", "rust") and runtime.get("native_available") is not True:
            raise EvidenceError(f"{label}: requested Rust comparison runtime is unavailable")
    presentation = _object(backends.get("presentation"), label + ".presentation")
    requested = request.get("native_presentation", "off")
    expected_native = "0" if requested == "off" else requested
    if presentation.get("requested") != expected_native:
        raise EvidenceError(f"{label}: actual native presentation request differs")
    for key in ("nativeCapeInstances", "nativeCapeCalls", "capeFallbackCalls"):
        _integer(presentation.get(key), label + "." + key)
    for kind in ("flight", "impact"):
        stats = _object(presentation.get(kind), label + "." + kind)
        for key in ("buildAttempts", "buildSuccesses", "buildFallbacks"):
            _integer(stats.get(key), label + "." + kind + "." + key)
        if stats["buildSuccesses"] > stats["buildAttempts"]:
            raise EvidenceError(f"{label}: inconsistent native build counts")
    if requested == "off" and (presentation["nativeCapeCalls"] or presentation["nativeCapeInstances"]
                                or any(presentation[k]["buildAttempts"] for k in ("flight", "impact"))):
        raise EvidenceError(f"{label}: native presentation ran despite being disabled")
    _object(backends.get("preparedContent"), label + ".preparedContent")
    return backends


def validate_mounted_runtime(cell: dict, runtime: dict, policy: dict, quality: str) -> None:
    """Phase6 actual coverage and boundary evidence; never infer calls from requested mode."""
    label = str(cell["id"])
    profiles = _object(cell.get("mountProfiles"), label + ".mountProfiles")
    if set(profiles) != MIXED_MOUNT_PROFILES or sum(
            _integer(value, label + ".mountProfileCount", 1) for value in profiles.values()) != 80:
        raise EvidenceError(f"{label}: six-profile mounted workload differs")
    supported = sum(profiles[profile] for profile in RUST_MOUNT_PROFILES)
    expected_fallback = profiles["giant_rat"]
    before = _object(cell["census"]["afterSpawn"].get("mountedPresentation"), label + ".beforeMounted")
    after = _object(cell["census"]["afterSample"].get("mountedPresentation"), label + ".afterMounted")
    pose = _object(after.get("rustPose"), label + ".rustPose")
    prior = _object(before.get("rustPose"), label + ".priorRustPose")
    if pose.get("available") != 80 or pose.get("supported") != supported \
            or pose.get("eligible") != supported or pose.get("profiles") != profiles \
            or pose.get("requestedModes") != {"rust": 80} or pose.get("failures") != 0 \
            or pose.get("disabled") != expected_fallback \
            or pose.get("eligibleActiveVisuals") != pose.get("appliedEligibleActiveVisuals"):
        raise EvidenceError(f"{label}: actual Rust rider coverage or fallback differs")
    active = _integer(pose.get("eligibleActiveVisuals"), label + ".eligibleActiveRiders", 1)
    applications = _integer(pose.get("applications"), label + ".rustApplications", 1)
    if active > supported or _integer(pose.get("registered"), label + ".registered", active) > supported:
        raise EvidenceError(f"{label}: native rider registration exceeds supported content")
    fresh = _object(pose.get("freshness"), label + ".freshness")
    if fresh.get("available") != 80 or fresh.get("activeEligibleCurrentVisuals") != active:
        raise EvidenceError(f"{label}: latest eligible active pose submissions were not applied")
    current = _integer(fresh.get("currentSubmissionVisuals"), label + ".currentSubmissions", active)
    ages = _object(fresh.get("applicationAgeFrames"), label + ".applicationAgeFrames")
    age_count = _integer(ages.get("count"), label + ".applicationAgeCount", active)
    low = _number(ages.get("minimum"), label + ".minimumApplicationAge")
    high = _number(ages.get("maximum"), label + ".maximumApplicationAge")
    total = _number(ages.get("sum"), label + ".summedApplicationAge")
    if current > supported or age_count > supported or low > high or total < low * age_count \
            or total > high * age_count:
        raise EvidenceError(f"{label}: inconsistent pose freshness evidence")
    # Ages include intentionally paused riders. Current-submission equality,
    # rather than a global age limit, verifies no submitted pose was dropped.
    secondary = _object(pose.get("secondary"), label + ".secondary")
    previous = _object(prior.get("secondary"), label + ".priorSecondary")
    if secondary.get("available") != 80 or _integer(secondary.get("clothFallbacks"), label + ".clothFallbacks") != 0:
        raise EvidenceError(f"{label}: secondary runtime is missing or fell back")
    for field in ("upperApplications", "reinApplications", "reinCalls"):
        value = _integer(secondary.get(field), label + "." + field, 1)
        if value <= _integer(previous.get(field), label + ".prior" + field):
            raise EvidenceError(f"{label}: no new actual {field} after spawn readiness")
    if secondary["upperApplications"] != applications or secondary["reinApplications"] != applications:
        raise EvidenceError(f"{label}: coupled native upper/rein applications differ from pose applications")
    if _integer(secondary.get("reinAvailable"), label + ".reinAvailable", 1) > supported:
        raise EvidenceError(f"{label}: rein availability exceeds supported profiles")
    native = _object(runtime["activeBackends"]["clientRuntime"].get("native"), label + ".rustNative")
    for api in ("mounted_profile_api", "mounted_upper_api", "mounted_cape_api", "mounted_reins_api"):
        if _integer(native.get(api), label + "." + api) != 1:
            raise EvidenceError(f"{label}: missing actual {api}")
    for field in ("poses_applied", "upper_applied", "rein_calls"):
        if _integer(native.get(field), label + ".native." + field, 1) < applications:
            raise EvidenceError(f"{label}: actual native {field} cannot attest census applications")
    if _integer(native.get("rein_attempts"), label + ".nativeReinAttempts") != native["rein_calls"] \
            or _integer(native.get("rein_failures"), label + ".nativeReinFailures") != 0:
        raise EvidenceError(f"{label}: native rein commit failed")
    cloth = _integer(secondary.get("clothCalls"), label + ".clothCalls")
    native_cloth = _integer(native.get("mounted_cape_calls"), label + ".nativeMountedClothCalls")
    if _integer(native.get("mounted_cape_attempts"), label + ".nativeMountedClothAttempts") != native_cloth:
        raise EvidenceError(f"{label}: native mounted cloth had an unsuccessful attempt")
    if native_cloth < cloth:
        raise EvidenceError(f"{label}: native mounted cloth counters disagree")
    if quality == "high" and _integer(policy.get("clothBodies"), label + ".clothBudget") > 0:
        _integer(after.get("scheduling", {}).get("cloth"), label + ".scheduledCloth", 1)
        _integer(secondary.get("clothAvailable"), label + ".clothAvailable", 1)
        if cloth <= _integer(previous.get("clothCalls"), label + ".priorClothCalls"):
            raise EvidenceError(f"{label}: High fixture did not execute eligible mounted cloth")
    elif cloth != 0 or native_cloth != 0:
        # This fixture's local rider has no cape. This is not a general ban on
        # the ordinary local-player cape allowance at Medium/Low.
        raise EvidenceError(f"{label}: inactive fixture cloth policy executed mounted cloth")
    batch = _object(runtime["activeBackends"].get("mountedBatch"), label + ".mountedBatch")
    if batch.get("present") is not True or batch.get("fallbacks") != 0:
        raise EvidenceError(f"{label}: actual Rust batch is absent or fell back")
    _integer(batch.get("batches"), label + ".nativeBatches", 1)


def validate_report(data: dict, request: dict, log: str) -> dict:
    """Reject invalid evidence, returning explicit measured/pending cell classifications.

    request contains the runner's effective arguments, not values copied from the report.
    Unknown additive report fields remain available for subsequent phase instrumentation.
    """
    finite_tree(data)
    errors = ERROR_PATTERN.findall(log)
    if errors:
        raise EvidenceError(f"engine log contains {len(errors)} script/load/error lines")
    if data.get("benchmark") != "crowd_presentation" or type(data.get("schemaVersion")) is not int \
            or data.get("schemaVersion") != 1:
        raise EvidenceError("unexpected benchmark/schema")
    if _integer(data.get("failureCount"), "failureCount") != 0 or data.get("failures") != []:
        raise EvidenceError("benchmark reports failures or omits failure metadata")
    if data.get("headless") is not (request["mode"] == "headless"):
        raise EvidenceError("actual display mode differs from requested mode")
    if request["mode"] == "windowed" and data.get("renderingMethod") != request["renderer"]:
        raise EvidenceError("actual renderer differs from requested renderer")
    if data.get("graphicsQuality") not in ("low", "medium", "high"):
        raise EvidenceError("actual graphics quality is missing")
    if data.get("diagnostics", "") != request.get("diagnostics", ""):
        raise EvidenceError("actual diagnostic feature removals differ from request")
    if request.get("quality") and data["graphicsQuality"] != request["quality"]:
        raise EvidenceError("actual graphics quality differs from requested quality")
    if data.get("viewport") != list(request["resolution"]):
        raise EvidenceError("actual viewport differs from requested resolution")
    if request.get("map") and data.get("map") != request["map"]:
        raise EvidenceError("actual map differs from requested map")
    if request.get("minimap") in ("show", "hide") \
            and data.get("minimapVisible") is not (request["minimap"] == "show"):
        raise EvidenceError("actual minimap visibility differs from request")
    measurement = _object(data.get("measurement"), "measurement")
    for field, key in (("fpsCap", "fps_cap"), ("sampleMilliseconds", "sample_ms"),
                       ("warmupMilliseconds", "warmup_ms"), ("driver", "driver")):
        if measurement.get(field) != request[key]:
            raise EvidenceError(f"measurement.{field} differs from request")
    if not _object(data.get("worldReadiness"), "worldReadiness").get("ready") is True:
        raise EvidenceError("initial world is not ready")
    policy = _object(data.get("crowdPolicy"), "crowdPolicy")
    if request.get("body_cap") is not None and policy.get("bodyCap") != request["body_cap"]:
        raise EvidenceError("actual body cap differs from request")
    budget = {"low": 8, "medium": 12, "high": 16}[data["graphicsQuality"]]
    expected_budgets = {"fullRateBodies": budget, "halfRateBodies": budget,
                        "clothBodies": 0 if request.get("settings_profile") == "performance" else 8}
    for entry in request.get("tuning", "").split(","):
        pair = entry.split("=")
        if len(pair) == 2 and pair[0].strip() in ("full", "half", "cloth"):
            try:
                expected_budgets[{"full": "fullRateBodies", "half": "halfRateBodies", "cloth": "clothBodies"}
                                 [pair[0].strip()]] = max(0, int(pair[1].strip()))
            except ValueError:
                pass  # Matches CrowdPresentation.configure's ignored malformed overrides.
    if any(policy.get(key) != value for key, value in expected_budgets.items()):
        raise EvidenceError("effective crowd animation/cloth budgets differ from requested tier/tuning")
    if data.get("presenceDots") != request.get("presence", 0) \
            or data.get("serverTime") is not request.get("server_time", False):
        raise EvidenceError("actual presence/server-time workload differs from request")
    # New phase-one reports attest effective settings/backends; an old report cannot
    # establish a new reference merely by containing valid historical timing fields.
    validate_runtime(data, request, data.get("renderingMethod"), data["graphicsQuality"],
                     _integer(policy.get("bodyCap"), "crowdPolicy.bodyCap"), "report")
    if request.get("executable_mode") == "exported":
        build = _object(data.get("runtimeBuild"), "runtimeBuild")
        if build.get("template") is not True or build.get("editor") is not False:
            raise EvidenceError("exported workload did not attest a standalone non-editor runtime")
    if request.get("executable"):
        actual_exe = _object(data.get("runtimeBuild"), "runtimeBuild").get("executablePath")
        if not isinstance(actual_exe, str) or os.path.normcase(str(Path(actual_exe).resolve())) \
                != os.path.normcase(str(Path(request["executable"]).resolve())):
            raise EvidenceError("actual engine executable differs from launched executable")
    if request.get("user_root"):
        user_dir = _object(data.get("runtimeBuild"), "runtimeBuild").get("userDataDir")
        if not isinstance(user_dir, str) or not Path(user_dir).resolve().is_relative_to(Path(request["user_root"]).resolve()):
            raise EvidenceError("engine user data escaped the isolated run directory")
    if request.get("settings_profile") == "performance":
        seed_dir = request.get("settings_seed_user_dir")
        actual = _object(data.get("runtimeBuild"), "runtimeBuild").get("userDataDir")
        if not isinstance(seed_dir, str) or not isinstance(actual, str) \
                or os.path.normcase(str(Path(actual).resolve())) != os.path.normcase(str(Path(seed_dir).resolve())):
            raise EvidenceError("Performance runtime did not use the exact seeded user directory")
    if request.get("replay"):
        replay = _object(data.get("replay"), "replay")
        if replay.get("ok") is not True:
            raise EvidenceError("replay input did not load")
    cells = data.get("cells")
    if not isinstance(cells, list) or not cells or not all(isinstance(c, dict) for c in cells):
        raise EvidenceError("missing or malformed cells")
    ids = [c.get("id") for c in cells]
    if any(not isinstance(name, str) for name in ids):
        raise EvidenceError("cell IDs must be strings")
    if len(set(ids)) != len(ids):
        raise EvidenceError("duplicate report cells")
    expected = selected_cells(request["cells"], request.get("replay", False))
    if request.get("replay"):
        if ids != [f"replay-{data.get('map')}"]:
            raise EvidenceError("replay must contain exactly its recorded-map cell")
    elif set(ids) != set(expected):
        raise EvidenceError("requested and reported cells differ")
    pending, measured, observed_native = [], [], []
    for cell in cells:
        name = str(cell["id"])
        if cell.get("status") == "unavailable_content":
            if name != "authored-herd" or cell.get("qualification") != "pending" \
                    or cell.get("declaredAmbientAnimals") != 0 or cell.get("frames") != 0 \
                    or not isinstance(cell.get("reason"), str) or not cell["reason"] \
                    or _object(cell.get("readiness"), name + ".readiness").get("ready") is not False:
                raise EvidenceError(f"{name}: invalid unavailable-content classification")
            pending.append(name)
            continue
        if cell.get("status", "complete") not in ("complete", "measured"):
            raise EvidenceError(f"{name}: workload status is not complete")
        frames = _integer(cell.get("frames"), name + ".frames", 60)
        _number(cell.get("sampleMilliseconds"), name + ".sampleMilliseconds", request["sample_ms"])
        if _object(cell.get("readiness"), name + ".readiness").get("ready") is not True:
            raise EvidenceError(f"{name}: workload is not ready")
        distribution = validate_distribution(cell.get("frameTime"), name + ".frameTime", frames)
        series = cell.get("frameSeries")
        if not isinstance(series, list) or len(series) != frames:
            raise EvidenceError(f"{name}: missing/incomplete raw frame series")
        values = sorted(_number(v, name + ".frameSeries", .000001) for v in series)
        calculated = {"mean": sum(values) / frames, "max": values[-1]}
        for key, fraction in (("p5", .05), ("p50", .5), ("p95", .95), ("p99", .99)):
            calculated[key] = values[math.ceil(fraction * frames) - 1]
        if any(abs(calculated[k] - distribution[k]) > .0011 for k in calculated):
            raise EvidenceError(f"{name}: frame statistics disagree with raw series")
        count = _integer(cell.get("count"), name + ".count", 1)
        if not request.get("replay"):
            wanted_count = int(name.rsplit("-", 1)[-1]) if name.rsplit("-", 1)[-1].isdigit() else 1
            if count != wanted_count:
                raise EvidenceError(f"{name}: actor population differs from requested cell")
        census = _object(cell.get("census"), name + ".census")
        for point in ("afterSpawn", "afterSample"):
            sample = _object(census.get(point), name + "." + point)
            nodes = _integer(sample.get("nodes"), name + ".nodes", 1)
            built = _integer(sample.get("builtBodies"), name + ".builtBodies")
            deferred = _integer(sample.get("deferred"), name + ".deferred")
            if built + deferred != nodes or (not request.get("replay") and nodes != count):
                raise EvidenceError(f"{name}: actor/body census is inconsistent")
        runtime = _object(cell.get("effectiveRuntime"), name + ".effectiveRuntime")
        observed_native.append(validate_runtime(runtime, request, data.get("renderingMethod"),
                                               data["graphicsQuality"], policy["bodyCap"], name))
        if name.startswith("traversal-"):
            route = _object(cell.get("route"), name + ".route")
            if cell.get("status") != "complete" or route.get("kind") != "synthetic_client_streaming" \
                    or route.get("serverNavigationCertified") is not False:
                raise EvidenceError(f"{name}: invalid traversal classification")
            legs = route.get("legs")
            expected_legs = ["first-southern-border", "consecutive-southern-border", "interior-entry",
                             "interior-return", "teleport", "return"]
            if not isinstance(legs, list) or [leg.get("id") for leg in legs if isinstance(leg, dict)] != expected_legs:
                raise EvidenceError(f"{name}: incomplete deterministic route")
            for leg in legs:
                if leg.get("success") is not True or _object(leg.get("readiness"), name + ".leg.readiness").get("ready") is not True:
                    raise EvidenceError(f"{name}: failed/unready route leg")
                _number(leg.get("milliseconds"), name + ".leg.milliseconds")
            validate_distribution(cell.get("wallFrameTime"), name + ".wallFrameTime", frames)
            if not isinstance(cell.get("wallFrameSeries"), list) or len(cell["wallFrameSeries"]) != frames:
                raise EvidenceError(f"{name}: incomplete delivered-frame series")
            wall_values = sorted(_number(v, name + ".wallFrameSeries", .000001) for v in cell["wallFrameSeries"])
            wall = cell["wallFrameTime"]
            wall_expected = {"mean": sum(wall_values) / frames, "max": wall_values[-1]}
            for key, fraction in (("p5", .05), ("p50", .5), ("p95", .95), ("p99", .99)):
                wall_expected[key] = wall_values[math.ceil(fraction * frames) - 1]
            if any(abs(wall_expected[key] - wall[key]) > .0011 for key in wall_expected):
                raise EvidenceError(f"{name}: delivered-frame statistics disagree with raw series")
        else:
            summary = _object(cell.get("summary"), name + ".summary")
            actual_frame = validate_distribution(summary.get("frameMilliseconds"), name + ".summary.frames", frames)
            if any(abs(actual_frame[key] - distribution[key]) > .0011 for key in calculated):
                raise EvidenceError(f"{name}: summary/frame distributions differ")
            for metric in ("processPhaseMilliseconds", "flushPhaseMilliseconds"):
                validate_distribution(summary.get(metric), name + "." + metric, frames)
            if request["mode"] == "windowed":
                for metric in ("drawPhaseMilliseconds", "worldRenderCpuMilliseconds", "worldRenderGpuMilliseconds", "drawCalls"):
                    validate_distribution(summary.get(metric), name + "." + metric, frames)
            for metric in ("actorRecords", "actorNodes"):
                records = validate_distribution(summary.get(metric), name + "." + metric, frames)
                if not request.get("replay") and (records["p5"] != count or records["max"] != count):
                    raise EvidenceError(f"{name}: population changed during sample")
            if name == "mixed-mounted-160":
                for point in ("afterSpawn", "afterSample"):
                    if census[point].get("mountedActors") != 80 or census[point].get("mountSkeletons") != 80:
                        raise EvidenceError(f"{name}: mounted workload does not contain 80 mounted actors/skeletons")
                if request.get("client_runtime") == "rust":
                    validate_mounted_runtime(cell, runtime, policy, data["graphicsQuality"])
        if request.get("replay"):
            window = _object(cell.get("replayWindow"), name + ".replayWindow")
            if window.get("exhausted") is True or int(window.get("mapChanges", 0)) != 0:
                raise EvidenceError(f"{name}: replay ended or changed map during sample")
        else:
            plan = _object(cell.get("plan"), name + ".plan")
            active = _integer(plan.get("active"), name + ".plan.active")
            moving = _integer(plan.get("moving"), name + ".plan.moving")
            fighting = _integer(plan.get("fighting"), name + ".plan.fighting")
            expected_active = count - 1 if name.startswith("combat-") else \
                (1 if name.startswith("traversal-") else (count + 1) // 3 if count > 1 else 0)
            expected_moving = 0 if name.startswith("combat-") else (expected_active + 1) // 2
            if (active, moving, fighting) != (expected_active, expected_moving, expected_active - expected_moving):
                raise EvidenceError(f"{name}: activity workload differs from requested cell")
            if active and not name.startswith("traversal-"):
                _number(cell.get("packetsPerSecond"), name + ".packetsPerSecond", .000001)
                ticks = validate_distribution(summary.get("tickFrameMilliseconds"), name + ".tickFrames")
                if ticks["count"] > frames or _number(summary.get("packetsPerFrame", {}).get("mean"),
                                                      name + ".packetsPerFrame.mean", .000001) <= 0:
                    raise EvidenceError(f"{name}: no observed packet activity")
        measured.append(name)
    mode = request.get("native_presentation", "off")
    if request.get("client_runtime") == "compare" and not any(
            _integer(backend["clientRuntime"].get("comparisons"), "clientRuntime.comparisons") > 0
            for backend in observed_native):
        raise EvidenceError("requested Rust comparison runtime did not execute")
    presentations = [backend["presentation"] for backend in observed_native]
    if mode in ("cape", "both", "all") and (not any(p["nativeCapeCalls"] > 0 for p in presentations)
                                            or any(p["capeFallbackCalls"] for p in presentations)):
        raise EvidenceError("requested native cape path was not exercised without fallbacks")
    for family, modes in (("flight", ("flight", "both", "all")), ("impact", ("world", "all"))):
        if mode in modes and (not any(p[family]["buildSuccesses"] > 0 for p in presentations)
                              or any(p[family]["buildFallbacks"] for p in presentations)):
            raise EvidenceError(f"requested native {family} path was not exercised without fallbacks")
    return {"valid": True, "qualification": "pending_content" if pending else
            "diagnostic" if request.get("diagnostics") else "screening",
            "measuredCells": measured, "pendingCells": pending}


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def hash_files(files: list[Path], base: Path) -> dict:
    entries = []
    for path in sorted(set(p.resolve() for p in files)):
        if not path.is_file():
            raise EvidenceError("identity input disappeared")
        try:
            name = path.relative_to(base.resolve()).as_posix()
        except ValueError:
            name = str(path)
        entries.append({"path": name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "files": entries,
            "fileCount": len(entries), "bytes": sum(e["bytes"] for e in entries)}


def verified_exported_asset_closure(stage: Path, declared: dict) -> dict:
    # Load the shared tool by exact path; no packager import, sys.path mutation,
    # engine start or circular dependency is needed by the benchmark runner.
    helper = Path(__file__).resolve().parents[2] / "tools/benchmark_asset_closure.py"
    spec = importlib.util.spec_from_file_location("rabbitlands_benchmark_asset_closure", helper)
    if spec is None or spec.loader is None:
        raise EvidenceError("asset closure verification helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module.verify_asset_closure(stage, declared)
    except (OSError, ValueError) as error:
        raise EvidenceError("exported asset closure verification failed: " + str(error)) from error


def manifest_identity(path: Path) -> dict:
    """Verify a local artifact manifest. References stay inside its directory."""
    data = read_json(path)
    raw = data.get("files", data.get("artifacts"))
    if isinstance(raw, dict):
        raw = [{"path": p, "sha256": digest} for p, digest in raw.items()]
    if not isinstance(raw, list) or not raw:
        raise EvidenceError("artifact manifest has no files/artifacts")
    complete = data.get("contentComplete") is True
    if complete and (data.get("schemaVersion") != 1 or type(data.get("schemaVersion")) is not int):
        raise EvidenceError("complete artifact manifest needs schemaVersion 1")
    files, expected_by_path, expected_bytes = [], {}, {}
    for entry in raw:
        entry = _object(entry, "artifact")
        name, expected = entry.get("path"), entry.get("sha256")
        if not isinstance(name, str) or not isinstance(expected, str) \
                or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise EvidenceError("artifact manifest needs path and SHA-256 for each file")
        artifact = (path.parent / name).resolve()
        if not artifact.is_relative_to(path.parent.resolve()) or not artifact.is_file():
            raise EvidenceError("manifest artifact missing or outside artifact directory")
        if artifact in expected_by_path:
            raise EvidenceError("duplicate manifest artifact")
        expected_by_path[artifact] = expected
        if complete or "bytes" in entry:
            expected_bytes[artifact] = _integer(entry.get("bytes"), "artifact.bytes")
        files.append(artifact)
    if complete:
        actual = set()
        for candidate in path.parent.rglob("*"):
            if not candidate.is_file() or candidate.resolve() == path.resolve():
                continue
            resolved = candidate.resolve()
            if not resolved.is_relative_to(path.parent.resolve()):
                raise EvidenceError("complete artifact inventory contains an escaping symlink")
            actual.add(resolved)
        if actual != set(expected_by_path):
            raise EvidenceError("complete artifact inventory changed: added or removed files")
    identity = hash_files(files, path.parent)
    aggregate = hashlib.sha256()
    for item in identity["files"]:
        artifact = (path.parent / item["path"]).resolve()
        if item["sha256"] != expected_by_path[artifact]:
            raise EvidenceError("artifact content differs from manifest")
        if artifact in expected_bytes and item["bytes"] != expected_bytes[artifact]:
            raise EvidenceError("artifact byte count differs from manifest")
        aggregate.update(item["path"].encode("utf-8") + b"\0" + bytes.fromhex(item["sha256"]))
    declared_hash = data.get("contentHash")
    if complete or declared_hash is not None:
        if not isinstance(declared_hash, str) or re.fullmatch(r"[0-9a-f]{64}", declared_hash) is None \
                or declared_hash != aggregate.hexdigest():
            raise EvidenceError("artifact aggregate contentHash differs from manifest")
    for total_key in ("bytes", "totalBytes"):
        if total_key in data and _integer(data[total_key], total_key) != identity["bytes"]:
            raise EvidenceError("artifact total byte count differs from manifest")
    result = {"manifestSha256": sha256_file(path), "scope": data.get("scope", "explicit artifacts"),
              "contentComplete": complete, "contentHash": aggregate.hexdigest(), **identity}
    if "assetClosure" in data:
        if not complete:
            raise EvidenceError("asset closure requires a complete staged package manifest")
        result["assetClosure"] = verified_exported_asset_closure(path.parent, data["assetClosure"])
    return result


def source_files(client: Path) -> list[Path]:
    binaries = {".dll", ".so", ".dylib"}
    suffixes = {".gd", ".uid", ".gdshader", ".tscn", ".tres", ".py", ".rs", ".cpp", ".h", ".hpp", ".gdextension", ".toml", ".lock"} | binaries
    files = [client / "project.godot"]
    closure_helper = client / "tools/benchmark_asset_closure.py"
    if closure_helper.is_file():
        files.append(closure_helper)
    for folder in ("src", "tests/integration", "native"):
        root = client / folder
        if root.is_dir():
            files += [p for p in root.rglob("*") if p.is_file() and p.suffix in suffixes
                      and not any(part in ({"target", "godot-cpp", "__pycache__"} |
                                           ({"build"} if p.suffix not in binaries else set()))
                                  for part in p.relative_to(root).parts)]
    return files


def asset_files(client: Path, maps: list[str]) -> list[Path]:
    """Runtime resources plus explicit current-map/chunk dependency closure; no authoring trees."""
    files = [p for folder in ("assets", "data") for p in (client / folder).rglob("*") if p.is_file()]
    registry_path = client / "data/maps/registry.json"
    if not registry_path.is_file():
        return files
    registry = read_json(registry_path).get("maps", {})
    pending = []
    for name in maps:
        if name == "none":
            continue
        if name not in registry:
            raise EvidenceError("asset identity requested unknown map")
        pending.append((client / registry[name]["manifest"].removeprefix("res://")).resolve())
    seen: set[Path] = set()
    vram_directories: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        if not path.is_relative_to(client.parent.resolve()) or not path.is_file():
            raise EvidenceError("map dependency missing or outside runtime repository")
        seen.add(path)
        files.append(path)
        vram = path.parent / "vram"
        if vram.is_dir() and vram not in vram_directories:
            vram_directories.add(vram)
            files += [p for p in vram.rglob("*") if p.is_file()]
        if path.suffix != ".json":
            continue
        doc = read_json(path)
        refs = list(doc.get("externalResources", {})) + list(doc.get("externalMeshes", {}))
        glb = doc.get("asset", {}).get("glb")
        if glb:
            refs.append(glb)
        refs += [c["manifest"] for c in doc.get("streamingChunks", {}).get("chunks", []) if "manifest" in c]
        for ref in refs:
            pending.append((client / ref[6:] if ref.startswith("res://") else path.parent / ref).resolve())
    return files


def default_lock_path(client: Path) -> Path:
    for parent in (client, *client.parents):
        if (parent / "rabbitlands-client").is_dir() and (parent / "rabbitlands-server").is_dir():
            return parent / ".benchmark-locks/client-performance.lock"
    return Path(tempfile.gettempdir()) / "rabbitlands-benchmark-locks/client-performance.lock"


class BenchmarkLock:
    """Advisory OS lock; process death releases it. Never delete another owner's file."""
    def __init__(self, path: Path, timeout: float = 0, label: str = "crowd"):
        self.path, self.timeout, self.label = path, timeout, label
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        self.file = os.fdopen(fd, "r+b", buffering=0)
        if os.fstat(fd).st_size == 0:
            self.file.write(b"\0")
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.file.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError) as exc:
                if time.monotonic() >= deadline:
                    self.file.close()
                    self.file = None
                    raise EvidenceError("benchmark execution lock is held; no other process was stopped") from exc
                time.sleep(min(.1, max(0, deadline - time.monotonic())))
        try:
            metadata = {"pid": os.getpid(), "host": socket.gethostname(), "label": self.label,
                        "startedUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            self.file.seek(1)
            self.file.truncate()
            self.file.write(json.dumps(metadata).encode())
        except BaseException:
            self.file.close()  # Closing releases the OS lock even if metadata could not be written.
            self.file = None
            raise
        return self

    def __exit__(self, *_exc):
        if self.file is not None:
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            self.file.close()
            self.file = None


def clean_environment(inherited: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    cleared = sorted(k for k in inherited if k.startswith(OVERRIDE_PREFIXES) or k in OVERRIDE_NAMES)
    return {k: v for k, v in inherited.items() if k not in cleared}, cleared


def require_private_replay_output(output: Path, client: Path) -> None:
    for parent in (client, *client.parents):
        if (parent / ".git").exists() and output.resolve().is_relative_to(parent.resolve()):
            raise EvidenceError("replay output contains player data: choose a directory outside the repository")
