extends SceneTree
## Actor geometry cook (actor LODs C2): the LOD policy (tools/actor_geometry/
## lod_policy.gd) and the cook's per-file steps (tools/actor_geometry/cook.gd),
## on real actor glTFs parsed as the runtime parses them.
##
## Checks: edge lengths encode the distance bands and the pixel-error clamp;
## level selection near 50/25/12/5 %; chains on welded shells and linings are
## valid sidecar levels (ascending edges, shrinking sizes, indices in range);
## per-face-tile soups (torso linings, creature soups) and seam-crossing proxies
## (the cape) get none; the proxy keeps corners on their UV island; the node
## scale reaches the edges; a cooked file is byte-deterministic, its entry and
## blob validate, the runtime applier applies it and the RenderingServer holds
## its levels; a changed source is refused.

const Format := preload("res://src/actors/actor_geometry_format.gd")
const ActorGeometry := preload("res://src/actors/actor_geometry.gd")
const LodPolicy := preload("res://tools/actor_geometry/lod_policy.gd")
const Cook := preload("res://tools/actor_geometry/cook.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")

const NATIVE := "res://assets/actors/native/"
const LEGS := NATIVE + "equipment/variants/human_male/amberwood_woodland_legguards_01.glb"
const TORSO := NATIVE + "equipment/variants/human_male/amberwood_woodland_cuirass_02.glb"
const BODY := NATIVE + "races/luminous_male.glb"
const MOTH := NATIVE + "creatures/amber_lantern_moth.glb"
const CAPE := NATIVE + "equipment/generic_cape.glb"
## Rigid prop nodes at 0.82 and 0.36 scale beside the 1.0 body mesh.
const DUELIST := NATIVE + "creatures/crimson_duelist.glb"
const ROOT := "user://actor-geometry-cook-test"

var _checks := 0
var _failures := 0
var _saved_environment := {}


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	for variable: String in [ActorGeometry.MODE_ENVIRONMENT, ActorGeometry.ROOT_ENVIRONMENT]:
		_saved_environment[variable] = OS.get_environment(variable)
	_expect(GltfQuantization.ensure_registered(), "glTF extensions register on the main thread")
	_remove_tree(ProjectSettings.globalize_path(ROOT))
	print("section: edges")
	_check_edges()
	print("section: selection")
	_check_selection()
	print("section: surfaces")
	_check_surfaces()
	print("section: proxy")
	_check_proxy()
	print("section: cook")
	_check_cook()
	_remove_tree(ProjectSettings.globalize_path(ROOT))
	for variable: String in _saved_environment:
		if str(_saved_environment[variable]).is_empty():
			OS.unset_environment(variable)
		else:
			OS.set_environment(variable, str(_saved_environment[variable]))
	ActorGeometry.reset()
	print("actor geometry cook: %s (%d checks)" % ["PASS" if _failures == 0 else "FAIL (%d)" % _failures, _checks])
	quit(1 if _failures > 0 else 0)


# --- edges --------------------------------------------------------------------

func _check_edges() -> void:
	_expect(absf(LodPolicy.lod_multiplier() - 1.658) < 0.001,
		"the reference camera's LOD multiplier is 2 tan(hfov/2) = %.4f (50 deg vertical, 16:9)" % LodPolicy.lod_multiplier())
	for target: int in LodPolicy.BAND_METRES.size():
		var band := LodPolicy.BAND_METRES[target]
		var edge := LodPolicy.edge_for(target, 0.0, 1.0)
		_expect(absf(LodPolicy.switch_depth(edge) - band) < 1.0e-4,
			"a lossless level for target %d starts at its %.0f m band at lod_bias 1 (got %.4f m)" % [
			target, band, LodPolicy.switch_depth(edge)])
		_expect(absf(LodPolicy.switch_depth(edge, 1.0, 0.35) - band * 0.35) < 1.0e-4,
			"Low's lod_bias 0.35 moves the %.0f m band to %.1f m" % [band, band * 0.35])
		var small := LodPolicy.edge_for(target, 0.0, 0.25)
		_expect(absf(LodPolicy.switch_depth(small, 0.25) - band) < 1.0e-4,
			"on a model drawn at 0.25 scale the band still starts at %.0f m" % band)
	# The error clamp: a level whose error is 0.3 m draws no earlier than where
	# 0.3 m covers MAX_ERROR_PX pixels at the reference width.
	var coarse := LodPolicy.edge_for(0, 0.3, 1.0)
	_expect(is_equal_approx(coarse, 0.3 / LodPolicy.MAX_ERROR_PX), "a coarse level's edge is error / MAX_ERROR_PX")
	var depth := LodPolicy.switch_depth(coarse)
	var pixels := 0.3 * LodPolicy.REFERENCE_WIDTH_PX / (depth * LodPolicy.lod_multiplier())
	_expect(absf(pixels - LodPolicy.MAX_ERROR_PX) < 1.0e-3,
		"at its switch depth (%.1f m) the level's error covers %.2f px" % [depth, pixels])
	_expect(is_equal_approx(LodPolicy.edge_for(0, 0.3, 0.25), coarse),
		"the error clamp does not depend on the model's scale")


