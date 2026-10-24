class_name RustSpellEffect3D
extends WorldEffect3D
## Godot owns the approved material/particle nodes. One coarse manager owns the
## native clock. This proxy never runs a second automatic clock while batched.
var runtime_generation := 0
var runtime_epoch := 0
var _batched := false
var _fallback_frame := -1
var _batch_mesh := ArrayMesh.new()
var _original_flight_mesh: Mesh
var last_impact_us := 0
var _native_commit: Dictionary = {}

func _presentation_valid() -> bool:
	if not is_instance_valid(self): return false
	if not _native_commit.is_empty():
		var parent := get_parent()
		if not _batched or runtime_generation != int(_native_commit.generation) or runtime_epoch != int(_native_commit.epoch) \
			or (parent.get_instance_id() if parent != null else 0) != int(_native_commit.parent_id):
			return false
		var original_guard: Callable = _native_commit.guard
		if not original_guard.is_null() and (not original_guard.is_valid() or not bool(original_guard.call())):
			return false
	return super._presentation_valid()

func set_publication_guard(guard: Callable) -> void:
	_presentation_guard = guard
	if is_instance_valid(flight):
		flight._presentation_guard = guard

func begin_batch(generation: int, epoch: int) -> bool:
	runtime_generation = generation
	runtime_epoch = epoch
	_original_flight_mesh = flight._mesh_node.mesh
	_batched = true
	flight._mesh_node.mesh = _batch_mesh
	if not is_instance_valid(self) or not _presentation_valid():
		return false
	set_process(false)
	return true

func native_spec(priority: bool) -> Dictionary:
	var color: Color = flight.tint
	return {"records": PackedInt64Array([get_instance_id(), runtime_generation,
		2, power_level, 1 if priority else 0]),
		"values": PackedFloat64Array([flight.start.x, flight.start.y, flight.start.z,
			flight.destination.x, flight.destination.y, flight.destination.z,
			_impact.x, _impact.y, _impact.z, color.r, color.g, color.b, color.a,
			release_delay, float(flight.duration)])}

func native_anchor() -> Dictionary:
	# Do not mutate presentation while collecting inputs: output is committed
	# only after every frame in the coarse result has passed validation.
	var from: Vector3 = flight.start
	var to: Vector3 = flight.destination
	var impact := _impact
	var source: Node3D = _source_actor.get_ref() as Node3D if _source_actor != null else null
	var target: Node3D = _target_actor.get_ref() as Node3D if _target_actor != null else null
	var source_valid: bool = is_instance_valid(source) and not _launched
	var target_valid: bool = is_instance_valid(target) and not impact_started
	if source_valid:
		from = to_local(source.spell_release_origin() if source is ReplicatedActor3D
			else source.global_position + Vector3.UP)
	if target_valid:
		to = to_local(target.spell_target_position() if target is ReplicatedActor3D
			else target.global_position + Vector3.UP)
		impact = to_local(target.global_position)
	return {"records": PackedInt64Array([get_instance_id(), runtime_generation,
		1 if source_valid else 0, 1 if target_valid else 0]),
		"values": PackedFloat64Array([from.x, from.y, from.z, to.x, to.y, to.z,
			impact.x, impact.y, impact.z])}

func apply_native(frame: Dictionary) -> void:
	var parent := get_parent()
	_native_commit = {"parent_id": parent.get_instance_id() if parent != null else 0,
		"generation": runtime_generation, "epoch": runtime_epoch, "guard": _presentation_guard}
	_apply_native_guarded(frame)
	if is_instance_valid(self): _native_commit = {}

