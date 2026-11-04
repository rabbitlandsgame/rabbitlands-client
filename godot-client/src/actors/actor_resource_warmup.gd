extends RefCounted
## The actor preparer: one worker prepares cold actor glTFs before Main builds
## the bodies that use them. Actors remain ordinary deferred nodes until
## publication on main. Workers never inspect live nodes, mutate session
## caches, or attach anything to a tree.
##
## Two kinds of job share the one worker, so the preparer runs one parse at a
## time (several GLTFDocument parses on workers at once have crashed the
## headless renderer; RLHeadLibrary and the world streams keep their own):
##   * creature jobs (`request`): a creature's geometry and its immutable
##     retargeted clips, packed on the worker by GlbSceneCache.prepare and
##     installed when the worker is joined, as before;
##   * actor file jobs (`request_closure`, avatar-worker AW-04a): each file of
##     an actor's asset closure (actor_asset_closure.gd: race scene, hair,
##     equipment) parsed by GlbSceneCache.prepare_actor, which never packs and
##     so waits for nothing on the main thread. Files read as equipment pieces
##     also get their pieces table read from the unpacked root on the worker
##     (ReplicatedActor3D.equipment_pieces_from). Main publishes at most
##     PUBLISH_PER_FRAME such file a process frame (install_actor_prepared packs
##     it: 1-4.4 ms headless, a race scene the most) and the pieces with it; a
##     root whose file main cached meanwhile is freed unpublished, pieces and
##     all (`alreadyCached`). The worker starts no parse while
##     PUBLISH_QUEUE_LIMIT parsed roots await publication. A closure's RL files
##     (a portrait Human's RL hairstyle module) are asked of
##     RLHeadLibrary.request, which parses them on its own worker.
## The next job is the most urgent queued one (PRIORITY_*), first asked first
## within a class; asking again with a more urgent class raises a queued job.
## A file GlbSceneCache already holds is never queued (`missing`). A file the
## worker could not prepare (an error record, a stale stamp, a failed start)
## is left to the main thread, which parses it on first use exactly as before;
## so is every file when the preparer is off: on the web build, with prepared
## content, with ELORIA_ACTOR_IMAGES=legacy (an equipment parse on a worker
## would wait for the main thread again) or ELORIA_ACTOR_PREPARER=off.
##
## The worker is never joined while it runs (`poll` joins it once it has
## finished): a parse can need the rendering server. The one exception is a
## preparer freed without being drained, which joins a running file job (it
## waits for nothing; `_notification`). Leaving a session calls
## `clear`, which drops every queued job and unpublished result; a running
## job finishes privately and its result is discarded.
##
## GlbSceneCache may evict an idle creature to stay inside the memory class's
## creature budget (memory classes M5). A creature prepared before and evicted
## since is cold again: `request` queues it on the worker as at first sight,
## so the actor stays deferred until the scene is back and is never parsed on
## the main thread because of the eviction.
const ActorImages := preload("res://src/actors/actor_images.gd")
## Priority classes, most urgent first (avatar-worker plan 3.2): the player's
## own avatar (AW-04d), the selection, combat target and staged scene actors,
## bodies within the build radius, mounts, everything else.
const PRIORITY_LOCAL := 0
const PRIORITY_TARGET := 1
const PRIORITY_NEAR := 2
const PRIORITY_MOUNT := 3
const PRIORITY_OTHER := 4
## Prepared actor files main publishes in one process frame, and the main
## thread time after which a frame publishes no more.
const PUBLISH_PER_FRAME := 1
const PUBLISH_BUDGET_USEC := 4000
## Parsed roots awaiting publication at which the worker starts no new job.
const PUBLISH_QUEUE_LIMIT := 2
## `off` (or `main`, `0`): every actor file is parsed on main as before.
const SWITCH_ENVIRONMENT := "ELORIA_ACTOR_PREPARER"

var _queue: Array[Dictionary] = []
var _known: Dictionary = {}
var _known_sources: Dictionary = {}
var _thread: Thread
var _active := ""
var _active_scene := ""
## The job the worker runs (a creature job or an actor file job).
var _active_job: Dictionary = {}
var _discard_active := false
## Ready creatures queued again because GlbSceneCache evicted their scene.
var requeued_after_eviction := 0
## Actor file jobs by canonical path: {kind, path, names {as asked: true},
## pieces, priority, seq}, from first request until published or given up.
var _files: Dictionary = {}
## Canonical paths the worker could not prepare: main parses them as before.
var _fallback: Dictionary = {}
## Parsed actor files awaiting publication: [{job, record}].
var _outbox: Array[Dictionary] = []
var _sequence := 0
var _publish_frame := -1
var _published_in_frame := 0
var _frame_publish_usec := 0
var _unclaimed_publish_usec := 0
var _switch := ""
var _stats := {"closureRequests": 0, "closureWaits": 0, "filesQueued": 0, "filesParsed": 0,
	"filesPublished": 0, "alreadyCached": 0, "piecesPublished": 0, "fallbacks": 0, "discarded": 0,
	"priorityRaises": 0, "rlWaits": 0,
	"workerUsec": 0, "maximumWorkerUsec": 0, "publishUsec": 0, "maximumPublishUsec": 0}

