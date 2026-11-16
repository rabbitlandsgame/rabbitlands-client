extends SceneTree
## Guards the map polish pass's three runtime look changes (2026-11-16).
##
## The water's edge (LookProfile.WATER_SHORE_*): the continent sea's look copy
## is drawn by the soft-edged shader at MEDIUM and HIGH, keeping every
## parameter the loader and the decode gave it, and stays the opaque shader at
## LOW and in the compatibility renderer; the quality's switch is a declared
## global; the opaque shader the loader puts in never reads depth.
##
## The cliff's tone: the steep-face rock is drawn as stone (look_rock_tone, here
## as GDScript): on green ground it is not green, on tan ground it keeps a
## modest warmth, and the paint gives it no grass trims.
##
## The forest floor: the moss patches are told apart from other glazes and
## cut at FOREST_FLOOR_RIM, and the cut (the shader's coverage, here as
## GDScript) draws them as dapples, neither the near-nothing PATCH_RIM left nor
## a flat solid disc.

const RendererFamily := preload("res://src/runtime/renderer_family.gd")

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	LookProfile.set_player_mode(LookProfile.Mode.FULL_PAINTED)
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	LookGround.apply_quality()
	_check_shore_constants()
	_check_shore_global()
	_check_shore_decode()
	_check_shore_shaders()
	_check_rock_tone()
	_check_rock_shader_text()
	_check_forest_floor_selection()
	_check_forest_floor_dapples()
	_check_forest_floor_steep()
	LookProfile.set_player_quality(LookProfile.QUALITY_DEFAULT)
	LookGround.apply_quality()
	if failures == 0:
		print("test_look_shore_cliff_floor: ok")
	quit(1 if failures > 0 else 0)

# --- The water's edge --------------------------------------------------------

func _check_shore_constants() -> void:
	var depth := LookProfile.WATER_SHORE_DEPTH
	var wobble := LookProfile.WATER_SHORE_WOBBLE
	var foam := LookProfile.WATER_SHORE_FOAM
	_expect(depth.x > depth.y and depth.y >= 0.0 and depth.x >= 0.4 and depth.x <= 2.0,
		"the water fades in over 0.4-2 m of depth from the waterline (%s)" % str(depth))
	_expect(wobble.x > 0.0 and wobble.x < depth.x * 0.5 and wobble.y > 0.5,
		"the depth wobble is smaller than half the fade (%s)" % str(wobble))
	_expect(foam.x > 0.0 and foam.x < depth.x and foam.y > 0.0 and foam.y <= 0.6 and foam.z > 0.0,
		"the foam is a band inside the fade and never solid (%s)" % str(foam))
	_expect(not bool(LookProfile.QUALITY_PRESETS[LookProfile.Quality.LOW]["water_shore"])
		and bool(LookProfile.QUALITY_PRESETS[LookProfile.Quality.MEDIUM]["water_shore"])
		and bool(LookProfile.QUALITY_PRESETS[LookProfile.Quality.HIGH]["water_shore"]),
		"LOW gives the soft water edge up, MEDIUM and HIGH draw it")

func _check_shore_global() -> void:
	var name := str(LookGround.WATER_SHORE_GLOBAL)
	var setting: Variant = ProjectSettings.get_setting("shader_globals/" + name)
	_expect(setting is Dictionary and str((setting as Dictionary).get("type", "")) == "float"
		and float((setting as Dictionary).get("value", 0.0)) == 1.0,
		"project.godot declares %s as a float global, 1 by default" % name)
	for level: int in [LookProfile.Quality.LOW, LookProfile.Quality.MEDIUM, LookProfile.Quality.HIGH]:
		LookProfile.set_player_quality(level)
		LookGround.apply_quality()
		var wanted := 0.0 if level == LookProfile.Quality.LOW else 1.0
		_expect(LookGround.water_shore_switch() == wanted
			and LookGround.WATER_SHORE_GLOBAL in RenderingServer.global_shader_parameter_get_list(),
			"%s gives the water's global %.0f" % [LookProfile.quality_name(level), wanted])
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	LookGround.apply_quality()

func _sea_root(sea: ShaderMaterial) -> Array:
	var world := Node3D.new()
	root.add_child(world)
	var mesh := MeshInstance3D.new()
	mesh.name = "Water_test_4_6"
	mesh.mesh = BoxMesh.new()
	world.add_child(mesh)
	mesh.set_surface_override_material(0, sea)
	return [world, mesh]

