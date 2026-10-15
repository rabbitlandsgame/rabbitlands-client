extends SceneTree
## Renders every torso design on every rig it ships for, as contact sheets.
##
## Added 2026-08-29 for Eloria Client.  The fit checker says whether a garment
## covers the body; it says nothing about whether the garment looks like the
## drawing it came from.  This is the other half of the evidence: each design
## from the front, the back, both sides and a three-quarter angle taken above
## the shoulder line - which is the one view that shows a shoulder seam at all -
## plus the posed frames the shoulder has to survive, and one wearing a cape.
##
## Headless has no framebuffer, so this must run WITHOUT --headless:
##
##   Godot_v4.7.2-stable_win64_console.exe --path . \
##       --script res://tests/torso_contact_sheets.gd
##
## Output goes to ELORIA_ARTIFACT_DIR, or user://torso-sheets by default.

## One cell of a sheet. Shots are taken through a SubViewport with its own 3D
## world, which is what makes a cell exactly this size and nothing else's.
## The root window is whatever the platform gave us and does not resize to
## order, so cropping CELL out of it took the top-left corner of a wider frame;
## and a SubViewport *without* own_world_3d shares the game's world and
## composites its sky and its nameplates behind every garment.
const CELL := Vector2i(320, 460)
const SHEET_COLUMNS := 5
## Sixty-four designs starting here; see eloria-assets/tools/torso_designs.py.
const FIRST_VISUAL := 120
const DESIGN_COUNT := 64
const PER_SHEET := 8
## Nameplates, selection rings and map dots live on this layer. Culling it is
## what stops "Unknown actor" being written across every cell.
const GAMEPLAY_ONLY_VISUAL_LAYER := 2

## Front, back, both sides, and the three-quarter view from above the shoulder.
## The last one is the point of the exercise: a seam over the deltoid is
## invisible from straight on and obvious from up here.
const ANGLES: Array[Dictionary] = [
	{"name": "front", "yaw": 0.0, "pitch": -6.0},
	{"name": "back", "yaw": 180.0, "pitch": -6.0},
	{"name": "left", "yaw": 90.0, "pitch": -6.0},
	{"name": "right", "yaw": -90.0, "pitch": -6.0},
	{"name": "over-shoulder", "yaw": 38.0, "pitch": -34.0},
]

## The clips criterion 5 names. Two of them raise the arm through the shoulder
## seam and one folds the waist.
const POSES: Array[Dictionary] = [
	{"name": "Idle_Subtle", "time": 0.5},
	{"name": "Jog", "time": 0.3},
	{"name": "Sprint", "time": 0.25},
	{"name": "Sword_Attack", "time": 0.35},
	{"name": "Bow_Pull_Hold", "time": 0.4},
	{"name": "Meditate", "time": 0.5},
]

## The reference rig and the one fit-group rig the torso set ships a variant for.
## See FIT_GROUPS in eloria-assets/tools/equipment_authoring.py: the measured
## variant list is male-reference plus "bust", and nothing else.
const RIGS: Array[String] = ["luminous_male", "stoneborn_female"]

var _models: Dictionary
var _equipment: Dictionary
var _animations: Dictionary
var _out := ""
var _camera: Camera3D
var _stage: Node3D
var _viewport: SubViewport
## Where the actor actually stands. The coordinate adapter places it where the
## server would - (0.5, 0, -0.5) for a tile origin - and setting the position
## back to zero does not stick, so the camera frames what is there instead.
var _subject := Vector3.ZERO
var _written := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_out = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _out.is_empty():
		_out = ProjectSettings.globalize_path("user://torso-sheets")
	DirAccess.make_dir_recursive_absolute(_out)
	_models = (_json("res://data/actors/models.json").get("models", {}) as Dictionary)
	_equipment = _json("res://data/actors/equipment.json")
	_build_stage()

	for rig: String in RIGS:
		for sheet: int in range(DESIGN_COUNT / PER_SHEET):
			await _render_sheet(rig, sheet)
	await _render_posed(RIGS[0], FIRST_VISUAL + 8)
	await _render_caped(RIGS[0], FIRST_VISUAL + 8)

	print("torso contact sheets: wrote %d to %s" % [_written, _out])
	quit(0 if _written > 0 else 1)

## One image per eight designs: a row each, a column per angle.
func _render_sheet(rig: String, sheet: int) -> void:
	var page := Image.create(CELL.x * SHEET_COLUMNS, CELL.y * PER_SHEET,
		false, Image.FORMAT_RGBA8)
	page.fill(Color(0.10, 0.10, 0.12))
	for row: int in range(PER_SHEET):
		var visual: int = FIRST_VISUAL + sheet * PER_SHEET + row
		var actor := await _dress(rig, visual, {})
		if actor == null:
			continue
		for column: int in range(ANGLES.size()):
			var shot := await _capture(ANGLES[column])
			if shot != null:
				page.blit_rect(shot, Rect2i(Vector2i.ZERO, CELL),
					Vector2i(column * CELL.x, row * CELL.y))
		actor.queue_free()
		await process_frame
	_save(page, "torso-%s-sheet%d.png" % [rig, sheet + 1])

