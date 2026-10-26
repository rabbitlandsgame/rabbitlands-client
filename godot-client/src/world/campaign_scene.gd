extends Node
## Reversible, per-view story staging. Only server snapshots authorize a scene;
## the camera, gestures, skip and transcript never complete a gameplay objective.
const DATA_PATH := "res://data/campaign/scenes.json"
const Dialogue := preload("res://src/ui/campaign_dialogue.gd")
const Choice := preload("res://src/ui/campaign_choice.gd")
const WAIT_LIMIT := 45.0
const MAX_DURATION := 60.0

signal presentation_finished(token: String, reason: String)
signal replay_finished(token: String, reason: String)
signal choice_requested(option_id: String)
signal inspection_requested(action: String)
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
var _dialogue: PanelContainer
var _bottom: PanelContainer
var _choice_dialog: PanelContainer
var _choice_scroll: ScrollContainer
var _choice_state: Dictionary = {}
var _choice_revealed := false
var _choice_waiting := false
var _choice_completed := false
var _choice_review := false
var _choice_initially_selected := false
var _choice_pending_at := -1
var _choice_error := ""
var _inspection_state: Dictionary = {}
var _inspection_sent := false
var _inspection_active := false
var _inspection_pending_at := -1
var _inspection_error := ""
var _protagonist_name := "You"
var _inspection_retry: Button
var _margin: MarginContainer
var _actions: HFlowContainer
var _account: Button
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
var _local_actor: WeakRef
var _local_start := Vector3.ZERO
var _returning := false
var _return_elapsed := 0.0
var _return_duration := 0.0
var _return_reason := ""
var _return_start: Dictionary = {}
var _reduced_view: Dictionary = {}
var _reduced_origin := Vector3.ZERO
var _resume_view: Dictionary = {}
var _resume_at := 0.0
var _resume_seconds := 0.0

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
	_bottom = bottom
	bottom.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	bottom.offset_top = -182
	bottom.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_screen.add_child(bottom)
	var margin := MarginContainer.new()
	_margin = margin
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 16)
	bottom.add_child(margin)
	var column := VBoxContainer.new()
	margin.add_child(column)
	_dialogue = Dialogue.new()
	column.add_child(_dialogue)
	_caption = _dialogue.body_label
	var actions := HFlowContainer.new()
	_actions = actions
	actions.add_theme_constant_override("h_separation", 14)
	actions.add_theme_constant_override("v_separation", 6)
	column.add_child(actions)
	_skip = Button.new()
	_skip.text = "Return to play · Esc"
	_skip.pressed.connect(skip)
	actions.add_child(_skip)
	_account = Button.new()
	_account.text = "Read scene account"
	_account.pressed.connect(show_transcript)
	actions.add_child(_account)
	_reduced = CheckButton.new()
	_reduced.text = "Reduced camera motion"
	_reduced.button_pressed = reduced_motion
	_reduced.toggled.connect(set_reduced_motion)
	actions.add_child(_reduced)
	_inspection_retry = Button.new()
	_inspection_retry.text = "Retry inspection"
	_inspection_retry.pressed.connect(_request_inspection)
	actions.add_child(_inspection_retry)
	_inspection_retry.hide()
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
	_choice_dialog = Choice.new()
	_choice_dialog.set_embedded(true)
	_choice_scroll = _dialogue.content_slot
	_choice_dialog.option_selected.connect(_on_choice_option)
	_choice_dialog.continue_requested.connect(_on_choice_continue)
	_choice_dialog.minimum_size_changed.connect(_layout_presentation)
	# Keep ownership even for old snapshots without a choice. The dialogue
	# retains the embedded control while switching back to ordinary speech.
	_dialogue.set_content("You", _choice_dialog)
	_dialogue.set_line("", "")
	get_viewport().size_changed.connect(_layout_presentation)
	_layout_presentation()
	_layer.hide()