## A creature's scene and retargeted clips, prepared on the worker at
## `priority`; true once published (or when this is no creature job: main
## builds it as before).
func request(config: Dictionary, animation: Dictionary, priority := PRIORITY_NEAR) -> bool:
	poll()
	var key := JSON.stringify([config, animation])
	if _known.has(key):
		if not bool(_known[key]):
			_raise(key, priority)
			return false
		if not GlbSceneCache.evicted(str(config.get("scene", ""))):
			return true
		# Evicted since it was prepared: cold again (see the header).
		_known.erase(key)
		_known_sources.erase(key)
		requeued_after_eviction += 1
	# Equipment libraries have external textures with main-thread readback
	# semantics. Their existing path is deliberately outside this creature job
	# (actor files go through `request_closure`).
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
	_queue.append({"kind": "creature", "key": key, "config": config.duplicate(true),
		"animation": animation.duplicate(true), "priority": priority, "seq": _next_sequence()})
	poll()
	return false

## Asks the worker for every file of `closure` (ActorAssetClosure.closure)
## that GlbSceneCache does not hold yet, at `priority`, and RLHeadLibrary for
## its RL files (parsed on the RL library's own worker). True once each is
## cached or left to the main thread (see the header): a body built then
## parses nothing it could have had prepared. Main thread.
func request_closure(closure: Dictionary, priority := PRIORITY_NEAR) -> bool:
	poll()
	var scenes: PackedStringArray = closure.get("scenes", PackedStringArray())
	var rl_files: PackedStringArray = closure.get("rl_files", PackedStringArray())
	if (scenes.is_empty() and rl_files.is_empty()) or not closure_enabled():
		return true
	_stats.closureRequests += 1
	var pieces: PackedStringArray = closure.get("pieces", PackedStringArray())
	var ready := true
	for name: String in scenes:
		var missing := GlbSceneCache.missing(PackedStringArray([name]))
		if missing.is_empty() or _fallback.has(missing[0]):
			continue
		ready = false
		_want_file(missing[0], name, pieces.has(name), priority)
	# Never parses on main; true where it cannot start a parse (main then
	# parses as before). One shared callback: readiness is asked again.
	if not rl_files.is_empty() and not GlbSceneCache.missing(rl_files).is_empty() \
			and not RLHeadLibrary.request(rl_files, _on_rl_files_ready):
		ready = false
		_stats.rlWaits += 1
	if not ready:
		_stats.closureWaits += 1
		poll()
	return ready

## Whether actor closures are prepared on the worker in this process (see the
## header). Main thread: it completes the glTF extension registration the
## worker relies on.
func closure_enabled() -> bool:
	return _closure_state(true) == "on"

## "on", or why closures are left to the main thread: "switch", "web",
## "prepared_content", "actor_images_legacy" (or "unregistered", only when
## `register` is false and no glTF parse has registered the extensions yet).
func _closure_state(register: bool) -> String:
	if _switch.is_empty():
		_switch = OS.get_environment(SWITCH_ENVIRONMENT).strip_edges().to_lower()
		if _switch.is_empty(): _switch = "on"
	if _switch in ["off", "main", "0", "false", "no"]:
		return "switch"
	if OS.has_feature("web"):
		return "web"
	if NativeAnimationImporter.PreparedContent.selected_mode() != "raw":
		return "prepared_content"
	var registered := NativeAnimationImporter.GltfQuantization.ensure_registered() if register \
		else NativeAnimationImporter.GltfQuantization.is_registered()
	if not registered:
		return "unregistered"
	return "on" if ActorImages.active() else "actor_images_legacy"

## Whether `path` (any spelling the cache accepts) is queued, parsing or
## awaiting publication.
func file_pending(path: String) -> bool:
	return _files.has(GlbSceneCache._canonical_path(path))

## Main-thread microseconds spent publishing since the last call (Main
## charges them to the frame's actor work).
func take_publish_usec() -> int:
	var spent := _unclaimed_publish_usec
	_unclaimed_publish_usec = 0
	return spent

