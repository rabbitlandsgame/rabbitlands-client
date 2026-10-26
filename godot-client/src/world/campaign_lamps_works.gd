extends "res://src/world/campaign_works.gd"
## A small dry shore work bay. Native props are unchanged; marked scales,
## arrows and captions are readouts of the server's controlled experiment.
const LAMP_ASSET := "res://assets/world/underground/amber_lantern.glb"
const CRATE_ASSET := "res://assets/world/underground/supply_crate.glb"
const ROPE_ASSET := "res://assets/world/underground/rope_coils.glb"
var lamps: Dictionary = {}
var lamp: Node3D
var equipment: Node3D
var service_lamp: Node3D
var lamp_light: OmniLight3D
var service_light: OmniLight3D
var beam_mark: MeshInstance3D
var threshold_mark: MeshInstance3D
var pointer: MeshInstance3D
var _readouts: Array[Node3D] = []
var _shown := true
var checkpoint: MeshInstance3D
var _checkpoint_active := false
var zones: Dictionary = {}

func apply_snapshot(snapshot: Dictionary, adapter: CoordinateAdapter, current_map: String,
		surface_sample: Callable, reduced_motion := false) -> void:
	if not bool(snapshot.get("active", false)) or str(snapshot.get("kind", "")) != "lamps" \
			or adapter == null or EloriaProtocol.map_id_from_reference(current_map) != "greenlight" \
			or EloriaProtocol.map_id_from_reference(str(snapshot.get("map", ""))) != "greenlight" \
			or not (snapshot.get("travel", {}) as Dictionary).is_empty():
		clear()
		return
	var anchors: Dictionary = snapshot.get("anchors", {})
	for required: String in ["marker", "lamp", "indicator", "gate", "equipment"]:
		if not anchors.has(required):
			clear()
			return
	_adapter = adapter
	_sample = surface_sample
	var identity := str(snapshot.get("run_id", ""))
	var geometry := JSON.stringify(anchors)
	if _identity != identity or _geometry != geometry or not is_instance_valid(lamp):
		var grounded: Dictionary = {}
		for key: String in anchors:
			var tile: Array = anchors[key]
			var at := _ground(adapter.tile_center(int(tile[0]), int(tile[1])))
			if not at.is_finite():
				clear()
				return
			grounded[key] = at
		clear()
		_identity = identity
		_geometry = geometry
		points = grounded
		_build_lamps()
		if not is_instance_valid(lamp):
			clear()
			return
	lamps = (snapshot.get("lamps", {}) as Dictionary).duplicate(true)
	var water := int(lamps.get("water", 0))
	var marker := int(lamps.get("marker_number", 1))
	var beam := int(lamps.get("beam_height", 1))
	mechanism = {"gauge": water}
	if reduced_motion:
		_setting = float(water)
		_process(0)
	threshold_mark.global_position = _gauge_base + Vector3.UP * (0.3 + marker * 0.65)
	beam_mark.global_position = points.indicator + Vector3.UP * (0.3 + beam * 0.4)
	pointer.global_position = points.indicator + Vector3.UP * (0.3 + water * 0.4)
	(labels.marker as Label3D).text = "Marker %d · water %d\nClearance %d" % [marker, water, int(lamps.get("clearance", 0))]
	var shape := str(lamps.get("lamp_shape", ""))
	(labels.lamp as Label3D).text = "%s %s · %s\nBeam %d" % [{"circle": "○", "triangle": "△", "square": "□"}.get(shape, ""), shape, str(lamps.get("lamp_word", "")), beam]
	(labels.indicator as Label3D).text = "Pointer · " + str(lamps.get("indicator", ""))
	var aligned := water == beam and water <= marker
	lamp_light.light_energy = 1.5 if aligned else 0.08
	var settings: Dictionary = lamps.get("settings", {})
	if labels.has("control"):
		(labels.control as Label3D).text = "Interval %s\nMarker %d · lamp %d · drain %d" % [["I", "II", "III", "IV"][clampi(int(lamps.get("cycle", 0)), 0, 3)], int(settings.get("marker", 0)), int(settings.get("shutter", 0)), int(settings.get("bleed", 0))]
	if labels.has("gate"):
		var holder := str(lamps.get("holder", ""))
		if holder == "edda":
			holder = "Edda Tine"
		(labels.gate as Label3D).text = "Mechanism · held by " + holder if bool(lamps.get("holder_active", false)) \
			else holder + " · approaching holding post" if not holder.is_empty() else "Mechanism · needs a holder"
	var equipment_tile: Array = lamps.get("equipment_tile", anchors.equipment)
	var equipment_point := _ground(adapter.tile_center(int(equipment_tile[0]), int(equipment_tile[1])))
	if equipment_point.is_finite():
		equipment.global_position = equipment_point
		(labels.equipment as Label3D).global_position = equipment_point + Vector3.UP * 1.5
	(labels.equipment as Label3D).text = "Equipment and readings · secure" if bool(lamps.get("evidence_secure", false)) else "Local equipment · make safe before inquiry"
	var fitting_reading: Dictionary = {}
	for reading: Dictionary in lamps.get("evidence_readings", []):
		if str(reading.get("post", "")) != "reference":
			fitting_reading = reading
	if not fitting_reading.is_empty():
		(labels.equipment as Label3D).text += "\nMeasured %d / stamp %d" % [int(fitting_reading.value), int(fitting_reading.claimed)]
	if is_instance_valid(service_lamp):
		var done := bool(lamps.get("lamp_done", false))
		var built := done or bool((lamps.get("supplies", {}) as Dictionary).get("lamp_built", false))
		service_light.light_energy = 1.2 if built else 0.0
		(labels.service_lamp as Label3D).text = "Service holder · spare-reed wick tested" if done \
			else "Spare-reed wick prepared · test from the other view" if built else "Supplied service holder · prepare its reed wick"
	if labels.has("board"):
		(labels.board as Label3D).text = "Work instructions · verified" if bool(lamps.get("board_done", false)) else "Read the work instructions"
	_update_zones(lamps.get("unsafe_zones", []))
	_checkpoint_active = false
	for target: Dictionary in snapshot.get("targets", []):
		if int(target.get("object_id", -1)) != 0 or not bool(target.get("enabled", false)):
			continue
		var at := _ground(adapter.tile_center(int(target.tile[0]), int(target.tile[1])))
		if at.is_finite():
			_checkpoint_active = true
			checkpoint.global_position = at + Vector3.UP * 0.06
			(labels.checkpoint as Label3D).global_position = at + Vector3.UP * 0.9
			(labels.checkpoint as Label3D).text = str(target.label)
		break
	checkpoint.visible = _shown and _checkpoint_active
	(labels.checkpoint as Label3D).visible = _shown and _checkpoint_active
	show()

