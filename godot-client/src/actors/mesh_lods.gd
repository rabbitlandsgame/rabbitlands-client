extends RefCounted
## Index LOD chains carried through the meshes the client derives from
## imported ones (actor LODs, chunk C6).
##
## Godot draws a surface's LOD levels from index arrays over that surface's own
## vertices; `ArrayMesh.add_surface_from_arrays(..., lods)` takes them as
## {edge_length: PackedInt32Array}. A derivation that rebuilds a surface from
## `surface_get_arrays` and passes `{}` drops them, so a cape, a beard or the
## neck skin would keep drawing every triangle at any distance while the body
## and armour around it step down. This module reads a surface's chains, checks
## them against what Godot accepts, and attaches them to the rebuilt surface.
##
## - Derivations that keep the topology (the cape's shoulder fold and armour
##   fit, the emblem UVs, the mounted attachment) copy the chains unchanged.
## - Derivations that build new geometry from part of a surface map the
##   parent's chains onto it (`remap`, the beard), or add one coarse level of
##   their own at the parent's first edge length (the neck skin), so the
##   derived surface switches when its parent does.
## - A source without chains gives a surface without chains, built with the
##   same call as before: the result is then exactly what it was.
##
## Reading chains from the server copies the surface's buffers (on the
## RenderingDevice that is a GPU readback). So:
## - a mesh built through `add_surface` keeps what it was given as metadata,
##   bound to its own RID and surface sizes, and a derivation of a derivation
##   reads it without another readback;
## - any other mesh is read back once and remembered in a small weak memo (the
##   same cape is folded over every torso, the same face grows every beard).
## No class_name: callers preload this file by path.

const META := &"mesh_lods"
## Godot stores a surface's indices (and every LOD level) as 16-bit values up
## to this many vertices, and as 32-bit values above it.
const SHORT_INDEX_VERTICES := 65536
## Meshes whose server read is remembered. Weak, bound to the RID and surface
## sizes; the oldest goes first. An entry is a few bytes without chains and
## the chains' own size (tens of KB for a body) with them.
const MEMO_LIMIT := 64

static var _memo := {}
static var _memo_lock := Mutex.new()
static var _server_reads := 0
static var _stored_reads := 0
static var _memo_reads := 0
static var _carried_surfaces := 0
static var _rejected_levels := 0


## The chains of one surface, as `add_surface_from_arrays` takes them. Values
## are copies, so callers may edit them.
static func read(mesh: Mesh, surface: int) -> Dictionary:
	if mesh == null or surface < 0 or surface >= mesh.get_surface_count():
		return {}
	var stored: Variant = _stored(mesh, surface)
	if stored is Dictionary:
		_stored_reads += 1
		return _copy(stored as Dictionary)
	if mesh is not ArrayMesh:
		return {}
	var array_mesh := mesh as ArrayMesh
	var key := array_mesh.get_rid().get_id()
	var sizes := Vector2i(array_mesh.surface_get_array_len(surface),
		array_mesh.surface_get_array_index_len(surface))
	_memo_lock.lock()
	var known: Variant = _recall(key, array_mesh, surface, sizes)
	_memo_lock.unlock()
	if known is Dictionary:
		_memo_reads += 1
		return _copy(known as Dictionary)
	var lods := server_lods(array_mesh, surface)
	_memo_lock.lock()
	_remember(key, array_mesh, surface, sizes, lods)
	_memo_lock.unlock()
	return lods


## The chains the RenderingServer holds for a surface, ignoring metadata.
static func server_lods(mesh: Mesh, surface: int) -> Dictionary:
	if mesh is not ArrayMesh or surface < 0 or surface >= mesh.get_surface_count():
		return {}
	_server_reads += 1
	var raw: Dictionary = RenderingServer.mesh_get_surface(mesh.get_rid(), surface)
	var levels: Variant = raw.get("lods", [])
	if levels is not Array or (levels as Array).is_empty():
		return {}
	var wide := int(raw.get("vertex_count", 0)) > SHORT_INDEX_VERTICES
	var result := {}
	for level_value: Variant in levels as Array:
		if level_value is not Dictionary:
			continue
		var level := level_value as Dictionary
		var edge := float(level.get("edge_length", 0.0))
		var data: Variant = level.get("index_data", PackedByteArray())
		if edge <= 0.0 or data is not PackedByteArray:
			continue
		var indices := _decode(data as PackedByteArray, wide)
		if not indices.is_empty():
			result[edge] = indices
	return result


