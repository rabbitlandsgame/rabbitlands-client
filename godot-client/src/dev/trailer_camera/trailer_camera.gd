extends Node3D
## Dev-only trailer camera: flies a Camera3D along a keyframed shot file over a
## served map loaded offline, the way tests/integration/rendered_*.gd load
## one (WorldLoader.load_world, WorldEnvironmentBinder.apply, the look pass and
## the hour). Nothing in the game reaches this scene. README.md beside it has
## the shot format and the render commands.
##
## Run it with user arguments after `--`:
##   --shot=<file>       the shot file (res://, absolute, or relative to the
##                       working directory); default `shot_path` below
##   --preview=<dir>     write one still per key and between keys, then quit
##   --fly               free camera for authoring; K prints a key
##   --loop              replay the shot instead of quitting at its end
## Under Movie Maker (`--write-movie`) the shot plays once at the fixed frame
## rate and the scene quits; every map chunk and neighbour the path sees is
## made resident before the first frame of the shot and streaming is paused,
## so nothing streams in while frames are written.

const TrailerShot := preload("res://src/dev/trailer_camera/trailer_shot.gd")
const REGISTRY_PATH := "res://data/maps/registry.json"
const DEFAULT_RESIDENT_MIB := 6144
const DEFAULT_STREAM_RADIUS := 240.0
const DEFAULT_NEIGHBOUR_RADIUS := 300.0
const DEFAULT_MAX_NEIGHBOURS := 4
## Frames held on the first key before the shot's clock starts: grass beds,
## ambient animals and screen-space effects settle on the opening frame. Under
## Movie Maker these are written too; the summary and the sidecar say how many
## to trim.
const DEFAULT_PREROLL_SECONDS := 1.0
## The ground under a key is searched from this far above its y downwards
## (and from high above as a fallback), so a key under an arch finds the road
## rather than the arch's top.
const GROUND_PROBE_ABOVE := 3.0
const GROUND_PROBE_FALLBACK := 600.0
const FLY_SPEED := 12.0
const MSAA := {0: Viewport.MSAA_DISABLED, 2: Viewport.MSAA_2X, 4: Viewport.MSAA_4X, 8: Viewport.MSAA_8X}

@export_file("*.json") var shot_path := "res://src/dev/trailer_camera/shots/landfall_north_gate.json"

var shot: TrailerShot
var _arguments: Dictionary = {}
var _camera: Camera3D
var _sun: DirectionalLight3D
var _moon: DirectionalLight3D
var _world_environment: WorldEnvironment
var _lighting: WorldManifest
var _active: Dictionary = {}
## Neighbouring regions shown around the active one, by map id: {root, manifest}
## as LookGrassBeds reads exterior residents.
var _residents: Dictionary = {}
var _fixed_fps := 0
var _movie_path := ""
var _state := "loading"
var _frame := 0
var _clock := 0.0
var _shot_frames := 0
var _preroll_left := 0
var _frames_at := {}
var _minute := NAN
var _fog_wanted := true
var _fly_yaw := 0.0
var _fly_pitch := 0.0
var _fly_speed := FLY_SPEED
var _fly_label: Label
var _sun_bearing := NAN

