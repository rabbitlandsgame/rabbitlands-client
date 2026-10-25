extends "res://src/world/campaign_works.gd"
## Private chapter presentation. Props reuse approved native assets; the small
## ground marks and water strip are readouts. Only snapshots change their state.
const JETTY_ASSET := "res://assets/world/underground/plank_jetty.glb"
const CRATE_ASSET := "res://assets/world/underground/supply_crate.glb"
const JETTY_DECK_HEIGHT := 2.59709
const DECK_CLEARANCE := 0.10
const MARKER_NAMES := ["Delivery marks", "Channel split", "Intake marks"]

var bank: Dictionary = {}
var crossing: Node3D
var reserve: Node3D
var markers: Dictionary = {}
var checkpoint: MeshInstance3D
var _checkpoint_active := false
var _markers_active := false
var deck_surface: StaticBody3D

func apply_snapshot(snapshot: Dictionary, adapter: CoordinateAdapter, current_map: String,
		surface_sample: Callable, reduced_motion := false) -> void:
	var valid := bool(snapshot.get("active", false)) and str(snapshot.get("kind", "")) == "bank" \
		and adapter != null and EloriaProtocol.map_id_from_reference(current_map) == "landfall" \
		and EloriaProtocol.map_id_from_reference(str(snapshot.get("map", ""))) == "landfall" \
		and (snapshot.get("travel", {}) as Dictionary).is_empty()
	if not valid:
		clear()
		return
	var anchors: Dictionary = snapshot.get("anchors", {})
	for required: String in ["model", "gauge", "flow", "marker_1", "marker_2", "marker_3"]:
		if not anchors.has(required):
			clear()
			return
	_adapter = adapter
	_sample = surface_sample
	var identity := str(snapshot.get("run_id", ""))
	var geometry := JSON.stringify(anchors)
	if _identity != identity or _geometry != geometry or not is_instance_valid(gate):
		var grounded: Dictionary = {}
		for key: String in anchors:
			var tile: Array = anchors[key]
			var point := _ground(adapter.tile_center(int(tile[0]), int(tile[1])))
			if not point.is_finite():
				clear()
				return # Retry when this part of the orchard has streamed in.
			grounded[key] = point
		var centre: Vector3 = grounded.model
		var left := _ground(centre + Vector3.LEFT * 2)
		var right := _ground(centre + Vector3.RIGHT * 2)
		var front := _ground(centre + Vector3.FORWARD * 0.5)
		var back := _ground(centre + Vector3.BACK * 0.5)
		if not left.is_finite() or not right.is_finite() or not front.is_finite() or not back.is_finite():
			clear()
			return
		clear()
		_identity = identity
		_geometry = geometry
		points = grounded
		_gate_rotation = Vector3(-atan(back.y - front.y), 0, atan((right.y - left.y) / 4))
		_build_bank()
		if not is_instance_valid(gate):
			clear()
			return
	bank = (snapshot.get("bank", {}) as Dictionary).duplicate(true)
	var status := int(bank.get("diversion", 0))
	var reading := int(bank.get("reading", 0))
	mechanism = {"gauge": reading}
	(labels.gauge as Label3D).text = "Measured: %d %s\nPermit: %d units" % [reading,
		"unit" if reading == 1 else "units", int(bank.get("claimed_gauge", 2))]
	(labels.model as Label3D).text = ["Intake closed", "Intake alone · unsteady", "Intake and return · steady"][clampi(status, 0, 2)]
	var finished := bool(bank.get("remedy_complete", false)) \
		or str(snapshot.get("key", "")) in ["reconstruction", "account", "complete"]
	_markers_active = finished
	var remedy := str(bank.get("remedy", ""))
	if labels.has("reserve"):
		var caption := "Emergency reserve · unspent"
		if finished:
			caption = {"reserve": "Emergency reserve · spent", "material": "Replacement fitted · 1 Wood Plank used",
				"maintenance": "Two crew checks · maintenance shift assigned"}.get(remedy, caption)
		(labels.reserve as Label3D).text = caption
	if is_instance_valid(reserve):
		reserve.visible = not (finished and remedy == "reserve")
	if is_instance_valid(crossing):
		var approach := str(bank.get("approach", ""))
		crossing.visible = bool(bank.get("crossing_ready", false)) and approach == "planks"
		if is_instance_valid(deck_surface):
			deck_surface.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER if crossing.visible else 0
		var caption := "Crossing work · 2 Wood Planks needed"
		if crossing.visible:
			caption = "Crossing fitted · 2 Wood Planks used"
		elif approach == "secure":
			caption = "Short path · anchors secured" if bool(bank.get("crossing_ready", false)) else "Short path · secure both anchors"
		elif approach == "detour":
			caption = "Long bank path · supplies kept"
		(labels.crossing as Label3D).text = caption
	for index: int in range(1, 4):
		var key := "marker_" + str(index)
		var complete := int(bank.get("sequence_step", 0)) >= index
		var wrong := _misplaced_at(str(bank.get("misplaced", "")), key, snapshot)
		var colour := Color("ef6f55") if wrong else Color("55ca9c") if complete else Color("e6c365")
		(markers[key].material_override as StandardMaterial3D).albedo_color = colour
		(markers[key] as MeshInstance3D).visible = _markers_active
		(labels[key] as Label3D).visible = _markers_active
		(labels[key] as Label3D).text = "Lift misplaced marker" if wrong else MARKER_NAMES[index - 1] + (" · verified" if complete else "")
	if labels.has("tree"):
		(labels.tree as Label3D).text = "Tree channel · cleared" if bool(bank.get("tree_cared", false)) else "Existing orchard tree · inspect channel"
	if labels.has("bypass"):
		(labels.bypass as Label3D).text = "New bypass · checked" if bool(bank.get("bypass_ready", false)) else "New maintenance bypass"
	if flow_material != null:
		flow_material.set_shader_parameter("flow_strength", float(status) * 0.5)
		flow_material.set_shader_parameter("verified", status == 2)
		flow_material.set_shader_parameter("reduced_motion", reduced_motion)
	_checkpoint_active = false
	for target: Dictionary in snapshot.get("targets", []):
		if int(target.get("object_id", -1)) != 0 or not bool(target.get("enabled", false)) or bool(target.get("completed", false)):
			continue
		var tile: Array = target.tile
		var point := _ground(adapter.tile_center(int(tile[0]), int(tile[1])))
		if not point.is_finite():
			break
		_checkpoint_active = true
		checkpoint.global_position = point + Vector3.UP * 0.1
		(labels.checkpoint as Label3D).global_position = point + Vector3.UP * 1.3
		(labels.checkpoint as Label3D).text = str(target.get("label", "Next route observation"))
		break
	checkpoint.visible = _checkpoint_active
	(labels.checkpoint as Label3D).visible = _checkpoint_active
	show()

