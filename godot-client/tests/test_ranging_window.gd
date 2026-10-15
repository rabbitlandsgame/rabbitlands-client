extends SceneTree
## Guards the ranging window.
##
## The window is a session tally of what the client honestly saw: a shot is a
## `missile_fired` event from the local actor, a hit is a ranging experience
## award, and everything else on it is arithmetic on those two counts. These
## tests emit the same signals AppState emits and expect the rows to say
## exactly what was counted - including while the panel is hidden, because a
## stat that only counted while watched would lie.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("local_actor_id", 7)
	# Loaded at runtime rather than preloaded: a preload would compile the
	# window before the autoloads it reads are registered.
	var window: Control = (load("res://src/ui/ranging_window.gd")
		as GDScript).new() as Control
	root.add_child(window)
	await process_frame

	var panel: PanelContainer = window.get_node("RangingWindow") as PanelContainer
	if not _expect(panel != null, "the window builds its panel"):
		quit(failures)
		return
	_expect(not panel.visible and not bool(window.call("is_open")),
		"it starts closed")

	# Counting runs even while hidden, and only the local actor's arrows count.
	app_state.emit_signal("missile_fired",
		{"source_actor_id": 7, "target_actor_id": 9})
	app_state.emit_signal("missile_fired",
		{"source_actor_id": 12, "target_actor_id": 7})
	_expect(int(window.get("shots")) == 1,
		"a local shot counts while hidden and another actor's does not: %d"
			% int(window.get("shots")))

	window.call("toggle")
	await process_frame
	_expect(panel.visible and bool(window.call("is_open")),
		"toggle opens it")
	var title: Label = panel.get_node(
		"RangingBody/RangingHeader/RangingTitle") as Label
	var close_button: Button = panel.get_node(
		"RangingBody/RangingHeader/RangingClose") as Button
	_expect(title != null and title.text == "Ranging"
		and close_button != null and close_button.text == "X",
		"the header carries the title and an X, per the house pattern")
	var rect: Rect2 = panel.get_global_rect()
	_expect(rect.position.x >= 0.0 and rect.position.y >= 0.0
		and rect.end.x <= 1280.0 - window.RESERVED_RIGHT_RAIL
		and rect.end.y <= 720.0,
		"it sits upper-left, clear of the resource rail: %s" % rect)

	var total: Label = panel.get_node("RangingBody/TotalShots") as Label
	var hit_row: Label = panel.get_node("RangingBody/SuccessfulHits") as Label
	var missed: Label = panel.get_node("RangingBody/MissedHits") as Label
	var success: Label = panel.get_node("RangingBody/SuccessRate") as Label
	var critical: Label = panel.get_node("RangingBody/CriticalRate") as Label
	var per_arrow: Label = panel.get_node("RangingBody/ExpPerArrow") as Label
	_expect(total.text == "Total shots 1",
		"opening shows what was counted while hidden: " + total.text)
	_expect(hit_row.text == "Successful hits 0"
		and missed.text == "Missed hits 1"
		and success.text == "Success rate 0.00 %"
		and per_arrow.text == "Exp/arrows 0.00 exp",
		"a shot with no award yet is a miss: %s / %s / %s / %s"
			% [hit_row.text, missed.text, success.text, per_arrow.text])

	# A second shot and its award: the award is the hit.
	app_state.emit_signal("missile_fired",
		{"source_actor_id": 7, "target_actor_id": 9})
	app_state.emit_signal("floating_feedback_requested",
		{"kind": "experience", "skill": "ranging", "amount": 25, "value": 125})
	_expect(int(window.get("shots")) == 2 and int(window.get("hits")) == 1
		and int(window.get("ranging_exp")) == 25,
		"a ranging award counts one hit and its experience")
	_expect(total.text == "Total shots 2"
		and hit_row.text == "Successful hits 1"
		and missed.text == "Missed hits 1",
		"missed stays shots minus hits: %s / %s / %s"
			% [total.text, hit_row.text, missed.text])
	_expect(success.text == "Success rate 50.00 %",
		"the success rate is hits over shots: " + success.text)
	_expect(per_arrow.text == "Exp/arrows 12.50 exp",
		"exp per arrow is total exp over shots: " + per_arrow.text)
	_expect(critical.text == "Critical rate -",
		"criticals render a dash because the server never states them: "
			+ critical.text)

	# Another skill's experience and a ranging level-up are not hits.
	app_state.emit_signal("floating_feedback_requested",
		{"kind": "experience", "skill": "ranging", "amount": 80, "bonus": true})
	app_state.emit_signal("floating_feedback_requested",
		{"kind": "experience", "skill": "attack", "amount": 40, "value": 40})
	app_state.emit_signal("floating_feedback_requested",
		{"kind": "level", "skill": "ranging", "level": 12})
	_expect(int(window.get("hits")) == 1 and int(window.get("ranging_exp")) == 25,
		"only normal ranging experience awards count as hits; tutorial bonuses do not")

	# Reset, from the button the way the player would.
	(panel.get_node("RangingBody/RangingReset") as Button).pressed.emit()
	_expect(int(window.get("shots")) == 0 and int(window.get("hits")) == 0
		and int(window.get("ranging_exp")) == 0,
		"reset zeroes the session counters")
	_expect(total.text == "Total shots 0"
		and success.text == "Success rate 0.00 %"
		and per_arrow.text == "Exp/arrows 0.00 exp",
		"and the rows say so at once: %s / %s / %s"
			% [total.text, success.text, per_arrow.text])

	close_button.pressed.emit()
	await process_frame
	_expect(not panel.visible and not bool(window.call("is_open")),
		"the X closes it")
	window.call("toggle")
	_expect(bool(window.call("is_open")), "toggle reopens it")
	window.call("toggle")
	_expect(not bool(window.call("is_open")), "and toggle closes it again")
	window.call("toggle")
	window.call("close")
	_expect(not bool(window.call("is_open")), "close() closes it")

	print("ranging window tests: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	window.queue_free()
	await process_frame
	quit(failures)

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
