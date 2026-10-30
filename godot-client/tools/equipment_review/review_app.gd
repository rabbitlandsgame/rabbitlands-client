extends Node3D
## Turntable review of fitted equipment on the real client actor.
##
## The actor is a real ReplicatedActor3D, configured as
## tests/canonical_equipment_preview.gd configures it: appearance, hair,
## animation import, wardrobe cover and equipment binding are the client's own.
## Race, sex, armour set and animation are chosen from drop-downs. The chosen
## clip loops. The camera orbits the character.
##
## Travel (V, or --travel yes) moves the actor through the scene while a walk or
## a run plays, at the client's own pace and clip speed, with the camera and
## floor following. In place the cape cloth never sees the actor move, so it
## hangs into the arms and legs as it never does in play. Travelling, the clip,
## the actor and the cloth advance together in the game's frames, so a pause
## freezes the cloth where it was rather than letting it drop.
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
const Wardrobe := preload("res://tools/equipment_review/review_wardrobe.gd")
const ITEM_CATALOG := "res://tools/equipment_review/item_catalog.json"
const PART_LABELS := {0: "Main hand", 1: "Off hand", 2: "Cape", 3: "Head",
	4: "Legs", 5: "Torso", 6: "Feet", 7: "Neck", 8: "Quiver"}
const VIEWS := {KEY_1: 0.0, KEY_2: 90.0, KEY_3: 180.0, KEY_4: -90.0, KEY_5: 35.0}
## Travelled this far from the origin, the actor and its cloth are carried back
## by whole metres, so a long run stays clear of float precision.
const TRAVEL_WRAP := 1000.0
## How long a replay travels before the noted frame, so the cloth is streaming.
const REPLAY_LEAD := 2.0
const FLOOR_SIZE := 12.0
## Travelling, the floor is this much wider, so its edge stays out of view.
const TRAVEL_FLOOR_SCALE := 4.0
const GRID_SHADER := """
shader_type spatial;
uniform vec3 floor_color : source_color;
uniform vec3 line_color : source_color;
varying vec2 ground;
void vertex() {
	ground = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xz;
}
void fragment() {
	// Metre lines fixed to the world, about a pixel wide at any distance.
	vec2 edge = abs(fract(ground + 0.5) - 0.5) / max(fwidth(ground), vec2(1e-4));
	ALBEDO = mix(floor_color, line_color, 1.0 - clamp(min(edge.x, edge.y) - 0.5, 0.0, 1.0));
}
"""

## Command-line options (set by equipment_review.gd before _ready).
var options: Dictionary = {}

var actor: ReplicatedActor3D
var _actor_generation := 0
var _models: Dictionary = {}
var _animation_map: Dictionary = {}
var _equipment: Dictionary = {}
var _sets: Array[Dictionary] = []
var _race := "luminous"
var _sex := "male"
var _set_index := 0
var _clip := "Idle_Subtle"
var _show_head := true
var _show_extras := true
var _show_hair := true
var _light_follows := true
var _paused := false
var _speed := 1.0
var _base_speed := 1.0
var _raw_loaded: PackedStringArray = []
var _travel := false
## Metres per second the chosen clip carries the actor: the client's walking or
## running pace, or 0 for a clip that stays on the spot.
var _travel_speed := 0.0
## Played seconds owed to the travelling actor, in whole frames.
var _travel_owed := 0.0
var _wardrobe := Wardrobe.new()
var _drafts: Dictionary = {}
var _piece_options: Dictionary = {}
var _piece_checks: Dictionary = {}
var _piece_buttons: Dictionary = {}
var _piece_scroll: ScrollContainer
var _atlas := ItemAtlas.new()
var _details_name: Label
var _details_icon: TextureRect
var _details_text: RichTextLabel
var _details_set: Label
var _details_comments: Label
var _comments: Array[Dictionary] = []
var _modal: ColorRect
var _noting := false

var _cam: Camera3D
var _key_light: DirectionalLight3D
var _floor: MeshInstance3D
var _floor_material: StandardMaterial3D
var _grid_material: ShaderMaterial
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
var _travel_check: CheckBox
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
	window.min_size = Vector2i(1280, 800)
	get_viewport().msaa_3d = Viewport.MSAA_4X
	_models = _read_json("res://data/actors/models.json").get("models", {}) as Dictionary
	_animation_map = _read_json("res://data/animations/luminous.json")
	_equipment = _read_json(str(options.get("equipment", "res://data/actors/equipment.json")))
	_build_sets()
	_wardrobe.configure(_equipment, _read_json(ITEM_CATALOG))
	_atlas.configure(_read_json("res://data/items/atlases.json"))
	_race = str(options.get("race", _race))
	_sex = str(options.get("sex", _sex))
	_clip = str(options.get("clip", _clip))
	_travel = options.get("travel", "no") == "yes"
	var wanted_set := str(options.get("set", ""))
	for i in range(_sets.size()):
		if str(_sets[i]["name"]).to_lower().begins_with(wanted_set.to_lower()) and not wanted_set.is_empty():
			_set_index = i
			break
	_wardrobe.use_set(_sets[_set_index]["visuals"])
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
	return _wardrobe.visuals()


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
	_floor = MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(FLOOR_SIZE, FLOOR_SIZE)
	_floor.mesh = plane
	_floor_material = StandardMaterial3D.new()
	_floor_material.albedo_color = Color(0.21, 0.24, 0.25)
	# A plain floor gives no sense of travel: moving, it carries a metre grid.
	_grid_material = ShaderMaterial.new()
	_grid_material.shader = Shader.new()
	_grid_material.shader.code = GRID_SHADER
	_grid_material.set_shader_parameter("floor_color", _floor_material.albedo_color)
	_grid_material.set_shader_parameter("line_color", Color(0.33, 0.37, 0.38))
	add_child(_floor)
	_update_floor()
	_cam = Camera3D.new()
	_cam.fov = 35.0
	# The actor's nameplate, health bar and their backing are gameplay overlays,
	# not equipment: their empty backing floated over the head as a dark box.
	_cam.cull_mask &= ~ReplicatedActor3D.GAMEPLAY_ONLY_VISUAL_LAYER
	add_child(_cam)
	_cam.current = true
	_update_camera()


