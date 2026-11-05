extends RefCounted
## Which renderer "Automatic" starts on this computer (wave 2, MOB-C3 game side).
##
## On an integrated GPU the Mobile renderer drew the iGPU proxy's world in about
## 0.75-0.80x Forward+'s GPU time (gate G1, 2026-11-03), but it is not
## qualified yet: its peak working set measured up to +6-7 % and it draws black
## roof seams. The
## owner's decision (2026-11-04) is to build the policy and keep the default
## OFF until a re-qualification passes, so INTEGRATED_RENDERER is "" and an
## ordinary launch behaves exactly as before. The policy can be switched on for
## a test without a code change through INTEGRATED_VARIABLE.
##
## Only the game process knows the RenderingDevice adapter that will render (an
## Optimus laptop's updater can sit on the other GPU), so the game decides. A
## first run starts on the project default (Forward+), HardwareTier classifies
## the adapter and seeds the tier, and `reconcile` then records a
## recommendation beside it in [graphics] of the settings file:
##
##   auto_renderer          what Automatic starts here; "" or absent = Forward+
##   auto_renderer_basis    why ("integrated_gpu")
##   auto_renderer_adapter  the adapter it was recorded on
##   auto_renderer_state    trial | ok | failed_fallback | failed_start |
##                          withdrawn
##   auto_renderer_attempts trial starts that have not reached "ok"
##
## These keys are a record, never the player's choice: an explicit `renderer`
## always wins, and a profile whose renderer is not Automatic is never touched.
## Automatic starts the recommendation while its state is trial or ok and fewer
## than MAX_TRIAL_ATTEMPTS trial starts have failed to reach ok (`resolve`).
## The updater applies the same rule before it starts the game
## (LaunchOptions.effective_renderer, the updater half of this work); the game
## applies it only while the policy is on, and on the first ordinary launch
## with the policy off it withdraws an active recommendation (state
## "withdrawn", auto_renderer ""), so turning INTEGRATED_RENDERER off is a real
## kill switch from the next launch.
##
## Trial: a process that runs the recommendation for CONFIRM_SECONDS marks it
## ok (`confirm`). A process that asked for it but runs OpenGL (the engine's
## fallback) marks it failed_fallback; a parent that finds MAX_TRIAL_ATTEMPTS
## restarts without ok marks it failed_start (the updater also writes
## failed_start when a trial start exits early with an error). Both failures
## leave Automatic on Forward+ for good on this profile.
##
## Restart (`restart`): when the updater announced the relaunch handshake in
## LAUNCHER_FEATURES_ENV, the game exits with RELAUNCH_EXIT_CODE and the
## updater starts it again with the new arguments, keeping its installation
## lock; otherwise the game restarts itself (OS.set_restart_on_exit), as an
## explicit renderer change always did. `restarting` is set first: Main must
## skip its setup in the process that is about to quit, or that process never
## exits (see `restart`).
##
## A launch that pins graphics or measures (HardwareTier.blocker: environment
## overrides, a `--script` main loop, the benchmarks, headless, the browser)
## writes nothing here and ignores the recommendation; the compatibility and
## safe-mode launchers always keep OpenGL. Godot consumes `--rendering-method`
## and `--rendering-driver` before OS.get_cmdline_args(), so the game cannot
## see an explicit engine flag; it sees only the launchers' user arguments.
##
## No class_name: the diagnostics autoload preloads this before the global
## class cache is current.

const HardwareTier := preload("res://src/runtime/hardware_tier.gd")
const LaunchOptions := preload("res://src/updates/launch_options.gd")
const RendererFamily := preload("res://src/runtime/renderer_family.gd")

