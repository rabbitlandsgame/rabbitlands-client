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
## sea's edge without a seam. Round 6: the water closes steeply from nothing
## at the cut and tints the shallows over a beach (never grey, never at the
## cut, no foam there either), closes within centimetres over steep ground,
## an object or a submerged rock's top (the gate's bump) and keeps the sea's
## colour there; a silhouette's depth in front of the water counts as deep;
## the noise hashes integer cells. Round 6 repair: a shelf a few centimetres
## under is covered at once (the floor) in a teal no brighter than about 1.2
## times the sea, so over the pale submerged sand it composites darker and
## more saturated than the dry sand; a chord end standing above the water
## (something in front of it: a tuft, a stump, a creature) tells nothing and
## cannot shut the gate; an end off the screen is pulled back to the frame's
## edge, and a pulled-back chord never opens a gate the whole chord shut.
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
## a flat solid disc; it never reads the 2 m facet's own normal (the exporter
## scales the coverage on a cliff or a step's riser, from the smoothed slope
## and the facet's own).

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
	# Round 6: inland water stays opaque at 0.12 m (the paths' graded brooks
	# rely on it), whatever the shallows now do.
	_expect(is_equal_approx(inland.z, 0.12) and is_equal_approx(inland.x, 0.5) and is_equal_approx(inland.y, 2.0),
		"inland water keeps round 4's threshold (0.5-2 m) and its 0.12 m fade (%s)" % str(inland))
	var clear := LookProfile.WATER_SHORE_CLEAR
	_expect(clear.x > 1.0 and clear.x <= 5.0 and clear.y > 0.0 and clear.y <= 0.05,
		"the water closes steeply and rises from nothing over a few centimetres (%s)" % str(clear))
	# Repair: over steep ground the sea closes within 0.2-0.3 m, crisp on a
	# rock's flank but no 0.1 m switch a gate flip draws as a ruled line, and
	# just past the rise the sea already covers half or more of the bed.
	_expect(clear.z >= 0.2 and clear.z <= 0.3 and clear.z < depth.x,
		"over steep ground the sea closes within 0.2-0.3 m (%.2f)" % clear.z)
	_expect(clear.w >= 0.5 and clear.w <= 0.8,
		"the sea covers 0.5-0.8 of the bed just past the rise (%.2f)" % clear.w)
	var shallow := LookProfile.WATER_SHORE_SHALLOW
	var gain := _luma(_sea_lit() * Vector3(shallow.x, shallow.y, shallow.z)) / _luma(_sea_lit())
	_expect(shallow.y > shallow.z and shallow.y > shallow.x and gain >= 1.0 and gain <= 1.25
		and shallow.w >= 0.0 and shallow.w < 0.5,
		"the shallows are a greener teal at most 1.25 times the sea's luminance (%.2f), inland water takes a small share (%s)"
			% [gain, str(shallow)])
	# Repair: lit by the sun the foam's colour is some 30 times the dark sea's
	# albedo, so at 0.12 it alone laid a grey-white band along the kelp notch's
	# waterline; it is a faint sheen.
	_expect(foam.y <= 0.08 and foam.x <= 0.2,
		"the foam is a thin, faint sheen, not a band (%s)" % str(foam))
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
						.is_equal_approx(LookProfile.WATER_SHORE_INLAND)
					and (drawn.get_shader_parameter(&"look_shore_clear") as Vector4)
						.is_equal_approx(LookProfile.WATER_SHORE_CLEAR)
					and (drawn.get_shader_parameter(&"look_shore_shallow") as Vector4)
						.is_equal_approx(LookProfile.WATER_SHORE_SHALLOW),
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
		and "look_shore_foam_up" in shore_names and "look_shore_inland" in shore_names
		and "look_shore_clear" in shore_names and "look_shore_shallow" in shore_names,
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
	# beneath a beach), and only sea pixels inside the fade (round 6: the gate
	# also shortens the fade there) pay for the four extra reads.
	_expect(not include.contains("dFdx(") and not include.contains("dFdy(")
		and not include.contains("fwidth("),
		"the shore reads no screen derivatives")
	var branch := include.find("if (wobbled < fade && inland < 1.0 && shore_on > 0.0 && shore_world.w > 0.5) {")
	var ends_ok := branch > 0
	for end: String in ["vec4 east = continent_water_chord_end(water_world, reach_x,",
			"vec4 west = continent_water_chord_end(water_world, -reach_x,",
			"vec4 south = continent_water_chord_end(water_world, reach_z,",
			"vec4 north = continent_water_chord_end(water_world, -reach_z,"]:
		ends_ok = ends_ok and include.find(end) > branch
	_expect(ends_ok and include.contains("vec3 facet = cross(south_end - north_end, east_end - west_end);"),
		"sea pixels inside the fade read the ground east, west, south and north of the water's point")
	_expect(include.count("textureLod(look_shore_depth_texture") == 1
		and include.count("continent_water_scene(") == 3
		and include.count("= continent_water_chord_end(water_world,") == 4,
		"one depth read per water pixel, four more inside the sea's fade")
	# Round 6: the noise hashes its integer cell (the float hash stepped along
	# cell lines at continent coordinates: ruled lines in the wash and the rim).
	_expect(include.contains("float continent_water_hash(ivec2 cell) {")
		and include.contains("uint h = (uint(cell.x) * 1597334677u) ^ (uint(cell.y) * 3812015801u);")
		and include.contains("continent_water_hash(cell + ivec2(1, 1))")
		and not include.contains("fract(vec3(p.xyx) * 0.1031)"),
		"the shore noise hashes integer lattice cells, never a float product")
	# Round 6: a silhouette's resolved depth in front of the water is deep water.
	_expect(include.contains("if (shore_depth < -(0.05 + 0.004 * length(VERTEX))) {")
		and include.find("shore_depth = 1000.0;", include.find("if (shore_depth < -(0.05")) > 0,
		"a scene point in front of the water counts as deep, not as a waterline")
	# Repair: a chord end tells nothing where its scene point stands above the
	# water (something in front of the end's own water point: a tuft, a stump,
	# a seaweed pile, a bank's crest, a creature, which round 6 read as steep
	# ground and drew as dark copies in the shallows), where nothing was drawn,
	# or off the screen even pulled back to the frame's edge: an end beyond the
	# edge is pulled back along the chord (clip space is linear along it) and
	# keeps its share of the reach. Such an end mirrors its opposite through the
	# ground under the pixel; a chord with neither end reads no slope; only with
	# neither chord does the wash stay. _gate models it.
	for line: String in [
			"vec4 inside = vec4(from.x, -from.x, from.y, -from.y) - 0.998 * from.w;",
			"vec4 slope = vec4(span.x, -span.x, span.y, -span.y) - 0.998 * span.w;",
			"float kept = min(min(cap.x, cap.y), min(cap.z, cap.w));",
			"if (kept < 0.1 || clip.w <= 0.000001) {",
			"if (scene.w < 0.5 || scene.y > level + 0.03) {",
			"return vec4(scene.xyz, kept);",
			"return end.w > 0.0 ? end.xyz : (opposite.w > 0.0 ? 2.0 * centre - opposite.xyz : centre + reach);",
			"float across = (plus.w * minus.y + minus.w * plus.y) / max(plus.w + minus.w, 0.000001);",
			"return (centre.y - across) / max(plus.w * minus.w, 0.2);",
			"if (max(east.w, west.w) > 0.0 || max(south.w, north.w) > 0.0) {",
			"vec3 east_end = continent_water_chord_point(shore_world.xyz, east, west, reach_x);",
			"vec3 west_end = continent_water_chord_point(shore_world.xyz, west, east, -reach_x);",
			"vec3 south_end = continent_water_chord_point(shore_world.xyz, south, north, reach_z);",
			"vec3 north_end = continent_water_chord_point(shore_world.xyz, north, south, -reach_z);",
			"if (min(east.w, west.w) > 0.0) {",
			"bumps += continent_water_chord_bump(shore_world.xyz, east, west);",
			"if (min(south.w, north.w) > 0.0) {",
			"bumps += continent_water_chord_bump(shore_world.xyz, south, north);",
			"float bump = abs(bumps) / max(chords, 1.0) / max(look_shore_foam_up.z, 0.001);"]:
		_expect(include.contains(line), "the gate still reads: %s" % line)
	_expect(not include.contains("continent_water_scene_at(") and not include.contains("bool blind"),
		"no end is read without the frame's pull-back and the above-the-water test")
	# Rounds 4 and 6: what _shore and _gate model, line for line.
	for line: String in [
			"float inland = smoothstep(look_shore_inland.x, look_shore_inland.y, continent_water_level);",
			"float fade = mix(look_shore_depth.x, min(look_shore_depth.x, look_shore_inland.z), inland);",
			"float wobble = look_shore_wobble.x * fade / max(look_shore_depth.x, 0.001);",
			"float wobbled = shore_depth + (shore_noise - 0.5) * 2.0 * wobble;",
			"float grade = length(facet.xz) / max(abs(facet.y), 0.000001) + bump;",
			"float facet_up = inversesqrt(1.0 + grade * grade);",
			"foam_ground = smoothstep(look_shore_foam_up.x, look_shore_foam_up.y, facet_up);",
			"float shore_fade = mix(min(fade, look_shore_clear.z), fade, max(foam_ground, inland));",
			"float shore_scale = shore_fade / max(look_shore_depth.x, 0.001);",
			"wobbled = shore_depth + (shore_noise - 0.5) * 2.0 * look_shore_wobble.x * shore_scale;",
			"float shore_t = clamp((wobbled - look_shore_depth.y) / max(shore_fade - look_shore_depth.y, 0.001), 0.0, 1.0);",
			"float shore_rise = smoothstep(0.0, max(look_shore_clear.y * shore_scale, 0.001), shore_depth);",
			"float shore_floor = look_shore_clear.w * (1.0 - inland);",
			"float shore_alpha = (shore_floor + (1.0 - shore_floor) * (1.0 - pow(1.0 - shore_t, look_shore_clear.x)))",
			"* shore_rise;",
			"vec3 shore_tint = mix(vec3(1.0), look_shore_shallow.rgb, foam_ground * mix(1.0, look_shore_shallow.w, inland));",
			"ALBEDO = mix(ALBEDO, mix(shore_shallow, ALBEDO, smoothstep(0.0, 1.0, shore_t)), shore_on);",
			"float foam_peak = 0.4 * look_shore_foam.x;",
			"float foam_band = shore_rise * smoothstep(0.0, foam_peak, wobbled)",
			"* (1.0 - smoothstep(foam_peak, look_shore_foam.x, wobbled)) * shore_on * (1.0 - inland);",
			"float foam = foam_band * smoothstep(0.45, 0.75, foam_noise) * look_shore_foam.y * foam_ground;",
			"float shore_cover = foam + shore_alpha * (1.0 - foam);",
			"ALBEDO = mix(ALBEDO, look_shore_foam_colour, foam / max(shore_cover, 0.0001));",
			"ALPHA = mix(1.0, clamp(shore_cover, 0.0, 1.0), shore_on);"]:
		_expect(include.contains(line), "the shore shader still reads: %s" % line)

