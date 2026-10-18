extends SceneTree
## Where the grass beds stop around pale paving and opaque kit paving, from
## above. Loads each target map offline as the trailer camera does (every chunk
## within reach resident, the look on at high quality), grows the grass beds
## around the target and writes, per target, a top-down map of a square around
## it and the counts behind it. It edits nothing and needs no GPU.
##
## Each map (PNG, PIXEL_METRES a pixel, north up):
##   grey       ground the grass may grow on, darker where the ray found none
##   brown      a road deck (by its coverage), orange an opaque deck (kit paving,
##              a bridge's timber)
##   blue       pale paving, as bright as the patches' summed coverage
##   red        the bounds the grass used to stop at (each paving patch's AABB
##              grown by OLD_PAVING_MARGIN)
##   green      a tuft's foot
## And per target in the JSON report: tufts in the square; on visible paving
## (summed coverage over LookProfile.PAVING_RIM.x); inside the old bounds; the
## open terrain inside the old bounds off the paint, and how much of it has
## no tuft within a metre; the time to grow the bed and its census. Per map:
## its opaque walk decks, where they lie and whether they carry vertex colour.
##
## Run headless from godot-client/ (ELORIA_LOOK=1 is set by the probe):
##   Godot --headless --path . --script res://tests/look/probe_paving_grass.gd
##     -- --out=<dir> [--targets=<file.json>]
## Targets: a JSON list of {map, id, x, z}; else TARGETS.

const REGISTRY_PATH := "res://data/maps/registry.json"
const PIXEL_METRES := 0.25
const SQUARE_METRES := 64.0
const STREAM_RADIUS := 160.0
## The margin the grass used to keep round every paving patch's bounds.
const OLD_PAVING_MARGIN := 0.5
const TARGETS := [
	{"map": "landfall", "id": "keep-forecourt", "x": -71.4, "z": -25.1},
	{"map": "landfall", "id": "court-gate", "x": -164.7, "z": -46.0},
	{"map": "landfall", "id": "paved-avenue", "x": -127.1, "z": -9.0},
	{"map": "landfall", "id": "arrival-plaza", "x": -152.0, "z": 34.0},
	{"map": "four_gates", "id": "central-plaza", "x": 0.0, "z": -8.6},
]

