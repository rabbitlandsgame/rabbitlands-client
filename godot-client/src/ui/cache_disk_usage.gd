extends RefCounted
## Read-only disk inventory for the settings window. Keep the caches' own
## ownership filters, but allow closing the window's owner to stop the scan
## between files instead of waiting for every historical cache generation.

const MapCache := preload("res://src/world/map_scene_cache.gd")
const GeometryCache := preload("res://src/world/map_geometry_cache.gd")
const CollisionCache := preload("res://src/world/map_collision_cache.gd")
const PavingCache := preload("res://src/world/map_paving_cache.gd")

var _mutex := Mutex.new()
var _cancelled := false

func cancel() -> void:
	_mutex.lock()
	_cancelled = true
	_mutex.unlock()

func _is_cancelled() -> bool:
	_mutex.lock()
	var result := _cancelled
	_mutex.unlock()
	return result

func measure() -> Dictionary:
	var bytes := 0
	for list_files: Callable in [MapCache.entries, GeometryCache._disk_files,
			CollisionCache._disk_files, PavingCache._disk_files]:
		if _is_cancelled():
			return {"cancelled": true, "bytes": bytes}
		for path: String in list_files.call():
			if _is_cancelled():
				return {"cancelled": true, "bytes": bytes}
			var file := FileAccess.open(path, FileAccess.READ)
			if file != null:
				bytes += file.get_length()
				file.close()
	return {"cancelled": false, "bytes": bytes}
