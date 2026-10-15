class_name ContinentChunkStream
extends Node3D

## A named territory owns metadata; only the selected independent GLBs occupy
## renderer/physics memory. Coordinates in every cell remain territory-local.
## This root itself transfers during exterior adoption, retaining loaded cells.
const DEFAULT_PRELOAD_DISTANCE := 240.0
const DEFAULT_RETAIN_DISTANCE := 320.0
const DEFAULT_MAXIMUM_CHUNKS := 64
const DEFAULT_RESIDENT_BYTES := 268435456
const RETIRE_NODES_PER_FRAME := 64
const RETIRE_BUDGET_USEC := 2000
## Cells whose bounds come this close to the focus are the ground the camera
## is framing, and they are admitted whatever the byte budget says; the budget
## only trims the lead beyond them. The default rig (26 m at -60 degrees
## through the 50 degree lens, 16:10) frames ground out to about 35 m from the
## focus and a lowered view looks well past that. The life passes made single
## Amberwood and Four Gates cells cost 250-480 MiB against the 256 MiB budget,
## so a nearest-first prefix kept one cell and left its framed neighbours -
## sometimes a second cell under the focus itself - as bare flat planes.
const FRAMED_RADIUS := 64.0
const VramTextures := preload("res://src/world/vram_textures.gd")
## Where configure() keeps a chunk's shared image figures as published.
const PUBLISHED_SHARED_KEY := "publishedSharedResourceResidentBytes"
## The geometry figure develop's exporters publish per GLB byte
## (build_continent.py: 5 x glbBytes). The walk that marks `blocking` (what
## prime() imports synchronously) never counts less than that: a publisher
## that counts geometry nearer the GPU's real figure (continent-v2: 1 x
## glbBytes) admits more cells to residency, but those stream in on the
## worker instead of lengthening the arrival. Every legacy cell already
## publishes exactly this figure, so its walk is unchanged.
const BLOCKING_GEOMETRY_PER_GLB_BYTE := 5

signal cell_ready(identity: String, imported: Node3D)
signal cell_retiring(identity: String, imported: Node3D)

var territory: WorldManifest
var cells: Dictionary = {}
var entries: Array[Dictionary] = []
var preload_distance := DEFAULT_PRELOAD_DISTANCE
var retain_distance := DEFAULT_RETAIN_DISTANCE
var maximum_chunks := DEFAULT_MAXIMUM_CHUNKS
var maximum_resident_bytes := DEFAULT_RESIDENT_BYTES
var resident_bytes := 0
var focus := Vector3.ZERO
var has_focus := false
## First authoritative/preload position, retained for cold-arrival diagnostics.
var initial_focus := Vector3.INF
var events: Array[Dictionary] = []
var revision := 0
var _cache_enabled := true
var _thread: Thread
var _pending: Dictionary = {}
var _paused := false
var _retry_after: Dictionary = {}
var _retiring: Array[Dictionary] = []
var _retirement_scheduled := false
var _retirement_draining := false
var _next_update := 0
var _physics_enabled := true
var _preview_enabled := false
## VramTextures.budget_generation() when the entries were last corrected.
var _corrected_generation := -1
## Import workers whose owner left the tree or re-primed before they finished.
## A worker may be waiting on rendering-server commands that only the main
## thread services, so joining it synchronously deadlocks the client; the
## exterior stream reaps these once they report finished.
static var _orphans: Array[Dictionary] = []

static func _orphan(thread: Thread, entry: Dictionary) -> void:
	_orphans.append({"thread": thread, "entry": entry})

static func orphans_pending() -> int:
	return _orphans.size()

static func reap_orphans() -> int:
	var remaining: Array[Dictionary] = []
	for orphan: Dictionary in _orphans:
		var thread := orphan.thread as Thread
		if thread.is_alive():
			remaining.append(orphan)
			continue
		var builder := thread.wait_to_finish() as WorldLoader
		if builder != null:
			var resident := builder.release_world()
			builder.free()
			if resident.root != null:
				(resident.root as Node).queue_free()
	_orphans = remaining
	return _orphans.size()

