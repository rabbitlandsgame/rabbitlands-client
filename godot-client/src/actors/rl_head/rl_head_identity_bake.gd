class_name RLHeadIdentityBake
extends RefCounted
## The RL head's identity baked into cached meshes, one per distinct face.
##
## Identity is up to 42 `id_` blend shapes (21 controls, each _p or _n) on the
## head, its beard and its hair, plus the hairstyle's `hl_` hair shapes. Drawn
## live, every non-zero weight is deformed again each frame the skeleton
## moves: in the Compatibility renderer that is one transform-feedback pass per
## weight per surface, which made a 40- and 160-Human crowd 2.9-3.4x slower
## than develop's High head (.local/rl-high/gate, 2026-10-28). A face's
## identity only changes with its appearance, so it is baked once instead: for
## one source mesh (a part at one level of detail, for one sex or style) and
## its quantised identity weights, an ArrayMesh whose vertices, normals and
## tangents have those weights added in, carrying only the shapes still driven
## live (the expression's `ex_` shapes, offset to the baked face), the
## source's materials, surface names and generated index LODs. Every actor
## showing the same face at the same level shares that mesh.
##
## Work is spread so no frame pays for much of it, driven by one per-frame
## callback while anything is pending:
##   * a request waits BAKE_DELAY_MSEC first, so a face that changes again at
##     once (the creation preview rebuilds per debounced slider step) or an
##     actor that leaves at once never bakes;
##   * a source mesh's arrays are read on the main thread once (at most one
##     source a frame) and reduced to sparse per-shape deltas on the
##     WorkerThreadPool (most shapes move a small part of the mesh);
##   * each bake runs on the WorkerThreadPool; its ArrayMesh is built on the
##     main thread, within FINISH_BUDGET_USEC a frame, and every node waiting
##     for it is called back.
## Until then, and whenever a bake cannot be had (the budget below is spent by
## meshes in use, or RL_HEAD_BAKE switches it off), the rig keeps drawing the
## live blend shapes exactly as before: the same silhouette, only dearer.
##
## Bounded: entries count their users (mesh nodes showing them). An entry no
## longer shown is kept for reuse among the IDLE_KEEP most recently released,
## within IDLE_BYTES; beyond that, or beyond BUDGET_BYTES of baked mesh data in
## all, the oldest idle entries go, and a request nobody wants any more before
## its bake started is dropped. Source data stays while any RL head is drawn
## and goes with the rest of RLHeadLibrary's caches.
##
## Where it bakes: by default only in the Compatibility renderer, where the
## live shapes are the cost (with the bake a 40/160-Human crowd fell from
## 3.9x/3.2x to 1.4x develop's High frame time). Forward+ deforms them in one
## compute pass and measured no gain (within noise) while the cache would hold
## up to BUDGET_BYTES more, so it draws live. RL_HEAD_BAKE=1 (`on`) bakes in
## every renderer and `0` (`off`, `live`) in none, for A/B checks.

## Weight resolution of the cache key (and of the baked weights): faces closer
## than this share a mesh. Identity shapes move a vertex at most a few
## centimetres, so the rounding moves it well under 1e-5 m.
const QUANTUM := 1.0 / 8192.0
## Estimated bytes of baked mesh data kept (in use and idle together).
const BUDGET_BYTES := 192 * 1024 * 1024
## Idle entries (shown by nobody) kept for reuse, most recently released first.
const IDLE_KEEP := 48
const IDLE_BYTES := 48 * 1024 * 1024
## A request waits this long before its bake starts.
const BAKE_DELAY_MSEC := 400
## Main-thread time a frame may spend building finished meshes (at least one).
const FINISH_BUDGET_USEC := 3000
## A shape moves a vertex when its position, normal or tangent changes by more
## than this; the rest are left out of the sparse deltas.
const MOVE_EPSILON := 1e-7

