extends Control
## Only shared login/creation files load up front. Maps and rare actors are lazy.
const Assets := preload("res://src/platform/browser_asset_service.gd")
var label: Label
var service: Node

func _ready() -> void:
	label = Label.new()
	label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.text = "Loading Rabbit Lands…"
	add_child(label)
	if not OS.has_feature("web"):
		label.text = "Use the browser build to run this client."
		return
	var manifest: Variant = JSON.parse_string(str(JavaScriptBridge.eval("JSON.stringify(window.RL_BROWSER_ASSETS)")))
	service = Assets.new()
	service.name = "BrowserAssetService"
	get_tree().root.add_child.call_deferred(service)
	await get_tree().process_frame
	if not manifest is Dictionary or not service.call("configure", WebPrototype.configuration(), manifest):
		label.text = "Game download catalog does not match this build."
		set_process(false)
		return
	while not bool(service.call("ensure_groups", ["startup"], "startup")):
		var state: Dictionary = service.call("snapshot")
		if not str(state.error).is_empty():
			label.text = "Cannot load game files: " + str(state.error)
			set_process(false)
			return
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
