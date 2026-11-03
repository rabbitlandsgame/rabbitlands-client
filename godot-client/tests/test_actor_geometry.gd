extends SceneTree
## Actor geometry sidecars (actor LODs C1): the shared format and the runtime
## applier, called directly on parsed GLTFStates the way the actor parse will
## call it. Sidecars are cooked in-test with the shared format: LOD chains from
## ImporterMesh.generate_lods and a deterministic lining mask shaped like the
## measured ones (about 1,700 kept runs, 59% of the torso lining kept).
##
## Checks: vertex attributes stay byte-identical; the RenderingServer surface
## carries the planned LOD levels; every rejection leaves the parse untouched;
## run compaction keeps exactly the kept triangles; blend-shape and 8-weight
## creatures apply on a worker Thread; off/generate/out-of-scope modes; the
## apply cost of an L1 torso stays within 3 ms (best of 5).

const Format := preload("res://src/actors/actor_geometry_format.gd")
const ActorGeometry := preload("res://src/actors/actor_geometry.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const CreaturePayload := preload("res://src/actors/creature_payload.gd")
const HardwareTier := preload("res://src/runtime/hardware_tier.gd")

const BODY := "res://assets/actors/native/races/luminous_male.glb"
const TORSO := "res://assets/actors/native/equipment/variants/human_male/amberwood_woodland_cuirass_02.glb"
## 25 corrective blend shapes.
const BLEND_CREATURE := "res://assets/actors/native/creatures/basic_expansion/cerberus.glb"
## JOINTS_1/WEIGHTS_1: 8 bone weights per vertex.
const WIDE_CREATURE := "res://assets/actors/native/creatures/ashen_wolf.glb"
const LINING := "GeneratedArmorBacking"
const ROOT := "user://actor-geometry-test"
const APPLY_BUDGET_USEC := 3000
const MIN_CHAIN_TRIANGLES := 64
const WORKER_TIMEOUT_MSEC := 120000

var _checks := 0
var _failures := 0
var _saved_environment := {}
var _sidecars := {}


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	for variable: String in [ActorGeometry.MODE_ENVIRONMENT, ActorGeometry.ROOT_ENVIRONMENT]:
		_saved_environment[variable] = OS.get_environment(variable)
	OS.set_environment(ActorGeometry.MODE_ENVIRONMENT, "sidecar")
	_expect(GltfQuantization.ensure_registered(), "glTF extensions register on the main thread")
	_remove_tree(ProjectSettings.globalize_path(ROOT))
	_check_format()
	_cook_fixtures()
	_check_apply()
	print("section: rejections")
	_check_rejections()
	print("section: compaction")
	_check_compaction()
	print("section: threads")
	await _check_threads()
	print("section: modes")
	_check_modes()
	print("section: costs")
	_check_costs()
	_remove_tree(ProjectSettings.globalize_path(ROOT))
	for variable: String in _saved_environment:
		if str(_saved_environment[variable]).is_empty():
			OS.unset_environment(variable)
		else:
			OS.set_environment(variable, str(_saved_environment[variable]))
	ActorGeometry.reset()
	print("actor geometry: %s (%d checks)" % ["PASS" if _failures == 0 else "FAIL (%d)" % _failures, _checks])
	quit(1 if _failures > 0 else 0)


# --- format -----------------------------------------------------------------

func _check_format() -> void:
	var engine := Format.engine_identity()
	var pattern := RegEx.create_from_string("^\\d+\\.\\d+\\.\\d+\\.[a-z0-9_]+\\.[a-z0-9_]+(\\.[0-9a-f]{9})?$")
	_expect(pattern.search(engine) != null, "engine identity %s names version, status, build and commit" % engine)
	var surface := {"vertex_count": 6, "index_count": 12, "index_digest": Format.index_digest(PackedInt32Array([0, 1, 2, 3, 4, 5, 0, 2, 4, 1, 3, 5])),
		"base": PackedInt32Array([0, 1, 2, 3, 4, 5]), "lods": [[0.25, PackedInt32Array([0, 2, 4])]]}
	var sidecar := _sidecar_header(BODY, "0".repeat(64), 10)
	sidecar.meshes = [{"name": "probe", "surfaces": [surface]}]
	_expect(Format.validate_sidecar(sidecar).is_empty(), "a minimal v1 sidecar validates")
	var encoded := Format.encode(sidecar)
	_expect(encoded == Format.encode(sidecar), "encoding is deterministic")
	var decoded := Format.decode(encoded)
	_expect(decoded.get("sidecar") == sidecar, "decode returns the encoded sidecar")
	_expect(str(Format.decode(encoded.slice(0, 10)).get("error")) == "length", "a truncated sidecar is rejected")
	var wrong_magic := encoded.duplicate()
	wrong_magic[0] = 0x58
	_expect(str(Format.decode(wrong_magic).get("error")) == "magic", "a foreign file is rejected by magic")
	var wrong_size := encoded.duplicate()
	wrong_size.encode_u64(8, 0)
	_expect(str(Format.decode(wrong_size).get("error")) == "size", "an impossible decoded size is rejected")
	var cases := {"schema": "schema", "policy": "policy", "replace": "unsupported key",
		"edge_order": "lod edge order", "lod_size": "lod size", "base_range": "base",
		"lod_range": "lod range", "runs_without_base": "compact_runs without base",
		"overlapping_runs": "compact_runs", "index_count": "index_count", "source_scope": "source"}
	for kind: String in cases:
		var problem := Format.validate_sidecar(_changed(sidecar, kind))
		_expect(problem.contains(str(cases[kind])), "an invalid sidecar is rejected for %s (got '%s')" % [kind, problem])
	# Base in a compacted numbering: 5 kept vertices.
	var compacted: Dictionary = sidecar.duplicate(true)
	compacted.meshes[0].surfaces[0].compact_runs = PackedInt32Array([0, 2, 3, 3])
	compacted.meshes[0].surfaces[0].base = PackedInt32Array([0, 1, 4])
	compacted.meshes[0].surfaces[0].lods = []
	_expect(Format.validate_sidecar(compacted).is_empty(), "base indices may address the compacted vertices")
	compacted.meshes[0].surfaces[0].base = PackedInt32Array([0, 1, 5])
	_expect(Format.validate_sidecar(compacted).contains("base"), "base indices beyond the compacted vertices are rejected")
	_expect(Format.compacted_vertex_count(PackedInt32Array([0, 2, 3, 3]), 6) == 5, "runs count their kept vertices")
	_expect(Format.compacted_vertex_count(PackedInt32Array([0, 2, 1, 3]), 6) == -1, "overlapping runs are refused")

	var catalog := Format.new_catalog()
	_expect(Format.validate_catalog(catalog).is_empty() and str(catalog.source_check) == "file",
		"a new catalogue validates and checks actor files by default")
	var round_trip: Variant = JSON.parse_string(JSON.stringify(catalog))
	_expect(Format.validate_catalog(round_trip).is_empty(), "the catalogue survives JSON (whole-number floats)")
	var entry := Format.catalog_entry("1".repeat(64), 100, encoded)
	_expect(Format.validate_entry(JSON.parse_string(JSON.stringify(entry))).is_empty(), "a catalogue entry validates after JSON")
	var renamed := entry.duplicate()
	renamed.sidecar = "blobs/other.rlgeo"
	_expect(Format.validate_entry(renamed) == "sidecar", "sidecars are content-addressed")
	var check := catalog.duplicate()
	check.source_check = "sometimes"
	_expect(Format.validate_catalog(check) == "source_check", "an unknown source check is rejected")
	_expect(Format.in_scope("res://assets/actors/native/equipment/variants/human_male/x.glb"), "equipment is in scope")
	_expect(not Format.in_scope("res://assets/actors/native/rl_heads/rl_head_male.glb"), "RL heads keep their authored LODs")
	_expect(not Format.in_scope("res://assets/world/interactives/storage_1.glb"), "world objects are out of scope")
	_expect(not Format.in_scope("res://assets/actors/native/../world/x.glb"), "paths must be simplified")
	_expect(ActorGeometry.logical_path(ProjectSettings.globalize_path(TORSO)) == TORSO,
		"an absolute actor path maps back to its res:// catalogue key")


# --- cooking (test-side stand-in for tools/actor_geometry/cook.gd) -----------

func _cook_fixtures() -> void:
	var torso_state := _parse(TORSO)
	var lining_triangles := 0
	for gltf_mesh: GLTFMesh in torso_state.get_meshes():
		if str(gltf_mesh.mesh.resource_name).ends_with(LINING):
			lining_triangles = (gltf_mesh.mesh.get_surface_arrays(0)[Mesh.ARRAY_INDEX] as PackedInt32Array).size() / 3
	var mask := _mask(lining_triangles)
	_sidecars[BODY] = _cook(_parse(BODY), BODY, {})
	_sidecars[TORSO] = _cook(torso_state, TORSO, {"mask": mask})
	_sidecars["torso_runs"] = _cook(_parse(TORSO), TORSO, {"mask": mask, "gap": 0})
	_sidecars["torso_merged"] = _cook(_parse(TORSO), TORSO, {"mask": mask, "gap": 9})
	_sidecars[BLEND_CREATURE] = _cook(_parse(BLEND_CREATURE), BLEND_CREATURE, {})
	_sidecars[WIDE_CREATURE] = _cook(_parse(WIDE_CREATURE), WIDE_CREATURE, {})
	var kept := 0
	for value: int in mask:
		kept += value
	print("cooked: torso lining %d triangles, mask keeps %d (%.0f%%) in %d runs" % [
		lining_triangles, kept, 100.0 * kept / maxi(lining_triangles, 1), _mask_runs(mask)])
	for key: String in _sidecars:
		_expect(Format.validate_sidecar(_sidecars[key]).is_empty(), "the cooked %s sidecar validates" % key.get_file())


func _sidecar_header(path: String, sha256: String, size: int) -> Dictionary:
	return {"schema": Format.SCHEMA, "policy": Format.POLICY, "engine": Format.engine_identity(),
		"source": {"path": path, "sha256": sha256, "bytes": size}, "meshes": []}


func _cook(state: GLTFState, path: String, options: Dictionary) -> Dictionary:
	var absolute := ProjectSettings.globalize_path(path)
	var sidecar := _sidecar_header(path, CreaturePayload.source_sha256(absolute), _file_size(absolute))
	for gltf_mesh: GLTFMesh in state.get_meshes():
		var mesh := gltf_mesh.mesh
		var surfaces: Array = []
		for surface: int in mesh.get_surface_count():
			var arrays := mesh.get_surface_arrays(surface)
			var record := Format.surface_record(arrays)
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			record["lods"] = []
			if str(mesh.resource_name).ends_with(LINING) and options.has("mask"):
				# Per-face-tile soup: masked base, no chain (the cook refuses one).
				var keep: PackedByteArray = options.mask
				if options.has("gap"):
					var compaction := _compaction(indices, keep, record.vertex_count, int(options.gap))
					record["base"] = compaction.base
					record["compact_runs"] = compaction.runs
				else:
					record["base"] = _masked(indices, keep)
			elif indices.size() / 3 >= MIN_CHAIN_TRIANGLES and not str(mesh.resource_name).ends_with(LINING):
				record["lods"] = _chain(arrays, mesh.get_surface_format(surface))
			surfaces.append(record)
		sidecar.meshes.append({"name": str(mesh.resource_name), "surfaces": surfaces})
	return sidecar


func _chain(arrays: Array, flags: int) -> Array:
	var probe := ImporterMesh.new()
	probe.add_surface(Mesh.PRIMITIVE_TRIANGLES, arrays.duplicate(), [], {}, null, "", flags)
	probe.generate_lods(60.0, 25.0, [])
	var levels: Array = []
	var previous_edge := 0.0
	var previous_size := (arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).size()
	for level: int in probe.get_surface_lod_count(0):
		var edge := probe.get_surface_lod_size(0, level)
		var indices := probe.get_surface_lod_indices(0, level)
		if edge > previous_edge and indices.size() < previous_size and indices.size() >= 3:
			levels.append([edge, indices])
			previous_edge = edge
			previous_size = indices.size()
	return levels


## Deterministic stand-in for a lining visibility mask: runs of 3-7 kept
## triangles separated by 2-5 hidden ones (measured masks: 289-1,747 runs).
func _mask(triangles: int) -> PackedByteArray:
	var keep := PackedByteArray()
	keep.resize(triangles)
	var triangle := 0
	var block := 0
	while triangle < triangles:
		var kept := mini(3 + (block * 7) % 5, triangles - triangle)
		for offset: int in kept:
			keep[triangle + offset] = 1
		triangle += kept + 2 + (block * 3) % 4
		block += 1
	return keep


func _mask_runs(mask: PackedByteArray) -> int:
	var runs := 0
	var previous := 0
	for value: int in mask:
		runs += int(value != 0 and previous == 0)
		previous = value
	return runs


func _masked(indices: PackedInt32Array, keep: PackedByteArray) -> PackedInt32Array:
	var base := PackedInt32Array()
	for triangle: int in keep.size():
		if keep[triangle] != 0:
			base.append_array(indices.slice(triangle * 3, triangle * 3 + 3))
	return base


## Runs over the vertices the kept triangles reference; gaps of up to `gap`
## unreferenced vertices are kept inside a run (fewer, longer runs).
func _compaction(indices: PackedInt32Array, keep: PackedByteArray, vertex_count: int, gap: int) -> Dictionary:
	var used := PackedByteArray()
	used.resize(vertex_count)
	for triangle: int in keep.size():
		if keep[triangle] != 0:
			for corner: int in 3:
				used[indices[triangle * 3 + corner]] = 1
	var runs := PackedInt32Array()
	var vertex := 0
	while vertex < vertex_count:
		if used[vertex] == 0:
			vertex += 1
			continue
		var start := vertex
		var end := vertex + 1
		var probe := end
		while probe < vertex_count and probe - end <= gap:
			if used[probe] != 0:
				end = probe + 1
			probe += 1
		runs.append(start)
		runs.append(end - start)
		vertex = end
	var remap := PackedInt32Array()
	remap.resize(vertex_count)
	remap.fill(-1)
	var next := 0
	for run: int in range(0, runs.size(), 2):
		for offset: int in runs[run + 1]:
			remap[runs[run] + offset] = next
			next += 1
	var base := PackedInt32Array()
	for triangle: int in keep.size():
		if keep[triangle] != 0:
			for corner: int in 3:
				base.append(remap[indices[triangle * 3 + corner]])
	return {"runs": runs, "base": base}


## Writes `sidecars` ({res:// path: sidecar}) and a catalogue into `root`.
func _install(root: String, sidecars: Dictionary, source_check := "file", catalog_engine := "") -> Dictionary:
	var absolute := ProjectSettings.globalize_path(root)
	DirAccess.make_dir_recursive_absolute(absolute.path_join(Format.BLOB_FOLDER))
	var catalog := Format.new_catalog(source_check)
	if not catalog_engine.is_empty():
		catalog.engine = catalog_engine
	for path: String in sidecars:
		var sidecar: Dictionary = sidecars[path]
		var bytes := Format.encode(sidecar)
		var entry := Format.catalog_entry(str(sidecar.source.sha256), int(sidecar.source.bytes), bytes)
		_write(absolute.path_join(str(entry.sidecar)), bytes)
		catalog.entries[path] = entry
	_write(absolute.path_join(Format.CATALOG_FILE), JSON.stringify(catalog, "\t").to_utf8_buffer())
	_use_root(root)
	return catalog


func _use_root(root: String) -> void:
	OS.set_environment(ActorGeometry.ROOT_ENVIRONMENT, ProjectSettings.globalize_path(root))
	ActorGeometry.reset()


# --- applying ---------------------------------------------------------------

func _check_apply() -> void:
	_install(ROOT + "/main", {BODY: _sidecars[BODY], TORSO: _sidecars[TORSO]})
	_expect(ActorGeometry.warm() == "ready", "the cooked catalogue loads")
	for path: String in [BODY, TORSO]:
		var baseline := _signature(_parse(path))
		var state := _parse(path)
		var materials := _materials(state)
		var result := ActorGeometry.apply(state, ProjectSettings.globalize_path(path))
		var after_materials := _materials(state)
		var same_materials := materials.size() == after_materials.size()
		for index: int in materials.size():
			same_materials = same_materials and is_same(materials[index], after_materials[index])
		_expect(same_materials, "%s: every rebuilt surface keeps its parsed material object" % path.get_file())
		_expect(str(result.status) == "applied" and str(result.reason).is_empty(),
			"%s: the sidecar applies (%s %s)" % [path.get_file(), result.status, result.reason])
		var sidecar: Dictionary = _sidecars[path]
		var applied := _signature(state)
		var planned_levels := 0
		var changed_surfaces := 0
		for mesh_index: int in baseline.size():
			for surface_index: int in (baseline[mesh_index] as Array).size():
				var before: Dictionary = baseline[mesh_index][surface_index]
				var after: Dictionary = applied[mesh_index][surface_index]
				var plan: Dictionary = sidecar.meshes[mesh_index].surfaces[surface_index]
				var label := "%s mesh %d surface %d" % [path.get_file(), mesh_index, surface_index]
				_expect(before.vertex == after.vertex, label + ": vertex attributes are byte-identical")
				_expect(before.shapes == after.shapes and before.flags == after.flags and before.material == after.material,
					label + ": blend shapes, flags and material are kept")
				_expect(after.index == (Format.sha256_hex((plan.base as PackedInt32Array).to_byte_array())
					if plan.has("base") else before.index), label + ": the base index buffer is the planned one")
				_expect(int(after.lods) == (plan.lods as Array).size(), label + ": the planned LOD levels are attached")
				planned_levels += (plan.lods as Array).size()
				changed_surfaces += int(Format.changes_surface(plan))
		_expect(int(result.surfaces) == changed_surfaces and int(result.lods) == planned_levels,
			"%s: the result counts %d changed surfaces and %d LOD levels" % [path.get_file(), changed_surfaces, planned_levels])
		_expect(planned_levels > 0, "%s: the fixture carries LOD chains" % path.get_file())
		_check_rendered(state, sidecar, path.get_file())


## The generated scene's RenderingServer surfaces carry the planned levels and
## the parsed vertex counts.
func _check_rendered(state: GLTFState, sidecar: Dictionary, label: String) -> void:
	var expected := {}
	for mesh_plan: Dictionary in sidecar.meshes:
		var counts: Array = []
		for plan: Dictionary in mesh_plan.surfaces:
			counts.append([(plan.lods as Array).size(), _vertex_count(plan)])
		expected[str(mesh_plan.name)] = counts
	var scene := (state.get_additional_data(&"test_document") as GLTFDocument).generate_scene(state)
	_expect(scene != null, label + ": generate_scene succeeds after the rebuild")
	if scene == null:
		return
	var seen := 0
	for node: Node in scene.find_children("*", "MeshInstance3D", true, false):
		var mesh := (node as MeshInstance3D).mesh as ArrayMesh
		if mesh == null or not expected.has(str(mesh.resource_name)):
			continue
		seen += 1
		var counts: Array = expected[str(mesh.resource_name)]
		for surface: int in mesh.get_surface_count():
			var server: Dictionary = RenderingServer.mesh_get_surface(mesh.get_rid(), surface)
			var server_levels := (server.get("lods", []) as Array).size()
			_expect(server_levels == int(counts[surface][0]) and mesh.surface_get_array_len(surface) == int(counts[surface][1]),
				"%s %s surface %d: RenderingServer holds %d LOD levels over %d vertices (planned %d over %d)" % [
				label, mesh.resource_name, surface, server_levels, mesh.surface_get_array_len(surface),
				counts[surface][0], counts[surface][1]])
	_expect(seen == expected.size(), "%s: every planned mesh reaches the scene (%d of %d)" % [label, seen, expected.size()])
	scene.free()


func _vertex_count(plan: Dictionary) -> int:
	return Format.compacted_vertex_count(plan.compact_runs, int(plan.vertex_count)) if plan.has("compact_runs") \
		else int(plan.vertex_count)


# --- rejections -------------------------------------------------------------

func _check_rejections() -> void:
	var torso: Dictionary = _sidecars[TORSO]
	_expect_rejected("not_listed", {BODY: _sidecars[BODY]}, {})
	_expect_rejected("sidecar_digest", {TORSO: torso}, {"tamper": true})
	_expect_rejected("engine", {TORSO: _changed(torso, "engine")}, {})
	_expect_rejected("engine", {TORSO: torso}, {"catalog_engine": "4.7.1.stable.official.000000000"})
	_expect_rejected("shape", {TORSO: _changed(torso, "extra_mesh")}, {})
	_expect_rejected("shape", {TORSO: _changed(torso, "renamed")}, {})
	_expect_rejected("surface", {TORSO: _changed(torso, "digest")}, {})
	_expect_rejected("surface", {TORSO: _changed(torso, "vertex_count")}, {})
	_expect_rejected("decode", {TORSO: _changed(torso, "schema")}, {})
	var stale := _changed(torso, "stale_source")
	_expect_rejected("source", {TORSO: stale}, {})
	_expect_rejected("source", {TORSO: torso}, {"caller_sha": "3".repeat(64)})
	# The entry and the sidecar must name the same source, size included.
	_expect_rejected("catalog", {TORSO: torso}, {"entry_bytes": 1})
	# A root verified together with the actor files may skip the file hash.
	_install(ROOT + "/parsed", {TORSO: stale}, "parsed")
	var parsed := ActorGeometry.apply(_parse(TORSO), ProjectSettings.globalize_path(TORSO))
	_expect(str(parsed.status) == "applied", "source_check parsed binds by the parsed indices alone (%s)" % parsed.reason)
	# Garbage catalogue.
	var absolute := ProjectSettings.globalize_path(ROOT + "/garbage")
	DirAccess.make_dir_recursive_absolute(absolute)
	_write(absolute.path_join(Format.CATALOG_FILE), "{not json".to_utf8_buffer())
	_use_root(ROOT + "/garbage")
	var garbage := ActorGeometry.apply(_parse(TORSO), ProjectSettings.globalize_path(TORSO))
	_expect(str(garbage.status) == "rejected" and str(garbage.reason) == "catalog", "an unreadable catalogue rejects (%s)" % garbage.reason)
	_expect(int(ActorGeometry.snapshot().reasons.get("catalog", 0)) == 1, "the snapshot counts the rejection")


func _changed(sidecar: Dictionary, kind: String) -> Dictionary:
	var value: Dictionary = sidecar.duplicate(true)
	var surface: Dictionary = value.meshes[0].surfaces[0]
	match kind:
		"schema": value.schema = 2
		"policy": value.policy = "rl-actor-geometry-v0"
		"replace": surface["replace"] = {}
		"edge_order": surface.lods = [[0.5, PackedInt32Array([0, 2, 4])], [0.25, PackedInt32Array([0, 1, 2])]]
		"lod_size": surface.lods = [[0.5, PackedInt32Array([0, 1, 2, 3, 4, 5])]]
		"base_range": surface.base = PackedInt32Array([0, 1, 6])
		"lod_range": surface.lods = [[0.5, PackedInt32Array([0, 1, -1])]]
		"runs_without_base":
			surface.erase("base")
			surface.compact_runs = PackedInt32Array([0, 6])
		"overlapping_runs": surface.compact_runs = PackedInt32Array([0, 4, 3, 3])
		"index_count": surface.index_count = 13
		"source_scope": value.source.path = "res://assets/actors/native/rl_heads/head.glb"
		"engine": value.engine = "4.7.1.stable.official.000000000"
		"extra_mesh": value.meshes.append(value.meshes[0].duplicate(true))
		"renamed": value.meshes[1].name = "renamed"
		"digest": value.meshes[1].surfaces[0].index_digest = Format.index_digest(PackedInt32Array([0, 1, 2]))
		"vertex_count": surface.vertex_count = int(surface.vertex_count) + 1
		"stale_source": value.source.sha256 = "2".repeat(64)
		_: push_error("unknown mutation " + kind)
	return value


func _expect_rejected(reason: String, sidecars: Dictionary, options: Dictionary) -> void:
	var root := "%s/reject-%s-%d" % [ROOT, reason, _checks]
	var catalog := _install(root, sidecars, "file", str(options.get("catalog_engine", "")))
	if bool(options.get("tamper", false)):
		var entry: Dictionary = catalog.entries[TORSO]
		var blob := ProjectSettings.globalize_path(root).path_join(str(entry.sidecar))
		var bytes := FileAccess.get_file_as_bytes(blob)
		bytes[bytes.size() - 1] = bytes[bytes.size() - 1] ^ 0xff
		_write(blob, bytes)
	if options.has("entry_bytes"):
		var entry: Dictionary = catalog.entries[TORSO]
		entry.source_bytes = int(entry.source_bytes) + int(options.entry_bytes)
		_write(ProjectSettings.globalize_path(root).path_join(Format.CATALOG_FILE),
			JSON.stringify(catalog, "\t").to_utf8_buffer())
		ActorGeometry.reset()
	var baseline := _signature(_parse(TORSO))
	var state := _parse(TORSO)
	var result := ActorGeometry.apply(state, ProjectSettings.globalize_path(TORSO), str(options.get("caller_sha", "")))
	_expect(str(result.status) == "rejected" and str(result.reason) == reason,
		"rejected for %s (got %s %s)" % [reason, result.status, result.reason])
	_expect(_signature(state) == baseline, "%s: the parse is left exactly as parsed" % reason)
	var snapshot := ActorGeometry.snapshot()
	_expect(int(snapshot.reasons.get(reason, 0)) == 1 and int(snapshot.statuses.get("rejected", 0)) == 1,
		"%s: diagnostics count one rejection" % reason)


# --- compaction -------------------------------------------------------------

func _check_compaction() -> void:
	for key: String in ["torso_runs", "torso_merged"]:
		var sidecar: Dictionary = _sidecars[key]
		_install("%s/%s" % [ROOT, key], {TORSO: sidecar}, "parsed")
		var original := _parse(TORSO)
		var state := _parse(TORSO)
		var result := ActorGeometry.apply(state, ProjectSettings.globalize_path(TORSO))
		_expect(str(result.status) == "applied", "%s: the compacted sidecar applies (%s)" % [key, result.reason])
		for mesh_index: int in state.get_meshes().size():
			var plan: Dictionary = sidecar.meshes[mesh_index].surfaces[0]
			if not plan.has("compact_runs"):
				continue
			var runs: PackedInt32Array = plan.compact_runs
			var before := (original.get_meshes()[mesh_index] as GLTFMesh).mesh.get_surface_arrays(0)
			var after := (state.get_meshes()[mesh_index] as GLTFMesh).mesh.get_surface_arrays(0)
			var kept := Format.compacted_vertex_count(runs, int(plan.vertex_count))
			var old_positions: PackedVector3Array = before[Mesh.ARRAY_VERTEX]
			var new_positions: PackedVector3Array = after[Mesh.ARRAY_VERTEX]
			_expect(new_positions.size() == kept and kept < old_positions.size(),
				"%s: %d of %d lining vertices kept in %d runs" % [key, kept, old_positions.size(), runs.size() / 2])
			var expected_positions := PackedVector3Array()
			for run: int in range(0, runs.size(), 2):
				for offset: int in runs[run + 1]:
					expected_positions.append(old_positions[runs[run] + offset])
			_expect(new_positions == expected_positions, key + ": positions are the kept runs in order")
			for slot: int in Mesh.ARRAY_MAX:
				if slot == Mesh.ARRAY_INDEX or before[slot] == null:
					continue
				var stride: int = before[slot].size() / old_positions.size()
				_expect(after[slot] != null and after[slot].size() == kept * stride and typeof(after[slot]) == typeof(before[slot]),
					"%s: array %d keeps its type and stride %d" % [key, slot, stride])
			# The same triangles in the same order, by corner position.
			var old_indices: PackedInt32Array = before[Mesh.ARRAY_INDEX]
			var new_indices: PackedInt32Array = after[Mesh.ARRAY_INDEX]
			var expected_corners := PackedVector3Array()
			var mask := _mask(old_indices.size() / 3)
			for triangle: int in mask.size():
				if mask[triangle] != 0:
					for corner: int in 3:
						expected_corners.append(old_positions[old_indices[triangle * 3 + corner]])
			var corners := PackedVector3Array()
			for index: int in new_indices:
				corners.append(new_positions[index])
			_expect(corners == expected_corners, key + ": the compacted base draws exactly the kept triangles")
		_check_rendered(state, sidecar, key)


# --- threads ----------------------------------------------------------------

func _check_threads() -> void:
	_install(ROOT + "/creatures", {BLEND_CREATURE: _sidecars[BLEND_CREATURE], WIDE_CREATURE: _sidecars[WIDE_CREATURE]})
	for path: String in [BLEND_CREATURE, WIDE_CREATURE]:
		var reference := _parse(path)
		var reference_mesh := (reference.get_meshes()[0] as GLTFMesh).mesh
		var thread := Thread.new()
		thread.start(_worker_build.bind(ProjectSettings.globalize_path(path)))
		# Like ActorResourceWarmup: keep the main loop running while the worker
		# parses (a parse may wait for the main thread), then join it.
		var deadline := Time.get_ticks_msec() + WORKER_TIMEOUT_MSEC
		while thread.is_alive() and Time.get_ticks_msec() < deadline:
			await process_frame
		if thread.is_alive():
			_expect(false, "%s: the worker parse finishes within %d s" % [path.get_file(), WORKER_TIMEOUT_MSEC / 1000])
			return
		var built: Dictionary = thread.wait_to_finish()
		var label := path.get_file()
		_expect(str(built.get("status", "")) == "applied", "%s: applies on a worker thread (%s)" % [label, built.get("reason", "")])
		var packed := built.get("scene") as PackedScene
		_expect(packed != null, label + ": the worker packs the generated scene")
		if packed == null:
			continue
		var scene := packed.instantiate()
		var levels := 0
		var wide := false
		var shapes := 0
		for node: Node in scene.find_children("*", "MeshInstance3D", true, false):
			var mesh := (node as MeshInstance3D).mesh as ArrayMesh
			if mesh == null:
				continue
			shapes = maxi(shapes, mesh.get_blend_shape_count())
			for surface: int in mesh.get_surface_count():
				levels += (RenderingServer.mesh_get_surface(mesh.get_rid(), surface).get("lods", []) as Array).size()
				wide = wide or (mesh.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS) != 0
		_expect(levels > 0, "%s: the worker-built mesh carries %d LOD levels" % [label, levels])
		_expect(shapes == reference_mesh.get_blend_shape_count(),
			"%s: %d blend shapes survive the rebuild" % [label, shapes])
		var reference_wide := (reference_mesh.get_surface_format(0) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS) != 0
		_expect(wide == reference_wide, "%s: 8-weight skinning is %s" % [label, "kept" if wide else "absent as parsed"])
		if path == WIDE_CREATURE:
			_expect(reference_wide, label + ": the fixture is an 8-weight creature")
		if path == BLEND_CREATURE:
			_expect(shapes > 0, label + ": the fixture has blend shapes")
		scene.free()


static func _worker_build(path: String) -> Dictionary:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	if CreaturePayload.append(document, path, state) != OK:
		return {"status": "parse failed"}
	var result := ActorGeometry.apply(state, path)
	var scene := document.generate_scene(state)
	if scene == null:
		return result
	_own(scene, scene)
	var packed := PackedScene.new()
	packed.pack(scene)
	scene.free()
	result["scene"] = packed
	return result


static func _own(node: Node, owner: Node) -> void:
	for child: Node in node.get_children():
		child.owner = owner
		_own(child, owner)


# --- modes ------------------------------------------------------------------

func _check_modes() -> void:
	# The startup record (HardwareTier) must name the mode the applier uses.
	for value: String in ["", "sidecar", " OFF ", "Generate", "generate", "on", "0", "false", "sidecars"]:
		for editor: bool in [true, false]:
			var ours := ActorGeometry.resolve_mode(value, editor)
			var recorded := HardwareTier.resolve_actor_geometry(value, not editor)
			_expect(ours == recorded, "mode '%s' (%s) resolves as the startup record does: %s vs %s" % [
				value, "editor" if editor else "export", ours, recorded])
	_expect(str(ActorGeometry.resolve_mode("generate", false).mode) == ActorGeometry.DEFAULT_MODE,
		"an exported build never generates LODs at parse time")
	_install(ROOT + "/modes", {BODY: _sidecars[BODY]})
	OS.set_environment(ActorGeometry.MODE_ENVIRONMENT, "off")
	ActorGeometry.reset()
	var baseline := _signature(_parse(BODY))
	var state := _parse(BODY)
	var off := ActorGeometry.apply(state, ProjectSettings.globalize_path(BODY))
	_expect(str(off.status) == "skipped" and str(off.reason) == "off" and _signature(state) == baseline,
		"RABBITLANDS_ACTOR_GEOMETRY=off leaves the parse alone")
	OS.set_environment(ActorGeometry.MODE_ENVIRONMENT, "generate")
	ActorGeometry.reset()
	state = _parse(BODY)
	var generated := ActorGeometry.apply(state, ProjectSettings.globalize_path(BODY))
	var generated_signature := _signature(state)
	var vertices_kept := true
	for mesh_index: int in baseline.size():
		for surface_index: int in (baseline[mesh_index] as Array).size():
			vertices_kept = vertices_kept and baseline[mesh_index][surface_index].vertex == generated_signature[mesh_index][surface_index].vertex
	_expect(str(generated.status) == "generated" and int(generated.lods) > 0 and vertices_kept,
		"the editor-only generate mode adds %d runtime LOD levels and keeps vertices" % int(generated.lods))
	OS.set_environment(ActorGeometry.MODE_ENVIRONMENT, "sidecar")
	ActorGeometry.reset()
	var head := ActorGeometry.apply(_parse(BODY), ProjectSettings.globalize_path("res://assets/actors/native/rl_heads/rl_head_male.glb"))
	_expect(str(head.status) == "skipped" and str(head.reason) == "out_of_scope", "RL head files are out of scope")
	var world := ActorGeometry.apply(_parse(BODY), ProjectSettings.globalize_path("res://assets/world/interactives/storage_1.glb"))
	_expect(str(world.status) == "skipped" and str(world.reason) == "out_of_scope", "world objects are out of scope")
	var empty := ProjectSettings.globalize_path(ROOT + "/empty")
	DirAccess.make_dir_recursive_absolute(empty)
	_use_root(ROOT + "/empty")
	state = _parse(BODY)
	var absent := ActorGeometry.apply(state, ProjectSettings.globalize_path(BODY))
	_expect(str(absent.status) == "skipped" and str(absent.reason) == "no_catalog" and _signature(state) == baseline,
		"without a catalogue the parse is unchanged")
	_expect(ActorGeometry.snapshot().catalog == "absent", "the snapshot reports the absent catalogue")


# --- costs ------------------------------------------------------------------

func _check_costs() -> void:
	var lines := PackedStringArray()
	# L1 torso: masked lining base and the shell chain, as an installed root
	# (source_check parsed) applies it on first sight.
	for key: String in [TORSO, "torso_runs", "torso_merged"]:
		var sidecar: Dictionary = _sidecars[key]
		_install("%s/cost-%s" % [ROOT, key.get_file()], {TORSO: sidecar}, "parsed")
		var best := 1 << 30
		var samples := PackedInt32Array()
		for attempt: int in 5:
			var state := _parse(TORSO)
			var result := ActorGeometry.apply(state, ProjectSettings.globalize_path(TORSO))
			if str(result.status) != "applied":
				best = -1
				break
			samples.append(int(result.usec))
			best = mini(best, int(result.usec))
		var runs := 0
		for mesh_plan: Dictionary in sidecar.meshes:
			for plan: Dictionary in mesh_plan.surfaces:
				runs += (plan.get("compact_runs", PackedInt32Array()) as PackedInt32Array).size() / 2
		lines.append("apply %s (runs %d): best %d us, samples %s, sidecar %d bytes" % [
			key.get_file(), runs, best, samples, Format.encode(sidecar).size()])
		if key == TORSO:
			_expect(best >= 0 and best <= APPLY_BUDGET_USEC,
				"an L1 torso applies within %d us on this machine (best of 5: %d us)" % [APPLY_BUDGET_USEC, best])
	# The default file check hashes the actor file once per first parse.
	_install(ROOT + "/cost-file", {TORSO: _sidecars[TORSO]}, "file")
	var file_best := 1 << 30
	for attempt: int in 3:
		var result := ActorGeometry.apply(_parse(TORSO), ProjectSettings.globalize_path(TORSO))
		file_best = mini(file_best, int(result.usec))
	lines.append("apply %s with source_check file: best %d us (file %d bytes)" % [
		TORSO.get_file(), file_best, _file_size(ProjectSettings.globalize_path(TORSO))])
	# A catalogue the size of the full cook (~2,070 actor files).
	var big := Format.new_catalog("parsed")
	for index: int in 2070:
		var stand_in := PackedByteArray()
		stand_in.resize(32)
		stand_in.encode_u32(0, index)
		var item := "res://assets/actors/native/equipment/variants/human_male/item_%04d.glb" % index
		big.entries[item] = Format.catalog_entry(Format.sha256_hex(stand_in), 2000000 + index, stand_in)
	var big_root := ProjectSettings.globalize_path(ROOT + "/cost-catalog")
	DirAccess.make_dir_recursive_absolute(big_root)
	var big_text := JSON.stringify(big, "\t")
	_write(big_root.path_join(Format.CATALOG_FILE), big_text.to_utf8_buffer())
	_use_root(ROOT + "/cost-catalog")
	var began := Time.get_ticks_usec()
	var status := ActorGeometry.warm()
	lines.append("catalogue of 2070 entries (%d bytes): first read %d us (%s)" % [
		big_text.length(), Time.get_ticks_usec() - began, status])
	_expect(status == "ready", "a full-size catalogue loads")
	# Index storage: i32 as stored vs a u16 packing, after zstd.
	var torso_runs: Dictionary = _sidecars["torso_runs"]
	var narrow: Dictionary = torso_runs.duplicate(true)
	for mesh_plan: Dictionary in narrow.meshes:
		for plan: Dictionary in mesh_plan.surfaces:
			if plan.has("base"):
				plan.base = _u16(plan.base)
			for level: Array in plan.lods:
				level[1] = _u16(level[1])
	lines.append("torso_runs zstd: i32 indices %d bytes, u16 indices %d bytes" % [
		var_to_bytes(torso_runs).compress(FileAccess.COMPRESSION_ZSTD).size(),
		var_to_bytes(narrow).compress(FileAccess.COMPRESSION_ZSTD).size()])
	for line: String in lines:
		print("cost: " + line)


func _u16(indices: PackedInt32Array) -> PackedByteArray:
	var bytes := PackedByteArray()
	bytes.resize(indices.size() * 2)
	for index: int in indices.size():
		bytes.encode_u16(index * 2, indices[index])
	return bytes


# --- helpers ----------------------------------------------------------------

func _parse(path: String) -> GLTFState:
	var state := GLTFState.new()
	var document := GLTFDocument.new()
	var error := CreaturePayload.append(document, ProjectSettings.globalize_path(path), state)
	_expect(error == OK, "%s parses" % path.get_file())
	state.set_additional_data(&"test_document", document) # generate_scene with the parsing document
	return state


## The material objects of every surface, to prove the rebuild reuses them.
func _materials(state: GLTFState) -> Array:
	var materials: Array = []
	for gltf_mesh: GLTFMesh in state.get_meshes():
		for surface: int in gltf_mesh.mesh.get_surface_count():
			materials.append(gltf_mesh.mesh.get_surface_material(surface))
	return materials


## Per mesh, per surface: digests of the vertex attributes, the index buffer
## and the blend shapes, the LOD count, flags and material.
func _signature(state: GLTFState) -> Array:
	var meshes: Array = []
	for gltf_mesh: GLTFMesh in state.get_meshes():
		var mesh := gltf_mesh.mesh
		var surfaces: Array = []
		for surface: int in mesh.get_surface_count():
			var arrays := mesh.get_surface_arrays(surface).duplicate()
			var indices: Variant = arrays[Mesh.ARRAY_INDEX]
			arrays[Mesh.ARRAY_INDEX] = null
			var shapes: Array = []
			for shape: int in mesh.get_blend_shape_count():
				shapes.append(mesh.get_surface_blend_shape_arrays(surface, shape))
			surfaces.append({"vertex": Format.sha256_hex(var_to_bytes(arrays)),
				"index": Format.sha256_hex((indices as PackedInt32Array).to_byte_array()) if indices is PackedInt32Array else "",
				"shapes": Format.sha256_hex(var_to_bytes(shapes)) + ":%d:%d" % [mesh.get_blend_shape_count(), mesh.get_blend_shape_mode()],
				"lods": mesh.get_surface_lod_count(surface), "flags": mesh.get_surface_format(surface),
				"material": str(mesh.get_surface_material(surface).resource_name) if mesh.get_surface_material(surface) != null else "",
				"name": mesh.get_surface_name(surface)})
		meshes.append(surfaces)
	return meshes


func _file_size(path: String) -> int:
	var file := FileAccess.open(path, FileAccess.READ)
	return file.get_length() if file != null else 0


func _write(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	_expect(file != null, "fixture %s can be written" % path.get_file())
	if file != null:
		file.store_buffer(bytes)
		file.close()


func _remove_tree(path: String) -> void:
	if not DirAccess.dir_exists_absolute(path):
		return
	for file: String in DirAccess.get_files_at(path):
		DirAccess.remove_absolute(path.path_join(file))
	for directory: String in DirAccess.get_directories_at(path):
		_remove_tree(path.path_join(directory))
	DirAccess.remove_absolute(path)


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if condition:
		return
	_failures += 1
	push_error("FAIL: " + message)
