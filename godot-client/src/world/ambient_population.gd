class_name AmbientPopulation
extends Node3D
## Spawns a map's declared ambient livestock and wildlife at runtime.
##
## These are scenery animals, not networked actors: they carry no actor id, no
## collision and no server state, so they must never be fused into the static
## world mesh where they would become part of the collision surface. Declaring
## them in the manifest and instancing them here keeps the static package clean
## while letting a region read as inhabited.
##
## Networked creatures and NPCs remain the server's business and continue to
## arrive through the normal actor path; the manifest records the placements a
## server profile should own under `runtimePopulation`.

const MODEL_CATALOG := "res://data/actors/models.json"
const NAVIGATION_LAYER := 8
## How often the herd is re-read against the camera; see AnimationGate.
const GATE_REFRESH_SECONDS := 0.15
## The sphere an animal is tested against the frustum with, before its own
## scale: the largest of them is a horse, two and a half metres nose to tail.
const VIEW_RADIUS := 3.0
const QUALITY := preload("res://src/actors/actor_render_quality.gd")
const ARCHIVED_MODELS := preload("res://src/actors/archived_model_policy.gd")
const SCENE_CACHE := preload("res://src/actors/glb_scene_cache.gd")
const CREATIONS_PER_PASS := [2, 3, 4]
const CREATION_BUDGET_USEC := 1500
const SCAN_ATTEMPTS_PER_PASS := 32
## One allowance across active/resident populations and physics catch-up steps.
static var _creation_frame := -1
static var _frame_creations := 0
static var _frame_attempts := 0
static var _frame_creation_started := 0

var _scenes: Dictionary = {}
var _spawned: Array[Node3D] = []
## Each animal with a clip playing, paired with the player playing it.
var _animated: Array[Array] = []
var _gate: AnimationGate = AnimationGate.new()
var _gate_countdown := 0.0
var _streamed: ContinentChunkStream
var _streamed_samples: Array[Dictionary] = []
var _sample_nodes: Dictionary = {}
var _sample_chunks: Dictionary = {}
var _pending_cells: Dictionary = {}
var _streamed_catalog: Dictionary = {}
var _streamed_space: PhysicsDirectSpaceState3D
var _quality := QUALITY.QUALITY_DEFAULT
var _legacy_samples: Array[Dictionary] = []
var _legacy_cursor := 0
var _legacy_catalog: Dictionary = {}
var _legacy_space: PhysicsDirectSpaceState3D
var _spawn_scan_active := false
var _spawn_scan_again := false
var _spawn_scan_cursor := 0
var _creation_passes := 0
var _creation_max_usec := 0

func populate(manifest: WorldManifest, space: PhysicsDirectSpaceState3D,
		chunk_stream: ContinentChunkStream = null) -> int:
	if chunk_stream != null:
		return _populate_streamed(manifest, space, chunk_stream)
	clear()
	var declared: Variant = manifest.data.get("ambientPopulation")
	if declared is not Dictionary:
		return 0
	var groups: Variant = (declared as Dictionary).get("groups", [])
	if groups is not Array:
		return 0
	_legacy_catalog = _load_catalog()
	_legacy_space = space
	_quality = QUALITY.normalized_quality(LookProfile.quality())
	for raw_group: Variant in groups as Array:
		if raw_group is not Dictionary:
			continue
		var group: Dictionary = raw_group as Dictionary
		var centre: Vector3 = _vector(group.get("center", [0, 0, 0]))
		var radius: float = float(group.get("radius", 6.0))
		var count: int = int(group.get("count", 1))
		var animation: String = str(group.get("animation", "Idle_A"))
		var scale: float = float(group.get("scale", 1.0))
		var rng := RandomNumberGenerator.new()
		rng.seed = int(group.get("seed", 1))
		for index in count:
			var angle := rng.randf() * TAU
			var reach := radius * sqrt(rng.randf())
			var position := Vector3(centre.x + cos(angle) * reach, centre.y,
				centre.z + sin(angle) * reach)
			_legacy_samples.append({"model": str(group.get("model", "")), "position": position,
				"scale": scale * rng.randf_range(0.94, 1.06), "rotation": rng.randf() * TAU,
				"animation": animation, "offset": rng.randf() * 4.0})
	_spawn_legacy_pending()
	set_physics_process(pending_creation_count() > 0)
	# The return remains the count actually built now. Larger declarations
	# continue in bounded passes; callers can inspect pending_creation_count().
	return _spawned.size()

