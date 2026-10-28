extends SceneTree
## The RL head's baked identity (RLHeadIdentityBake) against the live blend
## shapes, as the renderer draws them: windowed (it needs a GPU; serialise with
## gpu_lock.sh), in the current renderer.
##
## For several develop faces (the all-50 default, both extremes, Tavi with a
## full beard and an RL hairstyle, Mira with hers), front and profile, with no
## expression and with a blink, smile and open jaw: the head, beard and hair
## are drawn flat white on black (their silhouette) and as a view-depth ramp,
## first with the baked meshes, then live on the same actor (`set_control`
## with the same value turns the rig live), skinned to the same paused pose.
## The silhouettes must agree pixel for pixel and the depth ramps to one
## level, except for rasteriser ties: isolated pixels (no two touching) where
## an edge or two overlapping surfaces pass through a pixel centre, at most
## MAX_TIE_FRACTION of the covered pixels (sub-micrometre vertex differences
## flip them; a misplaced vertex would show as a strip). The headless
## test_rl_head_identity_bake.gd checks the vertices themselves (within 1e-5 m).
##
##   Godot --path godot-client --script res://tests/integration/rl_head_bake_silhouette.gd -- [--out <dir>]
## Prints RL_HEAD_BAKE_SILHOUETTE: PASS/FAIL and writes <out>/silhouette.json
## (with the images of any view that differs).

const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")
const PRESETS := preload("res://src/actors/human_portrait_presets.gd")
const BAKE := preload("res://src/actors/rl_head/rl_head_identity_bake.gd")
const MAX_TIE_FRACTION := 0.0002
const FLAT := """shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_opaque;
uniform int mode = 0;
void fragment() {
	if (mode == 0) {
		ALBEDO = vec3(1.0);
	} else {
		float d = clamp((-VERTEX.z - 0.6) / 1.2, 0.0, 1.0);
		ALBEDO = vec3(d);
	}
}
"""

var camera: Camera3D
var out_dir := ""
var report := {"views": []}
var failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var values := OS.get_cmdline_user_args()
	for index in range(0, values.size() - 1, 2):
		if values[index] == "--out":
			out_dir = values[index + 1]
	if out_dir.is_empty():
		out_dir = ProjectSettings.globalize_path("res://").path_join("../.local/rl-high/evidence/silhouette").simplify_path()
	DirAccess.make_dir_recursive_absolute(out_dir)
	OS.set_environment("RL_HEADS", "all")
	ReplicatedActor3D.reload_rl_heads_switch()
	# Baked in every renderer for the comparison, at once; spring hair off, so
	# both passes see the locks at rest.
	OS.set_environment("RL_HEAD_BAKE", "1")
	BAKE.reload_switch()
	BAKE.synchronous = true
	RLHairMotion.globally_enabled = false
	root.size = Vector2i(768, 768)
	root.msaa_3d = Viewport.MSAA_DISABLED
	var stage := Node3D.new()
	root.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color.BLACK
	world.environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	stage.add_child(world)
	camera = Camera3D.new()
	camera.near = 0.05
	stage.add_child(camera)
	camera.current = true
	report["renderer"] = RenderingServer.get_current_rendering_method()
	var flat := Shader.new()
	flat.code = FLAT
	var materials: Array[ShaderMaterial] = []
	for mode: int in 2:
		var material := ShaderMaterial.new()
		material.shader = flat
		material.set_shader_parameter("mode", mode)
		materials.append(material)
	var looks := [
		["male all-50 full beard rowan_shag", "male", {"facial_hair": 5, "hair": AppearanceVariants.pack_hair(1, 2)}],
		["male all-0", "male", _all(0).merged({"hair": AppearanceVariants.pack_hair(1, 3)}, true)],
		["male all-100 goatee", "male", _all(100).merged({"facial_hair": 3}, true)],
		["male Tavi", "male", PRESETS.appearance("Tavi")],
		["female all-50 mira_bun", "female", {"hair": AppearanceVariants.pack_hair(3, 4)}],
		["female all-100", "female", _all(100).merged({"hair": AppearanceVariants.pack_hair(3, 6)}, true)],
		["female Mira", "female", PRESETS.appearance("Mira")],
	]
	for look: Array in looks:
		var actor := Stage.spawn(stage, str(look[1]), look[2] as Dictionary)
		for frame: int in 3:
			await process_frame
		var rig := actor.rl_head()
		if rig == null:
			failures += 1
			push_error("bake silhouette: %s built no RL head" % look[0])
			actor.free()
			continue
		rig.expression().set_process(false)
		rig.expression().auto_blink = false
		rig.set_hair_motion_allowed(false)
		Stage.pose(actor, "Idle", 0.4)
		_hide_all_but_rig(actor, rig)
		var shots := {}
		var baked_ok := {}
		for pass_index: int in 2:
			if pass_index == 1:
				_go_live(rig)
			for expression: String in ["neutral", "blink smile jaw"]:
				_set_expression(rig, expression)
				for view: String in ["front", "profile"]:
					Stage.frame(camera, actor, view)
					for mode: int in 2:
						for node: MeshInstance3D in rig.all_meshes():
							node.material_override = materials[mode]
						var name := "%s_%s_%s_%s" % [str(look[0]).replace(" ", "-"), expression.replace(" ", "-"),
							view, "mask" if mode == 0 else "depth"]
						if pass_index == 0:
							baked_ok[name] = _all_shown_baked(rig)
							shots[name] = await _capture()
							continue
						var live := await _capture()
						var baked: Image = shots[name]
						var diff := _diff(baked, live)
						var ties := int(diff["pixels" if mode == 0 else "beyond_one"])
						var allowed := maxi(2, int(float(diff["covered"]) * MAX_TIE_FRACTION))
						var ok := bool(baked_ok[name]) and not _any_baked(rig) and ties <= allowed \
							and not bool(diff["touching"])
						if not ok:
							failures += 1
							baked.save_png(out_dir.path_join(name + "_baked.png"))
							live.save_png(out_dir.path_join(name + "_live.png"))
						(report["views"] as Array).append({"name": name, "baked_shown": baked_ok[name],
							"covered_pixels": diff["covered"], "differing_pixels": diff["pixels"],
							"pixels_beyond_one_level": diff["beyond_one"], "max_channel_difference": diff["max"],
							"touching": diff["touching"], "ok": ok})
						print("bake silhouette %s: %d covered, %d differ, %d beyond one level (max %d) %s" % [name,
							int(diff["covered"]), int(diff["pixels"]), int(diff["beyond_one"]), int(diff["max"]),
							"ok" if ok else "FAIL"])
		for node: MeshInstance3D in rig.all_meshes():
			node.material_override = null
		actor.queue_free()
		await process_frame
		await process_frame
	report["failures"] = failures
	report["max_tie_fraction"] = MAX_TIE_FRACTION
	var file := FileAccess.open(out_dir.path_join("silhouette.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t"))
	file.close()
	print("RL_HEAD_BAKE_SILHOUETTE: %s (%d views, %d failures) %s" % ["PASS" if failures == 0 else "FAIL",
		(report["views"] as Array).size(), failures, out_dir])
	quit(1 if failures > 0 else 0)


