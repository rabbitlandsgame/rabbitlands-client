extends SceneTree
## Paired live-player pilot: actual rigs and Godot mount clips, complete pose comparison.
const Shim := preload("res://src/mounts/rust_rider_pose.gd")
const RuntimeController := preload("res://src/runtime/client_runtime.gd")
var checks := 0
var failures := 0
var _raw_angle_max := 0.0
var _normalized_angle_max := 0.0
var _models: Dictionary
var _controller: FixtureController

class FixtureController extends RefCounted:
	var epoch := 1
	var generation := 1
	var native
	func native_runtime() -> RefCounted: return native
	func current_epoch() -> int: return epoch
	func allocate_instance_generation() -> int:
		generation += 1
		return generation
	func wants_rust_pose() -> bool: return true
	func is_compare_mode() -> bool: return false

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func _actor(body: String, id: int, scale: float, changed_rest: bool) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var config: Dictionary = _models[body]
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var errors := actor.configure({"actor_id": id, "x": 120, "y": 70, "rotation": 0,
		"kind": 1, "name": "RustPoseFixture", "scale": scale,
		"appearance": {"skin": 0, "hair": 0, "eyes": 0, "shirt": 0, "pants": 0, "boots": 0, "head": 0},
		"equipment_visuals": {}}, CoordinateAdapter.new(), config, mapping)
	expect(errors.is_empty(), body + " real actor loads: " + str(errors))
	if not errors.is_empty():
		actor.queue_free()
		return null
	actor.rotation.y = 1.1
	actor.position += Vector3(11.0, 3.5, -17.0)
	actor.set_process(false)
	actor.set_physics_process(false)
	if changed_rest:
		# Instance-only synthetic rest perturbation proves FK does not add rest twice.
		var rig := actor.get_skeleton()
		var bone := rig.find_bone("spine_01")
		var rest := rig.get_bone_rest(bone)
		rest.basis = Basis(Vector3.RIGHT, 0.17) * rest.basis.scaled(Vector3(1.05, 0.95, 1.1))
		rig.set_bone_rest(bone, rest)
	actor.set_mount_state({"mode": "mounted", "mount_id": "moor_pony", "gait": "walk", "step_us": 200000}, _models)
	expect(is_instance_valid(actor.get("_mount_visual")), body + " real Moor Pony configures")
	if not is_instance_valid(actor.get("_mount_visual")):
		actor.queue_free()
		return null
	actor.get("_mount_visual").set_process(false)
	actor.set_cape_cloth_allowed(false)
	actor.play_action(&"run")
	actor._presentation_speed = 3.75
	return actor

func _compare(a: ReplicatedActor3D, b: ReplicatedActor3D, label: String) -> void:
	var sa := a.get_skeleton()
	var sb := b.get_skeleton()
	var position_error := 0.0
	var angle_error := 0.0
	var scale_error := 0.0
	for bone: int in sa.get_bone_count():
		position_error = maxf(position_error, sa.get_bone_pose_position(bone).distance_to(sb.get_bone_pose_position(bone)))
		var qa := sa.get_bone_pose_rotation(bone)
		var qb := sb.get_bone_pose_rotation(bone)
		_raw_angle_max = maxf(_raw_angle_max, qa.angle_to(qb))
		angle_error = maxf(angle_error, Shim.rotation_error(qa, qb))
		scale_error = maxf(scale_error, sa.get_bone_pose_scale(bone).distance_to(sb.get_bone_pose_scale(bone)))
	expect(position_error < 0.0001, label + " every local position parity: " + str(position_error))
	expect(angle_error < 0.001, label + " every local rotation parity: " + str(angle_error))
	_normalized_angle_max = maxf(_normalized_angle_max, angle_error)
	expect(scale_error < 0.0001, label + " every local scale parity: " + str(scale_error))
	var va := a.get_node("NativeModel") as Node3D
	var vb := b.get_node("NativeModel") as Node3D
	expect(va.global_position.distance_to(vb.global_position) < 0.0001, label + " visual world position parity")
	expect(va.global_basis.x.distance_to(vb.global_basis.x) < 0.0001 and va.global_basis.y.distance_to(vb.global_basis.y) < 0.0001 and va.global_basis.z.distance_to(vb.global_basis.z) < 0.0001, label + " visual world basis parity")
	expect(a.global_transform.is_equal_approx(b.global_transform), label + " authoritative root untouched")

