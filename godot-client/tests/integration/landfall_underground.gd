extends SceneTree
## Real-loader acceptance: floors, safe arrivals, roofs, blackspace and models.
## With -- --captures DIR it also saves player-view renders of each section.

const PACKAGE := "res://../eloria-assets/maps/continent-v2/landfall_insides/client/world.json"
var failures := 0

func _init() -> void:
	call_deferred("run")

func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func ground(space: PhysicsDirectSpaceState3D, position: Vector3) -> Dictionary:
	return space.intersect_ray(PhysicsRayQueryParameters3D.create(
		position + Vector3(0, 20, 0), position - Vector3(0, 2, 0), 8))

func run() -> void:
	root.size = Vector2i(1280, 720)
	var stage := Node3D.new()
	root.add_child(stage)
	var loader := WorldLoader.new()
	stage.add_child(loader)
	loader.load_world(ProjectSettings.globalize_path(PACKAGE))
	var deadline := Time.get_ticks_msec() + 60000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	check(loader.world_root != null, "Underground world imports")
	if loader.world_root == null:
		quit(1)
		return
	check(loader.manifest.errors.is_empty(), "Underground manifest validates")
	var scenery := loader.world_root.get_node_or_null("UndergroundScenery")
	var placements: Array = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/world/underground-scenery.json")).placements
	check(scenery != null and scenery.get_child_count() == placements.size() and placements.size() > 45,
		"All reviewed imported scenery placements load")
	var reapply := preload("res://src/world/underground_scenery.gd")
	check(reapply.apply(loader.manifest, loader.world_root) == 0,
		"Applying presentation twice does not duplicate scenery")
	var cutaway := InteriorCutaway.new()
	check(cutaway.configure(loader.manifest, loader.world_root) > 4, "Roof and wall cutaways resolve")
	cutaway.update(0, true)
	# Only the cave the player stands in is drawn (the manifest is `sectioned`).
	var sections := SecretSections.new()
	check(sections.configure(loader.manifest, loader.world_root) > 0, "The underground's caves sort into sections")
	var cenote: Array = (loader.manifest.data.spawnPoints as Array).filter(
		func(s: Dictionary) -> bool: return s.id == "spindle_cavern")
	var at: Array = cenote[0].position
	sections.update(Vector3(at[0], 0, at[2]), true)
	cutaway.update(0, false, sections.current_section())
	var mine_floor := loader.world_root.find_child("Walk_lantern_mine*", true, false) as Node3D
	var cenote_floor := loader.world_root.find_child("Walk_spindle_cavern*", true, false) as Node3D
	check(sections.current_section() == "spindle_cavern" and cenote_floor.visible and not mine_floor.visible,
		"Only the cave the player is in is drawn")
	var mine_wall := loader.world_root.find_child("Build_lantern_mine_south*", true, false) as Node3D
	check(mine_wall != null and not mine_wall.visible, "Another cave's walls stay hidden as the camera turns")
	var roof := loader.world_root.find_child("Roof_spindle_cavern*", true, false) as Node3D
	check(roof != null and not roof.visible, "Entering a cave keeps its roof cut away")
	# Rocks set into the walls drop out near the player while their wall faces
	# the camera (yaw 0: the camera is to +Z); farther along they stay up.
	var near_wall := Vector3(60, 0, 240 - 180)
	cutaway.update(0, true, "spindle_cavern", near_wall)
	var near_hidden := 0
	var far_shown := 0
	for rock: Node in scenery.get_children():
		if not rock.has_meta("cutaway_outward"):
			continue
		var outward: Vector3 = rock.get_meta("cutaway_outward")
		var at_rock := (rock as Node3D).position
		var offset := Vector2(at_rock.x - near_wall.x, at_rock.z - near_wall.z)
		if outward.z > 0.8 and offset.y > 0.0:
			if offset.length() < 9.0 and not (rock as Node3D).visible:
				near_hidden += 1
			if offset.length() > 20.0 and (rock as Node3D).visible:
				far_shown += 1
	check(near_hidden > 0 and far_shown > 0, "Wall rocks drop out near the player and stay up farther along")
	cutaway.update(0, true, "", Vector3(-1000, 0, -1000))
	sections.reset()
	cutaway.update(0, true)
	for unused in range(8):
		await process_frame
	var space := stage.get_world_3d().direct_space_state
	for section: Dictionary in loader.manifest.data.spawnPoints:
		var p: Array = section.position
		check(not ground(space, Vector3(p[0], 0, p[2])).is_empty(), "Arrival has a rendered floor: " + str(section.id))
	for room: Dictionary in loader.manifest.data.chambers:
		var p: Array = room.position
		check(not ground(space, Vector3(p[0], 0, p[2])).is_empty(), "Chamber has a rendered floor: " + str(room.id))
	for p: Vector3 in [Vector3(120, 0, 120), Vector3(120, 0, 185), Vector3(55, 0, 120), Vector3(5, 0, 5)]:
		check(ground(space, p).is_empty(), "Blackspace is unfloored: " + str(p))
	# The Cenote Deeps' sinkhole pool (server tile 63,205) is water over a sunk bed, not floor.
	check(ground(space, Vector3(63, 0, 240 - 205)).is_empty(), "The cenote pool has no walk floor")
	var water := loader.world_root.find_child("Water_spindle_cavern*", true, false) as MeshInstance3D
	check(water != null and water.material_override is ShaderMaterial, "The cenote pool draws its water")
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world/objects.json"))
	var adapter := loader.manifest.coordinate_adapter()
	# The client's presentation path for this map: the package states none, so
	# the underground's own table lays out its Quartz seams and Salt pans.
	var main_script: Script = load("res://src/app/main.gd")
	var presented: Dictionary = main_script.call("map_presentation_of", "landfall_insides",
		loader.manifest.data, {}, reapply.harvest_presentation("landfall_insides"))
	var variants: Dictionary = catalog.harvestables.variants
	var laid_out := 0
	for node: Dictionary in loader.manifest.data.harvestables:
		var hint: Dictionary = (presented.nodes as Dictionary).get(int(node.objectId), {})
		var object := MapObject3D.new()
		stage.add_child(object)
		object.configure({"object_id":node.objectId, "kind":EloriaProtocol.MAP_OBJECT_HARVEST,
			"x":node.serverTile[0], "y":node.serverTile[1], "label":node.resource}, adapter, catalog,
			false, hint)
		check(not object.model_id.is_empty(), "Every underground resource uses imported art: " + str(node.resource))
		check(not object.get_node("Ring").visible, "Modelled resources keep the ring for active harvesting only")
		if str(node.resource) in ["Quartz", "Salt"]:
			var model := object.get_node_or_null("Model") as Node3D
			check(hint.has("variant") and hint.has("yaw") and model != null
				and object.model_id == str(variants[node.resource][int(hint.variant)])
				and absf(angle_difference(model.rotation.y, deg_to_rad(float(hint.yaw)))) < 1e-4,
				"Underground %s %d stands its stated variant at its stated yaw: %s"
				% [node.resource, int(node.objectId), object.model_id])
			laid_out += 1
	check(laid_out == 7, "All seven underground Quartz and Salt nodes are laid out: " + str(laid_out))
	for doorway: Dictionary in loader.manifest.data.portals:
		var object := MapObject3D.new()
		stage.add_child(object)
		object.configure({"object_id":doorway.objectId, "kind":EloriaProtocol.MAP_OBJECT_INTERACTIVE,
			"x":doorway.serverTile[0], "y":doorway.serverTile[1], "label":"Portal"}, adapter, catalog)
		check(object.offers_map_change(), "Doorway offers the server portal action")
		check(object.get_node_or_null("Model") == null and object.get_node_or_null("Ring") == null,
			"Doorway keeps the map's authored art")
		check(object.get_node("PickShape").shape.height >= 3.5, "Doorway has a full-height pick target")
	var captures := ""
	var args := OS.get_cmdline_user_args()
	if args.size() == 2 and args[0] == "--captures":
		captures = args[1]
	if not captures.is_empty():
		DirAccess.make_dir_recursive_absolute(captures)
		var env := WorldEnvironment.new()
		env.environment = Environment.new()
		stage.add_child(env)
		var sun := DirectionalLight3D.new()
		stage.add_child(sun)
		WorldEnvironmentBinder.apply(loader.manifest, env, sun)
		LightMarkerBinder.apply(loader.manifest, stage)
		var camera := Camera3D.new()
		camera.current = true
		camera.cull_mask = 1
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = 62
		camera.far = 500
		stage.add_child(camera)
		for section: Dictionary in loader.manifest.data.spawnPoints:
			var p: Array = section.position
			var centre := Vector3(float(p[0]), 0, float(p[2])-29)
			camera.look_at_from_position(centre+Vector3(0, 45, 50), centre, Vector3.UP)
			for unused in range(8):
				await process_frame
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(captures.path_join(str(section.id)+".png")) == OK, "Capture saves")
			camera.size = 23
			var room_focus := centre + Vector3(0,0,8)
			camera.look_at_from_position(room_focus+Vector3(0,18,19),room_focus,Vector3.UP)
			for unused in range(8): await process_frame
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(captures.path_join(str(section.id)+"-room.png")) == OK, "Room capture saves")
			camera.size = 62
		stage.queue_free()
		await process_frame
		var plan: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
			"res://../eloria-assets/maps/continent-v2/_continent_v2/content/underground.json"))
		for section: Dictionary in plan.sections:
			var e: Dictionary = section.entrance
			var p: Array = e.position
			var centre := Vector3(p[0], p[1], p[2])
			var exterior := Node3D.new()
			root.add_child(exterior)
			var exterior_loader := WorldLoader.new()
			exterior.add_child(exterior_loader)
			exterior_loader.load_world(ProjectSettings.globalize_path(
				"res://../eloria-assets/maps/continent-v2/"+str(e.map)+"/client/world.json"), centre)
			deadline = Time.get_ticks_msec()+90000
			var stream: ContinentChunkStream = exterior_loader.world_root
			while not framed_resident(stream, centre) and Time.get_ticks_msec()<deadline:
				await process_frame
			check(framed_resident(stream, centre), "Exterior entrance and framed neighbours load: "+str(e.map))
			await physics_frame
			var exterior_space := exterior.get_world_3d().direct_space_state
			var floor_hit := exterior_space.intersect_ray(PhysicsRayQueryParameters3D.create(
				centre+Vector3(0, 300, 0), centre-Vector3(0, 200, 0), 8))
			check(not floor_hit.is_empty(), "Exterior entrance has rendered ground: "+str(e.map))
			if not floor_hit.is_empty():
				print("Entrance ground ", e.map, ": authored=", centre.y, " rendered=", floor_hit.position.y)
				check(absf(floor_hit.position.y-centre.y)<2.0, "Exterior entrance matches ground height: "+str(e.map))
			var doorway := MapObject3D.new()
			exterior.add_child(doorway)
			doorway.configure({"object_id":e.object,"kind":EloriaProtocol.MAP_OBJECT_INTERACTIVE,
				"x":e.tile[0],"y":e.tile[1],"label":"Portal"},
				exterior_loader.manifest.coordinate_adapter(),catalog)
			if not floor_hit.is_empty(): doorway.set_surface_height(floor_hit.position.y)
			check(doorway.get_node_or_null("EntranceLabel") != null,
				"The real Portal label still shows the exterior entrance: "+str(e.map))
			check(doorway.get_node_or_null("EntranceModel") != null,
				"The exterior uses reviewed imported entrance art: "+str(e.map))
			var exterior_env := WorldEnvironment.new()
			exterior_env.environment = Environment.new()
			exterior.add_child(exterior_env)
			var exterior_sun := DirectionalLight3D.new()
			exterior.add_child(exterior_sun)
			WorldEnvironmentBinder.apply(exterior_loader.manifest, exterior_env, exterior_sun)
			var exterior_camera := Camera3D.new()
			exterior_camera.cull_mask = 3
			exterior_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
			exterior_camera.size = 20
			exterior_camera.current = true
			exterior.add_child(exterior_camera)
			exterior_camera.look_at_from_position(centre+Vector3(0, 15, 12), centre+Vector3(0, 1, 0), Vector3.UP)
			for unused in range(12):
				await process_frame
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(captures.path_join(str(section.id)+"-entrance.png")) == OK, "Entrance capture saves")
			await ContinentChunkStream.drain_workers(self)
			exterior.queue_free()
			await process_frame
	await ContinentChunkStream.drain_workers(self)
	if is_instance_valid(stage): stage.queue_free()
	for unused in range(8): await process_frame
	GlbSceneCache.clear()
	for unused in range(4): await process_frame
	print("Landfall underground: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures)")
	quit(0 if failures == 0 else 1)

func framed_resident(stream: ContinentChunkStream, position: Vector3) -> bool:
	if not stream.arrival_resident(position):
		return false
	for entry: Dictionary in stream.entries:
		if stream.bounds_distance(position, entry.bounds) <= 35.0 and not stream.cells.has(str(entry.id)):
			return false
	return true
