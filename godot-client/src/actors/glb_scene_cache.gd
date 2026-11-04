class_name GlbSceneCache

extends RefCounted
## Loads each glTF scene exactly once and hands out instances of the cached
## result.
##
## In-project actor assets prefer Godot's imported PackedScene. Besides avoiding
## a runtime parse, that path retains the importer's generated mesh LODs, shadow
## meshes, compression and texture mip chains. External authoring/test files and
## lean checkouts without an import cache keep the raw GLTFDocument fallback.
##
## Instances share their mesh, skin and material resources, which also removes
## the duplicate GPU uploads the per-actor parse produced. Per-actor tinting
## goes through `material_override`, so sharing the source materials cannot leak
## one actor's appearance into another.
##
## Threads: every actor glTF (race, hair, equipment, held prop, mount,
## creature, RL head) is parsed by `_parse_generate`, which enables the actor
## image extension (actor_images.gd) on its GLTFState. A packaged client
## imports the textures the equipment glTFs name by URI
## (tools/package_client.py), and plain GLTFDocument takes such a texture
## through ResourceLoader and then reads it back with get_image(). Outside the
## editor that is a RenderingServer texture read: on the main thread it stalls
## the GPU once per image, and on a worker it waits for the main thread to
## serve it, so a main thread that joins the worker (wait_to_finish) never
## returns. The extension takes the same texture without the read, so an actor
## parse and generate_scene() wait for nothing.
##
## PackedScene.pack() still waits: it asks each MeshInstance3D for its property
## list, a synchronous RenderingServer call (on a worker, about one main frame
## per mesh). So actor files reach a worker only through `prepare_actor`, which
## parses and generates and returns the scene unpacked, and main publishes it
## with `install_actor_prepared`, which packs. `prepare` packs on its worker; it
## serves the map preloaders' visualScenes (no actor file), creature warmup and
## the RL head library, and tests/test_package_actor_worker_contract.py and the
## packaging tests hold every caller to that. With ELORIA_ACTOR_IMAGES=legacy
## the extension is off and an equipment parse belongs on the main thread again
## (`prepare_actor` records "actor_images": false).

## Memory (memory classes M5, owner decision 10): every published entry gets a
## ledger row ({bytes, mesh_bytes, texture_bytes, domain, origin, ...}) with
## ResourceBytes estimates and a domain taken from its path (creature, race,
## hair, equipment, rl_head, world, other). Creature rows are measured when
## published; the others are measured later by the budget pass, a little at a
## time, so a map's world objects add no work to their publication.
## `retention_snapshot()` reports the bytes by domain.
##
## Only creatures are evicted, and only entries the creature warm-up prepared
## on its worker (built raw: never imported, prepared or geometry records,
## whose instances take other paths). Races, legacy hair and equipment are
## parsed on the main thread, so evicting them would bring back the re-parse
## hitch this cache exists to prevent; RL head files are the RL library's;
## world assets belong to map lifecycles (`release_sources`). The pass runs on
## the main thread every BUDGET_PASS_SECONDS (a SceneTree timer, armed while
## there are rows) and after a creature publication that leaves the domain over
## MemoryBudgets' `creature_scene_bytes`. It evicts idle entries, least recently
## used first, down to EVICT_TO_FRACTION of the budget; an entry is idle once
## it has been unused for the class's `creature_scene_idle_msec`. Idle means
## that every probe mesh's reference count is back at the count it had when
## the entry was published, before any instance: an instance, a Node
## duplicate() of one or any other holder keeps it in use, so an entry in use
## is never evicted (an unexpected holder only keeps memory alive). Eviction
## drops the entry (its key, as `forget`) and calls
## NativeAnimationImporter.release_sources() for the file (every creature names
## its own GLB as its animation library); an importer still prewarming the
## file skips the entry until a later pass. The warm-up
## (actor_resource_warmup.gd) asks `evicted()` and prepares such a creature
## again on its worker, as at first sight, so it is never parsed on the main
## thread because of an eviction (`evicted_main_rebuilds` counts any that are).

## World objects (harvest nodes, interactives) also come through here, and
## GLTFDocument builds their textures at runtime with no mip chain. Seen from the
## gameplay camera a node's 256-512 px texture is minified several times over, so
## without mips it aliases and swims as the camera moves - the reason
## world_loader rebuilds the chains of every map chunk. Models under this root
## get the same chains and the same anisotropic filter as the map around them.
## Actors get neither here (build_texture_mipmaps stays world-only): their
## images are produced inside the parse by the actor image extension
## (actor_images.gd), which uploads a GLB directory's offline VRAM sidecars
## (BC7/BC5/BC1 with their whole mip chain, AT-C2) where an index lists them
## and decodes the rest as before, without mips, sharing one texture per image
## across GLBs. That costs the parse no readback, so worker and main parses
## get the same result.
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const ActorImages := preload("res://src/actors/actor_images.gd")
const GltfAnimationFidelity := preload("res://src/actors/gltf_animation_fidelity.gd")
const CreaturePayload := preload("res://src/actors/creature_payload.gd")
const WorldObjectImages := preload("res://src/world/world_object_images.gd")
const SceneryImages := preload("res://src/world/scenery_image_sources.gd")
const ArchivedModelPolicy := preload("res://src/actors/archived_model_policy.gd")
const ResourceDiagnostics := preload("res://src/world/resource_diagnostics.gd")
const PreparedContent := preload("res://src/world/prepared_content.gd")
const PreparedLifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const GeometryCache := preload("res://src/world/map_geometry_cache.gd")
const GeometrySources := preload("res://src/world/map_geometry_texture_sources.gd")
const MapSceneCache := preload("res://src/world/map_scene_cache.gd")
const MapMaterialPreparation := preload("res://src/world/map_material_preparation.gd")
const MemoryBudgets := preload("res://src/runtime/memory_budgets.gd")
const ResourceBytes := preload("res://src/runtime/resource_bytes.gd")
const WORLD_ASSET_ROOT := "res://assets/world/"
## glTF files under this root are actor documents (see "Threads").
const ACTOR_ASSET_ROOT := "res://assets/actors/"
const BOUND_MAIN_ENVIRONMENT := "ELORIA_UNDERGROUND_BOUND_PREPARE"
const EARLY_WORLD_FILTER_ENVIRONMENT := "ELORIA_EARLY_WORLD_OBJECT_FILTER"

