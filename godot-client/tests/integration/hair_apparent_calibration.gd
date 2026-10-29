extends SceneTree
## Hair apparent-colour calibration probe (colour model spec revision 3, 4.4;
## R10, R11 and R13 evidence): the lit mean of the hair alone, per draw path,
## on the RL head stage, for the dyes the fit needs (--mode=fit) or for
## hold-out apparent colours drawn through the game's own resolver
## (--mode=verify, after data/actors/hair_apparent.json and the RL hair and
## beard LUTs are written).
##
## Windowed (GPU); serialise with gpu_lock.sh. The real client actor on the RL
## head stage (prototypes/rl_heads/rl_head_stage.gd, neutral look), front view,
## 512 px, no MSAA:
##   * the hair pixels are those that are the same over a black and a white
##     backdrop with every other mesh hidden (rl_head_colour_calibration's
##     method), found once per path, finish and style; each dye is then one
##     render over black, averaged over that mask in linear light;
##   * paths (spec 4.4): P1 Low/Medium Classic, P2 Classic with length or
##     volume off 50, P3 Low/Medium at finish positions 0, 25, 75 and 100
##     (and 37 and 63 in verify), B1 Low/Medium beard shells; P4 the classic
##     High hair finish at 0, 25, 50, 75 and 100 and B2 its beards
##     (RL_HEADS=classic, every style); P5 the RL module at the five finish
##     positions' levels and B3 the RL beards (male);
##   * fit: in Low/Medium/classic High the dye is forced through the game's
##     own path by a measured-table test seam (AppearanceColours.set_hair_tables
##     with an entry that returns exactly that dye); the RL face takes its hair
##     and beard colour directly.
## Writes --out=<abs.json> and prints HAIR_APPARENT_CALIBRATION_DONE. The fit
## (tools/colour_calibration/fit_hair.py) turns a fit run into hair_apparent.json
## and the RL LUTs; a verify run gives the accuracy tables.
##
##   Godot --path godot-client --resolution 512x512 --script res://tests/integration/hair_apparent_calibration.gd -- --out=<abs.json> [--mode=fit|verify] [--sex=female|male] [--groups=low,medium,p2,rl,high]
##     [--styles=1,3] [--beards=2,5] (quick subsets) [--rl-switch=all] [--exposure=0.5]
## Groups: low, medium (P1, P3, B1), p2 (two shapes), shape (P2 on the
## length x volume grid; verify: P2, and P3 at s 12/88, on two shapes),
## positions / positionshigh (P3 / P4 at the custom positions between the
## saved finishes), shapefinish / shapefinishhigh (the coarse length x volume
## grid at finish positions 0, 25, 75, 100), rl (P5,
## B3), rlshape (P5 at the module's authored level with length and volume off
## its preset, report only), high (P4, B2), shapehigh (P4 on the grid; verify:
## P4 at s 0/50/100 on two shapes).

const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")
const Colours := preload("res://src/actors/appearance_colours.gd")
const Finish := preload("res://src/actors/hair_finish.gd")
const Map := preload("res://src/actors/rl_head/rl_head_portrait_map.gd")
const SIZE := 512
const ALL_STYLES: Array[int] = [1, 2, 3, 4, 5, 6, 7, 8, 9]
const ALL_BEARDS: Array[int] = [2, 3, 4, 5]
const MODULE_SLOT := {"male": 1, "female": 3}
const MODULE := {"male": "rowan_shag", "female": "mira_bun"}
## hair_detail / hair_finish for a finish position s (spec 2.9).
const FINISH_LOOKS := {0: [2, 1], 6: [2, 7], 12: [2, 13], 25: [2, 0], 31: [2, 32], 37: [2, 38], 44: [0, 45],
	49: [0, 50], 50: [0, 0], 51: [0, 52], 56: [0, 57], 63: [1, 64], 69: [1, 70], 75: [1, 0], 88: [1, 89], 94: [1, 95],
	100: [1, 101]}
