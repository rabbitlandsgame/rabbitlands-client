extends RefCounted
## Bounded exit drain and the native exit watchdog for the client's own quit
## paths (avatar-worker AW-01): `Main._close_client` and the
## `--prepare-map-geometry` maintenance quit.
##
## Before `SceneTree.quit()` the close waits, frame by frame, for its
## background work: the actor warm-up, the RL head prewarm parse, the exterior
## preload worker (and the orphaned workers it reaps), the WorldPark preload.
## A worker that may wait for a RenderingServer call only the main thread
## serves is never joined while it runs, and GDScript still running on a worker
## during engine teardown can hang the process (the 4-core proxy stayed alive
## at 0 % CPU for 540 s after its report; AW-00's control quit during an RL
## head parse and hung 5 of 5 times). So:
##
## - `wait_until(tree, stage, idle)` serves frames until `idle` returns true,
##   for at most `STAGE_DEADLINE_MSEC` (8 s). A stage that times out prints one
##   `exit_drain stage=... result=timeout` line and the close goes on.
## - `quit(tree, code, reason)` arms the native exit watchdog and calls
##   `tree.quit(code)`. If the process is still alive `WATCHDOG_TIMEOUT_MSEC`
##   (10 s) later, the watchdog appends one line to
##   `user://logs/exit_watchdog.log` and stderr and ends the process with the
##   same code (TerminateProcess / _exit), so an exit code the caller meant
##   (for example the maintenance quit's 1) survives. The renderer relaunch
##   (`RendererPolicy.restart`, code 75) quits before the startup load and does
##   not come through here.
## - The watchdog is armed only after the drains (the close flushes settings
##   first), only from the game's own quit paths (never the updater or the
##   launcher), and never loads the library: it exists only when the startup
##   load (`NativeLibrary.startup()`) registered `client_runtime`. With no or a
##   refused payload, the runtime switched off (safe mode included) or an older
##   payload, the close quits exactly as before and the receipt says why
##   (`ClientRuntimeController.exit_watchdog_unavailable_reason()`).
## - `--exit-watchdog=off` or `RABBITLANDS_EXIT_WATCHDOG=off` leaves it unarmed
##   (to attach a debugger to a hung exit); a number of milliseconds
##   (`WATCHDOG_MIN_MSEC`..`WATCHDOG_MAX_MSEC`) replaces the 10 s. The argument
##   wins over the environment; an unknown value counts as not given.
##
## No `class_name`: callers preload this file. State is per process (static).

const ClientRuntime := preload("res://src/runtime/client_runtime.gd")
const NativeLibrary := preload("res://src/runtime/native_library.gd")
const STAGE_DEADLINE_MSEC := 8000
const WATCHDOG_TIMEOUT_MSEC := 10000
const WATCHDOG_MIN_MSEC := 100
const WATCHDOG_MAX_MSEC := 600000
const SWITCH_ENVIRONMENT := "RABBITLANDS_EXIT_WATCHDOG"
const SWITCH_ARGUMENT := "--exit-watchdog="
## Relative to the user data directory (Godot's own logs live beside it).
const WATCHDOG_LOG := "logs/exit_watchdog.log"

static var _closing := false
static var _reason := ""
static var _began_msec := 0
static var _stages: Array[Dictionary] = []
static var _repeats := 0
static var _watchdog: Dictionary = {}

## The first line of a close: true for the first request of this process,
## false (and a log line) for a repeat while that close is still draining, so
## a second click on the window's close button does not start a second drain.
static func begin(reason := "close") -> bool:
	if _closing:
		_repeats += 1
		print("exit_drain repeat=%s ignored while %s drains (%d ms)" % [reason, _reason,
			Time.get_ticks_msec() - _began_msec])
		return false
	_closing = true
	_reason = reason
	_began_msec = Time.get_ticks_msec()
	_stages.clear()
	return true

## Whether a close has begun in this process.
static func closing() -> bool:
	return _closing

## Serves frames until `idle.call()` returns true or `deadline_msec` has
## passed; returns whether it became idle. `idle` is checked before the first
## frame, so an idle stage costs no frame. A callable whose object is gone
## counts as idle (nothing is left to wait for). Every stage is recorded for
## the receipt; a timeout also prints a line at once.
static func wait_until(tree: SceneTree, stage: String, idle: Callable, deadline_msec := STAGE_DEADLINE_MSEC) -> bool:
	var began := Time.get_ticks_msec()
	var frames := 0
	var done := _idle(idle)
	while not done and Time.get_ticks_msec() - began < deadline_msec:
		await tree.process_frame
		frames += 1
		done = _idle(idle)
	var record := {"stage": stage, "idle": done, "ms": Time.get_ticks_msec() - began, "frames": frames}
	_stages.append(record)
	if not done:
		print("exit_drain stage=%s result=timeout ms=%d frames=%d deadline_ms=%d" % [stage, record.ms, frames,
			deadline_msec])
	return done

