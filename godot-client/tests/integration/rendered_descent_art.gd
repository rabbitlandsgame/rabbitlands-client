extends SceneTree
## The Serpent Deep's own art in the complete client: the descent temple on
## Suncoil (static scenery of the Suncoil package since its republish, the kit
## prototype kit-descent-temple-1; map object 59480, "Descent Temple", is only a
## pick-only click target on its front tile, so the temple is drawn once)
## beside Warden Sethra and the Serpent Catacombs door, and the boss floor's
## reward dais (59490) and way out (59491, "Descent Exit") on the real
## serpent_deep_descent package. The objects arrive as the server would send
## them (map objects through AppState, the keeper as an NPC actor).
##
## Saves under <out>/ (ELORIA_ARTIFACT_DIR, default res://test-artifacts/descent-art):
##   art-temple-game.png    the default game view beside the keeper (window)
##   art-temple-front.png   the camera turned to look west at the temple's front
##   art-temple-top.png     straight down, the server's blocked tiles x 272-279, y 744-751 outlined in yellow and the
##                          temple's front tile (280, 747) in cyan
##   art-boss-game.png      the boss arena: the dais and the way out, default view
##   art-boss-landing.png   the same from the landing side (the camera turned to look toward the arena,
##                          server -y), where the way out shows its front
##   art-boss-top.png       straight down over the arena
## and <out>/art-report.json: each model's world bounds in server tiles and the
## ground under the temple's corners. Rendered only (needs a display; one GPU
## job at a time on the laptop). Set ELORIA_NO_GEOMETRY_CACHE=1.
const SIZE := Vector2i(1600, 900)
const PLAYER_ID := 1
const KEEPER_ID := 30000
const TEMPLE := 59480
const DAIS := 59490
const EXIT := 59491
const CATACOMBS := 59013
## The temple's footprint the server blocks, and its front tile.
const FOOTPRINT := Rect2i(272, 744, 8, 8)
const FRONT := Vector2i(280, 747)

