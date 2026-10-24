extends RefCounted
## Keep prepared private materials alive until AFTER the owning render instance
## is freed. GeometryInstance3D clears its material members before its base
## VisualInstance3D destructor frees the instance RID. Object metadata survives
## both destructors, so these ordinary Resource refs supply the required order.
## No Node/script/child, raw RID, external queue or frame delay is introduced.
const META := &"rl_prepared_material_ownership"

static func attach(geometry: GeometryInstance3D) -> void:
	if geometry == null or geometry.has_meta(META):
		return
	geometry.set_meta(META, [])
	var weak: WeakRef = weakref(geometry)
	_capture(weak)
	# Callable contains only a WeakRef to the Node. The metadata Array itself
	# owns the Resources; a signal connection is not RefCounted ownership.
	geometry.tree_exiting.connect(_capture.bind(weak))

static func _hold(materials: Array, material: Material) -> void:
	if material != null and not materials.has(material):
		materials.append(material)

static func _capture(weak: WeakRef) -> void:
	var geometry := weak.get_ref() as GeometryInstance3D
	if geometry == null or not geometry.has_meta(META):
		return
	var materials: Array = geometry.get_meta(META)
	# Keep the initial private identities too: replacing an override may leave
	# a renderer dependency update for its previous identity still queued.
	_hold(materials, geometry.material_override)
	_hold(materials, geometry.material_overlay)
	if geometry is MeshInstance3D:
		var instance := geometry as MeshInstance3D
		if instance.mesh != null:
			for surface: int in instance.mesh.get_surface_count():
				_hold(materials, instance.mesh.surface_get_material(surface))
				_hold(materials, instance.get_surface_override_material(surface))
	elif geometry is MultiMeshInstance3D:
		var multi := (geometry as MultiMeshInstance3D).multimesh
		if multi != null and multi.mesh != null:
			for surface: int in multi.mesh.get_surface_count():
				_hold(materials, multi.mesh.surface_get_material(surface))

static func refresh(root: Node) -> void:
	# For a consumer replacing materials on a still-detached native source.
	# Ordinary live look/fade replacements are captured on every tree exit.
	var nodes: Array[Node] = []
	if root != null:
		nodes.append(root)
	while not nodes.is_empty():
		var node: Node = nodes.pop_back()
		for child: Node in node.get_children():
			nodes.append(child)
		if node.has_meta(META):
			_capture(weakref(node))

static func strip_runtime_metadata(root: Node) -> Array:
	# Cookers call immediately around PackedScene.pack with no await. Hold
	# each Array before removing the exact runtime-only key, then restore it.
	var undo: Array = []
	var nodes: Array[Node] = []
	if root != null:
		nodes.append(root)
	while not nodes.is_empty():
		var node: Node = nodes.pop_back()
		for child: Node in node.get_children():
			nodes.append(child)
		if node.has_meta(META):
			undo.append([node, node.get_meta(META)])
			node.remove_meta(META)
	return undo

static func restore_runtime_metadata(undo: Array) -> void:
	for row: Array in undo:
		var node := row[0] as Node
		if is_instance_valid(node):
			node.set_meta(META, row[1])
