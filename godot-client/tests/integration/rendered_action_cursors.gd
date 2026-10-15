extends SceneTree

## The action pointer over a real scene: a fixture world offers one of every
## hover target - an NPC, a creature, another player, a dropped bag, a harvest
## node, a portal, a service point, bare ground - and each is picked through
## the production rays and classified through the production table. The
## captured frame gets every chosen glyph composited at its own hotspot, so
## the artifact shows the pointer language in context the way a player meets
## it.

const SCREEN_SIZE := Vector2i(1280, 720)

var _artifact_directory := ""
var _failures := 0
var _main: Control
var _adapter: CoordinateAdapter

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifact_directory = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifact_directory.is_empty():
		_artifact_directory = ProjectSettings.globalize_path("res://test-artifacts/four-gates")
	_expect(DirAccess.make_dir_recursive_absolute(_artifact_directory) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	var scene_resource: Resource = load("res://src/app/main.tscn")
	_expect(scene_resource is PackedScene, "main scene loads")
	if not scene_resource is PackedScene:
		_finish()
		return
	_main = (scene_resource as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	(_main.get_node("LoginBackground") as TextureRect).hide()
	(_main.get_node("LoginPanel") as Control).hide()
	(_main.get_node("GameView") as Control).show()

	var cursors: MouseCursors = _main.get("mouse_cursors") as MouseCursors
	_expect(cursors != null and cursors.loaded(), "the scene built its cursor set")
	if cursors == null or not cursors.loaded():
		_finish()
		return
	cursors.apply(MouseCursors.WALK)
	_expect(cursors.current() == MouseCursors.WALK,
		"the hardware pointer accepts a glyph")

	var app_state: Node = root.get_node("AppState")
	app_state.set("authenticated", true)
	app_state.set("local_actor_id", 99)
	app_state.set("current_map", "four_gates")
	app_state.set("actors", {
		99: {"actor_id": 99, "x": 58, "y": 58, "rotation": 0, "actor_type": 1,
			"kind": 1, "name": "Ari", "health": 72, "max_health": 100,
			"alive": true, "sitting": false},
		101: {"actor_id": 101, "x": 52, "y": 58, "rotation": 0, "actor_type": 201,
			"kind": 2, "name": "Guide", "health": 50, "max_health": 50,
			"alive": true, "sitting": false},
		102: {"actor_id": 102, "x": 64, "y": 58, "rotation": 0, "actor_type": 401,
			"kind": 3, "name": "Wolf", "health": 40, "max_health": 40,
			"alive": true, "sitting": false},
		103: {"actor_id": 103, "x": 58, "y": 52, "rotation": 0, "actor_type": 1,
			"kind": 1, "name": "Rival", "health": 90, "max_health": 100,
			"alive": true, "sitting": false}})
	app_state.set("ground_bags", {7: {"bag_id": 7, "x": 52, "y": 52}})
	app_state.set("map_objects", {
		11: {"object_id": 11, "kind": 1, "x": 64, "y": 52, "label": "Blue Lupine",
			"detail": ""},
		12: {"object_id": 12, "kind": 2, "x": 52, "y": 64, "label": "Storage",
			"detail": ""},
		13: {"object_id": 13, "kind": 2, "x": 64, "y": 64, "label": "Portal",
			"detail": ""}})
	_main.call("_load_server_map")
	_main.call("_sync_world")
	for unused_frame: int in range(16):
		await physics_frame
		await process_frame
	_adapter = _main.get("adapter") as CoordinateAdapter

	# What the pointer promises over each fixture target, through the real
	# pick rays and the real table. Heights aim the ray at the body of each
	# target: an actor's chest, a bag or node near the ground.
	var probes: Array = [
		["npc", 101, 1.0, "npc", MouseCursors.TALK],
		["creature", 102, 1.0, "creature", MouseCursors.ATTACK],
		["player", 103, 1.0, "player", MouseCursors.EYE],
		["self", 99, 1.0, "self", MouseCursors.EYE],
	]
	var annotations: Array = []
	for probe: Array in probes:
		var actor_nodes: Dictionary = _main.get("actor_nodes") as Dictionary
		var node: Node3D = actor_nodes.get(int(probe[1])) as Node3D
		_expect(node != null, "%s fixture actor exists" % str(probe[0]))
		if node == null:
			continue
		_check_spot(str(probe[0]), node.global_position + Vector3.UP * float(probe[2]),
			str(probe[3]), int(probe[4]), annotations)

	var bag_nodes: Dictionary = _main.get("ground_bag_nodes") as Dictionary
	var bag_node: Node3D = bag_nodes.get(7) as Node3D
	_expect(bag_node != null, "ground bag fixture exists")
	if bag_node != null:
		_check_spot("bag", bag_node.global_position + Vector3.UP * 0.3,
			"bag", MouseCursors.PICK, annotations)

	var object_nodes: Dictionary = _main.get("map_object_nodes") as Dictionary
	var object_probes: Array = [
		["harvest", 11, "harvest", MouseCursors.HARVEST],
		["interactive", 12, "interactive", MouseCursors.USE],
		["portal", 13, "portal", MouseCursors.ENTER]]
	for probe: Array in object_probes:
		var map_object: MapObject3D = object_nodes.get(int(probe[1])) as MapObject3D
		_expect(map_object != null, "%s fixture object exists" % str(probe[0]))
		if map_object == null:
			continue
		_check_spot(str(probe[0]), map_object.global_position + Vector3.UP * 0.6,
			str(probe[2]), int(probe[3]), annotations)

	# Bare ground away from every fixture walks - and the modes change what a
	# player promises without touching what the ground promises. The spot sits
	# between the fixtures at the player's own height, so it stays inside the
	# camera's frame whatever the map's tile heights say.
	var ground := _adapter.tile_center(61, 61)
	ground.y = (_actor_position(99) - Vector3.UP).y
	_check_spot("ground", ground, "", MouseCursors.WALK, annotations)
	# The trade icon is a mode, as in Eternal Lands: usable with nobody
	# selected, it arms trade, and the pointer over a player turns to the
	# trade glyph - where the click sends TRADE_WITH.
	var trade_button: Button = _main.get("trade_button") as Button
	app_state.set("selected_actor_id", -1)
	_main.call("_sync_selection")
	_expect(not trade_button.disabled, "the trade icon is usable with nobody selected")
	trade_button.pressed.emit()
	_expect(str(_main.get("_interaction_mode")) == "trade",
		"pressing the trade icon arms trade mode")
	var trade_annotations: Array = []
	_check_spot("player-trade-mode", _actor_position(103), "player",
		MouseCursors.TRADE, trade_annotations)
	_expect(str(_main.call("_actor_click_action", 103,
		(app_state.get("actors") as Dictionary).get(103, {}), false)) == "trade",
		"armed, a click on that player is a trade request")
	await _capture_annotated("trade-cursor-armed.png", trade_annotations)
	_main.set("_interaction_mode", "attack")
	_check_spot("player-attack-mode", _actor_position(103), "player",
		MouseCursors.ATTACK, [])
	_check_spot("ground-attack-mode", ground, "", MouseCursors.WALK, [])
	_main.set("_interaction_mode", "walk")
	_main.set("_alt_attack_preview", true)
	_check_spot("player-alt-held", _actor_position(103), "player",
		MouseCursors.ATTACK, [])
	_main.set("_alt_attack_preview", false)
	app_state.set("pending_spell_target", "actor")
	_check_spot("npc-spell-pending", _actor_position(101), "npc",
		MouseCursors.WAND, [])
	app_state.set("pending_spell_target", "location")
	_check_spot("ground-spell-pending", ground, "", MouseCursors.WAND, [])
	app_state.set("pending_spell_target", "")

	# A bag dropped at your own feet: the sack outranks your own body for the
	# pointer and for the click - you are not a click target for yourself -
	# while a pending actor spell still claims you.
	var self_spot: Vector3 = _actor_position(99)
	_check_spot("self-no-underfoot-bag", self_spot, "self", MouseCursors.EYE, [])
	(app_state.get("ground_bags") as Dictionary)[8] = {"bag_id": 8, "x": 58, "y": 58}
	_main.call("_sync_ground_bags")
	_check_spot("self-underfoot-bag", self_spot, "bag", MouseCursors.PICK, [])
	app_state.set("pending_spell_target", "actor")
	_check_spot("self-underfoot-bag-spell", self_spot, "self", MouseCursors.WAND, [])
	app_state.set("pending_spell_target", "")
	var self_click := InputEventMouseButton.new()
	self_click.button_index = MOUSE_BUTTON_LEFT
	self_click.pressed = true
	var world_viewport: SubViewport = _main.get_node(
		"GameView/ViewportContainer/Viewport") as SubViewport
	_main.call("_handle_world_click", self_click,
		world_viewport.get_camera_3d().unproject_position(self_spot))
	_expect(int((app_state.get("ground_bag") as Dictionary).get("bag_id", -1)) == 8,
		"clicking your own body with a bag below begins opening that bag")
	(app_state.get("ground_bags") as Dictionary).erase(8)
	_main.call("_sync_ground_bags")

	await _capture_annotated("action-cursors.png", annotations)
	_finish()

func _actor_position(actor_id: int) -> Vector3:
	var actor_nodes: Dictionary = _main.get("actor_nodes") as Dictionary
	var node: Node3D = actor_nodes.get(actor_id) as Node3D
	return node.global_position + Vector3.UP if node != null else Vector3.ZERO

## Asks the production pipeline about one world position: unproject it the way
## the mouse would land on it, classify it with the real pick rays, choose the
## glyph from the real table.
func _check_spot(label: String, world_position: Vector3, wanted_target: String,
		wanted_cursor: int, annotations: Array) -> void:
	var viewport: SubViewport = _main.get_node(
		"GameView/ViewportContainer/Viewport") as SubViewport
	var camera: Camera3D = viewport.get_camera_3d()
	if camera == null or camera.is_position_behind(world_position):
		_expect(false, "%s is in front of the camera" % label)
		return
	var viewport_position: Vector2 = camera.unproject_position(world_position)
	var context: Dictionary = _main.call("_cursor_context_at", viewport_position)
	var got_target: String = str(context.get("target", ""))
	_expect(got_target == wanted_target,
		"%s classifies as \"%s\" (got \"%s\")" % [label, wanted_target, got_target])
	var got_cursor: int = MouseCursors.choose(context)
	_expect(got_cursor == wanted_cursor,
		"%s chooses cursor %d (got %d)" % [label, wanted_cursor, got_cursor])
	annotations.append({"label": label, "viewport_position": viewport_position,
		"cursor": got_cursor})

## The scene frame with every chosen glyph drawn at the spot it was chosen
## for, hotspot-aligned, exactly as the hardware pointer would sit.
func _capture_annotated(file_name: String, annotations: Array) -> void:
	for unused_frame: int in range(6):
		await process_frame
	RenderingServer.force_draw(false)
	var image_value: Variant = root.get_texture().get_image()
	if not image_value is Image:
		_expect(false, "rendered screenshot is available")
		return
	var image: Image = image_value as Image
	image.convert(Image.FORMAT_RGBA8)
	var container: TextureRect = _main.get_node("GameView/ViewportContainer") as TextureRect
	var viewport: SubViewport = _main.get_node(
		"GameView/ViewportContainer/Viewport") as SubViewport
	var cursors: MouseCursors = _main.get("mouse_cursors") as MouseCursors
	for annotation_value: Variant in annotations:
		var annotation: Dictionary = annotation_value as Dictionary
		var cursor_id: int = int(annotation.get("cursor", MouseCursors.ARROW))
		var glyph := Image.new()
		var glyph_path: String = ProjectSettings.globalize_path(
			"res://assets/ui/cursors/cursor_%s.png" % cursors.name_of(cursor_id))
		if glyph.load(glyph_path) != OK:
			_expect(false, "glyph loads for compositing: " + glyph_path)
			continue
		glyph.convert(Image.FORMAT_RGBA8)
		var viewport_position: Vector2 = annotation.get("viewport_position") as Vector2
		var window_position: Vector2 = (container.position
			+ viewport_position * container.size / Vector2(viewport.size))
		var hotspot: Vector2 = cursors.hotspot_of(cursor_id)
		image.blend_rect(glyph, Rect2i(Vector2i.ZERO, glyph.get_size()),
			Vector2i(window_position - hotspot))
	_expect(image.save_png(_artifact_directory.path_join(file_name)) == OK,
		"saved " + file_name)

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: ", message)
		return
	_failures += 1
	push_error("FAIL: " + message)

func _finish() -> void:
	# Hand both skinned shapes back to the operating system so the process
	# exits without the cursor textures counted as leaked.
	Input.set_custom_mouse_cursor(null, Input.CURSOR_ARROW)
	Input.set_custom_mouse_cursor(null, Input.CURSOR_IBEAM)
	var app_state: Node = root.get_node_or_null("AppState")
	if app_state != null:
		app_state.set("authenticated", false)
		app_state.set("local_actor_id", -1)
		app_state.set("current_map", "")
		app_state.set("pending_spell_target", "")
		app_state.call("close_ground_bag")
		(app_state.get("actors") as Dictionary).clear()
		(app_state.get("ground_bags") as Dictionary).clear()
		(app_state.get("map_objects") as Dictionary).clear()
	print("rendered action cursors: ", "PASS" if _failures == 0 else "FAIL")
	# The fixture map streams its chunks and its neighbour regions on workers;
	# quitting under a live one crashes the process at exit, so both are
	# stopped and waited for, as main.gd's _close_client does
	# (ContinentChunkStream.drain_workers).
	var exterior: ExteriorRegionStream = (_main.get("exterior_stream")
		as ExteriorRegionStream) if _main != null else null
	if exterior != null:
		exterior.clear()
		var deadline: int = Time.get_ticks_msec() + 30000
		while not exterior.is_idle() and Time.get_ticks_msec() < deadline:
			await process_frame
	await ContinentChunkStream.drain_workers(self)
	quit(_failures)
