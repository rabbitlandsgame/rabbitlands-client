extends SceneTree
## Evidence renders of the RL head on the real client actor.
##
## Windowed (it needs a GPU); serialise with gpu_lock.sh. Every framing is
## fixed to the Head bone's rest (rl_head_stage.gd VIEWS: narrow FOV, yaw
## positive towards the front view's image right), so the same view of two
## presets, sexes, qualities or frames lines up pixel for pixel. Every still
## gets a sidecar <name>.json: the camera (transform, FOV, projection, image
## size) and each `rlHead.landmarks` point carried by the Head bone into the
## current pose, in world space and projected to pixels.
##
##   Godot --path godot-client --script res://tests/integration/rl_head_renders.gd -- [options]
##
## Options (all optional):
##   --set <name>            output folder under .local/rl-heads/evidence/godot/
##   --out <dir>             write there instead
##   --presets mira,rowan    RL preset names (the lab's rl_head override), or
##                           `all`; legacy_female / legacy_male draw develop's
##                           head (at --quality medium, or classic High with
##                           RL_HEADS=classic); dev:<look> draws the RL head a
##                           saved appearance derives at High (RLHeadPortraitMap):
##                           dev:Rowan, dev:Mira, dev:Tavi (develop's presets as
##                           field values) and dev:default_male / dev:default_female
##                           (every field 50); dev:<look>@<sex> picks the body
##   --appearance '{"skin":3}'  JSON merged into a dev: look
##   --views front,profile   rl_head_stage.gd VIEWS names
##   --expressions neutral   RLFaceExpression presets or ex_ shapes, comma separated
##   --quality high          low | medium | high
##   --clip Rest --time 0.0  the pose for stills
##   --headwear 0,134        headwear visual ids, one render set each (0 = none)
##   --torso yes             wear the class-kit torso (5:209)
##   --hair <style> --beard <style> --controls nose_width=0.6,jaw_width=-0.4
##   --legacy_hair 2         appearance hair for the legacy_* presets (0 = bald)
##   --extremes <preset>     every identity control at +1 and at -1 on that preset
##   --brow-style arched --brow-thickness 0.5 --liner-wing 0.8   override the preset
##   --brow-grid yes         each brow style at thickness -1, 0 and +1, per preset
##   --grooming yes          on a dev: look, hair_length and hair_volume each at
##                           0, 50 and 100 (saved fields, the actor's own path),
##                           the hair's fine-detail level (RLHeadAppearance
##                           hair_detail, 0..100) at 0, 50 and 100, and the
##                           look as saved (`authored`), one at a time
##   --grooming-values 0,50,100   the values swept
##   --grooming-motion no    yes lets the hair springs settle between stills
##   --sequence Walk         numbered frames of a clip instead of stills (at most
##   --frames 48 --fps 24    60), with a procedural head turn (--turn no to keep
##   --talk yes              still) and seeded auto-blinks; --talk loops the jaw
##   --look neutral          the stage's tone (rl_head_stage.gd environment):
##                           neutral (colour check), game or graded
##   --size 640x640
## Writes <out>/renders.json and prints RL_HEAD_RENDERS_DONE.

const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")
const PRESETS := preload("res://src/actors/human_portrait_presets.gd")