func _ready() -> void:
	_arguments = _user_arguments()
	_fixed_fps = _engine_fixed_fps()
	_movie_path = Engine.get_write_movie_path()
	var path := str(_arguments.get("shot", shot_path))
	if not path.begins_with("res://") and not path.is_absolute_path():
		path = _repository_path(path)
	shot = TrailerShot.new()
	if not shot.load_file(path):
		_fail(shot.errors)
		return
	print("trailer shot=%s file=%s movie=%s fixed_fps=%d window=%s" % [shot.name, path,
		_movie_path if not _movie_path.is_empty() else "-", _fixed_fps, get_window().size])
	_check_resolution()
	_configure_look()
	_build_stage()
	_active = _load_region(str(shot.data.map))
	if _active.is_empty():
		_fail(["map %s did not load" % shot.data.map])
		return
	_lighting = _lighting_manifest(_active.manifest)
	_bind_environment()
	# Physics needs a step before the ground under a key can be found.
	_hold_streams(_raw_key_points())
	for unused: int in range(3):
		await get_tree().physics_frame
	var adapter: CoordinateAdapter = (_active.manifest as WorldManifest).coordinate_adapter()
	if not shot.resolve(func(tile: Vector2) -> Vector3: return adapter.tile_center(int(tile.x), int(tile.y)),
			_ground_at):
		_fail(shot.errors)
		return
	# The resolved path can reach a little past the keys; hold what it sees.
	_hold_streams(shot.samples())
	_place_neighbours()
	_show_whole_region(_active.root)
	_populate()
	_apply_pose(shot.evaluate(0.0))
	print("trailer path duration=%.2fs keys=%d" % [shot.duration, shot.keys.size()])
	if _arguments.has("preview"):
		await _write_previews(str(_arguments.preview))
		await _finish(0)
		return
	if _arguments.has("fly"):
		_start_fly()
		return
	_preroll_left = int(round(float(shot.data.get("preroll", DEFAULT_PREROLL_SECONDS)) * _frame_rate()))
	_shot_frames = maxi(1, int(round(shot.duration * _frame_rate())))
	_frames_at.preroll = Engine.get_frames_drawn()
	_state = "preroll"

func _process(delta: float) -> void:
	match _state:
		"preroll":
			_tend(shot.evaluate(0.0))
			_preroll_left -= 1
			if _preroll_left <= 0:
				_state = "playing"
				_frame = 0
				_clock = 0.0
				_frames_at.shot = Engine.get_frames_drawn()
				_play_frame()
		"playing":
			_frame += 1
			_clock += delta
			if _frame >= _shot_frames if _fixed_fps > 0 else _clock >= shot.duration:
				if _arguments.has("loop") and _movie_path.is_empty():
					_frame = 0
					_clock = 0.0
				else:
					_state = "done"
					_frames_at.done = Engine.get_frames_drawn()
					_finish(0)
					return
			_play_frame()
		"fly":
			_fly(delta)

## The camera on shot frame `_frame`: exactly frame / fps into the shot under
## a fixed frame rate (Movie Maker), real time otherwise.
func _play_frame() -> void:
	var time := float(_frame) / float(_fixed_fps) if _fixed_fps > 0 else _clock
	var pose := shot.evaluate(time)
	_apply_pose(pose)
	_tend(pose)

func _apply_pose(pose: Dictionary) -> void:
	var position: Vector3 = pose.position
	var target: Vector3 = pose.target
	_camera.fov = float(pose.fov)
	var up := Vector3.UP if absf((target - position).normalized().dot(Vector3.UP)) < 0.999 else Vector3.BACK
	_camera.look_at_from_position(position, target, up)
	if not is_zero_approx(float(pose.roll)):
		_camera.rotate_object_local(Vector3.BACK, deg_to_rad(float(pose.roll)))
	var minute := float(pose.minute)
	if not is_equal_approx(minute, _minute) and not (is_nan(minute) and is_nan(_minute)):
		_minute = minute
		_apply_hour()

## Grass grows around a ground point towards what the camera looks at, as it
## grows around the game camera's focus.
func _tend(pose: Dictionary) -> void:
	var position: Vector3 = pose.position
	var target: Vector3 = pose.target
	var reach := minf(position.distance_to(target), 40.0)
	var focus := position + (target - position).normalized() * reach
	var ground := _ground_at(focus)
	if not is_nan(ground):
		focus.y = ground
	LookGrassBeds.tend(self, _active.root, _active.manifest, _residents, focus)

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------