## The orbit target is held relative to the actor's ground point, so the camera
## follows a travelling actor; on the spot that point is the origin.
func _update_camera() -> void:
	var direction := Vector3(sin(_yaw) * cos(_pitch), sin(_pitch), cos(_yaw) * cos(_pitch))
	var focus := _target + _ground_point()
	_cam.global_position = focus + direction * _distance
	_cam.look_at(focus)
	if _light_follows:
		_key_light.rotation = Vector3(deg_to_rad(-35.0), _yaw + deg_to_rad(-30.0), 0.0)
	elif _key_light.rotation == Vector3.ZERO:
		_key_light.rotation_degrees = Vector3(-35, -30, 0)


func _ground_point() -> Vector3:
	if actor == null:
		return Vector3.ZERO
	return Vector3(actor.global_position.x, 0.0, actor.global_position.z)


## The floor stays under the actor; travelling it is wider and gridded, and the
## grid is fixed to the world, so it is the floor that reads as moving by.
func _update_floor() -> void:
	_floor.global_position = _ground_point()
	_floor.scale = Vector3.ONE * (TRAVEL_FLOOR_SCALE if _travel else 1.0)
	_floor.material_override = _grid_material if _travel else _floor_material


# ---------------------------------------------------------------- actor

func _rebuild_actor() -> void:
	_actor_generation += 1
	var generation := _actor_generation
	if actor != null:
		actor.queue_free()
		actor = null
		await get_tree().process_frame
	if generation != _actor_generation:
		return
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
	if options.get("debug-tint", "no") in ["yes", "parts"]:
		_debug_tint()


## --debug-tint yes: generated backings magenta, reconstructed inseams green,
## body and wardrobe surfaces cyan, so a hole can be told from a lining or the
## skin behind it. --debug-tint parts also draws the trousers' art yellow and
## the boots' orange.
func _debug_tint() -> void:
	var tints := {"backing": Color(1.0, 0.0, 1.0), "body": Color(0.0, 0.9, 0.9),
		"inseam": Color(0.1, 0.9, 0.1), "legs": Color(1.0, 0.85, 0.0), "boots": Color(1.0, 0.45, 0.0)}
	var by_part: bool = options.get("debug-tint", "no") == "parts"
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		var lower := mesh_node.name.to_lower()
		var kind := ("backing" if lower.contains("backing") else
			"inseam" if lower.contains("reconstructedinseams") else
			"body" if lower in ["body", "char1", "mesh_node"] or lower.begins_with("wardrobe_") else "")
		# --debug-tint parts: the trousers' and boots' own art too, to tell
		# which piece comes through which.
		if kind.is_empty() and by_part:
			kind = ("legs" if lower.begins_with("equipmentskin_4_") else
				"boots" if lower.begins_with("equipmentskin_6_") else "")
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
	var loadout := _wardrobe.snapshot()
	var set_name := str(_sets[_set_index]["name"])
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	_raw_loaded.clear()
	_equipment = _read_json(str(options.get("equipment", "res://data/actors/equipment.json")))
	_models = _read_json("res://data/actors/models.json").get("models", {}) as Dictionary
	_build_sets()
	_set_index = 0
	_set_opt.clear()
	for i in range(_sets.size()):
		_set_opt.add_item(_set_label(_sets[i]))
		if str(_sets[i]["name"]) == set_name:
			_set_index = i
	_set_opt.select(_set_index)
	_wardrobe.configure(_equipment, _read_json(ITEM_CATALOG))
	_wardrobe.restore(loadout)
	_fill_piece_options()
	_refresh_pieces()
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
	_travel_speed = _pace_for(action)
	if action != &"":
		# The action sets the game's playback speed and held-weapon pose. The
		# actor reads a walk or run speed off the pace it is travelling at.
		if _travel_speed > 0.0:
			actor._presentation_speed = _travel_speed
		actor.play_action(action, true)
		_base_speed = player.speed_scale
	actor._advance_facing_offset(1.0)
	player.play(clip)
	_apply_travel_mode()
	if _paused:
		player.pause()
		if _travel:
			_hold_pose()


## The client's own pace for a walk or a run: a metre tile per step, at the
## step length the actor assumes for that gait before it has timed the
## server's. Zero for anything that is not locomotion.
func _pace_for(action: StringName) -> float:
	if actor == null or action not in [&"walk", &"run"]:
		return 0.0
	# Gait 1 is a run and 0 a walk, as ReplicatedActor3D.pace_gait numbers them.
	return actor._metres_per_tile / actor._pace_for_gait(1 if action == &"run" else 0)


## Travelling, the clip and the cloth are advanced here, frame by frame, rather
## than by the engine: in step, and not at all while paused.
func _apply_travel_mode() -> void:
	if actor == null or actor.animation_player == null:
		return
	actor.animation_player.callback_mode_process = (
		AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL if _travel
		else AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE)
	for skeleton: Skeleton3D in _skeletons():
		skeleton.modifier_callback_mode_process = (
			Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL if _travel
			else Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_IDLE)
	_apply_speed()


## Travelling, the speed changes how many frames run, not how long each is.
func _apply_speed() -> void:
	if actor != null and actor.animation_player != null:
		actor.animation_player.speed_scale = _base_speed * (1.0 if _travel else _speed)


func _skeletons() -> Array[Skeleton3D]:
	var found: Array[Skeleton3D] = []
	if actor != null:
		for node: Node in actor.find_children("*", "Skeleton3D", true, false):
			found.append(node as Skeleton3D)
	return found


