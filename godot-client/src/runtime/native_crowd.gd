extends RefCounted
## The one loader for the `native_crowd` kernels and the actor-command reducer
## (rust-batch RB-C1g). RB-C1n compiled them into the verified `client_runtime`
## payload, so a consumer asks here instead of loading an extension itself:
##
##     var made := NativeCrowd.kernel("cape")  # {object, status, provider, reason}
##
## | feature | class | caller | selected by |
## | --- | --- | --- | --- |
## | `cape` | NativeCapeConstraintKernel | cape_cloth.gd | ELORIA_NATIVE_PRESENTATION `cape`, `both`/`1`, `all` |
## | `flight` | NativeSpellFlightGeometry | spell_flight_3d.gd | `flight`, `both`/`1`, `all` |
## | `world` | NativeWorldEffectGeometry | world_effect_3d.gd | `world`, `all` |
## | `reducer` | NativeCrowdReducer | app_state.gd | ELORIA_NATIVE_CROWD `1` |
##
## No `class_name`: callers preload this file, like `native_library.gd`.
##
## ## Defaults
##
## An unset variable means the feature's entry in DEFAULTS. Every entry is
## false: owner decision D-NATIVE (2026-11-04) loads the payload for every
## Windows player, but each native feature turns on by default only after its
## own release-build A/B. Turning one on is one value here; the tests cover both.
## `0`, `off`, `script`, `gdscript` and `legacy` select GDScript, and so does any
## value the table does not know (as before).
##
## ## Providers
##
## A class is used only when the verified payload registered it:
## `RabbitLandsClientRuntime.runtime_info().native_crowd_providers[<class>] ==
## "client_runtime"`. The payload is loaded through `NativeLibrary.ensure()` when
## it is not registered yet. The benchmark extension
## `res://bin/native_crowd.gdextension` (an unverified development build) is
## loaded and trusted only when `ELORIA_NATIVE_PROVIDER=benchmark` names it;
## otherwise a class some other extension registered is refused
## (`provider_untrusted`).
##
## ## Kill switch
##
## NativeLibrary's switch (`RABBITLANDS_NATIVE_RUNTIME=off`,
## `--native-runtime=off`, `--client-safe-mode`, the support setting) turns
## every feature off, the benchmark provider included, even when the classes are
## registered.
##
## ## Statuses
##
## `active`; `disabled` (not selected); `runtime_<code>` for a NativeLibrary
## refusal (`runtime_absent`, `runtime_checksum_mismatch`,
## `runtime_switched_off`, `runtime_off_main_thread`, ...);
## `class_unavailable` (the loaded payload lacks the class: an older payload);
## `provider_untrusted`; `extension_missing` and `off_main_thread` (benchmark
## provider); `instantiate_failed`; `api_unavailable` (the instance lacks the
## method its caller uses); `unknown_feature`.
##
## Threads: the loads (`ensure()`, the benchmark extension) are main-thread only;
## elsewhere a feature that would need one gets a `*off_main_thread` status and
## stays on GDScript. Instantiating an already-registered class works anywhere.

const NativeLibrary := preload("res://src/runtime/native_library.gd")

const PRESENTATION_ENVIRONMENT := "ELORIA_NATIVE_PRESENTATION"
const REDUCER_ENVIRONMENT := "ELORIA_NATIVE_CROWD"
const PROVIDER_ENVIRONMENT := "ELORIA_NATIVE_PROVIDER"
const BENCHMARK_PROVIDER := "benchmark"
const BENCHMARK_EXTENSION := "res://bin/native_crowd.gdextension"
## Player defaults per feature (see Defaults).
const DEFAULTS := {"cape": false, "flight": false, "world": false, "reducer": false}
const CLASSES := {"cape": &"NativeCapeConstraintKernel", "flight": &"NativeSpellFlightGeometry",
	"world": &"NativeWorldEffectGeometry", "reducer": &"NativeCrowdReducer"}
## The method each caller relies on.
const METHODS := {"cape": &"step", "flight": &"build", "world": &"build", "reducer": &"reduce_packet"}
## ELORIA_NATIVE_PRESENTATION values and the kernels they select (unchanged).
const PRESENTATION_MODES := {"cape": ["cape"], "flight": ["flight"], "both": ["cape", "flight"],
	"1": ["cape", "flight"], "world": ["world"], "all": ["cape", "flight", "world"]}
const OFF_VALUES: Array[String] = ["0", "off", "script", "gdscript", "legacy"]

static var _lock := Mutex.new()
static var _providers: Dictionary = {}
static var _providers_known := false
static var _stats: Dictionary = {}

## Makes the native object for `feature` when it is selected and allowed, else
## {object: null} with the reason. Returns {object, status, provider, reason}.
static func kernel(feature: String) -> Dictionary:
	var made := _make(feature)
	_record(feature, made)
	return made

## Pure selection, for fixtures and reporting: whether `feature` is selected by
## `environment` (the variables above) with `defaults`. Returns {wanted, reason}.
static func selection(feature: String, environment: Dictionary, defaults := DEFAULTS) -> Dictionary:
	var variable := REDUCER_ENVIRONMENT if feature == "reducer" else PRESENTATION_ENVIRONMENT
	var value := str(environment.get(variable, "")).strip_edges().to_lower()
	if value.is_empty():
		var by_default := bool(defaults.get(feature, false))
		return {"wanted": by_default, "reason": "default_on" if by_default else "default_off"}
	if value in OFF_VALUES:
		return {"wanted": false, "reason": "script_selected"}
	if feature == "reducer":
		return {"wanted": value == "1", "reason": "selected" if value == "1" else "unknown_value"}
	if not PRESENTATION_MODES.has(value):
		return {"wanted": false, "reason": "unknown_value"}
	var named: bool = feature in PRESENTATION_MODES[value]
	return {"wanted": named, "reason": "selected" if named else "not_selected"}