## Surfaces a still bake leaves out (see `acquire`): the teeth and tongue, which
## a closed mouth hides; in the Compatibility renderer the cornea's glossy shell
## too (still_dropped_materials), whose highlight is a pixel at the distances
## still faces are drawn there (beyond the 4 expressive faces within 4 m).
const STILL_DROPPED_MATERIALS: Array[String] = ["rl_mouth"]
const COMPATIBILITY_STILL_DROPPED_MATERIALS: Array[String] = ["rl_mouth", "rl_cornea"]

## Bake on the calling thread at once (tests and evidence renders), instead of
## after BAKE_DELAY_MSEC on the WorkerThreadPool with a callback.
static var synchronous := false
## BUDGET_BYTES, lowered by tests.
static var budget_bytes := BUDGET_BYTES

static var _switch := -1
static var _still_switch := -1
## Source mesh instance id -> {"source", "state": "fetch"|"prepare"|"ready",
## "task", "raw" (fetched arrays), "data" (sparse, once ready)}.
static var _sources: Dictionary = {}
static var _entries: Dictionary = {}
static var _idle: Array[String] = []
static var _bytes := 0
static var _idle_bytes := 0
static var _polling := false
static var _baked_count := 0


## Whether identities are baked (RL_HEAD_BAKE, read once per session, else
## the renderer: see the class notes).
static func enabled() -> bool:
	if _switch < 0:
		var value := OS.get_environment("RL_HEAD_BAKE").strip_edges().to_lower()
		if value in ["0", "off", "no", "false", "live"]:
			_switch = 0
		elif value in ["1", "on", "yes", "true", "all"]:
			_switch = 1
		else:
			_switch = 1 if RenderingServer.get_current_rendering_method() == "gl_compatibility" else 0
	return _switch == 1


## Whether faces that show no expression are drawn from still bakes - identity
## in, no live shapes, no mouth - in every renderer, whatever `enabled` says:
## every level of a face outside the few drawing their expressions, every
## level after a part's first (beyond 10 m at High), and every hair level
## (hair has no live shapes; RLHeadRig.MAX_EXPRESSIVE). Drawn still, a face
## deforms nothing per frame beyond its skinning and draws one surface fewer.
## RL_HEAD_STILL (`1`/`0`) forces it, read once per session.
static func still_enabled() -> bool:
	if _still_switch < 0:
		var value := OS.get_environment("RL_HEAD_STILL").strip_edges().to_lower()
		_still_switch = 0 if value in ["0", "off", "no", "false"] else 1
	return _still_switch == 1


## Reads RL_HEAD_BAKE and RL_HEAD_STILL again on the next check (tests switch them).
static func reload_switch() -> void:
	_switch = -1
	_still_switch = -1


## Whether a blend shape is baked (identity and hair shapes) rather than kept live.
static func is_baked_shape(shape: String) -> bool:
	return shape.begins_with("id_") or shape.begins_with("hl_")


## Whether `source` keeps any shape live in a bake (an `ex_` expression shape).
static func keeps_live_shapes(source: Mesh) -> bool:
	if source == null:
		return false
	for index: int in source.get_blend_shape_count():
		if not is_baked_shape(str(source.get_blend_shape_name(index))):
			return true
	return false


## Whether `source` has anything to bake.
static func has_baked_shapes(source: Mesh) -> bool:
	if source == null:
		return false
	for index: int in source.get_blend_shape_count():
		if is_baked_shape(str(source.get_blend_shape_name(index))):
			return true
	return false


## The cache key of `source` with `weights` (blend-shape name -> weight; any
## shape not named is 0): the source's identity, the quantised weights and
## whether the bake is still.
static func key(source: Mesh, weights: Dictionary, still: bool = false) -> String:
	var codes := PackedStringArray()
	for index: int in source.get_blend_shape_count():
		var shape := str(source.get_blend_shape_name(index))
		if not is_baked_shape(shape):
			continue
		var code := roundi(float(weights.get(shape, 0.0)) / QUANTUM)
		if code != 0:
			codes.append("%d:%d" % [index, code])
	return "%d|%s%s" % [source.get_instance_id(), ",".join(codes), "|still" if still else ""]


