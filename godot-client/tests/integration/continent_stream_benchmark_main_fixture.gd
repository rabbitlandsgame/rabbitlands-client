extends RefCounted
## Offline Main-listener integration, not a server/player replay. The camera
## proxy still drives movement; real Main season/grounding/binding listeners run.
var main: Control
var state: Node
var actor: ReplicatedActor3D
var adapter: CoordinateAdapter

func create(tree: SceneTree, manifest_path: String) -> Dictionary:
	main = (load("res://tests/integration/crowd_benchmark_main.tscn") as PackedScene).instantiate() as Control
	main.set_script(load("res://tests/integration/continent_stream_benchmark_main.gd"))
	tree.root.add_child(main)
	await tree.process_frame
	state = tree.root.get_node("AppState")
	state.set("authenticated",true)
	state.set("current_map","landfall")
	# Fix a representative server almanac value rather than leaving seasonal
	# listener work disabled in an offline process with no server packets.
	state.set("almanac",{"season":{"index":0}})
	(main.get("login_panel") as Control).hide()
	(main.get("creation_panel") as Control).hide()
	(main.get("game_view") as Control).show()
	# UI/network roster orchestration is outside this listener-only fixture.
	# Child streaming and deferred surface callbacks retain normal processing.
	main.set_process(false)
	main.set("loaded_server_map","landfall")
	(main.get("camera_rig") as Node).set_process(false)
	adapter = WorldManifest.load_file(manifest_path).coordinate_adapter()
	main.set("adapter",adapter)
	return {"stage":main.get("world_root"),"loader":main.get("world_loader"),
		"camera":main.get("gameplay_camera"),"environment":main.get("world_environment"),
		"sun":main.get("world_sun")}

func install_proxies(points: PackedVector3Array) -> void:
	var tile := adapter.godot_to_server(points[0])
	var dto := {"actor_id":19001,"x":tile.x,"y":tile.y,"rotation":0,"actor_type":1,
		"kind":1,"name":"Streaming benchmark proxy","alive":true,"appearance":{},
		"health":100,"max_health":100,"equipment_visuals":{}}
	state.set("local_actor_id",19001)
	state.set("actors",{19001:dto})
	actor = ReplicatedActor3D.new()
	actor.configure(dto,adapter,{}, {}, {},false)
	(main.get("world_root") as Node3D).add_child(actor)
	actor.set_process(false)
	actor.set_physics_process(false)
	(main.get("actor_nodes") as Dictionary)[19001] = actor
	var shape := CapsuleMesh.new()
	shape.radius = .3
	shape.height = 1.8
	var body := MeshInstance3D.new()
	body.mesh = shape
	body.position.y = .9
	body.layers = 2
	actor.add_child(body)
	# Generic fixture objects exercise actual navigation rays and ring draping;
	# authored scenery/prototype geometry remains entirely untouched.
	for index in range(12):
		var point := points[index % points.size()] + Vector3(float(index % 3),0,float(index / 3))
		var at := adapter.godot_to_server(point)
		var object := MapObject3D.new()
		object.configure({"object_id":20000+index,"kind":0,"x":at.x,"y":at.y,
			"label":"Benchmark fixture"},adapter,{})
		(main.get("world_root") as Node3D).add_child(object)
		(main.get("map_object_nodes") as Dictionary)[20000+index] = object
		(main.get("_ungrounded_map_objects") as Dictionary)[20000+index] = true
	for index in range(4):
		var at := adapter.godot_to_server(points[index % points.size()])
		var marker := MapMarker3D.new()
		marker.configure({"marker_id":21000+index,"x":at.x,"y":at.y,"label":"Benchmark marker"},adapter,false)
		(main.get("world_root") as Node3D).add_child(marker)
		(main.get("map_marker_nodes") as Dictionary)[21000+index] = marker
	main.call("_watch_chunk_surfaces")
	move(points[0])

func arrival_complete() -> void:
	main.get("arrival_curtain").call("finish")

func surface_work() -> Dictionary:
	return main.call("surface_work_snapshot")

func settled() -> bool:
	return int(main.get("_surface_followup_pending")) == 0 and not bool(main.get("_surface_refresh_running"))

func move(point: Vector3) -> void:
	if not is_instance_valid(actor): return
	var tile := adapter.godot_to_server(point)
	var records: Dictionary = state.get("actors")
	var dto: Dictionary = records[19001]
	dto.x = tile.x
	dto.y = tile.y
	actor.server_target = adapter.tile_center(tile.x,tile.y)
	actor.global_position = Vector3(point.x,actor.global_position.y,point.z)
	main.call("_place_actor_on_surface",actor,false,adapter.fallback_height())

func snapshot() -> Dictionary:
	return {"scope":"Offline real Main binding/listener integration with fixed season0,one capsule actor proxy,12generic objects and4markers; UI/roster process orchestration disabled, child streaming and deferred surface listeners active; no server, credentials or authoritative movement. Landfall has no authored promoted-scenery bindings.",
		"synthetic_season_index":0,
		"creation_preview_seed":424242,
		"world_viewport_resolution":[(main.get("main_viewport") as SubViewport).size.x,(main.get("main_viewport") as SubViewport).size.y],
		"world_render_scale":(main.get("main_viewport") as SubViewport).scaling_3d_scale,
		"actor_count":(main.get("actor_nodes") as Dictionary).size(),
		"object_count":(main.get("map_object_nodes") as Dictionary).size(),
		"marker_count":(main.get("map_marker_nodes") as Dictionary).size(),
		"surface_work":surface_work(),
		"local_grounded":(main.get("_grounded_actors") as Dictionary).has(19001)}

func release() -> void:
	if is_instance_valid(main): main.queue_free()
