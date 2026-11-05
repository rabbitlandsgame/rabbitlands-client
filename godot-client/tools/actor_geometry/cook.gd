extends SceneTree
## Actor geometry cook (actor LODs C2): headless Godot half of
## tools/actor_geometry_cache.py, which plans the work, launches this script
## once per batch and writes the catalogue. Docs: actor-geometry-lods.md.
##
##   RABBITLANDS_ACTOR_GEOMETRY_JOB=<job.json> godot --headless --path godot-client \
##       --script res://tools/actor_geometry/cook.gd
##
## Every file is parsed exactly as the runtime parses an actor glTF
## (GlbSceneCache._parse_generate: the project's glTF extensions registered on
## the main thread, ActorImages enabled on the state, CreaturePayload.append),
## so surface order, vertex counts and index buffers are the ones the runtime
## applier binds to. Nothing is written beside the sources.
##
## Job (JSON): {schema: 1, mode: "cook" | "verify", root: <absolute catalogue
## root>, report: <absolute report path>, policy_digest, raw_digests?: bool,
## scene_check?: bool, files: [{path: "res://...", file_sha256, bytes,
## model_scale, lining?, budget?}]} (`lining`: the lining stage's mask input,
## see lining_policy.gd; `budget`: the budget stage's Human source, see
## budget_policy.gd).
##   cook    parses each file, plans every surface with lod_policy.gd, and
##           writes the sidecar of a file with at least one chain to
##           <root>/blobs/<sha256>.rlgeo (content-addressed, written through a
##           temporary file). A file whose bytes no longer match file_sha256 is
##           refused (the planner hashed something else).
##   verify  reads <root>/catalog.json and applies each listed file's sidecar
##           with the runtime applier (ActorGeometry.apply) to a fresh parse,
##           and with scene_check compares the LOD levels the RenderingServer
##           holds after generate_scene() with the sidecar's.
## Report (JSON, written last through a temporary file): {schema, mode, ok,
## engine, policy, policy_settings, entries: {path: catalogue entry}, results:
## {path: per-file summary}, usec}. Before each file the cook prints
## "actor geometry cook: <path>", so engine errors in the log can be
## attributed to it.

const Format := preload("res://src/actors/actor_geometry_format.gd")
const ActorGeometry := preload("res://src/actors/actor_geometry.gd")
const LodPolicy := preload("res://tools/actor_geometry/lod_policy.gd")
const LiningPolicy := preload("res://tools/actor_geometry/lining_policy.gd")
const BudgetPolicy := preload("res://tools/actor_geometry/budget_policy.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const ActorImages := preload("res://src/actors/actor_images.gd")
const CreaturePayload := preload("res://src/actors/creature_payload.gd")

const JOB_ENVIRONMENT := "RABBITLANDS_ACTOR_GEOMETRY_JOB"
const JOB_SCHEMA := 1
const REPORT_SCHEMA := 1
const MODES: Array[String] = ["cook", "verify"]
const LOG_PREFIX := "actor geometry cook: "


func _init() -> void:
	call_deferred("_main")


func _main() -> void:
	var began := Time.get_ticks_usec()
	var job_path := OS.get_environment(JOB_ENVIRONMENT)
	var job := _read_job(job_path)
	if job.has("error"):
		printerr("%sjob %s rejected: %s" % [LOG_PREFIX, job_path, job.error])
		quit(2)
		return
	var report := {"schema": REPORT_SCHEMA, "mode": str(job.mode), "ok": false,
		"engine": Format.engine_identity(), "policy": Format.POLICY, "policy_settings": LodPolicy.settings(),
		"entries": {}, "results": {}, "usec": 0}
	if not GltfQuantization.ensure_registered():
		printerr(LOG_PREFIX + "glTF extensions did not register")
		quit(2)
		return
	var root := str(job.root)
	var catalog := {}
	# The cook parses plain; verify applies this job's catalogue and no other.
	OS.set_environment(ActorGeometry.MODE_ENVIRONMENT, "off" if str(job.mode) == "cook" else "sidecar")
	OS.set_environment(ActorGeometry.ROOT_ENVIRONMENT, root)
	ActorGeometry.reset()
	if str(job.mode) == "verify":
		catalog = _read_catalog(root)
		if catalog.has("error"):
			printerr("%scatalogue in %s rejected: %s" % [LOG_PREFIX, root, catalog.error])
			quit(2)
			return
	for item: Dictionary in job.files:
		var path := str(item.path)
		print(LOG_PREFIX + path)
		if str(job.mode) == "cook":
			var cooked := cook_file(item, root, str(job.get("policy_digest", "")), bool(job.get("raw_digests", false)))
			report.results[path] = cooked.summary
			if cooked.has("entry"):
				report.entries[path] = cooked.entry
		else:
			report.results[path] = verify_file(path, root, catalog, bool(job.get("scene_check", true)))
	report.ok = true
	report.usec = Time.get_ticks_usec() - began
	if not _write_text(str(job.report), JSON.stringify(report, "", true, true) + "\n"):
		printerr(LOG_PREFIX + "could not write the report " + str(job.report))
		quit(3)
		return
	print("%s%s done: %d files in %.1f s" % [LOG_PREFIX, job.mode, (job.files as Array).size(), report.usec / 1.0e6])
	quit(0)


static func _read_job(path: String) -> Dictionary:
	if path.is_empty() or not FileAccess.file_exists(path):
		return {"error": "missing (set %s)" % JOB_ENVIRONMENT}
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(path)) != OK or not parser.data is Dictionary:
		return {"error": "not a JSON object"}
	var job: Dictionary = parser.data
	if not job.get("schema") is float or int(job.schema) != JOB_SCHEMA:
		return {"error": "schema"}
	if not str(job.get("mode", "")) in MODES:
		return {"error": "mode"}
	for key: String in ["root", "report"]:
		if not job.get(key) is String or not str(job[key]).is_absolute_path():
			return {"error": key}
	if not job.get("files") is Array:
		return {"error": "files"}
	for item: Variant in job.files:
		if not item is Dictionary or not Format.in_scope(str((item as Dictionary).get("path", ""))):
			return {"error": "file %s" % str(item)}
		if str(job.mode) == "cook" and (not Format.is_digest((item as Dictionary).get("file_sha256")) \
				or not (item as Dictionary).get("model_scale") is float):
			return {"error": "file %s" % str(item)}
	return job