func _layout_presentation() -> void:
	if not is_instance_valid(_bottom):
		return
	var area := get_viewport().get_visible_rect().size
	var compact := area.x < 620.0 or area.y < 400.0
	var padding := 8 if compact else 16
	for side: String in ["left", "right", "top", "bottom"]:
		_margin.add_theme_constant_override("margin_" + side, padding)
	var height := minf(300.0, maxf(160.0, area.y - 88.0)) if _choice_waiting \
		else clampf(area.y * 0.30, 176.0, 242.0)
	_bottom.offset_top = -height
	_dialogue.fit_width(maxf(160.0, area.x - padding * 2.0))
	_dialogue.fit_content_height(maxf(64.0, height - (72.0 if compact else 96.0)))
	_skip.text = ("Return now · Esc" if _returning else "Return · Esc") if compact \
		else ("Return now · Esc" if _returning else "Return to play · Esc")
	_account.text = "Scene account" if compact else "Read scene account"
	_reduced.text = "Reduced motion" if compact else "Reduced camera motion"
	_actions.add_theme_constant_override("h_separation", 8 if compact else 14)
	for control: Control in [_skip, _account, _reduced, _inspection_retry]:
		control.add_theme_font_size_override("font_size", 14 if compact else 16)

func blocks_input() -> bool:
	return playing

func is_active() -> bool:
	return pending or playing

func is_replaying() -> bool:
	return _replaying

func choice_context() -> Dictionary:
	return {"run_id": _run, "token": _token, "id": str(_choice_state.get("id", "")), "waiting": _choice_waiting and playing and not _returning}

func inspection_context() -> Dictionary:
	return {"run_id": _run, "token": _token, "id": str(_inspection_state.get("id", "")),
		"waiting": playing and not _returning and _inspection_sent and str(_inspection_state.get("status", "")) != "complete"}

func inspection_send_failed() -> void:
	_inspection_pending_at = -1
	_inspection_error = "The inspection has not been confirmed. Retry, or return to play and inspect the landing."
	if is_instance_valid(_inspection_retry): _inspection_retry.show()

func _has_inspection() -> bool:
	return not _inspection_state.is_empty() \
		and str(_definition.get("inspection_id", "")) == str(_inspection_state.get("id", "")) \
		and EloriaProtocol.campaign_scene_inspection_valid(_inspection_state)

func _request_inspection() -> void:
	if not playing or _returning or _replaying or not _has_inspection() \
			or not bool(_inspection_state.get("can_start", false)) \
			or str(_inspection_state.get("status", "")) == "complete": return
	_inspection_sent = true
	_inspection_active = true
	_inspection_pending_at = Time.get_ticks_msec()
	_inspection_error = ""
	_inspection_retry.hide()
	inspection_requested.emit("start")

func _stop_inspection() -> void:
	if _inspection_active and not _replaying and str(_inspection_state.get("status", "")) != "complete":
		inspection_requested.emit("cancel")
	_inspection_active = false
	_inspection_pending_at = -1

func choice_send_failed() -> void:
	_choice_pending_at = -1
	_choice_error = "Your choice has not been confirmed. Try again, or return to play."
	if is_instance_valid(_choice_dialog):
		_choice_dialog.release_pending(_choice_error)

func _choice_token() -> String:
	return _run + "|" + _token + "|" + str(_choice_state.get("id", ""))

func _has_choice() -> bool:
	return not _choice_state.is_empty() and str(_definition.get("choice_id", "")) == str(_choice_state.get("id", "")) \
		and EloriaProtocol.campaign_scene_choice_valid(_choice_state)

func _show_choice() -> void:
	var payload := _choice_state.duplicate(true)
	payload.token = _choice_token()
	payload.error = _choice_error
	_choice_dialog.apply_choice(payload, _choice_review)
	_dialogue.set_content(_protagonist_name, _choice_dialog, _actors.get("protagonist") as Node3D)
	_layout_presentation()

func _on_choice_option(option_id: String, token: String) -> void:
	if not playing or _returning or not _choice_waiting or _choice_review or _replaying \
			or token != _choice_token() or _choice_pending_at >= 0 or not _has_choice() \
			or not str(_choice_state.get("selected", "")).is_empty() \
			or not bool(_choice_state.get("can_choose", false)) or not bool(_choice_state.get("owner_is_you", false)):
		return
	var offered := false
	for option: Dictionary in _choice_state.options:
		if str(option.id) == option_id: offered = true
	if not offered: return
	_choice_error = ""
	_choice_pending_at = Time.get_ticks_msec()
	choice_requested.emit(option_id)

func _on_choice_continue(token: String) -> void:
	if not playing or not _choice_waiting or not _choice_review or token != _choice_token(): return
	_finish_choice()

