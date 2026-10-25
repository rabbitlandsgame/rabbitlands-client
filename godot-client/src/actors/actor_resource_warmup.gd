extends RefCounted
## One worker prepares cold creature geometry and immutable retargeted clips.
## Actors remain ordinary deferred nodes until publication on main. Workers
## never inspect live nodes, mutate session caches, or attach anything to a tree.
var _queue: Array[Dictionary] = []
var _known: Dictionary = {}
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
	# A loader can need the rendering server. Never join a live worker on main:
	# cancel publication, and keep serving frames until is_idle() before exit.
	_discard_active = _thread != null
	poll()

func is_idle() -> bool:
	poll()
	return _thread == null and _queue.is_empty()

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
	var source: Node = NativeAnimationImporter._parse_library(source_path, false) as Node
	if source != null and not skeletons.is_empty():
		var resolver := AnimationResolver.new(animation)
		library = NativeAnimationImporter.prepare_detached(owner, source, source_path,
			skeletons[0] as Skeleton3D, config.get("boneAliases", {}),
			resolver.required_clips(), resolver.looping_clips)
	if source != null:
		source.free()
	owner.free()
	return {"scenes": scenes, "library": library}
