extends SceneTree

const PATH := preload("res://src/dev/map_authoring_region/path_control.gd")
var assertions := 0
var failures := 0

# In-memory resolved terrain with both a deep central valley and a high ridge.
# No production scenes, files, sculpt layers or editor actions are loaded/saved.
class FixtureTerrain extends Node3D:
	var origin := Vector2(-2.0, -2.0)
	var cell_metres := 1.0
	var grid_size := Vector2i(5, 5)
	var preview_revision := 0
	func sample(ix: int, iz: int) -> float:
		return -4.0 if ix == 2 and iz == 2 else (5.0 if ix == 3 else 1.0)
	func height_at_local(x: float, z: float) -> float:
		var fx := clampf((x - origin.x) / cell_metres, 0.0, float(grid_size.x - 1))
		var fz := clampf((z - origin.y) / cell_metres, 0.0, float(grid_size.y - 1))
		var ix := mini(floori(fx), grid_size.x - 2)
		var iz := mini(floori(fz), grid_size.y - 2)
		var u := fx - ix
		var v := fz - iz
		var a := sample(ix, iz)
		var b := sample(ix + 1, iz)
		var c := sample(ix, iz + 1)
		var d := sample(ix + 1, iz + 1)
		return a + (b - a) * u + (c - a) * v if u + v <= 1.0 else \
			d + (c - d) * (1.0 - u) + (b - d) * (1.0 - v)


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var region := Node3D.new()
	root.add_child(region)
	var terrain := FixtureTerrain.new()
	terrain.name = "Terrain"
	region.add_child(terrain)
	var roads := Node3D.new()
	roads.name = "Roads"
	region.add_child(roads)
	var path = PATH.new()
	path.preview_enabled = false
	roads.add_child(path)
	_check_face(path, terrain, false, false)
	_check_face(path, terrain, true, false)
	_check_face(path, terrain, true, true)
	# Exercise the real road preview branch, including final clockwise winding.
	path.transform = Transform3D.IDENTITY
	path.snapshot_mode = 1
	path.default_width = 3.0
	path.curve = Curve3D.new()
	path.curve.add_point(Vector3(-1.8, 10.0, 0.0))
	path.curve.add_point(Vector3(1.8, 10.0, 0.0))
	var points_before: Array = path.snapshot_points()
	path.preview_enabled = true
	path.call("_refresh_preview")
	var mesh_instance := path.get_node("__PathPreview") as MeshInstance3D
	var arrays: Array = mesh_instance.mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var grounded := true
	var winding := true
	var area := 0.0
	for i in range(0, indices.size(), 3):
		var a := vertices[indices[i]]
		var b := vertices[indices[i + 1]]
		var c := vertices[indices[i + 2]]
		var center := (a + b + c) / 3.0
		grounded = grounded and absf(center.y - terrain.height_at_local(center.x, center.z) - 0.055) < 0.0001
		winding = winding and (c - a).cross(b - a).y > 0.0
		area += absf((b - a).cross(c - a).y) * 0.5
	_check(grounded and winding, "real preview faces conform inside valleys/ridges and remain front-facing")
	_check(absf(area - 10.8) < 0.0001, "real preview retains ribbon footprint area")
	_check(path.snapshot_points() == points_before and mesh_instance.owner == null,
		"preview does not mutate saved controls or acquire saved ownership")
	_time_long_refresh(path, terrain)
	region.free()
	print("road terrain conformance: %d assertions, %d failures" % [assertions, failures])
	quit(1 if failures else 0)


