extends SceneTree
## Race features under equipment: the runtime half of race programme P4.
##
## A race feature is a mesh node of its own on the race body:
## `race_feature_head` (Votary horns, Stoneborn crown, Glasswarden crystals) and
## `race_feature_shoulders` (Mycelari growths). This checks what the actor does
## with them:
##   - headwear follows models["3:N"].raceFeatures, which is copied from
##     eloria-assets/tools/headwear_race_policy.json (checked here too): a
##     "hide" helm hides hair, scalp and the features; a "show" hood hides the
##     hair only and keeps scalp and features on a body with the feature node
##     (a body without one hides its scalp as before); an open band hides
##     nothing; a piece with no policy hides the features when it covers the
##     hair;
##   - every torso and every cape hides the shoulder growths unless the item
##     says "show", headwear marked raceShoulders "hide" (policy `shoulders`)
##     hides them too, and taking them off brings the growths back;
##   - no skin, hair or eye choice puts a material on a feature node.
## Until the rebuilt bodies carry the nodes, a body without one gets a
## synthetic copy of its scalp (or shirt) under the feature name, with a
## feature material of its own; a body that has the node is used as it is.

const POLICY_PATH := "../eloria-assets/tools/headwear_race_policy.json"
const LEATHER_HELM := 134
const BUCKLED_HOOD := 159
const SUN_HEADBAND := 170
## A hood whose scarf reaches the shoulder growths (policy shoulders "hide").
const SCARF_HOOD := 171
## Pieces that stay clear of the shoulder growths in every played clip (policy
## shoulders "none"): a cloth cap and an open hood.
const CLEAR_CAP := 149
const CLEAR_HOOD := 110
## The class-kit torsos and one cape: what a new character first wears.
const KIT_TORSOS := [209, 225, 222, 189]
const CAPE := 100

var failures := 0
var checks := 0
var synthetic := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _mesh(actor: ReplicatedActor3D, name: String) -> MeshInstance3D:
	return actor.find_child(name, true, false) as MeshInstance3D

## The body's own feature node, or a stand-in built from `source`: same mesh
## data, skin and skeleton, its own feature-named material, appended beside
## the body's other surfaces the way the rebuilt GLBs append it.
func _feature(actor: ReplicatedActor3D, name: String, source: String,
		material_name: String) -> MeshInstance3D:
	var existing := _mesh(actor, name)
	if existing != null:
		return existing
	var from := _mesh(actor, source)
	if from == null or from.mesh == null:
		return null
	var feature := from.duplicate() as MeshInstance3D
	feature.name = name
	feature.material_override = null
	for surface in from.mesh.get_surface_count():
		feature.set_surface_override_material(surface, null)
	var mesh := from.mesh.duplicate() as ArrayMesh
	var material := StandardMaterial3D.new()
	material.resource_name = material_name
	material.albedo_color = Color(0.82, 0.78, 0.66)
	for surface in mesh.get_surface_count():
		mesh.surface_set_material(surface, material)
	feature.mesh = mesh
	for meta: StringName in feature.get_meta_list():
		feature.remove_meta(meta)
	from.get_parent().add_child(feature)
	synthetic += 1
	return feature

func _hair_shown(actor: ReplicatedActor3D) -> bool:
	var shown := false
	for node: Node in actor.get_skeleton().get_children():
		if node.name.begins_with("AppearanceHair_"):
			shown = shown or (node as Node3D).visible
	return shown

func _configure(slug: String, models: Dictionary, equipment: Dictionary,
		appearance: Dictionary) -> ReplicatedActor3D:
	var config: Dictionary = models[slug]
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config["animationMap"]))
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure({"actor_id": 993, "x": 0, "y": 0, "rotation": 0,
		"kind": 1, "name": slug, "appearance": appearance, "equipment_visuals": {}},
		CoordinateAdapter.new({"walkingHeight": 0.0}), config, animations, equipment)
	expect(errors.is_empty(), slug + " configures: " + str(errors))
	return actor

