extends "res://src/actors/cape_mounted_fit.gd"
## Mirrors numeric calls without changing the actual actor's returned pose.

var parity_calls := 0
var parity_checks := 0
var parity_error_count := 0
var parity_failures: Array[String] = []
var parity_contexts: Dictionary = {}
var _parity_context := "initial"
var _parity_step := 0
var _parity_reference: RefCounted
var _parity_optimized: RefCounted
var _parity_template: Dictionary = {}
var _parity_guards_checked := false

func adopt_actual_state(source: RefCounted) -> void:
	for property: Dictionary in source.get_property_list():
		var name := str(property.name)
		if name.begins_with("_") and (int(property.usage) & PROPERTY_USAGE_SCRIPT_VARIABLE) != 0:
			set(name, source.get(name))

func begin_context(label: String) -> void:
	_parity_context = label
	_parity_step = 0

func _expect_equal(ok: bool, message: String) -> void:
	parity_checks += 1
	if not ok:
		parity_error_count += 1
		if parity_failures.size() < 16:
			parity_failures.append(_parity_context + ": " + message)

func _make_mirrors() -> bool:
	if _parity_reference != null:
		return true
	for field: StringName in TEMPLATE_FIELDS:
		_parity_template[str(field).trim_prefix("_")] = get(field)
	_parity_template.solver = {"edge_limit": EDGE_LIMIT, "gap_limit_m": GAP_LIMIT,
		"strain_tolerance": .005, "cold_iterations": COLD_ITERATIONS,
		"warm_iterations": WARM_ITERATIONS, "activate_contacts": true,
		"covered_clear": true, "exact_memo": true, "trusted_body": true,
		"parallel_contacts": true, "parallel_residuals": false,
		"refresh_clear_contacts": true}
	_parity_reference = ClassDB.instantiate("RabbitLandsCapeProjector")
	_parity_optimized = ClassDB.instantiate("RabbitLandsCapeProjector")
	var reference_ok: bool = _parity_reference.call("configure", _parity_template)
	_parity_template.solver.parallel_residuals = true
	var optimized_ok: bool = _parity_optimized.call("configure", _parity_template)
	_expect_equal(reference_ok and optimized_ok, "both numeric templates configure")
	return reference_ok and optimized_ok

func _call_projector(projector: RefCounted, packet: Array) -> Dictionary:
	var value: Variant = projector.callv("project", packet)
	return value as Dictionary if value is Dictionary else {}

func _body_signature(skeleton: Skeleton3D) -> PackedByteArray:
	var values := PackedFloat64Array()
	for bone: int in skeleton.get_bone_count():
		if skeleton.get_bone_name(bone).begins_with("cape_"):
			continue
		var pose := skeleton.get_bone_global_pose(bone)
		for vector: Vector3 in [pose.basis.x, pose.basis.y, pose.basis.z, pose.origin]:
			values.append_array(PackedFloat64Array([vector.x, vector.y, vector.z]))
	return values.to_byte_array()

func project(skeleton: Skeleton3D, world: Transform3D, frame: Transform3D,
		translations: PackedVector3Array, contact: Callable, plane_contact: Callable) -> PackedVector3Array:
	var actual := super.project(skeleton, world, frame, translations, contact, plane_contact)
	if not _make_mirrors():
		return actual
	var bodies: Array[Transform3D] = []
	for bone: int in _body_bones:
		bodies.append(skeleton.get_bone_global_pose(bone))
	var debug := _parity_step % 30 == 0 or _parity_step == 59
	var body_before := _body_signature(skeleton) if debug else PackedByteArray()
	var packet: Array = [world, frame, _root_frames, bodies, translations,
		_native_contacts, _native_mount, _native_body, debug]
	var results: Array[Dictionary] = [{}, {}]
	var order: Array = [0, 1] if parity_calls % 2 == 0 else [1, 0]
	for index: int in order:
		results[index] = _call_projector(_parity_reference if index == 0 else _parity_optimized, packet)
	var a := results[0]
	var b := results[1]
	var accepted := bool(a.get("ok", false)) and bool(b.get("ok", false))
	_expect_equal(accepted, "both projectors accept frame " + str(_parity_step))
	if accepted:
		var left: PackedVector3Array = a.translations
		var right: PackedVector3Array = b.translations
		_expect_equal(left.to_byte_array() == right.to_byte_array(), "all twelve controls are byte-identical")
		for key: String in ["gap_m", "strain", "iterations", "residual_point_hits", "residual_point_misses"]:
			_expect_equal(a.stats.has(key) and b.stats.has(key) and a.stats[key] == b.stats[key], "identical " + key)
		if debug:
			for key: String in ["world", "virtual_world", "posed_world", "posed_virtual_world"]:
				var first: PackedVector3Array = a.get(key, PackedVector3Array())
				var second: PackedVector3Array = b.get(key, PackedVector3Array())
				_expect_equal(not first.is_empty() and first.to_byte_array() == second.to_byte_array(), "byte-identical " + key)
			_expect_equal(body_before == _body_signature(skeleton), "numeric mirrors leave Body65 poses untouched")
		if not _parity_guards_checked:
			_probe_rejections(packet)
	var row: Dictionary = parity_contexts.get(_parity_context, {"calls": 0, "debug_skin_calls": 0})
	row.calls += 1
	row.debug_skin_calls += 1 if debug else 0
	parity_contexts[_parity_context] = row
	parity_calls += 1
	_parity_step += 1
	return actual

func _foreign_body() -> RefCounted:
	return ClassDB.instantiate("RabbitLandsCapeBodySurface")

func _probe_rejections(packet: Array) -> void:
	_parity_guards_checked = true
	var before: Dictionary = _parity_optimized.call("stats")
	for solver: Dictionary in [{"parallel_residuals": 1},
			{"parallel_residuals": true, "parallel_contacts": false},
			{"parallel_residuals": true, "parallel_contacts": true, "trusted_body": true, "exact_memo": false},
			{"parallel_contacts": true, "trusted_body": false}, {"refresh_clear_contacts": 1}]:
		var malformed := _parity_template.duplicate()
		malformed.solver = solver
		_expect_equal(not bool(_parity_optimized.call("configure", malformed)), "invalid optional flags are rejected")
	var thread := Thread.new()
	thread.start(_foreign_body)
	var foreign: RefCounted = thread.wait_to_finish()
	var invalid := packet.duplicate()
	invalid[7] = foreign
	_expect_equal(not bool(_call_projector(_parity_optimized, invalid).get("ok", true)), "foreign body owner is rejected")
	var after: Dictionary = _parity_optimized.call("stats")
	_expect_equal(before.calls == after.calls and before.history == after.history, "rejections preserve accepted history")

func parity_summary() -> Dictionary:
	return {"calls": parity_calls, "checks": parity_checks, "error_count": parity_error_count,
		"failures": parity_failures.duplicate(), "contexts": parity_contexts.duplicate(true),
		"rejection_guards_exercised": _parity_guards_checked}

func release_parity_mirrors() -> void:
	_parity_reference = null
	_parity_optimized = null
	_parity_template.clear()