## Ledger domains (see "Memory"). World assets are DOMAIN_WORLD; a path under
## none of DOMAIN_ROOTS is DOMAIN_OTHER (mounts, shared files, tests).
const DOMAIN_CREATURE := "creature"
const DOMAIN_RACE := "race"
const DOMAIN_HAIR := "hair"
const DOMAIN_EQUIPMENT := "equipment"
const DOMAIN_RL_HEAD := "rl_head"
const DOMAIN_WORLD := "world"
const DOMAIN_OTHER := "other"
const DOMAIN_ROOTS := {
	"res://assets/actors/native/creatures/": DOMAIN_CREATURE,
	"res://assets/actors/native/races/": DOMAIN_RACE,
	"res://assets/actors/native/hair/": DOMAIN_HAIR,
	"res://assets/actors/native/equipment/": DOMAIN_EQUIPMENT,
	"res://assets/actors/native/rl_heads/": DOMAIN_RL_HEAD,
}
## Who published an entry. Only ORIGIN_WORKER creature entries built raw are
## evictable.
const ORIGIN_WORKER := "worker" # install_prepared / install_actor_prepared of a worker's build
const ORIGIN_MAIN := "main" # built on the main thread (a cache miss or a fallback)
const ORIGIN_IMPORTED := "imported" # the editor's imported PackedScene, via prepare_actor
const ORIGIN_PREPARED := "prepared" # a prepared-content record
const ORIGIN_GEOMETRY := "geometry" # a geometry-cache record
const ORIGIN_UNKNOWN := "unknown" # found in the cache without a publication (pruning)
## Seconds between budget passes (main thread, SceneTree timer).
const BUDGET_PASS_SECONDS := 5.0
## An over-budget pass evicts down to this fraction of the creature budget.
const EVICT_TO_FRACTION := 0.85
## Main-thread time a pass may spend measuring pending (non-creature) rows.
const LEDGER_FILL_SLICE_USEC := 1000

static var _scenes: Dictionary = {}
static var _failed: Dictionary = {}
static var _prepared_entries: Dictionary = {}
static var _geometry_entries: Dictionary = {}
static var _direct_raw_scenes: Dictionary = {}
static var _diagnostics_mutex := Mutex.new()
static var _resource_timings: Dictionary = {}
static var _lookup_hits := 0
static var _lookup_misses := 0
## Memory ledger (see "Memory"), main thread only: canonical path -> row
## {bytes (-1 until measured), mesh_bytes, texture_bytes, domain, origin,
## evictable, scene_id, probes (WeakRefs to the scene's meshes), baseline
## (their reference counts at publication), published_msec, last_used_msec,
## idle_since_msec (0 while in use or not yet seen idle)}.
static var _ledger: Dictionary = {}
## Measured bytes of the ledger's rows by domain.
static var _domain_bytes: Dictionary = {}
static var _pending_rows := 0
static var _evictable_rows := 0
## Canonical paths evicted and not published since (`evicted`).
static var _evicted: Dictionary = {}
## Process totals (not reset by clear()).
static var _evictions := 0
static var _evicted_bytes := 0
static var _eviction_skips := 0
static var _evicted_main_rebuilds := 0
static var _budget_passes := 0
static var _budget_timer_armed := false
## [canonical root, domain] pairs of DOMAIN_ROOTS, built on first use.
static var _domain_prefixes: Array = []
## Test overrides of the creature budget and idle age (< 0: MemoryBudgets').
static var _test_budget_bytes := -1
static var _test_idle_msec := -1

static func missing(paths: PackedStringArray) -> PackedStringArray:
	var out := PackedStringArray()
	for path: String in paths:
		path = _canonical_path(path)
		if not _scenes.has(path) and not _failed.has(path):
			out.append(path)
	return out

static func prepare(paths: PackedStringArray) -> Dictionary:
	# Worker-owned resources. The main thread publishes them only on arrival.
	# It packs on the worker: never an equipment glTF (prepare_actor is the
	# actor worker path), see "Threads" above.
	var result: Dictionary = {}
	for path: String in paths:
		path = _canonical_path(path)
		var scenery := _scenery_inputs(path)
		if not scenery.is_empty() and not bool(scenery.get("ok", false)):
			continue
		if not GeometryCache.cooking and PreparedContent.selected_mode() != "require-pilot" and GeometryCache.eligible("asset",path):
			var geometry := GeometryCache.acquire("asset",path,_source_sha(path, scenery),{},MapSceneCache.is_enabled())
			if str(geometry.status) == "hit":
				result[path] = {"geometry_record":geometry}
				continue
		if PreparedContent.selected_mode() != "raw":
			var record := PreparedContent.acquire("scene", path, _source_sha(path, scenery),
				PreparedContent.scene_texture_token(path, scenery))
			if str(record.status) == "hit":
				result[path] = record # Immutable native Resources, never Nodes.
				continue
			if str(record.status) == "reject":
				continue
		var scene := _build(path, scenery)
		if scene != null:
			result[path] = {"raw_scene": scene, "source_sha256": _source_sha(path, scenery),
				"closure_token": str(scenery.get("closure_token", ""))} if not scenery.is_empty() else scene
	return result

static func install_prepared(scenes: Dictionary) -> void:
	for path: String in scenes:
		# A browser file may have been retired while this worker finished.
		if OS.has_feature("web") and not FileAccess.file_exists(path): continue
		if not _scenes.has(path):
			var prepared: Variant = scenes[path]
			if prepared is Dictionary:
				var scenery := _scenery_inputs(path)
				if not scenery.is_empty() and not bool(scenery.get("ok", false)):
					continue
				if prepared.has("raw_scene"):
					if str(prepared.get("source_sha256", "")) == _source_sha(path, scenery) \
							and str(prepared.get("closure_token", "")) == str(scenery.get("closure_token", "")):
						_put(path, prepared.raw_scene, ORIGIN_WORKER)
					else:
						var current := _build(path, scenery)
						if current != null: _put(path, current, ORIGIN_MAIN)
					continue
				if prepared.has("geometry_record"):
					var geometry: Dictionary = prepared.geometry_record
					if GeometryCache.revalidate(geometry):
						_put(path, geometry.resource, ORIGIN_GEOMETRY)
						_geometry_entries[path] = geometry
					else:
						var raw := _build(path, scenery)
						if raw != null: _put(path, raw, ORIGIN_MAIN)
					continue
				# Revalidate the current bytes/policy before publishing a worker record.
				var began := Time.get_ticks_usec()
				var verified := PreparedContent.acquire("scene", path, _source_sha(path, scenery),
					PreparedContent.scene_texture_token(path, scenery))
				_record_operation(&"prepared_completion_verify", began)
				if str(verified.status) == "hit":
					_put(path, verified.resource, ORIGIN_PREPARED)
					_prepared_entries[path] = verified.entry
				elif str(verified.status) == "miss":
					var raw := _build(path, scenery)
					if raw != null:
						_put(path, raw, ORIGIN_MAIN)
			else:
				_put(path, prepared, ORIGIN_WORKER)

