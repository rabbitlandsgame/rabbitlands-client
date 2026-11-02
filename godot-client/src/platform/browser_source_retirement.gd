extends RefCounted
## Separate raw-file eviction from bounded retirement of parsed templates.
## Live instances retain their resources; running workers are never joined.
const SLICE_USEC := 2000
var pending: Dictionary = {}
var warmup: RefCounted

func _init(actor_warmup: RefCounted = null) -> void:
	warmup = actor_warmup

func enqueue(paths: PackedStringArray) -> void:
	if warmup != null: warmup.call("invalidate_sources", paths)
	for path: String in paths:
		if path.get_extension().to_lower() in ["glb", "gltf"]: pending[path] = true

func advance() -> void:
	if pending.is_empty(): return
	var started := Time.get_ticks_usec()
	for path: String in pending.keys():
		var sources := PackedStringArray([path])
		GlbSceneCache.release_sources(sources)
		if NativeAnimationImporter.release_sources(sources): pending.erase(path)
		if Time.get_ticks_usec() - started >= SLICE_USEC: break