var _out := ""
var _report := {}

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	create_timer(1800.0).timeout.connect(func() -> void:
		push_error("PROBE timed out")
		quit(3))
	var arguments := {}
	for argument: String in OS.get_cmdline_user_args():
		var parts := argument.trim_prefix("--").split("=", true, 1)
		arguments[parts[0]] = parts[1] if parts.size() > 1 else ""
	_out = str(arguments.get("out", ProjectSettings.globalize_path("user://probe_paving_grass")))
	DirAccess.make_dir_recursive_absolute(_out)
	var targets: Array = TARGETS
	if arguments.has("targets"):
		targets = JSON.parse_string(FileAccess.get_file_as_string(str(arguments.targets)))
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "1")
	LookProfile.set_player_quality(LookProfile.quality_named("high"))
	var by_map := {}
	for target: Dictionary in targets:
		var key := str(target.map)
		if not by_map.has(key):
			by_map[key] = []
		(by_map[key] as Array).append(target)
	for map_id: String in by_map:
		await _probe_map(map_id, by_map[map_id] as Array)
	var file := FileAccess.open(_out.path_join("probe_paving_grass.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(_report, "\t"))
	file.close()
	print("PROBE wrote ", _out)
	quit(0)

func _probe_map(map_id: String, targets: Array) -> void:
	var registry: Dictionary = (JSON.parse_string(FileAccess.get_file_as_string(REGISTRY_PATH))
		as Dictionary).get("maps", {})
	var entry := MapRegistry.resolve(registry, map_id)
	var manifest_path := ProjectSettings.globalize_path(str(entry.get("manifest", "")))
	var stage := Node3D.new()
	stage.name = "ProbeStage_" + map_id
	root.add_child(stage)
	var loader := WorldLoader.new()
	stage.add_child(loader)
	loader.load_world(manifest_path, Vector3.INF, true)
	if loader.world_root == null:
		push_error("probe: %s did not load" % map_id)
		return
	var points := PackedVector3Array()
	for target: Dictionary in targets:
		points.append(Vector3(float(target.x), 0.0, float(target.z)))
	if loader.world_root is ContinentChunkStream:
		var stream := loader.world_root as ContinentChunkStream
		var wanted: Array[Dictionary] = []
		for chunk: Dictionary in stream.entries:
			for point: Vector3 in points:
				if ContinentChunkStream.bounds_distance(point, chunk.bounds) <= STREAM_RADIUS:
					wanted.append(chunk)
					break
		stream.entries.assign(wanted)
		stream.preload_distance = 1.0e9
		stream.retain_distance = 1.0e9
		stream.maximum_chunks = 1 << 20
		stream.maximum_resident_bytes = 6144 * 1048576
		stream.has_focus = false
		stream.prime(points[0])
		stream.pause_streaming()
	for unused: int in 4:
		await physics_frame
	for target: Dictionary in targets:
		_probe_target(stage, loader.world_root, loader.manifest, target)
	_report["%s_kit_decks" % map_id] = _kit_decks(loader.world_root)
	stage.queue_free()
	await process_frame

func _probe_target(stage: Node3D, world: Node3D, manifest: WorldManifest, target: Dictionary) -> void:
	var space := stage.get_world_3d().direct_space_state
	var centre := Vector3(float(target.x), 0.0, float(target.z))
	centre.y = _ground(space, centre)
	LookGrassBeds.clear(stage)
	LookGrassBeds.tend(stage, world, manifest, {}, centre)
	var beds := stage.get_node_or_null(LookGrassBeds.NODE_NAME) as LookGrassBeds
	if beds == null:
		push_error("probe: no grass at %s" % target.id)
		return
	var began := Time.get_ticks_usec()
	beds.settle()
	var grow_msec := float(Time.get_ticks_usec() - began) / 1000.0
	var tiles := (beds.get("_tiles") as Dictionary).size()
	# Every tuft, in the world (the bed's frame is the terrain's).
	var tufts: Array[Vector2] = []
	for position: Vector3 in beds.tuft_positions():
		var world_position := beds.global_transform * position
		tufts.append(Vector2(world_position.x, world_position.z))
	var paving: Array[Dictionary] = []
	for patch: Dictionary in beds.get("_patches") as Array:
		if bool(patch.paving):
			paving.append(patch)
	var size := int(SQUARE_METRES / PIXEL_METRES)
	var origin := Vector2(centre.x, centre.z) - Vector2.ONE * SQUARE_METRES * 0.5
	var image := Image.create(size, size, false, Image.FORMAT_RGB8)
	var coverage_at := PackedFloat32Array()
	coverage_at.resize(size * size)
	var old_zone := PackedByteArray()
	old_zone.resize(size * size)
	var open_ground := PackedByteArray()
	open_ground.resize(size * size)
	var open_in_zone := 0
	var bald_in_zone := 0
	var query := PhysicsRayQueryParameters3D.new()
	query.collision_mask = LookGrassBeds.WALK_LAYER | LookGrassBeds.WORLD_LAYER
	for j: int in size:
		for i: int in size:
			var spot := origin + Vector2(i + 0.5, j + 0.5) * PIXEL_METRES
			var point := Vector3(spot.x, centre.y, spot.y)
			query.from = point + Vector3.UP * 60.0
			query.to = point - Vector3.UP * 60.0
			var hit := space.intersect_ray(query)
			var colour := Color(0.05, 0.05, 0.05)
			var kind := -1
			if not hit.is_empty():
				point.y = (hit.position as Vector3).y
				var collider := hit.collider as CollisionObject3D
				var body: Dictionary = beds.call("_surface_of", collider) if collider != null \
					and (collider.collision_layer & LookGrassBeds.WALK_LAYER) != 0 else {}
				kind = int(body.get("kind", LookGrassBeds.Surface.NONE))
				match kind:
					LookGrassBeds.Surface.TERRAIN, LookGrassBeds.Surface.VERTEX:
						colour = Color(0.32, 0.34, 0.3)
					LookGrassBeds.Surface.DECK:
						colour = Color(0.36, 0.25, 0.14)
					LookGrassBeds.Surface.BRIDGE:
						colour = Color(0.85, 0.5, 0.12)
					_:
						colour = Color(0.12, 0.12, 0.12)
			var covered := 0.0
			var in_zone := false
			for patch: Dictionary in paving:
				var rect: Rect2 = patch.rect
				if rect.grow(OLD_PAVING_MARGIN).has_point(spot):
					in_zone = true
				if rect.has_point(spot):
					covered += maxf(float(beds.call("_patch_coverage", patch, point)), 0.0)
			coverage_at[j * size + i] = covered
			old_zone[j * size + i] = 1 if in_zone else 0
			if covered > 0.0:
				colour = colour.lerp(Color(0.35, 0.55, 1.0), clampf(covered, 0.0, 1.0) * 0.85)
			if kind == LookGrassBeds.Surface.TERRAIN:
				open_ground[j * size + i] = 1
				if in_zone and covered < LookProfile.PAVING_RIM.x:
					open_in_zone += 1
			image.set_pixel(i, j, colour)
	# The old bounds' outline.
	for j: int in size:
		for i: int in size:
			if old_zone[j * size + i] == 0:
				continue
			var edge := i == 0 or j == 0 or i == size - 1 or j == size - 1 \
				or old_zone[j * size + i - 1] == 0 or old_zone[j * size + i + 1] == 0 \
				or old_zone[(j - 1) * size + i] == 0 or old_zone[(j + 1) * size + i] == 0
			if edge:
				image.set_pixel(i, j, Color(0.9, 0.12, 0.1))
	var in_square := 0
	var on_paint := 0
	var in_old := 0
	var grown := PackedByteArray()
	grown.resize(size * size)
	for tuft: Vector2 in tufts:
		var pixel := ((tuft - origin) / PIXEL_METRES).floor()
		if pixel.x < 0 or pixel.y < 0 or pixel.x >= size or pixel.y >= size:
			continue
		var index := int(pixel.y) * size + int(pixel.x)
		in_square += 1
		if coverage_at[index] >= LookProfile.PAVING_RIM.x:
			on_paint += 1
		if old_zone[index] == 1:
			in_old += 1
		grown[index] = 1
		image.set_pixel(int(pixel.x), int(pixel.y), Color(0.3, 0.95, 0.25))
	# Open ground inside the old bounds with no tuft within a metre: bald.
	var reach := int(round(1.0 / PIXEL_METRES))
	for j: int in size:
		for i: int in size:
			var index := j * size + i
			if old_zone[index] == 0 or coverage_at[index] >= LookProfile.PAVING_RIM.x:
				continue
			if open_ground[index] == 0:
				continue
			var near := false
			for dj: int in range(-reach, reach + 1):
				for di: int in range(-reach, reach + 1):
					var x := i + di
					var y := j + dj
					if x >= 0 and y >= 0 and x < size and y < size and grown[y * size + x] == 1:
						near = true
						break
				if near:
					break
			if not near:
				bald_in_zone += 1
	var name := "%s_%s" % [target.map, target.id]
	image.save_png(_out.path_join(name + ".png"))
	_report[name] = {"centre": [centre.x, centre.y, centre.z], "pavingPatches": paving.size(),
		"tufts": in_square, "onPaint": on_paint, "inOldBounds": in_old,
		"openInOldBounds": open_in_zone, "baldInOldBounds": bald_in_zone,
		"growMsec": grow_msec, "tiles": tiles, "msecPerTile": grow_msec / maxf(tiles, 1.0),
		"census": beds.census()}
	print("PROBE ", name, " ", JSON.stringify(_report[name]))

## The opaque walk decks drawn as kit pieces (garden paving, inlays): where
## they lie, how big they are, and whether their meshes carry vertex colour.
func _kit_decks(world: Node3D) -> Array:
	var decks := []
	for node: Node in world.find_children("Walk_*", "MeshInstance3D", true, false):
		var deck := node as MeshInstance3D
		if deck.mesh == null:
			continue
		var material := deck.get_active_material(0) as BaseMaterial3D
		if material == null or material.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED:
			continue
		var box := deck.global_transform * deck.get_aabb()
		var arrays := deck.mesh.surface_get_arrays(0)
		decks.append({"name": String(deck.name), "min": [box.position.x, box.position.y, box.position.z],
			"max": [box.end.x, box.end.y, box.end.z],
			"vertices": (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size(),
			"colour": arrays[Mesh.ARRAY_COLOR] != null, "material": String(material.resource_name),
			"vertexAlbedo": material.vertex_color_use_as_albedo, "cull": material.cull_mode})
	return decks

func _ground(space: PhysicsDirectSpaceState3D, point: Vector3) -> float:
	var query := PhysicsRayQueryParameters3D.create(point + Vector3.UP * 600.0,
		point - Vector3.UP * 600.0, WorldLoader.NAVIGATION_SURFACE_LAYER)
	var hit := space.intersect_ray(query)
	return (hit.position as Vector3).y if not hit.is_empty() else 0.0
