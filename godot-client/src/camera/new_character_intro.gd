extends Node
## Creation-only arrival. The staging loader joins the ordinary World3D while
## hidden, so its worker imports and registers the city before login adopts it.
const Shot := preload("res://src/dev/trailer_camera/trailer_shot.gd")
const MAP := "landfall"
const DURATION := 8.0
const DISTANCE := 9.0
const PITCH := -24.0
const VIEW_RADIUS := 80.0
const LOAD_TIMEOUT_MSEC := 45000
const RUN_SPEED := 4.2
const DIALOGUE_TIMEOUT := 12.0

signal conversation_requested(actor_id: int)
signal conversation_ended

var pending := false
var playing := false
var elapsed := 0.0
var greeting_phase: StringName = &""
var _guide: Node3D
var _guide_beacon: MapMarker3D
var _guide_id := -1
var _guide_post := Transform3D.IDENTITY
var _approach := Vector3.ZERO
var _phase_elapsed := 0.0
var _wave_duration := 2.0
var _conversation_requested := false
var _loader: WorldLoader
var _stream: ContinentChunkStream
var _shot: RefCounted
var _layer: CanvasLayer
var _feed: TextureRect
var _curtain: ColorRect
var _caption: Label
var _wait_started := 0
var _ready_frames := 0
var _fov := 50.0
var _yaw := 0.0

static func final_position(spawn: Vector3, yaw: float) -> Vector3:
	var pitch := deg_to_rad(PITCH)
	return spawn + Vector3(sin(deg_to_rad(yaw)) * cos(pitch), -sin(pitch),
		cos(deg_to_rad(yaw)) * cos(pitch)) * DISTANCE

static func build_shot(spawn: Vector3, yaw := 0.0, fov := 50.0) -> RefCounted:
	var shot := Shot.new()
	var target := spawn + Vector3.UP * 1.2
	shot.parse(JSON.stringify({"map": MAP, "name": "Welcome to Landfall", "fov": fov,
		"keys": [
			{"t": 0, "position": _array(spawn + Vector3(68, 62, 100)),
				"lookAt": _array(spawn + Vector3(42, 2, -25))},
			{"t": 3, "position": _array(spawn + Vector3(-12, 40, 62)),
				"lookAt": _array(spawn + Vector3(15, 1.2, -12))},
			{"t": 5, "position": _array(spawn + Vector3(-8, 22, 28)),
				"lookAt": _array(target)},
			{"t": DURATION, "position": _array(final_position(spawn, yaw)),
				"lookAt": _array(target)}]}))
	shot.resolve(Callable(), Callable())
	return shot

static func evaluate(shot: RefCounted, time: float) -> Dictionary:
	# Ease the entire spline once: easing each segment would change velocity
	# abruptly at the city/descent keys. Both ends arrive at rest.
	return shot.evaluate(DURATION * smoothstep(0.0, DURATION, time))

static func _array(point: Vector3) -> Array:
	return [point.x, point.y, point.z]

func prewarm(entry: Dictionary, parent: Node3D) -> void:
	if is_instance_valid(_loader):
		return
	var path := str(entry.get("manifest", ""))
	if path.is_empty():
		return
	_loader = WorldLoader.new()
	_loader.name = "ArrivalPreload"
	parent.add_child(_loader)
	_loader.hide()
	_loader.load_world(ProjectSettings.globalize_path(path), Vector3.INF, true)
	_stream = _loader.world_root as ContinentChunkStream
	if _stream == null:
		discard_preload()
		return
	var spawns: Array = _loader.manifest.data.get("spawnPoints", [])
	if spawns.is_empty():
		discard_preload()
		return
	var position: Array = spawns[0].position
	var spawn := Vector3(float(position[0]), float(position[1]), float(position[2]))
	var points := PackedVector3Array([spawn])
	points.append_array(build_shot(spawn).samples(0.5))
	_stream.preload_views(points, VIEW_RADIUS)

func take_preload(map_id: String) -> Dictionary:
	if map_id != MAP or not is_instance_valid(_loader) or _stream == null:
		discard_preload()
		return {}
	var resident := _loader.release_world()
	_loader.queue_free()
	_loader = null
	(resident.root as Node3D).show()
	return resident

