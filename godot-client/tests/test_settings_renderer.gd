extends SceneTree
## The settings window's renderer choice (wave 2, MOB-C5): Settings names the
## renderer that is running (Mobile was labelled Forward+), offers Mobile once
## the launch code can start it, names what Automatic starts here ("Automatic
## (Mobile)"), says what each renderer is for, notes a renderer that could not
## start, and asks for a restart only when the choice starts a different
## renderer.
##
## Run headless with an isolated APPDATA/LOCALAPPDATA:
##   godot --headless --log-file <log> --path godot-client --script res://tests/test_settings_renderer.gd
## The settings file is copied first and put back at the end.

const Settings := preload("res://src/ui/settings_window.gd")
const RendererPolicy := preload("res://src/runtime/renderer_policy.gd")
const RendererFamily := preload("res://src/runtime/renderer_family.gd")
const LaunchOptions := preload("res://src/updates/launch_options.gd")
const HardwareTier := preload("res://src/runtime/hardware_tier.gd")

const ALL: Array[String] = ["forward_plus", "mobile", "gl_compatibility"]
const TODAY: Array[String] = ["forward_plus", "gl_compatibility"]
const LOW_NOTE := "This computer started on the Performance preset, chosen from its graphics, memory and processor at first launch. Your own changes are kept."