func _pair(body: String, scale: float, changed_rest: bool) -> void:
	var actors: Array[ReplicatedActor3D] = []
	for index: int in 3:
		var actor := _actor(body, 700 + index, scale, changed_rest)
		if actor != null:
			actors.append(actor)
	if actors.size() != 3:
		await _retire(actors)
		return
	var original: Array[Transform3D] = []
	for actor: ReplicatedActor3D in actors:
		original.append(actor.global_transform)
	actors[0].get("_mount_visual").rust_pose.configure(actors[0].get("_mount_visual").pose, "moor_pony", null, null, "legacy")
	for index: int in [1, 2]:
		actors[index].get("_mount_visual").rust_pose.configure(actors[index].get("_mount_visual").pose, "moor_pony", _controller)
	for gait: String in ["walk", "cruise", "burst"]:
		for actor: ReplicatedActor3D in actors:
			actor.get("_mount_visual").state.gait = gait
		for frame: int in 30:
			if frame == 6:
				for actor: ReplicatedActor3D in actors:
					actor.play_action(&"cast_aggressive")
			if frame == 16:
				for actor: ReplicatedActor3D in actors:
					actor.play_action(&"run")
			var before: Dictionary = _controller.native.runtime_info()
			for actor: ReplicatedActor3D in actors:
				actor.get("_mount_visual")._step_visual(1.0 / 60.0)
			Shim.flush_pending()
			var after: Dictionary = _controller.native.runtime_info()
			expect(int(after.pose_calls) == int(before.pose_calls) + 1, "two riders cross native boundary in one batch")
			expect(int(after.poses_applied) == int(before.poses_applied) + 2, "both complete native rider poses applied")
			for index: int in [1, 2]:
				_compare(actors[0], actors[index], body + " " + gait + " " + str(frame))
				var contacts: PackedFloat64Array = actors[index].get("_mount_visual").rust_pose.contact_errors()
				expect(contacts.size() == 5, "native solver exposes all five actual pre-upper-body contacts")
				for distance: float in contacts:
					expect(distance < 0.06, "native seat/hand/foot contact remains below legacy six-centimetre bound: " + str(distance))
			for index: int in 3:
				expect(actors[index].global_transform.is_equal_approx(original[index]), "server root and picking frame remain exact")
	# Compare mode must exercise the complete solver while legacy alone drives the rig.
	actors[1].get("_mount_visual").rust_pose._mode_override = "compare"
	for frame: int in 8:
		actors[1].get("_mount_visual")._step_visual(1.0 / 30.0)
	var shadow: Dictionary = actors[1].get("_mount_visual").rust_pose.snapshot()
	expect(int(shadow.comparisons) == 8 and int(shadow.failures) == 0, "shadow mode actually compared eight poses")
	expect(float(shadow.maxPositionError) < 0.0001 and float(shadow.maxAngleError) < 0.001 and float(shadow.maxScaleError) < 0.0001 and float(shadow.maxVisualError) < 0.0001, "full pre-upper-body shadow pose parity")
	actors[1].get("_mount_visual").rust_pose._mode_override = "rust"
	# Reset invalidates every old handle; the same live mount lazily registers fresh immutable data.
	_controller.epoch += 1
	expect(int(_controller.native.reset_epoch(_controller.epoch)) == 0, "map/session epoch advances")
	for index: int in [1, 2]:
		var shim = actors[index].get("_mount_visual").rust_pose
		actors[index].get("_mount_visual")._step_visual(0.0)
		Shim.flush_pending()
		expect(shim._epoch == _controller.epoch and shim.applications > 0, "live rider re-registers after reset")
	await _reject_invalid(actors[1])
	for actor: ReplicatedActor3D in actors:
		var visual: Node3D = actor.get_node("NativeModel")
		var exact: Transform3D = actor.get("_mount_visual").pose.visual_rest
		actor.set_mount_state({}, _models)
		expect(visual.transform.is_equal_approx(exact), "native pilot dismount restores exact native rest transform")
	# A fresh lifetime tests callbacks without contaminating the paired sequence.
	actors[1].set_mount_state({"mode": "mounted", "mount_id": "moor_pony", "gait": "walk", "step_us": 200000}, _models)
	actors[1].get("_mount_visual").set_process(false)
	actors[1].get("_mount_visual").rust_pose.configure(actors[1].get("_mount_visual").pose, "moor_pony", _controller)
	actors[1].get("_mount_visual")._step_visual(0.0)
	Shim.flush_pending()
	_reentrant_apply_probe(actors[1])
	await _retire(actors)