func discard_preload() -> void:
	if is_instance_valid(_loader):
		_loader.queue_free() # Stream exit orphans live imports without joining them.
	_loader = null
	_stream = null

func arm(viewport: SubViewport) -> void:
	_end_conversation()
	_restore_guide()
	greeting_phase = &""
	pending = true
	playing = false
	elapsed = 0.0
	_ready_frames = 0
	_wait_started = Time.get_ticks_msec()
	if _layer == null:
		_layer = CanvasLayer.new()
		_layer.name = "CharacterArrival"
		_layer.layer = 120
		add_child(_layer)
		_feed = TextureRect.new()
		_feed.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		_feed.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		_feed.stretch_mode = TextureRect.STRETCH_SCALE
		_layer.add_child(_feed)
		_curtain = ColorRect.new()
		_curtain.color = Color(0.025, 0.035, 0.045, 1.0)
		_curtain.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		_layer.add_child(_curtain)
		_caption = Label.new()
		_caption.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
		_caption.grow_horizontal = Control.GROW_DIRECTION_BOTH
		_caption.grow_vertical = Control.GROW_DIRECTION_BOTH
		_caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		_layer.add_child(_caption)
	_feed.texture = viewport.get_texture()
	_curtain.modulate.a = 1.0
	_caption.text = "Arriving in Landfall…"
	_caption.modulate.a = 1.0
	_caption.show()
	_layer.show()

func blocks_input() -> bool:
	return pending or playing or greeting_phase != &""

func allows_dialogue() -> bool:
	return greeting_phase == &"conversation" or greeting_phase == &"waiting_dialogue"

func dismiss_conversation() -> void:
	if allows_dialogue():
		_return_to_post()

func update(delta: float, rig: IsometricCameraController, actor: Node3D,
		grounded: bool, guide_ready: bool, guide: Node3D = null, guide_id := -1,
		dialogue: Dictionary = {}) -> void:
	if not blocks_input():
		return
	if greeting_phase != &"":
		_update_greeting(delta, actor, dialogue)
		_follow_guide_beacon()
		return
	if is_instance_valid(guide):
		_guide = guide
		_guide_id = guide_id
		_follow_guide_beacon()
	if pending:
		var failed := is_instance_valid(_stream) and _stream.views_failed()
		var timed_out := Time.get_ticks_msec() - _wait_started > LOAD_TIMEOUT_MSEC
		if failed or timed_out:
			# A failed scenery import must never strand a successfully created player.
			finish(rig, actor)
			cancel()
			return
		if not is_instance_valid(actor) or not grounded or not guide_ready:
			return
		if is_instance_valid(_stream) and not _stream.views_ready():
			return
		_ready_frames += 1
		if _ready_frames < 3:
			return
		_yaw = actor.global_rotation_degrees.y
		_fov = rig.camera.fov
		_shot = build_shot(actor.global_position, _yaw, _fov)
		pending = false
		playing = true
		rig.cancel_rotation()
		_caption.text = "Landfall · Esc to skip"
		apply_pose(rig, 0.0)
		return
	elapsed = minf(elapsed + delta, DURATION)
	apply_pose(rig, elapsed)
	_curtain.modulate.a = 1.0 - clampf(elapsed / 0.6, 0.0, 1.0)
	_caption.modulate.a = 1.0 - clampf((elapsed - 1.5) / 0.8, 0.0, 1.0)
	if elapsed >= DURATION:
		finish(rig, actor)

func apply_pose(rig: IsometricCameraController, time: float) -> void:
	var pose: Dictionary = evaluate(_shot, time)
	rig.camera.global_position = pose.position
	rig.camera.look_at(pose.target, Vector3.UP)
	rig.camera.near = 1.0

