extends SceneTree
## Exercise browser policy/lifecycle with native scene objects, without a GPU.
const Warmup := preload("res://src/world/camera_shader_warmup.gd")
class BrowserWarmup extends Warmup:
	func _is_web() -> bool: return true

var checks := 0
var failures := 0

func _initialize() -> void: _run.call_deferred()

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)

func _run() -> void:
	var previous_mode := OS.get_environment("ELORIA_CAMERA_WARMUP_VIEWPORT")
	var previous_uncap := OS.get_environment("ELORIA_CAMERA_WARMUP_UNCAP")
	var previous_frames := OS.get_environment("ELORIA_CAMERA_WARMUP_FRAMES")
	OS.set_environment("ELORIA_CAMERA_WARMUP_VIEWPORT", "small")
	OS.set_environment("ELORIA_CAMERA_WARMUP_UNCAP", "1")
	OS.set_environment("ELORIA_CAMERA_WARMUP_FRAMES", "")
	var original_cap := Engine.max_fps
	Engine.max_fps = 60
	var viewport := SubViewport.new()
	viewport.size = Vector2i(1280, 720)
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var world := Node3D.new()
	viewport.add_child(world)
	var mesh := MeshInstance3D.new()
	mesh.mesh = BoxMesh.new()
	mesh.material_override = StandardMaterial3D.new()
	world.add_child(mesh)
	var source := Camera3D.new()
	world.add_child(source)
	source.position = Vector3(0, 12, 8)
	source.look_at(Vector3.ZERO)
	source.make_current()
	var framing := source.global_transform
	var warm := BrowserWarmup.new()
	expect(warm.begin(world, source, Vector3.ZERO), "browser representative warm-up starts")
	expect(warm.views() == 24 and warm.snapshot().policy == "browser_representative",
		"browser draws 24 representative views rather than the native 240")
	expect(warm.snapshot().limit_msec == 5000 and warm.snapshot().frames_per_view == 2,
		"browser keeps two actual draws per view with a five-second ceiling")
	expect(warm._credit.is_empty() and not warm.snapshot().reused,
		"representative sweep never claims full content coverage or native reuse")
	expect(Engine.max_fps == 0 and viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"small warm-up suspends the full-resolution viewport and preserves uncapping")
	var first: int = warm._last_draw
	warm.advance(first + 1)
	expect(warm._view == 0, "one draw cannot qualify a representative view")
	for view: int in range(1, 25): warm.advance(first + view * 2)
	expect(not warm.active() and warm.completed(world, Vector3.ZERO),
		"all 48 draws finish and remember this arrival")
	expect(warm._coverage.is_empty(), "completed browser sweep does not credit full world coverage")
	expect(Engine.max_fps == 60 and viewport.render_target_update_mode == SubViewport.UPDATE_ALWAYS,
		"completion restores frame cap and original rendering")
	expect(source.global_transform == framing and viewport.get_camera_3d() == source,
		"completion preserves the player's camera framing")
	expect(not warm.begin(world, source, Vector3.ZERO), "same arrival does not sweep repeatedly")
	var far := Vector3(100, 0, 0)
	expect(warm.begin(world, source, far) and warm.views() == 24 and not warm.snapshot().reused,
		"new destination keeps representative policy without pretending full coverage")
	warm._started = Time.get_ticks_msec() - Warmup.WEB_LIMIT_MSEC - 1
	warm.advance(warm._last_draw)
	expect(not warm.active() and warm.snapshot().timed_out and warm._view == 0,
		"timeout releases the curtain even when rendering has not advanced")
	expect(warm._coverage.is_empty() and Engine.max_fps == 60
		and viewport.render_target_update_mode == SubViewport.UPDATE_ALWAYS,
		"timeout credits no coverage and restores rendering/cap")
	var another := Vector3(200, 0, 0)
	expect(warm.begin(world, source, another), "browser can prepare a later arrival")
	warm.cancel()
	expect(not warm.completed(world, another) and not Warmup.drawing(),
		"cancelled work records no completion and leaves no drawing camera")
	expect(warm.begin(world, source, another), "cancelled arrival can retry")
	var cutscene := Camera3D.new()
	world.add_child(cutscene)
	cutscene.make_current()
	warm.advance(warm._last_draw + 2)
	expect(not warm.active() and viewport.get_camera_3d() == cutscene and Engine.max_fps == 60,
		"camera takeover cancels the browser warm-up without stealing the camera")
	source.make_current()
	expect(warm.begin(world, source, another), "source destruction cleanup can be checked")
	source.free()
	warm.advance()
	expect(not warm.active() and Engine.max_fps == 60
		and viewport.render_target_update_mode == SubViewport.UPDATE_ALWAYS,
		"source destruction restores surviving viewport/cap")
	viewport.free()
	await process_frame
	Engine.max_fps = original_cap
	OS.set_environment("ELORIA_CAMERA_WARMUP_VIEWPORT", previous_mode)
	OS.set_environment("ELORIA_CAMERA_WARMUP_UNCAP", previous_uncap)
	OS.set_environment("ELORIA_CAMERA_WARMUP_FRAMES", previous_frames)
	print("browser camera shader warmup: %d checks; %d failures" % [checks, failures])
	quit(failures)