func _check_shore_decode() -> void:
	var sea := ShaderMaterial.new()
	sea.shader = load(LookGround.CONTINENT_WATER_PATH) as Shader
	var frame := Transform3D(Basis.IDENTITY, Vector3(1200.0, 0.0, 7000.0))
	sea.set_shader_parameter(&"water_to_continent", Projection(frame))
	sea.set_shader_parameter(&"has_wave_texture", true)
	sea.set_shader_parameter(&"flow_strength", 0.5)
	for method: String in [RendererFamily.FORWARD_PLUS, RendererFamily.MOBILE,
			RendererFamily.COMPATIBILITY]:
		RendererFamily.override_for_tests(method)
		for level: int in [LookProfile.Quality.LOW, LookProfile.Quality.HIGH]:
			LookProfile.set_player_quality(level)
			var made := _sea_root(sea)
			var world := made[0] as Node3D
			var mesh := made[1] as MeshInstance3D
			var changed := LookGround.decode_continent_sea(world)
			var drawn := mesh.get_surface_override_material(0) as ShaderMaterial
			var label := "%s %s" % [method, LookProfile.quality_name(level)]
			if method == RendererFamily.COMPATIBILITY:
				_expect(changed == 0 and drawn == sea,
					"%s: the compatibility renderer keeps the loader's opaque sea" % label)
			elif level == LookProfile.Quality.LOW:
				_expect(changed == 1 and drawn != sea
					and drawn.shader.resource_path == LookGround.CONTINENT_WATER_PATH,
					"%s: the decoded sea stays opaque and reads no depth" % label)
			else:
				_expect(changed == 1 and drawn != sea and drawn.shader == LookGround.SHADER_WATER_SHORE,
					"%s: the decoded sea draws its soft edge" % label)
				_expect(drawn.get_shader_parameter(&"look_decode_albedo") == true
					and float(drawn.get_shader_parameter(&"look_sea_value")) == LookProfile.CONTINENT_SEA_VALUE
					and drawn.get_shader_parameter(&"has_wave_texture") == true
					and is_equal_approx(float(drawn.get_shader_parameter(&"flow_strength")), 0.5)
					and drawn.get_shader_parameter(&"water_to_continent") == Projection(frame),
					"%s: the soft-edged sea keeps the loader's and the decode's parameters" % label)
				_expect((drawn.get_shader_parameter(&"look_shore_depth") as Vector2)
						.is_equal_approx(LookProfile.WATER_SHORE_DEPTH)
					and (drawn.get_shader_parameter(&"look_shore_foam") as Vector3)
						.is_equal_approx(LookProfile.WATER_SHORE_FOAM),
					"%s: the soft-edged sea takes the shore constants" % label)
				_expect(sea.shader.resource_path == LookGround.CONTINENT_WATER_PATH
					and sea.get_shader_parameter(&"look_decode_albedo") != true,
					"%s: the loader's own sea material is never edited" % label)
			world.free()
	RendererFamily.override_for_tests("")
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)

func _check_shore_shaders() -> void:
	var opaque := load(LookGround.CONTINENT_WATER_PATH) as Shader
	var names := _uniform_names(opaque)
	_expect("water_to_continent" in names and "look_decode_albedo" in names
		and "look_shore_depth" not in names and "look_shore_depth_texture" not in names,
		"the loader's opaque sea compiles and reads no depth")
	var shore_names := _uniform_names(LookGround.SHADER_WATER_SHORE)
	_expect("water_to_continent" in shore_names and "look_decode_albedo" in shore_names
		and "look_shore_depth" in shore_names and "look_shore_foam" in shore_names,
		"the soft-edged sea compiles with the shore uniforms")
	var include := FileAccess.get_file_as_string("res://src/world/continent_water.gdshaderinc")
	var shore := FileAccess.get_file_as_string("res://src/world/look/continent_water_shore.gdshader")
	_expect(include.contains("hint_depth_texture") and include.find("hint_depth_texture")
			> include.find("#ifdef CONTINENT_WATER_SHORE")
		and include.contains("global uniform float rl_water_shore;")
		and include.contains("ALPHA = mix(1.0,"),
		"only the shore variant reads depth and writes alpha, behind the quality's global")
	_expect(include.contains("#if CURRENT_RENDERER == RENDERER_COMPATIBILITY"),
		"the depth is unprojected for the compatibility renderer's clip range too")
	_expect(shore.contains("depth_draw_always") and shore.contains("#define CONTINENT_WATER_SHORE"),
		"the soft-edged sea still writes depth (its place in the transparent pass: test_look_sea_order)")