func _configure_look() -> void:
	# The look and quality the game would draw with; ELORIA_LOOK and
	# ELORIA_LOOK_QUALITY still override both, as they do in the game.
	LookProfile.set_player_look(bool(shot.data.get("paintedLook", true)))
	var level := LookProfile.quality_named(str(shot.data.get("quality", "high")))
	LookProfile.set_player_quality(level if level >= 0 else LookProfile.QUALITY_DEFAULT)
	var viewport := get_viewport()
	viewport.msaa_3d = MSAA.get(int(shot.data.get("msaa", 0)), Viewport.MSAA_DISABLED)
	viewport.use_taa = bool(shot.data.get("taa", false))

func _build_stage() -> void:
	_world_environment = WorldEnvironment.new()
	_world_environment.environment = Environment.new()
	add_child(_world_environment)
	_sun = DirectionalLight3D.new()
	_sun.name = "Sun"
	_sun.shadow_enabled = true
	add_child(_sun)
	_moon = DirectionalLight3D.new()
	_moon.name = "Moon"
	_moon.light_energy = 0.0
	_moon.shadow_enabled = false
	add_child(_moon)
	_camera = Camera3D.new()
	_camera.name = "TrailerCamera"
	_camera.near = float(shot.data.get("near", 0.1))
	_camera.far = float(shot.data.get("far", 3000.0))
	_camera.current = true
	add_child(_camera)

## Loads one region the way the game does and returns {id, root, manifest,
## loader, frame, translation}; empty when it fails. `map` is a registry id or
## a world.json path (which places no neighbours: it names no frame).
func _load_region(map: String) -> Dictionary:
	var manifest_path := map
	var map_id := map
	var registered: Dictionary = {}
	if not map.ends_with(".json"):
		registered = MapRegistry.resolve(_registry(), map)
		manifest_path = str(registered.get("manifest", ""))
		map_id = str(registered.get("registryKey", map))
	if manifest_path.begins_with("res://"):
		manifest_path = ProjectSettings.globalize_path(manifest_path)
	if manifest_path.is_empty() or not FileAccess.file_exists(manifest_path):
		push_error("trailer: no manifest for map %s (%s)" % [map, manifest_path])
		return {}
	var loader := WorldLoader.new()
	loader.name = "WorldLoader_" + map_id
	add_child(loader)
	var began := Time.get_ticks_msec()
	# Chunked territories wait for the shot to say where to prime them.
	loader.load_world(manifest_path, Vector3.INF, true)
	if loader.world_root == null:
		return {}
	var manifest := loader.manifest
	# A manifest carries its translation; only the registry names the
	# continent frame it belongs to, so the registry's geography wins.
	var geography: Dictionary = (manifest.data.get("continentGeography", {}) as Dictionary).duplicate()
	geography.merge(registered.get("continentGeography", {}) as Dictionary, true)
	var raw_translation: Array = geography.get("translation", []) as Array
	print("trailer loaded map=%s chunked=%s in %d ms" % [map_id, loader.world_root is ContinentChunkStream,
		Time.get_ticks_msec() - began])
	return {"id": map_id, "root": loader.world_root, "manifest": manifest, "loader": loader,
		"frame": str(geography.get("frame", "")),
		"translation": Vector3(float(raw_translation[0]), float(raw_translation[1]),
			float(raw_translation[2])) if raw_translation.size() == 3 else Vector3.INF}

func _registry() -> Dictionary:
	var document: Variant = JSON.parse_string(FileAccess.get_file_as_string(REGISTRY_PATH))
	return (document as Dictionary).get("maps", {}) as Dictionary if document is Dictionary else {}

## The manifest whose environment lights the shot, with the shot's variant
## ("golden-hour" and the like) merged over it.
func _lighting_manifest(manifest: WorldManifest) -> WorldManifest:
	var variant := str(shot.data.get("environmentVariant", ""))
	if variant.is_empty():
		return manifest
	var environment: Dictionary = (manifest.data.get("environment", {}) as Dictionary).duplicate(true)
	var variants: Dictionary = environment.get("variants", {}) as Dictionary
	if not variants.has(variant):
		push_warning("trailer: map has no environment variant %s; using its own light" % variant)
		return manifest
	environment.merge(variants[variant] as Dictionary, true)
	var shim := WorldManifest.new()
	shim.data = manifest.data.duplicate()
	shim.data.environment = environment
	shim.source_path = manifest.source_path
	return shim

