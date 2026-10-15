extends SceneTree
## Renders every footwear design on every rig it ships for, from every angle.
##
## Sixty-four designs across two authored rigs is a hundred and twenty-eight
## meshes, and each has to be looked at from the front, the back, both sides and
## a low three-quarter where the sole and the heel are visible. That is six
## hundred and forty views, which is not a thing to shoot one at a time: they are
## composed into one contact sheet per concept sheet per rig, so a sheet of eight
## designs can be held up against the art it came from.
##
## Headless has no framebuffer, so this runs under a real display:
##   Godot.exe --path godot-client --script res://tests/footwear_contact_sheet.gd
## Pass ELORIA_FOOTWEAR_ONLY to limit it to one design while iterating.

const TILE := Vector2i(340, 460)
const ANGLES := [
	{"name": "front", "yaw": 0.0, "pitch": -8.0},
	{"name": "back", "yaw": 180.0, "pitch": -8.0},
	{"name": "left", "yaw": 90.0, "pitch": -8.0},
	{"name": "right", "yaw": -90.0, "pitch": -8.0},
	{"name": "low3q", "yaw": -34.0, "pitch": 24.0},
]
## Framed on the boot rather than the body: a whole actor at this tile size puts
## the thing being judged in the bottom eighth of the frame.
const LOOK_AT := Vector3(0.0, 0.16, 0.0)
const DISTANCE := 1.15

var _viewport: SubViewport
var _camera: Camera3D
var _world: Node3D
var _models: Dictionary
var _equipment: Dictionary
var _catalogue: Array = []
var _out := ""

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_models = (_json("res://data/actors/models.json").get("models", {}) as Dictionary)
	_equipment = _json("res://data/actors/equipment.json")
	var manifest: Dictionary = _json("res://../eloria-assets/footwear-fit.json")
	if manifest.is_empty():
		push_error("no footwear-fit.json; run build_footwear.py first")
		quit(1)
		return
	var only: String = OS.get_environment("ELORIA_FOOTWEAR_ONLY")
	for slug: String in manifest:
		if only.is_empty() or slug == only:
			var entry: Dictionary = manifest[slug] as Dictionary
			entry["slug"] = slug
			_catalogue.append(entry)
	_catalogue.sort_custom(func(a, b): return int(a["visual"]) < int(b["visual"]))

	_out = OS.get_environment("ELORIA_FOOTWEAR_RENDERS")
	if _out.is_empty():
		_out = ProjectSettings.globalize_path("res://../eloria-assets/footwear-renders")
	DirAccess.make_dir_recursive_absolute(_out)
	_build_stage()

	# Every build a design ships, not only the two it started with: the fit
	# groups that claim `boots` are settled by measurement, and a sheet that
	# only photographs the reference one is evidence about a quarter of what
	# ships.
	var groups := {"reference": "luminous_male",
		"feminine_foot": "luminous_female",
		"broad_foot": "stoneborn_male",
		"saurian": "ssarathi_male"}
	var sheets := {}
	for entry: Dictionary in _catalogue:
		var variants: Dictionary = entry.get("variants", {}) as Dictionary
		for group: String in groups:
			if not variants.has(group):
				continue
			var rig: String = str((variants[group] as Dictionary).get("authoredFor",
				groups[group]))
			var row: Image = await _render_row(entry, rig)
			var key := "sheet%d-%s" % [int(entry["sheet"]), group]
			if not sheets.has(key):
				sheets[key] = []
			(sheets[key] as Array).append({"image": row, "label": entry["label"]})
	var written := 0
	for key: String in sheets:
		var rows: Array = sheets[key] as Array
		var sheet := Image.create(TILE.x * ANGLES.size(), TILE.y * rows.size(),
			false, Image.FORMAT_RGBA8)
		sheet.fill(Color(0.09, 0.09, 0.11))
		for index in range(rows.size()):
			var row: Image = (rows[index] as Dictionary)["image"] as Image
			sheet.blit_rect(row, Rect2i(Vector2i.ZERO, row.get_size()),
				Vector2i(0, TILE.y * index))
		if sheet.save_png(_out.path_join(key + ".png")) == OK:
			written += 1
	print("footwear contact sheets: %d written to %s" % [written, _out])
	quit(0)