func _finish_choice() -> void:
	_choice_waiting = false
	_choice_completed = true
	_choice_pending_at = -1
	_choice_dialog.reset()
	_layout_presentation()

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
	if playing and value != reduced_motion and _camera_handoff():
		if value:
			_reduced_view = _capture_camera()
			_reduced_origin = _local_position()
		else:
			_resume_view = _capture_camera()
			_resume_at = elapsed
			_resume_seconds = minf(1.0, maxf(0.05, _duration() - elapsed))
	reduced_motion = value
	if _returning and value:
		cancel(_return_reason)
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
	var previous_selection := str(_choice_state.get("selected", ""))
	_choice_state = (scene.get("choice", {}) as Dictionary).duplicate(true)
	_inspection_state = (scene.get("inspection", {}) as Dictionary).duplicate(true)
	_protagonist_name = str(_choice_state.get("owner", "You")).strip_edges()
	if _protagonist_name.is_empty(): _protagonist_name = "You"
	if is_active() and previous_selection != str(_choice_state.get("selected", "")):
		_build_transcript()
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
		# A named speaker may be known to the server before its native model has
		# finished construction. Keep the camera with the player until it exists.
		if not _replaying:
			for role: String in _definition.get("required_actors", []):
				if bindings.has(role):
					var speaker: Variant = actor_nodes.get(int(bindings[role]))
					if not is_instance_valid(speaker) or not speaker is Node3D:
						return
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
		if _returning:
			_return_elapsed = minf(_return_elapsed + maxf(0.0, delta), _return_duration)
			var weight := smoothstep(0.0, _return_duration, _return_elapsed)
			_apply_camera_pose(_mix_camera(_return_start, _gameplay_camera(), weight))
			_screen.modulate.a = 1.0 - weight
			if _return_elapsed >= _return_duration:
				cancel(_return_reason)
			return
		if is_instance_valid(_transcript) and _transcript.visible:
			return
		var next_elapsed := minf(elapsed + maxf(0.0, delta), _duration())
		if _has_inspection():
			if not _replaying and not _inspection_sent and next_elapsed >= float(_definition.get("inspection_at", 19.0)):
				_request_inspection()
			if not _replaying and str(_inspection_state.get("status", "")) != "complete" \
					and next_elapsed >= float(_definition.get("inspection_wait_at", 24.0)):
				elapsed = float(_definition.get("inspection_wait_at", 24.0))
				if str(_inspection_state.get("status", "")) == "blocked" and _inspection_error.is_empty() \
						and bool(_choice_state.get("owner_is_you", false)):
					inspection_send_failed()
					_inspection_error = "The path is blocked. Retry the walk, or return to play to reach the landing."
				if _inspection_pending_at >= 0 and Time.get_ticks_msec() - _inspection_pending_at >= 8000:
					inspection_send_failed()
				_apply_actors()
				_apply_camera()
				_update_caption()
				return
			if str(_inspection_state.get("status", "")) == "complete":
				_inspection_active = false
				_inspection_retry.hide()
		var choice_at := float(_definition.get("choice_at", -1.0))
		if _has_choice() and not _choice_completed and choice_at >= 0.0 and next_elapsed >= choice_at:
			elapsed = choice_at
			if not _choice_revealed:
				_choice_revealed = true
				_choice_waiting = true
				_choice_review = _replaying or _choice_initially_selected
			if not _choice_review and not str(_choice_state.get("selected", "")).is_empty():
				_finish_choice()
			else:
				if _choice_pending_at >= 0 and Time.get_ticks_msec() - _choice_pending_at >= 8000:
					choice_send_failed()
				_show_choice()
			_apply_actors()
			_apply_camera()
			_update_caption()
			return
		elapsed = next_elapsed
		_apply_actors()
		_apply_camera()
		_update_caption()
		if elapsed >= _duration():
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
	_local_actor = weakref(local)
	_local_start = local.global_position
	_returning = false
	_return_start.clear()
	_choice_revealed = false
	_choice_waiting = false
	_choice_completed = false
	_choice_review = false
	_choice_initially_selected = not str(_choice_state.get("selected", "")).is_empty()
	_choice_pending_at = -1
	_choice_error = ""
	_inspection_sent = false
	_inspection_active = false
	_inspection_pending_at = -1
	_inspection_error = ""
	_inspection_retry.hide()
	_choice_dialog.reset()
	_choice_scroll.hide()
	_resume_view.clear()
	_reduced_origin = _local_start
	_reduced_view = _gameplay_camera()
	var focus := get_viewport().gui_get_focus_owner()
	_saved_focus = weakref(focus) if focus != null else null
	_actors.clear()
	_posts.clear()
	for role: String in bindings:
		var actor_value: Variant = nodes.get(int(bindings[role]))
		if not is_instance_valid(actor_value) or not actor_value is Node3D:
			continue
		if actor_value == local and (role != "protagonist" or not bool(_definition.get("stage_protagonist", false))):
			continue
		var actor: Node3D = actor_value
		_actors[role] = actor
		_posts[role] = actor.global_transform
	if _actors.has("protagonist"):
		_anchors["protagonist_post"] = (_actors.protagonist as Node3D).global_position
		_anchors["protagonist_return"] = _authoritative_position(_actors.protagonist)
	for key: String in _anchors:
		_anchors[key] = _ground(_anchors[key])
	var anchor := str(_definition.get("anchor", ""))
	_origin = _anchors.get(anchor,
		(_actors[anchor] as Node3D).global_position if _actors.has(anchor) else local.global_position)
	if rig.has_method("cancel_rotation"):
		rig.call("cancel_rotation")
	_title.text = str(_definition.get("title", ""))
	_skip.text = "Return to play · Esc"
	_screen.modulate.a = 1.0
	_reduced.set_pressed_no_signal(reduced_motion)
	_layer.show()
	_skip.grab_focus()
	pending = false
	playing = true
	_apply_actors()
	_apply_camera()
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
	var transform := Transform3D(Basis.IDENTITY, position).looking_at(target, Vector3.UP)
	var pose := {"transform": transform, "target": target, "near": 0.5,
		"far": float(_saved.get("far", _camera.far)), "fov": float(_definition.get("fov", 50.0))}
	if _camera_handoff():
		if reduced_motion:
			# Reduced motion keeps the player's own framing, rather than cutting
			# to the first authored shot or flying across the scene.
			pose = _reduced_view.duplicate()
			var movement := _local_position() - _reduced_origin
			var held: Transform3D = pose.transform
			held.origin += movement
			pose.transform = held
			pose.target += movement
		else:
			var entry := _handoff_seconds("entry_seconds")
			if entry > 0.0 and elapsed < entry:
				pose = _mix_camera(_gameplay_camera(), pose, smoothstep(0.0, entry, elapsed))
			var exit := _handoff_seconds("exit_seconds")
			if exit > 0.0 and elapsed > _duration() - exit:
				pose = _mix_camera(pose, _gameplay_camera(), smoothstep(_duration() - exit, _duration(), elapsed))
			if not _resume_view.is_empty():
				pose = _mix_camera(_resume_view, pose, smoothstep(_resume_at, _resume_at + _resume_seconds, elapsed))
		var opacity := 1.0
		var entry_fade := minf(0.6, _handoff_seconds("entry_seconds"))
		if entry_fade > 0.0:
			opacity = smoothstep(0.0, entry_fade, elapsed)
		var exit_fade := minf(0.6, _handoff_seconds("exit_seconds"))
		if exit_fade > 0.0:
			opacity = minf(opacity, 1.0 - smoothstep(_duration() - exit_fade, _duration(), elapsed))
		_screen.modulate.a = opacity
	_apply_camera_pose(pose)

