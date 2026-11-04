extends RefCounted
## The one verified loader for the optional native payload `bin/client_runtime`:
## `client_runtime.dll` (`.so`, `.dylib`), its `client_runtime.gdextension`
## descriptor and `runtime-manifest.json`. Every caller that wants the library
## loaded goes through here, so the manifest, API, platform and checksum rules
## live in one place. Callers keep their own decisions and reason strings:
## `ClientRuntimeController` (the profile-gated mounted/compare/services pilot)
## and `cape_native_math.gd` (mounted cape arithmetic in any profile) map the
## codes below to the reasons their diagnostics and tests already report.
##
## No `class_name`: callers preload this file, like `memory_budgets.gd`.
##
## ## Checks, in order (the first failure is the result `code`)
##
## 1. `absent` - the directory has no `runtime-manifest.json`.
## 2. `manifest_invalid` - the manifest is not JSON or not an object.
## 3. `api_mismatch` - manifest `abi` is not `ABI`, or `engine_major` /
##    `engine_minor` differ from the running engine.
## 4. `unsupported_platform` - manifest `platform` is not this OS, `architecture`
##    is not `x86_64`, this build is not x86_64, or `library` is not this OS's
##    library name.
## 5. `incomplete` - the library or the descriptor file is missing.
## 6. `checksum_mismatch` - the SHA-256 of the library or the descriptor
##    differs from `library_sha256` / `descriptor_sha256`.
##
## `verify` stops there with `ok` and code `verified`. `load_verified` goes on:
##
## 7. `late_load_refused` - web. Web extensions must register during engine
##    startup; a late dlopen can wait on game threads indefinitely. (Today
##    step 4 already refuses every web manifest; this is the backstop.)
## 8. `off_main_thread` - `RUNTIME_CLASS` is not registered yet and the caller
##    is not the main thread. Nothing is loaded (see Threads).
## 9. `extension_unavailable` - after loading, `RUNTIME_CLASS` is not
##    registered.
## 10. `loaded` - `RUNTIME_CLASS` is registered. If it was registered before the
##    call (an earlier load), `load_extension` is not called again and
##    `load_status` is -1.
##
## These are compatibility and integrity checks, not a signature or a sandbox
## for untrusted libraries (`native/client_runtime/README.md`).
##
## ## Cost and caching
##
## `verify` and `load_verified` read the manifest and hash the library (about
## 1.3 MB) and descriptor on every call; nothing is remembered between calls.
## `ensure()` is the once-per-process entry point for the default directory: the
## first call verifies and loads, later calls return that first result without
## hashing again. Callers that must re-check (a controller re-initialising,
## fixtures in their own directory) call `load_verified(directory)`.
##
## ## Threads
##
## Loading is main-thread only: `GDExtensionManager.load_extension` registers
## classes. A worker thread that reaches the load step before anything was
## loaded gets `off_main_thread` instead, and `ensure()` does not remember that
## answer, so the main thread's first `ensure()` still loads. Once the runtime
## class is registered, any thread may verify and gets `loaded`.
##
## ## Startup load and kill switches (owner D-NATIVE, 2026-11-04)
##
## `Main._ready` calls `startup()`, so the verified payload is loaded for every
## desktop player who has one (Windows packages today) instead of on demand in
## the middle of play (the first mounted cape, the digest probe). Loading only
## registers classes: every native feature keeps its own default and switch
## (`native_crowd.gd` for the kernels and the reducer, `content_digest.gd`,
## `cape_native_math.gd`), and those defaults stay off until each feature's
## release-build A/B.
##
## One kill switch keeps the whole library unloaded, so every caller stays on
## its GDScript path. In order of precedence:
## 1. the user argument `--native-runtime=off` (or `auto`);
## 2. the environment `RABBITLANDS_NATIVE_RUNTIME=off` (or `auto`);
## 3. `--client-safe-mode`, the packaged safe-mode launch: off unless 1 or 2
##    names a valid value;
## 4. the support setting `[runtime] native_runtime = "off"` in
##    `user://eloria_hud.cfg` (`save_setting`; no settings-window control);
## 5. otherwise `auto`.
## Off spellings: OFF_SPELLINGS; on: ON_SPELLINGS; any other value counts as
## not given and is named in the result's `invalid`. The switch is resolved once
## per process (`switch_state()`). While it is off, `load_verified` and
## `ensure` return code `switched_off` before reading any file, so nothing is
## hashed or loaded; `verify`, which never loads, is unaffected.

