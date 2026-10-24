class_name RustSpellFlightManager
extends Node
const OptimizationProfile := preload("res://src/runtime/optimization_profile.gd")
## Human-testing heat-bolt slice. Unsupported shapes and any failed preflight use the
## normal WorldEffect3D path. All native output is validated before mesh writes.
const Proxy = preload("res://src/world/rust_spell_effect_3d.gd")
const SERVICE_NAME := "RustSpellFlights"
const MAX_FLIGHTS := 512
var _controller: ClientRuntimeController
var _native: RefCounted
var _epoch := 1
var _proxies: Dictionary = {} # id -> {weak, generation}; never retains an actor.
var _reason := "not_initialized"
var _costs: Dictionary = {}
var _last: Dictionary = {}
var _frames := 0
var _fallbacks := 0
var _high_water := 0
var _pending_failure := ""
var _processing_delta := 0.0
var _advancing := false
var _applied: Dictionary = {}
var _discarding := false
var _events := {"releases":0,"arrivals":0,"expiries":0}
var _admitted_rust := 0
var _admitted_legacy := 0
var _admission_frame := -1
var _frame_admission_us := 0

static func spawn(controller: ClientRuntimeController, parent: Node3D,
		effect: Dictionary, origin: Vector3, target: Variant,
		source: Node3D, receiver: Node3D, priority: bool, limit: int) -> Node3D:
	if OptimizationProfile.selected("rust_effects") != "heat_bolt" \
			or controller == null or controller.native_runtime() == null \
			or not controller.is_rust_mode() \
			or int(effect.get("effect", -1)) != 2 or not target is Vector3 \
			or not origin.is_finite() or not (target as Vector3).is_finite() \
			or origin.distance_squared_to(target as Vector3) <= 0.0025 \
			or float(effect.get("area_radius", 0.0)) > 0.0:
		return null
	if not is_instance_valid(parent) or parent.is_queued_for_deletion():
		return null
	var existing := parent.get_node_or_null(NodePath(SERVICE_NAME))
	if existing != null and (not existing is RustSpellFlightManager or existing.is_queued_for_deletion()):
		return null
	var manager := existing as RustSpellFlightManager
	if existing == null:
		var initialize_began := Time.get_ticks_usec()
		manager = RustSpellFlightManager.new()
		manager.name = SERVICE_NAME
		parent.add_child(manager)
		if not is_instance_valid(manager):
			return null
		if manager.get_parent() != parent or manager.is_queued_for_deletion():
			manager.queue_free()
			return null
		manager.initialize(controller)
		manager._add_cost("service_initialization_us", Time.get_ticks_usec()-initialize_began)
	if not manager.has_method("admit"):
		return null
	return manager.admit(effect, origin, target, source, receiver, priority, limit) as Node3D

static func snapshot_for(parent: Node3D) -> Dictionary:
	var manager := parent.get_node_or_null(NodePath(SERVICE_NAME)) if is_instance_valid(parent) else null
	return manager.snapshot() if manager != null and manager.has_method("snapshot") else {
		"active": false, "family": "heat_bolt", "reason": "not_instantiated",
		"requested":OptimizationProfile.selected("rust_effects")}

static func clear_for(parent: Node3D) -> void:
	var manager := parent.get_node_or_null(NodePath(SERVICE_NAME)) as RustSpellFlightManager if is_instance_valid(parent) else null
	if manager != null:
		manager.discard()

func discard() -> void:
	_discarding = true
	for row: Dictionary in _proxies.values():
		var proxy: RustSpellEffect3D = row.weak.get_ref() as RustSpellEffect3D
		if is_instance_valid(proxy) and not proxy.is_queued_for_deletion():
			proxy.queue_free()
	_proxies.clear()
	_native = null
	set_process(false)
	queue_free()

func _init() -> void:
	process_priority = 100 # Collect actors and apply all meshes in this same frame.
	set_process(false)

func initialize(controller: ClientRuntimeController) -> void:
	_controller = controller
	_epoch = controller.current_epoch()
	if not controller.is_rust_mode():
		_reason = "controller_not_rust"
		return
	if not ClassDB.class_exists("RabbitLandsSpellFlightRuntime"):
		_reason = "optional_capability_absent"
		return
	_native = ClassDB.instantiate("RabbitLandsSpellFlightRuntime") as RefCounted
	if _native == null or not _native.has_method("spawn_batch") or not _native.has_method("step_batch") \
			or not _native.has_method("cancel") or not _native.has_method("reset_epoch") \
			or not _native.has_method("runtime_info") or not _native.has_method("get_last_status"):
		_native = null
		_reason = "capability_invalid"
		return
	var info: Variant = _native.call("runtime_info")
	if not info is Dictionary or int(info.get("abi", -1)) != 1 or not bool(info.get("ready", false)) \
			or str(info.get("family", "")) != "heat_bolt" \
			or (_epoch > 1 and int(_native.call("reset_epoch", _epoch)) != 0):
		_native = null
		_reason = "capability_preflight_failed"
		return
	_reason = "rust_heat_bolt"