## The runtime's actor parse of `absolute` (GlbSceneCache._parse_generate for
## an actor document, minus generate_scene). Returns {state, document, error,
## usec}.
static func parse(absolute: String) -> Dictionary:
	var began := Time.get_ticks_usec()
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	ActorImages.enable(state, absolute)
	var error := CreaturePayload.append(document, absolute, state)
	return {"state": state, "document": document, "error": error, "usec": Time.get_ticks_usec() - began}


## Cooks one job file: {path, file_sha256, bytes, model_scale}. Returns
## {summary} and, when the file gets a sidecar, {entry} (its catalogue entry,
## after the blob is written under `root`).
static func cook_file(item: Dictionary, root: String, policy_digest: String, raw_digests := false) -> Dictionary:
	var began := Time.get_ticks_usec()
	var path := str(item.path)
	var absolute := ProjectSettings.globalize_path(path)
	var summary := {"status": "failed", "reason": "", "file_sha256": str(item.file_sha256),
		"model_scale": float(item.model_scale)}
	if not FileAccess.file_exists(absolute):
		summary.reason = "missing"
		return {"summary": summary}
	if FileAccess.get_sha256(absolute) != str(item.file_sha256):
		summary.reason = "source_changed"
		return {"summary": summary}
	var source_sha256 := CreaturePayload.source_sha256(absolute)
	var source_bytes := _file_length(absolute)
	var parsed := parse(absolute)
	summary["parse_usec"] = int(parsed.usec)
	if int(parsed.error) != OK or not Format.is_digest(source_sha256):
		summary.reason = "parse"
		return {"summary": summary}
	var plan := plan_state(parsed.state, path, source_sha256, source_bytes, float(item.model_scale), raw_digests)
	# Lining stage (actor LODs C4): masked lining bases from the job's masks.
	plan = LiningPolicy.apply(parsed.state, plan, item.get("lining", {}))
	# Budget stage (actor LODs C11): race refits capped against their Human source.
	plan = BudgetPolicy.apply(parsed.state, plan, item.get("budget", {}))
	summary["meshes"] = plan.meshes
	summary["changed_surfaces"] = plan.changed
	summary["lod_levels"] = plan.levels
	summary["source_sha256"] = source_sha256
	summary["source_bytes"] = source_bytes
	summary["plan_usec"] = int(plan.usec)
	if int(plan.changed) == 0:
		summary.status = "unchanged"
		summary["cook_usec"] = Time.get_ticks_usec() - began
		return {"summary": summary}
	var problem := Format.validate_sidecar(plan.sidecar)
	if not problem.is_empty():
		summary.reason = "invalid: " + problem
		return {"summary": summary}
	var bytes := Format.encode(plan.sidecar)
	var inputs := {"policy_digest": policy_digest} if not policy_digest.is_empty() else {}
	var entry := Format.catalog_entry(source_sha256, source_bytes, bytes, inputs)
	if not write_blob(root, entry, bytes):
		summary.reason = "write"
		return {"summary": summary}
	summary.status = "cooked"
	summary["sidecar_bytes"] = bytes.size()
	summary["sidecar_sha256"] = str(entry.sidecar_sha256)
	summary["cook_usec"] = Time.get_ticks_usec() - began
	return {"summary": summary, "entry": entry}


