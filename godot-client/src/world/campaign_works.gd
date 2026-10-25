extends Node3D
## A private demonstration apparatus using an existing approved sluice asset.
## Gauge marks and the water strip are interface/effect geometry. Every displayed
## setting comes from the server; this node has no objective or reward authority.
const SLUICE_ASSET := "res://assets/world/underground/timber_sluice_gate.glb"
const FLOW_SHADER := preload("res://src/world/campaign_flow.gdshader")

var gate: Node3D
var gauge_marker: MeshInstance3D
var flow_material: ShaderMaterial
var labels: Dictionary = {}
var points: Dictionary = {}
var mechanism: Dictionary = {}
var _identity := ""
var _geometry := ""
var _gauge_base := Vector3.ZERO
var _setting := 0.0
var _sample: Callable
var _adapter: CoordinateAdapter
var _gate_rotation := Vector3.ZERO

func apply_snapshot(snapshot: Dictionary, adapter: CoordinateAdapter, current_map: String,
		surface_sample: Callable, reduced_motion := false) -> void:
	var valid := bool(snapshot.get("active", false)) and adapter != null \
		and EloriaProtocol.map_id_from_reference(current_map) == "twinbrook" \
		and EloriaProtocol.map_id_from_reference(str(snapshot.get("map", ""))) == "twinbrook" \
		and (snapshot.get("travel", {}) as Dictionary).is_empty()
	if not valid:
		clear()
		return
	var anchors: Dictionary = snapshot.get("anchors", {})
	if not anchors.has("bypass") or not anchors.has("gauge") or not anchors.has("flow"):
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
				return # Retry after the neighboring navigation surface is resident.
			grounded[key] = point
		var prop: Vector3 = grounded.get("sluice_prop", grounded.bypass)
		var left := _ground(prop + Vector3.LEFT * 2.0)
		var right := _ground(prop + Vector3.RIGHT * 2.0)
		var front := _ground(prop + Vector3.FORWARD * 0.5)
		var back := _ground(prop + Vector3.BACK * 0.5)
		if not left.is_finite() or not right.is_finite() or not front.is_finite() or not back.is_finite():
			clear()
			return
		var slope_x := (right.y - left.y) / 4.0
		var slope_z := back.y - front.y
		clear()
		_identity = identity
		_geometry = geometry
		points = grounded
		_gate_rotation = Vector3(-atan(slope_z), 0, atan(slope_x))
		_build()
	mechanism = (snapshot.get("mechanism", {}) as Dictionary).duplicate(true)
	var open := bool(mechanism.get("bypass_open", false))
	var fitted := bool(mechanism.get("fitting", false))
	var flow := int(mechanism.get("flow", 0))
	if labels.has("bypass"):
		(labels.bypass as Label3D).text = "Bypass · " + ("held open" if open else "closed")
	if labels.has("fitting"):
		(labels.fitting as Label3D).text = ("Manual bypass · " + ("braced" if fitted else "needs bracing")) \
			if str(snapshot.get("cargo", "")) == "medical" else "Pump fitting · " + ("secured" if fitted else "not installed")
	if labels.has("gauge"):
		var measured := int(mechanism.get("gauge", 0))
		var claimed := int(mechanism.get("claimed_gauge", 2))
		(labels.gauge as Label3D).text = "Measured: %d %s\nPermit: %d %s" % [measured, "unit" if measured == 1 else "units", claimed, "unit" if claimed == 1 else "units"]
	if labels.has("flow"):
		(labels.flow as Label3D).text = ["Flow · stopped", "Flow · check the diversion", "Flow · controlled"][clampi(flow, 0, 2)]
	if flow_material != null:
		flow_material.set_shader_parameter("flow_strength", float(flow) * 0.5)
		flow_material.set_shader_parameter("verified", flow == 2)
		flow_material.set_shader_parameter("reduced_motion", reduced_motion)
	show()

