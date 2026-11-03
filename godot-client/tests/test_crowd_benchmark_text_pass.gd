extends SceneTree
## The crowd benchmark's overhead-text diagnostics (wave 2 OV-0) on a real
## benchmark Main, headless: the world-text pass modes behind `no_text_pass`
## and `text_pass_always`, the stopped pass staying hidden when a covering view
## closes, and `no_overhead` taking effect on an actor Main already presents.
## Headless draws nothing, so whether the pass renders is a windowed question;
## this checks the switches and the records the harness reads.
var failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = (load("res://tests/integration/crowd_benchmark_main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	await process_frame
	_text_pass_modes(main)
	await _overhead_switch(main)
	main.queue_free()
	await process_frame
	await process_frame
	print("CROWD_BENCHMARK_TEXT_PASS failures=", failures)
	quit(failures)


func _text_pass_modes(main: Control) -> void:
	var overlay := main.get("_world_text_overlay") as CanvasItem
	var viewport := overlay.get("text_viewport") as SubViewport
	var presence: Object = overlay.get("presence")
	var auto: Dictionary = main.call("benchmark_set_text_pass", "auto")
	_check(bool(auto.get("ok")) and auto.get("mode") == "auto" and auto.get("overlayVisible") == true
		and auto.get("idleWatching") == true, "auto keeps the shipping overlay and its idle watch: %s" % auto)
	_check(auto.get("passViewportSize") is Array and auto.get("worldViewportSize") is Array
		and auto.get("textNodesTracked") is int, "the snapshot reports the pass, its sizes and its layer")
	_check(main.call("benchmark_measure_text_pass", true) == true, "the pass viewport can be timed")
	var frame: Dictionary = main.call("benchmark_text_pass_frame", false)
	_check(frame.keys() == ["drawn"], "a headless frame reports only whether the pass drew")

	var off: Dictionary = main.call("benchmark_set_text_pass", "off")
	_check(bool(off.get("ok")) and off.get("mode") == "off" and not overlay.visible,
		"no_text_pass hides the overlay: %s" % off)
	_check(viewport.size == Vector2i(2, 2) and off.get("passViewportSize") == [2, 2],
		"no_text_pass shrinks the pass target to the SubViewport minimum")
	var console := main.get("console_panel") as Control
	console.show()
	console.hide() # Main re-shows world overlays when a covering view closes.
	_check(not overlay.visible, "a stopped pass stays hidden when the console closes")
	main.call("_sync_world_overlay_visibility")
	_check(not overlay.visible and (main.get("_floating_feedback_layer") as CanvasItem).visible,
		"only the text pass stays hidden; the other world overlays follow Main")

	var world_size := (main.get("main_viewport") as SubViewport).size
	var always: Dictionary = main.call("benchmark_set_text_pass", "always")
	_check(bool(always.get("ok")) and overlay.visible and not bool(presence.call("watching"))
		and always.get("idleWatching") == false, "text_pass_always shows the pass and stops its idle watch")
	# The overlay resizes its pass only before a drawn frame (never headless);
	# a cell after a stopped one must start with the shipping target allocated.
	_check(world_size.x > 2 and viewport.size == world_size and always.get("passViewportSize") == [world_size.x, world_size.y],
		"leaving no_text_pass gives the pass its world-size target back at once: %s" % viewport.size)
	var back: Dictionary = main.call("benchmark_set_text_pass", "auto")
	_check(bool(back.get("ok")) and overlay.visible and bool(presence.call("watching")),
		"auto restores the idle watch")
	main.call("benchmark_set_text_pass", "off")
	var restored: Dictionary = main.call("benchmark_set_text_pass", "auto")
	_check(bool(restored.get("ok")) and overlay.visible and viewport.size == world_size
		and restored.get("mode") == "auto", "the harness's cell-start restore returns the shipping pass: %s" % restored)
	var bad: Dictionary = main.call("benchmark_set_text_pass", "sometimes")
	_check(not bool(bad.get("ok", true)) and main.get("benchmark_text_pass_mode") == "auto",
		"an unknown mode is refused and changes nothing")
	_check(main.call("benchmark_measure_text_pass", false) == true, "timing switches off again")


func _overhead_switch(main: Control) -> void:
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	await process_frame
	# Bob, an enhanced NPC actor (the occupation test's packet), presented by Main.
	app_state.call("_on_packet", 51, _hex(
		"5c000203e1010000000001000001020304050b001e14071400"
		+ "12000190426f62000040ff0600"))
	await process_frame
	main.call("_sync_world")
	await process_frame
	var census: Dictionary = main.call("benchmark_overhead_census")
	if not _check(int(census.get("actors", 0)) == 1, "Main presents the actor: %s" % census):
		return
	_check(int(census.nameplateEnabled) == 1, "its banner is enabled by default")
	_check(int(main.call("benchmark_apply_overhead_switch")) == 0, "a full run changes no banner")
	main.set("benchmark_overhead_enabled", false)
	_check(int(main.call("benchmark_apply_overhead_switch")) == 1, "no_overhead reaches the presented actor")
	census = main.call("benchmark_overhead_census")
	_check(int(census.nameplateEnabled) == 0 and int(census.overheadShown) == 0 and int(census.healthShown) == 0,
		"and leaves no banner shown: %s" % census)
	main.set("benchmark_overhead_enabled", true)


func _hex(text: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index: int in range(0, text.length(), 2):
		bytes.append(text.substr(index, 2).hex_to_int())
	return bytes


func _check(ok: bool, label: String) -> bool:
	if not ok:
		failures += 1
		push_error(label)
	return ok
