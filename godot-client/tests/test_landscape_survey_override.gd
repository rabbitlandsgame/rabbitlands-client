extends SceneTree
## Pure candidate-selection checks: no renderer, login or map scene is loaded.
const Survey := preload("res://tests/integration/rendered_landscape_survey.gd")
var failures := 0

func _init() -> void:
	var registry := {"four-gates": {"alias": "four_gates"},
		"four_gates": {"manifest": "canonical", "coordinateTransform": {"serverOrigin": [203, 210]}},
		"sunmane_steppe": {"manifest": "sun", "coordinateTransform": {}}}
	var data := {"asset": {"id": "four-gates"}, "coordinateTransform": {"serverOrigin": [203, 210]}}
	var result := Survey._override_registry(registry, data, "candidate/world.json", [{"map": "four_gates"}])
	_expect(result.get("registryKey") == "four_gates", "asset alias resolves the actual server-map row")
	_expect(MapRegistry.resolve(registry, "four_gates").manifest == "candidate/world.json", "actual loading key selects candidate")
	_expect(registry["four-gates"] == {"alias": "four_gates"}, "alias row remains an alias")
	_expect(registry.sunmane_steppe.manifest == "sun", "unrelated region is untouched")
	data.coordinateTransform.serverOrigin[0] = 999
	_expect(registry.four_gates.coordinateTransform.serverOrigin[0] == 203, "coordinate data is copied")
	var before := registry.duplicate(true)
	_expect(Survey._override_registry(registry, data, "other", [{"map": "sunmane_steppe"}]).has("error"), "unselected target fails loudly")
	_expect(registry == before, "rejected target does not mutate registry")
	var missing := {"asset": {"id": "missing"}, "coordinateTransform": {}}
	_expect(Survey._override_registry(registry, missing, "other", [{"map": "missing"}]).has("error"), "unknown asset fails")
	var chain := {"old": {"alias": "four-gates"}, "four-gates": {"alias": "four_gates"},
		"four_gates": {"manifest": "canonical", "coordinateTransform": {}}}
	var chained := Survey._override_registry(chain, {"asset": {"id": "old"}, "coordinateTransform": {}}, "new", [{"map": "four-gates"}])
	_expect(chained.get("registryKey") == "four_gates" and chain.four_gates.manifest == "new", "alias chains use the production resolver")
	print("Landscape survey override: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _expect(condition: bool, label: String) -> void:
	if condition:
		print("PASS: ", label)
	else:
		failures += 1
		push_error(label)