## The baked mesh for `source` and `weights`, counted as one more user. When
## it is not ready yet, null: `on_ready` is called with it later (the user is
## counted already; release it as for a mesh). Null and not counted (`holds`
## is false) when nothing can be baked now: the switch is off, the source has
## no identity shapes, or the budget is spent by meshes in use. Draw live then.
## A `still` bake keeps no live shapes at all and leaves out
## still_dropped_materials (see still_enabled): its mesh can have
## fewer surfaces than its source.
static func acquire(source: ArrayMesh, weights: Dictionary, on_ready: Callable = Callable(),
		still: bool = false) -> ArrayMesh:
	if source == null or not has_baked_shapes(source) or not (enabled() or (still and still_enabled())):
		return null
	var entry_key := key(source, weights, still)
	var entry: Dictionary = _entries.get(entry_key, {})
	if not entry.is_empty():
		if int(entry["users"]) == 0:
			_idle.erase(entry_key)
			_idle_bytes -= int(entry["bytes"])
		entry["users"] = int(entry["users"]) + 1
		if entry["mesh"] != null:
			return entry["mesh"] as ArrayMesh
		if on_ready.is_valid():
			(entry["waiters"] as Array).append(on_ready)
		return null
	_evict_idle(IDLE_KEEP, IDLE_BYTES)
	if _bytes >= budget_bytes:
		return null
	entry = {"key": entry_key, "source": source, "weights": weights.duplicate(), "mesh": null, "users": 1,
		"bytes": 0, "waiters": [], "task": -1, "result": [], "still": still,
		"due": Time.get_ticks_msec() + BAKE_DELAY_MSEC}
	_entries[entry_key] = entry
	if synchronous:
		var data := _ready_source(source)
		entry["bytes"] = int(data["still_bytes" if still else "bytes"])
		_bytes += int(entry["bytes"])
		entry["result"] = compute(data, _vector(data, weights), not still)
		_finish(entry)
		return entry["mesh"] as ArrayMesh
	# Counted against the budget at once, so a burst of requests stops at it.
	entry["bytes"] = _estimate(source, still)
	_bytes += int(entry["bytes"])
	if on_ready.is_valid():
		(entry["waiters"] as Array).append(on_ready)
	_start_polling()
	return null


## Whether the cache has an entry for `entry_key` (ready or pending).
static func holds(entry_key: String) -> bool:
	return _entries.has(entry_key)


## One user fewer of the entry `entry_key` names (as `key` gave it). A baked
## entry nobody shows is kept idle for reuse, within IDLE_KEEP, IDLE_BYTES and
## the budget; one whose bake has not started is dropped.
static func release(entry_key: String) -> void:
	var entry: Dictionary = _entries.get(entry_key, {})
	if entry.is_empty() or int(entry["users"]) == 0:
		return
	entry["users"] = int(entry["users"]) - 1
	if int(entry["users"]) > 0:
		return
	if entry["mesh"] == null and int(entry["task"]) < 0:
		_drop(entry)
		return
	_idle.append(entry_key)
	_idle_bytes += int(entry["bytes"])
	_evict_idle(IDLE_KEEP, IDLE_BYTES)


## Completes every pending bake now and calls back its waiters (tests).
static func flush() -> void:
	for entry: Dictionary in _entries.values().duplicate():
		if entry["mesh"] != null or not _entries.has(str(entry["key"])):
			continue
		if int(entry["task"]) >= 0:
			WorkerThreadPool.wait_for_task_completion(int(entry["task"]))
			entry["task"] = -1
		else:
			var data := _ready_source(entry["source"] as ArrayMesh)
			entry["result"] = compute(data, _vector(data, entry["weights"] as Dictionary), not bool(entry["still"]))
		_finish(entry)