## Prepares one actor glTF for `install_actor_prepared`, on any thread once
## GltfQuantization.ensure_registered() has run on the main thread. It parses
## and generates and never packs, so it waits for nothing on the main thread
## (see "Threads"). Returns {"path", "actor_images"} plus one of:
##   "root"      the generated scene, unowned and unpacked, with "stamp" (the
##               file's modification time and length when it was read);
##   "packed"    the editor's imported PackedScene (checkouts only);
##   "prepared"  the result of `prepare`, when prepared content or the geometry
##               cache serve this file (immutable resources, as today);
##   "error"     why nothing was prepared ("unregistered", "not_actor_document",
##               "retired", "parse_failed"); the main thread builds as today.
## "actor_images" is false under ELORIA_ACTOR_IMAGES=legacy, when an equipment
## parse waits for the main thread again. A record holding a root owns a Node:
## hand it to install_actor_prepared or discard_actor_prepared, exactly once.
## Several actor parses never run at once (one preparer thread).
static func prepare_actor(path: String) -> Dictionary:
	var canonical := _canonical_path(path)
	var record := {"path": canonical, "actor_images": false}
	# Main's registration also publishes the actor image switch: a worker reads
	# it only after that, never while main writes it.
	if not GltfQuantization.ensure_registered():
		record["error"] = "unregistered"
		return record
	record["actor_images"] = ActorImages.active()
	if not is_actor_document(canonical):
		record["error"] = "not_actor_document"
		return record
	if ArchivedModelPolicy.is_retired_path(canonical):
		record["error"] = "retired"
		return record
	if PreparedContent.selected_mode() != "raw" \
			or (not GeometryCache.cooking and GeometryCache.eligible("asset", canonical)):
		record["prepared"] = prepare(PackedStringArray([canonical]))
		return record
	if not GeometryCache.cooking:
		var imported := _imported_actor_scene(canonical)
		if imported != null:
			record["packed"] = imported
			return record
	record["stamp"] = _source_stamp(canonical)
	var root := _parse_generate(canonical, {}, true)
	if root == null:
		record["error"] = "parse_failed"
		return record
	record["root"] = root
	return record

## Main thread: publishes a `prepare_actor` record into the session cache and
## returns whether its path is cached afterwards. A raw root is packed here
## (a race scene packs in 1-2 ms on main, against about one main frame per
## mesh on a worker) and freed. A root whose file changed since it was read,
## whose browser file was retired, or whose path is already cached is freed
## unpublished; the cache keeps, or later builds, the current scene as today.
static func install_actor_prepared(record: Dictionary) -> bool:
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		push_error("glb cache: install_actor_prepared is main-thread only")
		return false
	var path := str(record.get("path", ""))
	if record.get("prepared") is Dictionary:
		install_prepared(record.prepared)
		return _scenes.has(path)
	var root := _take_root(record)
	var publish := not path.is_empty() and not _scenes.has(path) \
		and not (OS.has_feature("web") and not FileAccess.file_exists(path))
	if record.get("packed") is PackedScene:
		if publish:
			_put(path, record.packed, ORIGIN_IMPORTED)
			_failed.erase(path)
		return _scenes.has(path)
	if root == null:
		return _scenes.has(path)
	if not publish or record.get("stamp") != _source_stamp(path):
		root.free()
		return _scenes.has(path)
	var began := Time.get_ticks_usec()
	var packed := _pack_generated(path, root)
	_record_operation(&"actor_prepared_install", began)
	if packed == null:
		return false
	_put(path, packed, ORIGIN_WORKER)
	_failed.erase(path)
	return true

## Frees a record's unpublished root (a cancelled or stale job). Any thread;
## a second call does nothing.
static func discard_actor_prepared(record: Dictionary) -> void:
	var root := _take_root(record)
	if root != null:
		root.free()

static func _take_root(record: Dictionary) -> Node3D:
	var value: Variant = record.get("root")
	record.erase("root")
	if typeof(value) != TYPE_OBJECT or not is_instance_valid(value):
		return null
	return value as Node3D

## Whether `path` is an actor glTF: under ACTOR_ASSET_ROOT, in the same
## globalized form the cache keys use.
static func is_actor_document(path: String) -> bool:
	var canonical := _canonical_path(path)
	return not canonical.is_empty() and canonical.begins_with(_canonical_path(ACTOR_ASSET_ROOT)) \
		and not is_world_asset(canonical)

static func _source_stamp(path: String) -> Array:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return []
	var length := file.get_length()
	file.close()
	return [FileAccess.get_modified_time(path), length]

## Underground's synchronous Main arrival can bind each asset before opening
## the next, instead of retaining every asset's decoded Images simultaneously.
## Worker preparation/publication and non-geometry consumers keep their path.
## True means handled (individual failures retain the ordinary raw fallback).
static func prepare_bound_main(paths: PackedStringArray) -> bool:
	if OS.get_thread_caller_id() != OS.get_main_thread_id() or OS.get_environment(BOUND_MAIN_ENVIRONMENT) == "0" \
			or GeometryCache.cooking or OS.get_environment("ELORIA_NO_GEOMETRY_CACHE") == "1" \
			or not MapSceneCache.is_enabled() or PreparedContent.selected_mode() == "require-pilot": return false
	# Preflight before publishing anything, so an unrelated caller cannot partly
	# switch its preparation strategy merely by including one scoped asset.
	for path: String in paths:
		if not GeometryCache.eligible("asset",path): return false
	for source: String in paths:
		var path := _canonical_path(source)
		if not _scenes.has(path) and not _failed.has(path):
			var prepared := prepare(PackedStringArray([path]))
			install_prepared(prepared) # Full source/payload/current-entry revalidation.
			prepared.clear()
		var geometry: Dictionary = _geometry_entries.get(path,{})
		if geometry.is_empty(): continue
		# Installed worker completions retain their first-use revalidation.
		var verify_again := not bool(geometry.get("bound",false)) and not bool(geometry.get("prepared_on_main",false))
		if GeometryCache.bind(geometry,verify_again): continue
		_geometry_entries.erase(path)
		_erase_scene(path)
		var raw := _build(path)
		if raw != null: _put(path, raw, ORIGIN_MAIN)
	return true

