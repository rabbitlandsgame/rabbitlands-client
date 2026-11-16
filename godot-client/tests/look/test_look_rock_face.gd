extends SceneTree
## Guards the painted ground's steep-face rock layer (LookProfile.ROCK_FACE_*,
## painted_ground_surface.gdshaderinc).
##
## The constants: the texture is a registered class texture that loads, the
## threshold begins on gentler ground than it is whole and stays clear of level
## ground even with its wobble, and LOW quality gives it up. The selection:
## only opaque terrain and base ground take it; a blended patch or a walk deck
## never does; a region's `ground.rock_face` 0 and LOW quality switch it off
## (look_rock_metres 0), and a change of quality switches it on painted roots
## (LookGround.apply_quality). The shader: level ground takes no rock sample
## (the weight is exactly 0 there), and the biome blend's look_paint is
## look_paint_rock without rock.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	LookProfile.set_player_mode(LookProfile.Mode.FULL_PAINTED)
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	_check_constants()
	_check_selection()
	_check_quality()
	_check_region_switch()
	_check_shader_text()
	LookProfile.set_player_quality(LookProfile.QUALITY_DEFAULT)
	if failures == 0:
		print("test_look_rock_face: ok")
	quit(1 if failures > 0 else 0)

func _check_constants() -> void:
	var entry: Variant = LookProfile.CLASS_TEXTURES.get(LookProfile.ROCK_FACE_TEXTURE)
	_expect(entry is Dictionary and ResourceLoader.exists(str((entry as Dictionary)["path"])),
		"the rock face is a registered class texture whose file exists")
	_expect(LookGround.class_texture(LookProfile.ROCK_FACE_TEXTURE) != null,
		"the rock face texture loads")
	var metres := float((entry as Dictionary)["metres"]) if entry is Dictionary else 0.0
	_expect(metres >= 4.0 and metres <= 16.0, "the rock face repeats every 4-16 m (%.1f)" % metres)
	var up := LookProfile.ROCK_FACE_UP
	var wobble := LookProfile.ROCK_FACE_WOBBLE
	_expect(up.x > up.y, "the rock begins on gentler ground (up %.2f) than it is whole (%.2f)"
		% [up.x, up.y])
	# Grade 1.2 (about 50 degrees) is where the planar texture streaks.
	var fifty := cos(atan(1.2))
	_expect(up.y < fifty and up.x > fifty, "a grade of 1.2 (up %.3f) lies inside the ramp" % fifty)
	# Level ground and gentle banks (up to about 35 degrees) never reach it,
	# whatever the noise does.
	_expect(up.x + wobble.x < cos(deg_to_rad(35.0)),
		"a 35 degree bank stays clear of the rock with the wobble (%.3f)" % (up.x + wobble.x))
	_expect(wobble.x >= 0.0 and wobble.y > 0.0, "the wobble is a size and a positive amplitude")
	_expect(LookProfile.ROCK_FACE_HUE >= 0.0 and LookProfile.ROCK_FACE_HUE <= 1.0
		and LookProfile.ROCK_FACE_VALUE > 0.0 and LookProfile.ROCK_FACE_GRAIN >= 0.0,
		"the hue share, value and grain are in range")
	_expect(not bool(LookProfile.QUALITY_PRESETS[LookProfile.Quality.LOW]["rock_face"])
		and bool(LookProfile.QUALITY_PRESETS[LookProfile.Quality.MEDIUM]["rock_face"])
		and bool(LookProfile.QUALITY_PRESETS[LookProfile.Quality.HIGH]["rock_face"]),
		"LOW gives the rock face up, MEDIUM and HIGH draw it")
	_expect("rock_face" in LookProfile.REGION_SECTIONS["ground"],
		"a region may switch the rock face off (ground.rock_face)")

func _standard(transparency: int, cull: int = BaseMaterial3D.CULL_BACK) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.transparency = transparency
	material.cull_mode = cull
	material.albedo_color = Color(0.6, 0.55, 0.45)
	material.vertex_color_use_as_albedo = true
	return material