## Drops every entry and source (RLHeadLibrary.release_unused, with no RL head
## left). A bake still running finishes into nothing.
static func clear() -> void:
	for entry: Dictionary in _entries.values():
		if int(entry["task"]) >= 0:
			WorkerThreadPool.wait_for_task_completion(int(entry["task"]))
		if entry["mesh"] != null:
			RLHeadRig.forget_mesh(entry["mesh"] as Mesh)
	for source: Dictionary in _sources.values():
		if int(source.get("task", -1)) >= 0:
			WorkerThreadPool.wait_for_task_completion(int(source["task"]))
	_entries.clear()
	_idle.clear()
	_sources.clear()
	_bytes = 0
	_idle_bytes = 0


## What the cache holds, for diagnostics and the budget evidence.
static func describe() -> Dictionary:
	var users := 0
	var ready := 0
	for entry: Dictionary in _entries.values():
		users += int(entry["users"])
		ready += 1 if entry["mesh"] != null else 0
	return {"enabled": enabled(), "entries": _entries.size(), "ready": ready, "idle": _idle.size(),
		"idle_bytes": _idle_bytes, "users": users, "bytes": _bytes, "budget_bytes": budget_bytes,
		"sources": _sources.size(), "baked_total": _baked_count}


# ---------------------------------------------------------------- internals

static func _drop(entry: Dictionary) -> void:
	var entry_key := str(entry["key"])
	if _entries.get(entry_key) != entry:
		return
	if int(entry["task"]) >= 0:
		WorkerThreadPool.wait_for_task_completion(int(entry["task"]))
		entry["task"] = -1
	if int(entry["users"]) == 0 and _idle.has(entry_key):
		_idle.erase(entry_key)
		_idle_bytes -= int(entry["bytes"])
	_bytes -= int(entry["bytes"])
	_entries.erase(entry_key)
	if entry["mesh"] != null:
		RLHeadRig.forget_mesh(entry["mesh"] as Mesh)


static func _evict_idle(keep: int, keep_bytes: int) -> void:
	while not _idle.is_empty() and (_idle.size() > keep or _idle_bytes > keep_bytes or _bytes > budget_bytes):
		var oldest: String = _idle[0]
		var entry: Dictionary = _entries.get(oldest, {})
		if entry.is_empty() or int(entry["users"]) > 0:
			_idle.pop_front()
			continue
		_drop(entry)


static func _start_polling() -> void:
	if _polling:
		return
	var tree := Engine.get_main_loop() as SceneTree
	if tree == null:
		flush()
		return
	_polling = true
	tree.process_frame.connect(_poll)


## One frame of the pipeline: sources to fetch (one a frame) and prepare,
## due requests to start, finished bakes to build within the frame's budget.
static func _poll() -> void:
	var pending := false
	var fetched := false
	var now := Time.get_ticks_msec()
	for source: Dictionary in _sources.values():
		if str(source["state"]) == "prepare" and WorkerThreadPool.is_task_completed(int(source["task"])):
			WorkerThreadPool.wait_for_task_completion(int(source["task"]))
			source["task"] = -1
			source["state"] = "ready"
			source.erase("raw")
	var started := Time.get_ticks_usec()
	var finished := 0
	for entry: Dictionary in _entries.values().duplicate():
		if entry["mesh"] != null or not _entries.has(str(entry["key"])):
			continue
		pending = true
		if int(entry["task"]) >= 0:
			if WorkerThreadPool.is_task_completed(int(entry["task"])) \
					and (finished == 0 or Time.get_ticks_usec() - started < FINISH_BUDGET_USEC):
				WorkerThreadPool.wait_for_task_completion(int(entry["task"]))
				entry["task"] = -1
				_finish(entry)
				finished += 1
			continue
		if now < int(entry["due"]):
			continue
		var source := _source_state(entry["source"] as ArrayMesh)
		if str(source["state"]) == "fetch":
			if fetched:
				continue
			fetched = true
			_fetch(source)
			continue
		if str(source["state"]) != "ready":
			continue
		var data: Dictionary = source["data"]
		var vector := _vector(data, entry["weights"] as Dictionary)
		var result: Array = entry["result"]
		var still := bool(entry["still"])
		var bytes := int(data["still_bytes" if still else "bytes"])
		_bytes += bytes - int(entry["bytes"])
		entry["bytes"] = bytes
		entry["task"] = WorkerThreadPool.add_task(func() -> void:
			result.append_array(compute(data, vector, not still)), false, "RL head identity bake")
	if not pending:
		var tree := Engine.get_main_loop() as SceneTree
		if tree != null and tree.process_frame.is_connected(_poll):
			tree.process_frame.disconnect(_poll)
		_polling = false