func clear() -> void:
	if is_instance_valid(_streamed):
		_streamed.cell_ready.disconnect(_on_cell_ready)
		_streamed.cell_retiring.disconnect(_on_cell_retiring)
	_streamed = null
	_streamed_samples.clear()
	_sample_nodes.clear()
	_sample_chunks.clear()
	_pending_cells.clear()
	_streamed_catalog.clear()
	_streamed_space = null
	_legacy_samples.clear()
	_legacy_cursor = 0
	_legacy_catalog.clear()
	_legacy_space = null
	_spawn_scan_active = false
	_spawn_scan_again = false
	_spawn_scan_cursor = 0
	_creation_passes = 0
	_creation_max_usec = 0
	set_physics_process(false)
	# Quiesce only the animals being discarded. Forgetting the gate cannot
	# cancel work that was already queued, and must not restore idle callbacks.
	for node: Variant in _spawned:
		if is_instance_valid(node):
			(node as Node3D).process_mode = Node.PROCESS_MODE_DISABLED
	_gate.reset(false)
	for node: Variant in _spawned:
		if is_instance_valid(node):
			node.queue_free()
	_spawned.clear()
	_animated.clear()
	_gate_countdown = 0.0

func _populate_streamed(manifest: WorldManifest, space: PhysicsDirectSpaceState3D,
		chunk_stream: ContinentChunkStream) -> int:
	if _streamed == chunk_stream:
		return _spawned.size() # Adoption keeps the same animals and animation phases.
	clear()
	_streamed = chunk_stream
	_quality = QUALITY.normalized_quality(LookProfile.quality())
	_streamed_space = space
	_streamed_catalog = _load_catalog()
	_streamed.cell_ready.connect(_on_cell_ready)
	_streamed.cell_retiring.connect(_on_cell_retiring)
	var groups: Array = manifest.data.get("ambientPopulation", {}).get("groups", [])
	for group: Dictionary in groups:
		var centre := _vector(group.get("center", [0,0,0]))
		var radius := float(group.get("radius", 6.0))
		var rng := RandomNumberGenerator.new()
		rng.seed = int(group.get("seed", 1))
		for index: int in int(group.get("count", 1)):
			var angle := rng.randf() * TAU
			var reach := radius * sqrt(rng.randf())
			var sample := {"id":_streamed_samples.size(), "model":str(group.get("model", "")),
				"position":Vector3(centre.x + cos(angle) * reach, centre.y, centre.z + sin(angle) * reach),
				"scale":float(group.get("scale", 1.0)) * rng.randf_range(0.94, 1.06),
				"rotation":rng.randf() * TAU, "animation":str(group.get("animation", "Idle_A")),
				"offset":rng.randf() * 4.0}
			_streamed_samples.append(sample)
	for identity: String in _streamed.cells:
		_on_cell_ready(identity, _streamed.cells[identity].root)
	return 0

func _on_cell_ready(identity: String, _imported: Node3D) -> void:
	if _streamed_samples.is_empty():
		return
	# Collision registration completes at the physics boundary after attachment.
	_pending_cells[identity] = Engine.get_physics_frames() + 1
	set_physics_process(true)

func _on_cell_retiring(identity: String, _imported: Node3D) -> void:
	_pending_cells.erase(identity)
	var removed: Array = []
	for sample_id: int in _sample_chunks.keys():
		if str(_sample_chunks[sample_id]) == identity:
			var node: Variant = _sample_nodes.get(sample_id)
			removed.append(node)
			_spawned.erase(node)
			_sample_nodes.erase(sample_id)
			_sample_chunks.erase(sample_id)
	# The chunk owns these nodes and frees them in its bounded retirement pass.
	# Do not independently queue_free descendants while that traversal owns them.
	for node: Variant in removed:
		if is_instance_valid(node):
			(node as Node3D).process_mode = Node.PROCESS_MODE_DISABLED
	var survivors: Array[Array] = []
	for pair: Array in _animated:
		if pair[0] in removed:
			_gate.discard(pair[1])
		else:
			survivors.append(pair)
	_animated = survivors
	_gate_countdown = 0.0
	var used_models: Dictionary = {}
	for sample_id: int in _sample_nodes:
		used_models[str(_streamed_samples[sample_id].model)] = true
	for model: String in _scenes.keys():
		if not used_models.has(model):
			_scenes.erase(model)

