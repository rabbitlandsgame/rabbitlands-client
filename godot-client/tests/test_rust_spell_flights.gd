extends SceneTree
const Manager = preload("res://src/world/rust_spell_flights.gd")
const Proxy = preload("res://src/world/rust_spell_effect_3d.gd")
const LegacyFlight = preload("res://src/world/spell_flight_3d.gd")
const Controller = preload("res://src/runtime/client_runtime.gd")
var failures := 0
var compared := 0
var cpp_compared := 0

class FakeController extends ClientRuntimeController:
	var token := RefCounted.new()
	func native_runtime() -> RefCounted:
		return token
	func is_rust_mode() -> bool:
		return token != null

class FakeRuntime extends RefCounted:
	var output: Variant = {}
	var status: Variant = 0
	func get_last_status() -> Variant:
		return status
	func step_batch(_records: PackedInt64Array, _values: PackedFloat64Array,
			_epoch: int, _delta: float, _view: Vector3, _right: Vector3, _up: Vector3) -> Variant:
		return output
	func cancel(_id: int, _generation: int, _epoch: int) -> int:
		return 0

class AdmissionRuntime extends FakeRuntime:
	func spawn_batch(_records: PackedInt64Array, _values: PackedFloat64Array, _epoch: int, _limit: int) -> PackedInt64Array:
		return PackedInt64Array([1])

class FakeImpactGeometry extends RefCounted:
	func build(_effect: int, _power: int, _elapsed: float, _progress: float, _impact: Vector3,
			_color: Color, _size: float, _radius: float, _area: float, _flight: bool, _contact: Vector3) -> Array:
		return [PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.UP]),
			PackedColorArray([Color.WHITE, Color.WHITE, Color.WHITE])]

func _resource_callback_lifetimes() -> void:
	for fault: String in ["mesh-owner", "mesh-epoch", "mesh-reparent", "mesh-manager", "mesh-reentrant",
		"details-owner", "details-epoch", "native-details-owner", "legacy-flight-owner"]:
		var f := _fake_fixture(0.65)
		var observed := {"calls": 0}
		var destination := Node3D.new()
		root.add_child(destination)
		var resource: Resource = f.a._batch_mesh
		if fault.begins_with("details-"):
			resource = f.a._details
		elif fault == "native-details-owner":
			f.a._native_geometry = FakeImpactGeometry.new()
			f.a._native_details = ArrayMesh.new()
			resource = f.a._native_details
		elif fault == "legacy-flight-owner":
			resource = f.a.flight._mesh
			f.native.output = {} # Force the actual legacy fallback draw path.
		var resource_callback := func() -> void:
			observed.calls += 1
			match fault:
				# This proxy's Script method is active: Godot requires queued
				# deletion of that locked object, unlike the native-only rider call.
				"mesh-owner", "details-owner", "native-details-owner", "legacy-flight-owner": f.a.queue_free()
				"mesh-epoch", "details-epoch": f.controller._epoch += 1
				"mesh-reparent": f.a.reparent(destination)
				"mesh-manager": root.remove_child(f.manager)
				"mesh-reentrant": f.manager._process(0.2)
		resource.changed.connect(resource_callback, CONNECT_ONE_SHOT)
		f.manager._process(0.65)
		_expect(observed.calls == 1, "real emitting Resource.changed positive control " + fault)
		_expect(not f.b._batched and absf(f.b.elapsed - 0.65) < 0.00001,
			"unapplied sibling resumes exactly one frame after " + fault)
		if is_instance_valid(f.a) and not f.a.is_queued_for_deletion():
			_expect(not f.a._batched and absf(f.a.elapsed - 0.65) < 0.00001,
				"partially published effect retains its one committed clock after " + fault)
		_expect(f.manager._native == null and f.manager._proxies.is_empty(),
			"callback abort leaves no native-owned proxies after " + fault)
		_destroy_fixture(f)
		destination.free()

