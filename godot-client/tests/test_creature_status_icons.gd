extends SceneTree
## Packet-to-actor coverage plus an optional rendered preview with real models.

var failures := 0
const StatusIcons := preload("res://src/ui/status_effect_icons.gd")

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var state: Node = root.get_node("AppState")
	var dto := {"actor_id": 9, "name": "Red Fox", "kind": 5, "x": 0, "y": 0,
		"rotation": 0, "health": 20, "max_health": 20}
	state.get("actors")[9] = dto.duplicate()
	_expect(EloriaProtocol.CLIENT_CAPABILITIES.has("creature_status_v1"), "status capability advertised")
	_packet(state, 9, ["poison", "cripple", "expose_cold"])
	_expect(state.get("actors")[9].negative_statuses == ["poison", "cripple", "expose_cold"],
		"authoritative snapshot is kept on the creature")
	state.call("_on_packet", 212, JSON.stringify({"kind": "actor_status", "actor_id": 9,
		"effects": ["poison", "shield", "regeneration"]}).to_utf8_buffer())
	_expect(state.get("actors")[9].status_effects == ["poison", "shield", "regeneration"]
		and state.get("actors")[9].negative_statuses == ["poison"], "both polarities are replicated")
	_packet(state, 9, ["focus_lock"])
	_expect(state.get("actors")[9].negative_statuses == ["focus_lock"], "Provoke focus lock is replicated")
	_packet(state, 404, ["poison"])
	_expect(not state.get("actors").has(404), "status cannot resurrect a removed actor")
	_packet(state, 9, [])
	_expect(state.get("actors")[9].negative_statuses.is_empty(), "empty snapshot clears effects")
	_packet(state, 9, "invalid")
	_expect(state.get("actors")[9].negative_statuses.is_empty(), "malformed effects ignored")
	state.call("_on_packet", 6, PackedByteArray([9, 0]))
	_packet(state, 9, ["poison"])
	_expect(not state.get("actors").has(9), "removed actor forgets its effects")

	root.size = Vector2i(1000, 600)
	var stage := Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("23313b")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = 0.8
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, -30, 0)
	stage.add_child(light)
	var camera := Camera3D.new()
	camera.fov = 50.0
	camera.cull_mask = 3
	stage.add_child(camera)
	camera.position = Vector3(0, 5, 10)
	camera.look_at(Vector3(0, 1, 0))
	camera.current = true
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0})
	var fox := ReplicatedActor3D.new()
	stage.add_child(fox)
	var config: Dictionary = registry.models.red_fox
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	_expect(fox.configure(dto, adapter, config, animations).is_empty(), "imported fox loads")
	fox.set_physics_process(false)
	fox.set_health_visible(true)
	var all_effects := ["poison", "cripple", "expose_heat", "expose_cold", "expose_magic", "expose_radiation"]
	fox.set_negative_statuses(all_effects + ["poison", "accuracy", "unknown"])
	var icons := fox.get_node("StatusIcons") as Node3D
	fox.set_status_effects(["focus_lock"])
	_expect(icons.get_child_count() == 1 and str(icons.get_child(0).name) == "focus_lock",
		"fixed focus has a dedicated overhead icon")
	fox.set_status_effects([])
	_expect(icons.get_child_count() == 0, "focus icon clears with the authoritative status")
	fox.set_negative_statuses(all_effects + ["poison", "accuracy", "unknown"])
	_expect(icons.get_child_count() == 6, "six distinct negative effects; duplicates and benefits excluded")
	_expect(icons.position.y == fox.get_node("Nameplate").position.y, "row follows model's head anchor")
	for index: int in range(6):
		var icon := icons.get_child(index) as MeshInstance3D
		var quad := icon.mesh as QuadMesh
		var material := quad.material as StandardMaterial3D
		_expect(str(icon.name) == all_effects[index], "stable icon order")
		_expect(material.albedo_texture != null and material.fixed_size and material.no_depth_test,
			"icon stays legible through zoom and terrain")
		_expect(quad.center_offset.y > 0 and icon.layers == preload("res://src/ui/world_label_style.gd").RENDER_LAYER,
			"icon stays above the name and off maps")
	fox.set_server_scale(2.0)
	_expect(icons.position.y == fox.get_node("Nameplate").position.y, "scaling lifts icons with the banner")
	fox.set_server_scale(1.0)
	fox.set_overhead_fade(0.5)
	_expect(is_equal_approx(((icons.get_child(0).mesh as QuadMesh).material as StandardMaterial3D).albedo_color.a, 0.5),
		"icons share banner fading")
	fox.set_overhead_crowded(true)
	_expect(not icons.visible, "crowded banner hides icons")
	fox.set_overhead_crowded(false)
	fox.set_nameplate_visible(false)
	_expect(not icons.visible, "name display setting hides icons")
	fox.set_nameplate_visible(true)
	fox.set_drawn(false)
	fox.set_negative_statuses(["poison"])
	_expect(not icons.visible, "updates cannot reveal an out-of-range actor")
	fox.set_negative_statuses([])
	fox.set_drawn(true)
	_expect(not icons.visible, "cleared effects stay absent after returning to range")
	fox.set_negative_statuses(all_effects)
	fox.apply_vitals(0, 20)
	_expect(not icons.visible and fox.negative_status_count() == 0, "death hides every status")
	fox.apply_vitals(20, 20)
	fox.set_overhead_fade(1.0)
	fox.set_title("Orchard scout")
	_expect((icons.get_child(0).mesh as QuadMesh).center_offset.y
		> ReplicatedActor3D.NEGATIVE_STATUS_RISE * ReplicatedActor3D.OVERHEAD_PIXEL,
		"icons leave room for a title")
	fox.set_title("")
	var main_script: GDScript = load("res://src/app/main.gd")
	var plain: Rect2 = main_script.overhead_block_rect(Vector2(400, 300), "Red Fox")
	var afflicted: Rect2 = main_script.overhead_block_rect(Vector2(400, 300), "Red Fox", "", 6)
	_expect(afflicted.position.y < plain.position.y and afflicted.size.x >= 6 * 20 + 5 * 3,
		"crowding reserves the icon row's height and width")
	var complete: Array = StatusIcons.TEXTURES.keys()
	dto["status_effects"] = complete
	fox.apply_server_state(dto, adapter, true)
	_expect(icons.get_child_count() == complete.size() and fox.status_effect_count() == complete.size(),
		"all negative and positive icons exist")
	var wrapped: Rect2 = main_script.overhead_block_rect(Vector2(400, 300), "Red Fox", "", complete.size())
	_expect(wrapped.size.x == afflicted.size.x and wrapped.size.y > afflicted.size.y,
		"large status lists grow upwards with a bounded width")
	_expect((icons.get_child(complete.size() - 1).mesh as QuadMesh).center_offset.y
		> (icons.get_child(0).mesh as QuadMesh).center_offset.y, "additional rows sit above the first")
	fox.set_status_effects(["poison", "shield", "regeneration", "haste"])

	var goblin := ReplicatedActor3D.new()
	stage.add_child(goblin)
	config = registry.models.mire_goblin
	animations = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var goblin_dto := dto.duplicate()
	goblin_dto.name = "Mire Goblin"
	_expect(goblin.configure(goblin_dto, adapter, config, animations).is_empty(), "imported goblin loads")
	goblin.set_physics_process(false)
	goblin.set_health_visible(true)
	goblin.set_status_effects(complete.filter(func(effect: String) -> bool: return effect not in StatusIcons.NEGATIVE))
	var player := ReplicatedActor3D.new()
	stage.add_child(player)
	config = registry.models.luminous_male
	animations = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var player_dto := dto.duplicate()
	player_dto.name = "Player"
	player_dto.kind = 1
	_expect(player.configure(player_dto, adapter, config, animations).is_empty(), "player model loads")
	player.set_physics_process(false)
	player.set_health_visible(true)
	player_dto["status_effects"] = ["cripple", "expose_heat", "magic_protection", "haste", "accuracy", "true_sight"]
	player.apply_server_state(player_dto, adapter, true)
	_expect(player.get_node("StatusIcons").get_child_count() == 6, "players show both positive and negative effects")
	_expect(bool(player.get("_hastened")), "replicated haste also changes movement presentation")
	fox.position.x = -3.0
	player.position.x = 3.0
	var legend := Label.new()
	legend.text = "ACTOR STATUS EFFECTS\nFox: mixed effects    Goblin: all %d positive effects    Player: mixed effects" % (
		complete.size() - StatusIcons.NEGATIVE.size())
	legend.position = Vector2(40, 40)
	legend.add_theme_font_size_override("font_size", 18)
	root.add_child(legend)
	await _test_own_player(state, complete)
	for frame: int in range(8):
		await process_frame
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		var artifacts := ProjectSettings.globalize_path("res://test-artifacts/actor-status")
		DirAccess.make_dir_recursive_absolute(artifacts)
		_expect(root.get_texture().get_image().save_png(artifacts.path_join("preview.png")) == OK,
			"rendered preview saved")
	stage.queue_free()
	legend.queue_free()
	await process_frame
	print("actor status icons: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _test_own_player(state: Node, effects: Array) -> void:
	state.get("actors").clear()
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	main.hide()
	await process_frame
	state.set("local_actor_id", 99)
	state.get("actors")[99] = {"actor_id": 99, "kind": 1, "health": 20, "status_effects": effects}
	main.call("_sync_local_status_icons")
	var grid := main.get("local_status_grid") as GridContainer
	_expect(grid != null and grid.get_child_count() == effects.size() and grid.columns == 6,
		"own overhead HUD shows all statuses and wraps them")
	_expect(grid.get_parent().get_child(0) == grid, "own icons appear above the name and resources")
	state.get("actors")[99].health = 0
	main.call("_sync_local_status_icons")
	_expect(not grid.visible, "own statuses disappear on death")
	state.get("actors")[99].health = 20
	main.set("_nameplates_enabled", false)
	main.call("_sync_local_status_icons")
	_expect(not grid.visible, "own statuses respect the display setting")
	state.get("actors").clear()
	main.queue_free()
	await process_frame

func _packet(state: Node, actor_id: int, effects: Variant) -> void:
	state.call("_on_packet", 212, JSON.stringify({"kind": "creature_status", "actor_id": actor_id,
		"effects": effects}).to_utf8_buffer())

func _expect(ok: bool, description: String) -> void:
	if not ok:
		failures += 1
		push_error(description)