## Plans every surface of a parsed actor glTF. Returns {sidecar, meshes (the
## per-surface report), changed (surfaces with a chain), levels, usec}.
static func plan_state(state: GLTFState, path: String, source_sha256: String, source_bytes: int,
		file_scale := 1.0, raw_digests := false) -> Dictionary:
	var began := Time.get_ticks_usec()
	var sidecar := {"schema": Format.SCHEMA, "policy": Format.POLICY, "engine": Format.engine_identity(),
		"source": {"path": path, "sha256": source_sha256, "bytes": source_bytes}, "meshes": []}
	var mesh_scales := mesh_node_scales(state)
	var report: Array = []
	var changed := 0
	var levels := 0
	var meshes: Array = state.get_meshes()
	for mesh_index: int in meshes.size():
		var mesh: ImporterMesh = (meshes[mesh_index] as GLTFMesh).mesh
		var scale := file_scale * float(mesh_scales[mesh_index])
		var plans: Array = []
		var surfaces: Array = []
		for surface: int in mesh.get_surface_count():
			var arrays := mesh.get_surface_arrays(surface)
			var record := Format.surface_record(arrays)
			var plan := LodPolicy.plan_surface(arrays, mesh.get_surface_format(surface),
				mesh.get_surface_primitive_type(surface), scale)
			record["lods"] = plan.lods
			plans.append(record)
			var row := {"triangles": int(record.index_count) / 3, "vertices": int(record.vertex_count),
				"method": str(plan.method), "levels": plan.levels}
			if not str(plan.reason).is_empty():
				row["reason"] = str(plan.reason)
			if float(plan.coherence) >= 0.0:
				row["coherence"] = snappedf(float(plan.coherence), 0.0001)
			if not (plan.raw as Array).is_empty() and str(plan.method) != "chain":
				row["generated"] = plan.raw
			if raw_digests:
				row["raw"] = _raw_digests(arrays, mesh.get_surface_format(surface), plan)
			surfaces.append(row)
			if not (plan.lods as Array).is_empty():
				changed += 1
				levels += (plan.lods as Array).size()
		(sidecar.meshes as Array).append({"name": str(mesh.resource_name), "surfaces": plans})
		report.append({"name": str(mesh.resource_name), "model_scale": scale, "surfaces": surfaces})
	return {"sidecar": sidecar, "meshes": report, "changed": changed, "levels": levels,
		"usec": Time.get_ticks_usec() - began}


## For the editor/template parity check: every level generate_lods produces
## on the exact surface, as [triangles, error, sha256 of the indices].
static func _raw_digests(arrays: Array, flags: int, plan: Dictionary) -> Array:
	if str(plan.method) != "chain":
		return []
	var out: Array = []
	for level: Array in LodPolicy.exact_chain(arrays, flags):
		out.append([(level[0] as PackedInt32Array).size() / 3, float(level[1]),
			Format.index_digest(level[0])])
	return out


## Per glTF mesh, the smallest absolute scale of the nodes that draw it (the
## product of node transforms from the scene root), or 1.0 for a mesh no node
## draws. A level switches by screen size, so its edge is set in mesh units
## for the smallest instance (larger instances switch later).
static func mesh_node_scales(state: GLTFState) -> Array:
	var nodes: Array = state.get_nodes()
	var global_bases: Array = []
	global_bases.resize(nodes.size())
	var scales: Array = []
	scales.resize(state.get_meshes().size())
	for node_index: int in nodes.size():
		var node := nodes[node_index] as GLTFNode
		if node == null or node.mesh < 0 or node.mesh >= scales.size():
			continue
		var basis := _global_basis(nodes, node_index, global_bases)
		var scale := basis.get_scale().abs()
		var largest := maxf(scale.x, maxf(scale.y, scale.z))
		if largest > 0.0 and is_finite(largest):
			scales[node.mesh] = largest if scales[node.mesh] == null else minf(float(scales[node.mesh]), largest)
	for mesh_index: int in scales.size():
		if scales[mesh_index] == null:
			scales[mesh_index] = 1.0
	return scales


