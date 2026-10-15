extends SceneTree

var failures := 0

func _init() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func run() -> void:
	var main: Control = load("res://src/app/main.gd").new()
	var state: Node = root.get_node("AppState")
	var companion := {"actor_id": 88, "name": "Oren", "kind": 1, "health": 500, "alive": true}
	# JSON numbers arrive as floats; use the actual tutorial payload format.
	state.lantern_tutorial = JSON.parse_string('{"active":true,"tutorial":"borrowed_sky","talk_actor_ids":[88]}')
	for mode: String in ["walk", "attack", "trade"]:
		main.set("_interaction_mode", mode)
		for alt: bool in [false, true]:
			check(main.call("_actor_click_action", 88, companion, alt) == "talk",
				"Oren can be greeted in %s mode" % mode)
	check(not main.call("_is_attackable_actor", 88, companion), "companions are not attack targets")
	check(not main.call("_is_tradeable_player", 88, companion), "companions are not trade targets")
	state.pending_spell_target = "actor"
	check(main.call("_actor_click_action", 88, companion, false) == "spell",
		"a selected healing spell still targets Oren")
	state.pending_spell_target = ""
	main.set("_interaction_mode", "walk")
	check(main.call("_actor_click_action", 89, companion, false) == "none",
		"other players do not become tutorial companions")
	state.lantern_tutorial["active"] = false
	check(main.call("_actor_click_action", 88, companion, false) == "none",
		"companion interaction ends when the tutorial is inactive")
	state.lantern_tutorial = {"active": true, "tutorial": "borrowed_sky"}
	check(main.call("_actor_click_action", 88, companion, false) == "none",
		"older tutorial payloads without companion ids remain valid")
	state.lantern_tutorial.clear()
	main.free()
	print("Tutorial companion interaction: %d failures" % failures)
	quit(failures)