## For a script that quits the SceneTree itself, such as a rendered test:
## pauses every chunk stream in `tree`, then lets frames run until none has a
## live import worker and every orphan is reaped. main.gd's _close_client
## waits the same way for its exterior stream. A worker still importing when
## the process exits crashes it at teardown ("Please call wait_to_finish()",
## 0xC0000005), and joining one here would deadlock (see _orphans). Since
## FRAMED_RADIUS leaves the framed cells beyond the budget to the worker, a
## test that quits soon after a load usually has one running. Returns false
## if the workers are still busy after `timeout_msec`.
static func drain_workers(tree: SceneTree, timeout_msec := 30000) -> bool:
	var streams: Array[ContinentChunkStream] = []
	for node: Node in tree.root.find_children("*", "", true, false):
		if node is ContinentChunkStream:
			var stream := node as ContinentChunkStream
			stream.pause_streaming()
			streams.append(stream)
	var deadline := Time.get_ticks_msec() + timeout_msec
	while true:
		var busy := reap_orphans() > 0
		for stream: ContinentChunkStream in streams:
			if is_instance_valid(stream) and not stream.can_retire():
				busy = true
		if not busy:
			return true
		if Time.get_ticks_msec() >= deadline:
			return false
		await tree.process_frame
	return false

func _release_worker(position: Vector3, install_if_near: bool) -> void:
	if _thread == null:
		return
	var pending := _pending
	_pending = {}
	if _thread.is_alive():
		# Never block the main thread on a live import.
		_orphan(_thread, pending)
		_thread = null
		_record("orphaned", str(pending.get("id", "")))
		return
	var builder := _thread.wait_to_finish() as WorldLoader
	_thread = null
	if install_if_near and bounds_distance(position, pending.bounds) <= preload_distance:
		_install(pending, builder)
	else:
		_discard_builder(pending, builder)

func configure(source: WorldManifest, cache_enabled: bool) -> void:
	territory = source
	_cache_enabled = cache_enabled
	set_meta("shared_stream_cells", true)
	var config: Dictionary = source.data.streamingChunks
	preload_distance = maxf(0, float(config.get("preloadDistance", DEFAULT_PRELOAD_DISTANCE)))
	retain_distance = maxf(preload_distance, float(config.get("retainDistance", DEFAULT_RETAIN_DISTANCE)))
	maximum_chunks = maxi(1, int(config.get("maximumLoadedChunks", DEFAULT_MAXIMUM_CHUNKS)))
	maximum_resident_bytes = maxi(1, int(config.get("maximumResidentBytes", DEFAULT_RESIDENT_BYTES)))
	# The sidecar indexes of every image this territory names, read before any
	# figure is corrected: the budget must not depend on a chunk import having
	# read them first, nor on where the shared images live.
	var indexes := VramTextures.read_indexes_for(source.data, source.glb_path().get_base_dir())
	for value: Dictionary in config.chunks:
		var entry := value.duplicate(true)
		entry.path = source.source_path.get_base_dir().path_join(str(entry.manifest))
		# Exporters should provide decoded geometry/texture/collision estimates.
		# The fallback deliberately exceeds packed file size; this is accounting,
		# not a claim that GPU/driver allocations can be measured from a manifest.
		entry.estimatedResidentBytes = maxi(1, int(entry.get("estimatedResidentBytes",
			maxi(1048576, int(entry.get("byteLength", 1048576)) * 12))))
		# The publisher counts each shared image as RGBA8 with mips. One this
		# client uploads from its VRAM-compressed sidecar holds a quarter or
		# an eighth of that; _correct_entries counts what it really holds
		# (vram_textures.gd) from the published figures kept here, which also
		# still decide what an arrival loads synchronously (see prime).
		var shared: Variant = entry.get("sharedResourceResidentBytes")
		if shared is Dictionary:
			entry[PUBLISHED_SHARED_KEY] = (shared as Dictionary).duplicate()
		entries.append(entry)
	var counted := _correct_entries()
	if VramTextures.mode() != VramTextures.Mode.OFF:
		print("vram_textures budget %s: %d of %d images at sidecar size; indexes %d of %d read (%d entries)" % [
			source.asset_id(), counted.x, counted.y, int(indexes.ok), int(indexes.directories),
			int(indexes.entries)])

## Rewrites every entry's shared image figures, in place, to what this client
## really holds for each (VramTextures.resident_bytes of the published one).
## Candidates and resident cells hold the same dictionaries (shallow copies),
## so they see it too. Returns (images at sidecar size, images counted).
func _correct_entries() -> Vector2i:
	_corrected_generation = VramTextures.budget_generation()
	var counted: Dictionary = {}
	var at_sidecar: Dictionary = {}
	for entry: Dictionary in entries:
		var published: Variant = entry.get(PUBLISHED_SHARED_KEY)
		var shared: Variant = entry.get("sharedResourceResidentBytes")
		if not published is Dictionary or not shared is Dictionary:
			continue
		for identity: String in published:
			var bytes := VramTextures.resident_bytes(identity, int(published[identity]))
			shared[identity] = bytes
			counted[identity] = true
			if bytes != int(published[identity]):
				at_sidecar[identity] = true
	return Vector2i(at_sidecar.size(), counted.size())