func _reentrant_apply_probe(actor: ReplicatedActor3D) -> void:
	var shim = actor.get("_mount_visual").rust_pose
	var native = _controller.native
	var owner = actor.get("_mount_visual")
	var rig := actor.get_skeleton()
	var records: PackedInt64Array = shim.record("idle")
	records[4] += 1
	var samples: PackedFloat64Array = shim.sample(Transform3D.IDENTITY, 0.0, 1.0)
	var before: Dictionary = native.runtime_info()
	var observed := {"seen": false, "nested": true, "reset": 0}
	var callback := func() -> void:
		if bool(observed.seen):
			return
		observed.seen = true
		observed.nested = native.solve_mounted_batch(records, samples, _controller.epoch, true)
		observed.reset = native.reset_epoch(_controller.epoch + 1)
		# Only the mount owner is destroyed. The currently updating rider
		# Skeleton3D survives; its weak owner binding and queued releases do not.
		owner.free()
	var signals: Array[StringName] = []
	for signal_name: StringName in [&"pose_updated", &"skeleton_updated"]:
		if rig.has_signal(signal_name):
			rig.connect(signal_name, callback)
			signals.append(signal_name)
	var ok: bool = native.solve_mounted_batch(records, samples, _controller.epoch, true)
	for signal_name: StringName in signals:
		if rig.is_connected(signal_name, callback):
			rig.disconnect(signal_name, callback)
	var after: Dictionary = native.runtime_info()
	expect(bool(observed.seen), "real Skeleton3D update callback is a positive reentrancy control")
	expect(not ok and not bool(observed.nested) and int(observed.reset) != 0, "owned apply rejects nested solve/reset and cancels after callback")
	expect(int(after.reentrant_rejections) >= int(before.reentrant_rejections) + 2, "actual rejected nested calls are diagnosed")
	expect(int(after.rig_count) == int(before.rig_count) - 1 and int(after.mounted_rider_count) == int(before.mounted_rider_count) - 1, "callback owner removal drains deferred rider and rig releases")
	expect(native.mounted_pose_metadata().is_empty() and native.mounted_pose_values().is_empty(), "cancelled apply publishes no valid complete-batch result")

func _foreign_thread_probe(native) -> void:
	var before: Dictionary = native.runtime_info()
	var before_status: int = native.get_last_status()
	var worker := Thread.new()
	var callback := func() -> Dictionary:
		return {"reset": native.reset_epoch(9999),
			"register": native.register_rig(PackedInt32Array(), PackedFloat64Array(), PackedFloat64Array()),
			"unregister": native.unregister_rig(1),
			"rider": native.register_mounted_rider(0, PackedInt32Array(), PackedFloat64Array(), PackedInt32Array(), PackedFloat64Array()),
			"bind": native.bind_mounted_rider(0, null, null, null, -1, 0),
			"unregisterRider": native.unregister_mounted_rider(1),
			"solve": native.solve_mounted_batch(PackedInt64Array(), PackedFloat64Array(), 1, true),
			"plan": native.plan_batch(PackedInt64Array(), 1, 0),
			"metadata": native.mounted_pose_metadata(), "values": native.mounted_pose_values(),
			"contacts": native.mounted_contact_errors(1, 1, 1),
			"info": native.runtime_info(), "status": native.get_last_status()}
	var error := worker.start(callback)
	expect(error == OK, "foreign-thread rejection fixture starts")
	if error != OK:
		return
	var rejected: Dictionary = worker.wait_to_finish()
	expect(int(rejected.reset) != 0 and int(rejected.register) == 0 and not bool(rejected.unregister) and int(rejected.rider) == 0 and not bool(rejected.bind) and not bool(rejected.unregisterRider) and not bool(rejected.solve), "every foreign mutation rejects")
	expect((rejected.plan as PackedInt64Array).is_empty() and (rejected.metadata as PackedInt64Array).is_empty() and (rejected.values as PackedFloat64Array).is_empty() and (rejected.contacts as PackedFloat64Array).is_empty(), "foreign buffer getters do not read mutable buffers")
	expect(int(rejected.status) != 0 and not bool(rejected.info.ready) and str(rejected.info.reason) == "wrong_thread", "foreign diagnostics return explicit unavailable state")
	expect(before == native.runtime_info() and before_status == native.get_last_status(), "foreign calls leave every owner counter and status unchanged")