## The levels Godot accepts for a surface of `vertex_count` vertices drawn from
## `index_count` indices: triangles only; a positive finite edge length; whole
## triangles; every index in range; fewer indices than the base and than the
## previous kept level. Others are dropped (and counted) rather than handed to
## the engine, which would print an error or draw out of range.
static func sanitize(lods: Dictionary, vertex_count: int, index_count: int,
		primitive: int = Mesh.PRIMITIVE_TRIANGLES) -> Dictionary:
	var result := {}
	if lods.is_empty():
		return result
	if primitive != Mesh.PRIMITIVE_TRIANGLES or vertex_count <= 0 or index_count <= 0:
		_rejected_levels += lods.size()
		return result
	var edges: Array = []
	for key: Variant in lods:
		if (key is float or key is int) and is_finite(float(key)) and float(key) > 0.0 \
				and lods[key] is PackedInt32Array:
			edges.append(key)
		else:
			_rejected_levels += 1
	edges.sort_custom(func(a: Variant, b: Variant) -> bool: return float(a) < float(b))
	var previous := index_count
	for key: Variant in edges:
		var indices := lods[key] as PackedInt32Array
		if indices.is_empty() or indices.size() % 3 != 0 or indices.size() >= previous \
				or result.has(float(key)) or not in_range(indices, vertex_count):
			_rejected_levels += 1
			continue
		result[float(key)] = indices
		previous = indices.size()
	return result


## Whether every index addresses one of `vertex_count` vertices (native sort).
static func in_range(indices: PackedInt32Array, vertex_count: int) -> bool:
	if indices.is_empty():
		return true
	var sorted := indices.duplicate()
	sorted.sort()
	return sorted[0] >= 0 and sorted[sorted.size() - 1] < vertex_count


## Each level's triangles whose three corners all have a place in the derived
## surface, renumbered: `map[old] = new`, or -1 where it has none. Levels left
## empty are dropped.
static func remap(lods: Dictionary, map: PackedInt32Array) -> Dictionary:
	var result := {}
	var size := map.size()
	for key: Variant in lods:
		var source := lods[key] as PackedInt32Array
		var kept := PackedInt32Array()
		kept.resize(source.size())
		var count := 0
		for corner: int in range(0, source.size() - 2, 3):
			var a := source[corner]
			var b := source[corner + 1]
			var c := source[corner + 2]
			if a < 0 or b < 0 or c < 0 or a >= size or b >= size or c >= size:
				continue
			var mapped_a := map[a]
			var mapped_b := map[b]
			var mapped_c := map[c]
			if mapped_a < 0 or mapped_b < 0 or mapped_c < 0:
				continue
			kept[count] = mapped_a
			kept[count + 1] = mapped_b
			kept[count + 2] = mapped_c
			count += 3
		if count > 0:
			kept.resize(count)
			result[key] = kept
	return result


## `add_surface_from_arrays` with the sanitized chains, recorded on the mesh so
## `read` needs no readback. With no chains this is the plain call with `{}`.
static func add_surface(mesh: ArrayMesh, primitive: int, arrays: Array,
		blend_shapes: Array, lods: Dictionary, flags: int) -> void:
	var vertex_count := _length(arrays, Mesh.ARRAY_VERTEX)
	var index_count := _length(arrays, Mesh.ARRAY_INDEX)
	var kept := sanitize(lods, vertex_count, index_count, primitive)
	var surface := mesh.get_surface_count()
	mesh.add_surface_from_arrays(primitive, arrays, blend_shapes, kept, flags)
	if mesh.get_surface_count() != surface + 1:
		return
	if not kept.is_empty():
		_carried_surfaces += 1
	var entries: Array = []
	if mesh.has_meta(META) and mesh.get_meta(META) is Array:
		# Written to a copy: code that copies a mesh's metadata onto another
		# (mesh_rest_coordinates, the RL head neck normals, retained mount
		# skins) shares this Array, and an in-place write would replace the
		# other mesh's record with this one's.
		entries = (mesh.get_meta(META) as Array).duplicate()
	if entries.size() <= surface:
		entries.resize(surface + 1)
	entries[surface] = [mesh.get_rid().get_id(), mesh.surface_get_array_len(surface),
		mesh.surface_get_array_index_len(surface), _copy(kept)]
	mesh.set_meta(META, entries)


