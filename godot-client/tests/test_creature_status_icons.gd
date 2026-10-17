extends SceneTree
## Packet-to-actor coverage plus an optional rendered preview with real models.

var failures := 0

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
	var icons := fox.get_node("NegativeStatusIcons") as Node3D
	_expect(icons.get_child_count() == 6, "six distinct negative effects; duplicates and benefits excluded")
	_expect(icons.position.y == fox.get_node("Nameplate").position.y, "row follows model's head anchor")
	for index: int in range(6):
		var icon := icons.get_child(index) as MeshInstance3D
		var quad := icon.mesh as QuadMesh
		var material := quad.material as StandardMaterial3D
		_expect(str(icon.name) == all_effects[index], "stable icon order")
		_expect(material.albedo_texture != null and material.fixed_size and material.no_depth_test,
			"icon stays legible through zoom and terrain")
		_expect(quad.center_offset.y > 0 and icon.layers == ReplicatedActor3D.GAMEPLAY_ONLY_VISUAL_LAYER,
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

	var goblin := ReplicatedActor3D.new()
	stage.add_child(goblin)
	config = registry.models.mire_goblin
	animations = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var goblin_dto := dto.duplicate()
	goblin_dto.name = "Mire Goblin"
	_expect(goblin.configure(goblin_dto, adapter, config, animations).is_empty(), "imported goblin loads")
	goblin.set_physics_process(false)
	goblin.set_health_visible(true)
	goblin.set_negative_statuses(["poison", "cripple"])
	fox.position.x = -1.8
	goblin.position.x = 1.8
	var legend := Label.new()
	legend.text = "NEGATIVE STATUS EFFECTS\nPoison   Cripple   Heat weakness   Cold weakness   Magic weakness   Radiation weakness"
	legend.position = Vector2(40, 40)
	legend.add_theme_font_size_override("font_size", 18)
	root.add_child(legend)
	for frame: int in range(8):
		await process_frame
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		var artifacts := ProjectSettings.globalize_path("res://test-artifacts/creature-status")
		DirAccess.make_dir_recursive_absolute(artifacts)
		_expect(root.get_texture().get_image().save_png(artifacts.path_join("preview.png")) == OK,
			"rendered preview saved")
	stage.queue_free()
	legend.queue_free()
	await process_frame
	print("creature status icons: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _packet(state: Node, actor_id: int, effects: Variant) -> void:
	state.call("_on_packet", 212, JSON.stringify({"kind": "creature_status", "actor_id": actor_id,
		"effects": effects}).to_utf8_buffer())

func _expect(ok: bool, description: String) -> void:
	if not ok:
		failures += 1
		push_error(description)
