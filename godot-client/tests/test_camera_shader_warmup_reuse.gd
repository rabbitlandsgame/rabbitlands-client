extends SceneTree
## A world remembers, for the session, the content its full warm-up sweeps
## drew. An arrival that adds none of it - a door back out to a parked map -
## draws the short sweep; anything new draws the full one.

const Warmup := preload("res://src/world/camera_shader_warmup.gd")
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func _mesh(parent: Node3D, material: Material, at: Vector3) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.material = material
	var node := MeshInstance3D.new()
	node.mesh = mesh
	node.position = at
	parent.add_child(node)
	return node

func _sweep(warm: Warmup) -> void:
	var first: int = warm._last_draw
	for view: int in range(1, warm.views() + 1):
		warm.advance(first + view * Warmup.FRAMES_PER_VIEW)

func _run() -> void:
	var holder := Node3D.new()
	root.add_child(holder)
	var world := Node3D.new()
	holder.add_child(world)
	var source := Camera3D.new()
	root.add_child(source)
	source.position = Vector3(0, 22, 13)
	source.look_at(Vector3.ZERO)
	source.cull_mask = 3
	source.make_current()
	var stone := StandardMaterial3D.new()
	var water := ShaderMaterial.new()
	water.shader = Shader.new()
	water.shader.code = "shader_type spatial;"
	_mesh(world, stone, Vector3(4, 0, 0))
	_mesh(world, water, Vector3(-4, 0, 0))
	var warm := Warmup.new()
	var full := _full_views()
	expect(warm.begin(world, source, Vector3.ZERO) and warm.views() == full
		and not warm.snapshot().reused, "a world's first arrival draws the full sweep")
	_sweep(warm)
	expect(not warm.active() and warm.completed(world, Vector3.ZERO), "the full sweep completes")

	# A door back out: the parked world is taken out of the tree and comes back
	# at the door, far from where it was warmed.
	holder.remove_child(world)
	holder.add_child(world)
	var door := Vector3(40, 0, 0)
	source.position = door + Vector3(0, 22, 13)
	expect(warm.begin(world, source, door) and warm.snapshot().reused
		and warm.views() == full / 4 and warm.snapshot().new_keys == 0,
		"a parked world back at a new focus with nothing new draws a quarter of the views")
	_sweep(warm)
	expect(not warm.active() and warm.completed(world, door),
		"the short sweep completes and records its focus")

	# Same shader, new parameters: the same variants.
	var pond := ShaderMaterial.new()
	pond.shader = water.shader
	_mesh(world, pond, door + Vector3(3, 0, 0))
	var bridge := door + Vector3(60, 0, 0)
	source.position = bridge + Vector3(0, 22, 13)
	expect(warm.begin(world, source, bridge) and warm.snapshot().reused,
		"another material on a shader already drawn adds nothing")
	warm.cancel()

	# A new material, or a new vertex format, is new content.
	var moss := StandardMaterial3D.new()
	var mossy := _mesh(world, moss, bridge + Vector3(2, 0, 0))
	expect(warm.begin(world, source, bridge) and not warm.snapshot().reused
		and warm.views() == full and warm.snapshot().new_keys > 0,
		"a material never drawn draws the full sweep")
	warm.cancel()
	expect(warm.begin(world, source, bridge) and not warm.snapshot().reused,
		"a cancelled full sweep vouches for nothing")
	_sweep(warm)
	var far := bridge + Vector3(100, 0, 0)
	source.position = far + Vector3(0, 22, 13)
	expect(warm.begin(world, source, far) and warm.snapshot().reused,
		"after a full sweep the new material is covered too")
	warm.cancel()

	# A lamp lights what stands near it with variants of its own.
	var lamp := OmniLight3D.new()
	lamp.position = far + Vector3(0, 3, 0)
	world.add_child(lamp)
	expect(warm.begin(world, source, far) and not warm.snapshot().reused,
		"a light never drawn draws the full sweep")
	_sweep(warm)
	lamp.queue_free()
	await process_frame

	# A mesh with a visibility range is content only where a sweep camera is
	# inside that range, and is covered only once every camera of a sweep was.
	var cairn := StandardMaterial3D.new()
	var distant := _mesh(world, cairn, Vector3(-400, 0, 0))
	distant.visibility_range_end = 50.0
	var start := Vector3.ZERO
	source.position = start + Vector3(0, 22, 13)
	expect(warm.begin(world, source, start) and warm.snapshot().reused,
		"a ranged mesh no sweep camera here could reach is not content here")
	warm.cancel()
	var hill := Vector3(-400, 0, 30)
	source.position = hill + Vector3(0, 22, 13)
	expect(warm.begin(world, source, hill) and not warm.snapshot().reused,
		"a ranged mesh first reached from here was never drawn, so the full sweep runs")
	_sweep(warm)
	var beside := Vector3(-380, 0, 0)
	source.position = beside + Vector3(0, 22, 13)
	expect(warm.begin(world, source, beside) and not warm.snapshot().reused,
		"a sweep that only might have drawn it does not vouch for it")
	_sweep(warm)
	var next := Vector3(-350, 0, 0)
	source.position = next + Vector3(0, 22, 13)
	expect(warm.begin(world, source, next) and warm.snapshot().reused,
		"once a sweep surely drew it, it is covered")
	warm.cancel()

	# Hidden content cannot be drawn, so it neither needs nor earns coverage.
	mossy.hide()
	var hidden := StandardMaterial3D.new()
	_mesh(world, hidden, next).hide()
	expect(warm.begin(world, source, next) and warm.snapshot().reused,
		"hidden meshes are not content a sweep could draw")
	warm.cancel()

	# The timed-out sweep stops early and vouches for nothing.
	var late := StandardMaterial3D.new()
	_mesh(world, late, next)
	expect(warm.begin(world, source, next) and not warm.snapshot().reused, "new content again")
	warm._started = Time.get_ticks_msec() - Warmup.LIMIT_MSEC - 1
	warm.advance()
	expect(not warm.active(), "the time limit ends the sweep")
	var further := next + Vector3(0, 0, 40)
	source.position = further + Vector3(0, 22, 13)
	expect(warm.begin(world, source, further) and not warm.snapshot().reused,
		"a timed-out sweep leaves its content uncovered")
	warm.cancel()

	var previous := OS.get_environment(Warmup.REUSE_VARIABLE)
	OS.set_environment(Warmup.REUSE_VARIABLE, "0")
	_sweep_once(warm, world, source, further)
	var again := further + Vector3(0, 0, 40)
	source.position = again + Vector3(0, 22, 13)
	expect(warm.begin(world, source, again) and not warm.snapshot().reused
		and warm.views() == full, "ELORIA_CAMERA_WARMUP_REUSE=0 always draws the full sweep")
	warm.cancel()
	OS.set_environment(Warmup.REUSE_VARIABLE, previous)

	var other := Node3D.new()
	root.add_child(other)
	_mesh(other, stone, Vector3.ZERO)
	expect(warm.begin(other, source, again) and not warm.snapshot().reused,
		"coverage belongs to its own world")
	_sweep(warm)
	world.free()
	var elsewhere := again + Vector3(0, 0, 40)
	source.position = elsewhere + Vector3(0, 22, 13)
	expect(warm.begin(other, source, elsewhere) and warm._coverage.size() == 1,
		"a freed world's record is dropped")
	warm.cancel()
	expect(not Warmup.drawing(), "no warm-up camera is left drawing")
	_check_sky_keys()
	_measure_scan(warm, source)
	other.free()
	source.free()
	holder.free()
	await process_frame
	print("camera shader warmup reuse tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

## Every map bind builds a new environment and sky; the same kind of sky is
## the same content, another kind is not.
func _check_sky_keys() -> void:
	var key := func(sky_material: Material) -> String:
		var camera := Camera3D.new()
		camera.environment = Environment.new()
		camera.environment.background_mode = Environment.BG_SKY
		camera.environment.sky = Sky.new()
		camera.environment.sky.sky_material = sky_material
		root.add_child(camera)
		var result: String = Warmup._environment_key(camera)
		camera.free()
		return result
	expect(key.call(ProceduralSkyMaterial.new()) == key.call(ProceduralSkyMaterial.new()),
		"a rebuilt procedural sky is the same content")
	var painted := ShaderMaterial.new()
	painted.shader = Shader.new()
	painted.shader.code = "shader_type sky;"
	expect(key.call(painted) != key.call(ProceduralSkyMaterial.new()),
		"a painted sky is not")

## What reading a large world costs on arrival: informational.
func _measure_scan(warm: Warmup, source: Camera3D) -> void:
	var big := Node3D.new()
	root.add_child(big)
	var materials: Array[Material] = []
	for index: int in 64:
		materials.append(StandardMaterial3D.new())
	for index: int in 5000:
		var cell := _mesh(big, materials[index % materials.size()],
			Vector3(index % 100, 0, index / 100) * 4.0)
		cell.visibility_range_end = 300.0 if index % 3 == 0 else 0.0
	source.position = Vector3(0, 22, 13)
	var started := Time.get_ticks_usec()
	var content: Array[Dictionary] = warm._content(big, source)
	print("info: content scan of 5000 meshes %.1f ms, %d keys" % [
		(Time.get_ticks_usec() - started) / 1000.0, content[0].size()])
	big.free()

func _sweep_once(warm: Warmup, world: Node3D, source: Camera3D, focus: Vector3) -> void:
	if warm.begin(world, source, focus):
		_sweep(warm)

func _full_views() -> int:
	return Warmup.PITCHES.size() * (360 / Warmup.YAW_STEP)