## The renderer Automatic records for an integrated GPU on a first run, and the
## kill switch: "" leaves Automatic on the project default (Forward+). Owner
## 2026-11-04: stays "" until the Mobile re-qualification (gate G4, MOB-C6)
## passes; then "mobile".
const INTEGRATED_RENDERER := ""
## Overrides INTEGRATED_RENDERER for a launch (and the restart it makes): one of
## INTEGRATED_CHOICES turns the policy on with it, an OFF spelling turns it
## off; anything else is ignored and reported. For testers and the
## re-qualification only. It is deliberately not one of HardwareTier's
## OVERRIDE_VARIABLES: its purpose is to exercise a real first run.
const INTEGRATED_VARIABLE := "RABBITLANDS_INTEGRATED_RENDERER"
const INTEGRATED_CHOICES: Array[String] = ["mobile"]
const OFF_SPELLINGS: Array[String] = ["off", "0", "false", "no", "none"]
## Platforms whose iGPUs get the recommendation (Linux and macOS are open
## owner questions; Linux's Performance preset already picks OpenGL).
const PLATFORMS: Array[String] = ["Windows"]
## Whether a profile from before this existed (Automatic, never recorded) also
## gets a recommendation. Off: only fresh profiles (open owner question; the
## reviewers' default).
const MIGRATE_EXISTING := false

const SECTION := HardwareTier.SECTION
const SETTINGS_PATH := HardwareTier.SETTINGS_PATH
const KEY_RENDERER := "auto_renderer"
const KEY_BASIS := "auto_renderer_basis"
const KEY_ADAPTER := "auto_renderer_adapter"
const KEY_STATE := "auto_renderer_state"
const KEY_ATTEMPTS := "auto_renderer_attempts"
const STATE_TRIAL := "trial"
const STATE_OK := "ok"
const STATE_FAILED_FALLBACK := "failed_fallback"
const STATE_FAILED_START := "failed_start"
const STATE_WITHDRAWN := "withdrawn"
## The states in which Automatic starts the recommendation.
const ACTIVE_STATES: Array[String] = [STATE_TRIAL, STATE_OK]
## Trial starts without reaching ok after which Automatic gives up.
const MAX_TRIAL_ATTEMPTS := 2
## How long a process must run the recommendation before it counts as ok.
const CONFIRM_SECONDS := 30.0

## The relaunch handshake with the updater: the updater lists RELAUNCH_FEATURE
## in LAUNCHER_FEATURES_ENV (comma-separated) when it relaunches a game that
## exits with RELAUNCH_EXIT_CODE. Same values as LaunchOptions' constants of
## the same names (checked by tests/test_renderer_policy.gd).
const RELAUNCH_EXIT_CODE := 75
const LAUNCHER_FEATURES_ENV := "RABBITLANDS_LAUNCHER_FEATURES"
const RELAUNCH_FEATURE := "renderer-relaunch"
## User arguments with which the launchers force OpenGL
## (LaunchOptions.game_arguments): such a launch is never restarted.
const COMPATIBILITY_ARGUMENTS: Array[String] = ["--client-compatibility", "--client-safe-mode"]

## Set by `begin_restart`: this process is about to quit into another renderer.
static var restarting := false
## This process's startup `reconcile` result, kept by ClientDiagnostics so the
## settings window can name what Automatic starts and what this launch asked
## for without parsing the settings file again (an established profile's file
## takes 14-20 ms). {} until then; a test may set its own.
static var launch := {}

## The policy in force: {"renderer": INTEGRATED_RENDERER or the variable's
## choice ("" = off), "source": "default"|"environment", "rejected": a value of
## the variable that was ignored, or ""}.
static func policy(environment_value := OS.get_environment(INTEGRATED_VARIABLE)) -> Dictionary:
	var text := environment_value.strip_edges().to_lower()
	if text in INTEGRATED_CHOICES:
		return {"renderer": text, "source": "environment", "rejected": ""}
	if text in OFF_SPELLINGS:
		return {"renderer": "", "source": "environment", "rejected": ""}
	return {"renderer": INTEGRATED_RENDERER, "source": "default", "rejected": text}

## The renderers the launch code can start by name: the ones LaunchOptions
## knows and has engine arguments for (Mobile once the updater half is in).
static func supported_renderers() -> Array[String]:
	var result: Array[String] = []
	for renderer: String in LaunchOptions.RENDERERS:
		if renderer != "auto" and LaunchOptions.renderer_name(renderer) == renderer \
				and not LaunchOptions.renderer_arguments(renderer).is_empty():
			result.append(renderer)
	return result