var main: Control
var state: Node
var out := ""
var failures := 0
var report := {}

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	out = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if out.is_empty():
		out = ProjectSettings.globalize_path("res://test-artifacts/descent-art")
	DirAccess.make_dir_recursive_absolute(out)
	root.size = SIZE
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	state = root.get_node("AppState")
	var ready_deadline := Time.get_ticks_msec() + 1800000
	while (main.get("map_registry") as Dictionary).is_empty() and Time.get_ticks_msec() < ready_deadline:
		await process_frame
	state.set("authenticated", true)
	main.get("login_panel").hide()
	main.get("creation_panel").hide()
	main.get("game_view").show()
	if not (main.get("minimap_frame") as Control).visible:
		main.call("_toggle_minimap")
	state.call("_on_packet", 5, PackedByteArray([180, 0]))
	await _temple()
	await _boss()
	var file := FileAccess.open(out.path_join("art-report.json"), FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(report, "  "))
		file.close()
	print("DESCENT_ART_REPORT ", JSON.stringify(report))
	print("rendered descent art: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _temple() -> void:
	var objects := {
		TEMPLE: _object(TEMPLE, FRONT, "Descent Temple", "The Serpent Deep"),
		CATACOMBS: _object(CATACOMBS, Vector2i(288, 755), "Portal", "Serpent Catacombs"),
	}
	var keeper := _actor(KEEPER_ID, "Warden Sethra", Vector2i(283, 747), 366, 2, 3)
	if not await _enter("suncoil", Vector2i(284, 750), objects, {KEEPER_ID: keeper}):
		return
	await _wait_chunks()
	await _settle(90)
	var temple: Node3D = (main.get("map_object_nodes") as Dictionary).get(TEMPLE)
	_expect(is_instance_valid(temple) and not temple.has_node("EntranceModel") and not temple.has_node("Model")
		and bool(temple.get("pick_only")), "the temple's map object is a click target only")
	var drawn := _named_visuals("descent_temple")
	_expect(drawn.size() == 1, "the map draws the temple once (%d)" % drawn.size())
	report["temple"] = _visual_bounds(drawn)
	report["temple_visuals"] = drawn.map(func(v: VisualInstance3D) -> String: return str(v.get_path()))
	report["temple_ground"] = _ground_under(FOOTPRINT)
	var rig: Node3D = main.get("camera_rig")
	rig.set("yaw_degrees", 0.0)
	await _settle(30)
	await _capture("art-temple-game.png", true)
	await _face(Vector3.LEFT)
	await _capture("art-temple-front.png", true)
	rig.set("yaw_degrees", 0.0)
	await _settle(10)
	var outline := _outline([[FOOTPRINT, Color(1, .85, .2)], [Rect2i(FRONT, Vector2i.ONE), Color(.3, .9, 1)]],
		temple.global_position.y + .25 if is_instance_valid(temple) else 0.0)
	await _top("art-temple-top.png", Vector2(277.0, 749.0), 34.0)
	outline.queue_free()

func _boss() -> void:
	var objects := {
		DAIS: _object(DAIS, Vector2i(677, 459), "Descent Dais", "Claim your reward"),
		EXIT: _object(EXIT, Vector2i(683, 461), "Descent Exit", "Return to the temple"),
	}
	if not await _enter("serpent_deep_descent", Vector2i(680, 468), objects, {}):
		return
	await _settle(60)
	var nodes: Dictionary = main.get("map_object_nodes")
	var exit: Node3D = nodes.get(EXIT)
	var dais: Node3D = nodes.get(DAIS)
	_expect(is_instance_valid(exit) and exit.has_node("EntranceModel"), "the way out stands its portal")
	_expect(is_instance_valid(dais) and dais.has_node("Model"), "the dais stands its altar")
	report["exit"] = _bounds(exit, "EntranceModel")
	report["dais"] = _bounds(dais, "Model")
	var rig: Node3D = main.get("camera_rig")
	rig.set("yaw_degrees", 0.0)
	await _settle(30)
	await _capture("art-boss-game.png", true)
	await _face(Vector3.BACK)
	await _capture("art-boss-landing.png", false)
	rig.set("yaw_degrees", 0.0)
	await _settle(10)
	await _top("art-boss-top.png", Vector2(680.0, 462.0), 26.0)

## Turns the camera rig until the camera looks along `toward` (world, flat).
func _face(toward: Vector3) -> void:
	var rig: Node3D = main.get("camera_rig")
	var camera: Camera3D = rig.get("camera")
	var best := 0.0
	var best_dot := -INF
	for yaw: float in [0.0, 90.0, 180.0, 270.0]:
		rig.set("yaw_degrees", yaw)
		await _settle(4)
		var look := -camera.global_transform.basis.z
		var dot := Vector2(look.x, look.z).normalized().dot(Vector2(toward.x, toward.z))
		if dot > best_dot:
			best_dot = dot
			best = yaw
	rig.set("yaw_degrees", best)
	await _settle(40)

## A model's world bounds as server tiles (min/max x and y) and metres (height).
func _bounds(node: Node3D, child: String) -> Dictionary:
	if not is_instance_valid(node) or not node.has_node(child):
		return {}
	var box := AABB()
	var first := true
	for mesh: MeshInstance3D in node.get_node(child).find_children("*", "MeshInstance3D", true, false):
		var world := mesh.global_transform * mesh.get_aabb()
		box = world if first else box.merge(world)
		first = false
	var adapter: CoordinateAdapter = main.get("adapter")
	var a := _server(adapter, box.position)
	var b := _server(adapter, box.end)
	return {"node": [snappedf(node.global_position.x, .01), snappedf(node.global_position.y, .01),
			snappedf(node.global_position.z, .01)],
		"tiles_x": [snappedf(minf(a.x, b.x), .01), snappedf(maxf(a.x, b.x), .01)],
		"tiles_y": [snappedf(minf(a.y, b.y), .01), snappedf(maxf(a.y, b.y), .01)],
		"bottom": snappedf(box.position.y, .01), "top": snappedf(box.end.y, .01)}

## The visual instances under the world whose node or mesh name holds `word`
## (dashes read as underscores).
func _named_visuals(word: String) -> Array:
	var found := []
	var root_node: Node = (main.get("world_loader") as WorldLoader).world_root
	for visual: VisualInstance3D in root_node.find_children("*", "VisualInstance3D", true, false):
		var names := str(visual.name)
		if visual is MeshInstance3D and (visual as MeshInstance3D).mesh != null:
			names += " " + (visual as MeshInstance3D).mesh.resource_name
		if (visual is MultiMeshInstance3D and (visual as MultiMeshInstance3D).multimesh != null
				and (visual as MultiMeshInstance3D).multimesh.mesh != null):
			names += " " + (visual as MultiMeshInstance3D).multimesh.mesh.resource_name
		if names.to_lower().replace("-", "_").contains(word):
			found.append(visual)
	return found

## The world bounds of `visuals` as server tiles (min/max x and y) and metres (height).
func _visual_bounds(visuals: Array) -> Dictionary:
	if visuals.is_empty():
		return {}
	var box := AABB()
	var first := true
	for visual: VisualInstance3D in visuals:
		var world := visual.global_transform * visual.get_aabb()
		box = world if first else box.merge(world)
		first = false
	var adapter: CoordinateAdapter = main.get("adapter")
	var a := _server(adapter, box.position)
	var b := _server(adapter, box.end)
	return {"tiles_x": [snappedf(minf(a.x, b.x), .01), snappedf(maxf(a.x, b.x), .01)],
		"tiles_y": [snappedf(minf(a.y, b.y), .01), snappedf(maxf(a.y, b.y), .01)],
		"bottom": snappedf(box.position.y, .01), "top": snappedf(box.end.y, .01)}

## A world point as fractional server tile coordinates.
static func _server(adapter: CoordinateAdapter, point: Vector3) -> Vector2:
	var origin := adapter.server_to_godot(0.0, 0.0)
	var unit := adapter.server_to_godot(1.0, 1.0) - origin
	return Vector2((point.x - origin.x) / unit.x, (point.z - origin.z) / unit.z)

## The ground height (world Y) under each corner and the centre of a tile rect.
func _ground_under(rect: Rect2i) -> Dictionary:
	var adapter: CoordinateAdapter = main.get("adapter")
	var space := root.get_world_3d().direct_space_state
	var result := {}
	var points := {"nw": Vector2(rect.position), "ne": Vector2(rect.end.x, rect.position.y),
		"sw": Vector2(rect.position.x, rect.end.y), "se": Vector2(rect.end), "centre": Vector2(rect.get_center())}
	for key: String in points:
		var p: Vector2 = points[key]
		var at := adapter.server_to_godot(p.x, p.y)
		var query := PhysicsRayQueryParameters3D.create(at + Vector3.UP * 200.0, at + Vector3.DOWN * 200.0)
		var hit := space.intersect_ray(query)
		result[key] = snappedf((hit.position as Vector3).y, .01) if not hit.is_empty() else null
	return result

## Yellow and cyan outlines of tile rects, a little above `height`, drawn over everything.
func _outline(rects: Array, height: float) -> MeshInstance3D:
	var adapter: CoordinateAdapter = main.get("adapter")
	var mesh := ImmediateMesh.new()
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.no_depth_test = true
	material.vertex_color_use_as_albedo = true
	mesh.surface_begin(Mesh.PRIMITIVE_LINES, material)
	for entry: Array in rects:
		var rect: Rect2i = entry[0]
		var colour: Color = entry[1]
		var corners := [Vector2(rect.position), Vector2(rect.end.x, rect.position.y), Vector2(rect.end),
			Vector2(rect.position.x, rect.end.y)]
		for i: int in 4:
			for p: Vector2 in [corners[i], corners[(i + 1) % 4]]:
				var at := adapter.server_to_godot(p.x, p.y)
				mesh.surface_set_color(colour)
				mesh.surface_add_vertex(Vector3(at.x, height, at.z))
	mesh.surface_end()
	var node := MeshInstance3D.new()
	node.mesh = mesh
	node.layers = 1
	(main.get("world_loader") as WorldLoader).world_root.add_child(node)
	return node

## Straight down over a server point, north up, 3D viewport only.
func _top(name: String, centre: Vector2, size: float) -> void:
	var adapter: CoordinateAdapter = main.get("adapter")
	var rig: Node3D = main.get("camera_rig")
	var rig_camera: Camera3D = rig.get("camera")
	var at := adapter.server_to_godot(centre.x, centre.y)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = size
	camera.near = 0.5
	camera.far = 400.0
	camera.cull_mask = rig_camera.cull_mask | 1
	rig.get_parent().add_child(camera)
	var ground := rig_camera.global_position.y
	camera.global_transform = Transform3D(Basis.looking_at(Vector3.DOWN, Vector3.FORWARD),
		Vector3(at.x, ground + 60.0, at.z))
	camera.make_current()
	await _settle(20)
	await _capture(name, false)
	rig_camera.make_current()
	camera.queue_free()
	await process_frame

## Changes map as the server's CHANGE_MAP would, then stands the player, the
## given actors and objects on it and waits for the curtain to lift.
func _enter(map_id: String, tile: Vector2i, objects: Dictionary, others: Dictionary) -> bool:
	state.set("actors", {})
	state.set("local_actor_id", -1)
	state.set("map_objects", {})
	state.set("current_map", map_id)
	main.call("_load_server_map")
	var loader: WorldLoader = main.get("world_loader")
	var deadline := Time.get_ticks_msec() + 180000
	while Time.get_ticks_msec() < deadline and not (loader.world_root != null and loader.manifest != null
			and loader.manifest.asset_id() == map_id and str(main.get("loaded_server_map")) == map_id):
		await process_frame
	var loaded := loader.manifest != null and loader.manifest.asset_id() == map_id
	_expect(loaded, "%s loads through Main" % map_id)
	if not loaded:
		return false
	var actors := {PLAYER_ID: _actor(PLAYER_ID, "Traveller", tile, 0, 1, 0)}
	actors.merge(others)
	state.set("map_objects", objects)
	state.set("local_actor_id", PLAYER_ID)
	state.set("actors", actors)
	state.call("mark_all_actors_changed")
	main.call("_sync_world")
	main.call("_sync_map_objects")
	deadline = Time.get_ticks_msec() + 120000
	var curtain: Object = main.get("arrival_curtain")
	while Time.get_ticks_msec() < deadline and ((main.get("actor_nodes") as Dictionary).size() < actors.size()
			or bool(curtain.call("is_showing"))):
		main.call("_sync_world", state.call("take_changed_actors"))
		await process_frame
	_expect(not bool(curtain.call("is_showing")), map_id + ": the arrival curtain lifts")
	await _settle(30)
	return true

func _actor(id: int, name: String, tile: Vector2i, actor_type: int, kind: int, facing: int) -> Dictionary:
	var rotation := maxi(0, facing) * 8192
	if rotation >= 32768:
		rotation -= 65536
	return {"actor_id": id, "x": tile.x, "y": tile.y, "rotation": rotation, "actor_type": actor_type,
		"kind": kind, "name": name, "health": 100, "max_health": 100, "alive": true, "appearance": {}}

func _object(id: int, tile: Vector2i, label: String, detail: String) -> Dictionary:
	return {"object_id": id, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x": tile.x, "y": tile.y,
		"label": label, "detail": detail}

func _wait_chunks() -> void:
	var stream := (main.get("world_loader") as WorldLoader).world_root as ContinentChunkStream
	if stream == null:
		return
	var deadline := Time.get_ticks_msec() + 90000
	while Time.get_ticks_msec() < deadline:
		var ready := stream._thread == null
		for entry: Dictionary in stream.selection(stream.focus, true):
			if float(entry.distance) <= stream.preload_distance and not stream.cells.has(str(entry.id)):
				ready = false
		if ready:
			break
		await process_frame
	await _settle(20)

func _settle(frames: int) -> void:
	for frame: int in frames:
		await physics_frame
		await process_frame

func _capture(name: String, whole: bool) -> void:
	await process_frame
	RenderingServer.force_draw(false)
	var image: Image = root.get_texture().get_image() if whole \
		else (main.get("main_viewport") as SubViewport).get_texture().get_image()
	_expect(image != null and image.save_png(out.path_join(name)) == OK, "saved " + name)

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: " + message)
		return
	failures += 1
	push_error("FAIL: " + message)
