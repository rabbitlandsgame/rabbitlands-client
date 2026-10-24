class_name ClientRuntimeController
extends RefCounted
## Optional compute service. Phase 4 observes the legacy gate; it never applies
## its output to presentation. Missing/invalid optional files stay on legacy.
const ABI := 1
const COMPARE_INTERVAL := 60
const COMPARE_LIMIT := 256
static var _current_ref: WeakRef
var _native: RefCounted
var _requested := "legacy"
var _mode := "legacy"
var _reason := "not_initialized"
var _epoch := 1
var _next_generation := 1
var _frames := 0
var _comparisons := 0
var _checked := 0
var _mismatches := 0
var _truncated := 0
var _manifest: Dictionary = {}

static func current() -> ClientRuntimeController:
	return _current_ref.get_ref() as ClientRuntimeController if _current_ref != null else null

func native_runtime() -> RefCounted:
	return _native

func current_epoch() -> int:
	return _epoch

func allocate_instance_generation() -> int:
	var generation := _next_generation
	_next_generation += 1
	return generation

func is_compare_mode() -> bool:
	return _mode == "compare"

func wants_rust_pose() -> bool:
	return false # Added only when the complete mounted slice is qualified.

func initialize(directory := "") -> void:
	close()
	_current_ref = weakref(self)
	_requested = OS.get_environment("RABBITLANDS_CLIENT_RUNTIME").strip_edges().to_lower()
	if _requested.is_empty():
		_requested = "legacy"
	_mode = "legacy"
	if _requested == "legacy":
		_reason = "legacy_selected"
		return
	if _requested != "compare":
		_reason = "unsupported_mode"
		return
	if directory.is_empty():
		directory = (ProjectSettings.globalize_path("res://bin/client_runtime") if OS.has_feature("editor")
			else OS.get_executable_path().get_base_dir().path_join("bin/client_runtime"))
	var manifest_path := directory.path_join("runtime-manifest.json")
	if not FileAccess.file_exists(manifest_path):
		_reason = "optional_runtime_absent"
		return
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(manifest_path)) != OK or not parser.data is Dictionary:
		_reason = "manifest_invalid"
		return
	_manifest = parser.data
	var version: Dictionary = Engine.get_version_info()
	if int(_manifest.get("abi", -1)) != ABI or int(_manifest.get("engine_major", -1)) != int(version.major) \
			or int(_manifest.get("engine_minor", -1)) != int(version.minor):
		_reason = "api_mismatch"
		return
	var platform := {"Windows": "windows", "Linux": "linux", "macOS": "macos"}.get(OS.get_name(), "unsupported") as String
	var library: String = str(_manifest.get("library", ""))
	var expected_library: String = {"windows": "client_runtime.dll", "linux": "client_runtime.so", "macos": "client_runtime.dylib"}.get(platform, "")
	if str(_manifest.get("platform", "")) != platform or not OS.has_feature(str(_manifest.get("architecture", ""))) \
			or library.is_empty() or library != expected_library:
		_reason = "unsupported_platform"
		return
	var library_path := directory.path_join(library)
	var descriptor := directory.path_join("client_runtime.gdextension")
	if not FileAccess.file_exists(library_path) or not FileAccess.file_exists(descriptor):
		_reason = "optional_runtime_incomplete"
		return
	if FileAccess.get_sha256(library_path) != str(_manifest.get("library_sha256", "")) \
			or FileAccess.get_sha256(descriptor) != str(_manifest.get("descriptor_sha256", "")):
		_reason = "runtime_checksum_mismatch"
		return
	if not ClassDB.class_exists("RabbitLandsClientRuntime"):
		GDExtensionManager.load_extension(descriptor)
	if not ClassDB.class_exists("RabbitLandsClientRuntime"):
		_reason = "extension_unavailable"
		return
	_native = ClassDB.instantiate("RabbitLandsClientRuntime") as RefCounted
	var info: Dictionary = _native.call("runtime_info") if _native != null else {}
	if int(info.get("abi", -1)) != ABI or not bool(info.get("ready", false)) \
			or int(info.get("engine_major", -1)) != int(version.major) or int(info.get("engine_minor", -1)) != int(version.minor):
		_native = null
		_reason = "native_api_mismatch"
		return
	if _epoch > 1 and int(_native.call("reset_epoch", _epoch)) != 0:
		_native = null
		_reason = "epoch_rejected"
		return
	_mode = "compare"
	_reason = "native_comparison_legacy_presentation"

func reset_session() -> void:
	_epoch += 1
	if _native != null and int(_native.call("reset_epoch", _epoch)) != 0:
		_mode = "legacy"
		_reason = "epoch_rejected"
		_native = null

func observe_gate(gate: AnimationGate) -> void:
	if _native == null or _mode != "compare":
		return
	_frames += 1
	if _frames % COMPARE_INTERVAL != 0:
		return
	var records := PackedInt64Array()
	var expected := PackedInt64Array()
	for group: Dictionary in gate._groups:
		for player: Variant in group.members:
			if not is_instance_valid(player):
				continue
			if expected.size() >= COMPARE_LIMIT:
				_truncated += 1
				continue
			records.append_array(PackedInt64Array([player.get_instance_id(), _epoch, 0, int(group.tier), int(group.phase)]))
			expected.append(1 if (gate._tick + int(group.phase)) % int(group.stride) == 0 else 0)
	var response: Variant = _native.call("plan_batch", records, _epoch, gate._tick)
	var status: Variant = _native.call("get_last_status")
	var output := PackedInt64Array()
	if response is PackedInt64Array:
		output = response
	var valid: bool = response is PackedInt64Array and status is int and status == 0 and output.size() == expected.size() * 4
	if valid:
		for index: int in expected.size():
			if output[index * 4] != records[index * 5] or output[index * 4 + 1] != records[index * 5 + 1] \
					or output[index * 4 + 2] != _epoch or output[index * 4 + 3] != expected[index]:
				valid = false
				break
	_comparisons += 1
	_checked += expected.size()
	if not valid:
		_mismatches += 1
		_mode = "legacy"
		_reason = "comparison_mismatch"
		_native = null

func snapshot() -> Dictionary:
	return {"requested": _requested, "mode": _mode, "reason": _reason, "epoch": _epoch,
		"presentation_backend": "legacy", "native_available": _native != null,
		"comparisons": _comparisons, "records_checked": _checked, "mismatches": _mismatches,
		"comparison_limit": COMPARE_LIMIT, "records_over_limit": _truncated,
		"native": _native.call("runtime_info") if _native != null else {}}

func close() -> void:
	_native = null
	_mode = "legacy"
	if current() == self:
		_current_ref = null
