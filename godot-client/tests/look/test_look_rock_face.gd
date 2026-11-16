extends SceneTree
## Guards the painted ground's steep-face rock layer (LookProfile.ROCK_FACE_*,
## painted_ground_surface.gdshaderinc).
##
## The constants: the texture is a registered class texture that loads, the
## threshold begins on gentler ground than it is whole and stays clear of level
## ground even with its wobble, and LOW quality gives it up. The selection:
## only opaque terrain and base ground take it; a blended patch or a walk deck
## never does; a region's `ground.rock_face` 0 switches it off
## (look_rock_metres 0). The quality: one global shader value
## (LookGround.ROCK_FACE_GLOBAL, declared in project.godot) is its switch, 0 at
## LOW, multiplied into every material's repeat as it draws, so a material
## keeps its repeat whatever the quality it was painted at. A root painted on
## a worker at one quality and installed after a change follows the new one,
## and so does terrain composited with a portable road (RoadGround.rebind,
## which keeps the marker too). The shader: level ground takes no rock sample
## (the weight is exactly 0 there), the biome blend's look_paint is
## look_paint_rock without rock, and every road composite variant still parses
## with the global declared once.

const RoadGround := preload("res://src/world/road_ground/road_ground.gd")
const Composite := preload("res://src/world/road_ground/material.gd")
const RoadData := preload("res://src/world/road_ground/field_data.gd")

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	LookProfile.set_player_mode(LookProfile.Mode.FULL_PAINTED)
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	LookGround.apply_quality()
	_check_constants()
	_check_global()
	_check_selection()
	_check_quality()
	await _check_installed_after_change()
	_check_road_composite()
	_check_road_rebind()
	_check_flat_ground()
	_check_region_switch()
	_check_shader_text()
	LookProfile.set_player_quality(LookProfile.QUALITY_DEFAULT)
	LookGround.apply_quality()
	if failures == 0:
		print("test_look_rock_face: ok")
	quit(1 if failures > 0 else 0)

func _metres() -> float:
	return float(LookProfile.CLASS_TEXTURES[LookProfile.ROCK_FACE_TEXTURE]["metres"])

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

## The quality's switch is a float global the project declares (a shader that
## names an undeclared global fails to compile in the real renderers, which
## the headless one does not check), on by default, and apply_quality gives it
## each quality's value.
func _check_global() -> void:
	var name := str(LookGround.ROCK_FACE_GLOBAL)
	var setting: Variant = ProjectSettings.get_setting("shader_globals/" + name)
	_expect(setting is Dictionary and str((setting as Dictionary).get("type", "")) == "float"
		and float((setting as Dictionary).get("value", 0.0)) == 1.0,
		"project.godot declares %s as a float global, 1 by default" % name)
	_expect(LookGround.ROCK_FACE_GLOBAL in RenderingServer.global_shader_parameter_get_list()
		and RenderingServer.global_shader_parameter_get_type(LookGround.ROCK_FACE_GLOBAL)
			== RenderingServer.GLOBAL_VAR_TYPE_FLOAT,
		"the renderer knows the rock face's global")
	for level: int in [LookProfile.Quality.LOW, LookProfile.Quality.MEDIUM, LookProfile.Quality.HIGH]:
		LookProfile.set_player_quality(level)
		var wanted := 0.0 if level == LookProfile.Quality.LOW else 1.0
		_expect(LookGround.apply_quality() == wanted and LookGround.rock_face_switch() == wanted,
			"%s gives the global %.0f" % [LookProfile.quality_name(level), wanted])
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	LookGround.apply_quality()

func _standard(transparency: int, cull: int = BaseMaterial3D.CULL_BACK) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.transparency = transparency
	material.cull_mode = cull
	material.albedo_color = Color(0.6, 0.55, 0.45)
	material.vertex_color_use_as_albedo = true
	return material

func _road_style() -> StandardMaterial3D:
	var style := StandardMaterial3D.new()
	style.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
	style.albedo_color = Color(0.45, 0.36, 0.25, 0.9)
	style.vertex_color_use_as_albedo = true
	return style

func _rock_metres(painted: Material) -> float:
	var shader := painted as ShaderMaterial
	if shader == null:
		return -1.0
	var value: Variant = shader.get_shader_parameter(&"look_rock_metres")
	return float(value) if value != null else 0.0

func _check_selection() -> void:
	var metres := _metres()
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
	_expect(deck != null and _rock_metres(deck) == 0.0 and LookGround.rock_face_drawn(deck) == 0.0,
		"a walk deck never takes the rock face")

