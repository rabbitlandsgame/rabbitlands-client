extends SceneTree
## N0: the shared verified native loader (`src/runtime/native_library.gd`) and
## its two callers, `ClientRuntimeController` and `cape_native_math.gd`.
## Each fixture payload in user:// fails a check before any load, so no fake
## library ever reaches `load_extension`; the real payload is exercised in the
## default directory. `--expect-native=present|absent` turns an unavailable
## or unexpected payload into a failure, as in test_client_runtime.gd.
## The web late-load refusal cannot run headless on desktop; it is the
## documented backstop behind the platform check.

const NativeLibrary := preload("res://src/runtime/native_library.gd")
const Controller := preload("res://src/runtime/client_runtime.gd")
const CapeNativeMath := preload("res://src/actors/cape_native_math.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> bool:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
	return ok

## Fixture payloads and what each caller reported for them before N0 (the
## reasons are the pre-N0 strings of client_runtime.gd and cape_native_math.gd).
## `manifest`: null = no manifest file, a String = raw text, a Dictionary =
## JSON. `@lib` / `@desc` / `@LIB` become the (upper-case) SHA-256 of the
## fixture files. `files`: name -> text; `@library` is this OS's library name.
static func cases() -> Array:
	var version := Engine.get_version_info()
	var base := {"abi": 1, "engine_major": int(version.major), "engine_minor": int(version.minor),
		"platform": NativeLibrary.platform(), "architecture": "x86_64", "library": NativeLibrary.library_name(),
		"library_sha256": "@lib", "descriptor_sha256": "@desc"}
	var both := {"@library": "fixture-not-a-native-library", "client_runtime.gdextension": "fixture-not-a-descriptor"}
	var rows: Array = []
	var add := func(name: String, manifest: Variant, files: Dictionary, code: String, runtime: String, cape: String) -> void:
		rows.append({"name": name, "manifest": manifest, "files": files, "code": code, "runtime": runtime, "cape": cape})
	var with := func(changes: Dictionary) -> Dictionary:
		var value := base.duplicate()
		for key: String in changes:
			if typeof(changes[key]) == TYPE_NIL:
				value.erase(key)
			else:
				value[key] = changes[key]
		return value
	add.call("no manifest", null, {}, "absent", "optional_runtime_absent", "payload_absent")
	add.call("manifest not JSON", "{ invalid manifest", both, "manifest_invalid", "manifest_invalid", "manifest_invalid")
	add.call("manifest a JSON array", "[1, 2]", both, "manifest_invalid", "manifest_invalid", "manifest_invalid")
	add.call("empty manifest object", "{}", both, "api_mismatch", "api_mismatch", "incompatible_payload")
	add.call("ABI 99", with.call({"abi": 99}), both, "api_mismatch", "api_mismatch", "incompatible_payload")
	add.call("ABI missing", with.call({"abi": null}), both, "api_mismatch", "api_mismatch", "incompatible_payload")
	add.call("engine major + 1", with.call({"engine_major": int(version.major) + 1}), both, "api_mismatch", "api_mismatch", "incompatible_payload")
	add.call("engine minor + 1", with.call({"engine_minor": int(version.minor) + 1}), both, "api_mismatch", "api_mismatch", "incompatible_payload")
	add.call("other platform", with.call({"platform": "fixture-platform"}), both, "unsupported_platform", "unsupported_platform", "incompatible_payload")
	add.call("architecture arm64", with.call({"architecture": "arm64"}), both, "unsupported_platform", "unsupported_platform", "incompatible_payload")
	add.call("architecture debug (an engine feature)", with.call({"architecture": "debug"}), both, "unsupported_platform", "unsupported_platform", "incompatible_payload")
	add.call("architecture missing", with.call({"architecture": null}), both, "unsupported_platform", "unsupported_platform", "incompatible_payload")
	add.call("another OS's library name", with.call({"library": "client_runtime.fixture"}), both, "unsupported_platform", "unsupported_platform", "incompatible_payload")
	add.call("library name empty", with.call({"library": ""}), both, "unsupported_platform", "unsupported_platform", "incompatible_payload")
	add.call("library and descriptor missing", with.call({}), {}, "incomplete", "optional_runtime_incomplete", "checksum_mismatch")
	add.call("descriptor missing", with.call({}), {"@library": "fixture-not-a-native-library"}, "incomplete", "optional_runtime_incomplete", "checksum_mismatch")
	add.call("library missing", with.call({}), {"client_runtime.gdextension": "fixture-not-a-descriptor"}, "incomplete", "optional_runtime_incomplete", "checksum_mismatch")
	add.call("library checksum wrong", with.call({"library_sha256": "incorrect"}), both, "checksum_mismatch", "runtime_checksum_mismatch", "checksum_mismatch")
	add.call("descriptor checksum wrong", with.call({"descriptor_sha256": "incorrect"}), both, "checksum_mismatch", "runtime_checksum_mismatch", "checksum_mismatch")
	add.call("library checksum upper-case", with.call({"library_sha256": "@LIB"}), both, "checksum_mismatch", "runtime_checksum_mismatch", "checksum_mismatch")
	add.call("checksums missing", with.call({"library_sha256": null, "descriptor_sha256": null}), both, "checksum_mismatch", "runtime_checksum_mismatch", "checksum_mismatch")
	# Passes every check. Only verify() sees it: loading would dlopen a text file.
	add.call("verified fixture (never loaded)", with.call({}), both, "verified", "", "")
	return rows

static func write_case(directory: String, row: Dictionary) -> void:
	var absolute := ProjectSettings.globalize_path(directory)
	DirAccess.make_dir_recursive_absolute(absolute)
	for name: String in DirAccess.get_files_at(absolute):
		DirAccess.remove_absolute(absolute.path_join(name))
	var digests := {}
	for name: String in row.files:
		var file_name := NativeLibrary.library_name() if name == "@library" else name
		var file := FileAccess.open(absolute.path_join(file_name), FileAccess.WRITE)
		file.store_string(str(row.files[name]))
		file.close()
		digests[name] = str(row.files[name]).sha256_text()
	if typeof(row.manifest) == TYPE_NIL:
		return
	var text := str(row.manifest)
	if row.manifest is Dictionary:
		var manifest: Dictionary = (row.manifest as Dictionary).duplicate()
		for key: String in manifest:
			match str(manifest[key]):
				"@lib": manifest[key] = str(digests.get("@library", ""))
				"@LIB": manifest[key] = str(digests.get("@library", "")).to_upper()
				"@desc": manifest[key] = str(digests.get("client_runtime.gdextension", ""))
		text = JSON.stringify(manifest)
	var file := FileAccess.open(absolute.path_join(NativeLibrary.MANIFEST_NAME), FileAccess.WRITE)
	file.store_string(text)
	file.close()

static func remove_case(directory: String) -> void:
	var absolute := ProjectSettings.globalize_path(directory)
	if not DirAccess.dir_exists_absolute(absolute):
		return
	for name: String in DirAccess.get_files_at(absolute):
		DirAccess.remove_absolute(absolute.path_join(name))
	DirAccess.remove_absolute(absolute)

func _helpers() -> void:
	var expected_platform: String = {"Windows": "windows", "Linux": "linux", "macOS": "macos"}.get(OS.get_name(), "unsupported")
	_expect(NativeLibrary.platform() == expected_platform, "platform id follows the OS name")
	_expect(NativeLibrary.library_name("windows") == "client_runtime.dll" and NativeLibrary.library_name("linux") == "client_runtime.so"
		and NativeLibrary.library_name("macos") == "client_runtime.dylib" and NativeLibrary.library_name("unsupported") == "",
		"library names per platform; none for an unsupported platform")
	var expected_directory := ProjectSettings.globalize_path("res://bin/client_runtime") if OS.has_feature("editor") \
		else OS.get_executable_path().get_base_dir().path_join("bin/client_runtime")
	_expect(NativeLibrary.default_directory() == expected_directory, "default directory is the editor project's or the executable's bin/client_runtime")
	for code: String in NativeLibrary.REFUSED:
		_expect(NativeLibrary.refused(code), "%s counts as refused before loading" % code)
	for code: String in ["verified", "loaded", "late_load_refused", "off_main_thread", "extension_unavailable"]:
		_expect(not NativeLibrary.refused(code), "%s is not a pre-load refusal" % code)
	_expect(Controller.ABI == NativeLibrary.ABI, "the controller checks runtime_info() against the loader's manifest ABI")

func _fixtures() -> void:
	var directory := "user://native-library-fixture-%d" % OS.get_process_id()
	var previous_mode := OS.get_environment("RABBITLANDS_CLIENT_RUNTIME")
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "compare")
	var controller := Controller.new()
	for row: Dictionary in cases():
		remove_case(directory)
		if typeof(row.manifest) != TYPE_NIL or not (row.files as Dictionary).is_empty():
			write_case(directory, row)
		var absolute := ProjectSettings.globalize_path(directory)
		var verified := NativeLibrary.verify(absolute)
		_expect(str(verified.code) == str(row.code) and bool(verified.ok) == (row.code == "verified"),
			"%s: verify code %s (got %s)" % [row.name, row.code, verified.code])
		_expect(str(verified.directory) == absolute, "%s: result names the directory" % row.name)
		_expect(CapeNativeMath.reason_for(verified) == str(row.cape),
			"%s: cape math reason '%s' (got '%s')" % [row.name, row.cape, CapeNativeMath.reason_for(verified)])
		if row.code == "verified":
			_expect(str(verified.library_path) == absolute.path_join(NativeLibrary.library_name())
				and str(verified.descriptor_path) == absolute.path_join(NativeLibrary.DESCRIPTOR_NAME)
				and (verified.manifest as Dictionary).get("abi") == 1.0,
				"%s: verified result carries the manifest and both paths" % row.name)
			continue
		var loads_before := int(NativeLibrary.stats().loads)
		var loaded := NativeLibrary.load_verified(absolute)
		_expect(str(loaded.code) == str(row.code) and not bool(loaded.ok) and int(loaded.load_status) == -1
			and int(NativeLibrary.stats().loads) == loads_before,
			"%s: load_verified refuses with the same code and never calls load_extension" % row.name)
		controller.initialize(absolute)
		var snapshot := controller.snapshot()
		_expect(snapshot.reason == row.runtime and snapshot.mode == "legacy" and not snapshot.native_available
			and controller.native_runtime() == null,
			"%s: client runtime reason '%s' (got '%s') and stays legacy" % [row.name, row.runtime, snapshot.reason])
		if row.name == "empty manifest object":
			_expect(controller._manifest == {}, "a parsed empty manifest object replaces the controller's manifest, as before")
		elif row.name == "ABI 99":
			_expect(int(controller._manifest.get("abi", 0)) == 99, "a parsed manifest is kept on the controller, as before")
		controller.close()
	# Before N0 an absent or unparsable manifest left the previous manifest in
	# place (benchmark_resource_admission reads it); keep that.
	write_case(directory, {"manifest": {"abi": 77}, "files": {}})
	controller.initialize(ProjectSettings.globalize_path(directory))
	remove_case(directory)
	controller.initialize(ProjectSettings.globalize_path(directory))
	_expect(controller.snapshot().reason == "optional_runtime_absent" and int(controller._manifest.get("abi", 0)) == 77,
		"an absent manifest leaves the controller's last parsed manifest in place, as before")
	controller.close()
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", previous_mode)

