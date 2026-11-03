extends SceneTree
## First-run graphics defaults from the hardware (src/runtime/hardware_tier.gd):
## the classifier, which launches may seed a profile, that a saved profile is
## never touched, that the client reads a seeded profile as the Performance
## preset, the entry screen's still default and the FSR upscaler choice. Use an
## isolated user directory; the player's settings file is restored at the end.

const HardwareTier := preload("res://src/runtime/hardware_tier.gd")
const Options := preload("res://src/world/graphics_options.gd")
const Backdrop := preload("res://src/ui/login_backdrop.gd")
const Settings := preload("res://src/ui/settings_window.gd")
const TEMP_SETTINGS := "user://test_hardware_tier.cfg"
const GIB := 1 << 30

var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
	else:
		print("PASS: " + label)

func _run() -> void:
	var saved_config: Variant = FileAccess.get_file_as_bytes(Options.SETTINGS_PATH) \
		if FileAccess.file_exists(Options.SETTINGS_PATH) else null
	var saved_quality := OS.get_environment(LookProfile.QUALITY_VARIABLE)
	var saved_look := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	_check_classifier()
	_check_blockers()
	_check_switches()
	_check_seeding()
	_check_scaling_mode()
	await _check_backdrop()
	await _check_client()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(TEMP_SETTINGS))
	if saved_config != null:
		var file := FileAccess.open(Options.SETTINGS_PATH, FileAccess.WRITE)
		file.store_buffer(saved_config)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(Options.SETTINGS_PATH))
	OS.set_environment(LookProfile.QUALITY_VARIABLE, saved_quality)
	OS.set_environment(LookProfile.ENABLE_VARIABLE, saved_look)
	print("hardware tier tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

## An ordinary player's launch, with `changes` merged over it.
func _launch(changes := {}) -> Dictionary:
	return {"web": false, "headless": false, "engine_args": PackedStringArray(),
		"user_args": PackedStringArray(), "overrides": PackedStringArray()}.merged(changes, true)

func _machine(type: int, adapter: String, driver: String, memory_gib: float, threads: int,
		vendor := "") -> Dictionary:
	return {"adapter_type": type, "adapter_name": adapter, "adapter_vendor": vendor,
		"rendering_driver": driver, "physical_memory": int(memory_gib * GIB) if memory_gib > 0 else -1,
		"cpu_threads": threads}

func _tier(inputs: Dictionary) -> String:
	return str(HardwareTier.classify(inputs).tier)

func _check_classifier() -> void:
	var integrated := RenderingDevice.DEVICE_TYPE_INTEGRATED_GPU
	var discrete := RenderingDevice.DEVICE_TYPE_DISCRETE_GPU
	var other := RenderingDevice.DEVICE_TYPE_OTHER
	var uhd := _machine(integrated, "Intel(R) UHD Graphics 620", "vulkan", 7.8, 8, "Intel")
	var verdict := HardwareTier.classify(uhd)
	expect(verdict.tier == "low" and "integrated_gpu" in verdict.basis and "memory" in verdict.basis,
		"a UHD 620 laptop with 8 GB is low, for its iGPU and its memory: %s" % verdict)
	expect(JSON.stringify(verdict).contains("\"basis\":[\"integrated_gpu\",\"memory\"]")
		and JSON.stringify(verdict).contains("\"memory_gib\":7.8"), "the startup log line carries the inputs")
	expect(_tier(_machine(integrated, "Intel(R) Iris(R) Xe Graphics", "vulkan", 31.7, 16)) == "low",
		"an integrated GPU is low however much memory the machine has")
	expect(_tier(_machine(discrete, "Intel(R) Graphics", "d3d12", 31.7, 24, "Intel")) == "low",
		"D3D12 reporting the Arrow Lake iGPU as discrete does not hide it")
	expect(_tier(_machine(other, "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)",
		"opengl3_angle", 15.9, 12, "Google Inc. (Intel)")) == "low",
		"Compatibility's untyped ANGLE adapter is classified by name")
	expect(_tier(_machine(discrete, "Intel(R) Arc(TM) A770 Graphics", "d3d12", 31.7, 16)) == "high",
		"a discrete Arc card is not mistaken for an iGPU under D3D12")
	for name: String in ["Intel(R) Arc(TM) Graphics", "Intel(R) Arc(TM) 140V GPU (16GB)",
			"AMD Radeon(TM) Graphics", "AMD Radeon(TM) Vega 8 Graphics",
			"AMD Radeon(TM) RX Vega 10 Graphics", "AMD Radeon 780M Graphics",
			"AMD Radeon(TM) R7 Graphics", "AMD Radeon 8060S Graphics", "AMD Custom GPU 0405",
			"Qualcomm(R) Adreno(TM) X1-85 GPU"]:
		expect(HardwareTier.adapter_class(_machine(other, name, "opengl3", 0, 0)) == "integrated",
			"named iGPU: " + name)
	for name: String in ["NVIDIA GeForce GTX 1050 Ti", "Quadro K620", "AMD Radeon RX 6600",
			"Radeon RX Vega", "AMD Radeon R7 200 Series", "AMD Radeon Pro 5500M",
			"Intel(R) Arc(TM) B580 Graphics", "Intel(R) Arc(TM) Pro A40 Graphics"]:
		expect(HardwareTier.adapter_class(_machine(other, name, "opengl3", 0, 0)) == "discrete",
			"named discrete GPU: " + name)
	expect(HardwareTier.adapter_class(_machine(other, "Microsoft Basic Render Driver", "d3d12", 0, 0)) == "software"
		and HardwareTier.adapter_class(_machine(RenderingDevice.DEVICE_TYPE_CPU, "llvmpipe (LLVM 15.0.7, 256 bits)",
			"vulkan", 0, 0)) == "software", "software rasterisers are recognised")
	expect(_tier(_machine(RenderingDevice.DEVICE_TYPE_VIRTUAL_GPU, "Virtio-GPU Venus", "vulkan", 31.7, 16)) == "low",
		"a virtual GPU is low")
	expect(_tier(_machine(integrated, "Apple M3 Max", "metal", 36.0, 14)) == "high"
		and _tier(_machine(integrated, "Apple M2 Pro", "metal", 16.0, 10)) == "medium"
		and _tier(_machine(integrated, "Apple M1", "metal", 8.0, 8)) == "low",
		"Apple silicon is judged by memory and threads, not as an Intel/AMD iGPU")
	expect(HardwareTier.adapter_class(_machine(integrated, "NVIDIA Tegra Orin", "vulkan", 0, 0)) == "integrated",
		"Vulkan's own device type is trusted over a name")
	expect(_tier(_machine(discrete, "NVIDIA GeForce RTX 3060", "vulkan", 7.9, 12)) == "low",
		"8 GB of memory is low even with a discrete GPU")
	expect(_tier(_machine(discrete, "NVIDIA GeForce GTX 1060 6GB", "vulkan", 15.9, 4)) == "low",
		"four CPU threads are low")
	expect(_tier(_machine(discrete, "NVIDIA GeForce RTX 3060", "vulkan", 15.8, 12)) == "medium",
		"a discrete GPU with 16 GB is medium")
	expect(_tier(_machine(discrete, "NVIDIA GeForce RTX 3060", "vulkan", 31.7, 8)) == "medium",
		"a discrete GPU with eight CPU threads is medium")
	expect(_tier(_machine(discrete, "NVIDIA GeForce RTX 5080 Laptop GPU", "vulkan", 31.6, 24)) == "high",
		"a discrete GPU with 32 GB and 24 threads keeps High")
	expect(_tier(_machine(other, "NVIDIA GeForce RTX 5080 Laptop GPU", "opengl3", 31.6, 24, "NVIDIA")) == "high",
		"Compatibility's untyped NVIDIA adapter keeps High")
	expect(_tier(_machine(discrete, "Some Future GPU", "vulkan", 0, 0)) == "high",
		"unknown memory and threads do not lower a discrete GPU")
	expect(_tier(_machine(other, "Some Future GPU", "opengl3", 11.8, 16)) == "medium",
		"an unrecognised untyped adapter is judged by memory and threads alone")

func _check_blockers() -> void:
	expect(HardwareTier.blocker(_launch()) == "", "an ordinary player launch may seed")
	var cases := {
		"web": {"web": true}, "headless": {"headless": true},
		"tool_launch": {"engine_args": PackedStringArray(["--path", ".", "--script", "res://x.gd"])},
		"argument_override": {"user_args": PackedStringArray(["--optimization-profile=human-testing"])},
		"environment_override": {"overrides": PackedStringArray(["ELORIA_LOOK_QUALITY"])},
	}
	for reason: String in cases:
		expect(HardwareTier.blocker(_launch(cases[reason])) == reason, "launch blocked: " + reason)
	expect(HardwareTier.blocker(_launch({"engine_args": PackedStringArray(
		["--rendering-method", "gl_compatibility", "--rendering-driver", "opengl3"])})) == "",
		"the compatibility launcher's renderer flags still seed quality")
	var variables := ["RABBITLANDS_CROWD_BENCH_START_TOKEN", "RABBITLANDS_CLIENT_RUNTIME",
		"ELORIA_LOOK_QUALITY", "RABBITLANDS_LAUNCH_CONTEXT"]
	var previous := {}
	for variable: String in variables:
		previous[variable] = OS.get_environment(variable)
		OS.set_environment(variable, "x")
	var overrides: PackedStringArray = HardwareTier.launch_context().overrides
	expect("RABBITLANDS_CROWD_BENCH_START_TOKEN" in overrides and "RABBITLANDS_CLIENT_RUNTIME" in overrides
		and "ELORIA_LOOK_QUALITY" in overrides, "benchmark, optimisation and quality overrides are seen")
	expect("RABBITLANDS_LAUNCH_CONTEXT" not in overrides, "the updater's ordinary launch context is not an override")
	for variable: String in variables:
		if str(previous[variable]).is_empty():
			OS.unset_environment(variable)
		else:
			OS.set_environment(variable, str(previous[variable]))
	expect(HardwareTier.blocker(HardwareTier.launch_context()) == "headless", "this headless run seeds nothing")
	expect(HardwareTier.blocker(HardwareTier.launch_context().merged({"headless": false}, true)) == "tool_launch",
		"a windowed --script run (tests, benchmarks in project mode) would seed nothing either")

## The wave-2 measurement switches (schedule 1.1 #16): each blocks seeding,
## and the getters other groups call parse one spelling everywhere.
func _check_switches() -> void:
	var variables: Array[String] = [HardwareTier.MEMORY_CLASS_VARIABLE,
		HardwareTier.WORLD_DISTANCE_VARIABLE, HardwareTier.ACTOR_IMAGES_VARIABLE,
		HardwareTier.ACTOR_VRAM_SELF_TEST_VARIABLE, HardwareTier.ACTOR_GEOMETRY_VARIABLE]
	expect(PackedStringArray(variables) == PackedStringArray(["RABBITLANDS_MEMORY_CLASS", "ELORIA_WORLD_DISTANCE",
		"ELORIA_ACTOR_IMAGES", "ELORIA_ACTOR_VRAM_SELF_TEST", "RABBITLANDS_ACTOR_GEOMETRY"]),
		"the five wave-2 variables are spelled as planned")
	var previous := {}
	for variable: String in variables:
		previous[variable] = OS.get_environment(variable)
		OS.unset_environment(variable)

	# Unset: every getter is the default and the startup log gains nothing.
	expect(HardwareTier.switches().is_empty(), "an ordinary launch sets no switches")
	var unforced := HardwareTier.memory_class_override()
	expect(unforced.memory_class == "" and unforced.source == "" and (unforced.rejected as PackedStringArray).is_empty(),
		"no memory class is forced by default")
	expect(HardwareTier.world_distance_mode() == "auto" and HardwareTier.world_distance_enabled()
		and HardwareTier.actor_images_mode() == "auto" and HardwareTier.actor_vram_self_test_dir() == ""
		and HardwareTier.actor_geometry_mode() == "sidecar", "the defaults: distance pass on, actor images auto, "
		+ "no self-test, actor geometry from sidecars")
	var headless := HardwareTier.seed_first_run(TEMP_SETTINGS)
	expect(not headless.has("switches") and headless.reason == "headless" and not headless.applied,
		"the startup record is unchanged without switches")

	# Each variable is an override, and the argument is one too.
	for variable: String in variables:
		OS.set_environment(variable, "x")
		expect(variable in HardwareTier.OVERRIDE_VARIABLES and variable in HardwareTier.launch_context().overrides
			and HardwareTier.blocker(HardwareTier.launch_context().merged({"headless": false,
				"engine_args": PackedStringArray()}, true)) == "environment_override",
			"%s keeps a first run from being seeded" % variable)
		OS.unset_environment(variable)
	expect(HardwareTier.blocker(_launch({"user_args": PackedStringArray(["--memory-class=small"])}))
		== "argument_override", "--memory-class= keeps a first run from being seeded")
	expect(HardwareTier.blocker(_launch({"user_args": PackedStringArray(["--memory-classes"])})) == "",
		"an unrelated argument does not")

	# The memory class: argument over environment, the last argument counts,
	# anything that is not a class is skipped and reported.
	var cases := [
		["small", [], "small", "environment", []],
		[" Medium ", [], "medium", "environment", []],
		["", ["--memory-class=large"], "large", "argument", []],
		["small", ["--memory-class=LARGE"], "large", "argument", []],
		["small", ["--memory-class=huge"], "small", "environment", ["huge"]],
		["tiny", [], "", "", ["tiny"]],
		["", ["--memory-class=small", "--memory-class=medium"], "medium", "argument", []],
		["", ["--optimization-profile=human-testing", "--memory-class="], "", "", []],
	]
	for case: Array in cases:
		var resolved := HardwareTier.resolve_memory_class(str(case[0]), PackedStringArray(case[1]))
		expect(resolved.memory_class == case[2] and resolved.source == case[3]
			and resolved.rejected == PackedStringArray(case[4]),
			"memory class %s %s -> %s" % [case[0], case[1], resolved])
	OS.set_environment(HardwareTier.MEMORY_CLASS_VARIABLE, "SMALL")
	var forced := HardwareTier.memory_class_override()
	expect(forced.memory_class == "small" and forced.source == "environment",
		"the environment forces the memory class: %s" % forced)
	OS.unset_environment(HardwareTier.MEMORY_CLASS_VARIABLE)

	# Mode switches: canonical names, off/on spellings, and unknown values.
	var modes := [
		[HardwareTier.WORLD_DISTANCE_VARIABLE, func() -> String: return HardwareTier.world_distance_mode(),
			{"off": "off", " OFF ": "off", "0": "off", "false": "off", "auto": "auto", "1": "auto",
				"on": "auto", "bogus": "auto"}],
		[HardwareTier.ACTOR_IMAGES_VARIABLE, func() -> String: return HardwareTier.actor_images_mode(),
			{"legacy": "legacy", "off": "legacy", "nomips": "nomips", "NoMips": "nomips", "auto": "auto",
				"sidecar": "auto"}],
		[HardwareTier.ACTOR_GEOMETRY_VARIABLE, func() -> String: return HardwareTier.actor_geometry_mode(),
			{"off": "off", " OFF ": "off", "0": "sidecar", "false": "sidecar", "sidecar": "sidecar",
				"generate": "generate", "on": "sidecar", "lods": "sidecar"}],
	]
	for row: Array in modes:
		var table: Dictionary = row[2]
		for value: String in table:
			OS.set_environment(str(row[0]), value)
			var mode := str((row[1] as Callable).call())
			expect(mode == table[value], "%s=%s reads as %s (got %s)" % [row[0], value, table[value], mode])
		OS.unset_environment(str(row[0]))
	OS.set_environment(HardwareTier.WORLD_DISTANCE_VARIABLE, "off")
	expect(not HardwareTier.world_distance_enabled(), "off disables the world distance pass")
	OS.unset_environment(HardwareTier.WORLD_DISTANCE_VARIABLE)
	expect(HardwareTier.resolve_actor_geometry("generate", true) == {"mode": "sidecar", "rejected": "generate"}
		and HardwareTier.resolve_actor_geometry("off", true) == {"mode": "off", "rejected": ""}
		and HardwareTier.resolve_actor_geometry("generate", false) == {"mode": "generate", "rejected": ""},
		"an exported build never generates actor geometry")
	# ActorGeometry reads the variable itself and knows only its three names, so
	# the logged mode must not turn 0/false/no/legacy/on into anything else.
	var geometry_ok := HardwareTier.resolve_actor_geometry("", false) == {"mode": "sidecar", "rejected": ""}
	for value: String in ["0", "false", "no", "legacy", "on", "1"]:
		geometry_ok = geometry_ok and HardwareTier.resolve_actor_geometry(value, false) \
			== {"mode": "sidecar", "rejected": value}
	expect(geometry_ok, "actor geometry takes only sidecar/off/generate, as its applier does")
	for value: String in ["assets/actors/native/races", " assets\\actors\\native\\races\\ "]:
		OS.set_environment(HardwareTier.ACTOR_VRAM_SELF_TEST_VARIABLE, value)
		expect(HardwareTier.actor_vram_self_test_dir() == "assets/actors/native/races",
			"the actor self-test directory %s is normalised" % value)
	OS.set_environment(HardwareTier.ACTOR_VRAM_SELF_TEST_VARIABLE, "off")
	expect(HardwareTier.actor_vram_self_test_dir() == "", "off names no self-test directory")

	# What the startup log records for a measurement launch.
	OS.set_environment(HardwareTier.MEMORY_CLASS_VARIABLE, "small")
	OS.set_environment(HardwareTier.WORLD_DISTANCE_VARIABLE, "off")
	OS.set_environment(HardwareTier.ACTOR_IMAGES_VARIABLE, "nomips")
	OS.set_environment(HardwareTier.ACTOR_VRAM_SELF_TEST_VARIABLE, "assets/actors/native/races/")
	OS.set_environment(HardwareTier.ACTOR_GEOMETRY_VARIABLE, "bogus")
	var expected := {"memory_class": "small", "memory_class_source": "environment", "world_distance": "off",
		"actor_images": "nomips", "actor_geometry": "sidecar",
		"actor_vram_self_test": "assets/actors/native/races", "rejected": {"actor_geometry": "bogus"}}
	var logged := HardwareTier.switches()
	expect(logged == expected, "switches() records each switch and the ignored value: %s" % logged)
	DirAccess.remove_absolute(ProjectSettings.globalize_path(TEMP_SETTINGS))
	var record := HardwareTier.seed_first_run(TEMP_SETTINGS)
	expect(record.get("switches", {}) == expected and not record.applied
		and not FileAccess.file_exists(TEMP_SETTINGS), "the startup hardware_tier record carries them")
	OS.set_environment(HardwareTier.MEMORY_CLASS_VARIABLE, "tiny")
	expect(HardwareTier.switches().get("rejected", {}).get("memory_class", "") == "tiny"
		and not HardwareTier.switches().has("memory_class"), "an ignored memory class is reported")

	for variable: String in variables:
		if str(previous[variable]).is_empty():
			OS.unset_environment(variable)
		else:
			OS.set_environment(variable, str(previous[variable]))

func _write(text: String) -> void:
	var file := FileAccess.open(TEMP_SETTINGS, FileAccess.WRITE)
	file.store_string(text)
	file.close()

func _check_seeding() -> void:
	var low := _machine(RenderingDevice.DEVICE_TYPE_INTEGRATED_GPU, "Intel(R) UHD Graphics 620", "vulkan", 7.8, 8)
	DirAccess.remove_absolute(ProjectSettings.globalize_path(TEMP_SETTINGS))
	var result := HardwareTier.seed_profile(TEMP_SETTINGS, low, _launch())
	var config := ConfigFile.new()
	expect(result.applied and result.reason == "first_run" and config.load(TEMP_SETTINGS) == OK,
		"a fresh profile is seeded: %s" % result)
	var expected: Dictionary = HardwareTier.TIER_SETTINGS[HardwareTier.Tier.LOW]
	var matches := true
	for key: String in expected:
		matches = matches and config.get_value("graphics", key) == expected[key]
	expect(matches and config.get_value("graphics", "hardware_tier") == "low",
		"the low tier saves the Performance preset's values and the tier")
	expect(HardwareTier.recorded_tier(TEMP_SETTINGS) == "low" and HardwareTier.has_saved_graphics(TEMP_SETTINGS),
		"the recorded tier and the section are found in the file's text")
	expect(not config.has_section_key("graphics", "renderer"), "the renderer stays Automatic")
	var before := FileAccess.get_file_as_bytes(TEMP_SETTINGS)
	var again := HardwareTier.seed_profile(TEMP_SETTINGS,
		_machine(RenderingDevice.DEVICE_TYPE_DISCRETE_GPU, "NVIDIA GeForce RTX 4090", "vulkan", 63.0, 32), _launch())
	expect(not again.applied and again.reason == "saved_settings"
		and FileAccess.get_file_as_bytes(TEMP_SETTINGS) == before, "a seeded choice is stable on later launches")
	_write("[graphics]\n\nshadows=true\n")
	before = FileAccess.get_file_as_bytes(TEMP_SETTINGS)
	result = HardwareTier.seed_profile(TEMP_SETTINGS, low, _launch())
	expect(not result.applied and result.reason == "saved_settings"
		and FileAccess.get_file_as_bytes(TEMP_SETTINGS) == before, "an existing player's graphics are never touched")
	expect(HardwareTier.recorded_tier(TEMP_SETTINGS) == "", "a profile from before tiers records none")
	_write("[hud_presets]\r\n\r\npresets={}\r\n\r\n[graphics]\r\n\r\nquality=\"high\"\r\n[broken")
	before = FileAccess.get_file_as_bytes(TEMP_SETTINGS)
	result = HardwareTier.seed_profile(TEMP_SETTINGS, low, _launch())
	expect(not result.applied and result.reason == "saved_settings"
		and FileAccess.get_file_as_bytes(TEMP_SETTINGS) == before,
		"a [graphics] header after other sections ends the check without parsing the rest")
	_write("[graphics_extra]\n\nx=1\n\n[hud]\n\nnote=\"[graphics\"\n")
	expect(not HardwareTier.has_saved_graphics(TEMP_SETTINGS), "a similar section name is not [graphics]")
	_write("[graphics\nquality=")
	before = FileAccess.get_file_as_bytes(TEMP_SETTINGS)
	result = HardwareTier.seed_profile(TEMP_SETTINGS, low, _launch())
	expect(not result.applied and result.reason == "settings_unreadable"
		and FileAccess.get_file_as_bytes(TEMP_SETTINGS) == before, "an unreadable settings file is never overwritten")
	_write("[start_screen]\n\nbackdrop=\"amberwood\"\n")
	result = HardwareTier.seed_profile(TEMP_SETTINGS,
		_machine(RenderingDevice.DEVICE_TYPE_DISCRETE_GPU, "NVIDIA GeForce RTX 3060", "vulkan", 15.8, 12), _launch())
	config = ConfigFile.new()
	config.load(TEMP_SETTINGS)
	expect(result.applied and result.tier == "medium" and config.get_value("graphics", "quality") == "high"
		and config.get_value("start_screen", "backdrop") == "amberwood"
		and config.get_section_keys("graphics").size() == 2
		and HardwareTier.recorded_tier(TEMP_SETTINGS) == "medium",
		"the medium tier is recorded, keeps High quality and keeps other sections")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(TEMP_SETTINGS))
	expect(not HardwareTier.has_saved_graphics(TEMP_SETTINGS) and HardwareTier.recorded_tier(TEMP_SETTINGS) == "",
		"a missing settings file has no section and no tier")
	result = HardwareTier.seed_profile(TEMP_SETTINGS, low,
		_launch({"overrides": PackedStringArray(["RABBITLANDS_CROWD_BENCH_START_TOKEN"])}))
	expect(not result.applied and result.tier == "low" and not FileAccess.file_exists(TEMP_SETTINGS),
		"a benchmark's fresh profile is classified for the log but not written")