# --- selection ----------------------------------------------------------------

func _check_selection() -> void:
	var base := 1000
	var chosen := LodPolicy.select_levels(_fake_raw([500, 240, 120, 60, 30, 14]), base)
	_expect(_triangles_of(chosen) == [500, 240, 120, 60] and _targets_of(chosen) == [0, 1, 2, 3],
		"a halving chain keeps the levels nearest 50/25/12/5 %% (%s)" % [_triangles_of(chosen)])
	chosen = LodPolicy.select_levels(_fake_raw([520, 100, 40]), base)
	_expect(_triangles_of(chosen) == [520, 100, 40] and _targets_of(chosen) == [0, 2, 3],
		"a target with no level within 1.5x is skipped, not filled with a far level (%s, targets %s)" % [
		_triangles_of(chosen), _targets_of(chosen)])
	chosen = LodPolicy.select_levels(_fake_raw([900, 800]), base)
	_expect(chosen.is_empty(), "levels far from every target (90 %, 80 %) are not kept")
	chosen = LodPolicy.select_levels(_fake_raw([50, 24]), 100)
	_expect(_triangles_of(chosen) == [50], "levels under %d triangles are never kept" % LodPolicy.MIN_LEVEL_TRIANGLES)


func _fake_raw(sizes: Array) -> Array:
	var raw: Array = []
	var error := 0.01
	for size: int in sizes:
		var indices := PackedInt32Array()
		indices.resize(size * 3)
		raw.append([indices, error])
		error *= 2.0
	return raw


func _triangles_of(chosen: Array) -> Array:
	var out: Array = []
	for item: Dictionary in chosen:
		out.append(int(item.triangles))
	return out


func _targets_of(chosen: Array) -> Array:
	var out: Array = []
	for item: Dictionary in chosen:
		out.append(int(item.target))
	return out


# --- surfaces -------------------------------------------------------------------

func _check_surfaces() -> void:
	var legs := _surfaces(LEGS)
	var shell: Dictionary = legs.get("Bark Legguards", {})
	_expect(not shell.is_empty() and str(shell.plan.method) == "chain" and (shell.plan.lods as Array).size() >= 2,
		"the legguard shell gets a chain of %d levels" % (shell.get("plan", {}).get("lods", []) as Array).size())
	for name: String in legs:
		_check_levels(LEGS.get_file() + " " + name, legs[name])
	var lining: Dictionary = legs.get("GeneratedLegBacking", {})
	_expect(not lining.is_empty() and (lining.plan.lods as Array).size() == 4,
		"the welded leg lining gets four levels (it is not a per-face-tile soup)")
	var torso := _surfaces(TORSO)
	var backing: Dictionary = torso.get("GeneratedArmorBacking", {})
	_expect(not backing.is_empty() and str(backing.plan.method) == "none" and str(backing.plan.reason) == "per_face_tiles"
		and float(backing.plan.coherence) < LodPolicy.COHERENCE,
		"the torso lining soup (per-face atlas tiles, coherence %.2f) gets no chain" % float(backing.get("plan", {}).get("coherence", -1.0)))
	_check_levels(TORSO.get_file() + " shell", torso.get("Mossbound Coat", {}))
	var moth := _surfaces(MOTH)
	for name: String in moth:
		_expect(str(moth[name].plan.reason) == "per_face_tiles", "the moth soup (per-face UV tiles) gets no chain")
	var cape := _surfaces(CAPE)
	for name: String in cape:
		var plan: Dictionary = cape[name].plan
		_expect(str(plan.reason) == "seams" and (plan.lods as Array).is_empty() and not (plan.raw as Array).is_empty(),
			"cape surface %s: the proxy levels cross UV seams and are refused (raw %s)" % [name, plan.raw])
	var body := _surfaces(BODY)
	_expect(str(body.get("eyes", {}).get("plan", {}).get("reason", "")) == "small", "a 54-triangle surface keeps its base")
	_check_levels(BODY.get_file() + " body", body.get("body", {}))
	# Determinism: two fresh parses plan byte-identical levels.
	var again := _surfaces(LEGS)
	var same := true
	for name: String in legs:
		same = same and var_to_bytes(legs[name].plan.lods) == var_to_bytes(again[name].plan.lods)
	_expect(same and not legs.is_empty(), "planning the same parse twice gives byte-identical levels")


