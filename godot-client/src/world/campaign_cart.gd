extends Node3D
## The run's cart and rescue equipment, driven only by accepted server poses.
## Native NPCs, movement, load work and rescue proof remain server/controller owned.
const CART_ASSET := "res://assets/world/campaign/road_handcart.glb"
const CRATE_ASSET := "res://assets/world/underground/supply_crate.glb"
const ROPE_ASSET := "res://assets/world/underground/rope_coils.glb"
const POST_ASSET := "res://assets/world/underground/mooring_posts.glb"
const LabelStyle := preload("res://src/ui/world_label_style.gd")
const CART_CENTER_X := -0.824876
const RAW_AXLE := Vector3(0, 0.62, 0)
const PLACEMENT_OFFSET := Vector3(0.4, 0, 0)
const ANCHORS := ["cart_anchor", "cart_post", "cart_release", "cart_fulcrum", "cart_unload_1",
	"cart_unload_2", "cart_rope_1", "cart_rope_2", "cart_hold", "worker_far", "muster"]

var cart_body: Node3D
var axle: Node3D
var native: Node3D
var loads: Array[Node3D] = []
var props: Dictionary = {}
var labels: Dictionary = {}
var points: Dictionary = {}
var cart: Dictionary = {}
var _identity := ""
var _geometry := ""
var _world: World3D
var _readouts_visible := true
var _vertices := PackedVector3Array()
var _from := Vector3.ZERO
var _to := Vector3.ZERO
var _from_tilt := 0.0
var _to_tilt := 0.0
var _display_tilt := 0.0
var _elapsed := 0.0
var _duration := 0.0
var _accepted_pose := ""
var _sample: Callable
var _accepted_position := Vector3.ZERO
var _accepted_tilt := 0.0
var _accident_progress := -1.0

func apply_snapshot(snapshot: Dictionary, adapter: CoordinateAdapter, current_map: String,
		surface_sample: Callable) -> void:
	var data: Variant = snapshot.get("cart", {})
	var anchors: Variant = snapshot.get("anchors", {})
	if not is_inside_tree() or not bool(snapshot.get("active", false)) or adapter == null \
			or str(snapshot.get("kind", "")) not in ["", "opening"] \
			or str(snapshot.get("run_id", "")).is_empty() \
			or not (snapshot.get("travel", {}) as Dictionary).is_empty() \
			or EloriaProtocol.map_id_from_reference(current_map) != "greenlight" \
			or EloriaProtocol.map_id_from_reference(str(snapshot.get("map", ""))) != "greenlight" \
			or not valid_cart(data) or not (anchors is Dictionary) or not surface_sample.is_valid():
		clear()
		return
	var tiles: Dictionary = {}
	for key: String in ANCHORS:
		if not _tile_valid(anchors.get(key)):
			clear()
			return
		tiles[key] = anchors[key]
	var geometry := JSON.stringify(tiles)
	var identity := str(snapshot.run_id)
	var pose_point := _ground_tile(adapter, data.tile, surface_sample)
	if not pose_point.is_finite():
		clear()
		return
	if _identity != identity or _geometry != geometry or _world != get_world_3d() \
			or not is_instance_valid(native):
		var grounded: Dictionary = {}
		for key: String in ANCHORS:
			var at := _ground_tile(adapter, tiles[key], surface_sample)
			if not at.is_finite():
				clear()
				return # Retry when the actual pier deck, not a registry fallback, is resident.
			grounded[key] = at
		clear()
		_identity = identity
		_geometry = geometry
		_world = get_world_3d()
		points = grounded
		_build()
		if not is_instance_valid(native) or _vertices.is_empty() or loads.size() != 2 \
				or not props.has("unload_1") or not props.has("unload_2") or not props.has("post"):
			clear()
			return
	_sample = surface_sample
	cart = (data as Dictionary).duplicate(true)
	_accept_pose(pose_point, float(cart.tilt_deg))
	_apply_loads()
	(labels.cart as Label3D).text = status_text(cart)
	(labels.hold as Label3D).text = "Brake held steady" if bool(cart.holder_active) else "Cart needs a steady hold"
	(labels.fulcrum as Label3D).text = "Lever and cribbing · ready" if bool(cart.fulcrum_ready) else "Lever and cribbing work post"
	for index: int in range(2):
		(labels["rope_%d" % (index + 1)] as Label3D).text = "Hauling line · secured" if index < int(cart.rope_ends) else "Hauling line · attachment %d" % (index + 1)
	_update_readouts()
	show()