func poll() -> void:
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return
	if _thread != null and not _thread.is_alive():
		var result: Dictionary = _thread.wait_to_finish()
		_thread = null
		var job := _active_job
		_active_job = {}
		if str(job.get("kind", "")) == "file":
			_finish_file(job, result)
		elif not _discard_active:
			GlbSceneCache.install_prepared(result.get("scenes", {}))
			NativeAnimationImporter.install_prepared(result.get("library", {}))
			_known[_active] = true # Failed preparation uses the normal fallback.
			# A preparation after an eviction that failed is not asked for
			# again on every request (a published scene cleared the mark).
			GlbSceneCache.clear_eviction(_active_scene)
		_discard_active = false
		_active = ""
		_active_scene = ""
	_publish_ready()
	_start_next()

func clear() -> void:
	_queue.clear()
	_known.clear()
	_known_sources.clear()
	_files.clear()
	_fallback.clear()
	for item: Dictionary in _outbox:
		GlbSceneCache.discard_actor_prepared(item.record)
		_stats.discarded += 1
	_outbox.clear()
	# A loader can need the rendering server. Never join a live worker on main:
	# cancel publication, and keep serving frames until is_idle() before exit.
	_discard_active = _thread != null
	poll()

func is_idle() -> bool:
	poll()
	return _thread == null and _queue.is_empty() and _outbox.is_empty()

## Freed without `clear` and `is_idle` (a test or tool that frees Main or
## quits at once): unpublished roots are freed, and a running actor file job is
## joined, since it waits for nothing on the main thread (see the header), so
## no GDScript is left running on a worker into engine teardown. A running
## creature job packs on the worker and may wait for the main thread: it is
## left as before.
func _notification(what: int) -> void:
	if what != NOTIFICATION_PREDELETE:
		return
	for item: Dictionary in _outbox:
		GlbSceneCache.discard_actor_prepared(item.record)
	_outbox.clear()
	if _thread != null and str(_active_job.get("kind", "")) == "file" \
			and OS.get_thread_caller_id() == OS.get_main_thread_id():
		var result: Variant = _thread.wait_to_finish()
		_thread = null
		_active_job = {}
		if result is Dictionary:
			GlbSceneCache.discard_actor_prepared(result as Dictionary)

## Plain-data counters for the client diagnostics snapshot ("closures": on,
## or why actor files are left to the main thread). Registers nothing.
func snapshot() -> Dictionary:
	var queued := {"creature": 0, "file": 0}
	for job: Dictionary in _queue:
		queued[str(job.get("kind", "creature"))] = int(queued.get(str(job.get("kind", "creature")), 0)) + 1
	var row := _stats.duplicate()
	row.merge({"closures": _closure_state(false), "queuedCreatures": queued.creature, "queuedFiles": queued.file,
		"active": str(_active_job.get("kind", "")), "awaitingPublish": _outbox.size(),
		"fallbackFiles": _fallback.size(), "requeuedAfterEviction": requeued_after_eviction}, true)
	return row

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
	for path: String in _files.keys() + _fallback.keys():
		if wanted.has(GlbSceneCache._file_key(path)):
			_files.erase(path)
			_fallback.erase(path)
	if invalid.is_empty(): return
	for key: String in invalid:
		_known.erase(key)
		_known_sources.erase(key)
		if key == _active: _discard_active = true
	_queue.assign(_queue.filter(func(job: Dictionary) -> bool: return not invalid.has(str(job.get("key", "")))))

## RLHeadLibrary's notice that requested RL files are in: readiness is asked
## again by the next request, so there is nothing to do here.
func _on_rl_files_ready() -> void:
	pass

func _next_sequence() -> int:
	_sequence += 1
	return _sequence

func _want_file(path: String, name: String, pieces: bool, priority: int) -> void:
	var job: Dictionary = _files.get(path, {})
	if job.is_empty():
		NativeAnimationImporter.VramTextures.ensure_registered()
		NativeAnimationImporter.MapMeshExtension.ensure_registered()
		job = {"kind": "file", "path": path, "names": {name: true}, "pieces": pieces,
			"priority": priority, "seq": _next_sequence()}
		_files[path] = job
		_queue.append(job)
		_stats.filesQueued += 1
		return
	(job.names as Dictionary)[name] = true
	job.pieces = bool(job.pieces) or pieces
	if priority < int(job.priority):
		job.priority = priority
		_stats.priorityRaises += 1

func _raise(key: String, priority: int) -> void:
	for job: Dictionary in _queue:
		if str(job.get("key", "")) == key and priority < int(job.get("priority", PRIORITY_OTHER)):
			job.priority = priority
			_stats.priorityRaises += 1

## The most urgent queued job's index (first asked first within a class).
func _next_index() -> int:
	var best := -1
	for index: int in _queue.size():
		var job: Dictionary = _queue[index]
		if best < 0 or int(job.priority) < int(_queue[best].priority) \
				or (int(job.priority) == int(_queue[best].priority) and int(job.seq) < int(_queue[best].seq)):
			best = index
	return best

