extends RefCounted
## Optional arithmetic only. This does not select a rider, animation or service
## mode; absent/incompatible payloads retain the complete script implementation.
static var _checked := false
static var _ready := false
static var _reason := "not_checked"

static func ready() -> bool:
	if OS.get_environment("RABBITLANDS_CAPE_MATH").to_lower() in ["gdscript", "legacy", "off"]:
		_reason = "script_selected"
		return false
	if _checked:
		return _ready
	_checked = true
	if _classes_ready():
		_ready = true
		_reason = "registered"
		return true
	var directory := ProjectSettings.globalize_path("res://bin/client_runtime") if OS.has_feature("editor") else \
		OS.get_executable_path().get_base_dir().path_join("bin/client_runtime")
	var path := directory.path_join("runtime-manifest.json")
	if not FileAccess.file_exists(path):
		_reason = "payload_absent"
		return false
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not value is Dictionary:
		_reason = "manifest_invalid"
		return false
	var platform := str({"Windows": "windows", "Linux": "linux", "macOS": "macos"}.get(OS.get_name(), ""))
	var library := str({"windows": "client_runtime.dll", "linux": "client_runtime.so", "macos": "client_runtime.dylib"}.get(platform, ""))
	var version := Engine.get_version_info()
	if library.is_empty() or not OS.has_feature("x86_64") \
			or int(value.get("abi", 0)) != 1 or str(value.get("platform", "")) != platform \
			or str(value.get("architecture", "")) != "x86_64" or str(value.get("library", "")) != library \
			or int(value.get("engine_major", 0)) != int(version.major) \
			or int(value.get("engine_minor", 0)) != int(version.minor):
		_reason = "incompatible_payload"
		return false
	var binary := directory.path_join(library)
	var descriptor := directory.path_join("client_runtime.gdextension")
	if not FileAccess.file_exists(binary) or not FileAccess.file_exists(descriptor) \
			or FileAccess.get_sha256(binary) != str(value.get("library_sha256", "")) \
			or FileAccess.get_sha256(descriptor) != str(value.get("descriptor_sha256", "")):
		_reason = "checksum_mismatch"
		return false
	GDExtensionManager.load_extension(descriptor)
	_ready = _classes_ready()
	_reason = "native_arithmetic" if _ready else "arithmetic_api_unavailable"
	return _ready

static func _classes_ready() -> bool:
	var available := ClassDB.class_exists(&"RabbitLandsCapeBodySurface") \
		and ClassDB.class_exists(&"RabbitLandsCapeProjector") \
		and ClassDB.class_has_method(&"RabbitLandsCapeBodySurface", &"body_plane_at") \
		and ClassDB.class_has_method(&"RabbitLandsCapeProjector", &"project") \
		and ClassDB.class_has_method(&"RabbitLandsCapeProjector", &"runtime_info")
	if not available:
		return false
	var projector := ClassDB.instantiate(&"RabbitLandsCapeProjector") as RefCounted
	return projector != null and int((projector.call("runtime_info") as Dictionary).get("api", 0)) == 2

static func stats() -> Dictionary:
	return {"ready": _ready, "reason": _reason}
