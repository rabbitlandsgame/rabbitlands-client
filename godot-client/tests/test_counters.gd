extends SceneTree
## Replay server packets through the counters window's expand controls.

const P := preload("res://src/network/protocol.gd")
# Payloads from eloria.protocol.counter_layout_packet.
const LAYOUT := "01030003436f6d626174004b696c6c730044656174687300427265616b6167657300014b696c6c7300040000004d6972726f7266696e204f74746572000244656174687300020000004d6972726f7266696e204f747465720001000000506f69736f6e0002427265616b6167657300010000004d696c697469612041726d696e672053776f72640001000000576f6f64656e20526f756e6420536869656c6400"
const UPDATED_LAYOUT := "01030003436f6d626174004b696c6c730044656174687300427265616b6167657300014b696c6c7300040000004d6972726f7266696e204f74746572000244656174687300030000004d6972726f7266696e204f747465720001000000506f69736f6e0002427265616b6167657300010000004d696c697469612041726d696e672053776f72640001000000576f6f64656e20526f756e6420536869656c6400"
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var state := root.get_node("/root/AppState")
	var hud := load("res://src/app/main.gd").new() as Control
	var panel := Control.new()
	var body := VBoxContainer.new()
	hud.add_child(panel)
	panel.add_child(body)
	hud.set("stats_panel", panel)
	hud.set("counter_body", body)
	hud.set("_counter_session_baseline", {"Kills": 4, "Deaths": 2, "Breakages": 1})
	state.call("_on_packet", P.ServerMessage.ELORIA_ACTIVITY_COUNTERS,
		"0103040000004b696c6c7300030000004465617468730002000000427265616b6167657300".hex_decode())
	state.call("_on_packet", P.ServerMessage.ELORIA_COUNTER_LAYOUT, LAYOUT.hex_decode())
	hud.call("_sync_counters")
	for counter: String in ["Kills", "Deaths", "Breakages"]:
		_expect(body.get_child(0).has_node("Counter%s/Expand" % counter),
			"%s has a detailed breakdown control" % counter)
	_expect(_details(body).is_empty(), "breakdowns start collapsed")
	for counter: String in ["Deaths", "Breakages"]:
		var arrow := body.get_child(0).get_node("Counter%s/Expand" % counter) as Button
		arrow.pressed.emit()
	_expect(_details(body) == ["Mirrorfin Otter=2", "Poison=1",
		"Militia Arming Sword=1", "Wooden Round Shield=1"],
		"death causes and broken items open independently with lifetime counts")
	var deaths := body.get_child(0).get_node("CounterDeaths")
	_expect((deaths.get_child(1) as Label).text == "1"
		and (deaths.get_child(2) as Label).text == "3",
		"the total retains its session and global columns")
	state.call("_on_packet", P.ServerMessage.ELORIA_COUNTER_LAYOUT,
		UPDATED_LAYOUT.hex_decode())
	hud.call("_sync_counters")
	_expect(_details(body) == ["Mirrorfin Otter=3", "Poison=1",
		"Militia Arming Sword=1", "Wooden Round Shield=1"],
		"an incoming layout refreshes counts while both breakdowns stay open")
	(body.get_child(0).get_node("CounterDeaths/Expand") as Button).pressed.emit()
	_expect(_details(body) == ["Militia Arming Sword=1", "Wooden Round Shield=1"],
		"collapsing deaths leaves breakages open")
	# A new character has no details and therefore no empty expand controls.
	state.call("_on_packet", P.ServerMessage.ELORIA_COUNTER_LAYOUT,
		"01000003436f6d626174004b696c6c730044656174687300427265616b6167657300".hex_decode())
	hud.call("_sync_counters")
	for counter: String in ["Kills", "Deaths", "Breakages"]:
		_expect(not body.get_child(0).has_node("Counter%s/Expand" % counter),
			"%s hides its control when there are no details" % counter)
	hud.free()
	await process_frame
	print("counter breakdowns: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _details(body: VBoxContainer) -> Array[String]:
	var details: Array[String] = []
	for row: Node in body.get_child(0).get_children():
		var label := row.get_child(0) as Label
		if not label.text.begins_with("    "):
			continue
		details.append("%s=%s" % [label.text.strip_edges(),
			(row.get_child(2) as Label).text])
		_expect((row.get_child(1) as Label).text.is_empty(),
			"details show lifetime counts without inventing session values")
	return details

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)
