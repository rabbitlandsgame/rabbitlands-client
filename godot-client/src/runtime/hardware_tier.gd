extends RefCounted
## First-run graphics defaults chosen from the hardware.
##
## Every install used to start on High quality, full map textures, 100 % 3D
## resolution and 160 crowd bodies. On an integrated GPU with 8 GB of memory
## that measured 24-27 FPS in a market crowd and 7.4-7.6 GB of process memory,
## which does not fit; the Performance preset on the same machine held 30 FPS
## in 3.2-3.35 GB (perf audit 2026-11, GPU-01, RAM-01, TEXTURES-08). So a fresh
## profile is classified once, before the texture tier is read and cached for
## the session, and the tier's values are saved like any other preference:
##
##   low    an integrated (not Apple silicon), software or virtual GPU, about
##          8 GB of memory or less, or four CPU threads or fewer: the
##          Performance preset;
##   medium otherwise, about 16 GB of memory or less, or eight CPU threads or
##          fewer: recorded, but High as before (see TIER_SETTINGS);
##   high   everything else: the defaults as they were.
##
## Only a profile with no [graphics] section is seeded, so a player who has
## ever saved a graphics preference is never touched, and once seeded the
## section exists and the choice is stable. A launch that pins graphics or
## measures (the environment overrides, a `--script` main loop, the crowd
## benchmark, headless, the browser build) is left alone and seeds nothing.
## The renderer is not part of this: Automatic stays Automatic.
##
## The script declares no `class_name` (callers preload it): it runs from an
## autoload, before anything has forced the global class cache up to date.

const OptimizationProfile := preload("res://src/runtime/optimization_profile.gd")

const SETTINGS_PATH := "user://eloria_hud.cfg"
const SECTION := "graphics"
## The tier a fresh profile was given, saved beside the values it seeded. It is
## a record, not a setting: nothing re-applies it.
const TIER_KEY := "hardware_tier"
enum Tier { LOW, MEDIUM, HIGH }
const TIER_NAMES: Array[String] = ["low", "medium", "high"]

## A nominal 8 GB or 16 GB machine reports a little less physical memory than
## that (firmware and integrated-GPU reservations), so each limit sits half a
## GiB above its size.
const GIB := 1 << 30
const LOW_MEMORY_BYTES := (GIB >> 1) * 17
const MEDIUM_MEMORY_BYTES := (GIB >> 1) * 33
const LOW_CPU_THREADS := 4
const MEDIUM_CPU_THREADS := 8

## What each tier writes to [graphics], in the settings file's own spelling.
## LOW is the settings window's Performance preset (main.gd
## `_apply_performance_preset`; the crowd benchmark's PERFORMANCE_GRAPHICS)
## without its renderer. MEDIUM and HIGH pin only the quality, and both keep
## High: a discrete GPU with 16 GB or eight threads is not the weak hardware
## these defaults are for, and Medium there would trade RL heads and SSIL for
## time that machine has. Medium as its default waits for the owner's call on
## the per-class budgets; the tier is recorded meanwhile.
## LOW's crowd setting follows the graphics quality (`crowd_bodies_auto`,
## 60 bodies at Low) rather than saving 60, as the Performance preset does
## (Low actor tier, 2026-11-02); a profile this tier seeded with 60 before
## that reads as following the quality (CrowdPresentation.follows_quality).
const TIER_SETTINGS := {
	Tier.LOW: {"quality": "low", "appearance": "painted_ground", "fps_limit": 30,
		"vsync_mode": "off", "render_scale": 0.75, "map_texture_quality": "half",
		"crowd_bodies_auto": true, "swaying_capes": 0, "shadows": false, "particles": true,
		"decorative_grass": false, "name_distance": 20.0},
	Tier.MEDIUM: {"quality": "high"},
	Tier.HIGH: {"quality": "high"},
}