func _duration() -> float:
	return minf(MAX_DURATION, maxf(0.0, float(_definition.get("duration", 0.0))))

func _handoff_seconds(key: String) -> float:
	return clampf(float(_definition.get(key, 0.0)), 0.0, minf(5.0, _duration() * 0.5))

func _camera_handoff() -> bool:
	return _handoff_seconds("entry_seconds") > 0.0 or _handoff_seconds("exit_seconds") > 0.0

func _local_position() -> Vector3:
	if _local_actor != null:
		var local := _local_actor.get_ref() as Node3D
		if is_instance_valid(local):
			return _authoritative_position(local) if _actors.get("protagonist") == local else local.global_position
	return _local_start

func _authoritative_position(actor: Node3D) -> Vector3:
	# A staged body may be between authored poses while ordinary native walk
	# packets update its real destination. Restore the viewport to that real pose.
	if actor is ReplicatedActor3D: return (actor as ReplicatedActor3D).server_target
	for property: Dictionary in actor.get_property_list():
		if str(property.name) == "server_target":
			var value: Variant = actor.get("server_target")
			if value is Vector3: return value
			if value is Transform3D: return value.origin
	return actor.global_position

func _authoritative_yaw(actor: Node3D, fallback: float) -> float:
	if actor is ReplicatedActor3D: return (actor as ReplicatedActor3D)._target_yaw
	for property: Dictionary in actor.get_property_list():
		if str(property.name) == "server_target":
			var value: Variant = actor.get("server_target")
			if value is Transform3D: return value.basis.get_euler().y
	return fallback