var args: Dictionary = {}
var stage: Node3D
var camera: Camera3D
var out_dir := ""
var report: Dictionary = {"renders": []}


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
	var size_parts := str(args.get("size", "640x640")).split("x")
	root.size = Vector2i(int(size_parts[0]), int(size_parts[1]))
	root.msaa_3d = Viewport.MSAA_4X
	stage = Node3D.new()
	root.add_child(stage)
	Stage.build(stage, str(args.get("look", "neutral")))
	camera = Camera3D.new()
	camera.cull_mask = 1
	camera.near = 0.05
	stage.add_child(camera)
	camera.current = true
	var evidence := ProjectSettings.globalize_path("res://").path_join(
		"../.local/rl-heads/evidence/godot").simplify_path()
	out_dir = str(args.get("out", evidence.path_join(str(args.get("set", "stills")))))
	DirAccess.make_dir_recursive_absolute(out_dir)
	report["renderer"] = RenderingServer.get_current_rendering_method()
	report["args"] = args
	var quality := maxi(0, ActorRenderQuality.QUALITY_NAMES.find(str(args.get("quality", "high"))))
	var presets := _list("presets", "mira,rowan")
	if presets.size() == 1 and presets[0] == "all":
		presets = RLHeadAppearance.preset_names()
	if args.has("extremes"):
		presets = PackedStringArray([str(args["extremes"])])
	for preset: String in presets:
		for headwear: String in _list("headwear", "0"):
			var actor := _spawn(preset, int(headwear), quality)
			if actor == null:
				continue
			for frame in 4:
				await process_frame
			if args.has("sequence"):
				await _sequence(actor, preset)
			elif args.has("extremes"):
				await _extremes(actor, preset)
			elif args.get("brow-grid", "no") == "yes":
				await _brow_grid(actor, preset)
			elif args.get("grooming", "no") == "yes":
				await _grooming(actor, preset)
			else:
				await _stills(actor, preset, int(headwear), quality)
			actor.queue_free()
			await process_frame
	var file := FileAccess.open(out_dir.path_join("renders.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t"))
	file.close()
	print("RL_HEAD_RENDERS_DONE ", out_dir, " ", (report["renders"] as Array).size())
	quit()


func _spawn(preset: String, headwear: int, quality: int) -> ReplicatedActor3D:
	var visuals := {}
	if headwear > 0:
		visuals[3] = headwear
	if args.get("torso", "no") == "yes":
		visuals[5] = Stage.TORSO
	if preset.begins_with("dev:"):
		var look := preset.trim_prefix("dev:")
		var sex := "female" if look in ["Mira", "default_female"] else "male"
		if look.contains("@"):
			sex = look.get_slice("@", 1)
			look = look.get_slice("@", 0)
		var appearance := {} if look.begins_with("default") else PRESETS.appearance(look)
		var extra: Variant = JSON.parse_string(str(args.get("appearance", "{}")))
		if extra is Dictionary:
			appearance.merge(extra as Dictionary, true)
		var dev_actor := Stage.spawn(stage, sex, appearance, visuals, quality)
		dev_actor.set_meta(&"rl_sex", sex)
		dev_actor.set_meta(&"appearance", appearance)
		if dev_actor.rl_head() != null:
			dev_actor.rl_head().expression().set_process(false)
			dev_actor.rl_head().expression().auto_blink = false
			dev_actor.rl_head().expression().set_seed(7)
		elif quality == ActorRenderQuality.Quality.HIGH and not ReplicatedActor3D.rl_heads_classic():
			push_error("RL head renders: %s built no RL head" % preset)
		return dev_actor
	if preset.begins_with("legacy_"):
		var sex := preset.trim_prefix("legacy_")
		var actor := Stage.spawn(stage, sex, {"skin": 1, "eyes": 2,
			"hair": int(args.get("legacy_hair", "0"))}, visuals, quality)
		actor.set_meta(&"rl_sex", sex)
		return actor
	var face := RLHeadAppearance.from_preset(preset)
	if face == null:
		push_error("RL head renders: no preset " + preset)
		return null
	if args.has("hair"):
		face.hair = str(args["hair"])
	if args.has("beard"):
		face.beard = str(args["beard"])
	for pair: String in _list("controls", ""):
		var parts := pair.split("=")
		if parts.size() == 2:
			face.set_control(parts[0], float(parts[1]))
	if args.has("brow-style"):
		var style := str(args["brow-style"])
		face.brow_style = RLHeadAppearance.brow_style_from(
			float(style) if style.is_valid_float() else style, face.brow_style)
	if args.has("brow-thickness"):
		face.brow_thickness = clampf(float(args["brow-thickness"]), -1.0, 1.0)
	if args.has("liner-wing"):
		face.liner_wing = clampf(float(args["liner-wing"]), 0.0, 1.0)
	var actor := Stage.spawn(stage, face.sex, {"rl_head": face.to_dict()}, visuals, quality)
	actor.set_meta(&"rl_sex", face.sex)
	if actor.rl_head() == null:
		push_error("RL head renders: %s built no RL head" % preset)
	else:
		var expression := actor.rl_head().expression()
		expression.set_process(false)
		expression.auto_blink = false
		expression.set_seed(7)
	return actor


