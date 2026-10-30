extends RefCounted
## Fit only the front strap over the clothing actually worn by this body.
## The authored case and Cape_Clearance shape remain untouched. Results are
## shared per body/outfit and derived from the original mesh on every change.

const CACHE_LIMIT := 48
const SOURCE_META := &"quiver_authored_mesh"
const LOD_READER := preload("res://src/actors/wardrobe_shirt_fit.gd")
static var _meshes: Dictionary = {}
static var _envelopes: Dictionary = {}


static func apply(instance: MeshInstance3D, layers: Array,
		skeleton: Skeleton3D, outfit_key: String) -> void:
	if instance.mesh == null or skeleton == null:
		return
	if not instance.has_meta(SOURCE_META):
		instance.set_meta(SOURCE_META, instance.mesh)
	var source: Mesh = instance.get_meta(SOURCE_META) as Mesh
	if layers.is_empty():
		instance.mesh = source
		return
	var key := "%s|%s" % [source.get_instance_id(), outfit_key]
	if not _meshes.has(key):
		if not _envelopes.has(outfit_key):
			if _envelopes.size() >= CACHE_LIMIT:
				_envelopes.clear()
			_envelopes[outfit_key] = envelope(layers, skeleton)
		if _meshes.size() >= CACHE_LIMIT:
			_meshes.clear()
		_meshes[key] = fit(source, _envelopes[outfit_key])
	instance.mesh = _meshes[key] as Mesh


## Measure the final rebound skin in skeleton rest space. Canonical armor is
## stretched by its binds on shorter/wider bodies; reading its raw vertices
## would measure a different wearer and miss both the waist and shoulders.
static func envelope(layers: Array, skeleton: Skeleton3D) -> Dictionary:
	var pelvis := skeleton.get_bone_global_rest(skeleton.find_bone("pelvis")).origin.y
	var shoulder := skeleton.get_bone_global_rest(skeleton.find_bone("upperarm_r")).origin.y
	var stature := skeleton.get_bone_global_rest(skeleton.find_bone("Head")).origin.y / 1.568490028858185
	var step := 0.012 * stature
	var low := pelvis - 0.08 * stature
	var high := shoulder + 0.055 * stature
	var half := 0.4 * stature
	var width := int(ceil(2.0 * half / step)) + 1
	var height := int(ceil((high - low) / step)) + 1
	var grid := PackedFloat32Array()
	var top_grid: Dictionary = {}
	grid.resize(width * height)
	grid.fill(-INF)
	for value: Variant in layers:
		var node := value as MeshInstance3D
		if node == null or node.mesh == null or node.skin == null or not node.visible:
			continue
		var skin := node.skin
		var matrices: Array[Transform3D] = []
		for bind: int in range(skin.get_bind_count()):
			var bone := skeleton.find_bone(skin.get_bind_name(bind))
			if bone < 0:
				bone = skin.get_bind_bone(bind)
			matrices.append(skeleton.get_bone_global_rest(bone) * skin.get_bind_pose(bind))
		for surface: int in range(node.mesh.get_surface_count()):
			var arrays := node.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			var stride := bones.size() / maxi(vertices.size(), 1)
			if stride == 0:
				continue
			var rest := PackedVector3Array()
			rest.resize(vertices.size())
			for vertex: int in range(vertices.size()):
				var point := Vector3.ZERO
				for slot: int in range(stride):
					var at := vertex * stride + slot
					if weights[at] > 0.0:
						point += (matrices[bones[at]] * vertices[vertex]) * weights[at]
				rest[vertex] = node.transform * point
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			for corner: int in range(0, indices.size(), 3):
				var a := rest[indices[corner]]
				var b := rest[indices[corner + 1]]
				var c := rest[indices[corner + 2]]
				if maxf(a.y, maxf(b.y, c.y)) >= shoulder - 0.08 * stature:
					_top_triangle(top_grid, a, b, c, step, shoulder - 0.08 * stature)
				if maxf(a.z, maxf(b.z, c.z)) <= 0.0:
					continue
				var determinant := (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y)
				if absf(determinant) < 0.00000001:
					continue
				var left := maxi(0, int(floor((minf(a.x, minf(b.x, c.x)) + half) / step)))
				var right := mini(width - 1, int(ceil((maxf(a.x, maxf(b.x, c.x)) + half) / step)))
				var bottom := maxi(0, int(floor((minf(a.y, minf(b.y, c.y)) - low) / step)))
				var top := mini(height - 1, int(ceil((maxf(a.y, maxf(b.y, c.y)) - low) / step)))
				for row: int in range(bottom, top + 1):
					var y := low + row * step
					for column: int in range(left, right + 1):
						var x := -half + column * step
						var u := ((b.y - c.y) * (x - c.x) + (c.x - b.x) * (y - c.y)) / determinant
						var v := ((c.y - a.y) * (x - c.x) + (a.x - c.x) * (y - c.y)) / determinant
						if u >= 0.0 and v >= 0.0 and u + v <= 1.0:
							var at := row * width + column
							grid[at] = maxf(grid[at], u * a.z + v * b.z + (1.0 - u - v) * c.z)
	return {"grid": grid, "step": step, "low": low, "half": half,
		"width": width, "height": height, "stature": stature,
		"top_grid": top_grid, "shoulder": shoulder}


