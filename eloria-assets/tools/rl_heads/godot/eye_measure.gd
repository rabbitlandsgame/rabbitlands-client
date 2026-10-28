extends SceneTree
## Eye measurement renders (local tool, not shipped). Works from any checkout
## that has prototypes/rl_heads/rl_head_stage.gd (develop primary or the RL
## prototype worktree): run with --script <absolute path to this file>.
##
## For each look and view it writes:
##   <name>.png       the normal still (stage lighting)
##   <name>_mask.png  a mask still: background black, skin and every other
##                    occluder flat magenta (unshaded, depth-writing), hair,
##                    brows, lashes, cornea and beard discarded, eyes drawn
##                    UNSHADED with their own textures (catchlight off)
##   <name>.json      camera, look and the RL landmarks projected to pixels
##
## Options:
##   --out <abs dir>
##   --looks dev:Mira,rl:mira|eye_style=1|eye_size=-1    (dev: needs develop)
##   --views eyes,front     rl_head_stage.gd VIEWS names
##   --expressions neutral  RL expression presets / ex_ shapes (RL heads only)
##   --quality high|medium|low
##   --size 800x800
##   --appearance '{"hair":0}'   merged into dev: looks

const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")

var args: Dictionary = {}
var stage: Node3D
var camera: Camera3D
var world: WorldEnvironment
var out_dir := ""
var report: Array = []
var _discard_material: ShaderMaterial
var _skin_material: StandardMaterial3D
var _black_env: Environment


func _init() -> void:
	var values := OS.get_cmdline_user_args()
	for index in range(0, values.size() - 1, 2):
		args[values[index].trim_prefix("--")] = values[index + 1]
	call_deferred("_run")


func _list(key: String, fallback: String) -> PackedStringArray:
	var result := PackedStringArray()
	for part: String in str(args.get(key, fallback)).split(",", false):
		result.append(part.strip_edges())
	return result


func _run() -> void:
	var size_parts := str(args.get("size", "800x800")).split("x")
	root.size = Vector2i(int(size_parts[0]), int(size_parts[1]))
	root.msaa_3d = Viewport.MSAA_4X
	stage = Node3D.new()
	root.add_child(stage)
	var built: Dictionary = Stage.build(stage, str(args.get("look", "neutral")))
	world = built["environment"] as WorldEnvironment
	camera = Camera3D.new()
	camera.cull_mask = 1
	camera.near = 0.05
	stage.add_child(camera)
	camera.current = true
	out_dir = str(args.get("out", ""))
	DirAccess.make_dir_recursive_absolute(out_dir)
	_make_materials()
	var quality := maxi(0, ActorRenderQuality.QUALITY_NAMES.find(str(args.get("quality", "high"))))
	for look: String in _list("looks", "rl:mira"):
		var actor := _spawn(look, quality)
		if actor == null:
			continue
		for frame in 4:
			await process_frame
		Stage.pose(actor, "Rest", 0.0)
		var rig: Variant = actor.rl_head() if actor.has_method("rl_head") else null
		for expression_name: String in _list("expressions", "neutral"):
			if rig != null:
				rig.expression().clear_expression(0.0)
				rig.expression().set_expression(expression_name, 1.0, 0.0)
				rig.expression().advance(0.0)
			for view: String in _list("views", "eyes,front"):
				Stage.frame(camera, actor, view)
				var name := "%s_%s_%s_%s" % [_slug(look), view, expression_name, str(args.get("quality", "high"))]
				await _shot(name, actor, look, view, expression_name, built)
		actor.queue_free()
		await process_frame
	var file := FileAccess.open(out_dir.path_join("measure_renders.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t"))
	file.close()
	print("EYE_MEASURE_DONE ", out_dir, " ", report.size())
	quit()


func _slug(look: String) -> String:
	return look.replace(":", "-").replace("|", "_").replace("=", "").replace("@", "_")


func _spawn(look: String, quality: int) -> ReplicatedActor3D:
	if look.begins_with("dev:"):
		var name := look.trim_prefix("dev:")
		var sex := "female" if name in ["Mira", "default_female"] else "male"
		if name.contains("@"):
			sex = name.get_slice("@", 1)
			name = name.get_slice("@", 0)
		var presets: GDScript = load("res://src/actors/human_portrait_presets.gd")
		var appearance: Dictionary = {} if name.begins_with("default") else presets.appearance(name)
		var extra: Variant = JSON.parse_string(str(args.get("appearance", "{}")))
		if extra is Dictionary:
			appearance.merge(extra as Dictionary, true)
		var dev_actor := Stage.spawn(stage, sex, appearance, {}, quality)
		dev_actor.set_meta(&"rl_sex", sex)
		_quiet(dev_actor)
		return dev_actor
	var parts := look.trim_prefix("rl:").split("|")
	var face := RLHeadAppearance.from_preset(parts[0])
	if face == null:
		push_error("eye_measure: no preset " + parts[0])
		return null
	for index: int in range(1, parts.size()):
		var pair := parts[index].split("=")
		if pair.size() != 2:
			continue
		if pair[0] in ["liner", "liner_wing", "freckles", "brow_thickness"]:
			face.set(pair[0], float(pair[1]))
		elif pair[0] == "hair":
			face.hair = pair[1]
		else:
			face.set_control(pair[0], float(pair[1]))
	var actor := Stage.spawn(stage, face.sex, {"rl_head": face.to_dict()}, {}, quality)
	actor.set_meta(&"rl_sex", face.sex)
	_quiet(actor)
	return actor


