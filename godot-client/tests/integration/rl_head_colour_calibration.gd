extends SceneTree
## Colour calibration probe for RLHeadPortraitMap's palette tables: for every
## skin (10), hair colour (20) and eye (12) palette index, the RL-side colour
## whose lit RL head matches what the Low/Medium head shows for that index.
##
## Windowed (GPU); serialise with gpu_lock.sh. The real client actor on the RL
## head stage (prototypes/rl_heads/rl_head_stage.gd, neutral look: linear tone
## mapping, key/fill/rim), the same camera for both heads:
##   * skin: the mean of three skin patches (both cheeks under the eyes, the
##     forehead centre) located from the head's landmarks, bald, no freckles;
##   * hair: every pixel of the hair alone (the other meshes hidden), found as
##     the pixels that are the same over a black and a white backdrop; the
##     Medium hairstyle in the slot the RL module replaces (male Parted,
##     female Buns) against the module;
##   * beard (male): develop's full beard shell against the RL full beard, alone;
##   * eyes: the iris pixels (those that change between a red and a green eye)
##     in the close eye framing, averaged over both eyes.
## Each RL colour starts from RLHeadPortraitMap's palette fallback and is
## corrected per channel in linear light by target / measured, ITERATIONS times.
## Writes --out=<abs.json> ({"colours": {...}, "residuals": ...}) and prints
## RL_HEAD_COLOUR_CALIBRATION_DONE; the table goes into
## data/actors/rl_head_wire_defaults.json `colours` by hand.
##
##   Godot --path godot-client --script res://tests/integration/rl_head_colour_calibration.gd -- --out=<abs.json>

const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")
const ITERATIONS := 3
const PATCH := 4
const MODULE_SLOT := {"male": 1, "female": 3}

var _out := ""
var _stage: Node3D
var _camera: Camera3D
var _environment: WorldEnvironment
var _report := {"colours": {"skin": {}, "hair": {}, "eyes": {}}, "residuals": {}, "targets": {}}


func _init() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			_out = argument.trim_prefix("--out=")
	call_deferred("_run")


func _run() -> void:
	root.size = Vector2i(512, 512)
	root.msaa_3d = Viewport.MSAA_DISABLED
	_stage = Node3D.new()
	root.add_child(_stage)
	var built := Stage.build(_stage, "neutral")
	_environment = built["environment"]
	(built["floor"] as Node3D).visible = false
	_camera = Camera3D.new()
	_camera.near = 0.05
	_stage.add_child(_camera)
	_camera.current = true
	for sex: String in ["female", "male"]:
		await _calibrate(sex)
	if not _out.is_empty():
		var file := FileAccess.open(_out, FileAccess.WRITE)
		file.store_string(JSON.stringify(_report, "\t"))
		file.close()
	print("RL_HEAD_COLOUR_CALIBRATION_DONE")
	quit(0)