## Measurement switches of the 2026-11 performance work (wave 2). Each one is
## in OVERRIDE_VARIABLES, and `--memory-class=` blocks seeding like the
## optimisation-profile arguments, so a launch that sets one never seeds a
## first run. The getters further down are the one place their values are
## parsed, so every consumer agrees on spelling and defaults.
##
## RABBITLANDS_MEMORY_CLASS / --memory-class=  small, medium or large: the
##     memory budget class instead of the probed one (memory_class_override).
## ELORIA_WORLD_DISTANCE  off: no world distance pass, for A/B captures
##     (world_distance_mode, world_distance_enabled).
## ELORIA_ACTOR_IMAGES  legacy: actor images parsed as before the actor image
##     extension; nomips: decoded actor images get no generated mips
##     (actor_images_mode).
## ELORIA_ACTOR_VRAM_SELF_TEST  a directory such as assets/actors/native/races
##     whose actor sidecar index the package smoke launch decodes
##     (actor_vram_self_test_dir).
## RABBITLANDS_ACTOR_GEOMETRY  off: actor meshes as parsed, no cooked LODs;
##     generate: cook them at runtime, development builds only
##     (actor_geometry_mode). It takes only its three mode names, as the
##     applier does: no off/on spellings.
const MEMORY_CLASS_VARIABLE := "RABBITLANDS_MEMORY_CLASS"
const MEMORY_CLASS_ARGUMENT := "--memory-class="
const MEMORY_CLASSES: Array[String] = ["small", "medium", "large"]
const WORLD_DISTANCE_VARIABLE := "ELORIA_WORLD_DISTANCE"
const WORLD_DISTANCE_MODES: Array[String] = ["auto", "off"]
const ACTOR_IMAGES_VARIABLE := "ELORIA_ACTOR_IMAGES"
const ACTOR_IMAGES_MODES: Array[String] = ["auto", "legacy", "nomips"]
const ACTOR_VRAM_SELF_TEST_VARIABLE := "ELORIA_ACTOR_VRAM_SELF_TEST"
const ACTOR_GEOMETRY_VARIABLE := "RABBITLANDS_ACTOR_GEOMETRY"
const ACTOR_GEOMETRY_MODES: Array[String] = ["sidecar", "off", "generate"]
## Spellings the world-distance and actor-image switches also accept for their
## off mode, and for their default (resolve_switch); the self-test directory
## reads an off spelling as no self-test. Actor geometry takes neither.
const OFF_SPELLINGS: Array[String] = ["off", "0", "false", "no", "legacy"]
const ON_SPELLINGS: Array[String] = ["on", "1", "true", "yes"]

## Environment variables that override graphics, crowd or runtime choices for a
## developer, a test or a measurement. Any of them set means the launch is not
## a player's first run. The optimisation profile's own variables are added
## from its table. RABBITLANDS_LAUNCH_CONTEXT is deliberately absent: the
## updater sets it on every ordinary launch. The content-digest switches
## (RABBITLANDS_CONTENT_DIGEST*) change no graphics and are left out.
const OVERRIDE_VARIABLES: Array[String] = ["ELORIA_LOOK", "ELORIA_LOOK_QUALITY",
	"ELORIA_LOOK_QUALITY_TRIM", "ELORIA_VRAM_TEXTURES", "RABBITLANDS_CROWD_BODY_CAP",
	"RABBITLANDS_CROWD_PRESENTATION", "RABBITLANDS_CROWD_TUNING",
	"RABBITLANDS_CROWD_BENCH_START_TOKEN", "RABBITLANDS_RESOURCE_BUDGET_MIB",
	"RABBITLANDS_CAPE_MATH", MEMORY_CLASS_VARIABLE, WORLD_DISTANCE_VARIABLE,
	ACTOR_IMAGES_VARIABLE, ACTOR_VRAM_SELF_TEST_VARIABLE, ACTOR_GEOMETRY_VARIABLE]
## Engine switches that start a tool, test or benchmark main loop.
const TOOL_ARGUMENTS: Array[String] = ["--script", "-s", "--editor", "-e"]