func _check_scaling_mode() -> void:
	expect(Options.scaling_mode(1.0, "forward_plus") == Viewport.SCALING_3D_MODE_BILINEAR,
		"100% draws without an upscaler pass")
	expect(Options.scaling_mode(0.75, "forward_plus") == Viewport.SCALING_3D_MODE_FSR
		and Options.scaling_mode(0.5, "mobile") == Viewport.SCALING_3D_MODE_FSR,
		"Forward+ and Mobile upscale a reduced 3D resolution with FSR 1")
	expect(Options.scaling_mode(0.75, "gl_compatibility") == Viewport.SCALING_3D_MODE_BILINEAR,
		"Compatibility, which has no FSR, keeps bilinear")

func _check_backdrop() -> void:
	var cases := [
		["[graphics]\n\nhardware_tier=\"low\"\n", false, "a low-tier first run starts the entry screen on its still"],
		["[graphics]\n\nhardware_tier=\"low\"\n\n[start_screen]\n\nanimated=true\n", true,
			"a saved Animate choice wins over the low tier"],
		["[graphics]\n\nhardware_tier=\"medium\"\n", true, "a medium-tier first run keeps the animation"],
		["[graphics]\n\nquality=\"low\"\n", true, "an existing Low player without a seeded tier keeps the animation"],
	]
	for case: Array in cases:
		_write(str(case[0]))
		var backdrop := Backdrop.new()
		backdrop.settings_path = TEMP_SETTINGS
		root.add_child(backdrop)
		backdrop.set_active(true)
		await process_frame
		var animated := bool(case[1])
		expect(backdrop.animation_enabled == animated and backdrop.animation_toggle.button_pressed == animated
			and (backdrop.video.stream != null) == animated and backdrop.poster.texture != null, str(case[2]))
		backdrop.queue_free()
		await process_frame

