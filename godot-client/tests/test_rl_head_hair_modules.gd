extends SceneTree
## Headless semantic hair contract. Synthetic entries exercise future variants
## without reserving a production ID or installing any asset.

const Modules := preload("res://src/actors/rl_head/rl_head_hair_modules.gd")
const Map := preload("res://src/actors/rl_head/rl_head_portrait_map.gd")
const Library := preload("res://src/actors/rl_head/rl_head_library.gd")
const Custom := preload("res://src/actors/portrait_customization.gd")
const FIXTURE := {
	31: {"name": "fixture_shared", "fallback_style": 1, "variants": {
		"female": {"name": "fixture_shared_female", "fallback_style": 3},
		"male": "fixture_shared_male"}},
	30: {"name": "fixture_one_body", "variants": {"female": "fixture_female_only"}},
}

class VariantForm extends "res://src/ui/portrait_customization_form.gd":
	func _module_entries() -> Dictionary:
		return FIXTURE

var checks := 0
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)

func _run() -> void:
	_check_legacy()
	_check_variants()
	await _check_form()
	print("RL semantic hair: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func _check_legacy() -> void:
	var frozen := {
		2: {"name": "rowan_shag", "sex": "male"},
		3: {"name": "mira_bun", "sex": "female"},
		4: {"name": "rounded_afro", "sex": "male", "fallback_style": 1},
		5: {"name": "cornrows_low_knot", "sex": "female", "fallback_style": 7},
		6: {"name": "shoulder_waves", "sex": "female", "fallback_style": 2},
		7: {"name": "curly_twin_buns", "sex": "female", "fallback_style": 3},
		8: {"name": "receding_sweep", "sex": "male", "fallback_style": 1},
	}
	_expect(Map.HAIR_MODULES == frozen, "IDs 2–8 are unchanged; no production IDs added")
	for id: int in frozen:
		var entry: Dictionary = frozen[id]
		var sex := str(entry.sex)
		var other := "male" if sex == "female" else "female"
		var look := {"hair": AppearanceVariants.pack_hair(2, 0), "hair_module": id}
		_expect(Map.hair(look, sex) == entry.name, "legacy ID %d resolves its original fit" % id)
		_expect(Map.hair(look, other) == Map.hair({"hair": look.hair}, other), "incompatible ID falls back to Auto")
		_expect(Library.hair_path(entry.name) == Library.hair_path(entry.name, sex), "filename API is unchanged")
		_expect(Library.hair_info(entry.name, sex) == Library.hair_info(entry.name),
			"sex-aware info uses the same concrete cache entry")
		_expect(Library.hair_path(entry.name, other).is_empty()
			and Library.hair_info(entry.name, other).is_empty(), "library refuses another body's registered fit")
		_expect(Library.hair_styles(sex).has(entry.name)
			and not Library.hair_styles(other).has(entry.name), "library list follows fit eligibility")
	# Every wire value remains representable, including unknown/reserved IDs.
	for id: int in 32:
		var look := {"hair_module": id}
		_expect(int(Custom.decode(Custom.encode(look, 3), 0).hair_module) == id,
			"PC/3 retains hair_module %d" % id)

func _check_variants() -> void:
	for sex: String in ["female", "male"]:
		var name := "fixture_shared_" + sex
		var look := {"hair": AppearanceVariants.pack_hair(2, 0), "hair_module": 31}
		_expect(Map.hair(look, sex, FIXTURE) == name, "one ID resolves the body's concrete file")
		_expect(Modules.file_name("fixture_shared", sex, FIXTURE) == name
			and Modules.file_name(name, sex, FIXTURE) == name, "semantic and concrete library names agree")
		var other := "male" if sex == "female" else "female"
		_expect(Modules.file_name(name, other, FIXTURE).is_empty(), "concrete variant cannot cross bodies")
		var face := RLHeadAppearance.new()
		face.sex = sex
		face.hair = name
		_expect(RLHeadAppearance.decode(face.encode(PackedStringArray()), PackedStringArray()).hair == name,
			"existing inline RL appearance encoding retains variant filenames")
		var inverse := Map.to_portrait_fields(face, sex, FIXTURE)
		_expect(int(inverse.hair_module) == 31 and int(inverse.hair_style) == (3 if sex == "female" else 1),
			"inverse retains the shared ID and sex-specific fallback")
		var saved := Custom.decode(Custom.encode({"hair_module": inverse.hair_module}, 3), 0)
		saved["hair"] = AppearanceVariants.pack_hair(int(inverse.hair_style), 0)
		_expect(Map.hair(saved, sex, FIXTURE) == name, "inverse, wire and forward round-trip")
		_expect(Map.hair({"hair": 0, "hair_module": 31}, sex, FIXTURE) == "none", "Bald still overrides a module")
		var grooming := Map.hair_shapes({"hair_length": 50, "hair_volume": 50}, name)
		_expect(float(grooming.length) == 0.0 and float(grooming.volume) == 0.0
			and int(grooming.detail) == 50, "new variants default to neutral grooming")
	_expect(Modules.resolve(30, "male", FIXTURE).is_empty(), "missing body variant is ineligible")
	_expect(Map.hair({"hair": 1, "hair_module": 30}, "male", FIXTURE) == "rowan_shag",
		"missing body variant uses existing Auto rule")
	_expect(Modules.resolve(31, "invalid", FIXTURE).is_empty(), "invalid body never selects a variant")
	_expect(Modules.file_name("unregistered_file", "male", FIXTURE) == "unregistered_file",
		"unregistered filename-only authoring assets remain readable")

func _select(form: VariantForm, id: int) -> void:
	var option := form.detail_controls.hair_module as OptionButton
	option.select(option.get_item_index(id))
	option.item_selected.emit(option.selected)

func _check_form() -> void:
	var form := VariantForm.new()
	root.add_child(form)
	await process_frame
	form.set_hair_style(2)
	form.set_body(0)
	var option := form.detail_controls.hair_module as OptionButton
	_expect(option.get_item_index(31) >= 0 and option.get_item_index(30) >= 0, "UI offers both female variants")
	_select(form, 31)
	form.set_body(1, true)
	_expect(int(form.values().hair_module) == 31 and option.get_item_index(31) >= 0,
		"creation preserves shared semantic ID on body switch")
	_expect(form.module_hint.text == "At High: Fixture Shared", "UI hint uses the semantic style label")
	form.set_body(0)
	_select(form, 30)
	form.set_body(1)
	_expect(int(form.values().hair_module) == 30 and option.selected == 0,
		"dressing room retains an unavailable body's saved module")
	form.set_body(1, true)
	_expect(int(form.values().hair_module) == 0 and option.get_item_index(30) < 0,
		"creation clears a known module with no matching variant")
	form.queue_free()
	await process_frame
