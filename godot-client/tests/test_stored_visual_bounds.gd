extends SceneTree
const Stored := preload("res://src/actors/stored_visual_bounds.gd")
var failures := 0
func _init() -> void:
	var mesh := MeshInstance3D.new(); mesh.mesh = BoxMesh.new()
	var original := mesh.get_aabb()
	if Stored.read(mesh) != original: failures += 1
	var record := {"position":[-1.0,-2.0,-3.0],"size":[2.0,3.0,4.0]}
	mesh.mesh.set_meta("extras",{Stored.KEY:record})
	if Stored.read(mesh) != AABB(Vector3(-1,-2,-3),Vector3(2,3,4)): failures += 1
	if mesh.get_aabb() != original: failures += 1
	for invalid: Dictionary in [{"position":[0,0],"size":[1,1,1]},
		{"position":[0,0,0],"size":[-1,1,1]}, {"position":["bad",0,0],"size":[1,1,1]},
		{"position":[0,0,0],"size":[0,0,0]}, {"position":[NAN,0,0],"size":[1,1,1]}]:
		mesh.mesh.set_meta("extras",{Stored.KEY:invalid})
		if Stored.read(mesh) != original: failures += 1
	mesh.free()
	print("STORED_VISUAL_BOUNDS failures=",failures)
	quit(1 if failures else 0)