var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> bool:
	if ok:
		print("PASS: " + label)
	else:
		failures += 1
		push_error("FAIL: " + label)
	return ok

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var path := RendererPolicy.SETTINGS_PATH
	var had_settings := FileAccess.file_exists(path)
	var saved_settings := FileAccess.get_file_as_bytes(path) if had_settings else PackedByteArray()
	var saved_policy := OS.get_environment(RendererPolicy.INTEGRATED_VARIABLE)
	OS.unset_environment(RendererPolicy.INTEGRATED_VARIABLE)
	var startup: Dictionary = RendererPolicy.launch.duplicate(true)
	_check_startup_snapshot(startup)
	_check_names()
	_check_tooltip()
	_check_fallback_text()
	_check_tier_note()
	_check_automatic()
	_check_restart_rule()
	await _check_window_live()
	await _check_window_mobile(path)
	await _check_window_fallback()
	await _check_window_reconciled_fallback()
	# Put everything back.
	Settings.renderers_for_tests = []
	RendererPolicy.launch = startup
	RendererFamily.override_for_tests("")
	if saved_policy.is_empty():
		OS.unset_environment(RendererPolicy.INTEGRATED_VARIABLE)
	else:
		OS.set_environment(RendererPolicy.INTEGRATED_VARIABLE, saved_policy)
	if had_settings:
		var file := FileAccess.open(path, FileAccess.WRITE)
		file.store_buffer(saved_settings)
		file.close()
	elif FileAccess.file_exists(path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	print("settings renderer tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(0 if failures == 0 else 1)

## ClientDiagnostics keeps its startup reconcile for the window, so the window
## does not parse the settings file a second time.
func _check_startup_snapshot(startup: Dictionary) -> void:
	expect(startup.get("values") is Dictionary and startup.has("requested") and startup.has("asked")
		and startup.has("effective"), "ClientDiagnostics kept this launch's renderer decision for the settings window")
	expect(Settings.launch_asked({"asked": "mobile", "requested": "forward_plus"}) == "mobile"
		and Settings.launch_asked({"requested": "forward_plus"}) == "forward_plus" and Settings.launch_asked({}) == "",
		"launch_asked: what the launch asked for, else what it requests")
	RendererPolicy.launch = {"values": {"renderer": "auto", "auto_renderer": "mobile",
		"auto_renderer_state": "ok", "auto_renderer_attempts": 0}}
	expect(RendererPolicy.launch_values().get("auto_renderer") == "mobile",
		"launch_values reads the kept values, not the file")
	RendererPolicy.launch = {}
	var file_path := "user://test_settings_renderer.cfg"
	var config := ConfigFile.new()
	config.set_value("graphics", "renderer", "gl_compatibility")
	config.set_value("graphics", RendererPolicy.KEY_RENDERER, "mobile")
	config.set_value("graphics", RendererPolicy.KEY_STATE, "failed_start")
	config.save(file_path)
	var read := RendererPolicy.launch_values(file_path)
	expect(read.get("renderer") == "gl_compatibility" and read.get("auto_renderer") == "mobile"
		and read.get("auto_renderer_state") == "failed_start",
		"without a kept decision launch_values reads the settings file")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(file_path))
	RendererPolicy.launch = startup

func _check_names() -> void:
	expect(Settings.renderer_choices(TODAY) == ["auto", "forward_plus", "gl_compatibility"],
		"today's launch code: Automatic, Forward+, OpenGL Compatibility")
	var shuffled: Array[String] = ["gl_compatibility", "mobile", "forward_plus"]
	expect(Settings.renderer_choices(shuffled) == ["auto", "forward_plus", "mobile", "gl_compatibility"],
		"with Mobile startable it is offered, in menu order")
	expect(Settings.renderer_choices([]) == ["auto"], "Automatic is always offered")
	var choices := Settings.renderer_choices(ALL)
	expect(Settings.renderer_choice_labels(choices, "mobile")
			== ["Automatic (Mobile)", "Forward+", "Mobile", "OpenGL Compatibility"],
		"labels: Automatic names Mobile when it starts Mobile")
	expect(Settings.renderer_choice_labels(choices, "forward_plus")[0] == "Automatic (Forward+)",
		"labels: Automatic (Forward+) by default")
	expect(Settings.renderer_choice_labels(Settings.renderer_choices(TODAY), "gl_compatibility")
			== ["Automatic (OpenGL Compatibility)", "Forward+", "OpenGL Compatibility"],
		"labels: the browser's Automatic is OpenGL Compatibility")
	expect(Settings.renderer_name("mobile") == "Mobile" and Settings.renderer_name("forward_plus") == "Forward+"
		and Settings.renderer_name("gl_compatibility") == "OpenGL Compatibility",
		"Mobile is called Mobile, never Forward+")
	expect(Settings.renderer_name("something_new") == "something_new", "an unknown method is shown as reported")
	var drivers := {"vulkan": "Vulkan", "d3d12": "Direct3D 12", "opengl3": "OpenGL",
		"opengl3_angle": "OpenGL (ANGLE)", "metal": "Metal", "opengl3_es": "OpenGL ES"}
	for driver: String in drivers:
		expect(Settings.driver_name(driver) == drivers[driver], "driver %s reads %s" % [driver, drivers[driver]])
	expect(Settings.driver_name("dummy") == "" and Settings.driver_name("") == "",
		"no driver name for the headless dummy driver")
	expect(Settings.driver_name("future_api") == "future_api", "an unknown driver is shown as reported")

func _check_tooltip() -> void:
	expect(Settings.running_renderer_text("mobile", "vulkan", "Intel(R) UHD Graphics 620")
			== "Running now: Mobile on Vulkan (Intel(R) UHD Graphics 620).",
		"running line: renderer, driver and adapter")
	expect(Settings.running_renderer_text("gl_compatibility", "opengl3_angle", " ANGLE (Intel) ")
			== "Running now: OpenGL Compatibility on OpenGL (ANGLE) (ANGLE (Intel)).",
		"running line: ANGLE")
	expect(Settings.running_renderer_text("forward_plus", "d3d12", "")
			== "Running now: Forward+ on Direct3D 12.", "running line without an adapter name")
	expect(Settings.running_renderer_text("forward_plus", "dummy", "") == "Running now: Forward+.",
		"running line headless")
	var all := Settings.renderer_tooltip("mobile", "vulkan", "Intel(R) Graphics", Settings.renderer_choices(ALL))
	var lines := all.split("\n")
	expect(lines.size() == 6 and lines[0] == "Running now: Mobile on Vulkan (Intel(R) Graphics)."
		and lines[1] == "Automatic uses the renderer chosen for this computer."
		and lines[2] == Settings.RENDERER_PURPOSES.forward_plus
		and lines[3] == Settings.RENDERER_PURPOSES.mobile
		and lines[4] == Settings.RENDERER_PURPOSES.gl_compatibility
		and lines[5] == "Close and reopen the game to apply a change. Compatibility launchers take precedence.",
		"tooltip: running now, Automatic, one line per renderer, how to apply:\n" + all)
	var today := Settings.renderer_tooltip("forward_plus", "vulkan", "GPU", Settings.renderer_choices(TODAY))
	expect(not "Mobile" in today and today.split("\n").size() == 5,
		"tooltip: no Mobile line while Mobile is not offered")
	expect(str(Settings.RENDERER_PURPOSES.mobile).contains("integrated graphics")
		and str(Settings.RENDERER_PURPOSES.forward_plus).contains("contact shade")
		and str(Settings.RENDERER_PURPOSES.forward_plus).contains("bounce light")
		and str(Settings.RENDERER_PURPOSES.gl_compatibility).contains("least memory"),
		"each renderer's purpose is the plan's")

func _check_fallback_text() -> void:
	var none := {}
	expect(Settings.renderer_fallback_text(none, "forward_plus", "forward_plus") == "", "no note when Forward+ runs")
	expect(Settings.renderer_fallback_text(none, "forward_plus", "gl_compatibility")
			== "Forward+ could not start on this computer, so the game is using OpenGL Compatibility.",
		"Forward+ asked for, OpenGL running: the engine's fallback")
	expect(Settings.renderer_fallback_text(none, "gl_compatibility", "gl_compatibility") == "",
		"a compatibility launcher or OpenGL choice is no fallback")
	expect(Settings.renderer_fallback_text(none, "", "gl_compatibility") == "",
		"nothing known about the request: no note")
	var failed_start := {"auto_renderer": "mobile", "auto_renderer_state": "failed_start"}
	expect(Settings.renderer_fallback_text(failed_start, "forward_plus", "forward_plus")
			== "Mobile could not start on this computer, so Automatic uses Forward+.",
		"failed_start: Automatic is back on Forward+")
	var failed_fallback := {"auto_renderer": "mobile", "auto_renderer_state": "failed_fallback"}
	expect(Settings.renderer_fallback_text(failed_fallback, "mobile", "gl_compatibility")
			== "Mobile could not start on this computer, so the game is using OpenGL Compatibility. Automatic uses Forward+ from the next start.",
		"Mobile fell back to OpenGL in this launch")
	expect(Settings.renderer_fallback_text(failed_start, "forward_plus", "gl_compatibility")
			== "Forward+ could not start on this computer, so the game is using OpenGL Compatibility. Mobile could not start on this computer, so Automatic uses Forward+.",
		"both: this launch's fallback and an earlier failed recommendation")
	for state: String in ["trial", "ok", "withdrawn", ""]:
		expect(Settings.renderer_fallback_text({"auto_renderer": "mobile", "auto_renderer_state": state},
				"mobile", "mobile") == "", "no note for a recommendation in state '%s'" % state)
	expect(Settings.renderer_fallback_text({"auto_renderer": "", "auto_renderer_state": "failed_start"},
		"forward_plus", "forward_plus") == "", "no note without a recorded renderer")

func _check_tier_note() -> void:
	expect(Settings.hardware_tier_note("low") == LOW_NOTE, "the Performance preset note is unchanged")
	expect(Settings.hardware_tier_note("low", "forward_plus") == LOW_NOTE,
		"the note is unchanged while Automatic starts Forward+")
	var mobile := Settings.hardware_tier_note("low", "mobile")
	expect(mobile.begins_with("This computer started on the Performance preset")
		and mobile.contains("Automatic uses the Mobile renderer") and mobile.ends_with("Your own changes are kept."),
		"a low first run on Mobile mentions the Mobile renderer: " + mobile)
	expect(Settings.hardware_tier_note("medium") == "" and Settings.hardware_tier_note("high") == ""
		and Settings.hardware_tier_note("") == "", "no note for medium, high or unseeded profiles")
	expect(Settings.hardware_tier_note("", "mobile").contains("Mobile renderer"),
		"an unseeded profile that Automatic starts on Mobile is told so")

func _check_automatic() -> void:
	expect(RendererPolicy.default_renderer() == "forward_plus", "the project starts Forward+ by default")
	expect(RendererPolicy.requested_renderer("auto", PackedStringArray()) == RendererPolicy.default_renderer(),
		"an Automatic launch asks for the project default")
	var active := {"renderer": "auto", "auto_renderer": "mobile", "auto_renderer_state": "trial",
		"auto_renderer_attempts": 0}
	expect(RendererPolicy.automatic_renderer(active, "mobile", ALL) == "mobile",
		"Automatic starts an active Mobile recommendation")
	expect(RendererPolicy.automatic_renderer(active, "", ALL) == "forward_plus",
		"policy off: Automatic starts Forward+")
	expect(RendererPolicy.automatic_renderer(active, "mobile", TODAY) == "forward_plus",
		"Mobile not startable by the launch code: Automatic starts Forward+")
	var explicit := active.duplicate()
	explicit.renderer = "gl_compatibility"
	expect(RendererPolicy.automatic_renderer(explicit, "mobile", ALL) == "mobile",
		"the player's explicit choice does not change what Automatic would start")
	for state: String in ["failed_fallback", "failed_start", "withdrawn", ""]:
		var values := active.duplicate()
		values.auto_renderer_state = state
		expect(RendererPolicy.automatic_renderer(values, "mobile", ALL) == "forward_plus",
			"state '%s': Automatic starts Forward+" % state)
	var tried := active.duplicate()
	tried.auto_renderer_attempts = RendererPolicy.MAX_TRIAL_ATTEMPTS
	expect(RendererPolicy.automatic_renderer(tried, "mobile", ALL) == "forward_plus",
		"too many trial starts: Automatic starts Forward+")
	expect(RendererPolicy.automatic_renderer({}, "mobile", ALL) == "forward_plus", "nothing recorded: Forward+")

func _check_restart_rule() -> void:
	# [choice, this launch's choice, running, what Automatic starts, restart needed]
	var cases := [
		["auto", "auto", "forward_plus", "forward_plus", false],
		["forward_plus", "auto", "forward_plus", "forward_plus", false],
		["mobile", "auto", "forward_plus", "forward_plus", true],
		["gl_compatibility", "auto", "forward_plus", "forward_plus", true],
		["auto", "forward_plus", "forward_plus", "forward_plus", false],
		["forward_plus", "forward_plus", "forward_plus", "forward_plus", false],
		["auto", "auto", "mobile", "mobile", false],
		["mobile", "auto", "mobile", "mobile", false],
		["forward_plus", "auto", "mobile", "mobile", true],
		["auto", "mobile", "mobile", "forward_plus", true],
		# A compatibility launcher runs OpenGL over a saved Forward+.
		["forward_plus", "forward_plus", "gl_compatibility", "forward_plus", false],
		["auto", "forward_plus", "gl_compatibility", "forward_plus", false],
		["gl_compatibility", "forward_plus", "gl_compatibility", "forward_plus", false],
		["mobile", "forward_plus", "gl_compatibility", "forward_plus", true],
		# Forward+ could not start: the fallback note explains, no restart notice.
		["auto", "auto", "gl_compatibility", "forward_plus", false],
		["forward_plus", "auto", "gl_compatibility", "forward_plus", false],
		["gl_compatibility", "gl_compatibility", "gl_compatibility", "forward_plus", false],
		["auto", "gl_compatibility", "gl_compatibility", "forward_plus", true],
	]
	for case: Array in cases:
		expect(Settings.renderer_restart_needed(case[0], case[1], case[2], case[3]) == case[4],
			"restart notice: choice %s, launched with %s, running %s, Automatic %s -> %s" % case)
	expect(Settings.started_renderer("auto", "mobile") == "mobile"
		and Settings.started_renderer("", "forward_plus") == "forward_plus"
		and Settings.started_renderer("gl_compatibility", "mobile") == "gl_compatibility",
		"started_renderer: Automatic starts what Automatic starts")
	# Live defaults (the policy is off, so Automatic starts Forward+): a
	# Forward+ choice never needs a restart from Automatic, and OpenGL does
	# unless OpenGL already runs.
	expect(not Settings.renderer_restart_needed("forward_plus", "auto")
		and Settings.renderer_restart_needed("gl_compatibility", "auto")
			== (RendererFamily.method() != RendererFamily.COMPATIBILITY),
		"live defaults on %s: Automatic and Forward+ start the same renderer" % RendererFamily.method())

func _build_window() -> Control:
	var window := Settings.new() as Control
	root.add_child(window)
	await process_frame
	return window

func _option(window: Control, key: String) -> OptionButton:
	return (window.get("panel") as Control).find_child(key, true, false) as OptionButton

func _items(option: OptionButton) -> Array:
	var result := []
	for index: int in option.item_count:
		result.append([option.get_item_text(index), option.get_item_metadata(index)])
	return result

func _check_window_live() -> void:
	Settings.renderers_for_tests = []
	OS.unset_environment(RendererPolicy.INTEGRATED_VARIABLE)
	var window := await _build_window()
	var option := _option(window, "renderer")
	if expect(option != null, "Graphics offers the renderer choice"):
		var expected := Settings.renderer_choices(RendererPolicy.supported_renderers())
		var values := []
		for index: int in option.item_count:
			values.append(option.get_item_metadata(index))
			var label := option.get_item_text(index)
			expect(label != "Forward+" or option.get_item_metadata(index) == "forward_plus",
				"only the Forward+ item is labelled Forward+")
		expect(values == Array(expected), "the window offers what the launch code can start: %s" % str(values))
		expect(option.get_item_text(0) == "Automatic (Forward+)",
			"the policy is off, so Automatic names Forward+: " + option.get_item_text(0))
		expect(option.tooltip_text.begins_with("Running now: " + Settings.renderer_name(RendererFamily.method()))
			and option.tooltip_text.ends_with("Compatibility launchers take precedence."),
			"the tooltip names the running renderer:\n" + option.tooltip_text)
		if "mobile" in LaunchOptions.RENDERERS:
			expect("mobile" in values, "Mobile is offered now that the launch code starts it")
		else:
			print("SKIP: Mobile is offered once LaunchOptions can start it (MOB-C3u, B8); offered now: ", values)
	# The game cannot see engine flags, so a headless run with
	# --rendering-method gl_compatibility looks like Forward+ falling back.
	var expected_note := Settings.renderer_fallback_text(RendererPolicy.launch_values(),
		Settings.launch_asked(RendererPolicy.launch), RendererFamily.method(), RendererPolicy.default_renderer())
	var note := window.get("renderer_fallback_note") as Label
	expect(note != null and note.text == expected_note and note.visible == (not expected_note.is_empty())
		and (RendererFamily.method() == RendererFamily.COMPATIBILITY or expected_note.is_empty()),
		"the fallback note follows this launch (%s): '%s'" % [RendererFamily.method(), expected_note])
	window.queue_free()
	await process_frame

func _check_window_mobile(path: String) -> void:
	# A tester's profile: the policy is on for this launch, Mobile is
	# recorded and confirmed, the game runs Mobile, and the launch code can
	# start it (as it can once MOB-C3u is in).
	Settings.renderers_for_tests = ALL
	OS.set_environment(RendererPolicy.INTEGRATED_VARIABLE, "mobile")
	RendererPolicy.launch = {"effective": "mobile", "requested": "mobile", "fallback": false,
		"values": {"renderer": "auto", "auto_renderer": "mobile", "auto_renderer_basis": "integrated_gpu",
			"auto_renderer_adapter": "Intel(R) UHD Graphics 620", "auto_renderer_state": "ok",
			"auto_renderer_attempts": 0, "recorded": true}}
	RendererFamily.override_for_tests("mobile")
	var config := ConfigFile.new()
	config.set_value(HardwareTier.SECTION, HardwareTier.TIER_KEY, "low")
	config.save(path)
	var window := await _build_window()
	var option := _option(window, "renderer")
	if expect(option != null, "Graphics offers the renderer choice (Mobile profile)"):
		expect(_items(option) == [["Automatic (Mobile)", "auto"], ["Forward+", "forward_plus"],
				["Mobile", "mobile"], ["OpenGL Compatibility", "gl_compatibility"]],
			"four choices, Automatic naming Mobile: %s" % str(_items(option)))
		var lines := option.tooltip_text.split("\n")
		expect(lines[0].begins_with("Running now: Mobile") and Settings.RENDERER_PURPOSES.mobile in lines,
			"the tooltip says Mobile is running, not Forward+:\n" + option.tooltip_text)
		var picked := []
		window.connect("setting_changed", func(section: String, key: String, value: Variant) -> void:
			picked.append([section, key, value]))
		option.select(2)
		option.item_selected.emit(2)
		expect(picked == [["Graphics", "renderer", "mobile"]], "picking Mobile asks to save renderer=mobile: %s" % str(picked))
		window.call("restore_value", "renderer", "mobile")
		expect(option.selected == 2, "a saved Mobile choice is shown as Mobile")
	var tier_note := (window.get("panel") as Control).find_child("HardwareTierNote", true, false) as Label
	expect(tier_note != null and tier_note.text == Settings.hardware_tier_note("low", "mobile"),
		"the first-run note mentions the Mobile renderer")
	var note := window.get("renderer_fallback_note") as Label
	expect(note != null and not note.visible, "no fallback note while Mobile runs")
	window.queue_free()
	await process_frame
	RendererFamily.override_for_tests("")

func _check_window_fallback() -> void:
	# Mobile was asked for and the engine fell back to OpenGL (reconcile marks
	# the trial failed_fallback; `requested` then names what Automatic starts
	# next, `asked` what this launch asked for).
	Settings.renderers_for_tests = ALL
	OS.set_environment(RendererPolicy.INTEGRATED_VARIABLE, "mobile")
	RendererPolicy.launch = {"effective": "auto", "requested": "forward_plus", "asked": "mobile", "fallback": true,
		"values": {"renderer": "auto", "auto_renderer": "mobile", "auto_renderer_state": "failed_fallback",
			"auto_renderer_attempts": 1, "recorded": true}}
	RendererFamily.override_for_tests("gl_compatibility")
	var window := await _build_window()
	var option := _option(window, "renderer")
	if expect(option != null, "Graphics offers the renderer choice (fallback)"):
		expect(option.get_item_text(0) == "Automatic (Forward+)", "after the failure Automatic names Forward+")
		expect(option.tooltip_text.begins_with("Running now: OpenGL Compatibility"),
			"the tooltip names OpenGL Compatibility as running")
	var note := window.get("renderer_fallback_note") as Label
	expect(note != null and note.visible and note.text == Settings.renderer_fallback_text(
			RendererPolicy.launch.values, "mobile", "gl_compatibility") and note.text.begins_with("Mobile could not start"),
		"the fallback note says Mobile could not start: " + (note.text if note != null else "<none>"))
	var panel := window.get("panel") as Control
	var page := note.get_parent() if note != null else null
	var notice := panel.find_child("GraphicsRestartNotice", true, false)
	expect(page != null and notice != null and note.get_index() < notice.get_index()
		and option != null and page.find_child("renderer", true, false) == option,
		"the fallback note sits on the Graphics page, before the restart notice")
	window.queue_free()
	await process_frame
	RendererFamily.override_for_tests("")

## The fallback note from the decision `reconcile` really records (not a
## hand-made one): after it marks the trial failed_fallback, `requested` names
## what Automatic starts next (Forward+), so the note must use what this launch
## asked for (`asked`, Mobile) or it says Forward+ could not start.
func _check_window_reconciled_fallback() -> void:
	var file_path := "user://test_settings_renderer_fallback.cfg"
	var ordinary := {"web": false, "headless": false, "engine_args": PackedStringArray(),
		"user_args": PackedStringArray(), "overrides": PackedStringArray()}
	var context := {"method": "gl_compatibility", "platform": "Windows", "launch": ordinary,
		"policy": RendererPolicy.policy("mobile"), "supported": ALL, "migrate_existing": false}
	var settled := {"tier": "low", "adapter_class": "integrated", "adapter": "Intel(R) UHD Graphics 620",
		"applied": false, "reason": "saved_settings"}
	for attempts: int in [0, 1]:
		_write_trial(file_path, attempts)
		var result := RendererPolicy.reconcile(settled, file_path, context)
		expect(result.action == "failed_fallback" and result.get("asked") == "mobile" and bool(result.fallback),
			"reconcile: a Mobile trial (attempts %d) that fell back to OpenGL asked for Mobile: %s" % [attempts, result])
		RendererPolicy.launch = result
		Settings.renderers_for_tests = ALL
		OS.set_environment(RendererPolicy.INTEGRATED_VARIABLE, "mobile")
		RendererFamily.override_for_tests("gl_compatibility")
		var window := await _build_window()
		var note := window.get("renderer_fallback_note") as Label
		expect(note != null and note.visible and note.text == "Mobile could not start on this computer, so the game is using OpenGL Compatibility. Automatic uses Forward+ from the next start.",
			"the reconciled fallback note names Mobile, not Forward+: " + (note.text if note != null else "<none>"))
		var option := _option(window, "renderer")
		expect(option != null and option.get_item_text(0) == "Automatic (Forward+)",
			"after the reconciled failure Automatic names Forward+")
		window.queue_free()
		await process_frame
	# The restart into Mobile came back on Forward+: no OpenGL, only the record.
	_write_trial(file_path, 1)
	var restart_context := context.duplicate(true)
	restart_context.method = "forward_plus"
	restart_context.launch.user_args = PackedStringArray([LaunchOptions.RENDERER_RESTART])
	var restarted := RendererPolicy.reconcile(settled, file_path, restart_context)
	expect(restarted.action == "failed_fallback" and restarted.get("asked") == "mobile"
		and Settings.renderer_fallback_text(restarted.values, str(restarted.asked), "forward_plus")
			== "Mobile could not start on this computer, so Automatic uses Forward+.",
		"a restart into Mobile that came back on Forward+: %s" % restarted)
	DirAccess.remove_absolute(ProjectSettings.globalize_path(file_path))
	RendererFamily.override_for_tests("")

func _write_trial(file_path: String, attempts: int) -> void:
	var config := ConfigFile.new()
	config.set_value("graphics", "hardware_tier", "low")
	config.set_value("graphics", "renderer", "auto")
	config.set_value("graphics", RendererPolicy.KEY_RENDERER, "mobile")
	config.set_value("graphics", RendererPolicy.KEY_BASIS, "integrated_gpu")
	config.set_value("graphics", RendererPolicy.KEY_ADAPTER, "Intel(R) UHD Graphics 620")
	config.set_value("graphics", RendererPolicy.KEY_STATE, "trial")
	config.set_value("graphics", RendererPolicy.KEY_ATTEMPTS, attempts)
	config.save(file_path)