func _physics_process(_delta: float) -> void:
	if _legacy_cursor < _legacy_samples.size():
		_spawn_legacy_pending()
	var ready := false
	for identity: String in _pending_cells.keys():
		if Engine.get_physics_frames() >= int(_pending_cells[identity]):
			_pending_cells.erase(identity)
			ready = true
	if ready:
		if _spawn_scan_active:
			_spawn_scan_again = true
		else:
			_spawn_scan_active = true
			_spawn_scan_cursor = 0
	if _spawn_scan_active:
		_spawn_ready_samples()
	if pending_creation_count() == 0:
		set_physics_process(false)

func _spawn_ready_samples() -> void:
	if not is_instance_valid(_streamed) or _streamed_space == null:
		_spawn_scan_active = false
		return
	var began := Time.get_ticks_usec()
	while _spawn_scan_cursor < _streamed_samples.size() and _claim_creation_attempt():
		var sample := _streamed_samples[_spawn_scan_cursor]
		_spawn_scan_cursor += 1
		var identity := int(sample.id)
		if _sample_nodes.has(identity):
			continue
		var position: Vector3 = _streamed.global_transform * (sample.position as Vector3)
		var query := PhysicsRayQueryParameters3D.create(position + Vector3.UP * 200.0,
			position - Vector3.UP * 200.0, NAVIGATION_LAYER | ExteriorRegionStream.PREVIEW_SURFACE_LAYER)
		var hit := _streamed_space.intersect_ray(query)
		var collider: Node = hit.get("collider") as Node
		if collider == null or not _streamed.is_ancestor_of(collider):
			continue # Cold terrain is pending, never a valid fallback animal height.
		var cell := collider
		while cell != _streamed and not cell.has_meta("continent_chunk_id"):
			cell = cell.get_parent()
		if cell == _streamed:
			continue
		var cell_id := str(cell.get_meta("continent_chunk_id"))
		if not _streamed.cells.has(cell_id):
			continue
		var scene := _scene_for(str(sample.model), _streamed_catalog)
		if scene == null:
			continue
		var instance := scene.instantiate() as Node3D
		if instance == null:
			continue
		cell.add_child(instance)
		instance.scale = Vector3.ONE * float(sample.scale)
		instance.rotation.y = float(sample.rotation)
		instance.global_position = hit.position
		QUALITY.apply_actor(instance, _quality)
		var player := _play(instance, str(sample.animation), float(sample.offset))
		if player != null:
			_track_animated(instance, player)
		_spawned.append(instance)
		_sample_nodes[identity] = instance
		_sample_chunks[identity] = cell_id
		_frame_creations += 1
	_note_creation_pass(began)
	if _spawn_scan_cursor >= _streamed_samples.size():
		_spawn_scan_active = _spawn_scan_again
		_spawn_scan_again = false
		_spawn_scan_cursor = 0

func _spawn_legacy_pending() -> void:
	var began := Time.get_ticks_usec()
	while _legacy_cursor < _legacy_samples.size() and _claim_creation_attempt():
		var sample := _legacy_samples[_legacy_cursor]
		_legacy_cursor += 1
		var scene := _scene_for(str(sample.model), _legacy_catalog)
		if scene == null:
			continue
		var instance := scene.instantiate() as Node3D
		if instance == null:
			continue
		add_child(instance)
		instance.scale = Vector3.ONE * float(sample.scale)
		instance.rotation.y = float(sample.rotation)
		instance.global_position = _grounded(sample.position as Vector3, _legacy_space)
		QUALITY.apply_actor(instance, _quality)
		var player := _play(instance, str(sample.animation), float(sample.offset))
		if player != null:
			_track_animated(instance, player)
		_spawned.append(instance)
		_frame_creations += 1
	_note_creation_pass(began)
	if _legacy_cursor >= _legacy_samples.size():
		_legacy_samples.clear()
		_legacy_cursor = 0
		_legacy_catalog.clear()
		_legacy_space = null