const FIT_POSITIONS: Array[int] = [0, 25, 75, 100]
## Custom finish positions between the saved finishes (group positions), and
## the hold-out positions verify draws between every measured one.
const BETWEEN_POSITIONS: Array[int] = [12, 37, 49, 51, 63, 88]
const VERIFY_POSITIONS: Array[int] = [0, 6, 25, 31, 44, 56, 69, 75, 94, 100]
## The coarse length x volume grid measured at the other finish positions.
const SHAPE_GRID_COARSE: Array[int] = [0, 50, 100]
const HIGH_POSITIONS: Array[int] = [0, 25, 50, 75, 100]
## Length / volume off 50 for P2 (and the separability spot checks).
const SHAPES: Array = [[20, 80], [85, 30]]
## The length x volume grid of the shape correction (groups shape, shapehigh).
const SHAPE_GRID: Array[int] = [0, 25, 50, 75, 100]
## Fit dyes (linear): black, greys up to D_MAX, primaries, and colours that
## exercise the pigment model's warm term and the RL sheen's hue term.
const FIT_DYES: Array = [[0, 0, 0], [0.25, 0.25, 0.25], [0.5, 0.5, 0.5], [1, 1, 1], [1.6, 1.6, 1.6],
	[1, 0, 0], [0, 1, 0], [0, 0, 1], [1.0, 0.4, 0.1], [0.6, 0.3, 0.12], [0.25, 0.12, 0.04],
	[0.05, 0.03, 0.02], [0.15, 0.3, 0.8], [1.6, 1.2, 0.5]]
## The RL dyes stay in 0..1 (an instance uniform colour).
const RL_DYES: Array = [[0, 0, 0], [0.25, 0.25, 0.25], [0.5, 0.5, 0.5], [0.8, 0.8, 0.8], [1, 1, 1],
	[1, 0, 0], [0, 1, 0], [0, 0, 1], [1.0, 0.4, 0.1], [0.6, 0.3, 0.12], [0.25, 0.12, 0.04],
	[0.05, 0.03, 0.02], [0.15, 0.3, 0.8], [1.0, 0.75, 0.3]]
## The custom wire the fit's forced dyes ride on (any custom triple works).
const FIT_WIRE := Vector3i(30, 40, 30)
## Verify: 27 hold-out apparent colours (OKHSL hue x saturation x lightness)
## and the three presets' concept hair (spec 5).
const VERIFY_HUES: Array[float] = [0.07, 0.38, 0.70]
const VERIFY_SATS: Array[float] = [0.30, 0.60, 0.90]
const VERIFY_LIGHTS: Array[float] = [0.18, 0.36, 0.54]
const PRESET_WIRES: Array = [[35, 45, 19], [25, 86, 39], [38, 40, 24]]

var _out := ""
var _mode := "fit"
var _sexes: Array = ["female", "male"]
var _groups: Array = ["low", "medium", "p2", "rl", "high"]
var STYLES: Array[int] = ALL_STYLES.duplicate()
var BEARDS: Array[int] = ALL_BEARDS.duplicate()
var _stage: Node3D
var _camera: Camera3D
var _environment: WorldEnvironment
var _linear := PackedFloat32Array()
var _report := {"instances": []}
var _started := 0
## The stage's tone-mapping exposure for the hair renders: 0.5 keeps every lit
## hair pixel below the linear tone mapper's clip at 1 (bright dyes up to D_MAX
## and light beards clip at the stage's exposure 1), and the means are divided
## by it, so the probe measures the unclipped lit response.
var _exposure := 0.5
## RL_HEADS for the RL groups: "" (the renderer's default) or "all" (draws the
## RL head in the Compatibility renderer too); classic groups use "classic".
var _rl_switch := ""
var _clipped := 0


func _init() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			_out = argument.trim_prefix("--out=")
		elif argument.begins_with("--mode="):
			_mode = argument.trim_prefix("--mode=")
		elif argument.begins_with("--sex="):
			_sexes = [argument.trim_prefix("--sex=")]
		elif argument.begins_with("--groups="):
			_groups = Array(argument.trim_prefix("--groups=").split(","))
		elif argument.begins_with("--rl-switch="):
			_rl_switch = argument.trim_prefix("--rl-switch=")
		elif argument.begins_with("--exposure="):
			_exposure = float(argument.trim_prefix("--exposure="))
		elif argument.begins_with("--styles="):
			STYLES.assign(Array(argument.trim_prefix("--styles=").split(",")).map(func(v: String) -> int: return int(v)))
		elif argument.begins_with("--beards="):
			BEARDS.assign(Array(argument.trim_prefix("--beards=").split(",")).map(func(v: String) -> int: return int(v)))
	call_deferred("_run")


