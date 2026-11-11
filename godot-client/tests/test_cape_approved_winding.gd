extends SceneTree
## The approved cape fits draw without dark slits: CapeApprovedData.fit_mesh
## winds every cloth and trim triangle the way its corners' normals point and
## every lining triangle toward the trunk, as the shared cape's build does
## (eloria-assets/tools/build_shared_cape.py), while keeping the approved
## vertices and triangle set exactly.
## Run with --headless --script res://tests/test_cape_approved_winding.gd.

const APPROVED := preload("res://src/actors/cape_approved_data.gd")
const CAPE := "res://assets/actors/native/equipment/generic_cape.glb"
const CATALOG := "res://data/actors/cape_motion/catalog.json"

var _checks := 0
var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_check_rule()
	var pieces: Array = ReplicatedActor3D._equipment_pieces(CAPE)
	_expect(not pieces.is_empty(), "the shared cape loads")
	if not pieces.is_empty():
		var template := (pieces[0] as Dictionary)["mesh"] as Mesh
		var catalog: Variant = JSON.parse_string(FileAccess.get_file_as_string(CATALOG))
		var fits: Dictionary = (catalog as Dictionary).get("fits", {}) if catalog is Dictionary else {}
		_expect(fits.has("wardrobe") and fits.has("armour"), "both approved fits are listed")
		for profile: String in fits:
			_check_fit(profile, fits[profile] as Dictionary, template)
	GlbSceneCache.clear()
	print("cape approved winding: %s (%d checks)" % [
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures, _checks])
	quit(1 if _failures > 0 else 0)


## The rule on hand-made triangles: Godot's front faces are clockwise.
func _check_rule() -> void:
	var vertices := PackedVector3Array([Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(0, 1, 0)])
	# Clockwise seen from +Z: faces +Z.
	var toward := PackedInt32Array([0, 2, 1])
	var away := PackedInt32Array([0, 1, 2])
	var plus_z := PackedVector3Array([Vector3.BACK, Vector3.BACK, Vector3.BACK])
	_expect(APPROVED.wound(toward, vertices, plus_z, false) == toward,
		"a cloth triangle facing its normals keeps its order")
	_expect(APPROVED.wound(away, vertices, plus_z, false) == PackedInt32Array([0, 2, 1]),
		"a cloth triangle facing against its normals is turned")
	# A lining triangle behind the trunk (z < 0) must face +Z, toward the axis.
	var behind := PackedVector3Array([Vector3(0, 0, -0.3), Vector3(1, 0, -0.3), Vector3(0, 1, -0.3)])
	_expect(APPROVED.wound(away, behind, PackedVector3Array(), true) == PackedInt32Array([0, 2, 1]),
		"a lining triangle facing away from the body is turned")
	_expect(APPROVED.wound(toward, behind, PackedVector3Array(), true) == toward,
		"a lining triangle facing the body keeps its order")


func _check_fit(profile: String, fit: Dictionary, template: Mesh) -> void:
	var mesh := APPROVED.fit_mesh(profile, template)
	_expect(mesh != null, "%s: the approved fit builds" % profile)
	if mesh == null:
		return
	var surfaces: Array = fit.get("surfaces", [])
	var file := str(fit.get("file", ""))
	_expect(mesh.get_surface_count() == surfaces.size(), "%s: every fit surface is built" % profile)
	for i: int in mini(mesh.get_surface_count(), surfaces.size()):
		var surface: Dictionary = surfaces[i]
		var name := str(surface.get("name", ""))
		var lining := APPROVED.is_lining(surface)
		var arrays := mesh.surface_get_arrays(i)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var built: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		var source := APPROVED._view(file, surface.get("indices", {})).to_int32_array()
		var approved := APPROVED._vectors3(APPROVED._floats(file, surface.get("positions", {})))
		_expect(vertices == approved, "%s %s: vertices are the approved ones" % [profile, name])
		_expect(_triangle_set(built) == _triangle_set(source),
			"%s %s: the triangle set is the approved one" % [profile, name])
		var against := 0
		var turned := 0
		for at: int in range(0, built.size(), 3):
			var a := built[at]
			var b := built[at + 1]
			var c := built[at + 2]
			var facing := (vertices[c] - vertices[a]).cross(vertices[b] - vertices[a])
			var wanted := normals[a] + normals[b] + normals[c]
			if lining:
				var centre := (vertices[a] + vertices[b] + vertices[c]) / 3.0
				wanted = Vector3(-centre.x, 0.0, -centre.z)
			if facing.dot(wanted) < 0.0:
				against += 1
			if source[at + 1] != b:
				turned += 1
		_expect(against == 0, "%s %s: no triangle faces %s (%d do)" % [profile, name,
			"away from the body" if lining else "against its normals", against])
		_expect(APPROVED.wound(built, vertices, normals, lining) == built,
			"%s %s: winding is settled (a second pass turns nothing)" % [profile, name])
		print("%s %s: %d of %d triangles turned" % [profile, name, turned, built.size() / 3])


## Each triangle as its sorted corners, so order within a triangle is ignored.
func _triangle_set(indices: PackedInt32Array) -> Array:
	var out: Array = []
	for at: int in range(0, indices.size() - 2, 3):
		var corners := [indices[at], indices[at + 1], indices[at + 2]]
		corners.sort()
		out.append(corners)
	out.sort()
	return out


func _expect(ok: bool, message: String) -> void:
	_checks += 1
	if not ok:
		_failures += 1
		push_error("cape approved winding: " + message)