func _rock_metres(painted: Material) -> float:
	var shader := painted as ShaderMaterial
	if shader == null:
		return -1.0
	var value: Variant = shader.get_shader_parameter(&"look_rock_metres")
	return float(value) if value != null else 0.0

func _check_selection() -> void:
	var metres := float(LookProfile.CLASS_TEXTURES[LookProfile.ROCK_FACE_TEXTURE]["metres"])
	_expect(LookGround.takes_rock_face(LookGround.Kind.TERRAIN, false)
		and LookGround.takes_rock_face(LookGround.Kind.PATCH, false)
		and not LookGround.takes_rock_face(LookGround.Kind.PATCH, true)
		and not LookGround.takes_rock_face(LookGround.Kind.DECK, false)
		and not LookGround.takes_rock_face(LookGround.Kind.DECK, true)
		and not LookGround.takes_rock_face(LookGround.Kind.TERRAIN, true),
		"only opaque terrain and base ground take the rock face")
	var terrain := LookGround.painted_source_for(_standard(BaseMaterial3D.TRANSPARENCY_DISABLED),
		LookGround.Kind.TERRAIN, true, "landfall")
	_expect(is_equal_approx(_rock_metres(terrain), metres)
		and (terrain as ShaderMaterial).get_shader_parameter(&"look_rock_texture") != null
		and (terrain as ShaderMaterial).has_meta(LookGround.ROCK_META),
		"opaque terrain takes the rock face at its repeat")
	var base := LookGround.painted_source_for(_standard(BaseMaterial3D.TRANSPARENCY_DISABLED,
		BaseMaterial3D.CULL_DISABLED), LookGround.Kind.PATCH, true, "landfall")
	_expect(is_equal_approx(_rock_metres(base), metres),
		"a two-sided opaque base patch takes the rock face")
	var overlay := LookGround.painted_source_for(_standard(
		BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS), LookGround.Kind.PATCH, true, "landfall")
	_expect(overlay != null and _rock_metres(overlay) == 0.0
		and not (overlay as ShaderMaterial).has_meta(LookGround.ROCK_META),
		"a blended patch keeps its own texture on a slope")
	var deck := LookGround.painted_source_for(_standard(
		BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS), LookGround.Kind.DECK, true, "landfall")
	_expect(deck != null and _rock_metres(deck) == 0.0, "a walk deck never takes the rock face")

func _check_quality() -> void:
	var metres := float(LookProfile.CLASS_TEXTURES[LookProfile.ROCK_FACE_TEXTURE]["metres"])
	LookProfile.set_player_quality(LookProfile.Quality.LOW)
	var low := LookGround.painted_source_for(_standard(BaseMaterial3D.TRANSPARENCY_DISABLED),
		LookGround.Kind.TERRAIN, true, "landfall")
	_expect(_rock_metres(low) == 0.0, "terrain painted at LOW has no rock face")
	# A root painted at LOW gains it when the player raises the quality.
	var root := Node3D.new()
	var mesh_instance := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh_instance.mesh = mesh
	mesh_instance.set_surface_override_material(0, low)
	root.add_child(mesh_instance)
	LookProfile.set_player_quality(LookProfile.Quality.MEDIUM)
	_expect(LookGround.apply_quality(root) == 1 and is_equal_approx(_rock_metres(low), metres),
		"raising the quality switches the rock face on a painted root")
	_expect(LookGround.apply_quality(root) == 0, "applying the same quality again changes nothing")
	LookProfile.set_player_quality(LookProfile.Quality.LOW)
	_expect(LookGround.apply_quality(root) == 1 and _rock_metres(low) == 0.0,
		"lowering it to LOW switches the rock face off again")
	root.free()
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	OS.set_environment(LookProfile.QUALITY_TRIM_VARIABLE, "rock_face=0")
	_expect(LookGround.rock_face_metres("landfall") == 0.0,
		"ELORIA_LOOK_QUALITY_TRIM rock_face=0 takes it off for a measurement")
	OS.unset_environment(LookProfile.QUALITY_TRIM_VARIABLE)
	_expect(LookGround.rock_face_metres("landfall") == metres, "HIGH draws it")