## Adapter names, lower-cased. D3D12 reports an Intel iGPU as discrete and the
## Compatibility renderer reports no type at all, so the name decides there.
const SOFTWARE_PATTERN := "llvmpipe|lavapipe|softpipe|swiftshader|microsoft basic render"
## Intel's discrete cards carry an A/B model number (Arc A770, Arc Pro A40,
## Arc B580) or are the Xe MAX; Arc Graphics, Arc 140V and the rest are iGPUs.
const INTEL_DISCRETE_PATTERN := "arc(\\(tm\\))?\\s+(pro\\s+)?[ab]\\d{2,3}|xe max|data center"
## AMD APUs: plain "Radeon Graphics", "Vega 8 Graphics", "780M", "8060S",
## "R7 Graphics", "HD 7660G/D" and the Steam Deck's custom GPU. Discrete
## cards name a series (RX, Pro, HD 7xxx, R9 390) instead.
const AMD_INTEGRATED_PATTERN := "radeon(\\(tm\\))?\\s+graphics|vega\\s*\\d+\\s*graphics" \
	+ "|radeon(\\(tm\\))?\\s+\\d{3}m\\b|radeon(\\(tm\\))?\\s+\\d{4}s\\b" \
	+ "|radeon(\\(tm\\))?\\s+r[2-7]\\s+graphics|radeon\\s+hd\\s+\\d{4}[dg]\\b|amd custom gpu"

## What the classifier reads from this machine.
static func probe() -> Dictionary:
	var memory := OS.get_memory_info()
	return {
		"adapter_type": int(RenderingServer.get_video_adapter_type()),
		"adapter_name": RenderingServer.get_video_adapter_name(),
		"adapter_vendor": RenderingServer.get_video_adapter_vendor(),
		"rendering_driver": RenderingServer.get_current_rendering_driver_name(),
		"physical_memory": int(memory.get("physical", -1)),
		"cpu_threads": OS.get_processor_count(),
	}

## "integrated", "discrete", "apple", "software", "virtual" or "unknown".
## Vulkan's device type is trusted; a name only decides where the type cannot.
## Apple silicon is integrated by type but is judged like a discrete GPU, by
## memory and threads alone: the measurements behind LOW are Intel and AMD
## iGPUs, which Windows lets share at most half of system memory.
static func adapter_class(inputs: Dictionary) -> String:
	var type := int(inputs.get("adapter_type", RenderingDevice.DEVICE_TYPE_OTHER))
	var named := _named_class("%s %s" % [inputs.get("adapter_name", ""),
		inputs.get("adapter_vendor", "")])
	if type == RenderingDevice.DEVICE_TYPE_CPU or named == "software":
		return "software"
	if named == "apple":
		return named
	if type == RenderingDevice.DEVICE_TYPE_VIRTUAL_GPU:
		return "virtual"
	var typed := {RenderingDevice.DEVICE_TYPE_INTEGRATED_GPU: "integrated",
		RenderingDevice.DEVICE_TYPE_DISCRETE_GPU: "discrete"}
	if typed.has(type) and str(inputs.get("rendering_driver", "")) != "d3d12":
		return typed[type]
	return named if named != "unknown" else str(typed.get(type, "unknown"))

static func _named_class(text: String) -> String:
	var name := text.to_lower()
	if _matches(name, SOFTWARE_PATTERN):
		return "software"
	if name.contains("apple"):
		return "apple"
	if name.contains("intel"):
		return "discrete" if _matches(name, INTEL_DISCRETE_PATTERN) else "integrated"
	if name.contains("radeon") or name.contains("amd custom gpu"):
		return "integrated" if _matches(name, AMD_INTEGRATED_PATTERN) else "discrete"
	for word: String in ["nvidia", "geforce", "quadro"]:
		if name.contains(word):
			return "discrete"
	for word: String in ["adreno", "mali", "powervr"]:
		if name.contains(word):
			return "integrated"
	return "unknown"

static func _matches(text: String, pattern: String) -> bool:
	var expression := RegEx.new()
	expression.compile(pattern)
	return expression.search(text) != null