func _construction_callback_lifetimes() -> void:
	# Queueing during tree entry is valid while the parent's child list is busy;
	# immediate free/reparent during that notification is not a valid engine API.
	var parent := Node3D.new()
	root.add_child(parent)
	var controller := FakeController.new()
	var manager_seen := {"calls": 0}
	parent.child_entered_tree.connect(func(node: Node) -> void:
		if node.name == Manager.SERVICE_NAME:
			manager_seen.calls += 1
			node.queue_free())
	var previous_family := OS.get_environment("RABBITLANDS_RUST_EFFECTS")
	OS.set_environment("RABBITLANDS_RUST_EFFECTS", "heat_bolt")
	var created := Manager.spawn(controller, parent, {"effect":2,"power":5}, Vector3.ZERO,
		Vector3(5,0,0), null, null, false, 48)
	OS.set_environment("RABBITLANDS_RUST_EFFECTS", previous_family)
	_expect(created == null and manager_seen.calls == 1, "queued entering manager is not initialized")
	parent.free()
	for fault: String in ["queue", "epoch", "controller"]:
		parent = Node3D.new()
		root.add_child(parent)
		var manager := Manager.new()
		parent.add_child(manager)
		controller = FakeController.new()
		manager._controller = controller
		manager._native = AdmissionRuntime.new()
		var seen := {"calls": 0}
		var entry_callback := func(node: Node) -> void:
			if node is RustSpellEffect3D:
				seen.calls += 1
				match fault:
					"queue": node.queue_free()
					"epoch": controller._epoch += 1
					"controller": controller.token = null
		parent.child_entered_tree.connect(entry_callback)
		var proxy := manager.admit({"effect":2,"power":5}, Vector3.ZERO, Vector3(5,0,0), null, null, false, 48)
		_expect(proxy == null and seen.calls == 1 and manager._proxies.is_empty(),
			"tree callback aborts proxy construction before admission: " + fault)
		parent.free()


func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> bool:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	return ok

func _proxy(origin := Vector3.ZERO) -> RustSpellEffect3D:
	var proxy := Proxy.new()
	root.add_child(proxy)
	proxy.configure(2, origin, origin + Vector3(5, 0, 0), 5)
	proxy.configure_timing(0.2, 0.4)
	proxy.begin_batch(proxy.get_instance_id(), 1)
	return proxy

func _empty() -> Array:
	return [PackedVector3Array(), PackedColorArray(), PackedVector2Array()]

func _surface(mesh: Mesh, index: int) -> Array:
	var a := mesh.surface_get_arrays(index)
	return [a[Mesh.ARRAY_VERTEX], a[Mesh.ARRAY_COLOR], a[Mesh.ARRAY_TEX_UV]]

func _submitted(surface: Array) -> Array:
	if (surface[0] as PackedVector3Array).is_empty():
		return _empty()
	# ImmediateMesh readback includes the engine's RGBA8 storage conversion.
	# Use the actual native publication representation on the other side too;
	# raw Rust/C++ arrays are compared separately at the original tolerance.
	var mesh := ArrayMesh.new()
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = surface[0]
	arrays[Mesh.ARRAY_COLOR] = surface[1]
	arrays[Mesh.ARRAY_TEX_UV] = surface[2]
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return _surface(mesh, 0)