## The renderer to recommend on a first run, or "": `integrated_renderer` for an
## integrated GPU (`classified`: HardwareTier.classify) on one of PLATFORMS,
## while the process runs a RenderingDevice method, which proves RD works here.
## A process that already fell back to OpenGL gets nothing.
static func recommend(classified: Dictionary, current_method: String, platform: String,
		integrated_renderer := INTEGRATED_RENDERER) -> String:
	if integrated_renderer.is_empty() or not platform in PLATFORMS:
		return ""
	if not current_method in RendererFamily.RD_METHODS:
		return ""
	return integrated_renderer if str(classified.get("adapter_class", "")) == "integrated" else ""

## The [graphics] values this policy reads, from a parsed settings file.
static func read_values(config: ConfigFile) -> Dictionary:
	var attempts: Variant = config.get_value(SECTION, KEY_ATTEMPTS, 0)
	var values := {
		"renderer": _text(config.get_value(SECTION, "renderer", "auto"), "auto"),
		"auto_renderer": _text(config.get_value(SECTION, KEY_RENDERER, ""), ""),
		"auto_renderer_basis": _text(config.get_value(SECTION, KEY_BASIS, ""), ""),
		"auto_renderer_adapter": _text(config.get_value(SECTION, KEY_ADAPTER, ""), ""),
		"auto_renderer_state": _text(config.get_value(SECTION, KEY_STATE, ""), ""),
		"auto_renderer_attempts": int(attempts) if attempts is int or attempts is float else 0,
		"recorded": config.has_section_key(SECTION, KEY_STATE),
	}
	return values

static func _text(value: Variant, fallback: String) -> String:
	return value if value is String else fallback

## The renderer `values` (read_values) start: the player's explicit choice when
## the launch code can start it, else the recorded recommendation while the
## policy is on (`policy_renderer` not "") and the recommendation is active,
## else "auto" (the project default, Forward+).
static func resolve(values: Dictionary, policy_renderer: String,
		supported: Array[String] = supported_renderers()) -> String:
	if not automatic(values, supported):
		return str(values.renderer)
	if policy_renderer.is_empty() or not recommendation_active(values, supported):
		return "auto"
	return str(values.get("auto_renderer", ""))

## Whether the player's choice in `values` is Automatic: "auto", or a value
## the launch code cannot start (read as Automatic, as LaunchOptions does).
static func automatic(values: Dictionary, supported: Array[String] = supported_renderers()) -> bool:
	var renderer := str(values.get("renderer", "auto"))
	return renderer == "auto" or not renderer in supported

## Whether `values` hold a recommendation Automatic may start: one the launch
## code can start, in an ACTIVE_STATES state, with fewer than
## MAX_TRIAL_ATTEMPTS attempts. The updater's rule, without the policy.
static func recommendation_active(values: Dictionary,
		supported: Array[String] = supported_renderers()) -> bool:
	var recommended := str(values.get("auto_renderer", ""))
	return recommended in supported and str(values.get("auto_renderer_state", "")) in ACTIVE_STATES \
		and int(values.get("auto_renderer_attempts", 0)) < MAX_TRIAL_ATTEMPTS

## What the settings file at `path` starts under the policy in force: the
## explicit choice, the active recommendation for Automatic, or "auto".
static func effective_renderer(path := SETTINGS_PATH) -> String:
	var config := ConfigFile.new()
	config.load(path)
	return resolve(read_values(config), str(policy().renderer))

## The renderer the project starts when no renderer is named: the project
## setting (Forward+), and OpenGL Compatibility in the browser.
static func default_renderer() -> String:
	if OS.has_feature("web"):
		return RendererFamily.COMPATIBILITY
	return str(ProjectSettings.get_setting("rendering/renderer/rendering_method",
		RendererFamily.FORWARD_PLUS))