func _suffix(headwear: int) -> String:
	var suffix := ""
	if headwear > 0:
		suffix += "_h%d" % headwear
	if args.get("torso", "no") == "yes":
		suffix += "_torso"
	if args.has("quality"):
		suffix += "_" + str(args["quality"])
	return suffix


func _stills(actor: ReplicatedActor3D, preset: String, headwear: int, quality: int) -> void:
	Stage.pose(actor, str(args.get("clip", "Rest")), float(args.get("time", "0.0")))
	var rig := actor.rl_head()
	for expression_name: String in _list("expressions", "neutral"):
		if rig != null:
			rig.expression().clear_expression(0.0)
			rig.expression().set_expression(expression_name, 1.0, 0.0)
			rig.expression().advance(0.0)
		for view: String in _list("views", "front,three_quarter,profile,rear"):
			Stage.frame(camera, actor, view)
			await _shot("%s_%s_%s%s" % [preset, view, expression_name, _suffix(headwear)],
				{"preset": preset, "view": view, "expression": expression_name, "headwear": headwear,
					"quality": ActorRenderQuality.quality_name(quality)}, actor, true)


## Each control alone at +1 and -1 on the preset, the rest of its face as is.
func _extremes(actor: ReplicatedActor3D, preset: String) -> void:
	Stage.pose(actor, str(args.get("clip", "Rest")), float(args.get("time", "0.0")))
	var rig := actor.rl_head()
	if rig == null:
		return
	for control: String in rig.head_info()["control_names"] as PackedStringArray:
		var authored := rig.appearance.control(control)
		for value: float in [1.0, -1.0]:
			rig.set_control(control, value)
			for view: String in _list("views", "front,profile"):
				Stage.frame(camera, actor, view)
				await _shot("%s_x_%s_%s_%s" % [preset, control, "p" if value > 0.0 else "n", view],
					{"preset": preset, "view": view, "control": control, "value": value}, actor, true)
		rig.set_control(control, authored)


## Each brow style at thickness -1, 0 and 1 on the preset, the rest as is.
func _brow_grid(actor: ReplicatedActor3D, preset: String) -> void:
	Stage.pose(actor, str(args.get("clip", "Rest")), float(args.get("time", "0.0")))
	var rig := actor.rl_head()
	if rig == null:
		return
	for style: int in RLHeadAppearance.BROW_STYLES.size():
		for thickness: float in [-1.0, 0.0, 1.0]:
			rig.appearance.brow_style = float(style)
			rig.appearance.brow_thickness = thickness
			rig.refresh_colours()
			for view: String in _list("views", "close"):
				Stage.frame(camera, actor, view)
				await _shot("%s_brow_%s_%s_%s" % [preset, RLHeadAppearance.BROW_STYLES[style],
					["thin", "mid", "thick"][int(thickness) + 1], view],
					{"preset": preset, "view": view, "brow_style": style, "brow_thickness": thickness},
					actor, true)


