extends SceneTree
## RB-C1g: the native runtime's kill switches and startup load (owner D-NATIVE,
## 2026-11-04) and the one kernel loader (src/runtime/native_crowd.gd).
##
## 1. Pure: NativeLibrary.resolve_switch precedence (argument > environment >
##    safe mode > settings > default) and spellings; NativeCrowd.selection for
##    both values of every default; the provider rule.
## 2. The support setting in a scratch cfg (never the player's file).
## 3. Switched off (RABBITLANDS_NATIVE_RUNTIME=off in this process):
##    load_verified/ensure/startup refuse without reading the payload; the client
##    runtime controller, ContentDigest, cape arithmetic and every kernel stay on
##    GDScript, the benchmark provider included.
## 4. Switched on (auto): unselected kernels never load the payload; a selected
##    kernel loads it through NativeLibrary.ensure() and is used only from the
##    client_runtime provider; the switch turned off again refuses registered
##    classes too. Without a payload (`--expect-native=absent`, or none built)
##    a selected kernel reports runtime_absent.
## `--expect-native=present|absent` (user argument) makes the payload state a
## failure instead of a NOTE.

const NativeLibrary := preload("res://src/runtime/native_library.gd")
const NativeCrowd := preload("res://src/runtime/native_crowd.gd")
const Controller := preload("res://src/runtime/client_runtime.gd")
const CapeNativeMath := preload("res://src/actors/cape_native_math.gd")
const SCRATCH := "user://rb_c1g_switch_fixture.cfg"
const VARIABLES: Array[String] = ["RABBITLANDS_NATIVE_RUNTIME", "ELORIA_NATIVE_PRESENTATION",
	"ELORIA_NATIVE_CROWD", "ELORIA_NATIVE_PROVIDER", "RABBITLANDS_CLIENT_RUNTIME", "RABBITLANDS_CONTENT_DIGEST"]

var failures := 0
var _saved := {}


func _init() -> void:
	call_deferred("_run")


func _expect(ok: bool, message: String) -> bool:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
	return ok


