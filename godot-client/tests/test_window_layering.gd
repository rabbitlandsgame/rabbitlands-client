extends SceneTree
## Guards the stacking order between the UI windows and the actor banner.
##
## The local player's name and bars follow the player around the middle of
## the screen at z 1, so any window that keeps a CanvasItem's default z of 0
## slides underneath them - the Reference window shipped that way. Every
## window, scene-built or code-built, must outrank the banner overlay.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	var banner: Control = main.get_node("%ActorResourceOverlay") as Control
	var banner_z: int = banner.z_index
	_expect(banner_z >= 1, "the actor banner clears the world viewport")
	for member: String in [
			"full_map", "stats_panel", "inventory_panel", "dialogue_panel",
			"trade_panel", "storage_panel", "ground_bag_panel",
			"manufacturing_panel", "item_lists_panel", "console_panel",
			"reading_panel", "popup_panel", "settings_panel",
			"spells_window", "emotes_window", "ranging_window", "guild_window",
			"settings_window", "reference_window", "player_info_panel"]:
		var window: Control = main.get(member) as Control
		if window == null:
			failures += 1
			push_error("FAIL: %s is not a Control on the main scene" % member)
			continue
		_expect(window.z_index > banner_z,
			"%s draws above the actor banner (z %d vs %d)"
			% [member, window.z_index, banner_z])
	main.queue_free()
	await process_frame
	print("window layering tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(value: bool, label: String) -> void:
	if value:
		return
	failures += 1
	push_error("FAIL: " + label)