## The shore as continent_water.gdshaderinc draws it (CONTINENT_WATER_SHORE) for
## water whose surface is `level` metres up in the continent's frame, `depth`
## metres over the ground beneath, the wobble noise at `noise` (0-1, 0.5 none)
## and the gate's up component `up` (the chords' normal with the bump, _gate);
## the foam's own noise at its strongest, the quality's switch on. x: what the
## water and its foam cover (ALPHA), y: the foam, z: the share of the shallow
## tint's gain (WATER_SHORE_SHALLOW) its colour takes.
func _shore(level: float, depth: float, noise: float, up: float) -> Vector3:
	var fade_row := LookProfile.WATER_SHORE_DEPTH
	var inland_row := LookProfile.WATER_SHORE_INLAND
	var up_row := LookProfile.WATER_SHORE_FOAM_UP
	var clear := LookProfile.WATER_SHORE_CLEAR
	var foam_row := LookProfile.WATER_SHORE_FOAM
	var inland := _glsl_smoothstep(inland_row.x, inland_row.y, level)
	var fade := lerpf(fade_row.x, minf(fade_row.x, inland_row.z), inland)
	var wobble := LookProfile.WATER_SHORE_WOBBLE.x * fade / maxf(fade_row.x, 0.001)
	var wobbled := depth + (noise - 0.5) * 2.0 * wobble
	var gate := 1.0
	if wobbled < fade and inland < 1.0:
		gate = _glsl_smoothstep(up_row.x, up_row.y, up)
	var shore_fade := lerpf(minf(fade, clear.z), fade, maxf(gate, inland))
	var scale := shore_fade / maxf(fade_row.x, 0.001)
	wobbled = depth + (noise - 0.5) * 2.0 * LookProfile.WATER_SHORE_WOBBLE.x * scale
	var t := clampf((wobbled - fade_row.y) / maxf(shore_fade - fade_row.y, 0.001), 0.0, 1.0)
	var rise := _glsl_smoothstep(0.0, maxf(clear.y * scale, 0.001), depth)
	var floor_cover := clear.w * (1.0 - inland)
	var alpha := (floor_cover + (1.0 - floor_cover) * (1.0 - pow(1.0 - t, clear.x))) * rise
	var peak := 0.4 * foam_row.x
	var foam := rise * _glsl_smoothstep(0.0, peak, wobbled) * (1.0 - _glsl_smoothstep(peak, foam_row.x, wobbled)) \
		* (1.0 - inland) * foam_row.y * gate
	var cover := foam + alpha * (1.0 - foam)
	var tint := (1.0 - _glsl_smoothstep(0.0, 1.0, t)) * gate * lerpf(1.0, LookProfile.WATER_SHORE_SHALLOW.w, inland)
	return Vector3(clampf(cover, 0.0, 1.0), foam, tint)