func _build_lamps() -> void:
	gate = _native(SLUICE_ASSET, points.gate, "CausewayWorkGate")
	lamp = _native(LAMP_ASSET, points.lamp, "CausewayTestLamp")
	equipment = _native(CRATE_ASSET, points.equipment, "CausewayLocalEquipment")
	if gate == null or lamp == null or equipment == null:
		return
	lamp_light = _light(lamp)
	for key: String in ["gate", "marker", "lamp", "indicator", "control", "equipment", "board"]:
		if points.has(key):
			_label(key, points[key] + (Vector3(-2, 1.5, 1.5) if key == "control" \
				else Vector3.UP * (3.0 if key == "lamp" else 3.4 if key == "marker" else 2.4 if key == "indicator" else 1.5)))
	for key: String in ["lamp_supply", "brace_stock"]:
		if points.has(key):
			_native(ROPE_ASSET if key == "brace_stock" else CRATE_ASSET, points[key], "Causeway" + key.capitalize())
	if points.has("service_lamp"):
		service_lamp = _native(LAMP_ASSET, points.service_lamp, "CausewayServiceHolder")
		if service_lamp != null:
			service_light = _light(service_lamp)
			_label("service_lamp", points.service_lamp + Vector3.UP * 3.0)
	_gauge_base = points.marker + Vector3.UP * 0.1
	for level: int in range(4):
		var line := _readout_quad(Vector2(0.7, 0.035), Color("f4e4b5"))
		line.global_position = _gauge_base + Vector3.UP * (0.3 + level * 0.65)
		_readouts.append(line)
		_label("level_" + str(level), line.global_position + Vector3.LEFT * 0.5)
		(labels["level_" + str(level)] as Label3D).text = str(level)
	gauge_marker = _readout_quad(Vector2(0.5, 0.12), Color("42cfe1"))
	threshold_mark = _readout_quad(Vector2(0.9, 0.05), Color("e8be5c"))
	beam_mark = _readout_quad(Vector2(0.8, 0.04), Color("f5cd6c"))
	pointer = _readout_quad(Vector2(0.4, 0.13), Color("4bd2e4"))
	_readouts.append_array([gauge_marker, threshold_mark, beam_mark, pointer])
	checkpoint = _readout_quad(Vector2(0.75, 0.75), Color("e8be5c"))
	(checkpoint.material_override as StandardMaterial3D).billboard_mode = BaseMaterial3D.BILLBOARD_DISABLED
	checkpoint.rotation.x = -PI * 0.5
	_label("checkpoint", points.control)
	for key: String in labels:
		var label: Label3D = labels[key]
		label.font_size = 30
		label.pixel_size = 0.0065
	set_readouts_visible(_shown)

