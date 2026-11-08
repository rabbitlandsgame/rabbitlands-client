extends Node3D
## A read-only remote film in the same rendered World3D. Its isolated ground
## layer and private cast never participate in gameplay picking or actor tables.
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const VramTextures := preload("res://src/world/vram_textures.gd")
const MapMeshExtension := preload("res://src/world/map_mesh_extension.gd")
const GROUND_LAYER := 1 << 29
const LOAD_LIMIT := 40.0
const ASSET_POLL_MSEC := 250
const ASSET_WAIT_MSEC := 300000
const VISUAL_ID_BASE := -1000000
var manifest: WorldManifest
var adapter: CoordinateAdapter
var focus_world := Vector3.ZERO
var map_lights: Node3D
var presenting := false
var _registry: Dictionary = {}
var _factory: Callable
var _asset_resolver: Callable
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
var _load_started := false
var _asset_owner := ""
var _asset_generation := 0
var _asset_groups: Array = []
var _asset_required: Dictionary = {}
var _asset_admitted := false
var _asset_check_at := 0
var _asset_progress := -1
var _asset_progress_at := 0
var _asset_worker: Thread
var _web_generation := 0
var _web_pending := false

func _ready() -> void:
	top_level = true
	global_transform = Transform3D.IDENTITY

func configure(registry: Dictionary, visual_factory: Callable, asset_resolver := Callable()) -> void:
	_registry = registry
	_factory = visual_factory
	_asset_resolver = asset_resolver

static func requested(snapshot: Dictionary) -> bool:
	var scene: Dictionary = snapshot.get("scene", {})
	var cutaway: Dictionary = scene.get("cutaway", {})
	return str(snapshot.get("kind", "")) == "rescue" and not str(snapshot.get("run_id", "")).is_empty() \
		and str(scene.get("id", "")) == "measure.rescue.shadow" \
		and MapRegistry.normalize_server_map_id(str(cutaway.get("map", ""))) == "landfall_insides" \
		and not (cutaway.get("actors", {}) as Dictionary).is_empty()

func prepare(snapshot: Dictionary, current_map: String, delta := 1.0 / 60.0) -> void:
	ContinentChunkStream.reap_orphans()
	var scene: Dictionary = snapshot.get("scene", {})
	var warming := str(scene.get("id", "")) == "measure.rescue.resolved" and scene.has("preload_cutaway")
	if (not requested(snapshot) and not warming) or MapRegistry.normalize_server_map_id(str(snapshot.get("map", ""))) \
			!= MapRegistry.normalize_server_map_id(current_map):
		clear()
		return
	var source: Dictionary = scene.preload_cutaway if warming else scene.cutaway
	var identity := str(snapshot.run_id) + ":" + MapRegistry.normalize_server_map_id(current_map) + ":" + str(source.map)
	if identity != _identity:
		clear()
		_identity = identity
		_source = source.duplicate(true)
		if _uses_browser_assets(): _collect_browser_assets()
	if not _load_started and _failed.is_empty():
		if _uses_browser_assets() and not _admit_browser_assets(): return
		_load_started = true
		_begin()
	_elapsed += maxf(0.0, delta)
	_poll()
	if not _loaded_ready and _failed.is_empty() and _elapsed >= LOAD_LIMIT:
		_fail("remote_ground_timeout")
	if _failed.is_empty() and manifest != null:
		_build_cast()

func _uses_browser_assets() -> bool:
	return OS.has_feature("web")

## Resolve once per preparation, with the same model policy as the factory.
## Downloaded archives remain on disk; only this room/cast is admitted to MEMFS.
func _collect_browser_assets() -> void:
	_asset_groups = WebPrototype.map_groups(str(_source.map)).duplicate()
	if _asset_groups.is_empty() or not _asset_resolver.is_valid():
		_fail("remote_browser_assets_unavailable")
		return
	for role: String in _source.actors:
		var resolved: Variant = _asset_resolver.call(_source.actors[role])
		if not resolved is Array or resolved.is_empty():
			_fail("remote_browser_cast_assets_unavailable: " + role)
			return
		for group: Variant in resolved:
			if not _asset_groups.has(group): _asset_groups.append(group)
	var catalog: Dictionary = WebPrototype.configuration().get("groups", {})
	var pending := _asset_groups.duplicate()
	while not pending.is_empty():
		var group := str(pending.pop_back())
		if _asset_required.has(group): continue
		if not catalog.get(group) is Dictionary:
			_fail("remote_browser_asset_group_unavailable: " + group)
			return
		_asset_required[group] = true
		pending.append_array(catalog[group].get("dependencies", []))
	_asset_generation += 1
	_asset_owner = "campaign-cutaway:%s:%s" % [get_instance_id(), _asset_generation]
	_asset_progress_at = Time.get_ticks_msec()