## {mesh name suffix after the file stem: {arrays, plan}} for surface 0 of
## every mesh, planned as the cook plans it (model scale 1).
func _surfaces(path: String) -> Dictionary:
	var parsed := Cook.parse(ProjectSettings.globalize_path(path))
	_expect(int(parsed.error) == OK, "%s parses" % path.get_file())
	var out := {}
	if int(parsed.error) != OK:
		return out
	var stem := path.get_file().get_basename() + "_"
	for gltf_mesh: GLTFMesh in parsed.state.get_meshes():
		var mesh := gltf_mesh.mesh
		var arrays := mesh.get_surface_arrays(0)
		var name := str(mesh.resource_name).trim_prefix(stem)
		out[name] = {"arrays": arrays, "plan": LodPolicy.plan_surface(arrays, mesh.get_surface_format(0),
			mesh.get_surface_primitive_type(0), 1.0)}
	return out


func _check_levels(label: String, surface: Dictionary) -> void:
	if surface.is_empty():
		_expect(false, label + ": surface found")
		return
	var plan: Dictionary = surface.plan
	var record := Format.surface_record(surface.arrays)
	record["lods"] = plan.lods
	_expect(Format.validate_surface(record).is_empty(), "%s: the planned levels are a valid sidecar surface (%s)" % [
		label, Format.validate_surface(record)])
	var previous_edge := 0.0
	var previous_size := int(record.index_count)
	var ok := true
	for index: int in (plan.levels as Array).size():
		var level: Array = plan.levels[index]
		var triangles := int(level[0])
		var edge := float(level[1])
		var error := float(level[2])
		var target := int(level[3])
		ok = ok and edge > previous_edge and triangles * 3 < previous_size
		ok = ok and edge >= LodPolicy.edge_for(target, 0.0, 1.0) - 1.0e-9 and edge >= error / LodPolicy.MAX_ERROR_PX - 1.0e-9
		var ratio := float(triangles) / float(record.index_count / 3) / LodPolicy.TARGET_FRACTIONS[target]
		ok = ok and ratio <= LodPolicy.TARGET_TOLERANCE + 1.0e-6 and ratio >= 1.0 / LodPolicy.TARGET_TOLERANCE - 1.0e-6
		ok = ok and triangles >= LodPolicy.MIN_LEVEL_TRIANGLES
		previous_edge = edge
		previous_size = triangles * 3
	_expect(ok, "%s: %d levels ascend in edge, shrink, sit near their targets and respect band and error floors %s" % [
		label, (plan.levels as Array).size(), plan.levels])


# --- proxy ---------------------------------------------------------------------