func _gameplay_camera() -> Dictionary:
	var movement := _local_position() - _local_start if _camera_handoff() else Vector3.ZERO
	var transform: Transform3D = _saved.get("camera", Transform3D.IDENTITY)
	transform.origin += movement
	var focus: Variant = _saved.get("focus")
	var target: Vector3 = focus + Vector3.UP * 1.2 + movement if focus is Vector3 \
		else transform.origin - transform.basis.z * 10.0
	return {"transform": transform, "target": target, "near": float(_saved.get("near", 0.5)),
		"far": float(_saved.get("far", 4000.0)), "fov": float(_saved.get("fov", 50.0))}

func _capture_camera() -> Dictionary:
	return {"transform": _camera.global_transform,
		"target": _view_focus.global_position + Vector3.UP if is_instance_valid(_view_focus) \
			else _camera.global_position - _camera.global_basis.z * 10.0,
		"near": _camera.near, "far": _camera.far, "fov": _camera.fov}

func _mix_camera(from: Dictionary, to: Dictionary, weight: float) -> Dictionary:
	return {"transform": (from.transform as Transform3D).interpolate_with(to.transform, weight),
		"target": (from.target as Vector3).lerp(to.target, weight),
		"near": lerpf(float(from.near), float(to.near), weight),
		"far": lerpf(float(from.far), float(to.far), weight),
		"fov": lerpf(float(from.fov), float(to.fov), weight)}

func _apply_camera_pose(pose: Dictionary) -> void:
	_camera.global_transform = pose.transform
	_camera.near = float(pose.near)
	_camera.far = float(pose.far)
	_camera.fov = float(pose.fov)
	_view_focus.global_position = (pose.target as Vector3) - Vector3.UP

func _apply_actors() -> void:
	var cues: Array = _definition.get("cues", [])
	if _actors.has("protagonist"):
		_anchors["protagonist_return"] = _ground(_authoritative_position(_actors.protagonist))
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
		if action == &"walk" and (progress >= 1.0 or from.distance_to(to) < 0.05):
			action = &"idle"
		var facing := str(chosen.get("face", ""))
		var face_point: Vector3 = _anchors.get(facing,
			(_actors[facing] as Node3D).global_position if _actors.has(facing) else _origin)
		var direction: Vector3 = face_point - at
		var resting_yaw := _authoritative_yaw(actor, post.basis.get_euler().y) if role == "protagonist" \
			else post.basis.get_euler().y
		var yaw := atan2(-direction.x, -direction.z) if facing != "post" \
			and Vector2(direction.x, direction.z).length() > 0.05 else resting_yaw
		if actor.has_method("set_cinematic_presentation"):
			actor.call("set_cinematic_presentation", at, yaw, action,
				to.distance_to(from) / move_seconds if move_seconds > 0.0 and progress < 1.0 else 0.0)
		else:
			actor.global_position = at
			actor.rotation.y = yaw

func _line_text(line: Dictionary) -> String:
	return str((line.get("variants", {}) as Dictionary).get(_variant, line.get("text", "")))

