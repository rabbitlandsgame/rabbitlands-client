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
## PC/3 custom colours (colour model spec revision 3, 4.3; R5, R12), with
## --part (the palette tables above are --part=palette, the default):
##   * skin: at knots every 5 slider positions (and the stops) x undertone
##     -1, -0.5, 0, 0.5, 1, the Medium cheeks with that custom skin are the
##     target and the RL skin is corrected as above; the knot is the RL /
##     final-skin gain (skinTone);
##   * eyes: the Medium iris for 20 pigments and the RL iris for 20 RL eye
##     colours, raw (both are affine in the colour by their shaders); the fit
##     (tools/colour_calibration/fit_skin_eyes.py) composes them into eyeLut;
##   * verify-skin / verify-eyes: hold-out skin tones and undertones, and 27
##     hold-out iris pigments (plus the limits' corners), drawn through
##     RLHeadPortraitMap and the actor as the game draws them, against the
##     Medium head; verify-eyes also reports the pupil-to-iris luminance ratio
##     at the darkest allowed iris.
##
##   Godot --path godot-client --script res://tests/integration/rl_head_colour_calibration.gd -- --out=<abs.json> [--part=palette|skin|eyes|verify-skin|verify-eyes]

const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")
const ITERATIONS := 3
const PATCH := 4
const MODULE_SLOT := {"male": 1, "female": 3}
const COLOURS := preload("res://src/actors/appearance_colours.gd")

var _out := ""
var _part := "palette"
var _stage: Node3D
var _camera: Camera3D
var _environment: WorldEnvironment
var _report := {"colours": {"skin": {}, "hair": {}, "eyes": {}}, "residuals": {}, "targets": {}}


func _init() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			_out = argument.trim_prefix("--out=")
		elif argument.begins_with("--part="):
			_part = argument.trim_prefix("--part=")
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
	_report["part"] = _part
	_report["renderer"] = RenderingServer.get_current_rendering_method()
	for sex: String in ["female", "male"]:
		if _part == "palette":
			await _calibrate(sex)
		else:
			await _custom(sex)
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


# ------------------------------------------------- PC/3 custom colours