static func _global_basis(nodes: Array, index: int, memo: Array) -> Basis:
	if memo[index] != null:
		return memo[index]
	var chain: Array[int] = []
	var cursor := index
	while cursor >= 0 and cursor < nodes.size() and memo[cursor] == null and chain.size() <= nodes.size():
		chain.append(cursor)
		cursor = (nodes[cursor] as GLTFNode).parent if nodes[cursor] != null else -1
	var basis := Basis.IDENTITY
	if cursor >= 0 and cursor < nodes.size() and memo[cursor] != null:
		basis = memo[cursor]
	for position: int in range(chain.size() - 1, -1, -1):
		var node := nodes[chain[position]] as GLTFNode
		basis = basis * (node.xform.basis if node != null else Basis.IDENTITY)
		memo[chain[position]] = basis
	return memo[index]


## Writes `bytes` to <root>/<entry.sidecar> unless an identical blob is there.
## Content-addressed, through a temporary file, so concurrent cooks agree.
static func write_blob(root: String, entry: Dictionary, bytes: PackedByteArray) -> bool:
	var path := root.path_join(str(entry.sidecar))
	if FileAccess.file_exists(path) and _file_length(path) == bytes.size() \
			and FileAccess.get_sha256(path) == str(entry.sidecar_sha256):
		return true
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var temporary := "%s.%d.tmp" % [path, OS.get_process_id()]
	var file := FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		return false
	file.store_buffer(bytes)
	file.close()
	if DirAccess.rename_absolute(temporary, path) != OK:
		DirAccess.remove_absolute(temporary)
		return FileAccess.file_exists(path) and FileAccess.get_sha256(path) == str(entry.sidecar_sha256)
	return true


## Applies the catalogued sidecar of `path` with the runtime applier to a fresh
## runtime parse. Returns {status, reason, apply_usec, levels} and, with
## scene_check, {scene_levels, scene_mismatches, unseen_levels}.
static func verify_file(path: String, root: String, catalog: Dictionary, scene_check: bool) -> Dictionary:
	var absolute := ProjectSettings.globalize_path(path)
	var parsed := parse(absolute)
	if int(parsed.error) != OK:
		return {"status": "failed", "reason": "parse"}
	var applied := ActorGeometry.apply(parsed.state, absolute)
	var result := {"status": str(applied.status), "reason": str(applied.reason),
		"apply_usec": int(applied.usec), "levels": int(applied.lods)}
	if not scene_check or str(applied.status) != "applied":
		return result
	var entry: Variant = (catalog.entries as Dictionary).get(path)
	var expected := {}
	if entry is Dictionary:
		var decoded := Format.decode(FileAccess.get_file_as_bytes(root.path_join(str(entry.sidecar))))
		for mesh_plan: Dictionary in (decoded.get("sidecar", {}) as Dictionary).get("meshes", []):
			var counts: Array = []
			for plan: Dictionary in mesh_plan.surfaces:
				counts.append((plan.lods as Array).size())
			expected[str(mesh_plan.name)] = counts
	var scene: Node = (parsed.document as GLTFDocument).generate_scene(parsed.state)
	if scene == null:
		result["scene_mismatches"] = -1
		return result
	var seen := {}
	var levels := 0
	var mismatches := 0
	for node: Node in scene.find_children("*", "MeshInstance3D", true, false):
		var mesh := (node as MeshInstance3D).mesh as ArrayMesh
		if mesh == null or seen.has(mesh.get_rid()):
			continue
		seen[mesh.get_rid()] = str(mesh.resource_name)
		var counts: Array = expected.get(str(mesh.resource_name), [])
		for surface: int in mesh.get_surface_count():
			var server_levels := (RenderingServer.mesh_get_surface(mesh.get_rid(), surface).get("lods", []) as Array).size()
			levels += server_levels
			if surface >= counts.size() or int(counts[surface]) != server_levels:
				mismatches += 1
	scene.free()
	var unseen := 0
	var drawn_names := {}
	for rid: RID in seen:
		drawn_names[str(seen[rid])] = true
	for mesh_name: String in expected:
		if not drawn_names.has(mesh_name):
			for count: int in expected[mesh_name]:
				unseen += count
	result["scene_levels"] = levels
	result["scene_mismatches"] = mismatches
	# Levels of meshes no node of the generated scene draws (never rendered).
	result["unseen_levels"] = unseen
	return result


static func _read_catalog(root: String) -> Dictionary:
	var path := root.path_join(Format.CATALOG_FILE)
	if not FileAccess.file_exists(path):
		return {"error": "missing"}
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(path)) != OK:
		return {"error": "json"}
	var problem := Format.validate_catalog(parser.data)
	return {"error": problem} if not problem.is_empty() else parser.data


static func _file_length(path: String) -> int:
	var file := FileAccess.open(path, FileAccess.READ)
	return file.get_length() if file != null else -1


static func _write_text(path: String, text: String) -> bool:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var temporary := "%s.%d.tmp" % [path, OS.get_process_id()]
	var file := FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(text)
	file.close()
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(path)
	return DirAccess.rename_absolute(temporary, path) == OK