## A worker thread must never be the one that loads the library (review fix):
## load_verified() and ensure() answer off_main_thread, load nothing, and
## ensure() does not remember it, so the main thread's first ensure() loads.
func _off_main_thread() -> void:
	NativeLibrary.reset_for_tests()
	var preverified := NativeLibrary.verify()
	var loads_before := int(NativeLibrary.stats().loads)
	var worker := Thread.new()
	worker.start(func() -> Array: return [NativeLibrary.load_verified(), NativeLibrary.ensure()])
	var answers: Array = worker.wait_to_finish()
	var expected := "off_main_thread" if bool(preverified.ok) else str(preverified.code)
	_expect(str(answers[0].code) == expected and not bool(answers[0].ok),
		"worker-thread load_verified answers %s (got %s)" % [expected, answers[0].code])
	_expect(str(answers[1].code) == expected and not bool(answers[1].ok),
		"worker-thread ensure answers %s (got %s)" % [expected, answers[1].code])
	_expect(int(NativeLibrary.stats().loads) == loads_before and not ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS),
		"a worker thread never calls load_extension")
	if bool(preverified.ok):
		_expect(not bool(NativeLibrary.stats().ensured), "an off_main_thread answer is not remembered by ensure()")
	NativeLibrary.reset_for_tests()