func admit(effect: Dictionary, origin: Vector3, target: Variant, source: Node3D,
		receiver: Node3D, priority: bool, limit: int) -> Node3D:
	if _native == null or not _pending_failure.is_empty() or _controller == null or _controller.current_epoch() != _epoch:
		return null
	var began := Time.get_ticks_usec()
	var parent := get_parent()
	var proxy := Proxy.new()
	proxy.runtime_generation = _controller.allocate_instance_generation()
	proxy.runtime_epoch = _epoch
	proxy.set_publication_guard(_can_prepare.bind(proxy, parent, proxy.runtime_generation))
	parent.add_child(proxy)
	if not is_instance_valid(self):
		if is_instance_valid(proxy): proxy.queue_free()
		return null
	if not _construction_continues(proxy, parent):
		return null
	proxy.configure(2, origin, target, int(effect.get("power", 1)))
	if not is_instance_valid(self):
		if is_instance_valid(proxy): proxy.queue_free()
		return null
	if not _construction_continues(proxy, parent):
		return null
	proxy.bind_actors(source, receiver)
	if not is_instance_valid(self):
		if is_instance_valid(proxy): proxy.queue_free()
		return null
	if not _construction_continues(proxy, parent):
		return null
	if effect.has("release_delay"):
		proxy.configure_timing(float(effect.release_delay), float(effect.get("flight_duration", 0.0)))
	if not is_instance_valid(self):
		if is_instance_valid(proxy): proxy.queue_free()
		return null
	if not _construction_continues(proxy, parent):
		return null
	var spec: Dictionary = proxy.native_spec(priority)
	var response: Variant = _native.call("spawn_batch", spec.records, spec.values, _epoch, clampi(limit, 1, MAX_FLIGHTS))
	var status: Variant = _native.call("get_last_status")
	if not response is PackedInt64Array or not status is int or status != 0 \
			or response.size() != 1 or int(response[0]) not in [0, 1]:
		# Existing effects retain their previous presentation; disable future use.
		_pending_failure = "admission_invalid"
		proxy.set_publication_guard(Callable())
		_admitted_legacy += 1
		set_process(true) # Existing clocks resume with this frame's real delta.
		_record_admission(Time.get_ticks_usec() - began)
		return proxy
	if int(response[0]) == 0:
		proxy.set_publication_guard(Callable())
		_admitted_legacy += 1
		# A hard capacity or stricter native soft cap cannot drop a Main-admitted
		# visual, especially one admitted for local/selection/combat priority.
		_record_admission(Time.get_ticks_usec() - began)
		return proxy
	if not proxy.begin_batch(proxy.runtime_generation, _epoch):
		if is_instance_valid(self) and _native != null:
			_native.call("cancel", proxy.get_instance_id() if is_instance_valid(proxy) else int(spec.records[0]), int(spec.records[1]), _epoch)
		if is_instance_valid(proxy):
			proxy.queue_free()
		return null
	_admitted_rust += 1
	_proxies[proxy.get_instance_id()] = {"weak": weakref(proxy), "generation": proxy.runtime_generation}
	_high_water = maxi(_high_water, _proxies.size())
	set_process(true)
	_record_admission(Time.get_ticks_usec() - began)
	return proxy

func _process(delta: float) -> void:
	if _advancing:
		_pending_failure = "reentrant_advance"
		return
	_advancing = true
	_advance_frame(delta)
	if is_instance_valid(self): _advancing = false

