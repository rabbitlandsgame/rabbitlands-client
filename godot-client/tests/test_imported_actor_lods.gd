extends SceneTree
## Actor/equipment GLBs must keep Godot's imported LOD chains in production,
## while raw external candidates remain usable in lean and authoring tests.

const Extras := preload("res://src/actors/glb_mesh_extras.gd")
const BODY := "res://assets/actors/native/races/luminous_male.glb"
# The Human male fits (each generated piece's base scene since the P7 cleanup).
const TORSO := "res://assets/actors/native/equipment/variants/human_male/amberwood_woodland_cuirass_01.glb"
const HELM := "res://assets/actors/native/equipment/variants/human_male/amberwood_forest_helm_01.glb"

var _checks := 0
var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_check_minimal_extras_reader()
	_check_cached_actor_body()
	_check_cached_equipment_resources()
	_check_external_fallback()
	GlbSceneCache.clear()
	print("imported actor LODs: %s (%d checks)" % [
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures, _checks])
	quit(1 if _failures > 0 else 0)


func _check_minimal_extras_reader() -> void:
	var torso := Extras.read(TORSO)
	var backing := torso.get("GeneratedArmorBacking", {}) as Dictionary
	var cover := backing.get("bodyCover", []) as Array
	_expect(cover.size() == 3 and float(cover[0]) > 0.0,
		"the JSON-only reader recovers fitted torso coverage")
	var helm := Extras.read(HELM)
	var covers_hair := false
	for extras_value: Variant in helm.values():
		var extras := extras_value as Dictionary
		covers_hair = covers_hair or bool(extras.get("coversHair", false))
	_expect(covers_hair, "the JSON-only reader recovers helmet hair coverage")
	_expect(Extras.read("res://does-not-exist.glb").is_empty(),
		"missing metadata files fail closed")


func _check_cached_actor_body() -> void:
	GlbSceneCache.clear()
	var body := GlbSceneCache.instantiate(BODY)
	_expect(body != null, "the actor body loads through the shared scene cache")
	if body == null:
		return
	var body_lods := _tree_lod_count(body)
	var imported := GlbSceneCache._imported_actor_scene(
		ProjectSettings.globalize_path(BODY))
	if imported != null:
		var imported_instance := imported.instantiate() as Node3D
		var imported_lods := _tree_lod_count(imported_instance)
		_expect(imported_lods > 0 and body_lods == imported_lods,
			"the cached actor body retains all imported LOD chains")
		imported_instance.free()
	else:
		_expect(body_lods == 0,
			"a lean actor body fallback does not generate LODs at runtime")
	body.free()


