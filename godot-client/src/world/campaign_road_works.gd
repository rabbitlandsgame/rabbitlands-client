extends Node3D
## Approved native props and interpolation between accepted, persisted cart poses.
## No route prediction, collision authority, objective completion or reward logic.
const CART := "res://assets/world/campaign/road_handcart.glb"
const CART_CENTRE := Vector3(-0.824876, 0.043751, 0)
const SACK := "res://assets/world/underground/feed_sacks.glb"
const CRATE := "res://assets/world/underground/supply_crate.glb"
const STATIC_PROPS := {"feed": SACK, "rope": "res://assets/world/underground/rope_coils.glb",
	"pantry": "res://assets/world/underground/barrel_stack.glb", "casks": "res://assets/world/underground/barrel_stack.glb",
	"fitting": CRATE, "holding": SACK}
var carts: Dictionary = {}
var poses: Dictionary = {}
var props: Dictionary = {}
var labels: Dictionary = {}
var points: Dictionary = {}
var checkpoint: MeshInstance3D
var _identity := ""
var _adapter: CoordinateAdapter
var _sample: Callable
var _readouts := true
var _reduced := false

func apply_snapshot(snapshot: Dictionary, adapter: CoordinateAdapter, current_map: String,
		surface_sample: Callable, reduced_motion := false) -> void:
	var map := EloriaProtocol.map_id_from_reference(current_map)
	if not bool(snapshot.get("active", false)) or str(snapshot.get("kind", "")) != "road" \
			or adapter == null or map not in ["hearthcroft", "brambleshaw"] \
			or EloriaProtocol.map_id_from_reference(str(snapshot.get("map", ""))) != map \
			or not (snapshot.get("travel", {}) as Dictionary).is_empty():
		clear()
		return
	_adapter = adapter
	_sample = surface_sample
	_reduced = reduced_motion
	var identity := str(snapshot.get("run_id", "")) + ":" + map
	if _identity != identity:
		clear()
		_identity = identity
	var anchors: Dictionary = snapshot.get("anchors", {})
	for key: String in STATIC_PROPS:
		if not anchors.has(key) or props.has(key):
			continue
		var point := _tile(anchors[key])
		var plane := _plane(point) if point.is_finite() else Vector3(NAN, NAN, NAN)
		if not point.is_finite() or not plane.is_finite():
			continue # Cold terrain is retried, never registry-height scenery.
		var prop := _asset(STATIC_PROPS[key])
		if prop == null:
			continue
		add_child(prop)
		prop.global_position = point
		prop.rotation = plane
		props[key] = prop
		points[key] = point
		_label(key, prop, Vector3(0, 1.65, 0))
	var road: Dictionary = snapshot.get("road", {})
	var seen: Array = []
	for cart: Dictionary in road.get("carts", []):
		var id := str(cart.id)
		seen.append(id)
		_accept_cart(cart)
		if carts.has(id):
			# This approved native cart has a separately authored cloth cover.
			# Open loading shows counted bundles; protection uses the cover.
			var covered := str(road.get("preparation", "")) == "protect" if id != "consignment" \
				else not bool((road.get("consignment", {}) as Dictionary).get("inspected", false))
			for cover: Node in carts[id].find_children("*sun_textile", "MeshInstance3D", true, false):
				(cover as MeshInstance3D).visible = covered
	for id: String in carts.keys():
		if id not in seen:
			carts[id].queue_free()
			carts.erase(id)
			poses.erase(id)
			labels.erase("cart_" + id)
	if not is_instance_valid(checkpoint):
		checkpoint = MeshInstance3D.new()
		var ring := TorusMesh.new()
		ring.inner_radius = 0.34
		ring.outer_radius = 0.43
		checkpoint.mesh = ring
		var material := StandardMaterial3D.new()
		material.albedo_color = Color("e6c365")
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		checkpoint.material_override = material
		add_child(checkpoint)
		_label("checkpoint", checkpoint, Vector3(0, 0.8, 0))
	checkpoint.hide()
	(labels.checkpoint as Label3D).hide()
	for target: Dictionary in snapshot.get("targets", []):
		if int(target.get("object_id", -1)) != 0 or not bool(target.get("enabled", false)):
			continue
		var at := _tile(target.tile)
		if at.is_finite():
			checkpoint.global_position = at + Vector3.UP * 0.06
			checkpoint.show()
			(labels.checkpoint as Label3D).text = str(target.label)
			(labels.checkpoint as Label3D).visible = _readouts
		break
	for key: String in props:
		var caption: String = {"feed": "Field food", "rope": "Crew bracing rope", "pantry": "Late arrivals' bowls",
			"casks": "Current consignment · sealed casks", "fitting": "Shipment fitting", "holding": "Witnessed holding place"}[key]
		if key == "feed":
			caption += " · %d portions left" % int((road.get("stock", {}) as Dictionary).get("remaining", 0))
		if key == "pantry":
			caption += " · %d reserved" % int((road.get("stock", {}) as Dictionary).get("reserved_last_bowl", 0))
		(labels[key] as Label3D).text = caption
	show()

