extends SceneTree
## Material-local metadata can disable UV strand highlights. No asset installed.
const Library := preload("res://src/actors/rl_head/rl_head_library.gd")
const Quality := ActorRenderQuality.Quality
var checks := 0
var failures := 0

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(message)

func _initialize() -> void:
	for mode: int in [0, 1]:
		Library.clear()
		Library._values_switch = mode
		for flag: String in ["absent", "true", "false"]:
			var style := "fixture_highlights_" + flag
			var materials: Array = []
			for name: String in ["rl_hair_clump", "rl_hair_card", "rl_beard"]:
				var extras := {"texture": "hair_clump.png"}
				if flag != "absent":
					extras["uvStrandHighlights"] = flag == "true"
				materials.append({"name": name, "extras": extras})
			# In-memory glTF headers exercise the real metadata/material path.
			Library._documents[Library.hair_path(style)] = {"materials": materials}
			Library._documents[Library.beard_path(style)] = {"materials": materials}
			for name: String in ["rl_hair_clump", "rl_hair_card", "rl_beard"]:
				for quality: int in [Quality.LOW, Quality.MEDIUM, Quality.HIGH]:
					var material := Library.material(name, "female", style, quality)
					check(bool(material.get_shader_parameter("anisotropic")) == (quality != Quality.LOW and flag != "false"),
						"%s %s quality%d mode%d highlight policy" % [name, flag, quality, mode])
		var mixed := "fixture_highlights_mixed"
		Library._documents[Library.hair_path(mixed)] = {"materials": [
			{"name": "rl_hair_clump", "extras": {"texture": "hair_clump.png", "uvStrandHighlights": false}},
			{"name": "rl_hair_card", "extras": {"texture": "hair_clump.png"}},
		]}
		check(not bool(Library.material("rl_hair_clump", "female", mixed, Quality.HIGH).get_shader_parameter("anisotropic"))
			and bool(Library.material("rl_hair_card", "female", mixed, Quality.HIGH).get_shader_parameter("anisotropic")),
			"Opt-out affects only the material that declares it")
		check_soft_roots(mode)
		for pair: Array in [["male", "rowan_shag"], ["female", "mira_bun"], ["male", "rounded_afro"],
				["female", "cornrows_low_knot"], ["female", "shoulder_waves"], ["female", "curly_twin_buns"], ["male", "receding_sweep"]]:
			check(bool(Library.material("rl_hair_clump", pair[0], pair[1], Quality.HIGH).get_shader_parameter("anisotropic")),
				"Existing hairstyle retains highlights: " + str(pair[1]))
		for beard: String in ["full_beard", "short_beard", "goatee", "moustache"]:
			check(bool(Library.material("rl_beard", "male", beard, Quality.HIGH).get_shader_parameter("anisotropic")),
				"Existing beard retains highlights: " + beard)
	Library.clear()
	Library._values_switch = -1
	print("RL hair strand highlights: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func check_soft_roots(mode: int) -> void:
	for reference: bool in [false, true]:
		for enabled: bool in [false, true]:
			var style := "fixture_roots_%s_%s" % [reference, enabled]
			Library._documents[Library.hair_path(style)] = {"materials": [{
				"name": "rl_hair_clump", "extras": {"texture": "hair_clump.png",
				"softHairline": true, "referenceSurface": reference, "softRootCoverage": enabled}}]}
			var material := Library.material("rl_hair_clump", "female", style, Quality.HIGH)
			check(material.shader.code.begins_with("#define RL_SOFT_ROOTS\n") == enabled,
				"explicit clump opt-in selects alpha-to-coverage mode%d" % mode)
			check(bool(material.get_shader_parameter("soft_root_coverage")) == enabled,
				"clump coverage capability reaches the shader")
			check(bool(material.get_shader_parameter("soft_hairline")) == (not reference or enabled),
				"reference shading preserves its old rule without explicit opt-in")
			check(Library.shader_values(material).has("eye_color"),
				"soft shader variants retain the age/grey carrier in both value modes")
	var curly := Library.material("rl_hair_clump", "female", "curly_twin_buns", Quality.HIGH)
	check(curly.shader.code.begins_with("#define RL_SOFT_ROOTS\n"), "existing curly hair keeps its soft-root shader")
	check(not bool(curly.get_shader_parameter("soft_root_coverage")), "existing curly asset does not acquire new colour semantics")
