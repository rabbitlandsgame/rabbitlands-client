extends SceneTree
## Live-client evidence for the generated armour set.
##
## Connects to a running development server, creates a character, and for
## each wearable slot equips the generated piece through the real inventory
## path -- `#give`, MOVE_INVENTORY_ITEM into a wear slot, ACTOR_WEAR_ITEM back
## from the server -- capturing the running client.  The generated set only;
## the older authored pieces are not involved.
##
## Needs the dev server on 127.0.0.1:2000 with the Eloria catalogue:
##   python -m eloria.server --items config/eloria/items.txt ... (see
##   compose.eloria.yaml for the full profile).

const SESSION_TIMEOUT_SECONDS := 45.0
const SCREEN_SIZE := Vector2i(1280, 720)

## slot -> [part, generated item id, generated visual].  The generated set
## only: it is equipped through the real server path -- #give,
## MOVE_INVENTORY_ITEM into a wear slot, ACTOR_WEAR_ITEM back -- and captured
## in the running client.  The older authored pieces are not involved.
const PIECES := {
	"body": [5, 1274, 184],
	"legs": [4, 1282, 171],
	"boots": [6, 1290, 192],
	"helm": [3, 1306, 117],
	"circlet": [3, 1298, 109],
	"boots2": [6, 1314, 200],
}

var _failures := 0
var _artifacts := ""
var _app_state: Node
var _network: Node
var _main: Control
var _camera: Camera3D
var _game_camera: Camera3D

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/equipment-live")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	_app_state = root.get_node("AppState")
	_network = root.get_node("Network")

	var host: String = OS.get_environment("ELORIA_INTEGRATION_HOST")
	if host.is_empty():
		host = "127.0.0.1"
	var port_text: String = OS.get_environment("ELORIA_INTEGRATION_PORT")
	var port: int = int(port_text) if port_text.is_valid_int() else 2000
	var suffix: String = _random_hex(5)

	var host_edit: LineEdit = _main.get_node("LoginPanel/Content/Host") as LineEdit
	var port_edit: SpinBox = _main.get_node("LoginPanel/Content/Port") as SpinBox
	host_edit.text = host
	port_edit.value = port
	_main.call("_on_connect_pressed")
	if not await _wait_for(func() -> bool:
			return str(_app_state.get("connection_state")) == "connected",
			SESSION_TIMEOUT_SECONDS):
		_fail("development server connection timed out")
		_finish()
		return

	_main.call("_on_new_character_pressed")
	var name_edit: LineEdit = _main.get_node(
		"CreationPanel/Columns/FormPanel/Form/CreateName") as LineEdit
	var password_edit: LineEdit = _main.get_node(
		"CreationPanel/Columns/FormPanel/Form/CreatePassword") as LineEdit
	var confirm_edit: LineEdit = _main.get_node(
		"CreationPanel/Columns/FormPanel/Form/CreateConfirm") as LineEdit
	name_edit.text = "Fit" + suffix
	var password: String = _random_hex(24)
	password_edit.text = password
	confirm_edit.text = password
	# The reference screenshots are all luminous_male (actor type 1), so the
	# comparison stays on the body every earlier measurement used.
	var gender: OptionButton = _main.get("create_gender") as OptionButton
	if gender != null:
		for option: int in range(gender.item_count):
			if gender.get_item_id(option) == 1:
				gender.select(option)
				_main.call("_on_create_gender_item_selected", option)
				break
	_main.call("_on_create_pressed")
	if not await _wait_for(func() -> bool:
			return bool(_app_state.get("authenticated")), SESSION_TIMEOUT_SECONDS):
		_fail("character creation timed out")
		_finish()
		return
	if not await _wait_for(func() -> bool:
			var local_id: int = int(_app_state.get("local_actor_id"))
			return (not str(_app_state.get("current_map")).is_empty()
				and local_id >= 0
				and (_main.get("actor_nodes") as Dictionary).has(local_id)),
			SESSION_TIMEOUT_SECONDS):
		_fail("world presentation timed out")
		_finish()
		return
	for _settle: int in range(20):
		await process_frame

	_game_camera = _main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/CameraRig/Camera") as Camera3D
	_camera = Camera3D.new()
	_camera.fov = 38.0
	# See what the player sees: the gameplay camera's cull mask keeps the
	# map-only discs over every actor out of the evidence.
	_camera.cull_mask = _game_camera.cull_mask
	_main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot").add_child(_camera)

	for slot: String in PIECES:
		var config: Array = PIECES[slot] as Array
		var part: int = int(config[0])
		var item_id: int = int(config[1])
		var visual: int = int(config[2])
		await _unequip_all()
		if not await _equip(part, item_id, visual):
			_fail("%s: item %d never landed on the actor" % [slot, item_id])
			continue
		for _settle: int in range(30):
			await process_frame
		await _capture_actor("live-%s" % slot,
			"%s (item %d, visual %d:%d) in the running client" % [
				slot, item_id, part, visual])

	# The whole generated kit at once, then the gameplay camera the player
	# actually plays with.
	await _unequip_all()
	var kit := {5: [1274, 184], 4: [1282, 171], 6: [1290, 192], 3: [1306, 117]}
	for part_key: int in kit:
		await _equip(part_key, int((kit[part_key] as Array)[0]),
			int((kit[part_key] as Array)[1]))
	for _settle: int in range(30):
		await process_frame
	await _capture_actor("live-generated-full-kit",
		"the full generated kit on one character")
	_camera.current = false
	_game_camera.current = true
	for _settle: int in range(4):
		await process_frame
	await _capture("live-gameplay-view.png",
		"the generated kit from the gameplay camera")

	print("live generated equipment: ", "PASS" if _failures == 0
		else "FAIL (%d)" % _failures)
	_finish()