func _check_proxy() -> void:
	# A welded grid with a UV seam down the middle (x = 0.5): the left chart has
	# u in [0, 0.25], the right chart u in [0.5, 0.75]. The seam column's right
	# copies come first, so a position's first vertex is the RIGHT one: only the
	# island-aware mapping gives left triangles their left copies.
	var arrays := _seam_grid(24)
	var welded := LodPolicy.weld(arrays)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	_expect(float(welded.coherence) < 1.0 and float(welded.coherence) > 0.9,
		"the seam grid's welded corners mostly agree on UV (%.3f)" % float(welded.coherence))
	var chain := LodPolicy.proxy_chain(arrays, welded)
	_expect(not chain.is_empty(), "the welded proxy simplifies (%d levels)" % chain.size())
	for level: Array in chain:
		var indices: PackedInt32Array = level[0]
		var in_range := true
		var single_chart := 0
		var left_wrong := 0
		for corner: int in range(0, indices.size(), 3):
			var charts := {}
			var all_left := true
			var any_inside := false
			for offset: int in 3:
				var vertex := indices[corner + offset]
				in_range = in_range and vertex >= 0 and vertex < vertices.size()
				if not in_range:
					break
				charts[uvs[vertex].x >= 0.5] = true
				all_left = all_left and vertices[vertex].x <= 0.5 + 1.0e-6
				any_inside = any_inside or vertices[vertex].x < 0.5 - 1.0e-6
			if not in_range:
				break
			single_chart += int(charts.size() == 1)
			if all_left and any_inside and charts.has(true):
				left_wrong += 1
		var triangles := indices.size() / 3
		_expect(in_range, "proxy level of %d triangles: every index addresses an original vertex" % triangles)
		_expect(left_wrong == 0,
			"proxy level of %d triangles: triangles left of the seam keep the left chart's UVs (%d do not)" % [triangles, left_wrong])
		_expect(absf(float(single_chart) / triangles - float(level[2])) < 1.0e-6,
			"proxy level of %d triangles: the island share %.3f is the share drawn from one chart" % [triangles, float(level[2])])


## A (n x n)-quad relief grid over x, z in [0, 1], welded inside each UV
## chart, with the seam column duplicated (right chart's copies first).
func _seam_grid(n: int) -> Array:
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var ids := {}
	var half := n / 2
	for chart: int in [1, 0]:
		for i: int in range(half if chart == 1 else 0, (n if chart == 1 else half) + 1):
			for j: int in n + 1:
				var x := float(i) / n
				var z := float(j) / n
				ids[Vector3i(chart, i, j)] = vertices.size()
				# Relief, so the simplifier keeps a real chain.
				vertices.append(Vector3(x, 0.08 * sin(6.0 * x) * cos(5.0 * z) + 0.03 * sin(13.0 * x + 3.0 * z), z))
				normals.append(Vector3.UP)
				uvs.append(Vector2(0.5 + x * 0.5 if chart == 1 else x * 0.5, z))
	var indices := PackedInt32Array()
	for i: int in n:
		var chart := 1 if i >= half else 0
		for j: int in n:
			var a: int = ids[Vector3i(chart, i, j)]
			var b: int = ids[Vector3i(chart, i + 1, j)]
			var c: int = ids[Vector3i(chart, i + 1, j + 1)]
			var d: int = ids[Vector3i(chart, i, j + 1)]
			indices.append_array([a, c, b, a, d, c])
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	return arrays


# --- cook ------------------------------------------------------------------------

