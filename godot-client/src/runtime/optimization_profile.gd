class_name ClientOptimizationProfile
extends RefCounted
## Development defaults for human testing, not hardware-qualified recommendations.
## Explicit feature options override the profile. No environment is mutated.
const ENVIRONMENT := "RABBITLANDS_OPTIMIZATION_PROFILE"
const ARGUMENT := "--optimization-profile="
const DEFAULT_PROFILE := "human-testing"
const FEATURES := {
	"client_runtime": {"environment": "RABBITLANDS_CLIENT_RUNTIME", "argument": "--client-runtime=", "active": "rust", "legacy": "legacy"},
	"remote_presentation": {"environment": "RABBITLANDS_REMOTE_PRESENTATION", "argument": "--remote-presentation=", "active": "rust", "legacy": "legacy"},
	"rust_effects": {"environment": "RABBITLANDS_RUST_EFFECTS", "argument": "--rust-effects=", "active": "heat_bolt", "legacy": "legacy"},
	"resource_admission": {"environment": "RABBITLANDS_RESOURCE_ADMISSION", "argument": "--resource-admission=", "active": "rust", "legacy": "legacy"},
	"prepared_content": {"environment": "RABBITLANDS_PREPARED_CONTENT", "argument": "--prepared-content=", "active": "auto", "legacy": "raw"},
	"prepared_node_policy": {"environment": "RABBITLANDS_PREPARED_NODE_POLICY", "argument": "--prepared-node-policy=", "active": "lazy-source-v1", "legacy": "retain"},
}

static func _option(environment_value: String, arguments: PackedStringArray, prefix: String) -> Dictionary:
	var value := environment_value.strip_edges().to_lower()
	var present := not value.is_empty()
	for argument: String in arguments:
		if argument.begins_with(prefix):
			value = argument.trim_prefix(prefix).strip_edges().to_lower()
			present = true
	return {"present": present, "value": value}

static func resolve_profile(environment_value: String, arguments: PackedStringArray) -> Dictionary:
	var option := _option(environment_value, arguments, ARGUMENT)
	var requested := str(option.value) if bool(option.present) else DEFAULT_PROFILE
	var active := requested == DEFAULT_PROFILE
	return {"requested": requested, "profile": DEFAULT_PROFILE if active else "legacy",
		"human_testing": active, "hardware_qualified": false,
		"reason": ("default_human_testing" if not bool(option.present) else "human_testing_selected")
			if active else ("legacy_selected" if requested == "legacy" else "invalid_profile_legacy")}

static func _resolve_feature(feature: String, environment_value: String,
		arguments: PackedStringArray, profile: Dictionary) -> String:
	var definition: Dictionary = FEATURES.get(feature, {})
	if definition.is_empty():
		return ""
	var option := _option(environment_value, arguments, str(definition.argument))
	if bool(option.present):
		return str(option.value)
	return str(definition.active if bool(profile.human_testing) else definition.legacy)

## Pure resolver for fixtures and reporting. The supplied environment is read only.
static func resolve(environment: Dictionary, arguments: PackedStringArray) -> Dictionary:
	var profile := resolve_profile(str(environment.get(ENVIRONMENT, "")), arguments)
	var features: Dictionary = {}
	for feature: String in FEATURES:
		var definition: Dictionary = FEATURES[feature]
		features[feature] = _resolve_feature(feature,
			str(environment.get(definition.environment, "")), arguments, profile)
	var result := profile.duplicate()
	result["features"] = features
	return result

static func selected(feature: String) -> String:
	var definition: Dictionary = FEATURES.get(feature, {})
	if definition.is_empty():
		return ""
	var arguments := OS.get_cmdline_user_args()
	var profile := resolve_profile(OS.get_environment(ENVIRONMENT), arguments)
	return _resolve_feature(feature, OS.get_environment(str(definition.environment)), arguments, profile)

static func snapshot() -> Dictionary:
	var environment := {ENVIRONMENT: OS.get_environment(ENVIRONMENT)}
	for definition: Dictionary in FEATURES.values():
		environment[definition.environment] = OS.get_environment(str(definition.environment))
	return resolve(environment, OS.get_cmdline_user_args())
