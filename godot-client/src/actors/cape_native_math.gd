extends RefCounted
## Optional arithmetic only. This does not select a rider, animation or service
## mode; absent/incompatible payloads retain the complete script implementation.
## The payload is verified and loaded by the shared `NativeLibrary.ensure()`.
const NativeLibrary := preload("res://src/runtime/native_library.gd")
## NativeLibrary refusal codes -> this file's reasons (unchanged strings).
const LOADER_REASONS := {"absent": "payload_absent", "manifest_invalid": "manifest_invalid",
	"api_mismatch": "incompatible_payload", "unsupported_platform": "incompatible_payload",
	"incomplete": "checksum_mismatch", "checksum_mismatch": "checksum_mismatch",
	"switched_off": "native_runtime_switched_off"}
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
	if OS.has_feature("web"):
		# Web extensions must register during engine startup, before game
		# threads exist. A late dlopen can wait on those threads indefinitely.
		_reason = "browser_payload_absent"
		return false
	var refusal := reason_for(NativeLibrary.ensure())
	if not refusal.is_empty():
		_reason = refusal
		return false
	_ready = _classes_ready()
	_reason = "native_arithmetic" if _ready else "arithmetic_api_unavailable"
	return _ready

## This file's reason when `NativeLibrary` refused the payload before loading
## it, or "" when the payload passed and the cape classes decide.
static func reason_for(loaded: Dictionary) -> String:
	return str(LOADER_REASONS.get(str(loaded.get("code", "")), ""))

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