## The renderer Automatic starts on this computer, by name, for the settings
## window's "Automatic (…)" item: the recorded recommendation in `values`
## (read_values) while the policy is on and the recommendation is active
## (`resolve`), else `default_renderer`. The player's own choice in `values`
## does not matter here.
static func automatic_renderer(values: Dictionary, policy_renderer := str(policy().renderer),
		supported: Array[String] = supported_renderers()) -> String:
	var as_automatic := values.duplicate()
	as_automatic["renderer"] = "auto"
	var resolved := resolve(as_automatic, policy_renderer, supported)
	return default_renderer() if resolved == "auto" else resolved

## The [graphics] values (read_values) this launch started with: `launch`'s,
## or, before ClientDiagnostics kept them, the settings file at `path`'s.
static func launch_values(path := SETTINGS_PATH) -> Dictionary:
	if launch.get("values") is Dictionary:
		return launch.values
	var config := ConfigFile.new()
	config.load(path)
	return read_values(config)

## Whether `user_args` come from a compatibility or safe-mode launcher.
static func compatibility_launch(user_args: PackedStringArray) -> bool:
	for argument: String in COMPATIBILITY_ARGUMENTS:
		if argument in user_args:
			return true
	return false

## The renderer a launch with `user_args` asks for when settings resolve to
## `effective`: OpenGL for the compatibility launchers, the project's method
## for "auto", else `effective`.
static func requested_renderer(effective: String, user_args: PackedStringArray) -> String:
	if compatibility_launch(user_args):
		return RendererFamily.COMPATIBILITY
	if effective == "auto":
		return default_renderer()
	return effective

## This process's state, for `reconcile`: the method in use, the platform, the
## launch (HardwareTier.launch_context), the policy and what launch code can
## start. A test passes its own values for any of these.
static func live_context(overrides := {}) -> Dictionary:
	var context := {"method": RendererFamily.method(), "platform": OS.get_name(),
		"launch": HardwareTier.launch_context(), "policy": policy(),
		"supported": supported_renderers(), "migrate_existing": MIGRATE_EXISTING}
	context.merge(overrides, true)
	return context

