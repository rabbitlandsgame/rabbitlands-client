extends SceneTree
## The fitted beard opts into feathering without changing other beard/hair routes.
var failures: Array[String] = []

func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error(message)

func _initialize() -> void:
	for material_values: int in [0, 1]:
		RLHeadLibrary.clear()
		RLHeadLibrary._values_switch = material_values
		var beard := RLHeadLibrary.material("rl_beard", "male", "full_beard", ActorRenderQuality.Quality.HIGH)
		check(beard.shader.code.begins_with("#define RL_BEARD_FEATHER\n"), "Full beard must opt into continuous alpha")
		check(beard.get_shader_parameter("lock_variation") == 0.0, "Coverage red must not change beard pigment")
		check(beard.get_shader_parameter("beard_gain") == 1.0, "Reference beard keeps calibrated pigment")
		check(beard.get_shader_parameter("has_texture") == true, "Full beard must load its painted atlas")
		check(RLHeadLibrary.shader_values(beard).has("hair_color"), "Feathered shader must retain per-face pigment ownership")
		var colour := Color(0.4, 0.2, 0.8)
		var individual := RLHeadLibrary.face_material(beard, {"hair_color": colour, "hair_detail": 0.5})
		check(individual.get_shader_parameter("hair_color") == colour, "Material values must retain each actor's beard colour")
		for style: String in ["short_beard", "goatee", "moustache"]:
			var other := RLHeadLibrary.material("rl_beard", "male", style, ActorRenderQuality.Quality.HIGH)
			check(not other.shader.code.begins_with("#define RL_BEARD_FEATHER\n"), style + " must retain its original shader route")
		for item: Array in [["male", "rowan_shag"], ["female", "mira_bun"], ["male", "rounded_afro"], ["female", "cornrows_low_knot"]]:
			var hair := RLHeadLibrary.material("rl_hair_clump", item[0], item[1], ActorRenderQuality.Quality.HIGH)
			check(not hair.shader.code.begins_with("#define RL_BEARD_FEATHER\n"), item[1] + " must retain its original shader route")
	RLHeadLibrary.clear()
	RLHeadLibrary._values_switch = -1
	print("RL full beard material scope: %d failures" % failures.size())
	quit(0 if failures.is_empty() else 1)
