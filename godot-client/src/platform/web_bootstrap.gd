extends Control
## Only shared login/creation files load up front. Maps and rare actors are lazy.
const Assets := preload("res://src/platform/browser_asset_service.gd")
signal retry_requested
var label: Label
var service: Node
var retry_button: Button
var _reload_only := false

func _ready() -> void:
	label = Label.new()
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.text = "Loading Rabbit Lands…"
	var centre := CenterContainer.new()
	centre.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(centre)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 20)
	centre.add_child(column)
	column.add_child(label)
	retry_button = Button.new()
	retry_button.name = "Retry"
	retry_button.custom_minimum_size = Vector2(160, 40)
	retry_button.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	retry_button.pressed.connect(_on_retry_pressed)
	column.add_child(retry_button)
	retry_button.hide()
	if not OS.has_feature("web"):
		label.text = "Use the browser build to run this client."
		return
	var manifest: Variant = JSON.parse_string(str(JavaScriptBridge.eval("JSON.stringify(window.RL_BROWSER_ASSETS)")))
	service = Assets.new()
	service.name = "BrowserAssetService"
	get_tree().root.add_child.call_deferred(service)
	await get_tree().process_frame
	if not manifest is Dictionary or not service.call("configure", WebPrototype.configuration(), manifest):
		_show_failure(true)
		return
	while not bool(service.call("ensure_groups", ["startup"], "startup")):
		var state: Dictionary = service.call("snapshot")
		if not str(state.error).is_empty():
			_show_failure((state.get("failed_groups", []) as Array).is_empty())
			await retry_requested
			set_process(true)
		await get_tree().process_frame
	set_process(false)
	print("browser_asset_cache ", JavaScriptBridge.eval("JSON.stringify(window.RL_BROWSER_CACHE_STATS)"))
	if not str(service.bridge.stats.storage_error).is_empty():
		label.text = "Game files could not be saved by this browser. Future visits may download again."
		await get_tree().create_timer(3.0).timeout
	print("browser_assets_ready startup root=", ProjectSettings.globalize_path("res://"))
	get_tree().change_scene_to_file("res://src/app/main.tscn")

func _process(_delta: float) -> void:
	if is_instance_valid(service):
		var state: Dictionary = service.call("snapshot")
		label.text = "Preparing game files (%d archives ready)…" % int(state.get("completed_archives", 0))

func _show_failure(reload_only: bool) -> void:
	set_process(false)
	_reload_only = reload_only
	label.text = ("Game files have changed. Reload to get the matching version." if reload_only
		else "Game files could not be loaded.\nCheck your connection and try again.")
	retry_button.text = "Reload" if reload_only else "Retry"
	retry_button.show()
	retry_button.grab_focus.call_deferred()

func _on_retry_pressed() -> void:
	if not retry_button.visible: return
	if _reload_only:
		JavaScriptBridge.eval("location.reload()")
		return
	retry_button.hide()
	service.call("retry_failed")
	label.text = "Retrying game files…"
	retry_requested.emit()