func _local_actor() -> ReplicatedActor3D:
	var local_id: int = int(_app_state.get("local_actor_id"))
	return (_main.get("actor_nodes") as Dictionary).get(local_id) as ReplicatedActor3D

func _close_interruptions() -> void:
	# A fresh character gets the greeter's popup; nothing about it is part of
	# this evidence.
	_app_state.call("close_popup")

## Give one item, wait for it to arrive (a new carry slot or a grown stack),
## move it to a wear slot, and wait for the server to dress the actor in the
## exact visual that item maps to.
func _equip(part: int, item_id: int, visual: int) -> bool:
	var before: Dictionary = {}
	for raw_slot: Variant in _app_state.get("inventory") as Dictionary:
		before[int(raw_slot)] = ((_app_state.get("inventory") as Dictionary)[
			raw_slot] as Dictionary).duplicate()
	_network.call("send_chat", "#give %d 1" % item_id)
	var changed_slot: Callable = func() -> int:
		var inventory: Dictionary = _app_state.get("inventory") as Dictionary
		for raw_slot: Variant in inventory:
			var index: int = int(raw_slot)
			if index >= 36:
				continue
			var was: Dictionary = before.get(index, {}) as Dictionary
			if was.hash() != (inventory[raw_slot] as Dictionary).hash():
				return index
		return -1
	if not await _wait_for(func() -> bool:
			return int(changed_slot.call()) >= 0, 30.0):
		print("equip diagnostics: item %d never arrived; inventory slots %s"
			% [item_id, (_app_state.get("inventory") as Dictionary).keys()])
		return false
	var landed: int = int(changed_slot.call())
	var inventory: Dictionary = _app_state.get("inventory") as Dictionary
	var wear: int = -1
	for index: int in range(36, 45):
		if not inventory.has(index):
			wear = index
			break
	if wear < 0:
		return false
	_main.call("_move_inventory_item", landed, wear)
	var worn: bool = await _wait_for(func() -> bool:
		var actor: ReplicatedActor3D = _local_actor()
		if actor == null:
			return false
		var visuals: Dictionary = actor.equipment_diagnostics().get(
			"visuals", {}) as Dictionary
		for raw_part: Variant in visuals:
			if int(raw_part) == part and int(visuals[raw_part]) == visual:
				return true
		return false, 30.0)
	if not worn:
		var actor: ReplicatedActor3D = _local_actor()
		print("equip diagnostics: item %d from slot %d to %d; visuals now %s"
			% [item_id, landed, wear,
			{} if actor == null else actor.equipment_diagnostics()])
	return worn

