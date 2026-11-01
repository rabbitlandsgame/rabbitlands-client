extends SceneTree
## Saved legacy selections migrate to modern shaders without baking grey into dye.
const STAGE := preload("res://prototypes/rl_heads/rl_head_stage.gd")
const LAB := preload("res://prototypes/rl_heads/rl_head_lab.gd")
const AGE := preload("res://src/actors/character_age.gd")
var failures := 0
var checks := 0

func _init() -> void:
	_run.call_deferred()

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

## Inspect values actually read by modern hair/beard shaders in either mode.
## Dye stays fixed; eye_color.a carries the independent greying amount.
func modern_values(actor: ReplicatedActor3D) -> Dictionary:
	var result := {}
	var rig := actor.hair_module_rig()
	if rig == null: return result
	for mesh: MeshInstance3D in rig.all_meshes():
		if mesh.mesh == null or mesh.is_queued_for_deletion(): continue
		for index: int in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(index) as ShaderMaterial
			if material == null: continue
			var uniforms := RLHeadLibrary.shader_values(material)
			if not uniforms.has("hair_color") or not uniforms.has("eye_color") \
					or uniforms.has("skin_color"): continue
			var dye: Variant = material.get_shader_parameter("hair_color") if RLHeadLibrary.material_values() \
				else mesh.get_instance_shader_parameter("hair_color")
			var carrier: Variant = material.get_shader_parameter("eye_color") if RLHeadLibrary.material_values() \
				else mesh.get_instance_shader_parameter("eye_color")
			result["%s:%d" % [rig.get_path_to(mesh), index]] = {"dye": dye, "carrier": carrier}
	return result

func check_values(values: Dictionary, grey: float, skin_age: float, label: String) -> void:
	check(not values.is_empty(), label + " has modern hair shader values")
	for key: String in values:
		var value: Dictionary = values[key]
		check(value.dye is Color and value.carrier is Color, label + " shader colours are populated")
		if value.carrier is Color:
			check(AGE.unpacked((value.carrier as Color).a).is_equal_approx(Vector2(skin_age, grey)),
				label + " shader receives independent age/grey amounts")

func dyes(values: Dictionary) -> Dictionary:
	var result := {}
	for key: String in values: result[key] = values[key].dye
	return result

func check_saved(actor: ReplicatedActor3D, base: Dictionary, label: String) -> void:
	for field: String in ["hair", "hair_module", "hair_detail", "hair_finish", "hair_hue", "hair_sat", "hair_light"]:
		check(actor._appearance.get(field, 0) == base.get(field, 0), label + " preserves saved " + field)

func legacy_colours(actor: ReplicatedActor3D) -> Array:
	var result: Array = []
	var native := actor.get_node("NativeModel") as Node3D
	for hair: MeshInstance3D in HighHairAppearance._hair_nodes(native):
		if hair.mesh == null or hair.is_queued_for_deletion() \
				or not HighHairAppearance._locally_visible(hair, native): continue
		for index: int in hair.mesh.get_surface_count():
			var material := hair.get_active_material(index)
			if material is ShaderMaterial:
				result.append((material as ShaderMaterial).get_shader_parameter("hair_color"))
			elif material is BaseMaterial3D:
				result.append((material as BaseMaterial3D).albedo_color)
	return result

