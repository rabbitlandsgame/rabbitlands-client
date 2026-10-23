extends Node
const Release = preload("res://src/updates/release.gd")
const PackageDownload = preload("res://src/updates/package_download.gd")
const StartupUpdate = preload("res://src/updates/startup_update.gd")
var _startup: Node
var identity: Dictionary = {}
var _target := ""
var _generation := 0
var _request: HTTPRequest
var _worker: Thread
var _status: Label
var _completed_bytes := 0
var _total_bytes := 0
var _queued: Dictionary = {}
var _busy := false
var _latest_notice: Dictionary = {}
var _retry_at_msec := 0
var _retry_attempt := 0
var _last_error := ""
var _lease := ""

func _ready() -> void:
	if get_node("/root/Network").offline_hud_preview:
		set_process(false)
		return
	identity = Release.read_json("res://data/client_release.json")
	if identity.get("platform", "source") != "source" and Release.update_owner(identity) == "github":
		var cache := Release.cache_for(Release.install_root())
		if DirAccess.make_dir_recursive_absolute(cache) == OK:
			_lease = cache.path_join("running-%d.json" % OS.get_process_id())
			Release.save_json(_lease, {"pid": OS.get_process_id()})
	var layer := CanvasLayer.new()
	layer.layer = 100
	add_child(layer)
	_status = Label.new()
	_status.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	_status.position = Vector2(-500, 14)
	_status.size = Vector2(480, 56)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_status.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_status.add_theme_color_override("font_color", Color("ffd58c"))
	_status.add_theme_color_override("font_shadow_color", Color.BLACK)
	_status.add_theme_constant_override("shadow_offset_x", 2)
	_status.add_theme_constant_override("shadow_offset_y", 2)
	layer.add_child(_status)
	_startup = StartupUpdate.new()
	_startup.identity = identity
	_startup.notice_changed.connect(func(message: String) -> void:
		_status.text = message
		get_node("/root/AppState").call("append_local_message", message, 3))
	add_child(_startup)
	if identity.get("platform", "source") == "source" or identity.get("public_key", "") == "":
		set_process(false)
		return
	get_node("/root/Network").connect("packet_received", _on_packet)
	get_node("/root/Network").connect("connection_state_changed", func(state: String) -> void:
		if state == "connected" and not _busy:
			_target = "")
	if Release.update_owner(identity) != "github":
		set_process(false)
		return
	# Cached updates from older clients still require explicit consent. The
	# startup checker owns discovery; there is no background install decision.
	set_process(false)

func _process(_delta: float) -> void:
	if not _busy and not _latest_notice.is_empty() and _retry_at_msec > 0 and Time.get_ticks_msec() >= _retry_at_msec:
		_retry_at_msec = 0
		_generation += 1
		_queued = _latest_notice.duplicate()
		_queued.generation = _generation
		_drain_updates()
	if is_instance_valid(_request) and _total_bytes > 0 and _request.download_file != "":
		var percent := clampi(int(100.0 * (_completed_bytes + _request.get_downloaded_bytes()) / _total_bytes), 0, 100)
		_status.text = "Downloading game update: %d%%\nInstalls on the next launch." % percent

func _cancel_request() -> void:
	if is_instance_valid(_request):
		_request.cancel_request()
		# cancel_request does not emit completion. Wake our awaiting coroutine.
		_request.request_completed.emit(HTTPRequest.RESULT_REQUEST_FAILED, 0, PackedStringArray(), PackedByteArray())

func _on_packet(command: int, payload: PackedByteArray) -> void:
	if command != 206 or payload.size() > 4096:
		return
	var notice: Variant = JSON.parse_string(payload.get_string_from_utf8())
	if not notice is Dictionary or notice.get("schema") != 1:
		return
	if Release.update_owner(identity) != "github":
		# No pending-cache read/write, HTTP request, download, or install for
		# Steam and manually replaced bundles, including stale GitHub notices.
		if notice.get("disabled", false) == true:
			_status.text = ""
		elif Release.valid_commit(notice.get("required_commit")):
			_status.text = "" if Release.contains_commit(identity, notice.required_commit) else Release.external_update_message(identity)
		return
	if _startup != null:
		# Discovery and consent own this launch's update decision. In particular,
		# a server policy cannot clear a refusal or replace a custom build.
		if _startup.declined or (Release.valid_commit(notice.get("required_commit")) and not Release.contains_commit(identity, notice.required_commit)):
			_status.text = StartupUpdate.COMPATIBILITY_NOTE
		return
	if notice.get("disabled", false) == true:
		_generation += 1
		_target = ""
		_queued.clear()
		_latest_notice.clear()
		_retry_at_msec = 0
		_cancel_request()
		DirAccess.remove_absolute(Release.cache_for(Release.install_root()).path_join("pending.json"))
		_status.text = ""
		return
	if not Release.valid_commit(notice.get("required_commit")):
		return
	var commit: String = notice.required_commit
	if Release.contains_commit(identity, commit):
		_generation += 1
		_target = ""
		_queued.clear()
		_latest_notice.clear()
		_retry_at_msec = 0
		_cancel_request()
		DirAccess.remove_absolute(Release.cache_for(Release.install_root()).path_join("pending.json"))
		_status.text = ""
		return
	var prefix := "https://github.com/%s/releases/download/" % str(identity.get("repository", ""))
	var url: Variant = notice.get("manifest_url", "")
	if not url is String or not url.begins_with(prefix) or not Release.https_url(url):
		_status.text = "The server's update source is not configured for this installation."
		return
	if _target == commit:
		return
	_target = commit
	_generation += 1
	_latest_notice = {"url": url, "commit": commit}
	_retry_at_msec = 0
	_retry_attempt = 0
	_last_error = ""
	_queued = {"url": url, "commit": commit, "generation": _generation}
	_cancel_request()
	if not _busy:
		_drain_updates()