func _quiet(actor: ReplicatedActor3D) -> void:
	if actor.has_method("rl_head") and actor.rl_head() != null:
		var expression: Variant = actor.rl_head().expression()
		expression.set_process(false)
		expression.auto_blink = false
		expression.set_seed(7)


func _make_materials() -> void:
	var discard := Shader.new()
	discard.code = "shader_type spatial;\nrender_mode unshaded;\nvoid fragment() { discard; }\n"
	_discard_material = ShaderMaterial.new()
	_discard_material.shader = discard
	_skin_material = StandardMaterial3D.new()
	_skin_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_skin_material.albedo_color = Color(1.0, 0.0, 1.0)
	_skin_material.cull_mode = BaseMaterial3D.CULL_BACK
	_black_env = Environment.new()
	_black_env.background_mode = Environment.BG_COLOR
	_black_env.background_color = Color.BLACK
	_black_env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_black_env.ambient_light_color = Color.BLACK
	_black_env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	_black_env.glow_enabled = false


## What a surface is for the mask: "eye", "discard" or "skin".
func _category(instance: MeshInstance3D, material: Material) -> String:
	var path := str(instance.get_path()).to_lower()
	var node_name := instance.name.to_lower()
	var shader_path := ""
	if material is ShaderMaterial and (material as ShaderMaterial).shader != null:
		shader_path = (material as ShaderMaterial).shader.resource_path.to_lower()
	var material_name := material.resource_name.to_lower() if material != null else ""
	if shader_path.ends_with("rl_eye.gdshader") or material_name == "rl_eye":
		return "eye"
	if node_name == "eyes" or (material_name.contains("eye") and not material_name.contains("brow")
			and not material_name.contains("lash")):
		return "eye"
	for word: String in ["rl_cornea", "rl_lash", "rl_brow", "rl_hair", "rl_beard"]:
		if shader_path.contains(word) or material_name == word:
			return "discard"
	if node_name in ["eyebrows", "eyelashes", "scalp"] or path.contains("hair") or path.contains("beard") \
			or material_name.contains("hair") or material_name.contains("lash") or material_name.contains("brow"):
		return "discard"
	return "skin"


func _unshaded_eye(material: Material) -> Material:
	if material is ShaderMaterial and (material as ShaderMaterial).shader != null:
		var source := material as ShaderMaterial
		var shader := Shader.new()
		shader.code = source.shader.code.replace("render_mode blend_mix,", "render_mode unshaded, blend_mix,")
		var copy := ShaderMaterial.new()
		copy.shader = shader
		for uniform: Dictionary in source.shader.get_shader_uniform_list():
			var uniform_name := str(uniform["name"])
			copy.set_shader_parameter(uniform_name, source.get_shader_parameter(uniform_name))
		copy.set_shader_parameter("catchlight", 0.0)
		return copy
	if material is BaseMaterial3D:
		var copy := (material as BaseMaterial3D).duplicate() as BaseMaterial3D
		copy.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		copy.emission_enabled = false
		return copy
	return material


func _shot(name: String, actor: ReplicatedActor3D, look: String, view: String, expression: String,
		built: Dictionary) -> void:
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(out_dir.path_join(name + ".png"))
	# ---- mask pass
	var restore: Array = []
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		if instance.mesh == null:
			continue
		var saved := {"node": instance, "overrides": [], "override": instance.material_override,
			"shadow": instance.cast_shadow}
		instance.material_override = null
		for surface: int in instance.mesh.get_surface_count():
			saved["overrides"].append(instance.get_surface_override_material(surface))
			var active := instance.get_active_material(surface)
			if saved["override"] != null:
				active = saved["override"]
			var category := _category(instance, active)
			var replacement: Material = _skin_material
			if category == "eye":
				replacement = _unshaded_eye(active)
			elif category == "discard":
				replacement = _discard_material
			instance.set_surface_override_material(surface, replacement)
		instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		restore.append(saved)
	var floor := built.get("floor") as MeshInstance3D
	floor.hide()
	var environment := world.environment
	world.environment = _black_env
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(out_dir.path_join(name + "_mask.png"))
	world.environment = environment
	floor.show()
	for saved: Dictionary in restore:
		var instance := saved["node"] as MeshInstance3D
		for surface: int in (saved["overrides"] as Array).size():
			instance.set_surface_override_material(surface, saved["overrides"][surface])
		instance.material_override = saved["override"]
		instance.cast_shadow = saved["shadow"]
	# ---- sidecar
	var points := {}
	var sex := str(actor.get_meta(&"rl_sex", "female"))
	var world_points: Dictionary = Stage.landmarks(actor, sex)
	for landmark: String in world_points:
		var position: Vector3 = world_points[landmark]
		var visible := root.get_visible_rect().size
		var scale := Vector2(root.size) / visible if visible.x > 0.0 else Vector2.ONE
		var pixel := camera.unproject_position(position) * scale
		points[landmark] = [pixel.x, pixel.y]
	# metres per pixel at the eye plane: project two points 1 cm apart
	var head: Transform3D = Stage.head_rest(actor)
	var forward := Stage.face_forward(actor)
	var anchor := head.origin + Vector3.UP * 0.07 + forward * 0.09
	var right := forward.cross(Vector3.UP).normalized()
	var p0 := camera.unproject_position(anchor)
	var p1 := camera.unproject_position(anchor + right * 0.01)
	var entry := {"name": name, "look": look, "view": view, "expression": expression,
		"landmarks": points, "px_per_cm": p0.distance_to(p1),
		"rl_face": actor.rl_head().appearance.to_dict() if actor.has_method("rl_head") and actor.rl_head() != null else {}}
	var file := FileAccess.open(out_dir.path_join(name + ".json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(entry, "\t"))
	file.close()
	report.append(entry)
