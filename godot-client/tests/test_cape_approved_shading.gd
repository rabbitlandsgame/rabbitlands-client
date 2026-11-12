extends SceneTree
## The approved cape fits draw smooth, without dark slits or facets.
## CapeApprovedData.fit_mesh gives each layer normals welded by position (the
## cloth and trim as one shell, the lining on its own), winds every shell
## triangle the way its corners' normals point and every lining triangle
## toward the trunk, as the shared cape's build does
## (eloria-assets/tools/build_shared_cape.py). The approved vertices, UVs, skin,
## tangent signs and triangle set stay exactly as the fit files hold them.
## Run with --headless --script res://tests/test_cape_approved_shading.gd.

const APPROVED := preload("res://src/actors/cape_approved_data.gd")
const CAPE := "res://assets/actors/native/equipment/generic_cape.glb"
const CATALOG := "res://data/actors/cape_motion/catalog.json"
## Largest normal difference allowed between copies of one position (radians).
const WELDED := 0.0005

var _checks := 0
var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_check_rule()
	_check_weld_rule()
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
	print("cape approved shading: %s (%d checks)" % [
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures, _checks])
	quit(1 if _failures > 0 else 0)


## The winding rule on hand-made triangles: Godot's front faces are clockwise.
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


## A flat square fanned into four triangles around its centre. Three share one
## UV island and face +Z; the fourth is a separate island (its own copies of
## the centre and two corners) wound to face -Z, with stored normals pointing
## -Z: shading turns it to match, and every copy of a position shares one +Z
## normal.
func _check_weld_rule() -> void:
	var centre := Vector3(0.5, 0.5, 0)
	var rim := [Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(1, 1, 0), Vector3(0, 1, 0)]
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	# 0 centre, 1-4 rim (island A); 5 centre, 6 rim[3], 7 rim[0] (island B).
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([centre, rim[0], rim[1], rim[2], rim[3],
		centre, rim[3], rim[0]])
	var stored := PackedVector3Array()
	var tangents := PackedFloat32Array()
	for v: int in 8:
		stored.append(Vector3.BACK if v < 5 else Vector3.FORWARD)
		tangents.append_array([1.0, 0.0, 0.0, 1.0 if v < 5 else -1.0])
	arrays[Mesh.ARRAY_NORMAL] = stored
	arrays[Mesh.ARRAY_TANGENT] = tangents
	# (centre, next, this) faces +Z; island B's (centre, rim[3], rim[0]) faces -Z.
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 2, 1, 0, 3, 2, 0, 4, 3, 5, 6, 7])
	var linings: Array[bool] = [false]
	APPROVED.shade([arrays], linings)
	var p: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var up := 0
	for at: int in range(0, indices.size(), 3):
		var face := (p[indices[at + 2]] - p[indices[at]]).cross(p[indices[at + 1]] - p[indices[at]])
		up += 1 if face.z > 0.0 else 0
	_expect(up == 4, "a mis-wound triangle of a flat sheet is turned to match its neighbours")
	var all_up := true
	for n: Vector3 in normals:
		all_up = all_up and n.is_equal_approx(Vector3.BACK)
	_expect(all_up, "every copy of a position gets the sheet's one smooth normal")
	var tangent_out: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT]
	_expect(tangent_out[3] == 1.0 and tangent_out[31] == -1.0, "tangent signs are kept")


func _check_fit(profile: String, fit: Dictionary, template: Mesh) -> void:
	var started := Time.get_ticks_usec()
	var mesh := APPROVED.fit_mesh(profile, template)
	print("%s fit built in %.1f ms (debug build, first build)" % [
		profile, (Time.get_ticks_usec() - started) / 1000.0])
	_expect(mesh != null, "%s: the approved fit builds" % profile)
	if mesh == null:
		return
	var surfaces: Array = fit.get("surfaces", [])
	var file := str(fit.get("file", ""))
	_expect(mesh.get_surface_count() == surfaces.size(), "%s: every fit surface is built" % profile)
	var layer_normals := {}
	var worst_jump := {}
	for i: int in mini(mesh.get_surface_count(), surfaces.size()):
		var surface: Dictionary = surfaces[i]
		var name := str(surface.get("name", ""))
		var lining := APPROVED.is_lining(surface)
		var layer := "lining" if lining else "shell"
		var arrays := mesh.surface_get_arrays(i)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT]
		var built: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		var source := APPROVED._view(file, surface.get("indices", {})).to_int32_array()
		var approved := APPROVED._vectors3(APPROVED._floats(file, surface.get("positions", {})))
		var source_tangents := APPROVED._floats(file, surface.get("tangents", {}))
		_expect(vertices == approved, "%s %s: vertices are the approved ones" % [profile, name])
		_expect(arrays[Mesh.ARRAY_TEX_UV] == APPROVED._vectors2(APPROVED._floats(file, surface.get("uv", {}))),
			"%s %s: UVs are the approved ones" % [profile, name])
		_expect(_triangle_set(built) == _triangle_set(source),
			"%s %s: the triangle set is the approved one" % [profile, name])
		var unit := true
		var perpendicular := true
		var signs := true
		for v: int in vertices.size():
			var n := normals[v]
			unit = unit and absf(n.length() - 1.0) < 0.001
			var t := Vector3(tangents[v * 4], tangents[v * 4 + 1], tangents[v * 4 + 2])
			perpendicular = perpendicular and absf(t.dot(n)) < 0.002 and absf(t.length() - 1.0) < 0.002
			signs = signs and signf(tangents[v * 4 + 3]) == signf(source_tangents[v * 4 + 3])
			# Welding: every copy of a position in a layer has one normal. The
			# mesh stores normals compressed, so compare within a small angle.
			var key := "%s|%s" % [layer, vertices[v]]
			if layer_normals.has(key):
				var jump := (layer_normals[key] as Vector3).angle_to(n)
				worst_jump[layer] = maxf(float(worst_jump.get(layer, 0.0)), jump)
			else:
				layer_normals[key] = n
		_expect(unit, "%s %s: normals are unit length" % [profile, name])
		_expect(perpendicular, "%s %s: tangents are unit and perpendicular to the normals" % [profile, name])
		_expect(signs, "%s %s: tangent signs are the approved ones" % [profile, name])
		var against := 0
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
		_expect(against == 0, "%s %s: no triangle faces %s (%d do)" % [profile, name,
			"away from the body" if lining else "against its normals", against])
		_expect(APPROVED.wound(built, vertices, normals, lining) == built,
			"%s %s: winding is settled (a second pass turns nothing)" % [profile, name])
	for layer: String in ["shell", "lining"]:
		var jump := float(worst_jump.get(layer, 0.0))
		print("%s %s: largest normal difference between copies of a position %.4f deg" % [
			profile, layer, rad_to_deg(jump)])
		_expect(worst_jump.has(layer) and jump < WELDED,
			"%s %s: copies of a position share one normal (worst %.3f deg)" % [profile, layer, rad_to_deg(jump)])


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
		push_error("cape approved shading: " + message)