func _build() -> void:
	gate = GlbSceneCache.instantiate(SLUICE_ASSET)
	if gate == null:
		return
	gate.name = "CampaignNativeSluice"
	add_child(gate)
	gate.global_position = points.get("sluice_prop", points.bypass)
	gate.rotation = _gate_rotation
	for child: Node in gate.find_children("*", "MeshInstance3D", true, false):
		(child as MeshInstance3D).layers = 2
	_label("bypass", points.bypass + Vector3(0, 2.5, 0))
	if points.has("fitting"):
		_label("fitting", points.fitting + Vector3(0, 1.2, 0))
	_gauge_base = points.gauge + Vector3(0, 0.15, 0)
	_label("gauge", _gauge_base + Vector3(0, 2.4, 0))
	for index: int in range(3):
		var mark := _readout_quad(Vector2(0.7, 0.035), Color("f3e8bb"))
		mark.global_position = _gauge_base + Vector3(0, 0.3 + index * 0.65, 0)
	var claim := _readout_quad(Vector2(0.9, 0.045), Color("f2c65c"))
	claim.name = "PermitClaimMark"
	claim.global_position = _gauge_base + Vector3(0, 1.6, 0)
	gauge_marker = _readout_quad(Vector2(0.5, 0.12), Color("41cde5"))
	gauge_marker.name = "GaugeReading"
	gauge_marker.global_position = _gauge_base + Vector3(0, 0.3, 0)
	_label("flow", points.flow + Vector3(0, 1.3, 0))
	flow_material = ShaderMaterial.new()
	flow_material.shader = FLOW_SHADER
	var start: Vector3 = points.get("intake", points.flow + Vector3(-5, 0, -2))
	var through: Vector3 = points.get("diversion", points.flow + Vector3(-1.5, 0, -2))
	_flow_segment(start, through)
	_flow_segment(through, points.flow)

func _label(key: String, point: Vector3) -> void:
	var label := Label3D.new()
	label.name = "CampaignIndicator_" + key
	label.font = ThemeDB.fallback_font
	label.font_size = 32
	label.pixel_size = 0.0065
	label.outline_size = 5
	label.outline_modulate = Color("111820")
	if key == "gauge":
		label.font_size = 40
		label.pixel_size = 0.008
		label.outline_size = 10
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.layers = 2
	label.modulate = Color("fff1c9")
	label.no_depth_test = false
	add_child(label)
	label.global_position = point
	labels[key] = label

func _readout_quad(size: Vector2, colour: Color) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	var quad := QuadMesh.new()
	quad.size = size
	node.mesh = quad
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = colour
	material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	node.material_override = material
	node.layers = 2
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(node)
	return node

func _flow_segment(start: Vector3, finish: Vector3) -> void:
	var sideways := Vector3(-(finish - start).z, 0, (finish - start).x).normalized() * 0.34
	if sideways.length_squared() < 0.01:
		return
	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for index: int in range(8):
		var a := start.lerp(finish, float(index) / 8.0)
		var b := start.lerp(finish, float(index + 1) / 8.0)
		var corners: Array[Vector3] = []
		for point: Vector3 in [a - sideways, a + sideways, b + sideways, b - sideways]:
			var sampled := _ground(point)
			corners.append(sampled if sampled.is_finite() else point)
		for corner: int in [0, 1, 2, 0, 2, 3]:
			mesh.surface_set_normal(Vector3.UP)
			mesh.surface_set_uv(Vector2(0 if corner in [0, 3] else 1, float(index) / 8.0 if corner < 2 else float(index + 1) / 8.0))
			mesh.surface_add_vertex(to_local(corners[corner] + Vector3.UP * 0.065))
	mesh.surface_end()
	var stream := MeshInstance3D.new()
	stream.name = "CampaignWaterReadout"
	stream.mesh = mesh
	stream.material_override = flow_material
	stream.layers = 2
	stream.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(stream)

func _ground(point: Vector3) -> Vector3:
	if _sample.is_valid():
		var height: Variant = _sample.call(point)
		if typeof(height) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(height)):
			point.y = float(height)
		else:
			point.y = NAN
	else:
		point.y = NAN
	return point

func set_readouts_visible(value: bool) -> void:
	for label: Label3D in labels.values():
		label.visible = value

func _process(delta: float) -> void:
	if not is_instance_valid(gauge_marker):
		return
	_setting = move_toward(_setting, float(mechanism.get("gauge", 0)), delta * 2.5)
	gauge_marker.global_position = _gauge_base + Vector3(0, 0.3 + _setting * 0.65, 0)

func clear() -> void:
	for child: Node in get_children():
		remove_child(child)
		child.queue_free()
	gate = null
	gauge_marker = null
	flow_material = null
	labels.clear()
	points.clear()
	mechanism.clear()
	_identity = ""
	_geometry = ""
	_setting = 0.0
	hide()