func _frame(proxy: RustSpellEffect3D, delta: float) -> Dictionary:
	var time := proxy.elapsed + delta
	proxy.flight.draw_at(time - proxy.release_delay)
	var mesh: Mesh = proxy.flight._mesh_node.mesh
	# While batched the visible mesh is separate; draw_at updates the original.
	mesh = proxy.flight._native_mesh if proxy.flight._native_geometry != null else proxy.flight._mesh
	var ribbon := _empty()
	var glow := _empty()
	if mesh.get_surface_count() == 2:
		ribbon = _surface(mesh, 0)
		glow = _surface(mesh, 1)
	elif mesh.get_surface_count() == 1:
		glow = _surface(mesh, 0)
	var age: float = time - proxy.release_delay - float(proxy.flight.duration)
	var progress := clampf(age / 1.1, 0.0, 1.0)
	var phase := 3 if progress >= 1.0 else (2 if age >= 0.0 else (1 if time >= proxy.release_delay else 0))
	var events := (1 if not proxy._launched and time >= proxy.release_delay else 0) \
		| (2 if not proxy.impact_started and age >= 0.0 else 0) | (4 if phase == 3 else 0)
	return {"id": proxy.get_instance_id(), "generation": proxy.runtime_generation,
		"epoch": 1, "phase": phase, "events": events, "elapsed": time,
		"progress": progress, "ring_scale": 0.55 + (1.0-pow(1.0-progress, 3.0))*0.6,
		"alpha": (1.0-progress)*0.65*SpellPresentation.power_intensity(proxy.power_level),
		"start": proxy.flight.start, "destination": proxy.flight.destination,
		"impact": proxy._impact, "bounds": AABB(Vector3(-100,-100,-100),Vector3(200,200,200)),
		"ribbon": ribbon, "glow": glow}

func _fake_fixture(delta: float) -> Dictionary:
	var manager := Manager.new()
	root.add_child(manager)
	manager.set_process(false)
	var controller := FakeController.new()
	manager._controller = controller
	var native := FakeRuntime.new()
	manager._native = native
	var a := _proxy()
	var b := _proxy(Vector3(0,0,2))
	manager._proxies[a.get_instance_id()] = {"weak": weakref(a), "generation": a.runtime_generation}
	manager._proxies[b.get_instance_id()] = {"weak": weakref(b), "generation": b.runtime_generation}
	var f1 := _frame(a, delta)
	var f2 := _frame(b, delta)
	native.output = {"abi":1, "epoch":1, "frames":[f1,f2], "core_us":0,
		"conversion_us":0, "adapter_us":0, "vertices":0}
	return {"manager":manager, "controller":controller, "native":native, "a":a, "b":b}

func _destroy_fixture(f: Dictionary) -> void:
	for key: String in ["a", "b"]:
		if is_instance_valid(f[key]):
			(f[key] as Node).free()
	if is_instance_valid(f.manager):
		(f.manager as Node).free()

func _bad_outputs() -> void:
	for fault: String in ["type", "missing", "duplicate", "id", "generation", "epoch",
		"phase", "events", "clock", "nan", "empty-geometry", "uv", "bounds", "status", "status-type"]:
		var f := _fake_fixture(0.65)
		var native: FakeRuntime = f.native
		var bad: Dictionary = native.output.frames[1]
		match fault:
			"type": native.output = []
			"missing": native.output.frames.pop_back()
			"duplicate": native.output.frames[1] = native.output.frames[0]
			"id": bad.id = -1
			"generation": bad.generation += 1
			"epoch": bad.epoch += 1
			"phase": bad.phase = 0
			"events": bad.events = 0
			"clock": bad.elapsed += 0.01
			"nan": bad.alpha = NAN
			"empty-geometry": bad.ribbon = _empty()
			"uv": bad.glow[2] = PackedVector2Array()
			"bounds": bad.bounds = AABB(Vector3.ZERO, Vector3(-1,-1,-1))
			"status": native.status = 1
			"status-type": native.status = "invalid"
		f.manager._process(0.65)
		_expect(f.manager._native == null and f.manager._proxies.is_empty(),
			"malformed %s rejects complete batch" % fault)
		for key: String in ["a", "b"]:
			var proxy: RustSpellEffect3D = f[key]
			_expect(not proxy._batched and absf(proxy.elapsed - 0.65) < 0.00001
				and proxy.impact_started and proxy.flight._mesh_node.mesh == proxy._original_flight_mesh,
				"malformed %s resumes %s legacy exactly once" % [fault,key])
		_destroy_fixture(f)

