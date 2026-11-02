extends SceneTree
## Exercise browser scheduling on native too, using injected metadata-only
## builders: main-thread construction, no synchronous prime, and cancellation.
const Park := preload("res://src/world/world_park.gd")

class Stream extends ContinentChunkStream:
	var primed := false
	func prime(_position: Vector3) -> void: primed = true

class Region extends ExteriorRegionStream:
	func _nearby(_map_id: String) -> bool: return true

var calls := 0
var caller := -1
var last_stream: Stream

func _initialize() -> void: _run.call_deferred()

func _builder(_path: String) -> WorldLoader:
	calls += 1
	caller = OS.get_thread_caller_id()
	var loader := WorldLoader.new()
	loader.manifest = WorldManifest.new()
	loader.manifest.data = {"asset":{"id":"neighbour"}, "spawnPoints":[{"position":[1,2,3]}]}
	last_stream = Stream.new()
	last_stream.set_process(false)
	loader.world_root = last_stream
	loader.add_child(last_stream)
	return loader

func _region() -> Region:
	var region := Region.new()
	region._browser_background = true
	region._prepare_browser_function = _builder
	region.active_map = "origin"
	root.add_child(region)
	region.set_process(false)
	return region

func _queue(region: Region, focus := Vector3(7,8,9)) -> void:
	region._pending_map = "neighbour"
	region._pending_generation = region._generation
	region._pending_started_usec = Time.get_ticks_usec()
	region._queue_web_preload("user://fixture/world.json", focus)

func _run() -> void:
	var region := _region()
	_queue(region)
	assert(calls == 0 and region._web_pending)
	assert(not region.is_idle() and not region._can_dispatch_preload())
	assert(region.diagnostic_snapshot().in_flight_maps == 1)
	await process_frame
	assert(calls == 1 and caller == OS.get_main_thread_id())
	assert(region._thread == null and region._web_builder != null)
	assert(last_stream.has_focus and last_stream.focus == Vector3(7,8,9))
	assert(not last_stream.primed, "browser prewarm never synchronously imports the arrival ring")
	region._process(0.0)
	assert(region.residents.has("neighbour") and last_stream.is_inside_tree())
	assert(not last_stream.primed and region.is_idle())
	region.clear()
	region.free()

	region = _region()
	_queue(region)
	var old := region._web_generation
	region.clear()
	_queue(region)
	region._prepare_web_region("stale-path", old)
	assert(region._web_pending and region._pending_map == "neighbour")
	await process_frame
	assert(calls == 2, "only the new owner may prepare this destination")
	var pending: WeakRef = weakref(region._web_builder)
	region.clear()
	assert(pending.get_ref() == null and region._web_builder == null)
	assert(region.is_idle())
	region.free()

	var park := Park.new()
	root.add_child(park)
	park._browser_background = true
	park.prepare_function = func(_a, _b, _c):
		assert(false, "browser whole-interior preload must not start a geometry worker")
		return null
	assert(not park.start_preload("four-gates-stormglass-house"))
	assert(park._preload.is_empty() and park.is_idle())
	park.free()
	print("PASS browser main-thread stream prewarm, lifecycle and whole-map guard")
	quit()
