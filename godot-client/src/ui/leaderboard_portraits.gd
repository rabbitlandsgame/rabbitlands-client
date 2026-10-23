extends Node
## One short-lived 3D stage bakes the real runtime character into cached icons.
## No per-card live viewports, uploads, guessed faces, or persistent player data.

signal portrait_ready(key: String, texture: Texture2D)
const CACHE_LIMIT := 32
const PORTRAIT_SIZE := 256
var textures: Dictionary = {}
var _order: Array[String] = []
var _queue: Array[Dictionary] = []
var _pending: Dictionary = {}
var _active := false
var _busy := false
var _generation := 0
var _registry: Dictionary = {}
var _equipment: Dictionary = {}
var _viewport: SubViewport
var _stage: Node3D
var _camera: Camera3D

func configure(registry: Dictionary, equipment: Dictionary) -> void:
	_registry = registry
	_equipment = equipment

static func cache_key(look: Dictionary) -> String:
	return JSON.stringify(look, "", true).sha256_text()

func begin_batch() -> void:
	_generation += 1
	_queue.clear()
	_pending.clear()

func set_active(value: bool) -> void:
	_active = value
	if not value:
		begin_batch()
		if is_instance_valid(_viewport):
			_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	elif not _queue.is_empty():
		_pump.call_deferred()

func request(look: Dictionary) -> Texture2D:
	var key := cache_key(look)
	if textures.has(key):
		_order.erase(key)
		_order.append(key)
		return textures[key]
	if look.is_empty() or not _active or DisplayServer.get_name() == "headless":
		return null
	if not _pending.has(key):
		_pending[key] = true
		_queue.append({"key":key, "look":look.duplicate(true), "generation":_generation})
		_pump.call_deferred()
	return null

func is_idle() -> bool:
	return not _busy and _queue.is_empty()

func clear() -> void:
	set_active(false)
	textures.clear()
	_order.clear()
	if is_instance_valid(_viewport):
		_viewport.queue_free()
		_viewport = null
		_stage = null

func _pump() -> void:
	if _busy or not _active or _queue.is_empty():
		return
	_busy = true
	_load_resources()
	_create_stage()
	while _active and not _queue.is_empty():
		_create_stage()
		var job: Dictionary = _queue.pop_front()
		var texture: Texture2D = await _render(job.look, int(job.generation))
		if int(job.generation) == _generation:
			_pending.erase(str(job.key))
		if texture != null and int(job.generation) == _generation:
			textures[job.key] = texture
			_order.erase(str(job.key))
			_order.append(str(job.key))
			while _order.size() > CACHE_LIMIT:
				textures.erase(_order.pop_front())
			portrait_ready.emit(str(job.key), texture)
	_busy = false
	if is_instance_valid(_viewport):
		_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED

func _load_resources() -> void:
	if _registry.is_empty():
		_registry = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	if _equipment.is_empty():
		_equipment = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))

func _create_stage() -> void:
	if is_instance_valid(_viewport):
		return
	_viewport = SubViewport.new()
	_viewport.name = "PortraitBakeStage"
	_viewport.own_world_3d = true
	_viewport.size = Vector2i(PORTRAIT_SIZE, PORTRAIT_SIZE)
	_viewport.msaa_3d = Viewport.MSAA_2X
	_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	add_child(_viewport)
	_stage = Node3D.new()
	_viewport.add_child(_stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("192534")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("d8dfef")
	environment.environment.ambient_light_energy = 0.85
	_stage.add_child(environment)
	for settings: Array in [[Vector3(-30, -155, 0), Color("ffe5bd"), 1.35],
			[Vector3(-15, 25, 0), Color("c0d9ff"), 0.65]]:
		var light := DirectionalLight3D.new()
		light.rotation_degrees = settings[0]
		light.light_color = settings[1]
		light.light_energy = settings[2]
		light.shadow_enabled = false
		_stage.add_child(light)
	_camera = Camera3D.new()
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.near = 0.02
	_stage.add_child(_camera)

func _render(look: Dictionary, generation: int) -> Texture2D:
	var model_id := str((_registry.get("actorTypes", {}) as Dictionary).get(str(int(look.get("actor_type", -1))), ""))
	var model: Dictionary = (_registry.get("models", {}) as Dictionary).get(model_id, {})
	if not model.has("culture") or bool(model.get("retired", false)):
		return null
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(str(model.animationMap)))
	var dto := {"actor_id":0, "kind":1, "name":"", "x":0, "y":0, "rotation":0,
		"actor_type":int(look.actor_type), "appearance":look.get("appearance", {}).duplicate(true),
		"equipment_visuals":look.get("equipment_visuals", {}).duplicate(true)}
	var errors := actor.configure(dto, CoordinateAdapter.new({"walkingHeight":0}), model, animation, _equipment)
	if not errors.is_empty() or actor.get_skeleton() == null:
		actor.queue_free()
		return null
	actor.collision_layer = 0
	actor.set_nameplate_visible(false)
	actor.set_health_visible(false)
	actor.set_hand_props_visible(false)
	actor.set_cape_cloth_allowed(false)
	actor.apply_render_quality(2, true)
	if actor.animation_player != null:
		actor.animation_player.advance(0)
		actor.animation_player.pause()
	actor.process_mode = Node.PROCESS_MODE_DISABLED
	# Wait for native bone attachments and appearance surfaces to settle.
	await get_tree().process_frame
	if generation != _generation or not _active:
		if is_instance_valid(actor):
			actor.queue_free()
		return null
	var skeleton := actor.get_skeleton()
	var head_bone := skeleton.find_bone("Head")
	if head_bone < 0:
		actor.queue_free()
		return null
	var head := skeleton.global_transform * skeleton.get_bone_global_pose(head_bone).origin
	var height := maxf(0.8, head.y - actor.global_position.y)
	var focus := head + Vector3(0, height * 0.02, 0)
	_camera.size = height * 0.32
	_camera.position = focus + Vector3(-0.32, 0.10, -2.8)
	_camera.look_at(focus)
	_viewport.render_target_update_mode = SubViewport.UPDATE_ONCE
	await RenderingServer.frame_post_draw
	var result: Texture2D
	if generation == _generation and _active:
		var image := _viewport.get_texture().get_image()
		if image != null and not image.is_empty():
			result = ImageTexture.create_from_image(image)
	if is_instance_valid(actor):
		actor.queue_free()
	await get_tree().process_frame
	return result
