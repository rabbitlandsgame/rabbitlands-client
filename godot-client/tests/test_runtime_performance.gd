extends SceneTree
## Guards the runtime-cost work: the map SubViewports must stay idle while their
## UI is hidden, the surface sampler must not re-query physics for an actor that
## has not moved, the animation importer must rebuild only the clips an actor
## can play, and the glTF cache must parse a file once. Then the per-packet
## work: item icons are shared, only the actors that changed are re-presented,
## a hidden statistics window is not rebuilt, a chat line is appended rather
## than the logs rebuilt, the animation library is parsed ahead of the first
## actor, and a pack of actors is built over several frames.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var scene: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(scene)
	await process_frame

	var map_viewport: SubViewport = scene.get_node("%MapViewport")
	var full_map_viewport: SubViewport = scene.get_node("%FullMapViewport")
	var preview_viewport: SubViewport = scene.get_node(
		"CreationPanel/Columns/CharacterPreview/Viewport")
	var minimap_frame: Control = scene.get_node("%MinimapFrame")
	var full_map: Control = scene.get_node("%FullMap")
	var map_image: Control = scene.get_node("%MapImage")

	_expect(map_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"minimap viewport ships idle instead of redrawing the world every frame")
	_expect(full_map_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"full-map viewport ships idle")
	_expect(preview_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"character preview viewport ships idle")

	minimap_frame.hide()
	full_map.hide()
	scene.call("_request_map_redraw")
	scene.call("_update_map_viewports")
	_expect(map_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"a hidden minimap requests no redraw")
	_expect(full_map_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"a hidden full map requests no redraw")

	minimap_frame.show()
	full_map.show()
	map_image.show()
	scene.call("_request_map_redraw")
	scene.call("_update_map_viewports")
	_expect(map_viewport.render_target_update_mode == SubViewport.UPDATE_ONCE,
		"a visible minimap requests a single redraw")
	_expect(full_map_viewport.render_target_update_mode == SubViewport.UPDATE_ONCE,
		"a visible full map requests a single redraw")

	map_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	scene.call("_update_map_viewports")
	_expect(map_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"minimap redraws are throttled rather than requested every frame")
	minimap_frame.hide()
	full_map.hide()

	# The map-load and toggle path runs on every map load and every full-map
	# toggle. It used to set UPDATE_ALWAYS for a visible panel, which put the
	# world back on full-rate rendering for up to one throttle interval and
	# undid the throttle it shares the file with. It may only ever idle a
	# viewport or request its single first frame.
	minimap_frame.show()
	full_map.show()
	map_image.show()
	scene.call("_sync_map_viewport_activity")
	_expect(map_viewport.render_target_update_mode == SubViewport.UPDATE_ONCE
		and full_map_viewport.render_target_update_mode == SubViewport.UPDATE_ONCE,
		"a map load with both panels visible requests one frame, not continuous redraw")
	minimap_frame.hide()
	full_map.hide()
	scene.call("_sync_map_viewport_activity")
	_expect(map_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED
		and full_map_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"a map load with both panels hidden idles both viewports")

	# The toggle paths themselves: opening the tab map or the minimap must not
	# reach UPDATE_ALWAYS either, and closing them must idle immediately.
	scene.call("_toggle_full_map")
	_expect(full_map.visible
		and full_map_viewport.render_target_update_mode == SubViewport.UPDATE_ONCE,
		"opening the tab map requests one redraw")
	scene.call("_show_continent_view")
	_expect(full_map_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"switching the tab map to the continent view idles the world render")
	scene.call("_show_current_map_view")
	_expect(full_map_viewport.render_target_update_mode == SubViewport.UPDATE_ONCE,
		"switching back to the live map requests one redraw")
	scene.call("_toggle_full_map")
	_expect(not full_map.visible
		and full_map_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"closing the tab map idles its viewport")
	scene.call("_toggle_minimap")
	_expect(minimap_frame.visible
		and map_viewport.render_target_update_mode == SubViewport.UPDATE_ONCE,
		"showing the minimap requests one redraw")
	scene.call("_toggle_minimap")
	_expect(not minimap_frame.visible
		and map_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"hiding the minimap idles its viewport")

	# The surface sampler is the per-actor physics query; it must be skipped for
	# an actor that has not moved since the last sample.
	var actor := ReplicatedActor3D.new()
	actor.actor_id = 4242
	actor.server_target = Vector3(3.0, 0.0, 7.0)
	scene.get_node("%WorldRoot").add_child(actor)
	var samples: Dictionary = scene.get("_actor_surface_samples")
	samples.clear()
	scene.call("_place_actor_on_surface", actor)
	_expect(samples.has(4242), "the first placement samples the rendered surface")
	var recorded: Variant = samples[4242]
	scene.call("_place_actor_on_surface", actor)
	_expect(samples[4242] == recorded, "an unmoved actor is not re-sampled")
	actor.server_target = Vector3(9.0, 0.0, 7.0)
	scene.call("_place_actor_on_surface", actor)
	_expect(samples[4242] != recorded, "a moved actor is re-sampled")
	actor.queue_free()

	# Only the clips the action map can request are worth rebuilding.
	var resolver := AnimationResolver.new({
		"actions": {"idle": "Idle_A", "walk": "Walk", "run": "Walk"}})
	var required: PackedStringArray = resolver.required_clips()
	_expect(required.size() == 2 and required.has("Idle_A") and required.has("Walk"),
		"the resolver reports each distinct clip once")

	# Packet decoding in place, so draining a burst does not re-copy the buffer.
	var burst := EloriaProtocol.encode(1, PackedByteArray([7, 8]))
	burst.append_array(EloriaProtocol.encode(2, PackedByteArray([9])))
	var first: Dictionary = EloriaProtocol.try_decode(burst)
	var second: Dictionary = EloriaProtocol.try_decode(burst, int(first.consumed))
	_expect(first.status == "ok" and int(first.command) == 1,
		"the first packet of a burst decodes at offset zero")
	_expect(second.status == "ok" and int(second.command) == 2,
		"the second packet decodes in place at an offset")

	# The decoders' lookup tables are constants of the class, not literals
	# inside the functions that read them. A partial-stat packet arrives with
	# every health, food and experience tick and every stat in one asks for its
	# name, so a table built inside `stat_key` was built again per stat.
	_expect(EloriaProtocol.STAT_SLOT_KEYS.size() > 80
		and str(EloriaProtocol.STAT_SLOT_KEYS[42]) == "health",
		"the partial-stat slot names are a shared constant")
	_expect(EloriaProtocol.stat_key(42) == "health"
		and EloriaProtocol.stat_key(999) == "slot_999",
		"stat_key answers out of that table and still names an unknown slot")
	_expect(EloriaProtocol.STATS_ATTRIBUTE_NAMES.size() == 12
		and EloriaProtocol.STATS_SKILL_LEVEL_SLOTS.size() == 13
		and EloriaProtocol.STATS_EXPERIENCE_SLOTS.size() == 13
		and EloriaProtocol.STATS_RESOURCE_NAMES.size() == 6,
		"the full statistics packet's slot tables are constants too")
	var stat_burst := PackedByteArray()
	for slot: int in [42, 43, 46]:
		stat_burst.append(slot)
		stat_burst.append_array(PackedByteArray([7, 0, 0, 0]))
	var decoded_stats: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.SEND_PARTIAL_STAT, stat_burst)
	_expect(decoded_stats.type == "partial_stats"
		and int((decoded_stats.values as Dictionary)["health"]) == 7
		and int((decoded_stats.values as Dictionary)["max_health"]) == 7
		and int((decoded_stats.values as Dictionary)["food"]) == 7,
		"a partial-stat packet still names every stat it carries")

	# A chat line is copied once and read twice, not copied for each reading.
	var chat_payload := PackedByteArray([3, 127 + 4])
	chat_payload.append_array("Hello".to_utf8_buffer())
	chat_payload.append(0)
	var decoded_chat: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.RAW_TEXT, chat_payload)
	_expect(decoded_chat.type == "chat" and int(decoded_chat.channel) == 3
		and str(decoded_chat.text) == "Hello" and int(decoded_chat.colour) == 4,
		"the colour and the text of a chat line both come off one copy of it")

	# Item icons are built once per picture and shared, not rebuilt per slot
	# per refresh.
	var atlas: RefCounted = scene.get("item_atlas")
	_expect(is_same(atlas.icon_for(3), atlas.icon_for(3)),
		"an item icon is built once and shared")
	_expect(not is_same(atlas.icon_for(3), atlas.icon_for(4)),
		"different pictures get different icons")

	# AppState names the actors it wrote, so a flush visits only those.
	var app_state: Node = root.get_node("AppState")
	app_state.set("authenticated", false)
	app_state.set("actors", {
		7: {"actor_id": 7, "x": 1, "y": 1, "rotation": 0, "actor_type": 1,
			"kind": 1, "name": "Seven", "health": 5, "max_health": 9},
		8: {"actor_id": 8, "x": 2, "y": 1, "rotation": 0, "actor_type": 1,
			"kind": 1, "name": "Eight", "health": 5, "max_health": 9}})
	app_state.call("take_changed_actors")
	app_state.call("_on_packet", EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND,
		PackedByteArray([7, 0, 20]))
	var changed: Dictionary = app_state.call("take_changed_actors")
	_expect(changed.has(7) and not changed.has(8),
		"an actor that moved is in the change set and one that stood still is not")
	_expect((app_state.call("take_changed_actors") as Dictionary).is_empty(),
		"taking the change set empties it")
	app_state.call("mark_all_actors_changed")
	_expect((app_state.call("take_changed_actors") as Dictionary).size() == 2,
		"the footprint table marks every actor")

	# The statistics window is not rebuilt while it is hidden.
	var stats_panel: Control = scene.get_node("%StatsPanel")
	var perk_line: Label = scene.get("stats_perk_line")
	stats_panel.hide()
	perk_line.text = "untouched"
	app_state.set("stats", {"health": 3, "max_health": 9})
	scene.call("_sync_stats")
	_expect(perk_line.text == "untouched",
		"a stats packet leaves a hidden statistics window alone")
	stats_panel.show()
	_expect(perk_line.text.begins_with("Perks:"),
		"showing the statistics window rebuilds it")
	stats_panel.hide()

	# A chat line is appended to the logs rather than rebuilding them, and the
	# panel keeps to its cap.
	var chat_output: RichTextLabel = scene.get_node("%ChatOutput")
	var lines: Array = app_state.get("chat_lines")
	lines.clear()
	for index: int in range(3):
		lines.append({"channel": 0, "text": "line %d" % index})
	scene.call("_sync_chat")
	var paragraphs: int = chat_output.get_paragraph_count()
	app_state.set("authenticated", true)
	app_state.call("append_local_message", "one more line", 0)
	_expect(chat_output.get_paragraph_count() == paragraphs + 1
		and chat_output.get_parsed_text().contains("one more line"),
		"a new chat line is appended to the panel")
	for index: int in range(120):
		app_state.call("append_local_message", "filler %d" % index, 0)
	_expect(chat_output.get_paragraph_count() == 101,
		"the chat panel keeps its hundred newest lines")
	_expect(chat_output.get_parsed_text().contains("filler 119")
		and not chat_output.get_parsed_text().contains("one more line"),
		"the oldest lines are the ones dropped")
	app_state.set("authenticated", false)

	# The shared animation library is parsed ahead of the first actor, and a
	# pack of actors is built over several frames rather than in one.
	var library: String = ProjectSettings.globalize_path(
		"res://assets/actors/native/shared/Universal_Animation_Library.glb")
	NativeAnimationImporter.prewarm(library)
	_expect(NativeAnimationImporter.is_prewarming(library)
		or NativeAnimationImporter.has_source(library),
		"prewarming starts the library parse")
	var pack: Dictionary = {}
	for index: int in range(7):
		pack[300 + index] = {"actor_id": 300 + index, "x": 3 + index, "y": 4,
			"rotation": 0, "actor_type": 1, "kind": 1, "name": "Pack %d" % index,
			"health": 5, "max_health": 9}
	app_state.set("actors", pack)
	scene.call("_sync_world")
	var nodes: Dictionary = scene.get("actor_nodes")
	_expect(nodes.size() == 4, "one pass builds at most the spawn budget of actors")
	for unused: int in range(4):
		await process_frame
	_expect(nodes.size() == 7, "the rest of the pack follows on the next frames")
	_expect(NativeAnimationImporter.has_source(library),
		"the first actor used the prewarmed library")
	app_state.set("actors", {})
	scene.call("_sync_world")
	NativeAnimationImporter.clear()

	# The presentation record is copied shallowly: two keys are replaced and
	# nothing that reads it writes into what is left.
	var record: Dictionary = {"actor_id": 11, "x": 4, "y": 5, "rotation": 0,
		"actor_type": 1, "kind": 1, "name": "Shallow", "health": 5,
		"max_health": 9, "appearance": {"hair": 2},
		"equipment_fallback_parts": [3]}
	var presented: Dictionary = scene.call("_presentation_dto", record)
	_expect(not is_same(presented, record),
		"the presentation record is a copy, so its own keys do not reach AppState")
	_expect(is_same(presented["appearance"], record["appearance"])
		and is_same(presented["equipment_fallback_parts"],
			record["equipment_fallback_parts"]),
		"what it does not replace is shared rather than copied a level at a time")
	_expect(not is_same(presented["equipment_visuals"],
		record.get("equipment_visuals")),
		"the wardrobe it does build is its own")

	# An actor packet restates the whole wardrobe. Asking for what is already
	# worn does nothing, and the first pass always runs in full.
	await _check_wardrobe_repeat()

	# A region names the same mesh on hundreds of nodes. The trimesh shape only
	# depends on the mesh, so it is built once per mesh per load and shared by
	# every body standing on it, and the import is walked once for every pass
	# that wanted a list of it.
	await _check_world_loader()

	# Godot's scene builder checks every name it adds against the children the
	# parent already holds, so a package that hangs eight thousand nodes off one
	# node is quadratic to build. Over-wide sibling lists are bucketed under
	# empty groups before the scene is generated.
	_check_sibling_regrouping()

	print("runtime performance tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	scene.queue_free()
	await process_frame
	quit(failures)

func _check_wardrobe_repeat() -> void:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var model := Node3D.new()
	model.name = "NativeModel"
	actor.add_child(model)
	# The one surface the cover pass writes to on every run: a wardrobe shirt
	# with a colour of its own and an override to put it on.
	var shirt := MeshInstance3D.new()
	shirt.name = "wardrobe_shirt"
	shirt.mesh = BoxMesh.new()
	shirt.set_meta("wardrobe_color", Color.SEA_GREEN)
	var material := StandardMaterial3D.new()
	shirt.material_override = material
	model.add_child(shirt)
	await process_frame

	actor.apply_equipment_visuals({}, [])
	_expect(material.albedo_color == Color.SEA_GREEN,
		"the first wardrobe pass runs in full however little it changes")
	material.albedo_color = Color.MAGENTA
	actor.apply_equipment_visuals({}, [])
	_expect(material.albedo_color == Color.MAGENTA,
		"asking again for the clothes already worn does nothing")
	_expect(not actor.call("_equipment_matches", {5: 208}, []),
		"a wardrobe that differs is not mistaken for the one worn")
	# The part loop's own second condition: a part the server offers a fallback
	# for is rebuilt while it has no nodes, so the pass may not be skipped.
	actor.set("_equipment_visuals", {5: 208})
	actor.set("_equipment_nodes", {})
	_expect(actor.call("_equipment_matches", {5: 208}, []),
		"the same visual on the same part is a match")
	_expect(not actor.call("_equipment_matches", {5: 208}, [5]),
		"a part offered a fallback with nothing built for it is not")
	actor.queue_free()
	await process_frame

func _check_world_loader() -> void:
	var loader := WorldLoader.new()
	root.add_child(loader)
	var world := Node3D.new()
	world.name = "ImportedWorld_probe"
	loader.add_child(world)
	loader.world_root = world
	var manifest := WorldManifest.new()
	manifest.data = {
		"schemaVersion": "1.0",
		"asset": {"id": "loader_probe", "glb": "world.glb", "units": "meters",
			"coordinateSystem": {"upAxis": "Y"}, "bounds": {}},
		"collision": {"nodeNames": ["Wall_1", "Wall_2", "Wall_3", "Gate_1"]},
		"navigation": {"surfaceNodePrefixes": ["Terrain_"]}}
	loader.manifest = manifest

	# Three walls off one mesh, a gate off another, two terrain tiles off a
	# third: nine bodies' worth of declarations over three meshes.
	var wall_mesh := BoxMesh.new()
	var gate_mesh := BoxMesh.new()
	var terrain_mesh := PlaneMesh.new()
	for entry: Array in [["Wall_1", wall_mesh], ["Wall_2", wall_mesh],
			["Wall_3", wall_mesh], ["Gate_1", gate_mesh],
			["Terrain_A", terrain_mesh], ["Terrain_B", terrain_mesh]]:
		var instance := MeshInstance3D.new()
		instance.name = str(entry[0])
		instance.mesh = entry[1] as Mesh
		world.add_child(instance)
	await process_frame

	var index: Dictionary = loader.call("_index_import")
	var listed: Array = index["meshInstances"] as Array
	_expect(listed.size() == 6,
		"one walk of the import lists every mesh instance exactly once")
	_expect((index["byName"] as Dictionary).size() == 6
		and (index["byName"] as Dictionary).has("Gate_1"),
		"the same walk indexes the nodes the collision declarations name")

	loader.call("_apply_collision_declarations", index["byName"])
	loader.call("_apply_rendered_walk_surfaces", listed)
	var shapes: Dictionary = {}
	for instance_value: Variant in listed:
		var instance: MeshInstance3D = instance_value as MeshInstance3D
		var body: StaticBody3D = null
		for child: Node in instance.get_children():
			if child is StaticBody3D:
				body = child as StaticBody3D
		if not _returns(body != null, str(instance.name) + " got its collision body"):
			continue
		var collision: CollisionShape3D = body.get_child(0) as CollisionShape3D
		shapes[instance.name] = collision.shape

	_expect(is_same(shapes.get("Wall_1"), shapes.get("Wall_2"))
		and is_same(shapes.get("Wall_1"), shapes.get("Wall_3")),
		"three nodes off one mesh share one trimesh shape instead of three")
	_expect(is_same(shapes.get("Terrain_A"), shapes.get("Terrain_B")),
		"two walk surfaces off one mesh share one shape too")
	_expect(not is_same(shapes.get("Wall_1"), shapes.get("Gate_1"))
		and not is_same(shapes.get("Wall_1"), shapes.get("Terrain_A")),
		"a different mesh gets its own shape")
	var shared: ConcavePolygonShape3D = shapes.get("Wall_1") as ConcavePolygonShape3D
	_expect(shared != null
		and shared.get_faces() == wall_mesh.create_trimesh_shape().get_faces(),
		"the shared shape holds the faces the mesh's own trimesh shape does")

	# The table is per load: a second map must not be handed the last one's
	# geometry.
	loader.unload_world()
	_expect((loader.get("_collision_shapes") as Dictionary).is_empty(),
		"unloading drops the shapes built for the map that just left")
	loader.queue_free()
	await process_frame

## The regrouping pass on a synthetic glTF state: one parent holding more
## children than the loader will hand to Godot, one narrow parent beside it and
## a wide list of scene roots. What must survive is every node, its transform,
## its order and its place under the same ancestor - only the depth may change.
func _check_sibling_regrouping() -> void:
	var loader := WorldLoader.new()
	var manifest := WorldManifest.new()
	manifest.data = {"asset": {"id": "regroup_probe"}}
	loader.manifest = manifest

	var wide: int = WorldLoader.MAX_SIBLINGS * 3
	var nodes: Array[GLTFNode] = []
	var trunk := GLTFNode.new()
	trunk.set_name("Trunk")
	nodes.append(trunk)
	var branch := GLTFNode.new()
	branch.set_name("Branch")
	branch.parent = 0
	nodes.append(branch)
	var trunk_children := PackedInt32Array([1])
	var expected_order: PackedStringArray = PackedStringArray(["Branch"])
	for index: int in range(wide):
		var leaf := GLTFNode.new()
		leaf.set_name("Leaf_%d" % index)
		leaf.position = Vector3(float(index), 0.0, 0.0)
		leaf.parent = 0
		nodes.append(leaf)
		trunk_children.append(nodes.size() - 1)
		expected_order.append(leaf.get_name())
	trunk.set_children(trunk_children)
	# A second root beside the trunk, so the root list is exercised too.
	var roots := PackedInt32Array([0])
	for index: int in range(wide):
		var loose := GLTFNode.new()
		loose.set_name("Loose_%d" % index)
		nodes.append(loose)
		roots.append(nodes.size() - 1)

	var state := GLTFState.new()
	state.set_nodes(nodes)
	state.root_nodes = roots
	var added: int = loader.call("_regroup_wide_siblings", state)
	_expect(added > 0, "a package wider than the limit is regrouped")

	var regrouped: Array = state.get_nodes()
	_expect(regrouped.size() == nodes.size() + added,
		"regrouping adds groups and removes nothing")
	# No sibling list anywhere - the roots included - may still be over-wide.
	var widest: int = state.root_nodes.size()
	for node_value: Variant in regrouped:
		widest = maxi(widest, (node_value as GLTFNode).get_children().size())
	_expect(widest <= WorldLoader.MAX_SIBLINGS,
		"no sibling list is left wider than the limit (widest %d)" % widest)

	# Every leaf still hangs under the trunk, in the order the package gave, and
	# the groups between them are empty transforms.
	var order: PackedStringArray = PackedStringArray()
	var groups := 0
	for node_value: Variant in regrouped:
		var node: GLTFNode = node_value as GLTFNode
		if not node.get_name().begins_with(WorldLoader.GROUP_NAME_PREFIX):
			continue
		groups += 1
		_expect(node.position.is_zero_approx() and node.scale.is_equal_approx(Vector3.ONE)
			and node.mesh < 0,
			"a grouping node carries no geometry and no transform")
	for group_value: int in _groups_under(regrouped, 0):
		for leaf_index: int in (regrouped[group_value] as GLTFNode).get_children():
			order.append((regrouped[leaf_index] as GLTFNode).get_name())
			_expect((regrouped[leaf_index] as GLTFNode).parent == group_value,
				"a bucketed child names the group it was moved under")
	_expect(groups == added, "every group the pass reports is in the state")
	_expect(order == expected_order,
		"the trunk's children are the same nodes in the same order")

	# A map may turn it off, and a package with a rig is left alone whatever it
	# says, because Godot places a Skeleton3D from where its joints sit.
	manifest.data["rendering"] = {"regroupWideSiblings": false}
	var untouched := GLTFState.new()
	untouched.set_nodes(nodes.duplicate())
	untouched.root_nodes = roots
	_expect(int(loader.call("_regroup_wide_siblings", untouched)) == 0,
		"a map that switches regrouping off keeps the tree the package built")
	manifest.data.erase("rendering")
	var rigged := GLTFState.new()
	rigged.set_nodes(nodes.duplicate())
	rigged.root_nodes = roots
	rigged.set_skins([GLTFSkin.new()])
	_expect(int(loader.call("_regroup_wide_siblings", rigged)) == 0,
		"a package carrying a skin is left exactly as it was authored")
	loader.free()

## The grouping nodes whose parent is `parent`, in the order the parent lists
## them, which is the order the package's children were bucketed in.
func _groups_under(nodes: Array, parent: int) -> PackedInt32Array:
	return (nodes[parent] as GLTFNode).get_children()

func _returns(value: bool, label: String) -> bool:
	_expect(value, label)
	return value

func _expect(value: bool, label: String) -> void:
	if value:
		return
	failures += 1
	push_error("FAIL: " + label)