func _run() -> void:
	_started = Time.get_ticks_msec()
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	root.size = Vector2i(SIZE, SIZE)
	root.msaa_3d = Viewport.MSAA_DISABLED
	for value: int in 256:
		_linear.append(Colours._lin(value / 255.0))
	_stage = Node3D.new()
	root.add_child(_stage)
	var built := Stage.build(_stage, "neutral")
	_environment = built["environment"]
	_environment.environment.tonemap_exposure = _exposure
	(built["floor"] as Node3D).visible = false
	_camera = Camera3D.new()
	_camera.near = 0.05
	_stage.add_child(_camera)
	_camera.current = true
	_report["mode"] = _mode
	_report["renderer"] = RenderingServer.get_current_rendering_method()
	_report["size"] = SIZE
	_report["exposure"] = _exposure
	_report["skinGain"] = {"female": _array(Colours.SKIN_GAIN["female"]), "male": _array(Colours.SKIN_GAIN["male"])}
	_report["verifyWires"] = _verify_wires()
	for sex: String in _sexes:
		await _calibrate(sex)
	Colours.set_hair_tables({})
	_report["seconds"] = (Time.get_ticks_msec() - _started) / 1000.0
	if not _out.is_empty():
		var file := FileAccess.open(_out, FileAccess.WRITE)
		file.store_string(JSON.stringify(_report, "\t"))
		file.close()
	print("HAIR_APPARENT_CALIBRATION_DONE %d instances in %.0f s" % [(_report.instances as Array).size(), _report.seconds])
	quit(0)


func _verify_wires() -> Array:
	var wires: Array = []
	for h: float in VERIFY_HUES:
		for s: float in VERIFY_SATS:
			for l: float in VERIFY_LIGHTS:
				var wire := Colours.quantise(Color.from_ok_hsl(h, s, l))
				wires.append([wire.x, wire.y, wire.z])
	for wire: Array in PRESET_WIRES:
		wires.append(wire)
	return wires


func _set_rl_switch(classic: bool) -> void:
	OS.set_environment("RL_HEADS", "classic" if classic else _rl_switch)
	ReplicatedActor3D.reload_rl_heads_switch()