func _calibrate(sex: String) -> void:
	var medium := Stage.spawn(_stage, sex, {}, {}, ActorRenderQuality.Quality.MEDIUM, 9701)
	var high := Stage.spawn(_stage, sex, {}, {}, ActorRenderQuality.Quality.HIGH, 9702)
	high.hold_portrait_pose(self)
	for frame: int in 4:
		await process_frame
	var rig := high.rl_head()
	if rig == null:
		push_error("colour calibration: no RL head for " + sex)
		return
	Stage.pose(medium, "Rest", 0.0)
	Stage.pose(high, "Rest", 0.0)
	# ---- skin: bald, clean, no freckles; three patches
	var skins: Array = []
	var skin_residual := 0.0
	for index: int in 10:
		medium.apply_appearance_variants({"skin": index})
		var target := await _skin_sample(medium, sex)
		var colour := RLHeadPortraitMap.skin_color(index, sex) if not _table_has("skin") \
			else _fallback_skin(index, sex)
		var face := rig.appearance.duplicate_appearance()
		face.freckles = 0.0
		face.hair = RLHeadAppearance.NONE
		var measured := Color.BLACK
		for step: int in ITERATIONS + 1:
			face.skin = colour
			rig.apply_appearance(face)
			measured = await _skin_sample(high, sex)
			if step < ITERATIONS:
				colour = _correct(colour, target, measured)
		skins.append(_rgb(colour))
		skin_residual = maxf(skin_residual, _error(target, measured))
		(_report.targets as Dictionary)["%s_skin_%d" % [sex, index]] = [_rgb(target), _rgb(measured)]
	(_report.colours.skin as Dictionary)[sex] = skins
	(_report.residuals as Dictionary)[sex + "_skin_max"] = skin_residual
	print("RL colour %s skin residual %.4f" % [sex, skin_residual])
	# ---- hair: the hair alone over two backdrops
	var hairs: Array = []
	var hair_residual := 0.0
	Stage.frame(_camera, medium, "front")
	for index: int in 20:
		medium.apply_appearance_variants({"hair": AppearanceVariants.pack_hair(MODULE_SLOT[sex], index)})
		Stage.pose(medium, "Rest", 0.0)
		var target := await _hair_sample(medium, false)
		var colour := AppearanceVariants.hair_color(index)
		var face := RLHeadPortraitMap.face({"hair": AppearanceVariants.pack_hair(MODULE_SLOT[sex], index)}, sex)
		var measured := Color.BLACK
		for step: int in ITERATIONS + 1:
			face.hair_color = colour
			rig.apply_appearance(face)
			measured = await _hair_sample(high, true)
			if step < ITERATIONS:
				colour = _correct(colour, target, measured)
		hairs.append(_rgb(colour))
		hair_residual = maxf(hair_residual, _error(target, measured))
		(_report.targets as Dictionary)["%s_hair_%d" % [sex, index]] = [_rgb(target), _rgb(measured)]
	(_report.colours.hair as Dictionary)[sex] = hairs
	(_report.residuals as Dictionary)[sex + "_hair_max"] = hair_residual
	print("RL colour %s hair residual %.4f" % [sex, hair_residual])
	# ---- beard (male only at High): the beard alone over two backdrops,
	# develop's PortraitGroom full beard against the RL full beard, bald
	if sex == "male":
		var beards: Array = []
		var beard_residual := 0.0
		for index: int in 20:
			var look := {"facial_hair": 5, "hair": AppearanceVariants.pack_hair(0, index)}
			medium.apply_appearance_variants(look)
			Stage.pose(medium, "Rest", 0.0)
			var target := await _part_sample(medium, func(mesh: MeshInstance3D) -> bool:
				return str(mesh.name) == "PortraitFacialHair")
			var colour := RLHeadPortraitMap.hair_color(index, sex)
			var face := RLHeadPortraitMap.face(look, sex)
			var measured := Color.BLACK
			for step: int in ITERATIONS + 1:
				face.beard_color = colour
				face.beard_color_set = true
				rig.apply_appearance(face)
				measured = await _part_sample(high, func(mesh: MeshInstance3D) -> bool:
					return str(mesh.name).begins_with("RLBeard"))
				if step < ITERATIONS:
					colour = _correct(colour, target, measured)
			beards.append(_rgb(colour))
			beard_residual = maxf(beard_residual, _error(target, measured))
			(_report.targets as Dictionary)["%s_beard_%d" % [sex, index]] = [_rgb(target), _rgb(measured)]
		_report.colours["beard"] = {"male": beards}
		(_report.residuals as Dictionary)[sex + "_beard_max"] = beard_residual
		print("RL colour %s beard residual %.4f" % [sex, beard_residual])
	# ---- eyes: iris pixels, close framing
	medium.apply_appearance_variants({})
	rig.apply_appearance(RLHeadPortraitMap.face({}, sex))
	var eyes: Array = []
	var eye_residual := 0.0
	var medium_mask := await _iris_mask(medium, func(index: int) -> void:
		medium.apply_appearance_variants({"eyes": index}))
	var high_mask := await _iris_mask(high, func(index: int) -> void:
		var face := rig.appearance.duplicate_appearance()
		face.eyes = AppearanceVariants.eye_color(index)
		rig.apply_appearance(face))
	for index: int in 12:
		medium.apply_appearance_variants({"eyes": index})
		var target := await _masked(medium, medium_mask)
		var colour := RLHeadPortraitMap.natural_iris(AppearanceVariants.eye_color(index))
		var measured := Color.BLACK
		for step: int in ITERATIONS + 1:
			var face := rig.appearance.duplicate_appearance()
			face.eyes = colour
			rig.apply_appearance(face)
			measured = await _masked(high, high_mask)
			if step < ITERATIONS:
				colour = _correct(colour, target, measured)
		eyes.append(_rgb(colour))
		eye_residual = maxf(eye_residual, _error(target, measured))
		(_report.targets as Dictionary)["%s_eyes_%d" % [sex, index]] = [_rgb(target), _rgb(measured)]
	(_report.colours.eyes as Dictionary)[sex] = eyes
	(_report.residuals as Dictionary)[sex + "_eyes_max"] = eye_residual
	(_report.residuals as Dictionary)[sex + "_iris_pixels"] = [medium_mask.size(), high_mask.size()]
	print("RL colour %s eyes residual %.4f (iris pixels %d / %d)" % [sex, eye_residual, medium_mask.size(), high_mask.size()])
	high.release_portrait_pose(self)
	medium.queue_free()
	high.queue_free()
	await process_frame


