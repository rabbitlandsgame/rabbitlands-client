class_name MissileFlight3D
extends Node3D
## Cosmetic flight over the authoritative shot. Same broadhead/fletching asset
## as the nocked arrow, launched from the fingers, tangent to a shallow arc.
const FLIGHT_SECONDS := 0.25
const ARROW_PATH := "res://assets/actors/native/equipment/ranger_arrow.glb"
var origin := Vector3.ZERO
var destination := Vector3.ZERO
var elapsed := 0.0
var flight_seconds := FLIGHT_SECONDS
var _arc_height := 0.12
var _arrow: Node3D
var _trail := ImmediateMesh.new()
var _trail_material := CombatEffectMesh.material()
var _trail_node: MeshInstance3D

func configure(from_position: Vector3, to_position: Vector3,
		release_origin: Variant = null, ground_target := false) -> void:
	origin = release_origin as Vector3 if release_origin is Vector3 else from_position + Vector3.UP * 1.1
	destination = to_position + Vector3.UP * (0.06 if ground_target else 1.0)
	var distance := origin.distance_to(destination)
	flight_seconds = clampf(distance / 28.0, 0.12, 0.65)
	_arc_height = clampf(distance * 0.025, 0.04, 0.45)
	global_position = origin
	_arrow = GlbSceneCache.instantiate(ARROW_PATH)
	if _arrow != null:
		_arrow.name = "Shaft"
		add_child(_arrow)
	_trail_node = MeshInstance3D.new()
	_trail_node.name = "Trail"
	_trail_node.mesh = _trail
	_trail_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_trail_node)
	_update_visual(0.0)

func point_at(progress: float) -> Vector3:
	return origin.lerp(destination, progress) + Vector3.UP * (4.0 * _arc_height * progress * (1.0-progress))

func _update_visual(progress: float) -> void:
	global_position = point_at(progress)
	var tangent := destination - origin + Vector3.UP * (4.0 * _arc_height * (1.0-2.0*progress))
	if _arrow != null and tangent.length_squared() > 0.00001:
		var up := Vector3.RIGHT if absf(tangent.normalized().dot(Vector3.UP)) > 0.99 else Vector3.UP
		_arrow.look_at(global_position + tangent, up)
	_trail.clear_surfaces()
	_trail.surface_begin(Mesh.PRIMITIVE_TRIANGLES, _trail_material)
	var tail_fraction := minf(progress, 0.055 / flight_seconds)
	for i: int in 8:
		var a := float(i) / 8.0
		var b := float(i+1) / 8.0
		CombatEffectMesh.line(_trail, to_local(point_at(progress-tail_fraction*(1.0-a))),
			to_local(point_at(progress-tail_fraction*(1.0-b))), 0.022*b,
			Color(0.88, 0.79, 0.51, b*0.42))
	_trail.surface_end()

func _process(delta: float) -> void:
	elapsed += delta
	var progress := clampf(elapsed / flight_seconds, 0.0, 1.0)
	_update_visual(progress)
	if progress >= 1.0:
		queue_free()
