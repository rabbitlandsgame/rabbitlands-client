extends SceneTree
## Pure precedence checks plus actual selectors after autoload initialization.
const Policy := preload("res://src/runtime/optimization_profile.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)

func _run() -> void:
	var active := {"client_runtime": "rust", "remote_presentation": "rust",
		"rust_effects": "heat_bolt", "resource_admission": "rust",
		"prepared_content": "auto", "prepared_node_policy": "lazy-source-v1"}
	var legacy := {"client_runtime": "legacy", "remote_presentation": "legacy",
		"rust_effects": "legacy", "resource_admission": "legacy",
		"prepared_content": "raw", "prepared_node_policy": "retain"}
	var environment: Dictionary = {}
	var before := environment.duplicate(true)
	var result := Policy.resolve(environment, PackedStringArray())
	_check(result.features == active and result.profile == "human-testing"
		and result.reason == "default_human_testing" and not result.hardware_qualified,
		"ordinary launch requests all human-testing features")
	_check(environment == before, "pure resolution never modifies its input")
	for profile: String in ["legacy", "invalid", " "]:
		var arguments := PackedStringArray(["--optimization-profile=" + profile])
		result = Policy.resolve({}, arguments)
		_check(result.features == legacy and result.profile == "legacy",
			"legacy and invalid explicit profiles fail safely to legacy")
	result = Policy.resolve({Policy.ENVIRONMENT: "legacy"},
		PackedStringArray(["--optimization-profile=human-testing"]))
	_check(result.features == active, "profile CLI overrides profile environment")
	for feature: String in Policy.FEATURES:
		var definition: Dictionary = Policy.FEATURES[feature]
		environment = {Policy.ENVIRONMENT: "human-testing", definition.environment: legacy[feature]}
		result = Policy.resolve(environment, PackedStringArray())
		_check(result.features[feature] == legacy[feature], "individual legacy environment override: " + feature)
		result = Policy.resolve(environment, PackedStringArray([str(definition.argument) + str(active[feature])]))
		_check(result.features[feature] == active[feature], "individual CLI overrides environment: " + feature)
		environment = {Policy.ENVIRONMENT: "legacy", definition.environment: active[feature]}
		result = Policy.resolve(environment, PackedStringArray())
		_check(result.features[feature] == active[feature], "explicit feature opt-in overrides global legacy: " + feature)
		for other: String in legacy:
			if other != feature:
				_check(result.features[other] == legacy[other], "other families preserve global rollback")
	result = Policy.resolve({}, PackedStringArray(["--client-runtime="]))
	_check(result.features.client_runtime.is_empty(), "explicit empty feature CLI cannot enable a default")
	result = Policy.resolve({}, PackedStringArray(["--optimization-profile=legacy", "--optimization-profile=human-testing"]))
	_check(result.features == active, "last profile CLI occurrence wins")
	await _check_actual_selectors(active, legacy)
	print("optimization profile: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _check_actual_selectors(active: Dictionary, legacy: Dictionary) -> void:
	var saved: Dictionary = {}
	var names: Array[String] = [Policy.ENVIRONMENT]
	for definition: Dictionary in Policy.FEATURES.values():
		names.append(str(definition.environment))
	for name: String in names:
		saved[name] = {"present": OS.has_environment(name), "value": OS.get_environment(name)}
		OS.unset_environment(name)
	# Dynamic loading avoids an autoload parser dependency in SceneTree scripts.
	var controller_script: Script = load("res://src/runtime/client_runtime.gd")
	var admission: Script = load("res://src/runtime/resource_admission.gd")
	var prepared: Script = load("res://src/world/prepared_content.gd")
	var placements: Script = load("res://src/world/prepared_placements.gd")
	var effects: Script = load("res://src/world/rust_spell_flights.gd")
	var previous_request: int = admission._request_mode
	for enabled: bool in [true, false]:
		if enabled:
			OS.unset_environment(Policy.ENVIRONMENT)
		else:
			OS.set_environment(Policy.ENVIRONMENT, "legacy")
		var expected: Dictionary = active if enabled else legacy
		for feature: String in expected:
			_check(Policy.selected(feature) == expected[feature], "actual environment resolution: " + feature)
		var controller: Variant = controller_script.new()
		# Guaranteed missing directory proves the fallback without loading a DLL.
		controller.initialize("user://optimization-profile-no-native-" + str(OS.get_process_id()))
		var snapshot: Dictionary = controller.snapshot()
		_check(snapshot.requested == expected.client_runtime and snapshot.mode == "legacy",
			"controller consumes profile and preserves missing-payload fallback")
		_check(snapshot.optimization_profile.features == expected, "controller reports resolved profile requests")
		controller.close()
		admission._request_mode = -1
		_check(bool(admission.requested()) == enabled, "admission consumes the profile")
		_check(prepared.selected_mode() == expected.prepared_content, "prepared content consumes the profile")
		_check(prepared.node_policy() == expected.prepared_node_policy
			and placements.selected_policy() == expected.prepared_node_policy,
			"catalog selection and live placement policy agree")
		var effect_snapshot: Dictionary = effects.snapshot_for(null)
		_check(effect_snapshot.requested == expected.rust_effects, "effect diagnostics use resolved requests")
	admission._request_mode = previous_request
	for name: String in saved:
		if bool(saved[name].present):
			OS.set_environment(name, str(saved[name].value))
		else:
			OS.unset_environment(name)
	await process_frame
