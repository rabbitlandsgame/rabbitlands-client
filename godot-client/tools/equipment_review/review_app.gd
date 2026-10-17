extends Node3D
## Turntable review of fitted equipment on the real client actor.
##
## The actor is a real ReplicatedActor3D, configured as
## tests/canonical_equipment_preview.gd configures it: appearance, hair,
## animation import, wardrobe cover and equipment binding are the client's own.
## Race, sex, armour set and animation are chosen from drop-downs. The chosen
## clip loops. The camera orbits the character.
##
## F2 (or C) takes a screenshot of the current view, without the panels, and
## asks for a note. Each note is appended to notes.jsonl, with the full state
## needed to reproduce the view, and to notes.md, in one session folder under
## <checkout>/.local/asset-authoring/working/equipment-review/.
##
## A piece whose GLB changed since Godot last imported it is loaded straight
## from the file, so the viewer always shows what is on disk. F5 reloads after
## an edit.

const RACES: Array = [
	["luminous", "Luminous (Human)"], ["votary", "Votary"], ["glasswarden", "Glasswarden"],
	["orun", "Orun"], ["greyhaven", "Greyhaven"], ["ssarathi", "Ssarathi"],
	["stoneborn", "Stoneborn"], ["mycelari", "Mycelari"],
]
const FIRST_CLIPS: Array[String] = ["Idle_Subtle", "Walk", "Jog", "Run_Female", "Fighting_Idle", "Idle_A"]
const HEAD_PART := 3
const EXTRA_PARTS: Array[int] = [0, 1, 2]
const SETS_FILE := "res://tools/equipment_review/review_sets.json"
const VIEWS := {KEY_1: 0.0, KEY_2: 90.0, KEY_3: 180.0, KEY_4: -90.0, KEY_5: 35.0}

## Command-line options (set by equipment_review.gd before _ready).
var options: Dictionary = {}

var actor: ReplicatedActor3D
var _models: Dictionary = {}
var _animation_map: Dictionary = {}
var _equipment: Dictionary = {}
var _sets: Array[Dictionary] = []
var _race := "luminous"
var _sex := "male"
var _set_index := 0
var _clip := "Idle_Subtle"
var _show_head := true
var _show_extras := false
var _show_hair := true
var _light_follows := true
var _paused := false
var _speed := 1.0
var _base_speed := 1.0
var _raw_loaded: PackedStringArray = []

var _cam: Camera3D
var _key_light: DirectionalLight3D
var _yaw := 0.0
var _pitch := 0.10
var _distance := 3.1
var _target := Vector3(0.0, 0.95, 0.0)
var _dragging := MOUSE_BUTTON_NONE

var _ui: CanvasLayer
var _race_opt: OptionButton
var _sex_opt: OptionButton
var _set_opt: OptionButton
var _clip_opt: OptionButton
var _pause_button: Button
var _clip_label: Label
var _status: Label
var _toast: Label
var _toast_until := 0
var _dialog: PanelContainer
var _dialog_text: TextEdit
var _dialog_label: Label

var _review_dir := ""
var _note_count := 0
var _pending_shot: Image
var _pending_state: Dictionary = {}
var _resume_after_note := false
var _commit := ""
var _branch := ""
var _session: Dictionary = {}


func _ready() -> void:
	var window := get_window()
	window.title = "Rabbit Lands - equipment review"
	window.size = Vector2i(int(options.get("width", "1600")), int(options.get("height", "1000")))
	window.min_size = Vector2i(900, 600)
	get_viewport().msaa_3d = Viewport.MSAA_4X
	_models = _read_json("res://data/actors/models.json").get("models", {}) as Dictionary
	_animation_map = _read_json("res://data/animations/luminous.json")
	_equipment = _read_json(str(options.get("equipment", "res://data/actors/equipment.json")))
	_build_sets()
	_race = str(options.get("race", _race))
	_sex = str(options.get("sex", _sex))
	_clip = str(options.get("clip", _clip))
	var wanted_set := str(options.get("set", ""))
	for i in range(_sets.size()):
		if str(_sets[i]["name"]).to_lower().begins_with(wanted_set.to_lower()) and not wanted_set.is_empty():
			_set_index = i
			break
	_build_stage()
	_build_ui()
	_start_session()
	_rebuild_actor()
	if options.get("selftest", "no") == "yes":
		_selftest.call_deferred()
	elif options.has("replay"):
		_replay.call_deferred()


# ---------------------------------------------------------------- data