## Re-corrects when an answer of VramTextures.resident_bytes may have changed
## since: a sidecar refused at load (or not used for a role) uploads RGBA8,
## and from then on that image must count its published figure again.
func _refresh_corrections() -> void:
	if VramTextures.budget_generation() != _corrected_generation:
		var counted := _correct_entries()
		print("vram_textures budget %s rechecked: %d of %d images at sidecar size" % [
			territory.asset_id() if territory != null else "", counted.x, counted.y])

static func bounds_distance(position: Vector3, bounds: Dictionary) -> float:
	var lower: Array = bounds.min
	var upper: Array = bounds.max
	var dx := maxf(float(lower[0]) - position.x, maxf(0, position.x - float(upper[0])))
	var dz := maxf(float(lower[2]) - position.z, maxf(0, position.z - float(upper[2])))
	return Vector2(dx, dz).length()

## `key` names the image figures to count: the ones configure() corrected to
## what this client really holds (the default), or PUBLISHED_SHARED_KEY.
static func incremental_cost(entry: Dictionary, shared: Dictionary,
		key := "sharedResourceResidentBytes") -> int:
	# Decoded textures are pooled by content hash. Count each hash once across
	# the prospective resident set, while keeping legacy all-in estimates valid.
	if not entry.has("geometryResidentBytes"):
		return int(entry.estimatedResidentBytes)
	var geometry := int(entry.geometryResidentBytes)
	if key == PUBLISHED_SHARED_KEY and entry.has("glbBytes"):
		geometry = maxi(geometry, BLOCKING_GEOMETRY_PER_GLB_BYTE * int(entry.glbBytes))
	var cost := maxi(1, geometry)
	var images: Dictionary = entry.get(key, entry.get("sharedResourceResidentBytes", {}))
	for identity: String in images:
		var bytes := maxi(0, int(images[identity]))
		var previous := int(shared.get(identity, 0))
		cost += maxi(0, bytes - previous)
		shared[identity] = maxi(previous, bytes)
	return cost

func selection(position: Vector3, retain := false) -> Array[Dictionary]:
	_refresh_corrections()
	var candidates: Array[Dictionary] = []
	for entry: Dictionary in entries:
		var distance := bounds_distance(position, entry.bounds)
		var limit := retain_distance if retain and cells.has(str(entry.id)) else preload_distance
		if distance <= limit:
			var candidate := entry.duplicate()
			candidate.distance = distance
			candidates.append(candidate)
	candidates.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return str(a.id) < str(b.id) if is_equal_approx(a.distance, b.distance) else a.distance < b.distance)
	var selected: Array[Dictionary] = []
	var estimated := 0
	var shared: Dictionary = {}
	# The same walk on the published figures, which is develop's estimate:
	# the corrected costs are never larger, so this selection is a superset
	# of develop's in the same order, and `blocking` marks exactly the cells
	# develop's budget admitted (prime() loads only those synchronously).
	var published_estimated := 0
	var published_shared: Dictionary = {}
	for candidate: Dictionary in candidates:
		var cost := incremental_cost(candidate, shared)
		var published_cost := incremental_cost(candidate, published_shared, PUBLISHED_SHARED_KEY)
		# Never substitute a farther cheap cell for the nearest terrain. Allow
		# one oversize cell so a low budget cannot remove the arrival surface,
		# and every framed cell so one oversize cell cannot starve its
		# neighbours (candidates are nearest-first, so framed cells lead).
		var framed := float(candidate.distance) <= FRAMED_RADIUS
		var over_budget := not selected.is_empty() and estimated + cost > maximum_resident_bytes
		if selected.size() >= maximum_chunks or (over_budget and not framed):
			break
		# Admitted for the frame, not by the budget: prime() leaves these to
		# the worker unless they hold the arrival itself.
		candidate.beyond_budget = over_budget
		var within_published := published_estimated + published_cost <= maximum_resident_bytes
		candidate.blocking = selected.is_empty() or within_published
		selected.append(candidate)
		estimated += cost
		published_estimated += published_cost
	return selected