func _bind_environment() -> void:
	WorldEnvironmentBinder.apply(_lighting, _world_environment, _sun, self)
	LookSky.install(_lighting, _world_environment)
	LookGround.paint_bound(_active.root, _active.manifest)
	LookSwitch.apply_shadow_quality(_sun)
	_sun.directional_shadow_max_distance = float(shot.data.get("shadowDistance", 200.0))
	_fog_wanted = _world_environment.environment.fog_enabled and bool(shot.data.get("fog", true))
	if shot.data.get("sunBearing") is float:
		_sun_bearing = float(shot.data.sunBearing)
	_minute = float(shot.data.gameMinute) if shot.data.get("gameMinute") is float else NAN
	_apply_hour()
	if bool(shot.data.get("lightMarkers", true)):
		var lights := Node3D.new()
		lights.name = "MapLights"
		add_child(lights)
		LightMarkerBinder.apply(_active.manifest, lights)

## The hour, as main.gd's _apply_day_night lays it over the map's own light:
## the server's daylight curve, then the look's grade and painted sky. A shot
## without a gameMinute keeps the map's authored (noon) light.
func _apply_hour() -> void:
	if not is_nan(_sun_bearing):
		# The compass bearing the sun stands at; the light travels the other way.
		_sun.rotation_degrees.y = 180.0 - _sun_bearing
	if not is_nan(_minute):
		DayNightBinder.apply(_lighting, _world_environment, _sun, _minute, _moon)
	LookGrade.apply(_lighting, _world_environment, _sun)
	LookSky.apply(_lighting, _world_environment, 180.0 if is_nan(_minute) else _minute)
	_world_environment.environment.fog_enabled = _fog_wanted

## Makes every chunk within the shot's stream radius of `points` resident now,
## synchronously, then pauses the stream so nothing loads or retires while the
## shot plays. A non-chunked region is resident whole already. Collision of
## a cell installed here is usable after the next physics frame.
func _hold_streams(points: PackedVector3Array) -> void:
	for region: Dictionary in [_active] + _residents.values():
		if region.root is not ContinentChunkStream:
			continue
		var offset: Vector3 = region.get("offset", Vector3.ZERO)
		var local := PackedVector3Array()
		for point: Vector3 in points:
			local.append(point - offset)
		_hold_chunks(region.root as ContinentChunkStream, local, str(region.id))

func _hold_chunks(stream: ContinentChunkStream, points: PackedVector3Array, map_id: String) -> void:
	var radius := float(shot.data.get("streamRadius", DEFAULT_STREAM_RADIUS))
	if not stream.has_meta("trailer_all_entries"):
		stream.set_meta("trailer_all_entries", stream.entries.duplicate())
	var wanted: Array[Dictionary] = []
	for entry: Dictionary in stream.get_meta("trailer_all_entries") as Array:
		for point: Vector3 in points:
			if ContinentChunkStream.bounds_distance(point, entry.bounds) <= radius:
				wanted.append(entry)
				break
	if wanted.is_empty():
		return
	# Only the cells this shot sees are candidates, all of them within reach
	# and under one budget, so prime() installs every one synchronously.
	stream.entries.assign(wanted)
	stream.preload_distance = 1.0e9
	stream.retain_distance = 1.0e9
	stream.maximum_chunks = 1 << 20
	stream.maximum_resident_bytes = int(shot.data.get("residentBudgetMiB", DEFAULT_RESIDENT_MIB)) * 1048576
	var began := Time.get_ticks_msec()
	stream.has_focus = false
	stream.prime(points[0])
	stream.pause_streaming()
	print("trailer chunks map=%s resident=%d of %d wanted (%d in territory) est_mib=%d in %d ms" % [
		map_id, stream.cells.size(), wanted.size(), (stream.get_meta("trailer_all_entries") as Array).size(),
		stream.resident_bytes / 1048576, Time.get_ticks_msec() - began])
	if stream.cells.size() < wanted.size():
		push_warning("trailer: %d chunks of %s did not fit residentBudgetMiB and will be missing" % [
			wanted.size() - stream.cells.size(), map_id])

