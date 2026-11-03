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
import shutil
import socket
import tempfile
import time
from typing import Any
from benchmark_soak_validation import soak_ids, validate_soak
from benchmark_remote_validation import validate_remote, validate_remote_cell
from benchmark_prepared_validation import configure_prepared_request, validate_prepared
from benchmark_heat_bolt_validation import HeatBoltEvidenceError, validate_heat_bolt_cell


class EvidenceError(ValueError):
    pass


OLD_CELLS = [name for count in (100, 160, 200, 300)
             for name in (f"s3-market-{count}", f"s2-invasion-{count}")]
OLD_CELLS += ["combat-100", "combat-160", "aoi-160", "empty"]
PHASE1_CELLS = ["s3-market-160", "s2-invasion-160", "mixed-mounted-160",
                "combat-160", "empty", "traversal-southern-cold", "traversal-southern-warm"]
PHASE7_CELLS = ["combat-heat-bolt-160"]
UNDEAD_CELLS = [f"production-undead-{count}" for count in (160, 300, 500)]
GAUNTLET_CELL = "authored-gauntlet-resinroad-combat-21"
GAUNTLET_FIXTURE = "tests/fixtures/gauntlet_performance_wave.json"
UNDEAD_SPECIES = {"zombie": {"actorType": 746, "footprint": [1, 1]},
                  "skeleton": {"actorType": 745, "footprint": [1, 1]},
                  "drowned_lich_king": {"actorType": 671, "footprint": [2, 2]}}
ALL_CELLS = OLD_CELLS + ["mixed-mounted-160", "authored-herd",
                         "traversal-southern-cold", "traversal-southern-warm"]
# Explicit wave-2 selectors outside the historical `all` membership.
SEAM_CELLS = ["traversal-seam-walk"]
TRAVERSAL_CELLS = ["traversal-southern-cold", "traversal-southern-warm"] + SEAM_CELLS
# performance_workloads.gd: the six-leg southern route and the walking seam route.
ROUTE_LEGS = {"southern": ["first-southern-border", "consecutive-southern-border", "interior-entry",
                           "interior-return", "teleport", "return"],
              "seam": ["walking-seam"]}
# Route fixture version 2 (wave 2 AW-00) adds per-leg settle/visible times.
ROUTE_VERSION = 2
# The configuration-overlay worker pools tools/continent_stream_benchmark_project.py supports.
WORKER_POOL_THREADS = (4, 8)
# Attribution switches (RABBITLANDS_CROWD_BENCH_DIAG). no_text_pass and
# text_pass_always are the wave-2 OV-0 world-text pass modes.
DIAGNOSTICS = ("no_animation", "no_overhead", "no_ground", "no_text_pass", "text_pass_always")
# Engine options a rendered run may add to the runner's own (wave-2 MOB-C6a,
# --engine-arg): the GPU a multi-GPU machine renders on (the laptop's iGPU proxy
# is --gpu-index 1), the rendering driver and Godot's GPU profile. Nothing else:
# the renderer, resolution, paths, log and script stay the runner's.
ENGINE_ARGS = {"--gpu-index": "index", "--rendering-driver": "driver", "--gpu-profile": None}
RENDERING_DRIVERS = {"forward_plus": ("vulkan", "d3d12", "metal"), "mobile": ("vulkan", "d3d12", "metal"),
                     "gl_compatibility": ("opengl3", "opengl3_angle", "opengl3_es")}
# Per-frame viewport GPU times (rendered runs). A reading above the bound is a
# wrapped timestamp, not a frame (validate_gpu_timestamps).
GPU_TIME_METRICS = ("worldRenderGpuMilliseconds", "rootRenderGpuMilliseconds", "renderGpuSumMilliseconds",
                    "textPassRenderGpuMilliseconds")
MAX_PLAUSIBLE_GPU_MILLISECONDS = 60000.0
# Godot's shader and pipeline caches in the user data directory, the only things
# --seed-profile copies into a run's fresh user root (MOB-C6a: warm repeats).
PROFILE_SEED_DIRECTORIES = ("shader_cache", "vulkan", "d3d12")
ERROR_PATTERN = re.compile(r"SCRIPT ERROR|Parse Error|Failed to load|Error loading|ERROR:", re.I)
OVERRIDE_PREFIXES = ("ELORIA_LOOK", "ELORIA_CROWD_", "ELORIA_NATIVE_", "RABBITLANDS_CROWD_")
OVERRIDE_NAMES = {"ELORIA_VRAM_TEXTURES", "ELORIA_NO_MAP_CACHE", "ELORIA_SAFE_MODE", "RABBITLANDS_CLIENT_RUNTIME", "RABBITLANDS_RUST_EFFECTS"}
OVERRIDE_NAMES.update({"RABBITLANDS_RESOURCE_ADMISSION", "RABBITLANDS_RESOURCE_BUDGET_MIB"})
OVERRIDE_NAMES.update({"RABBITLANDS_PREPARED_CONTENT", "RABBITLANDS_PREPARED_NODE_POLICY"})
OVERRIDE_NAMES.update({"ELORIA_WARDROBE_TEXTURE_CACHE", "ELORIA_ACTOR_BUILD_PROFILE"})
# The world-text pass idle switch; --diagnostics text_pass_always is the recorded way.
OVERRIDE_NAMES.add("ELORIA_WORLD_TEXT_IDLE")
PERFORMANCE_GRAPHICS = {
    "quality": "low", "appearance": "painted_ground", "fps_limit": 30,
    "render_scale": .75, "map_texture_quality": "half", "crowd_bodies": 60,
    "swaying_capes": 0, "shadows": False, "particles": True,
    "decorative_grass": False, "name_distance": 20.0,
}
PERFORMANCE_PROFILES = {"performance": 30, "performance-60": 60, "performance-60-scale50": 60}
PERFORMANCE_RENDER_SCALES = {"performance": .75, "performance-60": .75, "performance-60-scale50": .5}
RUST_MOUNT_PROFILES = frozenset({"moor_pony", "golden_plains_horse", "crystalback_tortoise",
                               "rabbit", "jadefeather_raptor"})
MIXED_MOUNT_PROFILES = RUST_MOUNT_PROFILES | {"giant_rat"}


def configure_prepared_profile(args) -> None:
    try:
        configure_prepared_request(args)
    except ValueError as exc:
        raise EvidenceError(str(exc)) from exc


