extends Node
## Reversible, per-view story staging. Only server snapshots authorize a scene;
## the camera, gestures, skip and transcript never complete a gameplay objective.
const DATA_PATH := "res://data/campaign/scenes.json"
const WAIT_LIMIT := 45.0
const MAX_DURATION := 60.0

signal presentation_finished(token: String, reason: String)
signal replay_finished(token: String, reason: String)
signal transcript_changed(text: String)

var reduced_motion := false
var playing := false
var pending := false
var elapsed := 0.0
var _wait_elapsed := 0.0
var _actor_wait_elapsed := 0.0
var _token := ""
var _map := ""
var _run := ""
var _variant := ""
var _definition: Dictionary = {}
var _handled: Dictionary = {}
var _actors: Dictionary = {}
var _posts: Dictionary = {}
var _rig: Node3D
var _camera: Camera3D
var _saved: Dictionary = {}
var _origin := Vector3.ZERO
var _saved_focus: WeakRef
var _layer: CanvasLayer
var _screen: Control
var _feed: TextureRect
var _title: Label
var _caption: Label
var _skip: Button
var _reduced: CheckButton
var _transcript: AcceptDialog
var _transcript_text: RichTextLabel
var _last_transcript := ""
var _definitions: Dictionary = {}
var _anchors: Dictionary = {}
var _adapter: CoordinateAdapter
var _surface_sample: Callable
var _ambient_actor: Node3D
var _ambient_post := Transform3D.IDENTITY
var _ambient_elapsed := 0.0
var _ack_identity := ""
var _ack_requested := false
var _view_focus: Node3D
var _replay_requested_identity := ""
var _replaying := false
var _replay_bindings: Dictionary = {}
var _replay_nodes: Dictionary = {}

func _ready() -> void:
	var config := ConfigFile.new()
	if config.load("user://campaign_presentation.cfg") == OK:
		reduced_motion = bool(config.get_value("presentation", "reduced_motion", false))

static func scene_definitions() -> Dictionary:
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(DATA_PATH))
	return data.get("scenes", {}) if data is Dictionary else {}

static func map_key(value: String) -> String:
	return EloriaProtocol.map_id_from_reference(value)

func configure(view: SubViewport = null) -> void:
	if _layer != null:
		if view != null:
			_feed.texture = view.get_texture()
		return
	_layer = CanvasLayer.new()
	_layer.name = "CampaignPresentation"
	_layer.layer = 119
	add_child(_layer)
	_screen = Control.new()
	_screen.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_screen.mouse_filter = Control.MOUSE_FILTER_STOP
	_layer.add_child(_screen)
	_feed = TextureRect.new()
	_feed.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_feed.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_feed.stretch_mode = TextureRect.STRETCH_SCALE
	_feed.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if view != null:
		_feed.texture = view.get_texture()
	_screen.add_child(_feed)
	var top := PanelContainer.new()
	top.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	top.offset_bottom = 66
	_screen.add_child(top)
	_title = Label.new()
	_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_title.add_theme_font_size_override("font_size", 23)
	top.add_child(_title)
	var bottom := PanelContainer.new()
	bottom.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	bottom.offset_top = -182
	bottom.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_screen.add_child(bottom)
	var margin := MarginContainer.new()
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 16)
	bottom.add_child(margin)
	var column := VBoxContainer.new()
	margin.add_child(column)
	_caption = Label.new()
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_caption.custom_minimum_size.y = 82
	_caption.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_caption.add_theme_font_size_override("font_size", 20)
	column.add_child(_caption)
	var actions := HFlowContainer.new()
	actions.add_theme_constant_override("h_separation", 14)
	actions.add_theme_constant_override("v_separation", 6)
	column.add_child(actions)
	_skip = Button.new()
	_skip.text = "Return to play · Esc"
	_skip.pressed.connect(skip)
	actions.add_child(_skip)
	var account := Button.new()
	account.text = "Read scene account"
	account.pressed.connect(show_transcript)
	actions.add_child(account)
	_reduced = CheckButton.new()
	_reduced.text = "Reduced camera motion"
	_reduced.button_pressed = reduced_motion
	_reduced.toggled.connect(set_reduced_motion)
	actions.add_child(_reduced)
	_transcript = AcceptDialog.new()
	_transcript.title = "Scene account"
	_transcript.dialog_text = ""
	_transcript.min_size = Vector2i(360, 220)
	_transcript.size = Vector2i(680, 400)
	add_child(_transcript)
	_transcript_text = RichTextLabel.new()
	_transcript_text.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_transcript_text.offset_left = 16
	_transcript_text.offset_right = -16
	_transcript_text.offset_top = 12
	_transcript_text.offset_bottom = -52
	_transcript_text.selection_enabled = true
	_transcript_text.bbcode_enabled = false
	_transcript.add_child(_transcript_text)
	_layer.hide()

