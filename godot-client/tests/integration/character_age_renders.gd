extends SceneTree
## Offscreen GPU check: real saved PC/4 appearance, shared/material-value modes,
## two-actor isolation, live edits and exact neutral recovery. Use GPU lock.
const STAGE := preload("res://prototypes/rl_heads/rl_head_stage.gd")
const PC := preload("res://src/actors/portrait_customization.gd")
const AGE := preload("res://src/actors/character_age.gd")
var failures: Array[String] = []
var checks := 0
var out := ""
var stage: Node3D
var camera: Camera3D

func _init() -> void:
	_run.call_deferred()

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)

func _settle() -> void:
	for frame: int in 5:
		await process_frame
	await RenderingServer.frame_post_draw

func _capture(name: String) -> Image:
	await _settle()
	var image := root.get_texture().get_image()
	check(image != null and not image.is_empty(), "capture " + name)
	if image != null:
		image.save_png(out.path_join(name + ".png"))
	return image

func _check_carriers(actor: ReplicatedActor3D, age: int, grey: int) -> void:
	var expected := AGE.packed(age / 100.0, grey / 100.0)
	var skin := 0
	var hair := 0
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if not mesh.has_meta(RLHeadRig.MESH_META): continue
		for index: int in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(index) as ShaderMaterial
			if material == null or not RLHeadLibrary.shader_values(material).has("eye_color"): continue
			var colour: Color = material.get_shader_parameter("eye_color") if RLHeadLibrary.material_values() else mesh.get_instance_shader_parameter("eye_color")
			check(colour.a == expected, "%s carrier %.0f expected %.0f" % [mesh.name, colour.a, expected])
			if material.resource_name == "rl_skin": skin += 1
			if material.resource_name in ["rl_hair_clump", "rl_hair_card", "rl_beard"]: hair += 1
	check(skin > 0 and hair > 0, "age state reaches both skin and hair/beard")

func _quiet(actor: ReplicatedActor3D) -> void:
	STAGE.pose(actor, "Rest", 0.0)
	var rig := actor.rl_head()
	check(rig != null, "real actor has RL head")
	if rig == null: return
	rig.set_portrait_pose(true)
	rig.set_hair_motion_allowed(false)
	rig.expression().set_process(false)
	rig.expression().auto_blink = false
	rig.expression().clear_expression(0.0)
	rig.expression().advance(0.0)

func _saved(base: Dictionary, age: int, grey: int) -> Dictionary:
	var decoded := PC.decode(PC.encode(base.merged({"skin_age": age, "hair_grey": grey}, true), 4), 0)
	return base.merged(decoded, true)