func _reject_invalid(actor: ReplicatedActor3D) -> void:
	var shim = actor.get("_mount_visual").rust_pose
	var native = _controller.native
	var records: PackedInt64Array = shim.record("idle")
	records[4] += 1
	var samples: PackedFloat64Array = shim.sample(Transform3D.IDENTITY, 0.0, 1.0)
	var skeleton := actor.get_skeleton()
	var before: Array[Transform3D] = []
	for bone: int in skeleton.get_bone_count():
		before.append(skeleton.get_bone_pose(bone))
	var visual := (actor.get_node("NativeModel") as Node3D).global_transform
	for bad: int in 4:
		var r := records.duplicate()
		var s := samples.duplicate()
		var epoch := _controller.epoch
		if bad == 0: r[1] += 100
		if bad == 1: epoch -= 1
		if bad == 2: s[13] = 0.0
		if bad == 3: s[0] = NAN
		expect(not native.solve_mounted_batch(r, s, epoch, true), "invalid or stale complete batch rejected " + str(bad))
		var unchanged := visual.is_equal_approx((actor.get_node("NativeModel") as Node3D).global_transform)
		for bone: int in skeleton.get_bone_count():
			unchanged = unchanged and before[bone].is_equal_approx(skeleton.get_bone_pose(bone))
		expect(unchanged, "rejected batch does not partially mutate any pose or visual")
	await process_frame

func _retire(actors: Array[ReplicatedActor3D]) -> void:
	Shim.close_batches()
	for actor: ReplicatedActor3D in actors:
		actor.process_mode = Node.PROCESS_MODE_DISABLED
	await _drain()
	for actor: ReplicatedActor3D in actors:
		actor.queue_free()
	await _drain()

func _drain() -> void:
	await physics_frame
	await process_frame
	await process_frame

func run() -> void:
	var q := Quaternion(0.2, 0.3, 0.4, 0.5)
	expect(Shim.rotation_error(q, q) < 0.0000001, "angle comparison has a zero self-distance for non-unit stored quaternions")
	expect(Shim.rotation_error(q, Quaternion(-q.x, -q.y, -q.z, -q.w)) < 0.0000001, "quaternion signs describe the same rotation")
	expect(absf(Shim.rotation_error(Quaternion.IDENTITY, Quaternion(Vector3.UP, 0.02)) - 0.02) < 0.000001, "angle comparison detects an actual known rotation")
	var loader := RuntimeController.new()
	var previous_mode := OS.get_environment("RABBITLANDS_CLIENT_RUNTIME")
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "compare")
	loader.initialize()
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", previous_mode)
	var loaded = loader.native_runtime()
	expect(loaded != null, "native-present test requires the validated optional extension: " + str(loader.snapshot()))
	if loaded == null:
		loader.close()
		quit(1)
		return
	_controller = FixtureController.new()
	_controller.native = loaded
	expect(_controller.native.has_method("solve_mounted_batch"), "rider API exists, not only scheduler API")
	if not _controller.native.has_method("solve_mounted_batch"):
		loader.close()
		quit(1)
		return
	_foreign_thread_probe(_controller.native)
	_models = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	for body: String in ["luminous_male", "luminous_female"]:
		await _pair(body, 1.0, false)
		await _pair(body, 1.35, true)
	Shim.close_batches()
	_controller.native = null
	_controller = null
	loaded = null
	loader.close()
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await _drain()
	print("RUST_MOUNTED_POSE_ANGLES ", JSON.stringify({"rawEngineAngleMaximum": _raw_angle_max, "normalizedF64AngleMaximum": _normalized_angle_max}))
	print("RUST_MOUNTED_POSE_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