func _claim_creation_attempt() -> bool:
	var frame := Engine.get_process_frames()
	if frame != _creation_frame:
		_creation_frame = frame
		_frame_creations = 0
		_frame_attempts = 0
		_frame_creation_started = Time.get_ticks_usec()
	if _frame_creations >= int(CREATIONS_PER_PASS[_quality]) or _frame_attempts >= SCAN_ATTEMPTS_PER_PASS \
			or (_frame_attempts > 0 and Time.get_ticks_usec() - _frame_creation_started >= CREATION_BUDGET_USEC):
		return false
	_frame_attempts += 1
	return true

func _note_creation_pass(began: int) -> void:
	_creation_passes += 1
	_creation_max_usec = maxi(_creation_max_usec, Time.get_ticks_usec() - began)

func pending_creation_count() -> int:
	return maxi(0, _legacy_samples.size() - _legacy_cursor) + _pending_cells.size() \
		+ (maxi(1, _streamed_samples.size() - _spawn_scan_cursor) if _spawn_scan_active else 0)

func creation_status() -> Dictionary:
	return {"pending": pending_creation_count(), "spawned": _spawned.size(),
		"passes": _creation_passes, "maximumPassMicroseconds": _creation_max_usec,
		"quality": QUALITY.quality_name(_quality)}

func _track_animated(animal: Node3D, player: AnimationPlayer) -> void:
	var skeleton := animal as Skeleton3D
	if skeleton == null:
		var skeletons := animal.find_children("*", "Skeleton3D", true, false)
		if not skeletons.is_empty():
			skeleton = skeletons[0] as Skeleton3D
	_animated.append([animal, player, skeleton])
	_gate_countdown = 0.0

func apply_render_quality(level: int) -> void:
	_quality = QUALITY.normalized_quality(level)
	for animal: Node3D in _spawned:
		if is_instance_valid(animal):
			QUALITY.apply_actor(animal, _quality)
	_gate_countdown = 0.0

## Declared scenery animals use a separate animation allowance from replicated
## actors. No populated authored herd is currently approved by the catalog.
## If content is declared later, offscreen model subtrees sleep; visible bodies
## use quality-specific full/half caps, with the rest at quarter rate. The gate
## consumes elapsed time every frame and ranks bodies on a slower clock.
func _process(delta: float) -> void:
	if _quality != LookProfile.quality():
		apply_render_quality(LookProfile.quality())
	if _animated.is_empty():
		return
	_gate.advance(delta)
	_gate_countdown -= delta
	if _gate_countdown > 0.0:
		return
	_gate_countdown = GATE_REFRESH_SECONDS
	var camera := get_viewport().get_camera_3d() if is_inside_tree() else null
	_gate.begin(camera)
	var ranked: Array = []
	for pair: Array in _animated:
		var animal_value: Variant = pair[0]
		var player_value: Variant = pair[1]
		if not is_instance_valid(animal_value) or not is_instance_valid(player_value):
			continue
		var animal: Node3D = animal_value as Node3D
		var tier := _gate.classify(animal.global_position + Vector3.UP,
			VIEW_RADIUS * maxf(animal.global_basis.get_scale().y, 0.1))
		if tier == AnimationGate.Tier.PAUSED:
			_apply_animal_tier(pair, tier)
		else:
			ranked.append([camera.global_position.distance_squared_to(animal.global_position) if camera != null else 0.0,
				pair, tier])
	ranked.sort_custom(func(a: Array, b: Array) -> bool: return a[0] < b[0])
	var full_budget: int = [8, 12, 16][_quality]
	var half_budget: int = [8, 12, 16][_quality]
	for index: int in ranked.size():
		var entry := ranked[index] as Array
		var tier := AnimationGate.Tier.HALF
		if camera == null or (index < full_budget and int(entry[2]) == AnimationGate.Tier.FULL):
			tier = AnimationGate.Tier.FULL
		elif index >= full_budget + half_budget:
			tier = AnimationGate.Tier.QUARTER
		_apply_animal_tier(entry[1] as Array, tier)