## A material keeps its repeat whatever the quality it was painted at; the
## global decides whether it draws.
func _check_quality() -> void:
	var metres := _metres()
	LookProfile.set_player_quality(LookProfile.Quality.LOW)
	LookGround.apply_quality()
	var low := LookGround.painted_source_for(_standard(BaseMaterial3D.TRANSPARENCY_DISABLED),
		LookGround.Kind.TERRAIN, true, "landfall")
	_expect(is_equal_approx(_rock_metres(low), metres) and LookGround.rock_face_drawn(low) == 0.0,
		"terrain painted at LOW keeps its repeat and draws no rock face")
	LookProfile.set_player_quality(LookProfile.Quality.MEDIUM)
	LookGround.apply_quality()
	_expect(is_equal_approx(LookGround.rock_face_drawn(low), metres)
		and is_equal_approx(_rock_metres(low), metres),
		"raising the quality draws the rock face on terrain painted at LOW, without touching it")
	LookProfile.set_player_quality(LookProfile.Quality.LOW)
	LookGround.apply_quality()
	_expect(LookGround.rock_face_drawn(low) == 0.0, "lowering it to LOW switches the rock face off again")
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	OS.set_environment(LookProfile.QUALITY_TRIM_VARIABLE, "rock_face=0")
	_expect(LookGround.rock_face_switch() == 0.0 and LookGround.rock_face_metres("landfall") == metres,
		"ELORIA_LOOK_QUALITY_TRIM rock_face=0 takes it off for a measurement through the switch")
	OS.unset_environment(LookProfile.QUALITY_TRIM_VARIABLE)
	_expect(LookGround.rock_face_switch() == 1.0 and LookGround.apply_quality() == 1.0,
		"HIGH draws it")

func _terrain_root(label: String) -> Node3D:
	var root := Node3D.new()
	root.name = "rock_root_" + label
	var terrain := MeshInstance3D.new()
	terrain.name = "Terrain_rock_" + label
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, BoxMesh.new().get_mesh_arrays())
	mesh.surface_set_material(0, _standard(BaseMaterial3D.TRANSPARENCY_DISABLED))
	terrain.mesh = mesh
	root.add_child(terrain)
	return root

func _paint_on_worker(root: Node) -> int:
	return LookGround.paint(root, "landfall")

## The race the quality hook used to lose: a loader worker paints a chunk at
## one quality, the player changes it before main installs the chunk (main
## applies the change to the roots it has), and the chunk arrives afterwards.
## Nothing visits it, and it draws at the new quality all the same.
func _check_installed_after_change() -> void:
	var metres := _metres()
	for change: Array in [[LookProfile.Quality.LOW, LookProfile.Quality.HIGH],
			[LookProfile.Quality.HIGH, LookProfile.Quality.LOW],
			[LookProfile.Quality.MEDIUM, LookProfile.Quality.LOW]]:
		var before: int = change[0]
		var after: int = change[1]
		LookProfile.set_player_quality(before)
		LookGround.apply_quality()
		var root := _terrain_root(LookProfile.quality_name(before))
		var thread := Thread.new()
		_expect(thread.start(_paint_on_worker.bind(root)) == OK, "the paint worker starts")
		while thread.is_alive():
			await process_frame
		var surfaces := int(thread.wait_to_finish())
		var painted := (root.get_child(0) as MeshInstance3D).get_surface_override_material(0)
		LookProfile.set_player_quality(after)
		LookGround.apply_quality()
		get_root().add_child(root)
		var wanted := 0.0 if after == LookProfile.Quality.LOW else metres
		_expect(surfaces == 1 and painted is ShaderMaterial and painted.has_meta(LookGround.ROCK_META)
			and is_equal_approx(_rock_metres(painted), metres)
			and is_equal_approx(LookGround.rock_face_drawn(painted), wanted),
			"terrain painted on a worker at %s and installed after a change to %s draws %.1f m rock"
				% [LookProfile.quality_name(before), LookProfile.quality_name(after), wanted])
		root.free()
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	LookGround.apply_quality()

func _sources() -> Dictionary:
	return {"surface": FileAccess.get_file_as_string(Composite.SURFACE),
		"paint": FileAccess.get_file_as_string(Composite.PAINT)}

func _uniform_names(shader: Shader) -> Array[String]:
	var names: Array[String] = []
	if shader != null:
		for uniform: Dictionary in shader.get_shader_uniform_list():
			names.append(str(uniform["name"]))
	return names