func finish(rig: IsometricCameraController, actor: Node3D) -> void:
	var was_playing := playing
	pending = false
	playing = false
	if is_instance_valid(_stream):
		_stream.release_views()
	_stream = null
	if is_instance_valid(actor):
		rig.distance = DISTANCE
		rig.pitch_degrees = PITCH
		rig.yaw_degrees = _yaw if was_playing else actor.global_rotation_degrees.y
		rig.set_focus(actor.global_position)
	if _layer != null:
		_layer.hide()
	if is_instance_valid(_guide) and is_instance_valid(actor):
		if _layer != null:
			_curtain.modulate.a = 0.0
			_caption.hide()
			_layer.show()
		_guide_post = _guide.global_transform
		_approach = actor.global_position + actor.global_basis.x * 1.7 - actor.global_basis.z * 2.4
		_wave_duration = clampf(float(_guide.call("cinematic_action_duration", &"emote_greet")), 1.0, 4.0)
		greeting_phase = &"wave"
		_phase_elapsed = 0.0
		_pose_guide(_guide_post.origin, actor.global_position, &"emote_greet")

func _pose_guide(point: Vector3, facing: Vector3, action: StringName, speed := 0.0) -> void:
	var direction := facing - point
	var yaw := atan2(-direction.x, -direction.z) if Vector2(direction.x, direction.z).length() > 0.01 \
		else _guide.rotation.y
	_guide.call("set_cinematic_presentation", point, yaw, action, speed)

func _update_greeting(delta: float, actor: Node3D, dialogue: Dictionary) -> void:
	if not is_instance_valid(_guide) or not is_instance_valid(actor):
		cancel()
		return
	_phase_elapsed += delta
	match greeting_phase:
		&"wave":
			if _phase_elapsed >= _wave_duration:
				greeting_phase = &"approach"
				_phase_elapsed = 0.0
		&"approach", &"return":
			var returning := greeting_phase == &"return"
			var destination := _guide_post.origin if returning else _approach
			var point := _guide.global_position.move_toward(destination, RUN_SPEED * delta)
			_pose_guide(point, destination, &"run", RUN_SPEED)
			if point.distance_to(destination) < 0.01:
				if returning:
					_restore_guide()
					greeting_phase = &""
					if _layer != null:
						_layer.hide()
				else:
					_pose_guide(point, actor.global_position, &"idle")
					greeting_phase = &"waiting_dialogue"
					_phase_elapsed = 0.0
					_conversation_requested = true
					if _layer != null:
						_layer.hide()
					conversation_requested.emit(_guide_id)
		&"waiting_dialogue":
			if bool(dialogue.get("open", false)) and str(dialogue.get("name", "")) == "Nash" \
					and not str(dialogue.get("text", "")).is_empty():
				greeting_phase = &"conversation"
			elif _phase_elapsed >= DIALOGUE_TIMEOUT:
				_return_to_post()
		&"conversation":
			if not bool(dialogue.get("open", false)):
				_return_to_post()

func _return_to_post() -> void:
	greeting_phase = &"return"
	_phase_elapsed = 0.0
	if _layer != null:
		_layer.show()
	_end_conversation()

func _end_conversation() -> void:
	if _conversation_requested:
		_conversation_requested = false
		conversation_ended.emit()

func _restore_guide() -> void:
	if is_instance_valid(_guide_beacon):
		_guide_beacon.queue_free()
	_guide_beacon = null
	if is_instance_valid(_guide):
		_guide.call("end_cinematic_presentation")
	_guide = null
	_guide_id = -1

func _follow_guide_beacon() -> void:
	if not is_instance_valid(_guide):
		return
	if not is_instance_valid(_guide_beacon):
		_guide_beacon = MapMarker3D.new()
		_guide.get_parent().add_child(_guide_beacon)
		_guide_beacon.configure({"label": "Nash"}, CoordinateAdapter.new(), false)
		_guide_beacon.get_node("WorldLabel").hide()
	_guide_beacon.follow_actor(_guide.global_position)

func owns_guide_beacon(actor_id: int) -> bool:
	return is_instance_valid(_guide_beacon) and _guide_id == actor_id

func cancel() -> void:
	_end_conversation()
	_restore_guide()
	greeting_phase = &""
	pending = false
	playing = false
	if is_instance_valid(_stream):
		_stream.release_views()
	discard_preload()
	if _layer != null:
		_layer.hide()