func _check_cook() -> void:
	var root := ProjectSettings.globalize_path(ROOT)
	var item := _item(LEGS)
	var first := Cook.cook_file(item, root, "f".repeat(64))
	_expect(str(first.summary.status) == "cooked" and first.has("entry"),
		"the legguards cook (%s %s)" % [first.summary.status, first.summary.get("reason", "")])
	if not first.has("entry"):
		return
	var entry: Dictionary = first.entry
	_expect(Format.validate_entry(JSON.parse_string(JSON.stringify(entry))).is_empty(),
		"the catalogue entry validates after JSON")
	_expect(str(entry.get("inputs", {}).get("policy_digest", "")) == "f".repeat(64), "the entry records the policy digest")
	var bytes := FileAccess.get_file_as_bytes(root.path_join(str(entry.sidecar)))
	_expect(bytes.size() == int(entry.sidecar_bytes) and Format.sha256_hex(bytes) == str(entry.sidecar_sha256),
		"the blob is written content-addressed")
	var decoded := Format.decode(bytes)
	_expect(decoded.has("sidecar"), "the blob decodes and validates (%s)" % decoded.get("error", ""))
	var second := Cook.cook_file(item, root, "f".repeat(64))
	_expect(second.get("entry") == entry, "cooking the same file again gives the same entry (deterministic bytes)")
	_expect(int(first.summary.lod_levels) == _levels_in(decoded.get("sidecar", {})),
		"the summary counts the sidecar's %d levels" % int(first.summary.lod_levels))

	var stale := _item(LEGS)
	stale.file_sha256 = "0".repeat(64)
	_expect(str(Cook.cook_file(stale, root, "").summary.reason) == "source_changed",
		"a file whose bytes differ from the planner's hash is refused")
	var moth := Cook.cook_file(_item(MOTH), root, "")
	_expect(str(moth.summary.status) == "unchanged" and not moth.has("entry"),
		"a file with no chain gets no sidecar or entry")

	var scaled := Cook.parse(ProjectSettings.globalize_path(DUELIST))
	var scales := Cook.mesh_node_scales(scaled.state)
	var smallest := 1.0
	for value: Variant in scales:
		smallest = minf(smallest, float(value))
	_expect(scales.size() == (scaled.state as GLTFState).get_meshes().size() and absf(smallest - 0.36) < 0.01,
		"node scales reach the meshes (%s)" % [scales])
	var duelist := Cook.cook_file(_item(DUELIST, 2.0), root, "")
	var floor_ok := true
	for mesh: Dictionary in duelist.summary.get("meshes", []):
		for surface: Dictionary in mesh.surfaces:
			for level: Array in surface.levels:
				floor_ok = floor_ok and float(level[1]) >= LodPolicy.edge_for(int(level[3]), 0.0, float(mesh.model_scale)) - 1.0e-9
	_expect(str(duelist.summary.status) == "cooked" and floor_ok,
		"edges use the file scale times the node scale (bands hold in world metres)")

	# The runtime applier takes the cooked catalogue; the RenderingServer
	# holds the levels after generate_scene.
	var catalog := Format.new_catalog("file")
	catalog.entries[LEGS] = entry
	var file := FileAccess.open(root.path_join(Format.CATALOG_FILE), FileAccess.WRITE)
	file.store_string(JSON.stringify(catalog))
	file.close()
	OS.set_environment(ActorGeometry.MODE_ENVIRONMENT, "sidecar")
	OS.set_environment(ActorGeometry.ROOT_ENVIRONMENT, root)
	ActorGeometry.reset()
	var parsed_catalog: Dictionary = JSON.parse_string(JSON.stringify(catalog))
	var verified := Cook.verify_file(LEGS, root, parsed_catalog, true)
	_expect(str(verified.status) == "applied" and int(verified.levels) == int(first.summary.lod_levels),
		"the runtime applier applies the cooked sidecar (%s %s, %d levels)" % [verified.status, verified.reason, int(verified.get("levels", 0))])
	_expect(int(verified.get("scene_mismatches", -1)) == 0 and int(verified.get("scene_levels", 0)) == int(first.summary.lod_levels),
		"the RenderingServer holds all %d cooked levels (%d seen, %d mismatches)" % [
		int(first.summary.lod_levels), int(verified.get("scene_levels", 0)), int(verified.get("scene_mismatches", -1))])
	var unlisted := Cook.verify_file(TORSO, root, parsed_catalog, true)
	_expect(str(unlisted.status) == "rejected" and str(unlisted.reason) == "not_listed",
		"a file the catalogue does not list stays as parsed")


func _item(path: String, model_scale := 1.0) -> Dictionary:
	var absolute := ProjectSettings.globalize_path(path)
	return {"path": path, "file_sha256": FileAccess.get_sha256(absolute), "bytes": 0, "model_scale": model_scale}


func _levels_in(sidecar: Dictionary) -> int:
	var levels := 0
	for mesh: Dictionary in sidecar.get("meshes", []):
		for surface: Dictionary in mesh.surfaces:
			levels += (surface.lods as Array).size()
	return levels


# --- helpers -------------------------------------------------------------------

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