## A dev: look's hair groomed one choice at a time: hair_length, hair_volume
## (saved fields, re-applied through the actor as an edit would be) and the
## fine-detail level (set on the RL face: the saved finish has three values),
## each at the --grooming-values; `authored` is the look as saved.
func _grooming(actor: ReplicatedActor3D, preset: String) -> void:
	Stage.pose(actor, str(args.get("clip", "Rest")), float(args.get("time", "0.0")))
	var rig := actor.rl_head()
	if rig == null or not actor.has_meta(&"appearance"):
		push_error("RL head renders: --grooming needs a dev: look drawn with the RL head (%s)" % preset)
		return
	# The springs rest at their bind pose (--grooming-motion yes lets them
	# settle), so the stills differ by the choice alone.
	rig.set_hair_motion_allowed(args.get("grooming-motion", "no") == "yes")
	var saved: Dictionary = (actor.get_meta(&"appearance") as Dictionary).duplicate(true)
	var cases: Array = [["authored", -1]]
	for field: String in ["hair_length", "hair_volume", "hair_detail"]:
		for value: String in _list("grooming-values", "0,50,100"):
			cases.append([field, int(value)])
	for case: Array in cases:
		var field: String = case[0]
		var appearance := saved.duplicate(true)
		if field in ["hair_length", "hair_volume"]:
			appearance[field] = case[1]
		actor.apply_appearance_variants(appearance)
		actor.set_meta(&"appearance", appearance)
		Stage.pose(actor, str(args.get("clip", "Rest")), float(args.get("time", "0.0")))
		if field == "hair_detail":
			rig.appearance.hair_detail = int(case[1])
			rig.refresh_colours()
		var label := field if field == "authored" else "%s_%03d" % [field, int(case[1])]
		for view: String in _list("views", "front,profile"):
			Stage.frame(camera, actor, view)
			await _shot("%s_%s_%s" % [preset, label, view], {"preset": preset, "view": view, "grooming": field,
				"value": case[1], "hair_detail_uniform": rig.hair_detail_uniform(),
				"hl_weights": _hl_weights(rig)}, actor, true)
	actor.apply_appearance_variants(saved)
	actor.set_meta(&"appearance", saved)


## The grooming shapes' weights on the hair's first level.
func _hl_weights(rig: RLHeadRig) -> Dictionary:
	var weights := {}
	var levels: Array = rig.mesh_nodes()["hair"]
	if levels.is_empty() or (levels[0] as Array).is_empty():
		return weights
	var node := (levels[0] as Array)[0] as MeshInstance3D
	for shape: String in RLHeadRig.HAIR_LENGTH_SHAPES + RLHeadRig.HAIR_VOLUME_SHAPES:
		var index := RLHeadRig.shape_index(node, shape)
		if index >= 0:
			weights[shape] = snappedf(node.get_blend_shape_value(index), 0.0001)
	return weights


func _sequence(actor: ReplicatedActor3D, preset: String) -> void:
	var clip_label := str(args.get("sequence", "Walk"))
	var frames := clampi(int(args.get("frames", "48")), 1, 60)
	var fps := float(args.get("fps", "24"))
	var turn: bool = args.get("turn", "yes") == "yes"
	var rig := actor.rl_head()
	if rig != null:
		rig.expression().auto_blink = true
		rig.expression().set_seed(11)
		rig.expression().set_talking(args.get("talk", "no") == "yes")
	Stage.frame(camera, actor, str(args.get("views", "three_quarter")).split(",")[0])
	var skeleton := actor.get_skeleton()
	var head := skeleton.find_bone("Head")
	for frame: int in frames:
		var time := float(frame) / fps
		Stage.pose(actor, clip_label, time)
		if turn:
			var yaw := deg_to_rad(30.0) * sin(TAU * float(frame) / float(frames))
			skeleton.set_bone_pose_rotation(head,
				skeleton.get_bone_pose_rotation(head) * Quaternion(Vector3.UP, yaw))
		if rig != null:
			rig.expression().advance(1.0 / fps)
		await _shot("%s_%s_%03d" % [preset, clip_label.to_lower(), frame],
			{"preset": preset, "clip": clip_label, "frame": frame}, actor, false)