func _calibrate(sex: String) -> void:
	_set_rl_switch(false)
	var low_medium := _groups.has("low") or _groups.has("medium") or _groups.has("p2") or _groups.has("shape") 		or _groups.has("positions") or _groups.has("shapefinish")
	if low_medium:
		var medium := Stage.spawn(_stage, sex, {}, {}, ActorRenderQuality.Quality.MEDIUM, 9801)
		var low := Stage.spawn(_stage, sex, {}, {}, ActorRenderQuality.Quality.LOW, 9802) if _groups.has("low") else null
		for frame: int in 4:
			await process_frame
		if _groups.has("medium"):
			for style: int in STYLES:
				await _legacy(medium, sex, "P1", "medium", style, 50, 50, 50)
			var positions: Array = FIT_POSITIONS.duplicate() if _mode == "fit" else VERIFY_POSITIONS.duplicate()
			for s: int in positions:
				for style: int in STYLES:
					await _legacy(medium, sex, "P3", "medium", style, s, 50, 50)
			for beard: int in BEARDS:
				await _beard(medium, sex, "B1", "medium", beard)
		if _groups.has("p2"):
			for shape: Array in SHAPES:
				for style: int in STYLES:
					await _legacy(medium, sex, "P2", "medium", style, 50, int(shape[0]), int(shape[1]))
		if _groups.has("shape"):
			for style: int in STYLES:
				for shape: Array in _shapes():
					if _mode == "fit":
						await _legacy(medium, sex, "P2", "medium", style, 50, int(shape[0]), int(shape[1]))
					else:
						for s: int in [12, 50, 88]:
							await _legacy(medium, sex, "P3" if s != 50 else "P2", "medium", style, s, int(shape[0]), int(shape[1]))
		if _groups.has("positions") and _mode == "fit":
			for s: int in BETWEEN_POSITIONS:
				for style: int in STYLES:
					await _legacy(medium, sex, "P3", "medium", style, s, 50, 50)
		if _groups.has("shapefinish") and _mode == "fit":
			for s: int in FIT_POSITIONS:
				for style: int in STYLES:
					for shape: Array in _coarse_shapes():
						await _legacy(medium, sex, "P3", "medium", style, s, int(shape[0]), int(shape[1]))
		if low != null:
			for style: int in STYLES:
				await _legacy(low, sex, "P1", "low", style, 50, 50, 50)
			for beard: int in BEARDS:
				await _beard(low, sex, "B1", "low", beard)
			low.queue_free()
		medium.queue_free()
		await process_frame
	if _groups.has("rl") or _groups.has("rlshape"):
		var high := Stage.spawn(_stage, sex, {}, {}, ActorRenderQuality.Quality.HIGH, 9803)
		high.hold_portrait_pose(self)
		for frame: int in 4:
			await process_frame
		if high.rl_head() == null:
			push_error("hair calibration: no RL head for " + sex)
		else:
			for s: int in (HIGH_POSITIONS if _groups.has("rl") else []):
				await _rl_hair(high, sex, s)
			if sex == "male" and _groups.has("rl"):
				for beard: int in BEARDS:
					await _rl_beard(high, sex, beard)
			# P4 under the RL head (a legacy style), to show it is the classic path.
			for style: int in [2, 5]:
				await _legacy(high, sex, "P4", "high-rl", style, 50, 50, 50)
		if high.rl_head() != null and _groups.has("rlshape") and _mode == "fit":
			for shape: Array in [[0, 0], [20, 80], [85, 30], [100, 100]]:
				await _rl_hair(high, sex, 75 if sex == "male" else 25, int(shape[0]), int(shape[1]))
		high.release_portrait_pose(self)
		high.queue_free()
		await process_frame
	if _groups.has("high") or _groups.has("shapehigh") or _groups.has("positionshigh") or _groups.has("shapefinishhigh"):
		_set_rl_switch(true)
		var classic := Stage.spawn(_stage, sex, {}, {}, ActorRenderQuality.Quality.HIGH, 9804)
		for frame: int in 4:
			await process_frame
		if _groups.has("high"):
			var positions: Array = HIGH_POSITIONS.duplicate() if _mode == "fit" else VERIFY_POSITIONS.duplicate()
			for s: int in positions:
				for style: int in STYLES:
					await _legacy(classic, sex, "P4", "high", style, s, 50, 50)
			for beard: int in BEARDS:
				await _beard(classic, sex, "B2", "high", beard)
		if _groups.has("shapehigh"):
			for style: int in STYLES:
				for shape: Array in _shapes():
					for s: int in ([50] if _mode == "fit" else [12, 50, 88]):
						await _legacy(classic, sex, "P4", "high", style, s, int(shape[0]), int(shape[1]))
		if _groups.has("positionshigh") and _mode == "fit":
			for s: int in BETWEEN_POSITIONS:
				for style: int in STYLES:
					await _legacy(classic, sex, "P4", "high", style, s, 50, 50)
		if _groups.has("shapefinishhigh") and _mode == "fit":
			for s: int in FIT_POSITIONS:
				for style: int in STYLES:
					for shape: Array in _coarse_shapes():
						await _legacy(classic, sex, "P4", "high", style, s, int(shape[0]), int(shape[1]))
		classic.queue_free()
		await process_frame
		_set_rl_switch(false)


# ------------------------------------------------------------ instances

## The coarse grid less its centre (shape factors at the other finishes).
func _coarse_shapes() -> Array:
	var result: Array = []
	for length: int in SHAPE_GRID_COARSE:
		for volume: int in SHAPE_GRID_COARSE:
			if length != 50 or volume != 50:
				result.append([length, volume])
	return result


## The shapes a shape group measures: the grid less its centre (fit), or the
## two spot-check shapes (verify).
func _shapes() -> Array:
	if _mode != "fit":
		return SHAPES
	var result: Array = []
	for length: int in SHAPE_GRID:
		for volume: int in SHAPE_GRID:
			if length != 50 or volume != 50:
				result.append([length, volume])
	return result

func _finish_look(s: int) -> Dictionary:
	var pair: Array = FINISH_LOOKS[s]
	return {"hair_detail": pair[0], "hair_finish": pair[1]}