func _request_browser_assets() -> bool:
	return WebPrototype.ensure_groups(_asset_groups, _asset_owner, 1)

func _browser_asset_state() -> Dictionary:
	return WebPrototype.asset_snapshot()

func _browser_asset_release() -> Callable:
	return WebPrototype.retire_groups

func _retry_browser_asset_groups() -> int:
	return WebPrototype.retry_failed()

## Only the player's explicit Retry action resets sticky download failures.
func retry_browser_assets() -> void:
	if _uses_browser_assets() and _failed.begins_with("remote_browser_asset_"):
		_retry_browser_asset_groups()

func _admit_browser_assets() -> bool:
	var now := Time.get_ticks_msec()
	if now < _asset_check_at: return false
	_asset_check_at = now + ASSET_POLL_MSEC
	if _request_browser_assets():
		_asset_admitted = true
		return true
	var state := _browser_asset_state()
	if state.is_empty():
		_fail("remote_browser_asset_service_unavailable")
		return false
	for group: Variant in state.get("failed_groups", []):
		if _asset_required.has(str(group)):
			_fail("remote_browser_asset_download: " + str(state.get("error", "download_failed")))
			return false
	var progress := int(state.get("completed_archives", 0))
	if progress != _asset_progress:
		_asset_progress = progress
		_asset_progress_at = now
	if now - _asset_progress_at >= ASSET_WAIT_MSEC:
		_fail("remote_browser_asset_timeout")
	return false

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
	if OS.has_feature("web"):
		# Match the streamed-world browser path: WebGL materialization stays
		# on Main, and a cancelled deferred load never publishes another room.
		_web_pending = true
		_prepare_web_world.call_deferred(ProjectSettings.globalize_path(path), _web_generation)
		return
	_thread = Thread.new()
	if not _asset_owner.is_empty(): _asset_worker = _thread
	var error := _thread.start(WorldLoader.prepare_detached.bind(ProjectSettings.globalize_path(path),
		MapSceneCache.is_enabled(), PackedStringArray(), Vector3.INF, true))
	if error != OK:
		_thread = null
		_fail("remote_worker_start: " + error_string(error))

func _prepare_web_world(path: String, generation: int) -> void:
	if generation != _web_generation or not _web_pending: return
	var builder := WorldLoader.prepare_detached(path, MapSceneCache.is_enabled(),
		PackedStringArray(), Vector3.INF, true)
	if generation != _web_generation or not _web_pending:
		if builder != null: builder.free()
		return
	_web_pending = false
	_adopt_builder(builder)

func _poll() -> void:
	if _thread == null or _thread.is_alive(): return
	var builder := _thread.wait_to_finish() as WorldLoader
	_thread = null
	_adopt_builder(builder)

func _adopt_builder(builder: WorldLoader) -> void:
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
	_web_generation += 1
	_web_pending = false
	_release_asset_owner()
	_failed = reason
	_loaded_ready = false
	set_presenting(false)
	if _thread != null:
		ContinentChunkStream._orphan(_thread,{"id":"campaign_cutaway","estimatedResidentBytes":0})
		_thread = null

func clear() -> void:
	_web_generation += 1
	_web_pending = false
	_release_asset_owner()
	_asset_groups.clear()
	_asset_required.clear()
	_asset_admitted = false
	_asset_check_at = 0
	_asset_progress = -1
	_load_started = false
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

func _release_asset_owner() -> void:
	if not _asset_owner.is_empty():
		var release := _browser_asset_release()
		if _asset_worker != null and _asset_worker.is_alive():
			_release_after_worker(_asset_worker, _asset_owner, release)
		elif release.is_valid(): release.call(_asset_owner)
	_asset_owner = ""
	_asset_worker = null

## The callback belongs to the asset service, never to this retiring module.
## The ordinary orphan reaper owns joining/freeing the worker's result.
static func _release_after_worker(worker: Thread, owner: String, release: Callable) -> void:
	var tree := Engine.get_main_loop() as SceneTree
	while worker.is_alive():
		if tree == null or not is_instance_valid(tree.root): return
		await tree.create_timer(0.25).timeout
	if release.is_valid(): release.call(owner)

func status() -> Dictionary:
	return {"ready":_loaded_ready,"loading":_thread != null or _web_pending,"error":_failed,"elapsed":_elapsed,
		"identity":_identity,"presenting":presenting,"cast":_nodes.size(),
		"asset_owner":_asset_owner,"asset_groups":_asset_groups.duplicate(),"asset_admitted":_asset_admitted,
		"asset_waiting":not _asset_owner.is_empty() and not _asset_admitted and _failed.is_empty()}

func is_idle() -> bool:
	return _thread == null and not _web_pending and ContinentChunkStream.reap_orphans() == 0

func _exit_tree() -> void: clear()
