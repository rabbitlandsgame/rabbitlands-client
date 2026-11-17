extends SceneTree
## Guards the soft-edged sea's place in the transparent pass
## (LookProfile.WATER_SHORE_PRIORITY, LookGround.glaze_priority; map polish
## verify 2026-11-16).
##
## At MEDIUM and HIGH the continent sea's look copy blends and writes depth, so
## Godot sorts it with every other blended surface: lower render_priority
## first, then back to front by each instance's AABB centre. Its 96 m Water_
## cells must draw after every painted blended ground copy - glazes, overlays,
## walk decks, cut-out patches, kit paving and the road composites built on
## them - or a glaze under the shallow edge fails against the sea's depth and
## shows the near-black its own depth pre-pass left (Coilmere's knob mole).
## And before everything else - rain, flames, spells, markers, the harvest
## glint, faded kit models, at 0 and up - or a nearer sea cell paints over
## them. Lowering only the sea would leave the glazes after it.

const RendererFamily := preload("res://src/runtime/renderer_family.gd")
const Composite := preload("res://src/world/road_ground/material.gd")
const Road := preload("res://src/world/road_ground/road_ground.gd")

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	LookProfile.set_player_mode(LookProfile.Mode.FULL_PAINTED)
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	LookGround.apply_quality()
	var sea := _check_sea()
	_check_glazes(sea)
	_check_glaze_priority_range(sea)
	_check_road_composite(sea)
	_check_effects_after(sea)
	LookProfile.set_player_quality(LookProfile.QUALITY_DEFAULT)
	LookGround.apply_quality()
	RendererFamily.override_for_tests("")
	if failures == 0:
		print("test_look_sea_order: ok")
	quit(1 if failures > 0 else 0)

## The decoded sea's priority at HIGH (soft) and LOW (opaque), in Forward+.
func _check_sea() -> int:
	RendererFamily.override_for_tests(RendererFamily.FORWARD_PLUS)
	var source := ShaderMaterial.new()
	source.shader = load(LookGround.CONTINENT_WATER_PATH) as Shader
	var drawn := {}
	for level: int in [LookProfile.Quality.LOW, LookProfile.Quality.HIGH]:
		LookProfile.set_player_quality(level)
		var world := Node3D.new()
		root.add_child(world)
		var mesh := MeshInstance3D.new()
		mesh.name = "Water_test_4_6"
		mesh.mesh = BoxMesh.new()
		world.add_child(mesh)
		mesh.set_surface_override_material(0, source)
		LookGround.decode_continent_sea(world)
		drawn[level] = mesh.get_surface_override_material(0) as ShaderMaterial
		world.free()
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	var soft := drawn[LookProfile.Quality.HIGH] as ShaderMaterial
	var opaque := drawn[LookProfile.Quality.LOW] as ShaderMaterial
	_expect(soft != null and soft.shader == LookGround.SHADER_WATER_SHORE
		and soft.render_priority == LookProfile.WATER_SHORE_PRIORITY,
		"the soft-edged sea draws at WATER_SHORE_PRIORITY (%d)" % (
			soft.render_priority if soft != null else 999))
	_expect(LookProfile.WATER_SHORE_PRIORITY < 0
		and LookProfile.WATER_SHORE_PRIORITY - 1 >= Material.RENDER_PRIORITY_MIN,
		"the sea sits below the default priority with room for the ground under it")
	_expect(opaque != null and opaque.shader.resource_path == LookGround.CONTINENT_WATER_PATH
		and opaque.render_priority == source.render_priority,
		"LOW's opaque sea keeps the loader's priority (it draws in the opaque pass)")
	_expect(source.render_priority == 0, "the loader's own sea material is never edited")
	# Inland water (an elevated lake or river cell, map polish round 4) is the
	# same material in the same place: the shader alone gives it its narrow
	# fade (LookProfile.WATER_SHORE_INLAND), by its continent height.
	var highland := Node3D.new()
	root.add_child(highland)
	var river := MeshInstance3D.new()
	river.name = "Water_test_5_6"
	river.mesh = BoxMesh.new()
	river.position = Vector3(0.0, 142.0, 0.0)
	highland.add_child(river)
	river.set_surface_override_material(0, source)
	LookGround.decode_continent_sea(highland)
	var inland := river.get_surface_override_material(0) as ShaderMaterial
	_expect(inland != null and soft != null and inland.shader == soft.shader
		and inland.render_priority == soft.render_priority
		and inland.get_shader_parameter(&"look_shore_inland") == LookProfile.WATER_SHORE_INLAND,
		"an inland water cell draws with the sea's shader at the sea's priority")
	highland.free()
	return soft.render_priority if soft != null else 0