func _check_region_switch() -> void:
	var problems := PackedStringArray()
	var typed := LookProfile.typed_region({"id": "test_rock", "schema": 1,
		"ground": {"rock_face": 0}}, "test_rock", problems)
	_expect(problems.is_empty() and float((typed["ground"] as Dictionary)["rock_face"]) == 0.0,
		"ground.rock_face is a valid region number")

func _check_shader_text() -> void:
	var surface := FileAccess.get_file_as_string("res://src/world/look/painted_ground_surface.gdshaderinc")
	var paint := FileAccess.get_file_as_string("res://src/world/look/painted_ground_paint.gdshaderinc")
	# Level ground: the weight is 0 and no rock texture is sampled; the samples
	# come after `rock <= 0.0` returns and use textureGrad with gradients taken
	# before it.
	var layer_at := paint.find("vec4 look_rock_layer(")
	var early_at := paint.find("if (rock <= 0.0) {", layer_at)
	var gradient_at := paint.find("dFdx(p)", layer_at)
	var sample_at := paint.find("textureGrad(look_rock_texture", layer_at)
	_expect(layer_at >= 0 and gradient_at > layer_at and early_at > gradient_at
		and sample_at > early_at and not paint.contains("texture(look_rock_texture")
		and not surface.contains("look_rock_texture"),
		"rock samples are taken only where the face is steep, with explicit gradients")
	_expect(surface.contains("look_paint_rock(albedo, reference, vertex_colour, look_ground_xz, world_normal,"),
		"painted ground hands the rock weight to the paint")
	# road_ground/material.gd copies the surface's fragment body into its road
	# evaluation with look_* names prefixed: what it composes must still parse.
	var header := FileAccess.get_file_as_string("res://src/world/look/painted_ground.gdshader")
	var RoadMaterial: GDScript = load("res://src/world/road_ground/material.gd")
	var composed: Dictionary = RoadMaterial.call("_compose_code", header, surface, paint, true)
	_expect(bool(composed.get("ok", false)), "the road compositor still finds its anchors")
	if bool(composed.get("ok", false)):
		var road_shader := Shader.new()
		road_shader.code = str(composed["code"])
		var road_names: Array[String] = []
		for uniform: Dictionary in road_shader.get_shader_uniform_list():
			road_names.append(str(uniform["name"]))
		_expect("look_rock_metres" in road_names and "road_look_rock_metres" in road_names,
			"the composed road ground shader parses with the rock layer in both halves")
	_expect(paint.contains("return look_paint_rock(albedo, reference, vertex_colour, xz, world_normal, 0.0);"),
		"look_paint (the biome blend's splice) is look_paint_rock without rock")
	_expect(paint.contains("rock > 0.0 ? mix(look_verge_grain_steep, look_rock_grain, rock)\n\t\t: look_verge_grain_steep"),
		"without rock the steep grain is the region's verge_grain_steep exactly")
	# Both painted ground shaders compile with the layer in (a shader that fails
	# to compile has no uniforms to list).
	for path: String in ["res://src/world/look/painted_ground.gdshader",
			"res://src/world/look/painted_ground_two_sided.gdshader",
			"res://src/world/look/painted_ground_overlay.gdshader",
			"res://src/world/look/painted_ground_deck.gdshader"]:
		var shader := load(path) as Shader
		var names: Array[String] = []
		if shader != null:
			for uniform: Dictionary in shader.get_shader_uniform_list():
				names.append(str(uniform["name"]))
		_expect("look_rock_metres" in names and "look_rock_texture" in names
			and "look_rock_grain" in names, "%s declares the rock layer" % path.get_file())

func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures += 1
	push_error("test_look_rock_face: " + message)
	print("FAIL: " + message)