func _light(parent: Node3D) -> OmniLight3D:
	var light := OmniLight3D.new()
	light.position = Vector3(-0.4, 1.6, 0)
	light.light_color = Color("ffd591")
	light.omni_range = 4.0
	light.shadow_enabled = false
	light.light_energy = 0.0
	parent.add_child(light)
	return light

func _native(path: String, point: Vector3, title: String) -> Node3D:
	var instance := GlbSceneCache.instantiate(path)
	if instance == null:
		return null
	var wrapper := Node3D.new()
	wrapper.name = title
	wrapper.add_child(instance)
	add_child(wrapper)
	wrapper.global_position = point
	for child: Node in wrapper.find_children("*", "MeshInstance3D", true, false):
		(child as MeshInstance3D).layers = 2
	return wrapper

func set_readouts_visible(value: bool) -> void:
	_shown = value
	super.set_readouts_visible(value)
	for readout: Node3D in _readouts:
		if is_instance_valid(readout):
			readout.visible = value
	if is_instance_valid(checkpoint):
		checkpoint.visible = value and _checkpoint_active
	if labels.has("checkpoint"):
		(labels.checkpoint as Label3D).visible = value and _checkpoint_active
	for zone: Node3D in zones.values():
		zone.visible = value

func _update_zones(readings: Array) -> void:
	for reading: Dictionary in readings:
		var key := str(reading.key)
		var bounds: Array = reading.bounds
		if not zones.has(key):
			var zone := Node3D.new()
			zone.name = "WorkBoundary_" + key
			add_child(zone)
			var start := _adapter.server_to_godot(float(bounds[0]), float(bounds[1]))
			var end := _adapter.server_to_godot(float(bounds[2]) + 1.0, float(bounds[3]) + 1.0)
			var middle := _ground((start + end) * 0.5)
			if not middle.is_finite():
				zone.queue_free()
				continue
			var width := absf(end.x - start.x)
			var depth := absf(end.z - start.z)
			for side: int in range(4):
				var edge := _readout_quad(Vector2(width if side < 2 else 0.06, 0.06 if side < 2 else depth), Color("dbb85a"))
				remove_child(edge)
				zone.add_child(edge)
				(edge.material_override as StandardMaterial3D).billboard_mode = BaseMaterial3D.BILLBOARD_DISABLED
				edge.rotation.x = -PI * 0.5
				edge.global_position = middle + Vector3(0 if side < 2 else width * (-0.5 if side == 2 else 0.5), 0.04, depth * (-0.5 if side == 0 else 0.5) if side < 2 else 0)
			zones[key] = zone
			_label("zone_" + key, middle + Vector3(-width * 0.5 + 1.0, 0.5, depth * 0.5 + 0.2))
		var closed := bool(reading.active)
		(labels["zone_" + key] as Label3D).text = ("STOP · " if closed else "OPEN · ") + key.replace("_", " ")
		for edge: Node in (zones[key] as Node3D).get_children():
			((edge as MeshInstance3D).material_override as StandardMaterial3D).albedo_color = Color("de785d") if closed else Color("64cfac")
		(zones[key] as Node3D).visible = _shown

func clear() -> void:
	super.clear()
	lamps.clear()
	_readouts.clear()
	zones.clear()
	checkpoint = null
	_checkpoint_active = false
	lamp = null
	equipment = null
	service_lamp = null
	lamp_light = null
	service_light = null
	beam_mark = null
	threshold_mark = null
	pointer = null
