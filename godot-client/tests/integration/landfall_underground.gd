extends SceneTree
## Real-loader acceptance: floors, safe arrivals, roofs, blackspace and models.
## With -- --captures DIR it also saves player-view renders of each section.
## Pass 2 (2026-10-21): every door of a section (`entrances`), every passage
## between sections (its mouth, its portal, the section it lands in) and every
## wall vein node (its seam set into the rock face) are checked too.

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
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/world/underground-scenery.json"))
	var placements: Array = config.placements
	var plan: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://../eloria-assets/maps/continent-v2/_continent_v2/content/underground.json"))
	var cells := int(plan.map.cells)
	var listed: Array = loader.manifest.data.sections
	check(listed.size() == (plan.sections as Array).size() and listed.size() >= 4,
		"Every cave of the source is a section of the package: " + str(listed.size()))
	check(scenery != null and scenery.get_child_count() == placements.size(),
		"All reviewed imported scenery placements load")
	for section: Dictionary in listed:
		var inside := placements.filter(func(p: Dictionary) -> bool: return _in_bounds(p.position, section.bounds))
		# a pocket (pass 2: 150-450 tiles) has the wall rocks of its short wall; a cave has twenty and more
		var lo: Array = section.bounds["min"]
		var hi: Array = section.bounds["max"]
		var needed := 20 if (float(hi[0]) - float(lo[0])) * (float(hi[1]) - float(lo[1])) >= 1600.0 else 12
		check(inside.size() >= needed, "Every cave is dressed in kit scenery: %s (%d)" % [section.id, inside.size()])
		check((config.get("surfaces", {}) as Dictionary).has(str(section.id)),
			"Every cave states its surfaces: " + str(section.id))
	var reapply := preload("res://src/world/underground_scenery.gd")
	check(reapply.apply(loader.manifest, loader.world_root) == 0,
		"Applying presentation twice does not duplicate scenery")
	var cutaway := InteriorCutaway.new()
	check(cutaway.configure(loader.manifest, loader.world_root) > 4, "Roof and wall cutaways resolve")
	cutaway.update(0, true)
	# Only the cave the player stands in is drawn (the manifest is `sectioned`).
	var sections := SecretSections.new()
	check(sections.configure(loader.manifest, loader.world_root) > 0, "The underground's caves sort into sections")
	var near_hidden := {}
	var far_shown := 0
	var pillar_runs := 0
	for spawn: Dictionary in loader.manifest.data.spawnPoints:
		var id := str(spawn.section)
		var at: Array = spawn.position
		sections.update(Vector3(at[0], 0, at[2]), true)
		cutaway.update(0, false, sections.current_section())
		var own_floor := loader.world_root.find_child("Walk_" + id + "_*", true, false) as Node3D
		var others_hidden := true
		for other: Dictionary in listed:
			if str(other.id) == id:
				continue
			var floor_node := loader.world_root.find_child("Walk_" + str(other.id) + "_*", true, false) as Node3D
			var wall := loader.world_root.find_child("Build_" + str(other.id) + "_*", true, false) as Node3D
			others_hidden = others_hidden and floor_node != null and not floor_node.visible \
				and wall != null and not wall.visible
		check(sections.current_section() == id and own_floor != null and own_floor.visible and others_hidden,
			"Only the cave the player is in is drawn, other caves' walls stay hidden: " + id)
		var roof := loader.world_root.find_child("Roof_" + id + "_*", true, false) as Node3D
		check(roof != null and not roof.visible, "Entering a cave keeps its roof cut away: " + id)
		# Rocks set into the walls drop out near the player while their wall faces
		# the camera (yaw 0: the camera is to +Z); farther along they stay up.
		var rocks: Array = scenery.get_children().filter(func(rock: Node) -> bool:
			return rock.has_meta("cutaway_outward") and sections._section_at(
				Vector2((rock as Node3D).position.x, (rock as Node3D).position.z)) == id)
		check(not rocks.is_empty(), "Every cave's walls are lined with kit rocks: " + id)
		var facing: Array = rocks.filter(func(rock: Node) -> bool:
			return (rock.get_meta("cutaway_outward") as Vector3).z > 0.8)
		if not facing.is_empty():
			var rock := facing[facing.size() / 2] as Node3D
			var focus := rock.position - Vector3(0, 0, 5)
			cutaway.update(0, true, id, focus)
			near_hidden[id] = not rock.visible
			for other: Node in facing:
				if (other as Node3D).position.distance_to(focus) > 20.0 and (other as Node3D).visible:
					far_shown += 1
		check(bool(near_hidden.get(id, false)), "A wall rock drops out near the player on the camera's side: " + id)
		# A looping cave's rock pillars are walled; a run of a pillar's face drops out
		# near the player on the camera's side and stands farther off.
		for wall: Dictionary in loader.manifest.data.cutaway.walls:
			if str(wall.get("section", "")) != id or not wall.has("centre"):
				continue
			pillar_runs += 1
			if pillar_runs % 7 != 1:
				continue
			var outward := Vector3(wall.outward[0], 0, wall.outward[2]).normalized()
			var centre := Vector3(wall.centre[0], 0, wall.centre[1])
			var node := loader.world_root.find_child(str(wall.node), true, false) as Node3D
			var yaw := rad_to_deg(atan2(outward.x, outward.z))
			cutaway.update(yaw, true, id, centre - outward * 5.0)
			var dropped := node != null and not node.visible
			cutaway.update(yaw, true, id, centre - outward * 40.0)
			check(dropped and node.visible,
				"A pillar's face drops out near the player and stands farther off: " + str(wall.node))
	check(far_shown > 0, "Wall rocks farther along stay up")
	var looping := (plan.sections as Array).filter(func(s: Dictionary) -> bool:
		return (s.links as Array).size() >= (s.rooms as Array).size())
	check(looping.is_empty() or pillar_runs > 0, "Looping caves wall their rock pillars: " + str(pillar_runs))
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
	# Blackspace between the caves has no floor at all.
	var blank := 0
	for gx in range(5, cells, 20):
		for gz in range(5, cells, 20):
			var point := Vector3(gx, 0, gz)
			if listed.any(func(s: Dictionary) -> bool: return _in_bounds([gx, 0, gz], s.bounds, 4.0)):
				continue
			blank += 1
			check(ground(space, point).is_empty(), "Blackspace is unfloored: " + str(point))
	check(blank > 100, "Blackspace sampled between the caves: " + str(blank))
	# Pools are water over a sunk bed, not floor, in every cave that has them.
	for section: Dictionary in plan.sections:
		for pool: Array in section.get("pools", []):
			check(ground(space, Vector3(pool[0], 0, cells - float(pool[1]))).is_empty(),
				"A pool has no walk floor: %s %s" % [section.id, pool])
		if not (section.get("pools", []) as Array).is_empty():
			var water := loader.world_root.find_child("Water_" + str(section.id) + "_*", true, false) as MeshInstance3D
			check(water != null and water.material_override is ShaderMaterial, "The pools draw their water: " + str(section.id))
	# Walkable ledges (a section's `ledges`): the rendered walk surface climbs each ramp from the floor to its terrace.
	for section: Dictionary in plan.sections:
		for ledge: Dictionary in section.get("ledges", []):
			for ramp: Array in ledge.get("ramps", []):
				var foot := ground(space, Vector3(ramp[0], 0, cells - float(ramp[1])))
				var top := ground(space, Vector3(ramp[2], 0, cells - float(ramp[3])))
				check(not foot.is_empty() and not top.is_empty() and absf((foot.position as Vector3).y) < 0.05
					and absf((top.position as Vector3).y - float(ledge.height)) < 0.05,
					"A ledge's ramp climbs from the floor to its terrace: %s %s" % [section.id, ramp])
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world/objects.json"))
	var adapter := loader.manifest.coordinate_adapter()
	# The client's presentation path for this map: the package states none, so
	# the underground's own table lays out its seams, pans, banks and mats.
	var main_script: Script = load("res://src/app/main.gd")
	var presented: Dictionary = main_script.call("map_presentation_of", "landfall_insides",
		loader.manifest.data, {}, reapply.harvest_presentation("landfall_insides"))
	var variants: Dictionary = catalog.harvestables.variants
	var table: Dictionary = reapply.harvest_presentation("landfall_insides")
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
		# a wall node (a vein: placement wall) is checked below, set into its face
		if table.has(str(int(node.objectId))) and str((table[str(int(node.objectId))] as Dictionary).get("placement", "")) != "wall":
			var model := object.get_node_or_null("Model") as Node3D
			check(hint.has("variant") and hint.has("yaw") and model != null
				and object.model_id == str(variants[node.resource][int(hint.variant)])
				and absf(angle_difference(model.rotation.y, deg_to_rad(float(hint.yaw)))) < 1e-4,
				"Underground %s %d stands its stated variant at its stated yaw: %s"
				% [node.resource, int(node.objectId), object.model_id])
			laid_out += 1
	var floor_table := table.values().filter(func(h: Dictionary) -> bool: return str(h.get("placement", "")) != "wall").size()
	check(laid_out == floor_table and laid_out >= 7,
		"Every laid-out underground node stands its stated variant: %d of %d" % [laid_out, floor_table])
	var names := {}
	for section: Dictionary in plan.sections:
		names[str(section.id)] = str(section.name)
	var own_map := str(loader.manifest.data.asset.id)
	var passages := 0
	sections.configure(loader.manifest, loader.world_root)
	for doorway: Dictionary in loader.manifest.data.portals:
		var object := MapObject3D.new()
		stage.add_child(object)
		var passage := str(doorway.destinationMap) == own_map
		var detail := ("A way leads on into %s. Danger." % names.get(str(doorway.get("destinationSection", "")), "")) \
			if passage else ""
		object.configure({"object_id":doorway.objectId, "kind":EloriaProtocol.MAP_OBJECT_INTERACTIVE,
			"x":doorway.serverTile[0], "y":doorway.serverTile[1], "label":"Portal", "detail":detail}, adapter, catalog)
		check(object.offers_map_change(), "Doorway offers the server portal action")
		check(object.get_node_or_null("Model") == null and object.get_node_or_null("Ring") == null,
			"Doorway keeps the map's authored art")
		check(object.get_node("PickShape").shape.height >= 3.5, "Doorway has a full-height pick target")
		if not passage:
			continue
		# A passage end: the way on stands in its own section and lands in the other one, where the client then
		# shows only that section (SecretSections), and its mouth is drawn in its section's rock.
		passages += 1
		var from := str(doorway.section)
		var to := str(doorway.destinationSection)
		check(object.destination() == names.get(to, "?"), "A passage names the section it leads into: " + str(doorway.id))
		var here: Vector3 = adapter.tile_center(int(doorway.serverTile[0]), int(doorway.serverTile[1]))
		var there: Vector3 = adapter.tile_center(int(doorway.destinationTile[0]), int(doorway.destinationTile[1]))
		sections.update(here, true)
		check(sections.current_section() == from, "A passage's way on stands in its own section: " + str(doorway.id))
		sections.update(there, true)
		cutaway.update(0, false, sections.current_section(), there)
		var arrived_floor := loader.world_root.find_child("Walk_" + to + "_*", true, false) as Node3D
		var left_floor := loader.world_root.find_child("Walk_" + from + "_*", true, false) as Node3D
		check(sections.current_section() == to and arrived_floor != null and arrived_floor.visible
			and left_floor != null and not left_floor.visible,
			"Using a passage shows the section it lands in, alone: %s -> %s" % [from, to])
		var mouths := loader.world_root.find_children("Build_" + from + "_mouth*", "MeshInstance3D", true, false)
		check(not mouths.is_empty(), "A passage end's mouth is drawn in its section's rock: " + str(doorway.id))
		check((loader.manifest.data.cutaway.walls as Array).any(func(wall: Dictionary) -> bool:
			return str(wall.node).begins_with("Build_" + from + "_mouth") and str(wall.section) == from),
			"A passage mouth is cut away with its wall: " + str(doorway.id))
	var source_passages := 0
	for passage: Dictionary in plan.get("passages", []):
		source_passages += (passage.ends as Array).size()
	check(passages == source_passages, "Every passage end of the source is a portal: %d of %d" % [passages, source_passages])
	sections.reset()
	cutaway.update(0, true)
	# Wall vein nodes stand their label's wall seam set into the rock face: the seam's origin a hand's breadth
	# behind the face a ray from the node's tile meets (the walls are world collision, layer 1).
	var wall_nodes := 0
	var wall_variants: Dictionary = catalog.harvestables.get("wallVariants", {})
	for node: Dictionary in loader.manifest.data.harvestables:
		var hint: Dictionary = table.get(str(int(node.objectId)), {})
		if str(hint.get("placement", "")) != "wall":
			continue
		wall_nodes += 1
		var object := MapObject3D.new()
		stage.add_child(object)
		object.configure({"object_id":node.objectId, "kind":EloriaProtocol.MAP_OBJECT_HARVEST,
			"x":node.serverTile[0], "y":node.serverTile[1], "label":node.resource}, adapter, catalog,
			false, (presented.nodes as Dictionary).get(int(node.objectId), {}))
		var model := object.get_node_or_null("Model") as Node3D
		check(object.is_wall_placed() and model != null
			and ((wall_variants.get(str(node.resource), []) as Array).has(object.model_id) if wall_variants.has(str(node.resource))
				else object.model_id == str(catalog.harvestables.resources.get(str(node.resource), ""))),
			"A wall node stands its label's wall seam: %d %s %s" % [int(node.objectId), node.resource, object.model_id])
		if model == null:
			continue
		var facing := Vector3(sin(deg_to_rad(float(hint.yaw))), 0, cos(deg_to_rad(float(hint.yaw))))
		var start := object.global_position + Vector3.UP
		var hit := stage.get_world_3d().direct_space_state.intersect_ray(
			PhysicsRayQueryParameters3D.create(start, start - facing * 4.0, 1))
		var seam := model.global_position
		check(not hit.is_empty() and absf(((hit.position as Vector3) - start).length()
			- (Vector2(seam.x, seam.z) - Vector2(start.x, start.z)).length()) < 0.6,
			"A wall seam is set into its rock face: %d (face %s, seam %s)" % [int(node.objectId),
			hit.get("position"), seam])
	check(wall_nodes == table.values().filter(func(h: Dictionary) -> bool:
		return str(h.get("placement", "")) == "wall").size(), "Every wall node of the table was checked: " + str(wall_nodes))
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
			# Framed on the cave's bounds, then on its largest room.
			var own: Array = listed.filter(func(s: Dictionary) -> bool: return str(s.id) == str(section.section))
			var lo: Array = own[0].bounds["min"]
			var hi: Array = own[0].bounds["max"]
			var centre := Vector3((float(lo[0]) + float(hi[0])) / 2, 0, (float(lo[1]) + float(hi[1])) / 2)
			camera.size = maxf(62.0, (float(hi[0]) - float(lo[0])) * 0.6)
			camera.look_at_from_position(centre+Vector3(0, 45, 50), centre, Vector3.UP)
			for unused in range(8):
				await process_frame
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(captures.path_join(str(section.id)+".png")) == OK, "Capture saves")
			camera.size = 23
			var rooms: Array = (loader.manifest.data.chambers as Array).filter(func(c: Dictionary) -> bool:
				return str(c.section) == str(section.section))
			rooms.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return float(a.radius) > float(b.radius))
			var room_at: Array = rooms[0].position
			var room_focus := Vector3(float(room_at[0]), 0, float(room_at[2]))
			camera.look_at_from_position(room_focus+Vector3(0,18,19),room_focus,Vector3.UP)
			for unused in range(8): await process_frame
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(captures.path_join(str(section.id)+"-room.png")) == OK, "Room capture saves")
			camera.size = 62
		stage.queue_free()
		await process_frame
		var doors: Array = []
		for section: Dictionary in plan.sections:
			var own_doors: Array = section.get("entrances", [section.entrance] if section.has("entrance") else [])
			for index in own_doors.size():
				doors.append([section, own_doors[index], index])
		for pair: Array in doors:
			var section: Dictionary = pair[0]
			var e: Dictionary = pair[1]
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
			var door_name := str(section.id) + ("" if int(pair[2]) == 0 else "-door" + str(int(pair[2])))
			check(root.get_texture().get_image().save_png(captures.path_join(door_name+"-entrance.png")) == OK, "Entrance capture saves")
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

## Whether a placement or point [x, y, z] lies in a manifest section's X/Z bounds (plus `margin` metres).
func _in_bounds(position: Array, bounds: Dictionary, margin := 0.0) -> bool:
	var lo: Array = bounds["min"]
	var hi: Array = bounds["max"]
	return float(position[0]) >= float(lo[0]) - margin and float(position[0]) <= float(hi[0]) + margin \
		and float(position[2]) >= float(lo[1]) - margin and float(position[2]) <= float(hi[1]) + margin

func framed_resident(stream: ContinentChunkStream, position: Vector3) -> bool:
	if not stream.arrival_resident(position):
		return false
	for entry: Dictionary in stream.entries:
		if stream.bounds_distance(position, entry.bounds) <= 35.0 and not stream.cells.has(str(entry.id)):
			return false
	return true
