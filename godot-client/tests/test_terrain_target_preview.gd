extends SceneTree
const Preview = preload("res://src/world/terrain_target_preview.gd")
var failures := 0
func _init() -> void: run.call_deferred()
func check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error(label)
func run() -> void:
	var center := Vector3(10, 0, -5)
	var slope := Preview.build(center, 4.0,
		func(p: Vector3) -> Vector3: return Vector3(p.x, p.x * 0.4 + p.z * 0.2, p.z))
	check(slope.get_surface_count() == 1, "slope has a footprint")
	for v: Vector3 in slope.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]:
		var p := v + center
		check(is_equal_approx(p.y, p.x * 0.4 + p.z * 0.2 + Preview.LIFT), "all vertices follow slope")
	var steps := Preview.build(Vector3.ZERO, 4.0,
		func(p: Vector3) -> Vector3: return Vector3(p.x, 2.0 if p.x > 0 else 0.0, p.z))
	var vertices: PackedVector3Array = steps.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var upper := false
	var lower := false
	for i: int in range(0, vertices.size(), 3):
		upper = upper or vertices[i].y > 1
		lower = lower or vertices[i].y < 1
		check(is_equal_approx(vertices[i].y, vertices[i+1].y) and is_equal_approx(vertices[i].y, vertices[i+2].y), "no floating bridge across step")
	check(upper and lower, "both step levels remain visible")
	var edge := Preview.build(Vector3.ZERO, 4.0,
		func(p: Vector3) -> Variant: return p if p.x < 0 else null)
	for v: Vector3 in edge.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]:
		check(v.x < 0, "missing ground is not filled")
	var empty := Preview.build(Vector3.ZERO, 1.0, func(_p: Vector3) -> Variant: return null)
	check(empty.get_surface_count() == 0, "all-miss footprint is empty")
	print("terrain target preview failures=", failures)
	quit(failures)
