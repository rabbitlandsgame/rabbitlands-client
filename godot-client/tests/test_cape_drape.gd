extends SceneTree
## The cape's yoke is pushed out of the worn torso without tearing a sliver off.
##
## `CapeDrape.drape` pushes each yoke vertex straight out along its bearing to
## the torso's reach, faded off past the point of the shoulder and up into the
## collar. Unlimited, that push changed fastest exactly where the fades fall
## off: at the sides of the collar a coat's shoulder stands 140 mm out along a
## collar vertex's bearing, one vertex went out 110 mm while the one 30 mm above
## it moved 20, and the edge between them stretched 3.6 to 4.9 times - a spike
## of cloth over the shoulder on every torso of the ladder. These wear the real
## cape over the bulkiest Human torsos and measure the cloth.

const CAPE := "res://assets/actors/native/equipment/generic_cape.glb"
const TORSOS := [
	"res://assets/actors/native/equipment/variants/human_male/eloria_frontier_shirt_01.glb",
	"res://assets/actors/native/equipment/variants/human_male/militia_torso_armor_03.glb",
	"res://assets/actors/native/equipment/variants/human_female/eloria_arcane_armor_08.glb",
	"res://assets/actors/native/equipment/variants/human_female/eloria_frontier_shirt_01.glb",
]
## An edge may lengthen by its own rest length (SLOPE 1) plus what the ring
## gains from going out along diverging bearings; measured, the worst is 1.98.
const MAX_STRETCH := 2.2
## Edges shorter than this are rounding at the welded seams, not cloth.
const MIN_EDGE := 0.005
## Where the push is full, the slope limit may hold a vertex back from the
## reach by no more than this.
const HELD_BACK := 0.005

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _expect(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		_failures += 1
		push_error("cape drape: " + message)
		print("  FAIL ", message)


## Every mesh of an equipment scene, as the actor reads them: the mesh and,
## for a skinned one, the bone name behind each skin bind.
func _pieces(path: String) -> Array:
	var pieces: Array = []
	var scene: PackedScene = load(path) as PackedScene
	if scene == null:
		return pieces
	var root: Node = scene.instantiate()
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		var names := PackedStringArray()
		if mesh_node.skin != null:
			for bind: int in range(mesh_node.skin.get_bind_count()):
				names.append(mesh_node.skin.get_bind_name(bind))
		pieces.append({"mesh": mesh_node.mesh, "bones": names})
	root.free()
	return pieces


## How much of a vertex the spine holds (no cape_ bone), as the drape reads it.
func _rigid(bones: PackedStringArray, arrays: Array, index: int) -> float:
	var bone_indices: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var per_vertex: int = bone_indices.size() / maxi(vertices.size(), 1)
	var rigid := 0.0
	for slot: int in range(per_vertex):
		var bone: int = bone_indices[index * per_vertex + slot]
		if bone >= 0 and bone < bones.size() and not bones[bone].begins_with(CapeDrape.CAPE_BONE_PREFIX):
			rigid += weights[index * per_vertex + slot]
	return rigid


func _run() -> void:
	var capes: Array = _pieces(CAPE)
	_expect(capes.size() == 1, "the cape is one mesh")
	if capes.is_empty():
		quit(1)
		return
	var mesh: Mesh = capes[0]["mesh"]
	var bones: PackedStringArray = capes[0]["bones"]
	for torso: String in TORSOS:
		var name: String = "%s/%s" % [torso.get_base_dir().get_file(), torso.get_file().get_basename()]
		var grid: PackedFloat32Array = CapeDrape.envelope(_pieces(torso))
		_expect(not grid.is_empty(), "%s has an envelope" % name)
		var draped: Mesh = CapeDrape.drape(mesh, bones, grid)
		var worst := 1.0
		var furthest := 0.0
		var inside := 0
		var seams := {}
		var torn := 0
		for surface: int in range(mesh.get_surface_count()):
			var arrays: Array = mesh.surface_get_arrays(surface)
			var rest: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var worn: PackedVector3Array = draped.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			for corner: int in range(0, indices.size() - 2, 3):
				for side: int in range(3):
					var a: int = indices[corner + side]
					var b: int = indices[corner + (side + 1) % 3]
					var before: float = rest[a].distance_to(rest[b])
					if before < MIN_EDGE:
						continue
					worst = maxf(worst, worn[a].distance_to(worn[b]) / before)
			for index: int in range(rest.size()):
				var point: Vector3 = worn[index]
				furthest = maxf(furthest, rest[index].distance_to(point))
				# A trim and the cloth beside it share their border vertices
				# by position; both copies have to land in the same place.
				var key: Vector3 = rest[index].snapped(Vector3.ONE * 0.00001)
				if seams.has(key) and (seams[key] as Vector3).distance_to(point) > 0.0001:
					torn += 1
				seams[key] = point
				# Where the push is full - across the back, below the
				# shoulder line, held by the spine alone - nothing of the
				# torso may stand outside the cloth.
				var bearing: float = rad_to_deg(atan2(point.x, -point.z))
				if (absf(bearing) > CapeDrape.DRAPE_ARC or point.y < CapeDrape.BAND_FLOOR
						or point.y > CapeDrape.DRAPE_SHOULDER
						or _rigid(bones, arrays, index) < 0.999):
					continue
				var radius: float = Vector2(point.x, point.z).length()
				if radius + HELD_BACK < CapeDrape.reach(grid, bearing, point.y):
					inside += 1
		print("  %s: worst stretch %.2f, furthest push %.3f m" % [name, worst, furthest])
		_expect(worst <= MAX_STRETCH, "%s stretches no edge past %.1fx (%.2f)" % [name, MAX_STRETCH, worst])
		_expect(inside == 0, "%s leaves no armour outside the cloth across the back (%d inside)" % [name, inside])
		_expect(torn == 0, "%s keeps every seam closed (%d open)" % [name, torn])
	print("cape drape: %s" % ("PASS" if _failures == 0 else "%d FAILED" % _failures))
	quit(0 if _failures == 0 else 1)