## Key positions before the ground is known: enough to choose chunks, which
## are picked by horizontal distance.
func _raw_key_points() -> PackedVector3Array:
	var adapter: CoordinateAdapter = (_active.manifest as WorldManifest).coordinate_adapter()
	var points := PackedVector3Array()
	for key: Dictionary in shot.keys:
		for field: String in ["position", "target"]:
			var value: Variant = key.get(field)
			if value is Vector3 and (value as Vector3).is_finite():
				points.append(value)
		for field: String in ["tile", "target_tile"]:
			if key.has(field):
				points.append(adapter.tile_center(int(key[field].x), int(key[field].y)))
	return points

## Other regions of the same continent near the path, placed by their
## continent translations, so a flyover does not end at the map's edge.
## `neighbours` is a list of map ids, or "auto" for every region within
## neighbourRadius of the path (nearest first, at most maxNeighbours).
func _place_neighbours() -> void:
	var wanted: Variant = shot.data.get("neighbours", [])
	if not _active.translation.is_finite() or (wanted is Array and (wanted as Array).is_empty()):
		return
	var ids: Array[String] = []
	if str(wanted) == "auto":
		ids = _nearby_regions()
	elif wanted is Array:
		for value: Variant in wanted as Array:
			ids.append(str(value))
	for map_id: String in ids:
		var region := _load_region(map_id)
		if region.is_empty():
			continue
		if region.frame != _active.frame or not (region.translation as Vector3).is_finite():
			push_warning("trailer: %s is not on %s's continent" % [map_id, _active.id])
			(region.loader as Node).queue_free()
			continue
		var offset: Vector3 = region.translation - _active.translation
		region.offset = offset
		(region.loader as Node3D).position = offset
		_show_whole_region(region.root)
		_residents[region.id] = region
		print("trailer neighbour=%s offset=%s" % [region.id, offset])
	if not _residents.is_empty():
		_hold_streams(shot.samples())

func _nearby_regions() -> Array[String]:
	var radius := float(shot.data.get("neighbourRadius", DEFAULT_NEIGHBOUR_RADIUS))
	var points := shot.samples(1.0)
	var found: Array[Dictionary] = []
	var registry := _registry()
	for key: Variant in registry:
		var entry := MapRegistry.resolve(registry, str(key))
		var geography: Dictionary = entry.get("continentGeography", {}) as Dictionary
		var raw: Array = geography.get("translation", []) as Array
		var map_id := str(entry.get("registryKey", key))
		if raw.size() != 3 or str(geography.get("frame", "")) != _active.frame or map_id == _active.id:
			continue
		var path := ProjectSettings.globalize_path(str(entry.get("manifest", "")))
		var document: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) \
			if FileAccess.file_exists(path) else null
		if document is not Dictionary:
			continue
		var bounds: Dictionary = ((document as Dictionary).get("asset", {}) as Dictionary).get("bounds", {}) as Dictionary
		if not bounds.has("min"):
			continue
		var offset := Vector3(float(raw[0]), float(raw[1]), float(raw[2])) - (_active.translation as Vector3)
		var nearest := INF
		for point: Vector3 in points:
			nearest = minf(nearest, ContinentChunkStream.bounds_distance(point - offset, bounds))
		if nearest <= radius:
			found.append({"id": map_id, "distance": nearest})
	found.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a.distance < b.distance)
	var ids: Array[String] = []
	for item: Dictionary in found.slice(0, int(shot.data.get("maxNeighbours", DEFAULT_MAX_NEIGHBOURS))):
		ids.append(str(item.id))
	return ids

