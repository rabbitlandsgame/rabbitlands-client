extends SceneTree
## Renders every leg garment beside every rig it ships for, as contact sheets.
##
## The fit checker settles whether a garment contains the body. It cannot settle
## whether the garment looks like the picture it was drawn from, and sixty-four
## designs is far past what anyone will check by opening them one at a time. So
## each design gets one sheet: five angles across the top - front, back, both
## sides and a low three-quarter, which is the angle a player actually sees a
## character from - and the four posed clips underneath.
##
## Run WITHOUT `--headless`; headless has no framebuffer and every capture comes
## back blank.
##
##     Godot_v4.7.2-stable_win64_console.exe --path godot-client \
##         --script res://tests/legwear_contact_sheets.gd
##
## `ELORIA_LEGWEAR_SHEETS` picks the output directory, `ELORIA_LEGWEAR_ONLY`
## limits the run to a comma-separated list of visual ids while iterating.

const CELL := Vector2i(240, 400)
const SETTLE := 10

## Camera yaw in degrees, and the pitch that goes with it. The last is the low
## three-quarter: below eye level, because that is where the game camera sits
## and it is the angle that shows a hem meeting a boot.
const ANGLES: Array[Vector3] = [
	Vector3(0, 0, 0), Vector3(180, 0, 0), Vector3(90, 0, 0),
	Vector3(270, 0, 0), Vector3(35, -12, 0),
]
const ANGLE_NAMES: Array[String] = ["front", "back", "left", "right", "low 3/4"]
const CLIPS: Array[String] = ["Jog", "Sprint", "Meditate", "Sitting_Exit"]

var _models: Dictionary
var _equipment: Dictionary
var _out_dir: String
var _only: Array[String] = []
var _failures := 0
var _debug := false

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_out_dir = OS.get_environment("ELORIA_LEGWEAR_SHEETS")
	if _out_dir.is_empty():
		_out_dir = "user://legwear_sheets"
	DirAccess.make_dir_recursive_absolute(_out_dir)
	var only := OS.get_environment("ELORIA_LEGWEAR_ONLY")
	if not only.is_empty():
		for piece in only.split(",", false):
			_only.append(piece.strip_edges())

	_debug = not OS.get_environment("ELORIA_LEGWEAR_DEBUG").is_empty()
	_models = (_json("res://data/actors/models.json").get("models", {}) as Dictionary)
	_equipment = _json("res://data/actors/equipment.json")
	root.size = CELL

	var world := _build_world()
	var designs := _designs()
	print("legwear sheets: %d designs -> %s" % [designs.size(), _out_dir])
	for design: Dictionary in designs:
		for rig: String in _rigs_for(design):
			await _sheet(world, design, rig)
	print("legwear sheets: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

## Every part-4 model the registry carries a `kind` for, which is the rebuilt
## set; the generic tier and the culture pieces predate this and are left alone.
func _designs() -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	for key: String in (_equipment.get("models", {}) as Dictionary):
		if not key.begins_with("4:"):
			continue
		var model: Dictionary = _equipment["models"][key]
		if not model.has("kind"):
			continue
		var visual := int(key.split(":")[1])
		if visual < 107:
			continue
		if not _only.is_empty() and not _only.has(str(visual)):
			continue
		out.append({"visual": visual, "kind": str(model["kind"]),
			"scene": str(model.get("scene", "")),
			"variants": (model.get("variants", {}) as Dictionary)})
	out.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return int(a["visual"]) < int(b["visual"]))
	return out

## The reference rig plus one wearer per fit group the design ships a variant
## for. Rendering all sixteen races would be sixteen pictures of the same mesh
## refitted; what is worth looking at is each *authored* mesh.
func _rigs_for(design: Dictionary) -> Array[String]:
	var rigs: Array[String] = ["luminous_male"]
	for group: String in (design["variants"] as Dictionary):
		var spec: Dictionary = design["variants"][group]
		var rig := str(spec.get("authoredFor", ""))
		if not rig.is_empty() and not rigs.has(rig):
			rigs.append(rig)
	return rigs

