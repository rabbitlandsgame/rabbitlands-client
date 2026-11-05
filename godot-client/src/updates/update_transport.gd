extends Node
const Release = preload("res://src/updates/release.gd")
# HTTPRequest's download thread reads one chunk, then sleeps until the next
# timer tick: 15.6 ms at Windows' default timer resolution, about 2 ms when a
# finer one is in effect. The 64 KiB default capped package downloads at 4.2
# (or about 30) MB/s; 1 MiB lifts that to about 66 (or 250) MB/s. Cancelling
# waits for the chunk being read: up to about 1 s on an 8 Mbit/s connection,
# about 8 s on a 1 Mbit/s one.
const DOWNLOAD_CHUNK_BYTES := 1024 * 1024
var _request: HTTPRequest
var _thread: Thread
# Set only while fetch_pointer runs (fetch keeps its signature: fixtures
# override it to redirect requests, and fetch_pointer goes through them).
var _pointer_timeout := 0.0

# The signed R2 pointer (Release.fetch_pointer): small, and read before the
# GitHub alias, so a slow, blocked or challenged R2 delays discovery by at
# most Release.POINTER_TIMEOUT_SEC.
func fetch_pointer(url: String) -> Dictionary:
	_pointer_timeout = Release.POINTER_TIMEOUT_SEC
	var fetched: Dictionary = await fetch(url, "", Release.MAX_POINTER_BYTES)
	_pointer_timeout = 0.0
	return fetched

# A failed request returns {"error", "status", "result"}: the HTTP status (0
# without a reply) and the HTTPRequest result, which package downloads read to
# decide on a retry (package_download.gd). A request that could not start made
# no network attempt and returns only "error", which is never retried.
func fetch(url: String, path := "", limit := Release.MAX_MANIFEST_BYTES) -> Dictionary:
	_request = _new_http_request()
	_request.use_threads = true
	_request.accept_gzip = false
	_request.timeout = 3600.0 if path != "" else (_pointer_timeout if _pointer_timeout > 0.0 else 30.0)
	_request.body_size_limit = limit
	_request.download_file = path
	if path != "":
		# File downloads only; manifests and API replies keep the default.
		_request.download_chunk_size = DOWNLOAD_CHUNK_BYTES
	add_child(_request)
	var accept := "application/vnd.github+json" if url.begins_with("https://api.github.com/") else "application/octet-stream"
	var error := _request.request(url, ["Accept: " + accept, "Cache-Control: no-cache", "User-Agent: RabbitLands-Client"])
	if error != OK:
		_request.queue_free()
		_request = null
		return {"error": "The update download could not start."}
	var response: Array = await _request.request_completed
	_request.queue_free()
	_request = null
	if response[0] != HTTPRequest.RESULT_SUCCESS or response[1] != 200:
		return {"error": "The update download failed. Check the internet connection and try again.",
			"status": int(response[1]), "result": int(response[0])}
	return {"body": response[3]}

# Every request starts here with the system's certificate checks. Only test
# fixtures override it, to trust their local server's certificate.
func _new_http_request() -> HTTPRequest:
	return HTTPRequest.new()

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
