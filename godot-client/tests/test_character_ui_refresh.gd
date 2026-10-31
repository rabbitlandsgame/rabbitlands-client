extends SceneTree
## A nonlethal health burst reduces state immediately and paints each view once.
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var app := root.get_node("AppState")
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.set_script(load("res://tests/fixtures/character_ui_refresh_main.gd"))
	root.add_child(main)
	await process_frame
	await process_frame
	app.authenticated = true
	app.stats = {"health": 1000, "max_health": 1000, "attack_exp": 0}
	main._track_experience()
	main.reset_refresh_counts()
	var started := Time.get_ticks_usec()
	for index in range(100):
		app.stats.health = 999 - index
		app.state_changed.emit(&"stats")
		app.state_changed.emit(&"spells")
		app.state_changed.emit(&"spell_power")
	_expect(app.stats.health == 900, "the latest health is authoritative before rendering")
	_expect(main.refresh_counts == {"stats": 0, "spells": 0, "crafting": 0},
		"a packet burst does not rebuild views inline")
	await process_frame
	await process_frame
	_expect(main.refresh_counts == {"stats": 1, "spells": 1, "crafting": 1},
		"one process frame paints each affected view once")
	_expect(main.rendered_health == 900, "the health view shows the final packet value")
	print("character_ui_burst ", JSON.stringify({"updates": 300,
		"view_refreshes": main.refresh_counts, "elapsed_us": Time.get_ticks_usec() - started}))
	main.reset_refresh_counts()
	for gain: int in [3, 9, 2]:
		app.stats.attack_exp = int(app.stats.attack_exp) + gain
		app.state_changed.emit(&"stats")
	await process_frame
	await process_frame
	_expect(main._session_xp_gain.get("attack", 0) == 14, "session XP keeps every gain")
	_expect(main._session_xp_max.get("attack", 0) == 9, "maximum XP stays a single award")
	_expect(main._session_xp_last.get("attack", 0) == 2, "last XP stays the last award")
	_expect(main.refresh_counts.stats == 1, "XP display updates share a frame")
	app.state_changed.emit(&"stats")
	app.authenticated = false
	app.local_actor_id = 60001
	app.actors[60001] = {"health": 100, "max_health": 100, "alive": true}
	var events := {"actors": 0, "stats": 0}
	var observe := func(path: StringName) -> void:
		if events.has(str(path)):
			events[str(path)] += 1
	app.state_changed.connect(observe)
	for _index in range(100):
		app._apply_actor_health_delta(60001, 0)
		app._apply_actor_health_delta(60001, 20)
	_expect(events == {"actors": 0, "stats": 0}, "zero and capped healing do not refresh unchanged state")
	app._apply_actor_health_delta(60001, -5)
	_expect(app.actors[60001].health == 95 and app.stats.health == 95,
		"real health changes still apply immediately")
	_expect(events == {"actors": 1, "stats": 1}, "real health changes notify both consumers")
	app.state_changed.disconnect(observe)
	# A pending update from a disconnected character must not paint after logout.
	app.authenticated = false
	main.reset_refresh_counts()
	await process_frame
	await process_frame
	_expect(main.refresh_counts == {"stats": 0, "spells": 0, "crafting": 0},
		"logout discards queued character presentation")
	app.actors.erase(60001)
	app.local_actor_id = -1
	main.queue_free()
	await process_frame
	print("character UI refresh: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)