## The front depth field cannot see the roof of a shoulder. Sample that roof
## in X/Z too, including the short band that turns over it toward the back.
static func _top_triangle(grid: Dictionary, a: Vector3, b: Vector3,
		c: Vector3, step: float, floor_y: float) -> void:
	var determinant := (b.z - c.z) * (a.x - c.x) + (c.x - b.x) * (a.z - c.z)
	if absf(determinant) < 0.00000001:
		return
	for iz: int in range(int(floor(minf(a.z, minf(b.z, c.z)) / step)),
			int(ceil(maxf(a.z, maxf(b.z, c.z)) / step)) + 1):
		if absf(iz * step) > 0.20:
			continue
		for ix: int in range(int(floor(minf(a.x, minf(b.x, c.x)) / step)),
				int(ceil(maxf(a.x, maxf(b.x, c.x)) / step)) + 1):
			if absf(ix * step) > 0.40:
				continue
			var u := ((b.z - c.z) * (ix * step - c.x) + (c.x - b.x) * (iz * step - c.z)) / determinant
			var v := ((c.z - a.z) * (ix * step - c.x) + (a.x - c.x) * (iz * step - c.z)) / determinant
			if u >= 0.0 and v >= 0.0 and u + v <= 1.0:
				var y := u * a.y + v * b.y + (1.0 - u - v) * c.y
				if y >= floor_y:
					var at := Vector2i(ix, iz)
					grid[at] = maxf(float(grid.get(at, -INF)), y)


static func _top_offset(field: Dictionary, point: Vector3) -> float:
	if not field.has("top_grid"):
		return 0.0
	var stature := float(field.stature)
	var shoulder := float(field.shoulder)
	if point.z < -0.10 * stature or point.y < shoulder - 0.065 * stature or point.y > shoulder + 0.12 * stature:
		return 0.0
	var step := float(field.step)
	var at := Vector2i(int(floor(point.x / step)), int(floor(point.z / step)))
	var roof := -INF
	for dz: int in [0, 1]:
		for dx: int in [0, 1]:
			roof = maxf(roof, float(field.top_grid.get(at + Vector2i(dx, dz), -INF)))
	return clampf(roof + 0.008 * stature - point.y, 0.0, 0.030 * stature) if is_finite(roof) else 0.0


