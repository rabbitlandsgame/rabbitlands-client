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
	_check_namespace()
	_check_placement_capability()
	_check_default_replacements()
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
	for id: int in frozen:
		_expect(Map.HAIR_MODULES.get(id) == frozen[id], "existing module %d keeps its entry" % id)
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

func _check_namespace() -> void:
	_expect(Modules.validate().ok and Modules.validate(FIXTURE).ok, "live and synthetic variant registries validate")
	var cross_alias := {
		9: {"name": "collision", "sex": "male"},
		10: {"name": "other", "variants": {"female": "collision"}},
	}
	var checked := Modules.validate(cross_alias)
	_expect(not checked.ok and str(checked.errors).contains("Semantic name collision"),
		"a semantic alias cannot shadow another ID's concrete fit across sexes")
	var reverse_order := {10: cross_alias[10], 9: cross_alias[9]}
	_expect(not Modules.validate(reverse_order).ok, "cross-alias rejection is independent of insertion order")
	var duplicate_alias := {9: {"name": "same", "sex": "male"}, 10: {"name": "same", "sex": "female"}}
	_expect(not Modules.validate(duplicate_alias).ok, "semantic aliases have one ID owner globally")
	var duplicate_fit := {
		9: {"name": "one", "variants": {"female": "fit"}},
		10: {"name": "two", "variants": {"female": "fit"}},
	}
	_expect(not Modules.validate(duplicate_fit).ok, "a body's concrete fit has one ID owner")
	_expect(Modules.validate({9: {"name": "same", "variants": {"female": "same", "male": "same"}}}).ok,
		"one ID can own its own alias and both body's concrete fits")
	_expect(not Modules.validate({32: {"name": "outside_wire", "sex": "female"}}).ok,
		"new entries cannot exceed existing wire capacity")
	_expect(not Modules.validate({9: {"name": "bad_fallback", "variants": {"male": {"name": "fit", "fallback_style": 0}}}}).ok,
		"variant fallback must be a nonbald existing hairstyle slot")

func _check_placement_capability() -> void:
	var entries := {
		31: {"name": "fixture_tied", "tie_height": true, "variants": {
			"female": "fixture_tied_female",
			"male": {"name": "fixture_tied_male", "tie_height": false}}},
		30: {"name": "fixture_one_tie", "sex": "female", "tie_height": true},
	}
	_expect(Modules.validate(entries).ok, "placement flags are valid optional metadata")
	_expect(Modules.supports_tie_height(31, "female", entries), "qualified variant inherits placement support")
	_expect(not Modules.supports_tie_height(31, "male", entries), "a variant can decline placement support")
	_expect(Modules.supports_tie_height(30, "female", entries), "a single-body fit can declare placement support")
	_expect(not Modules.supports_tie_height(30, "male", entries), "unavailable body never exposes placement")
	_expect(not Modules.supports_tie_height(29, "female", entries), "unknown module never exposes placement")
	for id: int in range(2, 9):
		for sex: String in ["female", "male"]:
			_expect(not Modules.supports_tie_height(id, sex), "existing styles retain fixed attachment placement")
	_expect(not Modules.validate({9: {"name": "bad_flag", "sex": "female", "tie_height": 1}}).ok,
		"integer placement flag is rejected")
	_expect(not Modules.validate({9: {"name": "bad_variant_flag", "variants": {"female": {"name": "fit", "tie_height": "true"}}}}).ok,
		"variant placement flag must be boolean")


func _check_default_replacements() -> void:
	var entries := {
		22: {"name": "fixture_part", "variants": {"female": "fixture_part_female", "male": "fixture_part_male"}},
		9: {"name": "fixture_long", "sex": "female", "fallback_style": 2},
	}
	var before := entries.duplicate(true)
	_expect(Modules.LEGACY_REPLACEMENTS.size() == 9, "every original hairstyle family has a replacement reservation")
	for sex: String in ["female", "male"]:
		var saved := {"hair": AppearanceVariants.pack_hair(1, 3), "hair_module": 1}
		var wire := Custom.encode(saved, 3)
		_expect(Map.hair(saved, sex, entries) == "fixture_part_" + sex,
			"saved classic selection resolves its body's modern replacement")
		_expect(wire == Custom.encode(saved, 3) and saved.hair_module == 1,
			"lookup does not rewrite saved slots or module bytes")
		_expect(Map.upgrade_legacy("legacy:parted", sex, entries) == "fixture_part_" + sex,
			"raw legacy aliases use the same replacement")
	_expect(Map.hair({"hair": AppearanceVariants.pack_hair(2, 0)}, "female", entries) == "fixture_long",
		"automatic long selection uses the qualified replacement")
	_expect(Map.hair({"hair": AppearanceVariants.pack_hair(2, 0)}, "male", entries) == "legacy:long",
		"an unavailable fit never crosses to another body's asset")
	_expect(Map.hair({"hair": 1}, "male", entries) == "rowan_shag", "existing modern automatic reference stays selected")
	_expect(Map.hair({"hair": 0, "hair_module": 1}, "female", entries) == "none", "Bald remains Bald")
	_expect(Modules.replacement_id(0, "female", entries) == 0 and Modules.replacement_id(99, "male", entries) == 0,
		"unknown and bald slots do not select an arbitrary module")
	_expect(entries == before, "replacement resolution leaves the registry unchanged")

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
	_expect(form.module_hint.text == "Selected: Fixture Shared", "UI hint uses the semantic style label")
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