## Whether an external registration may stand in for the payload, and the
## benchmark extension may be loaded (`ELORIA_NATIVE_PROVIDER=benchmark`).
static func benchmark_allowed(environment := {}) -> bool:
	var value: String = str(environment.get(PROVIDER_ENVIRONMENT, "")) if not environment.is_empty() \
		else OS.get_environment(PROVIDER_ENVIRONMENT)
	return value.strip_edges().to_lower() == BENCHMARK_PROVIDER

## Pure provider rule: whether a class registered by `provider` ("client_runtime",
## "external", "absent", or "" when no runtime reports providers) may be used.
static func provider_trusted(provider: String, benchmark: bool) -> bool:
	return provider == "client_runtime" or (benchmark and provider in ["external", ""])

## `runtime_info().native_crowd_providers` of the registered runtime, or {}
## before it is registered (or from a payload older than RB-C1n). Cached once
## the runtime is registered.
static func providers() -> Dictionary:
	_lock.lock()
	if not _providers_known and ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS):
		var runtime: Object = ClassDB.instantiate(NativeLibrary.RUNTIME_CLASS)
		var info: Variant = runtime.call("runtime_info") if runtime != null and runtime.has_method("runtime_info") else {}
		var found: Variant = (info as Dictionary).get("native_crowd_providers", {}) if info is Dictionary else {}
		_providers = (found as Dictionary).duplicate() if found is Dictionary else {}
		_providers_known = true
	var out := _providers.duplicate()
	_lock.unlock()
	return out

## {defaults, benchmark_provider, providers, features: {feature: {selected,
## reason, attempts, active, last_status, provider}}} for diagnostics and the
## startup receipt.
static func snapshot() -> Dictionary:
	var environment := _environment()
	var features := {}
	_lock.lock()
	for feature: String in CLASSES:
		var entry: Dictionary = _stats.get(feature, {"attempts": 0, "active": 0, "last_status": "", "provider": ""})
		var selected := selection(feature, environment)
		features[feature] = entry.duplicate()
		features[feature].merge({"selected": selected.wanted, "reason": selected.reason})
	_lock.unlock()
	return {"defaults": DEFAULTS.duplicate(), "benchmark_provider": benchmark_allowed(),
		"providers": providers(), "features": features}

## Forgets the provider cache and the counters (tests only).
static func reset_for_tests() -> void:
	_lock.lock()
	_providers = {}
	_providers_known = false
	_stats = {}
	_lock.unlock()

static func _environment() -> Dictionary:
	return {PRESENTATION_ENVIRONMENT: OS.get_environment(PRESENTATION_ENVIRONMENT),
		REDUCER_ENVIRONMENT: OS.get_environment(REDUCER_ENVIRONMENT)}

static func _on_main_thread() -> bool:
	return OS.get_thread_caller_id() == OS.get_main_thread_id()

static func _make(feature: String) -> Dictionary:
	var made := {"object": null, "status": "disabled", "provider": "", "reason": ""}
	if not CLASSES.has(feature):
		made.status = "unknown_feature"
		return made
	# One variable read per call: flights and impacts are made per cast.
	var variable := REDUCER_ENVIRONMENT if feature == "reducer" else PRESENTATION_ENVIRONMENT
	var selected := selection(feature, {variable: OS.get_environment(variable)})
	made.reason = selected.reason
	if not bool(selected.wanted):
		return made
	if str(NativeLibrary.switch_state().mode) == "off":
		made.status = "runtime_" + NativeLibrary.SWITCHED_OFF
		return made
	var name: StringName = CLASSES[feature]
	var benchmark := benchmark_allowed()
	if benchmark and not ClassDB.class_exists(name):
		if not FileAccess.file_exists(BENCHMARK_EXTENSION):
			made.status = "extension_missing"
			return made
		if not _on_main_thread():
			made.status = "off_main_thread"
			return made
		GDExtensionManager.load_extension(BENCHMARK_EXTENSION)
		_forget_providers()
	if not ClassDB.class_exists(name):
		if ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS):
			made.status = "class_unavailable"
			return made
		var loaded := NativeLibrary.ensure()
		if not bool(loaded.get("ok", false)):
			made.status = "runtime_" + str(loaded.get("code", "absent"))
			return made
		_forget_providers()
		if not ClassDB.class_exists(name):
			made.status = "class_unavailable"
			return made
	var provider := str(providers().get(str(name), ""))
	made.provider = provider if not provider.is_empty() else "unknown"
	if not provider_trusted(provider, benchmark):
		made.status = "provider_untrusted"
		return made
	var object: Object = ClassDB.instantiate(name)
	if object == null:
		made.status = "instantiate_failed"
		return made
	if not object.has_method(METHODS[feature]):
		made.status = "api_unavailable"
		return made
	made.object = object
	made.status = "active"
	return made

static func _forget_providers() -> void:
	_lock.lock()
	_providers = {}
	_providers_known = false
	_lock.unlock()

static func _record(feature: String, made: Dictionary) -> void:
	if str(made.status) == "disabled":
		return
	_lock.lock()
	var entry: Dictionary = _stats.get(feature, {"attempts": 0, "active": 0, "last_status": "", "provider": ""})
	entry.attempts = int(entry.attempts) + 1
	entry.active = int(entry.active) + int(made.object != null)
	entry.last_status = str(made.status)
	entry.provider = str(made.provider)
	_stats[feature] = entry
	_lock.unlock()