## Records a first run's recommendation and the trial's outcome in the settings
## file at `path` (see the header), and says what this launch should run.
## `tier_result` is HardwareTier.seed_first_run()'s (classify + applied +
## reason), taken just before. Writes only on an ordinary launch (blocker ""),
## never to a file that exists but cannot be read, and only the five keys
## above. Returns:
##   effective     the renderer the settings resolve to ("auto" or a name);
##                 a blocked launch reads only the explicit choice
##   requested     what the settings ask the engine for after this call
##                 (requested_renderer of `effective`): after a failed_fallback
##                 that is what Automatic starts next, not what this launch
##                 asked for
##   asked         what this launch asked the engine for, as far as the game
##                 can tell (it cannot see engine flags): the recommendation
##                 when this call found it running or failed it, else the
##                 settings before this call (requested_renderer)
##   fallback      true when `requested` is a RenderingDevice method and the
##                 process runs OpenGL
##   action        none | recorded | failed_fallback | failed_start |
##                 withdrawn, what was written
##   reason        why nothing (else) was done, "" when an action was taken
##   confirm_after seconds after which `confirm` may mark the trial ok, 0 for
##                 none
##   values        the policy's [graphics] values after this call
##   policy        {"renderer", "source", "rejected"} (see `policy`)
static func reconcile(tier_result: Dictionary, path := SETTINGS_PATH, context := {}) -> Dictionary:
	var live := live_context(context)
	var supported: Array[String] = []
	supported.assign(live.supported)
	var method := str(live.method)
	var launch_info: Dictionary = live.launch
	var user_args := PackedStringArray(launch_info.get("user_args", PackedStringArray()))
	var policy_info: Dictionary = live.policy
	var policy_renderer := str(policy_info.renderer)
	var config := ConfigFile.new()
	var exists := FileAccess.file_exists(path)
	var readable := not exists or config.load(path) == OK
	var values := read_values(config)
	var result := {"action": "none", "reason": "", "confirm_after": 0.0, "policy": policy_info}
	var blocked := HardwareTier.blocker(launch_info)
	var recommended := str(values.auto_renderer)
	var state := str(values.auto_renderer_state)
	# Before any write: what these settings asked this launch for.
	var asked := requested_renderer(resolve(values, policy_renderer if blocked.is_empty() else "", supported),
		user_args)
	var write := {}
	if not blocked.is_empty():
		result.reason = blocked
	elif not readable:
		result.reason = "settings_unreadable"
	elif not automatic(values, supported):
		result.reason = "explicit_renderer"
	elif policy_renderer.is_empty():
		if not recommended.is_empty() and state in ACTIVE_STATES:
			write = {KEY_RENDERER: "", KEY_STATE: STATE_WITHDRAWN}
			result.action = "withdrawn"
		else:
			result.reason = "policy_off"
	elif not bool(values.recorded):
		var fresh := bool(tier_result.get("applied", false))
		var migrating := bool(live.migrate_existing) and str(tier_result.get("reason", "")) == "saved_settings"
		var candidate := recommend(tier_result, method, str(live.platform), policy_renderer)
		if not fresh and not migrating:
			result.reason = "not_first_run"
		elif candidate.is_empty():
			result.reason = _no_recommendation_reason(tier_result, method, str(live.platform))
		elif not candidate in supported:
			result.reason = "launch_unsupported"
		else:
			write = {KEY_RENDERER: candidate,
				KEY_BASIS: str(tier_result.get("adapter_class", "")) + "_gpu",
				KEY_ADAPTER: str(tier_result.get("adapter", "")),
				KEY_STATE: STATE_TRIAL, KEY_ATTEMPTS: 0}
			result.action = "recorded"
	elif not state in ACTIVE_STATES or not recommended in supported:
		result.reason = "inactive"
	elif method == recommended:
		result.reason = "running"
		asked = recommended
	elif method == RendererFamily.COMPATIBILITY and not compatibility_launch(user_args):
		# Asked for a RenderingDevice method; the engine fell back to OpenGL.
		write = {KEY_STATE: STATE_FAILED_FALLBACK}
		result.action = "failed_fallback"
		asked = recommended
	elif LaunchOptions.RENDERER_RESTART in user_args and method != RendererFamily.COMPATIBILITY:
		# This is the restart into the recommendation, and it did not get it.
		write = {KEY_STATE: STATE_FAILED_FALLBACK}
		result.action = "failed_fallback"
		asked = recommended
	elif state == STATE_TRIAL and int(values.auto_renderer_attempts) >= MAX_TRIAL_ATTEMPTS:
		write = {KEY_STATE: STATE_FAILED_START}
		result.action = "failed_start"
	if not write.is_empty():
		for key: String in write:
			config.set_value(SECTION, key, write[key])
		var error := config.save(path)
		if error != OK:
			result.action = "none"
			result.reason = "save_failed: " + error_string(error)
		else:
			values = read_values(config)
	# A process running an active trial confirms it once it has lasted.
	if blocked.is_empty() and readable and not policy_renderer.is_empty() \
			and automatic(values, supported) and str(values.auto_renderer_state) == STATE_TRIAL \
			and str(values.auto_renderer) == method and method in supported:
		result.confirm_after = CONFIRM_SECONDS
	result["values"] = values
	var effective := resolve(values, policy_renderer if blocked.is_empty() else "", supported)
	result["effective"] = effective
	var requested := requested_renderer(effective, user_args)
	result["requested"] = requested
	result["asked"] = asked
	result["fallback"] = requested in RendererFamily.RD_METHODS and method == RendererFamily.COMPATIBILITY
	return result

static func _no_recommendation_reason(classified: Dictionary, method: String, platform: String) -> String:
	if not platform in PLATFORMS:
		return "platform"
	if not method in RendererFamily.RD_METHODS:
		return "not_rendering_device"
	return "adapter_" + str(classified.get("adapter_class", "unknown"))

