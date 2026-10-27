extends Node3D
## Run-owned debris beside the real pier. Geometry, floor and movement authority
## stay with the published map; only confirmed snapshots change its status.
const DRIFTWOOD_ASSET := "res://assets/world/underground/driftwood.glb"
const LabelStyle := preload("res://src/ui/world_label_style.gd")
const TILE_FIELDS := ["damage_tile", "work_tile", "far_tile", "muster_tile"]

@export var debris_offset := Vector3(-0.5, 0.05, 2.0)
@export var debris_scale := 0.6
@export var debris_yaw_degrees := -160.0
@export var debris_roll_degrees := 8.0

var debris: Node3D
var native: Node3D
var status_label: Label3D
var points: Dictionary = {}
var crossing: Dictionary = {}
var _identity := ""
var _geometry := ""
var _world: World3D
var _readouts_visible := true

func apply_snapshot(snapshot: Dictionary, adapter: CoordinateAdapter, current_map: String,
		surface_sample: Callable) -> void:
	var data: Variant = snapshot.get("crossing", {})
	if not is_inside_tree() or not bool(snapshot.get("active", false)) or adapter == null \
			or str(snapshot.get("kind", "")) not in ["", "opening"] \
			or str(snapshot.get("run_id", "")).is_empty() \
			or not (snapshot.get("travel", {}) as Dictionary).is_empty() \
			or EloriaProtocol.map_id_from_reference(current_map) != "greenlight" \
			or EloriaProtocol.map_id_from_reference(str(snapshot.get("map", ""))) != "greenlight" \
			or not EloriaProtocol.campaign_crossing_valid(data) or (data as Dictionary).is_empty() \
			or not surface_sample.is_valid():
		clear()
		return
	var identity := str(snapshot.run_id)
	var tiles: Dictionary = {}
	for field: String in TILE_FIELDS:
		tiles[field] = data[field]
	var geometry := JSON.stringify(tiles)
	if _identity != identity or _geometry != geometry or _world != get_world_3d() \
			or not is_instance_valid(native):
		var grounded: Dictionary = {}
		for field: String in TILE_FIELDS:
			var tile: Array = data[field]
			var point := adapter.tile_center(int(tile[0]), int(tile[1]))
			var height: Variant = surface_sample.call(point)
			if typeof(height) not in [TYPE_FLOAT, TYPE_INT] or not is_finite(float(height)):
				clear()
				return # Revisit after the real pier navigation surface is resident.
			point.y = float(height)
			grounded[field] = point
		clear()
		_identity = identity
		_geometry = geometry
		_world = get_world_3d()
		points = grounded
		_build()
		if not is_instance_valid(native):
			clear()
			return
	crossing = (data as Dictionary).duplicate(true)
	debris.visible = not bool(crossing.braced) and not bool(crossing.rope_secured)
	status_label.text = status_text(crossing)
	status_label.visible = _readouts_visible
	show()

static func status_text(value: Dictionary) -> String:
	if bool(value.get("load_tested", false)):
		return "Load test passed"
	if bool(value.get("braced", false)):
		return "Access braced · load test next"
	if bool(value.get("rope_secured", false)):
		return "Handline secured · single file"
	return "Loose support · one person at a time"

func _build() -> void:
	native = GlbSceneCache.instantiate(DRIFTWOOD_ASSET)
	if native == null:
		return
	debris = Node3D.new()
	debris.name = "CampaignLodgedDriftwood"
	add_child(debris)
	debris.add_child(native)
	# The outer placement preserves the approved asset's own baked root,
	# embedded materials, geometry and texture closure.
	debris.global_position = (points.damage_tile as Vector3) + debris_offset
	debris.rotation_degrees = Vector3(0, debris_yaw_degrees, debris_roll_degrees)
	debris.scale = Vector3.ONE * debris_scale
	for child: Node in native.find_children("*", "MeshInstance3D", true, false):
		(child as MeshInstance3D).layers = 2 # Native portraits render layer 1 only.
	status_label = Label3D.new()
	status_label.name = "CampaignCrossingStatus"
	status_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	status_label.fixed_size = true
	status_label.visibility_range_end = 45.0
	status_label.modulate = Color("f1d59c")
	LabelStyle.apply(status_label, 14, 0.0012953, 5)
	add_child(status_label)
	status_label.global_position = (points.damage_tile as Vector3) + Vector3.UP * 1.55

func set_readouts_visible(value: bool) -> void:
	_readouts_visible = value
	if is_instance_valid(status_label):
		status_label.visible = value

func clear() -> void:
	for child: Node in get_children():
		if child is Node3D:
			(child as Node3D).hide()
		child.queue_free()
	debris = null
	native = null
	status_label = null
	points.clear()
	crossing.clear()
	_identity = ""
	_geometry = ""
	_world = null
	hide()