func _set_travel(on: bool) -> void:
	_travel = on
	if _travel_check != null:
		_travel_check.set_pressed_no_signal(on)
	_travel_owed = 0.0
	if actor != null:
		actor.global_position = Vector3.ZERO
		var cloth: Node = actor._cape_cloth
		if cloth != null:
			cloth.call("reset")
	_play_clip(_clip)
	_update_floor()
	_update_camera()
	_toast_message("Travel on: walks and runs move" if on else "Travel off: clips play on the spot")


## The way the actor faces, and travels, as the client moves it.
func _heading() -> Vector3:
	var ahead := -actor.global_transform.basis.z
	ahead.y = 0.0
	return ahead.normalized()


## One frame of play, `seconds` long: the clip advances, the actor travels and
## the cloth steps, together, as in the game. Works paused. The skeleton runs
## its modifiers once at the end of the frame, with the time it was given
## summed, so a frame is the finest step there is: call this once per frame.
func _travel_frame(seconds: float) -> void:
	if actor == null or actor.animation_player == null or seconds <= 0.0:
		return
	var player := actor.animation_player
	var held := not player.is_playing()
	if held:
		player.play()
	player.advance(seconds)
	if held:
		player.pause()
	actor.global_position += _heading() * _travel_speed * seconds
	for skeleton: Skeleton3D in _skeletons():
		skeleton.advance(seconds)
	_carry_back()
	_update_floor()
	_update_camera()


## A pose set with the clip held (a seek, a new clip) is drawn with the cloth
## left where it was. Without this the cape would show its bind shape: the
## skeleton only keeps the cloth's bones for an update it was advanced in.
func _hold_pose() -> void:
	if actor == null or actor.animation_player == null or not actor.animation_player.has_animation(_clip):
		return
	actor.animation_player.seek(actor.animation_player.current_animation_position, true)
	for skeleton: Skeleton3D in _skeletons():
		skeleton.advance(0.0)


## Past TRAVEL_WRAP, carry the actor back by whole metres, cloth and all, so
## the grid and the cape see nothing happen.
func _carry_back(limit := TRAVEL_WRAP) -> void:
	var offset := _ground_point()
	if offset.length() < limit:
		return
	offset = offset.round()
	actor.global_position -= offset
	var cloth: Node = actor._cape_cloth
	if cloth == null:
		return
	for state: String in ["_points", "_previous"]:
		var chains: Array = cloth.get(state)
		for chain in range(chains.size()):
			var points: PackedVector3Array = chains[chain]
			for i in range(points.size()):
				points[i] -= offset
			chains[chain] = points
	cloth.set("_last_anchor", (cloth.get("_last_anchor") as Vector3) - offset)


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
	var seconds := frames / 30.0 / maxf(_base_speed, 0.01)
	if _travel and frames > 0:
		# Forward, play the step as a frame, so the cloth moves with the body.
		_travel_frame(seconds)
		return
	player.seek(fposmod(player.current_animation_position + frames / 30.0, length), true)
	if _travel:
		# Back, the actor steps back too; the cloth cannot run backwards, so it holds.
		actor.global_position += _heading() * _travel_speed * seconds
		_hold_pose()
		_update_floor()
		_update_camera()


# ---------------------------------------------------------------- UI