func _environment() -> Environment:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.94, 0.90, 0.82)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.62, 0.60, 0.58)
	env.ambient_light_energy = 1.0
	return env


func _build_world() -> Node3D:
	var world := Node3D.new()
	root.add_child(world)
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.94, 0.90, 0.82)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.62, 0.60, 0.58)
	env.ambient_light_energy = 1.0
	var we := WorldEnvironment.new()
	we.environment = env
	world.add_child(we)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-42, -38, 0)
	key.light_energy = 1.5
	world.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-14, 140, 0)
	fill.light_energy = 0.55
	world.add_child(fill)
	return world

func _sheet(world: Node3D, design: Dictionary, rig: String) -> void:
	var visual := int(design["visual"])
	if not _models.has(rig):
		_failures += 1
		push_error("no model config for " + rig)
		return
	# One actor and one camera for the whole sheet, moved between shots.
	# Rebuilding them per cell - which is what this did first - meant a fresh
	# actor was photographed before its meshes had resolved and a fresh camera
	# fought the old one for `current`, so most cells came back as background
	# and the few that did not were torn across two frames.
	var actor := ReplicatedActor3D.new()
	world.add_child(actor)
	var model_config: Dictionary = _models[rig]
	var animation_config: Dictionary = _json(str(model_config.get(
		"animationMap", "res://data/animations/luminous.json")))
	# Parts 5 and 6 come along deliberately: the waist and the boot cuff are
	# seams with the torso and the footwear, and a leg garment photographed on
	# its own hides exactly the two joins most likely to be wrong.
	var dto := {"actor_id": 1, "x": 0, "y": 0, "rotation": 0,
		"appearance": {"skin": 1, "hair": 2, "eyes": 3,
			"shirt": 1, "pants": 2, "boots": 3, "head": 1},
		"equipment_visuals": {4: visual, 5: 110, 6: 100}}
	var adapter := CoordinateAdapter.new({"walkingHeight": 0.0, "invertServerY": true})
	actor.configure(dto, adapter, model_config, animation_config, _equipment)

	var camera := Camera3D.new()
	camera.fov = 32.0
	# The camera carries the environment itself.  A `WorldEnvironment` node was
	# not enough - the actor scene brings its own world and the captures came
	# back against default sky, which is where the band of blue across every
	# early sheet came from.
	camera.environment = _environment()
	world.add_child(camera)
	camera.current = true
	# Let the actor's meshes resolve before the first capture; the equipment is
	# loaded and rebound asynchronously and the first frame after `configure`
	# has a body with nothing on it.
	for _warm in range(SETTLE * 2):
		await process_frame

	var cells: Array[Image] = []
	for index in ANGLES.size():
		cells.append(await _shoot(actor, camera, ANGLES[index], ""))
	for clip: String in CLIPS:
		cells.append(await _shoot(actor, camera, ANGLES[4], clip))

	actor.queue_free()
	camera.queue_free()
	await process_frame

	var sheet := _tile(cells, 5)
	var path := "%s/4-%03d__%s.png" % [_out_dir, visual, rig]
	if sheet.save_png(path) != OK:
		_failures += 1
		push_error("could not write " + path)

