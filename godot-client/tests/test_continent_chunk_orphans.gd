extends SceneTree

## A live chunk import worker is never joined on the main thread. Joining it
## while it waits for rendering-server commands that only this thread services
## froze the client (no frames, no heartbeats) on a server teleport during a
## neighbour load. Owners that leave the tree or re-prime orphan the worker; the
## exterior stream reaps it once it reports finished.
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func _slow_worker() -> Variant:
	OS.delay_msec(700)
	return null

func _pending(identity: String) -> Dictionary:
	return {"id": identity, "bounds": {"min": [-10, 0, -10], "max": [10, 1, 10]}, "estimatedResidentBytes": 1}

func _run() -> void:
	await process_frame
	_expect(ContinentChunkStream.orphans_pending() == 0, "no orphan workers before the test")
	# 1. Freeing a stream root while its import is live must not block.
	var stream := ContinentChunkStream.new()
	root.add_child(stream)
	stream._pending = _pending("live-exit")
	stream._thread = Thread.new()
	_expect(stream._thread.start(_slow_worker) == OK, "live worker started")
	var began := Time.get_ticks_msec()
	stream.free()
	var elapsed := Time.get_ticks_msec() - began
	_expect(elapsed < 300, "freeing a root with a live worker returns without joining it (%d ms)" % elapsed)
	_expect(ContinentChunkStream.orphans_pending() == 1, "the live worker is orphaned, not joined")
	# 2. Re-priming an arrival while an import is live orphans it as well.
	var second := ContinentChunkStream.new()
	root.add_child(second)
	second._pending = _pending("live-arrival")
	second._thread = Thread.new()
	_expect(second._thread.start(_slow_worker) == OK, "second live worker started")
	began = Time.get_ticks_msec()
	second._release_worker(Vector3.ZERO, true)
	_expect(Time.get_ticks_msec() - began < 300 and second._thread == null and second._pending.is_empty(),
		"arrival release does not wait on a live worker and clears its pending entry")
	_expect(ContinentChunkStream.orphans_pending() == 2, "both live workers are orphaned")
	# 3. Orphans are reaped only once finished, while frames keep running.
	var deadline := Time.get_ticks_msec() + 4000
	var frames := 0
	while ContinentChunkStream.reap_orphans() > 0 and Time.get_ticks_msec() < deadline:
		frames += 1
		await process_frame
	_expect(ContinentChunkStream.orphans_pending() == 0, "finished workers are reaped after %d frames" % frames)
	_expect(frames > 1, "reaping waited across frames instead of blocking")
	# 4. A finished worker is joined normally on release.
	var third := ContinentChunkStream.new()
	root.add_child(third)
	third._pending = _pending("finished")
	third._thread = Thread.new()
	_expect(third._thread.start(func() -> Variant: return null) == OK, "finished worker started")
	while third._thread.is_alive():
		await process_frame
	third._release_worker(Vector3.ZERO, true)
	_expect(third._thread == null and ContinentChunkStream.orphans_pending() == 0, "a finished worker is joined without orphaning")
	# 5. A script that quits the tree itself drains first: a stream's live
	# worker and an orphan both finish across frames, and the stream is paused
	# so it requests nothing more. Quitting under either crashed the process.
	var fourth := ContinentChunkStream.new()
	root.add_child(fourth)
	fourth._pending = _pending("live-at-quit")
	fourth._thread = Thread.new()
	_expect(fourth._thread.start(_slow_worker) == OK, "worker live at quit started")
	var fifth := ContinentChunkStream.new()
	root.add_child(fifth)
	fifth._pending = _pending("orphaned-at-quit")
	fifth._thread = Thread.new()
	_expect(fifth._thread.start(_slow_worker) == OK, "worker orphaned at quit started")
	fifth.free()
	var frames_before := Engine.get_process_frames()
	var drained: bool = await ContinentChunkStream.drain_workers(self, 4000)
	_expect(drained and fourth._thread == null and ContinentChunkStream.orphans_pending() == 0,
		"draining leaves no live worker and no orphan behind")
	_expect(fourth._paused, "a drained stream is paused")
	_expect(Engine.get_process_frames() - frames_before > 1, "draining waited across frames instead of joining")
	fourth.free()
	third.free()
	second.free()
	print("orphan worker test: %d failures" % failures)
	quit(1 if failures > 0 else 0)