func _table_has(_category: String) -> bool:
	return false


func _fallback_skin(index: int, sex: String) -> Color:
	return RLHeadPortraitMap.skin_color(index, sex)


func _rgb(colour: Color) -> Array:
	return [snappedf(colour.r, 0.0001), snappedf(colour.g, 0.0001), snappedf(colour.b, 0.0001)]


func _error(a: Color, b: Color) -> float:
	return maxf(absf(a.r - b.r), maxf(absf(a.g - b.g), absf(a.b - b.b)))


## One per-channel step in linear light: the colour that would have measured
## `target` had the response been proportional.
func _correct(colour: Color, target: Color, measured: Color) -> Color:
	var c := colour.srgb_to_linear()
	var t := target.srgb_to_linear()
	var m := measured.srgb_to_linear()
	var result := Color(
		clampf(c.r * t.r / maxf(m.r, 1e-4), 0.0, 1.0),
		clampf(c.g * t.g / maxf(m.g, 1e-4), 0.0, 1.0),
		clampf(c.b * t.b / maxf(m.b, 1e-4), 0.0, 1.0))
	return result.linear_to_srgb()


func _show_only(actor: ReplicatedActor3D, keep: Callable) -> Dictionary:
	var saved := {}
	for node: Node in _stage.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		saved[mesh] = mesh.visible
		var ours := actor.is_ancestor_of(mesh)
		mesh.visible = mesh.visible and ours and keep.call(mesh)
	return saved


func _restore(saved: Dictionary) -> void:
	for mesh: Variant in saved:
		if is_instance_valid(mesh):
			(mesh as MeshInstance3D).visible = saved[mesh]


func _render() -> Image:
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	return root.get_texture().get_image()


func _canvas_to_image() -> Vector2:
	var visible := root.get_visible_rect().size
	return Vector2(root.size) / visible if visible.x > 0.0 and visible.y > 0.0 else Vector2.ONE


func _skin_points(actor: ReplicatedActor3D, sex: String) -> Array:
	var marks := Stage.landmarks(actor, sex)
	var eye_l: Vector3 = marks.get("eyeL", Vector3.ZERO)
	var eye_r: Vector3 = marks.get("eyeR", Vector3.ZERO)
	var nose: Vector3 = marks.get("nose", Vector3.ZERO)
	var down := (eye_l + eye_r) * 0.5 - nose
	return [eye_l.lerp(nose, 0.55) + (eye_l - eye_r) * 0.25, eye_r.lerp(nose, 0.55) + (eye_r - eye_l) * 0.25,
		(eye_l + eye_r) * 0.5 + down.normalized() * 0.05]