func _advance_frame(delta: float) -> void:
	_processing_delta = delta
	_applied.clear()
	if _native == null:
		return
	if not _pending_failure.is_empty():
		_fail_closed(delta, _pending_failure)
		return
	if _controller == null or _controller.native_runtime() == null \
			or _controller.current_epoch() != _epoch or not _controller.is_rust_mode():
		_fail_closed(delta, "controller_changed")
		return
	var began := Time.get_ticks_usec()
	var collect_began := began
	var records := PackedInt64Array()
	var values := PackedFloat64Array()
	var live: Dictionary = {}
	var expected_anchors: Dictionary = {}
	for id: int in _proxies:
		var proxy: RustSpellEffect3D = _proxies[id].weak.get_ref() as RustSpellEffect3D
		if not is_instance_valid(proxy) or proxy.is_queued_for_deletion():
			_native.call("cancel", id, int(_proxies[id].generation), _epoch)
			continue
		live[id] = proxy
		var anchor: Dictionary = proxy.native_anchor()
		expected_anchors[id] = anchor
		records.append_array(anchor.records)
		values.append_array(anchor.values)
	var collected := Time.get_ticks_usec() - collect_began
	for id: int in _proxies.keys():
		if not live.has(id):
			_proxies.erase(id)
	if live.is_empty():
		set_process(false)
		return
	var camera := get_viewport().get_camera_3d()
	var view := camera.global_basis.z.normalized() if camera != null else Vector3(0.3, 0.5, 1).normalized()
	var right := camera.global_basis.x.normalized() if camera != null else Vector3.RIGHT
	var up := view.cross(right).normalized()
	var native_began := Time.get_ticks_usec()
	var response: Variant = _native.call("step_batch", records, values, _epoch, delta, view, right, up)
	var call_us := Time.get_ticks_usec() - native_began
	var validation_began := Time.get_ticks_usec()
	var status: Variant = _native.call("get_last_status")
	if not status is int or status != 0 or not _valid_result(response, live, delta, expected_anchors):
		_fail_closed(delta, "invalid_whole_batch")
		return
	var validation_us := Time.get_ticks_usec() - validation_began
	var submission_began := Time.get_ticks_usec()
	var impact_us := 0
	for frame: Dictionary in response.frames:
		var proxy: RustSpellEffect3D = live[int(frame.id)]
		# Mesh/material/visibility publication can synchronously call game code.
		# Revalidate ownership after every preceding callback boundary.
		if not _can_submit(proxy, int(frame.generation)):
			_fail_closed(delta, "reentrant_lifecycle_change", _applied)
			_processing_delta = 0.0
			return
		_applied[int(frame.id)] = true
		for flag: int in [1,2,4]:
			if (int(frame.events) & flag) != 0:
				var label: String = {1:"releases",2:"arrivals",4:"expiries"}[flag]
				_events[label] = int(_events[label])+1
		proxy.set_publication_guard(_can_submit.bind(proxy, int(frame.generation)))
		proxy.apply_native(frame)
		if not is_instance_valid(self):
			return
		if is_instance_valid(proxy):
			impact_us += int(proxy.last_impact_us)
		if not is_inside_tree() or is_queued_for_deletion() or _native == null:
			_processing_delta = 0.0
			return
		var expected_expiry: bool = is_instance_valid(proxy) and proxy.is_queued_for_deletion() and int(frame.phase) == 3
		if not is_instance_valid(proxy) or (proxy.is_queued_for_deletion() and not expected_expiry) \
				or (not proxy.is_queued_for_deletion() and not _can_submit(proxy, int(frame.generation))) \
				or not _pending_failure.is_empty() or _controller == null \
				or _controller.current_epoch() != _epoch or _controller.native_runtime() == null or not _controller.is_rust_mode():
			_fail_closed(delta, "reentrant_lifecycle_change", _applied)
			_processing_delta = 0.0
			return
		if int(frame.phase) == 3:
			_proxies.erase(int(frame.id))
	var submission_us := Time.get_ticks_usec() - submission_began
	var advance_us := Time.get_ticks_usec() - began
	var admission_us := _frame_admission_us if _admission_frame == Engine.get_process_frames() else 0
	_frames += 1
	_last = {"frame": Engine.get_process_frames(), "effects": live.size(),
		"anchor_and_packing_us": collected, "native_call_us": call_us,
		"native_core_us": int(response.core_us), "native_conversion_us": int(response.conversion_us),
		"native_adapter_us": int(response.adapter_us), "validation_us": validation_us,
		"mesh_and_impact_submission_us": submission_us, "impact_submission_us": impact_us,
		"advance_total_us": advance_us, "admission_us_this_frame": admission_us,
		"total_us": advance_us+admission_us, "vertices": int(response.vertices)}
	for key: String in _last:
		if key.ends_with("_us") or key == "vertices":
			_add_cost(key, int(_last[key]))
	if _proxies.is_empty():
		set_process(false)
	_processing_delta = 0.0
	_applied.clear()