func _reentrant_lifecycle() -> void:
	var epoch := _fake_fixture(0.65)
	epoch.a._ring.visibility_changed.connect(func() -> void:
		epoch.controller._epoch += 1, CONNECT_ONE_SHOT)
	epoch.manager._process(0.65)
	_expect(epoch.manager._native == null and not epoch.a._batched and not epoch.b._batched,
		"arrival observer epoch change rejects remaining submissions")
	_expect(absf(epoch.a.elapsed - 0.65) < 0.00001 and absf(epoch.b.elapsed - 0.65) < 0.00001,
		"reentrant epoch fallback neither duplicates nor drops this frame")
	_destroy_fixture(epoch)
	var removal := _fake_fixture(0.65)
	removal.a._ring.visibility_changed.connect(func() -> void:
		root.remove_child(removal.manager), CONNECT_ONE_SHOT)
	removal.manager._process(0.65)
	_expect(not removal.a._batched and not removal.b._batched
		and absf(removal.a.elapsed - 0.65) < 0.00001 and absf(removal.b.elapsed - 0.65) < 0.00001,
		"manager-only removal resumes surviving siblings without a frozen clock")
	_destroy_fixture(removal)
	var reparented := _fake_fixture(0.65)
	var other_world := Node3D.new()
	root.add_child(other_world)
	reparented.a._ring.visibility_changed.connect(func() -> void:
		reparented.b.reparent(other_world), CONNECT_ONE_SHOT)
	reparented.manager._process(0.65)
	_expect(reparented.manager._native == null and not reparented.b._batched
		and absf(reparented.b.elapsed-0.65) < 0.00001,
		"another world's proxy cannot receive an old local-space frame")
	_destroy_fixture(reparented)
	other_world.free()
	var reused := _fake_fixture(0.65)
	reused.a._ring.visibility_changed.connect(func() -> void:
		reused.b.runtime_generation += 1, CONNECT_ONE_SHOT)
	reused.manager._process(0.65)
	_expect(reused.manager._native == null and not reused.b._batched,
		"submission rechecks a generation changed by an earlier callback")
	_destroy_fixture(reused)

func _valid_manager_commit() -> void:
	var f := _fake_fixture(0.3)
	var arrivals := [0]
	f.a._ring.visibility_changed.connect(func() -> void: arrivals[0] += 1)
	f.manager._process(0.3)
	_expect(f.a._batched and absf(f.a.elapsed-0.3) < 0.00001 and not f.a.impact_started
		and f.a._batch_mesh.get_surface_count() == 2,"valid coarse batch publishes both ribbon/glow surfaces")
	_expect(f.manager._last.frame == Engine.get_process_frames(),"submission occurs in the current frame")
	_expect(f.a._batch_mesh.surface_get_material(0) == f.a.flight._ribbon_material
		and f.a._batch_mesh.surface_get_material(1) == f.a.flight._glow_material,
		"per-effect material, transparency and render-priority ownership preserved")
	for delta: float in [0.4,0.2]:
		f.native.output.frames = [_frame(f.a,delta),_frame(f.b,delta)]
		f.manager._process(delta)
	_expect(arrivals[0] == 1 and f.a.impact_started and absf(f.a.elapsed-0.9) < 0.00001,
		"arrival is applied once while subsequent frames preserve impact state")
	_expect(f.manager._events == {"releases":2,"arrivals":2,"expiries":0},
		"manager publishes exact release/arrival counts for the whole batch")
	_destroy_fixture(f)