func _legacy(actor: ReplicatedActor3D, sex: String, path: String, quality: String, style: int, s: int,
		length: int, volume: int) -> void:
	var look := {"facial_hair": 0, "hair_length": length, "hair_volume": volume}
	look.merge(_finish_look(s), true)
	var key := "%s/%s/%d/%d" % [sex, path, style, s]
	var keep := func(mesh: MeshInstance3D) -> bool: return _is_legacy_hair(mesh, actor)
	await _measure_appearance(actor, sex, key, path, quality, style, s, look, keep,
		{"length": length, "volume": volume})


func _beard(actor: ReplicatedActor3D, sex: String, path: String, quality: String, beard: int) -> void:
	var look := {"facial_hair": beard, "hair_detail": 0, "hair_finish": 0}
	var key := "%s/%s/%d/50" % [sex, path, beard]
	var keep := func(mesh: MeshInstance3D) -> bool: return str(mesh.name) == "PortraitFacialHair"
	await _measure_appearance(actor, sex, key, path, quality, beard, 50, look, keep, {}, true)


## One Low/Medium/classic High path: its mask, then each fit dye (forced
## through the game's path) or each hold-out colour (through the resolver).
func _measure_appearance(actor: ReplicatedActor3D, sex: String, key: String, path: String, quality: String,
		style: int, s: int, look: Dictionary, keep: Callable, extra: Dictionary, beard: bool = false) -> void:
	var record := {"key": key, "path": path, "quality": quality, "sex": sex, "style": style, "s": s, "samples": []}
	record.merge(extra, true)
	var hair_style := 0 if beard else style
	var started := Time.get_ticks_msec()
	if _mode == "fit":
		await _apply_forced(actor, sex, look, hair_style, Vector3(0.5, 0.5, 0.5))
		var mask := await _mask(actor, keep)
		record["pixels"] = mask.size()
		for dye: Array in FIT_DYES:
			var d := Vector3(float(dye[0]), float(dye[1]), float(dye[2]))
			await _apply_forced(actor, sex, look, hair_style, d)
			var mu := await _mean(actor, keep, mask)
			(record.samples as Array).append({"dye": _array(d), "mu": _array(mu), "clipped": _clipped})
	else:
		Colours.set_hair_tables({})
		var mask := PackedInt32Array()
		for wire_value: Array in _report.verifyWires:
			var wire := Vector3i(int(wire_value[0]), int(wire_value[1]), int(wire_value[2]))
			var apparent := Colours.triple_colour(wire)
			var index := Colours.nearest_hair_index(apparent, sex)
			var custom := look.merged({"hair": AppearanceVariants.pack_hair(hair_style, index),
				"hair_hue": wire.x, "hair_sat": wire.y, "hair_light": wire.z}, true)
			actor.apply_appearance_variants(custom)
			Stage.pose(actor, "Rest", 0.0)
			if mask.is_empty():
				mask = await _mask(actor, keep)
				record["pixels"] = mask.size()
			var expected: Dictionary = Colours.hair_dye_linear(Colours.to_linear(apparent), sex, path, style, float(s))
			var mu := await _mean(actor, keep, mask)
			(record.samples as Array).append({"wire": wire_value, "apparent": _array(Colours.to_linear(apparent)),
				"reach": expected.reach, "dye": _array(expected.dye), "mu": _array(mu), "clipped": _clipped})
	record["seconds"] = (Time.get_ticks_msec() - started) / 1000.0
	(_report.instances as Array).append(record)
	print("hair calibration %s %s (%d px, %.1f s)" % [key, quality, int(record.get("pixels", 0)), record.seconds])


## Draws `look` with the dye forced to `dye` on every Low/Medium/classic High
## hair and beard path of this sex: a measured linear entry whose inverse is
## exactly that dye for the fit wire's apparent colour.
func _apply_forced(actor: ReplicatedActor3D, sex: String, look: Dictionary, hair_style: int, dye: Vector3) -> void:
	var apparent := Colours.to_linear(Colours.triple_colour(FIT_WIRE))
	var skin_gain: Vector3 = Colours.SKIN_GAIN[sex]
	var gain := Vector3.ZERO
	for axis: int in 3:
		gain[axis] = skin_gain[axis] * apparent[axis] / dye[axis] if dye[axis] > 0.0 else 1e12
	var entry := {"gain": _array(gain), "floor": [0.0, 0.0, 0.0]}
	var paths := {}
	for path: String in ["P1", "P2", "P3", "P4", "B1", "B2"]:
		for style: int in range(10):
			for s: int in [0, 25, 37, 50, 63, 75, 100]:
				paths["%s/%s/%d/%d" % [sex, path, style, s]] = entry
	Colours.set_hair_tables(paths)
	var index := Colours.nearest_hair_index(Colours.triple_colour(FIT_WIRE), sex)
	actor.apply_appearance_variants(look.merged({"hair": AppearanceVariants.pack_hair(hair_style, index),
		"hair_hue": FIT_WIRE.x, "hair_sat": FIT_WIRE.y, "hair_light": FIT_WIRE.z}, true))
	Stage.pose(actor, "Rest", 0.0)


