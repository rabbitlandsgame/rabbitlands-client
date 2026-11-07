extends SceneTree
const Preparation := preload("res://src/actors/browser_actor_preparation.gd")
var failures := 0

class Backend extends RefCounted:
	var cached: Dictionary = {}
	var calls: Array[Dictionary] = []
	var rejected: Dictionary = {}
	func canonical(path: String) -> String: return path.replace("/./", "/")
	func missing(paths: PackedStringArray) -> PackedStringArray:
		var result := PackedStringArray()
		for path: String in paths:
			if not cached.has(path): result.append(path)
		return result
	func prepare(path: String, names: PackedStringArray, pieces: bool) -> bool:
		calls.append({"path": path, "names": names, "pieces": pieces,
			"main": OS.get_thread_caller_id() == OS.get_main_thread_id()})
		if rejected.has(path): return false
		cached[path] = true
		return true
	func callbacks() -> Dictionary:
		return {"canonical": canonical, "missing": missing, "prepare": prepare}

func _initialize() -> void: _run.call_deferred()

func expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func closure(paths: Array, pieces: Array = [], rl: Array = []) -> Dictionary:
	return {"scenes": PackedStringArray(paths), "pieces": PackedStringArray(pieces),
		"rl_files": PackedStringArray(rl)}

func _run() -> void:
	var backend := Backend.new()
	var queue := Preparation.new(backend.callbacks())
	expect(not queue.request(closure(["a", "b"], ["a"]), 2, 10), "cold closure waits")
	expect(backend.calls.is_empty(), "request never parses inside a packet/readiness handler")
	expect(not queue.request(closure(["c"]), 0, 20), "urgent closure queues")
	queue.advance(1)
	expect(backend.calls.size() == 1 and backend.calls[0].path == "c", "local priority precedes earlier remote work")
	expect(queue.take_ready() == [20], "completion notifies the actual owner")
	queue.advance(1)
	expect(backend.calls.size() == 1, "multiple readiness/poll calls cannot prepare twice in one frame")
	queue.advance(2)
	expect(backend.calls.size() == 2 and backend.calls[1].path == "a" and backend.calls[1].pieces,
		"equal priorities retain source order and equipment extraction flag")
	expect(queue.take_ready().is_empty(), "multi-file closure stays pending until every file is ready")
	queue.advance(3)
	expect(backend.calls.size() == 3 and backend.calls[2].path == "b", "next file runs in the next frame")
	expect(queue.take_ready() == [10], "final file makes the waiting outfit eligible without another server packet")
	expect(queue.request(closure(["a", "b"]), 2, 10), "cached files are ready without another preparation")
	expect(int(queue.snapshot().preparedFiles) == 3 and int(queue.snapshot().pendingFiles) == 0,
		"preparation counters count physical files")
	for call: Dictionary in backend.calls: expect(bool(call.main), "all preparation is on main")

	# Shared jobs survive until their final source owner is cancelled. An outfit
	# change must not leave its obsolete work queued behind a newly requested one.
	backend = Backend.new()
	queue = Preparation.new(backend.callbacks())
	queue.request(closure(["shared", "old"]), 4, 1)
	queue.request(closure(["shared"]), 3, 2)
	queue.request(closure(["shared", "new"]), 0, 1)
	expect(int(queue.snapshot().pendingFiles) == 2 and int(queue.snapshot().cancelled) == 1,
		"superseded unshared source is cancelled; common source is deduplicated")
	expect(int(queue.snapshot().priorityRaises) == 1, "a queued source can be promoted to local priority")
	queue.cancel(1)
	queue.advance(10)
	expect(backend.calls.size() == 1 and backend.calls[0].path == "shared",
		"cancelling one owner preserves the source needed by another")
	expect(queue.take_ready() == [2], "cancelled owners cannot receive stale completions")
	queue.request(closure(["parked"]), 1, 3)
	queue.prune({}, [3])
	expect(int(queue.snapshot().pendingFiles) == 1, "parked/held body keeps its admitted source preparation")
	queue.prune({})
	queue.advance(11)
	expect(backend.calls.size() == 1 and int(queue.snapshot().pendingFiles) == 0,
		"pruning the final body cancels work before its download pins are released")

	# Failures use the normal build fallback without a retry every frame;
	# retirement invalidation allows a newly downloaded file to be tried again.
	backend = Backend.new()
	backend.rejected["bad"] = true
	queue = Preparation.new(backend.callbacks())
	queue.request(closure(["bad"]), 0, 5)
	queue.advance(20)
	expect(queue.request(closure(["bad"]), 0, 5), "failed preparation cannot strand an arrival")
	queue.advance(21)
	expect(backend.calls.size() == 1 and int(queue.snapshot().failures) == 1, "failed source is not repeatedly reparsed")
	queue.invalidate_sources(PackedStringArray(["bad"]))
	backend.rejected.clear()
	expect(not queue.request(closure(["bad"]), 0, 5), "redownload after invalidation admits a fresh preparation")
	queue.advance(22)
	expect(backend.calls.size() == 2 and queue.take_ready() == [5], "replacement source can complete after failure")
	backend.cached.erase("bad")
	expect(not queue.request(closure(["bad"]), 0, 5), "evicted scene becomes cold and is queued again")
	queue.invalidate_sources(PackedStringArray(["bad"]))
	queue.advance(23)
	expect(backend.calls.size() == 2, "retired pending raw files are never parsed")

	# RL head files join the same bounded queue; cached parallel publication
	# and session clears cannot manufacture more than one parse in a frame.
	backend = Backend.new()
	queue = Preparation.new(backend.callbacks())
	queue.request(closure(["body"], [], ["rl_head"]), 0, 7)
	backend.cached["body"] = true
	queue.advance(30)
	expect(backend.calls.size() == 1 and backend.calls[0].path == "rl_head",
		"already-published scenes are skipped and RL files share the preparation budget")
	expect(int(queue.snapshot().alreadyCached) == 1, "external cache publication is measured")
	queue.clear()
	queue.request(closure(["after_clear"]), 0, 8)
	queue.advance(30)
	expect(backend.calls.size() == 1, "session clear cannot reset the per-frame limit")
	queue.advance(31)
	expect(backend.calls.size() == 2 and queue.take_ready() == [8], "new session progresses in its next frame")
	expect(queue.take_ready().is_empty(), "readiness notifications are consumed once")
	queue.request(closure(["externally_cached"]), 0, 9)
	backend.cached["externally_cached"] = true
	queue.advance(32)
	expect(backend.calls.size() == 2 and queue.take_ready() == [9],
		"parallel cache publication notifies a stationary outfit without parsing again")
	expect(int(queue.snapshot().filesPerFrame) == 1 and int(queue.snapshot().prepareUsec) >= 0,
		"diagnostics expose the bounded work and measured preparation time")
	backend = Backend.new()
	queue = Preparation.new(backend.callbacks())
	queue.request(closure(["folder/item", "folder/./item"], ["folder/item"]), 0, 1)
	queue.advance(40)
	expect(backend.calls.size() == 1 and backend.calls[0].names.size() == 2 and backend.calls[0].pieces,
		"canonical source deduplication preserves every equipment alias and its extraction request")
	print("browser actor preparation: ", failures, " failures")
	quit(failures)