## Builds the entry's mesh from its computed arrays and calls its waiters. An
## entry that was dropped meanwhile (clear, eviction) builds nothing.
static func _finish(entry: Dictionary) -> void:
	if _entries.get(str(entry["key"])) != entry:
		return
	var source := entry["source"] as ArrayMesh
	var state: Dictionary = _sources.get(source.get_instance_id(), {})
	var data: Dictionary = state.get("data", {})
	var result: Array = entry["result"]
	if data.is_empty() or result.size() != (data["surfaces"] as Array).size():
		# Nothing to build from: its users stay live.
		entry["users"] = 0
		_drop(entry)
		return
	var still := bool(entry["still"])
	var mesh := ArrayMesh.new()
	mesh.resource_name = source.resource_name
	mesh.blend_shape_mode = int(data["mode"])
	var names: PackedStringArray = data["names"]
	if not still:
		for index: int in data["kept"] as PackedInt32Array:
			mesh.add_blend_shape(names[index])
	var made := 0
	for surface: int in result.size():
		var source_surface: Dictionary = (data["surfaces"] as Array)[surface]
		var baked: Dictionary = result[surface]
		if still and _still_dropped(source_surface):
			continue
		var arrays: Array = (source_surface["arrays"] as Array).duplicate()
		arrays[Mesh.ARRAY_VERTEX] = baked["v"]
		if not (baked["n"] as PackedVector3Array).is_empty():
			arrays[Mesh.ARRAY_NORMAL] = baked["n"]
		if not (baked["t"] as PackedFloat32Array).is_empty():
			arrays[Mesh.ARRAY_TANGENT] = baked["t"]
		var shapes: Array = []
		for kept: Array in baked["kept"] as Array:
			var shape_arrays: Array = []
			shape_arrays.resize(Mesh.ARRAY_MAX)
			shape_arrays[Mesh.ARRAY_VERTEX] = kept[0]
			if not (kept[1] as PackedVector3Array).is_empty():
				shape_arrays[Mesh.ARRAY_NORMAL] = kept[1]
			if not (kept[2] as PackedFloat32Array).is_empty():
				shape_arrays[Mesh.ARRAY_TANGENT] = kept[2]
			shapes.append(shape_arrays)
		mesh.add_surface_from_arrays(int(source_surface["primitive"]), arrays, shapes,
			source_surface["lods"] as Dictionary, int(source_surface["flags"]))
		mesh.surface_set_material(made, source_surface["material"] as Material)
		mesh.surface_set_name(made, str(source_surface["name"]))
		made += 1
	entry["mesh"] = mesh
	entry["result"] = []
	_baked_count += 1
	var waiters: Array = entry["waiters"]
	entry["waiters"] = []
	if int(entry["users"]) == 0:
		# Released while it baked: it waits idle for reuse (see release).
		return
	for waiter: Callable in waiters:
		if waiter.is_valid():
			waiter.call(mesh)


## The materials whose surfaces a still bake leaves out in this renderer.
static func still_dropped_materials() -> Array[String]:
	if RenderingServer.get_current_rendering_method() == "gl_compatibility":
		return COMPATIBILITY_STILL_DROPPED_MATERIALS
	return STILL_DROPPED_MATERIALS