func _check_cached_equipment_resources() -> void:
	GlbSceneCache.clear()
	var first := GlbSceneCache.instantiate(TORSO)
	var second := GlbSceneCache.instantiate(
		ProjectSettings.globalize_path(TORSO))
	_expect(first != null and second != null,
		"resource and absolute paths both instantiate the cached equipment scene")
	if first == null or second == null:
		_free_nodes([first, second])
		return
	var first_meshes := _meshes_by_name(first)
	var second_meshes := _meshes_by_name(second)
	_expect(first_meshes.size() == 2 and second_meshes.size() == 2,
		"the fitted torso keeps both imported mesh pieces")
	for mesh_name: String in first_meshes:
		var one := first_meshes[mesh_name] as MeshInstance3D
		var two := second_meshes.get(mesh_name) as MeshInstance3D
		_expect(two != null and is_same(one.mesh, two.mesh),
			"cached instances share %s geometry" % mesh_name)

	var pieces: Array = ReplicatedActor3D._equipment_pieces(TORSO)
	_expect(pieces.size() == first_meshes.size(),
		"equipment extraction consumes one cached scene instance")
	var piece_lods := 0
	for piece_value: Variant in pieces:
		var piece := piece_value as Dictionary
		var source := first_meshes.get(str(piece.get("name", ""))) as MeshInstance3D
		_expect(source != null and is_same(piece.get("mesh") as Mesh, source.mesh),
			"equipment retains the cached %s mesh resource" % piece.get("name", ""))
		if source == null:
			continue
		_expect((piece.get("transform", Transform3D.IDENTITY) as Transform3D
			).is_equal_approx(ReplicatedActor3D._relative_transform(source, first)),
			"equipment retains %s's accumulated transform" % source.name)
		_expect(int(piece.get("binds", []).size()) == (
			source.skin.get_bind_count() if source.skin != null else 0),
			"equipment retains %s's skin bind contract" % source.name)
		_expect(is_same(piece.get("material_override") as Material,
				source.material_override)
			and is_equal_approx(float(piece.get("lod_bias", 0.0)), source.lod_bias),
			"equipment retains %s's node render state" % source.name)
		piece_lods += _mesh_lod_count(piece.get("mesh") as Mesh)

	# This branch is taken in an editor/imported checkout and in an export. A
	# lean source-only checkout intentionally takes the raw fallback instead.
	var imported := GlbSceneCache._imported_actor_scene(
		ProjectSettings.globalize_path(TORSO))
	if imported != null:
		var imported_instance := imported.instantiate() as Node3D
		var imported_lods := _tree_lod_count(imported_instance)
		_expect(imported_lods > 0,
			"the production PackedScene contains generated LOD index chains")
		_expect(piece_lods == imported_lods,
			"equipment extraction preserves every imported LOD chain")
		imported_instance.free()
	else:
		_expect(piece_lods == 0,
			"a lean checkout uses the raw fallback without generating runtime LODs")
	_free_nodes([first, second])


func _check_external_fallback() -> void:
	var source := ProjectSettings.globalize_path(TORSO)
	var candidate := ProjectSettings.globalize_path(
		TORSO.get_base_dir() + "/_external-equipment-lod-fallback.glb")
	var copy_error := DirAccess.copy_absolute(source, candidate)
	_expect(copy_error == OK, "the external fallback fixture can be staged")
	if copy_error != OK:
		return
	GlbSceneCache.clear()
	var scene := GlbSceneCache.instantiate(candidate)
	_expect(scene != null and _meshes_by_name(scene).size() == 2,
		"an external GLB still loads through the raw parser fallback")
	var pieces: Array = ReplicatedActor3D._equipment_pieces(candidate)
	_expect(pieces.size() == 2,
		"external equipment still feeds the fitting pipeline")
	var has_cover := false
	for piece_value: Variant in pieces:
		var cover: Array = (piece_value as Dictionary).get("body_cover", []) as Array
		has_cover = has_cover or cover.size() == 3
	_expect(has_cover,
		"external equipment metadata survives without a duplicate mesh import")
	if scene != null:
		scene.free()
	DirAccess.remove_absolute(candidate)


func _meshes_by_name(parent: Node) -> Dictionary:
	var meshes: Dictionary = {}
	if parent == null:
		return meshes
	for node_value: Node in parent.find_children("*", "MeshInstance3D", true, false):
		var mesh := node_value as MeshInstance3D
		if mesh.mesh != null:
			meshes[str(mesh.name)] = mesh
	return meshes


func _tree_lod_count(parent: Node) -> int:
	var count := 0
	for mesh: MeshInstance3D in _meshes_by_name(parent).values():
		count += _mesh_lod_count(mesh.mesh)
	return count


func _mesh_lod_count(mesh: Mesh) -> int:
	if mesh is not ArrayMesh:
		return 0
	var surfaces: Variant = mesh.get("_surfaces")
	if surfaces is not Array:
		return 0
	var count := 0
	for surface_value: Variant in surfaces as Array:
		if surface_value is not Dictionary:
			continue
		var lods: Variant = (surface_value as Dictionary).get("lods", {})
		if lods is Array:
			count += (lods as Array).size()
		elif lods is Dictionary:
			count += (lods as Dictionary).size()
	return count


func _free_nodes(nodes: Array) -> void:
	for node_value: Variant in nodes:
		var node := node_value as Node
		if node != null:
			node.free()


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if condition:
		return
	_failures += 1
	push_error("FAIL: " + message)