func _check_policy_table(equipment: Dictionary) -> void:
	var path := ProjectSettings.globalize_path("res://").path_join(POLICY_PATH)
	var text := FileAccess.get_file_as_string(path)
	expect(not text.is_empty(), "the headwear race policy table is readable at " + path)
	if text.is_empty():
		return
	var policy: Dictionary = JSON.parse_string(text)
	var pieces: Dictionary = policy.get("pieces", {})
	var headwear := 0
	var shown := 0
	for key: String in equipment["models"]:
		var model: Dictionary = equipment["models"][key]
		if not key.begins_with("3:"):
			expect(not model.has("raceFeatures") or str(model["raceFeatures"]) in ["show", "hide"],
				key + " raceFeatures is show or hide")
			continue
		headwear += 1
		var row: Dictionary = pieces.get(key, {})
		expect(not row.is_empty(), key + " has a row in the headwear race policy")
		expect(str(row.get("name", "")) == str(model.get("name", "")),
			key + " policy row names the same piece")
		expect(str(row.get("kind", "")) in ["helm", "hood", "cap", "hat", "coif",
			"wrap", "turban", "veil", "band"], key + " policy kind is known")
		expect(str(row.get("raceFeatures", "")) in ["show", "hide"]
			and str(row.get("ears", "")) in ["tuck", "none"]
			and str(row.get("horns", "")) in ["passThrough", "none"]
			and str(row.get("shoulders", "")) in ["hide", "none"],
			key + " policy values are known")
		expect(str(model.get("raceFeatures", "")) == str(row.get("raceFeatures", "")),
			key + " equipment.json raceFeatures matches the policy table")
		expect(str(model.get("raceShoulders", "none")) == str(row.get("shoulders", "")),
			key + " equipment.json raceShoulders matches the policy table")
		if str(row.get("raceFeatures", "")) == "show":
			shown += 1
			expect(str(row.get("kind", "")) in ["hood", "band"], key + " only hoods and open bands show")
	expect(headwear == 64 and pieces.size() == 64, "64 headwear pieces, 64 policy rows")
	expect(shown == 15, "11 hoods and 4 open bands show the race features, got %d" % shown)

func _check_headwear(models: Dictionary, equipment: Dictionary) -> void:
	for slug: String in ["votary_male", "stoneborn_female"]:
		var actor := _configure(slug, models, equipment, {"hair": 1, "skin": 0})
		var feature := _feature(actor, "race_feature_head", "scalp", "Race feature horn")
		var scalp := _mesh(actor, "scalp")
		expect(feature != null and scalp != null, slug + " has a head feature and a scalp")
		if feature == null or scalp == null:
			actor.free()
			continue
		actor.apply_appearance_variants({"hair": 1, "skin": 0})
		expect(feature.visible and scalp.visible and _hair_shown(actor),
			slug + " bare head shows features, scalp and hair")
		actor.apply_equipment_visuals({3: LEATHER_HELM})
		expect(not feature.visible and not scalp.visible and not _hair_shown(actor),
			slug + " Leather Helm hides the features, the scalp and the hair")
		actor.apply_equipment_visuals({3: BUCKLED_HOOD})
		expect(feature.visible, slug + " Buckled Hood shows the features")
		expect(scalp.visible, slug + " Buckled Hood keeps the feature-free scalp")
		expect(not _hair_shown(actor), slug + " Buckled Hood still hides the hair")
		actor.apply_equipment_visuals({3: SUN_HEADBAND})
		expect(feature.visible and scalp.visible and _hair_shown(actor),
			slug + " an open band hides none of them")
		actor.apply_equipment_visuals({3: LEATHER_HELM, 5: KIT_TORSOS[0]})
		actor.apply_equipment_visuals({5: KIT_TORSOS[0]})
		expect(feature.visible and scalp.visible and _hair_shown(actor),
			slug + " taking the helm off restores features, scalp and hair")
		actor.apply_equipment_visuals({})
		# Skin 5 dyes the head; the features are not skin.
		var before := feature.mesh.surface_get_material(0)
		actor.apply_appearance_variants({"hair": 1, "skin": 5, "eyes": 6})
		expect(feature.material_override == null
			and feature.get_surface_override_material(0) == null
			and feature.get_active_material(0) == before,
			slug + " skin 5 leaves the feature material untouched")
		expect(scalp.get_surface_override_material(0) is ShaderMaterial
			or scalp.material_override is ShaderMaterial,
			slug + " skin 5 still dyes the scalp")
		actor.free()
	# A piece with no policy falls back on coversHair: features hidden.
	var unpoliced: Dictionary = equipment.duplicate(true)
	(unpoliced["models"]["3:%d" % BUCKLED_HOOD] as Dictionary).erase("raceFeatures")
	var band_hides: Dictionary = unpoliced["models"]["3:%d" % SUN_HEADBAND]
	band_hides["raceFeatures"] = "hide"
	var actor := _configure("votary_female", models, unpoliced, {"hair": 2})
	var feature := _feature(actor, "race_feature_head", "scalp", "Race feature horn")
	var scalp := _mesh(actor, "scalp")
	actor.apply_equipment_visuals({3: BUCKLED_HOOD})
	expect(not feature.visible and not scalp.visible and not _hair_shown(actor),
		"a hair-covering piece without a policy hides features and scalp")
	actor.apply_equipment_visuals({3: SUN_HEADBAND})
	expect(not feature.visible and scalp.visible and _hair_shown(actor),
		"an explicit hide on an open band hides only the features")
	actor.apply_equipment_visuals({})
	expect(feature.visible and scalp.visible and _hair_shown(actor),
		"unequipping the band restores the features")
	actor.free()
	# Human bodies need their scalp to close the visible head inside a hood,
	# including when they have no separate race-feature node.
	var human := _configure("luminous_male", models, equipment, {"hair": 1})
	expect(_mesh(human, "race_feature_head") == null, "the Human body carries no race_feature_head")
	human.apply_equipment_visuals({3: BUCKLED_HOOD})
	expect(_mesh(human, "scalp").visible and not _hair_shown(human),
		"a show hood on a body without features preserves the scalp and hides hair")
	human.apply_equipment_visuals({3: LEATHER_HELM})
	expect(not _mesh(human, "scalp").visible, "a helm still hides a Human scalp")
	human.apply_equipment_visuals({})
	expect(_mesh(human, "scalp").visible and _hair_shown(human), "bare-headed the Human scalp and hair return")
	human.free()

