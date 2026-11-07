extends RefCounted
## Main-thread browser preparation. Requests only queue work; advance() prepares
## at most one missing file in a rendered frame. No worker or live join exists.
## BrowserActorAssets owns the downloaded source pins until Main cancels/prunes
## the corresponding actor here, before releasing those pins.
var _backend: Dictionary
var _jobs: Dictionary = {}
var _owners: Dictionary = {}
var _fallback: Dictionary = {}
var _waiting: Dictionary = {}
var _ready: Dictionary = {}
var _sequence := 0
var _last_frame := -1
var _unclaimed_usec := 0
var _stats := {"enabled": true, "queuedFiles": 0, "preparedFiles": 0,
	"alreadyCached": 0, "failures": 0, "cancelled": 0, "priorityRaises": 0,
	"requests": 0, "waits": 0, "prepareUsec": 0, "lastPrepareUsec": 0,
	"maximumPrepareUsec": 0}

func _init(backend: Dictionary) -> void:
	_backend = backend

## All source files must already have been admitted and pinned by the browser
## download service. Replacing an owner's closure cancels its obsolete jobs.
func request(closure: Dictionary, priority: int, owner: int) -> bool:
	_stats.requests += 1
	_ready.erase(owner)
	var wanted := {}
	var pieces: PackedStringArray = closure.get("pieces", PackedStringArray())
	var names: PackedStringArray = closure.get("scenes", PackedStringArray()).duplicate()
	names.append_array(closure.get("rl_files", PackedStringArray()))
	for name: String in names:
		var path := str((_backend.canonical as Callable).call(name))
		if path.is_empty(): continue
		if not wanted.has(path): wanted[path] = {}
		wanted[path][name] = pieces.has(name)
	_replace_owner(owner, wanted)
	var ready := true
	for path: String in wanted:
		if _missing(path).is_empty() or _fallback.has(path):
			continue
		ready = false
		if not _jobs.has(path):
			_sequence += 1
			_jobs[path] = {"path": path, "owners": {}, "names": {}, "pieces": false, "seq": _sequence}
			_stats.queuedFiles += 1
		var job: Dictionary = _jobs[path]
		if (job.owners as Dictionary).has(owner) and priority < int(job.owners[owner]):
			_stats.priorityRaises += 1
		job.owners[owner] = priority
		for name: String in (wanted[path] as Dictionary):
			job.names[name] = true
			job.pieces = bool(job.pieces) or bool(wanted[path][name])
	if not ready:
		_stats.waits += 1
		_waiting[owner] = true
	else:
		_waiting.erase(owner)
	return ready

func _missing(path: String) -> PackedStringArray:
	return (_backend.missing as Callable).call(PackedStringArray([path])) as PackedStringArray

func _replace_owner(owner: int, wanted: Dictionary) -> void:
	for path: String in (_owners.get(owner, {}) as Dictionary):
		if wanted.has(path) or not _jobs.has(path): continue
		var job: Dictionary = _jobs[path]
		(job.owners as Dictionary).erase(owner)
		if (job.owners as Dictionary).is_empty():
			_jobs.erase(path)
			_stats.cancelled += 1
	_owners[owner] = wanted

## Main calls once per process frame, outside packet/state handlers. Repeated
## calls in that frame cannot begin another parse, including after a clear.
func advance(frame := -1) -> void:
	var current := Engine.get_process_frames() if frame < 0 else frame
	if _last_frame == current or _jobs.is_empty(): return
	var chosen := ""
	var best_priority := 2147483647
	var best_sequence := 2147483647
	for path: String in _jobs.keys():
		if _missing(path).is_empty():
			var cached_job: Dictionary = _jobs[path]
			_jobs.erase(path)
			_stats.alreadyCached += 1
			_notify_ready(cached_job.owners)
			continue
		var job: Dictionary = _jobs[path]
		var priority := 2147483647
		for rank: int in (job.owners as Dictionary).values(): priority = mini(priority, rank)
		if priority < best_priority or (priority == best_priority and int(job.seq) < best_sequence):
			chosen = path
			best_priority = priority
			best_sequence = int(job.seq)
	if chosen.is_empty(): return
	_last_frame = current
	var selected: Dictionary = _jobs[chosen]
	_jobs.erase(chosen)
	var started := Time.get_ticks_usec()
	var names := PackedStringArray((selected.names as Dictionary).keys())
	var prepared := bool((_backend.prepare as Callable).call(chosen, names, bool(selected.pieces)))
	var elapsed := Time.get_ticks_usec() - started
	_unclaimed_usec += elapsed
	_stats.prepareUsec += elapsed
	_stats.lastPrepareUsec = elapsed
	_stats.maximumPrepareUsec = maxi(int(_stats.maximumPrepareUsec), elapsed)
	if prepared:
		_stats.preparedFiles += 1
	else:
		# As with the desktop preparer, a failed file falls back to the ordinary
		# build rather than keeping a body hidden indefinitely.
		_fallback[chosen] = true
		_stats.failures += 1
	_notify_ready(selected.owners)

func _notify_ready(owners: Dictionary) -> void:
	for owner: int in owners:
		if not _waiting.has(owner): continue
		var complete := true
		for path: String in (_owners.get(owner, {}) as Dictionary):
			if not _missing(path).is_empty() and not _fallback.has(path):
				complete = false
				break
		if complete:
			_waiting.erase(owner)
			_ready[owner] = true

func take_ready() -> Array[int]:
	var ready: Array[int] = []
	ready.assign(_ready.keys())
	_ready.clear()
	return ready

func take_usec() -> int:
	var elapsed := _unclaimed_usec
	_unclaimed_usec = 0
	return elapsed

func prune(live: Dictionary, kept: Array = []) -> void:
	for owner: int in _owners.keys():
		if live.has(owner) or kept.has(owner): continue
		cancel(owner)

func cancel(owner: int) -> void:
	_replace_owner(owner, {})
	_owners.erase(owner)
	_waiting.erase(owner)
	_ready.erase(owner)

func invalidate_sources(paths: PackedStringArray) -> void:
	for name: String in paths:
		var path := str((_backend.canonical as Callable).call(name))
		if _jobs.erase(path): _stats.cancelled += 1
		_fallback.erase(path)

func clear() -> void:
	_stats.cancelled += _jobs.size()
	_jobs.clear()
	_owners.clear()
	_fallback.clear()
	_waiting.clear()
	_ready.clear()
	_unclaimed_usec = 0

func snapshot() -> Dictionary:
	return _stats.merged({"pendingFiles": _jobs.size(), "owners": _owners.size(),
		"fallbackFiles": _fallback.size(), "filesPerFrame": 1})