## The tier `inputs` (see `probe`) fall in, with what put them there.
static func classify(inputs: Dictionary) -> Dictionary:
	var adapter := adapter_class(inputs)
	var memory := int(inputs.get("physical_memory", -1))
	var threads := int(inputs.get("cpu_threads", 0))
	var basis := PackedStringArray()
	if adapter in ["integrated", "software", "virtual"]:
		basis.append(adapter + "_gpu")
	if memory > 0 and memory <= LOW_MEMORY_BYTES:
		basis.append("memory")
	if threads > 0 and threads <= LOW_CPU_THREADS:
		basis.append("cpu_threads")
	var tier := Tier.LOW
	if basis.is_empty():
		tier = Tier.MEDIUM
		if memory > 0 and memory <= MEDIUM_MEMORY_BYTES:
			basis.append("memory")
		if threads > 0 and threads <= MEDIUM_CPU_THREADS:
			basis.append("cpu_threads")
		if basis.is_empty():
			tier = Tier.HIGH
	return {"tier": TIER_NAMES[tier], "adapter_class": adapter,
		"adapter_type": int(inputs.get("adapter_type", RenderingDevice.DEVICE_TYPE_OTHER)),
		"adapter": str(inputs.get("adapter_name", "")),
		"rendering_driver": str(inputs.get("rendering_driver", "")),
		"memory_gib": snappedf(memory / float(GIB), 0.1) if memory > 0 else -1.0,
		"cpu_threads": threads, "basis": Array(basis)}

## This launch's arguments and overrides, for `blocker`.
static func launch_context() -> Dictionary:
	var variables: Array[String] = []
	variables.append_array(OVERRIDE_VARIABLES)
	variables.append(OptimizationProfile.ENVIRONMENT)
	for definition: Dictionary in OptimizationProfile.FEATURES.values():
		variables.append(str(definition.environment))
	var overrides := PackedStringArray()
	for variable: String in variables:
		if not OS.get_environment(variable).strip_edges().is_empty():
			overrides.append(variable)
	return {"web": OS.has_feature("web"), "headless": DisplayServer.get_name() == "headless",
		"engine_args": OS.get_cmdline_args(), "user_args": OS.get_cmdline_user_args(),
		"overrides": overrides}

## Why this launch must not seed a profile, or "" when it may.
static func blocker(launch: Dictionary) -> String:
	if bool(launch.get("web", false)):
		return "web"
	if bool(launch.get("headless", false)):
		return "headless"
	for argument: String in launch.get("engine_args", PackedStringArray()):
		if argument in TOOL_ARGUMENTS or argument.begins_with("--script="):
			return "tool_launch"
	var prefixes: Array[String] = [OptimizationProfile.ARGUMENT, MEMORY_CLASS_ARGUMENT]
	for definition: Dictionary in OptimizationProfile.FEATURES.values():
		prefixes.append(str(definition.argument))
	for argument: String in launch.get("user_args", PackedStringArray()):
		for prefix: String in prefixes:
			if argument.begins_with(prefix):
				return "argument_override"
	if not (launch.get("overrides", PackedStringArray()) as PackedStringArray).is_empty():
		return "environment_override"
	return ""

## Seeds this machine's tier into a fresh profile. Call once at startup, before
## GraphicsOptions.active_texture_skip(); returns what `seed_profile` returns,
## for the startup log, plus the measurement `switches` a launch sets (none on
## a player's launch, whose log line is unchanged).
static func seed_first_run(path := SETTINGS_PATH) -> Dictionary:
	var result := seed_profile(path, probe(), launch_context())
	var set_switches := switches()
	if not set_switches.is_empty():
		result["switches"] = set_switches
	return result

## Classifies `inputs` and, when `launch` allows it and the file at `path` has
## no [graphics] section, writes the tier's values there. A file that exists
## but cannot be read is never overwritten. The result says what was decided
## (`classify`), whether it was written (`applied`) and why (`reason`).
static func seed_profile(path: String, inputs: Dictionary, launch: Dictionary) -> Dictionary:
	var result := classify(inputs)
	result["applied"] = false
	result["reason"] = blocker(launch)
	if not str(result.reason).is_empty():
		return result
	if has_saved_graphics(path):
		result["reason"] = "saved_settings"
		return result
	var config := ConfigFile.new()
	var error := config.load(path)
	if error != OK and FileAccess.file_exists(path):
		result["reason"] = "settings_unreadable"
		return result
	if config.has_section(SECTION):
		result["reason"] = "saved_settings"
		return result
	var tier := TIER_NAMES.find(str(result.tier))
	var values: Dictionary = TIER_SETTINGS[tier]
	for key: String in values:
		config.set_value(SECTION, key, values[key])
	config.set_value(SECTION, TIER_KEY, TIER_NAMES[tier])
	var save_error := config.save(path)
	if save_error != OK:
		result["reason"] = "save_failed: " + error_string(save_error)
		return result
	result["applied"] = true
	result["reason"] = "first_run"
	return result