func _check_face(path: Node3D, terrain: Node3D, transformed: bool, exterior: bool) -> void:
	path.transform = Transform3D(Basis(Vector3.UP, 0.43).scaled(Vector3(1.3, 1.0, 0.8)),
		Vector3(0.2, 2.0, -0.3)) if transformed else Transform3D.IDENTITY
	var to_path := path.global_transform.affine_inverse() * terrain.global_transform
	var corners := [Vector3(-1.8, 0.0, -1.6), Vector3(1.8, 0.0, -1.4), Vector3(0.3, 0.0, 1.8)]
	if exterior:
		corners = [Vector3(-3.0, 0.0, -3.0), Vector3(3.0, 0.0, -2.5), Vector3(0.3, 0.0, 3.0)]
	var source := PackedVector3Array()
	var source_uv := PackedVector2Array()
	var source_uv2 := PackedVector2Array()
	for point: Vector3 in corners:
		source.append(to_path * point)
		source_uv.append(Vector2(point.x * 2.0 + point.z, point.z * 3.0))
		source_uv2.append(Vector2(point.x * 0.1 + 0.5, 2.0))
	var vertices := PackedVector3Array()
	var uvs := PackedVector2Array()
	var uv2s := PackedVector2Array()
	var indices := PackedInt32Array()
	path.call("_append_terrain_road_triangle", [0, 1, 2], source, source_uv, source_uv2,
		terrain, vertices, uvs, uv2s, indices)
	var to_terrain := to_path.affine_inverse()
	var grounded := true
	var attributes := true
	var winding := true
	var area := 0.0
	var minimum_oriented_area := INF
	for i in vertices.size():
		var p := to_terrain * vertices[i]
		attributes = attributes and uvs[i].distance_to(Vector2(p.x * 2.0 + p.z, p.z * 3.0)) < 0.0001
		attributes = attributes and uv2s[i].distance_to(Vector2(p.x * 0.1 + 0.5, 2.0)) < 0.0001
	for i in range(0, indices.size(), 3):
		var a := to_terrain * vertices[indices[i]]
		var b := to_terrain * vertices[indices[i + 1]]
		var c := to_terrain * vertices[indices[i + 2]]
		# Evaluate the represented float32 positions in scalar float64; a Vector3
		# cross rounds the nearly cancelling products a second time.
		var signed_area := (float(b.z) - float(a.z)) * (float(c.x) - float(a.x)) - \
			(float(b.x) - float(a.x)) * (float(c.z) - float(a.z))
		minimum_oriented_area = minf(minimum_oriented_area, -signed_area)
		winding = winding and signed_area < 0.0
		area += absf(signed_area) * 0.5
		for weight: Vector3 in [Vector3(0.2, 0.3, 0.5), Vector3(0.6, 0.2, 0.2), Vector3(0.0, 0.5, 0.5)]:
			var p := a * weight.x + b * weight.y + c * weight.z
			grounded = grounded and absf(p.y - terrain.height_at_local(p.x, p.z) - 0.055) < 0.0001
	var expected := absf((corners[1] - corners[0]).cross(corners[2] - corners[0]).y) * 0.5
	_check(indices.size() > 3 and grounded, "subdivision conforms throughout faces, including transformed/clamped terrain")
	_check(absf(area - expected) < 0.0001 and winding,
		"subdivision preserves oriented footprint area (area %.12f expected %.12f minimum orientation %.12f)" % [area, expected, minimum_oriented_area])
	_check(attributes, "cuts interpolate UV and width/feather UV2 without changing projection")


func _time_long_refresh(path: Node3D, terrain: Node3D) -> void:
	path.preview_enabled = false
	path.transform = Transform3D.IDENTITY
	terrain.origin = Vector2(-4.0, -14.0)
	terrain.cell_metres = 2.0
	terrain.grid_size = Vector2i(221, 15)
	var curve := Curve3D.new()
	for index in 850:
		curve.add_point(Vector3(float(index) * 0.5, 2.0, sin(float(index) * 0.04) * 2.0))
	path.curve = curve
	path.default_width = 8.0
	path.point_widths = PackedFloat32Array()
	path.preview_enabled = true
	var started := Time.get_ticks_usec()
	path.call("_refresh_preview")
	var elapsed := float(Time.get_ticks_usec() - started) / 1000.0
	var preview := path.get_node("__PathPreview") as MeshInstance3D
	var arrays: Array = preview.mesh.surface_get_arrays(0)
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	print("synthetic 850-control, 8m road preview: %.3f ms; %d triangles" % [elapsed, indices.size() / 3])
	_check(indices.size() > 0, "representative long-road refresh produces a mesh without saving source")


func _check(condition: bool, message: String) -> void:
	assertions += 1
	if not condition:
		failures += 1
		push_error(message)