func _build_bank() -> void:
	gate = _native(SLUICE_ASSET, points.model, "BankDiversionModel")
	if gate == null:
		return
	gate.rotation = _gate_rotation
	_label("model", points.model + Vector3(0, 2.4, 0))
	_gauge_base = points.gauge + Vector3.UP * 0.15
	_label("gauge", _gauge_base + Vector3.UP * 2.4)
	(labels.gauge as Label3D).no_depth_test = true
	for index: int in range(3):
		var mark := _readout_quad(Vector2(0.7, 0.035), Color("f3e8bb"))
		mark.global_position = _gauge_base + Vector3(0, 0.3 + index * 0.65, 0)
	var claim := _readout_quad(Vector2(0.9, 0.045), Color("f2c65c"))
	claim.name = "BankPermitClaimMark"
	claim.global_position = _gauge_base + Vector3.UP * 1.6
	gauge_marker = _readout_quad(Vector2(0.5, 0.12), Color("41cde5"))
	gauge_marker.name = "BankGaugeReading"
	gauge_marker.global_position = _gauge_base + Vector3.UP * 0.3
	flow_material = ShaderMaterial.new()
	flow_material.shader = FLOW_SHADER
	var intake: Vector3 = points.get("intake", points.model)
	var diversion: Vector3 = points.get("diversion", points.flow)
	_flow_segment(intake, diversion)
	_flow_segment(diversion, points.flow)
	if points.has("reserve"):
		reserve = _native(CRATE_ASSET, points.reserve, "BankEmergencyReserve")
		_label("reserve", points.reserve + Vector3.UP * 1.7)
	if points.has("crossing"):
		crossing = _native(JETTY_ASSET, points.crossing + Vector3.UP * (DECK_CLEARANCE - JETTY_DECK_HEIGHT), "BankPreparedCrossing")
		if crossing != null:
			crossing.rotation.y = PI * 0.5
			deck_surface = StaticBody3D.new()
			deck_surface.name = "BankPreparedDeckSurface"
			deck_surface.collision_layer = 0
			deck_surface.collision_mask = 0
			crossing.add_child(deck_surface)
			var collision := CollisionShape3D.new()
			var deck := BoxShape3D.new()
			deck.size = Vector3(1.0, 0.05, 4.5) # Only the server's central walk lane.
			collision.shape = deck
			collision.position.y = JETTY_DECK_HEIGHT - 0.025
			deck_surface.add_child(collision)
		_label("crossing", points.crossing + Vector3.UP * 1.6)
	for index: int in range(1, 4):
		var key := "marker_" + str(index)
		var mark := _readout_quad(Vector2(0.65, 0.32), Color("e6c365"))
		(mark.material_override as StandardMaterial3D).billboard_mode = BaseMaterial3D.BILLBOARD_DISABLED
		mark.rotation.x = -PI * 0.5
		mark.global_position = points[key] + Vector3.UP * 0.08
		mark.name = "BankRemovable_" + key
		markers[key] = mark
		_label(key, points[key] + Vector3.UP * 1.1)
	for key: String in ["tree", "bypass"]:
		if points.has(key):
			_label(key, points[key] + Vector3.UP * 1.3)
	checkpoint = _readout_quad(Vector2(0.8, 0.8), Color("41cde5"))
	(checkpoint.material_override as StandardMaterial3D).billboard_mode = BaseMaterial3D.BILLBOARD_DISABLED
	checkpoint.rotation.x = -PI * 0.5
	checkpoint.name = "BankNextWalkCheckpoint"
	_label("checkpoint", points.flow + Vector3.UP * 1.3)