const ABI := 1
const MANIFEST_NAME := "runtime-manifest.json"
const DESCRIPTOR_NAME := "client_runtime.gdextension"
const RUNTIME_CLASS := &"RabbitLandsClientRuntime"
const PLATFORMS := {"Windows": "windows", "Linux": "linux", "macOS": "macos"}
const LIBRARIES := {"windows": "client_runtime.dll", "linux": "client_runtime.so", "macos": "client_runtime.dylib"}
## Codes that mean the payload was refused before anything was loaded.
const REFUSED := ["absent", "manifest_invalid", "api_mismatch", "unsupported_platform", "incomplete", "checksum_mismatch"]
## The code `load_verified` and `ensure` return while the kill switch is off.
const SWITCHED_OFF := "switched_off"
const SWITCH_ENVIRONMENT := "RABBITLANDS_NATIVE_RUNTIME"
const SWITCH_ARGUMENT := "--native-runtime="
## The packaged safe-mode launch's user argument (launch_options.gd, the
## safe-mode launchers); content_digest.gd reads the same argument.
const SAFE_MODE_ARGUMENT := "--client-safe-mode"
const SETTINGS_PATH := "user://eloria_hud.cfg"
const SETTINGS_SECTION := "runtime"
const SETTINGS_KEY := "native_runtime"
const OFF_SPELLINGS: Array[String] = ["off", "0", "false", "no", "legacy", "gdscript", "script"]
const ON_SPELLINGS: Array[String] = ["auto", "on", "1", "true", "yes"]

static var _ensured := false
static var _ensure_result: Dictionary = {}
static var _verifications := 0
static var _loads := 0
static var _switch: Dictionary = {}
static var _switch_lock := Mutex.new()
static var _startup: Dictionary = {}

## `<executable>/bin/client_runtime`, or the project's `bin/client_runtime` in
## the editor and headless editor-binary runs.
static func default_directory() -> String:
	return ProjectSettings.globalize_path("res://bin/client_runtime") if OS.has_feature("editor") \
		else OS.get_executable_path().get_base_dir().path_join("bin/client_runtime")

## `windows`, `linux`, `macos`, or `unsupported`.
static func platform() -> String:
	return str(PLATFORMS.get(OS.get_name(), "unsupported"))

## The library file name this OS loads, or "" where no payload is supported.
static func library_name(platform_id := "") -> String:
	return str(LIBRARIES.get(platform() if platform_id.is_empty() else platform_id, ""))

## Checks 1-6 without loading anything. Returns `{ok, code, directory,
## manifest, library_path, descriptor_path, load_status}`; `manifest` is {}
## when there is no parsed object (codes `absent`, `manifest_invalid`).
static func verify(directory := "") -> Dictionary:
	_verifications += 1
	if directory.is_empty():
		directory = default_directory()
	var result := {"ok": false, "code": "absent", "directory": directory, "manifest": {},
		"library_path": "", "descriptor_path": "", "load_status": -1}
	var manifest_path := directory.path_join(MANIFEST_NAME)
	if not FileAccess.file_exists(manifest_path):
		return result
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(manifest_path)) != OK or not parser.data is Dictionary:
		result.code = "manifest_invalid"
		return result
	var manifest: Dictionary = parser.data
	result.manifest = manifest
	var version: Dictionary = Engine.get_version_info()
	if int(manifest.get("abi", -1)) != ABI or int(manifest.get("engine_major", -1)) != int(version.major) \
			or int(manifest.get("engine_minor", -1)) != int(version.minor):
		result.code = "api_mismatch"
		return result
	var expected_library := library_name()
	if str(manifest.get("platform", "")) != platform() or str(manifest.get("architecture", "")) != "x86_64" \
			or not OS.has_feature("x86_64") \
			or expected_library.is_empty() or str(manifest.get("library", "")) != expected_library:
		result.code = "unsupported_platform"
		return result
	var library_path := directory.path_join(expected_library)
	var descriptor_path := directory.path_join(DESCRIPTOR_NAME)
	result.library_path = library_path
	result.descriptor_path = descriptor_path
	if not FileAccess.file_exists(library_path) or not FileAccess.file_exists(descriptor_path):
		result.code = "incomplete"
		return result
	if FileAccess.get_sha256(library_path) != str(manifest.get("library_sha256", "")) \
			or FileAccess.get_sha256(descriptor_path) != str(manifest.get("descriptor_sha256", "")):
		result.code = "checksum_mismatch"
		return result
	result.ok = true
	result.code = "verified"
	return result

