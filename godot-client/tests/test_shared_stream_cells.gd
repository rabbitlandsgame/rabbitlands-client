extends SceneTree

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func _surface(parent: Node3D, title: String, z: float, depth: float, y := 0.0) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	mesh.name = title
	var box := BoxMesh.new()
	box.size = Vector3(20, .02, depth)
	mesh.mesh = box
	mesh.position = Vector3(0, y, z)
	parent.add_child(mesh)
	var body := StaticBody3D.new()
	body.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	mesh.add_child(body)
	var shape := CollisionShape3D.new()
	var bounds := BoxShape3D.new()
	bounds.size = box.size
	shape.shape = bounds
	body.add_child(shape)
	return mesh

func _manifest(identity: String, outward: Array) -> WorldManifest:
	var result := WorldManifest.new()
	result.data = {"asset": {"id": identity, "serverCells": 64},
		"coordinateTransform": {"serverOrigin": [10,10], "serverCells": [64,64]},
		"streamingBorders": [{"id": "test-road", "anchor": [0,0,0], "outward": outward,
			"geometryMode": "shared-cells-v2", "sceneNodes": ["Terrain_Approach"]}]}
	return result

func _run() -> void:
	var stage := Node3D.new()
	root.add_child(stage)
	var loader := WorldLoader.new()
	stage.add_child(loader)
	var near_manifest := _manifest("amberwood", [0,-1])
	var far_manifest := _manifest("whitehorn_range", [0,1])
	far_manifest.data.streamingBorders[0].geometryMode = "continent-owned-v1"
	var near := Node3D.new()
	stage.add_child(near)
	_surface(near,"Terrain_Approach",10,20)
	_surface(near,"Terrain_Core",30,20)
	var threshold := _surface(near,"Walk_StreamThreshold_test-road",-1,2,.5)
	loader.world_root = near
	loader.manifest = near_manifest
	loader._group_streaming_views()
	_expect(not threshold.visible, "source threshold supports the trigger without drawing duplicate scenery")
	var far := Node3D.new()
	stage.add_child(far)
	var actual := _surface(far,"Terrain_Approach",-10,20)
	var far_core := _surface(far,"Terrain_Core",-30,20)
	# A non-overlapping owned corner wraps east of the active ground, behind
	# the central road's seam plane. It has no copied/borrowed surface.
	var far_corner := _surface(far,"Terrain_OwnedCorner",5,6)
	far_corner.position.x = 20
	var far_threshold := _surface(far,"Walk_StreamThreshold_test-road",-30,2,.5)
	var far_wall := StaticBody3D.new()
	far_wall.collision_layer = 1
	far.add_child(far_wall)
	var original_id := actual.get_instance_id()
	var core_id := far_core.get_instance_id()
	loader.world_root = far
	loader.manifest = far_manifest
	loader._group_streaming_views()
	_expect(bool(far.get_meta("shared_stream_cells", false)) and far.has_node("StreamCell_test-road"),
		"continent-owned loader uses the same actual-node grouping as shared cells")
	_expect(not far_threshold.visible and bool(far_threshold.get_meta("stream_threshold", false)),
		"continent-owned loader hides and tags the navigation-only threshold")
	# Exercise legacy strip selection first, then change only the frame mode.
	far_manifest.data.streamingBorders[0].geometryMode = "shared-cells-v2"
	var stream := ExteriorRegionStream.new()
	stage.add_child(stream)
	stream.links = [{"seamless": true, "ends": [
		{"map":"amberwood", "position":[0,0,-1], "frame":near_manifest.data.streamingBorders[0]},
		{"map":"whitehorn_range", "position":[0,0,1], "frame":far_manifest.data.streamingBorders[0]}]}]
	stream.residents["whitehorn_range"] = {"root":far,"manifest":far_manifest}
	stream.activate("amberwood",near,near_manifest)
	await physics_frame
	await physics_frame
	_expect(actual.is_visible_in_tree() and not far_core.is_visible_in_tree(), "resident exposes its actual shared approach")
	_expect(far.find_children("Terrain_Approach", "MeshInstance3D", true, false).size() == 1, "approach has one node, not a preview copy")
	var space := stage.get_world_3d().direct_space_state
	for depth: float in [1.1,12.1]:
		var target: Variant = stream.pick_neighbor(space,Vector3(0,20,-depth),Vector3.DOWN,true)
		_expect(target is Vector3, "visible neighbor target accepts a click at depth %s" % depth)
		_expect(stream.pending_walk.get("map") == "whitehorn_range", "click keeps the destination map")
		_expect(stream.pending_walk.get("tile") == Vector2i(10,floori(10+depth)), "click keeps the destination's tile frame")
		_expect(stream.pending_walk.get("run") == true, "shift-click preserves run intent")
	far_manifest.data.coordinateTransform.serverCells = [1,1]
	_expect(stream.pick_neighbor(space,Vector3(0,20,-10),Vector3.DOWN,false) == null, "rendered margins outside served bounds are rejected")
	_expect(stream.pending_walk.is_empty(), "rejected click cannot leave a stale continuation")
	far_manifest.data.coordinateTransform.serverCells = [64,64]
	stream.pick_neighbor(space,Vector3(0,20,-12.1),Vector3.DOWN,false)
	var continuation := stream.take_continuation("whitehorn_range")
	_expect(continuation.tile == Vector2i(10,22) and not stream.pending_walk.is_empty(), "crossing retains the exact target until authoritative arrival")
	stream.take_continuation("whitehorn_range", {"x":10,"y":22,"command_sequence":30})
	_expect(stream.pending_walk.is_empty(), "authoritative exact arrival consumes the click intent")
	far_manifest.data.streamingBorders[0].geometryMode = "continent-owned-v1"
	stream._refresh_views()
	await physics_frame
	await physics_frame
	_expect(far_core.is_visible_in_tree() and far_core.get_instance_id() == core_id,
		"owned resident exposes its original core beyond the approach strip")
	_expect(not far_threshold.is_visible_in_tree(), "full owned view cannot reveal the hidden trigger skin")
	_expect((far_core.get_child(0) as StaticBody3D).collision_layer == ExteriorRegionStream.PREVIEW_SURFACE_LAYER,
		"owned core ground is pickable only on neighbor layer 16")
	_expect(far_wall.collision_layer == 0 and (far_threshold.get_child(0) as StaticBody3D).collision_layer == 0,
		"resident structures and invisible thresholds have no collision ownership")
	var owned_target: Variant = stream.pick_neighbor(space,Vector3(0,20,-30),Vector3.DOWN,true)
	_expect(owned_target is Vector3 and stream.pending_walk.get("tile") == Vector2i(10,40),
		"full owned ground keeps the exact distant destination tile")
	_expect(absf((stream.pending_walk.get("world_point", Vector3.INF) as Vector3).y - .01) < .001,
		"owned click hits the actual ground below the invisible threshold")
	var corner_target: Variant = stream.pick_neighbor(space,Vector3(20.5,20,4.5),Vector3.DOWN,false)
	_expect(corner_target is Vector3 and corner_target == Vector3(0,0,-1),
		"a visible owned corner behind the road plane still routes through its real crossing")
	var corner_continuation := stream.take_continuation("whitehorn_range")
	_expect(corner_continuation.get("tile") == Vector2i(30,5) and not bool(corner_continuation.get("run", true)),
		"owned corner continuation preserves its exact physical destination tile and walk intent")
	far_manifest.data.streamingBorders[0].geometryMode = "shared-cells-v2"
	stream._refresh_views()
	_expect(not far_core.is_visible_in_tree() and (far_core.get_child(0) as StaticBody3D).collision_layer == 0,
		"switching back to legacy mode hides and unpicks the core")
	far_manifest.data.streamingBorders[0].geometryMode = "continent-owned-v1"
	stream._refresh_views()
	# A visible shared riverbank without a direct crossing must retain the
	# exact click while following the real road through an intermediate map.
	var direct: Dictionary = stream.links[0]
	direct.seamless = false
	direct.visualOnly = true
	var config := {"serverOrigin": [100,80]}
	stream.links.append({"seamless": true, "ends": [
		{"map":"amberwood", "position":[6,0,7], "coordinateTransform":config},
		{"map":"mirrorhold", "position":[3,0,4], "coordinateTransform":config}]})
	stream.links.append({"seamless": true, "ends": [
		{"map":"mirrorhold", "position":[20.5,0,-30.5], "coordinateTransform":config},
		{"map":"whitehorn_range", "position":[2,0,3], "coordinateTransform":config}]})
	stream._refresh_views()
	await physics_frame
	await physics_frame
	_expect(far_core.is_visible_in_tree(), "geographic neighbor remains visible without a direct road")
	var routed: Variant = stream.pick_neighbor(space,Vector3(0,20,-30),Vector3.DOWN,true)
	_expect(routed == Vector3(6,0,7), "riverbank click starts at the real first road crossing")
	_expect(stream.take_continuation("amberwood").is_empty(), "current-map actor updates cannot repeat the issued route")
	var middle := stream.take_continuation("mirrorhold")
	_expect(middle.get("tile") == Vector2i(120,110) and bool(middle.get("run", false)),
		"intermediate arrival continues through its actual next gate with run intent")
	_expect(stream.take_continuation("mirrorhold").is_empty(), "intermediate gate is issued only once")
	var final_target := stream.take_continuation("whitehorn_range")
	_expect(final_target.get("tile") == Vector2i(10,40) and not stream.pending_walk.is_empty(),
		"multi-map road route retains the exact originally clicked tile")
	stream.take_continuation("whitehorn_range", {"x":10,"y":40,"command_sequence":70})
	_expect(stream.pending_walk.is_empty(), "multi-map road route finishes only at the exact target")
	stream.links = [direct]
	_expect(stream.pick_neighbor(space,Vector3(0,20,-30),Vector3.DOWN,false) == null,
		"visual adjacency alone cannot invent a walkable crossing")
	direct.seamless = true
	direct.visualOnly = false
	ExteriorRegionStream._set_view(far)
	ExteriorRegionStream._set_collision(far,true)
	_expect(actual.get_instance_id() == original_id and actual.is_visible_in_tree(), "adoption keeps the same visible authored node")
	_expect((actual.get_child(0) as StaticBody3D).collision_layer == WorldLoader.NAVIGATION_SURFACE_LAYER, "adoption changes physics ownership")
	_expect(far_core.get_instance_id() == core_id and far_wall.collision_layer == 1
		and (far_threshold.get_child(0) as StaticBody3D).collision_layer == WorldLoader.NAVIGATION_SURFACE_LAYER
		and not far_threshold.visible, "adoption restores original core and structural physics while the trigger stays invisible")
	stream.residents.clear()
	loader.world_root = null
	stage.queue_free()
	await process_frame
	print("shared stream cells: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