## The tier a first run recorded in `config`, or "" for a profile that was
## never seeded (every profile from before this existed).
static func seeded_tier(config: ConfigFile) -> String:
	var value: Variant = config.get_value(SECTION, TIER_KEY, "")
	return value if value is String and value in TIER_NAMES else ""

## Whether the settings file at `path` has a [graphics] section, from its text.
## An established player's file also holds HUD presets and notes (about 0.5 MB,
## 14-20 ms to parse here), too much to parse on every launch only to learn the
## profile is not fresh. A header inside a note's text just leaves that profile
## unseeded, as every profile was before this existed.
static func has_saved_graphics(path: String) -> bool:
	if not FileAccess.file_exists(path):
		return false
	var text := FileAccess.get_file_as_string(path)
	var header := "[%s]" % SECTION
	return text.begins_with(header) or text.contains("\n" + header)

## `seeded_tier` for the settings file at `path`, read from its text for the
## same reason (only [graphics] has this key), for a caller without the parsed
## file.
static func recorded_tier(path: String) -> String:
	if not FileAccess.file_exists(path):
		return ""
	var expression := RegEx.new()
	expression.compile("(?m)^%s=\"(\\w+)\"" % TIER_KEY)
	var found := expression.search(FileAccess.get_file_as_string(path))
	var value := found.get_string(1) if found != null else ""
	return value if value in TIER_NAMES else ""

## The entry screen's Animate default for a profile without a saved choice: a
## low-tier first run starts on the still, saving a 1600x900 Theora decode on
## the main thread while login work runs (UI-13).
static func animated_backdrop_default(config: ConfigFile) -> bool:
	return seeded_tier(config) != TIER_NAMES[Tier.LOW]

# Measurement switches (see MEMORY_CLASS_VARIABLE above). The getters read the
# environment and the user arguments on every call: that is cheap, safe on a
# worker thread, and lets a test change them. A caller that needs one answer
# per session keeps the first. They print nothing; `switches()` (logged at
# startup by seed_first_run) reports every value that was ignored.

## The memory class this launch forces, or "" to use the probed class:
## {"memory_class", "source": "argument"|"environment"|"", "rejected"}.
static func memory_class_override() -> Dictionary:
	return resolve_memory_class(OS.get_environment(MEMORY_CLASS_VARIABLE),
		OS.get_cmdline_user_args())

## Pure form of `memory_class_override`. A valid `--memory-class=` argument
## wins over the environment, the last one when repeated, as for the
## optimisation-profile arguments; a value that is not a class is skipped and
## listed in "rejected" (the next valid source, or the probe, decides).
static func resolve_memory_class(environment_value: String,
		arguments: PackedStringArray) -> Dictionary:
	var memory_class := ""
	var source := ""
	var rejected := PackedStringArray()
	var candidates: Array[Array] = [[environment_value, "environment"]]
	for argument: String in arguments:
		if argument.begins_with(MEMORY_CLASS_ARGUMENT):
			candidates.append([argument.trim_prefix(MEMORY_CLASS_ARGUMENT), "argument"])
	for candidate: Array in candidates:
		var value := str(candidate[0]).strip_edges().to_lower()
		if value in MEMORY_CLASSES:
			memory_class = value
			source = str(candidate[1])
		elif not value.is_empty():
			rejected.append(value)
	return {"memory_class": memory_class, "source": source, "rejected": rejected}

## "auto" (the world distance pass runs) or "off".
static func world_distance_mode() -> String:
	return str(resolve_switch(OS.get_environment(WORLD_DISTANCE_VARIABLE),
		WORLD_DISTANCE_MODES, "off").mode)

static func world_distance_enabled() -> bool:
	return world_distance_mode() != "off"