## Returns the shared scene for `path`, or null when unavailable. Treat this
## scene and its subresources as immutable. Like instantiate(), call only on the
## main thread; worker preparation retains its separate build/publication path.
static func packed_scene(path: String) -> PackedScene:
	# Direct PackedScene callers own their legacy instantiate behavior. Never
	# expose a native template that requires the prepared lifecycle adapter.
	return _packed_scene(path, false)

static func _packed_scene(path: String, allow_prepared: bool) -> PackedScene:
	if ArchivedModelPolicy.is_retired_path(path):
		return null
	path = _canonical_path(path)
	if path.is_empty() or _failed.has(path):
		return null
	if _geometry_entries.has(path):
		if allow_prepared: return _scenes.get(path) as PackedScene
		var raw := _direct_raw_scenes.get(path) as PackedScene
		if raw == null:
			raw = _build(path)
			if raw != null: _direct_raw_scenes[path] = raw
		return raw
	# An installed in-memory template owns already verified immutable Resources.
	# Verify loose inputs for a new disk/cache acquisition, never per placement.
	var scenery: Dictionary = {}
	if not _scenes.has(path) or _prepared_entries.has(path):
		scenery = _scenery_inputs(path)
		if not scenery.is_empty() and not bool(scenery.get("ok", false)):
			return null
	if allow_prepared and not _scenes.has(path) and not GeometryCache.cooking \
			and PreparedContent.selected_mode() != "require-pilot" and GeometryCache.eligible("asset",path):
		var geometry := GeometryCache.acquire("asset",path,_source_sha(path, scenery),{},MapSceneCache.is_enabled())
		if str(geometry.status) == "hit":
			_put(path, geometry.resource, ORIGIN_GEOMETRY)
			_geometry_entries[path] = geometry
			return geometry.resource as PackedScene
	if allow_prepared and (PreparedContent.selected_mode() != "raw" or _prepared_entries.has(path)):
		var verification_began := Time.get_ticks_usec()
		var verified := PreparedContent.acquire("scene", path, _source_sha(path, scenery),
			PreparedContent.scene_texture_token(path, scenery))
		_record_operation(&"prepared_publication_verify", verification_began)
		if str(verified.status) == "hit":
			_put(path, verified.resource, ORIGIN_PREPARED)
			_prepared_entries[path] = verified.entry
		elif str(verified.status) == "reject":
			return null
		elif _prepared_entries.has(path):
			_prepared_entries.erase(path)
			_erase_scene(path)
	var packed: PackedScene = _scenes.get(path) as PackedScene
	_touch(path)
	if not allow_prepared and _prepared_entries.has(path):
		var raw := _direct_raw_scenes.get(path) as PackedScene
		if raw == null:
			raw = _build(path, scenery)
			if raw != null:
				_direct_raw_scenes[path] = raw
		return raw
	if packed == null:
		_lookup_misses += 1
		if _evicted.has(path):
			_evicted_main_rebuilds += 1
		var miss_began := Time.get_ticks_usec()
		packed = _build(path, scenery)
		_record_operation(&"cache_miss_build", miss_began, false)
		if packed == null:
			_failed[path] = true
			return null
		_put(path, packed, ORIGIN_MAIN)
	else:
		_lookup_hits += 1
	return packed

## The cached scene for `path` when it is the plain runtime glTF parse of that
## file: not imported, prepared, geometry-bound or given the world-object image
## pass. Null otherwise; never builds. Main thread, like the cache itself.
static func runtime_parse(path: String) -> PackedScene:
	path = _canonical_path(path)
	if is_world_asset(path) or _prepared_entries.has(path) or _geometry_entries.has(path):
		return null
	var packed := _scenes.get(path) as PackedScene
	if packed != null:
		_touch(path)
	return packed if packed != null and packed.resource_path.is_empty() else null

## Returns a fresh instance of `path`, or null when the file cannot be imported.
static func instantiate(path: String) -> Node3D:
	var packed := _packed_scene(path, true)
	if packed == null:
		return null
	var instantiate_began := Time.get_ticks_usec()
	var entry: Dictionary = _prepared_entries.get(_canonical_path(path), {})
	var instance: Node3D
	var geometry: Dictionary = _geometry_entries.get(_canonical_path(path),{})
	if not geometry.is_empty():
		instance = GeometryCache.instantiate(geometry,not bool(geometry.get("bound",false)) and not bool(geometry.get("prepared_on_main",false)))
		if instance == null:
			_geometry_entries.erase(_canonical_path(path))
			_erase_scene(_canonical_path(path))
			packed = _build(_canonical_path(path))
			if packed != null:
				_put(_canonical_path(path), packed, ORIGIN_MAIN)
				instance = packed.instantiate() as Node3D
	elif entry.is_empty():
		instance = packed.instantiate() as Node3D
	else:
		instance = PreparedLifecycle.instantiate({"status": "hit", "resource": packed, "entry": entry})
		if instance == null and PreparedContent.selected_mode() == "auto":
			_prepared_entries.erase(_canonical_path(path))
			packed = _build(_canonical_path(path))
			if packed != null:
				_put(_canonical_path(path), packed, ORIGIN_MAIN)
				instance = packed.instantiate() as Node3D
	_record_operation(&"scene_instantiate", instantiate_began)
	return instance

## Drops every cached scene. Call when leaving a session so the next map is not
## charged for models it no longer uses.
static func clear() -> void:
	_scenes.clear()
	_failed.clear()
	_prepared_entries.clear()
	_geometry_entries.clear()
	_direct_raw_scenes.clear()
	_ledger.clear()
	_domain_bytes.clear()
	_pending_rows = 0
	_evictable_rows = 0
	_evicted.clear()

