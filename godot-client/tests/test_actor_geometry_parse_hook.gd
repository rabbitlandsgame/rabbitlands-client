extends SceneTree
## ALOD-C1h: GlbSceneCache's one actor parse helper (_parse_generate) hands the
## parsed state to ActorGeometry.apply after the parse and before
## generate_scene(), so every path that builds an actor scene draws the same
## cooked geometry:
##   main      _build_raw (cache misses, fallbacks, prepared cooks);
##   worker    prepare_actor on a Thread + install_actor_prepared on main;
##   warm-up   prepare on a Thread (packs there) + install_prepared.
## Checked on the RenderingServer surfaces of the built scenes: the planned LOD
## levels and base indices, vertex, attribute, skin and blend shape data
## byte-identical to the plain parse, and the worker results equal to main's.
## The off switch, a file without an entry, a tampered sidecar, a missing
## catalogue, RL heads (out of scope) and documents outside the actor root all
## build exactly the plain parse. The prepared-content actor token names the
## geometry variant (PreparedContent.actor_geometry_variant).

const Format := preload("res://src/actors/actor_geometry_format.gd")
const ActorGeometry := preload("res://src/actors/actor_geometry.gd")
const ActorImages := preload("res://src/actors/actor_images.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const CreaturePayload := preload("res://src/actors/creature_payload.gd")
const Prepared := preload("res://src/world/prepared_content.gd")
const Cache := preload("res://src/actors/glb_scene_cache.gd")

const BODY := "res://assets/actors/native/races/luminous_male.glb"
## Raw-parsed through _build_raw only: an editor checkout imports equipment.
const TORSO := "res://assets/actors/native/equipment/variants/human_male/amberwood_woodland_cuirass_02.glb"
## JOINTS_1/WEIGHTS_1 (8 bone weights).
const CREATURE := "res://assets/actors/native/creatures/ashen_wolf.glb"
## In the actor root, never listed in the fixture catalogue.
const UNLISTED := "res://assets/actors/native/creatures/basic_expansion/cerberus.glb"
const HEAD := "res://assets/actors/native/rl_heads/rl_head_male.glb"
## A glTF outside the actor root (an AT-C2 fixture): never an actor document.
const FOREIGN := "res://tests/fixtures/actor_vram/assets/actors/native/creatures/wolf.glb"
const LINING := "GeneratedArmorBacking"
const ROOT := "user://actor-geometry-hook-test"
const MIN_CHAIN_TRIANGLES := 64
const WORKER_TIMEOUT_MSEC := 120000
## Upper bound for the hook's cost without a catalogue (the release case until
## release packaging installs one): the applier only resolves the path.
const NO_CATALOG_BUDGET_USEC := 2000

var _checks := 0
var _failures := 0
var _saved_environment := {}
var _sidecars := {}
var _plain := {}


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	for variable: String in [ActorGeometry.MODE_ENVIRONMENT, ActorGeometry.ROOT_ENVIRONMENT]:
		_saved_environment[variable] = OS.get_environment(variable)
	_expect(GltfQuantization.ensure_registered(), "glTF extensions register on the main thread")
	_remove_tree(ProjectSettings.globalize_path(ROOT))
	_cook_fixtures()
	print("section: plain builds")
	_build_plain()
	print("section: main path")
	_check_main()
	print("section: worker paths")
	await _check_workers()
	print("section: fail closed")
	_check_fail_closed()
	print("section: prepared token")
	_check_token()
	print("section: costs")
	_check_costs()
	Cache.clear()
	_remove_tree(ProjectSettings.globalize_path(ROOT))
	for variable: String in _saved_environment:
		if str(_saved_environment[variable]).is_empty():
			OS.unset_environment(variable)
		else:
			OS.set_environment(variable, str(_saved_environment[variable]))
	ActorGeometry.reset()
	print("actor geometry parse hook: %s (%d checks)" % ["PASS" if _failures == 0 else "FAIL (%d)" % _failures, _checks])
	quit(1 if _failures > 0 else 0)


# --- fixtures (test-side stand-in for tools/actor_geometry/cook.gd) ---------

func _cook_fixtures() -> void:
	_sidecars[BODY] = _cook(BODY, false)
	_sidecars[TORSO] = _cook(TORSO, true)
	_sidecars[CREATURE] = _cook(CREATURE, false)
	for path: String in _sidecars:
		var sidecar: Dictionary = _sidecars[path]
		_expect(Format.validate_sidecar(sidecar).is_empty(), "the cooked %s sidecar validates" % path.get_file())
		_expect(_planned_levels(sidecar) > 0, "%s: the fixture carries LOD chains" % path.get_file())
	var based := false
	for mesh_plan: Dictionary in (_sidecars[TORSO] as Dictionary).meshes:
		for plan: Dictionary in mesh_plan.surfaces:
			based = based or plan.has("base")
	_expect(based, "the torso fixture replaces its lining's base indices")


## The runtime actor parse (as cook.gd parses), then for every surface of at
## least MIN_CHAIN_TRIANGLES a generate_lods chain; with `mask_lining` the
## lining soup keeps two of every three triangles as its base and no chain.
func _cook(path: String, mask_lining: bool) -> Dictionary:
	var absolute := ProjectSettings.globalize_path(path)
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	ActorImages.enable(state, absolute)
	_expect(CreaturePayload.append(document, absolute, state) == OK, "%s parses for the cook" % path.get_file())
	var sidecar := {"schema": Format.SCHEMA, "policy": Format.POLICY, "engine": Format.engine_identity(),
		"source": {"path": path, "sha256": CreaturePayload.source_sha256(absolute), "bytes": _file_size(absolute)},
		"meshes": []}
	for gltf_mesh: GLTFMesh in state.get_meshes():
		var mesh := gltf_mesh.mesh
		var surfaces: Array = []
		for surface: int in mesh.get_surface_count():
			var arrays := mesh.get_surface_arrays(surface)
			var record := Format.surface_record(arrays)
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			record["lods"] = []
			if str(mesh.resource_name).ends_with(LINING):
				if mask_lining:
					var base := PackedInt32Array()
					for triangle: int in indices.size() / 3:
						if triangle % 3 != 0:
							base.append_array(indices.slice(triangle * 3, triangle * 3 + 3))
					record["base"] = base
			elif indices.size() / 3 >= MIN_CHAIN_TRIANGLES:
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


func _planned_levels(sidecar: Dictionary) -> int:
	var levels := 0
	for mesh_plan: Dictionary in sidecar.meshes:
		for plan: Dictionary in mesh_plan.surfaces:
			levels += (plan.lods as Array).size()
	return levels


## Writes `sidecars` ({res:// path: sidecar}) and a catalogue into `root` and
## points the applier at it in `mode`. Returns the catalogue.
func _install(root: String, sidecars: Dictionary, mode := "sidecar", source_check := "file") -> Dictionary:
	var absolute := ProjectSettings.globalize_path(root)
	DirAccess.make_dir_recursive_absolute(absolute.path_join(Format.BLOB_FOLDER))
	var catalog := Format.new_catalog(source_check)
	for path: String in sidecars:
		var sidecar: Dictionary = sidecars[path]
		var bytes := Format.encode(sidecar)
		var entry := Format.catalog_entry(str(sidecar.source.sha256), int(sidecar.source.bytes), bytes)
		_write(absolute.path_join(str(entry.sidecar)), bytes)
		catalog.entries[path] = entry
	_write(absolute.path_join(Format.CATALOG_FILE), JSON.stringify(catalog, "\t").to_utf8_buffer())
	_use(root, mode)
	return catalog


func _use(root: String, mode: String) -> void:
	OS.set_environment(ActorGeometry.MODE_ENVIRONMENT, mode)
	OS.set_environment(ActorGeometry.ROOT_ENVIRONMENT, ProjectSettings.globalize_path(root))
	ActorGeometry.reset()
	Cache.clear()


# --- plain builds -------------------------------------------------------------

## The reference: each fixture built through the cache with the switch off.
func _build_plain() -> void:
	_install(ROOT + "/off", _sidecars, "off")
	for path: String in [BODY, TORSO, CREATURE]:
		var signature := _built(path)
		_plain[path] = signature
		_expect(not signature.is_empty(), "%s builds plain with the switch off" % path.get_file())
		_expect(_level_count(signature) == 0, "%s: the plain raw parse has no LOD levels" % path.get_file())
	var snapshot := ActorGeometry.snapshot()
	_expect(int(snapshot.reasons.get("off", 0)) == 3 and int(snapshot.statuses.get("skipped", 0)) == 3,
		"the hook runs once per actor build and the off switch skips it (%s)" % snapshot.reasons)


# --- main thread --------------------------------------------------------------

func _check_main() -> void:
	_install(ROOT + "/main", _sidecars)
	for path: String in [BODY, TORSO, CREATURE]:
		var began := _geometry_timing()
		var signature := _built(path)
		_expect_planned(signature, path, "main")
		_expect(int(_geometry_timing().count) == int(began.count) + 1,
			"%s: the cache records one actor_geometry_apply timing" % path.get_file())
	var snapshot := ActorGeometry.snapshot()
	_expect(int(snapshot.statuses.get("applied", 0)) == 3 and int(snapshot.lod_levels) == _planned_levels(_sidecars[BODY]) \
		+ _planned_levels(_sidecars[TORSO]) + _planned_levels(_sidecars[CREATURE]),
		"the applier counts 3 applied files and every planned level (%s)" % snapshot.statuses)
	var retention: Dictionary = Cache.retention_snapshot()
	_expect(retention.get("actor_geometry") is Dictionary and int(retention.actor_geometry.statuses.get("applied", 0)) == 3,
		"GlbSceneCache.retention_snapshot carries the applier's counters")
	_expect((retention.timings.operations as Dictionary).has(&"actor_geometry_apply"),
		"the cache's timings carry actor_geometry_apply")
	# The public instantiate path of a raw-parsed actor (races are never
	# editor-imported) reaches the same helper.
	Cache.clear()
	if Cache._imported_actor_scene(ProjectSettings.globalize_path(BODY)) == null:
		var instance := Cache.instantiate(BODY)
		_expect(instance != null, "instantiate builds the body")
		if instance != null:
			_expect_planned(_server_signature(instance), BODY, "instantiate")
			instance.free()
	# Main and worker must agree: keep main's signatures for the worker checks.
	Cache.clear()


# --- workers ------------------------------------------------------------------

func _check_workers() -> void:
	_install(ROOT + "/worker", _sidecars)
	var main_body := _built(BODY)
	var main_creature := _built(CREATURE)
	for path: String in [BODY, CREATURE]:
		Cache.clear()
		if Cache._imported_actor_scene(ProjectSettings.globalize_path(path)) != null:
			_expect(false, "%s is raw-parsed in this checkout (the worker fixture needs it)" % path.get_file())
			continue
		var result: Variant = await _on_worker(_worker_prepare_actor.bind(ProjectSettings.globalize_path(path)))
		var record: Dictionary = result if result is Dictionary else {}
		_expect(record.get("root") is Node3D and bool(record.get("actor_images", false)),
			"%s: prepare_actor returns a generated root on the worker (%s)" % [path.get_file(), record.get("error", "")])
		if not record.get("root") is Node3D:
			Cache.discard_actor_prepared(record)
			continue
		_expect(Cache.install_actor_prepared(record), "%s: main publishes the worker's root" % path.get_file())
		var signature := _cached_signature(path)
		_expect_planned(signature, path, "prepare_actor")
		_expect(signature == (main_body if path == BODY else main_creature),
			"%s: the worker's surfaces equal the main build's, LOD levels included" % path.get_file())
	# The creature warm-up path: prepare() parses and packs on its worker.
	Cache.clear()
	var canonical := ProjectSettings.globalize_path(CREATURE)
	var warm: Variant = await _on_worker(_worker_prepare.bind(canonical))
	var prepared: Dictionary = warm if warm is Dictionary else {}
	_expect(prepared.get(canonical) is PackedScene, "the warm-up path prepares the creature on its worker")
	Cache.install_prepared(prepared)
	var warmed := _cached_signature(CREATURE)
	_expect_planned(warmed, CREATURE, "prepare")
	_expect(warmed == main_creature, "the warm-up worker's surfaces equal the main build's")
	Cache.clear()


static func _worker_prepare_actor(path: String) -> Dictionary:
	return Cache.prepare_actor(path)


static func _worker_prepare(path: String) -> Dictionary:
	return Cache.prepare(PackedStringArray([path]))


## Runs `callable` on a Thread while main keeps serving frames (a parse or a
## pack may wait for the main thread), then joins it.
func _on_worker(callable: Callable) -> Variant:
	var thread := Thread.new()
	if thread.start(callable) != OK:
		_expect(false, "a worker thread starts")
		return null
	var deadline := Time.get_ticks_msec() + WORKER_TIMEOUT_MSEC
	while thread.is_alive() and Time.get_ticks_msec() < deadline:
		await process_frame
	if thread.is_alive():
		_expect(false, "the worker finishes within %d s" % (WORKER_TIMEOUT_MSEC / 1000))
		return null
	return thread.wait_to_finish()


# --- fail closed ----------------------------------------------------------------

func _check_fail_closed() -> void:
	# A tampered sidecar: rejected, and the cache builds exactly the plain parse.
	var catalog := _install(ROOT + "/tamper", {TORSO: _sidecars[TORSO], BODY: _sidecars[BODY]})
	var blob := ProjectSettings.globalize_path(ROOT + "/tamper").path_join(str(catalog.entries[TORSO].sidecar))
	var bytes := FileAccess.get_file_as_bytes(blob)
	bytes[bytes.size() - 1] = bytes[bytes.size() - 1] ^ 0xff
	_write(blob, bytes)
	_expect(_built(TORSO) == _plain[TORSO], "a tampered sidecar builds the torso exactly as parsed")
	_expect(int(ActorGeometry.snapshot().reasons.get("sidecar_digest", 0)) == 1, "the tampered sidecar is counted once")
	# The rest of the catalogue still applies.
	_expect_planned(_built(BODY), BODY, "beside a rejected entry")
	# Not listed: an actor document the catalogue does not name.
	var unlisted := _built(UNLISTED)
	_expect(not unlisted.is_empty() and _level_count(unlisted) == 0, "an unlisted creature builds as parsed")
	_expect(int(ActorGeometry.snapshot().reasons.get("not_listed", 0)) == 1, "the unlisted file is counted as not_listed")
	# No catalogue at all (an exported build until release packaging installs one).
	var empty := ProjectSettings.globalize_path(ROOT + "/empty")
	DirAccess.make_dir_recursive_absolute(empty)
	_use(ROOT + "/empty", "sidecar")
	_expect(_built(BODY) == _plain[BODY], "without a catalogue the body builds exactly as parsed")
	_expect(int(ActorGeometry.snapshot().reasons.get("no_catalog", 0)) == 1 and ActorGeometry.snapshot().catalog == "absent",
		"the missing catalogue is reported as absent")
	# RL heads keep their authored LODs: the hook runs and skips them.
	_install(ROOT + "/scope", _sidecars)
	var head := Cache._build_raw(ProjectSettings.globalize_path(HEAD))
	_expect(head != null, "the RL head builds raw")
	_expect(int(ActorGeometry.snapshot().reasons.get("out_of_scope", 0)) == 1, "an RL head is out of the applier's scope")
	# A glTF outside the actor root never reaches the applier.
	var before := ActorGeometry.snapshot()
	var timing_before := int(_geometry_timing().count)
	var foreign := Cache._build_raw(ProjectSettings.globalize_path(FOREIGN))
	_expect(foreign != null, "a glTF outside the actor root builds raw")
	_expect(ActorGeometry.snapshot().statuses == before.statuses and int(_geometry_timing().count) == timing_before,
		"a document outside the actor root is not handed to the applier")
	# The editor-only generate mode reaches the helper as well.
	_use(ROOT + "/scope", "generate")
	var generated := _built(BODY)
	_expect(_level_count(generated) > 0 and int(ActorGeometry.snapshot().statuses.get("generated", 0)) == 1,
		"the editor-only generate mode adds runtime LOD levels through the helper")
	_expect(_same_vertices(generated, _plain[BODY]), "generated levels keep the parsed vertices")
	Cache.clear()


# --- prepared-content token -------------------------------------------------

func _check_token() -> void:
	var catalog := _install(ROOT + "/token", {BODY: _sidecars[BODY]})
	var sha := str(catalog.entries[BODY].sidecar_sha256)
	var variant := Prepared.actor_geometry_variant(BODY)
	_expect(variant == "sidecar:" + sha, "the listed body's variant names its sidecar (%s)" % variant)
	_expect(Prepared.actor_geometry_variant(ProjectSettings.globalize_path(BODY)) == variant,
		"an absolute path resolves to the same variant")
	var listed := Prepared.scene_texture_token(BODY)
	_expect(listed.begins_with("scene-images-v2|actor-images|") and listed.ends_with("|geometry=sidecar:" + sha),
		"the actor token carries the geometry variant last (%s)" % listed)
	_expect(Prepared.actor_geometry_variant(UNLISTED).is_empty() and not "geometry=" in Prepared.scene_texture_token(UNLISTED),
		"an unlisted actor keeps the plain token")
	_expect(Prepared.actor_geometry_variant(HEAD).is_empty(), "an RL head has no geometry variant")
	var world := Prepared.scene_texture_token("res://assets/world/interactives/storage.glb")
	_expect(not "geometry=" in world, "world tokens are unchanged (%s)" % world)
	# The switch off: the plain token, the same string the token had before.
	_use(ROOT + "/token", "off")
	var plain := Prepared.scene_texture_token(BODY)
	_expect(not "geometry=" in plain and listed == plain + "|geometry=sidecar:" + sha,
		"with the switch off the body's token is the plain one")
	_use(ROOT + "/token", "generate")
	_expect(Prepared.actor_geometry_variant(BODY) == "generate", "the editor-only generate mode is its own variant")
	# Another sidecar for the same file is another variant.
	var other: Dictionary = (_sidecars[BODY] as Dictionary).duplicate(true)
	for mesh_plan: Dictionary in other.meshes:
		for plan: Dictionary in mesh_plan.surfaces:
			if not (plan.lods as Array).is_empty():
				(plan.lods as Array).resize(1)
	var changed := _install(ROOT + "/token-other", {BODY: other})
	_expect(Prepared.actor_geometry_variant(BODY) == "sidecar:" + str(changed.entries[BODY].sidecar_sha256)
		and Prepared.actor_geometry_variant(BODY) != variant, "a different sidecar is a different variant")
	# A catalogue that does not load, or an entry that does not validate, is plain.
	var garbage := ProjectSettings.globalize_path(ROOT + "/token-garbage")
	DirAccess.make_dir_recursive_absolute(garbage)
	_write(garbage.path_join(Format.CATALOG_FILE), "{not json".to_utf8_buffer())
	_use(ROOT + "/token-garbage", "sidecar")
	_expect(Prepared.actor_geometry_variant(BODY).is_empty(), "a rejected catalogue gives the plain token")
	var renamed := _install(ROOT + "/token-renamed", {BODY: _sidecars[BODY]})
	renamed.entries[BODY].sidecar = "blobs/other.rlgeo"
	_write(ProjectSettings.globalize_path(ROOT + "/token-renamed").path_join(Format.CATALOG_FILE),
		JSON.stringify(renamed, "\t").to_utf8_buffer())
	ActorGeometry.reset()
	_expect(Prepared.actor_geometry_variant(BODY).is_empty(), "an entry that does not validate gives the plain token")


# --- costs ----------------------------------------------------------------------

func _check_costs() -> void:
	var lines := PackedStringArray()
	# Without a catalogue: what every actor parse pays in an exported build
	# today. The first call of a process also reads the switch and looks for
	# the catalogue; later ones only resolve the path.
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(ROOT + "/cost-empty"))
	_use(ROOT + "/cost-empty", "sidecar")
	var first := _hook_usec(CREATURE)
	var best := 1 << 30
	for attempt: int in 5:
		Cache.clear()
		best = mini(best, _hook_usec(CREATURE))
	lines.append("hook without a catalogue (%s): first call %d us, then best of 5 %d us" % [
		CREATURE.get_file(), first, best])
	_expect(best >= 0 and best <= NO_CATALOG_BUDGET_USEC,
		"the hook costs at most %d us without a catalogue (best of 5: %d us)" % [NO_CATALOG_BUDGET_USEC, best])
	# A catalogue listing the file: per first sight of a file the applier reads,
	# hashes, decodes and binds its sidecar and rebuilds the changed meshes; with
	# source_check "file" (developer roots) it also hashes the actor file.
	for source_check: String in ["file", "parsed"]:
		_install("%s/cost-%s" % [ROOT, source_check], _sidecars, "sidecar", source_check)
		var catalog_read := _hook_usec(BODY)
		lines.append("source_check %s: first apply in the process %d us (reads the catalogue)" % [source_check, catalog_read])
		for path: String in [BODY, TORSO, CREATURE]:
			var applied := 1 << 30
			for attempt: int in 3:
				Cache.clear()
				applied = mini(applied, _hook_usec(path))
			lines.append("source_check %s: hook applying %s (%d bytes): best of 3 %d us" % [
				source_check, path.get_file(), _file_size(ProjectSettings.globalize_path(path)), applied])
	var operations: Dictionary = Cache.retention_snapshot().timings.operations
	for operation: StringName in [&"gltf_parse", &"actor_geometry_apply", &"gltf_generate_scene", &"scene_pack"]:
		var row: Dictionary = operations.get(operation, {"count": 0, "total_us": 0})
		lines.append("session mean %s: %d us over %d calls" % [operation, int(row.total_us) / maxi(1, int(row.count)), int(row.count)])
	for line: String in lines:
		print("cost: " + line)


