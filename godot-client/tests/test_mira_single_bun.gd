extends SceneTree
## Mira is an explicit single-bun look, not the default legacy Buns family.
const PC := preload("res://src/actors/portrait_customization.gd")
const PRESETS := preload("res://src/actors/human_portrait_presets.gd")
const MAP := preload("res://src/actors/rl_head/rl_head_portrait_map.gd")
const MODULES := preload("res://src/actors/rl_head/rl_head_hair_modules.gd")
const BASES := preload("res://src/ui/creation_base_library.gd")
const FORM := preload("res://src/ui/portrait_customization_form.gd")
var checks := 0
var failures := 0

func _initialize() -> void:
	_run.call_deferred()

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _run() -> void:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	check(int(PRESETS.detail("Mira").hair_module) == 3, "Mira detail explicitly selects her original module")
	check(not MODULES.supports_native_head(3, "female"), "original Mira asset remains High-only")
	check(MODULES.supports_native_head(25, "female"), "named lower-tier alternative is independently qualified")
	for version: int in [3, 4]:
		var row := BASES.find(BASES.rows(registry, version), "study_mira")
		var appearance: Dictionary = row.look.appearance
		check(row.sex == "female" and int(appearance.hair_module) == 3, "PC%d Mira catalog pins the single bun" % version)
		check(AppearanceVariants.hair_style(int(appearance.hair)) == 3, "Mira keeps her compatibility family byte")
		check(PC.validate(appearance, version).ok, "Mira validates on the negotiated protocol")
		var decoded := appearance.merged(PC.decode(PC.encode(appearance, version), 0), true)
		check(int(decoded.hair_module) == 3 and MAP.hair(decoded, "female") == "mira_bun",
			"PC%d wire round trip preserves the original High single bun" % version)
		check(MAP.native_hair(decoded, "female") == "painted_topknot_female",
			"Mira uses the qualified single topknot on Native tiers")
		var face := RLHeadAppearance.from_preset("mira")
		var inverse := MAP.to_portrait_fields(face, "female")
		check(int(inverse.hair_style) == 3 and int(inverse.get("hair_module", 0)) == 3,
			"Mira inverse preserves both compatibility family and explicit module")
		var inverse_look := appearance.merged(inverse, true)
		inverse_look.hair = AppearanceVariants.pack_hair(int(inverse.hair_style),
			AppearanceVariants.hair_color_index(int(appearance.hair)))
		inverse_look.erase("hair_style")
		var inverse_wire := inverse_look.merged(PC.decode(PC.encode(inverse_look, version), 0), true)
		check(MAP.face(inverse_wire, "female").hair == face.hair,
			"PC%d inverse/wire/forward round trip keeps Mira's chosen hair" % version)
	# PC0-2 cannot encode a module. Their historical family-only behavior stays.
	for version: int in [0, 1, 2]:
		var row := BASES.find(BASES.rows(registry, version), "study_mira")
		check(int(row.look.appearance.get("hair_module", 0)) == 0,
			"PC%d catalog does not pretend to carry an unsupported variation" % version)
		check(MAP.hair(row.look.appearance, "female") == "painted_twin_buns_female",
			"PC%d retains its existing family-only rendering" % version)
	var auto := {"hair": AppearanceVariants.pack_hair(3, 14), "hair_module": 0}
	var explicit := auto.merged({"hair_module": 3}, true)
	for module: int in [0, 1]:
		var look := auto.merged({"hair_module": module}, true)
		check(MAP.hair(look, "female") == "painted_twin_buns_female" \
			and MAP.native_hair(look, "female") == "painted_twin_buns_female",
			"ordinary Auto/classic Buns still chooses twin buns")
	check(MAP.native_hair(explicit, "male") == "painted_twin_buns_male",
		"female named fallback never selects a male topknot")
	var missing := MODULES.ENTRIES.duplicate(true)
	missing.erase(25)
	check(MAP.native_hair(explicit, "female", missing) == "painted_twin_buns_female",
		"missing named alternative falls back to the qualified saved family")
	var unqualified := MODULES.ENTRIES.duplicate(true)
	unqualified[25].variants.female.native_head = false
	check(MAP.native_hair(explicit, "female", unqualified) == "painted_twin_buns_female",
		"unqualified named alternative cannot bypass the Native gate")
	var wrong_sex := MODULES.ENTRIES.duplicate(true)
	wrong_sex[25].variants.erase("female")
	check(MAP.native_hair(explicit, "female", wrong_sex) == "painted_twin_buns_female",
		"another sex's qualified alternative cannot be selected")
	var form := FORM.new()
	root.add_child(form)
	form.set_body(0)
	form.set_detail_enabled(true)
	form.apply_preset("Mira")
	check(int(form.values().hair_module) == 3, "editor Mira preset preserves the explicit single bun")
	var saved: Dictionary = BASES.find(BASES.rows(registry, 4), "study_mira").look.appearance
	form.set_values(saved)
	check(int(form.values().hair_module) == 3, "applying Mira as a creation basis keeps her module in the editor")
	form.set_detail_enabled(false)
	form.apply_preset("Mira")
	check(int(form.values().hair_module) == 0, "older editor preset does not introduce an unsupported module")
	form.free()
	await process_frame
	print("Mira single bun: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