func _apply_animal_tier(pair: Array, tier: int) -> void:
	var animal := pair[0] as Node3D
	animal.process_mode = Node.PROCESS_MODE_DISABLED if tier == AnimationGate.Tier.PAUSED else Node.PROCESS_MODE_INHERIT
	_gate.apply(pair[1] as AnimationPlayer, tier, pair[2] as Skeleton3D)

func _grounded(position: Vector3, space: PhysicsDirectSpaceState3D) -> Vector3:
	if space == null:
		return position
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(position.x, position.y + 200.0, position.z),
		Vector3(position.x, position.y - 200.0, position.z), NAVIGATION_LAYER)
	var hit := space.intersect_ray(query)
	var found: Variant = hit.get("position")
	if found is Vector3:
		return found as Vector3
	return position

## Starts the clip and returns the player it runs on, or null when the model
## has nothing to play.
func _play(instance: Node3D, animation: String, offset: float) -> AnimationPlayer:
	var players := instance.find_children("*", "AnimationPlayer", true, false)
	if players.is_empty():
		return null
	var player := players[0] as AnimationPlayer
	if not player.has_animation(animation):
		animation = "Idle_A"
	if not player.has_animation(animation):
		return null
	var clip := player.get_animation(animation)
	if clip.loop_mode != Animation.LOOP_LINEAR:
		# Packed scenes share libraries and animations with actors and other
		# populations. Replace a shallow library copy and only this clip; never
		# mutate the cache-owned resources while making scenery animation loop.
		var separator := animation.find("/")
		var library_name := animation.substr(0, separator) if separator >= 0 else ""
		var clip_name := animation.substr(separator + 1) if separator >= 0 else animation
		var source_library := player.get_animation_library(library_name)
		var library := source_library.duplicate() as AnimationLibrary
		var private_clip := clip.duplicate() as Animation
		private_clip.loop_mode = Animation.LOOP_LINEAR
		library.remove_animation(clip_name)
		library.add_animation(clip_name, private_clip)
		player.remove_animation_library(library_name)
		player.add_animation_library(library_name, library)
		clip = private_clip
	player.play(animation)
	# Offset each animal so a herd does not breathe in lockstep.
	player.seek(fmod(offset, maxf(clip.length, 0.1)), true)
	return player

func _load_catalog() -> Dictionary:
	var file := FileAccess.open(MODEL_CATALOG, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if parsed is not Dictionary:
		return {}
	var models: Variant = (parsed as Dictionary).get("models", {})
	return models as Dictionary if models is Dictionary else {}

func _scene_for(model: String, catalog: Dictionary) -> PackedScene:
	if model.is_empty():
		return null
	var entry: Variant = catalog.get(model)
	if entry is not Dictionary:
		return null
	var path: String = str((entry as Dictionary).get("scene", ""))
	if path.is_empty() or ARCHIVED_MODELS.is_retired_path(path):
		return null
	if _scenes.has(model):
		return _scenes[model] as PackedScene
	var packed: PackedScene
	var extension := path.get_extension().to_lower()
	if extension == "glb" or extension == "gltf":
		# Shipping native assets are loose files, without imported PCK remaps.
		# Share actor parsing, imported-scene preference and retired filtering.
		# Both creation callers claim their soft budget before reaching here.
		packed = SCENE_CACHE.packed_scene(path)
	elif ResourceLoader.exists(path, "PackedScene"):
		packed = ResourceLoader.load(path, "PackedScene", ResourceLoader.CACHE_MODE_REUSE) as PackedScene
	if packed == null:
		push_warning("ambient population: %s could not load as a PackedScene" % path)
		return null
	_scenes[model] = packed
	return packed

static func _vector(value: Variant) -> Vector3:
	if value is Array and (value as Array).size() >= 3:
		var values: Array = value as Array
		return Vector3(float(values[0]), float(values[1]), float(values[2]))
	return Vector3.ZERO