const UNDERTONES: Array[float] = [-1.0, -0.5, 0.0, 0.5, 1.0]
## Linear RL eye colours for the affine fit of the RL iris.
const EYE_FIT: Array = [[0.0, 0.0, 0.0], [0.1, 0.1, 0.1], [0.3, 0.3, 0.3], [0.6, 0.6, 0.6], [1.0, 1.0, 1.0],
	[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [0.6, 0.3, 0.1], [0.1, 0.4, 0.2], [0.2, 0.3, 0.7],
	[0.5, 0.1, 0.4], [0.05, 0.2, 0.3], [0.8, 0.6, 0.2], [0.3, 0.05, 0.02], [0.4, 0.5, 0.6], [0.02, 0.06, 0.15],
	[0.7, 0.2, 0.25], [0.25, 0.6, 0.55], [0.9, 0.85, 0.5]]
## OKHSL (hue, saturation, lightness) pigments inside the iris limits for the
## Medium fit, drawn through the game's custom-eye path.
const EYE_FIT_OKHSL: Array = [[0.0, 0.0, 0.2], [0.0, 0.0, 0.5], [0.0, 0.0, 0.8], [0.08, 0.9, 0.5], [0.33, 0.9, 0.5],
	[0.62, 0.9, 0.5], [0.08, 0.6, 0.3], [0.2, 0.8, 0.7], [0.45, 0.7, 0.4], [0.55, 0.5, 0.65], [0.75, 0.85, 0.35],
	[0.9, 0.6, 0.55], [0.15, 0.3, 0.25], [0.5, 0.9, 0.75], [0.7, 0.4, 0.22], [0.97, 0.9, 0.3], [0.3, 0.2, 0.6],
	[0.12, 0.92, 0.78], [0.66, 0.92, 0.2], [0.4, 0.55, 0.5]]
const VERIFY_POSITIONS: Array[int] = [3, 13, 30, 50, 70, 110, 140, 170, 190]
const VERIFY_UNDERTONES: Array[float] = [-0.75, -0.25, 0.0, 0.25, 0.75]


## The knot positions: every 5 from 1 and the six stops.
func _knot_positions() -> Array[int]:
	var result: Array[int] = []
	for p: int in range(1, 202, 5):
		result.append(p)
	for p: int in COLOURS.SKIN_STOP_POSITION:
		if not result.has(p):
			result.append(p)
	result.sort()
	return result


func _undertone_wire(t: float) -> int:
	return 0 if is_zero_approx(t) else clampi(roundi(101.0 + 100.0 * t), 1, 201)


func _skin_look(p: int, t: float) -> Dictionary:
	return {"skin": COLOURS.nearest_skin_index(p), "skin_tone": p, "skin_undertone": _undertone_wire(t)}


func _linear_rgb(colour: Color) -> Array:
	var v := COLOURS.to_linear(colour)
	return [v.x, v.y, v.z]


func _custom(sex: String) -> void:
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
	var config := RLHeadPortraitMap.human_config(sex)
	var stops: Array = []
	for stop: int in COLOURS.SKIN_STOP_INDEX.size():
		var index: int = COLOURS.SKIN_STOP_INDEX[stop]
		stops.append({"index": index, "position": COLOURS.SKIN_STOP_POSITION[stop],
			"table": _linear_rgb(RLHeadPortraitMap.skin_color(index, sex)),
			"stop": _linear_rgb(COLOURS.skin_stop_colour(index, sex))})
	_report[sex + "_skin_stops"] = stops
	if _part == "skin" or _part == "verify-skin":
		var rows: Array = []
		var cases: Array = []
		if _part == "skin":
			for p: int in _knot_positions():
				for t: float in UNDERTONES:
					cases.append([p, t])
		else:
			for p: int in VERIFY_POSITIONS:
				for t: float in VERIFY_UNDERTONES:
					cases.append([p, t])
		for case: Array in cases:
			var p: int = case[0]
			var t: float = case[1]
			var look := _skin_look(p, t)
			var resolved := COLOURS.skin(look, config)
			medium.apply_appearance_variants(look)
			Stage.pose(medium, "Rest", 0.0)
			var target := await _skin_sample(medium, sex)
			var face := RLHeadPortraitMap.face(look, sex)
			face.freckles = 0.0
			face.hair = RLHeadAppearance.NONE
			var colour := face.skin
			var measured := Color.BLACK
			var steps := ITERATIONS if _part == "skin" else 0
			for step: int in steps + 1:
				face.skin = colour
				rig.apply_appearance(face)
				measured = await _skin_sample(high, sex)
				if step < steps:
					colour = _correct(colour, target, measured)
			rows.append({"position": p, "undertone": t, "custom": resolved.custom, "final": _linear_rgb(resolved.colour),
				"rl": _linear_rgb(colour), "target": _linear_rgb(target), "measured": _linear_rgb(measured),
				"error": _error(target, measured)})
		_report[sex + "_skin"] = rows
		print("RL colour %s %s: %d cases, worst %.4f" % [sex, _part, rows.size(),
			rows.reduce(func(worst: float, row: Dictionary) -> float: return maxf(worst, float(row.error)), 0.0)])
	else:
		var medium_mask := await _iris_mask(medium, func(index: int) -> void:
			medium.apply_appearance_variants({"eyes": index}))
		var high_mask := await _iris_mask(high, func(index: int) -> void:
			var face := rig.appearance.duplicate_appearance()
			face.eyes = AppearanceVariants.eye_color(index)
			rig.apply_appearance(face))
		_report[sex + "_iris_pixels"] = [medium_mask.size(), high_mask.size()]
		if _part == "eyes":
			var medium_rows: Array = []
			var rl_rows: Array = []
			for value: Array in EYE_FIT_OKHSL:
				# Medium: a custom pigment through the game's own path (its
				# limits applied); the pigment drawn is the resolver's.
				var wire := COLOURS.quantise(Color.from_ok_hsl(value[0], value[1], value[2]))
				var look := {"eyes": COLOURS.nearest_eye_index(COLOURS.triple_colour(wire)), "eye_hue": wire.x,
					"eye_sat": wire.y, "eye_light": wire.z}
				var resolved := COLOURS.eyes(look, config)
				medium.apply_appearance_variants(look)
				medium_rows.append({"pigment": _linear_rgb(resolved.pigment), "custom": resolved.custom,
					"mu": await _masked_linear(medium, medium_mask)})
			for value: Array in EYE_FIT:
				var face := rig.appearance.duplicate_appearance()
				face.eyes = COLOURS.to_srgb(Vector3(float(value[0]), float(value[1]), float(value[2])))
				rig.apply_appearance(face)
				rl_rows.append({"eye": value, "mu": await _masked_linear(high, high_mask)})
			_report[sex + "_eyes_medium"] = medium_rows
			_report[sex + "_eyes_rl"] = rl_rows
			var palette: Array = []
			for index: int in 12:
				medium.apply_appearance_variants({"eyes": index})
				var target := await _masked_linear(medium, medium_mask)
				var face := rig.appearance.duplicate_appearance()
				face.eyes = RLHeadPortraitMap.eye_color(index, sex)
				rig.apply_appearance(face)
				palette.append({"index": index, "pigment": _linear_rgb(AppearanceVariants.eye_color(index)),
					"table": _linear_rgb(RLHeadPortraitMap.eye_color(index, sex)), "medium": target,
					"rl": await _masked_linear(high, high_mask)})
			_report[sex + "_eyes_palette"] = palette
			print("RL colour %s eyes: %d + %d fit samples" % [sex, medium_rows.size(), rl_rows.size()])
		else:
			var rows: Array = []
			for wire: Vector3i in _eye_holdout():
				var pigment := COLOURS.triple_colour(wire)
				var index := COLOURS.nearest_eye_index(pigment)
				var look := {"eyes": index, "eye_hue": wire.x, "eye_sat": wire.y, "eye_light": wire.z}
				var resolved := COLOURS.eyes(look, config)
				medium.apply_appearance_variants(look)
				var target := await _masked_linear(medium, medium_mask)
				var face := RLHeadPortraitMap.face(look, sex)
				var drawn := rig.appearance.duplicate_appearance()
				drawn.eyes = face.eyes
				rig.apply_appearance(drawn)
				var measured := await _masked_linear(high, high_mask)
				var error := 0.0
				for axis: int in 3:
					error = maxf(error, absf(COLOURS._enc(float(target[axis]))
						- COLOURS._enc(float(measured[axis]))))
				rows.append({"wire": [wire.x, wire.y, wire.z], "custom": resolved.custom, "limited": resolved.limited,
					"pigment": _linear_rgb(resolved.pigment), "rl": _linear_rgb(face.eyes), "medium": target,
					"measured": measured, "error": error})
			_report[sex + "_eyes_verify"] = rows
			_report[sex + "_pupil_ratio"] = await _pupil_ratio(medium, high, rig, medium_mask, high_mask, sex)
			print("RL colour %s verify-eyes: %d cases" % [sex, rows.size()])
	high.release_portrait_pose(self)
	medium.queue_free()
	high.queue_free()
	await process_frame


## 27 hold-out iris pigments (OKHSL hue x saturation x lightness inside the
## limits) and the limits' corners (lightness 0.1 and 0.9, saturation 1).
func _eye_holdout() -> Array[Vector3i]:
	var result: Array[Vector3i] = []
	for h: float in [0.05, 0.38, 0.71]:
		for s: float in [0.25, 0.55, 0.85]:
			for l: float in [0.25, 0.5, 0.75]:
				result.append(COLOURS.quantise(Color.from_ok_hsl(h, s, l)))
	for corner: Array in [[0.6, 1.0, 0.1], [0.1, 1.0, 0.9], [0.3, 0.2, 0.05], [0.9, 0.5, 0.95]]:
		result.append(COLOURS.quantise(Color.from_ok_hsl(corner[0], corner[1], corner[2])))
	return result


func _masked_linear(actor: ReplicatedActor3D, mask: PackedInt32Array) -> Array:
	var other := _others(actor)
	Stage.frame(_camera, actor, "eyes")
	var image := await _render()
	_restore_others(other)
	var total := Vector3.ZERO
	for at: int in mask:
		var sample := image.get_pixel(at % image.get_width(), at / image.get_width()).srgb_to_linear()
		total += Vector3(sample.r, sample.g, sample.b)
	total /= float(maxi(1, mask.size()))
	return [total.x, total.y, total.z]


## Iris / pupil luminance at the darkest allowed iris (OKHSL lightness 0.20,
## grey): the pupil is the pixels inside the iris mask's disc, within 0.3 of
## its radius, that are not in the mask.
func _pupil_ratio(medium: ReplicatedActor3D, high: ReplicatedActor3D, rig: RLHeadRig, medium_mask: PackedInt32Array,
		high_mask: PackedInt32Array, sex: String) -> Dictionary:
	var darkest := Color.from_ok_hsl(0.0, 0.0, COLOURS.EYE_LIGHT_MIN)
	var wire := COLOURS.quantise(darkest)
	var look := {"eyes": COLOURS.nearest_eye_index(darkest), "eye_hue": wire.x,
		"eye_sat": wire.y, "eye_light": wire.z}
	medium.apply_appearance_variants(look)
	var drawn := rig.appearance.duplicate_appearance()
	drawn.eyes = RLHeadPortraitMap.face(look, sex).eyes
	rig.apply_appearance(drawn)
	var result := {}
	for pair: Array in [["medium", medium, medium_mask], ["rl", high, high_mask]]:
		var actor: ReplicatedActor3D = pair[1]
		var mask: PackedInt32Array = pair[2]
		var other := _others(actor)
		Stage.frame(_camera, actor, "eyes")
		var image := await _render()
		_restore_others(other)
		var width := image.get_width()
		var in_mask := {}
		for at: int in mask:
			in_mask[at] = true
		var iris := 0.0
		for at: int in mask:
			iris += image.get_pixel(at % width, at / width).srgb_to_linear().get_luminance()
		iris /= float(maxi(1, mask.size()))
		# Two eyes: split the mask by x about its mean, one disc each.
		var mean_x := 0.0
		for at: int in mask:
			mean_x += float(at % width)
		mean_x /= float(maxi(1, mask.size()))
		var pupil := 0.0
		var count := 0
		for side: int in 2:
			var centre := Vector2.ZERO
			var members := 0
			for at: int in mask:
				if (float(at % width) < mean_x) == (side == 0):
					centre += Vector2(at % width, at / width)
					members += 1
			if members == 0:
				continue
			centre /= float(members)
			var radius := sqrt(float(members) / PI) * 1.15
			for y: int in range(int(centre.y - radius), int(centre.y + radius) + 1):
				for x: int in range(int(centre.x - radius), int(centre.x + radius) + 1):
					if Vector2(x, y).distance_to(centre) < radius * 0.3 and not in_mask.has(y * width + x):
						pupil += image.get_pixel(x, y).srgb_to_linear().get_luminance()
						count += 1
		pupil /= float(maxi(1, count))
		result[pair[0]] = {"iris": iris, "pupil": pupil, "pupil_pixels": count,
			"ratio": iris / maxf(pupil, 1e-6)}
	return result


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