func blocks_input() -> bool:
	return playing

func is_active() -> bool:
	return pending or playing

func can_replay(snapshot: Dictionary, current_map: String) -> bool:
	return _replay_requested_identity.is_empty() and _replay_allowed(snapshot, current_map)

func _replay_allowed(snapshot: Dictionary, current_map: String) -> bool:
	if is_active() or not bool(snapshot.get("active", false)):
		return false
	var here := map_key(current_map)
	if here.is_empty() or map_key(str(snapshot.get("map", ""))) != here:
		return false
	var scene: Dictionary = snapshot.get("scene", {})
	var token := str(scene.get("token", ""))
	var run := str(snapshot.get("run_id", ""))
	var identity := run + ":" + token
	if run.is_empty() or token.is_empty() or not _handled.has(identity):
		return false
	if _definitions.is_empty():
		_definitions = scene_definitions()
	if not _definitions.has(str(scene.get("id", ""))):
		return false
	if str(snapshot.get("kind", "")) == "lamps" \
			and str(scene.get("id", "")) in ["measure.lamps.admission", "measure.lamps.resolved"] \
			and not bool((snapshot.get("lamps", {}) as Dictionary).get("evidence_secure", false)):
		return false
	# A replay cannot stand in for an outstanding first viewing or rejoin ack.
	return not bool(scene.get("requires_ack", false)) or \
		(_ack_identity == identity + ":" + str(scene.get("ack_revision", 0)) and _ack_requested)

func request_replay(snapshot: Dictionary, current_map: String) -> bool:
	if not can_replay(snapshot, current_map):
		return false
	_replay_requested_identity = str(snapshot.get("run_id", "")) + ":" + str(snapshot.scene.token)
	return true

func work_readouts_visible() -> bool:
	if not playing:
		return true
	var shown := bool(_definition.get("show_readouts", false))
	for shot: Dictionary in _definition.get("shots", []):
		if float(shot.get("t", 0)) > (0.0 if reduced_motion else elapsed):
			break
		if shot.has("readouts"):
			shown = bool(shot.readouts)
	return shown

func occlusion_focus() -> Node3D:
	return _view_focus if playing else null

func transcript_text() -> String:
	return _last_transcript

func show_transcript() -> void:
	configure()
	_transcript_text.text = _last_transcript if not _last_transcript.is_empty() else "No scene has played yet."
	var viewport_size := get_viewport().get_visible_rect().size
	_transcript.popup_centered(Vector2i(mini(680, int(viewport_size.x * 0.9)),
		mini(400, int(viewport_size.y * 0.8))))

func set_reduced_motion(value: bool, persist := true) -> void:
	reduced_motion = value
	if is_instance_valid(_reduced):
		_reduced.set_pressed_no_signal(value)
	if persist:
		var config := ConfigFile.new()
		config.set_value("presentation", "reduced_motion", value)
		config.save("user://campaign_presentation.cfg")

