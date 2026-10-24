extends SceneTree
## Exercise the real late-priority Node; fake numeric backend avoids model startup.
const Batch := preload("res://src/mounts/rust_rider_pose_batch.gd")
var checks := 0
var failures := 0

class FakeNative extends RefCounted:
	var calls := 0
	var reject := false
	var last := PackedInt64Array()
	func solve_mounted_batch(records: PackedInt64Array, _samples: PackedFloat64Array, _epoch: int, apply: bool) -> bool:
		calls += 1
		last = records.duplicate()
		return apply and not reject

class FakePose extends RefCounted:
	var _native
	var _epoch := 1
	var _frame := 1
	var id := 1
	var generation := 1
	var map_frame := 1
	var alive := true
	var applications := 0
	var fallback := 0
	var finished := 0
	var prepared_at := -1
	var finished_at := -2
	func still_valid(epoch: int) -> bool: return alive and epoch == _epoch
	func frame_identity() -> Array: return [id, generation, map_frame]
	func matches_frame_identity(identity: Array) -> bool: return identity == frame_identity()
	func record(_gait: String) -> PackedInt64Array: return PackedInt64Array([id, generation, id + 10, 0, _frame])
	func sample(_seat: Transform3D, _seconds: float, _cycle: float) -> PackedFloat64Array:
		return PackedFloat64Array([1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,0.,1.])
	func fallback_fit(_seat: Transform3D, _gait: String, _seconds: float, _cycle: float) -> void:
		fallback += 1
	func finish() -> void:
		finished += 1
		finished_at = Engine.get_process_frames()

class Producer extends Node:
	var batch
	var poses: Array = []
	func _process(_delta: float) -> void:
		for pose: FakePose in poses:
			pose.prepared_at = Engine.get_process_frames()
			batch.submit(pose, Transform3D.IDENTITY, "idle", 0., 1., pose.finish)
		set_process(false)

class Observer extends Node:
	var poses: Array = []
	var observed := false
	var same_frame := true
	func _init() -> void: process_priority = 2000000
	func _process(_delta: float) -> void:
		for pose: FakePose in poses:
			same_frame = same_frame and pose.finished == 1 and pose.prepared_at == pose.finished_at and pose.finished_at == Engine.get_process_frames()
		observed = true
		set_process(false)

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func _pose(native: RefCounted, id: int) -> FakePose:
	var pose := FakePose.new()
	pose._native = native
	pose.id = id
	return pose

func run() -> void:
	var native := FakeNative.new()
	var batch := Batch.new()
	root.add_child(batch)
	var a := _pose(native, 1)
	var b := _pose(native, 2)
	var producer := Producer.new()
	producer.batch = batch
	producer.poses = [a, b]
	root.add_child(producer)
	var observer := Observer.new()
	observer.poses = [a, b]
	root.add_child(observer)
	await process_frame
	await process_frame
	expect(observer.observed and observer.same_frame, "real process-priority flush finishes both riders in their preparation frame")
	expect(native.calls == 1 and native.last.size() == 10 and a.applications == 1 and b.applications == 1, "real coordinator uses one native batch for both riders")
	producer.queue_free()
	observer.queue_free()
	# Simulate an actual reset, park/dismount, or replacement invalidating pending work.
	var c := _pose(native, 3)
	batch.submit(c, Transform3D.IDENTITY, "idle", 0., 1., c.finish)
	c._epoch += 1
	batch.flush()
	expect(native.calls == 1 and c.finished == 0, "pending old-epoch row cannot submit or finish")
	var rebased := _pose(native, 30)
	batch.submit(rebased, Transform3D.IDENTITY, "idle", 0., 1., rebased.finish)
	rebased.map_frame += 1
	batch.flush()
	expect(native.calls == 1 and rebased.finished == 0, "same-session continuous map/rebase identity rejects the prepared old-frame seat")
	var old := _pose(native, 4)
	batch.submit(old, Transform3D.IDENTITY, "idle", 0., 1., old.finish)
	old.alive = false
	var replacement := _pose(native, 4)
	replacement.generation = 2
	batch.submit(replacement, Transform3D.IDENTITY, "idle", 0., 1., replacement.finish)
	batch.flush()
	expect(old.finished == 0 and replacement.finished == 1 and native.last.size() == 5 and native.last[1] == 2, "same actor ID replacement submits only the new generation")
	var abandoned := _pose(native, 5)
	# A Callable bound to this RefCounted fake would itself retain it; production
	# finish callbacks target the mount Node. Use an empty callback for this probe.
	batch.submit(abandoned, Transform3D.IDENTITY, "idle", 0., 1., Callable())
	abandoned = null
	var calls_before := native.calls
	batch.flush()
	expect(native.calls == calls_before, "weak pose membership does not keep an abandoned instance alive")
	native.reject = true
	a._frame += 1
	b._frame += 1
	batch.submit(a, Transform3D.IDENTITY, "idle", 0., 1., a.finish)
	batch.submit(b, Transform3D.IDENTITY, "idle", 0., 1., b.finish)
	batch.flush()
	expect(a.fallback == 1 and b.fallback == 1 and a.finished == 2 and b.finished == 2, "complete batch failure performs full legacy fit before both finish passes")
	var discarded := _pose(native, 6)
	batch.submit(discarded, Transform3D.IDENTITY, "idle", 0., 1., discarded.finish)
	batch.close()
	await physics_frame
	await process_frame
	await process_frame
	expect(discarded.finished == 0, "close discards queued work and releases owned batch Node")
	print("RUST_RIDER_BATCH_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