static func valid_cart(value: Variant) -> bool:
	if not (value is Dictionary) or value.is_empty() or not EloriaProtocol.campaign_cart_valid(value):
		return false
	# Beyond the wire's numeric bounds, this native placement was audited only
	# through 18 degrees; a steeper grounded pose would lift both wheels.
	return float(value.tilt_deg) <= 18

static func _tile_valid(value: Variant) -> bool:
	if not (value is Array) or value.size() != 2:
		return false
	for number: Variant in value:
		if typeof(number) not in [TYPE_FLOAT, TYPE_INT] or not is_finite(float(number)) or float(number) != floor(float(number)):
			return false
	return true

static func status_text(value: Dictionary) -> String:
	match str(value.get("state", "")):
		"safe": return "Worker safely ashore"
		"escorting": return "Worker moving to the shore refuge"
		"treated": return "Worker treated · walk together to shore"
		"released": return "Cart secured · worker free · first aid next"
		"prepared": return "Rescue prepared · lift and secure the shaft"
	return "Worker trapped · %d cargo crates aboard" % int(value.get("load_units", 2))

func _build() -> void:
	cart_body = Node3D.new()
	cart_body.name = "CampaignLastCart"
	add_child(cart_body)
	axle = Node3D.new()
	axle.name = "NativeAxlePivot"
	cart_body.add_child(axle)
	var source_offset := Node3D.new()
	source_offset.position = -RAW_AXLE
	axle.add_child(source_offset)
	native = GlbSceneCache.instantiate(CART_ASSET)
	if native == null:
		return
	source_offset.add_child(native)
	_layers(native)
	_collect_vertices(native, Transform3D.IDENTITY)
	# The original textile is a separate native cover, also removable in Road.
	# The timber, wheels, shafts, materials and all source transforms stay intact.
	for cover: Node in native.find_children("*sun_textile", "MeshInstance3D", true, false):
		(cover as MeshInstance3D).hide()
	for index: int in range(2):
		var load := _asset(CRATE_ASSET)
		if load == null:
			continue
		source_offset.add_child(load)
		load.position = Vector3(-0.5, 0.86, -0.31 if index == 0 else 0.31)
		load.scale = Vector3.ONE * 0.52
		loads.append(load)
		var unloaded := _prop("unload_%d" % (index + 1), CRATE_ASSET, points["cart_unload_%d" % (index + 1)])
		if unloaded != null:
			unloaded.scale = Vector3.ONE * 0.52
			unloaded.hide()
	_prop("post", POST_ASSET, points.cart_post)
	for key: String in ["lever", "crib"]:
		var timber := _shaft_component(key == "lever")
		if timber != null:
			add_child(timber)
			props[key] = timber
	for index: int in range(2):
		var key := "rope_%d" % (index + 1)
		var coil := _prop(key, ROPE_ASSET, points["cart_rope_%d" % (index + 1)])
		if coil != null:
			coil.scale = Vector3.ONE * 0.65
		_label(key, points["cart_rope_%d" % (index + 1)] + Vector3.UP * 0.85)
	_label("cart", points.cart_anchor + Vector3.UP * 2.2)
	_label("hold", points.cart_hold + Vector3.UP * 1.25)
	_label("fulcrum", points.cart_fulcrum + Vector3.UP * 0.65)

func _asset(path: String) -> Node3D:
	var source := GlbSceneCache.instantiate(path)
	if source == null:
		return null
	var wrapper := Node3D.new()
	wrapper.add_child(source)
	_layers(source)
	return wrapper

func _prop(key: String, path: String, point: Vector3) -> Node3D:
	var instance := _asset(path)
	if instance != null:
		add_child(instance)
		instance.global_position = point
		props[key] = instance
	return instance

func _layers(node: Node) -> void:
	if node is MeshInstance3D:
		(node as MeshInstance3D).layers = 2
	for child: Node in node.get_children():
		_layers(child)

