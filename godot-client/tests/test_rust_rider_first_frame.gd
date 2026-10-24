extends "res://tests/test_rust_rider_batch_lifecycle.gd"
## No pre-added Batch: the actual production Shim.configure must create it.
const Shim := preload("res://src/mounts/rust_rider_pose.gd")

class FixtureLegacy extends RefCounted:
	var actor: Node3D
	var visual_root: Node3D
	var profile: Dictionary = {}

class FixtureController extends RefCounted:
	var generation := 0
	func wants_rust_pose() -> bool: return true
	func is_compare_mode() -> bool: return false
	func allocate_instance_generation() -> int:
		generation += 1
		return generation

func run() -> void:
	Shim.close_batches()
	await physics_frame
	await process_frame
	await process_frame
	expect(Shim.shared_batch_if_present() == null, "first-creation probe starts without a shared batch")
	var actor := Node3D.new()
	root.add_child(actor)
	var visual := Node3D.new()
	actor.add_child(visual)
	var legacy := FixtureLegacy.new()
	legacy.actor = actor
	legacy.visual_root = visual
	var native := FakeNative.new()
	var controller := FixtureController.new()
	var shim := Shim.new()
	shim.configure(legacy, "moor_pony", controller, native, "rust")
	var batch := Shim.shared_batch_if_present()
	if batch == null:
		expect(false, "actual Rust configure prewarms the initially absent late batch")
		actor.queue_free()
		await process_frame
		quit(1)
		return
	var pose := _pose(native, 91)
	var producer := Producer.new()
	producer.batch = batch
	producer.poses = [pose]
	root.add_child(producer)
	var observer := Observer.new()
	observer.poses = [pose]
	root.add_child(observer)
	await process_frame
	await process_frame
	expect(observer.observed and observer.same_frame, "first-ever configured native mounted preparation finishes in its first producer frame")
	expect(native.calls == 1 and pose.applications == 1, "first creation neither drops nor duplicates the initial native batch")
	producer.queue_free()
	observer.queue_free()
	shim.close()
	Shim.close_batches()
	actor.queue_free()
	await physics_frame
	await process_frame
	await process_frame
	# Legacy configure must preserve the ordinary no-coordinator/no-DLL path.
	actor = Node3D.new()
	root.add_child(actor)
	visual = Node3D.new()
	actor.add_child(visual)
	legacy.actor = actor
	legacy.visual_root = visual
	shim.configure(legacy, "moor_pony", null, null, "legacy")
	expect(Shim.shared_batch_if_present() == null, "legacy configure creates no optional batch")
	shim.close()
	actor.queue_free()
	await physics_frame
	await process_frame
	await process_frame
	print("RUST_RIDER_FIRST_FRAME_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