func _check_shoulders(models: Dictionary, equipment: Dictionary) -> void:
	for slug: String in ["mycelari_female", "mycelari_male"]:
		var actor := _configure(slug, models, equipment, {"skin": 0})
		var growths := _feature(actor, "race_feature_shoulders", "wardrobe_shirt",
			"Race feature growth")
		expect(growths != null, slug + " has shoulder growths")
		if growths == null:
			actor.free()
			continue
		actor.apply_appearance_variants({"skin": 0})
		expect(growths.visible, slug + " bare shoulders show the growths")
		for torso: int in KIT_TORSOS:
			actor.apply_equipment_visuals({5: torso})
			expect(not growths.visible, "%s torso 5:%d hides the growths" % [slug, torso])
		actor.apply_equipment_visuals({})
		expect(growths.visible, slug + " taking the torso off restores the growths")
		actor.apply_equipment_visuals({2: CAPE})
		expect(not growths.visible, slug + " a cape hides the growths")
		actor.apply_equipment_visuals({2: CAPE, 5: KIT_TORSOS[0]})
		actor.apply_equipment_visuals({2: CAPE})
		expect(not growths.visible, slug + " the cape keeps them hidden once the torso is off")
		actor.apply_equipment_visuals({3: CLEAR_CAP, 4: 230, 6: 226})
		expect(growths.visible, slug + " head, legs and feet leave the growths alone")
		actor.apply_equipment_visuals({3: SCARF_HOOD})
		expect(not growths.visible, slug + " a hood whose scarf reaches the shoulders hides the growths")
		actor.apply_equipment_visuals({3: CLEAR_HOOD})
		expect(growths.visible, slug + " a hood clear of the shoulders leaves them")
		actor.apply_appearance_variants({"skin": 5})
		expect(growths.material_override == null
			and growths.get_surface_override_material(0) == null,
			slug + " skin 5 leaves the growth material untouched")
		actor.free()
	# A per-item override keeps them up under that one torso.
	var shown: Dictionary = equipment.duplicate(true)
	(shown["models"]["5:%d" % KIT_TORSOS[0]] as Dictionary)["raceFeatures"] = "show"
	var actor := _configure("mycelari_female", models, shown, {})
	var growths := _feature(actor, "race_feature_shoulders", "wardrobe_shirt", "Race feature growth")
	actor.apply_equipment_visuals({5: KIT_TORSOS[0]})
	expect(growths.visible, "a torso marked show keeps the growths")
	actor.apply_equipment_visuals({5: KIT_TORSOS[1]})
	expect(not growths.visible, "the next torso without the mark hides them")
	actor.free()

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	_check_policy_table(equipment)
	_check_headwear(models, equipment)
	_check_shoulders(models, equipment)
	print("RACE FEATURES: %d checks, %d failures (%d synthetic feature nodes)" % [checks, failures, synthetic])
	quit(1 if failures else 0)