## Terrain composited with a portable road (Composite.build) carries the base
## half's repeat, reads the same global as it draws and so follows the quality;
## the road half never takes rock. The look-off (RG_ORIGINAL_BASE) and biome
## composites parse with the global's declaration copied into their road half.
func _check_road_composite() -> void:
	var metres := _metres()
	var sources := _sources()
	var style := _road_style()
	var styles: Array[BaseMaterial3D] = [style]
	var base := LookGround.painted_source_for(_standard(BaseMaterial3D.TRANSPARENCY_DISABLED,
		BaseMaterial3D.CULL_DISABLED), LookGround.Kind.PATCH, true, "landfall") as ShaderMaterial
	var road := LookGround.painted_source_for(style, LookGround.Kind.DECK, true, "landfall") as ShaderMaterial
	var made: Dictionary = Composite.build(base, road, styles, true, {}, sources)
	_expect(bool(made.get("ok", false)), "a painted base patch composes with a road: %s"
		% str(made.get("error", "")))
	if not bool(made.get("ok", false)):
		return
	var composite := made.material as ShaderMaterial
	var names := _uniform_names(composite.shader)
	_expect("look_rock_metres" in names and "road_look_rock_metres" in names,
		"the composed road ground shader parses with the rock layer in both halves")
	_expect(is_equal_approx(_rock_metres(composite), metres)
		and composite.get_shader_parameter(&"look_rock_texture") != null,
		"the composite keeps the base half's rock repeat and texture")
	var road_metres: Variant = composite.get_shader_parameter(&"road_look_rock_metres")
	_expect(road_metres == null or float(road_metres) == 0.0, "the road half never takes the rock face")
	_expect(composite.shader.code.contains("return road_look_rock_metres * rl_rock_face;"),
		"the road half's copy reads the same global")
	LookProfile.set_player_quality(LookProfile.Quality.LOW)
	LookGround.apply_quality()
	var at_low := LookGround.rock_face_drawn(composite)
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	LookGround.apply_quality()
	_expect(at_low == 0.0 and is_equal_approx(LookGround.rock_face_drawn(composite), metres),
		"road-composited terrain follows the quality (LOW %.1f m, HIGH %.1f m)"
			% [at_low, LookGround.rock_face_drawn(composite)])
	# Look off: the original base (RG_ORIGINAL_BASE) and a PBR road.
	var target := MeshInstance3D.new()
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, PlaneMesh.new().get_mesh_arrays())
	target.mesh = mesh
	var raw_base: ShaderMaterial = RoadGround._raw_base(_standard(BaseMaterial3D.TRANSPARENCY_DISABLED),
		target, 0, "landfall")
	var raw: Dictionary = Composite.build(raw_base, RoadGround._pbr_adapter(style, true), styles, false,
		{}, sources)
	_expect(bool(raw.get("ok", false)) and not _uniform_names((raw.material as ShaderMaterial).shader).is_empty(),
		"the look-off road composite still parses")
	target.free()
	# The biome blend's painted base.
	var biome := ShaderMaterial.new()
	biome.shader = load(LookGround.BIOME_SHADER_PATH) as Shader
	var painted_biome := LookGround.painted_source_for(biome, LookGround.Kind.BIOME, false, "landfall") \
		as ShaderMaterial
	if painted_biome != null:
		var blended: Dictionary = Composite.build(painted_biome, road, styles, true, {}, sources)
		_expect(bool(blended.get("ok", false))
			and not _uniform_names((blended.material as ShaderMaterial).shader).is_empty(),
			"the biome base road composite still parses")

