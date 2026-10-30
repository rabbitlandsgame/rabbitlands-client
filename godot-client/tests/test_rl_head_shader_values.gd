extends SceneTree
## Shared shader variants and material-value copies retain actor pigment ownership.
var failures: Array[String] = []

func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error(message)

func _initialize() -> void:
	for mode: int in [0, 1]:
		RLHeadLibrary.reload_values_switch()
		RLHeadLibrary._values_switch = mode
		var source := RLHeadLibrary.material("rl_beard", "male", "short_beard", ActorRenderQuality.Quality.HIGH)
		var shader := source.shader
		for depth: int in 2:
			var variant := Shader.new()
			variant.code = "#define RL_TEST_VARIANT_%d\n" % depth + shader.code
			variant.set_meta(&"rl_base_shader", shader)
			shader = variant
		var shared := source.duplicate() as ShaderMaterial
		shared.shader = shader
		check(RLHeadLibrary.shader_values(shared).has("hair_color"), "Nested shader variant lost pigment ownership")
		var first_colour := Color(0.4, 0.2, 0.8)
		var second_colour := Color(0.7, 0.6, 0.5)
		var first := RLHeadLibrary.face_material(shared, {"hair_color": first_colour, "hair_detail": 0.5})
		var second := RLHeadLibrary.face_material(shared, {"hair_color": second_colour, "hair_detail": 0.5})
		check(RLHeadLibrary.shader_values(first).has("hair_color"), "Material-value shader copy lost pigment ownership")
		check(RLHeadLibrary.shader_values(second).has("hair_detail"), "Material-value shader copy lost grooming ownership")
		check(first.get_shader_parameter("hair_color") == first_colour, "First actor lost its pigment")
		check(second.get_shader_parameter("hair_color") == second_colour, "Second actor lost its pigment")
		check(first != second, "Different actor pigments shared one material")
	RLHeadLibrary.clear()
	RLHeadLibrary.reload_values_switch()
	print("RL shader value ownership: %d failures" % failures.size())
	quit(0 if failures.is_empty() else 1)