func update(delta: float, snapshot: Dictionary, rig: Node3D, actor_nodes: Dictionary,
		local_actor_id: int, current_map: String, world_ready := true,
		coordinate_adapter: CoordinateAdapter = null, surface_sample := Callable()) -> void:
	if not bool(snapshot.get("active", false)):
		cancel("inactive")
		return
	var incoming_map := map_key(str(snapshot.get("map", "")))
	var here := map_key(current_map)
	if incoming_map.is_empty() or incoming_map != here:
		cancel("map_changed")
		return
	var scene: Dictionary = snapshot.get("scene", {})
	if str(snapshot.get("kind", "")) == "lamps" \
			and str(scene.get("id", "")) in ["measure.lamps.admission", "measure.lamps.resolved"] \
			and not bool((snapshot.get("lamps", {}) as Dictionary).get("evidence_secure", false)):
		cancel("evidence_not_secure")
		return
	var next_token := str(scene.get("token", ""))
	var next_run := str(snapshot.get("run_id", ""))
	if is_active() and (_token != next_token or _run != next_run or _map != here):
		cancel("replaced")
	if next_token.is_empty() or scene.is_empty():
		_replay_requested_identity = ""
		return
	var identity := next_run + ":" + next_token
	var ack_identity := identity + ":" + str(scene.get("ack_revision", 0))
	if _ack_identity != ack_identity or not bool(scene.get("requires_ack", false)):
		_ack_identity = ack_identity
		_ack_requested = false
	if not is_active():
		var replay := _replay_requested_identity == identity and _replay_allowed(snapshot, current_map)
		_replay_requested_identity = ""
		if _handled.has(identity) and not replay:
			if bool(scene.get("requires_ack", false)) and not _ack_requested:
				_ack_requested = true
				presentation_finished.emit(next_token, "already_seen")
			return
		if _definitions.is_empty():
			_definitions = scene_definitions()
		var id := str(scene.get("id", ""))
		if not _definitions.has(id):
			_handled[identity] = true
			return # An unknown presentation must never lock a working quest.
		_token = next_token
		_replaying = replay
		_run = next_run
		_map = here
		_variant = str(scene.get("variant", snapshot.get("cargo_priority", "")))
		_definition = (_definitions[id] as Dictionary).duplicate(true)
		_adapter = coordinate_adapter
		_surface_sample = surface_sample
		_anchors.clear()
		var raw_anchors: Dictionary = (snapshot.get("anchors", {}) as Dictionary).duplicate(true)
		raw_anchors.merge(scene.get("anchors", {}), true)
		# A road scene establishes the accepted cart pose at the scene barrier,
		# never a future waypoint along the route.
		if str(snapshot.get("kind", "")) == "road":
			for cart: Dictionary in (snapshot.get("road", {}) as Dictionary).get("carts", []):
				raw_anchors["cart_" + str(cart.id)] = cart.tile
		if str(snapshot.get("kind", "")) == "lamps":
			var equipment_tile: Array = (snapshot.get("lamps", {}) as Dictionary).get("equipment_tile", raw_anchors.get("equipment", []))
			if equipment_tile.size() == 2:
				raw_anchors.equipment_current = equipment_tile
		if _adapter != null:
			for key: String in raw_anchors:
				var tile: Array = raw_anchors[key]
				_anchors[key] = _ground(_adapter.tile_center(int(tile[0]), int(tile[1])))
		pending = true
		_wait_elapsed = 0.0
		_actor_wait_elapsed = 0.0
		elapsed = 0.0
		_rig = rig
		_build_transcript()
	if pending:
		_wait_elapsed += maxf(0.0, delta)
		if _wait_elapsed >= WAIT_LIMIT:
			_handled[identity] = true
			cancel("loading_timeout")
			return
		var local_value: Variant = actor_nodes.get(local_actor_id)
		if not world_ready or not is_instance_valid(local_value) or not local_value is Node3D or not is_instance_valid(rig):
			return
		var local: Node3D = local_value
		var bindings: Dictionary = scene.get("actors", snapshot.get("actors", {}))
		if _replaying:
			for role: String in bindings:
				var bound: Variant = actor_nodes.get(int(bindings[role]))
				if not is_instance_valid(bound) or not bound is Node3D:
					_actor_wait_elapsed += maxf(0.0, delta)
					if _actor_wait_elapsed >= 2.0:
						cancel("actor_lost")
					return
		if _actor_wait_elapsed < 2.0:
			for role: String in bindings:
				if not is_instance_valid(actor_nodes.get(int(bindings[role]))):
					_actor_wait_elapsed += maxf(0.0, delta)
					return # Give budgeted NPC construction a brief opportunity to finish.
		var camera_value: Variant = rig.get("camera")
		if not camera_value is Camera3D or not is_instance_valid(camera_value):
			return
		if not _anchors_ready():
			return # Keep gameplay available while neighboring terrain finishes loading.
		_start(rig, camera_value as Camera3D, local, actor_nodes, bindings)
		if _replaying:
			_replay_bindings = bindings.duplicate(true)
			_replay_nodes = {local_actor_id: local}
			for role: String in bindings:
				var actor_id := int(bindings[role])
				_replay_nodes[actor_id] = actor_nodes.get(actor_id)
		_handled[identity] = true
	if playing:
		if _replaying:
			if scene.get("actors", snapshot.get("actors", {})) != _replay_bindings:
				cancel("actor_lost")
				return
			for actor_id: int in _replay_nodes:
				if not is_instance_valid(_replay_nodes[actor_id]) or actor_nodes.get(actor_id) != _replay_nodes[actor_id]:
					cancel("actor_lost")
					return
		if not is_instance_valid(_rig) or not is_instance_valid(_camera):
			cancel("camera_lost")
			return
		# Never hold the player's controls for a missing NPC or an asset failure.
		for role: String in _actors:
			if not is_instance_valid(_actors[role]):
				cancel("actor_lost")
				return
		if is_instance_valid(_transcript) and _transcript.visible:
			return
		elapsed = minf(elapsed + maxf(0.0, delta), minf(MAX_DURATION, float(_definition.get("duration", 0.0))))
		_apply_camera()
		_apply_actors()
		_update_caption()
		if elapsed >= minf(MAX_DURATION, float(_definition.get("duration", 0.0))):
			cancel("finished")