## Marks the trial ok when this process still runs the recommendation it is
## trialling (call CONFIRM_SECONDS after start, when `reconcile` said so), and
## clears the attempts. Returns {"action": "confirmed"|"none", "reason"}.
static func confirm(path := SETTINGS_PATH, method := RendererFamily.method()) -> Dictionary:
	var config := ConfigFile.new()
	if FileAccess.file_exists(path) and config.load(path) != OK:
		return {"action": "none", "reason": "settings_unreadable"}
	var values := read_values(config)
	if not automatic(values) or str(values.auto_renderer_state) != STATE_TRIAL \
			or str(values.auto_renderer) != method:
		return {"action": "none", "reason": "not_trialling"}
	config.set_value(SECTION, KEY_STATE, STATE_OK)
	config.set_value(SECTION, KEY_ATTEMPTS, 0)
	var error := config.save(path)
	if error != OK:
		return {"action": "none", "reason": "save_failed: " + error_string(error)}
	return {"action": "confirmed", "reason": "", "auto_renderer": method}

## LaunchOptions.needs_renderer_restart, and never for the compatibility and
## safe-mode launchers: they force OpenGL with engine flags the game cannot see.
static func needs_restart(renderer: String, current: String, engine_args: PackedStringArray,
		user_args: PackedStringArray, headless: bool) -> bool:
	if compatibility_launch(user_args):
		return false
	return LaunchOptions.needs_renderer_restart(renderer, current, engine_args, user_args, headless)

## Whether the updater that started this process relaunches on
## RELAUNCH_EXIT_CODE (`features`: LAUNCHER_FEATURES_ENV's value).
static func launcher_relaunches(features := OS.get_environment(LAUNCHER_FEATURES_ENV)) -> bool:
	for feature: String in features.split(",", false):
		if feature.strip_edges() == RELAUNCH_FEATURE:
			return true
	return false

## How a restart into `renderer` happens: {"mode": "relaunch", "exit_code"}
## (the updater starts the game again with the settings' arguments) or
## {"mode": "restart_on_exit", "exit_code": 0, "arguments"} (this process
## restarts itself with LaunchOptions.restart_arguments).
static func restart_plan(renderer: String, features: String, engine_args: PackedStringArray,
		user_args: PackedStringArray) -> Dictionary:
	if launcher_relaunches(features):
		return {"mode": "relaunch", "exit_code": RELAUNCH_EXIT_CODE, "renderer": renderer}
	return {"mode": "restart_on_exit", "exit_code": 0, "renderer": renderer,
		"arguments": LaunchOptions.restart_arguments(renderer, engine_args, user_args)}

## Counts a trial start when `renderer` is the recommendation Automatic is
## trialling (so a renderer that crashes at start is given up after
## MAX_TRIAL_ATTEMPTS), sets `restarting` and returns `restart_plan`'s plan for
## this process. Does not quit: `restart` does.
static func begin_restart(renderer: String, path := SETTINGS_PATH,
		features := OS.get_environment(LAUNCHER_FEATURES_ENV),
		engine_args := OS.get_cmdline_args(), user_args := OS.get_cmdline_user_args()) -> Dictionary:
	var plan := restart_plan(renderer, features, engine_args, user_args)
	plan["counted"] = false
	var config := ConfigFile.new()
	if not FileAccess.file_exists(path) or config.load(path) == OK:
		var values := read_values(config)
		if automatic(values) and str(values.auto_renderer) == renderer \
				and str(values.auto_renderer_state) == STATE_TRIAL:
			config.set_value(SECTION, KEY_ATTEMPTS, int(values.auto_renderer_attempts) + 1)
			plan["counted"] = config.save(path) == OK
			plan["attempts"] = int(values.auto_renderer_attempts) + 1
	restarting = true
	return plan

## Restarts the game into `renderer` (see the header) and quits `tree`.
## Called from the diagnostics autoload's _ready, the quit ends the main loop
## after the first frame, but the process only exits if Main has not started
## its startup work by then: with it running, the windowed game stops drawing
## and never exits (measured, 2026-11-04, also for the explicit-renderer
## restart before this file). Main therefore returns from _ready at once while
## ClientDiagnostics.restart_pending() is true.
static func restart(tree: SceneTree, renderer: String, path := SETTINGS_PATH) -> Dictionary:
	var plan := begin_restart(renderer, path)
	if str(plan.mode) == "relaunch":
		tree.quit(RELAUNCH_EXIT_CODE)
	else:
		OS.set_restart_on_exit(true, plan.arguments)
		tree.quit()
	return plan