# --- The cliff's tone ------------------------------------------------------------

func _luma(colour: Vector3) -> float:
	return colour.dot(Vector3(0.2126, 0.7152, 0.0722))

func _green(colour: Vector3) -> float:
	return smoothstep(0.02, 0.12, (colour.y - maxf(colour.x, colour.z)) / maxf(colour.y, 0.0001))

## look_rock_tone (painted_ground_paint.gdshaderinc) as GDScript.
func _rock_tone(ground: Vector3, face_mean: Vector3) -> Vector3:
	var luma := maxf(_luma(ground), 0.0001)
	var ground_hue := (ground / luma).lerp(Vector3.ONE, _green(ground))
	var own_hue := face_mean / maxf(_luma(face_mean), 0.0001)
	return ground_hue.lerp(own_hue, LookProfile.ROCK_FACE_HUE) * luma * LookProfile.ROCK_FACE_VALUE

func _check_rock_tone() -> void:
	var texture := LookGround.class_texture(LookProfile.ROCK_FACE_TEXTURE)
	var face_mean := Vector3(0.2, 0.2, 0.2)
	if texture != null:
		var image := texture.get_image()
		if image != null:
			if image.is_compressed():
				image.decompress()
			image = image.duplicate() as Image
			image.resize(1, 1, Image.INTERPOLATE_BILINEAR)
			var mean := image.get_pixel(0, 0).srgb_to_linear()
			face_mean = Vector3(maxf(mean.r, 0.02), maxf(mean.g, 0.02), maxf(mean.b, 0.02))
	# Coilmere's green verge (the biome grass under the warm key) and
	# Landfall's tan ground, linear.
	var green_ground := Vector3(0.15, 0.19, 0.02) * 0.6
	var tan_ground := Vector3(0.2, 0.15, 0.08)
	var on_green := _rock_tone(green_ground, face_mean)
	var on_tan := _rock_tone(tan_ground, face_mean)
	_expect(_green(on_green) == 0.0,
		"stone on green ground is not grass: green leads by %.3f" % (
			(on_green.y - maxf(on_green.x, on_green.z)) / maxf(on_green.y, 0.0001)))
	_expect(is_equal_approx(_luma(on_green), _luma(green_ground) * LookProfile.ROCK_FACE_VALUE)
		and is_equal_approx(_luma(on_tan), _luma(tan_ground) * LookProfile.ROCK_FACE_VALUE),
		"the stone keeps the ground's luminance, so the value hierarchy holds")
	var own_warmth := face_mean.x / face_mean.z
	_expect(on_tan.x / on_tan.z > own_warmth,
		"stone on tan ground keeps some of its warmth (r/b %.2f against the rock's own %.2f)"
			% [on_tan.x / on_tan.z, own_warmth])
	_expect(LookProfile.ROCK_FACE_HUE >= 0.6 and LookProfile.ROCK_FACE_HUE < 1.0,
		"the ground's hue is a modest share of the stone's (%.2f of its own)" % LookProfile.ROCK_FACE_HUE)

func _check_rock_shader_text() -> void:
	var paint := FileAccess.get_file_as_string("res://src/world/look/painted_ground_paint.gdshaderinc")
	var surface := FileAccess.get_file_as_string("res://src/world/look/painted_ground_surface.gdshaderinc")
	_expect(paint.contains("vec3 look_rock_tone(vec3 ground, vec3 face_mean) {")
		and paint.contains("vec4 look_rock_layer(vec3 albedo, inout vec3 reference,")
		and paint.find("float look_green(") < paint.find("vec3 look_rock_tone("),
		"the rock layer draws stone from the ground's colour after its tint and vertex colour")
	_expect(paint.contains("float verge_green = look_green(reference) * (1.0 - rock);")
		and paint.count("look_green(reference)") == 2,
		"the verge's grass trims skip the rock face")
	var vertex_at := surface.find("reference *= vertex_colour;")
	var layer_at := surface.find("look_rock_layer(albedo, reference, world_normal,")
	_expect(vertex_at > 0 and layer_at > vertex_at,
		"the rock is laid over the albedo after the vertex colour that would green it")

# --- The forest floor ---------------------------------------------------------