func _build_ui() -> void:
	_ui = CanvasLayer.new()
	add_child(_ui)
	var theme := Theme.new()
	theme.default_font_size = 14
	var backing := StyleBoxFlat.new()
	backing.bg_color = Color(0.105, 0.13, 0.15, 0.98)
	backing.content_margin_left = 10
	backing.content_margin_right = 10
	backing.content_margin_top = 10
	backing.content_margin_bottom = 10
	theme.set_stylebox("panel", "PanelContainer", backing)
	var panel := PanelContainer.new()
	panel.theme = theme
	_ui.add_child(panel)
	panel.anchor_bottom = 1.0
	panel.offset_left = 12
	panel.offset_top = 12
	panel.offset_right = 334
	panel.offset_bottom = -52
	var scroll := ScrollContainer.new()
	_piece_scroll = scroll
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	panel.add_child(scroll)
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 6)
	scroll.add_child(box)
	var title := Label.new()
	title.text = "Rabbit Lands · Equipment preview"
	title.add_theme_font_size_override("font_size", 16)
	title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(title)
	_set_opt = _option(box, "Equipment set  ·  ← / →")
	for entry: Dictionary in _sets:
		_set_opt.add_item(_set_label(entry))
	_set_opt.select(_set_index)
	_set_opt.item_selected.connect(_select_set)
	var set_buttons := HBoxContainer.new()
	box.add_child(set_buttons)
	_button(set_buttons, "← Previous", func() -> void: _select_set(posmod(_set_index - 1, _sets.size())))
	_button(set_buttons, "Next →", func() -> void: _select_set(posmod(_set_index + 1, _sets.size())))
	_button(set_buttons, "Restore set", _restore_set)
	var hint := Label.new()
	hint.text = "Check to show a piece. Click its slot for details.\nEach list includes pieces from every set."
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.add_theme_font_size_override("font_size", 12)
	box.add_child(hint)
	for part: int in PART_LABELS:
		if not _wardrobe.by_part.has(part):
			continue
		var row := HBoxContainer.new()
		box.add_child(row)
		var check := CheckBox.new()
		check.focus_mode = Control.FOCUS_NONE
		check.tooltip_text = "Show or hide this piece without removing the selection"
		row.add_child(check)
		_piece_checks[part] = check
		check.toggled.connect(func(on: bool) -> void: _toggle_piece(part, on))
		var inspect := Button.new()
		inspect.text = str(PART_LABELS[part])
		inspect.alignment = HORIZONTAL_ALIGNMENT_LEFT
		inspect.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		inspect.toggle_mode = true
		inspect.focus_mode = Control.FOCUS_NONE
		row.add_child(inspect)
		_piece_buttons[part] = inspect
		inspect.pressed.connect(func() -> void:
			_wardrobe.selected_part = part
			_refresh_pieces())
		var choice := OptionButton.new()
		choice.focus_mode = Control.FOCUS_NONE
		choice.fit_to_longest_item = false
		choice.clip_text = true
		box.add_child(choice)
		_piece_options[part] = choice
		choice.item_selected.connect(func(i: int) -> void:
			_wardrobe.choose(part, str(choice.get_item_metadata(i)))
			_loadout_changed())
	_fill_piece_options()
	box.add_child(HSeparator.new())
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
	_clip_opt = _option(box, "Animation (loops)")
	_clip_opt.item_selected.connect(func(i: int) -> void: _play_clip(_clip_opt.get_item_text(i)))
	_check(box, "Hair", _show_hair, func(on: bool) -> void:
		_show_hair = on
		_rebuild_actor())
	_check(box, "Light follows camera", _light_follows, func(on: bool) -> void:
		_light_follows = on
		_update_camera())
	_travel_check = _check(box, "Travel: walks and runs move (V)", _travel, func(on: bool) -> void:
		_set_travel(on))
	var buttons := HBoxContainer.new()
	box.add_child(buttons)
	_pause_button = _button(buttons, "Pause (Space)", func() -> void: _set_paused(not _paused))
	_button(buttons, "Reload (F5)", func() -> void: _reload_from_disk())
	_button(buttons, "Notes", func() -> void:
		if _ensure_session():
			OS.shell_open(_review_dir))
	_clip_label = Label.new()
	box.add_child(_clip_label)
	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.custom_minimum_size = Vector2(290, 0)
	_status.add_theme_font_size_override("font_size", 12)
	box.add_child(_status)
	var help := Label.new()
	help.add_theme_font_size_override("font_size", 12)
	help.text = ("Left drag: orbit. Right/middle drag: pan.\n"
		+ "Up/Down: inspect equipped pieces.\n"
		+ "Wheel or Q/E: zoom. A/D: turn. PgUp/PgDn: tilt.\n"
		+ "1 front, 2 side, 3 back, 4 other side, 5 three-quarter.\n"
		+ "R: reset view. Space: pause. , and .: step a frame.\n"
		+ "[ and ]: speed. V: travel. H: hide panels.\n"
		+ "T: piece comment. S: set comment. F2/C: view note.")
	box.add_child(help)
	_toast = Label.new()
	_toast.anchor_top = 1.0
	_toast.anchor_bottom = 1.0
	_toast.offset_left = 16
	_toast.offset_top = -40
	_toast.add_theme_font_size_override("font_size", 16)
	_ui.add_child(_toast)
	_build_details(theme)
	_build_dialog()
	_refresh_pieces()


func _set_label(entry: Dictionary) -> String:
	return str(entry["name"]).trim_prefix("Audit ")


func _select_set(index: int) -> void:
	if _noting or _dialog.visible:
		return
	_drafts[str(_sets[_set_index]["name"])] = _wardrobe.snapshot()
	_set_index = posmod(index, _sets.size())
	_set_opt.select(_set_index)
	var name := str(_sets[_set_index]["name"])
	if _drafts.has(name):
		_wardrobe.restore(_drafts[name])
	else:
		_wardrobe.use_set(_sets[_set_index]["visuals"])
	_loadout_changed()


func _restore_set() -> void:
	_wardrobe.use_set(_sets[_set_index]["visuals"])
	_loadout_changed()


func _fill_piece_options() -> void:
	for part: int in _piece_options:
		var choice: OptionButton = _piece_options[part]
		choice.clear()
		choice.add_item("Empty slot")
		choice.set_item_metadata(0, "")
		for piece: Dictionary in _wardrobe.by_part.get(part, []):
			choice.add_item(str(piece.name) + (" · visual only" if bool(piece.get("visual_only", false)) else ""))
			choice.set_item_metadata(choice.item_count - 1, str(piece.id))
			choice.set_item_tooltip(choice.item_count - 1, str(piece.name))


func _toggle_piece(part: int, on: bool) -> void:
	_wardrobe.selected_part = part
	_wardrobe.disabled[part] = not on
	_loadout_changed()


func _loadout_changed() -> void:
	_apply_equipment()
	_play_clip(_clip)
	_refresh_pieces()
	_set_status("%s · %s" % [_race_label(), _set_label(_sets[_set_index])])


func _refresh_pieces() -> void:
	for part: int in _piece_options:
		var piece := _wardrobe.piece_at(part)
		var choice: OptionButton = _piece_options[part]
		var check: CheckBox = _piece_checks[part]
		check.disabled = piece.is_empty()
		check.set_pressed_no_signal(not piece.is_empty() and not bool(_wardrobe.disabled.get(part, false)))
		(_piece_buttons[part] as Button).set_pressed_no_signal(part == _wardrobe.selected_part)
		choice.select(0)
		for i in range(choice.item_count):
			if str(choice.get_item_metadata(i)) == str(piece.get("id", "")):
				choice.select(i)
				break
	_refresh_details()