func _rl_hair(actor: ReplicatedActor3D, sex: String, s: int, length: int = -1, volume: int = -1) -> void:
	var module: String = MODULE[sex]
	var level := Map.detail_level(float(s), module)
	var key := "%s/P5/%s/%d" % [sex, module, level]
	var look := {"hair": AppearanceVariants.pack_hair(MODULE_SLOT[sex], 2), "facial_hair": 0}
	if length >= 0:
		look.merge({"hair_length": length, "hair_volume": volume}, true)
	look.merge(_finish_look(s), true)
	var keep := func(mesh: MeshInstance3D) -> bool: return _is_rl_hair(mesh, actor)
	await _measure_rl(actor, sex, key, "P5", s, level, look, keep, false, 0,
		{"length": length, "volume": volume} if length >= 0 else {})


func _rl_beard(actor: ReplicatedActor3D, sex: String, beard: int) -> void:
	var name: String = Map.BEARDS[beard]
	var key := "%s/B3/%s/50" % [sex, name]
	var look := {"hair": AppearanceVariants.pack_hair(0, 2), "facial_hair": beard, "hair_detail": 0, "hair_finish": 0}
	var keep := func(mesh: MeshInstance3D) -> bool: return str(mesh.name).begins_with("RLBeard")
	await _measure_rl(actor, sex, key, "B3", 50, 50, look, keep, true, beard)


## One RL path: the RL face from the look; fit sets its hair or beard colour
## directly, verify draws hold-out colours through the actor and the map.
func _measure_rl(actor: ReplicatedActor3D, sex: String, key: String, path: String, s: int, level: int,
		look: Dictionary, keep: Callable, beard: bool, beard_style: int = 0, extra: Dictionary = {}) -> void:
	var record := {"key": key, "path": path, "quality": "high-rl", "sex": sex, "s": s, "level": level,
		"style": beard_style if beard else MODULE_SLOT[sex], "samples": []}
	record.merge(extra, true)
	var started := Time.get_ticks_msec()
	var rig := actor.rl_head()
	if _mode == "fit":
		actor.apply_appearance_variants(look)
		Stage.pose(actor, "Rest", 0.0)
		var face := RLHeadPortraitMap.face(look, sex)
		var set_dye := func(dye: Vector3) -> void:
			var colour := Colours.to_srgb(dye)
			if beard:
				face.beard_color = colour
				face.beard_color_set = true
			else:
				face.hair_color = colour
			rig.apply_appearance(face)
		set_dye.call(Vector3(0.5, 0.5, 0.5))
		var mask := await _mask(actor, keep)
		record["pixels"] = mask.size()
		for dye: Array in RL_DYES:
			var d := Vector3(float(dye[0]), float(dye[1]), float(dye[2]))
			set_dye.call(d)
			var mu := await _mean(actor, keep, mask)
			(record.samples as Array).append({"dye": _array(d), "mu": _array(mu), "clipped": _clipped})
	else:
		var mask := PackedInt32Array()
		for wire_value: Array in _report.verifyWires:
			var wire := Vector3i(int(wire_value[0]), int(wire_value[1]), int(wire_value[2]))
			var apparent := Colours.triple_colour(wire)
			var index := Colours.nearest_hair_index(apparent, sex)
			var custom := look.merged({"hair": AppearanceVariants.pack_hair(
				0 if beard else MODULE_SLOT[sex], index), "hair_hue": wire.x, "hair_sat": wire.y, "hair_light": wire.z}, true)
			actor.apply_appearance_variants(custom)
			Stage.pose(actor, "Rest", 0.0)
			if mask.is_empty():
				mask = await _mask(actor, keep)
				record["pixels"] = mask.size()
			var face := RLHeadPortraitMap.face(custom, sex)
			var dye := Colours.to_linear(face.beard_color if beard else face.hair_color)
			var mu := await _mean(actor, keep, mask)
			(record.samples as Array).append({"wire": wire_value, "apparent": _array(Colours.to_linear(apparent)),
				"dye": _array(dye), "level": face.hair_detail, "mu": _array(mu), "clipped": _clipped})
	record["seconds"] = (Time.get_ticks_msec() - started) / 1000.0
	(_report.instances as Array).append(record)
	print("hair calibration %s (%d px, %.1f s)" % [key, int(record.get("pixels", 0)), record.seconds])