## The ground gate as continent_water.gdshaderinc reads it. `centre`: the
## ground under the pixel; `ends`: what the reads east, west, south and north
## of the water's point return, each a Vector3 (the scene there, at the whole
## reach), a Vector4 whose w is the share of the reach the end was pulled back
## to at the frame's edge, or null (off the screen even a tenth of the way
## out, or nothing drawn); `level`: the water's surface. An end standing more
## than 3 cm above the surface (something in front of the water, or ground out
## of it) tells nothing. An end that tells nothing is its opposite mirrored
## through the centre; a chord with neither end reads no slope; with neither
## chord the wash stays. The bump comes from the chords with both ends, each
## scaled to a whole chord. The grade plus the bump, as an up component,
## through WATER_SHORE_FOAM_UP.
func _gate(centre: Vector3, ends: Array, level: float) -> float:
	var reach := LookProfile.WATER_SHORE_FOAM_UP.z
	var at: Array[Vector3] = []
	var kept: Array[float] = []
	for end: Variant in ends:
		var point := Vector3.ZERO
		var share := 0.0
		if end is Vector4:
			var four: Vector4 = end
			point = Vector3(four.x, four.y, four.z)
			share = four.w
		elif end is Vector3:
			point = end
			share = 1.0
		if share < 0.1 or point.y > level + 0.03:
			share = 0.0
		at.append(point)
		kept.append(share)
	if maxf(kept[0], kept[1]) <= 0.0 and maxf(kept[2], kept[3]) <= 0.0:
		return 1.0
	var steps: Array[Vector3] = [Vector3(reach, 0.0, 0.0), Vector3(-reach, 0.0, 0.0), Vector3(0.0, 0.0, reach),
		Vector3(0.0, 0.0, -reach)]
	var points: Array[Vector3] = []
	for i: int in 4:
		if kept[i] > 0.0:
			points.append(at[i])
		elif kept[i ^ 1] > 0.0:
			points.append(2.0 * centre - at[i ^ 1])
		else:
			points.append(centre + steps[i])
	var facet := (points[2] - points[3]).cross(points[0] - points[1])
	var bumps := 0.0
	var chords := 0.0
	for plus: int in [0, 2]:
		var minus := plus + 1
		if minf(kept[plus], kept[minus]) > 0.0:
			var across := (kept[plus] * at[minus].y + kept[minus] * at[plus].y) / (kept[plus] + kept[minus])
			bumps += (centre.y - across) / maxf(kept[plus] * kept[minus], 0.2)
			chords += 1.0
	var bump := absf(bumps) / maxf(chords, 1.0) / maxf(reach, 0.001)
	var grade := Vector2(facet.x, facet.z).length() / maxf(absf(facet.y), 0.000001) + bump
	var up := 1.0 / sqrt(1.0 + grade * grade)
	var row := LookProfile.WATER_SHORE_FOAM_UP
	return _glsl_smoothstep(row.x, row.y, up)