func _patch(material_name: String, transparency: BaseMaterial3D.Transparency, tint: Color,
		priority := 0) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.resource_name = material_name
	material.transparency = transparency
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.albedo_color = tint
	material.vertex_color_use_as_albedo = true
	material.render_priority = priority
	return material

## Every painted blended ground copy draws before the sea; opaque copies keep
## their source's priority.
func _check_glazes(sea: int) -> void:
	var prepass := BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
	var cases := [
		["overlay (yard glaze)", _patch("authored_coilmere_yard-03", prepass, Color("9a8a6a")),
			LookGround.Kind.PATCH, LookGround.SHADER_OVERLAY],
		["pale paving (knob mole)", _patch("authored_coilmere_knob-mole-paving", prepass, Color("d8d0c0")),
			LookGround.Kind.PATCH, LookGround.SHADER_OVERLAY],
		["forest floor", _patch("authored_coilmere_th-forest2-23", prepass, Color("858066")),
			LookGround.Kind.PATCH, LookGround.SHADER_OVERLAY],
		["plain blend", _patch("authored_coilmere_sand-01", BaseMaterial3D.TRANSPARENCY_ALPHA,
			Color("c8b48a")), LookGround.Kind.PATCH, LookGround.SHADER_BLEND],
		["cut-out patch", _patch("authored_coilmere_scree-01", BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR,
			Color("8a8478")), LookGround.Kind.PATCH, LookGround.SHADER_CUTOUT],
		["walk deck (road)", _patch("authored_coilmere_road-01", prepass, Color("8a7050")),
			LookGround.Kind.DECK, LookGround.SHADER_DECK],
	]
	for row: Array in cases:
		var painted := LookGround.painted_source_for(row[1], row[2], true, "coilmere") as ShaderMaterial
		_expect(painted != null and painted.shader == row[3],
			"%s is painted with its blended shader" % row[0])
		if painted != null:
			_expect(painted.render_priority < sea,
				"%s draws before the sea (%d < %d)" % [row[0], painted.render_priority, sea])
	# Kit paving: an opaque deck the look feathers into a blended copy.
	var kit := StandardMaterial3D.new()
	kit.resource_name = "garden-paving-limestone"
	kit.albedo_color = Color("d8d0c0")
	var mesh := ArrayMesh.new()
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3(1, 0, 0), Vector3(0, 0, 1)])
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var kit_painted := LookGround.paint_kit_paving(kit, mesh, 0, "coilmere", Rect2()) as ShaderMaterial
	_expect(kit_painted != null and kit_painted.render_priority < sea,
		"kit paving's blended copy draws before the sea")
	# Opaque copies are not moved.
	for priority: int in [0, 3]:
		var ground := StandardMaterial3D.new()
		ground.resource_name = "continental_ground"
		ground.albedo_color = Color("6f7a4a")
		ground.vertex_color_use_as_albedo = true
		ground.render_priority = priority
		var opaque := LookGround.painted_source_for(ground, LookGround.Kind.TERRAIN, true, "coilmere") \
			as ShaderMaterial
		_expect(opaque != null and opaque.shader == LookGround.SHADER_OPAQUE
			and opaque.render_priority == priority,
			"opaque terrain keeps its source's priority (%d)" % priority)
	# The Mobile renderer's depth pre-pass rides on the copy at its priority.
	var deck := LookGround.painted_source_for(cases[5][1], LookGround.Kind.DECK, true, "coilmere") \
		as ShaderMaterial
	var pass_made := LookGround.mobile_prepass(deck, RendererFamily.MOBILE)
	_expect(pass_made != null and pass_made.render_priority == deck.render_priority
		and deck.render_priority < sea,
		"Mobile's deck pre-pass and its blended pass keep the deck's place before the sea")