## Called before the first actor grounding, with the server's actual arrival.
## No default-spawn cells are read when the client is waiting for that packet.
## Loads synchronously only what the byte budget admits plus every cell under
## the arrival; framed cells beyond the budget stream in on the worker, so an
## arrival costs no more blocking import than it did before FRAMED_RADIUS.
## The synchronous part is judged on the published figures (`blocking`), not
## on the VRAM-corrected ones: the correction admits more cells to residency,
## and every one of those would otherwise lengthen the arrival freeze (the
## build is mostly geometry and scene work, which compressed textures do not
## shorten). The extra cells stream in on the worker like any framed cell.
func prime(position: Vector3) -> void:
	if has_focus:
		return
	focus = position
	has_focus = true
	if not initial_focus.is_finite():
		initial_focus = position
	for entry: Dictionary in selection(position):
		if cells.has(str(entry.id)):
			continue
		var blocking := not bool(entry.get("beyond_budget", false)) and bool(entry.get("blocking", true))
		if not blocking and float(entry.distance) > .01:
			continue
		var builder := WorldLoader.prepare_detached(str(entry.path), _cache_enabled)
		_install(entry, builder)

## True when every cell whose bounds hold the position is resident. Bounds
## include the props that overhang a cell, so neighbours overlap: a resident
## neighbour can cover a destination whose own ground cell is still missing,
## and an actor grounded then stands on whatever the neighbour has there.
func arrival_resident(position: Vector3) -> bool:
	var covering := 0
	for entry: Dictionary in entries:
		if bounds_distance(position, entry.bounds) <= .01:
			covering += 1
			if not cells.has(str(entry.id)):
				return false
	return covering > 0

func ensure_position(position: Vector3) -> bool:
	if not has_focus:
		prime(position)
		return true
	if arrival_resident(position):
		return false
	var wanted := selection(position)
	if wanted.is_empty():
		return false
	# Same-territory teleports do not necessarily create a new map root. Ground
	# the actual destination before constructing the actor there. The ordinary
	# 240m lead keeps this synchronous fallback off the continuous walk path.
	focus = position
	_release_worker(position, true)
	var keep: Dictionary = {}
	for entry: Dictionary in wanted:
		keep[str(entry.id)] = true
	for identity: String in cells.keys():
		if not keep.has(identity):
			_retire_cell(identity)
	has_focus = false
	prime(position)
	_record("arrival_reprime", "")
	return true

func update_focus(position: Vector3) -> void:
	if not has_focus or _paused:
		return
	focus = position
	if Time.get_ticks_msec() < _next_update:
		return
	_next_update = Time.get_ticks_msec() + 250
	var selected := selection(position, true)
	var wanted: Dictionary = {}
	for entry: Dictionary in selected:
		wanted[str(entry.id)] = true
	for identity: String in cells.keys():
		if not wanted.has(identity):
			_retire_cell(identity)
	if _thread != null or not _retiring.is_empty():
		return
	for entry: Dictionary in selected:
		if cells.has(str(entry.id)) or float(entry.distance) > preload_distance:
			continue
		if Time.get_ticks_msec() < int(_retry_after.get(str(entry.id), 0)):
			continue
		_pending = entry
		_thread = Thread.new()
		var error := _thread.start(WorldLoader.prepare_detached.bind(str(entry.path), _cache_enabled))
		if error != OK:
			_thread = null
			_failed(entry, error_string(error))
		else:
			_record("requested", str(entry.id))
		break

func _process(_delta: float) -> void:
	poll_pending()
	if not _retiring.is_empty() and not _retirement_scheduled:
		_retirement_scheduled = true
		_drain_retired_deferred.call_deferred()
	if has_focus and not _paused:
		update_focus(focus)

func _drain_retired_deferred() -> void:
	_retirement_scheduled = false
	# An exterior retirement may have taken ownership since this was queued.
	# Finish process/input callbacks before destroying any of their nodes.
	if is_inside_tree() and can_process():
		_drain_retired()

func poll_pending() -> void:
	if _thread == null or _thread.is_alive():
		return
	var builder := _thread.wait_to_finish() as WorldLoader
	_thread = null
	var entry := _pending
	_pending = {}
	if _paused or bounds_distance(focus, entry.bounds) > retain_distance:
		_discard_builder(entry, builder)
	else:
		_install(entry, builder)