## One capture: place the camera, optionally hold a pose, settle, read back.
func _shoot(actor: ReplicatedActor3D, camera: Camera3D, angle: Vector3,
		clip: String) -> Image:
	if actor.animation_player != null:
		if clip.is_empty():
			actor.animation_player.stop()
		elif actor.animation_player.has_animation(clip):
			actor.animation_player.play(clip)
			actor.animation_player.seek(
				actor.animation_player.get_animation(clip).length * 0.5, true)
			actor.animation_player.pause()
	var yaw := deg_to_rad(angle.x)
	var pitch := deg_to_rad(angle.y)
	# Framed on the legs rather than the whole figure: this is a trouser sheet
	# and a full-length shot spends most of its pixels on a torso.  The focus
	# sits at mid-thigh and the distance keeps the hem and the boot cuff in
	# frame, which is the join the sheet exists to show.
	# Framed on the actor rather than on the origin.  `configure` places the
	# actor through the coordinate adapter, so it does not stand at (0,0,0) and
	# a camera aimed there photographs the empty ground beside it - which is why
	# the figure sat half out of frame on the first sheets whatever the distance.
	var aim: Node3D = actor.get_node_or_null("NativeModel") as Node3D
	var base: Vector3 = aim.global_position if aim != null else actor.global_position
	var focus := base + Vector3(0, 0.72, 0)
	var distance := 3.15
	camera.position = focus + Vector3(
		sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * distance
	camera.look_at(focus, Vector3.UP)
	for _settle in range(SETTLE):
		await process_frame
	# Wait for the renderer, not just the scene tree.  `process_frame` says the
	# frame's logic is done, not that the GPU has finished drawing it, and
	# reading the framebuffer on that signal returns whatever is in it at the
	# time - which was the old camera position down one half of the image and
	# the new one down the other, plus a band of unclear sky.  Every figure on
	# the first sheets was torn vertically for this reason and it looked for all
	# the world like a tiling bug.
	await RenderingServer.frame_post_draw
	var raw := root.get_texture().get_image()
	var cell := _fit_to_cell(raw)
	if _debug:
		print("  capture raw %v -> cell %v (want %v)" % [raw.get_size(),
			cell.get_size(), CELL])
	return cell

## Bring a capture to exactly `CELL`, whatever the window happens to be.
##
## `root.size` is a request, not a promise - the OS window keeps its own size
## from the project settings - so the framebuffer comes back at something like
## 1152x648 however small the viewport is asked to be. Blitting that straight
## into a 240-wide cell overflowed into the next three, which is why the first
## sheets had figures sliced across cell boundaries and bands of sky where the
## neighbouring capture should have been. Crop to the cell's aspect about the
## centre, then scale: the framing is then the same whatever machine renders it.
func _fit_to_cell(image: Image) -> Image:
	var size := image.get_size()
	if size.x <= 0 or size.y <= 0:
		return Image.create(CELL.x, CELL.y, false, Image.FORMAT_RGBA8)
	var want := float(CELL.x) / float(CELL.y)
	var have := float(size.x) / float(size.y)
	var crop := size
	if have > want:
		crop.x = int(round(float(size.y) * want))
	else:
		crop.y = int(round(float(size.x) / want))
	var origin := Vector2i((size.x - crop.x) / 2, (size.y - crop.y) / 2)
	var cell := Image.create(crop.x, crop.y, false, image.get_format())
	cell.blit_rect(image, Rect2i(origin, crop), Vector2i.ZERO)
	cell.resize(CELL.x, CELL.y, Image.INTERPOLATE_LANCZOS)
	return cell

func _tile(cells: Array[Image], columns: int) -> Image:
	var rows := int(ceil(float(cells.size()) / float(columns)))
	var sheet := Image.create(CELL.x * columns, CELL.y * rows, false,
		cells[0].get_format())
	sheet.fill(Color(0.87, 0.83, 0.74))
	for index in cells.size():
		var cell: Image = cells[index]
		if cell.get_format() != sheet.get_format():
			cell.convert(sheet.get_format())
		sheet.blit_rect(cell, Rect2i(Vector2i.ZERO, cell.get_size()),
			Vector2i((index % columns) * CELL.x, int(index / columns) * CELL.y))
	return sheet

func _json(path: String) -> Dictionary:
	var text := FileAccess.get_file_as_string(path)
	var parsed: Variant = JSON.parse_string(text)
	return parsed as Dictionary if parsed is Dictionary else {}