## glaze_priority keeps the copies' order among themselves and every one of
## them under the sea, within Godot's range.
func _check_glaze_priority_range(sea: int) -> void:
	var last := Material.RENDER_PRIORITY_MIN - 1
	var ordered := true
	var under := true
	for source: int in range(Material.RENDER_PRIORITY_MIN, Material.RENDER_PRIORITY_MAX + 1):
		var shifted := LookGround.glaze_priority(source)
		ordered = ordered and shifted >= last
		under = under and shifted < sea and shifted >= Material.RENDER_PRIORITY_MIN
		last = shifted
	_expect(ordered and under, "glaze_priority is monotonic and always under the sea")
	_expect(LookGround.glaze_priority(0) == LookProfile.WATER_SHORE_PRIORITY - 1
		and LookGround.glaze_priority(-1) < LookGround.glaze_priority(0)
		and LookGround.glaze_priority(Material.RENDER_PRIORITY_MIN) == Material.RENDER_PRIORITY_MIN,
		"the continent's glazes (0) sit just under the sea, more negative sources stay apart")

## A road composite built on a painted glaze keeps the glaze's place.
func _check_road_composite(sea: int) -> void:
	var glaze := _patch("authored_coilmere_yard-03", BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS,
		Color("9a8a6a"))
	var base := LookGround.painted_source_for(glaze, LookGround.Kind.PATCH, true, "coilmere") \
		as ShaderMaterial
	var style := StandardMaterial3D.new()
	style.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	style.albedo_color = Color(0.3, 0.2, 0.1, 0.8)
	style.vertex_color_use_as_albedo = true
	var styles: Array[BaseMaterial3D] = [style]
	var road := LookGround.painted_source_for(style, LookGround.Kind.DECK, true, "coilmere") \
		as ShaderMaterial
	var sources := {"surface": FileAccess.get_file_as_string(Composite.SURFACE),
		"paint": FileAccess.get_file_as_string(Composite.PAINT)}
	var made: Dictionary = Composite.build(base, road, styles, true, {}, sources)
	var material := made.get("material") as ShaderMaterial
	_expect(bool(made.get("ok", false)) and material != null and material.render_priority < sea,
		"a road composite on a glaze draws before the sea (%s)" % str(made.get("error", "")))
	if material != null:
		var names: Array[String] = []
		for uniform: Dictionary in material.shader.get_shader_uniform_list():
			names.append(str(uniform["name"]))
		_expect("look_rim_steep" in names and "road_look_rim_steep" in names,
			"the composite parses with both halves' steep-face cut")

## Nothing outside the painted ground and the sea sorts under the default
## priority: every runtime render_priority the client assigns is a copy of a
## source's, a positive constant or 0. (The authoring pilot under src/dev
## orders its own regions from -128 and never meets the continent sea.)
func _check_effects_after(sea: int) -> void:
	_expect(StandardMaterial3D.new().render_priority > sea and ShaderMaterial.new().render_priority > sea,
		"an effect, marker or kit material at the default priority draws after the sea")
	var negative := RegEx.create_from_string(
		"render_priority\\s*=\\s*(-|Material\\.RENDER_PRIORITY_MIN|clampi\\s*\\(\\s*-)")
	var found: Array[String] = []
	for path: String in _scripts("res://src"):
		if path.begins_with("res://src/dev/"):
			continue
		var text := FileAccess.get_file_as_string(path)
		for line: String in text.split("\n"):
			if negative.search(line) != null:
				found.append("%s: %s" % [path, line.strip_edges()])
	_expect(found.is_empty(), "no runtime surface sorts under the sea: %s" % str(found))
	var glint := FileAccess.get_file_as_string("res://src/world/harvest_sparkle_3d.gd")
	var weather := FileAccess.get_file_as_string("res://src/world/weather_3d.gd")
	_expect(glint.contains("render_priority = 1") and not weather.contains("render_priority"),
		"the harvest glint (1) and the weather (0) draw after the sea")

func _scripts(directory: String) -> Array[String]:
	var paths: Array[String] = []
	for file: String in DirAccess.get_files_at(directory):
		if file.ends_with(".gd"):
			paths.append(directory.path_join(file))
	for child: String in DirAccess.get_directories_at(directory):
		paths.append_array(_scripts(directory.path_join(child)))
	return paths

func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures += 1
	push_error("test_look_sea_order: " + message)
	print("FAIL: " + message)
