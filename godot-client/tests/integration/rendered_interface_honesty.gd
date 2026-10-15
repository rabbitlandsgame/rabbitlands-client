extends SceneTree
## Rendered evidence for damage floating over whoever took it, and for the
## overhead vitals banner it sits beside.
##
## The banner is not new. This client already draws health, ether, food and
## action over the player's own character, with Eternal Lands' own wording and
## a switch per row - which is more than the forum ever asked for, and the
## reason nothing was added for it. The capture records that, so the next
## person reading the register does not build a second food bar on top of the
## one that is already there. (This one did, and the screenshot is what caught
## it: every assertion about the duplicate passed.)

const SCREEN_SIZE := Vector2i(1280, 720)

var _artifacts := ""
var _failures := 0
var _main: Control
var _app_state: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/salvage")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE

	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	(_main.get_node("LoginBackground") as TextureRect).hide()
	(_main.get_node("LoginPanel") as Control).hide()
	(_main.get_node("GameView") as Control).show()
	_app_state = root.get_node("AppState")
	_app_state.set("authenticated", true)
	_app_state.set("local_actor_id", 99)
	_app_state.set("current_map", "four_gates")
	_app_state.set("actors", {
		99: {"actor_id": 99, "x": 58, "y": 58, "rotation": 0, "actor_type": 1,
			"kind": 1, "name": "Kellan", "health": 72, "max_health": 100,
			"alive": true, "sitting": false},
		140: {"actor_id": 140, "x": 61, "y": 58, "rotation": 0,
			"actor_type": 401, "kind": 2, "name": "Reedhorn Stag",
			"health": 140, "max_health": 200, "alive": true, "sitting": false}})
	# Food at 12 of 45, which is where the bar earns its place: low enough to
	# matter and not so low the player would already have noticed.
	_app_state.set("stats", {
		"health": 72, "max_health": 100, "ether": 33, "max_ether": 50,
		"action_points": 18, "max_action_points": 30, "food": 12,
		"carried": 205, "capacity": 320})
	# Setting the dictionary does not announce it, and the world sync is
	# coalesced behind that signal, so the actor nodes are only built once it
	# is emitted.
	_app_state.call("emit_signal", "state_changed", &"actors")
	await _settle()
	_main.call("_sync_world")
	await _settle()
	# The food bar is fed from the statistics sync, which needs the actor node
	# to exist first - so it runs after the world, not with it.
	_main.call("_sync_stats")
	await _settle()

	var actor: Node = _main.get("actor_nodes").get(99)
	_expect(actor != null, "the local actor exists")
	# The banner already carries food, so the register's first row wants
	# nothing built. Pinned here so a later reading of it does not add a
	# second one.
	_expect(_main.get("_hud_element_options") != null
			and "food_bar" in _main.get("BANNER_OPTION_DEFAULTS"),
		"food is one of the banner rows the client already draws and can toggle")
	await _capture("overhead-vitals.png",
		"health, ether, food and action over the player's own character - all"
			+ " four already drawn, which is why nothing was added for them")

	# Damage floats over whoever took it. Both actors change at once so the
	# capture shows the player's own hit and the creature's together.
	var actors: Dictionary = (_app_state.get("actors") as Dictionary).duplicate(true)
	(actors[99] as Dictionary)["health"] = 49
	(actors[140] as Dictionary)["health"] = 96
	_app_state.set("actors", actors)
	_main.call("_sync_world")
	await _settle()
	var labels: Array = _main.get("_active_floating_labels") as Array
	_expect(labels.size() >= 2,
		"a number floated for each actor whose health changed (%d)" % labels.size())
	await _capture("damage-numbers.png",
		"damage over the actor that took it, in red, for the player and the"
			+ " creature at once rather than only over the player")

	_app_state.set("authenticated", false)
	_main.queue_free()
	await process_frame
	print("rendered interface honesty: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

func _settle() -> void:
	for _frame: int in range(6):
		await process_frame

func _capture(name: String, description: String) -> void:
	await process_frame
	var image: Image = root.get_texture().get_image()
	_expect(image != null and image.get_size() == SCREEN_SIZE,
		"%s is a full %dx%d frame" % [name, SCREEN_SIZE.x, SCREEN_SIZE.y])
	if image == null:
		return
	_expect(_has_colour_variation(image),
		"%s contains rendered colour variation rather than a dummy frame" % name)
	_expect(image.save_png(_artifacts.path_join(name)) == OK, "%s is written" % name)
	print("capture ", name, ": ", description)

func _has_colour_variation(image: Image) -> bool:
	var lowest := 2.0
	var highest := -1.0
	for y: int in range(0, image.get_height(), 8):
		for x: int in range(0, image.get_width(), 8):
			var luminance: float = image.get_pixel(x, y).get_luminance()
			lowest = minf(lowest, luminance)
			highest = maxf(highest, luminance)
	return highest - lowest > 0.02

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