## Whether a still bake leaves this source surface out.
static func _still_dropped(source_surface: Dictionary) -> bool:
	var material := source_surface.get("material") as Material
	return material != null and still_dropped_materials().has(material.resource_name)


static func _source_state(source: ArrayMesh) -> Dictionary:
	var id := source.get_instance_id()
	if not _sources.has(id):
		_sources[id] = {"source": source, "state": "fetch", "task": -1}
	return _sources[id] as Dictionary


## A source's sparse data at once, fetching and preparing it on this thread
## if it is not ready (synchronous mode and flush).
static func _ready_source(source: ArrayMesh) -> Dictionary:
	var state := _source_state(source)
	if str(state["state"]) == "fetch":
		_fetch(state)
	if str(state["state"]) == "prepare":
		if int(state["task"]) >= 0:
			WorkerThreadPool.wait_for_task_completion(int(state["task"]))
			state["task"] = -1
		else:
			_prepare(state["raw"] as Dictionary, state)
		state["state"] = "ready"
		state.erase("raw")
	return state["data"] as Dictionary


## Reads a source mesh's arrays on the main thread; their reduction to sparse
## deltas runs on the WorkerThreadPool (or at once in synchronous mode).
static func _fetch(state: Dictionary) -> void:
	var source := state["source"] as ArrayMesh
	var names := PackedStringArray()
	for index: int in source.get_blend_shape_count():
		names.append(str(source.get_blend_shape_name(index)))
	var raw := {"names": names, "mode": source.blend_shape_mode, "surfaces": []}
	for surface: int in source.get_surface_count():
		(raw["surfaces"] as Array).append({"arrays": source.surface_get_arrays(surface),
			"shapes": source.surface_get_blend_shape_arrays(surface), "lods": _lods(source, surface),
			"flags": source.surface_get_format(surface), "primitive": source.surface_get_primitive_type(surface),
			"material": source.surface_get_material(surface), "name": source.surface_get_name(surface)})
	state["raw"] = raw
	state["state"] = "prepare"
	state["data"] = {}
	if synchronous:
		return
	var data: Dictionary = state["data"]
	state["task"] = WorkerThreadPool.add_task(func() -> void:
		_prepare(raw, {"data": data}), false, "RL head identity bake source")


## Reduces fetched arrays to the bake's source data in `into["data"]` (filled
## in place, so a worker can write it). Touches no Object.
static func _prepare(raw: Dictionary, into: Dictionary) -> void:
	var names: PackedStringArray = raw["names"]
	var baked := PackedInt32Array()
	var kept := PackedInt32Array()
	for index: int in names.size():
		if is_baked_shape(names[index]):
			baked.append(index)
		else:
			kept.append(index)
	var surfaces: Array = []
	var bytes := 0
	var still_bytes := 0
	for fetched: Dictionary in raw["surfaces"] as Array:
		var arrays: Array = fetched["arrays"]
		var shapes: Array = fetched["shapes"]
		var base_v: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var base_n: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL] if arrays[Mesh.ARRAY_NORMAL] is PackedVector3Array \
			else PackedVector3Array()
		var base_t: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT] if arrays[Mesh.ARRAY_TANGENT] is PackedFloat32Array \
			else PackedFloat32Array()
		var sparse: Array = []
		for index: int in names.size():
			sparse.append(_sparse(base_v, base_n, base_t, shapes[index] as Array) if index < shapes.size() else [])
		bytes += _surface_bytes(arrays, kept.size(), fetched["lods"] as Dictionary)
		if not _still_dropped(fetched):
			still_bytes += _surface_bytes(arrays, 0, fetched["lods"] as Dictionary)
		var surface := fetched.duplicate()
		surface.erase("shapes")
		surface["base_v"] = base_v
		surface["base_n"] = base_n
		surface["base_t"] = base_t
		surface["sparse"] = sparse
		surfaces.append(surface)
	var data: Dictionary = into["data"] if into.has("data") else {}
	data.merge({"names": names, "baked": baked, "kept": kept, "mode": raw["mode"], "surfaces": surfaces,
		"bytes": bytes, "still_bytes": still_bytes}, true)
	into["data"] = data


