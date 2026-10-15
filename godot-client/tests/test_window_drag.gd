extends SceneTree
## Guards the two things the HUD follow-up promised about windows and icons.
##
## Every window moves by its title bar, as Eternal Lands moves all of its own,
## and a window dragged past the edge is pulled back rather than lost - a
## window whose title bar left the screen could never be dragged back.
##
## The sit icon is a pair, the way icon_window.cpp's multi-icon is: it wears
## the stand icon while the player is seated, because standing is what pressing
## it does then.

## Every scene window that must answer to a drag, and the handle it is grabbed
## by. The console and the full map are deliberately absent: both are
## full-screen views rather than popups.
const DRAGGABLE := {
	"GameView/ChatWindow": "Frame/Layout/Header",
	"GameView/StatsPanel": "Content/Header",
	"GameView/TradePanel": "Content/Title",
	"GameView/StoragePanel": "Content/Title",
	"GameView/ManufacturingPanel": "Content/Title",
	"GameView/ItemListsPanel": "Content/Header",
	"GameView/DialoguePanel": "DialogueContent/DialogueName",
	"GameView/PopupPanel": "PopupContent/PopupTitle",
	"GameView/ReadingPanel": "ReadingContent/ReadingHeader",
}

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene
		).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("LoginPanel") as Control).hide()
	(main.get_node("GameView") as Control).show()
	await process_frame

	for path: Variant in DRAGGABLE:
		var panel: Control = main.get_node_or_null(str(path)) as Control
		_expect(panel != null, "%s exists" % str(path))
		if panel == null:
			continue
		var handle: Control = panel.get_node_or_null(
			str(DRAGGABLE[path])) as Control
		_expect(handle != null and handle.mouse_filter == Control.MOUSE_FILTER_STOP,
			"%s is grabbed by %s" % [str(path), str(DRAGGABLE[path])])
		var dragger: Node = panel.get_node_or_null("WindowDrag")
		_expect(dragger != null and dragger.get("window") == panel,
			"%s moves by its title bar" % str(path))

	# The script-built windows carry the same node, so none of them is the one
	# window a player cannot move.
	for window_name: String in ["settings_window", "reference_window",
			"spells_window", "emotes_window", "ranging_window"]:
		var layer: Node = main.get(window_name) as Node
		_expect(layer != null, "%s is built" % window_name)
		if layer == null:
			continue
		var panel: Control = layer.get("panel") as Control
		_expect(panel != null and panel.get_node_or_null("WindowDrag") != null,
			"%s moves by its title bar" % window_name)

	# A window dragged off the top-left is pulled back to the margin rather
	# than left somewhere its title bar cannot be reached.
	var stats_panel: Control = main.get_node("GameView/StatsPanel") as Control
	stats_panel.show()
	var dragger: Node = stats_panel.get_node("WindowDrag")
	stats_panel.global_position = Vector2(-400.0, -400.0)
	dragger.call("clamp_into_view")
	_expect(stats_panel.global_position.x >= 0.0
		and stats_panel.global_position.y >= 0.0,
		"a window dragged off the corner is pulled back into view: %s"
			% stats_panel.global_position)
	# And one dragged over the rail is kept clear of it, because nothing may
	# cover the fixed resource rail.
	stats_panel.global_position = Vector2(4000.0, 4000.0)
	dragger.call("clamp_into_view")
	_expect(stats_panel.get_global_rect().end.x <= 1280.0 - 96.0 + 1.0,
		"a window dragged over the rail is kept clear of it: %s"
			% stats_panel.get_global_rect())
	stats_panel.hide()

	# The sit icon and the stand icon are one pair.
	var app_state: Node = root.get_node("AppState")
	app_state.set("local_actor_id", 7)
	app_state.set("actors", {7: {"actor_id": 7, "name": "Ari", "kind": 1,
		"alive": true, "sitting": false}})
	main.call("_sync_hud_button_states", true)
	var sit_button: Button = main.get_node(
		"GameView/Quickbar/QuickRows/Buttons/SitButton") as Button
	var standing_region: Rect2 = (sit_button.icon as AtlasTexture).region
	(app_state.get("actors") as Dictionary)[7]["sitting"] = true
	main.call("_sync_hud_button_states", true)
	var seated_region: Rect2 = (sit_button.icon as AtlasTexture).region
	_expect(seated_region != standing_region
		and seated_region == main.get("STAND_ICON_REGION"),
		"the sit icon wears the stand icon while seated: %s" % seated_region)
	(app_state.get("actors") as Dictionary)[7]["sitting"] = false
	main.call("_sync_hud_button_states", true)
	_expect((sit_button.icon as AtlasTexture).region == standing_region,
		"and goes back to the sit icon on standing")

	app_state.set("local_actor_id", -1)
	(app_state.get("actors") as Dictionary).clear()
	print("window drag tests: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	quit(failures)

func _expect(value: bool, label: String) -> void:
	if value:
		return
	failures += 1
	push_error("FAIL: " + label)