func _compare(expected: Array, actual: Array, label: String) -> void:
	if not _expect(expected.size() == 3 and actual.size() == 3, label + " slots"):
		return
	var e: PackedVector3Array = expected[0]
	var a: PackedVector3Array = actual[0]
	if not _expect(e.size() == a.size(), label + " vertex count/order"):
		return
	var colors_e: PackedColorArray = expected[1]
	var colors_a: PackedColorArray = actual[1]
	var good: bool = expected[2] == actual[2] and colors_e.size() == colors_a.size()
	var maximum_position := 0.0
	var maximum_color := 0.0
	for i: int in e.size():
		var distance := e[i].distance_to(a[i])
		maximum_position = maxf(maximum_position, distance)
		good = good and distance <= 0.0005
		if colors_e.size() == colors_a.size():
			var c: Color = colors_e[i] - colors_a[i]
			maximum_color = maxf(maximum_color, maxf(maxf(absf(c.r), absf(c.g)), maxf(absf(c.b), absf(c.a))))
			good = good and absf(c.r) < 0.00002 and absf(c.g) < 0.00002 \
				and absf(c.b) < 0.00002 and absf(c.a) < 0.00002
	if not good:
		print("FLIGHT_GEOMETRY_DIFFERENCE ", JSON.stringify({"label":label,"position":maximum_position,"color":maximum_color,"uvEqual":expected[2] == actual[2],"expectedColor":str(colors_e[0]) if not colors_e.is_empty() else "empty","actualColor":str(colors_a[0]) if not colors_a.is_empty() else "empty"}))
	_expect(good, label + " positions <=0.5mm, colors <=2e-5, UVs exact")

func _native_geometry(native: RefCounted) -> void:
	var epoch := 1
	var cpp: RefCounted = ClassDB.instantiate("NativeSpellFlightGeometry") as RefCounted \
		if ClassDB.class_exists("NativeSpellFlightGeometry") else null
	if OS.get_cmdline_user_args().has("--expect-cpp-comparator"):
		_expect(cpp != null and str(native.call("runtime_info").get("cpp_comparator_provider","")) == "client_runtime",
			"requested unchanged C++ comparator comes from verified runtime payload")
	var ends: Array[Vector3] = [Vector3(13,4,-8), Vector3(-4,20,1), Vector3(-4,2,1)]
	for power: int in range(1,11):
		for end: Vector3 in ends:
			for time: float in [-0.1, 0.0, 0.18, 0.42, 0.65]:
				epoch += 1
				_expect(int(native.call("reset_epoch", epoch)) == 0, "fresh geometry epoch")
				var flight := LegacyFlight.new()
				root.add_child(flight)
				flight.configure(2, Color(0.2,0.7,0.9,0.8), Vector3(-4,2,1), end, power)
				flight.duration = 0.4
				var spec := PackedFloat64Array([-4,2,1,end.x,end.y,end.z,end.x,end.y-1,end.z,
					0.2,0.7,0.9,0.8,0.2,0.4])
				var admitted: PackedInt64Array = native.call("spawn_batch", PackedInt64Array([1,1,2,power,0]),spec,epoch,48)
				_expect(admitted == PackedInt64Array([1]), "geometry flight admitted")
				var result: Dictionary = native.call("step_batch", PackedInt64Array(), PackedFloat64Array(),epoch,time+0.2,
					Vector3.BACK,Vector3.RIGHT,Vector3.UP)
				if not _expect(result.get("frames", []).size() == 1, "native geometry publishes one frame"):
					flight.free()
					continue
				var frame: Dictionary = result.frames[0]
				flight.draw_at(time)
				var mesh: Mesh = flight._mesh_node.mesh
				var ribbon := _surface(mesh,0) if mesh.get_surface_count() == 2 else _empty()
				var glow := _surface(mesh,mesh.get_surface_count()-1) if mesh.get_surface_count() > 0 else _empty()
				_compare(ribbon,_submitted(frame.ribbon),"power%d time%.2f ribbon" % [power,time])
				_compare(glow,_submitted(frame.glow),"power%d time%.2f glow" % [power,time])
				compared += 1
				if cpp != null and time < 0.64:
					var arrays: Array = cpp.call("build",2,flight.tint,flight.start,flight.destination,flight._side,flight._up,
						flight._path_spread,flight._path_arc,flight._tail_fraction,0.4,time,Vector3.BACK,Vector3.RIGHT,Vector3.UP,
						SpellPresentation.power_scale(power),SpellPresentation.power_count(18,power))
					_compare([arrays[0],arrays[1],arrays[2]],frame.ribbon,"C++ ribbon")
					_compare([arrays[3],arrays[4],arrays[5]],frame.glow,"C++ glow")
					cpp_compared += 1
				flight.free()