func _read_json(path: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed as Dictionary if parsed is Dictionary else {}


func _build_sets() -> void:
	_sets.clear()
	for calling: Dictionary in CreationArchetypes.CLASSES:
		var visuals := {}
		var source: Dictionary = calling.get("equipment_visuals", {}) as Dictionary
		for part: Variant in source:
			visuals[int(part)] = int(source[part])
		_sets.append({"name": "%s starter kit" % calling.get("label", "?"), "visuals": visuals})
	for entry: Variant in _read_json(SETS_FILE).get("sets", []) as Array:
		var visuals := {}
		var source: Dictionary = (entry as Dictionary).get("visuals", {}) as Dictionary
		for part: Variant in source:
			visuals[int(part)] = int(source[part])
		_sets.append({"name": str((entry as Dictionary).get("name", "?")), "visuals": visuals})


func _slug() -> String:
	return "%s_%s" % [_race, _sex]


func _current_visuals() -> Dictionary:
	var visuals := {}
	var wanted: Dictionary = _sets[_set_index]["visuals"] as Dictionary
	for part: int in wanted:
		if part == HEAD_PART and not _show_head:
			continue
		if part in EXTRA_PARTS and not _show_extras:
			continue
		visuals[part] = wanted[part]
	return visuals


# ---------------------------------------------------------------- stage

func _build_stage() -> void:
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(0.13, 0.16, 0.19)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(0.9, 0.93, 1.0)
	environment.environment.ambient_light_energy = 0.65
	add_child(environment)
	_key_light = DirectionalLight3D.new()
	_key_light.light_energy = 1.2
	_key_light.shadow_enabled = true
	add_child(_key_light)
	var fill := DirectionalLight3D.new()
	fill.light_energy = 0.35
	fill.rotation_degrees = Vector3(-20, 150, 0)
	add_child(fill)
	var floor_mesh := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(12, 12)
	floor_mesh.mesh = plane
	var floor_material := StandardMaterial3D.new()
	floor_material.albedo_color = Color(0.21, 0.24, 0.25)
	floor_mesh.material_override = floor_material
	add_child(floor_mesh)
	_cam = Camera3D.new()
	_cam.fov = 35.0
	# The actor's nameplate, health bar and their backing are gameplay overlays,
	# not equipment: their empty backing floated over the head as a dark box.
	_cam.cull_mask &= ~ReplicatedActor3D.GAMEPLAY_ONLY_VISUAL_LAYER
	add_child(_cam)
	_cam.current = true
	_update_camera()


func _update_camera() -> void:
	var direction := Vector3(sin(_yaw) * cos(_pitch), sin(_pitch), cos(_yaw) * cos(_pitch))
	_cam.global_position = _target + direction * _distance
	_cam.look_at(_target)
	if _light_follows:
		_key_light.rotation = Vector3(deg_to_rad(-35.0), _yaw + deg_to_rad(-30.0), 0.0)
	elif _key_light.rotation == Vector3.ZERO:
		_key_light.rotation_degrees = Vector3(-35, -30, 0)


# ---------------------------------------------------------------- actor

func _rebuild_actor() -> void:
	if actor != null:
		actor.queue_free()
		actor = null
		await get_tree().process_frame
	var slug := _slug()
	if not _models.has(slug):
		_set_status("No model %s in models.json" % slug)
		return
	var config: Dictionary = (_models[slug] as Dictionary).duplicate(true)
	# As the preview: keep the authored face where the generated mask is absent.
	if config.has("faceAppearance") and not ResourceLoader.exists(
			str((config.faceAppearance as Dictionary).get("mask", ""))):
		config.erase("faceAppearance")
	if not _show_hair:
		config["hairStyles"] = []
	var appearance := {"skin": 0, "eyes": 0, "hair": 0, "shirt": 0, "pants": 0, "boots": 0, "head": 0}
	actor = ReplicatedActor3D.new()
	add_child(actor)
	var errors: Array = actor.configure({"actor_id": 9010, "x": 0, "y": 0, "rotation": 0, "kind": 1,
		"name": "", "appearance": appearance, "equipment_visuals": {}},
		CoordinateAdapter.new({"walkingHeight": 0.0}), config, _animation_map, _equipment)
	if not errors.is_empty():
		_set_status("configure: %s" % str(errors))
		push_error(str(errors))
		return
	actor.server_target = Vector3.ZERO
	actor.apply_render_quality(ActorRenderQuality.QUALITY_NAMES.find("high"), false)
	actor.global_position = Vector3.ZERO
	actor.rotation.y = PI
	actor.set_process(false)
	actor.set_physics_process(false)
	for marker: Node in actor.find_children("MapDot*", "MeshInstance3D", true, false):
		(marker as MeshInstance3D).hide()
	_apply_equipment()
	_refresh_clip_list()
	_play_clip(_clip)
	_set_status("%s, %s" % [_race_label(), _sets[_set_index]["name"]])


func _apply_equipment() -> void:
	if actor == null:
		return
	var visuals := _current_visuals()
	_prefer_files_on_disk(visuals)
	actor.apply_equipment_visuals(visuals)
	if options.get("debug-tint", "no") == "yes":
		_debug_tint()


## --debug-tint yes: generated backings magenta, body and wardrobe surfaces cyan,
## so a hole can be told from a lining or the skin behind it.
func _debug_tint() -> void:
	var tints := {"backing": Color(1.0, 0.0, 1.0), "body": Color(0.0, 0.9, 0.9)}
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		var lower := mesh_node.name.to_lower()
		var kind := ("backing" if lower.contains("backing") else
			"body" if lower in ["body", "char1", "mesh_node"] or lower.begins_with("wardrobe_") else "")
		if options.get("debug-meshes", "no") == "yes":
			var first := mesh_node.get_active_material(0) if mesh_node.mesh != null and mesh_node.mesh.get_surface_count() > 0 else null
			print("MESH ", actor.get_path_to(mesh_node), " visible=", mesh_node.is_visible_in_tree(),
				" surfaces=", mesh_node.mesh.get_surface_count() if mesh_node.mesh != null else 0,
				" material=", first.resource_name if first != null else "-",
				" transparency=", (first as BaseMaterial3D).transparency if first is BaseMaterial3D else -1,
				" tint=", kind)
		if kind.is_empty():
			continue
		var material := StandardMaterial3D.new()
		material.albedo_color = tints[kind]
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		mesh_node.material_override = material


## Where a GLB changed after Godot imported it, the imported scene is stale:
## build that piece from the file instead, before the actor asks for it.
func _prefer_files_on_disk(visuals: Dictionary) -> void:
	var models: Dictionary = _equipment.get("models", {}) as Dictionary
	for part: int in visuals:
		var model: Dictionary = models.get("%d:%d" % [part, int(visuals[part])], {}) as Dictionary
		if model.is_empty():
			continue
		var path := str(actor._fit_variant(model).get("scene", ""))
		if path.is_empty() or not _import_is_stale(path):
			continue
		var key := GlbSceneCache._canonical_path(path)
		if not GlbSceneCache._scenes.has(key):
			var packed := GlbSceneCache._build_raw(path)
			if packed != null:
				GlbSceneCache.install_prepared({key: packed})
		if not _raw_loaded.has(path):
			_raw_loaded.append(path)


func _import_is_stale(path: String) -> bool:
	var import_path := path + ".import"
	if not FileAccess.file_exists(import_path):
		return false  # never imported: the cache already reads the file itself
	var imported := ""
	for line: String in FileAccess.get_file_as_string(import_path).split("\n"):
		if line.begins_with("path="):
			imported = line.get_slice("=", 1).strip_edges().trim_prefix("\"").trim_suffix("\"")
			break
	if imported.is_empty():
		return false
	var md5_path := imported.get_basename() + ".md5"
	if not FileAccess.file_exists(md5_path):
		return true
	for line: String in FileAccess.get_file_as_string(md5_path).split("\n"):
		if line.begins_with("source_md5="):
			var recorded := line.get_slice("=", 1).strip_edges().trim_prefix("\"").trim_suffix("\"")
			return recorded != FileAccess.get_md5(path)
	return true


func _reload_from_disk() -> void:
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	_raw_loaded.clear()
	_equipment = _read_json(str(options.get("equipment", "res://data/actors/equipment.json")))
	_models = _read_json("res://data/actors/models.json").get("models", {}) as Dictionary
	_build_sets()
	await _rebuild_actor()
	_toast_message("Reloaded equipment from disk")


# ---------------------------------------------------------------- animation

func _refresh_clip_list() -> void:
	if actor == null or actor.animation_player == null:
		return
	var names: Array[String] = []
	for clip: StringName in actor.animation_player.get_animation_list():
		if str(clip) != "RESET":
			names.append(str(clip))
	names.sort()
	var ordered: Array[String] = []
	for clip: String in FIRST_CLIPS:
		if names.has(clip):
			ordered.append(clip)
	for clip: String in names:
		if not ordered.has(clip):
			ordered.append(clip)
	_clip_opt.clear()
	for clip: String in ordered:
		_clip_opt.add_item(clip)
	if not ordered.has(_clip) and not ordered.is_empty():
		_clip = ordered[0]
	_clip_opt.select(ordered.find(_clip))


func _action_for(clip: String) -> StringName:
	var actions: Dictionary = _animation_map.get("actions", {}) as Dictionary
	for action: String in actions:
		if str(actions[action]) == clip:
			return StringName(action)
	return &""


func _play_clip(clip: String) -> void:
	_clip = clip
	if actor == null or actor.animation_player == null:
		return
	var player := actor.animation_player
	if not player.has_animation(clip):
		return
	player.get_animation(clip).loop_mode = Animation.LOOP_LINEAR
	var action := _action_for(clip)
	_base_speed = 1.0
	if action != &"":
		# The action sets the game's playback speed and held-weapon pose.
		actor.play_action(action, true)
		_base_speed = player.speed_scale
	actor._advance_facing_offset(1.0)
	player.play(clip)
	player.speed_scale = _base_speed * _speed
	if _paused:
		player.pause()


func _set_paused(paused: bool) -> void:
	_paused = paused
	_pause_button.text = "Play (Space)" if paused else "Pause (Space)"
	if actor == null or actor.animation_player == null:
		return
	if paused:
		actor.animation_player.pause()
	else:
		actor.animation_player.play()


func _step(frames: int) -> void:
	if actor == null or actor.animation_player == null or not actor.animation_player.has_animation(_clip):
		return
	_set_paused(true)
	var player := actor.animation_player
	var length := player.get_animation(_clip).length
	player.seek(fposmod(player.current_animation_position + frames / 30.0, length), true)


# ---------------------------------------------------------------- UI

func _build_ui() -> void:
	_ui = CanvasLayer.new()
	add_child(_ui)
	var theme := Theme.new()
	theme.default_font_size = 14
	var panel := PanelContainer.new()
	panel.theme = theme
	panel.position = Vector2(12, 12)
	_ui.add_child(panel)
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(280, 0)
	panel.add_child(box)
	var title := Label.new()
	title.text = "Equipment review"
	box.add_child(title)
	_race_opt = _option(box, "Race")
	for race: Array in RACES:
		_race_opt.add_item(str(race[1]))
	_race_opt.select(maxi(0, RACES.map(func(r: Array) -> String: return str(r[0])).find(_race)))
	_race_opt.item_selected.connect(func(i: int) -> void:
		_race = str(RACES[i][0])
		_rebuild_actor())
	_sex_opt = _option(box, "Sex")
	_sex_opt.add_item("Male")
	_sex_opt.add_item("Female")
	_sex_opt.select(0 if _sex == "male" else 1)
	_sex_opt.item_selected.connect(func(i: int) -> void:
		_sex = "male" if i == 0 else "female"
		_rebuild_actor())
	_set_opt = _option(box, "Armour set")
	for entry: Dictionary in _sets:
		_set_opt.add_item(str(entry["name"]))
	_set_opt.select(_set_index)
	_set_opt.item_selected.connect(func(i: int) -> void:
		_set_index = i
		_apply_equipment()
		_play_clip(_clip)
		_set_status("%s, %s" % [_race_label(), _sets[_set_index]["name"]]))
	_clip_opt = _option(box, "Animation (loops)")
	_clip_opt.item_selected.connect(func(i: int) -> void: _play_clip(_clip_opt.get_item_text(i)))
	_check(box, "Headwear", _show_head, func(on: bool) -> void:
		_show_head = on
		_apply_equipment())
	_check(box, "Weapons and cape", _show_extras, func(on: bool) -> void:
		_show_extras = on
		_apply_equipment()
		_play_clip(_clip))
	_check(box, "Hair", _show_hair, func(on: bool) -> void:
		_show_hair = on
		_rebuild_actor())
	_check(box, "Light follows camera", _light_follows, func(on: bool) -> void:
		_light_follows = on
		_update_camera())
	var buttons := HBoxContainer.new()
	box.add_child(buttons)
	_pause_button = _button(buttons, "Pause (Space)", func() -> void: _set_paused(not _paused))
	_button(buttons, "Note (F2)", func() -> void: _begin_note())
	_button(buttons, "Reload (F5)", func() -> void: _reload_from_disk())
	_button(buttons, "Notes", func() -> void:
		_ensure_session()
		OS.shell_open(_review_dir))
	_clip_label = Label.new()
	box.add_child(_clip_label)
	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.custom_minimum_size = Vector2(280, 0)
	_status.add_theme_font_size_override("font_size", 12)
	box.add_child(_status)
	var help := Label.new()
	help.add_theme_font_size_override("font_size", 12)
	help.text = ("Left drag: orbit. Right/middle drag: pan.\n"
		+ "Wheel or Q/E: zoom. A/D, arrows: turn. W/S: tilt.\n"
		+ "1 front, 2 side, 3 back, 4 other side, 5 three-quarter.\n"
		+ "R: reset view. Space: pause. , and .: step a frame.\n"
		+ "[ and ]: speed. H: hide panels. F5: reload from disk.\n"
		+ "F2 or C: screenshot and note.")
	box.add_child(help)
	_toast = Label.new()
	_toast.anchor_top = 1.0
	_toast.anchor_bottom = 1.0
	_toast.offset_left = 16
	_toast.offset_top = -40
	_toast.add_theme_font_size_override("font_size", 16)
	_ui.add_child(_toast)
	_build_dialog()


func _option(box: VBoxContainer, label: String) -> OptionButton:
	var caption := Label.new()
	caption.text = label
	box.add_child(caption)
	var option := OptionButton.new()
	option.focus_mode = Control.FOCUS_NONE
	box.add_child(option)
	return option


func _check(box: VBoxContainer, label: String, on: bool, toggled: Callable) -> void:
	var check := CheckBox.new()
	check.text = label
	check.button_pressed = on
	check.focus_mode = Control.FOCUS_NONE
	check.toggled.connect(toggled)
	box.add_child(check)


func _button(box: HBoxContainer, label: String, pressed: Callable) -> Button:
	var button := Button.new()
	button.text = label
	button.focus_mode = Control.FOCUS_NONE
	button.pressed.connect(pressed)
	box.add_child(button)
	return button


func _build_dialog() -> void:
	_dialog = PanelContainer.new()
	_dialog.theme = Theme.new()
	_dialog.theme.default_font_size = 15
	_dialog.custom_minimum_size = Vector2(660, 260)
	_dialog.visible = false
	_ui.add_child(_dialog)
	var box := VBoxContainer.new()
	_dialog.add_child(box)
	_dialog_label = Label.new()
	_dialog_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_dialog_label.custom_minimum_size = Vector2(640, 0)
	box.add_child(_dialog_label)
	_dialog_text = TextEdit.new()
	_dialog_text.custom_minimum_size = Vector2(640, 170)
	_dialog_text.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	_dialog_text.gui_input.connect(_on_dialog_key)
	box.add_child(_dialog_text)
	var row := HBoxContainer.new()
	box.add_child(row)
	_button(row, "Save (Ctrl+Enter)", func() -> void: _save_note())
	_button(row, "Cancel (Esc)", func() -> void: _close_note())


func _on_dialog_key(event: InputEvent) -> void:
	var key := event as InputEventKey
	if key == null or not key.pressed:
		return
	if key.keycode in [KEY_ENTER, KEY_KP_ENTER] and key.ctrl_pressed:
		_save_note()
		get_viewport().set_input_as_handled()
	elif key.keycode == KEY_ESCAPE:
		_close_note()
		get_viewport().set_input_as_handled()


func _set_status(text: String) -> void:
	if _status != null:
		_status.text = text + ("\nLoaded from disk (newer than the import): %d file(s)" % _raw_loaded.size()
			if not _raw_loaded.is_empty() else "") + "\nNotes: " + _review_dir


func _toast_message(text: String) -> void:
	_toast.text = text
	_toast_until = Time.get_ticks_msec() + 4000


func _race_label() -> String:
	for race: Array in RACES:
		if race[0] == _race:
			return "%s %s" % [race[1], _sex]
	return _slug()


# ---------------------------------------------------------------- input

func _unhandled_input(event: InputEvent) -> void:
	if _dialog.visible:
		return
	var button := event as InputEventMouseButton
	if button != null:
		if button.button_index == MOUSE_BUTTON_WHEEL_UP and button.pressed:
			_distance = maxf(0.6, _distance * 0.9)
		elif button.button_index == MOUSE_BUTTON_WHEEL_DOWN and button.pressed:
			_distance = minf(9.0, _distance / 0.9)
		elif button.pressed:
			_dragging = button.button_index
		else:
			_dragging = MOUSE_BUTTON_NONE
		_update_camera()
		return
	var motion := event as InputEventMouseMotion
	if motion != null and _dragging != MOUSE_BUTTON_NONE:
		if _dragging == MOUSE_BUTTON_LEFT:
			_yaw -= motion.relative.x * 0.008
			_pitch = clampf(_pitch + motion.relative.y * 0.006, -1.2, 1.45)
		else:
			var right := _cam.global_transform.basis.x
			var up := _cam.global_transform.basis.y
			_target += (-right * motion.relative.x + up * motion.relative.y) * 0.0012 * _distance
		_update_camera()
		return
	var key := event as InputEventKey
	if key == null or not key.pressed or key.echo:
		return
	match key.keycode:
		KEY_F2, KEY_C:
			_begin_note()
		KEY_SPACE:
			_set_paused(not _paused)
		KEY_H:
			for child: Node in _ui.get_children():
				if child != _dialog and child != _toast:
					(child as CanvasItem).visible = not (child as CanvasItem).visible
		KEY_F5:
			_reload_from_disk()
		KEY_R:
			_yaw = 0.0
			_pitch = 0.10
			_distance = 3.1
			_target = Vector3(0.0, 0.95, 0.0)
			_update_camera()
		KEY_COMMA:
			_step(-1)
		KEY_PERIOD:
			_step(1)
		KEY_BRACKETLEFT, KEY_BRACKETRIGHT:
			_speed = clampf(_speed * (0.5 if key.keycode == KEY_BRACKETLEFT else 2.0), 0.125, 4.0)
			if actor != null and actor.animation_player != null:
				actor.animation_player.speed_scale = _base_speed * _speed
			_toast_message("Speed x%s" % _speed)
		_:
			if VIEWS.has(key.keycode):
				_yaw = deg_to_rad(float(VIEWS[key.keycode]))
				_update_camera()


func _process(delta: float) -> void:
	if not _dialog.visible:
		var turn := 0.0
		var tilt := 0.0
		var zoom := 0.0
		if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT): turn += 1.0
		if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT): turn -= 1.0
		if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP): tilt += 1.0
		if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN): tilt -= 1.0
		if Input.is_key_pressed(KEY_Q): zoom -= 1.0
		if Input.is_key_pressed(KEY_E): zoom += 1.0
		if turn != 0.0 or tilt != 0.0 or zoom != 0.0:
			_yaw += turn * delta * 1.6
			_pitch = clampf(_pitch + tilt * delta * 1.0, -1.2, 1.45)
			_distance = clampf(_distance * (1.0 + zoom * delta * 1.2), 0.6, 9.0)
			_update_camera()
	if _toast_until > 0 and Time.get_ticks_msec() > _toast_until:
		_toast.text = ""
		_toast_until = 0
	if actor != null and actor.animation_player != null and actor.animation_player.has_animation(_clip):
		var player := actor.animation_player
		_clip_label.text = "%s  %.2f / %.2f s  x%s%s" % [_clip, player.current_animation_position,
			player.get_animation(_clip).length, _speed, "  (paused)" if _paused else ""]


