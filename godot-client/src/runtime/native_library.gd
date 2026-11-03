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

const ABI := 1
const MANIFEST_NAME := "runtime-manifest.json"
const DESCRIPTOR_NAME := "client_runtime.gdextension"
const RUNTIME_CLASS := &"RabbitLandsClientRuntime"
const PLATFORMS := {"Windows": "windows", "Linux": "linux", "macOS": "macos"}
const LIBRARIES := {"windows": "client_runtime.dll", "linux": "client_runtime.so", "macos": "client_runtime.dylib"}
## Codes that mean the payload was refused before anything was loaded.
const REFUSED := ["absent", "manifest_invalid", "api_mismatch", "unsupported_platform", "incomplete", "checksum_mismatch"]

static var _ensured := false
static var _ensure_result: Dictionary = {}
static var _verifications := 0
static var _loads := 0

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
## and loads its descriptor. `ok` is true only for code `loaded`.
static func load_verified(directory := "") -> Dictionary:
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

## Forgets the `ensure()` result (tests only; a loaded library stays loaded).
static func reset_for_tests() -> void:
	_ensured = false
	_ensure_result = {}