## The client itself reads a seeded profile as the Performance preset, keeps
## the tier through its own saves, and the in-game preset still writes what
## the low tier writes (so the two cannot drift apart).
func _check_client() -> void:
	var saved_player_quality := LookProfile.player_quality()
	var saved_player_mode := LookProfile.player_mode()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(Options.SETTINGS_PATH))
	var seeded := HardwareTier.seed_profile(Options.SETTINGS_PATH,
		_machine(RenderingDevice.DEVICE_TYPE_INTEGRATED_GPU, "Intel(R) UHD Graphics 620", "vulkan", 7.8, 8),
		_launch())
	expect(seeded.applied, "the player's fresh settings file is seeded")
	root.size = Vector2i(1280, 720)
	var main := load("res://src/app/main.tscn").instantiate() as Control
	root.add_child(main)
	await process_frame
	main.set_process(false)
	var viewport: SubViewport = main.get("main_viewport")
	var crowd: RefCounted = main.get("crowd")
	expect(LookProfile.player_quality() == LookProfile.Quality.LOW
		and LookProfile.player_mode() == LookProfile.Mode.PAINTED_GROUND, "a seeded profile loads Low quality")
	expect(Engine.max_fps == 30 and main.get("_vsync_preference") == "off"
		and is_equal_approx(viewport.scaling_3d_scale, 0.75), "a seeded profile loads the frame cap and 75% scale")
	expect(main.get("_map_texture_quality") == "half" and crowd.get("body_cap") == 60
		and main.get("_swaying_capes") == 0 and not main.get("_shadows_enabled")
		and main.get("_effects_enabled") and not Options.decorative_grass
		and is_equal_approx(float(main.get("_name_distance_metres")), 20.0),
		"a seeded profile loads half textures, 60 bodies and the preset's toggles")
	expect(bool(main.get("_crowd_bodies_auto")) and int(main.get("_crowd_bodies")) == 60
		and int(root.get_node("Network").get("declared_actor_cap")) == 60,
		"its crowd count follows the quality: 60 at Low, declared to the server as 60")
	expect(main.get("_renderer_preference") == "auto", "a seeded profile keeps the Automatic renderer")
	var backdrop: Control = main.get("start_screen_backdrop")
	expect(not backdrop.get("animation_enabled"), "the client's entry screen starts on the still")
	var window: Control = main.get("settings_window")
	var note := (window.get("panel") as Control).find_child("HardwareTierNote", true, false) as Label
	expect(note != null and note.text == Settings.hardware_tier_note("low"),
		"the graphics settings say the Performance preset was chosen at first launch")
	expect(Settings.hardware_tier_note("high").is_empty() and Settings.hardware_tier_note("medium").is_empty()
		and Settings.hardware_tier_note("").is_empty(),
		"High, medium-tier (still High) and unseeded profiles show no note")
	main.call("_on_client_setting_changed", "Graphics", "quality", LookProfile.Quality.HIGH)
	main.call("_on_client_setting_changed", "Graphics", "renderer", "auto")
	main.call("_apply_performance_preset")
	var stored := ConfigFile.new()
	stored.load(Options.SETTINGS_PATH)
	var drift := PackedStringArray()
	var expected: Dictionary = HardwareTier.TIER_SETTINGS[HardwareTier.Tier.LOW]
	for key: String in expected:
		if stored.get_value("graphics", key) != expected[key]:
			drift.append("%s=%s" % [key, stored.get_value("graphics", key)])
	expect(drift.is_empty(), "the low tier matches the in-game Performance preset: %s" % ", ".join(drift))
	expect(stored.get_value("graphics", "hardware_tier") == "low", "the client's own saves keep the recorded tier")
	_check_crowd_migration(main)
	main.queue_free()
	await process_frame
	Engine.max_fps = 0
	Options.decorative_grass = true
	LookProfile.set_player_quality(saved_player_quality)
	LookProfile.set_player_mode(saved_player_mode)