## Drops `path` (exactly this key, in any spelling the cache accepts) from
## every table, as the RL head library does by erasing the dictionaries itself
## (rl_head_library.gd _forget_scene). Live instances keep their resources.
## Main thread. Not an eviction: `evicted(path)` stays false.
static func forget(path: String) -> void:
	var key := _canonical_path(path)
	_forget_key(key)
	_evicted.erase(key)

## Erases the cache key `key` (already canonical) from every table and the
## ledger: one lookup each, never a walk over the other entries.
static func _forget_key(key: String) -> void:
	for cache: Dictionary in [_scenes, _direct_raw_scenes, _failed, _prepared_entries, _geometry_entries]:
		cache.erase(key)
	_drop_row(key)

## Whether the budget evicted `path`'s scene (enforce_budget) and nothing has
## published it since. The creature warm-up asks this of a creature it once
## prepared, to prepare it again on its worker. Main thread.
static func evicted(path: String) -> bool:
	if _evicted.is_empty():
		return false
	var key := _canonical_path(path)
	return _evicted.has(key) and not _scenes.has(key)

## Forgets that `path` was evicted (a preparation that failed after one, so it
## is not asked for again on every request). Main thread.
static func clear_eviction(path: String) -> void:
	if not _evicted.is_empty():
		_evicted.erase(_canonical_path(path))

## The ledger domain of `path` (DOMAIN_*), from where it lives.
static func domain_of(path: String) -> String:
	var canonical := _canonical_path(path)
	if is_world_asset(canonical):
		return DOMAIN_WORLD
	if _domain_prefixes.is_empty():
		var built: Array = []
		for root: String in DOMAIN_ROOTS:
			built.append([_canonical_path(root), DOMAIN_ROOTS[root]])
		_domain_prefixes = built
	for prefix: Array in _domain_prefixes:
		if canonical.begins_with(str(prefix[0])):
			return str(prefix[1])
	return DOMAIN_OTHER

## This session's creature budget: MemoryBudgets' `creature_scene_bytes` for
## the machine's memory class.
static func creature_budget_bytes() -> int:
	return _test_budget_bytes if _test_budget_bytes >= 0 \
		else int(MemoryBudgets.value(MemoryBudgets.CREATURE_SCENE_BYTES))

## How long a creature entry must be idle before it may be evicted.
static func creature_idle_msec() -> int:
	return _test_idle_msec if _test_idle_msec >= 0 \
		else int(MemoryBudgets.value(MemoryBudgets.CREATURE_SCENE_IDLE_MSEC))

## Tests: replaces the creature budget and idle age (-1 restores the class's).
static func set_budget_for_tests(budget_bytes := -1, idle_msec := -1) -> void:
	_test_budget_bytes = budget_bytes
	_test_idle_msec = idle_msec

## Measured bytes of the ledger's `domain` rows (pending rows not included).
static func domain_bytes(domain: String) -> int:
	return int(_domain_bytes.get(domain, 0))

## One budget pass, on the main thread (anywhere else it does nothing): prunes
## ledger rows whose scene left the cache, measures pending rows for at most
## `fill_slice_usec`, notes which creature entries are idle, and when the
## creature domain is over its budget evicts idle entries unused for the idle
## age, least recently used first, down to EVICT_TO_FRACTION of the budget.
## `now_msec` (ticks; < 0: now) is for tests. Returns {"evicted",
## "evicted_bytes", "skipped", "creature_bytes" (after), "budget",
## "idle_candidates"}.
static func enforce_budget(now_msec := -1, fill_slice_usec := LEDGER_FILL_SLICE_USEC) -> Dictionary:
	var report := {"evicted": 0, "evicted_bytes": 0, "skipped": 0,
		"creature_bytes": domain_bytes(DOMAIN_CREATURE), "budget": -1, "idle_candidates": 0}
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return report
	var began := Time.get_ticks_usec()
	_budget_passes += 1
	var now := Time.get_ticks_msec() if now_msec < 0 else now_msec
	_prune_ledger()
	if fill_slice_usec > 0 and _pending_rows > 0:
		_fill_pending(fill_slice_usec)
	var budget := creature_budget_bytes()
	var idle_age := creature_idle_msec()
	report.budget = budget
	var candidates: Array = []
	if _evictable_rows > 0:
		for path: String in _ledger:
			var row: Dictionary = _ledger[path]
			if not bool(row.evictable):
				continue
			if _is_busy(row):
				# Held by a live instance is a use: least recently used means
				# the entry whose last holder went first, not the one first
				# instantiated longest ago.
				row.last_used_msec = maxi(int(row.last_used_msec), now)
				row.idle_since_msec = 0
				continue
			# Seen idle for the first time: it counts from now (a conservative
			# start, at most one pass late), never from its last use.
			if int(row.idle_since_msec) <= 0:
				row.idle_since_msec = now
			if now - int(row.idle_since_msec) >= idle_age:
				candidates.append([int(row.last_used_msec), path])
	report.idle_candidates = candidates.size()
	var total := domain_bytes(DOMAIN_CREATURE)
	if total > budget and not candidates.is_empty():
		candidates.sort_custom(func(a: Array, b: Array) -> bool:
			return int(a[0]) < int(b[0]) if int(a[0]) != int(b[0]) else str(a[1]) < str(b[1]))
		var target := int(budget * EVICT_TO_FRACTION)
		for candidate: Array in candidates:
			if total <= target:
				break
			var path: String = candidate[1]
			# Its library goes with it; an importer still prewarming the file
			# is never joined: the entry waits for a later pass. Asked first,
			# because release_sources() drops the file's libraries even when
			# it then reports the live prewarm, and a skipped entry must keep
			# its libraries with its scene.
			if _library_prewarm_alive(path) \
					or not NativeAnimationImporter.release_sources(PackedStringArray([path])):
				report.skipped += 1
				_eviction_skips += 1
				continue
			var row_bytes := maxi(0, int((_ledger.get(path, {}) as Dictionary).get("bytes", 0)))
			# The row's key is the entry's own key (a worker publication).
			_forget_key(path)
			_evicted[path] = true
			_evictions += 1
			_evicted_bytes += row_bytes
			total -= row_bytes
			report.evicted += 1
			report.evicted_bytes += row_bytes
	report.creature_bytes = domain_bytes(DOMAIN_CREATURE)
	_record_operation(&"budget_pass", began)
	return report