## The same design through the clips the shoulder has to survive.
func _render_posed(rig: String, visual: int) -> void:
	var page := Image.create(CELL.x * POSES.size(), CELL.y * 2, false,
		Image.FORMAT_RGBA8)
	page.fill(Color(0.10, 0.10, 0.12))
	var actor := await _dress(rig, visual, {})
	if actor == null:
		return
	for column: int in range(POSES.size()):
		_pose(actor, POSES[column])
		await process_frame
		# Straight on, and then from above the shoulder line where a seam shows.
		var front := await _capture(ANGLES[0])
		if front != null:
			page.blit_rect(front, Rect2i(Vector2i.ZERO, CELL), Vector2i(column * CELL.x, 0))
		var over := await _capture(ANGLES[4])
		if over != null:
			page.blit_rect(over, Rect2i(Vector2i.ZERO, CELL), Vector2i(column * CELL.x, CELL.y))
	actor.queue_free()
	await process_frame
	_save(page, "torso-%s-posed.png" % rig)

## The cape hangs off spine_03, which is the volume a raised yoke occupies.
func _render_caped(rig: String, visual: int) -> void:
	var page := Image.create(CELL.x * ANGLES.size(), CELL.y, false,
		Image.FORMAT_RGBA8)
	page.fill(Color(0.10, 0.10, 0.12))
	var actor := await _dress(rig, visual, {2: 100})
	if actor == null:
		return
	for column: int in range(ANGLES.size()):
		var shot := await _capture(ANGLES[column])
		if shot != null:
			page.blit_rect(shot, Rect2i(Vector2i.ZERO, CELL), Vector2i(column * CELL.x, 0))
	actor.queue_free()
	await process_frame
	_save(page, "torso-%s-caped.png" % rig)

func _build_stage() -> void:
	_viewport = SubViewport.new()
	_viewport.size = CELL
	_viewport.own_world_3d = true
	_viewport.transparent_bg = false
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(_viewport)
	_stage = Node3D.new()
	_viewport.add_child(_stage)
	_camera = Camera3D.new()
	# Everything the player sees but a garment sheet should not: the nameplate,
	# the selection ring and the map dot all sit on the gameplay-only layer.
	_camera.cull_mask = ~GAMEPLAY_ONLY_VISUAL_LAYER
	_camera.fov = 42.0
	_stage.add_child(_camera)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-38.0, 34.0, 0.0)
	key.light_energy = 1.6
	_stage.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-12.0, -140.0, 0.0)
	fill.light_energy = 0.6
	_stage.add_child(fill)
	var environment := WorldEnvironment.new()
	var settings := Environment.new()
	settings.background_mode = Environment.BG_COLOR
	settings.background_color = Color(0.10, 0.10, 0.12)
	settings.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	settings.ambient_light_color = Color(0.44, 0.46, 0.52)
	settings.ambient_light_energy = 1.0
	environment.environment = settings
	# Also on the camera: the project ships a default environment with a sky,
	# and in an own-world SubViewport that sky was still drawn behind the
	# garment as a blue band across the top of every cell.
	_camera.environment = settings
	_stage.add_child(environment)

func _dress(rig: String, visual: int, extra: Dictionary) -> ReplicatedActor3D:
	var config: Dictionary = _models.get(rig, {}) as Dictionary
	if config.is_empty():
		push_error("no model for rig " + rig)
		return null
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	var visuals: Dictionary = {5: visual}
	visuals.merge(extra, true)
	var dto := {"actor_id": 1, "x": 0, "y": 0, "rotation": 0, "name": "",
		"appearance": {"skin": 1, "hair": 2, "eyes": 3,
			"shirt": 1, "pants": 2, "boots": 3, "head": 1},
		"equipment_visuals": visuals}
	var map := str(config.get("animationMap", "res://data/animations/luminous.json"))
	if not _animations.has(map):
		_animations[map] = _json(map)
	var errors := actor.configure(dto,
		CoordinateAdapter.new({"walkingHeight": 0.0, "invertServerY": true}),
		config, _animations[map] as Dictionary, _equipment)
	if not errors.is_empty():
		push_error("visual %d on %s: %s" % [visual, rig, ", ".join(errors)])
	for _settle: int in range(4):
		await process_frame
	_subject = actor.position
	return actor

func _pose(actor: ReplicatedActor3D, pose: Dictionary) -> void:
	var player: AnimationPlayer = null
	for node: Node in actor.find_children("*", "AnimationPlayer", true, false):
		player = node as AnimationPlayer
		break
	if player == null:
		return
	var clip := str(pose.get("name", ""))
	if not player.has_animation(clip):
		return
	player.play(clip)
	player.seek(float(pose.get("time", 0.0)), true)
	player.pause()

## Frames the torso, not the whole actor: this is a sheet about one garment.
func _capture(angle: Dictionary) -> Image:
	var yaw := deg_to_rad(float(angle.get("yaw", 0.0)))
	var pitch := deg_to_rad(float(angle.get("pitch", 0.0)))
	var focus := _subject + Vector3(0.0, 1.16, 0.0)
	var distance := 1.75
	var offset := Vector3(
		sin(yaw) * cos(pitch), -sin(pitch), cos(yaw) * cos(pitch)) * distance
	_camera.position = focus + offset
	_camera.look_at(focus, Vector3.UP)
	_camera.make_current()
	# Long enough for the skinned rebind and the material upload to land.
	for _settle: int in range(8):
		await process_frame
	var texture := _viewport.get_texture()
	if texture == null:
		return null
	var image := texture.get_image()
	if image.get_size() != CELL:
		push_error("viewport rendered %s, expected %s" % [image.get_size(), CELL])
	return image

func _save(page: Image, name: String) -> void:
	if page.save_png(_out.path_join(name)) == OK:
		_written += 1
		print("wrote ", name)
	else:
		push_error("could not write " + name)

func _json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		push_error("missing " + path)
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	return parsed as Dictionary if parsed is Dictionary else {}
