extends RefCounted
## One worker prepares cold creature geometry and immutable retargeted clips.
## Actors remain ordinary deferred nodes until publication on main. Workers
## never inspect live nodes, mutate session caches, or attach anything to a tree.
var _queue: Array[Dictionary] = []
var _known: Dictionary = {}
var _known_sources: Dictionary = {}
var _thread: Thread
var _active := ""
var _discard_active := false

func request(config: Dictionary, animation: Dictionary) -> bool:
	poll()
	var key := JSON.stringify([config, animation])
	if _known.has(key):
		return bool(_known[key])
	# Equipment libraries have external textures with main-thread readback
	# semantics. Their existing path is deliberately outside this creature job.
	var path := str(config.get("scene", ""))
	if not path.begins_with("res://assets/actors/native/creatures/") \
			or bool(config.get("retired", false)) \
			or NativeAnimationImporter.ArchivedModelPolicy.is_retired_path(path) \
			or NativeAnimationImporter.PreparedContent.selected_mode() != "raw":
		return true
	NativeAnimationImporter.GltfQuantization.ensure_registered()
	NativeAnimationImporter.VramTextures.ensure_registered()
	NativeAnimationImporter.MapMeshExtension.ensure_registered()
	_known[key] = false
	if OS.has_feature("web"):
		_known_sources[key] = [GlbSceneCache._file_key(path),
			GlbSceneCache._file_key(str(config.get("animationLibrary", "")))]
	_queue.append({"key": key, "config": config.duplicate(true), "animation": animation.duplicate(true)})
	poll()
	return false

func poll() -> void:
	if _thread != null and not _thread.is_alive():
		var result: Dictionary = _thread.wait_to_finish()
		_thread = null
		if not _discard_active:
			GlbSceneCache.install_prepared(result.get("scenes", {}))
			NativeAnimationImporter.install_prepared(result.get("library", {}))
			_known[_active] = true # Failed preparation uses the normal fallback.
		_discard_active = false
		_active = ""
	if _thread == null and not _queue.is_empty():
		var job: Dictionary = _queue.pop_front()
		_active = str(job.key)
		_thread = Thread.new()
		if _thread.start(_prepare.bind(job.config, job.animation)) != OK:
			_thread = null
			_known[_active] = true
			_active = ""

func clear() -> void:
	_queue.clear()
	_known.clear()
	_known_sources.clear()
	# A loader can need the rendering server. Never join a live worker on main:
	# cancel publication, and keep serving frames until is_idle() before exit.
	_discard_active = _thread != null
	poll()

func is_idle() -> bool:
	poll()
	return _thread == null and _queue.is_empty()

## Keep readiness coherent with the browser's raw-file/template retirement.
## An active job finishes privately and discards its result without joining.
func invalidate_sources(paths: PackedStringArray) -> void:
	var wanted := {}
	for path: String in paths: wanted[GlbSceneCache._file_key(path)] = true
	var invalid := {}
	for key: String in _known_sources:
		for source: String in _known_sources[key]:
			if wanted.has(source):
				invalid[key] = true
				break
	if invalid.is_empty(): return
	for key: String in invalid:
		_known.erase(key)
		_known_sources.erase(key)
		if key == _active: _discard_active = true
	_queue.assign(_queue.filter(func(job: Dictionary) -> bool: return not invalid.has(str(job.key))))

static func _prepare(config: Dictionary, animation: Dictionary) -> Dictionary:
	var path := ProjectSettings.globalize_path(str(config.scene))
	var scenes := GlbSceneCache.prepare(PackedStringArray([path]))
	var packed: PackedScene = scenes.get(path) as PackedScene
	if packed == null:
		return {"scenes": scenes}
	var owner := Node3D.new()
	var model := packed.instantiate()
	model.name = "NativeModel"
	owner.add_child(model)
	var skeletons := model.find_children("*", "Skeleton3D", true, false)
	var library := {}
	var source_path := ProjectSettings.globalize_path(str(config.get("animationLibrary", "")))
	# Creatures name their own GLB as their animation library, and the scene just
	# prepared is the very parse _parse_library would repeat: its instance is the
	# clip source. A second parse would decode and upload every texture and mesh
	# again only to free them.
	var shared := NativeAnimationImporter.is_runtime_parse_of(packed, path, source_path)
	var source: Node = model if shared else NativeAnimationImporter._parse_library(source_path, false) as Node
	if source != null and not skeletons.is_empty():
		var resolver := AnimationResolver.new(animation)
		library = NativeAnimationImporter.prepare_detached(owner, source, source_path,
			skeletons[0] as Skeleton3D, config.get("boneAliases", {}),
			resolver.required_clips(), resolver.looping_clips)
	if source != null and not shared:
		source.free()
	owner.free()
	return {"scenes": scenes, "library": library}
