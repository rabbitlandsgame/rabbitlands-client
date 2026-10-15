extends SceneTree
## Guards the look's switch and the graphics quality in the running client, on
## a real map loaded the way a player's is, through main's own settings path.
##
## The map is loaded with the look off, as develop draws it, and that is the
## reference: switched on, the map is painted, its sky painted and graded and
## its grass grown; switched off again, every mesh of every loaded root draws
## the very materials it drew before, the environment and the sun are what
## the binders made them, and no grass bed is left. Switching many times in a
## row, some in one frame, ends in the same two states and adds nothing. The
## quality reaches the grade's screen-space effects, the grass and the sun's
## cascades at once.
##
## ELORIA_LOOK_LIVE_MAPS picks the maps (registry ids, comma-separated). The
## default is lantern_reach, the smallest outdoor map that has a scene script,
## a sea decoded in place, painted ground, grass and a painted sky. A continent
## map (amberwood, four_gates) brings its chunks and neighbours in too, for a
## minute or two of loading; an interior (four-gates-mirrorsmith-forge, which
## the look leaves alone, or crownwater_insides, sunlit and graded but with
## its void kept dark) checks that the switch leaves those as they should be.
## The shadows switch is checked on each map too: it has to hold over the
## hour and the border blend, which rewrite the sun's flag.
##
## Each map is then loaded twice more, for the player's own paths: with the
## look on, as a new installation loads it (the loader paints on its workers,
## or reads the map cache), which must draw what the live switch drew; then
## switched off, which must draw what a load with the look off draws. Those
## compare across loads, whose materials are new objects, so they compare what
## each mesh draws by kind (`_material_signature`) rather than by identity.
## ELORIA_LOOK_LIVE_RELOAD=0 skips them.
##
## Run with ELORIA_LOOK and ELORIA_LOOK_QUALITY unset. The switch goes through
## main's settings path, which writes user://eloria_hud.cfg, so the player's
## file is copied first and put back after.

const SETTINGS_PATH := "user://eloria_hud.cfg"
const MAPS_VARIABLE := "ELORIA_LOOK_LIVE_MAPS"
const RELOAD_VARIABLE := "ELORIA_LOOK_LIVE_RELOAD"
## Where the traveller stands on each map the test knows (its spawn or a view
## the reviews use).
const PLACES := {
	"lantern_reach": Vector2(17.0, -20.0),
	"amberwood": Vector2(-28.0, 100.7),
	"four_gates": Vector2(0.0, 150.0),
}
## Environment properties the switch has to give back exactly.
const ENVIRONMENT_PROPERTIES := ["background_mode", "background_energy_multiplier",
	"tonemap_mode", "tonemap_exposure", "tonemap_white", "adjustment_enabled",
	"adjustment_brightness", "adjustment_contrast", "adjustment_saturation",
	"adjustment_color_correction", "glow_enabled", "ssao_enabled", "ssil_enabled",
	"fog_enabled", "fog_mode", "fog_density", "fog_light_color", "fog_light_energy",
	"fog_sky_affect", "fog_aerial_perspective", "fog_depth_begin", "fog_depth_end",
	"ambient_light_source", "ambient_light_color", "ambient_light_energy",
	"ambient_light_sky_contribution"]