static func _all(value: int) -> Dictionary:
	var result := {}
	for field: String in PortraitCustomization.FIELDS:
		result[field] = mini(value, PortraitCustomization.maximum(field))
	return result


func _hide_all_but_rig(actor: ReplicatedActor3D, rig: RLHeadRig) -> void:
	var keep := {}
	for node: MeshInstance3D in rig.all_meshes():
		keep[node] = true
	for node: Node in actor.find_children("*", "GeometryInstance3D", true, false):
		if not keep.has(node):
			(node as GeometryInstance3D).visible = false


## A repeatable face: held neutral and released (no blink under way, nothing
## faded in), then the expression asked for.
func _set_expression(rig: RLHeadRig, expression: String) -> void:
	var face := rig.expression()
	face.hold_neutral(true)
	face.hold_neutral(false)
	face.auto_blink = false
	if expression != "neutral":
		face.set_expression("smile", 0.6, 0.0)
		face.set_expression("ex_jaw_open", 0.35, 0.0, true)
		face.blink()
		face.advance(0.09)


func _any_baked(rig: RLHeadRig) -> bool:
	for node: MeshInstance3D in rig.all_meshes():
		if rig.is_baked(node):
			return true
	return false


func _all_shown_baked(rig: RLHeadRig) -> bool:
	for node: MeshInstance3D in rig.all_meshes():
		if node.visible and not rig.is_baked(node):
			return false
	return true


## Turns every level live with the same face (set_control with its own value).
func _go_live(rig: RLHeadRig) -> void:
	var names: PackedStringArray = rig.head_info()["control_names"]
	rig.set_control(names[0], rig.appearance.control(names[0]))


func _capture() -> Image:
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	image.convert(Image.FORMAT_RGB8)
	return image


func _diff(a: Image, b: Image) -> Dictionary:
	var pixels := 0
	var beyond_one := 0
	var covered := 0
	var most := 0
	var width := a.get_width()
	var marked := {}
	var data_a := a.get_data()
	var data_b := b.get_data()
	for i: int in range(0, mini(data_a.size(), data_b.size()), 3):
		var lit := data_a[i] + data_a[i + 1] + data_a[i + 2] > 0 or data_b[i] + data_b[i + 1] + data_b[i + 2] > 0
		if lit:
			covered += 1
		var delta := maxi(absi(data_a[i] - data_b[i]), maxi(absi(data_a[i + 1] - data_b[i + 1]),
			absi(data_a[i + 2] - data_b[i + 2])))
		if delta > 0:
			pixels += 1
			most = maxi(most, delta)
		if delta > 1:
			beyond_one += 1
			marked[i / 3] = true
	# Ties are isolated pixels; two touching ones would be a strip.
	var touching := false
	for pixel: int in marked:
		for offset: int in [1, width - 1, width, width + 1]:
			if marked.has(pixel + offset):
				touching = true
	return {"pixels": pixels, "beyond_one": beyond_one, "covered": covered, "max": most, "touching": touching}