func _build_details(theme: Theme) -> void:
	var panel := PanelContainer.new()
	panel.theme = theme
	_ui.add_child(panel)
	panel.anchor_left = 1.0
	panel.anchor_right = 1.0
	panel.anchor_bottom = 1.0
	panel.offset_left = -372
	panel.offset_right = -12
	panel.offset_top = 12
	panel.offset_bottom = -52
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	panel.add_child(scroll)
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.custom_minimum_size.x = 310
	box.add_theme_constant_override("separation", 12)
	scroll.add_child(box)
	_details_set = Label.new()
	_details_set.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_details_set)
	var row := HBoxContainer.new()
	box.add_child(row)
	_button(row, "Piece comment (T)", func() -> void: _begin_note("piece"))
	_button(row, "Set comment (S)", func() -> void: _begin_note("set"))
	box.add_child(HSeparator.new())
	_details_icon = TextureRect.new()
	_details_icon.custom_minimum_size = Vector2(100, 100)
	_details_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_details_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	box.add_child(_details_icon)
	_details_name = Label.new()
	_details_name.add_theme_font_size_override("font_size", 22)
	_details_name.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_details_name)
	_details_text = RichTextLabel.new()
	_details_text.fit_content = true
	_details_text.scroll_active = false
	_details_text.selection_enabled = true
	box.add_child(_details_text)
	box.add_child(HSeparator.new())
	_details_comments = Label.new()
	_details_comments.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_details_comments)
	var notes := HBoxContainer.new()
	box.add_child(notes)
	_button(notes, "Open saved comments", func() -> void:
		if _ensure_session():
			OS.shell_open(_review_dir))
	_button(notes, "View note (F2)", func() -> void: _begin_note())


func _refresh_details() -> void:
	if _details_name == null:
		return
	_details_set.text = "%s\n%d / %d sets · %d available visuals" % [
		_set_label(_sets[_set_index]), _set_index + 1, _sets.size(), _wardrobe.available_visual_count()]
	var part := _wardrobe.selected_part
	var piece := _wardrobe.piece_at(part)
	_details_name.text = str(piece.get("name", str(PART_LABELS.get(part, "Piece")) + " · empty"))
	var image_id := int(piece.get("image_id", -1))
	_details_icon.texture = (_atlas.worn_icon_for(image_id) if bool(piece.get("worn", false)) else _atlas.icon_for(image_id)) if image_id >= 0 else _atlas.placeholder_icon()
	_details_text.clear()
	if piece.is_empty():
		_details_text.add_text("Choose equipment for this slot to inspect its game details.")
	else:
		var lines := PackedStringArray()
		lines.append("%s · %s" % [PART_LABELS.get(part, "Piece"), "Hidden" if bool(_wardrobe.disabled.get(part, false)) else "Visible"])
		lines.append("\n" + str(piece.get("description", "")))
		lines.append("\nStats")
		var stats: Dictionary = piece.get("stats", {})
		if stats.is_empty():
			lines.append("No game stats available for this visual.")
		for stat: String in stats:
			var value: Variant = stats[stat]
			var words := "%s – %s" % [_stat_number(value[0]), _stat_number(value[1])] if value is Array and value.size() == 2 else _stat_number(value)
			lines.append("%s: %s" % ["Weight (EMU)" if stat == "weight_emu" else stat.replace("_", " ").capitalize(), words])
		for effect: Dictionary in piece.get("effects", []):
			lines.append("\n%s · %s (%s%%)" % [str(effect.get("trigger", "")).capitalize(),
				str(effect.get("kind", "")).replace("_", " "), float(effect.get("chance", 0)) * 100.0])
			for parameter: Array in effect.get("parameters", []):
				lines.append("  %s: %s" % [str(parameter[0]).replace("_", " "), str(parameter[1])])
			if not str(effect.get("message", "")).is_empty():
				lines.append(str(effect.message))
		if not str(piece.get("degrades_to", "")).is_empty():
			lines.append("\nDegrades to: " + str(piece.degrades_to))
		if piece.get("wear_chance") != null:
			lines.append("Wear chance: %s" % piece.wear_chance)
		if piece.has("item_id"):
			lines.append("\nItem #%d · visual %s" % [int(piece.item_id), str(piece.key)])
		if str(piece.get("canonical_name", "")) != str(piece.name):
			lines.append("Catalog name: " + str(piece.canonical_name))
		_details_text.add_text("\n".join(lines))
	var notes := PackedStringArray(["Comments this session"])
	for entry: Dictionary in _comments:
		var target: Dictionary = entry.get("target", {})
		if (str(entry.get("scope", "")) == "piece" and str(target.get("id", "")) == str(piece.get("id", ""))) or (str(entry.get("scope", "")) == "set" and entry.get("set") == _sets[_set_index]["name"]):
			notes.append("\n%s: %s" % ["Piece" if entry.scope == "piece" else "Set", str(entry.comment)])
	_details_comments.text = "\n".join(notes) + ("\nNo comments yet. T comments on the selected piece; S comments on the set." if notes.size() == 1 else "")


func _stat_number(value: Variant) -> String:
	return str(int(value)) if value is float and is_equal_approx(value, roundf(value)) else str(value)


func _option(box: VBoxContainer, label: String) -> OptionButton:
	var caption := Label.new()
	caption.text = label
	box.add_child(caption)
	var option := OptionButton.new()
	option.focus_mode = Control.FOCUS_NONE
	box.add_child(option)
	return option


func _check(box: VBoxContainer, label: String, on: bool, toggled: Callable) -> CheckBox:
	var check := CheckBox.new()
	check.text = label
	check.button_pressed = on
	check.focus_mode = Control.FOCUS_NONE
	check.toggled.connect(toggled)
	box.add_child(check)
	return check


func _button(box: HBoxContainer, label: String, pressed: Callable) -> Button:
	var button := Button.new()
	button.text = label
	button.focus_mode = Control.FOCUS_NONE
	button.pressed.connect(pressed)
	box.add_child(button)
	return button


