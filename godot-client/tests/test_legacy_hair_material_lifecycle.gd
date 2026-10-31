extends SceneTree
## Rendered regression: run with the supported Godot executable and Vulkan.
## Headless cannot exercise renderer material dependencies and skips explicitly.
const Stage = preload("res://prototypes/rl_heads/rl_head_stage.gd")

class ErrorLog extends Logger:
	var mutex := Mutex.new()
	var errors: Array[Dictionary] = []
	func _log_error(function: String, file: String, line: int, code: String,
			rationale: String, _editor_notify: bool, _error_type: int,
			_script_backtraces: Array[ScriptBacktrace]) -> void:
		mutex.lock()
		errors.append({"function": function, "file": file, "line": line,
			"code": code, "rationale": rationale})
		mutex.unlock()
	func snapshot() -> Array[Dictionary]:
		mutex.lock()
		var result := errors.duplicate(true)
		mutex.unlock()
		return result

var checks := 0
var failures := 0

func _initialize() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func settle(frames: int) -> void:
	for frame: int in frames:
		await process_frame
	await RenderingServer.frame_post_draw

func run() -> void:
	if DisplayServer.get_name() == "headless":
		print("SKIP legacy hair material lifecycle: a rendered Vulkan run is required")
		quit()
		return
	var log := ErrorLog.new()
	OS.add_logger(log)
	var viewport := SubViewport.new()
	viewport.size = Vector2i(256, 256)
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var world := Node3D.new()
	viewport.add_child(world)
	Stage.build(world, "neutral")
	var app := {"hair": AppearanceVariants.pack_hair(1, 11), "hair_module": 1,
		"hair_length": 50, "hair_volume": 50, "hair_detail": 0, "hair_finish": 0,
		"skin": 2, "eyes": 2, "facial_hair": 0}
	var actor := Stage.spawn(world, "female", app, {}, ActorRenderQuality.Quality.HIGH)
	await settle(30)
	Stage.pose(actor, "Rest", 0)
	var target := Stage.head_rest(actor).origin + Vector3.UP * 0.085
	var camera := Camera3D.new()
	camera.fov = 24
	camera.near = 0.02
	world.add_child(camera)
	camera.global_position = target + Stage.face_forward(actor) * 1.15
	camera.look_at(target, Vector3.UP)
	camera.current = true
	# Repeated Classic, finish changes, another style, then quality changes on
	# this same live actor must not leave the renderer holding a freed material.
	var states: Array = [[2, 1, 50, 50, 50], [2, 1, 0, 0, 25],
		[2, 1, 20, 75, 75], [2, 5, 0, 0, 25], [2, 1, 50, 50, 50],
		[0, 5, 50, 50, 50], [1, 1, 50, 50, 50], [2, 1, 50, 50, 50]]
	for values: Array in states:
		app.hair = AppearanceVariants.pack_hair(values[1], 11)
		app.hair_length = values[2]
		app.hair_volume = values[3]
		app.merge(HairFinish.canonical(values[4]), true)
		actor.apply_render_quality(values[0], false)
		actor.apply_appearance_variants(app)
		await settle(10)
		expect(actor.render_quality() == values[0], "requested quality remains active")
		expect(actor._legacy_hair_style_drawn() == values[1], "requested legacy style remains drawn")
		var visible_hair := 0
		for hair: MeshInstance3D in HighHairAppearance._hair_nodes(actor.get_node("NativeModel")):
			if hair.is_visible_in_tree() and hair.mesh != null:
				visible_hair += 1
				expect(hair.mesh.get_surface_count() > 0, "replacement retains a renderable mesh")
				for surface: int in hair.mesh.get_surface_count():
					expect(hair.get_active_material(surface) != null, "replacement retains its material")
		expect(visible_hair > 0, "replacement hair remains visible")
	actor.queue_free()
	await settle(8)
	viewport.queue_free()
	await settle(4)
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	RLHeadLibrary.clear()
	GlbSceneCache.clear()
	var errors := log.snapshot()
	OS.remove_logger(log)
	expect(errors.is_empty(), "style and quality changes produce no renderer errors: " + str(errors))
	print("Legacy hair material lifecycle: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