## A neighbour shows all its own ground, as an owned continent neighbour does
## in the game, and none of the border previews meant for a single crossing.
static func _show_whole_region(root: Node3D) -> void:
	var roots: Array[Node] = [root]
	if root is ContinentChunkStream:
		roots.append_array(root.get_children())
	for each: Node in roots:
		for node: Node in each.get_children():
			if node is not Node3D:
				continue
			if str(node.name).begins_with("StreamPreview_"):
				(node as Node3D).visible = false
			elif str(node.name) == "StreamActive" or node.has_meta("stream_borders"):
				(node as Node3D).visible = true

func _populate() -> void:
	if not bool(shot.data.get("ambientLife", true)):
		return
	var population := AmbientPopulation.new()
	population.name = "AmbientPopulation"
	add_child(population)
	var stream: ContinentChunkStream = _active.root as ContinentChunkStream \
		if _active.root is ContinentChunkStream else null
	population.populate(_active.manifest, get_world_3d().direct_space_state, stream)

## The walkable ground under `point`: the first navigation surface found
## below GROUND_PROBE_ABOVE over it, else the first from high above. NAN where
## there is none.
func _ground_at(point: Vector3) -> float:
	var space := get_world_3d().direct_space_state
	for start: float in [point.y + GROUND_PROBE_ABOVE, point.y + GROUND_PROBE_FALLBACK]:
		var query := PhysicsRayQueryParameters3D.create(Vector3(point.x, start, point.z),
			Vector3(point.x, point.y - GROUND_PROBE_FALLBACK, point.z),
			WorldLoader.NAVIGATION_SURFACE_LAYER)
		var hit := space.intersect_ray(query)
		if not hit.is_empty():
			return (hit.position as Vector3).y
	return NAN

# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

## One still per key and one halfway between keys, after the grass and the
## animals have had frames to settle on each, and with the grass bed placed in
## full: its per-frame build budget leaves most of the bed unbuilt after those
## frames (a Landfall bed takes about 1.5 s of 2-6 ms budgets), and the stills
## showed bare lawns away from the focus.
func _write_previews(directory: String) -> void:
	if not directory.is_absolute_path():
		directory = _repository_path(directory)
	DirAccess.make_dir_recursive_absolute(directory)
	var times: Array[float] = []
	var start := float(shot.keys[0].t)
	for index: int in shot.keys.size():
		times.append(float(shot.keys[index].t) - start)
		if index + 1 < shot.keys.size():
			times.append((float(shot.keys[index].t) + float(shot.keys[index + 1].t)) * 0.5 - start)
	for index: int in times.size():
		var pose := shot.evaluate(times[index])
		_apply_pose(pose)
		for unused: int in range(20):
			_tend(pose)
			await get_tree().process_frame
		var beds := get_node_or_null(LookGrassBeds.NODE_NAME) as LookGrassBeds
		if beds != null:
			beds.settle()
		for unused: int in range(3):
			await get_tree().process_frame
		RenderingServer.force_draw(false)
		var image := get_viewport().get_texture().get_image()
		var file := directory.path_join("%s_%02d_t%05.2f.png" % [shot.name, index, times[index]])
		image.save_png(file)
		print("trailer preview ", file)

func _finish(code: int) -> void:
	if code == 0 and _frames_at.has("shot"):
		var summary := {"shot": shot.name, "fps": _frame_rate(), "fixedFps": _fixed_fps,
			"shotFrames": _shot_frames, "durationSeconds": shot.duration,
			"framesDrawnBeforeShot": int(_frames_at.shot),
			"framesDrawnAtEnd": int(_frames_at.get("done", Engine.get_frames_drawn())),
			"movie": _movie_path}
		print("trailer done ", JSON.stringify(summary))
		if not _movie_path.is_empty():
			var sidecar := FileAccess.open(_movie_path + ".trailer.json", FileAccess.WRITE)
			if sidecar != null:
				sidecar.store_string(JSON.stringify(summary, "  ") + "\n")
	# Nothing may still be importing when the process exits (see
	# ContinentChunkStream.drain_workers).
	await ContinentChunkStream.drain_workers(get_tree())
	get_tree().quit(code)

