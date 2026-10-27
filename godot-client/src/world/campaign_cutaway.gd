extends Node3D
## A read-only remote film in the same rendered World3D. Its isolated ground
## layer and private cast never participate in gameplay picking or actor tables.
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const VramTextures := preload("res://src/world/vram_textures.gd")
const MapMeshExtension := preload("res://src/world/map_mesh_extension.gd")
const GROUND_LAYER := 1 << 29
const LOAD_LIMIT := 40.0
const VISUAL_ID_BASE := -1000000
var manifest: WorldManifest
var adapter: CoordinateAdapter
var focus_world := Vector3.ZERO
var map_lights: Node3D
var presenting := false
var _registry: Dictionary = {}
var _factory: Callable
var _identity := ""
var _source: Dictionary = {}
var _thread: Thread
var _loader: WorldLoader
var _cast_root: Node3D
var _nodes: Dictionary = {}
var _dtos: Dictionary = {}
var _bindings: Dictionary = {}
var _loaded_ready := false
var _failed := ""
var _elapsed := 0.0
var _sections := SecretSections.new()

func _ready() -> void:
	top_level = true
	global_transform = Transform3D.IDENTITY

func configure(registry: Dictionary, visual_factory: Callable) -> void:
	_registry = registry
	_factory = visual_factory

static func requested(snapshot: Dictionary) -> bool:
	var scene: Dictionary = snapshot.get("scene", {})
	var cutaway: Dictionary = scene.get("cutaway", {})
	return str(snapshot.get("kind", "")) == "rescue" and not str(snapshot.get("run_id", "")).is_empty() \
		and str(scene.get("id", "")) == "measure.rescue.shadow" \
		and MapRegistry.normalize_server_map_id(str(cutaway.get("map", ""))) == "landfall_insides" \
		and not (cutaway.get("actors", {}) as Dictionary).is_empty()

func prepare(snapshot: Dictionary, current_map: String, delta := 1.0 / 60.0) -> void:
	ContinentChunkStream.reap_orphans()
	if not requested(snapshot) or MapRegistry.normalize_server_map_id(str(snapshot.get("map", ""))) \
			!= MapRegistry.normalize_server_map_id(current_map):
		clear()
		return
	var source: Dictionary = snapshot.scene.cutaway
	var identity := str(snapshot.run_id) + ":" + MapRegistry.normalize_server_map_id(current_map) + ":" + str(source.map)
	if identity != _identity:
		clear()
		_identity = identity
		_source = source.duplicate(true)
		_begin()
	_elapsed += maxf(0.0, delta)
	_poll()
	if not _loaded_ready and _failed.is_empty() and _elapsed >= LOAD_LIMIT:
		_fail("remote_ground_timeout")
	if _failed.is_empty() and manifest != null:
		_build_cast()

func _begin() -> void:
	var entry := MapRegistry.resolve(_registry, str(_source.map))
	var path := str(entry.get("manifest", ""))
	if path.is_empty() or not FileAccess.file_exists(path):
		_fail("remote_manifest_unavailable")
		return
	adapter = CoordinateAdapter.new(entry.get("coordinateTransform", {}))
	for role: String in _source.actors:
		var id := VISUAL_ID_BASE-_bindings.size()
		var dto: Dictionary = (_source.actors[role] as Dictionary).duplicate(true)
		dto.actor_id = id
		if dto.get("death_presentation") is Dictionary:
			dto.death_presentation.actor_id = id
		_bindings[role] = id
		_dtos[id] = dto
	# Registration happens on the main thread before the standard detached loader.
	if not GltfQuantization.ensure_registered() or not VramTextures.ensure_registered() or not MapMeshExtension.ensure_registered():
		_fail("remote_import_registration")
		return
	_thread = Thread.new()
	var error := _thread.start(WorldLoader.prepare_detached.bind(ProjectSettings.globalize_path(path),
		MapSceneCache.is_enabled(), PackedStringArray(), Vector3.INF, true))
	if error != OK:
		_thread = null
		_fail("remote_worker_start: " + error_string(error))

func _poll() -> void:
	if _thread == null or _thread.is_alive(): return
	var builder := _thread.wait_to_finish() as WorldLoader
	_thread = null
	if builder == null:
		_fail("remote_import_failed")
		return
	var resident := builder.release_world()
	builder.free()
	if resident.get("root") == null or resident.get("manifest") == null:
		_fail("remote_import_failed")
		return
	_loader = WorldLoader.new()
	_loader.name = "RemoteCampaignWorld"
	add_child(_loader)
	_loader.hide()
	_loader.adopt_world(resident)
	manifest = _loader.manifest
	adapter = manifest.coordinate_adapter()
	_isolate_tree(_loader.world_root)
	if _loader.world_root is ContinentChunkStream:
		var stream := _loader.world_root as ContinentChunkStream
		stream.cell_ready.connect(func(_id: String, imported: Node3D) -> void: _isolate_tree(imported))
		var tile: Array = _source.get("anchors", {}).get("boss_body", [])
		if tile.size() == 2:
			stream.preload_views(PackedVector3Array([adapter.tile_center(int(tile[0]),int(tile[1]))]),36.0)
	map_lights = Node3D.new()
	map_lights.name = "RemoteMapLights"
	add_child(map_lights)
	LightMarkerBinder.apply(manifest,map_lights)
	map_lights.hide()
	var focus_tile: Array = _source.get("anchors", {}).get("boss_body", [])
	if focus_tile.size() == 2:
		focus_world = adapter.tile_center(int(focus_tile[0]),int(focus_tile[1]))
		_sections.configure(manifest,self)
		_sections.update(focus_world,true)
	_cast_root = Node3D.new()
	_cast_root.name = "RemoteCampaignCast"
	add_child(_cast_root)
	_cast_root.hide()

