extends RefCounted
## Loads the ground around a known future arrival on another map - where the
## server says a respawn will land (the death state's `destination`) - in a
## hidden stream, the way the new-character intro preloads Landfall, so the
## map change adopts it instead of loading while the player waits.
##
## Only a streamed territory is prewarmed: a whole map's build is one
## synchronous step and stays with the ordinary load behind the curtain. The
## hidden stream's collision is off until it is adopted: its cells sit at
## territory-local coordinates in the shared world, and their bodies would
## otherwise answer the grounding rays of the map in play.

var map_id := ""
var tile := Vector2i(-1, -1)
var _loader: WorldLoader
var _stream: ContinentChunkStream
## manifest path -> whether it streams; read once per map.
var _streams: Dictionary = {}

func prewarm(entry: Dictionary, destination_map: String, destination_tile: Vector2i, parent: Node3D) -> void:
	if is_instance_valid(_loader) and map_id == destination_map and tile == destination_tile:
		return
	discard()
	var path := ProjectSettings.globalize_path(str(entry.get("manifest", "")))
	if path.is_empty() or not streams(path):
		return
	var loader := WorldLoader.new()
	loader.name = "RespawnPreload"
	parent.add_child(loader)
	loader.hide()
	loader.load_world(path, Vector3.INF, true)
	var stream := loader.world_root as ContinentChunkStream
	if stream == null or loader.coordinate_adapter == null:
		loader.queue_free()
		return
	stream.set_physics_mode(false, false)
	stream.preload_views(PackedVector3Array([
		loader.coordinate_adapter.tile_center(destination_tile.x, destination_tile.y)]),
		ContinentChunkStream.ARRIVAL_FRAME_METRES)
	_loader = loader
	_stream = stream
	map_id = destination_map
	tile = destination_tile

## The prewarmed world for WorldLoader.adopt_world when `destination_map` is
## the one prewarmed, collision restored and ordinary selection resumed; empty
## (and the prewarm dropped) otherwise.
func take(destination_map: String) -> Dictionary:
	if destination_map != map_id or not is_instance_valid(_loader) or _stream == null:
		discard()
		return {}
	var stream := _stream
	var resident := _loader.release_world()
	_loader.queue_free()
	_loader = null
	_stream = null
	map_id = ""
	tile = Vector2i(-1, -1)
	ExteriorRegionStream._set_collision(stream, true)
	stream.release_views()
	stream.show()
	return resident

func discard() -> void:
	if is_instance_valid(_loader):
		_loader.queue_free() # Stream exit orphans live imports without joining them.
	_loader = null
	_stream = null
	map_id = ""
	tile = Vector2i(-1, -1)

func pending() -> bool:
	return is_instance_valid(_loader)

func is_ready() -> bool:
	return _stream != null and _stream.views_ready()

## Whether the manifest at `path` streams its ground in chunks. A whole map is
## built synchronously on load (WorldLoader.load_world).
func streams(path: String) -> bool:
	if not _streams.has(path):
		_streams[path] = FileAccess.file_exists(path) \
			and FileAccess.get_file_as_string(path).contains("\"streamingChunks\"")
	return bool(_streams[path])