func _shaft_component(positive_z: bool) -> Node3D:
	# Reuse one actual disconnected shaft from the approved imported cart. This
	# selects original triangles; it does not generate a new beam, wedge or face.
	for source: MeshInstance3D in native.find_children("*sun_timber_dark", "MeshInstance3D", true, false):
		var arrays := source.mesh.surface_get_arrays(0)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		if indices.is_empty():
			for index: int in vertices.size():indices.append(index)
		var linked: Dictionary = {}
		var seed := -1
		var farthest := -INF
		for triangle: int in indices.size()/3:
			for corner: int in range(3):
				var vertex := vertices[indices[triangle*3+corner]]
				var weld := Vector3i(roundi(vertex.x*100000),roundi(vertex.y*100000),roundi(vertex.z*100000))
				if not linked.has(weld):linked[weld]=[]
				(linked[weld] as Array).append(triangle)
				if (vertex.z > 0 if positive_z else vertex.z < 0) and vertex.x > farthest:
					farthest=vertex.x;seed=triangle
		if seed < 0 or farthest < 2.89:
			continue
		var seen: Dictionary = {}
		var queue := [seed]
		while not queue.is_empty():
			var triangle: int = queue.pop_back()
			if seen.has(triangle):continue
			seen[triangle]=true
			for corner: int in range(3):
				var vertex := vertices[indices[triangle*3+corner]]
				var weld := Vector3i(roundi(vertex.x*100000),roundi(vertex.y*100000),roundi(vertex.z*100000))
				for neighbour: int in linked[weld]:
					if not seen.has(neighbour):queue.append(neighbour)
		var triangles: Array = seen.keys()
		triangles.sort()
		if triangles.size() != 12:
			continue # A changed native model requires another connected-part audit.
		var used := PackedInt32Array()
		var remap: Dictionary = {}
		var selected := PackedInt32Array()
		for triangle: int in triangles:
			for corner: int in range(3):
				var original := int(indices[triangle*3+corner])
				if not remap.has(original):
					remap[original]=used.size();used.append(original)
				selected.append(remap[original])
		var component: Array = arrays.duplicate(true)
		for channel: int in Mesh.ARRAY_MAX:
			if channel == Mesh.ARRAY_INDEX or arrays[channel] == null:
				continue
			var original: Variant = arrays[channel]
			if original.size() == 0:continue
			if original.size()%vertices.size() != 0:return null
			var stride: int = original.size()/vertices.size()
			var copy: Variant = original.duplicate()
			copy.resize(0)
			for index: int in used:
				for part: int in stride:copy.append(original[index*stride+part])
			component[channel]=copy
		component[Mesh.ARRAY_INDEX]=selected
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,component)
		mesh.surface_set_material(0,source.mesh.surface_get_material(0))
		var selected_part := MeshInstance3D.new()
		selected_part.mesh=mesh
		selected_part.layers=2
		selected_part.transform=source.transform
		selected_part.set_meta("source_vertex_ids",used)
		selected_part.set_meta("source_mesh",source.mesh)
		selected_part.set_meta("source_triangles",triangles)
		# Keep the exact submitted native attribute data for preservation checks.
		# Godot's normal upload/readback has a small octahedral quantization error.
		selected_part.set_meta("source_arrays",component)
		var origin := Node3D.new()
		origin.add_child(selected_part)
		var bounds: AABB = selected_part.transform*mesh.get_aabb()
		origin.position=-Vector3(bounds.get_center().x,bounds.position.y,bounds.get_center().z)
		var wrapper := Node3D.new()
		wrapper.name="NativeStockLever" if positive_z else "NativeCrosswiseCrib"
		wrapper.add_child(origin)
		return wrapper
	return null

func _collect_vertices(node: Node, parent: Transform3D) -> void:
	var here := parent * ((node as Node3D).transform if node is Node3D else Transform3D.IDENTITY)
	if node is MeshInstance3D:
		var mesh: Mesh = (node as MeshInstance3D).mesh
		if mesh != null:
			for surface: int in mesh.get_surface_count():
				var arrays := mesh.surface_get_arrays(surface)
				if arrays.size() > Mesh.ARRAY_VERTEX and arrays[Mesh.ARRAY_VERTEX] is PackedVector3Array:
					for vertex: Vector3 in arrays[Mesh.ARRAY_VERTEX]:
						_vertices.append(here * vertex)
	for child: Node in node.get_children():
		_collect_vertices(child, here)

func _accept_pose(point: Vector3, tilt: float) -> void:
	var pose_key := JSON.stringify([point.x, point.y, point.z, tilt])
	if pose_key == _accepted_pose:
		return
	var initial := _accepted_pose.is_empty()
	_from = point if initial else _accepted_position
	_to = point
	_from_tilt = tilt if initial else _accepted_tilt
	_to_tilt = tilt
	_elapsed = 0
	_duration = 0 if initial else 0.7
	_accepted_pose = pose_key
	_process(0)