## LAT-L5's settings migration through the client's own load: profiles saved
## before the crowd count could follow the quality. 160 (or nothing) and the
## first-run low tier's 60 follow it; any other number, or 60 the player set
## with the old Performance preset, stays a number; a saved switch decides.
func _check_crowd_migration(main: Control) -> void:
	var crowd: RefCounted = main.get("crowd")
	var cases := [
		["quality=\"low\"\ncrowd_bodies=60\nhardware_tier=\"low\"\n", true, 60, 160,
			"a wave-1 low-tier profile (60) follows the quality: 60 at Low, 160 at High"],
		["quality=\"low\"\ncrowd_bodies=60\n", false, 60, 60,
			"60 saved by the old Performance preset stays 60 at every quality"],
		["quality=\"low\"\ncrowd_bodies=160\n", true, 60, 160,
			"the old default 160 follows the quality"],
		["quality=\"low\"\n", true, 60, 160, "a profile without a crowd count follows the quality"],
		["quality=\"high\"\ncrowd_bodies=90\nhardware_tier=\"low\"\n", false, 90, 90,
			"a player's own 90 stays 90"],
		["quality=\"low\"\ncrowd_bodies=160\ncrowd_bodies_auto=false\n", false, 160, 160,
			"a saved switch off keeps the number"],
	]
	for case: Array in cases:
		var file := FileAccess.open(Options.SETTINGS_PATH, FileAccess.WRITE)
		file.store_string("[graphics]\n\n" + str(case[0]))
		file.close()
		main.call("_load_hud_settings")
		var level := LookProfile.player_quality()
		var at_saved := int(crowd.get("body_cap"))
		var low_cap := at_saved if level == LookProfile.Quality.LOW else -1
		main.call("_on_client_setting_changed", "Graphics", "quality", LookProfile.Quality.HIGH)
		var high_cap := int(crowd.get("body_cap"))
		if low_cap < 0:
			main.call("_on_client_setting_changed", "Graphics", "quality", LookProfile.Quality.LOW)
			low_cap = int(crowd.get("body_cap"))
		var stored := ConfigFile.new()
		stored.load(Options.SETTINGS_PATH)
		expect(bool(main.get("_crowd_bodies_auto")) == bool(case[1]) and low_cap == int(case[2])
			and high_cap == int(case[3]) and stored.get_value("graphics", "crowd_bodies_auto") == bool(case[1]),
			"%s (follows %s, Low %d, High %d, saved %s)" % [case[4], main.get("_crowd_bodies_auto"),
				low_cap, high_cap, stored.get_value("graphics", "crowd_bodies_auto")])