## Arms the exit watchdog, prints the receipt line and quits with `code`.
## Returns the watchdog result (see `arm_watchdog`). The drain is closed by
## then: a later `begin()` is still refused.
static func quit(tree: SceneTree, code := 0, reason := "") -> Dictionary:
	if reason.is_empty():
		reason = _reason if not _reason.is_empty() else "quit"
	if not _closing:
		_closing = true
		_reason = reason
		_began_msec = Time.get_ticks_msec()
	_watchdog = arm_watchdog(code, reason)
	print("exit_drain result=%s reason=%s code=%d ms=%d stages=%s watchdog=%s timeout_ms=%d" % [
		"clean" if timed_out().is_empty() else "timeout", reason, code, Time.get_ticks_msec() - _began_msec,
		_stage_summary(), str(_watchdog.status), int(_watchdog.timeout_msec)])
	tree.quit(code)
	return _watchdog

## Arms the native watchdog for this process's setting (or `timeout_msec`
## when given) with `code`. Returns ClientRuntimeController.arm_exit_watchdog's
## result, or {armed: false, status: "switched_off_by_setting"} when the
## watchdog switch is off.
static func arm_watchdog(code := 0, reason := "quit", timeout_msec := -1) -> Dictionary:
	var setting := watchdog_setting()
	var timeout := timeout_msec if timeout_msec > 0 else int(setting.timeout_msec)
	if str(setting.mode) == "off" and timeout_msec <= 0:
		return {"armed": false, "status": "switched_off_by_setting", "timeout_msec": 0, "exit_code": code,
			"log_path": "", "source": str(setting.source)}
	var log_path := watchdog_log_path()
	if ClientRuntime.exit_watchdog_unavailable_reason().is_empty() and not DirAccess.dir_exists_absolute(log_path.get_base_dir()):
		# Godot creates logs/ only for its own file log (not with --log-file).
		DirAccess.make_dir_recursive_absolute(log_path.get_base_dir())
	var result := ClientRuntime.arm_exit_watchdog(timeout, code, log_path, reason)
	result["source"] = str(setting.source)
	return result

## Absolute path of the watchdog's log (one line per firing, appended).
static func watchdog_log_path() -> String:
	return OS.get_user_data_dir().path_join(WATCHDOG_LOG)

## This process's watchdog switch: {mode ("auto" or "off"), timeout_msec,
## source ("argument", "environment" or "default"), invalid}.
static func watchdog_setting() -> Dictionary:
	var arguments := OS.get_cmdline_args()
	arguments.append_array(OS.get_cmdline_user_args())
	return resolve_watchdog(OS.get_environment(SWITCH_ENVIRONMENT), arguments)

## Pure resolver of the watchdog switch (see `watchdog_setting`). A value is an
## off spelling (NativeLibrary.OFF_SPELLINGS), an on spelling (the default
## timeout) or whole milliseconds within the limits; anything else is listed
## in `invalid` and counts as not given.
static func resolve_watchdog(environment_value: String, arguments: PackedStringArray) -> Dictionary:
	var argument := ""
	var argument_given := false
	for value: String in arguments:
		if value.begins_with(SWITCH_ARGUMENT):
			argument = value.trim_prefix(SWITCH_ARGUMENT)
			argument_given = true
	var invalid: Array[String] = []
	for candidate: Array in [["argument", argument, argument_given],
			["environment", environment_value, not environment_value.strip_edges().is_empty()]]:
		if not bool(candidate[2]):
			continue
		var parsed := _watchdog_value(str(candidate[1]))
		if parsed.is_empty():
			invalid.append(str(candidate[0]))
			continue
		parsed["source"] = str(candidate[0])
		parsed["invalid"] = invalid.duplicate()
		return parsed
	return {"mode": "auto", "timeout_msec": WATCHDOG_TIMEOUT_MSEC, "source": "default", "invalid": invalid}

## The stages that did not become idle in time, in order.
static func timed_out() -> Array[String]:
	var out: Array[String] = []
	for record: Dictionary in _stages:
		if not bool(record.idle):
			out.append(str(record.stage))
	return out

## For diagnostics and tests.
static func snapshot() -> Dictionary:
	return {"closing": _closing, "reason": _reason, "elapsed_ms": Time.get_ticks_msec() - _began_msec if _closing else 0,
		"stages": _stages.duplicate(true), "timed_out": timed_out(), "repeats": _repeats,
		"watchdog": _watchdog.duplicate(true), "setting": watchdog_setting()}

## Forgets the close (tests only; an armed native watchdog stays armed).
static func reset_for_tests() -> void:
	_closing = false
	_reason = ""
	_began_msec = 0
	_stages.clear()
	_repeats = 0
	_watchdog = {}

static func _idle(idle: Callable) -> bool:
	return not idle.is_valid() or bool(idle.call())

static func _watchdog_value(value: String) -> Dictionary:
	var spelling := value.strip_edges().to_lower()
	if spelling in NativeLibrary.OFF_SPELLINGS:
		return {"mode": "off", "timeout_msec": 0}
	if spelling in NativeLibrary.ON_SPELLINGS:
		return {"mode": "auto", "timeout_msec": WATCHDOG_TIMEOUT_MSEC}
	if spelling.is_valid_int():
		var milliseconds := spelling.to_int()
		if milliseconds >= WATCHDOG_MIN_MSEC and milliseconds <= WATCHDOG_MAX_MSEC:
			return {"mode": "auto", "timeout_msec": milliseconds}
	return {}

static func _stage_summary() -> String:
	var parts: PackedStringArray = []
	for record: Dictionary in _stages:
		parts.append("%s:%d%s" % [record.stage, int(record.ms), "" if bool(record.idle) else "!"])
	return ",".join(parts) if not parts.is_empty() else "-"