func _update_caption() -> void:
	if _choice_waiting:
		_dialogue.set_content(_protagonist_name, _choice_dialog, _actors.get("protagonist") as Node3D)
		return
	var chosen: Dictionary = {}
	for line: Dictionary in _definition.get("lines", []):
		if float(line.get("at", 0.0)) > elapsed:
			break
		chosen = line
	var speaker := str(chosen.get("speaker", ""))
	var role := str(chosen.get("speaker_actor", ""))
	if role == "protagonist": speaker = _protagonist_name
	var text := _line_text(chosen)
	if _has_inspection() and not _replaying and elapsed >= float(_definition.get("inspection_wait_at", 24.0)) \
			and str(_inspection_state.get("status", "")) != "complete":
		speaker = _protagonist_name
		role = "protagonist"
		text = _inspection_error if not _inspection_error.is_empty() else \
			"Waiting for the story owner to inspect the landing…" if not bool(_choice_state.get("owner_is_you", false)) else \
			"Taking a closer look at the damaged landing…"
	if _choice_completed and _has_choice() and elapsed < float(_definition.get("choice_response_until", _duration())):
		speaker = "Odo Fenn"
		role = "odo"
		text = str(_choice_state.get("response", ""))
		if text.is_empty(): text = "No rescue plan was recorded. Speak to Odo when you are ready to decide."
	if role.is_empty() and not speaker.is_empty():
		role = {"Odo Fenn": "odo", "Landing clerk": "clerk", "Dock foreman": "foreman",
			"Worker": "worker", "Works Hand": "worker", "Serit Voss": "voss"}.get(speaker, "")
		if role.is_empty():
			for candidate: String in _actors:
				if candidate.length() > 2 and speaker.to_lower().contains(candidate.to_lower()):
					role = candidate
					break
	var actor: Node3D = _actors.get(role) as Node3D
	_dialogue.set_line(speaker, text, actor if is_instance_valid(actor) else null)

func _build_transcript() -> void:
	var lines: PackedStringArray = [str(_definition.get("title", "")), ""]
	for line: Dictionary in _definition.get("lines", []):
		var speaker := str(line.get("speaker", ""))
		lines.append((speaker + ": " if not speaker.is_empty() else "") + _line_text(line))
	if _has_choice():
		lines.append(str(_choice_state.get("title", "Choose a rescue plan")))
		for option: Dictionary in _choice_state.options:
			lines.append(("[Recorded choice] " if str(option.id) == str(_choice_state.get("selected", "")) else "") \
				+ str(option.label) + ": " + str(option.detail))
		if not str(_choice_state.get("response", "")).is_empty():
			lines.append("Odo Fenn: " + str(_choice_state.response))
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
	_stop_inspection()
	if _returning:
		cancel(_return_reason)
	elif playing and _handoff_seconds("exit_seconds") > 0.0 and not reduced_motion:
		_returning = true
		_return_elapsed = 0.0
		_return_duration = minf(0.7, _handoff_seconds("exit_seconds"))
		_return_reason = "skipped"
		_return_start = _capture_camera()
		_choice_dialog.hide()
		if is_instance_valid(_transcript):
			_transcript.hide()
		_skip.text = "Return now · Esc"
	else:
		cancel("skipped")

func cancel(reason := "cancelled") -> void:
	_stop_inspection()
	var owned := is_active()
	var was_replay := _replaying
	var movement := _local_position() - _local_start if _camera_handoff() else Vector3.ZERO
	_returning = false
	_return_elapsed = 0.0
	_return_start.clear()
	_choice_waiting = false
	_choice_pending_at = -1
	if is_instance_valid(_inspection_retry): _inspection_retry.hide()
	if is_instance_valid(_choice_dialog): _choice_dialog.reset()
	if is_instance_valid(_choice_scroll): _choice_scroll.hide()
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
			var rig_pose: Transform3D = _saved.rig
			rig_pose.origin += movement
			_rig.global_transform = rig_pose
			for key: String in ["focus", "distance", "pitch_degrees", "yaw_degrees"]:
				if _saved[key] != null:
					_rig.set(key, _saved[key] + movement if key == "focus" and _saved[key] is Vector3 else _saved[key])
		if is_instance_valid(_camera):
			var camera_pose: Transform3D = _saved.camera
			camera_pose.origin += movement
			_camera.global_transform = camera_pose
			_camera.fov = float(_saved.fov)
			_camera.near = float(_saved.near)
			_camera.far = float(_saved.far)
	_saved.clear()
	_local_actor = null
	_reduced_view.clear()
	_resume_view.clear()
	pending = false
	playing = false
	if _layer != null:
		_layer.hide()
	if is_instance_valid(_dialogue):
		_dialogue.reset()
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
