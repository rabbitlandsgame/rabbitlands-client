extends SceneTree

var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func run() -> void:
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.get_node("GameView").show()
	var state := root.get_node("AppState")
	state.authenticated = true
	state.local_actor_id = 900
	check_ingredient_filter(main, state)
	check_quest_tracking(main, state)
	await check_crafting_and_bar(main)
	await check_corpses(main, state)
	state.actors.clear()
	main.actor_nodes.clear()
	main.queue_free()
	state._on_connection_state_changed("disconnected")
	await process_frame
	print("Stream playtest: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func check_crafting_and_bar(main: Control) -> void:
	main._settle_mix_run({"entry": -1, "output": "Wood Plank"}, 0)
	main._sync_manufacturing_detail()
	expect(main.manufacturing_status.text.contains("failed"), "an unsuccessful craft is explicit in the crafting window")
	expect(main.manufacturing_status.get_theme_color("font_color").r > main.manufacturing_status.get_theme_color("font_color").g * 2, "crafting failure is red")
	main.manufacturing_panel.show()
	await process_frame
	await process_frame
	expect(main.manufacturing_panel.size.y < 720, "the crafting window fits a 720px display")
	var bar: Variant = main.casting_bar
	bar.set_visible_slot_count(12)
	bar.set_horizontal(true)
	await process_frame
	await process_frame
	expect(bar.buttons[11].get_parent().visible, "the twelfth spell slot is displayed")
	expect(bar.panel.size.x > bar.panel.size.y, "horizontal orientation lays the spell bar across the screen")
	var layout: Dictionary = bar.hud_layout()
	bar.set_horizontal(false)
	bar.restore_hud_layout(layout)
	expect(bar.horizontal and not bar.docked and bar.visible_slot_count == 12, "orientation and all twelve slots survive layout restoration")
	main._hud_element_options["side_stats"] = false
	main._apply_hud_element_options()
	expect(not main.skill_rows.visible, "the HUD statistics toggle hides the skill list")
	main._hud_element_options["side_stats"] = true
	main._apply_hud_element_options()
	expect(main.skill_rows.visible, "the HUD statistics toggle shows the skill list")
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world/objects.json"))
	var bramble := MapObject3D.new()
	main.world_root.add_child(bramble)
	bramble.configure({"object_id": 8123, "kind": EloriaProtocol.MAP_OBJECT_HARVEST, "x": 0, "y": 0, "label": "Bramble"}, CoordinateAdapter.new({}), catalog)
	expect(bramble.get_node_or_null("Model") != null and bramble.model_id.begins_with("bramble_hedge"), "older Bramble nodes display an approved imported hedge")
	var cache := MapObject3D.new()
	main.world_root.add_child(cache)
	cache.configure({"object_id": 8124, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x": 0, "y": 0, "label": "Cache"}, CoordinateAdapter.new({}), catalog)
	cache.set_surface_height(7.2)
	expect(cache.get_node_or_null("Model") != null and cache.get_node_or_null("CacheLabel") != null and cache.global_position.y > 7.2, "a cache displays the approved strongbox above the ground")
	bramble.queue_free()
	cache.queue_free()
	var entrance := MapObject3D.new()
	main.world_root.add_child(entrance)
	entrance.configure({"object_id": 59001, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x": 332, "y": 86, "label": "Portal"},CoordinateAdapter.new({}),catalog)
	expect(entrance.get_node_or_null("EntranceModel") != null and entrance.get_node("EntranceLabel").text.contains("Lantern Mine"), "the actual server Portal uses imported entrance art and a readable label")
	entrance.queue_free()
	var mineral := MapObject3D.new()
	main.world_root.add_child(mineral)
	mineral.configure({"object_id":8199,"kind":EloriaProtocol.MAP_OBJECT_HARVEST,"x":0,"y":0,"label":"Copper"},CoordinateAdapter.new({}),catalog)
	expect(mineral.get_node_or_null("Model") != null and mineral.get_node("ResourceLabel").text == "Copper", "reused mineral art keeps the actual resource identity")
	mineral.set_active(true)
	expect(mineral.get_node("Ring").visible,"harvesting marks the modelled mineral")
	mineral.set_active(false)
	expect(not mineral.get_node("Ring").visible,"a modelled mineral has no idle placeholder ring")
	mineral.queue_free()
	var creature := ReplicatedActor3D.new()
	main.world_root.add_child(creature)
	var creature_model: Dictionary = main.models.rabbit
	creature.configure({"actor_id":904,"x":0,"y":0,"rotation":0,"kind":5,"name":"Rabbit","health":20,"max_health":20},CoordinateAdapter.new({}),creature_model,main._animation_for_model(creature_model))
	expect(creature.get_node("Nameplate").visible,"a living creature shows its name")
	creature.apply_vitals(0,20)
	expect(not creature.get_node("Nameplate").visible,"a creature death immediately hides its nameplate")
	creature.apply_vitals(20,20)
	expect(creature.get_node("Nameplate").visible,"a revived creature restores its nameplate")
	creature.queue_free()
	main.manufacturing_panel.hide()

func check_quest_tracking(main: Control, state: Node) -> void:
	state.quest_journal.clear()
	state.quest_journal.append({"title": "A Companion on the Road", "location": "Main world",
		"objective": "Let your companion land a hit", "current": 2, "target": 5})
	state.lantern_tutorial = {"active": true, "tutorial": "field_dispatch", "adventure": "A Companion on the Road"}
	var windows: Control = main.extension_windows
	windows._on_state_changed(&"lantern_tutorial")
	expect(windows.quest_track_button.text == "Untrack", "the journal recognizes the server's tracked dispatch")
	expect(not windows.tracked_quest.visible, "the dispatch guide is not duplicated by a second tracker")
	state.lantern_tutorial = {"active": false, "tutorial": "field_dispatch"}
	windows._on_state_changed(&"lantern_tutorial")
	expect(windows.quest_track_button.text == "Track", "stopping guidance offers Track to resume")
	expect(state.quest_journal.size() == 1, "stopping tracking retains the active quest")
	state.lantern_tutorial = {"active": true, "tutorial": "field_dispatch", "adventure": "A Companion on the Road"}
	windows._on_state_changed(&"lantern_tutorial")
	expect(windows.quest_track_button.text == "Untrack", "restored server state resumes the selected dispatch")
	state.quest_journal.clear()

func check_ingredient_filter(main: Control, state: Node) -> void:
	main.manufacturing_catalog.configure({"recipes": [{"output": "Wood Plank", "skill": "manufacturing",
		"ingredients": [{"name": "Hearthroot", "quantity": 2}],
		"tools": [{"name": "Hatchet"}], "knowledgeIndex": 3, "knowledge": "Woodworking", "mana": 5}]})
	state.inventory = {0: {"quantity": 2}}
	state.inventory_names = {0: "Hearthroot"}
	state.known_knowledge.clear()
	state.stats = {"food": 0, "ether": 0}
	state.mix_state = {"near_storage": false}
	main.manufacturing_ready_preference = true
	main.manufacturing_panel.show()
	main.selected_manufacturing_recipe = 0
	main._sync_manufacturing()
	expect(main.manufacturing_ready_only.text == "Has ingredients only", "filter names what it checks")
	expect(main.manufacturing_list.item_count == 1,
		"a supplied recipe remains visible when hungry, out of mana, without its tool or unread book")
	expect(main.manufacturing_mix_one.disabled, "ingredients alone do not enable an illegal mix")
	for message: String in ["Food must be above zero", "Need 5 ethereal points", "Required tool: Hatchet", "Unread knowledge: Woodworking"]:
		expect(main.manufacturing_detail.text.contains(message), "visible recipe explains: " + message)
	state.inventory.clear()
	state.inventory_names.clear()
	main._sync_manufacturing()
	expect(main.manufacturing_list.item_count == 0, "the ingredient filter still removes recipes missing ingredients")
	main.manufacturing_ready_preference = false
	main._sync_manufacturing()
	expect(main.manufacturing_list.item_count == 1, "turning the filter off exposes missing recipes again")
	main.manufacturing_panel.hide()

func pick_body(main: Control, actor_id: int, position: Vector3, creature: bool, health: int) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	actor.actor_id = actor_id
	actor.set("_is_creature", creature)
	var shape := CollisionShape3D.new()
	shape.shape = SphereShape3D.new()
	(shape.shape as SphereShape3D).radius = 0.75
	actor.add_child(shape)
	main.world_root.add_child(actor)
	actor.global_position = position
	actor.server_target = position
	actor.apply_vitals(health, 20)
	actor.set_process(false)
	main.actor_nodes[actor_id] = actor
	return actor

func check_corpses(main: Control, state: Node) -> void:
	var viewport_point := Vector2(main.main_viewport.size) * 0.5
	var origin: Vector3 = main.camera_rig.ray_origin(viewport_point)
	var direction: Vector3 = main.camera_rig.ray_direction(viewport_point)
	var dead := pick_body(main, 901, origin + direction * 10.0, true, 0)
	var live := pick_body(main, 902, origin + direction * 15.0, true, 20)
	state.actors[901] = {"kind": ReplicatedActor3D.CREATURE_ACTOR_KIND, "health": 0, "alive": false}
	state.actors[902] = {"kind": ReplicatedActor3D.CREATURE_ACTOR_KIND, "health": 20, "alive": true}
	main.gameplay_world = main.world_root.get_world_3d()
	await physics_frame
	await physics_frame
	expect(main._pick_actor(viewport_point) == 902, "a physics ray reaches the living creature through a corpse")
	var fallen := pick_body(main, 903, origin + direction * 5.0, false, 0)
	state.actors[903] = {"kind": 1, "health": 0, "alive": false}
	await process_frame
	await physics_frame
	await physics_frame
	var picked: int = main._pick_actor(viewport_point)
	expect(picked == 903, "a fallen player remains selectable for revival (picked %d)" % picked)
	var marks: Array = main._collect_minimap_marks()
	expect(not marks.any(func(mark: Dictionary) -> bool: return mark.position.is_equal_approx(dead.global_position)),
		"the minimap does not mark a creature corpse")
	expect(marks.any(func(mark: Dictionary) -> bool: return mark.position.is_equal_approx(live.global_position)),
		"the minimap keeps the living creature")
	expect(marks.any(func(mark: Dictionary) -> bool: return mark.position.is_equal_approx(fallen.global_position)),
		"the minimap keeps a fallen player")
	dead.apply_server_state({"x": 0, "y": 0, "rotation": 0, "health": 20, "alive": true}, CoordinateAdapter.new({}))
	expect(dead.collision_layer == 2, "an authoritative living state restores creature picking")
	var before := live.global_position
	live.apply_server_state({"x": 12, "y": 0, "rotation": 0, "health": 20, "alive": true, "command": 20}, CoordinateAdapter.new({}))
	expect(live.global_position.is_equal_approx(before), "a delayed creature movement burst interpolates instead of jumping")
