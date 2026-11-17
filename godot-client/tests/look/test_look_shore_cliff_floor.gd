extends SceneTree
## Guards the map polish pass's three runtime look changes (2026-11-16).
##
## The water's edge (LookProfile.WATER_SHORE_*): the continent sea's look copy
## is drawn by the soft-edged shader at MEDIUM and HIGH, keeping every
## parameter the loader and the decode gave it, and stays the opaque shader at
## LOW and in the compatibility renderer; the quality's switch is a declared
## global; the opaque shader the loader puts in never reads depth. Round 4
## (the shore's alpha and foam, here as GDScript, _shore): inland water
## (Twinbrook's graded brook) reads as water with no foam, Suncoil's 0.7 m
## shelf is opaque, a beach keeps its gradient and wash, a bank facet gets no
## foam (at the frame's edge too, _gate), and a river mouth blends into the
## sea's edge without a seam.
##
## The cliff's tone: the steep-face rock is drawn as stone on a cliff
## (look_rock_tone, here as GDScript): on green ground it is not green, on tan
## ground it keeps a modest warmth, and the paint gives the stone no grass
## trims (which faces are cliffs, read from the ground's smoothed normal:
## test_look_rock_face).
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
	_check_shore_model()
	_check_shore_gate_edge()
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
	_expect(depth.x <= 0.7,
		"the sea's fade ends by 0.7 m, so Suncoil's shelf beside the pier is not drawn through it (%s)"
			% str(depth))
	var up := LookProfile.WATER_SHORE_FOAM_UP
	_expect(up.x < up.y and up.x >= 0.7 and up.y <= 0.95,
		"the foam fades out between a beach and a bank facet (%s)" % str(up))
	_expect(up.z >= 0.25 and up.z <= 1.0,
		"the ground's slope is read over a chord of 0.5-2 m, not a pixel (%s)" % str(up))
	var inland := LookProfile.WATER_SHORE_INLAND
	_expect(inland.x > 0.0 and inland.x < inland.y and inland.y <= 5.0 and inland.z > 0.0
		and inland.z <= 0.2 and inland.z < depth.x,
		"inland water starts a little above the sea and fades in over a few centimetres (%s)" % str(inland))
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
						.is_equal_approx(LookProfile.WATER_SHORE_FOAM)
					and (drawn.get_shader_parameter(&"look_shore_foam_up") as Vector3)
						.is_equal_approx(LookProfile.WATER_SHORE_FOAM_UP)
					and (drawn.get_shader_parameter(&"look_shore_inland") as Vector3)
						.is_equal_approx(LookProfile.WATER_SHORE_INLAND),
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
		and "look_shore_depth" in shore_names and "look_shore_foam" in shore_names
		and "look_shore_foam_up" in shore_names and "look_shore_inland" in shore_names,
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
	# Round 4: what _shore models, line for line.
	_expect(include.contains("continent_water_level = (water_to_continent * vec4(VERTEX, 1.0)).y;"),
		"inland water is told by its continent height, which a rebase cannot move")
	# The slope beneath the foam is a chord's, read back around the water's own
	# point, never a pixel's (a pixel's derivative switches the foam along each
	# 2 m facet's edge and reads the ground layers a few millimetres apart
	# beneath a beach), and only the foam's band pays for the four extra reads.
	_expect(not include.contains("dFdx(") and not include.contains("dFdy(")
		and not include.contains("fwidth("),
		"the shore reads no screen derivatives")
	var branch := include.find("if (foam_band > 0.0 && shore_world.w > 0.5) {")
	_expect(branch > 0 and include.find("continent_water_scene_at(water_world + reach_x,") > branch
		and include.find("continent_water_scene_at(water_world - reach_z,") > branch
		and include.contains("vec3 facet = cross(south.xyz - north.xyz, east.xyz - west.xyz);"),
		"the foam's band reads the ground east, west, south and north of the water's point")
	# Near the frame's edge an end falls off the screen: it becomes the ground
	# under the pixel (a half chord), and only a chord blind at both ends keeps
	# the wash (_gate models it). Round 4's first gate kept the wash whenever
	# any end left the screen, which drew the steep-facet streaks back in a
	# strip a chord wide along every edge of the frame (Suncoil's pier root).
	var blind_at := include.find(
		"bool blind = (east.w < 0.5 && west.w < 0.5) || (south.w < 0.5 && north.w < 0.5);")
	var facet_at := include.find("vec3 facet = cross(south.xyz - north.xyz, east.xyz - west.xyz);")
	var swaps_ok := blind_at > branch
	for end: String in ["east", "west", "south", "north"]:
		var swap_at := include.find("%s = %s.w > 0.5 ? %s : shore_world;" % [end, end, end])
		swaps_ok = swaps_ok and swap_at > blind_at and swap_at < facet_at
	_expect(swaps_ok and include.contains("if (!blind) {")
		and not include.contains("east.w * west.w * south.w * north.w"),
		"an end off the screen reads the ground under the pixel; only a chord blind at both ends keeps the wash")
	for line: String in [
			"float inland = smoothstep(look_shore_inland.x, look_shore_inland.y, continent_water_level);",
			"float fade = mix(look_shore_depth.x, min(look_shore_depth.x, look_shore_inland.z), inland);",
			"float wobble = look_shore_wobble.x * fade / max(look_shore_depth.x, 0.001);",
			"float shore_alpha = smoothstep(look_shore_depth.y, max(fade, look_shore_depth.y + 0.001), wobbled);",
			"foam_ground = smoothstep(look_shore_foam_up.x, look_shore_foam_up.y, facet_up);",
			"float foam_band = (1.0 - smoothstep(0.0, look_shore_foam.x, wobbled)) * shore_on * (1.0 - inland);",
			"float foam = foam_band * smoothstep(0.35, 0.7, foam_noise) * look_shore_foam.y * foam_ground;"]:
		_expect(include.contains(line), "the shore shader still reads: %s" % line)