func _apply_native_guarded(frame: Dictionary) -> void:
	var parent_at_start := get_parent()
	elapsed = float(frame.elapsed)
	_launched = int(frame.phase) >= 1
	_impact = frame.impact
	flight.set_endpoints(frame.start, frame.destination)
	if not is_instance_valid(self) or not _presentation_valid():
		return
	_ring.position = _impact + Vector3.UP * 0.055
	if not is_instance_valid(self) or not _presentation_valid():
		return
	_burst.position = flight.destination
	if not is_instance_valid(self) or not _presentation_valid():
		return
	_batch_mesh.clear_surfaces()
	if not is_instance_valid(self) or not _presentation_valid():
		return
	_batch_mesh.custom_aabb = frame.bounds
	if not is_instance_valid(self) or not _presentation_valid():
		return
	_submit_surface(frame.ribbon, flight._ribbon_material)
	if not is_instance_valid(self) or not _presentation_valid():
		return
	_submit_surface(frame.glow, flight._glow_material)
	if not is_instance_valid(self) or not _presentation_valid():
		return
	last_impact_us = 0
	if int(frame.phase) < 2:
		return
	var began := Time.get_ticks_usec()
	if (int(frame.events) & 2) != 0:
		_start_impact()
		if not is_instance_valid(self) or not _presentation_valid():
			return
		# Showing the ring can synchronously remove/retire this effect.
		if not is_instance_valid(self) or not is_inside_tree() or is_queued_for_deletion() \
				or not _batched or get_parent() != parent_at_start:
			return
	_ring.scale = Vector3(float(frame.ring_scale), 1.0, float(frame.ring_scale))
	if not is_instance_valid(self) or not _presentation_valid():
		return
	_material.albedo_color.a = float(frame.alpha)
	if not is_instance_valid(self) or not _presentation_valid():
		return
	(_material.next_pass as StandardMaterial3D).albedo_color.a = _material.albedo_color.a * 0.40
	if not is_instance_valid(self) or not _presentation_valid():
		return
	_draw_details(float(frame.progress))
	if not is_instance_valid(self) or not _presentation_valid():
		return
	if int(frame.phase) == 3:
		queue_free()
	last_impact_us = Time.get_ticks_usec() - began

func _start_impact() -> void:
	impact_started = true
	var ring := _ring
	var burst := _burst
	if is_instance_valid(ring):
		ring.show()
		if not is_instance_valid(self) or not _presentation_valid():
			return
	if not is_instance_valid(self) or not is_instance_valid(burst) or is_queued_for_deletion():
		return
	burst.restart()
	if not is_instance_valid(self) or not _presentation_valid():
		return
	burst.emitting = true
	if not is_instance_valid(self) or not _presentation_valid():
		return

func _submit_surface(packed: Array, material: Material) -> void:
	if (packed[0] as PackedVector3Array).is_empty():
		return
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = packed[0]
	arrays[Mesh.ARRAY_COLOR] = packed[1]
	arrays[Mesh.ARRAY_TEX_UV] = packed[2]
	_batch_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	if not is_instance_valid(self) or not _presentation_valid():
		return
	_batch_mesh.surface_set_material(_batch_mesh.get_surface_count() - 1, material)
	if not is_instance_valid(self) or not _presentation_valid():
		return

func resume_legacy(delta: float) -> void:
	if not _batched:
		return
	var suspended_commit := _native_commit
	_native_commit = {}
	_resume_legacy_guarded(delta)
	if is_instance_valid(self): _native_commit = suspended_commit

func _resume_legacy_guarded(delta: float) -> void:
	_batched = false
	# The manager has already disabled native ownership. Legacy fallback keeps
	# only ordinary local lifetime guards, and advances this frame exactly once.
	set_publication_guard(Callable())
	_fallback_frame = Engine.get_process_frames()
	_batch_mesh.clear_surfaces()
	if not is_instance_valid(self) or not _presentation_valid():
		return
	flight._mesh_node.mesh = _original_flight_mesh
	if not is_instance_valid(self) or not _presentation_valid():
		return
	_fallback_frame = Engine.get_process_frames()
	set_process(true)
	# Native results were never applied for this frame; advance it exactly once.
	super._process(delta)

func _process(delta: float) -> void:
	if not _batched and _fallback_frame != Engine.get_process_frames():
		super._process(delta)