func _start(rig: Node3D, camera: Camera3D, local: Node3D, nodes: Dictionary,
		bindings: Dictionary) -> void:
	configure()
	if not is_instance_valid(_view_focus):
		_view_focus = Node3D.new()
		_view_focus.name = "CampaignViewFocus"
		add_child(_view_focus)
	_release_ambient()
	_rig = rig
	_camera = camera
	_saved = {"rig": rig.global_transform, "camera": camera.global_transform,
		"fov": camera.fov, "near": camera.near, "far": camera.far,
		"focus": rig.get("focus"), "distance": rig.get("distance"),
		"pitch_degrees": rig.get("pitch_degrees"), "yaw_degrees": rig.get("yaw_degrees")}
	var focus := get_viewport().gui_get_focus_owner()
	_saved_focus = weakref(focus) if focus != null else null
	_actors.clear()
	_posts.clear()
	for role: String in bindings:
		var actor_value: Variant = nodes.get(int(bindings[role]))
		if not is_instance_valid(actor_value) or not actor_value is Node3D or actor_value == local:
			continue
		var actor: Node3D = actor_value
		_actors[role] = actor
		_posts[role] = actor.global_transform
	for key: String in _anchors:
		_anchors[key] = _ground(_anchors[key])
	var anchor := str(_definition.get("anchor", ""))
	_origin = _anchors.get(anchor,
		(_actors[anchor] as Node3D).global_position if _actors.has(anchor) else local.global_position)
	if rig.has_method("cancel_rotation"):
		rig.call("cancel_rotation")
	_title.text = str(_definition.get("title", ""))
	_reduced.set_pressed_no_signal(reduced_motion)
	_layer.show()
	_skip.grab_focus()
	pending = false
	playing = true
	_apply_camera()
	_apply_actors()
	_update_caption()

func _apply_camera() -> void:
	var shots: Array = _definition.get("shots", [])
	if shots.is_empty():
		return
	var first: Dictionary = shots[0]
	var last: Dictionary = first
	var weight := 0.0
	if not reduced_motion:
		for i in range(1, shots.size()):
			last = shots[i]
			if elapsed <= float(last.t):
				if bool(last.get("cut", false)):
					if elapsed < float(last.t):
						last = first
					else:
						first = last
				else:
					weight = smoothstep(float(first.t), float(last.t), elapsed)
				break
			first = last
	var first_anchor: Vector3 = _anchors.get(str(first.get("anchor", "")), _origin)
	var last_anchor: Vector3 = _anchors.get(str(last.get("anchor", "")), _origin)
	if _actors.has(str(first.get("anchor_actor", ""))):
		first_anchor = (_actors[str(first.anchor_actor)] as Node3D).global_position
	if _actors.has(str(last.get("anchor_actor", ""))):
		last_anchor = (_actors[str(last.anchor_actor)] as Node3D).global_position
	var position := (first_anchor + _vector(first.position)).lerp(last_anchor + _vector(last.position), weight)
	var target := (first_anchor + _vector(first.target)).lerp(last_anchor + _vector(last.target), weight)
	_camera.global_position = position
	_camera.look_at(target, Vector3.UP)
	_view_focus.global_position = target - Vector3.UP # Existing scenery fade probes chest height.
	_camera.near = 0.5
	_camera.fov = float(_definition.get("fov", 50.0))