## Drop everything out of the wear slots so the next piece starts clean.
## Dropped, not stowed: a fresh character's carry capacity holds only a few
## armour pieces, and a hoard of them makes the server quietly refuse the
## next #give.
func _unequip_all() -> void:
	for index: int in range(36, 45):
		var inventory: Dictionary = _app_state.get("inventory") as Dictionary
		if not inventory.has(index):
			continue
		var free: int = -1
		for carry: int in range(0, 36):
			if not inventory.has(carry):
				free = carry
				break
		if free < 0:
			continue
		# In two steps, because the server only drops from carry slots: back
		# into the bag, then onto the ground.
		_main.call("_move_inventory_item", index, free)
		if not await _wait_for(func() -> bool:
				return not (_app_state.get("inventory") as Dictionary).has(index),
				10.0):
			continue
		var carried: Dictionary = (_app_state.get("inventory")
			as Dictionary).get(free, {}) as Dictionary
		_network.call("drop_inventory_item", free,
			maxi(1, int(carried.get("quantity", 1))))
		await _wait_for(func() -> bool:
			return not (_app_state.get("inventory") as Dictionary).has(free),
			10.0)
	for _settle: int in range(10):
		await process_frame

## Frame the actor's visible meshes and capture it from both sides, so one of
## the two shots is always the front whatever the server left the yaw at.
func _capture_actor(stem: String, description: String) -> void:
	var actor: ReplicatedActor3D = _local_actor()
	if actor == null:
		_fail(stem + ": no local actor to frame")
		return
	_close_interruptions()
	var bounds: AABB = _actor_bounds(actor)
	var centre: Vector3 = bounds.get_center()
	var radius: float = maxf(0.9, bounds.size.length() * 0.5)
	var yaw: float = actor.rotation.y
	_game_camera.current = false
	_camera.current = true
	# The subject is the gear, so the nameplate, bars and every other overlay
	# riding the actor steps out of frame for the capture.
	var hidden: Array[Node3D] = []
	for child: Node in actor.get_children():
		var spatial := child as Node3D
		if spatial != null and spatial.name != "NativeModel" and spatial.visible:
			spatial.visible = false
			hidden.append(spatial)
	for view: int in range(2):
		var direction := Vector3(sin(yaw), 0.0, cos(yaw)) * (1 if view == 0 else -1)
		_camera.global_position = (centre + direction * radius * 2.3
			+ Vector3(0.0, radius * 0.35, 0.0))
		_camera.look_at(centre, Vector3.UP)
		for _settle: int in range(3):
			await process_frame
		await _capture("%s-view%d.png" % [stem, view], description)
	for spatial: Node3D in hidden:
		spatial.visible = true

func _actor_bounds(actor: Node) -> AABB:
	# The native model only: the actor also carries a nameplate, selection
	# ring and map dot, and merging those in frames the whole plaza.
	var scope: Node = actor.get_node_or_null("NativeModel")
	if scope == null:
		scope = actor
	var bounds := AABB()
	var found := false
	for mesh: Node in scope.find_children("*", "MeshInstance3D", true, false):
		var instance: VisualInstance3D = mesh as VisualInstance3D
		if instance == null or not instance.visible:
			continue
		var world_aabb: AABB = instance.global_transform * instance.get_aabb()
		bounds = world_aabb if not found else bounds.merge(world_aabb)
		found = true
	return bounds if found else AABB((actor as Node3D).global_position, Vector3.ONE * 2.0)

func _capture(name: String, description: String) -> void:
	await process_frame
	var image: Image = root.get_texture().get_image()
	_expect(image != null, "%s captures a frame" % name)
	if image == null:
		return
	_expect(image.save_png(_artifacts.path_join(name)) == OK,
		"%s is written" % name)
	print("capture ", name, ": ", description)

func _wait_for(condition: Callable, timeout_seconds: float) -> bool:
	var deadline: int = Time.get_ticks_msec() + int(timeout_seconds * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if condition.call():
			return true
		await process_frame
	return false

func _random_hex(length: int) -> String:
	var text := ""
	for _index: int in range(length):
		text += "0123456789abcdef"[randi() % 16]
	return text

func _fail(label: String) -> void:
	_failures += 1
	push_error("FAIL: " + label)

func _expect(value: bool, label: String) -> bool:
	if not value:
		_fail(label)
	return value

func _finish() -> void:
	print("live generated equipment finished with %d failure(s)" % _failures)
	quit(_failures)