## The shore's alpha (x) and foam (y) as continent_water.gdshaderinc draws them
## (CONTINENT_WATER_SHORE) for water whose surface is `level` metres up in the
## continent's frame, `depth` metres over the ground beneath, the wobble noise
## at `noise` (0-1, 0.5 none) and that ground's normal up component `up`; the
## foam's own noise at its strongest, the quality's switch on.
func _shore(level: float, depth: float, noise: float, up: float) -> Vector2:
	var fade_row := LookProfile.WATER_SHORE_DEPTH
	var inland_row := LookProfile.WATER_SHORE_INLAND
	var up_row := LookProfile.WATER_SHORE_FOAM_UP
	var inland := smoothstep(inland_row.x, inland_row.y, level)
	var fade := lerpf(fade_row.x, minf(fade_row.x, inland_row.z), inland)
	var wobble := LookProfile.WATER_SHORE_WOBBLE.x * fade / maxf(fade_row.x, 0.001)
	var wobbled := depth + (noise - 0.5) * 2.0 * wobble
	var alpha := smoothstep(fade_row.y, maxf(fade, fade_row.y + 0.001), wobbled)
	var foam := (1.0 - smoothstep(0.0, LookProfile.WATER_SHORE_FOAM.x, wobbled)) \
		* LookProfile.WATER_SHORE_FOAM.y * smoothstep(up_row.x, up_row.y, up) * (1.0 - inland)
	return Vector2(clampf(alpha + foam, 0.0, 1.0), foam)

## The foam's ground gate as continent_water.gdshaderinc reads it: `ends` holds
## the ground east, west, south and north of the water's point (null where
## that end is off the screen), `centre` the ground under the pixel itself.
func _gate(centre: Vector3, ends: Array) -> float:
	if (ends[0] == null and ends[1] == null) or (ends[2] == null and ends[3] == null):
		return 1.0
	var at: Array[Vector3] = []
	for end: Variant in ends:
		if end == null:
			at.append(centre)
		else:
			at.append(end as Vector3)
	var facet := (at[2] - at[3]).cross(at[0] - at[1])
	var up := absf(facet.y) / maxf(facet.length(), 0.000001)
	var row := LookProfile.WATER_SHORE_FOAM_UP
	return _glsl_smoothstep(row.x, row.y, up)

## The ground of the plane y = -grade_x x - grade_z z at the chord's four ends
## around the origin, `off` naming the ends off the screen.
func _plane_ends(grade_x: float, grade_z: float, off: Array) -> Array:
	var reach := LookProfile.WATER_SHORE_FOAM_UP.z
	var ends := []
	var names := ["east", "west", "south", "north"]
	var steps := [Vector2(reach, 0.0), Vector2(-reach, 0.0), Vector2(0.0, reach), Vector2(0.0, -reach)]
	for i: int in 4:
		var step: Vector2 = steps[i]
		if names[i] in off:
			ends.append(null)
		else:
			ends.append(Vector3(step.x, -grade_x * step.x - grade_z * step.y, step.y))
	return ends

func _check_shore_gate_edge() -> void:
	# Suncoil's pier root at the frame's right edge: pixel (1595, 155) lies on
	# a facet whose 1 m chord faces up 0.72 (grade about 0.96), and its east end
	# projects off the screen. Every half chord still reads it as a bank.
	var bank := 0.96
	for off: Array in [[], ["east"], ["west"], ["south"], ["north"], ["east", "north"], ["west", "south"]]:
		_expect(_gate(Vector3.ZERO, _plane_ends(bank, 0.0, off)) == 0.0
			and _gate(Vector3.ZERO, _plane_ends(0.0, bank, off)) == 0.0
			and _gate(Vector3.ZERO, _plane_ends(bank * 0.7, bank * 0.7, off)) == 0.0,
			"a bank facet gets no foam with %s off the screen" % (str(off) if not off.is_empty() else "no end"))
		_expect(_gate(Vector3.ZERO, _plane_ends(0.2, 0.1, off)) == 1.0,
			"a beach keeps its whole wash with %s off the screen" % (str(off) if not off.is_empty() else "no end"))
	# Only a chord with both ends off the screen cannot tell: the wash stays.
	_expect(_gate(Vector3.ZERO, _plane_ends(bank, 0.0, ["east", "west"])) == 1.0
		and _gate(Vector3.ZERO, _plane_ends(bank, 0.0, ["south", "north"])) == 1.0,
		"a chord blind at both ends keeps the wash")

