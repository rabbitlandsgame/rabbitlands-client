extends Node
const Release = preload("res://src/updates/release.gd")
var _request: HTTPRequest
var _thread: Thread

func fetch(url: String, path := "", limit := Release.MAX_MANIFEST_BYTES) -> Dictionary:
	_request = HTTPRequest.new()
	_request.use_threads = true
	_request.accept_gzip = false
	_request.timeout = 3600.0 if path != "" else 30.0
	_request.body_size_limit = limit
	_request.download_file = path
	add_child(_request)
	var error := _request.request(url, ["Accept: application/octet-stream", "Cache-Control: no-cache"])
	if error != OK:
		_request.queue_free()
		_request = null
		return {"error": "The update download could not start."}
	var response: Array = await _request.request_completed
	_request.queue_free()
	_request = null
	if response[0] != HTTPRequest.RESULT_SUCCESS or response[1] != 200:
		return {"error": "The update download failed. Check the internet connection and try again."}
	return {"body": response[3]}

func worker(callable: Callable) -> Variant:
	_thread = Thread.new()
	if _thread.start(callable) != OK:
		_thread = null
		return "The update verification could not start."
	while _thread.is_alive():
		await get_tree().process_frame
	var result: Variant = _thread.wait_to_finish()
	_thread = null
	return result

func _exit_tree() -> void:
	if _request != null:
		_request.cancel_request()
	if _thread != null:
		_thread.wait_to_finish()