static func _isolate_tree(root: Node) -> void:
	if not is_instance_valid(root): return
	var pending: Array[Node] = [root]
	while not pending.is_empty():
		var node := pending.pop_back() as Node
		pending.append_array(node.get_children())
		if node is CollisionObject3D:
			var body := node as CollisionObject3D
			body.collision_layer = GROUND_LAYER if (body.collision_layer & (WorldLoader.NAVIGATION_SURFACE_LAYER | GROUND_LAYER)) != 0 else 0
			body.collision_mask = 0
			body.force_update_transform()

func surface_height(point: Vector3) -> float:
	if not is_inside_tree() or get_world_3d() == null or not point.is_finite(): return NAN
	var query := PhysicsRayQueryParameters3D.create(point+Vector3.UP*200,
		point+Vector3.DOWN*1800,GROUND_LAYER)
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	return (hit.position as Vector3).y+0.025 if hit.get("position") is Vector3 else NAN

func _build_cast() -> void:
	if adapter == null or not is_instance_valid(_cast_root) or not _factory.is_valid(): return
	var tile: Array = _source.get("anchors", {}).get("boss_body", [])
	if tile.size() != 2:
		_fail("remote_boss_anchor_missing")
		return
	focus_world = adapter.tile_center(int(tile[0]),int(tile[1]))
	var ground := surface_height(focus_world)
	if not is_finite(ground): return
	focus_world.y = ground
	for role: String in _source.actors:
		var id := int(_bindings[role])
		if _nodes.has(id): continue
		var dto: Dictionary = _dtos[id]
		if not dto.has("x") or not dto.has("y"): continue
		if not is_finite(surface_height(adapter.tile_center(int(dto.x),int(dto.y)))): return
		var visual: Variant = _factory.call(dto.duplicate(true),_cast_root,adapter,surface_height)
		if not is_instance_valid(visual) or not visual is Node3D:
			_fail("remote_actor_unavailable: "+role)
			return
		var node := visual as Node3D
		if node is CollisionObject3D:
			(node as CollisionObject3D).collision_layer = 0
			(node as CollisionObject3D).collision_mask = 0
		_nodes[id] = node
	_loaded_ready = not _bindings.is_empty() and _nodes.size() == _bindings.size()

## All rewriting is confined to this copy. The authenticated map, real local
## actor and rig remain outdoors; only the film's cast and anchors are remote.
func view_context(snapshot: Dictionary, live_nodes: Dictionary, live_dtos: Dictionary,
		normal_adapter: CoordinateAdapter, normal_surface: Callable, replaying := false) -> Dictionary:
	var remote := requested(snapshot)
	var result := {"snapshot":snapshot,"nodes":live_nodes,"dtos":live_dtos,
		"adapter":normal_adapter,"surface":normal_surface,"ready":true,"remote":remote}
	if not remote: return result
	result.ready = _loaded_ready
	var proxy := snapshot.duplicate(true)
	proxy.anchors = {}
	proxy.scene.anchors = (_source.get("anchors", {}) as Dictionary).duplicate(true)
	proxy.scene.actors = (proxy.scene.get("actors", {}) as Dictionary).duplicate(true)
	proxy.scene.actors.merge(_bindings,true)
	if _bindings.has("goblin_boss"):
		proxy.scene.corpse_template = (_dtos[_bindings.goblin_boss] as Dictionary).duplicate(true)
	var nodes := live_nodes.duplicate()
	# Replay's own scoped actor cache reconstructs fresh undissolved bodies.
	# Never show the base cast alongside those clones.
	if not replaying: nodes.merge(_nodes,true)
	var dtos := live_dtos.duplicate()
	dtos.merge(_dtos,true)
	result.merge({"snapshot":proxy,"nodes":nodes,"dtos":dtos,"adapter":adapter,"surface":surface_height},true)
	return result

func set_presenting(value: bool, show_native_cast := true) -> void:
	presenting = value and _loaded_ready
	if is_instance_valid(_loader): _loader.visible = presenting
	if is_instance_valid(map_lights): map_lights.visible = presenting
	if is_instance_valid(_cast_root):
		_cast_root.visible = presenting and show_native_cast
		_cast_root.process_mode = Node.PROCESS_MODE_INHERIT if _cast_root.visible else Node.PROCESS_MODE_DISABLED

func _fail(reason: String) -> void:
	_failed = reason
	_loaded_ready = false
	set_presenting(false)
	if _thread != null:
		ContinentChunkStream._orphan(_thread,{"id":"campaign_cutaway","estimatedResidentBytes":0})
		_thread = null

func clear() -> void:
	if _thread != null:
		ContinentChunkStream._orphan(_thread,{"id":"campaign_cutaway","estimatedResidentBytes":0})
		_thread = null
	set_presenting(false)
	for node: Node in [_loader,_cast_root,map_lights]:
		if is_instance_valid(node): node.queue_free()
	_loader = null
	_cast_root = null
	map_lights = null
	manifest = null
	adapter = null
	_sections.reset()
	_nodes.clear()
	_dtos.clear()
	_bindings.clear()
	_identity = ""
	_source.clear()
	_loaded_ready = false
	_failed = ""
	_elapsed = 0.0

func status() -> Dictionary:
	return {"ready":_loaded_ready,"loading":_thread != null,"error":_failed,"elapsed":_elapsed,
		"identity":_identity,"presenting":presenting,"cast":_nodes.size()}

func is_idle() -> bool:
	return _thread == null and ContinentChunkStream.reap_orphans() == 0

func _exit_tree() -> void: clear()
