extends Control
## Prepare the existing loose runtime assets in the browser's virtual filesystem.
var request: HTTPRequest
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
	request = HTTPRequest.new()
	request.download_chunk_size = 1024 * 1024
	request.body_size_limit = 64 * 1024 * 1024
	add_child(request)
	var manifest: Variant = JSON.parse_string(str(JavaScriptBridge.eval("JSON.stringify(window.RL_BROWSER_ASSETS)")))
	var expected: Array = WebPrototype.configuration().get("archives", [])
	if not manifest is Dictionary or expected.is_empty() or manifest.get("archives") != expected:
		label.text = "Game download manifest does not match this build."
		return
	part_count = expected.size()
	var count := 0
	for row: Dictionary in expected:
		part_number += 1
		var url := str(manifest.base_url) + str(row.file)
		if request.request(url) != OK:
			label.text = "Could not start the game download. Reload to retry."
			return
		var response: Array = await request.request_completed
		if response[0] != HTTPRequest.RESULT_SUCCESS or response[1] != 200:
			label.text = "Game download failed (%d/%d). Reload to retry." % [response[0], response[1]]
			return
		var body: PackedByteArray = response[3]
		response.clear()
		if body.size() != int(row.bytes):
			label.text = "Game download is incomplete. Reload to retry."
			return
		completed_bytes += body.size()
		var unpacked := await _unpack(body, str(row.sha256))
		if unpacked < 0: return
		count += unpacked
	set_process(false)
	print("browser_assets_ready ", count, " root=", ProjectSettings.globalize_path("res://"))
	get_tree().change_scene_to_file("res://src/app/main.tscn")

func _process(_delta: float) -> void:
	if request != null and request.get_http_client_status() == HTTPClient.STATUS_BODY:
		label.text = "Downloading game assets: %.1f MB (%d/%d)" % [
			(completed_bytes + request.get_downloaded_bytes()) / 1048576.0, part_number, part_count]

func _unpack(body: PackedByteArray, expected: String) -> int:
	label.text = "Preparing Landfall (%d/%d)…" % [part_number, part_count]
	DirAccess.make_dir_recursive_absolute(ARCHIVE.get_base_dir())
	var downloaded := FileAccess.open(ARCHIVE, FileAccess.WRITE)
	if downloaded == null:
		label.text = "Cannot prepare the downloaded game assets."
		return -1
	downloaded.store_buffer(body)
	downloaded.close()
	body.clear()
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