func _apply_actors() -> void:
	var cues: Array = _definition.get("cues", [])
	for role: String in _actors:
		var actor: Node3D = _actors[role]
		var post: Transform3D = _posts[role]
		var chosen: Dictionary = {}
		var previous_offset := Vector3.ZERO
		for cue: Dictionary in cues:
			if str(cue.get("actor", "")) != role or float(cue.get("at", 0.0)) > elapsed:
				continue
			if not chosen.is_empty():
				previous_offset = _vector(chosen.get("offset", [0, 0, 0]))
			chosen = cue
		if chosen.is_empty():
			continue
		var destination := _vector(chosen.get("offset", [0, 0, 0]))
		var move_seconds := float(chosen.get("move_seconds", 0.0))
		var progress := clampf((elapsed - float(chosen.get("at", 0.0))) / move_seconds, 0.0, 1.0) \
			if move_seconds > 0.0 else 1.0
		var from: Vector3 = _anchors.get(str(chosen.get("from", "")), post.origin + previous_offset)
		var to: Vector3 = _anchors.get(str(chosen.get("destination", "")), post.origin + destination)
		var at := _ground(from.lerp(to, progress))
		var action := StringName(str(chosen.get("action", "idle")))
		if action == &"walk" and progress >= 1.0:
			action = &"idle"
		var facing := str(chosen.get("face", ""))
		var face_point: Vector3 = _anchors.get(facing,
			(_actors[facing] as Node3D).global_position if _actors.has(facing) else _origin)
		var direction: Vector3 = face_point - at
		var yaw := atan2(-direction.x, -direction.z) if Vector2(direction.x, direction.z).length() > 0.05 else post.basis.get_euler().y
		if actor.has_method("set_cinematic_presentation"):
			actor.call("set_cinematic_presentation", at, yaw, action,
				to.distance_to(from) / move_seconds if move_seconds > 0.0 and progress < 1.0 else 0.0)
		else:
			actor.global_position = at
			actor.rotation.y = yaw

func _line_text(line: Dictionary) -> String:
	return str((line.get("variants", {}) as Dictionary).get(_variant, line.get("text", "")))

func _update_caption() -> void:
	var caption := ""
	for line: Dictionary in _definition.get("lines", []):
		if float(line.get("at", 0.0)) > elapsed:
			break
		var speaker := str(line.get("speaker", ""))
		caption = (speaker + ": " if not speaker.is_empty() else "") + _line_text(line)
	_caption.text = caption

func _build_transcript() -> void:
	var lines: PackedStringArray = [str(_definition.get("title", "")), ""]
	for line: Dictionary in _definition.get("lines", []):
		var speaker := str(line.get("speaker", ""))
		lines.append((speaker + ": " if not speaker.is_empty() else "") + _line_text(line))
	_last_transcript = "\n\n".join(lines)
	transcript_changed.emit(_last_transcript)

func handle_input(event: InputEvent) -> bool:
	if not playing:
		return false
	if event is InputEventKey and event.is_pressed() and not (event as InputEventKey).echo:
		if (event as InputEventKey).physical_keycode == KEY_ESCAPE:
			if is_instance_valid(_transcript) and _transcript.visible:
				_transcript.hide()
			else:
				skip()
			return true
	# Let GUI navigation and buttons receive input; the host suppresses world hotkeys.
	return false

func skip() -> void:
	cancel("skipped")

func cancel(reason := "cancelled") -> void:
	var owned := is_active()
	var was_replay := _replaying
	_replay_requested_identity = ""
	_replaying = false
	_replay_bindings.clear()
	_replay_nodes.clear()
	for role: String in _actors:
		var actor_value: Variant = _actors[role]
		if not is_instance_valid(actor_value):
			continue
		var actor: Node3D = actor_value
		if actor.has_method("end_cinematic_presentation"):
			actor.call("end_cinematic_presentation")
		else:
			actor.global_transform = _posts[role]
	_actors.clear()
	_posts.clear()
	if not _saved.is_empty():
		if is_instance_valid(_rig):
			_rig.global_transform = _saved.rig
			for key: String in ["focus", "distance", "pitch_degrees", "yaw_degrees"]:
				if _saved[key] != null:
					_rig.set(key, _saved[key])
		if is_instance_valid(_camera):
			_camera.global_transform = _saved.camera
			_camera.fov = float(_saved.fov)
			_camera.near = float(_saved.near)
			_camera.far = float(_saved.far)
	_saved.clear()
	pending = false
	playing = false
	if _layer != null:
		_layer.hide()
	if is_instance_valid(_transcript):
		_transcript.hide()
	if _saved_focus != null:
		var control := _saved_focus.get_ref() as Control
		if is_instance_valid(control) and control.is_inside_tree() and control.is_visible_in_tree():
			control.grab_focus()
		_saved_focus = null
	if owned:
		if was_replay:
			replay_finished.emit(_token, reason)
		else:
			if reason in ["finished", "skipped", "loading_timeout", "actor_lost", "camera_lost"]:
				_ack_requested = true
			presentation_finished.emit(_token, reason)
	if reason in ["disconnected", "map_changed", "session_ended", "unavailable"]:
		_ack_identity = ""
		_ack_requested = false
	if reason not in ["finished", "skipped"]:
		_release_ambient()