func _run() -> void:
	for name: String in VARIABLES:
		_saved[name] = OS.get_environment(name)
		OS.set_environment(name, "")
	_pure_switch()
	_pure_selection()
	_settings_file()
	_switched_off()
	_switched_on()
	for name: String in VARIABLES:
		OS.set_environment(name, str(_saved[name]))
	print("native runtime switches: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)


func _switch(environment: String, arguments: Array, stored: Variant) -> Dictionary:
	return NativeLibrary.resolve_switch(environment, PackedStringArray(arguments), stored)


func _is(state: Dictionary, mode: String, source: String, invalid := []) -> bool:
	return str(state.mode) == mode and str(state.source) == source \
		and JSON.stringify(Array(state.invalid)) == JSON.stringify(invalid) \
		and str(state.reason) == source + "_" + mode


func _pure_switch() -> void:
	_expect(_is(_switch("", [], null), "auto", "default"), "no switch: the payload loads (default auto)")
	for spelling: String in NativeLibrary.OFF_SPELLINGS + [" OFF ", "Off"]:
		_expect(_is(_switch(spelling, [], null), "off", "environment"),
			"RABBITLANDS_NATIVE_RUNTIME='%s' switches the runtime off" % spelling)
	for spelling: String in NativeLibrary.ON_SPELLINGS + [" Auto "]:
		_expect(_is(_switch(spelling, [], null), "auto", "environment"),
			"RABBITLANDS_NATIVE_RUNTIME='%s' keeps it on" % spelling)
	_expect(_is(_switch("bogus", [], null), "auto", "default", ["environment"]),
		"an unknown environment value counts as not given and is reported")
	_expect(_is(_switch("", ["--native-runtime=off"], null), "off", "argument"), "--native-runtime=off")
	_expect(_is(_switch("off", ["--native-runtime=auto"], null), "auto", "argument"),
		"the argument wins over the environment")
	_expect(_is(_switch("off", ["--native-runtime="], null), "off", "environment", ["argument"]),
		"an empty argument is invalid and the environment decides")
	_expect(_is(_switch("", ["--client-safe-mode"], null), "off", "safe_mode") and
		bool(_switch("", ["--client-safe-mode"], null).safe_mode), "safe mode switches the runtime off")
	_expect(_is(_switch("auto", ["--client-safe-mode"], null), "auto", "environment"),
		"an explicit valid value wins over safe mode (as --content-digest does)")
	_expect(_is(_switch("bogus", ["--client-safe-mode"], null), "off", "safe_mode", ["environment"]),
		"an invalid value cannot turn safe mode back on")
	_expect(_is(_switch("", ["--client-safe-mode"], "auto"), "off", "safe_mode"),
		"the setting cannot turn safe mode back on")
	_expect(_is(_switch("", ["--client-compatibility"], null), "auto", "default"),
		"the compatibility launch (renderer only) keeps the runtime")
	_expect(_is(_switch("", [], "off"), "off", "settings"), "settings 'off' switches it off")
	_expect(_is(_switch("", [], false), "off", "settings"), "settings false switches it off")
	_expect(_is(_switch("", [], true), "auto", "settings"), "settings true keeps it on")
	_expect(_is(_switch("", [], "auto"), "auto", "settings"), "settings 'auto' keeps it on")
	_expect(_is(_switch("", [], 42), "auto", "default", ["settings"]), "an unknown setting is reported, default kept")
	_expect(_is(_switch("on", [], "off"), "auto", "environment"), "the environment wins over the setting")
	_expect(_is(_switch("", ["--native-runtime=on"], "off"), "auto", "argument"), "the argument wins over the setting")
	_expect(NativeLibrary.switch_mode(&"off") == "off" and NativeLibrary.switch_mode(null) == ""
		and NativeLibrary.switch_mode(0) == "", "switch_mode spellings: StringName, null, int")


func _pure_selection() -> void:
	var presentation := {"cape": ["cape"], "flight": ["flight"], "both": ["cape", "flight"],
		"1": ["cape", "flight"], "world": ["world"], "all": ["cape", "flight", "world"],
		" ALL ": ["cape", "flight", "world"]}
	var all_on := {"cape": true, "flight": true, "world": true, "reducer": true}
	for defaults: Dictionary in [NativeCrowd.DEFAULTS, all_on]:
		var label := "defaults on" if defaults == all_on else "shipped defaults"
		for feature: String in ["cape", "flight", "world"]:
			var by_default := NativeCrowd.selection(feature, {"ELORIA_NATIVE_PRESENTATION": ""}, defaults)
			_expect(bool(by_default.wanted) == bool(defaults[feature]),
				"%s: unset selects %s's default (%s)" % [label, feature, by_default])
			for off: String in ["0", "off", "script", "gdscript", "legacy", "unknown"]:
				_expect(not bool(NativeCrowd.selection(feature, {"ELORIA_NATIVE_PRESENTATION": off}, defaults).wanted),
					"%s: '%s' keeps %s on GDScript" % [label, off, feature])
			for mode: String in presentation:
				var wanted := bool(NativeCrowd.selection(feature, {"ELORIA_NATIVE_PRESENTATION": mode}, defaults).wanted)
				_expect(wanted == (feature in presentation[mode]),
					"%s: '%s' selects %s = %s" % [label, mode, feature, feature in presentation[mode]])
		_expect(bool(NativeCrowd.selection("reducer", {"ELORIA_NATIVE_CROWD": ""}, defaults).wanted) == bool(defaults.reducer),
			"%s: unset ELORIA_NATIVE_CROWD selects the reducer's default" % label)
		_expect(bool(NativeCrowd.selection("reducer", {"ELORIA_NATIVE_CROWD": "1"}, defaults).wanted),
			"%s: ELORIA_NATIVE_CROWD=1 selects the reducer" % label)
		for off: String in ["0", "off", "legacy", "yes"]:
			_expect(not bool(NativeCrowd.selection("reducer", {"ELORIA_NATIVE_CROWD": off}, defaults).wanted),
				"%s: ELORIA_NATIVE_CROWD='%s' keeps the GDScript reducer" % [label, off])
	_expect(NativeCrowd.DEFAULTS.values().count(true) == 0,
		"D-NATIVE: every kernel and the reducer default off until its own release-build A/B")
	_expect(NativeCrowd.provider_trusted("client_runtime", false) and not NativeCrowd.provider_trusted("external", false)
		and not NativeCrowd.provider_trusted("", false) and not NativeCrowd.provider_trusted("absent", true)
		and NativeCrowd.provider_trusted("external", true) and NativeCrowd.provider_trusted("", true),
		"provider rule: client_runtime always; external or unknown only with the benchmark provider")
	_expect(NativeCrowd.benchmark_allowed({"ELORIA_NATIVE_PROVIDER": " Benchmark "})
		and not NativeCrowd.benchmark_allowed({"ELORIA_NATIVE_PROVIDER": "client_runtime"})
		and not NativeCrowd.benchmark_allowed({"ELORIA_NATIVE_PROVIDER": ""}),
		"only ELORIA_NATIVE_PROVIDER=benchmark names the benchmark extension")


func _settings_file() -> void:
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SCRATCH))
	_expect(NativeLibrary.saved_setting(SCRATCH) == null, "a missing settings file stores no switch")
	var config := ConfigFile.new()
	config.set_value("graphics", "quality", "low")
	config.save(SCRATCH)
	_expect(NativeLibrary.saved_setting(SCRATCH) == null, "a settings file without the key stores no switch")
	_expect(NativeLibrary.save_setting("OFF", SCRATCH) == OK and NativeLibrary.saved_setting(SCRATCH) == "off",
		"save_setting stores the normalised 'off'")
	var reread := ConfigFile.new()
	_expect(reread.load(SCRATCH) == OK and reread.get_value("graphics", "quality", "") == "low",
		"saving the switch keeps the other settings")
	_expect(NativeLibrary.save_setting("bogus", SCRATCH) == ERR_INVALID_PARAMETER
		and NativeLibrary.saved_setting(SCRATCH) == "off", "an unknown value is refused and nothing is written")
	_expect(_is(NativeLibrary.resolve_switch("", PackedStringArray(), NativeLibrary.saved_setting(SCRATCH)),
		"off", "settings"), "the stored setting switches the runtime off")
	_expect(NativeLibrary.save_setting(true, SCRATCH) == OK and NativeLibrary.saved_setting(SCRATCH) == "auto",
		"save_setting(true) stores 'auto'")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SCRATCH))
	_expect(NativeLibrary.SETTINGS_PATH == "user://eloria_hud.cfg" and NativeLibrary.SETTINGS_SECTION == "runtime"
		and NativeLibrary.SETTINGS_KEY == "native_runtime", "the support setting lives beside the client settings")