## The hook's own time (the cache's actor_geometry_apply timing) for one raw
## build of `path`.
func _hook_usec(path: String) -> int:
	var before := int(_geometry_timing().total_us)
	_built(path)
	return int(_geometry_timing().total_us) - before


# --- helpers --------------------------------------------------------------------

## Builds `path` through the cache's main-thread raw build and returns the
## RenderingServer signature of an instance ({} when it did not build).
func _built(path: String) -> Dictionary:
	var packed := Cache._build_raw(ProjectSettings.globalize_path(path))
	if packed == null:
		return {}
	var scene := packed.instantiate()
	var signature := _server_signature(scene)
	scene.free()
	return signature


## The RenderingServer signature of the scene the cache now holds for `path`.
func _cached_signature(path: String) -> Dictionary:
	var packed := Cache.packed_scene(path)
	_expect(packed != null, "%s is in the cache" % path.get_file())
	if packed == null:
		return {}
	var scene := packed.instantiate()
	var signature := _server_signature(scene)
	scene.free()
	return signature


## Per distinct mesh of `scene` (traversal order, keyed by name and
## occurrence), per surface: the RenderingServer's vertex and index counts,
## digests of its vertex, attribute, skin, blend shape and index data, and its
## LOD levels as [edge length, index digest].
func _server_signature(scene: Node) -> Dictionary:
	var out := {}
	var seen := {}
	var occurrences := {}
	for node: Node in scene.find_children("*", "MeshInstance3D", true, false):
		var mesh := (node as MeshInstance3D).mesh as ArrayMesh
		if mesh == null or seen.has(mesh.get_rid()):
			continue
		seen[mesh.get_rid()] = true
		var mesh_name := str(mesh.resource_name)
		var occurrence := int(occurrences.get(mesh_name, 0))
		occurrences[mesh_name] = occurrence + 1
		var surfaces: Array = []
		for surface: int in mesh.get_surface_count():
			var server: Dictionary = RenderingServer.mesh_get_surface(mesh.get_rid(), surface)
			var levels: Array = []
			for level: Dictionary in server.get("lods", []):
				levels.append([float(level.get("edge_length", 0.0)), _sha(level.get("index_data"))])
			surfaces.append({"vertex_count": int(server.get("vertex_count", 0)),
				"index_count": int(server.get("index_count", 0)), "format": int(server.get("format", 0)),
				"vertex": _sha(server.get("vertex_data")), "attribute": _sha(server.get("attribute_data")),
				"skin": _sha(server.get("skin_data")), "shapes": _sha(server.get("blend_shape_data")),
				"index": _sha(server.get("index_data")), "lods": levels})
		out["%s#%d" % [mesh_name, occurrence]] = surfaces
	return out


