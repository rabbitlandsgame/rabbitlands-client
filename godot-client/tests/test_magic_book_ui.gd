extends SceneTree
var failures := 0

class CaptureNetwork extends EloriaNetworkClient:
	var sent: PackedByteArray
	func send_frame(frame: PackedByteArray, _sensitive := false) -> Error:
		sent = frame
		return OK

func _init() -> void: call_deferred("run")
func check(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func run() -> void:
	root.size = Vector2i(1280, 800)
	var capture := CaptureNetwork.new()
	capture.magic_pending = {"op":"cast", "id":6, "power":8}
	capture.magic_scope = "target"
	capture.touch_actor(44)
	var request: Dictionary = JSON.parse_string(capture.sent.slice(3).get_string_from_utf8())
	check(capture.sent[0] == 202 and request.target_id == 44 and request.power == 8, "actor selection preserves the chosen power")
	check(capture.magic_pending.is_empty(), "selection is consumed once")
	capture.magic_pending = {"op":"cast", "id":20, "power":5}
	capture.magic_scope = "burst"
	capture.move_to(Vector2i(12, 14))
	request = JSON.parse_string(capture.sent.slice(3).get_string_from_utf8())
	check(capture.sent[0] == 202 and request.x == 12 and request.y == 14, "ground selection casts a Burst instead of moving")
	capture.free()
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	main.get_node("LoginPanel").hide()
	main.get_node("GameView").show()
	var selector: Control = main.get("magic_selection")
	selector.pending={"op":"cast","id":10,"power":1}
	root.get_node("Network").magic_selection_completed.emit()
	check(selector.pending.is_empty(),"a completed target selection cannot later count as cancellation")
	var payload := {"kind":"transmute", "id":8, "entries":[{"slot":2,"item_id":33,
		"instance_id":0,"name":"Deep Coal","rarity":"Rare","required_power":5,
		"available":10,"unit_gold":24}]}
	selector.pending = {"op":"cast","id":8,"power":4}
	root.get_node("AppState").call("_on_packet", 212, JSON.stringify(payload).to_utf8_buffer())
	check(selector.popup.visible and selector.popup.get_ok_button().disabled, "Rare items cannot be transmuted below Power 5")
	selector.pending.power = 5
	selector.quantity.value = 3
	selector.call("_update_quote")
	check(not selector.popup.get_ok_button().disabled and selector.description.text.contains("72 Gold Coins"), "Transmute previews selected quantity and exact gold")
	await capture_ui("transmute.png")
	selector.cancel()
	selector.pending = {"op":"cast","id":9,"power":5}
	root.get_node("AppState").call("_on_packet", 212, JSON.stringify({"kind":"recall","id":9,
		"entries":[{"key":"forest:20:21","name":"Amberwood","map":"forest","x":20,"y":21}]}).to_utf8_buffer())
	check(selector.choices.get_item_text(0).contains("Amberwood") and not selector.quantity.visible, "Recall shows portal entrance choices")
	await capture_ui("recall.png")
	selector.cancel()
	var window: Control = main.get("spells_window")
	window.call("toggle")
	window.search.text = "ward"
	window.scope_filter.select(3)
	window.call("_filter_spells")
	var visible_count := 0
	for button: Button in window._buttons.values():
		if button.visible:
			visible_count += 1
			check(button.tooltip_text.contains("Allies"), "scope filter contains only Allies variants")
	check(visible_count == 5, "five individual/combined ward families are searchable")
	window.call("_on_spell_pressed", 31)
	await capture_ui("spellbook.png")
	root.get_node("AppState").call("_on_packet", 212, JSON.stringify({"kind":"burst","effect":84,
		"power":10,"radius":4,"x":20,"y":20,"scope":"burst"}).to_utf8_buffer())
	var effects: Array = main.get("world_effects")
	check(not effects.is_empty() and effects.back().area_radius > 0, "the area packet creates a production world pulse")
	var source := ReplicatedActor3D.new()
	var target := ReplicatedActor3D.new()
	main.get("world_root").add_child(source)
	main.get("world_root").add_child(target)
	source.position = Vector3(10, 0, -20)
	target.position = Vector3(20, 0, -20)
	main.get("actor_nodes")[901] = source
	main.get("actor_nodes")[902] = target
	root.get_node("AppState").call("_on_packet", 212, JSON.stringify({"kind":"spell_impact",
		"effect":83,"actor_id":901,"target_id":902,"power":4,
		"release_delay":0.45,"flight_duration":0.62}).to_utf8_buffer())
	effects = main.get("world_effects")
	var timed: WorldEffect3D = effects.back()
	timed.set_process(false)
	check(timed.flight != null and is_equal_approx(timed.release_delay, 0.45)
		and is_equal_approx(timed.flight.duration, 0.62) and not timed.impact_started,
		"timed target packets reach the production effect with the server clock")
	root.get_node("AppState").call("_on_packet", 212, JSON.stringify({"kind":"burst","effect":83,
		"actor_id":901,"power":4,"radius":4,"x":20,"y":20,"scope":"burst",
		"release_delay":0.45,"flight_duration":0.62}).to_utf8_buffer())
	effects = main.get("world_effects")
	timed = effects.back()
	timed.set_process(false)
	check(timed.flight != null and timed.area_radius > 0 and not timed.impact_started,
		"timed bursts travel from the caster and delay the area pulse until impact")
	timed._process(1.069)
	check(not timed.impact_started, "production burst does not explode early")
	timed._process(0.002)
	check(timed.impact_started, "production burst explodes at the damage deadline")
	await process_frame
	await process_frame
	main.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("magic book UI: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func capture_ui(filename: String) -> void:
	var path := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if path.is_empty() or DisplayServer.get_name() == "headless": return
	await process_frame
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(path)
	root.get_texture().get_image().save_png(path.path_join(filename))
