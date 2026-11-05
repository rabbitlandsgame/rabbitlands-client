extends RefCounted
const Release = preload("res://src/updates/release.gd")
const Packages = preload("res://src/updates/package_updates.gd")
# A part is fetched at most 1 + RETRY_WAITS_SEC.size() times: at once, then
# after each wait. Retries cover a failed connection or transfer, replies an
# edge or server may lift (403 challenge pages, 408, 429, 5xx) and one hash
# mismatch. A 404 or 410 ends at once. A retry always starts from an empty
# file, from the same signed row: no other host and never unverified bytes.
const RETRY_WAITS_SEC: Array[float] = [5.0, 30.0]
const RETRY_STATUSES := [403, 408, 429]
const MISSING_STATUSES := [404, 410]
const MISSING_ERROR := "The update files are not available yet. Try again later."
const VERIFICATION_ERROR := "A downloaded package failed verification."
const CANCELLED_ERROR := "Update cancelled."
# How often a retry wait checks for cancellation.
const WAIT_SLICE_SEC := 0.25

static func prepare(root: String, release: Dictionary, fetch: Callable, worker: Callable, progress := Callable(), cancelled := Callable(), prepared_plan: Dictionary = {}, retry_waits: Array = RETRY_WAITS_SEC) -> String:
	prepared_plan.clear()
	var cache := Release.cache_for(root)
	if Release.is_link(cache) or Release.is_link(cache.path_join("packages")) or DirAccess.make_dir_recursive_absolute(cache.path_join("packages")) != OK:
		return "The package cache is not writable."
	var checked: Variant = await worker.call(func() -> Packages.CheckedPlan: return Packages.inspect(root, release, progress))
	if not checked is Packages.CheckedPlan:
		return "The package verification could not start."
	var needed: Array = checked.needed
	var total := 0
	var completed := 0
	for package: Dictionary in needed:
		if Release.is_link(Packages.package_path(cache, package)) or Release.is_link(Packages.package_path(cache, package) + ".tmp"):
			return "The package cache files must not be links."
		total += int(package.size)
	for package: Dictionary in needed:
		if _cancelled(cancelled):
			return CANCELLED_ERROR
		var ready: Variant = await worker.call(func() -> bool: return Release.check_file(Packages.package_path(cache, package), int(package.size), package.sha256))
		if ready != true:
			for part: Dictionary in package.parts:
				Release.report_progress(progress, "Downloading changed packages", completed, total, package.id)
				var path := cache.path_join("packages/" + part.sha256 + ".part")
				if Release.is_link(path) or Release.is_link(path + ".tmp"):
					return "The package cache files must not be links."
				# A verified part is kept until its package is assembled, so a
				# rerun after any failure resumes at part granularity.
				var valid: Variant = await worker.call(func() -> bool: return Release.check_file(path, int(part.size), part.sha256))
				if valid != true:
					var error: String = await download_part(part, path, fetch, worker, cancelled, retry_waits,
						func(seconds: float) -> void:
							Release.report_progress(progress, "Downloading changed packages", completed, total, "%s (retrying in %d s)" % [package.id, ceili(seconds)]))
					if error != "":
						return error
				completed += int(part.size)
			var error: String = await worker.call(func() -> String: return Packages.assemble(cache, package))
			if error != "":
				return error
		else:
			completed += int(package.size)
	Release.report_progress(progress, "Changed packages ready", 1, 1, "%d of %d packages needed downloads" % [needed.size(), release.packages.size()])
	prepared_plan["checked"] = checked
	return ""

static func download_part(part: Dictionary, path: String, fetch: Callable, worker: Callable, cancelled := Callable(), retry_waits: Array = RETRY_WAITS_SEC, waiting := Callable()) -> String:
	# Fetches one signed part into path + ".tmp", checks its size and SHA-256,
	# then renames it to path. Returns "" or the error that ended the attempts.
	# waiting(seconds) is told about each retry wait before it starts.
	var temporary := path + ".tmp"
	var problem := ""
	var mismatches := 0
	for attempt in retry_waits.size() + 1:
		if attempt > 0:
			var seconds := float(retry_waits[attempt - 1])
			if waiting.is_valid():
				waiting.call(seconds)
			if not await wait(seconds, cancelled):
				return CANCELLED_ERROR
		# A partial or rejected file never seeds the next attempt.
		DirAccess.remove_absolute(temporary)
		var result: Dictionary = await fetch.call(part.url, temporary, int(part.size))
		if _cancelled(cancelled):
			DirAccess.remove_absolute(temporary)
			return CANCELLED_ERROR
		if result.has("error"):
			problem = MISSING_ERROR if missing(result) else str(result.error)
			if not retryable(result):
				DirAccess.remove_absolute(temporary)
				return problem
		else:
			var valid: Variant = await worker.call(func() -> bool: return Release.check_file(temporary, int(part.size), part.sha256))
			if valid == true:
				if DirAccess.rename_absolute(temporary, path) == OK:
					return ""
				DirAccess.remove_absolute(temporary)
				return "The verified package download could not be recorded."
			mismatches += 1
			problem = VERIFICATION_ERROR
			if mismatches > 1:
				DirAccess.remove_absolute(temporary)
				return problem
		DirAccess.remove_absolute(temporary)
	return problem

static func missing(result: Dictionary) -> bool:
	# The host answered that the file does not exist (yet): retrying cannot help.
	return int(result.get("status", 0)) in MISSING_STATUSES

static func retryable(result: Dictionary) -> bool:
	# Only a network attempt is retried; a result without a status (a request
	# that could not start, or the setup's local copy that failed) is final.
	# Status 0 is no reply at all; 200 with a failed result is a transfer cut
	# short, too slow or longer than signed.
	if not result.has("status") or missing(result):
		return false
	# A file that cannot be written here is not the network's fault.
	if int(result.get("result", -1)) in [HTTPRequest.RESULT_DOWNLOAD_FILE_CANT_OPEN, HTTPRequest.RESULT_DOWNLOAD_FILE_WRITE_ERROR]:
		return false
	var status := int(result.status)
	return status in [0, 200] or status in RETRY_STATUSES or status >= 500

static func wait(seconds: float, cancelled := Callable()) -> bool:
	# Waits on the scene tree's timers, in slices, so a cancellation is seen
	# within WAIT_SLICE_SEC. Returns false when cancelled.
	var tree := Engine.get_main_loop() as SceneTree
	var deadline := Time.get_ticks_msec() + int(seconds * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if _cancelled(cancelled):
			return false
		var left := (deadline - Time.get_ticks_msec()) / 1000.0
		if tree == null:
			OS.delay_msec(int(minf(left, WAIT_SLICE_SEC) * 1000.0))
		else:
			await tree.create_timer(minf(left, WAIT_SLICE_SEC)).timeout
	return not _cancelled(cancelled)

static func _cancelled(cancelled: Callable) -> bool:
	return cancelled.is_valid() and cancelled.call() == true