## The planned levels, base index counts and parsed vertices reach the
## RenderingServer; every attribute but the replaced indices equals the plain
## parse.
func _expect_planned(signature: Dictionary, path: String, label: String) -> void:
	var file := "%s (%s)" % [path.get_file(), label]
	_expect(not signature.is_empty(), file + ": builds")
	if signature.is_empty():
		return
	var plain: Dictionary = _plain.get(path, {})
	var sidecar: Dictionary = _sidecars[path]
	var seen := 0
	for mesh_plan: Dictionary in sidecar.meshes:
		var key := "%s#0" % str(mesh_plan.name)
		var surfaces: Variant = signature.get(key)
		if not surfaces is Array:
			continue
		seen += 1
		var plain_surfaces: Array = plain.get(key, [])
		for index: int in (mesh_plan.surfaces as Array).size():
			var plan: Dictionary = mesh_plan.surfaces[index]
			var actual: Dictionary = surfaces[index]
			var where := "%s %s surface %d" % [file, mesh_plan.name, index]
			var expected_indices := (plan.base as PackedInt32Array).size() if plan.has("base") else int(plan.index_count)
			_expect((actual.lods as Array).size() == (plan.lods as Array).size() and int(actual.index_count) == expected_indices
				and int(actual.vertex_count) == int(plan.vertex_count),
				"%s: %d LOD levels, %d indices over %d vertices (planned %d, %d, %d)" % [where, (actual.lods as Array).size(),
				actual.index_count, actual.vertex_count, (plan.lods as Array).size(), expected_indices, plan.vertex_count])
			if index < plain_surfaces.size():
				var reference: Dictionary = plain_surfaces[index]
				_expect(actual.vertex == reference.vertex and actual.attribute == reference.attribute
					and actual.skin == reference.skin and actual.shapes == reference.shapes and actual.format == reference.format,
					where + ": vertex, attribute, skin and blend shape data equal the plain parse")
				_expect((actual.index == reference.index) != plan.has("base"),
					where + ": the index buffer is the parsed one unless the sidecar replaces it")
	_expect(seen == sidecar.meshes.size() and (plain.is_empty() or plain.size() == signature.size()),
		"%s: every planned mesh reaches the scene (%d of %d)" % [file, seen, sidecar.meshes.size()])


func _level_count(signature: Dictionary) -> int:
	var levels := 0
	for key: String in signature:
		for surface: Dictionary in signature[key]:
			levels += (surface.lods as Array).size()
	return levels


func _same_vertices(one: Dictionary, two: Dictionary) -> bool:
	if one.size() != two.size():
		return false
	for key: String in one:
		var left: Array = one[key]
		var right: Array = two.get(key, [])
		if left.size() != right.size():
			return false
		for index: int in left.size():
			if left[index].vertex != right[index].vertex or left[index].index != right[index].index:
				return false
	return true


func _geometry_timing() -> Dictionary:
	var operations: Dictionary = Cache.retention_snapshot().timings.operations
	return operations.get(&"actor_geometry_apply", {"count": 0, "total_us": 0})


func _sha(value: Variant) -> String:
	if not value is PackedByteArray:
		return ""
	return Format.sha256_hex(value)


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
