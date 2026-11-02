extends SceneTree
## Exercise the real rig and skin shader's value plumbing without loading
## character GLBs or textures. The visual counterpart is the short-coils nape.
const Rig := preload("res://src/actors/rl_head/rl_head_rig.gd")
const Library := preload("res://src/actors/rl_head/rl_head_library.gd")
const Policy := preload("res://src/actors/rl_head/rl_head_scalp_overlay.gd")
const Modules := preload("res://src/actors/rl_head/rl_head_hair_modules.gd")
const Age := preload("res://src/actors/character_age.gd")
var checks := 0
var failures := 0


func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)


func _initialize() -> void:
	check_registered_styles()
	for mode: int in [0, 1]:
		check_rig(mode)
	Library.clear()
	Library.reload_values_switch()
	print("RL scalp overlay: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)


func check_registered_styles() -> void:
	var names := PackedStringArray(RLHeadAppearance.HAIR_STYLES)
	for id: int in Modules.ENTRIES:
		var entry: Dictionary = Modules.ENTRIES[id]
		for sex: String in ["female", "male"]:
			var name := Modules.file_name(str(entry.name), sex)
			if not name.is_empty() and not names.has(name):
				names.append(name)
	# Unknown future styles retain the established default as well.
	names.append("future_style")
	for style: String in names:
		check(is_zero_approx(Policy.amount(style, false, Rig.HAIRLINE_UNDER_HAIR)),
			"Absent hairstyle never paints skin: " + style)
		var expected := 0.0 if style == "short_coils_male" else Rig.HAIRLINE_UNDER_HAIR
		check(is_equal_approx(Policy.amount(style, true, Rig.HAIRLINE_UNDER_HAIR), expected),
			"Only short coils opt out of the existing scalp underlay: " + style)


func check_rig(mode: int) -> void:
	var baseline := draw_values("rowan_shag", "rowan_shag", "male", true, false, false, mode)
	check(is_equal_approx(baseline.head.hairline, Rig.HAIRLINE_UNDER_HAIR),
		"Approved hair keeps its scalp underlay in values mode%d" % mode)
	for pair: Array in [["rowan_shag", "male"], ["mira_bun", "female"],
		["rounded_afro", "male"], ["cornrows_low_knot", "female"],
		["shoulder_waves", "female"], ["curly_twin_buns", "female"],
		["receding_sweep", "male"]]:
		var result := draw_values(pair[0], pair[0], pair[1], true, false, false, mode)
		check(is_equal_approx(result.head.hairline, Rig.HAIRLINE_UNDER_HAIR),
			"Approved original style unchanged in mode%d: %s" % [mode, pair[0]])
		compare_other_values(result, baseline, "approved " + str(pair[0]))
	var coils := draw_values("short_coils_male", "short_coils_male", "male", true, false, false, mode)
	check(is_zero_approx(coils.head.hairline), "Short coils remove the painted nape in mode%d" % mode)
	compare_other_values(coils, baseline, "short coils")
	check(coils.hair == baseline.hair, "Short coils retain hair pigment, detail and greying values")
	var alias := draw_values("short_coils", "short_coils", "male", true, false, false, mode)
	check(alias.head == coils.head and alias.hair == coils.hair,
		"The registered semantic alias uses the same concrete scalp policy")
	var native := draw_values("short_coils_male", "short_coils_male", "male", true, false, true, mode)
	check(native.head == coils.head and native.hair == coils.hair and native.beard == coils.beard,
		"Native attachment retains the same colour policy")
	check(is_zero_approx(coils.weights.hl_native_fit) and is_equal_approx(native.weights.hl_native_fit, 1.0),
		"Native corrective still belongs only to Native attachment")
	native.weights.erase("hl_native_fit")
	coils.weights.erase("hl_native_fit")
	check(native.weights == coils.weights, "Native and High retain identical player groom weights")
	for scenario: Array in [["none", "none", false, false, 0.0],
		["", "short_coils_male", false, false, 0.0],
		["legacy:parted", "legacy:parted", false, true, Rig.HAIRLINE_UNDER_HAIR],
		["rowan_shag", "short_coils_male", true, false, Rig.HAIRLINE_UNDER_HAIR],
		["short_coils_male", "rowan_shag", true, false, 0.0]]:
		var result := draw_values(scenario[0], scenario[1], "male", scenario[2], scenario[3], false, mode)
		check(is_equal_approx(result.head.hairline, scenario[4]),
			"Scalp follows the actually drawn style, bald/missing and external fallback: " + str(scenario))
		compare_other_values(result, baseline, "resolved " + str(scenario[0]))


func compare_other_values(result: Dictionary, baseline: Dictionary, label: String) -> void:
	var head: Dictionary = result.head.duplicate()
	var original: Dictionary = baseline.head.duplicate()
	head.erase("hairline")
	original.erase("hairline")
	check(head == original, "Other skin, brow, eye, body and age values unchanged: " + label)
	check(result.beard == baseline.beard, "Independent beard pigment and greying unchanged: " + label)


func draw_values(style: String, saved_style: String, sex: String, present: bool,
		external: bool, native: bool, mode: int) -> Dictionary:
	Library.reload_values_switch()
	Library._values_switch = mode
	var rig := Rig.new()
	rig.quality = ActorRenderQuality.Quality.HIGH
	rig.appearance = RLHeadAppearance.new()
	var face := rig.appearance
	face.sex = sex
	face.hair = saved_style
	face.hair_color = Color(0.8, 0.72, 0.61)
	face.beard_color = Color(0.21, 0.13, 0.09)
	face.beard_color_set = true
	face.beard = "full_beard"
	face.hair_length = 0.4
	face.hair_volume = -0.3
	face.hair_detail = 80
	face.skin_age = 0.6
	face.hair_grey = 0.7
	face.freckles = 0.2
	face.stubble = 0.3
	face.liner = 0.1
	var before := face.to_dict().duplicate(true)
	rig._body_skin_color = Color(0.6, 0.45, 0.32)
	rig._hair_style = style
	rig._hair_external = external
	rig._hair_only = native
	rig._beard_style = face.beard
	var head := fixture(rig, "rl_skin", sex, "", mode)
	var beard := fixture(rig, "rl_beard", sex, face.beard, mode)
	rig._head_lods = [[head]]
	rig._beard_lods = [[beard]]
	var hair: MeshInstance3D = null
	if present:
		hair = fixture(rig, "rl_hair_clump", sex, style, mode)
		rig._hair_lods = [[hair]]
	rig._apply_colours()
	var values := {
		"head": node_values(head, Rig.INSTANCE_UNIFORMS, mode),
		"beard": node_values(beard, ["hair_color", "eye_color"], mode),
		"hair": node_values(hair, Rig.HAIR_INSTANCE_UNIFORMS, mode) if hair != null else {},
		"weights": rig._hair_shape_weights(),
	}
	check(face.to_dict() == before, "Drawing never changes the saved appearance")
	check(is_equal_approx(values.head.eye_color.a, Age.packed(0.6, 0.7)),
		"Skin age and greying remain independent packed values")
	check(is_equal_approx(values.weights.hl_length_p, 0.4)
		and is_equal_approx(values.weights.hl_volume_n, 0.3), "Length and volume retain their authored weights")
	rig.free()
	return values


func fixture(rig: Node3D, role: String, sex: String, style: String, mode: int) -> MeshInstance3D:
	var shared := ShaderMaterial.new()
	shared.resource_name = role
	shared.shader = Library.SHADERS[Library.MATERIAL_SHADERS[role]]
	if mode == 1:
		shared.shader = Library._values_shader(shared.shader)
	check(Library.shader_values(shared).has("hairline") if role == "rl_skin" else true,
		"The real skin shader owns the scalp value")
	# Supply texture-free shared materials; production rig/material dispatch and
	# the actual shader variants still run, without importing character assets.
	var concrete_style := Modules.file_name(style, sex) if role == "rl_hair_clump" else style
	Library._materials["%s|%s|%s|%d" % [role, sex, concrete_style, rig.quality]] = shared
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.UP])
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, shared)
	var node := MeshInstance3D.new()
	node.mesh = mesh
	rig.add_child(node)
	return node


func node_values(node: MeshInstance3D, names: Array, mode: int) -> Dictionary:
	var result := {}
	for name: String in names:
		result[name] = (node.get_surface_override_material(0) as ShaderMaterial).get_shader_parameter(name) \
			if mode == 1 else node.get_instance_shader_parameter(name)
	return result