def configure_settings_profile(args, system: str | None = None) -> None:
    """Resolve omitted arguments, rejecting overrides that would mislabel a preset."""
    profile = getattr(args, "settings_profile", "default")
    if profile not in ("default", *PERFORMANCE_PROFILES):
        raise EvidenceError("unknown settings profile")
    if profile in PERFORMANCE_PROFILES:
        profile_fps = PERFORMANCE_PROFILES[profile]
        if (platform.system() if system is None else system) not in ("Windows", "Linux"):
            raise EvidenceError("Performance settings seeding supports Windows and Linux only")
        for field, absent, expected in (("quality", "", "low"), ("fps_cap", None, profile_fps),
                                        ("body_cap", None, 60)):
            value = getattr(args, field)
            if field == "fps_cap" and value == 0:
                # Uncapped: the preset's settings without its frame cap, for GPU-time
                # comparisons (MOB-C6 protocol, gate G1). The seeded file keeps the
                # preset's own cap; the requested 0 is recorded and validated.
                continue
            if value != absent and value != expected:
                raise EvidenceError(f"Performance profile conflicts with --{field.replace('_', '-')}; requires {expected}")
            setattr(args, field, expected)
        if args.tuning:
            raise EvidenceError("Performance profile does not allow crowd tuning overrides")
    elif args.fps_cap is None:
        args.fps_cap = 60  # Preserve the existing default profile.
    cells = selected_cells(args.cells, bool(args.replay))
    undead = [name in UNDEAD_CELLS for name in cells]
    if any(undead):
        if not all(undead):
            raise EvidenceError("production undead and historical cells need separate runs/prewarms")
        if getattr(args, "map", "") not in ("", "twinbrook"):
            raise EvidenceError("production undead requires the authored Twinbrook map")
        if getattr(args, "centre", "") not in ("", "453,168"):
            raise EvidenceError("production undead requires authored centre 453,168")
        args.map, args.centre = "twinbrook", "453,168"
    if GAUNTLET_CELL in cells:
        if cells != [GAUNTLET_CELL]:
            raise EvidenceError("authored gauntlet and other cells need separate runs/prewarms")
        fixture = gauntlet_fixture()
        map_id = fixture["map"]
        centre = ",".join(str(int(value)) for value in fixture["centreTile"])
        if getattr(args, "map", "") not in ("", map_id):
            raise EvidenceError(f"authored gauntlet requires {map_id}")
        if getattr(args, "centre", "") not in ("", centre):
            raise EvidenceError(f"authored gauntlet requires observer centre {centre}")
        args.map, args.centre = map_id, centre
    if "mixed-mounted-160" in cells and args.body_cap is not None and 0 < args.body_cap < 80:
        raise EvidenceError("mixed-mounted-160 requires 80 mounted bodies; the requested body cap is below 80")


def require_pinned_body_cap(args) -> str | None:
    """Comparison runs at plain Low state their body cap (wave-2 schedule, wave A).

    Since LAT-L5 the crowd count follows the quality: `--quality low` without
    `--body-cap` draws 60 bodies, where earlier runs drew 160. A quiet-comparison
    run is refused unless it pins the cap (`--body-cap 160` reproduces earlier
    runs); a screening run gets a note instead. Performance profiles pin 60.
    """
    if getattr(args, "settings_profile", "default") != "default" or args.quality != "low" \
            or args.body_cap is not None:
        return None
    message = ("plain Low follows the quality to 60 bodies since LAT-L5; pass --body-cap 160 to compare "
               "with earlier runs (or --body-cap 60 to state the new default)")
    if getattr(args, "measurement_status", "screening") == "quiet-comparison":
        raise EvidenceError("quiet-comparison runs at --quality low must pin the body cap: " + message)
    return message


def parse_engine_args(values: list[str] | None, renderer: str, mode: str) -> list[str]:
    """--engine-arg values as the exact engine tokens, refused unless allowlisted.

    Each value is one option with its value: "--gpu-index 1", "--gpu-index=1",
    "--rendering-driver=d3d12" or "--gpu-profile" (argparse needs
    `--engine-arg=--gpu-profile` or a quoted value with a space). An option
    given twice, a malformed index, a driver of the other renderer family, or
    any option outside ENGINE_ARGS (the renderer, resolution, paths, log and
    script are the runner's) is refused before anything launches. Headless runs
    render nothing, so they take none.
    """
    tokens: list[str] = []
    for value in values or []:
        for part in str(value).split():
            name, separator, rest = part.partition("=")
            tokens += [name, rest] if separator and name.startswith("--") else [part]
    result: list[str] = []
    seen: set[str] = set()
    index = 0
    while index < len(tokens):
        name = tokens[index]
        if name not in ENGINE_ARGS:
            raise EvidenceError(f"unsupported --engine-arg {name!r}; allowed: {', '.join(ENGINE_ARGS)}")
        if name in seen:
            raise EvidenceError(f"--engine-arg {name} given twice")
        seen.add(name)
        kind = ENGINE_ARGS[name]
        if kind is None:
            result.append(name)
            index += 1
            continue
        if index + 1 >= len(tokens) or not tokens[index + 1]:
            raise EvidenceError(f"--engine-arg {name} needs a value")
        value = tokens[index + 1]
        if kind == "index" and re.fullmatch(r"[0-9]{1,2}", value) is None:
            raise EvidenceError("--engine-arg --gpu-index takes a device index 0-99")
        if kind == "driver" and value not in RENDERING_DRIVERS.get(renderer, ()):
            raise EvidenceError(f"--engine-arg --rendering-driver {value!r} does not run the {renderer} renderer; "
                                f"choose one of {', '.join(RENDERING_DRIVERS.get(renderer, ()))}")
        result += [name, value]
        index += 2
    if result and mode != "windowed":
        raise EvidenceError("--engine-arg selects a GPU, driver or GPU profile: it needs a rendered (windowed) run")
    return result


def engine_arg_value(engine_args: list[str] | None, name: str) -> str | None:
    """The value an allowlisted engine option was given, or None."""
    tokens = list(engine_args or [])
    if name not in tokens:
        return None
    index = tokens.index(name)
    return "" if ENGINE_ARGS.get(name) is None else tokens[index + 1]


def seed_settings_profile(profile: str, client: Path, user_root: Path,
                          environment: dict[str, str], system: str | None = None) -> dict | None:
    """Write only fresh, generated preferences before Godot caches texture quality.

    Windows custom user:// uses APPDATA; Linux uses XDG_DATA_HOME and the
    project's explicit linuxbsd custom-directory override. Startup attestation
    must confirm that the engine opened this exact generated directory.
    """
    if profile == "default":
        return None
    system = platform.system() if system is None else system
    if profile not in PERFORMANCE_PROFILES or system not in ("Windows", "Linux"):
        raise EvidenceError("Performance settings seeding supports Windows and Linux only")
    user_dir = isolated_user_data_dir(client, user_root, environment, system, "Performance profile")
    path = user_dir / "eloria_hud.cfg"
    graphics = PERFORMANCE_GRAPHICS | {"fps_limit": PERFORMANCE_PROFILES[profile],
                                       "render_scale": PERFORMANCE_RENDER_SCALES[profile]}
    content = "[graphics]\n\n" + "".join(
        f"{key}={json.dumps(value, ensure_ascii=False, allow_nan=False)}\n"
        for key, value in graphics.items())
    user_dir.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    except FileExistsError as exc:
        raise EvidenceError("settings seed already exists; no existing preferences were overwritten") from exc
    return {"profile": profile, "path": str(path), "userDataDir": str(user_dir),
            "content": content, "sha256": sha256_file(path), "bytes": path.stat().st_size,
            "scope": "generated initial settings before startup; no inherited user config"}


def isolated_user_data_dir(client: Path, user_root: Path, environment: dict[str, str],
                           system: str, purpose: str) -> Path:
    """The project's custom user:// directory inside a run's fresh isolated root.

    Windows custom user:// uses APPDATA; Linux uses XDG_DATA_HOME and the
    project's explicit linuxbsd custom-directory override. `purpose` names the
    seed in refusals.
    """
    root = user_root.resolve()
    variable = "APPDATA" if system == "Windows" else "XDG_DATA_HOME"
    data_home = environment.get(variable)
    if not data_home or not Path(data_home).is_absolute() or Path(data_home).resolve() != root:
        raise EvidenceError(f"{purpose} requires the fresh isolated {variable} directory")
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
            or (system == "Linux" and application.get(custom + ".linuxbsd") != '"godot/app_userdata/Eloria"') \
            or any(key.startswith(custom + ".") and key != custom + ".linuxbsd" for key in application):
        raise EvidenceError(f"{purpose} does not support this project's custom user directory settings")
    user_dir = root / ("Godot/app_userdata/Eloria" if system == "Windows" else "godot/app_userdata/Eloria")
    if not user_dir.resolve().is_relative_to(root):
        raise EvidenceError(f"{purpose} path escaped the isolated run directory")
    return user_dir


