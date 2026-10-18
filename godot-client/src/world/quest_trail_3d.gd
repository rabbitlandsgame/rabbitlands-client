extends Node3D
## The server supplies a walkable route. Lightweight chevrons mark only nearby
## loaded ground; both maps retain the rest of the trail at a fixed pixel size.
const COLOUR := Color(0.48, 1.0, 0.24, 0.9)
const SPACING := 4
const RANGE := 55.0
const MAX_VISIBLE := 48
var points := PackedVector3Array()
var _visible: Dictionary = {}
var _flat: ArrayMesh
var _material: StandardMaterial3D
var _elapsed := 0.0
var _nearest := 0

func apply_state(state: Dictionary, adapter: CoordinateAdapter, map_id: String) -> void:
	clear()
	if adapter == null or not bool(state.get("active", false)) \
			or state.get("tutorial", "") != "watchpost" or bool(state.get("paused", false)) \
			or state.get("map", "") != map_id:
		return
	for tile: Array in state.get("route", []):
		points.append(adapter.tile_center(int(tile[0]), int(tile[1])))

func clear() -> void:
	points.clear()
	_nearest = 0
	for node: MeshInstance3D in _visible.values():
		node.queue_free()
	_visible.clear()

func update_trail(delta: float, player: Vector3) -> void:
	_elapsed += delta
	if _elapsed < 0.2:
		return
	_elapsed = 0.0
	var best := INF
	for index: int in points.size():
		var distance := Vector2(points[index].x - player.x, points[index].z - player.z).length_squared()
		if distance < best:
			best = distance
			_nearest = index
	var wanted := {}
	if _flat == null:
		_build_mesh()
	for index: int in range(_nearest + 2, points.size(), SPACING):
		if wanted.size() >= MAX_VISIBLE:
			break
		var point := points[index]
		if Vector2(point.x - player.x, point.z - player.z).length() > RANGE:
			continue
		var height: Variant = GroundDrape.surface_height(get_world_3d().direct_space_state, point.x, point.z)
		if height == null:
			continue # Distant chunks will contribute their ground when loaded.
		wanted[index] = true
		if _visible.has(index):
			continue
		var arrow := MeshInstance3D.new()
		arrow.mesh = _flat
		arrow.material_override = _material
		arrow.layers = MapMarker3D.GAMEPLAY_LAYER
		arrow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(arrow)
		arrow.global_position = Vector3(point.x, float(height), point.z)
		var direction := points[mini(index + 1, points.size() - 1)] - points[maxi(0, index - 1)]
		arrow.rotation.y = atan2(-direction.x, -direction.z)
		var draped := GroundDrape.drape(arrow, _flat, 0.12)
		arrow.mesh = draped if draped != null else _flat
		_visible[index] = arrow
	for index: Variant in _visible.keys():
		if not wanted.has(index):
			(_visible[index] as Node).queue_free()
			_visible.erase(index)

func map_marks() -> Array[Dictionary]:
	var marks: Array[Dictionary] = []
	for index: int in range(_nearest, points.size(), SPACING):
		marks.append({"position": points[index], "type": &"quest_route", "colour": COLOUR,
			"radius": 2.2, "label": "Quest trail"})
	return marks

func _build_mesh() -> void:
	_material = StandardMaterial3D.new()
	_material.albedo_color = COLOUR
	_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(-0.3, 0, 0.24),
		Vector3(0, 0, -0.42), Vector3(0, 0, 0.04), Vector3(0, 0, -0.42),
		Vector3(0.3, 0, 0.24), Vector3(0, 0, 0.04)])
	_flat = ArrayMesh.new()
	_flat.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