func _fail(errors: Variant) -> void:
	for message: Variant in errors:
		push_error("trailer: " + str(message))
	_state = "failed"
	_finish(1)

func _check_resolution() -> void:
	var wanted: Variant = shot.data.get("resolution")
	if wanted is not Array or (wanted as Array).size() != 2:
		return
	var size := Vector2i(int(wanted[0]), int(wanted[1]))
	if get_window().size != size:
		push_warning("trailer: window is %s, shot wants %s; pass --resolution %dx%d" % [
			get_window().size, size, size.x, size.y])

func _frame_rate() -> float:
	return float(_fixed_fps) if _fixed_fps > 0 else float(shot.data.get("fps", 60.0))

## A relative path on the command line is relative to the client repository
## (the folder holding godot-client/), wherever Godot was started from.
static func _repository_path(path: String) -> String:
	return ProjectSettings.globalize_path("res://").get_base_dir().get_base_dir().path_join(path).simplify_path()

static func _engine_fixed_fps() -> int:
	var arguments := OS.get_cmdline_args()
	var index := arguments.find("--fixed-fps")
	if index >= 0 and index + 1 < arguments.size():
		return int(arguments[index + 1])
	# Movie Maker without --fixed-fps records at the project's movie rate.
	if not Engine.get_write_movie_path().is_empty():
		return int(ProjectSettings.get_setting("editor/movie_writer/fps", 60))
	return 0

static func _user_arguments() -> Dictionary:
	var result := {}
	for argument: String in OS.get_cmdline_user_args():
		if not argument.begins_with("--"):
			continue
		var pair := argument.substr(2).split("=", true, 1)
		result[pair[0]] = pair[1] if pair.size() > 1 else "true"
	return result

# --------------------------------------------------------------------------
# Free camera for authoring
# --------------------------------------------------------------------------

func _start_fly() -> void:
	_state = "fly"
	var forward := -_camera.global_transform.basis.z
	_fly_yaw = rad_to_deg(atan2(forward.x, -forward.z))
	_fly_pitch = rad_to_deg(asin(clampf(forward.y, -1.0, 1.0)))
	# Authoring streams around the camera as the game does, with the shot's budget.
	for region: Dictionary in [_active] + _residents.values():
		var stream := region.root as ContinentChunkStream
		if stream == null:
			continue
		stream.entries.assign(stream.get_meta("trailer_all_entries", stream.entries))
		stream.preload_distance = float(shot.data.get("streamRadius", DEFAULT_STREAM_RADIUS))
		stream.retain_distance = stream.preload_distance + 80.0
		# The stream has no public resume: pause_streaming() is for quitting.
		stream.set("_paused", false)
	var layer := CanvasLayer.new()
	add_child(layer)
	_fly_label = Label.new()
	_fly_label.position = Vector2(16, 16)
	_fly_label.add_theme_color_override("font_outline_color", Color.BLACK)
	_fly_label.add_theme_constant_override("outline_size", 6)
	layer.add_child(_fly_label)