## RoadGround.rebind on a chunk whose base ground takes the rock face: the
## composite it installs keeps ROCK_META and follows the quality.
func _check_road_rebind() -> void:
	var metres := _metres()
	var style := _road_style()
	var data: Resource = RoadData.new()
	data.document = {"targets": [{"name": "AuthoredGround_rockBase"}],
		"source_frame_node": "AuthoredGround_rockBase",
		"source_frame_matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
		"removed_road_node_names": []}
	var styles: Array[BaseMaterial3D] = [style]
	data.styles = styles
	data.shader_sources = _sources()
	data.coverage = Image.create(2, 2, false, Image.FORMAT_L8)
	data.ids = Image.create(2, 2, false, Image.FORMAT_RGB8)
	data.coefficients = Image.create(2, 2, false, Image.FORMAT_RGBAF)
	data.records_per_row = 1
	data.extent = Vector2(4.0, 4.0)
	var root := Node3D.new()
	root.name = "rock_road_root"
	var target := MeshInstance3D.new()
	target.name = "AuthoredGround_rockBase"
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, PlaneMesh.new().get_mesh_arrays())
	mesh.surface_set_material(0, _standard(BaseMaterial3D.TRANSPARENCY_DISABLED, BaseMaterial3D.CULL_DISABLED))
	target.mesh = mesh
	root.add_child(target)
	get_root().add_child(root)
	root.set_meta(RoadGround.META, {"data": data})
	var manifest := WorldManifest.new()
	manifest.data = {"continentGeography": {"region": "landfall"},
		"asset": {"id": "landfall__chunk_07_09"}}
	var bound: Dictionary = RoadGround.rebind(root, manifest)
	var composite := target.get_active_material(0) as ShaderMaterial
	_expect(bool(bound.get("ok", false)) and composite != null
		and composite.has_meta(RoadGround.MATERIAL_META)
		and str(composite.get_meta(LookGround.ROCK_META, "")) == "landfall"
		and is_equal_approx(_rock_metres(composite), metres),
		"a road composite of rock-face base ground keeps the marker and repeat: %s"
			% str(bound.get("error", "")))
	if composite != null:
		LookProfile.set_player_quality(LookProfile.Quality.LOW)
		LookGround.apply_quality()
		var at_low := LookGround.rock_face_drawn(composite)
		LookProfile.set_player_quality(LookProfile.Quality.MEDIUM)
		LookGround.apply_quality()
		_expect(at_low == 0.0 and is_equal_approx(LookGround.rock_face_drawn(composite), metres),
			"a bound road chunk's base ground follows the quality")
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	LookGround.apply_quality()
	root.free()

## The shader's weight (look_rock_weight) as GDScript: level ground and banks
## up to 35 degrees take none of the rock with the noise at either extreme and
## the switch on, so look_rock_layer returns their texel untouched and samples
## nothing; with the switch off nothing does.
func _check_flat_ground() -> void:
	var up := LookProfile.ROCK_FACE_UP
	var wobble := LookProfile.ROCK_FACE_WOBBLE
	var worst := 0.0
	for degrees: float in [0.0, 10.0, 20.0, 35.0]:
		for noise: float in [0.0, 0.5, 0.9999]:
			var normal_up := cos(deg_to_rad(degrees))
			var shifted := normal_up + (noise - 0.5) * 2.0 * wobble.x
			worst = maxf(worst, 1.0 - smoothstep(up.y, up.x, shifted))
	_expect(worst == 0.0, "level ground and banks to 35 degrees take no rock (worst weight %.4f)" % worst)
	var cliff := 1.0 - smoothstep(up.y, up.x, cos(deg_to_rad(60.0)) + wobble.x)
	_expect(cliff == 1.0, "a 60 degree cliff is wholly rock face whatever the noise")

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
	# The quality's switch: declared once, behind the guard road_ground's copy
	# of this include needs, and read wherever the repeat is.
	var guard_at := paint.find("#ifndef RL_ROCK_FACE_GLOBAL\n#define RL_ROCK_FACE_GLOBAL\n"
		+ "global uniform float rl_rock_face;\n#endif")
	_expect(guard_at >= 0 and paint.count("global uniform float rl_rock_face;") == 1,
		"the rock face's global is declared once, behind its guard")
	_expect(paint.contains("float look_rock_repeat() {\n\treturn look_rock_metres * rl_rock_face;\n}"),
		"the repeat as drawn is the material's times the global")
	var code := PackedStringArray()
	for line: String in paint.split("\n"):
		code.append(line.get_slice("//", 0))
	var bare := "\n".join(code)
	_expect(bare.count("look_rock_metres") == 2 and bare.count("look_rock_repeat()") == 3,
		"look_rock_metres is read only through look_rock_repeat, which both rock functions call")
	_expect(surface.contains("look_paint_rock(albedo, reference, vertex_colour, look_ground_xz, world_normal,"),
		"painted ground hands the rock weight to the paint")
	# road_ground/material.gd copies the surface's fragment body into its road
	# evaluation with look_* names prefixed: what it composes must still parse.
	var header := FileAccess.get_file_as_string("res://src/world/look/painted_ground.gdshader")
	var composed: Dictionary = Composite._compose_code(header, surface, paint, true)
	_expect(bool(composed.get("ok", false)), "the road compositor still finds its anchors")
	if bool(composed.get("ok", false)):
		var road_shader := Shader.new()
		road_shader.code = str(composed["code"])
		var road_names := _uniform_names(road_shader)
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
		var names := _uniform_names(load(path) as Shader)
		_expect("look_rock_metres" in names and "look_rock_texture" in names
			and "look_rock_grain" in names, "%s declares the rock layer" % path.get_file())

func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures += 1
	push_error("test_look_rock_face: " + message)
	print("FAIL: " + message)