func _run() -> void:
	var saved_environment := {}
	for name: String in ["RL_HEADS", "RL_HEAD_VALUES", "RL_HEAD_BAKE", "RL_HEAD_STILL"]:
		saved_environment[name] = OS.get_environment(name)
	OS.set_environment("RL_HEADS", "all")
	OS.set_environment("RL_HEAD_BAKE", "0")
	OS.set_environment("RL_HEAD_STILL", "0")
	ReplicatedActor3D.reload_rl_heads_switch()
	# Three saved finishes, custom sleek/messy endpoints and an interior value.
	for mode: String in ["instance", "material"]:
		OS.set_environment("RL_HEAD_VALUES", mode)
		RLHeadLibrary.reload_values_switch()
		for sex: String in ["female", "male"]:
			var custom := AppearanceColours.frozen_hair(2, sex) + Vector3i(0, 0, 2)
			for quality: int in [0, 1, 2]:
				var base := {"skin": 2, "hair": AppearanceVariants.pack_hair(1, 2), "eyes": 2,
					"hair_module": 1, "facial_hair": 4, "skin_age": 23,
					"hair_hue": custom.x, "hair_sat": custom.y, "hair_light": custom.z}
				var actor := STAGE.spawn(root, sex, base, {}, quality)
				var other := STAGE.spawn(root, sex, base.merged({"hair_grey": 37, "skin_age": 17}, true), {}, quality, 9301)
				await process_frame
				var isolated := modern_values(other)
				check_values(isolated, .37, .17, mode + " independent actor")
				for position: int in [25, 50, 75, 0, 63, 100]:
					var look := base.merged(HairFinish.canonical(position), true)
					var label := "%s %s quality%d finish%d" % [mode, sex, quality, position]
					actor.apply_appearance_variants(look)
					await process_frame
					check(actor.hair_module_rig() != null and actor._legacy_hair_style_drawn() == 0,
						label + " saved legacy selection draws its modern replacement")
					var original := modern_values(actor)
					check_values(original, 0.0, .23, label + " neutral")
					actor.apply_appearance_variants(look.merged({"hair_grey": 100}, true))
					await process_frame
					var grey := modern_values(actor)
					check_values(grey, 1.0, .23, label + " grey")
					check(grey != original and dyes(grey) == dyes(original), label + " greys via carrier without altering dye")
					check(modern_values(other) == isolated, label + " leaves the other actor unchanged")
					check_saved(actor, look, label)
					actor.apply_appearance_variants(look)
					await process_frame
					check(modern_values(actor) == original, label + " zero restores exact shader state")
					check(modern_values(other) == isolated, label + " recovery preserves actor isolation")
				actor.free()
				other.free()
				await process_frame
		# Actual offline slider writes normalized rl_head data without a server.
		var lab := LAB.new()
		root.add_child(lab)
		for frame: int in 5: await process_frame
		lab.face.hair = RLHeadLibrary.legacy_hair_styles(lab._sex)[0]
		lab.face.hair_grey = 0.0
		lab._apply_face()
		var source_dye: Color = lab.face.hair_color
		var before := modern_values(lab.actor)
		check_values(before, 0.0, lab.face.skin_age, mode + " offline neutral")
		var slider := lab._amount_sliders.hair_grey as HSlider
		slider.value = 1.0
		await process_frame
		check_values(modern_values(lab.actor), 1.0, lab.face.skin_age, mode + " offline grey")
		check(lab.face.hair_color == source_dye and lab.face.hair_grey == 1.0,
			mode + " offline slider preserves source dye")
		check(is_equal_approx(float(lab._actor_appearance().rl_head.hair_grey), 1.0),
			mode + " offline saved JSON retains normalized greying")
		slider.value = 0.0
		await process_frame
		check(modern_values(lab.actor) == before and lab.face.hair_color == source_dye,
			mode + " offline slider restores exact neutral state")
		lab.free()
		await process_frame
		RLHeadLibrary.clear()
	# Explicitly retain the dormant classic material-path regression, without
	# requiring retired native hair nodes on modern actors.
	OS.set_environment("RL_HEADS", "classic")
	ReplicatedActor3D.reload_rl_heads_switch()
	var classic_look := {"skin": 2, "hair": AppearanceVariants.pack_hair(1, 1), "eyes": 2, "hair_module": 1}
	var classic := STAGE.spawn(root, "male", classic_look, {}, 0)
	await process_frame
	var original := legacy_colours(classic)
	check(not original.is_empty() and classic.hair_module_rig() == null, "classic fallback has direct material colours")
	classic.apply_appearance_variants(classic_look.merged({"hair_grey": 100}, true))
	await process_frame
	check(legacy_colours(classic) != original, "classic fallback greys its direct material")
	check(int(classic._appearance.hair) == int(classic_look.hair), "classic fallback preserves saved dye")
	classic.apply_appearance_variants(classic_look)
	await process_frame
	check(legacy_colours(classic) == original, "classic fallback restores exact material dye")
	classic.free()
	await process_frame
	for name: String in saved_environment: OS.set_environment(name, saved_environment[name])
	ReplicatedActor3D.reload_rl_heads_switch()
	RLHeadLibrary.reload_values_switch()
	RLHeadLibrary.clear()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("Character age legacy: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
