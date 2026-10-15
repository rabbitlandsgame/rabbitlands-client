extends SceneTree
## Other actors' names fade out with distance from the player.
##
## The overhead block is drawn at a fixed screen size, so a name sixty metres
## off was as large as one at arm's length and a castle gate read as a field of
## labels. Past the player's name distance the name, title and health bar come
## off; the body stays until the draw distance. Whoever the player is fighting
## keeps theirs at any range.

## main.gd is loaded at run time, not preloaded: it reads the autoload singletons,
## which a SceneTree script is compiled before.
var MainScript: GDScript
const SettingsWindowScript := preload("res://src/ui/settings_window.gd")

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	MainScript = load("res://src/app/main.gd") as GDScript
	if not _expect(MainScript != null and MainScript.can_instantiate(), "main.gd compiles"):
		quit(failures)
		return
	_test_fade_curve()
	await _test_actor()
	await _test_main()
	print("nameplate distance tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _test_fade_curve() -> void:
	var fade_metres: float = MainScript.NAME_FADE_METRES
	_expect(MainScript.nameplate_fade(0.0, 30.0) == 1.0, "a name at your feet is whole")
	_expect(MainScript.nameplate_fade(30.0 - fade_metres, 30.0) == 1.0,
		"and stays whole until the fade begins")
	_expect(is_equal_approx(MainScript.nameplate_fade(30.0 - fade_metres * 0.5, 30.0), 0.5),
		"half way through the fade it is half there")
	_expect(MainScript.nameplate_fade(30.0, 30.0) == 0.0, "at the name distance it is gone")
	_expect(MainScript.nameplate_fade(70.0, 30.0) == 0.0, "and stays gone past it")

func _test_actor() -> void:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/models.json")) as Dictionary
	var config: Dictionary = (registry.models as Dictionary)["red_fox"] as Dictionary
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		str(config.animationMap))) as Dictionary
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure({"actor_id": 7, "x": 0, "y": 0, "rotation": 0,
		"kind": 5, "name": "Red Fox", "name_colour": 14, "scale": 1.0,
		"health": 20, "max_health": 20}, adapter, config, animations)
	_expect(errors.is_empty(), "the fox loads: %s" % [errors])
	actor.set_physics_process(false)
	actor.set_health_visible(true)
	actor.set_title("Orchard scout")
	await process_frame
	var plate := actor.get_node("Nameplate") as Label3D
	var title := actor.get_node("TitleLine") as Label3D
	var backing := actor.get_node("HealthBarBackground") as MeshInstance3D
	var fill := actor.get_node("HealthBarFill") as MeshInstance3D
	var numbers := actor.get_node("HealthNumbers") as Label3D
	var name_colour: Color = plate.modulate

	_expect(actor.overhead_fade() == 1.0 and plate.visible and title.visible
		and backing.visible and fill.visible and numbers.visible,
		"an actor starts with its whole block showing")

	actor.set_overhead_fade(0.5)
	_expect(plate.visible and title.visible and backing.visible and numbers.visible,
		"part way through the fade everything is still drawn")
	_expect(is_equal_approx(plate.modulate.a, 0.5)
		and is_equal_approx(plate.outline_modulate.a, 0.5)
		and is_equal_approx(title.modulate.a, 0.5)
		and is_equal_approx(numbers.modulate.a, 0.5),
		"the labels and their outlines fade together")
	_expect(Color(plate.modulate, 1.0).is_equal_approx(Color(name_colour, 1.0)),
		"fading does not lose the server's name colour")
	_expect(is_equal_approx(_quad_alpha(backing),
			ReplicatedActor3D.HEALTH_BAR_BACKING.a * 0.5)
		and is_equal_approx(_quad_alpha(fill), 0.5),
		"the bar fades from its own opacity, not from opaque")
	actor.apply_vitals(9, 20)
	_expect(is_equal_approx(_quad_alpha(fill), 0.5),
		"a health change repaints the fill without losing the fade")

	actor.set_overhead_fade(0.0)
	_expect(not plate.visible and not title.visible and not backing.visible
		and not fill.visible and not numbers.visible,
		"past the name distance the name, title and bar are not drawn at all")
	actor.show_speech_bubble("Here!", 60000)
	_expect((actor.get_node("SpeechBubble") as Label3D).visible,
		"what somebody says still shows while their name is faded")
	actor.clear_speech_bubble()

	actor.set_overhead_fade(1.0)
	_expect(plate.visible and title.visible and backing.visible and fill.visible
		and is_equal_approx(plate.modulate.a, 1.0) and is_equal_approx(_quad_alpha(fill), 1.0),
		"back inside it everything returns whole")

	actor.set_nameplate_visible(false)
	actor.set_overhead_fade(0.8)
	_expect(not plate.visible and not backing.visible,
		"a name the banner options switched off is not brought back by the fade")
	actor.set_nameplate_visible(true)

	actor.set_drawn(false)
	actor.set_overhead_fade(0.6)
	_expect(not plate.visible and not backing.visible,
		"a fade change out of the draw distance does not float a name over nothing")
	actor.set_overhead_fade(0.0)
	actor.set_drawn(true)
	_expect(not plate.visible and not title.visible and not backing.visible,
		"coming back into range restores the body but not a name that faded meanwhile")
	_expect((actor.get_node("NativeModel") as Node3D).visible,
		"and the body is drawn again")
	actor.set_overhead_fade(1.0)
	_expect(plate.visible, "and the name follows the fade from there")

	actor.queue_free()
	await process_frame

func _test_main() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	var saved: Variant = main.get("_name_distance_metres")
	var window: Control = main.get("settings_window") as Control
	if not _expect(window != null, "main builds its settings window"):
		return
	var slider: HSlider = window.find_child("name_distance", true, false) as HSlider
	var reading: Label = window.find_child("NameDistanceValue", true, false) as Label
	_expect(slider != null and reading != null,
		"the graphics tab carries a name distance slider and its reading")
	if slider != null and reading != null:
		_expect(slider.min_value == SettingsWindowScript.NAME_DISTANCE_MIN
			and slider.max_value == float(MainScript.ACTOR_DRAW_DISTANCE_METRES),
			"the slider reaches as far as actors are drawn and no further")
		# Through the signal a drag sends, not by calling the handler.
		slider.value = 45.0
		_expect(is_equal_approx(float(main.get("_name_distance_metres")), 45.0),
			"moving the slider moves the name distance")
		_expect(reading.text == "45 m", "and the reading says so: %s" % reading.text)
	main.call("_on_client_setting_changed", "Graphics", "name_distance", 500.0)
	_expect(float(main.get("_name_distance_metres"))
			== SettingsWindowScript.NAME_DISTANCE_MAX,
		"a distance past the draw distance is held to it")
	main.call("_on_client_setting_changed", "Graphics", "name_distance", "far")
	_expect(float(main.get("_name_distance_metres"))
			== SettingsWindowScript.NAME_DISTANCE_DEFAULT,
		"a value that is not a number falls back to the default")
	main.call("_set_name_distance", saved)
	main.call("_save_hud_settings")
	main.queue_free()
	await process_frame

func _quad_alpha(quad: MeshInstance3D) -> float:
	return ((quad.mesh as QuadMesh).material as StandardMaterial3D).albedo_color.a

func _expect(value: bool, label: String) -> bool:
	if value:
		return true
	failures += 1
	push_error("FAIL: " + label)
	return false