func _build_stage() -> void:
	_viewport = SubViewport.new()
	_viewport.size = TILE
	_viewport.transparent_bg = false
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(_viewport)
	_world = Node3D.new()
	_viewport.add_child(_world)
	var environment := WorldEnvironment.new()
	var settings := Environment.new()
	settings.background_mode = Environment.BG_COLOR
	settings.background_color = Color(0.94, 0.91, 0.84)
	settings.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	settings.ambient_light_color = Color(0.62, 0.63, 0.68)
	settings.ambient_light_energy = 1.15
	environment.environment = settings
	_world.add_child(environment)
	var key_light := DirectionalLight3D.new()
	key_light.rotation_degrees = Vector3(-42.0, -38.0, 0.0)
	key_light.light_energy = 1.5
	_world.add_child(key_light)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-14.0, 148.0, 0.0)
	fill.light_energy = 0.55
	_world.add_child(fill)
	_camera = Camera3D.new()
	_camera.fov = 34.0
	_world.add_child(_camera)

func _render_row(entry: Dictionary, rig: String) -> Image:
	var actor := ReplicatedActor3D.new()
	_world.add_child(actor)
	var model_config: Dictionary = _models.get(rig, {}) as Dictionary
	var animation: Dictionary = _json(str(model_config.get(
		"animationMap", "res://data/animations/luminous.json")))
	var dto := {"actor_id": 1, "x": 0, "y": 0, "rotation": 0,
		"appearance": {"skin": 1, "hair": 2, "eyes": 3,
			"shirt": 1, "pants": 2, "boots": 3, "head": 0},
		"equipment_visuals": {6: int(entry["visual"])}}
	var adapter := CoordinateAdapter.new({"walkingHeight": 0.0, "invertServerY": true})
	actor.configure(dto, adapter, model_config, animation, _equipment)
	# The adapter puts an actor where the server says; for a turntable it goes
	# at the origin, which is what the camera is aimed at.
	actor.global_position = Vector3.ZERO
	var diagnostics: Dictionary = actor.equipment_diagnostics()
	if int(diagnostics.get("skinned", 0)) < 1:
		push_error("%s on %s attached no skinned boot" % [entry["slug"], rig])

	# Framed on what was actually built rather than on a guessed height. The
	# boots sit where the wearer's feet are, and that is 235 mm up a digitigrade
	# leg and 87 mm up a plantigrade one; one fixed aim point cannot hold both.
	for _pose in range(8):
		await process_frame
	var bounds := _equipment_bounds(actor)
	var focus: Vector3 = bounds.get_center()
	var reach: float = maxf(bounds.size.length(), 0.22)
	var back: float = reach / tan(deg_to_rad(_camera.fov * 0.5)) * 0.62

	var row := Image.create(TILE.x * ANGLES.size(), TILE.y, false, Image.FORMAT_RGBA8)
	for index in range(ANGLES.size()):
		var angle: Dictionary = ANGLES[index] as Dictionary
		var yaw: float = deg_to_rad(float(angle["yaw"]))
		var pitch: float = deg_to_rad(float(angle["pitch"]))
		var offset := Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch))
		_camera.position = focus + offset * back
		_camera.look_at(focus, Vector3.UP)
		# Settle, then draw once and read the frame that draw produced.
		# Reading straight after `process_frame` returns whatever the viewport
		# last happened to hold, which is a blank tile as often as not, and the
		# skeleton needs a few frames anyway: it is posed by the animation
		# player and the garment rebound on top of it, so an immediate capture
		# shows a rest pose with nothing skinned onto it.
		for _settle in range(4):
			await process_frame
		await RenderingServer.frame_post_draw
		var shot: Image = _viewport.get_texture().get_image()
		row.blit_rect(shot, Rect2i(Vector2i.ZERO, shot.get_size()),
			Vector2i(TILE.x * index, 0))
	actor.queue_free()
	await process_frame
	return row

func _equipment_bounds(actor: Node) -> AABB:
	"""The worn boot's own extent, in world space."""
	var bounds := AABB()
	var started := false
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_node: MeshInstance3D = node as MeshInstance3D
		if not mesh_node.has_meta("native_equipment") or mesh_node.mesh == null:
			continue
		var box: AABB = mesh_node.global_transform * mesh_node.mesh.get_aabb()
		bounds = box if not started else bounds.merge(box)
		started = true
	if not started:
		bounds = AABB(Vector3(-0.2, 0.0, -0.2), Vector3(0.4, 0.35, 0.4))
	return bounds.grow(0.03)

func _json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed = JSON.parse_string(file.get_as_text())
	return parsed if parsed is Dictionary else {}