var failures := 0
var main: Control
var state: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var saved_settings: PackedByteArray = FileAccess.get_file_as_bytes(SETTINGS_PATH) \
		if FileAccess.file_exists(SETTINGS_PATH) else PackedByteArray()
	var had_settings := FileAccess.file_exists(SETTINGS_PATH)
	var saved_variables := {}
	for variable: String in [LookProfile.ENABLE_VARIABLE, LookProfile.QUALITY_VARIABLE]:
		saved_variables[variable] = OS.get_environment(variable)
		OS.unset_environment(variable)
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	state = root.get_node("AppState")
	state.set("authenticated", true)
	main.get("login_panel").hide()
	main.get("creation_panel").hide()
	main.get("game_view").show()
	state.call("_on_packet", 5, PackedByteArray([180, 0]))
	# Nothing fades in front of the traveller: a fade swaps materials too, and
	# this compares materials.
	main.call("_on_show_through_obstacles_toggled", false)
	_setting("quality", LookProfile.Quality.HIGH)
	_setting("look", false)

	var maps := OS.get_environment(MAPS_VARIABLE).split(",", false)
	if maps.is_empty():
		maps = PackedStringArray(["lantern_reach"])
	for map_id: String in maps:
		if not await _load(map_id.strip_edges()):
			failures += 1
			continue
		await _check_map(map_id.strip_edges())

	main.call("_on_disconnect_pressed")
	main.get("exterior_stream").clear()
	while not main.get("exterior_stream").is_idle():
		await process_frame
	for frame: int in 6:
		await process_frame
	main.queue_free()
	await process_frame
	if had_settings:
		var file := FileAccess.open(SETTINGS_PATH, FileAccess.WRITE)
		file.store_buffer(saved_settings)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))
	for variable: String in saved_variables:
		if str(saved_variables[variable]).is_empty():
			OS.unset_environment(variable)
		else:
			OS.set_environment(variable, str(saved_variables[variable]))
	print("look live tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(1 if failures > 0 else 0)

func _check_map(map_id: String) -> void:
	var reference := _snapshot()
	_expect(reference.look_surfaces == 0 and reference.beds == 0,
		"%s: loaded with the look off, nothing of the look's is drawn" % map_id)

	# An interior with no sun is neither painted nor graded, only faded as
	# develop fades it; one with a sun is graded, and its sky painted unless
	# its region file keeps its void dark (sky.paint 0).
	var manifest: WorldManifest = (main.get("world_loader") as WorldLoader).manifest
	var outdoor := LookGround.outdoor(manifest)
	var sky_painted := outdoor and LookProfile.sky_painted(manifest.asset_id())
	_setting("look", true)
	await _frames(20)
	var painted := _snapshot()
	if outdoor:
		_expect(painted.environment.tonemap_mode == Environment.TONE_MAPPER_AGX
			and (painted.sky == "ShaderMaterial") == sky_painted,
			"%s: switched on, the map is graded%s" % [map_id,
				" and its sky painted" if sky_painted else ", its void left dark"])
		_expect(painted.look_surfaces > 0,
			"%s: and painted (%d surfaces)" % [map_id, painted.look_surfaces])
	else:
		_expect(painted.look_surfaces == 0 and painted.environment == reference.environment,
			"%s: an interior without a sun is neither painted nor graded" % map_id)
	# The bed node is made on any map the look is on; it grows only outdoors.
	_expect(painted.beds == 1, "%s: one grass bed (%d)" % [map_id, painted.beds])

	_setting("look", false)
	await _frames(20)
	_compare(map_id + ": switched off", _snapshot(), reference)

	# Many switches, several of them in one frame.
	for turn: int in 7:
		_setting("look", turn % 2 == 0)
		if turn % 3 == 2:
			await process_frame
	await _frames(20)
	var again := _snapshot()
	_expect(LookProfile.enabled() and again.look_surfaces == painted.look_surfaces
		and again.beds == 1 and again.twins == 0 and again.nodes == painted.nodes,
		"%s: after switching over and over it is painted as the first time, one grass bed, no extra node (%d/%d surfaces, %d/%d nodes)"
			% [map_id, again.look_surfaces, painted.look_surfaces, again.nodes, painted.nodes])

	# The quality while the look is on.
	_setting("quality", LookProfile.Quality.LOW)
	await _frames(10)
	var low: Dictionary = LookProfile.QUALITY_PRESETS[LookProfile.Quality.LOW]
	var environment: Environment = (main.get("world_environment") as WorldEnvironment).environment
	var sun: DirectionalLight3D = main.get("world_sun")
	var graded := outdoor
	_expect((not graded or (environment.glow_enabled == bool(low.glow)
			and environment.ssao_enabled == (bool(low.ssao) and LookProfile.screen_space_effects())
			and environment.ssil_enabled == (bool(low.ssil) and LookProfile.screen_space_effects())))
		and _beds() == (1 if bool(low.grass) else 0)
		and sun.directional_shadow_mode == _shadow_mode(int(low.shadow_splits)),
		"%s: LOW reaches the grade, the grass and the sun's cascades at once" % map_id)
	_setting("quality", LookProfile.Quality.HIGH)
	await _frames(10)
	_expect(environment == (main.get("world_environment") as WorldEnvironment).environment
		and (not graded or (environment.glow_enabled
			and environment.ssao_enabled == LookProfile.screen_space_effects()))
		and _beds() == 1 and sun.directional_shadow_mode == DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS,
		"%s: and HIGH brings it all back, in the same environment" % map_id)

	# The shadows switch holds over the binders, which rewrite the sun's flag
	# on every clock packet and border update.
	_setting("shadows", false)
	main.call("_apply_day_night")
	main.call("_update_border_lighting")
	await _frames(5)
	_expect(not sun.shadow_enabled,
		"%s: directional shadows switched off stay off through the hour and the borders" % map_id)
	_setting("shadows", true)

	_setting("look", false)
	await _frames(20)
	_compare(map_id + ": off at last", _snapshot(), reference)
	if OS.get_environment(RELOAD_VARIABLE) != "0":
		await _check_loads(map_id, painted)

## The player's default path and its reverse, on the same map loaded again:
## loaded with the look on it must draw what the live switch drew on the look
## off load (`painted`); switched off, what a load with the look off draws;
## and switched on again from there, what the load with the look on drew.
func _check_loads(map_id: String, painted: Dictionary) -> void:
	_setting("look", true)
	if not await _reload(map_id):
		return
	var loaded_on := _snapshot()
	_compare_loads(map_id + ": switched on live, against loaded with the look on",
		painted, loaded_on)
	_setting("look", false)
	await _frames(20)
	var switched_off := _snapshot()
	if not await _reload(map_id):
		return
	var loaded_off := _snapshot()
	# The kinds have to tell the look from its absence, or the comparisons
	# here would pass on anything (an interior without a sun is not painted).
	_expect(painted.look_surfaces == 0 or loaded_off.signatures != loaded_on.signatures,
		"%s: what a mesh draws by kind tells the look on from off" % map_id)
	_compare_loads(map_id + ": loaded with the look on and switched off, against loaded with it off",
		switched_off, loaded_off)
	_setting("look", true)
	await _frames(20)
	_compare_loads(map_id + ": loaded with the look off and switched on, against loaded with it on",
		_snapshot(), loaded_on)
	_setting("look", false)
	await _frames(20)

## Two states of two different loads: every mesh both loads hold draws the
## same kind of material in every slot, the environment, sky and sun are the
## same, and so are the look's counts. A continent map's outermost chunks and
## neighbours may differ between loads with the streams' timing, so the meshes
## are compared where both loads have them, and the rest is only reported.
func _compare_loads(label: String, now: Dictionary, reference: Dictionary) -> void:
	var different: Array[String] = []
	var shared := 0
	for path: String in reference.signatures:
		if not now.signatures.has(path):
			continue
		shared += 1
		if now.signatures[path] != reference.signatures[path]:
			different.append(path)
	var only_now: int = now.signatures.size() - shared
	var only_reference: int = reference.signatures.size() - shared
	for state: Dictionary in [now, reference]:
		if state.signatures.size() != state.materials.size():
			print("NOTE %s: roots share a map id, %d of %d meshes compared"
				% [label, state.signatures.size(), state.materials.size()])
	if only_now > 0 or only_reference > 0:
		print("NOTE %s: %d meshes only in the first, %d only in the second"
			% [label, only_now, only_reference])
	_expect(shared > 0 and different.is_empty(),
		"%s, every mesh draws the same kind of material (%d meshes; differ: %s)"
			% [label, shared, str(different.slice(0, 6))])
	if not different.is_empty():
		var first := different[0]
		print("  %s\n    now       %s\n    reference %s"
			% [first, str(now.signatures[first]), str(reference.signatures[first])])
	var properties: Array[String] = []
	for property: String in reference.environment:
		if now.environment[property] != reference.environment[property]:
			properties.append("%s %s!=%s" % [property, now.environment[property],
				reference.environment[property]])
	_expect(properties.is_empty() and now.sky == reference.sky
		and now.sky_meta == reference.sky_meta,
		"%s, the same environment: %s (sky %s against %s)"
			% [label, str(properties), now.sky, reference.sky])
	_expect(now.sun == reference.sun, "%s, and the same sun: %s against %s"
		% [label, str(now.sun), str(reference.sun)])
	_expect(now.beds == reference.beds and now.twins == reference.twins
		and (now.look_surfaces == 0) == (reference.look_surfaces == 0),
		"%s, and the same grass beds, twins and look (%d/%d beds, %d/%d look surfaces)"
			% [label, now.beds, reference.beds, now.look_surfaces, reference.look_surfaces])

## Loads the map the test is on again, from nothing, as a new session would.
func _reload(map_id: String) -> bool:
	main.set("loaded_server_map", "")
	if await _load(map_id):
		return true
	failures += 1
	return false

## What a material draws, by kind: its class, name, shader and the few
## properties the look changes, and for one of the look's stand-ins the same
## of the material it stands in for. Not the object, which every load makes
## anew, nor its resource path, which a map read from the cache carries and a
## freshly built one does not.
func _material_signature(material: Material, follow_source := true) -> Array:
	if material == null:
		return []
	var shader_path := ""
	var decoded: Variant = null
	var shader_material := material as ShaderMaterial
	if shader_material != null:
		if shader_material.shader != null \
				and shader_material.shader.resource_path.begins_with("res://"):
			shader_path = shader_material.shader.resource_path.get_slice("::", 0)
		decoded = shader_material.get_shader_parameter(&"look_decode_albedo")
	var standard := material as BaseMaterial3D
	var signature: Array = [material.get_class(), material.resource_name, shader_path, decoded]
	if standard != null:
		signature.append_array([standard.albedo_color, standard.transparency,
			standard.albedo_texture.get_size() if standard.albedo_texture != null else Vector2.ZERO])
	if follow_source and material.has_meta(LookProfile.SOURCE_META):
		signature.append(_material_signature(LookSwitch.source_of(material), false))
	return signature

## Everything the switch must give back, and what it adds.
func _snapshot() -> Dictionary:
	var loader: WorldLoader = main.get("world_loader")
	var materials := {}
	var signatures := {}
	var look_surfaces := 0
	var nodes := 0
	var twins := 0
	for world: Dictionary in LookSwitch.worlds(loader.world_root, loader.manifest,
			(main.get("exterior_stream") as ExteriorRegionStream).residents):
		var world_root := world.root as Node
		look_surfaces += LookSwitch.look_surfaces(world_root)
		var all := world_root.find_children("*", "", true, false)
		nodes += all.size()
		for node: Node in all:
			if node.name == LookFade.SHADOW_TWIN_NAME:
				twins += 1
			var geometry := node as GeometryInstance3D
			if geometry == null:
				continue
			var entry := [geometry.material_override, geometry.cast_shadow]
			# Not the node's visibility: an interior's cutaway hides its roof by
			# where the traveller stands, which settles differently per load.
			var signature := [geometry.get_class(), geometry.cast_shadow,
				_material_signature(geometry.material_override)]
			if node is MeshInstance3D:
				for surface: int in (node as MeshInstance3D).get_surface_override_material_count():
					var surface_material := (node as MeshInstance3D).get_surface_override_material(surface)
					entry.append(surface_material)
					signature.append(_material_signature(surface_material))
			if geometry.material_override is ShaderMaterial:
				entry.append((geometry.material_override as ShaderMaterial).get_shader_parameter(
					&"look_decode_albedo"))
			var relative := String(world_root.get_path_to(node))
			materials[String(world_root.name) + "/" + relative] = entry
			# Across loads a root is known by what it was loaded from: the
			# root of a map loaded again is added while the old one is still
			# being freed, and comes back renamed.
			signatures[(world.manifest as WorldManifest).asset_id() + "/" + relative] = signature
	var environment: Environment = (main.get("world_environment") as WorldEnvironment).environment
	var properties := {}
	for property: String in ENVIRONMENT_PROPERTIES:
		properties[property] = environment.get(property)
	var sun: DirectionalLight3D = main.get("world_sun")
	return {"materials": materials, "signatures": signatures,
		"look_surfaces": look_surfaces, "nodes": nodes,
		"twins": twins, "beds": _beds(), "environment": properties,
		"sky": environment.sky.sky_material.get_class() if environment.sky != null \
			and environment.sky.sky_material != null else "none",
		"sky_meta": environment.has_meta(LookSky.PAINTED_META),
		"sun": [sun.light_color, sun.light_energy, sun.shadow_enabled,
			sun.directional_shadow_mode, sun.get_meta_list()]}

func _compare(label: String, now: Dictionary, reference: Dictionary) -> void:
	var different: Array[String] = []
	for path: String in reference.materials:
		if now.materials.get(path) != reference.materials[path]:
			different.append(path)
	_expect(different.is_empty() and now.materials.size() == reference.materials.size(),
		"%s, every mesh draws the materials it drew before (%d meshes; differ: %s)"
			% [label, reference.materials.size(), str(different.slice(0, 6))])
	var properties: Array[String] = []
	for property: String in reference.environment:
		if now.environment[property] != reference.environment[property]:
			properties.append("%s %s!=%s" % [property, now.environment[property],
				reference.environment[property]])
	_expect(properties.is_empty() and now.sky == reference.sky and not now.sky_meta,
		"%s, the environment is the binders' again: %s (sky %s)" % [label, str(properties), now.sky])
	_expect(now.sun == reference.sun, "%s, and so is the sun: %s against %s"
		% [label, str(now.sun), str(reference.sun)])
	_expect(now.look_surfaces == 0 and now.beds == 0 and now.twins == 0
		and now.nodes == reference.nodes,
		"%s, nothing of the look's is left and no node was added (%d look surfaces, %d beds, %d/%d nodes)"
			% [label, now.look_surfaces, now.beds, now.nodes, reference.nodes])

## The switch through main's own settings path, as the window sends it.
func _setting(key: String, value: Variant) -> void:
	main.call("_on_client_setting_changed", "Graphics", key, value)

func _beds() -> int:
	var world_root: Node = main.get("world_root")
	var count := 0
	for child: Node in world_root.get_children():
		if child is LookGrassBeds:
			count += 1
	return count

func _shadow_mode(splits: int) -> DirectionalLight3D.ShadowMode:
	match splits:
		1:
			return DirectionalLight3D.SHADOW_ORTHOGONAL
		2:
			return DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
	return DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS

func _frames(count: int) -> void:
	for frame: int in count:
		await physics_frame
		await process_frame

## The survey's own sequence: switch map, place the traveller, settle, then
## wait until every selected cell of the active territory is resident.
func _load(map_id: String) -> bool:
	state.set("actors", {})
	state.set("local_actor_id", -1)
	state.set("current_map", map_id)
	main.call("_load_server_map")
	var loader: WorldLoader = main.get("world_loader")
	var deadline := Time.get_ticks_msec() + 180000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	if loader.world_root == null:
		push_error("Map failed to load: " + map_id)
		return false
	var place: Vector2 = PLACES.get(map_id, Vector2.ZERO)
	var adapter: CoordinateAdapter = main.get("adapter")
	var tile: Vector2i = adapter.godot_to_server(Vector3(place.x, 0, place.y))
	state.set("local_actor_id", 1)
	state.set("actors", {1: {"actor_id": 1, "x": tile.x, "y": tile.y, "rotation": 0,
		"actor_type": 0, "kind": 1, "name": "Traveller", "health": 100, "max_health": 100,
		"alive": true, "appearance": {}}})
	state.call("mark_all_actors_changed")
	main.call("_sync_world")
	await _frames(60)
	deadline = Time.get_ticks_msec() + 120000
	var stream: ExteriorRegionStream = main.get("exterior_stream")
	while not (_chunks_ready(loader.world_root) and stream.is_idle()) \
			and Time.get_ticks_msec() < deadline:
		await process_frame
	await _frames(30)
	return true

func _chunks_ready(active: Node3D) -> bool:
	if not active is ContinentChunkStream:
		return true
	var chunks := active as ContinentChunkStream
	if not chunks.has_focus or chunks._thread != null or not chunks._retiring.is_empty():
		return false
	for entry: Dictionary in chunks.selection(chunks.focus, true):
		if float(entry.distance) <= chunks.preload_distance and not chunks.cells.has(str(entry.id)):
			return false
	return true

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS " + message)
	else:
		failures += 1
		print("FAIL " + message)