static func reach(field: Dictionary, x: float, y: float) -> float:
	var column := int(floor((x + float(field.half)) / float(field.step)))
	var row := int(floor((y - float(field.low)) / float(field.step)))
	var width := int(field.width)
	var height := int(field.height)
	var result := -INF
	var grid: PackedFloat32Array = field.grid
	for dy: int in [0, 1]:
		for dx: int in [0, 1]:
			if column + dx >= 0 and column + dx < width and row + dy >= 0 and row + dy < height:
				result = maxf(result, grid[(row + dy) * width + column + dx])
	return result


static func fit(source: Mesh, field: Dictionary) -> Mesh:
	var step := float(field.step)
	var low := float(field.low)
	var stature := float(field.stature)
	var pushes := PackedFloat32Array()
	pushes.resize(int(field.height))
	pushes.fill(0.0)
	# Move a whole cross-section together. Projecting each vertex onto the
	# armor surface separately would flatten the buckle and turn seams inside out.
	for surface: int in range(source.get_surface_count()):
		var vertices: PackedVector3Array = source.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
		for point: Vector3 in vertices:
			if point.z <= 0.025 * stature:
				continue
			var row := int(round((point.y - low) / step))
			if row < 0 or row >= pushes.size():
				continue
			var depth := reach(field, point.x, point.y)
			if is_finite(depth):
				pushes[row] = maxf(pushes[row], depth + 0.007 * stature - point.z)
	# Spread the required clearance gently along the band. Buckles keep their
	# relief and the strap bends smoothly around a breastplate or a thick collar.
	for row: int in range(1, pushes.size()):
		pushes[row] = maxf(pushes[row], pushes[row - 1] - step * 0.7)
	for row: int in range(pushes.size() - 2, -1, -1):
		pushes[row] = maxf(pushes[row], pushes[row + 1] - step * 0.7)
	var moved := false
	var result := ArrayMesh.new()
	result.resource_name = source.resource_name + " Chest Strap Fit"
	for shape: int in range(source.get_blend_shape_count()):
		result.add_blend_shape(source.get_blend_shape_name(shape))
	if source is ArrayMesh:
		result.blend_shape_mode = (source as ArrayMesh).blend_shape_mode
	for surface: int in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var offsets := PackedVector3Array()
		offsets.resize(vertices.size())
		offsets.fill(Vector3.ZERO)
		for vertex: int in range(vertices.size()):
			var point := vertices[vertex]
			var lift := _top_offset(field, point)
			vertices[vertex].y += lift
			offsets[vertex].y = lift
			moved = moved or lift > 0.00001
			if point.z <= 0.025 * stature:
				continue
			var at := clampf((point.y - low) / step, 0.0, float(pushes.size() - 1))
			var from := int(floor(at))
			var push := lerpf(pushes[from], pushes[mini(from + 1, pushes.size() - 1)], at - from)
			push *= smoothstep(0.025 * stature, 0.06 * stature, point.z)
			if push > 0.00001:
				vertices[vertex].z += push
				offsets[vertex].z = push
				moved = true
		arrays[Mesh.ARRAY_VERTEX] = vertices
		var shapes := source.surface_get_blend_shape_arrays(surface)
		if result.blend_shape_mode == Mesh.BLEND_SHAPE_MODE_NORMALIZED:
			# Normalized shapes carry complete positions. Apply the same cloth
			# offset to them or selecting the cape shape would undo the armor fit.
			for shape_arrays: Array in shapes:
				var points: PackedVector3Array = shape_arrays[Mesh.ARRAY_VERTEX]
				for vertex: int in range(points.size()):
					points[vertex] += offsets[vertex]
				shape_arrays[Mesh.ARRAY_VERTEX] = points
		result.add_surface_from_arrays(source.surface_get_primitive_type(surface), arrays,
			shapes, LOD_READER._surface_lods(source, surface),
			source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		result.surface_set_material(surface, source.surface_get_material(surface))
		result.surface_set_name(surface, source.surface_get_name(surface))
	return result if moved else source