def _is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def profile_seed_source(path: Path) -> Path:
    """The user data directory a --seed-profile DIR names.

    DIR is a user data directory (it holds shader_cache/, vulkan/ or d3d12/) or a
    run's isolated user root (`<out-dir>/userdata/<run>`), whose
    Godot/app_userdata/Eloria (godot/... on Linux) is used.
    """
    root = Path(path).resolve()
    if not root.is_dir():
        raise EvidenceError("--seed-profile directory does not exist")
    for candidate in (root, root / "Godot/app_userdata/Eloria", root / "godot/app_userdata/Eloria"):
        if any((candidate / name).is_dir() for name in PROFILE_SEED_DIRECTORIES):
            if _is_link(candidate) or not candidate.resolve().is_relative_to(root):
                raise EvidenceError("--seed-profile user data directory is a link")
            return candidate
    raise EvidenceError("--seed-profile holds no shader_cache/, vulkan/ or d3d12/ directory")


def seed_profile_caches(source: Path, client: Path, user_root: Path, environment: dict[str, str],
                        system: str | None = None) -> dict:
    """Copy only Godot's shader and pipeline caches into a run's fresh user directory.

    Without a seed every repeat starts cold (MOB-C6a). PROFILE_SEED_DIRECTORIES
    are copied file by file and verified; settings, prepared-world caches and
    everything else in the source stay out, and links are refused. The engine
    must open exactly this directory (startup acknowledgement and report check).
    Driver caches (LOCALAPPDATA, the GPU vendor's own) are not controlled here.
    """
    system = platform.system() if system is None else system
    if system not in ("Windows", "Linux"):
        raise EvidenceError("--seed-profile supports Windows and Linux only")
    source = profile_seed_source(source)
    user_dir = isolated_user_data_dir(client, user_root, environment, system, "--seed-profile")
    if source.resolve().is_relative_to(user_root.resolve()) or user_root.resolve().is_relative_to(source.resolve()):
        raise EvidenceError("--seed-profile overlaps the run's own user root")
    # Check everything first, so a refused seed leaves nothing in the run's root.
    planned: dict[str, list[Path]] = {}
    for name in PROFILE_SEED_DIRECTORIES:
        top = source / name
        if not top.exists() and not _is_link(top):
            continue
        if _is_link(top) or not top.is_dir():
            raise EvidenceError(f"--seed-profile {name} is a link or not a directory")
        if (user_dir / name).exists():
            raise EvidenceError(f"--seed-profile would overwrite the run's {name}")
        planned[name] = []
        for directory, subdirectories, names in os.walk(top, followlinks=False):
            current = Path(directory)
            for child in [*subdirectories, *names]:
                if _is_link(current / child):
                    raise EvidenceError(f"--seed-profile {name} contains a link")
            for file_name in sorted(names):
                if not (current / file_name).is_file():
                    raise EvidenceError(f"--seed-profile {name} contains a special file")
                planned[name].append(current / file_name)
    if not any(planned.values()):
        raise EvidenceError("--seed-profile caches are empty")
    digest = hashlib.sha256()
    directories: dict[str, dict] = {}
    pipeline_caches: list[str] = []
    for name, paths in planned.items():
        files = size = 0
        for path in sorted(paths):
            relative = path.relative_to(source).as_posix()
            destination = user_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            file_digest = sha256_file(path)
            if sha256_file(destination) != file_digest:
                raise EvidenceError("--seed-profile copy differs from its source")
            digest.update(f"{relative}\0{file_digest}\n".encode("utf-8"))
            files += 1
            size += path.stat().st_size
            if name != "shader_cache" and path.parent == source / name:
                pipeline_caches.append(relative)
        directories[name] = {"files": files, "bytes": size}
    return {"source": str(source), "userDataDir": str(user_dir), "directories": directories,
            "files": sum(entry["files"] for entry in directories.values()),
            "bytes": sum(entry["bytes"] for entry in directories.values()),
            "sha256": digest.hexdigest(), "pipelineCaches": sorted(pipeline_caches),
            "scope": "Godot shader_cache/, vulkan/ and d3d12/ only; settings, prepared-world caches and "
                     "GPU driver caches (LOCALAPPDATA) are not copied"}


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
    if profile.startswith("route-soak-"):
        if replay: raise EvidenceError("same-process route soak cannot replay private data")
        try: return soak_ids(profile)
        except ValueError as exc: raise EvidenceError(str(exc)) from exc
    if replay:
        return []  # The recording determines its map; validate exactly one replay cell later.
    profiles = {"phase4": OLD_CELLS, "quick": ["s3-market-160", "s2-invasion-160"],
                "phase1": PHASE1_CELLS, "phase7": PHASE7_CELLS, "all": ALL_CELLS,
                "production-undead": UNDEAD_CELLS, "traversal": TRAVERSAL_CELLS}
    names = list(profiles[profile]) if profile in profiles else profile.split(",")
    if not names or any(not item or item not in ALL_CELLS + PHASE7_CELLS + SEAM_CELLS + UNDEAD_CELLS + [GAUNTLET_CELL]
                        for item in names):
        raise EvidenceError("unknown or empty benchmark cell selector")
    if len(set(names)) != len(names):
        raise EvidenceError("duplicate benchmark cell selector")
    return names