func _fly(delta: float) -> void:
	var move := Vector3.ZERO
	if Input.is_physical_key_pressed(KEY_W): move.z -= 1.0
	if Input.is_physical_key_pressed(KEY_S): move.z += 1.0
	if Input.is_physical_key_pressed(KEY_A): move.x -= 1.0
	if Input.is_physical_key_pressed(KEY_D): move.x += 1.0
	if Input.is_physical_key_pressed(KEY_E): move.y += 1.0
	if Input.is_physical_key_pressed(KEY_Q): move.y -= 1.0
	var speed := _fly_speed * (4.0 if Input.is_physical_key_pressed(KEY_SHIFT) else 1.0)
	var basis := Basis(Vector3.UP, deg_to_rad(-_fly_yaw))
	var position := _camera.global_position + (basis * Vector3(move.x, 0.0, move.z) + Vector3(0.0, move.y, 0.0)) * speed * delta
	var target := position + TrailerShot.direction(_fly_yaw, _fly_pitch) * TrailerShot.LOOK_AHEAD_METRES
	_apply_pose({"position": position, "target": target, "fov": _camera.fov, "roll": 0.0, "minute": _minute})
	_tend({"position": position, "target": target})
	for region: Dictionary in [_active] + _residents.values():
		if region.root is ContinentChunkStream:
			(region.root as ContinentChunkStream).update_focus(position - (region.get("offset", Vector3.ZERO) as Vector3))
	var ground := _ground_at(position)
	_fly_label.text = "%s  pos %.1f, %.1f, %.1f  yaw %.0f pitch %.0f  fov %.0f  above ground %s  minute %s  speed %.0f\n%s" % [
		shot.name, position.x, position.y, position.z, _fly_yaw, _fly_pitch, _camera.fov,
		"-" if is_nan(ground) else "%.1f" % (position.y - ground), "map" if is_nan(_minute) else "%.0f" % _minute,
		speed, "WASD move, Q/E down/up, Shift fast, right-drag look, wheel speed, Z/X fov, [ ] hour, K copy key, Esc quit"]

func _unhandled_input(event: InputEvent) -> void:
	if _state != "fly":
		if event is InputEventKey and (event as InputEventKey).pressed \
				and (event as InputEventKey).physical_keycode == KEY_ESCAPE and _movie_path.is_empty():
			_finish(0)
		return
	if event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
		var motion := (event as InputEventMouseMotion).relative
		_fly_yaw = fposmod(_fly_yaw + motion.x * 0.2, 360.0)
		_fly_pitch = clampf(_fly_pitch - motion.y * 0.2, -89.0, 89.0)
	elif event is InputEventMouseButton and (event as InputEventMouseButton).pressed:
		match (event as InputEventMouseButton).button_index:
			MOUSE_BUTTON_WHEEL_UP: _fly_speed = minf(_fly_speed * 1.25, 400.0)
			MOUSE_BUTTON_WHEEL_DOWN: _fly_speed = maxf(_fly_speed / 1.25, 0.5)
	elif event is InputEventKey and (event as InputEventKey).pressed:
		match (event as InputEventKey).physical_keycode:
			KEY_K: _print_key()
			KEY_Z: _camera.fov = maxf(_camera.fov - 2.0, 10.0)
			KEY_X: _camera.fov = minf(_camera.fov + 2.0, 100.0)
			KEY_BRACKETLEFT: _set_fly_minute(-10.0)
			KEY_BRACKETRIGHT: _set_fly_minute(10.0)
			KEY_ESCAPE: _finish(0)

func _set_fly_minute(step: float) -> void:
	_minute = fposmod((180.0 if is_nan(_minute) else _minute) + step, DayNightBinder.MINUTES_PER_DAY)
	_apply_hour()

## Prints the camera as a shot key and copies it to the clipboard.
func _print_key() -> void:
	var position := _camera.global_position
	var target := position + TrailerShot.direction(_fly_yaw, _fly_pitch) * TrailerShot.LOOK_AHEAD_METRES
	var key := {"position": [snappedf(position.x, 0.01), snappedf(position.y, 0.01), snappedf(position.z, 0.01)],
		"lookAt": [snappedf(target.x, 0.01), snappedf(target.y, 0.01), snappedf(target.z, 0.01)],
		"fov": snappedf(_camera.fov, 0.5)}
	var ground := _ground_at(position)
	if not is_nan(ground):
		key.aboveGround = snappedf(position.y - ground, 0.01)
	var text := JSON.stringify(key)
	DisplayServer.clipboard_set(text)
	print("trailer key ", text)
