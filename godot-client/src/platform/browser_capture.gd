extends RefCounted
## A player-requested PNG download, never a hidden browser filesystem path.

static func download_png(image: Image, filename: String, downloader := Callable()) -> Error:
	if image == null or image.is_empty():
		return ERR_INVALID_PARAMETER
	if not downloader.is_valid() and not OS.has_feature("web"):
		return ERR_UNAVAILABLE
	var png := image.save_png_to_buffer()
	if png.is_empty():
		return ERR_FILE_CANT_WRITE
	if downloader.is_valid():
		downloader.call(png, filename, "image/png")
	else:
		JavaScriptBridge.download_buffer(png, filename, "image/png")
	return OK