func _build_dialog() -> void:
	_modal = ColorRect.new()
	_modal.color = Color(0, 0, 0, 0.55)
	_modal.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_modal.visible = false
	_ui.add_child(_modal)
	_dialog = PanelContainer.new()
	_dialog.theme = Theme.new()
	_dialog.theme.default_font_size = 15
	var backing := StyleBoxFlat.new()
	backing.bg_color = Color(0.105, 0.13, 0.15, 1.0)
	backing.content_margin_left = 16
	backing.content_margin_right = 16
	backing.content_margin_top = 16
	backing.content_margin_bottom = 16
	_dialog.theme.set_stylebox("panel", "PanelContainer", backing)
	_dialog.custom_minimum_size = Vector2(660, 260)
	_dialog.visible = false
	_modal.add_child(_dialog)
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
		_status.text = text + "\n" + _extras_line() + ("\nLoaded from disk (newer than the import): %d file(s)" % _raw_loaded.size()
			if not _raw_loaded.is_empty() else "") + "\nNotes: " + _review_dir


## Visibility counts include substitutions and all individually hidden pieces.
func _extras_line() -> String:
	return "%d of %d selected pieces visible" % [_current_visuals().size(), _wardrobe.selected.size()]


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
	if _dialog.visible or _noting:
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
	if key == null or not key.pressed or key.echo or key.ctrl_pressed or key.alt_pressed or key.meta_pressed:
		return
	match key.keycode:
		KEY_UP, KEY_DOWN:
			_wardrobe.cycle_piece(-1 if key.keycode == KEY_UP else 1)
			_refresh_pieces()
			if _piece_buttons.has(_wardrobe.selected_part):
				_piece_scroll.ensure_control_visible(_piece_buttons[_wardrobe.selected_part])
		KEY_LEFT:
			_select_set(_set_index - 1)
		KEY_RIGHT:
			_select_set(_set_index + 1)
		KEY_T:
			_begin_note("piece")
		KEY_S:
			_begin_note("set")
		KEY_F2, KEY_C:
			_begin_note()
		KEY_SPACE:
			_set_paused(not _paused)
		KEY_H:
			for child: Node in _ui.get_children():
				if child != _modal and child != _toast:
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
			_apply_speed()
			_toast_message("Speed x%s" % _speed)
		KEY_V:
			_set_travel(not _travel)
		_:
			if VIEWS.has(key.keycode):
				_yaw = deg_to_rad(float(VIEWS[key.keycode]))
				_update_camera()


func _process(delta: float) -> void:
	if not _dialog.visible and not _noting:
		var turn := 0.0
		var tilt := 0.0
		var zoom := 0.0
		if Input.is_key_pressed(KEY_A): turn += 1.0
		if Input.is_key_pressed(KEY_D): turn -= 1.0
		if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_PAGEUP): tilt += 1.0
		if Input.is_key_pressed(KEY_PAGEDOWN): tilt -= 1.0
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
	if _travel and not _paused:
		# Whole frames, as many as the speed asks for. Slowed, the frames come
		# less often rather than shorter, so the cloth damps as it does in play.
		_travel_owed += delta * _speed
		var frame := minf(delta, 1.0 / 30.0)
		if _travel_owed >= frame * 0.5:
			var run := maxf(frame, minf(_travel_owed, frame * 4.0))
			_travel_frame(run)
			_travel_owed = clampf(_travel_owed - run, -frame, frame)
	if actor != null and actor.animation_player != null and actor.animation_player.has_animation(_clip):
		var player := actor.animation_player
		_clip_label.text = "%s  %.2f / %.2f s  x%s%s%s" % [_clip, player.current_animation_position,
			player.get_animation(_clip).length, _speed, "  (paused)" if _paused else "",
			"\nTravelling %.2f m/s, clip x%.2f" % [_travel_speed, _base_speed]
			if _travel and _travel_speed > 0.0 else ""]


# ---------------------------------------------------------------- notes

func _start_session() -> void:
	var project := ProjectSettings.globalize_path("res://").trim_suffix("/")
	var checkout := project.get_base_dir()
	var stamp := Time.get_datetime_string_from_system().replace(":", "-").replace("T", "_") + "_%d_%d" % [OS.get_process_id(), Time.get_ticks_msec()]
	var root := str(options.get("review-dir", checkout.path_join(".local/asset-authoring/working/equipment-review")))
	_review_dir = root.path_join(stamp)
	_commit = _git(checkout, ["rev-parse", "HEAD"])
	_branch = _git(checkout, ["rev-parse", "--abbrev-ref", "HEAD"])
	_session = {"started": Time.get_datetime_string_from_system(), "checkout": checkout,
		"branch": _branch, "commit": _commit, "dirty": _git(checkout, ["status", "--porcelain"]) != "",
		"godot": Engine.get_version_info().get("string", ""), "options": options}
	print("EQUIPMENT_REVIEW notes folder: ", _review_dir)


## The session folder is written with its first note, so a look without notes leaves nothing.
func _ensure_session() -> bool:
	if FileAccess.file_exists(_review_dir.path_join("session.json")) and FileAccess.file_exists(_review_dir.path_join("notes.md")):
		return true
	if DirAccess.make_dir_recursive_absolute(_review_dir) != OK:
		_toast_message("Cannot create the comments folder: " + _review_dir)
		return false
	var file := FileAccess.open(_review_dir.path_join("session.json"), FileAccess.WRITE)
	if file == null:
		_toast_message("Cannot write session details: " + error_string(FileAccess.get_open_error()))
		return false
	file.store_string(JSON.stringify(_session, "\t") + "\n")
	file = FileAccess.open(_review_dir.path_join("notes.md"), FileAccess.WRITE)
	if file == null:
		_toast_message("Cannot write the comments index")
		return false
	file.store_string("# Equipment review %s\n\nCheckout `%s`, branch `%s`, commit `%s`.\n\n" % [
		_session["started"], _session["checkout"], _branch, _commit.left(10)])
	return true


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
		"loadout": _wardrobe.snapshot(), "selected_part": _wardrobe.selected_part,
		"headwear": visuals.has(HEAD_PART),
		"weapons_and_cape": EXTRA_PARTS.any(func(part: int) -> bool: return visuals.has(part)), "hair": _show_hair,
		"pieces": pieces, "clip": _clip, "clip_time": snappedf(time, 0.001),
		"clip_length": snappedf(length, 0.001), "paused": _paused, "speed": _speed,
		# The camera target is relative to the actor's ground point, which only
		# leaves the origin while travelling.
		"travel": _travel, "travel_speed": snappedf(_travel_speed if _travel else 0.0, 0.001),
		"clip_playback": snappedf(_base_speed, 0.001),
		"camera": {"yaw_degrees": snappedf(rad_to_deg(_yaw), 0.1), "pitch_degrees": snappedf(rad_to_deg(_pitch), 0.1),
			"distance": snappedf(_distance, 0.001), "target": [snappedf(_target.x, 0.001),
			snappedf(_target.y, 0.001), snappedf(_target.z, 0.001)]},
		"window": [get_window().size.x, get_window().size.y], "commit": _commit, "branch": _branch}