func _native_lifecycle(native: RefCounted) -> void:
	_expect(int(native.call("reset_epoch",1000)) == 0,"lifecycle epoch")
	var spec := PackedFloat64Array([0,1,0, 5,1,0, 5,0,0, 1,0.42,0.18,1, 0.2,0.4])
	var decisions: PackedInt64Array = native.call("spawn_batch",PackedInt64Array([1,1,2,5,0, 2,1,2,5,0, 3,1,2,5,1]),
		spec + spec + spec,1000,1)
	_expect(decisions == PackedInt64Array([1,0,1]),"normal cap and priority bypass")
	var seen := 0
	for delta: float in [0.1,0.1,0.401,1.1]:
		var result: Dictionary = native.call("step_batch",PackedInt64Array(),PackedFloat64Array(),1000,delta,
			Vector3.BACK,Vector3.RIGHT,Vector3.UP)
		_expect(result.frames.size() == 2,"both admitted flights publish together")
		for frame: Dictionary in result.frames:
			if frame.id == 1:
				_expect((seen & int(frame.events)) == 0,"lifecycle events occur exactly once")
				seen |= int(frame.events)
	_expect(seen == 7 and int(native.call("runtime_info").live) == 0,"release arrival and expiry all occur")
	_expect(int(native.call("cancel",1,1,1000)) == 2,"expired identity cannot be canceled again")
	_expect(int(native.call("reset_epoch",1001)) == 0,"reset advances session")
	_expect((native.call("spawn_batch",PackedInt64Array([1,1,2,5,0]),spec,1000,48) as PackedInt64Array).is_empty()
		and int(native.call("get_last_status")) == 2,"stale session is rejected without engine error")
	var bad := spec.duplicate()
	bad[14] = NAN
	_expect((native.call("spawn_batch",PackedInt64Array([1,1,2,5,0, 2,1,2,5,0]),spec+bad,1001,48) as PackedInt64Array).is_empty()
		and int(native.call("runtime_info").live) == 0,"invalid whole admission leaves no partial flight")
	_expect((native.call("spawn_batch",PackedInt64Array([1,7,2,5,0]),spec,1001,48) as PackedInt64Array) == PackedInt64Array([1]),
		"fresh generated identity admits")
	var anchors := PackedInt64Array([1,7,1,1])
	var positions := PackedFloat64Array([1,2,3, 7,2,0, 7,1,0])
	var moved: Dictionary = native.call("step_batch",anchors,positions,1001,0.2,Vector3.BACK,Vector3.RIGHT,Vector3.UP)
	_expect(moved.frames[0].start == Vector3(1,2,3) and moved.frames[0].destination == Vector3(7,2,0),
		"source and target anchors update before release")
	var removed := PackedFloat64Array([99,99,99, 99,99,99, 99,99,99])
	var retained: Dictionary = native.call("step_batch",PackedInt64Array([1,7,1,0]),removed,1001,0.1,
		Vector3.BACK,Vector3.RIGHT,Vector3.UP)
	_expect(retained.frames[0].start == Vector3(1,2,3) and retained.frames[0].destination == Vector3(7,2,0),
		"released source freezes and removed target retains last endpoint")
	var before: int = int(native.call("runtime_info").frames)
	positions[0] = NAN
	var invalid: Dictionary = native.call("step_batch",anchors,positions,1001,0.5,Vector3.BACK,Vector3.RIGHT,Vector3.UP)
	_expect(invalid.is_empty() and int(native.call("get_last_status")) == 1
		and int(native.call("runtime_info").frames) == before,"invalid whole step cannot advance a clock or publish partial geometry")
	var unchanged: Dictionary = native.call("step_batch",PackedInt64Array(),PackedFloat64Array(),1001,0.0,
		Vector3.BACK,Vector3.RIGHT,Vector3.UP)
	_expect(absf(float(unchanged.frames[0].elapsed)-0.3) < 0.00001,"rejected delta was not consumed")
	_expect(int(native.call("cancel",1,6,1001)) == 2 and int(native.call("cancel",1,7,1001)) == 0,
		"only current generation can cancel its flight")
	_expect((native.call("spawn_batch",PackedInt64Array([1,8,2,5,0]),spec,1001,48) as PackedInt64Array) == PackedInt64Array([1]),
		"canceled slot can be reused under a new generation")
	_expect((native.call("step_batch",PackedInt64Array([1,7,0,0]),removed,1001,0.0,
		Vector3.BACK,Vector3.RIGHT,Vector3.UP) as Dictionary).is_empty() and int(native.call("get_last_status")) == 2,
		"old generation cannot control a reused slot")