## The scene on the ground y = lift - grade_x x - grade_z z + shape (x^2 + z^2)
## (shape below 0: a hump) at the chord's four ends around the origin: `lost`
## names the ends that read nothing, `pulled` maps an end to the share of the
## reach it was pulled back to at the frame's edge.
func _plane_ends(grade_x: float, grade_z: float, lost: Array, pulled := {}, shape := 0.0,
		lift := 0.0) -> Array:
	var reach := LookProfile.WATER_SHORE_FOAM_UP.z
	var ends := []
	var names := ["east", "west", "south", "north"]
	var steps := [Vector2(reach, 0.0), Vector2(-reach, 0.0), Vector2(0.0, reach), Vector2(0.0, -reach)]
	for i: int in 4:
		var share := float(pulled.get(names[i], 1.0))
		var step: Vector2 = (steps[i] as Vector2) * share
		var y := lift - grade_x * step.x - grade_z * step.y + shape * step.length_squared()
		if names[i] in lost:
			ends.append(null)
		elif share < 1.0:
			ends.append(Vector4(step.x, y, step.y, share))
		else:
			ends.append(Vector3(step.x, y, step.y))
	return ends

func _check_shore_gate_edge() -> void:
	# The pixel's ground 0.1 m under the water (the surface at y 0.1): the ends
	# uphill of it that stand out of the water tell nothing (they mirror the
	# downhill ends), as at any real waterline.
	var level := 0.1
	# Suncoil's pier root at the frame's right edge: pixel (1595, 155) lies on
	# a facet whose 1 m chord faces up 0.72 (grade about 0.96), and its east end
	# projects off the screen. With an end pulled back to the frame's edge or
	# lost, it still reads as a bank, and a beach as a beach.
	var bank := 0.96
	var cases: Array = [[[], {}], [[], {"east": 0.3}], [[], {"west": 0.3}], [[], {"south": 0.3}],
		[[], {"north": 0.3}], [[], {"east": 0.3, "north": 0.5}], [["west"], {}], [["north"], {"south": 0.4}]]
	for case: Array in cases:
		var lost: Array = case[0]
		var pulled: Dictionary = case[1]
		var label := "%s lost, %s pulled back" % [str(lost), str(pulled)]
		_expect(_gate(Vector3.ZERO, _plane_ends(bank, 0.0, lost, pulled), level) == 0.0
			and _gate(Vector3.ZERO, _plane_ends(bank * 0.7, bank * 0.7, lost, pulled), level) == 0.0,
			"a bank facet reads steep with %s" % label)
		_expect(_gate(Vector3.ZERO, _plane_ends(0.2, 0.1, lost, pulled), level) == 1.0,
			"a beach keeps its whole wash with %s" % label)
	# A chord with neither end telling reads no slope along it: the other chord
	# still reads a bank across it; with neither chord the wash stays.
	_expect(_gate(Vector3.ZERO, _plane_ends(0.0, bank, ["east", "west"]), level) == 0.0,
		"a chord blind at both ends leaves the other chord's bank")
	_expect(_gate(Vector3.ZERO, _plane_ends(bank, bank, ["east", "west", "south", "north"]), level) == 1.0,
		"with no end telling, the wash stays")
	# Repair: something in front of the water at an end (a tuft, a stump, a
	# seaweed pile, a creature: here 1 m above the surface and 3 m nearer the
	# camera, south) tells nothing. A beach reads as the beach and a bank as a
	# bank: no opaque copy of the occluder in the shallows. (Here the pixel's
	# ground is 0.4 m down and every end under water; where the end opposite
	# the occluded one is out of the water too, that chord reads no slope.)
	var deep := 0.4
	for grade: float in [0.3, 0.45, 0.5, 0.6]:
		var whole := _gate(Vector3.ZERO, _plane_ends(grade * 0.6, grade * 0.8, []), deep)
		for i: int in 4:
			var ends := _plane_ends(grade * 0.6, grade * 0.8, [])
			var end: Vector3 = ends[i]
			ends[i] = Vector3(end.x, deep + 1.0, end.z + 3.0)
			_expect(is_equal_approx(_gate(Vector3.ZERO, ends, deep), whole),
				"a grade-%.2f beach with end %d hidden by an occluder reads %.2f, as the plane (%.2f)"
					% [grade, i, _gate(Vector3.ZERO, ends, deep), whole])
	var hidden := _plane_ends(bank, 0.0, [])
	hidden[0] = Vector3(0.5, 0.6 + 1.0, 3.5)
	_expect(_gate(Vector3.ZERO, hidden, 0.6) == 0.0, "a bank with an occluded end still reads steep")
	# Round 6, the bump: a submerged rock's top 0.14 m down whose four ends lie
	# on the rock's flanks or the seabed around it (a flat chord) reads steep;
	# a beach's plane has none.
	var rock_top := Vector3(0.0, -0.14, 0.0)
	_expect(_gate(rock_top, _plane_ends(0.0, 0.0, [], {}, 0.0, -0.84), 0.0) == 0.0,
		"a submerged rock's top whose chords lie flat on the seabed reads steep (%.2f)"
			% _gate(rock_top, _plane_ends(0.0, 0.0, [], {}, 0.0, -0.84), 0.0))
	_expect(_gate(Vector3(0.0, -0.1, 0.0), _plane_ends(0.3, 0.2, [], {}, 0.0, -0.1), 0.0) == 1.0,
		"a beach's plane has no bump")
	# A beach near the gate's edge (Saltsound's 281-292 step, grade 0.45-0.5)
	# reads the same with any one end pulled back or lost: no line along the
	# frame's edge.
	for grade: float in [0.45, 0.5, 0.6]:
		var whole := _gate(Vector3.ZERO, _plane_ends(grade * 0.6, grade * 0.8, []), deep)
		for end: String in ["east", "west", "south", "north"]:
			var pulled_gate := _gate(Vector3.ZERO, _plane_ends(grade * 0.6, grade * 0.8, [], {end: 0.35}), deep)
			var lost_gate := _gate(Vector3.ZERO, _plane_ends(grade * 0.6, grade * 0.8, [end]), deep)
			_expect(is_equal_approx(pulled_gate, whole) and is_equal_approx(lost_gate, whole),
				"a grade-%.2f beach reads %.2f whole, %.2f with %s pulled back, %.2f with it lost"
					% [grade, whole, pulled_gate, end, lost_gate])
	# A chord pulled back at the frame's edge never opens a gate the whole chord
	# shuts more: a submerged hump (shape -1.4, its top 5 cm down, a gate
	# between open and shut) reads at least as steep.
	for end: String in ["east", "west", "south", "north"]:
		var top := Vector3(0.0, -0.05, 0.0)
		var whole := _gate(top, _plane_ends(0.0, 0.0, [], {}, -1.4, -0.05), 0.0)
		for share: float in [0.2, 0.5, 0.8]:
			var cut := _gate(top, _plane_ends(0.0, 0.0, [], {end: share}, -1.4, -0.05), 0.0)
			_expect(cut <= whole + 0.000001,
				"a hump with %s pulled back to %.1f reads %.2f, no more open than whole (%.2f)"
					% [end, share, cut, whole])

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
	_expect(_shore(142.1, 0.01, 0.5, 1.0).x < 0.3,
		"the brook still fades in at its very edge (%.2f at 0.01 m)" % _shore(142.1, 0.01, 0.5, 1.0).x)
	# Round 6 keeps inland water's 0.12 m: opaque there at the wobble's worst.
	_expect(_shore(142.1, 0.12, 0.0, 1.0).x >= 0.98 and _shore(99.3, 0.12, 0.0, 1.0).x >= 0.98,
		"inland water is opaque 0.12 m down (%.3f)" % _shore(142.1, 0.12, 0.0, 1.0).x)
	_expect(_shore(142.1, 0.03, 0.5, 1.0).z <= LookProfile.WATER_SHORE_SHALLOW.w,
		"inland water takes only its share of the shallow tint (%.2f)" % _shore(142.1, 0.03, 0.5, 1.0).z)
	_expect(_shore(47.57, 0.05, 0.5, 1.0).y == 0.0 and _shore(99.3, 0.05, 0.5, 1.0).y == 0.0,
		"Reedfall's and Hornmere's lakes carry no surf")
	# Suncoil's shelf beside the pier: 0.71-0.95 m deep. At 0.9 m of fade it
	# showed through as a pale wedge; it is opaque at the wobble's worst.
	_expect(_shore(0.0, 0.71, 0.0, 1.0).x >= 0.999,
		"a 0.71 m shelf is opaque (%.3f)" % _shore(0.0, 0.71, 0.0, 1.0).x)
	# Round 6: nothing at the cut itself, whatever the wobble, so neither the
	# water nor its foam redraws the facets' straight cut.
	for noise: float in [0.0, 0.25, 0.5, 0.75, 1.0]:
		for up: float in [1.0, 0.7]:
			var cut := _shore(0.0, 0.0, noise, up)
			_expect(cut.x == 0.0 and cut.y == 0.0,
				"nothing is drawn at the cut (noise %.2f, up %.1f)" % [noise, up])
	# Round 6: the water closes steeply. Round 4's smoothstep left a beach's
	# first decimetres nearly clear, so sand blended with the dark teal drew a
	# grey film; now it covers more at every depth, half by 0.15 m, and still
	# keeps a gradient (not opaque 0.3 m down: 1.5 m of beach at grade 0.2).
	var closes := true
	for i: int in range(1, 10):
		var d := 0.05 * i
		closes = closes and _shore(0.0, d, 0.5, 1.0).x > _glsl_smoothstep(0.0, 0.55, d)
	_expect(closes, "the water covers a beach more than round 4's fade at every depth 0.05-0.45 m")
	_expect(_shore(0.0, 0.15, 0.5, 1.0).x >= 0.5 and _shore(0.0, 0.3, 0.5, 1.0).x < 0.98,
		"a beach closes fast but keeps a gradient (%.2f at 0.15 m, %.2f at 0.3 m)" % [
			_shore(0.0, 0.15, 0.5, 1.0).x, _shore(0.0, 0.3, 0.5, 1.0).x])
	# The beach's shallows take the turquoise; steep ground keeps the sea's
	# colour (a dark grass bank under the whole tint glowed cyan).
	_expect(_shore(0.0, 0.05, 0.5, 1.0).z > 0.8 and _shore(0.0, 0.05, 0.5, 0.7).z == 0.0,
		"a beach's shallows are tinted (%.2f), a bank's are not (%.2f)" % [
			_shore(0.0, 0.05, 0.5, 1.0).z, _shore(0.0, 0.05, 0.5, 0.7).z])
	# Over steep ground or an object (gate shut) the sea closes within
	# WATER_SHORE_CLEAR.z, where a beach still keeps a gradient.
	var steep_d := LookProfile.WATER_SHORE_CLEAR.z
	_expect(_shore(0.0, steep_d, 0.5, 0.7).x >= 0.99 and _shore(0.0, steep_d, 0.5, 1.0).x < 0.95,
		"a bank closes within %.2f m (%.2f), a beach does not (%.2f)" % [steep_d,
			_shore(0.0, steep_d, 0.5, 0.7).x, _shore(0.0, steep_d, 0.5, 1.0).x])
	# Repair: a gate that flips in one pixel (a rock's foot, a riser's crest)
	# steps the cover by little, so it draws no ruled line: at most 0.2 at any
	# depth, where round 6's 0.1 m steep fade switched 0.4-0.55 at once.
	var flip := 0.0
	for i: int in range(1, 30):
		var d := 0.01 * i
		flip = maxf(flip, _shore(0.0, d, 0.5, 0.7).x - _shore(0.0, d, 0.5, 1.0).x)
	_expect(flip <= 0.2, "a gate flip steps the cover by at most %.2f" % flip)
	# Repair: just past the rise the sea covers WATER_SHORE_CLEAR.w of the bed
	# at the wobble's worst, so a shelf or a notch a few centimetres (or
	# millimetres) under is darkened at once, not shown through as a pane.
	var floor_cover := LookProfile.WATER_SHORE_CLEAR.w
	var rise_d := LookProfile.WATER_SHORE_CLEAR.y
	for noise: float in [0.0, 0.5, 1.0]:
		_expect(_shore(0.0, rise_d * 1.01, noise, 1.0).x >= floor_cover - 0.001
			and _shore(0.0, 0.05, noise, 1.0).x >= floor_cover,
			"a shelf just past the rise is covered %.2f, at 5 cm %.2f (noise %.1f)" % [
				_shore(0.0, rise_d * 1.01, noise, 1.0).x, _shore(0.0, 0.05, noise, 1.0).x, noise])
	# Repair, the review's frosted pane (Saltsound's kelp notch): over the
	# submerged sand as the ground draws it (165, 160, 145, paler and greyer
	# than the dry sand beside it, 157, 143, 113), the shallows composite in
	# linear light with the sea as the renders light it (15, 93, 100 beside the
	# notch). Over the first decimetre, averaged over the wobble, they are at
	# most 0.85 of the dry sand's luma and at least 0.2 saturated: darkened,
	# tinted wet sand, not a pane lighter than the beach.
	var bed := _linear(Vector3(165.0, 160.0, 145.0))
	var sand_luma := _luma(Vector3(157.0, 143.0, 113.0))
	for d: float in [0.01, 0.03, 0.05, 0.1]:
		var mean := Vector3.ZERO
		for noise: float in [0.0, 0.25, 0.5, 0.75, 1.0]:
			mean += _shallows(bed, 0.0, d, noise, 1.0) / 5.0
		var saturation := (maxf(mean.x, maxf(mean.y, mean.z)) - minf(mean.x, minf(mean.y, mean.z))) \
			/ maxf(maxf(mean.x, maxf(mean.y, mean.z)), 0.0001)
		_expect(_luma(mean) <= 0.85 * sand_luma and saturation >= 0.2,
			"%.2f m over the pale shelf composites to %s: luma %.0f against the dry sand's %.0f, saturation %.2f"
				% [d, str(mean.round()), _luma(mean), sand_luma, saturation])
	# The foam is a thin ridge off the waterline, light, and gone by FOAM.x.
	var ridge := 0.4 * LookProfile.WATER_SHORE_FOAM.x
	_expect(_shore(0.0, ridge, 0.5, 0.95).y > 0.02 and _shore(0.0, ridge, 0.5, 0.95).y <= 0.08
		and _shore(0.0, LookProfile.WATER_SHORE_FOAM.x, 0.5, 1.0).y == 0.0,
		"a beach keeps a light wash at its ridge (%.2f) and none past it" % _shore(0.0, ridge, 0.5, 0.95).y)
	# Suncoil's pier-root tooth (its facets under the foam face up 0.68 / 0.74 /
	# 0.83 at the 10th / 50th / 90th percentile) drew a pale streaked smear;
	# Boarsend's beach (0.90 / 0.92 / 0.96) keeps its whole wash.
	_expect(_shore(0.0, 0.05, 0.5, 0.68).y == 0.0 and _shore(0.0, 0.05, 0.5, 0.74).y == 0.0
		and _shore(0.0, 0.05, 0.5, 0.83).y < 0.75 * _shore(0.0, 0.05, 0.5, 1.0).y,
		"the tooth's facets get little or no foam (%.2f at its 90th percentile)"
			% _shore(0.0, 0.05, 0.5, 0.83).y)
	_expect(is_equal_approx(_shore(0.0, 0.05, 0.5, 0.9).y, _shore(0.0, 0.05, 0.5, 1.0).y),
		"a beach's facet keeps its whole wash")
	# Round 6: the tooth's facets also close fast and keep the sea's colour.
	_expect(_shore(0.0, 0.08, 0.5, 0.74).x > 0.9 and _shore(0.0, 0.08, 0.5, 0.74).z == 0.0,
		"the tooth's median facet is covered 0.9 within 8 cm, untinted (%.2f)" % _shore(0.0, 0.08, 0.5, 0.74).x)
	# A river mouth runs from the sea's edge into inland water without a seam.
	var previous := _shore(0.0, 0.1, 0.5, 1.0)
	var jump := 0.0
	for step: int in range(1, 41):
		var now := _shore(step * 0.05, 0.1, 0.5, 1.0)
		jump = maxf(jump, maxf(maxf(absf(now.x - previous.x), absf(now.y - previous.y)), absf(now.z - previous.z)))
		previous = now
	_expect(jump < 0.1, "alpha, foam and tint change by at most %.3f per 5 cm of river mouth" % jump)