func _can_prepare(proxy: RustSpellEffect3D, parent: Node, generation: int) -> bool:
	return is_instance_valid(self) and is_inside_tree() and not is_queued_for_deletion() \
		and _native != null and _pending_failure.is_empty() and _controller != null and _controller.native_runtime() != null \
		and _controller.current_epoch() == _epoch and _controller.is_rust_mode() \
		and is_instance_valid(proxy) and not proxy.is_queued_for_deletion() \
		and is_instance_valid(parent) and proxy.get_parent() == parent and proxy.is_inside_tree() \
		and proxy.runtime_epoch == _epoch and proxy.runtime_generation == generation

func _construction_continues(proxy: RustSpellEffect3D, parent: Node) -> bool:
	if not is_instance_valid(self):
		if is_instance_valid(proxy): proxy.queue_free()
		return false
	if not is_instance_valid(proxy): return false
	if not _can_prepare(proxy, parent, proxy.runtime_generation):
		proxy.queue_free()
		return false
	return true

func _can_submit(proxy: RustSpellEffect3D, generation := -1) -> bool:
	return is_inside_tree() and not is_queued_for_deletion() and _native != null and _pending_failure.is_empty() \
		and _controller != null and _controller.native_runtime() != null \
		and _controller.current_epoch() == _epoch \
		and _controller.is_rust_mode() \
		and is_instance_valid(proxy) and proxy.is_inside_tree() and not proxy.is_queued_for_deletion() \
		and proxy.get_parent() == get_parent() and int(proxy.runtime_epoch) == _epoch and proxy._batched \
		and (generation < 0 or int(proxy.runtime_generation) == generation)

func _valid_result(result: Variant, live: Dictionary, delta: float, anchors: Dictionary = {}) -> bool:
	if not result is Dictionary or int(result.get("abi", -1)) != 1 \
			or int(result.get("epoch", -1)) != _epoch or not result.get("frames") is Array \
			or result.frames.size() != live.size():
		return false
	for key: String in ["core_us", "conversion_us", "adapter_us", "vertices"]:
		if not result.get(key) is int or int(result[key]) < 0:
			return false
	var seen: Dictionary = {}
	for candidate: Variant in result.frames:
		if not candidate is Dictionary:
			return false
		var f: Dictionary = candidate
		for key: String in ["id", "generation", "epoch", "phase", "events"]:
			if not f.get(key) is int:
				return false
		var id := int(f.id)
		if not live.has(id) or seen.has(id):
			return false
		seen[id] = true
		var proxy: RustSpellEffect3D = live[id]
		if int(f.generation) != int(proxy.runtime_generation) or int(f.epoch) != _epoch:
			return false
		for key: String in ["elapsed", "progress", "ring_scale", "alpha"]:
			if typeof(f.get(key)) not in [TYPE_FLOAT, TYPE_INT] or not is_finite(float(f[key])):
				return false
		var elapsed: float = proxy.elapsed + delta
		var age: float = elapsed - proxy.release_delay - float(proxy.flight.duration)
		var progress: float = clampf(age / WorldEffect3D.LIFETIME_SECONDS, 0.0, 1.0)
		var phase := 3 if progress >= 1.0 else (2 if age >= 0.0 else (1 if elapsed >= proxy.release_delay else 0))
		var events := (1 if not proxy._launched and elapsed >= proxy.release_delay else 0) \
			| (2 if not proxy.impact_started and age >= 0.0 else 0) | (4 if phase == 3 else 0)
		if absf(float(f.elapsed) - elapsed) > 0.00001 or absf(float(f.progress) - progress) > 0.00001 \
				or int(f.phase) != phase or int(f.events) != events \
				or absf(float(f.ring_scale) - (0.55 + (1.0 - pow(1.0-progress, 3.0))*0.6)) > 0.00001 \
				or absf(float(f.alpha) - (1.0-progress)*0.65*SpellPresentation.power_intensity(proxy.power_level)) > 0.00001:
			return false
		for key: String in ["start", "destination", "impact"]:
			if not f.get(key) is Vector3 or not (f[key] as Vector3).is_finite():
				return false
		var anchor: Dictionary = anchors.get(id, {})
		if not anchor.is_empty():
			var v: PackedFloat64Array = anchor.values
			var expected_start: Vector3 = Vector3(v[0], v[1], v[2]) if int(anchor.records[2]) == 1 else proxy.flight.start
			var expected_target: Vector3 = Vector3(v[3], v[4], v[5]) if int(anchor.records[3]) == 1 else proxy.flight.destination
			var expected_impact: Vector3 = Vector3(v[6], v[7], v[8]) if int(anchor.records[3]) == 1 else proxy._impact
			if not (f.start as Vector3).is_equal_approx(expected_start) \
					or not (f.destination as Vector3).is_equal_approx(expected_target) \
					or not (f.impact as Vector3).is_equal_approx(expected_impact):
				return false
		if not f.get("bounds") is AABB or not (f.bounds as AABB).position.is_finite() \
				or not (f.bounds as AABB).size.is_finite() or (f.bounds as AABB).size.x < 0.0 \
				or (f.bounds as AABB).size.y < 0.0 or (f.bounds as AABB).size.z < 0.0:
			return false
		if not _valid_surface(f.get("ribbon"), 336) or not _valid_surface(f.get("glow"), 504):
			return false
		var flight_time: float = elapsed - proxy.release_delay
		var ribbon_count := 0
		var glow_count := 0
		if flight_time < float(proxy.flight.duration) + 0.24:
			glow_count = 18
			if flight_time >= 0.0:
				ribbon_count = 336
				var count := SpellPresentation.power_count(18, proxy.power_level)
				var p := clampf(flight_time / float(proxy.flight.duration), 0.0, 1.0)
				for i: int in count:
					if p - float(i)/count*0.42 > 0.0:
						glow_count += 6
		if (f.ribbon[0] as PackedVector3Array).size() != ribbon_count \
				or (f.glow[0] as PackedVector3Array).size() != glow_count:
			return false
		var bounds: AABB = (f.bounds as AABB).grow(0.0001)
		for surface: Array in [f.ribbon, f.glow]:
			for vertex: Vector3 in surface[0]:
				if not bounds.has_point(vertex):
					return false
	return true