func update_ambient(snapshot: Dictionary, actor_nodes: Dictionary, adapter: CoordinateAdapter,
		surface_sample: Callable, delta := 1.0 / 60.0) -> void:
	if is_active():
		return
	var mechanism: Dictionary = snapshot.get("mechanism", {})
	var lamps: Dictionary = snapshot.get("lamps", {})
	var lamps_hold := str(snapshot.get("kind", "")) == "lamps" \
		and map_key(str(snapshot.get("map", ""))) == "greenlight" \
		and "edda" in str(lamps.get("holder", "")).to_lower() and bool(lamps.get("holder_active", false))
	var wanted := bool(snapshot.get("active", false)) and map_key(str(snapshot.get("map", ""))) == "twinbrook" \
		and bool(mechanism.get("bypass_open", false)) and not bool(mechanism.get("crew_safe", false))
	wanted = wanted or bool(snapshot.get("active", false)) and lamps_hold
	var bindings: Dictionary = snapshot.get("actors", {})
	var actor_value: Variant = actor_nodes.get(int(bindings.get("edda" if lamps_hold else "voss", -1)))
	if not wanted or not is_instance_valid(actor_value) or not actor_value is Node3D:
		_release_ambient()
		return
	var actor: Node3D = actor_value
	if is_instance_valid(_ambient_actor) and _ambient_actor != actor:
		_release_ambient()
	if _ambient_actor != actor:
		_ambient_post = actor.global_transform
		_ambient_elapsed = 0.0
	_ambient_actor = actor
	_ambient_elapsed += maxf(0, delta)
	var post := _ambient_post.origin
	var face := post + Vector3.FORWARD
	var anchors: Dictionary = snapshot.get("anchors", {})
	var anchor: Array = anchors.get("gate", []) if lamps_hold else anchors.get("sluice_prop", anchors.get("bypass", []))
	var work: Array = anchors.get("edda_work", []) if lamps_hold else anchors.get("voss_work", [])
	if adapter != null:
		if work.size() == 2:
			post = adapter.tile_center(int(work[0]), int(work[1]))
		if anchor.size() == 2:
			face = adapter.tile_center(int(anchor[0]), int(anchor[1]))
	# The real companion must reach the held post first. The one-metre
	# reversible step only brings her hands to the already held gate surface.
	if lamps_hold and _ambient_elapsed <= maxf(0, delta) \
			and Vector2(actor.global_position.x - post.x, actor.global_position.z - post.z).length() > 0.8:
		_release_ambient()
		return
	var at := post + Vector3.BACK * minf(1.0, _ambient_elapsed / 0.8)
	if surface_sample.is_valid():
		var height: Variant = surface_sample.call(at)
		if typeof(height) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(height)):
			at.y = float(height)
		else:
			return
	var direction := face - at
	var yaw := atan2(-direction.x, -direction.z) if Vector2(direction.x, direction.z).length() > 0.05 else actor.rotation.y
	if actor.has_method("set_cinematic_presentation"):
		actor.call("set_cinematic_presentation", at, yaw, &"defend", 0.0)

func _release_ambient() -> void:
	if is_instance_valid(_ambient_actor) and _ambient_actor.has_method("end_cinematic_presentation"):
		_ambient_actor.call("end_cinematic_presentation")
	elif is_instance_valid(_ambient_actor):
		_ambient_actor.global_transform = _ambient_post
	_ambient_actor = null
	_ambient_elapsed = 0.0

func _anchors_ready() -> bool:
	if not _surface_sample.is_valid():
		return true # Legacy scenes with no coordinate anchors use live actor posts.
	for key: String in _anchors:
		var point: Vector3 = _anchors[key]
		var height: Variant = _surface_sample.call(point)
		if typeof(height) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(height)):
			return false
		point.y = float(height)
		_anchors[key] = point
	return true

func _ground(point: Vector3) -> Vector3:
	if _surface_sample.is_valid():
		var height: Variant = _surface_sample.call(point)
		if typeof(height) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(height)):
			point.y = float(height)
	return point

func reset_session() -> void:
	cancel("session_ended")
	_handled.clear()
	_token = ""
	_run = ""
	_map = ""

func _exit_tree() -> void:
	cancel("tree_exit")

static func _vector(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))