func _drain_updates() -> void:
	_busy = true
	while not _queued.is_empty():
		var next := _queued.duplicate()
		_queued.clear()
		await _download(next.url, next.commit, next.generation)
	_busy = false

func _fetch(url: String, path := "", limit := Release.MAX_MANIFEST_BYTES) -> Dictionary:
	var request := _new_http_request()
	request.use_threads = true
	request.accept_gzip = false
	request.body_size_limit = limit
	request.timeout = 3600.0 if path != "" else 60.0
	request.download_file = path
	add_child(request)
	_request = request
	var error := request.request(url, ["Accept: application/octet-stream", "Cache-Control: no-cache"])
	if error != OK:
		_request = null
		request.queue_free()
		return {"error": "The update download could not start."}
	var response: Array = await request.request_completed
	request.queue_free()
	_request = null
	if response[0] != HTTPRequest.RESULT_SUCCESS or response[1] != 200:
		return {"error": "The update download failed."}
	return {"body": response[3]}

func _new_http_request() -> HTTPRequest:
	return HTTPRequest.new()

func _run_worker(callable: Callable) -> Variant:
	_worker = Thread.new()
	if _worker.start(callable) != OK:
		_worker = null
		return "The update verification could not start."
	while _worker.is_alive():
		await get_tree().process_frame
	var result: Variant = _worker.wait_to_finish()
	_worker = null
	return result

func _download(url: String, commit: String, generation: int) -> void:
	if Release.update_owner(identity) != "github":
		return
	_status.text = "A game update is available. Checking release information…"
	var fetched := await _fetch(url)
	if generation != _generation:
		return
	if fetched.has("error"):
		_failed(fetched.error)
		return
	var parsed: Variant = JSON.parse_string(fetched.body.get_string_from_utf8())
	var envelope: Dictionary = parsed if parsed is Dictionary else {}
	var release := Release.verify_manifest(envelope, identity, commit)
	if release.has("error"):
		_failed(release.error)
		return
	var cache := Release.cache_for(Release.install_root())
	if DirAccess.make_dir_recursive_absolute(cache) != OK:
		_failed("The update cache is not writable.")
		return
	if release.schema == 2:
		var error: String = await PackageDownload.prepare(Release.install_root(), release, _fetch, _run_worker,
			func(phase: String, _done: int, _total: int, detail: String) -> void: _status.text = phase + " " + detail,
			func() -> bool: return generation != _generation)
		if generation != _generation:
			return
		if error != "" or Release.save_json(cache.path_join("pending.json"), envelope) != OK:
			_failed(error if error != "" else "The package readiness record could not be saved.")
			return
		_status.text = "Changed game packages downloaded. Close and restart Rabbit Lands to install."
		_retry_at_msec = 0
		_retry_attempt = 0
		return
	var pending := Release.verify_manifest(Release.read_json(cache.path_join("pending.json")), identity, commit)
	if not pending.has("error") and pending.sha256 == release.sha256:
		var ready: Variant = await _run_worker(func() -> bool: return Release.check_file(cache.path_join("release.zip"), int(release.size), release.sha256))
		if generation != _generation:
			return
		if ready == true:
			_status.text = "Game update downloaded. Close and restart Rabbit Lands to install."
			return
	DirAccess.remove_absolute(cache.path_join("pending.json"))
	_completed_bytes = 0
	_total_bytes = int(release.size)
	for index in release.parts.size():
		var part: Dictionary = release.parts[index]
		var path := cache.path_join("part-%04d" % index)
		var valid: Variant = await _run_worker(func() -> bool: return Release.check_file(path, int(part.size), part.sha256))
		if generation != _generation:
			return
		if valid != true:
			fetched = await _fetch(part.url, path + ".tmp", int(part.size))
			if generation != _generation:
				return
			if fetched.has("error"):
				_failed(fetched.error)
				return
			valid = await _run_worker(func() -> bool: return Release.check_file(path + ".tmp", int(part.size), part.sha256))
			if generation != _generation:
				return
			if valid != true or DirAccess.rename_absolute(path + ".tmp", path) != OK:
				_failed("The downloaded update failed verification.")
				return
		_completed_bytes += int(part.size)
	_total_bytes = 0
	_status.text = "Verifying downloaded game update…"
	var error: Variant = await _run_worker(func() -> String: return Release.assemble(cache, release))
	if generation != _generation:
		return
	if error != "" or Release.save_json(cache.path_join("pending.json"), envelope) != OK:
		_failed(str(error) if error != "" else "The update readiness record could not be saved.")
		return
	_status.text = "Game update downloaded. Close and restart Rabbit Lands to install."
	_retry_at_msec = 0
	_retry_attempt = 0
	get_node("/root/AppState").call("append_local_message", _status.text, 3)

func _failed(message: String) -> void:
	_total_bytes = 0
	var delay := mini(300, 30 * int(pow(2, mini(_retry_attempt, 4))))
	_retry_attempt += 1
	_retry_at_msec = Time.get_ticks_msec() + delay * 1000
	_status.text = message + " Retrying in %d seconds." % delay
	if message != _last_error:
		get_node("/root/AppState").call("append_local_message", _status.text, 3)
		_last_error = message

func _exit_tree() -> void:
	if is_instance_valid(_request):
		_request.cancel_request()
	if _worker != null:
		_worker.wait_to_finish()
	if _lease != "":
		DirAccess.remove_absolute(_lease)