func set_readouts_visible(value: bool) -> void:
	super.set_readouts_visible(value)
	if is_instance_valid(checkpoint):
		checkpoint.visible = value and _checkpoint_active
	if labels.has("checkpoint"):
		(labels.checkpoint as Label3D).visible = value and _checkpoint_active
	for key: String in markers:
		(labels[key] as Label3D).visible = value and _markers_active

func _native(path: String, point: Vector3, title: String) -> Node3D:
	var instance := GlbSceneCache.instantiate(path)
	if instance == null:
		return null
	# Keep baked GLB normalization on its own root. The wrapper owns only the
	# approved placement, yaw and deck-height correction.
	var wrapper := Node3D.new()
	wrapper.name = title
	add_child(wrapper)
	wrapper.add_child(instance)
	wrapper.global_position = point
	for child: Node in wrapper.find_children("*", "MeshInstance3D", true, false):
		(child as MeshInstance3D).layers = 2
		if str(child.name).begins_with("Walk_"):
			(child as MeshInstance3D).hide()
	return wrapper

func _misplaced_at(misplaced: String, key: String, snapshot: Dictionary) -> bool:
	if misplaced.is_empty():
		return false
	if misplaced == key:
		return true
	var aliases := {"marker_1": "delivery", "marker_2": "split", "marker_3": "intake"}
	if misplaced.contains(aliases[key]):
		return true
	var anchor: Array = (snapshot.get("anchors", {}) as Dictionary).get(key, [])
	for target: Dictionary in snapshot.get("targets", []):
		if str(target.get("id", "")) == misplaced and target.get("tile", []) == anchor:
			return true
	return false

func clear() -> void:
	super.clear()
	bank.clear()
	markers.clear()
	crossing = null
	reserve = null
	checkpoint = null
	_checkpoint_active = false
	_markers_active = false
	deck_surface = null