func _begin_note(scope := "view") -> void:
	if _dialog.visible or _noting:
		return
	var piece := _wardrobe.piece_at(_wardrobe.selected_part)
	if scope == "piece" and piece.is_empty():
		_toast_message("Select a piece in the left panel before adding a piece comment")
		return
	_noting = true
	_dragging = MOUSE_BUTTON_NONE
	_pending_state = _state()
	_pending_state["scope"] = scope
	_pending_state["target"] = piece.duplicate(true) if scope == "piece" else {"set": _sets[_set_index]["name"]}
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
	var subject := str(piece.name) if scope == "piece" else _set_label(_sets[_set_index])
	_dialog_label.text = "%s comment: %s\n%s · %s at %.2f s. Ctrl+Enter saves, Esc cancels." % [
		scope.capitalize(), subject, _race_label(), _clip, _pending_state["clip_time"]]
	_dialog_text.text = ""
	_dialog.visible = true
	_modal.visible = true
	_noting = false
	_dialog.reset_size()
	_dialog.position = ((get_viewport().get_visible_rect().size - _dialog.get_combined_minimum_size()) / 2.0).floor()
	_dialog_text.grab_focus()


func _save_note() -> void:
	if not _dialog.visible:
		return
	var comment := _dialog_text.text.strip_edges()
	if comment.is_empty():
		_dialog_label.text = "Write a comment before saving. Esc cancels."
		return
	if not _ensure_session():
		_dialog_label.text = "Could not save. Check the comments folder and try again. Your text is preserved."
		return
	var next := _note_count + 1
	var shot := "shot_%03d.png" % next
	if _pending_shot == null or _pending_shot.save_png(_review_dir.path_join(shot)) != OK:
		_dialog_label.text = "Could not save the screenshot. Your comment is preserved; try again."
		return
	var entry := _pending_state.duplicate(true)
	entry["n"] = next
	entry["time"] = Time.get_datetime_string_from_system()
	entry["comment"] = comment
	entry["screenshot"] = shot
	var path := _review_dir.path_join("notes.jsonl")
	var file := FileAccess.open(path, FileAccess.READ_WRITE) if FileAccess.file_exists(path) \
		else FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_dialog_label.text = "Could not save the comment. Your text is preserved; try again."
		return
	file.seek_end()
	file.store_line(JSON.stringify(entry))
	file.flush()
	if file.get_error() != OK:
		_dialog_label.text = "The comment could not be written. Your text is preserved."
		return
	_note_count = next
	_comments.append(entry)
	file = FileAccess.open(_review_dir.path_join("notes.md"), FileAccess.READ_WRITE)
	var parts := PackedStringArray()
	for piece: Dictionary in entry["pieces"]:
		parts.append("%s %s" % [piece["key"], piece["name"]])
	if file != null:
		file.seek_end()
		file.store_string("## %d. %s comment: %s\n\n%s, %s. %s at %.2f s%s. Pieces: %s.\n\n%s\n\n![](%s)\n\n" % [
			_note_count, str(entry.scope).capitalize(), str(entry.target.get("name", entry["set"])),
			_race_label(), entry["set"], entry["clip"], entry["clip_time"], _travel_words(entry),
			", ".join(parts), comment, shot])
	_close_note()
	_refresh_details()
	_toast_message("Saved note %d (%s)" % [_note_count, shot])


func _travel_words(state: Dictionary) -> String:
	if not bool(state.get("travel", false)):
		return ""
	if float(state.get("travel_speed", 0.0)) <= 0.0:
		return " (travel on, on the spot)"
	return " travelling at %.2f m/s (clip x%.2f)" % [float(state["travel_speed"]), float(state["clip_playback"])]


func _close_note() -> void:
	_dialog.visible = false
	_modal.visible = false
	_noting = false
	_dialog_text.release_focus()
	if _resume_after_note:
		_set_paused(false)


# ---------------------------------------------------------------- self-test