func _valid_surface(surface: Variant, maximum: int) -> bool:
	if not surface is Array or surface.size() != 3 or not surface[0] is PackedVector3Array \
			or not surface[1] is PackedColorArray or not surface[2] is PackedVector2Array:
		return false
	var vertices: PackedVector3Array = surface[0]
	var colors: PackedColorArray = surface[1]
	var uvs: PackedVector2Array = surface[2]
	if vertices.size() > maximum or vertices.size() % 6 != 0 \
			or colors.size() != vertices.size() or uvs.size() != vertices.size():
		return false
	for i: int in vertices.size():
		if not vertices[i].is_finite() or not uvs[i].is_finite() \
				or not is_finite(colors[i].r) or not is_finite(colors[i].g) \
				or not is_finite(colors[i].b) or not is_finite(colors[i].a):
			return false
	return true

func _fail_closed(delta: float, reason: String, advanced: Dictionary = {}) -> void:
	# Snapshot before callbacks: a visibility observer may remove this manager.
	var rows := _proxies.duplicate()
	_proxies.clear()
	_native = null
	_reason = reason
	_fallbacks += 1
	set_process(false)
	for id: int in rows:
		var row: Dictionary = rows[id]
		var proxy: RustSpellEffect3D = row.weak.get_ref() as RustSpellEffect3D
		if is_instance_valid(proxy) and not proxy.is_queued_for_deletion():
			proxy.resume_legacy(0.0 if advanced.has(id) else delta)

func _add_cost(key: String, value: int) -> void:
	_costs[key] = int(_costs.get(key, 0)) + value

func _record_admission(microseconds: int) -> void:
	if _admission_frame != Engine.get_process_frames():
		_admission_frame = Engine.get_process_frames()
		_frame_admission_us = 0
	_frame_admission_us += microseconds
	_add_cost("admission_us",microseconds)

func snapshot() -> Dictionary:
	return {"active": _native != null, "family": "heat_bolt", "reason": _reason,
		"requested": OptimizationProfile.selected("rust_effects"),
		"epoch": _epoch, "live": _proxies.size(), "high_water": _high_water,
		"admitted_rust":_admitted_rust,"admitted_legacy":_admitted_legacy,"events":_events.duplicate(),
		"frames": _frames, "fallbacks": _fallbacks, "last_frame": _last.duplicate(),
		"complete_cumulative_us":int(_costs.get("service_initialization_us",0))
			+int(_costs.get("admission_us",0))+int(_costs.get("advance_total_us",0)),
		"cumulative_costs": _costs.duplicate(), "timing_scope": "main-thread inclusive; nested fields overlap",
		"native": _native.call("runtime_info") if _native != null else {}}

func _exit_tree() -> void:
	if not _discarding:
		_fail_closed(_processing_delta, "manager_exited", _applied)
	else:
		_proxies.clear()
		_native = null
	_controller = null