# ---------------------------------------------------------------- notes

func _start_session() -> void:
	var project := ProjectSettings.globalize_path("res://").trim_suffix("/")
	var checkout := project.get_base_dir()
	var stamp := Time.get_datetime_string_from_system().replace(":", "-").replace("T", "_")
	var root := str(options.get("review-dir", checkout.path_join(".local/asset-authoring/working/equipment-review")))
	_review_dir = root.path_join(stamp)
	_commit = _git(checkout, ["rev-parse", "HEAD"])
	_branch = _git(checkout, ["rev-parse", "--abbrev-ref", "HEAD"])
	_session = {"started": Time.get_datetime_string_from_system(), "checkout": checkout,
		"branch": _branch, "commit": _commit, "dirty": _git(checkout, ["status", "--porcelain"]) != "",
		"godot": Engine.get_version_info().get("string", ""), "options": options}
	print("EQUIPMENT_REVIEW notes folder: ", _review_dir)


## The session folder is written with its first note, so a look without notes leaves nothing.
func _ensure_session() -> void:
	if FileAccess.file_exists(_review_dir.path_join("session.json")):
		return
	DirAccess.make_dir_recursive_absolute(_review_dir)
	var file := FileAccess.open(_review_dir.path_join("session.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(_session, "\t") + "\n")
	file = FileAccess.open(_review_dir.path_join("notes.md"), FileAccess.WRITE)
	file.store_string("# Equipment review %s\n\nCheckout `%s`, branch `%s`, commit `%s`.\n\n" % [
		_session["started"], _session["checkout"], _branch, _commit.left(10)])


func _git(checkout: String, arguments: Array) -> String:
	var output: Array = []
	var code := OS.execute("git", ["-C", checkout] + arguments, output, true)
	return str(output[0]).strip_edges() if code == 0 and not output.is_empty() else ""


func _state() -> Dictionary:
	var visuals := _current_visuals()
	var pieces: Array = []
	var models: Dictionary = _equipment.get("models", {}) as Dictionary
	for part: int in visuals:
		var key := "%d:%d" % [part, int(visuals[part])]
		var model: Dictionary = models.get(key, {}) as Dictionary
		var resolved: Dictionary = actor._fit_variant(model) if actor != null and not model.is_empty() else model
		pieces.append({"part": part, "visual": int(visuals[part]), "key": key,
			"name": str(model.get("name", "")), "scene": str(resolved.get("scene", "")),
			"loaded_from_disk": _raw_loaded.has(str(resolved.get("scene", "")))})
	var time := 0.0
	var length := 0.0
	if actor != null and actor.animation_player != null and actor.animation_player.has_animation(_clip):
		time = actor.animation_player.current_animation_position
		length = actor.animation_player.get_animation(_clip).length
	return {"race": _race, "sex": _sex, "slug": _slug(), "set": _sets[_set_index]["name"],
		"headwear": _show_head, "weapons_and_cape": _show_extras, "hair": _show_hair,
		"pieces": pieces, "clip": _clip, "clip_time": snappedf(time, 0.001),
		"clip_length": snappedf(length, 0.001), "paused": _paused, "speed": _speed,
		"camera": {"yaw_degrees": snappedf(rad_to_deg(_yaw), 0.1), "pitch_degrees": snappedf(rad_to_deg(_pitch), 0.1),
			"distance": snappedf(_distance, 0.001), "target": [snappedf(_target.x, 0.001),
			snappedf(_target.y, 0.001), snappedf(_target.z, 0.001)]},
		"window": [get_window().size.x, get_window().size.y], "commit": _commit, "branch": _branch}


func _begin_note() -> void:
	if _dialog.visible:
		return
	_pending_state = _state()
	_resume_after_note = not _paused
	if not _paused:
		_set_paused(true)
	var shown: Array[CanvasItem] = []
	for child: Node in _ui.get_children():
		if (child as CanvasItem).visible:
			shown.append(child as CanvasItem)
			(child as CanvasItem).visible = false
	await RenderingServer.frame_post_draw
	_pending_shot = get_viewport().get_texture().get_image()
	for item: CanvasItem in shown:
		item.visible = true
	_dialog_label.text = "Note %d: %s, %s, %s at %.2f s. Ctrl+Enter saves, Esc cancels." % [
		_note_count + 1, _race_label(), _sets[_set_index]["name"], _clip, _pending_state["clip_time"]]
	_dialog_text.text = ""
	_dialog.visible = true
	_dialog.reset_size()
	_dialog.position = ((get_viewport().get_visible_rect().size - _dialog.get_combined_minimum_size()) / 2.0).floor()
	_dialog_text.grab_focus()


func _save_note() -> void:
	if not _dialog.visible:
		return
	var comment := _dialog_text.text.strip_edges()
	_ensure_session()
	_note_count += 1
	var shot := "shot_%03d.png" % _note_count
	_pending_shot.save_png(_review_dir.path_join(shot))
	var entry := _pending_state.duplicate(true)
	entry["n"] = _note_count
	entry["time"] = Time.get_datetime_string_from_system()
	entry["comment"] = comment
	entry["screenshot"] = shot
	var path := _review_dir.path_join("notes.jsonl")
	var file := FileAccess.open(path, FileAccess.READ_WRITE) if FileAccess.file_exists(path) \
		else FileAccess.open(path, FileAccess.WRITE)
	file.seek_end()
	file.store_line(JSON.stringify(entry))
	file = FileAccess.open(_review_dir.path_join("notes.md"), FileAccess.READ_WRITE)
	file.seek_end()
	var parts := PackedStringArray()
	for piece: Dictionary in entry["pieces"]:
		parts.append("%s %s" % [piece["key"], piece["name"]])
	file.store_string("## %d. %s, %s\n\n%s at %.2f s, camera yaw %s, pitch %s. Pieces: %s.\n\n%s\n\n![](%s)\n\n" % [
		_note_count, _race_label(), entry["set"], entry["clip"], entry["clip_time"],
		entry["camera"]["yaw_degrees"], entry["camera"]["pitch_degrees"], ", ".join(parts),
		comment if not comment.is_empty() else "(no comment)", shot])
	_close_note()
	_toast_message("Saved note %d (%s)" % [_note_count, shot])


func _close_note() -> void:
	_dialog.visible = false
	_dialog_text.release_focus()
	if _resume_after_note:
		_set_paused(false)


# ---------------------------------------------------------------- self-test

## --selftest yes: walk every control once, save one note, quit. For the tool's own checks.
func _selftest() -> void:
	await get_tree().create_timer(1.5).timeout
	_ensure_session()
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(_review_dir.path_join("ui_check.png"))
	for step: Array in [["sex", 1], ["race", 5], ["set", 4], ["clip", 1], ["race", 0], ["sex", 0], ["set", 0], ["clip", 2]]:
		match str(step[0]):
			"race":
				_race_opt.select(int(step[1]))
				_race_opt.item_selected.emit(int(step[1]))
			"sex":
				_sex_opt.select(int(step[1]))
				_sex_opt.item_selected.emit(int(step[1]))
			"set":
				_set_opt.select(int(step[1]))
				_set_opt.item_selected.emit(int(step[1]))
			"clip":
				_clip_opt.select(int(step[1]))
				_clip_opt.item_selected.emit(int(step[1]))
		await get_tree().create_timer(1.0).timeout
		print("SELFTEST ", step, " -> ", _slug(), " | ", _sets[_set_index]["name"], " | ", _clip,
			" | equipment ", actor.equipment_diagnostics() if actor != null else {})
	_yaw = deg_to_rad(35.0)
	_update_camera()
	await get_tree().create_timer(0.5).timeout
	await _begin_note()
	_dialog_text.text = "self-test note"
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(_review_dir.path_join("dialog_check.png"))
	_save_note()
	print("SELFTEST_OK ", _review_dir)
	await get_tree().create_timer(0.3).timeout
	get_tree().quit()


## --replay <notes.jsonl> [--notes 7,13] [--out <dir>]: restore each note's view
## (race, sex, set, toggles, clip time, camera), save replay_NNN.png without the
## panels, and quit. Shows what a fix did to the view a note was written on.
func _replay() -> void:
	var path := str(options["replay"])
	var wanted := str(options.get("notes", "")).split(",", false)
	var out := str(options.get("out", path.get_base_dir().path_join("replay")))
	DirAccess.make_dir_recursive_absolute(out)
	_ui.visible = false
	for line: String in FileAccess.get_file_as_string(path).split("\n", false):
		var note: Dictionary = JSON.parse_string(line) as Dictionary
		if not wanted.is_empty() and not wanted.has(str(int(note["n"]))):
			continue
		_race = str(note["race"])
		_sex = str(note["sex"])
		for i in range(_sets.size()):
			if _sets[i]["name"] == note["set"]:
				_set_index = i
		_show_head = (bool(note.get("headwear", true)) if not options.has("headwear")
			else options["headwear"] == "yes")
		_show_extras = bool(note.get("weapons_and_cape", false))
		_show_hair = bool(note.get("hair", true))
		_speed = float(note.get("speed", 1.0))
		_clip = str(note["clip"])
		_paused = true
		await _rebuild_actor()
		var camera: Dictionary = note["camera"] as Dictionary
		_yaw = deg_to_rad(float(camera["yaw_degrees"]))
		_pitch = deg_to_rad(float(camera["pitch_degrees"]))
		_distance = float(camera["distance"])
		var target: Array = camera["target"] as Array
		_target = Vector3(float(target[0]), float(target[1]), float(target[2]))
		_update_camera()
		if actor != null and actor.animation_player != null and actor.animation_player.has_animation(_clip):
			actor.animation_player.seek(float(note["clip_time"]), true)
		for _frame in range(3):
			await RenderingServer.frame_post_draw
		var shot := out.path_join("replay_%03d.png" % int(note["n"]))
		get_viewport().get_texture().get_image().save_png(shot)
		print("REPLAY ", int(note["n"]), " -> ", shot)
	print("REPLAY_OK ", out)
	get_tree().quit()