func _kernels(presentation: String, crowd: String) -> Dictionary:
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", presentation)
	OS.set_environment("ELORIA_NATIVE_CROWD", crowd)
	var made := {}
	for feature: String in ["cape", "flight", "world", "reducer"]:
		made[feature] = NativeCrowd.kernel(feature)
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", "")
	OS.set_environment("ELORIA_NATIVE_CROWD", "")
	return made


func _all_status(made: Dictionary, status: String) -> bool:
	return made.values().all(func(entry: Dictionary) -> bool:
		return entry.object == null and str(entry.status) == status)


func _switched_off() -> void:
	var registered := ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS)
	if not _expect(not registered, "nothing loaded the payload before the switch tests"):
		return
	OS.set_environment("RABBITLANDS_NATIVE_RUNTIME", "off")
	NativeLibrary.reset_for_tests()
	_expect(_is(NativeLibrary.switch_state(), "off", "environment"), "RABBITLANDS_NATIVE_RUNTIME=off in this process")
	var before: Dictionary = NativeLibrary.stats()
	var refused := NativeLibrary.load_verified()
	_expect(not bool(refused.ok) and str(refused.code) == NativeLibrary.SWITCHED_OFF and str(refused.switch) == "environment"
		and int(refused.load_status) == -1 and str(refused.directory) == NativeLibrary.default_directory(),
		"load_verified refuses with switched_off (%s)" % [refused])
	var fixture := NativeLibrary.load_verified("C:/nonexistent/client_runtime")
	_expect(str(fixture.code) == NativeLibrary.SWITCHED_OFF and str(fixture.directory) == "C:/nonexistent/client_runtime",
		"an explicit directory is refused too")
	var ensured := NativeLibrary.ensure()
	var started := NativeLibrary.startup()
	var after: Dictionary = NativeLibrary.stats()
	_expect(str(ensured.code) == NativeLibrary.SWITCHED_OFF and str(started.code) == NativeLibrary.SWITCHED_OFF
		and bool(after.ensured) and str(after.code) == NativeLibrary.SWITCHED_OFF,
		"ensure() and startup() remember switched_off")
	_expect(int(after.verifications) == int(before.verifications) and int(after.loads) == int(before.loads)
		and not ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS), "switched off, the payload is neither hashed nor loaded")
	var snapshot := NativeLibrary.snapshot()
	_expect(str(snapshot.switch) == "off" and str(snapshot.switch_source) == "environment"
		and str((snapshot.startup as Dictionary).get("code", "")) == NativeLibrary.SWITCHED_OFF
		and not bool(snapshot.registered), "snapshot reports the switch and the startup result (%s)" % [snapshot])
	# ensure() ran before startup() here, so the record must not pass off an
	# earlier caller's verify+load as its own (review fix).
	_expect(bool((snapshot.startup as Dictionary).get("prior", false)),
		"startup() after an earlier ensure() records prior=true (%s)" % [snapshot.startup])
	var first_startup: Dictionary = (snapshot.startup as Dictionary).duplicate()
	NativeLibrary.startup()
	_expect(NativeLibrary.snapshot().startup == first_startup, "a second startup() keeps the first record")
	# Client runtime controller (human-testing pilot): its own reason string.
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "compare")
	var controller := Controller.new()
	controller.initialize()
	var runtime: Dictionary = controller.snapshot()
	_expect(str(runtime.reason) == "native_runtime_switched_off" and str(runtime.mode) == "legacy"
		and not bool(runtime.native_available), "the client runtime controller reports native_runtime_switched_off (%s)" % runtime.reason)
	controller.close()
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "")
	# Content digest: an explicit native request falls back with the switch named.
	OS.set_environment("RABBITLANDS_CONTENT_DIGEST", "native")
	ContentDigest.reset()
	ContentDigest.initialize()
	var digest: Dictionary = ContentDigest.snapshot()
	_expect(str(digest.backend) == "gdscript" and str(digest.reason) == "native_unavailable_switched_off"
		and str((digest.native as Dictionary).get("code", "")) == NativeLibrary.SWITCHED_OFF,
		"ContentDigest native falls back to GDScript (%s, %s)" % [digest.backend, digest.reason])
	OS.set_environment("RABBITLANDS_CONTENT_DIGEST", "")
	ContentDigest.reset()
	# Mounted cape arithmetic stays on GDScript.
	_expect(not CapeNativeMath.ready(), "mounted cape arithmetic stays on GDScript")
	var cape_reason := str(CapeNativeMath.stats().reason)
	if cape_reason == "native_runtime_switched_off":
		_expect(true, "cape arithmetic names the switch")
	else:
		_expect(cape_reason == "arithmetic_api_unavailable", "cape arithmetic falls back (%s)" % cape_reason)
		print("NOTE: cape_native_math.gd does not map switched_off yet (RB-C1g hook pending); reason ", cape_reason)
	# Every kernel and the reducer, also with the benchmark provider named.
	_expect(_all_status(_kernels("all", "1"), "runtime_switched_off"),
		"switched off, every selected kernel and the reducer report runtime_switched_off")
	OS.set_environment("ELORIA_NATIVE_PROVIDER", "benchmark")
	_expect(_all_status(_kernels("all", "1"), "runtime_switched_off"), "the benchmark provider is switched off too")
	OS.set_environment("ELORIA_NATIVE_PROVIDER", "")
	_expect(_all_status(_kernels("", ""), "disabled"), "unselected kernels report disabled")
	_expect(not ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS) and int(NativeLibrary.stats().loads) == int(before.loads),
		"nothing above loaded the payload")
	OS.set_environment("RABBITLANDS_NATIVE_RUNTIME", "")
	NativeLibrary.reset_for_tests()
	NativeCrowd.reset_for_tests()


