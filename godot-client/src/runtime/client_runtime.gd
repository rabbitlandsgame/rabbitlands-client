class_name ClientRuntimeController
extends RefCounted
const OptimizationProfile := preload("res://src/runtime/optimization_profile.gd")
const NativeLibrary := preload("res://src/runtime/native_library.gd")
## NativeLibrary result codes -> this controller's reasons (unchanged strings).
const LOADER_REASONS := {"absent": "optional_runtime_absent", "manifest_invalid": "manifest_invalid",
	"api_mismatch": "api_mismatch", "unsupported_platform": "unsupported_platform",
	"incomplete": "optional_runtime_incomplete", "checksum_mismatch": "runtime_checksum_mismatch",
	"late_load_refused": "late_load_refused", "extension_unavailable": "extension_unavailable",
	"switched_off": "native_runtime_switched_off"}
const MOUNTED_PROFILE_IDS := ["moor_pony", "golden_plains_horse", "crystalback_tortoise", "rabbit", "jadefeather_raptor"]
## Human-testing defaults request the optional runtime. Comparison observes
## legacy presentation; Rust mode owns supported mounted work when available.
## One ABI for the manifest (checked by NativeLibrary) and `runtime_info()`.
const ABI := NativeLibrary.ABI
const COMPARE_INTERVAL := 60
const COMPARE_LIMIT := 256
## The native exit watchdog (avatar-worker AW-01; `exit_drain.gd` arms it).
const EXIT_WATCHDOG_CLASS := &"RabbitLandsExitWatchdog"
## `RabbitLandsExitWatchdog.arm()` return codes -> status strings.
const EXIT_WATCHDOG_STATUS := {0: "armed", 1: "invalid_argument", 2: "thread_failed", 3: "pin_failed",
	4: "firing"}
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

func is_rust_mode() -> bool:
	return _mode == "rust" and _native != null

func wants_rust_pose() -> bool:
	return is_rust_mode()

func initialize(directory := "") -> void:
	close()
	_current_ref = weakref(self)
	_requested = OptimizationProfile.selected("client_runtime")
	_mode = "legacy"
	if _requested == "legacy":
		_reason = "legacy_selected"
		return
	if _requested not in ["compare", "rust", "services"]:
		_reason = "unsupported_mode"
		return
	# Every check runs again on each initialize (no NativeLibrary.ensure() cache).
	var loaded := NativeLibrary.load_verified(directory)
	if str(loaded.code) not in ["absent", "manifest_invalid", NativeLibrary.SWITCHED_OFF]:
		_manifest = loaded.manifest
	if not bool(loaded.ok):
		_reason = str(LOADER_REASONS.get(loaded.code, loaded.code))
		return
	var version: Dictionary = Engine.get_version_info()
	_native = ClassDB.instantiate(NativeLibrary.RUNTIME_CLASS) as RefCounted
	var info: Dictionary = _native.call("runtime_info") if _native != null else {}
	if int(info.get("abi", -1)) != ABI or not bool(info.get("ready", false)) \
			or int(info.get("engine_major", -1)) != int(version.major) or int(info.get("engine_minor", -1)) != int(version.minor):
		_native = null
		_reason = "native_api_mismatch"
		return
	if _requested == "rust" and (int(info.get("mounted_pose_api", -1)) != 1 or int(info.get("engine_scalar_bytes", 0)) != 4):
		_native = null
		_reason = "mounted_pilot_unavailable"
		return
	if _epoch > 1 and int(_native.call("reset_epoch", _epoch)) != 0:
		_native = null
		_reason = "epoch_rejected"
		return
	_mode = _requested
	_reason = "native_resource_services_legacy_presentation" if _mode == "services" else ("native_mounted_pilot" if _mode == "rust" else "native_comparison_legacy_presentation")

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
		"optimization_profile": OptimizationProfile.snapshot(),
		"presentation_backend": "mixed" if is_rust_mode() else "legacy", "native_available": _native != null,
		"mounted_pose_enabled": wants_rust_pose(), "mounted_pose_profiles": MOUNTED_PROFILE_IDS.duplicate(),
		"comparisons": _comparisons, "records_checked": _checked, "mismatches": _mismatches,
		"comparison_limit": COMPARE_LIMIT, "records_over_limit": _truncated,
		"native": _native.call("runtime_info") if _native != null else {}}

func close() -> void:
	_native = null
	_mode = "legacy"
	if current() == self:
		_current_ref = null

## ## Exit watchdog (avatar-worker AW-01)
##
## `RabbitLandsExitWatchdog` is a process-wide native timer in the payload: once
## armed, a detached native thread ends the process with the given exit code
## (TerminateProcess / _exit) if it is still alive `timeout_msec` later, after
## appending one line to `log_path` and stderr. These bindings work in every
## optimization profile but never load the library: the watchdog is available
## only when the payload is already registered (`NativeLibrary.startup()` at
## `Main._ready`), so the exit path never verifies or loads a DLL. Without it
## the result's `status` says why and the caller quits as before.

## Arms (or re-arms; the latest call wins) the exit watchdog. Returns {armed,
## status ("armed", "invalid_argument", "thread_failed", "pin_failed",
## "firing", or an unavailable reason), timeout_msec, exit_code, log_path}.
static func arm_exit_watchdog(timeout_msec: int, exit_code: int, log_path := "", reason := "") -> Dictionary:
	var result := {"armed": false, "status": "", "timeout_msec": timeout_msec, "exit_code": exit_code,
		"log_path": log_path}
	var watchdog := _exit_watchdog()
	if watchdog == null:
		result.status = exit_watchdog_unavailable_reason()
		return result
	var status := int(watchdog.call("arm", timeout_msec, exit_code, log_path, reason))
	result.status = str(EXIT_WATCHDOG_STATUS.get(status, "status_%d" % status))
	result.armed = status == 0
	return result

## Cancels a pending watchdog deadline (tests). Returns whether one was pending.
static func disarm_exit_watchdog() -> bool:
	var watchdog := _exit_watchdog()
	return watchdog != null and bool(watchdog.call("disarm"))

## The native watchdog's state plus `available`; {available: false, reason}
## when the class is not registered.
static func exit_watchdog_state() -> Dictionary:
	var watchdog := _exit_watchdog()
	if watchdog == null:
		return {"available": false, "reason": exit_watchdog_unavailable_reason()}
	var out: Dictionary = watchdog.call("state")
	out["available"] = true
	return out

## "" when the watchdog can be armed; otherwise why not: the native runtime is
## switched off (NativeLibrary's kill switch wins even over a registered
## class), it was not loaded (no or a refused payload, or no startup load), or
## the loaded payload predates the watchdog.
static func exit_watchdog_unavailable_reason() -> String:
	if str(NativeLibrary.switch_state().mode) == "off":
		return "native_runtime_switched_off"
	if not ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS):
		return "native_runtime_not_loaded"
	return "" if ClassDB.class_exists(EXIT_WATCHDOG_CLASS) else "watchdog_unavailable"

static func _exit_watchdog() -> RefCounted:
	if not exit_watchdog_unavailable_reason().is_empty():
		return null
	return ClassDB.instantiate(EXIT_WATCHDOG_CLASS) as RefCounted