func _process(delta: float) -> void:
	if not is_instance_valid(cart_body) or _accepted_pose.is_empty():
		return
	_elapsed = minf(_elapsed + delta, _duration)
	var weight := 1.0 if _duration <= 0 else smoothstep(0, 1, _elapsed / _duration)
	var point := _from.lerp(_to, weight)
	_accepted_position=point
	_accepted_tilt=lerpf(_from_tilt,_to_tilt,weight)
	_display_tilt=_accepted_tilt
	if _accident_progress >= 0:
		point=(points.cart_anchor as Vector3)+Vector3(-0.35*(1-_accident_progress),0,0)
		_display_tilt=17.0*_accident_progress
	var height: Variant = _sample.call(point) if _sample.is_valid() else NAN
	if typeof(height) not in [TYPE_FLOAT, TYPE_INT] or not is_finite(float(height)):
		cart_body.hide()
		return
	point.y = float(height)
	cart_body.global_position = point + PLACEMENT_OFFSET
	var basis := Basis(Vector3(0,0,1), deg_to_rad(-_display_tilt))
	var minimum := INF
	for vertex: Vector3 in _vertices:
		minimum = minf(minimum, (RAW_AXLE + basis * (vertex - RAW_AXLE)).y)
	# Preserve wheel contact using actual imported vertices, not an invented floor
	# or an AABB corner whose volume contains empty space below a tilted shaft.
	axle.position = Vector3(CART_CENTER_X, RAW_AXLE.y - minimum, 0)
	axle.basis = basis
	cart_body.show()
	if labels.has("cart"):
		(labels.cart as Label3D).global_position = point + Vector3.UP * 2.2
	_place_timbers()

func _place_timbers() -> void:
	if not props.has("lever") or not props.has("crib"):
		return
	var ready := bool(cart.get("fulcrum_ready",false)) and _accident_progress < 0
	for key: String in ["lever","crib"]:
		var timber := props[key] as Node3D
		timber.visible=_accident_progress < 0
		if ready:
			# The loose tools stay at their real work site when the freed cart
			# backs away; they are not attached scenery dragged by its chassis.
			timber.global_position=(points.cart_anchor as Vector3)+PLACEMENT_OFFSET+Vector3(1.05,0.04,0.5 if key=="lever" else 0)
			timber.rotation=Vector3(0,0 if key=="lever" else PI/2,0)
		else:
			timber.global_position=(points.cart_fulcrum as Vector3)+Vector3(0,0,0.45 if key=="crib" else 0)
			timber.rotation=Vector3.ZERO

func _apply_loads() -> void:
	for index: int in loads.size():
		loads[index].visible=_accident_progress >= 0 or index<int(cart.get("load_units",0))
		(props["unload_%d"%(index+1)] as Node3D).visible=_accident_progress < 0 and index<int(cart.get("unloaded",0))

func set_cinematic_accident(progress: float) -> void:
	if not is_finite(progress) or progress < 0:
		clear_cinematic_presentation()
		return
	_accident_progress=clampf(progress,0,1)
	_apply_loads()
	_process(0)

func clear_cinematic_presentation() -> void:
	if _accident_progress < 0:return
	_accident_progress=-1
	_elapsed=_duration # Cleanup restores the latest accepted pose, not an old staged transform.
	_apply_loads()
	_process(0)

static func _ground_tile(adapter: CoordinateAdapter, tile: Array, sample: Callable) -> Vector3:
	var point := adapter.tile_center(int(tile[0]), int(tile[1]))
	var height: Variant = sample.call(point)
	point.y = float(height) if typeof(height) in [TYPE_FLOAT, TYPE_INT] and is_finite(float(height)) else NAN
	return point

func _label(key: String, point: Vector3) -> void:
	var label := Label3D.new()
	label.name = "CampaignCart" + key.capitalize()
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.fixed_size = true
	label.visibility_range_end = 45
	label.modulate = Color("f1d59c")
	LabelStyle.apply(label, 14, 0.0012953, 5)
	add_child(label)
	label.global_position = point
	labels[key] = label

func _update_readouts() -> void:
	for key: String in labels:
		(labels[key] as Label3D).visible = _readouts_visible and (key not in ["fulcrum", "rope_1", "rope_2"] \
			or (key == "fulcrum" and str(cart.get("route", "")) == "lever") \
			or (key.begins_with("rope_") and str(cart.get("route", "")) == "haul"))
		if key == "hold":
			(labels[key] as Label3D).visible = _readouts_visible and str(cart.get("state", "")) in ["trapped", "prepared"]

func set_readouts_visible(value: bool) -> void:
	_readouts_visible = value
	_update_readouts()

func clear() -> void:
	for child: Node in get_children():
		if child is Node3D:
			(child as Node3D).hide()
		remove_child(child)
		child.queue_free()
	cart_body = null
	axle = null
	native = null
	loads.clear()
	props.clear()
	labels.clear()
	points.clear()
	cart.clear()
	_vertices.clear()
	_identity = ""
	_geometry = ""
	_world = null
	_accepted_pose = ""
	_sample = Callable()
	_accident_progress=-1
	_accepted_position=Vector3.ZERO
	_accepted_tilt=0
	hide()