func _foreign_thread_rejection(native: RefCounted) -> void:
	var before: Dictionary = native.call("runtime_info")
	var before_status := int(native.call("get_last_status"))
	var worker := Thread.new()
	var started := worker.start(func() -> Dictionary:
		return {"info": native.call("runtime_info"), "status": native.call("get_last_status"),
			"reset": native.call("reset_epoch", 5000), "cancel": native.call("cancel", 1, 1, 1),
			"spawn": native.call("spawn_batch", PackedInt64Array(), PackedFloat64Array(), 1, 48),
			"step": native.call("step_batch", PackedInt64Array(), PackedFloat64Array(), 1, 0.0,
				Vector3.BACK, Vector3.RIGHT, Vector3.UP)})
	_expect(started == OK, "foreign-thread rejection probe starts")
	if started != OK:
		return
	var result: Dictionary = worker.wait_to_finish()
	_expect(result.info == {"ready":false, "status":1, "reason":"wrong_thread"}
		and result.status == 1 and result.reset == 1 and result.cancel == 1
		and (result.spawn as PackedInt64Array).is_empty() and (result.step as Dictionary).is_empty(),
		"every foreign-thread API rejects without mutable diagnostics access")
	_expect(native.call("runtime_info") == before and int(native.call("get_last_status")) == before_status,
		"foreign-thread misuse does not mutate owner state, status, counters or epoch")


func _run() -> void:
	var old_runtime := OS.get_environment("RABBITLANDS_CLIENT_RUNTIME")
	var old_presentation := OS.get_environment("ELORIA_NATIVE_PRESENTATION")
	OS.set_environment("ELORIA_NATIVE_PRESENTATION","")
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.current = true
	_resource_callback_lifetimes()
	_construction_callback_lifetimes()
	_bad_outputs()
	_reentrant_lifecycle()
	_valid_manager_commit()
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME","rust")
	var controller := Controller.new()
	controller.initialize()
	var available: bool = controller.is_rust_mode() and ClassDB.class_exists("RabbitLandsSpellFlightRuntime")
	if OS.get_cmdline_user_args().has("--expect-native"):
		_expect(available,"requested native flight capability is verified and loaded")
	if available:
		var native: RefCounted = ClassDB.instantiate("RabbitLandsSpellFlightRuntime") as RefCounted
		_foreign_thread_rejection(native)
		_native_geometry(native)
		_native_lifecycle(native)
		native = null
	else:
		print("SKIP actual Rust flight tests: optional capability absent")
	controller.close()
	camera.free()
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME",old_runtime)
	OS.set_environment("ELORIA_NATIVE_PRESENTATION",old_presentation)
	print("Rust spell flights: ","PASS" if failures == 0 else "FAIL",
		" GD geometry cases=",compared," C++ cases=",cpp_compared)
	quit(failures)