def validate_undead_cell(cell: dict) -> None:
    """The new population counts remote creatures, in addition to one player."""
    name = cell["id"]
    remote = int(name.rsplit("-", 1)[-1])
    expected = {species: remote // 3 + int(index < remote % 3)
                for index, species in enumerate(UNDEAD_SPECIES)}
    if cell.get("count") != remote + 1 or cell.get("creatureCount") != remote \
            or cell.get("cohort") != "twinbrook-onslaught-v1" \
            or cell.get("populationScope") != "remote_creatures_plus_one_player" \
            or cell.get("speciesCounts") != expected \
            or cell.get("stressAboveDefaultServerCaps") is not (remote > 160):
        raise EvidenceError(f"{name}: production undead population metadata differs")
    active = (remote + 2) // 3
    if cell.get("plan") != {"active": active, "moving": (active + 1) // 2, "fighting": active // 2} \
            or cell.get("combatDriver") != "melee_only":
        raise EvidenceError(f"{name}: production undead activity differs")
    names = list(UNDEAD_SPECIES)
    def species_counts(indices):
        return {species: sum(names[index % 3] == species for index in indices) for species in names}
    if cell.get("activitySpecies") != {"active": species_counts(range(active)),
                                       "moving": species_counts(range(0, active, 2)),
                                       "fighting": species_counts(range(1, active, 2))}:
        raise EvidenceError(f"{name}: production undead active species differ")
    for boundary in ("afterSpawn", "afterSample"):
        observed = cell.get("census", {}).get(boundary, {}).get("productionUndead", {})
        if observed != {"remoteCreatures": remote, "localPlayers": 1,
                        "species": expected, "invalidProfiles": 0, "aliveRemoteCreatures": remote, "invalidHealth": 0}:
            raise EvidenceError(f"{name}: production undead census/profile/alive mismatch at {boundary}")


def gauntlet_fixture() -> dict:
    return read_json(Path(__file__).resolve().parents[2] / GAUNTLET_FIXTURE)


def validate_gauntlet_cohort(data: dict) -> None:
    fixture = gauntlet_fixture()
    cohort = data.get("creatureCohort", {})
    fixture_path = Path(__file__).resolve().parents[2] / GAUNTLET_FIXTURE
    if data.get("map") != fixture["map"] or data.get("centreTile") != fixture["centreTile"] \
            or cohort.get("id") != "resinroad-sounder-w5-pulse3-v1" \
            or cohort.get("fixture") != "res://" + GAUNTLET_FIXTURE \
            or cohort.get("fixtureSha256") != sha256_file(fixture_path) \
            or cohort.get("profiles") != fixture["profiles"] or cohort.get("wave") != fixture["wave"] \
            or cohort.get("waveCentreTile") != fixture.get("waveCentreTile") or cohort.get("observer") != fixture.get("observer") \
            or cohort.get("qualification") != fixture["qualification"] \
            or data.get("creatureFootprints") != {str(p["actorType"]): p["footprint"] for p in fixture["profiles"]} \
            or data.get("prewarmed", {}).get("creatureModels") != [p["model"] for p in fixture["profiles"]]:
        raise EvidenceError("authored gauntlet cohort/map/fixture/prewarm differs")


def validate_gauntlet_cell(cell: dict) -> None:
    fixture = gauntlet_fixture()
    species = {p["model"]: p["count"] for p in fixture["profiles"]}
    remote = len(fixture["actors"])
    if cell.get("count") != remote + 1 or cell.get("creatureCount") != remote \
            or cell.get("cohort") != "resinroad-sounder-w5-pulse3-v1" \
            or cell.get("populationScope") != "remote_creatures_plus_one_player" \
            or cell.get("positionScope") != "exact_authored_spawn_tiles" or cell.get("speciesCounts") != species \
            or cell.get("combatDriver") != "scripted_melee_only" \
            or cell.get("plan") != {"active": remote, "moving": 0, "fighting": remote} \
            or cell.get("activitySpecies") != {"active": species, "moving": {}, "fighting": species}:
        raise EvidenceError("authored gauntlet population/activity differs")
    for boundary in ("afterSpawn", "preSample", "afterSample"):
        sample = cell.get("census", {}).get(boundary, {})
        minimum_visible = _integer(fixture.get("observer", {}).get("minimumExpectedInFrustumCreatures"), "gauntlet.minimumVisibleCreatures", 1) + 1
        if boundary != "afterSpawn" and _integer(sample.get("inFrustumBuiltBodies"), "gauntlet.inFrustumBuiltBodies") < minimum_visible:
            raise EvidenceError(f"authored gauntlet has fewer than {minimum_visible} visible built bodies at {boundary}")
        observed = sample.get("authoredGauntlet", {})
        if observed != {"remoteCreatures": remote, "localPlayers": 1, "species": species, "invalidProfiles": 0,
                        "aliveRemoteCreatures": remote, "invalidHealth": 0}:
            raise EvidenceError(f"authored gauntlet census/profile/tile/alive mismatch at {boundary}")


def route_legs_for(cell_name: str) -> list[str]:
    """The leg ids a traversal cell must report, in order."""
    return ROUTE_LEGS["seam" if cell_name.startswith("traversal-seam") else "southern"]


def validate_route_v2(route: dict, frames: int, name: str) -> None:
    """Route fixture version 2: settle/visible times, curtain and frame ranges per leg.

    Whether a seam crossing was continuous is a measurement (the neighbour may not
    be resident in time), so it is reported, never required.
    """
    if route.get("routeVersion") != ROUTE_VERSION or route.get("legSchema") != 2 \
            or route.get("routeId") != ("seam" if name.startswith("traversal-seam") else "southern"):
        raise EvidenceError(f"{name}: unexpected route fixture version/schema")
    previous_end = None
    for leg in route["legs"]:
        label = f"{name}.{leg.get('id')}"
        settle = _number(leg.get("settleMs"), label + ".settleMs")
        if abs(settle - _number(leg.get("milliseconds"), label + ".milliseconds")) > .001:
            raise EvidenceError(f"{label}: settle time differs from the transition time")
        visible = leg.get("visibleMs")
        # settleMs is the historical transition time, a difference of two whole-millisecond
        # clock readings; visibleMs is measured in microseconds from a later start. A report
        # inside the settle window can therefore exceed it by under one truncated millisecond.
        if visible is not None and _number(visible, label + ".visibleMs") >= settle + 1.0:
            raise EvidenceError(f"{label}: player-visible time exceeds the settle time")
        if not isinstance(leg.get("visibleBasis"), str) or (visible is None) != (leg.get("arrivalReports") == 0):
            raise EvidenceError(f"{label}: visible time disagrees with its arrival reports")
        curtain = _object(leg.get("curtain"), label + ".curtain")
        if not isinstance(curtain.get("shown"), bool) \
                or (curtain["shown"] is False and curtain.get("shownMs") is not None):
            raise EvidenceError(f"{label}: inconsistent arrival curtain evidence")
        if not isinstance(leg.get("continuousHandoff"), bool) or not isinstance(leg.get("expectContinuous"), bool):
            raise EvidenceError(f"{label}: handoff classification missing")
        ranges = _object(leg.get("frameRanges"), label + ".frameRanges")
        bounds = []
        for phase in ("start", "walk", "transition", "capture"):
            pair = ranges.get(phase)
            if not isinstance(pair, list) or len(pair) != 2:
                raise EvidenceError(f"{label}: frame range {phase} missing")
            bounds.append((_integer(pair[0], label + "." + phase), _integer(pair[1], label + "." + phase)))
        flat = [value for pair in bounds for value in pair]
        if flat != sorted(flat) or any(bounds[i][1] != bounds[i + 1][0] for i in range(3)) \
                or flat[-1] > frames or (previous_end is not None and flat[0] != previous_end):
            raise EvidenceError(f"{label}: frame ranges are not contiguous within the route series")
        if _integer(leg.get("sampledFrames"), label + ".sampledFrames") != flat[-1] - bounds[2][0]:
            raise EvidenceError(f"{label}: sampled frame count differs from its frame ranges")
        previous_end = flat[-1]


def validate_worker_pool(data: dict, request: dict) -> None:
    """A requested worker pool must be the one the engine reports it started with."""
    requested = request.get("worker_threads", 0) or 0
    if not requested:
        return
    pool = _object(data.get("workerPool"), "workerPool")
    if pool.get("maxThreadsSetting") != requested:
        raise EvidenceError("actual worker pool size differs from the requested overlay")


def parse_diagnostics(text: str) -> list[str]:
    """--diagnostics: attribution switches, never acceptance modes (RABBITLANDS_CROWD_BENCH_DIAG).

    Split like the harness (`split(",", false)`: empty entries dropped, nothing
    stripped), so a name the harness would ignore is refused here instead.
    """
    names = [name for name in (text or "").split(",") if name]
    unknown = sorted(set(names) - set(DIAGNOSTICS))
    if unknown:
        raise EvidenceError(f"unknown --diagnostics {unknown}; known: {', '.join(DIAGNOSTICS)}")
    if len(set(names)) != len(names):
        raise EvidenceError("--diagnostics names a switch twice")
    if "no_text_pass" in names and "text_pass_always" in names:
        raise EvidenceError("--diagnostics no_text_pass and text_pass_always are opposite text-pass modes")
    return names


def text_pass_mode(names: list[str]) -> str:
    """The harness's text_pass_mode(): the world-text pass mode a diagnostic list selects."""
    return "off" if "no_text_pass" in names else "always" if "text_pass_always" in names else "auto"


def _stopped_pass_size(size) -> bool:
    """no_text_pass shrinks the pass target to the smallest a SubViewport keeps (2x2)."""
    return isinstance(size, list) and len(size) == 2 and all(
        type(value) is int and 0 < value <= 2 for value in size)


def validate_overhead_diagnostics(data: dict, request: dict, require_records: bool = False) -> None:
    """OV-0: an overhead or text-pass diagnostic took effect in every sampled crowd cell.

    Reports from before OV-0 carry no textPass/overhead records; they are
    accepted only when no such diagnostic was requested and `require_records`
    is false (the decision-8 gate requires them of every report it compares).
    Every cell starts from the shipping pass (`textPass.cellStart`), so a pass
    stopped by an earlier cell never shrinks a later cell's withCrowd memory.
    """
    names = parse_diagnostics(request.get("diagnostics", ""))
    mode = text_pass_mode(names)
    required = require_records or mode != "auto" or "no_overhead" in names
    for cell in data.get("cells", []):
        if not isinstance(cell, dict) or "summary" not in cell or cell.get("status") == "unavailable_content":
            continue
        name = str(cell.get("id"))
        if "textPass" not in cell and not required:
            continue
        state = _object(cell.get("textPass"), name + ".textPass")
        if state.get("present") is not True or state.get("mode") != mode:
            raise EvidenceError(f"{name}: world-text pass mode differs from the requested diagnostics")
        if required or "cellStart" in state:
            start = _object(state.get("cellStart"), name + ".textPass.cellStart")
            if start.get("ok") is not True or start.get("mode") != "auto" \
                    or _stopped_pass_size(start.get("passViewportSize")):
                raise EvidenceError(f"{name}: the cell did not start from the shipping world-text pass")
        if require_records:
            overhead = _object(cell.get("overhead"), name + ".overhead")
            for boundary in ("sampleStart", "afterSample"):
                _object(overhead.get(boundary), f"{name}.overhead.{boundary}")
        drawn = _integer(state.get("drawnFrames"), name + ".textPass.drawnFrames")
        sampled = _integer(state.get("sampledFrames"), name + ".textPass.sampledFrames")
        if drawn > sampled or sampled != cell.get("frames"):
            raise EvidenceError(f"{name}: text-pass frame counts disagree with the sample")
        if mode == "off" and (drawn != 0 or state.get("overlayVisible") is not False
                              or not _stopped_pass_size(state.get("passViewportSize"))):
            raise EvidenceError(f"{name}: no_text_pass left the world-text pass rendering or its target allocated")
        if mode == "always" and (state.get("idleWatching") is not False
                                 or (request["mode"] == "windowed" and drawn != sampled)):
            raise EvidenceError(f"{name}: text_pass_always did not render the pass every frame")
        if "no_overhead" in names:
            overhead = _object(cell.get("overhead"), name + ".overhead")
            for boundary in ("sampleStart", "afterSample"):
                census = _object(overhead.get(boundary), f"{name}.overhead.{boundary}")
                if census.get("overheadShown") != 0 or census.get("healthShown") != 0:
                    raise EvidenceError(f"{name}: no_overhead left actor banners shown at {boundary}")


def resolve_worker_threads(value: str, affinity: str) -> int:
    """--worker-threads: 0 (engine default), 4, 8 or `affinity` (the mask's CPU count)."""
    if value in ("", "0"):
        return 0
    if value == "affinity":
        if not affinity:
            raise EvidenceError("--worker-threads affinity requires --affinity")
        count = bin(int(affinity, 16)).count("1")
    else:
        try:
            count = int(value)
        except ValueError as exc:
            raise EvidenceError("--worker-threads must be 0, 4, 8 or affinity") from exc
    if count not in WORKER_POOL_THREADS:
        raise EvidenceError(f"worker pool overlays support {WORKER_POOL_THREADS} threads, not {count}")
    return count


def prepare_worker_overlay(project: Path, threads: int) -> dict:
    """A private configuration overlay of `project` whose override.cfg sets the pool size.

    Godot reads threading/worker_pool/max_threads once at startup, from project.godot
    and the override.cfg beside it; a source project has no other per-run source, and
    the checkout's own override.cfg is shared. The overlay (the project's own
    tools/continent_stream_benchmark_project.py) links the source/data/import
    directories, copies project.godot and the class/UID caches, and lives in the
    checkout's ignored .local directory. The original configuration is never edited.
    """
    tool = project / "tools" / "continent_stream_benchmark_project.py"
    if not tool.is_file():
        raise EvidenceError("worker pool overlay tool is missing from the project")
    spec = importlib.util.spec_from_file_location("rl_worker_pool_overlay_" + hashlib.sha256(
        str(tool.resolve()).encode()).hexdigest()[:12], tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if Path(module.SOURCE).resolve() != project.resolve():
        raise EvidenceError("worker pool overlay tool belongs to another checkout")
    folder = project.parent / ".local" / "crowd-benchmark-overlay" / f"threads-{threads}"
    try:
        manifest = module.prepare(folder, threads)
    except (ValueError, RuntimeError, OSError) as exc:
        raise EvidenceError(f"worker pool overlay could not be prepared: {exc}") from exc
    overlay = Path(manifest["project"])
    if manifest.get("worker_threads") != threads or not (overlay / "project.godot").is_file() \
            or f"worker_pool/max_threads={threads}" not in (overlay / "override.cfg").read_text(encoding="utf-8"):
        raise EvidenceError("worker pool overlay does not set the requested pool size")
    return manifest


def validate_steady_pacing(cell: dict, request: dict) -> None:
    required = request["mode"] == "windowed" and request["renderer"] == "gl_compatibility"
    for boundary in ("preSample", "afterSample"):
        state = _object(cell.get("pacing", {}).get(boundary), cell["id"] + ".pacing." + boundary)
        if state.get("frameCap") != request["fps_cap"] \
                or (request["mode"] == "windowed" and state.get("vsyncMode") != 0) \
                or state.get("warmingRequired") is not required \
                or any(state.get(key) is not False for key in ("arrivalPending", "arrivalVisible", "headWarmupActive")):
            raise EvidenceError(f"{cell['id']}: steady pacing/arrival differs at {boundary}")
        warm = _object(state.get("cameraWarmup"), cell["id"] + ".cameraWarmup")
        if warm.get("active") is not False or (required and (warm.get("view") != 240 or warm.get("views") != 240 \
                or warm.get("frames_per_view") != 2 or warm.get("timed_out") is not False)):
            raise EvidenceError(f"{cell['id']}: complete warming differs at {boundary}")


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
    if request.get("profile_seed_user_dir") and os.path.normcase(str(Path(user_dir).resolve())) \
            != os.path.normcase(str(Path(request["profile_seed_user_dir"]).resolve())):
        raise EvidenceError("startup acknowledgement did not use the directory --seed-profile filled")
    return data


def validate_gpu_timestamps(summary: dict, name: str) -> None:
    """Refuse a viewport GPU time no frame can take (MOB-C6a, measured on the iGPU proxy).

    viewport_get_measured_render_time_gpu occasionally returns a wrapped
    timestamp difference (about 1.8e13 ms: 2^64 ns) on the Intel iGPU. One such
    frame turns the cell's mean world GPU time into nonsense, so the run is
    rejected for a rerun instead of feeding a renderer comparison.
    """
    for metric in GPU_TIME_METRICS:
        value = summary.get(metric)
        maximum = value.get("max") if isinstance(value, dict) else None
        if isinstance(maximum, (int, float)) and maximum > MAX_PLAUSIBLE_GPU_MILLISECONDS:
            raise EvidenceError(f"{name}: {metric} max {maximum:.3g} ms is a wrapped GPU timestamp "
                                "(engine/driver timer), not a frame; rerun")


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


def validate_resource_admission(backends: dict, request: dict, label: str) -> None:
    requested = request.get("resource_admission", "legacy")
    # Legacy checkpoints may predate admission instrumentation. An explicit
    # Rust request must prove its cached request, budget and instantiated owner.
    if "resourceAdmission" not in backends and requested == "legacy":
        return
    admission = _object(backends.get("resourceAdmission"), label + ".resourceAdmission")
    budget = request.get("resource_admission_budget_mib", 768) * 1048576
    if admission.get("requested_mode") != requested or admission.get("requested_estimate_budget") != budget:
        raise EvidenceError(f"{label}: actual admission request/budget differs")
    if admission.get("mode") != requested:
        raise EvidenceError(f"{label}: admission backend differs or fell back")
    if requested == "legacy":
        if admission.get("requested") is not False:
            raise EvidenceError(f"{label}: admission was unexpectedly enabled")
        return
    if admission.get("reason") != "rust_global_admission" or admission.get("estimate_budget") != budget:
        raise EvidenceError(f"{label}: Rust admission backend/budget is unavailable")
    for key in ("admitted", "denied", "publication_grants", "publication_deferrals", "transition_failures"):
        _integer(admission.get(key), label + ".resourceAdmission." + key)
    if admission["transition_failures"] != 0:
        raise EvidenceError(f"{label}: admission lifecycle transition failed")
    graph = _object(admission.get("dependency_graph"), label + ".admissionDependencyGraph")
    if _object(graph.get("failures"), label + ".admissionGraphFailures"):
        raise EvidenceError(f"{label}: admission dependency graph failed")
    _integer(graph.get("registrations"), label + ".admissionGraphRegistrations")
    native = _object(admission.get("native"), label + ".admissionNative")
    for key in ("reserved", "loading", "ready", "active", "retiring", "cancelled", "old_epoch", "denials", "forced_sync"):
        _integer(native.get(key), label + ".admissionNative." + key)


def validate_runtime(runtime: dict, request: dict, renderer: str, quality: str,
                     body_cap: int, label: str) -> dict:
    settings = _object(runtime.get("effectiveSettings"), label + ".effectiveSettings")
    backends = _object(runtime.get("activeBackends"), label + ".activeBackends")
    expected = {"quality": quality, "bodyCap": body_cap, "frameCap": request["fps_cap"],
                "renderer": renderer, "rootSize": list(request["resolution"])}
    if request.get("settings_profile") in PERFORMANCE_PROFILES:
        # 0: the preset uncapped for GPU-time comparisons (configure_settings_profile).
        if request["fps_cap"] not in (PERFORMANCE_PROFILES[request["settings_profile"]], 0):
            raise EvidenceError(f"{label}: frame cap differs from named Performance profile")
        expected.update(quality="low", bodyCap=60, renderScale=PERFORMANCE_RENDER_SCALES[request["settings_profile"]],
                        textureQuality="half", textureSkip=1, appearance="painted_ground")
        expected.update(clothBudget=0, shadowsPreference=False, sunShadowsEnabled=False,
                        particlesEnabled=True, decorativeGrass=False, nameDistanceMetres=20.0)
    if request.get("mode") == "windowed" and any(
            name in UNDEAD_CELLS or name == GAUNTLET_CELL
            for name in selected_cells(request["cells"], bool(request.get("replay")))):
        expected["vsyncMode"] = 0
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
    try:
        validate_remote(backends.get("remotePresentation"), backends.get("remoteCoverage"),
                        request.get("remote_presentation", "legacy"), label)
    except ValueError as exc:
        raise EvidenceError(str(exc)) from exc
    requested_runtime = request.get("client_runtime", "legacy")
    # Older legacy checkpoints predate this optional service. Native requests
    # require its actual instantiated backend at every observed boundary.
    if "clientRuntime" in backends or requested_runtime != "legacy":
        runtime = _object(backends.get("clientRuntime"), label + ".clientRuntime")
        expected_presentation = "mixed" if requested_runtime == "rust" else "legacy"
        if runtime.get("requested") != requested_runtime or runtime.get("mode") != requested_runtime \
                or runtime.get("presentation_backend") != expected_presentation or runtime.get("mismatches") != 0:
            raise EvidenceError(f"{label}: actual client runtime differs or fell back")
        if requested_runtime in ("compare", "rust", "services") and runtime.get("native_available") is not True:
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
    validate_resource_admission(backends, request, label)
    try:
        validate_prepared(backends, request, label)
    except ValueError as exc:
        raise EvidenceError(str(exc)) from exc
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
    validate_profile_frames(data, request)
    errors = ERROR_PATTERN.findall(log)
    if errors:
        raise EvidenceError(f"engine log contains {len(errors)} script/load/error lines")
    if GAUNTLET_CELL in selected_cells(request["cells"], bool(request.get("replay"))):
        validate_gauntlet_cohort(data)
    if data.get("benchmark") != "crowd_presentation" or type(data.get("schemaVersion")) is not int \
            or data.get("schemaVersion") != 1:
        raise EvidenceError("unexpected benchmark/schema")
    if _integer(data.get("failureCount"), "failureCount") != 0 or data.get("failures") != []:
        raise EvidenceError("benchmark reports failures or omits failure metadata")
    if data.get("functionalOnly") is True:
        raise EvidenceError("functional-only placement probe is not accepted timing evidence")
    if any(name in UNDEAD_CELLS for name in selected_cells(request["cells"], bool(request.get("replay")))):
        cohort = data.get("creatureCohort", {})
        profiles = [{"model": species, **profile, "health": health, "scale": 1.0}
                    for (species, profile), health in zip(UNDEAD_SPECIES.items(), (400, 262, 1088))]
        if data.get("map") != "twinbrook" or data.get("centreTile") != [453, 168] \
                or cohort.get("id") != "twinbrook-onslaught-v1" or cohort.get("profiles") != profiles \
                or cohort.get("sourceWaveMaximum") != 500 \
                or data.get("creatureFootprints") != {str(p["actorType"]): p["footprint"] for p in profiles} \
                or data.get("prewarmed", {}).get("creatureModels") != list(UNDEAD_SPECIES):
            raise EvidenceError("production undead cohort/map/prewarm differs")
    if data.get("headless") is not (request["mode"] == "headless"):
        raise EvidenceError("actual display mode differs from requested mode")
    if request["mode"] == "windowed" and data.get("renderingMethod") != request["renderer"]:
        raise EvidenceError("actual renderer differs from requested renderer")
    driver = engine_arg_value(request.get("engine_args"), "--rendering-driver")
    if driver and data.get("renderingDriver") != driver:
        # Godot falls back to another driver when the requested one fails to start.
        raise EvidenceError("actual rendering driver differs from the requested --rendering-driver")
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
    if request["mode"] == "windowed" and "window_mode" in request:
        expected_mode = 0 if request["window_mode"] == "windowed" else (
            3 if measurement.get("windowPlatform") == "macOS" else 4)
        if (measurement.get("requestedWindowMode") != request["window_mode"]
                or measurement.get("requestedDisplayWindowMode") != expected_mode
                or measurement.get("actualWindowMode") != expected_mode):
            raise EvidenceError("actual window mode differs from requested window mode")
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
                        "clothBodies": 0 if request.get("settings_profile") in PERFORMANCE_PROFILES else 8}
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
    validate_worker_pool(data, request)
    validate_overhead_diagnostics(data, request)
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
    if request.get("settings_profile") in PERFORMANCE_PROFILES:
        seed_dir = request.get("settings_seed_user_dir")
        actual = _object(data.get("runtimeBuild"), "runtimeBuild").get("userDataDir")
        if not isinstance(seed_dir, str) or not isinstance(actual, str) \
                or os.path.normcase(str(Path(actual).resolve())) != os.path.normcase(str(Path(seed_dir).resolve())):
            raise EvidenceError("Performance runtime did not use the exact seeded user directory")
    if request.get("profile_seed_user_dir"):
        actual = _object(data.get("runtimeBuild"), "runtimeBuild").get("userDataDir")
        if not isinstance(actual, str) or os.path.normcase(str(Path(actual).resolve())) \
                != os.path.normcase(str(Path(request["profile_seed_user_dir"]).resolve())):
            raise EvidenceError("runtime did not use the directory --seed-profile filled")
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
            wanted_count = (22 if name == GAUNTLET_CELL else
                            int(name.rsplit("-", 1)[-1]) + 1 if name in UNDEAD_CELLS else
                            int(name.rsplit("-", 1)[-1]) if name.rsplit("-", 1)[-1].isdigit() else 1)
            if count != wanted_count:
                raise EvidenceError(f"{name}: actor population differs from requested cell")
        try:
            validate_remote_cell(cell, request.get("remote_presentation", "legacy"))
        except ValueError as exc:
            raise EvidenceError(str(exc)) from exc
        census = _object(cell.get("census"), name + ".census")
        if name in UNDEAD_CELLS:
            validate_undead_cell(cell)
        if name == GAUNTLET_CELL:
            validate_gauntlet_cell(cell)
        points = ("afterSpawn", "preSample", "afterSample") if name in UNDEAD_CELLS or name == GAUNTLET_CELL else ("afterSpawn", "afterSample")
        for point in points:
            sample = _object(census.get(point), name + "." + point)
            nodes = _integer(sample.get("nodes"), name + ".nodes", 1)
            built = _integer(sample.get("builtBodies"), name + ".builtBodies")
            deferred = _integer(sample.get("deferred"), name + ".deferred")
            if built + deferred != nodes or (not request.get("replay") and nodes != count):
                raise EvidenceError(f"{name}: actor/body census is inconsistent")
            body_fields = ("visibleBuiltBodies", "inFrustumBuiltBodies", "bodyTierFull", "bodyTierHalf", "bodyTierQuarter", "bodyTierPaused")
            if name in UNDEAD_CELLS or name == GAUNTLET_CELL or any(field in sample for field in body_fields):
                actual = {field: _integer(sample.get(field), name + "." + field) for field in body_fields}
                if not 0 <= actual["inFrustumBuiltBodies"] <= actual["visibleBuiltBodies"] <= built \
                        or sum(actual[field] for field in body_fields[2:]) != built:
                    raise EvidenceError(f"{name}: built-body visibility/tier census is inconsistent")
        if name in UNDEAD_CELLS or name == GAUNTLET_CELL:
            validate_steady_pacing(cell, request)
        runtime = _object(cell.get("effectiveRuntime"), name + ".effectiveRuntime")
        observed_native.append(validate_runtime(runtime, request, data.get("renderingMethod"),
                                               data["graphicsQuality"], policy["bodyCap"], name))
        if name.startswith("traversal-"):
            route = _object(cell.get("route"), name + ".route")
            if cell.get("status") != "complete" or route.get("kind") != "synthetic_client_streaming" \
                    or route.get("serverNavigationCertified") is not False:
                raise EvidenceError(f"{name}: invalid traversal classification")
            legs = route.get("legs")
            expected_legs = route_legs_for(name)
            if not isinstance(legs, list) or [leg.get("id") for leg in legs if isinstance(leg, dict)] != expected_legs:
                raise EvidenceError(f"{name}: incomplete deterministic route")
            for leg in legs:
                if leg.get("success") is not True or _object(leg.get("readiness"), name + ".leg.readiness").get("ready") is not True:
                    raise EvidenceError(f"{name}: failed/unready route leg")
                _number(leg.get("milliseconds"), name + ".leg.milliseconds")
            if "routeVersion" in route or name == "traversal-seam-walk":
                validate_route_v2(route, frames, name)
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
                validate_gpu_timestamps(summary, name)
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
            expected_active = count - 1 if name.startswith("combat-") or name == GAUNTLET_CELL else \
                (1 if name.startswith("traversal-") else (count + 1) // 3 if count > 1 else 0)
            expected_moving = 16 if name == "combat-heat-bolt-160" else (
                0 if name.startswith("combat-") or name == GAUNTLET_CELL else (expected_active + 1) // 2)
            if (active, moving, fighting) != (expected_active, expected_moving, expected_active - expected_moving):
                raise EvidenceError(f"{name}: activity workload differs from requested cell")
            if active and not name.startswith("traversal-"):
                _number(cell.get("packetsPerSecond"), name + ".packetsPerSecond", .000001)
                ticks = validate_distribution(summary.get("tickFrameMilliseconds"), name + ".tickFrames")
                if ticks["count"] > frames or _number(summary.get("packetsPerFrame", {}).get("mean"),
                                                      name + ".packetsPerFrame.mean", .000001) <= 0:
                    raise EvidenceError(f"{name}: no observed packet activity")
        if name == "combat-heat-bolt-160":
            try:
                validate_heat_bolt_cell(cell, request)
            except HeatBoltEvidenceError as exc:
                raise EvidenceError(str(exc)) from exc
        capture = cell.get("boundaryCapture")
        if request.get("capture_boundaries", False):
            capture = _object(capture, name + ".boundaryCapture")
            if request.get("mode") != "windowed" or capture.get("requested") is not True \
                    or capture.get("status") != "captured" or capture.get("outsideSample") is not True \
                    or capture.get("boundary") != "after_sample_before_despawn" \
                    or capture.get("viewport") != "world" or not isinstance(capture.get("path"), str):
                raise EvidenceError(f"{name}: requested boundary image was not captured")
            _integer(capture.get("width"), name + ".capture.width", 1)
            _integer(capture.get("height"), name + ".capture.height", 1)
            _integer(capture.get("captureMicroseconds"), name + ".capture.microseconds")
            if not isinstance(capture.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", capture["sha256"]):
                raise EvidenceError(f"{name}: boundary image identity missing")
        elif capture is not None:
            raise EvidenceError(f"{name}: boundary image was not requested")
        measured.append(name)
    if request.get("resource_admission") == "rust" and any(str(cell["id"]).startswith("traversal-") for cell in cells):
        if not any(backend["resourceAdmission"]["admitted"] > 0
                   and backend["resourceAdmission"]["publication_grants"] > 0
                   and backend["resourceAdmission"]["dependency_graph"]["registrations"] > 0
                   for backend in observed_native):
            raise EvidenceError("requested Rust route admission did not execute real launch/publication/dependency work")
    try:
        validate_soak(data, request["cells"])
    except ValueError as exc:
        raise EvidenceError(str(exc)) from exc
    mode = request.get("native_presentation", "off")
    if request.get("client_runtime") == "compare" and not any(
            _integer(backend["clientRuntime"].get("comparisons"), "clientRuntime.comparisons") > 0
            for backend in observed_native):
        raise EvidenceError("requested Rust comparison runtime did not execute")
    rust_effects = [backend.get("rustSpellFlights", {}) for backend in observed_native]
    if request.get("rust_effects", "legacy") == "heat_bolt":
        if not any(v.get("frames", 0) > 0 for v in rust_effects) or any(
                v.get("fallbacks", 0) or v.get("admitted_legacy", 0) for v in rust_effects):
            raise EvidenceError("Rust spell family never executed cleanly or fell back")
    elif any(v.get("frames", 0) > 0 for v in rust_effects):
        raise EvidenceError("Rust spell family ran despite being disabled")
    presentations = [backend["presentation"] for backend in observed_native]
    if mode in ("cape", "both", "all") and (not any(p["nativeCapeCalls"] > 0 for p in presentations)
                                            or any(p["capeFallbackCalls"] for p in presentations)):
        raise EvidenceError("requested native cape path was not exercised without fallbacks")
    for family, modes in (("flight", ("flight", "both", "all")), ("impact", ("world", "all"))):
        if mode in modes and (not any(p[family]["buildSuccesses"] > 0 for p in presentations)
                              or any(p[family]["buildFallbacks"] for p in presentations)):
            raise EvidenceError(f"requested native {family} path was not exercised without fallbacks")
    return {"valid": True, "qualification": "pending_content" if pending else
            "diagnostic" if request.get("diagnostics") or request.get("attribution") else "screening",
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
    fixture = client / GAUNTLET_FIXTURE
    if fixture.is_file():
        files.append(fixture)
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
    # Navigation can show neighbouring regions, so conservatively attest the
    # complete small picture catalog, including every private section image.
    backgrounds = client / "data/maps/map-backgrounds.json"
    if backgrounds.is_file():
        for row in read_json(backgrounds).get("maps", {}).values():
            for picture in ([row] if row.get("path") else []) + list(row.get("sections", {}).values()):
                resource = picture.get("path", "")
                if not isinstance(resource, str) or not resource.startswith("res://"):
                    raise EvidenceError("map background identity has no resource path")
                path = (client / resource.removeprefix("res://")).resolve()
                if not path.is_relative_to(client.parent.resolve()) or not path.is_file():
                    raise EvidenceError("map background identity is missing/outside the runtime repository")
                files.append(path)
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
        visited = set()
        while registry[name].get("alias"):
            if name in visited or registry[name]["alias"] not in registry:
                raise EvidenceError("map asset identity has an invalid alias")
            visited.add(name)
            name = registry[name]["alias"]
        pending.append((client / registry[name]["manifest"].removeprefix("res://")).resolve())
    seen: set[Path] = set()
    vram_directories: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        if not path.is_relative_to(client.parent.resolve()) or not path.is_file():
            raise EvidenceError(f"map dependency missing or outside runtime repository: {path}")
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
        chunks = doc.get("streamingChunks", {}).get("chunks", [])
        glb = doc.get("asset", {}).get("glb")
        # WorldLoader takes the chunk-stream path before importing asset.glb.
        # Published stream roots deliberately omit that obsolete monolithic GLB.
        # Every real chunk manifest/mesh and shared resource is still required.
        if glb and not chunks:
            refs.append(glb)
        refs += [c["manifest"] for c in chunks if "manifest" in c]
        for ref in refs:
            pending.append((client / ref[6:] if ref.startswith("res://") else path.parent / ref).resolve())
    return list(dict.fromkeys(files))


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


def validate_profile_frames(data: dict, request: dict) -> None:
    if not request.get("attribution"):
        return
    if request.get("executable_mode", "project") != "project":
        raise EvidenceError("detailed attribution is source-project-only; exports are unsupported")
    measurement = data.get("measurement")
    if not isinstance(measurement, dict) or measurement.get("attribution") is not True:
        raise EvidenceError("detailed attribution request was not applied")
    if measurement.get("attributionScope") != "source-project-only":
        raise EvidenceError("detailed attribution source-project scope is missing")
    for cell in data.get("cells", []):
        if cell.get("status") == "unavailable_content":
            continue
        frames = cell.get("profileFrames")
        series = cell.get("frameSeries")
        if (cell.get("profileSchemaVersion") != 1 or not isinstance(frames, list)
                or not isinstance(series, list) or len(frames) != cell.get("frames")
                or len(series) != len(frames) or type(cell.get("count")) is not int):
            raise EvidenceError("detailed frame profile is incomplete")
        for index, row in enumerate(frames):

            if (not isinstance(row, dict) or row.get("listener_timing_valid") is not True
                    or row.get("listener_timing_errors") != []
                    or not isinstance(row.get("listener_layout_scope"), str)
                    or not row["listener_layout_scope"].startswith("stable synchronous original callables")):
                raise EvidenceError("detailed listener timings require stable original callable layouts")
            if (not isinstance(row, dict) or row.get("index") != index or row.get("aligned") is not True
                    or type(row.get("engine_frame")) is not int
                    or row["engine_frame"] < 0
                    or row["engine_frame"] != row.get("gate_engine_frame")
                    or row.get("frame_ms") != cell["frameSeries"][index]):
                raise EvidenceError("detailed frame clocks are misaligned")
            if not all(isinstance(row.get(key), dict) for key in ("phases", "microseconds", "manual", "listeners", "census")):
                raise EvidenceError("detailed frame attribution fields are missing")
            if row.get("packet_origin_engine_frame") != row["engine_frame"]:
                raise EvidenceError("detailed packet origin frame differs from completed draw")
            phase_frames = row.get("phase_frames", {})
            if not isinstance(phase_frames, dict):
                raise EvidenceError("detailed phase boundary clocks are missing")
            for name in ("origin", "process_end", "draw_end") + (() if request.get("mode") == "headless" else ("draw_start",)):
                if phase_frames.get(name) != row["engine_frame"]:
                    raise EvidenceError("detailed phase boundary frame differs from completed draw")
            metric_frames = row.get("metric_frames")
            if not isinstance(metric_frames, dict):
                raise EvidenceError("detailed timer frame origins are missing")
            if not {"main_process_inclusive", "half_rate_step"} <= metric_frames.keys():
                raise EvidenceError("detailed Main/gate timer origins are incomplete")
            for metric in metric_frames.values():
                if (not isinstance(metric, dict) or set(metric) != {"origin", "execution"}
                        or any(not isinstance(metric[key], list) or not metric[key]
                               or any(type(frame) is not int or frame != row["engine_frame"] for frame in metric[key])
                               for key in ("origin", "execution"))):
                    raise EvidenceError("detailed timer execution frame differs from completed draw")
            tiers = row["census"].get("tiers", {})
            if (not isinstance(tiers, dict) or set(tiers) != {"full", "half", "quarter", "paused"}
                    or any(type(value) is not int or value < 0 for value in tiers.values())
                    or sum(tiers.values()) != cell["count"]):
                raise EvidenceError("detailed frame tier census does not cover every actor")