# ------------------------------------------------------------ sampling

func _is_legacy_hair(mesh: MeshInstance3D, actor: ReplicatedActor3D) -> bool:
	var walker: Node = mesh
	while walker != null and walker != actor:
		var name := str(walker.name)
		if name.begins_with("AppearanceHair_"):
			return name != RLHeadRig.HAIR_NODE_NAME
		walker = walker.get_parent()
	return false


func _is_rl_hair(mesh: MeshInstance3D, actor: ReplicatedActor3D) -> bool:
	var walker: Node = mesh
	while walker != null and walker != actor:
		if str(walker.name) == RLHeadRig.HAIR_NODE_NAME:
			return true
		walker = walker.get_parent()
	return false


func _array(v: Vector3) -> Array:
	return [v.x, v.y, v.z]


func _show_only(actor: ReplicatedActor3D, keep: Callable) -> Dictionary:
	var saved := {}
	for child: Node in _stage.get_children():
		if child is ReplicatedActor3D and child != actor:
			saved[child] = (child as Node3D).visible
			(child as Node3D).visible = false
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		saved[mesh] = mesh.visible
		mesh.visible = mesh.visible and keep.call(mesh)
	return saved


func _restore(saved: Dictionary) -> void:
	for node: Variant in saved:
		if is_instance_valid(node):
			(node as Node3D).visible = saved[node]


func _render(backdrop: Color) -> Image:
	_environment.environment.background_color = backdrop
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	if image.get_format() != Image.FORMAT_RGBA8:
		image.convert(Image.FORMAT_RGBA8)
	return image


## The hair-only pixels: the same over a black and a white backdrop (and not
## the white backdrop itself), the meshes `keep` picks alone.
func _mask(actor: ReplicatedActor3D, keep: Callable) -> PackedInt32Array:
	Stage.frame(_camera, actor, "front")
	var saved := _show_only(actor, keep)
	var original := _environment.environment.background_color
	var dark := (await _render(Color.BLACK)).get_data()
	var light := (await _render(Color.WHITE)).get_data()
	_environment.environment.background_color = original
	_restore(saved)
	var mask := PackedInt32Array()
	for pixel: int in range(0, dark.size() / 4):
		var at := pixel * 4
		if absi(dark[at] - light[at]) + absi(dark[at + 1] - light[at + 1]) + absi(dark[at + 2] - light[at + 2]) > 1:
			continue
		if light[at] >= 254 and light[at + 1] >= 254 and light[at + 2] >= 254:
			continue
		mask.append(at)
	if mask.is_empty():
		push_warning("hair calibration: no hair pixels")
	return mask


## The linear mean over `mask` of one render over black, divided by the
## exposure; `_clipped` counts the mask pixels with a channel at 254 or more.
func _mean(actor: ReplicatedActor3D, keep: Callable, mask: PackedInt32Array) -> Vector3:
	Stage.frame(_camera, actor, "front")
	var saved := _show_only(actor, keep)
	var original := _environment.environment.background_color
	var data := (await _render(Color.BLACK)).get_data()
	_environment.environment.background_color = original
	_restore(saved)
	var r := 0.0
	var g := 0.0
	var b := 0.0
	_clipped = 0
	for at: int in mask:
		r += _linear[data[at]]
		g += _linear[data[at + 1]]
		b += _linear[data[at + 2]]
		if data[at] >= 254 or data[at + 1] >= 254 or data[at + 2] >= 254:
			_clipped += 1
	var count := maxf(1.0, float(mask.size())) * _exposure
	return Vector3(r / count, g / count, b / count)