func _switched_on() -> void:
	var args := OS.get_cmdline_user_args()
	_expect(_is(NativeLibrary.switch_state(), "auto", "default"), "switch back to the default")
	_expect(_all_status(_kernels("", ""), "disabled") and not ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS)
		and not bool(NativeLibrary.stats().ensured), "unselected kernels never load the payload")
	var available := bool(NativeLibrary.verify().ok)
	if args.has("--expect-native=present"):
		_expect(available, "requested native-present run: the default payload verifies")
	elif args.has("--expect-native=absent"):
		_expect(not available, "requested native-absent run: no default payload")
	var loads := int(NativeLibrary.stats().loads)
	var made := _kernels("all", "1")
	if not available:
		_expect(_all_status(made, "runtime_" + str(NativeLibrary.verify().code)),
			"without a payload every selected kernel reports why (%s)" % [made.values().map(func(e: Dictionary) -> String: return e.status)])
		print("NOTE: no verified default payload; the provider checks below were skipped")
		return
	for feature: String in made:
		var entry: Dictionary = made[feature]
		_expect(entry.object != null and str(entry.status) == "active" and str(entry.provider) == "client_runtime"
			and (entry.object as Object).get_class() == str(NativeCrowd.CLASSES[feature]),
			"%s comes from the client_runtime payload (%s, %s)" % [feature, entry.status, entry.provider])
	_expect(bool(NativeLibrary.stats().ensured) and str(NativeLibrary.stats().code) == "loaded"
		and int(NativeLibrary.stats().loads) == loads + 1, "the first selected kernel loaded the payload once, through ensure()")
	_kernels("all", "1")
	_expect(int(NativeLibrary.stats().loads) == loads + 1, "later kernels reuse the loaded payload")
	var providers := NativeCrowd.providers()
	_expect(str(providers.get("NativeCapeConstraintKernel", "")) == "client_runtime"
		and str(providers.get("NativeCrowdReducer", "")) == "client_runtime", "providers come from runtime_info (%s)" % [providers])
	OS.set_environment("ELORIA_NATIVE_PROVIDER", "benchmark")
	var benchmark := _kernels("cape", "")
	_expect(str((benchmark.cape as Dictionary).status) == "active" and str((benchmark.cape as Dictionary).provider) == "client_runtime",
		"with the benchmark provider named, a class the payload registered is still the payload's")
	OS.set_environment("ELORIA_NATIVE_PROVIDER", "")
	var loaded_paths := Array(GDExtensionManager.get_loaded_extensions())
	_expect(loaded_paths.filter(func(path: String) -> bool: return path.get_file() == "native_crowd.gdextension").is_empty(),
		"the benchmark extension was never loaded (%s)" % [loaded_paths])
	var snapshot := NativeCrowd.snapshot()
	_expect(int(((snapshot.features as Dictionary).cape as Dictionary).active) >= 2
		and str(((snapshot.features as Dictionary).cape as Dictionary).last_status) == "active"
		and not bool(((snapshot.features as Dictionary).cape as Dictionary).selected),
		"the loader snapshot counts made kernels per feature (%s)" % [(snapshot.features as Dictionary).cape])
	# The switch wins over classes that are already registered.
	OS.set_environment("RABBITLANDS_NATIVE_RUNTIME", "off")
	NativeLibrary.reset_for_tests()
	_expect(_all_status(_kernels("all", "1"), "runtime_switched_off"),
		"switched off after a load, registered classes are refused too")
	OS.set_environment("RABBITLANDS_NATIVE_RUNTIME", "")
	NativeLibrary.reset_for_tests()