## Checks 1-10: verifies the payload in `directory` (default: `default_directory()`)
## and loads its descriptor. `ok` is true only for code `loaded`. While the
## kill switch is off it returns code `switched_off` (and `switch`, the source
## that turned it off) without reading any file.
static func load_verified(directory := "") -> Dictionary:
	var state := switch_state()
	if str(state.mode) == "off":
		return {"ok": false, "code": SWITCHED_OFF, "switch": str(state.source),
			"directory": default_directory() if directory.is_empty() else directory, "manifest": {},
			"library_path": "", "descriptor_path": "", "load_status": -1}
	var result := verify(directory)
	if not bool(result.ok):
		return result
	result.ok = false
	if OS.has_feature("web"):
		result.code = "late_load_refused"
		return result
	if not ClassDB.class_exists(RUNTIME_CLASS):
		if OS.get_thread_caller_id() != OS.get_main_thread_id():
			result.code = "off_main_thread"
			return result
		_loads += 1
		result.load_status = int(GDExtensionManager.load_extension(str(result.descriptor_path)))
	if not ClassDB.class_exists(RUNTIME_CLASS):
		result.code = "extension_unavailable"
		return result
	result.ok = true
	result.code = "loaded"
	return result

## Once per process: the first call runs `load_verified()` on the default
## directory; every later call returns a copy of that first result. An
## `off_main_thread` answer is returned but not remembered.
static func ensure() -> Dictionary:
	if not _ensured:
		var result := load_verified()
		if str(result.code) == "off_main_thread":
			return result
		_ensure_result = result
		_ensured = true
	return _ensure_result.duplicate(true)

## Whether `code` means the payload was refused before anything was loaded.
static func refused(code: String) -> bool:
	return code in REFUSED

static func stats() -> Dictionary:
	return {"ensured": _ensured, "code": str(_ensure_result.get("code", "")) if _ensured else "",
		"verifications": _verifications, "loads": _loads}

## Main._ready, once (owner D-NATIVE): `ensure()` at startup, so the first
## native consumer finds the payload registered (or refused) instead of
## verifying and loading it mid-game. Prints one `native_runtime stage=startup`
## line. A web build returns code `web` without touching the loader. Later calls
## return `ensure()`'s result without printing again. `prior` is true when an
## earlier caller (an autoload opt-in such as `ELORIA_NATIVE_CROWD=1`) already
## ran `ensure()`; `us` then excludes the verify+load it paid.
static func startup() -> Dictionary:
	if OS.has_feature("web"):
		return {"ok": false, "code": "web", "directory": "", "manifest": {}, "library_path": "",
			"descriptor_path": "", "load_status": -1}
	if not _startup.is_empty():
		return ensure()
	var prior := _ensured
	var began := Time.get_ticks_usec()
	var result := ensure()
	var state := switch_state()
	_startup = {"code": str(result.code), "us": Time.get_ticks_usec() - began, "switch": str(state.mode),
		"source": str(state.source), "prior": prior}
	print("native_runtime stage=startup code=%s switch=%s source=%s us=%d prior=%s" % [_startup.code,
		_startup.switch, _startup.source, _startup.us, "yes" if prior else "no"])
	return result

## The kill switch of this process, resolved once: {mode ("auto" or "off"),
## source, reason, safe_mode, invalid}; see `resolve_switch`.
static func switch_state() -> Dictionary:
	_switch_lock.lock()
	if _switch.is_empty():
		var arguments := OS.get_cmdline_args()
		arguments.append_array(OS.get_cmdline_user_args())
		_switch = resolve_switch(OS.get_environment(SWITCH_ENVIRONMENT), arguments, saved_setting())
	var state := _switch.duplicate(true)
	_switch_lock.unlock()
	return state