func _check_shore_model() -> void:
	# Twinbrook's graded brook (castle-brook-west, surface 142-143 m): drawn
	# depth 0.03 / 0.13 / 0.28 m at its 10th / 50th / 90th percentile. Under the
	# sea's edge it drew at alpha 0.1-0.5 with foam; now it reads as water.
	var lowest := 1.0
	for noise: float in [0.0, 0.5, 1.0]:
		lowest = minf(lowest, _shore(142.1, 0.13, noise, 1.0).x)
		_expect(_shore(142.1, 0.28, noise, 1.0).x > 0.99 and _shore(142.1, 0.13, noise, 1.0).y == 0.0,
			"the brook is opaque at its 90th percentile and carries no foam (noise %.1f)" % noise)
	_expect(lowest >= 0.9, "the brook's median depth draws at alpha %.2f (0.9 or more)" % lowest)
	_expect(_shore(142.1, 0.02, 0.5, 1.0).x < 0.3,
		"the brook still fades in at its very edge (%.2f)" % _shore(142.1, 0.02, 0.5, 1.0).x)
	_expect(_shore(47.57, 0.05, 0.5, 1.0).y == 0.0 and _shore(99.3, 0.05, 0.5, 1.0).y == 0.0,
		"Reedfall's and Hornmere's lakes carry no surf")
	# Suncoil's shelf beside the pier: 0.71-0.95 m deep. At 0.9 m of fade it
	# showed through as a pale wedge; it is opaque at the wobble's worst.
	_expect(_shore(0.0, 0.71, 0.0, 1.0).x >= 0.999,
		"a 0.71 m shelf is opaque (%.3f)" % _shore(0.0, 0.71, 0.0, 1.0).x)
	# A sea beach keeps its gradient: still clear near the waterline and not yet
	# opaque 0.35 m down (1.75 m of beach at grade 0.2), with its wash.
	_expect(_shore(0.0, 0.03, 0.5, 1.0).x < 0.6 and _shore(0.0, 0.35, 0.5, 1.0).x < 0.95,
		"a beach keeps a gradient (%.2f at 0.03 m, %.2f at 0.35 m)" % [
			_shore(0.0, 0.03, 0.5, 1.0).x, _shore(0.0, 0.35, 0.5, 1.0).x])
	_expect(_shore(0.0, 0.05, 0.5, 0.95).y > 0.3,
		"a beach keeps its wash (%.2f)" % _shore(0.0, 0.05, 0.5, 0.95).y)
	# Suncoil's pier-root tooth (its facets under the foam face up 0.68 / 0.74 /
	# 0.83 at the 10th / 50th / 90th percentile) drew a pale streaked smear;
	# Boarsend's beach (0.90 / 0.92 / 0.96) keeps its whole wash.
	_expect(_shore(0.0, 0.05, 0.5, 0.68).y == 0.0 and _shore(0.0, 0.05, 0.5, 0.74).y == 0.0
		and _shore(0.0, 0.05, 0.5, 0.83).y < 0.75 * _shore(0.0, 0.05, 0.5, 1.0).y,
		"the tooth's facets get little or no foam (%.2f at its 90th percentile)"
			% _shore(0.0, 0.05, 0.5, 0.83).y)
	_expect(is_equal_approx(_shore(0.0, 0.05, 0.5, 0.9).y, _shore(0.0, 0.05, 0.5, 1.0).y),
		"a beach's facet keeps its whole wash")
	# A river mouth runs from the sea's edge into inland water without a seam.
	var previous := _shore(0.0, 0.1, 0.5, 1.0)
	var jump := 0.0
	for step: int in range(1, 41):
		var now := _shore(step * 0.05, 0.1, 0.5, 1.0)
		jump = maxf(jump, maxf(absf(now.x - previous.x), absf(now.y - previous.y)))
		previous = now
	_expect(jump < 0.1, "alpha and foam change by at most %.3f per 5 cm of river mouth" % jump)

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
	_expect(paint.contains("float verge_green = look_green(reference) * (1.0 - stone);")
		and paint.count("look_green(reference)") == 2,
		"the verge's grass trims skip the stone")
	var vertex_at := surface.find("reference *= vertex_colour;")
	var layer_at := surface.find("look_rock_layer(albedo, reference, texel_mean, look_rock_tint, world_normal,")
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