## The level count `read` reports, for tests and diagnostics.
static func level_count(mesh: Mesh, surface: int) -> int:
	return read(mesh, surface).size()


static func snapshot() -> Dictionary:
	_memo_lock.lock()
	var remembered := _memo.size()
	_memo_lock.unlock()
	return {"server_reads": _server_reads, "stored_reads": _stored_reads,
		"memo_reads": _memo_reads, "remembered_meshes": remembered,
		"carried_surfaces": _carried_surfaces, "rejected_levels": _rejected_levels}


static func reset_counters() -> void:
	_server_reads = 0
	_stored_reads = 0
	_memo_reads = 0
	_carried_surfaces = 0
	_rejected_levels = 0


## Forget every remembered server read (session teardown, tests).
static func clear() -> void:
	_memo_lock.lock()
	_memo.clear()
	_memo_lock.unlock()


static func _recall(key: int, mesh: ArrayMesh, surface: int, sizes: Vector2i) -> Variant:
	var entry: Variant = _memo.get(key)
	if entry is not Array or ((entry as Array)[0] as WeakRef).get_ref() != mesh:
		return null
	var surfaces: Dictionary = (entry as Array)[1]
	var known: Variant = surfaces.get(surface)
	if known is not Array or (known as Array)[0] != sizes:
		return null
	return (known as Array)[1]


static func _remember(key: int, mesh: ArrayMesh, surface: int, sizes: Vector2i,
		lods: Dictionary) -> void:
	var entry: Variant = _memo.get(key)
	if entry is not Array or ((entry as Array)[0] as WeakRef).get_ref() != mesh:
		if not _memo.has(key) and _memo.size() >= MEMO_LIMIT:
			_memo.erase(_memo.keys()[0])
		entry = [weakref(mesh), {}]
		_memo[key] = entry
	((entry as Array)[1] as Dictionary)[surface] = [sizes, _copy(lods)]


static func _stored(mesh: Mesh, surface: int) -> Variant:
	if mesh is not ArrayMesh or not mesh.has_meta(META):
		return null
	var entries: Variant = mesh.get_meta(META)
	if entries is not Array or surface >= (entries as Array).size():
		return null
	var entry: Variant = (entries as Array)[surface]
	if entry is not Array or (entry as Array).size() != 4 or entry[3] is not Dictionary:
		return null
	var array_mesh := mesh as ArrayMesh
	# Metadata travels with copies and duplicates; only the mesh it was
	# recorded on, unchanged, may answer from it.
	if int(entry[0]) != array_mesh.get_rid().get_id() \
			or int(entry[1]) != array_mesh.surface_get_array_len(surface) \
			or int(entry[2]) != array_mesh.surface_get_array_index_len(surface):
		return null
	return entry[3]


static func _copy(lods: Dictionary) -> Dictionary:
	var result := {}
	for key: Variant in lods:
		result[key] = (lods[key] as PackedInt32Array).duplicate()
	return result


static func _length(arrays: Array, slot: int) -> int:
	if arrays.size() <= slot:
		return 0
	var values: Variant = arrays[slot]
	if values is PackedVector3Array or values is PackedVector2Array or values is PackedInt32Array:
		return values.size()
	return 0


## Little-endian u16 or u32 indices. The 16-bit form is read as 32-bit words,
## two indices per word, which halves the GDScript loop.
static func _decode(bytes: PackedByteArray, wide: bool) -> PackedInt32Array:
	if wide:
		return bytes.to_int32_array() if bytes.size() % 4 == 0 else PackedInt32Array()
	if bytes.size() % 2 != 0:
		return PackedInt32Array()
	var count := bytes.size() / 2
	var padded := bytes
	if bytes.size() % 4 != 0:
		padded = bytes.duplicate()
		padded.append(0)
		padded.append(0)
	var words := padded.to_int32_array()
	var indices := PackedInt32Array()
	indices.resize(words.size() * 2)
	for word: int in range(words.size()):
		var value := words[word]
		indices[word * 2] = value & 0xFFFF
		indices[word * 2 + 1] = (value >> 16) & 0xFFFF
	indices.resize(count)
	return indices