func _patch(material_name: String, tint: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.resource_name = material_name
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.albedo_color = tint
	material.vertex_color_use_as_albedo = true
	return material

func _check_forest_floor_selection() -> void:
	var moss := Color("858066")
	var floor := _patch("authored_landfall_forest-21", moss)
	var yard := _patch("authored_landfall_yard-03", moss)
	var litter := _patch("authored_amberwood_forest-litter", Color("f29e52"))
	var forest_meadow := _patch("authored_coilmere_th-forest2-clearing", Color("6f9a3c"))
	_expect(LookGround.is_forest_floor(floor) and LookGround.is_forest_floor(
			_patch("authored_coilmere_th-forest2-23", moss))
		and LookGround.is_forest_floor(_patch("authored_boarsend_gs-forest-01", moss)),
		"the continent's forest-floor moss patches are forest floor")
	_expect(not LookGround.is_forest_floor(yard) and not LookGround.is_forest_floor(litter)
		and not LookGround.is_forest_floor(forest_meadow),
		"a yard of the same tint, bright leaf litter and a green clearing are not")
	var opaque := floor.duplicate() as StandardMaterial3D
	opaque.transparency = BaseMaterial3D.TRANSPARENCY_DISABLED
	_expect(not LookGround.is_forest_floor(opaque), "an opaque base surface is not a glaze")
	var painted := LookGround.painted_source_for(floor, LookGround.Kind.PATCH, true, "landfall") as ShaderMaterial
	var plain := LookGround.painted_source_for(yard, LookGround.Kind.PATCH, true, "landfall") as ShaderMaterial
	_expect(painted != null and painted.get_shader_parameter(&"look_rim") == LookProfile.FOREST_FLOOR_RIM
		and painted.get_shader_parameter(&"look_rim_lobe") == Vector2(
			LookProfile.FOREST_FLOOR_RIM_LOBE.x, LookProfile.FOREST_FLOOR_LOBE_METRES)
		and is_equal_approx(float(painted.get_shader_parameter(&"look_rim_grain")),
			LookProfile.FOREST_FLOOR_RIM_LOBE.y),
		"a forest floor is cut at FOREST_FLOOR_RIM")
	_expect(plain != null and plain.get_shader_parameter(&"look_rim") == LookProfile.PATCH_RIM
		and plain.get_shader_parameter(&"look_rim_lobe") == Vector2(
			LookProfile.PATCH_RIM_LOBE.x, LookProfile.RIM_LOBE_METRES),
		"every other glaze keeps PATCH_RIM")
	_expect(painted != null and is_equal_approx(float(painted.get_shader_parameter(&"look_opacity")),
			LookProfile.PATCH_OPACITY),
		"the forest floor stays a glaze over the ground")
	_expect(LookProfile.FOREST_FLOOR_RIM.x < 0.4 and LookProfile.PATCH_RIM.x > 0.4,
		"the forest floor's cut sits under its 0.4 interior; PATCH_RIM's sat over it")

func _hash(p: Vector2) -> float:
	var p3 := Vector3(p.x, p.y, p.x) * 0.1031
	p3 = Vector3(p3.x - floorf(p3.x), p3.y - floorf(p3.y), p3.z - floorf(p3.z))
	var d := p3.dot(Vector3(p3.y, p3.z, p3.x) + Vector3.ONE * 33.33)
	p3 += Vector3.ONE * d
	var v := (p3.x + p3.y) * p3.z
	return v - floorf(v)

func _noise(p: Vector2) -> float:
	var cell := Vector2(floorf(p.x), floorf(p.y))
	var f := p - cell
	var u := f * f * (Vector2.ONE * 3.0 - 2.0 * f)
	var a := _hash(cell)
	var b := _hash(cell + Vector2(1.0, 0.0))
	var c := _hash(cell + Vector2(0.0, 1.0))
	var d := _hash(cell + Vector2(1.0, 1.0))
	return lerpf(lerpf(a, b, u.x), lerpf(c, d, u.x), u.y)

## The coverage painted_ground_surface.gdshaderinc cuts a patch's vertex
## alpha to, as GDScript, with the texture's grain as a value noise of about
## the moss pack's own scale.
func _coverage(alpha: float, xz: Vector2, rim: Vector3, lobe_amount: float, lobe_metres: float,
		grain_amount: float) -> float:
	var lobe_p := xz / lobe_metres
	var lobe := 0.65 * _noise(lobe_p + Vector2(41.3, 17.9)) \
		+ 0.35 * _noise(lobe_p * 2.7 + Vector2(7.1, 29.3)) - 0.5
	var grain := clampf((_noise(xz / 0.35 + Vector2(3.3, 8.1)) - 0.5) * 0.8, -1.0, 1.0)
	var weight := alpha + (_noise(xz / LookProfile.RIM_NOISE_METRES) - 0.5) * 2.0 * rim.z \
		+ lobe * 2.0 * lobe_amount + grain * grain_amount
	return smoothstep(rim.x - rim.y, rim.x + rim.y, weight)

func _share(alpha: float, forest: bool) -> Array:
	var rim := LookProfile.FOREST_FLOOR_RIM if forest else LookProfile.PATCH_RIM
	var lobe := LookProfile.FOREST_FLOOR_RIM_LOBE if forest else LookProfile.PATCH_RIM_LOBE
	var metres := LookProfile.FOREST_FLOOR_LOBE_METRES if forest else LookProfile.RIM_LOBE_METRES
	var total := 0.0
	var solid := 0
	var count := 0
	for i: int in 120:
		for j: int in 120:
			var xz := Vector2(1300.0 + i * 0.5, 7100.0 + j * 0.5)
			var covered := _coverage(alpha, xz, rim, lobe.x, metres, lobe.y)
			total += covered
			solid += 1 if covered > 0.99 else 0
			count += 1
	return [total / count, float(solid) / count]

func _check_forest_floor_dapples() -> void:
	var before: Array = _share(0.4, false)
	var inside: Array = _share(0.4, true)
	var blend: Array = _share(0.2, true)
	print("forest floor coverage: PATCH_RIM %.2f, FOREST_FLOOR_RIM inside %.2f (solid %.2f), mid-blend %.2f"
		% [before[0], inside[0], inside[1], blend[0]])
	_expect(float(inside[0]) >= float(before[0]) + 0.2,
		"the forest floor draws at least a fifth more of its interior than PATCH_RIM did (%.2f against %.2f)"
			% [inside[0], before[0]])
	_expect(float(inside[0]) >= 0.5 and float(inside[0]) <= 0.8,
		"the forest floor's interior is about half to two thirds moss (%.2f)" % inside[0])
	_expect(float(inside[1]) <= 0.7,
		"and not one solid disc: %.2f of it is fully covered" % inside[1])
	_expect(float(blend[0]) < float(inside[0]) * 0.6,
		"it thins out across its blend (%.2f at half coverage)" % blend[0])

## GLSL's smoothstep, edges either way round.
func _glsl_smoothstep(edge0: float, edge1: float, x: float) -> float:
	var t := clampf((x - edge0) / (edge1 - edge0), 0.0, 1.0)
	return t * t * (3.0 - 2.0 * t)

## look_rock_steep (painted_ground_paint.gdshaderinc) as GDScript.
func _rock_steep(up: float, xz: Vector2) -> float:
	var wobble := LookProfile.ROCK_FACE_WOBBLE
	var wobbled := up + (_noise(xz / wobble.y + Vector2(23.1, 4.7)) - 0.5) * 2.0 * wobble.x
	return 1.0 - _glsl_smoothstep(LookProfile.ROCK_FACE_UP.y, LookProfile.ROCK_FACE_UP.x, wobbled)

## The forest floor's coverage on ground whose normal has world-up component
## `up`: the cut's whole weight scaled by look_steep_keep, as the surface does.
func _floor_coverage(alpha: float, xz: Vector2, up: float) -> float:
	var rim := LookProfile.FOREST_FLOOR_RIM
	var lobe_p := xz / LookProfile.FOREST_FLOOR_LOBE_METRES
	var lobe := 0.65 * _noise(lobe_p + Vector2(41.3, 17.9)) \
		+ 0.35 * _noise(lobe_p * 2.7 + Vector2(7.1, 29.3)) - 0.5
	var grain := clampf((_noise(xz / 0.35 + Vector2(3.3, 8.1)) - 0.5) * 0.8, -1.0, 1.0)
	var keep := 1.0 - LookProfile.FOREST_FLOOR_STEEP * _rock_steep(up, xz)
	var weight := (alpha + (_noise(xz / LookProfile.RIM_NOISE_METRES) - 0.5) * 2.0 * rim.z \
		+ lobe * 2.0 * LookProfile.FOREST_FLOOR_RIM_LOBE.x + grain * LookProfile.FOREST_FLOOR_RIM_LOBE.y) * keep
	return smoothstep(rim.x - rim.y, rim.x + rim.y, weight)

## On a cliff the forest floor gives way to the stone; on level ground it
## dapples exactly as before. The exporter's coverage on steep ground
## alternates 0 and 0.4 vertex by vertex: the worst case is 0.4 everywhere.
func _check_forest_floor_steep() -> void:
	var moss := Color("858066")
	var painted := LookGround.painted_source_for(_patch("authored_coilmere_th-forest2-23", moss),
		LookGround.Kind.PATCH, true, "coilmere") as ShaderMaterial
	var yard := LookGround.painted_source_for(_patch("authored_coilmere_yard-03", moss),
		LookGround.Kind.PATCH, true, "coilmere") as ShaderMaterial
	_expect(painted != null and is_equal_approx(float(painted.get_shader_parameter(&"look_rim_steep")),
			LookProfile.FOREST_FLOOR_STEEP) and LookProfile.FOREST_FLOOR_STEEP == 1.0
		and painted.get_shader_parameter(&"look_rock_up") == LookProfile.ROCK_FACE_UP
		and painted.get_shader_parameter(&"look_rock_wobble") == LookProfile.ROCK_FACE_WOBBLE,
		"a forest floor gives way over the rock layer's steepness band")
	var yard_steep: Variant = yard.get_shader_parameter(&"look_rim_steep") if yard != null else 1.0
	_expect(yard != null and (yard_steep == null or float(yard_steep) == 0.0),
		"every other glaze keeps its coverage on a slope")
	var level_same := true
	var level_total := 0.0
	var steep_max := 0.0
	var ramp_total := 0.0
	var count := 0
	for i: int in 120:
		for j: int in 120:
			var xz := Vector2(1300.0 + i * 0.5, 7100.0 + j * 0.5)
			var before := _coverage(0.4, xz, LookProfile.FOREST_FLOOR_RIM,
				LookProfile.FOREST_FLOOR_RIM_LOBE.x, LookProfile.FOREST_FLOOR_LOBE_METRES,
				LookProfile.FOREST_FLOOR_RIM_LOBE.y)
			var level := _floor_coverage(0.4, xz, 1.0)
			level_same = level_same and level == before
			level_total += level
			# Grade 1.33 (53 degrees, up 0.6) and steeper: the rock is whole.
			steep_max = maxf(steep_max, _floor_coverage(0.4, xz, 0.6 - LookProfile.ROCK_FACE_WOBBLE.x))
			steep_max = maxf(steep_max, _floor_coverage(0.4, xz, 0.45))
			# Halfway through the band (up 0.66, about 49 degrees).
			ramp_total += _floor_coverage(0.4, xz, 0.66)
			count += 1
	print("forest floor on slopes: level %.2f, mid-band %.2f, steep max %.3f"
		% [level_total / count, ramp_total / count, steep_max])
	_expect(level_same, "on level ground the forest floor dapples exactly as before")
	_expect(steep_max == 0.0, "on a cliff (grade 1.33 and up) no forest floor draws (max %.3f)" % steep_max)
	_expect(ramp_total / count < level_total / count * 0.75,
		"it thins out across the rock's band (%.2f against %.2f level)" % [ramp_total / count,
			level_total / count])
	var surface := FileAccess.get_file_as_string("res://src/world/look/painted_ground_surface.gdshaderinc")
	var paint := FileAccess.get_file_as_string("res://src/world/look/painted_ground_paint.gdshaderinc")
	_expect(surface.contains("* look_steep_keep(look_rim_steep, world_normal, look_ground_xz);")
		and surface.contains("uniform float look_rim_steep = 0.0;")
		and paint.contains("float look_rock_steep(vec3 world_normal, vec2 xz) {")
		and paint.contains("return look_rock_steep(world_normal, xz);"),
		"the surface scales its cut's weight by the rock layer's own steepness")
	var overlay_names := _uniform_names(LookGround.SHADER_OVERLAY)
	_expect("look_rim_steep" in overlay_names and "look_rock_up" in overlay_names,
		"the overlay parses with the steep-face cut")

func _uniform_names(shader: Shader) -> Array[String]:
	var names: Array[String] = []
	if shader != null:
		for uniform: Dictionary in shader.get_shader_uniform_list():
			names.append(str(uniform["name"]))
	return names

func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures += 1
	push_error("test_look_shore_cliff_floor: " + message)
	print("FAIL: " + message)
