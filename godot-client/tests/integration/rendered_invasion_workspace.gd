extends SceneTree
## Focused UI rendering, independent of the client's world and actor loaders.
const Assistant := preload("res://src/ui/invasion_assistant.gd")
const Fixtures := preload("res://tests/integration/rendered_invasion_assistant.gd")
var _assistant: Window
var _artifacts := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/invasion-workspace")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	root.size = Vector2i(1280, 720)
	RenderingServer.set_default_clear_color(Color("25383c"))
	_assistant = Assistant.new()
	_assistant.monitor_preferences_path = _artifacts.path_join("preferences.cfg")
	root.add_child(_assistant)
	_assistant.set_process(false)
	_assistant.configure_monitor_dock(func() -> Rect2: return Rect2(0, 0, 1184, 680))
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json"))
	_assistant.configure_registry(registry.get("maps", {}))
	_assistant._preferred_scale = 1.0
	_assistant.apply_update({"kind": "index", "selected_map": "four_gates", "totals": {"players": 34, "invasions": 61, "active_groups": 3}, "maps": Fixtures._index_maps()})
	_assistant.apply_update(Fixtures._map_state())
	var groups: Dictionary = Fixtures._groups_state()
	groups.groups[0].alive = 24
	groups.groups[0].queued = 12
	groups.groups[0].composition[2].quantity = 8
	groups.groups[0].movement = {"anchor": {"x": 310, "y": 260}, "radius": 18, "region": null}
	for entry: Array in [["Market Vanguard", 28, 0], ["South Gate Patrol", 9, 6]]:
		var group: Dictionary = groups.groups[0].duplicate(true)
		group.name = entry[0]
		group.alive = entry[1]
		group.queued = entry[2]
		groups.groups.append(group)
	_assistant.apply_update(groups)
	_assistant.apply_update(Fixtures._monsters_state())
	_assistant._show_inspector_section(1)
	_assistant._fit_to_viewport()
	await _capture("B-builder.png")
	_assistant._show_inspector_section(2)
	await _capture("B-settings.png")
	_assistant._show_inspector_section(0)
	_assistant.resize_to_scale(0.65)
	_assistant._size_save_countdown = 0.0
	await _capture("B-compact.png")
	_assistant.set_monitor_mode(true)
	_assistant._on_monitor_location(1)
	_assistant._update_freshness()
	await _capture("C-monitor.png")
	_assistant._monitor_rows["Market Vanguard"].button.pressed.emit()
	if _assistant.selected_group.name != "Market Vanguard":
		_failures += 1
	_assistant.monitor_composition_button.pressed.emit()
	await _capture("C-composition.png")
	_assistant.set_monitor_docked(false)
	await _capture("C-floating.png")
	print("focused invasion workspace render: ", "PASS" if _failures == 0 else "FAIL")
	_assistant.queue_free()
	quit(_failures)

func _capture(name: String) -> void:
	for i: int in range(4):
		await process_frame
	await RenderingServer.frame_post_draw
	var pixels := root.get_texture().get_image()
	if pixels == null or pixels.save_png(_artifacts.path_join(name)) != OK:
		_failures += 1
	print("capture ", name)