func _skin_sample(actor: ReplicatedActor3D, sex: String) -> Color:
	var other := _others(actor)
	Stage.frame(_camera, actor, "front")
	var image := await _render()
	_restore_others(other)
	var total := Color(0, 0, 0)
	var count := 0
	for point: Vector3 in _skin_points(actor, sex):
		var pixel := _camera.unproject_position(point) * _canvas_to_image()
		for dy: int in range(-PATCH, PATCH + 1):
			for dx: int in range(-PATCH, PATCH + 1):
				var x := clampi(int(pixel.x) + dx, 0, image.get_width() - 1)
				var y := clampi(int(pixel.y) + dy, 0, image.get_height() - 1)
				var sample := image.get_pixel(x, y).srgb_to_linear()
				total += Color(sample.r, sample.g, sample.b)
				count += 1
	return Color(total.r / count, total.g / count, total.b / count).linear_to_srgb()


## Hides the other actors on the stage; returns what to restore.
func _others(actor: ReplicatedActor3D) -> Array:
	var hidden: Array = []
	for child: Node in _stage.get_children():
		if child is ReplicatedActor3D and child != actor and (child as Node3D).visible:
			(child as Node3D).visible = false
			hidden.append(child)
	return hidden


func _restore_others(hidden: Array) -> void:
	for child: Variant in hidden:
		(child as Node3D).visible = true


func _hair_sample(actor: ReplicatedActor3D, rl: bool) -> Color:
	return await _part_sample(actor, func(mesh: MeshInstance3D) -> bool:
		var walker: Node = mesh
		while walker != null and walker != actor:
			var name := str(walker.name)
			if name.begins_with("AppearanceHair_"):
				return (name == RLHeadRig.HAIR_NODE_NAME) == rl
			walker = walker.get_parent()
		return false)


## The mean colour of the meshes `keep` picks, alone, over two backdrops.
func _part_sample(actor: ReplicatedActor3D, keep: Callable) -> Color:
	var other := _others(actor)
	Stage.frame(_camera, actor, "front")
	var saved := _show_only(actor, keep)
	var environment := _environment.environment
	var backdrop := environment.background_color
	environment.background_color = Color.BLACK
	var dark := await _render()
	environment.background_color = Color.WHITE
	var light := await _render()
	environment.background_color = backdrop
	_restore(saved)
	_restore_others(other)
	var total := Color(0, 0, 0)
	var count := 0
	for y: int in dark.get_height():
		for x: int in dark.get_width():
			var a := dark.get_pixel(x, y)
			var b := light.get_pixel(x, y)
			if absf(a.r - b.r) + absf(a.g - b.g) + absf(a.b - b.b) > 0.004:
				continue
			if b.r > 0.995 and b.g > 0.995 and b.b > 0.995:
				continue
			var linear := a.srgb_to_linear()
			total += Color(linear.r, linear.g, linear.b)
			count += 1
	if count == 0:
		push_warning("colour calibration: no hair pixels")
		return Color.BLACK
	return Color(total.r / count, total.g / count, total.b / count).linear_to_srgb()


## Pixels in the close eye framing that change between a red and a green eye.
func _iris_mask(actor: ReplicatedActor3D, set_eye: Callable) -> PackedInt32Array:
	var other := _others(actor)
	Stage.frame(_camera, actor, "eyes")
	set_eye.call(6)
	var red := await _render()
	set_eye.call(1)
	var green := await _render()
	_restore_others(other)
	var mask := PackedInt32Array()
	for y: int in red.get_height():
		for x: int in red.get_width():
			var a := red.get_pixel(x, y)
			var b := green.get_pixel(x, y)
			if absf(a.r - b.r) + absf(a.g - b.g) > 0.12:
				mask.append(y * red.get_width() + x)
	return mask


func _masked(actor: ReplicatedActor3D, mask: PackedInt32Array) -> Color:
	var other := _others(actor)
	Stage.frame(_camera, actor, "eyes")
	var image := await _render()
	_restore_others(other)
	var total := Color(0, 0, 0)
	for at: int in mask:
		var sample := image.get_pixel(at % image.get_width(), at / image.get_width()).srgb_to_linear()
		total += Color(sample.r, sample.g, sample.b)
	var count := maxi(1, mask.size())
	return Color(total.r / count, total.g / count, total.b / count).linear_to_srgb()