## Whether NativeAnimationImporter is still parsing `path` as an animation
## library on a prewarm thread (any spelling of the file). Read only, main
## thread, where the importer keeps its prewarm threads.
static func _library_prewarm_alive(path: String) -> bool:
	var prewarming: Dictionary = NativeAnimationImporter._prewarming
	if prewarming.is_empty():
		return false
	var key := _file_key(path)
	for source: String in prewarming:
		if _file_key(source) == key and (prewarming[source] as Thread).is_alive():
			return true
	return false

## Publishes `scene` for `path` (canonical) with its ledger row.
static func _put(path: String, scene: Variant, origin: String) -> void:
	_scenes[path] = scene
	_note_published(path, scene, origin)

## Removes `path` (canonical) from the scenes and the ledger.
static func _erase_scene(path: String) -> void:
	_scenes.erase(path)
	_drop_row(path)

## A publication's ledger row. Off the main thread (no caller today) the row
## is left to the next pass's pruning, as ORIGIN_UNKNOWN.
static func _note_published(path: String, scene: Variant, origin: String) -> void:
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return
	_evicted.erase(path)
	var row := _add_row(path, scene, origin)
	if row.is_empty():
		return
	if str(row.domain) == DOMAIN_CREATURE:
		# Measured now: the budget reads it. Probes and their baseline are
		# taken with no instance alive (callers publish before instantiating).
		_fill_row(path, row)
		if bool(row.evictable):
			row.baseline = _probe_counts(row.probes)
			if domain_bytes(DOMAIN_CREATURE) > creature_budget_bytes():
				enforce_budget(-1, 0)
	_arm_budget_timer()

static func _add_row(path: String, scene: Variant, origin: String) -> Dictionary:
	_drop_row(path)
	var packed := scene as PackedScene
	if packed == null:
		return {}
	var now := Time.get_ticks_msec()
	var domain := domain_of(path)
	var row := {"bytes": -1, "mesh_bytes": 0, "texture_bytes": 0, "domain": domain, "origin": origin,
		"evictable": domain == DOMAIN_CREATURE and origin == ORIGIN_WORKER and packed.resource_path.is_empty(),
		"scene_id": packed.get_instance_id(), "probes": [], "baseline": PackedInt32Array(),
		"published_msec": now, "last_used_msec": now, "idle_since_msec": 0}
	_ledger[path] = row
	_pending_rows += 1
	if bool(row.evictable):
		_evictable_rows += 1
	return row

static func _drop_row(path: String) -> void:
	var row: Dictionary = _ledger.get(path, {})
	if row.is_empty():
		return
	if int(row.bytes) < 0:
		_pending_rows -= 1
	else:
		var domain := str(row.domain)
		_domain_bytes[domain] = int(_domain_bytes.get(domain, 0)) - int(row.bytes)
		if int(_domain_bytes[domain]) <= 0:
			_domain_bytes.erase(domain)
	if bool(row.evictable):
		_evictable_rows -= 1
	_ledger.erase(path)

## Measures `row` (ResourceBytes, no read-back) and, for an evictable row,
## keeps WeakRefs to the scene's meshes as its probes.
static func _fill_row(path: String, row: Dictionary) -> void:
	var scene := _scenes.get(path) as PackedScene
	if scene == null or scene.get_instance_id() != int(row.scene_id) or int(row.bytes) >= 0:
		return
	var walked := ResourceBytes.scene_resources(scene, _texture_mipmaps(path, scene))
	row.mesh_bytes = int(walked.mesh_bytes)
	row.texture_bytes = int(walked.texture_bytes)
	row.bytes = int(walked.bytes)
	_pending_rows -= 1
	var domain := str(row.domain)
	_domain_bytes[domain] = int(_domain_bytes.get(domain, 0)) + int(row.bytes)
	if bool(row.evictable):
		var probes: Array[WeakRef] = []
		for mesh: Mesh in walked.meshes:
			probes.append(weakref(mesh))
		row.probes = probes

## Mip chains the ledger counts for a scene's ImageTextures: none for an actor
## document's runtime parse from a directory without sidecars (actor_images.gd,
## like GLTFDocument, decodes embedded images without mips; imported URI
## textures read their own header), the full chain otherwise (erring high: a
## directory with a sidecar index mixes BC sidecars, which have their chain,
## with decoded images, which do not; ActorImages.may_have_mipmaps).
static func _texture_mipmaps(path: String, scene: PackedScene) -> int:
	return ResourceBytes.MIPMAPS_NONE if scene.resource_path.is_empty() and is_actor_document(path) \
		and not ActorImages.may_have_mipmaps(path.get_base_dir()) else ResourceBytes.MIPMAPS_UNKNOWN

## Measures pending rows for about `slice_usec` (a row is never split).
static func _fill_pending(slice_usec: int) -> void:
	var began := Time.get_ticks_usec()
	for path: String in _ledger.keys():
		if Time.get_ticks_usec() - began >= slice_usec:
			return
		var row: Dictionary = _ledger[path]
		if int(row.bytes) < 0:
			_fill_row(path, row)

## Drops rows whose scene left the cache or was replaced without a
## publication, and adds rows (ORIGIN_UNKNOWN, never evictable) for scenes the
## cache holds without one.
static func _prune_ledger() -> void:
	for path: String in _ledger.keys():
		var scene: Variant = _scenes.get(path)
		if typeof(scene) != TYPE_OBJECT or not is_instance_valid(scene) \
				or (scene as Object).get_instance_id() != int(_ledger[path].scene_id):
			_drop_row(path)
	if _ledger.size() < _scenes.size():
		for path: String in _scenes:
			if not _ledger.has(path):
				_add_row(path, _scenes[path], ORIGIN_UNKNOWN)

## Whether anything beyond the cache holds `row`'s scene: a probe mesh whose
## reference count is above its count at publication. A row without probes
## is never idle.
static func _is_busy(row: Dictionary) -> bool:
	var probes: Array = row.probes
	var baseline: PackedInt32Array = row.baseline
	if probes.is_empty() or baseline.size() != probes.size():
		return true
	var counts := _probe_counts(probes)
	for index: int in counts.size():
		if counts[index] > baseline[index]:
			return true
	return false

## Reference counts of `probes`' meshes (-1 for one already freed), each read
## the same way at publication and at every pass, so the reader's own
## reference cancels out.
static func _probe_counts(probes: Array) -> PackedInt32Array:
	var counts := PackedInt32Array()
	counts.resize(probes.size())
	for index: int in probes.size():
		counts[index] = _probe_count(probes[index] as WeakRef)
	return counts