## --selftest yes: exercise controls, save piece/set/view notes, then quit.
func _selftest() -> void:
	await get_tree().create_timer(1.5).timeout
	_ensure_session()
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(_review_dir.path_join("ui_check.png"))
	# Use the same keyboard path as an interactive reviewer, including wraparound.
	var key := InputEventKey.new()
	key.pressed = true
	var initial_set := _set_index
	var initial_loadout := _wardrobe.snapshot()
	var initial_pitch := _pitch
	# Feed real viewport key events: selection updates the icon/details, not gear
	# or camera movement, and skips the starter kit's empty quiver slot.
	key.keycode = KEY_DOWN
	Input.parse_input_event(key)
	await get_tree().process_frame
	assert(_wardrobe.selected_part == 6)
	assert(_details_name.text == str(_wardrobe.piece_at(6).name))
	assert(_details_icon.texture == _atlas.icon_for(int(_wardrobe.piece_at(6).image_id)))
	key = key.duplicate()
	key.pressed = false
	Input.parse_input_event(key)
	key = key.duplicate()
	key.pressed = true
	key.keycode = KEY_UP
	Input.parse_input_event(key)
	await get_tree().process_frame
	assert(_wardrobe.selected_part == 5)
	assert(_wardrobe.snapshot() == initial_loadout and _set_index == initial_set)
	assert(is_equal_approx(_pitch, initial_pitch))
	key = key.duplicate()
	key.pressed = false
	Input.parse_input_event(key)
	key = key.duplicate()
	key.pressed = true
	key.keycode = KEY_LEFT
	_unhandled_input(key)
	assert(_set_index == posmod(initial_set - 1, _sets.size()))
	key.keycode = KEY_RIGHT
	_unhandled_input(key)
	assert(_set_index == initial_set)
	var torso_choice: OptionButton = _piece_options[5]
	for i in range(torso_choice.item_count):
		if str(torso_choice.get_item_metadata(i)) == str((_wardrobe.by_key["5:192"] as Dictionary).id):
			torso_choice.select(i)
			torso_choice.item_selected.emit(i)
			break
	assert(int(_current_visuals()[5]) == 192 and int(_current_visuals()[4]) == 220)
	(_piece_checks[5] as CheckBox).button_pressed = false
	assert(not _current_visuals().has(5))
	(_piece_checks[5] as CheckBox).button_pressed = true
	assert(int(_current_visuals()[5]) == 192)
	(_piece_checks[3] as CheckBox).button_pressed = false
	_select_set(initial_set + 1)
	_select_set(initial_set)
	assert(int(_current_visuals()[5]) == 192 and not _current_visuals().has(3))
	(_piece_buttons[5] as Button).pressed.emit()
	key.keycode = KEY_T
	_unhandled_input(key)
	while _noting:
		await get_tree().process_frame
	assert(_dialog.visible and _pending_state.scope == "piece")
	assert(str(_pending_state.target.id) == str(_wardrobe.piece_at(5).id))
	# Arrow keys inside the comment editor must never navigate sets.
	key.keycode = KEY_RIGHT
	_unhandled_input(key)
	assert(_set_index == initial_set)
	_dialog_text.text = "self-test piece comment"
	_save_note()
	key.keycode = KEY_S
	_unhandled_input(key)
	while _noting:
		await get_tree().process_frame
	assert(_dialog.visible and _pending_state.scope == "set")
	_dialog_text.text = "self-test full-set comment"
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(_review_dir.path_join("set_dialog_check.png"))
	_save_note()
	assert(_note_count == 2)
	_restore_set()
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
	# Travel: a run carries the actor at the client's pace, and the note says so.
	_play_clip("Run_Female")
	_set_travel(true)
	await get_tree().create_timer(1.0).timeout
	print("SELFTEST travel ", _clip, " ", snappedf(_travel_speed, 0.01), " m/s, clip x",
		snappedf(_base_speed, 0.01), ", at ", _ground_point())
	await _begin_note()
	_dialog_text.text = "self-test note"
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(_review_dir.path_join("dialog_check.png"))
	_save_note()
	_set_travel(false)
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
		if note.has("loadout"):
			_wardrobe.restore(note.loadout)
		else:
			_wardrobe.use_set(_sets[_set_index]["visuals"])
		_show_head = (bool(note.get("headwear", true)) if not options.has("headwear")
			else options["headwear"] == "yes")
		_show_extras = bool(note.get("weapons_and_cape", false))
		if not note.has("loadout"):
			_wardrobe.disabled[HEAD_PART] = not _show_head
			for part: int in EXTRA_PARTS:
				_wardrobe.disabled[part] = not _show_extras
		_wardrobe.selected_part = int(note.get("selected_part", 5))
		_show_hair = bool(note.get("hair", true))
		_travel = (bool(note.get("travel", false)) if not options.has("travel")
			else options["travel"] == "yes")
		_speed = float(note.get("speed", 1.0))
		_clip = str(note["clip"])
		_paused = true
		await _rebuild_actor()
		_update_floor()
		var camera: Dictionary = note["camera"] as Dictionary
		_yaw = deg_to_rad(float(camera["yaw_degrees"]))
		_pitch = deg_to_rad(float(camera["pitch_degrees"]))
		_distance = float(camera["distance"])
		var target: Array = camera["target"] as Array
		_target = Vector3(float(target[0]), float(target[1]), float(target[2]))
		_update_camera()
		if actor != null and actor.animation_player != null and actor.animation_player.has_animation(_clip):
			if _travel:
				await _travel_up_to(float(note["clip_time"]))
			else:
				actor.animation_player.seek(float(note["clip_time"]), true)
		for _frame in range(3):
			await RenderingServer.frame_post_draw
		var shot := out.path_join("replay_%03d.png" % int(note["n"]))
		get_viewport().get_texture().get_image().save_png(shot)
		print("REPLAY ", int(note["n"]), " -> ", shot, "  travel %.2f m/s, clip x%.2f, %.2f m" % [
			_travel_speed if _travel else 0.0, _base_speed, _ground_point().length()] if _travel else "")
	print("REPLAY_OK ", out)
	get_tree().quit()


## REPLAY_LEAD seconds of play that end on the noted clip time, one 60 Hz game
## frame per drawn frame, so the noted frame has the cloth in motion.
func _travel_up_to(clip_time: float) -> void:
	var player := actor.animation_player
	var frame := 1.0 / 60.0
	var frames := roundi(REPLAY_LEAD / frame)
	player.seek(fposmod(clip_time - frames * frame * _base_speed, player.get_animation(_clip).length), true)
	actor.global_position = Vector3.ZERO
	var cloth: Node = actor._cape_cloth
	if cloth != null:
		cloth.call("reset")
	for _i in range(frames):
		_travel_frame(frame)
		await get_tree().process_frame