func _run() -> void:
	if DisplayServer.get_name() == "headless":
		print("SKIP character age GPU: a rendered run is required")
		quit()
		return
	out = ProjectSettings.globalize_path("res://../.local/human-age/renders")
	DirAccess.make_dir_recursive_absolute(out)
	root.size = Vector2i(640, 640)
	root.msaa_3d = Viewport.MSAA_4X
	stage = Node3D.new()
	root.add_child(stage)
	STAGE.build(stage)
	camera = Camera3D.new()
	camera.cull_mask = 1
	camera.near = .02
	stage.add_child(camera)
	camera.current = true
	if OS.get_cmdline_user_args().has("--skin-review"):
		await _skin_review()
		quit(0 if failures.is_empty() else 1)
		return
	var modes: Array = [1] if RenderingServer.get_current_rendering_method() == "gl_compatibility" else [0, 1]
	for mode: int in modes:
		RLHeadLibrary.reload_values_switch()
		RLHeadLibrary._values_switch = mode
		for sex: String in ["female", "male"]:
			var prefix := "%s_%s" % ["material" if mode else "instance", sex]
			var base := {"skin": 3 if sex == "female" else 2, "hair": 1, "eyes": 2,
				"facial_hair": 0 if sex == "female" else 4, "hair_module": 3 if sex == "female" else 8}
			var actor := STAGE.spawn(stage, sex, base)
			_quiet(actor)
			var other := STAGE.spawn(stage, sex, _saved(base, 17, 83), {}, ActorRenderQuality.Quality.HIGH, 9301)
			_quiet(other)
			other.hide()
			STAGE.frame(camera, actor, "front")
			await _settle()
			var original := await _capture(prefix + "_omitted")
			if OS.get_cmdline_user_args().has("--baseline-shaders"):
				await _baseline(actor, prefix, original)
			for pair: Vector2i in [Vector2i(0, 0), Vector2i(50, 0), Vector2i(100, 0), Vector2i(0, 50), Vector2i(0, 100)]:
				actor.apply_appearance_variants(_saved(base, pair.x, pair.y))
				_quiet(actor)
				_check_carriers(actor, pair.x, pair.y)
				_check_carriers(other, 17, 83)
				var image := await _capture("%s_age%d_grey%d" % [prefix, pair.x, pair.y])
				if pair == Vector2i.ZERO:
					check(image.get_data() == original.get_data(), prefix + " explicit zero exactly matches old save")
				else:
					check(image.get_data() != original.get_data(), prefix + " slider changes actual pixels " + str(pair))
			for step: int in 12:
				var age := (step * 37) % 101
				var grey := (step * 53) % 101
				actor.apply_appearance_variants(_saved(base, age, grey))
				_check_carriers(actor, age, grey)
				_check_carriers(other, 17, 83)
				await process_frame
			actor.apply_appearance_variants(base)
			_quiet(actor)
			var recovered := await _capture(prefix + "_recovered")
			check(recovered.get_data() == original.get_data(), prefix + " neutral recovery pixel exact")
			actor.free()
			other.free()
			await process_frame
	RLHeadLibrary.reload_values_switch()
	var report := {"checks": checks, "failures": failures, "renderer": RenderingServer.get_current_rendering_method()}
	var file := FileAccess.open(out.path_join("report.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t"))
	print("Character age GPU: %d checks, %d failures; %s" % [checks, failures.size(), out])
	quit(0 if failures.is_empty() else 1)

func _baseline(actor: ReplicatedActor3D, prefix: String, original: Image) -> void:
	var swapped: Array = []
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if not mesh.has_meta(RLHeadRig.MESH_META): continue
		for index: int in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(index) as ShaderMaterial
			if material == null or material.resource_name not in ["rl_skin", "rl_hair_clump", "rl_hair_card", "rl_beard"]: continue
			var source := out.get_base_dir().path_join("baseline_%s.gdshader" % ("skin" if material.resource_name == "rl_skin" else "hair"))
			check(FileAccess.file_exists(source), "pinned pre-age shader is available")
			var defines := ""
			for line: String in material.shader.code.split("\n"):
				if line.begins_with("#define "): defines += line + "\n"
			var shader := Shader.new()
			shader.code = defines + FileAccess.get_file_as_string(source)
			var copy := ShaderMaterial.new()
			copy.shader = shader
			for uniform: Dictionary in shader.get_shader_uniform_list():
				var name := str(uniform.name)
				var value: Variant = material.get_shader_parameter(name)
				if value != null: copy.set_shader_parameter(name, value)
			swapped.append([mesh, index, mesh.get_surface_override_material(index)])
			mesh.set_surface_override_material(index, copy)
	var image := await _capture(prefix + "_pre_age_shader")
	check(image.get_data() == original.get_data(), prefix + " zero effect matches pinned pre-age skin/hair shader pixels")
	for item: Array in swapped:
		(item[0] as MeshInstance3D).set_surface_override_material(item[1], item[2])

func _skin_review() -> void:
	for sex: String in ["female", "male"]:
		var base := {"skin": 3 if sex == "female" else 2, "hair": 0, "eyes": 2, "facial_hair": 0}
		var actor := STAGE.spawn(stage, sex, base)
		_quiet(actor)
		STAGE.frame(camera, actor, "front")
		for age: int in [0, 50, 100]:
			actor.apply_appearance_variants(_saved(base, age, 0))
			_quiet(actor)
			await _capture("skin_review_%s_age%d" % [sex, age])
		actor.free()
		await process_frame
	print("Character skin-age visual review complete: ", out)