## The open sea as the renders light it beside Saltsound's kelp notch
## (15, 93, 100 in the still), in linear light.
func _sea_lit() -> Vector3:
	return _linear(Vector3(15.0, 93.0, 100.0))

## An sRGB colour (0-255) in linear light, and back.
func _linear(srgb: Vector3) -> Vector3:
	var out := Vector3.ZERO
	for i: int in 3:
		var c := srgb[i] / 255.0
		out[i] = c / 12.92 if c <= 0.04045 else pow((c + 0.055) / 1.055, 2.4)
	return out

func _srgb(linear: Vector3) -> Vector3:
	var out := Vector3.ZERO
	for i: int in 3:
		var c := clampf(linear[i], 0.0, 1.0)
		out[i] = 255.0 * (c * 12.92 if c <= 0.0031308 else 1.055 * pow(c, 1.0 / 2.4) - 0.055)
	return out

## What the shallows composite to (sRGB 0-255) over the bed `bed` (linear):
## the sea as lit (_sea_lit) times the shallow tint at _shore's share, over
## the bed at _shore's cover, blended in linear light (the foam left out).
func _shallows(bed: Vector3, level: float, depth: float, noise: float, up: float) -> Vector3:
	var shore := _shore(level, depth, noise, up)
	var tint_row := LookProfile.WATER_SHORE_SHALLOW
	var tint := Vector3.ONE.lerp(Vector3(tint_row.x, tint_row.y, tint_row.z), shore.z)
	return _srgb(_sea_lit() * tint * shore.x + bed * (1.0 - shore.x))

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
## `up`: the cut's whole weight scaled by look_steep_keep, as the surface does
## (by 1 - FOREST_FLOOR_STEEP times the rock's steepness: by 1 now).
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