func _install(entry: Dictionary, builder: WorldLoader) -> void:
	if builder == null:
		_failed(entry, "builder_missing")
		return
	var resident := builder.release_world()
	builder.free()
	var imported := resident.root as Node3D
	if imported == null:
		_failed(entry, "chunk_import_failed")
		return
	if not str(entry.get("packageDigest", "")).is_empty() and str(entry.packageDigest) != str(resident.digest):
		imported.free()
		_failed(entry, "chunk_package_digest_mismatch")
		return
	imported.set_meta("continent_chunk_id", str(entry.id))
	ExteriorRegionStream._set_collision(imported, _physics_enabled, _preview_enabled, "", true)
	add_child(imported)
	resident.entry = entry
	cells[str(entry.id)] = resident
	_update_resident_bytes()
	_changed()
	_record("ready", str(entry.id))
	cell_ready.emit(str(entry.id), imported)

func set_physics_mode(enabled: bool, preview: bool) -> void:
	_physics_enabled = enabled
	_preview_enabled = preview

func pause_streaming() -> void:
	_paused = true

func can_retire() -> bool:
	poll_pending()
	return _thread == null

func _retire_cell(identity: String) -> void:
	var resident: Dictionary = cells[identity]
	cells.erase(identity)
	var imported := resident.root as Node3D
	imported.process_mode = Node.PROCESS_MODE_DISABLED
	imported.visible = false
	ExteriorRegionStream._set_collision(imported, false)
	_retiring.append({"root": imported, "stack": [imported], "entry": resident.entry})
	cell_retiring.emit(identity, imported)
	_changed()
	_record("evicted", identity)

func _discard_builder(entry: Dictionary, builder: WorldLoader) -> void:
	if builder == null:
		return
	var resident := builder.release_world()
	builder.free()
	if resident.root != null:
		var imported := resident.root as Node3D
		imported.process_mode = Node.PROCESS_MODE_DISABLED
		imported.visible = false
		add_child(imported)
		_retiring.append({"root": imported, "stack": [imported], "entry": entry})
		_update_resident_bytes()
	_record("discarded", str(entry.id))

func _drain_retired() -> void:
	# Node destruction emits exit signals before it finishes detaching. A
	# callback must not walk the same child again while its destructor runs.
	if _retirement_draining:
		return
	_retirement_draining = true
	var began := Time.get_ticks_usec()
	var freed := 0
	while not _retiring.is_empty() and freed < RETIRE_NODES_PER_FRAME and Time.get_ticks_usec() - began < RETIRE_BUDGET_USEC:
		var retired: Dictionary = _retiring[0]
		var stack: Array = retired.stack
		if stack.is_empty():
			_retiring.pop_front()
			_update_resident_bytes()
			continue
		# Pick proxies and other independently owned descendants may have been
		# queued for deletion between slices. Validate before casting to Node.
		var node: Variant = stack.back()
		if not is_instance_valid(node):
			stack.pop_back()
		elif node.get_child_count() > 0:
			stack.append(node.get_child(node.get_child_count() - 1))
		else:
			stack.pop_back()
			node.free()
			freed += 1
		if stack.is_empty():
			_retiring.pop_front()
			_update_resident_bytes()
	_retirement_draining = false

func _update_resident_bytes() -> void:
	_refresh_corrections()
	resident_bytes = 0
	var shared: Dictionary = {}
	for resident: Dictionary in cells.values():
		resident_bytes += incremental_cost(resident.entry, shared)
	# Hidden retirement nodes still hold materials and textures until freed.
	for retired: Dictionary in _retiring:
		resident_bytes += incremental_cost(retired.entry, shared)

func _changed() -> void:
	revision += 1
	# Existing exterior collision/view caches must see newly attached cells.
	if has_meta("stream_physics"):
		remove_meta("stream_physics")

func _failed(entry: Dictionary, reason: String) -> void:
	_retry_after[str(entry.id)] = Time.get_ticks_msec() + 30000
	_record("failed", str(entry.id), {"reason": reason})

func _record(kind: String, identity: String, details := {}) -> void:
	var event := {"event": kind, "chunk": identity, "resident_bytes": resident_bytes}
	event.merge(details)
	events.append(event)
	if events.size() > 100:
		events.pop_front()
	print("continent_chunk ", JSON.stringify(event))

func _exit_tree() -> void:
	_paused = true
	# Normal exterior retirement polls completion before freeing any descendant.
	# A map change or disconnect can still free this root while an import is
	# live; that worker is orphaned and reaped later, never joined here.
	if _thread != null:
		if _thread.is_alive():
			_orphan(_thread, _pending)
			_record("orphaned", str(_pending.get("id", "")))
		else:
			var builder := _thread.wait_to_finish() as WorldLoader
			if builder != null:
				builder.free()
		_thread = null
		_pending = {}

func _enter_tree() -> void:
	_paused = false
