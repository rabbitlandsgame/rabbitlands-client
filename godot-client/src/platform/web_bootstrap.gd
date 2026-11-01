extends Control
## Unpacks the bounded prototype's existing loose files into the browser's
## private virtual filesystem before starting the ordinary client scene.
var request: HTTPRequest
var label: Label
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
	request.body_size_limit = 1024 * 1024 * 1024
	add_child(request)
	request.request_completed.connect(_downloaded)
	var base := str(JavaScriptBridge.eval("window.location.href.split('#')[0].split('?')[0].replace(/[^/]*$/, '')"))
	var assets_url := str(WebPrototype.configuration().get("assets_url", ""))
	if assets_url.is_empty(): assets_url = base + "assets.zip"
	if request.request(assets_url) != OK:
		label.text = "Could not start the game download. Reload to retry."

func _process(_delta: float) -> void:
	if request != null and request.get_http_client_status() == HTTPClient.STATUS_BODY:
		label.text = "Downloading game assets: %.1f MB" % (request.get_downloaded_bytes() / 1048576.0)

func _downloaded(result: int, code: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
	set_process(false)
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		label.text = "Game download failed (%d/%d). Reload to retry." % [result, code]
		return
	label.text = "Preparing Landfall…"
	# Materialize explicitly: the web HTTP backend can report a completed file
	# download after removing its temporary file during request cleanup.
	DirAccess.make_dir_recursive_absolute(ARCHIVE.get_base_dir())
	var downloaded := FileAccess.open(ARCHIVE, FileAccess.WRITE)
	if downloaded == null:
		label.text = "Cannot prepare the downloaded game assets."
		return
	downloaded.store_buffer(_body)
	downloaded.close()
	_body.clear()
	await get_tree().process_frame
	var expected := str(WebPrototype.configuration().get("assets_sha256", ""))
	var actual := FileAccess.get_sha256(ARCHIVE)
	if expected.is_empty() or actual != expected:
		push_error("browser_asset_digest expected=%s actual=%s" % [expected, actual])
		label.text = "Game download is incomplete or outdated. Reload to retry."
		return
	var zip := ZIPReader.new()
	if zip.open(ARCHIVE) != OK:
		label.text = "Cannot open the downloaded game assets."
		return
	var count := 0
	for entry: String in zip.get_files():
		if entry.ends_with("/"): continue
		if ".." in entry.split("/") or "\\" in entry or entry.begins_with("/") \
				or not (entry.begins_with("godot-client/assets/") or entry.begins_with("eloria-assets/")):
			label.text = "Invalid game asset path."
			zip.close()
			return
		var logical := ("res://" + entry.trim_prefix("godot-client/")) if entry.begins_with("godot-client/") else "res://../" + entry
		var destination := ProjectSettings.globalize_path(logical)
		if destination.begins_with("res://"): destination = destination.trim_prefix("res://")
		if not destination.is_absolute_path(): destination = "/".path_join(destination)
		destination = destination.simplify_path()
		if DirAccess.make_dir_recursive_absolute(destination.get_base_dir()) != OK:
			label.text = "Cannot prepare the game asset folder."
			zip.close()
			return
		var file := FileAccess.open(destination, FileAccess.WRITE)
		if file == null:
			label.text = "Cannot prepare a game asset."
			zip.close()
			return
		file.store_buffer(zip.read_file(entry))
		file.close()
		count += 1
		if count % 12 == 0: await get_tree().process_frame
	zip.close()
	DirAccess.remove_absolute(ARCHIVE)
	print("browser_assets_ready ", count, " root=", ProjectSettings.globalize_path("res://"))
	get_tree().change_scene_to_file("res://src/app/main.tscn")