## The forest floor never reads its 2 m facet's own normal: cut out by the rock
## layer's steepness facet by facet (FOREST_FLOOR_STEEP 1), it drew flat olive
## triangles with ruled edges on Landfall's forest-21 bank, whose 44-60 degree
## facets lie on ground smoothed to 0.86-1.0 (map polish review of round 4,
## 2026-11-17). On a cliff or a step's riser it gives way to the stone through
## its coverage: the exporter scales it at each facet corner from the smoothed
## slope and the facet's own (terrain_export.py forest_floor_keep, tested in
## test_base_smooth_up.py), so a cliff's face carries none, and with none the
## cut draws next to nothing.
func _check_forest_floor_steep() -> void:
	var moss := Color("858066")
	var painted := LookGround.painted_source_for(_patch("authored_coilmere_th-forest2-23", moss),
		LookGround.Kind.PATCH, true, "coilmere") as ShaderMaterial
	var yard := LookGround.painted_source_for(_patch("authored_coilmere_yard-03", moss),
		LookGround.Kind.PATCH, true, "coilmere") as ShaderMaterial
	_expect(painted != null and is_equal_approx(float(painted.get_shader_parameter(&"look_rim_steep")),
			LookProfile.FOREST_FLOOR_STEEP) and LookProfile.FOREST_FLOOR_STEEP == 0.0,
		"a forest floor's cut keeps none of the per-facet steep cut")
	var yard_steep: Variant = yard.get_shader_parameter(&"look_rim_steep") if yard != null else 1.0
	_expect(yard != null and (yard_steep == null or float(yard_steep) == 0.0),
		"every other glaze keeps its coverage on a slope")
	var level_same := true
	var facet_same := true
	var level_total := 0.0
	var bare_total := 0.0
	var bare_max := 0.0
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
			# A bank's 44-60 degree facets (up 0.5-0.72) and a cliff's: the
			# same coverage draws the same floor.
			for up: float in [0.72, 0.66, 0.6, 0.5, 0.3]:
				facet_same = facet_same and _floor_coverage(0.4, xz, up) == level
			# A cliff's vertices, which the exporter's fade leaves at 0.
			var bare := _floor_coverage(0.0, xz, 0.45)
			bare_total += bare
			bare_max = maxf(bare_max, bare)
			count += 1
	print("forest floor on slopes: level %.2f, coverage 0 mean %.4f (max %.3f)"
		% [level_total / count, bare_total / count, bare_max])
	_expect(level_same, "on level ground the forest floor dapples exactly as before")
	_expect(facet_same, "a steep facet draws the floor its coverage gives, as level ground does")
	_expect(bare_total / count < 0.01,
		"where the exporter's fade leaves no coverage next to nothing draws (%.4f)" % (bare_total / count))
	var surface := FileAccess.get_file_as_string("res://src/world/look/painted_ground_surface.gdshaderinc")
	var paint := FileAccess.get_file_as_string("res://src/world/look/painted_ground_paint.gdshaderinc")
	_expect(surface.contains("* look_steep_keep(look_rim_steep, world_normal, look_ground_xz);")
		and surface.contains("uniform float look_rim_steep = 0.0;")
		and paint.contains("float look_rock_steep(vec3 world_normal, vec2 xz) {")
		and paint.contains("return look_rock_steep(world_normal, xz);"),
		"the surface can still scale its cut's weight by the rock layer's steepness (none does)")
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