func _accept_cart(row: Dictionary) -> void:
	var id := str(row.id)
	var point := _tile(row.tile)
	if not point.is_finite():
		return
	var seq := int(row.get("motion_seq", 0))
	if poses.has(id) and seq < int(poses[id].seq):
		return # An old snapshot cannot rewind a persisted cart.
	if not carts.has(id):
		var cart := _asset(CART)
		if cart == null:
			return
		add_child(cart)
		cart.global_position = point
		carts[id] = cart
		_label("cart_" + id, cart, Vector3(0, 2.25, 0))
		var load_node := Node3D.new()
		load_node.name = "AcceptedCargo"
		cart.add_child(load_node)
		for index: int in range(1 if id == "consignment" else 3):
			var bundle := _asset(CRATE if id == "consignment" else SACK)
			if bundle != null:
				load_node.add_child(bundle)
				bundle.position = Vector3(-0.825 + (index - 1) * 0.65 if id != "consignment" else -0.825, 0.85, 0)
				bundle.scale = Vector3.ONE * 0.6
	var node: Node3D = carts[id]
	var previous: Dictionary = poses.get(id, {})
	if previous.is_empty() or seq != int(previous.seq):
		var from: Vector3 = node.global_position
		var tile: Array = row.tile
		var old_tile: Array = previous.get("tile", tile)
		var adjacent := maxi(absi(int(tile[0]) - int(old_tile[0])), absi(int(tile[1]) - int(old_tile[1]))) <= 1
		var interpolate := not previous.is_empty() and adjacent and seq == int(previous.seq) + 1 \
			and str(row.state) == "moving" and not _reduced
		poses[id] = {"seq": seq, "tile": tile.duplicate(), "from": from if interpolate else point,
			"to": point, "elapsed": 0.0, "duration": float(row.get("step_ms", 250)) / 1000.0 if interpolate else 0.0}
		if not interpolate:
			node.global_position = point
	var facing: Array = row.get("facing", [1, 0])
	var vector := _adapter.server_to_godot(float(facing[0]), float(facing[1])) \
		- _adapter.server_to_godot(0, 0)
	if vector.length_squared() > 0.001:
		# These authored lanes keep the five-tile shaft axis east/west even
		# while backing to a checkpoint; no turn sweeps through crew posts.
		node.rotation.y = 0.0 if absf(vector.x) > 0.01 else atan2(-vector.z, vector.x)
	node.rotation.z = deg_to_rad(float(row.get("lean_deg", 0)))
	var label: Label3D = labels["cart_" + id]
	label.text = {"lead": "Lead cart", "rear": "Rear cart", "consignment": "Witnessed consignment"}[id] \
		+ " · %d load units\n%s · %d/%d" % [int(row.get("cargo_units", 0)), str(row.state).capitalize(),
		int(row.get("route_index", 0)) + 1, int(row.get("route_total", 1))]
	# The label is world-upright even when a recovering cart leans.
	label.global_rotation = Vector3.ZERO
	var cargo := node.get_node_or_null("AcceptedCargo") as Node3D
	if cargo != null:
		cargo.visible = int(row.get("cargo_units", 0)) > 0
		var bundles := clampi(ceili(float(row.get("cargo_units", 0)) / 2.0), 0, 3)
		for index: int in cargo.get_child_count():
			(cargo.get_child(index) as Node3D).visible = index < bundles
	poses[id]["lean"] = float(row.get("lean_deg", 0))

func _process(delta: float) -> void:
	for id: String in poses:
		if not carts.has(id):
			continue
		var pose: Dictionary = poses[id]
		pose.elapsed = minf(float(pose.elapsed) + delta, float(pose.duration))
		var weight := 1.0 if float(pose.duration) <= 0 else float(pose.elapsed) / float(pose.duration)
		var point: Vector3 = (pose.from as Vector3).lerp(pose.to, weight)
		# Sample the real terrain under every accepted interpolation step.
		point = _ground(point)
		if point.is_finite():
			(carts[id] as Node3D).global_position = point
			var plane := _plane(point)
			if plane.is_finite():
				(carts[id] as Node3D).rotation.x = plane.x
				(carts[id] as Node3D).rotation.z = plane.z + deg_to_rad(float(pose.get("lean", 0)))

func _asset(path: String) -> Node3D:
	var instance := GlbSceneCache.instantiate(path)
	if instance == null:
		return null
	var wrapper := Node3D.new()
	if path == CART:
		var pivot := Node3D.new()
		pivot.position = CART_CENTRE
		wrapper.add_child(pivot)
		pivot.add_child(instance)
	else:
		wrapper.add_child(instance) # Keep the native root transform intact.
	return wrapper

func _label(key: String, parent: Node3D, offset: Vector3) -> void:
	var label := Label3D.new()
	label.position = offset
	label.font_size = 30
	label.pixel_size = 0.009
	label.outline_size = 7
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = false
	label.visible = _readouts
	parent.add_child(label)
	labels[key] = label

func _tile(tile: Array) -> Vector3:
	return _ground(_adapter.tile_center(int(tile[0]), int(tile[1])))

func _ground(point: Vector3) -> Vector3:
	var height: Variant = _sample.call(point) if _sample.is_valid() else NAN
	point.y = float(height) if typeof(height) in [TYPE_INT, TYPE_FLOAT] else NAN
	return point

func _plane(point: Vector3) -> Vector3:
	var left := _ground(point + Vector3.LEFT * 0.5)
	var right := _ground(point + Vector3.RIGHT * 0.5)
	var front := _ground(point + Vector3.FORWARD * 0.5)
	var back := _ground(point + Vector3.BACK * 0.5)
	if not left.is_finite() or not right.is_finite() or not front.is_finite() or not back.is_finite():
		return Vector3(NAN, NAN, NAN)
	return Vector3(-atan(back.y - front.y), 0, atan(right.y - left.y))

func set_readouts_visible(value: bool) -> void:
	_readouts = value
	for label: Label3D in labels.values():
		label.visible = value

func clear() -> void:
	for child: Node in get_children():
		remove_child(child)
		child.queue_free()
	carts.clear()
	poses.clear()
	props.clear()
	labels.clear()
	points.clear()
	checkpoint = null
	_identity = ""
	hide()