func _ensure_once() -> void:
	NativeLibrary.reset_for_tests()
	var first := NativeLibrary.ensure()
	var after_first: Dictionary = NativeLibrary.stats()
	var second := NativeLibrary.ensure()
	var after_second: Dictionary = NativeLibrary.stats()
	_expect(bool(after_first.ensured) and str(after_first.code) == str(first.code), "ensure records its result")
	_expect(first == second and int(after_second.verifications) == int(after_first.verifications)
		and int(after_second.loads) == int(after_first.loads), "a second ensure() neither re-verifies nor reloads")
	second.code = "caller-mutated"
	_expect(str(NativeLibrary.ensure().code) == str(first.code), "callers get a copy of the ensure() result")
	_expect(str(first.directory) == NativeLibrary.default_directory(), "ensure() uses the default directory")

func _real_payload() -> void:
	var args := OS.get_cmdline_user_args()
	var cape_mode := OS.get_environment("RABBITLANDS_CAPE_MATH")
	OS.set_environment("RABBITLANDS_CAPE_MATH", "off")
	_expect(not CapeNativeMath.ready() and str(CapeNativeMath.stats().reason) == "script_selected"
		and not bool(NativeLibrary.stats().ensured), "RABBITLANDS_CAPE_MATH=off selects script math without touching the loader")
	OS.set_environment("RABBITLANDS_CAPE_MATH", cape_mode)
	var preverified := NativeLibrary.verify()
	if args.has("--expect-native=present") or args.has("--expect-native"):
		_expect(bool(preverified.ok), "requested native-present run has a verified payload (%s)" % preverified.code)
	elif args.has("--expect-native=absent"):
		_expect(not bool(preverified.ok), "requested native-absent run has no verified payload (%s)" % preverified.code)
	var registered_before := ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS)
	_expect(not registered_before, "nothing loaded the runtime before the cape check")
	# Cape math is the first caller: it loads through ensure().
	var cape_ready := CapeNativeMath.ready()
	var cape: Dictionary = CapeNativeMath.stats()
	var ensured: Dictionary = NativeLibrary.stats()
	if not bool(preverified.ok):
		_expect(not cape_ready and str(cape.reason) == CapeNativeMath.reason_for(preverified),
			"cape math without a payload reports %s" % cape.reason)
		_expect(int(ensured.loads) == 0 and not ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS), "a refused payload is never loaded")
		print("SKIP: real payload checks; optional native payload is unavailable (", preverified.code, ")")
		return
	_expect(cape_ready and str(cape.reason) == "native_arithmetic", "cape math loads the verified payload itself (%s)" % cape.reason)
	_expect(bool(ensured.ensured) and str(ensured.code) == "loaded" and int(ensured.loads) == 1,
		"cape math loaded through the one ensure() (loads=%d)" % int(ensured.loads))
	_expect(ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS), "the runtime class is registered")
	var again := NativeLibrary.load_verified()
	_expect(bool(again.ok) and str(again.code) == "loaded" and int(again.load_status) == -1
		and int(NativeLibrary.stats().loads) == 1, "re-verifying a registered runtime does not load it twice")
	var previous_mode := OS.get_environment("RABBITLANDS_CLIENT_RUNTIME")
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "compare")
	var controller := Controller.new()
	var verifications := int(NativeLibrary.stats().verifications)
	controller.initialize()
	var snapshot := controller.snapshot()
	_expect(snapshot.native_available and snapshot.mode == "compare" and snapshot.reason == "native_comparison_legacy_presentation",
		"client runtime uses the already registered payload (%s)" % snapshot.reason)
	_expect(int(NativeLibrary.stats().verifications) == verifications + 1, "client runtime re-verifies on initialize, as before")
	_expect(str(controller._manifest.get("library_sha256", "")) == str((preverified.manifest as Dictionary).get("library_sha256", "")),
		"client runtime keeps the verified manifest")
	controller.close()
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", previous_mode)

func _run() -> void:
	_helpers()
	_fixtures()
	_off_main_thread()
	_real_payload()
	_ensure_once()
	print("native library tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