static func _probe_count(probe: WeakRef) -> int:
	var held: Variant = probe.get_ref() if probe != null else null
	return (held as RefCounted).get_reference_count() if held is RefCounted else -1

## An instance or a direct use of `path`'s entry: it is in use now.
static func _touch(path: String) -> void:
	var row: Variant = _ledger.get(path)
	if row != null and bool(row.evictable):
		row.last_used_msec = Time.get_ticks_msec()
		row.idle_since_msec = 0

static func _arm_budget_timer() -> void:
	if _budget_timer_armed or _ledger.is_empty() or OS.get_thread_caller_id() != OS.get_main_thread_id():
		return
	var tree := Engine.get_main_loop() as SceneTree
	if tree == null:
		return
	_budget_timer_armed = true
	tree.create_timer(BUDGET_PASS_SECONDS, true, false, true).timeout.connect(_budget_tick)

static func _budget_tick() -> void:
	_budget_timer_armed = false
	enforce_budget()
	_arm_budget_timer()

static func cached_scene_count() -> int:
	return _scenes.size() + _direct_raw_scenes.size()

static func _file_key(path: String) -> String:
	var value := _canonical_path(path)
	if value.begins_with("res://"): value = value.trim_prefix("res://")
	if not value.is_absolute_path(): value = "/".path_join(value)
	return value.simplify_path()

## Main-thread retirement of memoized templates, not their live instances.
static func release_sources(paths: PackedStringArray) -> void:
	var wanted := {}
	for path: String in paths: wanted[_file_key(path)] = true
	for cache: Dictionary in [_scenes, _direct_raw_scenes, _failed, _prepared_entries, _geometry_entries]:
		for source: String in cache.keys():
			if wanted.has(_file_key(source)): cache.erase(source)
	for source: String in _ledger.keys():
		if not _scenes.has(source): _drop_row(source)

## Read on the main thread, where cache publication/clearing already lives.
## Worker builds only update timing data behind the separate mutex. Counts do
## not attempt expensive resource walks: the byte figures are the ledger's
## running totals (ResourceBytes estimates, not measured allocations; rows
## still waiting to be measured are counted in "pending_rows", not in bytes).
## "budget", "idle_msec" and "evictions" concern the creature domain, the one
## that is evicted.
static func retention_snapshot() -> Dictionary:
	_diagnostics_mutex.lock()
	var timings := ResourceDiagnostics.snapshot(_resource_timings)
	_diagnostics_mutex.unlock()
	var total := 0
	for domain: String in _domain_bytes:
		total += int(_domain_bytes[domain])
	return {"strong_scene_entries": _scenes.size() + _direct_raw_scenes.size(),
		"direct_raw_scene_entries": _direct_raw_scenes.size(), "failed_paths": _failed.size(),
		"lookup_hits": _lookup_hits, "lookup_misses": _lookup_misses,
		"bytes_estimate_available": true, "timings": timings,
		"actor_images": ActorImages.retention_snapshot(),
		"entries": _scenes.size(), "bytes": total, "bytes_by_domain": _domain_bytes.duplicate(),
		"pending_rows": _pending_rows, "budget_domain": DOMAIN_CREATURE,
		"budget": creature_budget_bytes(), "idle_msec": creature_idle_msec(),
		"evictable_entries": _evictable_rows, "evictions": _evictions, "evicted_bytes": _evicted_bytes,
		"eviction_skips": _eviction_skips, "evicted_awaiting": _evicted.size(),
		"evicted_main_rebuilds": _evicted_main_rebuilds, "budget_passes": _budget_passes}

static func _record_operation(operation: StringName, started: int, atomic := true) -> void:
	var elapsed := Time.get_ticks_usec() - started
	_diagnostics_mutex.lock()
	ResourceDiagnostics.record_elapsed(_resource_timings, operation, elapsed, atomic)
	_diagnostics_mutex.unlock()

static func _canonical_path(path: String) -> String:
	# Export templates may globalize res:// to a relative name. Scenery's
	# external file closure is rooted beside the executable, independent of cwd.
	if path.begins_with(WORLD_ASSET_ROOT):
		return PreparedContent._runtime_absolute(path)
	return ProjectSettings.globalize_path(path) if path.begins_with("res://") else path

static func _scenery_inputs(path: String) -> Dictionary:
	if not is_world_asset(path): return {}
	var began := Time.get_ticks_usec()
	var verified := SceneryImages.verify(path)
	_record_operation(&"scenery_source_verify", began)
	if not bool(verified.get("ok", false)):
		push_error("scenery image source rejected: %s (%s)" % [path, str(verified.get("error", "invalid"))])
	return verified

static func _source_sha(path: String, scenery: Dictionary) -> String:
	return str(scenery.source_sha256) if not scenery.is_empty() and scenery.get("source_sha256") is String \
		else CreaturePayload.source_sha256(path)

static func _build(path: String, scenery: Dictionary = {}) -> PackedScene:
	if ArchivedModelPolicy.is_retired_path(path):
		return null
	if is_world_asset(path) and scenery.is_empty(): scenery = _scenery_inputs(path)
	if not scenery.is_empty() and not bool(scenery.get("ok", false)): return null
	if GeometryCache.cooking: return _build_raw(path, scenery)
	var imported := _imported_actor_scene(path)
	if imported != null:
		return imported
	return _build_raw(path, scenery)

## ResourceLoader resolves the `.import` remap in an editor checkout and the
## equivalent remap in an exported PCK. Restricting this preference to actor
## assets leaves the world-authoring cache's external-file semantics unchanged.
static func _imported_actor_scene(path: String) -> PackedScene:
	var resource_path := ProjectSettings.localize_path(path)
	if not resource_path.begins_with("res://assets/actors/"):
		return null
	var extension := resource_path.get_extension().to_lower()
	if extension != "glb" and extension != "gltf":
		return null
	if OS.has_feature("editor"):
		if _editor_import_path(resource_path).is_empty():
			return null
	if not ResourceLoader.exists(resource_path, "PackedScene"):
		return null
	var began := Time.get_ticks_usec()
	var imported := ResourceLoader.load(resource_path, "PackedScene",
		ResourceLoader.CACHE_MODE_REUSE) as PackedScene
	_record_operation(&"imported_scene_read", began)
	return imported