func _shot(name: String, info: Dictionary, actor: ReplicatedActor3D, sidecar: bool) -> void:
	# File names: dev:<look>@<sex> carries characters Windows does not allow.
	name = name.replace(":", "-").replace("@", "_")
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var path := out_dir.path_join(name + ".png")
	root.get_texture().get_image().save_png(path)
	info["file"] = path.get_file()
	var rig := actor.rl_head()
	if actor.has_meta(&"appearance"):
		info["appearance"] = actor.get_meta(&"appearance")
	info["sources"] = _sources(rig)
	if rig != null:
		info["rl_face"] = rig.appearance.to_dict()
		info["lod_band"] = rig.lod_band()
		info["near_triangles"] = rig.near_triangle_count()
		info["expression_weights"] = rig.expression().weights()
		var body := actor.get_node("NativeModel").find_child("body", true, false) as MeshInstance3D
		if body != null and body.has_meta(&"uncovered_body_mesh"):
			info["body_cut"] = RLHeadBodyCut.describe(body.get_meta(&"uncovered_body_mesh") as Mesh,
				str(rig.head_info().get("path", "")))
	if sidecar:
		var side := info.duplicate()
		side["camera"] = _camera_record()
		var points := {}
		var world := Stage.landmarks(actor, str(actor.get_meta(&"rl_sex", "female")))
		for landmark: String in world:
			var position: Vector3 = world[landmark]
			# unproject_position answers in the root viewport's 2D coordinates,
			# which the project's canvas stretch scales from the image size.
			var pixel := camera.unproject_position(position) * _canvas_to_image()
			points[landmark] = {"world": [position.x, position.y, position.z],
				"pixel": [pixel.x, pixel.y], "in_front": not camera.is_position_behind(position)}
		side["landmarks"] = points
		var file := FileAccess.open(out_dir.path_join(name + ".json"), FileAccess.WRITE)
		file.store_string(JSON.stringify(side, "\t"))
		file.close()
	(report["renders"] as Array).append(info)


## SHA-256 of what the still was made from: the head, hair and beard files the
## rig draws, and the mapping data.
func _sources(rig: RLHeadRig) -> Dictionary:
	var files := ["res://data/actors/rl_head_wire_defaults.json", "res://src/actors/rl_head/rl_head_portrait_map.gd"]
	if rig != null:
		files.append(str(rig.head_info().get("path", "")))
		if RLHeadPortraitMap.is_module(rig.appearance.hair):
			files.append(RLHeadLibrary.hair_path(rig.appearance.hair))
		if rig.appearance.beard not in [RLHeadAppearance.NONE, RLHeadAppearance.STUBBLE]:
			files.append(RLHeadLibrary.beard_path(rig.appearance.beard))
	var result := {}
	for file: String in files:
		if FileAccess.file_exists(file):
			result[file] = FileAccess.get_sha256(file)
	return result


func _canvas_to_image() -> Vector2:
	var visible := root.get_visible_rect().size
	return Vector2(root.size) / visible if visible.x > 0.0 and visible.y > 0.0 else Vector2.ONE


func _camera_record() -> Dictionary:
	var basis := camera.global_basis
	var origin := camera.global_position
	var projection := camera.get_camera_projection()
	var columns: Array = []
	for column: int in 4:
		var value: Vector4 = projection[column]
		columns.append([value.x, value.y, value.z, value.w])
	return {"origin": [origin.x, origin.y, origin.z],
		"basis_columns": [[basis.x.x, basis.x.y, basis.x.z], [basis.y.x, basis.y.y, basis.y.z],
			[basis.z.x, basis.z.y, basis.z.z]],
		"projection": "perspective", "fov_y_degrees": camera.fov, "near": camera.near,
		"far": camera.far, "image_size": [root.size.x, root.size.y],
		"projection_columns": columns}
