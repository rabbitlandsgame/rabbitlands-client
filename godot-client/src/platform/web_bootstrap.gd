extends Control
## Prepare the existing loose runtime assets in the browser's virtual filesystem.
signal archive_ready(ok: bool, message: String)
var bridge: JavaScriptObject
var archive_callback: JavaScriptObject
var label: Label
var completed_bytes := 0
var part_number := 0
var part_count := 0
const ARCHIVE := "/tmp/rabbitlands-prototype-assets.zip"

func _ready() -> void:
	label = Label.new()
	label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.text = "Loading Rabbit Lands browser prototype…"
	add_child(label)
	if not OS.has_feature("web"):
		label.text = "Use the browser build to run this prototype."
		return
	bridge = JavaScriptBridge.get_interface("RabbitLandsBrowser")
	archive_callback = JavaScriptBridge.create_callback(_archive_ready)
	var manifest: Variant = JSON.parse_string(str(JavaScriptBridge.eval("JSON.stringify(window.RL_BROWSER_ASSETS)")))
	var expected: Array = WebPrototype.configuration().get("archives", [])
	if not manifest is Dictionary or expected.is_empty() or manifest.get("archives") != expected:
		label.text = "Game download manifest does not match this build."
		return
	part_count = expected.size()
	var count := 0
	for row: Dictionary in expected:
		part_number += 1
		bridge.fetch_archive(part_number - 1, archive_callback)
		var response: Array = await archive_ready
		if not bool(response[0]):
			label.text = "Cannot load game files: " + str(response[1])
			return
		completed_bytes += int(row.bytes)
		var unpacked := await _unpack(str(row.sha256))
		if unpacked < 0: return
		count += unpacked
	set_process(false)
	print("browser_asset_cache ", JavaScriptBridge.eval("JSON.stringify(window.RL_BROWSER_CACHE_STATS)"))
	if not str(bridge.stats.storage_error).is_empty():
		label.text = "Game files could not be saved by this browser. Future visits may download again."
		await get_tree().create_timer(3.0).timeout
	print("browser_assets_ready ", count, " root=", ProjectSettings.globalize_path("res://"))
	get_tree().change_scene_to_file("res://src/app/main.tscn")

func _process(_delta: float) -> void:
	if bridge != null:
		label.text = "Loading game files: %d/%d (%d reused from this device)" % [part_number, part_count, int(bridge.stats.hits)]

func _archive_ready(args: Array) -> void:
	archive_ready.emit(bool(args[0]), str(args[1]))

func _unpack(expected: String) -> int:
	label.text = "Preparing Landfall (%d/%d)…" % [part_number, part_count]
	await get_tree().process_frame
	if FileAccess.get_sha256(ARCHIVE) != expected:
		label.text = "Game download is incomplete or outdated. Reload to retry."
		DirAccess.remove_absolute(ARCHIVE)
		return -1
	var zip := ZIPReader.new()
	if zip.open(ARCHIVE) != OK:
		label.text = "Cannot open the downloaded game assets."
		return -1
	var count := 0
	for entry: String in zip.get_files():
		if entry.ends_with("/"): continue
		if ".." in entry.split("/") or "\\" in entry or entry.begins_with("/") \
				or not (entry.begins_with("godot-client/assets/") or entry.begins_with("eloria-assets/")):
			label.text = "Invalid game asset path."
			zip.close()
			return -1
		var logical := ("res://" + entry.trim_prefix("godot-client/")) if entry.begins_with("godot-client/") else "res://../" + entry
		var destination := ProjectSettings.globalize_path(logical)
		if destination.begins_with("res://"): destination = destination.trim_prefix("res://")
		if not destination.is_absolute_path(): destination = "/".path_join(destination)
		destination = destination.simplify_path()
		if DirAccess.make_dir_recursive_absolute(destination.get_base_dir()) != OK:
			label.text = "Cannot prepare the game asset folder."
			zip.close()
			return -1
		var file := FileAccess.open(destination, FileAccess.WRITE)
		if file == null:
			label.text = "Cannot prepare a game asset."
			zip.close()
			return -1
		file.store_buffer(zip.read_file(entry))
		file.close()
		count += 1
		if count % 12 == 0: await get_tree().process_frame
	zip.close()
	DirAccess.remove_absolute(ARCHIVE)
	return count
