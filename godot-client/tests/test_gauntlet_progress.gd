extends SceneTree
const Hud := preload("res://src/ui/gauntlet_progress_hud.gd")
var checks := 0
var failures := 0

class ClockHud extends "res://src/ui/gauntlet_progress_hud.gd":
	var clock := 100000
	func _now_msec() -> int: return clock

func _init() -> void: run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func snapshot() -> Dictionary:
	return {"version":1,"active":true,"run_id":"test-run","map_id":"sunmane_gauntlet_2",
		"wave":1,"waves":6,"title":"The First Bowl","phase":"fighting","enemies":8,
		"pulses_landed":1,"pulses_total":3,"pulses_pending":2,"arrival_serial":1,
		"release_remaining_ms":10000,"release_enemy_threshold":2}

func decode(state: Dictionary) -> Dictionary:
	return EloriaProtocol.decode_server(189, JSON.stringify(state).to_utf8_buffer())

func run() -> void:
	create_timer(45).timeout.connect(func(): push_error("Gauntlet progress timed out"); quit(1))
	root.size = Vector2i(1280,720)
	root.get_node("Network").block_for_hud_preview()
	var app := root.get_node("AppState")
	app.authenticated = true
	app.current_map = "maps/nymara/sunmane_gauntlet_2.elm"
	app.gauntlet_progress.clear()
	var hud := ClockHud.new()
	root.add_child(hud)
	await process_frame
	expect(not hud.panel.visible, "no encounter data leaves the HUD hidden")
	expect("gauntlet_progress_v1" in EloriaProtocol.CLIENT_CAPABILITIES, "the new snapshot capability is declared")
	var state := snapshot()
	expect(decode(state).type == "gauntlet_progress", "the production protocol admits a timed reinforcement snapshot")
	app._on_packet(189, JSON.stringify(state).to_utf8_buffer())
	hud.apply_snapshot(app.gauntlet_progress, hud.clock)
	expect(hud.panel.visible and hud.heading.text.contains("Wave 1 / 6")
		and hud.counts.text.contains("8") and hud.counts.text.contains("Future pulses: 2"),
		"wire state separately displays the current wave, enemies and future pulses")
	expect(not hud.arrival.visible, "first receipt or reconnect never replays a historical arrival")
	hud.clock += 4000
	hud._refresh()
	expect(hud.release.text.contains("≤6s") and hud.release.text.contains("2 enemies"),
		"a local countdown retains the earlier enemy-count release condition")
	hud.clock += 6001
	hud._refresh()
	expect(hud.release.text.contains("awaiting the next server pulse") and not hud.arrival.visible,
		"clock expiry does not invent an arrival or advance a pulse")
	state.pulses_landed = 2;state.pulses_pending = 1;state.arrival_serial = 2
	app._on_packet(189, JSON.stringify(state).to_utf8_buffer())
	hud.apply_snapshot(state, hud.clock)
	var arrival_until := hud._arrival_until
	expect(hud.arrival.visible and hud.arrival.text == "Reinforcements arrived",
		"an authoritative new pulse creates an audio-independent arrival cue")
	hud.clock += 1000
	hud.apply_snapshot(state, hud.clock)
	expect(hud._arrival_until == arrival_until, "duplicate snapshots cannot restart the arrival cue")
	app._on_packet(189, JSON.stringify(snapshot()).to_utf8_buffer())
	expect(app.gauntlet_progress.arrival_serial == 2 and hud._serial == 2,
		"an older pulse cannot rewind counters or create a later duplicate arrival cue")
	hud.clock += 1600
	hud._refresh()
	expect(not hud.arrival.visible, "the arrival cue expires without another network packet")
	state.release_remaining_ms = null
	hud.apply_snapshot(state, hud.clock)
	expect(hud.release.text.contains("2 or fewer") and not hud.release.text.contains("≤"),
		"ordinary roaming reinforcements use an enemy threshold without a fake timer")
	state.pulses_landed = 3;state.pulses_pending = 0;state.arrival_serial = 3
	state.release_enemy_threshold = null
	hud.apply_snapshot(state, hud.clock)
	expect(hud.release.text == "All reinforcement pulses have arrived.", "the final pulse is distinct from remaining enemies")
	for mutation: String in ["flag", "fraction", "negative", "order", "phase", "timer", "serial", "empty"]:
		var invalid := snapshot()
		match mutation:
			"flag": invalid.active = 1
			"fraction": invalid.wave = 1.5
			"negative": invalid.enemies = -1
			"order": invalid.pulses_pending = 3
			"phase": invalid.phase = {}
			"timer": invalid.release_enemy_threshold = null
			"serial": invalid.arrival_serial = 2
			"empty": invalid.run_id = ""
		expect(decode(invalid).type == "invalid", "malformed encounter " + mutation + " is rejected")
	var before: Dictionary = app.gauntlet_progress.duplicate(true)
	var foreign := snapshot();foreign.map_id = "sunmane_gauntlet_3"
	app._on_packet(189, JSON.stringify(foreign).to_utf8_buffer())
	expect(app.gauntlet_progress == before, "a stale snapshot for another copy cannot replace current progress")
	app._on_packet(189, JSON.stringify({"version":1,"active":false,"run_id":"previous-run","map_id":"sunmane_gauntlet_2"}).to_utf8_buffer())
	expect(app.gauntlet_progress == before, "a delayed terminal snapshot cannot clear a newer run")
	var enabled := [false]
	hud.configure(func() -> Rect2: return Rect2(Vector2(1100,650),Vector2(180,60)),
		func() -> bool: return enabled[0])
	hud._refresh()
	expect(not hud.panel.visible, "the combat HUD visibility preference also hides its encounter companion")
	enabled[0] = true
	hud._refresh()
	await process_frame
	hud._layout()
	expect(root.get_visible_rect().encloses(hud.panel.get_global_rect()), "the companion stays on screen beside an edge-positioned combat HUD")
	root.size = Vector2i(480,320)
	await process_frame;await process_frame
	hud._refresh()
	expect(root.get_visible_rect().encloses(hud.panel.get_global_rect()), "wrapped encounter text remains bounded in a small viewport")
	var map_payload := "maps/nymara/sunmane_gauntlet_3.elm".to_utf8_buffer();map_payload.append(0)
	app._on_packet(EloriaProtocol.ServerMessage.CHANGE_MAP, map_payload)
	expect(app.gauntlet_progress.is_empty() and not hud.panel.visible, "map changes retire the old encounter immediately")
	app.current_map = "maps/nymara/sunmane_gauntlet_2.elm"
	app._on_packet(189, JSON.stringify(snapshot()).to_utf8_buffer())
	app._on_packet(189, JSON.stringify({"version":1,"active":false}).to_utf8_buffer())
	expect(app.gauntlet_progress.is_empty() and not hud.panel.visible, "an explicit terminal snapshot clears the HUD")
	app._on_packet(189, JSON.stringify(snapshot()).to_utf8_buffer())
	app._on_connection_state_changed("disconnected")
	expect(app.gauntlet_progress.is_empty() and not hud.panel.visible and hud._serial == -1,
		"disconnect clears counters and arrival history before reconnect")
	hud.free()
	print("gauntlet progress: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