## Estimated GPU bytes of one baked surface: 20 bytes of position, normal and
## tangent per vertex for the base and each kept shape, skin 16, attributes,
## and 16-bit indices for the surface and its LODs.
static func _surface_bytes(arrays: Array, kept: int, lods: Dictionary) -> int:
	var count := (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
	var indices: Variant = arrays[Mesh.ARRAY_INDEX]
	var index_count := (indices as PackedInt32Array).size() if indices is PackedInt32Array else 0
	for lod: Variant in lods.values():
		index_count += (lod as PackedInt32Array).size()
	var attributes := 0
	for slot: int in [Mesh.ARRAY_TEX_UV, Mesh.ARRAY_TEX_UV2, Mesh.ARRAY_COLOR]:
		if arrays[slot] != null:
			attributes += 8 if slot != Mesh.ARRAY_COLOR else 4
	return count * (20 * (1 + kept) + 16 + attributes) + index_count * 2


## The same estimate before the source is read (vertex and shape counts only).
static func _estimate(source: ArrayMesh, still: bool = false) -> int:
	var state: Dictionary = _sources.get(source.get_instance_id(), {})
	# Only a ready source's data: a worker may still be filling it.
	if str(state.get("state", "")) == "ready":
		return int((state["data"] as Dictionary)["still_bytes" if still else "bytes"])
	var kept := 0
	for index: int in source.get_blend_shape_count():
		kept += 0 if still or is_baked_shape(str(source.get_blend_shape_name(index))) else 1
	var bytes := 0
	for surface: int in source.get_surface_count():
		bytes += source.surface_get_array_len(surface) * (20 * (1 + kept) + 28) \
			+ source.surface_get_array_index_len(surface) * 4
	return bytes


static func _vector(data: Dictionary, weights: Dictionary) -> PackedFloat32Array:
	var vector := PackedFloat32Array()
	var names: PackedStringArray = data["names"]
	for index: int in data["baked"] as PackedInt32Array:
		vector.append(roundi(float(weights.get(names[index], 0.0)) / QUANTUM) * QUANTUM)
	return vector


## The vertices one blend shape moves, with their position, normal and tangent
## deltas from the base: [indices, positions, normals, tangent xyz], or [] for
## a shape that moves nothing on this surface.
static func _sparse(base_v: PackedVector3Array, base_n: PackedVector3Array, base_t: PackedFloat32Array,
		shape: Array) -> Array:
	var shape_v: PackedVector3Array = shape[Mesh.ARRAY_VERTEX] if shape.size() > Mesh.ARRAY_VERTEX \
		and shape[Mesh.ARRAY_VERTEX] is PackedVector3Array else PackedVector3Array()
	if shape_v.size() != base_v.size():
		return []
	var shape_n: PackedVector3Array = shape[Mesh.ARRAY_NORMAL] if shape[Mesh.ARRAY_NORMAL] is PackedVector3Array \
		else PackedVector3Array()
	var shape_t: PackedFloat32Array = shape[Mesh.ARRAY_TANGENT] if shape[Mesh.ARRAY_TANGENT] is PackedFloat32Array \
		else PackedFloat32Array()
	var use_n := shape_n.size() == base_v.size() and base_n.size() == base_v.size()
	var use_t := shape_t.size() == base_v.size() * 4 and base_t.size() == base_v.size() * 4
	var indices := PackedInt32Array()
	var dv := PackedVector3Array()
	var dn := PackedVector3Array()
	var dt := PackedVector3Array()
	for i: int in base_v.size():
		var p := shape_v[i] - base_v[i]
		var n := shape_n[i] - base_n[i] if use_n else Vector3.ZERO
		var t := Vector3(shape_t[i * 4] - base_t[i * 4], shape_t[i * 4 + 1] - base_t[i * 4 + 1],
			shape_t[i * 4 + 2] - base_t[i * 4 + 2]) if use_t else Vector3.ZERO
		if p.length_squared() + n.length_squared() + t.length_squared() <= MOVE_EPSILON * MOVE_EPSILON:
			continue
		indices.append(i)
		dv.append(p)
		if use_n:
			dn.append(n)
		if use_t:
			dt.append(t)
	if indices.is_empty():
		return []
	return [indices, dv, dn, dt]


## The surface's generated index LODs, as add_surface_from_arrays takes them.
static func _lods(source: ArrayMesh, surface: int) -> Dictionary:
	var result := {}
	var packed := RenderingServer.mesh_get_surface(source.get_rid(), surface)
	var index_count := int(packed.get("index_count", 0))
	var index_data: Variant = packed.get("index_data")
	if index_count <= 0 or index_data is not PackedByteArray:
		return result
	var element := (index_data as PackedByteArray).size() / index_count
	for lod: Variant in packed.get("lods", []) as Array:
		if lod is not Dictionary or (lod as Dictionary).get("index_data") is not PackedByteArray:
			continue
		var bytes: PackedByteArray = (lod as Dictionary)["index_data"]
		var indices := PackedInt32Array()
		if element == 4:
			indices = bytes.to_int32_array()
		else:
			indices.resize(bytes.size() / 2)
			for i: int in indices.size():
				indices[i] = bytes.decode_u16(i * 2)
		result[float((lod as Dictionary).get("edge_length", 0.0))] = indices
	return result


## The baked arrays for one source and weight vector (in the order of the
## source's baked shapes): per surface, the vertices, normals and tangents with
## the weights added, and (`with_shapes`) for every kept shape its arrays
## offset to them. Touches no Object, so it runs on any thread.
static func compute(data: Dictionary, weights: PackedFloat32Array, with_shapes: bool = true) -> Array:
	var results: Array = []
	var baked: PackedInt32Array = data["baked"]
	var kept: PackedInt32Array = data["kept"]
	for surface: Dictionary in data["surfaces"] as Array:
		var v: PackedVector3Array = (surface["base_v"] as PackedVector3Array).duplicate()
		var n: PackedVector3Array = (surface["base_n"] as PackedVector3Array).duplicate()
		var t: PackedFloat32Array = (surface["base_t"] as PackedFloat32Array).duplicate()
		var sparse: Array = surface["sparse"]
		for k: int in baked.size():
			var w := weights[k]
			if w == 0.0:
				continue
			_add(v, n, t, sparse[baked[k]] as Array, w)
		var shapes: Array = []
		for shape: int in (kept if with_shapes else PackedInt32Array()):
			var sv := v.duplicate()
			var sn := n.duplicate()
			var st := t.duplicate()
			_add(sv, sn, st, sparse[shape] as Array, 1.0)
			shapes.append([sv, sn, st])
		results.append({"v": v, "n": n, "t": t, "kept": shapes})
	return results


static func _add(v: PackedVector3Array, n: PackedVector3Array, t: PackedFloat32Array, delta: Array,
		w: float) -> void:
	if delta.is_empty():
		return
	var indices: PackedInt32Array = delta[0]
	var dv: PackedVector3Array = delta[1]
	var dn: PackedVector3Array = delta[2]
	var dt: PackedVector3Array = delta[3]
	for j: int in indices.size():
		v[indices[j]] += dv[j] * w
	if not dn.is_empty():
		for j: int in indices.size():
			n[indices[j]] += dn[j] * w
	if not dt.is_empty():
		for j: int in indices.size():
			var at := indices[j] * 4
			var d := dt[j] * w
			t[at] += d.x
			t[at + 1] += d.y
			t[at + 2] += d.z
