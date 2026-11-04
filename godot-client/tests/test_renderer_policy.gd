extends SceneTree
## Which renderer Automatic starts (src/runtime/renderer_policy.gd, MOB-C3 game
## side): the owner's default (off), the policy switch, the recommendation
## matrix over the adapters the design probed, the resolution rule, what a
## first run records, the trial's transitions (ok, failed_fallback,
## failed_start, withdrawn), launches that must not be touched, the restart
## handshake's plan and attempt counting, the compatibility launchers, the
## startup record's fields and, once the updater half (MOB-C3u) and Main's
## restart guard exist, that they agree with this file. Uses an isolated user
## directory and its own settings file; the player's file is never read.
##
## `-- --relaunch-child` (run with RABBITLANDS_LAUNCHER_FEATURES=renderer-relaunch)
## calls the real RendererPolicy.restart for a trial and must exit with
## RendererPolicy.RELAUNCH_EXIT_CODE (75) after counting the attempt in
## user://test_renderer_policy_child.cfg.

const Policy := preload("res://src/runtime/renderer_policy.gd")
const HardwareTier := preload("res://src/runtime/hardware_tier.gd")
const LaunchOptions := preload("res://src/updates/launch_options.gd")
const RendererFamily := preload("res://src/runtime/renderer_family.gd")
const Diagnostics := preload("res://src/diagnostics/client_diagnostics.gd")
const TEMP := "user://test_renderer_policy.cfg"
const CHILD := "user://test_renderer_policy_child.cfg"
const GIB := 1 << 30
## What the launch code can start once the updater half knows Mobile.
const WITH_MOBILE: Array[String] = ["forward_plus", "mobile", "gl_compatibility"]
## What it can start before that (this tree until MOB-C3u lands).
const WITHOUT_MOBILE: Array[String] = ["forward_plus", "gl_compatibility"]
const ON := {"renderer": "mobile", "source": "environment", "rejected": ""}

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
	if "--relaunch-child" in OS.get_cmdline_user_args():
		_relaunch_child()
		return
	var saved := {}
	for variable: String in [Policy.INTEGRATED_VARIABLE, Policy.LAUNCHER_FEATURES_ENV]:
		saved[variable] = OS.get_environment(variable) if OS.has_environment(variable) else null
		OS.unset_environment(variable)
	_check_default_off()
	_check_policy_switch()
	_check_recommend_matrix()
	_check_resolve()
	_check_first_run()
	_check_trial()
	_check_untouched()
	_check_restart()
	_check_needs_restart()
	_check_diagnostics_fields()
	_check_launch_conformance()
	await _check_main_guard()
	Policy.restarting = false
	DirAccess.remove_absolute(ProjectSettings.globalize_path(TEMP))
	for variable: String in saved:
		if saved[variable] == null:
			OS.unset_environment(variable)
		else:
			OS.set_environment(variable, saved[variable])
	print("renderer policy tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

# Helpers ---------------------------------------------------------------------

## An ordinary player's launch, with `changes` merged over it.
func _launch(changes := {}) -> Dictionary:
	return {"web": false, "headless": false, "engine_args": PackedStringArray(),
		"user_args": PackedStringArray(), "overrides": PackedStringArray()}.merged(changes, true)

## A Windows process on Forward+ with the policy on and Mobile startable.
func _context(changes := {}) -> Dictionary:
	return {"method": "forward_plus", "platform": "Windows", "launch": _launch(), "policy": ON,
		"supported": WITH_MOBILE, "migrate_existing": false}.merged(changes, true)

func _machine(type: int, adapter: String, driver: String, vendor := "") -> Dictionary:
	return {"adapter_type": type, "adapter_name": adapter, "adapter_vendor": vendor,
		"rendering_driver": driver, "physical_memory": int(7.8 * GIB), "cpu_threads": 8}

func _uhd620() -> Dictionary:
	return _machine(RenderingDevice.DEVICE_TYPE_INTEGRATED_GPU, "Intel(R) UHD Graphics 620", "vulkan", "Intel")

func _remove() -> void:
	DirAccess.remove_absolute(ProjectSettings.globalize_path(TEMP))

## A fresh profile seeded as a first run on `inputs`; returns seed_profile's result.
func _seed(inputs: Dictionary) -> Dictionary:
	_remove()
	return HardwareTier.seed_profile(TEMP, inputs, _launch())

## A settled profile: HUD notes, the Low tier and `values` in [graphics].
func _write(values: Dictionary, path := TEMP) -> void:
	var config := ConfigFile.new()
	config.set_value("notes", "text", "keep [graphics] notes")
	config.set_value("lower_hud", "order", ["health", "mana"])
	config.set_value("graphics", "quality", "low")
	config.set_value("graphics", "hardware_tier", "low")
	for key: String in values:
		config.set_value("graphics", key, values[key])
	config.save(path)

func _trial(state := "trial", attempts := 0, extra := {}) -> Dictionary:
	return {"renderer": "auto", "auto_renderer": "mobile", "auto_renderer_basis": "integrated_gpu",
		"auto_renderer_adapter": "Intel(R) UHD Graphics 620", "auto_renderer_state": state,
		"auto_renderer_attempts": attempts}.merged(extra, true)

func _values(path := TEMP) -> Dictionary:
	var config := ConfigFile.new()
	config.load(path)
	return Policy.read_values(config)

func _bytes(path := TEMP) -> PackedByteArray:
	return FileAccess.get_file_as_bytes(path) if FileAccess.file_exists(path) else PackedByteArray()

## A settled-profile tier result (not a first run).
func _settled_tier(inputs := _uhd620()) -> Dictionary:
	return HardwareTier.classify(inputs).merged({"applied": false, "reason": "saved_settings"}, true)

# Checks ----------------------------------------------------------------------

func _check_default_off() -> void:
	expect(Policy.INTEGRATED_RENDERER == "",
		"owner 2026-11-04: the integrated-GPU Mobile default stays off until the re-qualification passes")
	var off := Policy.policy("")
	expect(off.renderer == "" and off.source == "default", "no switch: the policy is off: %s" % off)
	var tier := _seed(_uhd620())
	var before := _bytes()
	var result := Policy.reconcile(tier, TEMP, _context({"policy": off}))
	expect(result.action == "none" and result.reason == "policy_off" and _bytes() == before,
		"a fresh iGPU first run with the default policy records nothing: %s" % result)
	expect(result.effective == "auto" and result.confirm_after == 0.0,
		"... and Automatic stays on the project default")
	expect(Policy.supported_renderers().has("forward_plus") and Policy.supported_renderers().has("gl_compatibility"),
		"the launch code can start Forward+ and OpenGL by name")
	expect(Policy.supported_renderers().has("mobile") == ("mobile" in LaunchOptions.RENDERERS),
		"Mobile is startable exactly when LaunchOptions knows it (MOB-C3u)")

func _check_policy_switch() -> void:
	for spelling: String in ["mobile", " Mobile ", "MOBILE"]:
		var on := Policy.policy(spelling)
		expect(on.renderer == "mobile" and on.source == "environment" and on.rejected == "",
			"%s=%s turns the policy on with Mobile" % [Policy.INTEGRATED_VARIABLE, spelling])
	for spelling: String in ["off", "0", "false", "no", "none"]:
		var off := Policy.policy(spelling)
		expect(off.renderer == "" and off.source == "environment", "%s turns the policy off" % spelling)
	for spelling: String in ["forward_plus", "gl_compatibility", "vulkan"]:
		var ignored := Policy.policy(spelling)
		expect(ignored.renderer == Policy.INTEGRATED_RENDERER and ignored.source == "default"
			and ignored.rejected == spelling, "%s is not a recommendation; ignored and reported" % spelling)
	expect(not Policy.INTEGRATED_VARIABLE in HardwareTier.OVERRIDE_VARIABLES,
		"the policy switch does not block first-run seeding (it exists to test a first run)")
	OS.set_environment(Policy.INTEGRATED_VARIABLE, "mobile")
	expect(Policy.policy().renderer == "mobile"
		and not Policy.INTEGRATED_VARIABLE in HardwareTier.launch_context().overrides,
		"the switch is read from the environment and is not an override")
	OS.unset_environment(Policy.INTEGRATED_VARIABLE)

func _check_recommend_matrix() -> void:
	var integrated := RenderingDevice.DEVICE_TYPE_INTEGRATED_GPU
	var discrete := RenderingDevice.DEVICE_TYPE_DISCRETE_GPU
	var other := RenderingDevice.DEVICE_TYPE_OTHER
	var cpu := RenderingDevice.DEVICE_TYPE_CPU
	# The design probe's adapters (wave2-design/exp/probe.log): name, vendor,
	# device type, driver, expected recommendation on Windows.
	var cases := [
		["Intel(R) Graphics", "Intel", integrated, "vulkan", "mobile"],
		["Intel(R) Graphics", "Intel", discrete, "d3d12", "mobile"],
		["Intel(R) UHD Graphics 620", "Intel", integrated, "vulkan", "mobile"],
		["Intel(R) UHD Graphics 620", "Intel", other, "opengl3", ""],
		["ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)", "Google Inc. (Intel)",
			other, "opengl3_angle", ""],
		["Intel(R) Iris(R) Xe Graphics", "Intel", integrated, "vulkan", "mobile"],
		["Intel(R) Arc(TM) A370M Graphics", "Intel", discrete, "d3d12", ""],
		["Intel(R) Arc(TM) 140V GPU (16GB)", "Intel", discrete, "d3d12", "mobile"],
		["AMD Radeon(TM) Graphics", "AMD", integrated, "vulkan", "mobile"],
		["AMD Radeon(TM) Vega 8 Graphics", "AMD", integrated, "vulkan", "mobile"],
		["AMD Radeon RX 6500 XT", "AMD", discrete, "vulkan", ""],
		["NVIDIA Quadro K620", "NVIDIA", discrete, "vulkan", ""],
		["NVIDIA GeForce GTX 750", "NVIDIA", discrete, "vulkan", ""],
		["Microsoft Basic Render Driver", "Microsoft", cpu, "d3d12", ""],
		["llvmpipe (LLVM 15.0.7, 256 bits)", "Mesa", cpu, "vulkan", ""],
	]
	for row: Array in cases:
		var classified := HardwareTier.classify(_machine(row[2], row[0], row[3], row[1]))
		var method := "gl_compatibility" if str(row[3]).begins_with("opengl3") else "forward_plus"
		var got := Policy.recommend(classified, method, "Windows", "mobile")
		expect(got == row[4], "recommend %s on %s (%s): \"%s\"" % [row[0], row[3], classified.adapter_class, got])
		expect(Policy.recommend(classified, method, "Linux", "mobile") == "",
			"Windows only: nothing for %s on Linux" % row[0])
		expect(Policy.recommend(classified, method, "Windows", "") == "",
			"the policy off recommends nothing for " + row[0])
	var uhd := HardwareTier.classify(_uhd620())
	expect(Policy.recommend(uhd, "mobile", "Windows", "mobile") == "mobile",
		"a process already on Mobile is RenderingDevice too")
	expect(Policy.recommend(uhd, "gl_compatibility", "Windows", "mobile") == "",
		"a process that fell back to OpenGL has not proven RenderingDevice")
	expect(Policy.recommend(uhd, "forward_plus", "macOS", "mobile") == "", "macOS stays out")

func _check_resolve() -> void:
	var cases := [
		[{}, "auto", "a profile without the keys stays Automatic"],
		[{"renderer": "forward_plus"}, "forward_plus", "an explicit Forward+ starts Forward+"],
		[_trial().merged({"renderer": "forward_plus"}, true), "forward_plus", "an explicit renderer wins over a trial"],
		[_trial().merged({"renderer": "gl_compatibility"}, true), "gl_compatibility", "an explicit OpenGL wins"],
		[{"renderer": "mobile"}, "mobile", "an explicit Mobile starts Mobile"],
		[_trial().merged({"renderer": "vulkan"}, true), "mobile", "an unknown renderer value reads as Automatic"],
		[_trial("trial", 0), "mobile", "a new trial starts the recommendation"],
		[_trial("trial", 1), "mobile", "a second trial start is allowed"],
		[_trial("trial", 2), "auto", "two trial starts without ok give up"],
		[_trial("ok", 0), "mobile", "a confirmed recommendation starts"],
		[_trial("failed_fallback"), "auto", "failed_fallback stays on the default"],
		[_trial("failed_start"), "auto", "failed_start stays on the default"],
		[_trial("withdrawn"), "auto", "a withdrawn recommendation stays on the default"],
		[_trial(""), "auto", "a recommendation without a state is not active"],
		[_trial("unheard_of"), "auto", "an unknown state is not active"],
		[_trial().merged({"auto_renderer": ""}, true), "auto", "an empty recommendation is the default"],
	]
	for row: Array in cases:
		var got := Policy.resolve(row[0], "mobile", WITH_MOBILE)
		expect(got == row[1], "%s: %s" % [row[2], got])
	expect(Policy.resolve(_trial(), "", WITH_MOBILE) == "auto",
		"with the policy off the game ignores a recorded recommendation")
	expect(Policy.resolve({"renderer": "forward_plus"}, "", WITH_MOBILE) == "forward_plus",
		"with the policy off an explicit renderer still wins")
	expect(Policy.resolve(_trial(), "mobile", WITHOUT_MOBILE) == "auto"
		and Policy.resolve({"renderer": "mobile"}, "mobile", WITHOUT_MOBILE) == "auto",
		"before the launch code knows Mobile, neither a recommendation nor a choice of it starts it")
	expect(Policy.recommendation_active(_trial("trial", 1), WITH_MOBILE)
		and not Policy.recommendation_active(_trial("trial", 2), WITH_MOBILE)
		and not Policy.recommendation_active(_trial("ok", 2), WITH_MOBILE),
		"the updater's rule: active states with fewer than MAX_TRIAL_ATTEMPTS attempts")

func _check_first_run() -> void:
	var tier := _seed(_uhd620())
	expect(bool(tier.applied) and tier.tier == "low", "the hardware tier seeds the fresh iGPU profile first")
	var result := Policy.reconcile(tier, TEMP, _context())
	var values := _values()
	expect(result.action == "recorded" and result.reason == "", "a fresh iGPU first run records: %s" % result)
	expect(values.auto_renderer == "mobile" and values.auto_renderer_basis == "integrated_gpu"
		and values.auto_renderer_adapter == "Intel(R) UHD Graphics 620" and values.auto_renderer_state == "trial"
		and values.auto_renderer_attempts == 0, "... the recommendation, its basis, adapter and trial: %s" % values)
	var config := ConfigFile.new()
	config.load(TEMP)
	expect(not config.has_section_key("graphics", "renderer") and config.get_value("graphics", "quality") == "low"
		and config.get_value("graphics", "hardware_tier") == "low",
		"... beside the seeded tier, without saving a renderer choice")
	expect(result.effective == "mobile" and result.requested == "mobile" and not result.fallback
		and result.confirm_after == 0.0, "... so this Forward+ process restarts into it (not confirmed here)")
	expect(Policy.needs_restart(result.effective, "forward_plus", PackedStringArray(), PackedStringArray(), false),
		"... and the restart check agrees")
	var recorded := _bytes()
	var again := Policy.reconcile(_settled_tier(), TEMP, _context())
	expect(again.action == "none" and again.reason == "" and again.effective == "mobile" and _bytes() == recorded,
		"the next Forward+ start writes nothing more and still restarts: %s" % again)

	tier = _seed(_uhd620())
	result = Policy.reconcile(tier, TEMP, _context({"method": "mobile"}))
	expect(result.action == "recorded" and result.effective == "mobile" and result.confirm_after == Policy.CONFIRM_SECONDS
		and not Policy.needs_restart("mobile", "mobile", PackedStringArray(), PackedStringArray(), false),
		"a first run already on Mobile records, needs no restart and confirms after %d s" % Policy.CONFIRM_SECONDS)

	var refusals := [
		[_machine(RenderingDevice.DEVICE_TYPE_OTHER, "Intel(R) UHD Graphics 620", "opengl3", "Intel"),
			{"method": "gl_compatibility"}, "not_rendering_device", "a first run that fell back to OpenGL"],
		[_machine(RenderingDevice.DEVICE_TYPE_DISCRETE_GPU, "NVIDIA Quadro K620", "vulkan", "NVIDIA"), {},
			"adapter_discrete", "a discrete GPU"],
		[_machine(RenderingDevice.DEVICE_TYPE_CPU, "llvmpipe (LLVM 15.0.7, 256 bits)", "vulkan", "Mesa"), {},
			"adapter_software", "a software rasteriser"],
		[_uhd620(), {"platform": "Linux"}, "platform", "Linux"],
		[_uhd620(), {"supported": WITHOUT_MOBILE}, "launch_unsupported",
			"launch code that cannot start Mobile yet"],
	]
	for row: Array in refusals:
		tier = _seed(row[0])
		var before := _bytes()
		result = Policy.reconcile(tier, TEMP, _context(row[1]))
		expect(result.action == "none" and result.reason == row[2] and _bytes() == before
			and result.effective == "auto", "%s records nothing (%s): %s" % [row[3], row[2], result.reason])
	# This tree's own launch code, whatever it can start.
	tier = _seed(_uhd620())
	result = Policy.reconcile(tier, TEMP, _context({"supported": Policy.supported_renderers()}))
	var expected := "recorded" if "mobile" in LaunchOptions.RENDERERS else "none"
	expect(result.action == expected, "with this tree's LaunchOptions a first run is '%s': %s" % [expected, result.reason])

	# Profiles from before this existed are migrated only behind MIGRATE_EXISTING.
	_write({"renderer": "auto"})
	var before_migration := _bytes()
	result = Policy.reconcile(_settled_tier(), TEMP, _context())
	expect(Policy.MIGRATE_EXISTING == false and result.reason == "not_first_run" and _bytes() == before_migration,
		"an existing Automatic profile is not migrated by default")
	result = Policy.reconcile(_settled_tier(), TEMP, _context({"migrate_existing": true}))
	expect(result.action == "recorded" and _values().auto_renderer == "mobile",
		"with migration on, an existing Automatic iGPU profile is recorded")
	var preserved := ConfigFile.new()
	preserved.load(TEMP)
	expect(preserved.get_value("notes", "text") == "keep [graphics] notes"
		and preserved.get_value("lower_hud", "order") == ["health", "mana"],
		"a write keeps every other section of the settings file")

func _check_trial() -> void:
	# The restarted (or updater-started) Mobile process.
	_write(_trial("trial", 1))
	var before := _bytes()
	var result := Policy.reconcile(_settled_tier(), TEMP, _context({"method": "mobile"}))
	expect(result.action == "none" and result.reason == "running" and result.confirm_after == Policy.CONFIRM_SECONDS
		and _bytes() == before and result.effective == "mobile", "a trial on Mobile waits to confirm: %s" % result)
	expect(Policy.confirm(TEMP, "forward_plus").action == "none", "confirm on another renderer does nothing")
	var confirmed := Policy.confirm(TEMP, "mobile")
	var values := _values()
	expect(confirmed.action == "confirmed" and values.auto_renderer_state == "ok" and values.auto_renderer_attempts == 0,
		"confirm marks the trial ok and clears the attempts: %s" % values)
	expect(Policy.confirm(TEMP, "mobile").reason == "not_trialling", "a confirmed trial is not confirmed twice")
	result = Policy.reconcile(_settled_tier(), TEMP, _context())
	expect(result.action == "none" and result.effective == "mobile" and result.confirm_after == 0.0,
		"an ok recommendation starts Mobile on later launches")

	# A renderer value the launch code cannot start reads as Automatic.
	_write(_trial("trial", 1, {"renderer": "vulkan"}))
	result = Policy.reconcile(_settled_tier(), TEMP, _context({"method": "mobile"}))
	expect(result.reason == "running" and result.confirm_after == Policy.CONFIRM_SECONDS
		and Policy.confirm(TEMP, "mobile").action == "confirmed",
		"an unknown renderer value is Automatic for the trial too")
	_write(_trial("trial", 1, {"renderer": "mobile"}))
	result = Policy.reconcile(_settled_tier(), TEMP, _context({"supported": WITHOUT_MOBILE}))
	expect(result.reason == "inactive" and result.effective == "auto",
		"a Mobile choice the launch code cannot start yet is Automatic, and its trial inactive")
	# The second trial start's process may still confirm.
	_write(_trial("trial", 2))
	result = Policy.reconcile(_settled_tier(), TEMP, _context({"method": "mobile"}))
	expect(result.reason == "running" and result.confirm_after == Policy.CONFIRM_SECONDS
		and _values().auto_renderer_state == "trial", "the process of the last allowed trial start can confirm")
	# A parent that finds the attempts used up gives up.
	result = Policy.reconcile(_settled_tier(), TEMP, _context())
	expect(result.action == "failed_start" and _values().auto_renderer_state == "failed_start"
		and result.effective == "auto", "two trial starts without ok give failed_start: %s" % result)
	result = Policy.reconcile(_settled_tier(), TEMP, _context())
	expect(result.reason == "inactive" and result.effective == "auto", "failed_start is permanent")

	# Mobile was asked for and the engine fell back to OpenGL.
	_write(_trial("trial", 1))
	result = Policy.reconcile(_settled_tier(), TEMP, _context({"method": "gl_compatibility"}))
	expect(result.action == "failed_fallback" and _values().auto_renderer_state == "failed_fallback"
		and result.effective == "auto" and result.fallback and result.requested == "forward_plus",
		"an OpenGL fallback gives failed_fallback; this session continues on OpenGL: %s" % result)
	_write(_trial("ok", 0))
	result = Policy.reconcile(_settled_tier(), TEMP, _context({"method": "gl_compatibility"}))
	expect(result.action == "failed_fallback", "a confirmed recommendation that later falls back is given up too")
	# The compatibility launchers ask for OpenGL themselves.
	for argument: String in Policy.COMPATIBILITY_ARGUMENTS:
		_write(_trial("trial", 1))
		before = _bytes()
		result = Policy.reconcile(_settled_tier(), TEMP, _context({"method": "gl_compatibility",
			"launch": _launch({"user_args": PackedStringArray([argument])})}))
		expect(result.action == "none" and _bytes() == before and result.requested == "gl_compatibility"
			and not result.fallback and not Policy.needs_restart(result.effective, "gl_compatibility",
			PackedStringArray(), PackedStringArray([argument]), false),
			"%s keeps OpenGL and the trial as it was" % argument)
	# The restart into Mobile came back on Forward+.
	_write(_trial("trial", 1))
	result = Policy.reconcile(_settled_tier(), TEMP, _context({
		"launch": _launch({"user_args": PackedStringArray([LaunchOptions.RENDERER_RESTART])})}))
	expect(result.action == "failed_fallback" and result.effective == "auto",
		"a restarted process that did not get Mobile gives it up (no restart loop)")
	# An ordinary parent on Forward+ during the trial: nothing to write, restart.
	_write(_trial("trial", 1))
	before = _bytes()
	result = Policy.reconcile(_settled_tier(), TEMP, _context())
	expect(result.action == "none" and _bytes() == before and result.effective == "mobile",
		"a Forward+ parent during a trial writes nothing and restarts into Mobile")

	# The kill switch: with the policy off an active recommendation is withdrawn.
	_write(_trial("ok", 0))
	result = Policy.reconcile(_settled_tier(), TEMP, _context({"policy": Policy.policy("")}))
	values = _values()
	expect(result.action == "withdrawn" and values.auto_renderer == "" and values.auto_renderer_state == "withdrawn"
		and values.auto_renderer_basis == "integrated_gpu" and result.effective == "auto",
		"the policy off withdraws a recorded recommendation (kept as a record): %s" % values)
	result = Policy.reconcile(_settled_tier(), TEMP, _context())
	expect(result.reason == "inactive" and result.effective == "auto" and _values().auto_renderer == "",
		"a withdrawn recommendation is not recorded again when the policy comes back")
	_write(_trial("failed_start", 2))
	before = _bytes()
	result = Policy.reconcile(_settled_tier(), TEMP, _context({"policy": Policy.policy("")}))
	expect(result.reason == "policy_off" and _bytes() == before, "a failed record is left as it is")

func _check_untouched() -> void:
	# Explicit choices are never touched.
	for renderer: String in ["forward_plus", "gl_compatibility", "mobile"]:
		_write(_trial("trial", 1, {"renderer": renderer}))
		var before := _bytes()
		var result := Policy.reconcile(_settled_tier(), TEMP, _context({"method": "gl_compatibility"}))
		expect(result.reason == "explicit_renderer" and result.action == "none" and _bytes() == before
			and result.effective == renderer and result.confirm_after == 0.0,
			"an explicit %s leaves the record alone" % renderer)
	# Launches that pin graphics or measure write nothing and ignore the record.
	var blocked := {
		"headless": _launch({"headless": true}),
		"web": _launch({"web": true}),
		"tool_launch": _launch({"engine_args": PackedStringArray(["--script", "res://tests/x.gd"])}),
		"environment_override": _launch({"overrides": PackedStringArray(["ELORIA_LOOK"])}),
		"argument_override": _launch({"user_args": PackedStringArray(["--memory-class=small"])}),
	}
	for reason: String in blocked:
		var tier := _seed(_uhd620())
		var seeded := _bytes()
		var result := Policy.reconcile(tier, TEMP, _context({"launch": blocked[reason]}))
		expect(result.reason == reason and _bytes() == seeded, "a %s launch records nothing" % reason)
		_write(_trial("trial", 2))
		var before := _bytes()
		result = Policy.reconcile(_settled_tier(), TEMP, _context({"launch": blocked[reason],
			"method": "mobile"}))
		expect(result.reason == reason and _bytes() == before and result.effective == "auto"
			and result.confirm_after == 0.0, "a %s launch changes no trial and ignores it" % reason)
		_write(_trial("ok", 0))
		before = _bytes()
		result = Policy.reconcile(_settled_tier(), TEMP, _context({"launch": blocked[reason],
			"policy": Policy.policy("")}))
		expect(result.reason == reason and _bytes() == before, "a %s launch withdraws nothing" % reason)
	# A settings file that exists but cannot be read is never overwritten.
	var file := FileAccess.open(TEMP, FileAccess.WRITE)
	file.store_string("[graphics]\nauto_renderer=\"mobile\nnot = = a config\n")
	file.close()
	var garbage := _bytes()
	var result := Policy.reconcile(HardwareTier.classify(_uhd620()).merged({"applied": true}, true), TEMP, _context())
	expect(result.reason == "settings_unreadable" and _bytes() == garbage and result.effective == "auto",
		"an unreadable settings file is left alone")
	expect(Policy.confirm(TEMP, "mobile").reason == "settings_unreadable" and _bytes() == garbage,
		"confirm leaves it alone too")

func _check_restart() -> void:
	var engine := PackedStringArray(["--verbose"])
	var user := PackedStringArray(["--server=localhost"])
	for features: String in ["renderer-relaunch", "updates, renderer-relaunch ,x"]:
		var plan := Policy.restart_plan("mobile", features, engine, user)
		expect(plan.mode == "relaunch" and plan.exit_code == Policy.RELAUNCH_EXIT_CODE and plan.exit_code == 75,
			"the updater's '%s' feature relaunches with exit code 75" % features)
	for features: String in ["", "renderer", "renderer-relaunched"]:
		var plan := Policy.restart_plan("gl_compatibility", features, engine, user)
		var args: PackedStringArray = plan.arguments
		var split := args.find("--")
		expect(plan.mode == "restart_on_exit" and plan.exit_code == 0
			and args == LaunchOptions.restart_arguments("gl_compatibility", engine, user)
			and args.find("gl_compatibility") < split and LaunchOptions.RENDERER_RESTART in args.slice(split)
			and "--server=localhost" in args.slice(split),
			"without the feature ('%s') the game restarts itself, marked against loops" % features)
	expect(Policy.launcher_relaunches("renderer-relaunch") and not Policy.launcher_relaunches("")
		and not Policy.launcher_relaunches("renderer-relaunch-v0"), "the feature list is parsed exactly")

	# Attempts are counted for the trialled recommendation only.
	_write(_trial("trial", 0))
	Policy.restarting = false
	expect(not Diagnostics.restart_pending(), "no restart is pending before one is begun")
	var plan := Policy.begin_restart("mobile", TEMP, "renderer-relaunch", engine, user)
	expect(plan.mode == "relaunch" and plan.counted and plan.attempts == 1 and _values().auto_renderer_attempts == 1,
		"a restart into the trial counts one attempt: %s" % plan)
	expect(Policy.restarting and Diagnostics.restart_pending(), "Main's guard sees the pending restart")
	plan = Policy.begin_restart("mobile", TEMP, "", engine, user)
	expect(plan.mode == "restart_on_exit" and _values().auto_renderer_attempts == 2,
		"the self-restart path counts too")
	var uncounted := [
		[_trial("trial", 0, {"renderer": "forward_plus"}), "forward_plus", "an explicit renderer's restart"],
		[_trial("ok", 0), "mobile", "a restart into a confirmed recommendation"],
		[{"renderer": "auto"}, "mobile", "a restart without a recommendation"],
		[_trial("trial", 0), "gl_compatibility", "a restart into another renderer than the trialled one"],
	]
	for row: Array in uncounted:
		_write(row[0])
		var before := _bytes()
		plan = Policy.begin_restart(row[1], TEMP, "", engine, user)
		expect(not plan.counted and _bytes() == before, "no attempt is counted for %s" % row[2])
	Policy.restarting = false

func _check_needs_restart() -> void:
	var none := PackedStringArray()
	expect(Policy.needs_restart("mobile", "forward_plus", none, none, false),
		"Automatic resolving to Mobile restarts a Forward+ process")
	expect(not Policy.needs_restart("auto", "forward_plus", none, none, false), "Automatic as before: no restart")
	expect(not Policy.needs_restart("mobile", "mobile", none, none, false), "already on it: no restart")
	expect(not Policy.needs_restart("mobile", "forward_plus", none, none, true), "headless never restarts")
	expect(not Policy.needs_restart("mobile", "forward_plus", none,
		PackedStringArray([LaunchOptions.RENDERER_RESTART]), false), "a restarted process never restarts again")
	expect(not Policy.needs_restart("mobile", "forward_plus", PackedStringArray(["--script", "x.gd"]), none, false),
		"a tool launch never restarts")
	for argument: String in Policy.COMPATIBILITY_ARGUMENTS:
		expect(not Policy.needs_restart("forward_plus", "gl_compatibility", none, PackedStringArray([argument]), false),
			"%s keeps OpenGL even over an explicit Forward+ choice (its engine flags are invisible here)" % argument)
		expect(LaunchOptions.game_arguments(PackedStringArray([argument]), none, "C:/Game", false).has("gl_compatibility"),
			"%s is a launcher argument that forces OpenGL" % argument)

func _check_diagnostics_fields() -> void:
	var tier := _seed(_uhd620())
	var result := Policy.reconcile(tier, TEMP, _context())
	var fields := Diagnostics.renderer_policy_fields(result, tier)
	expect(fields.renderer_effective == "mobile" and fields.renderer_requested == "mobile"
		and fields.renderer_fallback == false and fields.auto_renderer == "mobile"
		and fields.auto_renderer_state == "trial" and fields.auto_renderer_attempts == 0
		and fields.adapter_class == "integrated", "the startup record names the recommendation: %s" % fields)
	expect(fields.renderer_policy == {"integrated_renderer": "mobile", "source": "environment",
		"action": "recorded", "reason": ""}, "... and the policy that made it: %s" % fields.renderer_policy)
	var rejected := Policy.reconcile(tier, TEMP, _context({"policy": Policy.policy("vulkan")}))
	expect(Diagnostics.renderer_policy_fields(rejected, tier).renderer_policy.get("rejected") == "vulkan",
		"an ignored switch value is reported")
	expect(not JSON.stringify(fields).contains("keep [graphics] notes"), "the fields carry no settings text")

## Once the updater half (MOB-C3u) is in this tree, it must agree with the game.
func _check_launch_conformance() -> void:
	# Through the loaded scripts, so this compiles against both halves.
	var options: Script = load("res://src/updates/launch_options.gd")
	var policy_script: Script = load("res://src/runtime/renderer_policy.gd")
	var constants := options.get_script_constant_map()
	for name: String in ["RELAUNCH_EXIT_CODE", "LAUNCHER_FEATURES_ENV", "RELAUNCH_FEATURE"]:
		if constants.has(name):
			expect(constants[name] == policy_script.get_script_constant_map()[name],
				"LaunchOptions.%s equals RendererPolicy's" % name)
		else:
			print("SKIP: LaunchOptions.%s is not in this tree yet (MOB-C3u)" % name)
	if not options.has_method("effective_renderer"):
		print("SKIP: LaunchOptions.effective_renderer is not in this tree yet (MOB-C3u)")
		return
	var supported := Policy.supported_renderers()
	var cases: Array[Dictionary] = [{}, {"renderer": "forward_plus"}, {"renderer": "gl_compatibility"},
		{"renderer": "mobile"}, {"renderer": "vulkan"}, _trial("trial", 0), _trial("trial", 1), _trial("trial", 2),
		_trial("ok", 0), _trial("ok", 2), _trial("failed_fallback"), _trial("failed_start"), _trial("withdrawn"),
		_trial(""), _trial("unheard_of"), _trial("trial", 0, {"auto_renderer": ""}),
		_trial("trial", 0, {"renderer": "forward_plus"})]
	for values: Dictionary in cases:
		_write(values)
		var launcher := str(options.call("effective_renderer", TEMP))
		var game := Policy.resolve(_values(), "mobile", supported)
		expect(launcher == game, "the updater and the game (policy on) start the same renderer for %s: %s vs %s"
			% [values, launcher, game])

## Main's restart guard (a hook for main.gd, B5): once it is in main.gd, a
## pending restart skips Main's setup. Without it a restarting windowed game
## stops after one frame and never exits (measured), so a renderer restart
## does not work at all until the hook is in.
func _check_main_guard() -> void:
	var source := FileAccess.get_file_as_string("res://src/app/main.gd")
	if not source.contains("restart_pending()"):
		print("SKIP: Main's restart guard is not in main.gd yet (hook for B5; renderer restarts hang without it)")
		return
	Policy.restarting = true
	var main := load("res://src/app/main.tscn").instantiate() as Control
	root.add_child(main)
	await process_frame
	var presentation: Variant = main.get("remote_presentation")
	expect(main.process_mode == Node.PROCESS_MODE_DISABLED
		and (not (presentation is Node) or (presentation as Node).get_parent() != main),
		"a pending restart skips Main's setup")
	Policy.restarting = false
	main.queue_free()
	await process_frame
	await process_frame

## `-- --relaunch-child`: a trial restart through the updater's handshake.
func _relaunch_child() -> void:
	if not Policy.launcher_relaunches():
		push_error("FAIL: run the relaunch child with %s=%s" % [Policy.LAUNCHER_FEATURES_ENV, Policy.RELAUNCH_FEATURE])
		quit(2)
		return
	_write(_trial("trial", 0), CHILD)
	var plan := Policy.restart(self, "mobile", CHILD)
	print("RELAUNCH_CHILD mode=%s attempts=%d restarting=%s pending=%s" % [plan.mode,
		int(_values(CHILD).auto_renderer_attempts), Policy.restarting, Diagnostics.restart_pending()])