func _start_next() -> void:
	while _thread == null and not _queue.is_empty() and _outbox.size() < PUBLISH_QUEUE_LIMIT:
		var job: Dictionary = _queue.pop_at(_next_index())
		if str(job.get("kind", "")) == "file":
			var path := str(job.path)
			if not is_same(_files.get(path), job):
				continue
			if GlbSceneCache.missing(PackedStringArray([path])).is_empty():
				# Published meanwhile (a main-thread build or another job).
				_files.erase(path)
				continue
			_active_job = job
			_thread = Thread.new()
			if _thread.start(_prepare_file.bind(path, bool(job.pieces))) != OK:
				_thread = null
				_active_job = {}
				_files.erase(path)
				_fallback[path] = true
				_stats.fallbacks += 1
			continue
		_active_job = job
		_active = str(job.key)
		_active_scene = str((job.config as Dictionary).get("scene", ""))
		_thread = Thread.new()
		if _thread.start(_prepare.bind(job.config, job.animation)) != OK:
			_thread = null
			_active_job = {}
			_known[_active] = true
			GlbSceneCache.clear_eviction(_active_scene)
			_active = ""
			_active_scene = ""

func _finish_file(job: Dictionary, record: Dictionary) -> void:
	var path := str(job.path)
	var worker_usec := int(record.get("worker_usec", 0))
	_stats.workerUsec += worker_usec
	_stats.maximumWorkerUsec = maxi(int(_stats.maximumWorkerUsec), worker_usec)
	if _discard_active or not is_same(_files.get(path), job):
		GlbSceneCache.discard_actor_prepared(record)
		_stats.discarded += 1
		return
	_stats.filesParsed += 1
	if not (record.has("root") or record.has("packed") or record.has("prepared")):
		# An error record ("not_actor_document", "retired", "parse_failed"):
		# main builds this file as before, once, when a body asks for it.
		_files.erase(path)
		_fallback[path] = true
		_stats.fallbacks += 1
		return
	_outbox.append({"job": job, "record": record})

func _publish_ready() -> void:
	if _outbox.is_empty():
		return
	var frame := Engine.get_process_frames()
	if frame != _publish_frame:
		_publish_frame = frame
		_published_in_frame = 0
		_frame_publish_usec = 0
	while not _outbox.is_empty() and _published_in_frame < PUBLISH_PER_FRAME \
			and _frame_publish_usec < PUBLISH_BUDGET_USEC:
		var item: Dictionary = _outbox.pop_front()
		var began := Time.get_ticks_usec()
		_publish(item.job, item.record)
		var spent := Time.get_ticks_usec() - began
		_published_in_frame += 1
		_frame_publish_usec += spent
		_unclaimed_publish_usec += spent
		_stats.publishUsec += spent
		_stats.maximumPublishUsec = maxi(int(_stats.maximumPublishUsec), spent)

func _publish(job: Dictionary, record: Dictionary) -> void:
	var path := str(job.path)
	_files.erase(path)
	var root: Variant = record.get("root")
	var had_root := typeof(root) == TYPE_OBJECT and is_instance_valid(root)
	var was_missing := not GlbSceneCache.missing(PackedStringArray([path])).is_empty()
	if not GlbSceneCache.install_actor_prepared(record):
		# Stale (the file changed since it was read), retired or unpackable:
		# main builds it as before when a body asks for it.
		_fallback[path] = true
		_stats.fallbacks += 1
		return
	if not was_missing:
		# Cached meanwhile (a main-thread build parsed it): the cache keeps that
		# scene, install_actor_prepared freed this root unpublished, and its
		# pieces (another parse's meshes) go with it.
		_stats.alreadyCached += 1
		return
	_stats.filesPublished += 1
	# The pieces were read from the root just packed into the cache, so they
	# share its meshes as pieces read from an instance of it would.
	var pieces: Variant = record.get("pieces")
	if had_root and pieces is Array:
		for name: String in (job.names as Dictionary):
			if ReplicatedActor3D.install_equipment_pieces(name, pieces as Array):
				_stats.piecesPublished += 1

## Worker: one actor file (see the header). Never packs or instantiates.
static func _prepare_file(path: String, pieces: bool) -> Dictionary:
	var began := Time.get_ticks_usec()
	var record := GlbSceneCache.prepare_actor(path)
	var root: Variant = record.get("root")
	if pieces and typeof(root) == TYPE_OBJECT and root is Node3D:
		record["pieces"] = ReplicatedActor3D.equipment_pieces_from(root as Node3D, path)
	record["worker_usec"] = Time.get_ticks_usec() - began
	return record

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