## "auto" (sidecars where staged, otherwise decoded with mips), "legacy" or
## "nomips".
static func actor_images_mode() -> String:
	return str(resolve_switch(OS.get_environment(ACTOR_IMAGES_VARIABLE),
		ACTOR_IMAGES_MODES, "legacy").mode)

## The directory to self-test actor sidecars in, with forward slashes and no
## trailing slash, or "" for no self-test.
static func actor_vram_self_test_dir() -> String:
	var value := OS.get_environment(ACTOR_VRAM_SELF_TEST_VARIABLE).strip_edges()
	if value.to_lower() in OFF_SPELLINGS:
		return ""
	return value.replace("\\", "/").trim_suffix("/")

## "sidecar" (cooked actor LODs where the catalogue has them), "off" or
## "generate". An exported build never generates: it reads "sidecar".
static func actor_geometry_mode() -> String:
	return str(resolve_actor_geometry(OS.get_environment(ACTOR_GEOMETRY_VARIABLE),
		OS.has_feature("template")).mode)

## Only the three mode names count here, as in ActorGeometry's own reading of
## the variable (src/actors/actor_geometry.gd): any other non-empty value,
## 0/false/no/on included, is the default and reported, so the startup record
## never names a mode the applier is not in.
static func resolve_actor_geometry(value: String, exported: bool) -> Dictionary:
	var text := value.strip_edges().to_lower()
	if text.is_empty():
		return {"mode": ACTOR_GEOMETRY_MODES[0], "rejected": ""}
	if not text in ACTOR_GEOMETRY_MODES:
		return {"mode": ACTOR_GEOMETRY_MODES[0], "rejected": text}
	if exported and text == "generate":
		return {"mode": ACTOR_GEOMETRY_MODES[0], "rejected": "generate"}
	return {"mode": text, "rejected": ""}

## `value` as one of `modes`, trimmed and lower-cased: empty or an ON spelling
## is the default `modes[0]`, an OFF spelling is `off_mode`, anything else
## that is not a mode is the default too and is returned in "rejected".
static func resolve_switch(value: String, modes: Array[String], off_mode := "") -> Dictionary:
	var text := value.strip_edges().to_lower()
	if text in modes:
		return {"mode": text, "rejected": ""}
	if not off_mode.is_empty() and text in OFF_SPELLINGS:
		return {"mode": off_mode, "rejected": ""}
	if text.is_empty() or text in ON_SPELLINGS:
		return {"mode": modes[0], "rejected": ""}
	return {"mode": modes[0], "rejected": text}

## The switches this launch sets, with what each resolved to, for the startup
## log; {} on an ordinary launch. Values that were ignored are listed under
## "rejected" by the same keys.
static func switches() -> Dictionary:
	var result := {}
	var rejected := {}
	var memory := memory_class_override()
	if not str(memory.memory_class).is_empty():
		result["memory_class"] = memory.memory_class
		result["memory_class_source"] = memory.source
	var memory_rejected: PackedStringArray = memory.rejected
	if not memory_rejected.is_empty():
		rejected["memory_class"] = ",".join(memory_rejected)
	var exported := OS.has_feature("template")
	var parsed := {
		"world_distance": [WORLD_DISTANCE_VARIABLE,
			resolve_switch(OS.get_environment(WORLD_DISTANCE_VARIABLE), WORLD_DISTANCE_MODES, "off")],
		"actor_images": [ACTOR_IMAGES_VARIABLE,
			resolve_switch(OS.get_environment(ACTOR_IMAGES_VARIABLE), ACTOR_IMAGES_MODES, "legacy")],
		"actor_geometry": [ACTOR_GEOMETRY_VARIABLE,
			resolve_actor_geometry(OS.get_environment(ACTOR_GEOMETRY_VARIABLE), exported)],
	}
	for key: String in parsed:
		var variable := str(parsed[key][0])
		if OS.get_environment(variable).strip_edges().is_empty():
			continue
		var choice: Dictionary = parsed[key][1]
		result[key] = choice.mode
		if not str(choice.rejected).is_empty():
			rejected[key] = choice.rejected
	var self_test := actor_vram_self_test_dir()
	if not self_test.is_empty():
		result["actor_vram_self_test"] = self_test
	if not rejected.is_empty():
		result["rejected"] = rejected
	return result