## An ignored loose-native folder can retain import files from an older
## checkout. ResourceLoader still follows those remaps, even though an editor
## scan now excludes their source. Honor the active folder policy first.
## Kept separate from the actor whitelist for small ignored import fixtures.
static func _editor_import_path(resource_path: String) -> String:
	var directory := resource_path.get_base_dir()
	while directory.begins_with("res://") or directory.begins_with("user://"):
		if FileAccess.file_exists(directory.path_join(".gdignore")):
			return ""
		if directory in ["res://", "user://"]: break
		var parent := directory.get_base_dir()
		if parent == directory: break
		directory = parent
	# ResourceLoader.exists() also accepts skipped or unfinished editor imports.
	var import_settings := ConfigFile.new()
	if import_settings.load(resource_path + ".import") != OK \
			or str(import_settings.get_value("remap", "importer", "")) != "scene":
		return ""
	var imported_path := str(import_settings.get_value("remap", "path", ""))
	return imported_path if not imported_path.is_empty() and FileAccess.file_exists(imported_path) else ""

static func _build_raw(path: String, scenery: Dictionary = {}) -> PackedScene:
	var generated := _parse_generate(path, scenery, is_actor_document(path))
	return _pack_generated(path, generated) if generated != null else null

## The one runtime glTF parse, shared by `_build_raw` (main) and
## `prepare_actor` (any thread): the file's generated scene, unowned and
## unpacked, or null. An actor document gets the actor image extension, whose
## sidecars and shared textures (AT-C2) are in place when the parse returns,
## on either path; a world asset its image pass. Steps that change the parsed
## state for both paths after the parse (ALOD-C1h's cooked geometry) go here,
## before generate_scene().
static func _parse_generate(path: String, scenery: Dictionary, actor_document: bool) -> Node3D:
	if not GltfQuantization.ensure_registered():
		push_error("raw glTF parse requires main-thread extension initialization")
		return null
	var document: GLTFDocument = GLTFDocument.new()
	var state: GLTFState = GLTFState.new()
	var world_asset := is_world_asset(path)
	if world_asset:
		if scenery.is_empty(): scenery = _scenery_inputs(path)
		if not bool(scenery.get("ok", false)): return null
		state.set_additional_data(WorldObjectImages.ENABLED, true)
		state.set_additional_data(SceneryImages.VERIFIED_KEY, scenery)
	elif actor_document:
		ActorImages.enable(state, path)
	var operation_began := Time.get_ticks_usec()
	var parse_error: Error
	if world_asset and scenery.get("bytes") is PackedByteArray:
		state.filename = path.get_file().get_basename()
		parse_error = document.append_from_buffer(scenery.bytes, path.get_base_dir().trim_suffix("/") + "/", state)
	else:
		parse_error = CreaturePayload.append(document, path, state)
	# Texture extension jobs are complete; do not retain a second source blob.
	state.set_additional_data(SceneryImages.VERIFIED_KEY, null)
	scenery = {}
	_record_operation(&"gltf_parse", operation_began)
	if parse_error != OK or (world_asset and WorldObjectImages.has_source_errors(state)):
		return null
	if world_asset and int(state.get_additional_data(WorldObjectImages.PREPARED)) < state.get_images().size():
		build_texture_mipmaps(state)
	var early_filter := world_asset and OS.get_environment(EARLY_WORLD_FILTER_ENVIRONMENT) != "0" and MapMaterialPreparation.enabled()
	if early_filter: MapMaterialPreparation.prepare(state)
	GeometrySources.note(state,path)
	operation_began = Time.get_ticks_usec()
	var generated: Node = document.generate_scene(state, GltfAnimationFidelity.bake_fps(state))
	_record_operation(&"gltf_generate_scene", operation_began)
	if generated == null:
		return null
	if generated is not Node3D:
		generated.free()
		return null
	if world_asset:
		_filter_anisotropic(generated,early_filter)
	return generated as Node3D

## Packs a `_parse_generate` root and frees it. On a worker pack() waits for
## the main thread about once per mesh (see "Threads"): `prepare` accepts
## that, `install_actor_prepared` packs on main instead.
static func _pack_generated(path: String, generated: Node3D) -> PackedScene:
	_claim(generated, generated)
	var packed: PackedScene = PackedScene.new()
	var operation_began := Time.get_ticks_usec()
	var packed_error: Error = packed.pack(generated)
	_record_operation(&"scene_pack", operation_began)
	operation_began = Time.get_ticks_usec()
	generated.free()
	_record_operation(&"temporary_scene_free", operation_began)
	if packed_error != OK:
		push_warning("glb cache: pack failed for %s (%s)" % [
			path, error_string(packed_error)])
		return null
	return packed

static func is_world_asset(path: String) -> bool:
	return _canonical_path(path).begins_with(_canonical_path(WORLD_ASSET_ROOT))

## Gives every image the state carries a mip chain. The images are the objects
## the generated materials will reference, so this must run before
## generate_scene(). Returns how many images were rebuilt.
static func build_texture_mipmaps(state: GLTFState) -> int:
	var rebuilt := 0
	for texture_value: Variant in state.get_images():
		var texture: ImageTexture = texture_value as ImageTexture
		if texture == null:
			continue
		var image: Image = texture.get_image()
		if image == null or image.is_empty() or image.has_mipmaps():
			continue
		if image.is_compressed() and image.decompress() != OK:
			continue
		image.generate_mipmaps()
		texture.set_image(image)
		rebuilt += 1
	return rebuilt

static func _filter_anisotropic(root: Node, early_filter := false) -> void:
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh: Mesh = (node as MeshInstance3D).mesh
		if mesh == null:
			continue
		for surface: int in range(mesh.get_surface_count()):
			var material := mesh.surface_get_material(surface) as BaseMaterial3D
			# Either opt-out restores the old unconditional late setter, so timing
			# controls include its shader-dirty ordering as well as its final value.
			if material != null and (not early_filter or material.texture_filter != MapMaterialPreparation.FILTER):
				material.texture_filter = MapMaterialPreparation.FILTER

# PackedScene.pack() only stores nodes owned by the packed root.
static func _claim(node: Node, scene_owner: Node) -> void:
	for child: Node in node.get_children():
		child.owner = scene_owner
		_claim(child, scene_owner)
