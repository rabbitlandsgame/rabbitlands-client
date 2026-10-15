extends SceneTree
## Guards the Emotes window.
##
## The list is read from the client's own animation table, so the suite parses
## the same file and demands the window show exactly the emote_* actions it
## holds - no more, no fewer. Performing goes through the Callable the window
## is configured with, and the one-a-second throttle is checked by asking
## twice in the same instant and counting one call.

var failures := 0
var performed: Array[String] = []

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var window: Control = (load("res://src/ui/emotes_window.gd")
		as GDScript).new() as Control
	root.add_child(window)
	await process_frame

	var panel: PanelContainer = window.get_node("EmotesWindow") as PanelContainer
	if not _expect(panel != null, "the window builds its panel"):
		quit(failures)
		return
	_expect(not panel.visible and not bool(window.call("is_open")),
		"the window starts closed")

	# The catalogue: exactly the emote_* actions of luminous.json, stripped
	# and sorted. "bow" is in the shipped table, so it must be here.
	var names: Array = window.call("emote_names") as Array
	var expected: Array[String] = _catalog_emotes()
	_expect(names.has("bow"), "the client can bow: %s" % str(names))
	_expect(not expected.is_empty() and names == expected,
		"every name is the emote_-stripped form of a luminous.json action,"
			+ " sorted: %s" % str(names))

	# Open it. One category, already chosen; the list shows display names.
	window.call("toggle")
	await process_frame
	_expect(panel.visible and bool(window.call("is_open")),
		"toggle() opens the window")
	var rect: Rect2 = panel.get_global_rect()
	_expect(rect.position.x >= 0.0 and rect.position.y >= 0.0
		and rect.end.x <= 1280.0 - float(window.RESERVED_RIGHT_RAIL)
		and rect.end.y <= 720.0,
		"it fits 1280x720 clear of the resource rail: %s" % rect)
	var categories: ItemList = panel.get_node(
		"EmotesBody/CategoryList") as ItemList
	_expect(categories.item_count == 1
		and categories.get_item_text(0) == "Actions"
		and categories.is_selected(0),
		"the single category Actions is listed and pre-selected")
	var emotes: ItemList = panel.get_node("EmotesBody/EmoteList") as ItemList
	_expect(emotes.item_count == expected.size(),
		"the list carries every emote: %d" % emotes.item_count)

	# Selecting shows the trigger line, capitalized name over wire name.
	var trigger: Label = panel.get_node(
		"EmotesBody/EmotesFooter/TriggerLine") as Label
	var do_button: Button = panel.get_node(
		"EmotesBody/EmotesFooter/DoButton") as Button
	_expect(trigger.text.is_empty() and do_button.disabled,
		"nothing is claimed before anything is chosen")
	var bow: int = expected.find("bow")
	_expect(emotes.get_item_text(bow) == "Bow"
		and str(emotes.get_item_metadata(bow)) == "bow",
		"the row shows Bow and carries the wire name bow")
	emotes.select(bow)
	emotes.item_selected.emit(bow)
	_expect(trigger.text == "Trigger:  #emote bow",
		"selecting shows the trigger line: %s" % trigger.text)
	_expect(not do_button.disabled, "and arms the Do button")

	# Performing goes through the configured Callable, once a second at most.
	window.call("configure", _record)
	emotes.item_activated.emit(bow)
	emotes.item_activated.emit(bow)
	_expect(performed == ["bow"],
		"two activations in the same second perform once: %s" % str(performed))
	# The Do button is the other way in, and the cooldown gates it too.
	do_button.pressed.emit()
	_expect(performed == ["bow"],
		"the Do button inside the cooldown does nothing: %s" % str(performed))
	window.set("_last_perform_msec",
		Time.get_ticks_msec() - int(window.PERFORM_COOLDOWN_MSEC) - 1)
	do_button.pressed.emit()
	_expect(performed == ["bow", "bow"],
		"once the second has passed the Do button performs: %s" % str(performed))

	# Open, closed, open again.
	window.call("close")
	_expect(not panel.visible and not bool(window.call("is_open")),
		"close() hides it")
	window.call("toggle")
	_expect(panel.visible and bool(window.call("is_open")),
		"and toggle() brings it back")
	window.call("toggle")
	_expect(not bool(window.call("is_open")), "toggle() again puts it away")

	print("emotes window tests: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	window.queue_free()
	await process_frame
	quit(failures)

func _record(wire: String) -> void:
	performed.append(wire)

## The same file the window reads, reduced the same way: every emote_* key of
## the actions table, stripped and sorted.
func _catalog_emotes() -> Array[String]:
	var found: Array[String] = []
	var file: FileAccess = FileAccess.open(
		"res://data/animations/luminous.json", FileAccess.READ)
	if file == null:
		return found
	var parsed: Dictionary = JSON.parse_string(file.get_as_text()) as Dictionary
	var actions: Dictionary = parsed.get("actions", {}) as Dictionary
	for key: Variant in actions:
		if str(key).begins_with("emote_"):
			found.append(str(key).trim_prefix("emote_"))
	found.sort()
	return found

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
