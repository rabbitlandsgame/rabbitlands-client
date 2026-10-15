extends RefCounted

## Fade state belongs to actual scenery roots, not the authoritative map ID.
## Reconciliation visits only the active root and the bounded resident list;
## each root's mesh index is built once and survives promotion and rebasing.
const FadeScript := preload("res://src/world/occluder_fade.gd")

var _worlds: Dictionary = {}
var _enabled := false

func sync_worlds(manifest: WorldManifest, imported_world: Variant, residents: Dictionary,
		dynamic_roots: Array = []) -> int:
	var wanted: Dictionary = {}
	_include(wanted, imported_world, manifest)
	for resident: Dictionary in residents.values():
		_include(wanted, resident.get("root"), resident.get("manifest") as WorldManifest)
	for dynamic_root: Variant in dynamic_roots:
		_include(wanted, dynamic_root, manifest)
	for identity: int in _worlds.keys():
		if not wanted.has(identity):
			_remove(identity)
	var count := 0
	for identity: int in wanted:
		if not _worlds.has(identity):
			var entry: Dictionary = wanted[identity]
			var fade: RefCounted = FadeScript.new()
			fade.configure(entry.manifest, entry.root)
			fade.set_enabled(_enabled)
			_worlds[identity] = {"root": entry.root, "fade": fade}
		count += int(_worlds[identity].fade.indexed_count())
	return count

func _include(wanted: Dictionary, imported_world: Variant, manifest: WorldManifest) -> void:
	if is_instance_valid(imported_world) and imported_world is Node3D and imported_world.is_inside_tree() and not imported_world.is_queued_for_deletion():
		if imported_world is ContinentChunkStream:
			# Each arriving/retiring cell owns its own stable fade index. Indexing
			# the territory container once would miss all subsequently loaded trees.
			for cell: Dictionary in imported_world.cells.values():
				_include(wanted, cell.root, cell.manifest)
			return
		wanted[imported_world.get_instance_id()] = {"root": imported_world, "manifest": manifest}

func _remove(identity: int) -> void:
	(_worlds[identity].fade as RefCounted).reset()
	_worlds.erase(identity)

func reset() -> void:
	for identity: int in _worlds.keys():
		_remove(identity)

## Every root's faded meshes back to rest at once, the indexes kept (see
## OccluderFade.release).
func release() -> void:
	for entry: Dictionary in _worlds.values():
		entry.fade.release()

func is_enabled() -> bool:
	return _enabled

func is_active() -> bool:
	for entry: Dictionary in _worlds.values():
		if entry.fade.is_active():
			return true
	return false

func set_enabled(enabled: bool) -> void:
	_enabled = enabled
	for entry: Dictionary in _worlds.values():
		entry.fade.set_enabled(enabled)

func update(delta: float, camera: Camera3D, player: Node3D) -> void:
	for identity: int in _worlds.keys():
		var entry: Dictionary = _worlds[identity]
		if not is_instance_valid(entry.root) or not entry.root.is_inside_tree() or entry.root.is_queued_for_deletion():
			_remove(identity)
		else:
			entry.fade.update(delta, camera, player)