## Pure resolver of the kill switch, for fixtures and reporting. `stored` is the
## settings value (`saved_setting()`: null when absent). Returns {mode ("auto" or
## "off"), source ("argument", "environment", "safe_mode", "settings" or
## "default"), reason ("<source>_<mode>"), safe_mode, invalid (the sources whose
## value was not a known spelling; they count as not given)}.
static func resolve_switch(environment_value: String, arguments: PackedStringArray, stored: Variant) -> Dictionary:
	var argument := ""
	var argument_given := false
	var safe_mode := false
	for value: String in arguments:
		if value.begins_with(SWITCH_ARGUMENT):
			argument = value.trim_prefix(SWITCH_ARGUMENT)
			argument_given = true
		elif value == SAFE_MODE_ARGUMENT:
			safe_mode = true
	var invalid: Array[String] = []
	var candidates := [["argument", argument, argument_given],
		["environment", environment_value, not environment_value.strip_edges().is_empty()]]
	if stored != null:
		candidates.append(["settings", stored, true])
	for candidate: Array in candidates:
		if not bool(candidate[2]):
			continue
		if str(candidate[0]) == "settings" and safe_mode:
			break
		var mode := switch_mode(candidate[1])
		if mode.is_empty():
			invalid.append(str(candidate[0]))
			continue
		return _switch_result(mode, str(candidate[0]), safe_mode, invalid)
	if safe_mode:
		return _switch_result("off", "safe_mode", true, invalid)
	return _switch_result("auto", "default", false, invalid)

## "auto", "off", or "" for a value that is neither (a bool counts: false is off).
static func switch_mode(value: Variant) -> String:
	if value is bool:
		return "auto" if value else "off"
	if not value is String and not value is StringName:
		return ""
	var spelling := str(value).strip_edges().to_lower()
	if spelling in OFF_SPELLINGS:
		return "off"
	if spelling in ON_SPELLINGS:
		return "auto"
	return ""

static func _switch_result(mode: String, source: String, safe_mode: bool, invalid: Array[String]) -> Dictionary:
	return {"mode": mode, "source": source, "reason": source + "_" + mode, "safe_mode": safe_mode,
		"invalid": invalid.duplicate()}

## The stored support setting, or null when the file or the key is missing.
static func saved_setting(path := SETTINGS_PATH) -> Variant:
	var config := ConfigFile.new()
	if config.load(path) != OK or not config.has_section_key(SETTINGS_SECTION, SETTINGS_KEY):
		return null
	return config.get_value(SETTINGS_SECTION, SETTINGS_KEY)

## Stores the support setting ("auto" or "off", any spelling) beside the other
## client settings. It takes effect at the next start. An unreadable existing
## file is left alone (its error is returned) rather than rewritten.
static func save_setting(value: Variant, path := SETTINGS_PATH) -> Error:
	var mode := switch_mode(value)
	if mode.is_empty():
		return ERR_INVALID_PARAMETER
	var config := ConfigFile.new()
	if FileAccess.file_exists(path):
		var error := config.load(path)
		if error != OK:
			return error
	config.set_value(SETTINGS_SECTION, SETTINGS_KEY, mode)
	return config.save(path)

## For diagnostics and the startup receipt: `stats()` plus the switch and the
## startup load.
static func snapshot() -> Dictionary:
	var state := switch_state()
	var out := stats()
	out.merge({"switch": state.mode, "switch_source": state.source, "switch_reason": state.reason,
		"safe_mode": state.safe_mode, "switch_invalid": state.invalid, "startup": _startup.duplicate(),
		"registered": ClassDB.class_exists(RUNTIME_CLASS)})
	return out

## Forgets the `ensure()` result, the resolved switch and the startup record
## (tests only; a loaded library stays loaded).
static func reset_for_tests() -> void:
	_ensured = false
	_ensure_result = {}
	_switch_lock.lock()
	_switch = {}
	_switch_lock.unlock()
	_startup = {}
