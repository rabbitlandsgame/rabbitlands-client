extends SceneTree
const Capture := preload("res://src/platform/browser_capture.gd")
var captured: Array = []

func _initialize() -> void:
	call_deferred("_run")

func _download(bytes: PackedByteArray, filename: String, mime: String) -> void:
	captured.append({"bytes":bytes, "filename":filename, "mime":mime})

func _run() -> void:
	assert(Capture.download_png(null, "unused.png", _download) == ERR_INVALID_PARAMETER)
	assert(captured.is_empty())
	var image := Image.create(3, 2, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.4, 0.6, 0.8, 1.0))
	assert(Capture.download_png(image, "rabbitlands-test.png", _download) == OK)
	assert(captured.size() == 1)
	assert(captured[0].filename == "rabbitlands-test.png" and captured[0].mime == "image/png")
	var restored := Image.new()
	assert(restored.load_png_from_buffer(captured[0].bytes) == OK)
	assert(restored.get_size() == image.get_size() and restored.get_data() == image.get_data())
	print("browser screenshot download: PASS")
	quit()
