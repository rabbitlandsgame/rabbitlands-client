class_name PlacedObject3D
extends Node3D
## One object the server put into a map that was already being played in.
##
## Everything this client knew about a map used to arrive with the map, so
## nothing could raise a totem in the square while somebody was standing in it.
## `GET_3D_OBJ(75)` says what to place and where; this draws it.
##
## The server names a model rather than a file, and the names it uses come from
## a legacy `3dobjects/...e3d` namespace this client has no art for and must not
## import. So the model name chooses between a small set of generated shapes by
## what the name says it is, and a name that matches nothing is drawn as a
## plain marker rather than not at all: an object that is there should be
## visible even when its appearance is not.

## The visual layer the gameplay camera renders.
const GAMEPLAY_LAYER := 1
const WORLD_LABEL_STYLE := preload("res://src/ui/world_label_style.gd")
const GROUND_RETRY_SECONDS := 0.25

var object_id := -1
var model := ""
var _ground_retry := 0.0
var _configured := false
var _initial_position := Vector3.ZERO

func _ready() -> void:
	if _configured:
		global_position = _initial_position
	set_physics_process(_configured)

func configure(placed: Dictionary, position: Vector3) -> void:
	object_id = int(placed.get("object_id", -1))
	model = str(placed.get("model", ""))
	_configured = true
	name = "PlacedObject_%d" % object_id
	_initial_position = position
	if is_inside_tree():
		global_position = position
	else:
		self.position = position
	rotation.y = deg_to_rad(float(int(placed.get("rotation", 0))))
	var shape: MeshInstance3D = MeshInstance3D.new()
	shape.name = "Shape"
	shape.mesh = _mesh_for(model)
	shape.layers = GAMEPLAY_LAYER
	# Mesh primitives are centred. Keep the node itself as the ground anchor,
	# and raise the geometry so its lower half is not inside the terrain.
	var bounds := shape.mesh.get_aabb()
	shape.position.y = -bounds.position.y
	add_child(shape)
	if model in ["ctf_red_flag", "ctf_blue_flag"]:
		shape.rotation.y = PI * 0.5
		var label := Label3D.new()
		label.text = "Red flag" if model == "ctf_red_flag" else "Blue flag"
		label.position.y = bounds.size.y + 0.6
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.no_depth_test = true
		label.fixed_size = true
		# Keep the objective text clear of the local player's resource overlay.
		label.offset.x = -90.0 if model == "ctf_red_flag" else 90.0
		WORLD_LABEL_STYLE.apply(label, 12, ReplicatedActor3D.OVERHEAD_PIXEL, 2)
		add_child(label)
	_ground_retry = 0.0
	set_physics_process(true)
	_try_ground.call_deferred()

func _physics_process(delta: float) -> void:
	_ground_retry -= delta
	if _ground_retry <= 0.0:
		_try_ground()

func _try_ground() -> void:
	_ground_retry = GROUND_RETRY_SECONDS
	if not is_inside_tree() or get_world_3d() == null:
		return
	# A flag can arrive before the streamed walk surface. Preserve its supplied
	# height on misses, retry at a bounded cadence, and stop querying once hit.
	var query := PhysicsRayQueryParameters3D.create(global_position + Vector3.UP * 200.0,
		global_position + Vector3.DOWN * 1800.0, WorldLoader.NAVIGATION_SURFACE_LAYER)
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		query.from += Vector3(0.0001, 0, 0.0001)
		query.to += Vector3(0.0001, 0, 0.0001)
		hit = get_world_3d().direct_space_state.intersect_ray(query)
	var point: Variant = hit.get("position")
	if point is Vector3:
		global_position.y = (point as Vector3).y
		set_physics_process(false)

## Which of the generated shapes a named object gets. The match is on what the
## name says the thing is, so a new prop whose name says "totem" is a totem
## without anybody editing this.
static func shape_name_for(model: String) -> String:
	var lowered: String = model.to_lower()
	if lowered.contains("totem") or lowered.contains("pillar"):
		return "totem"
	if lowered.contains("banner") or lowered.contains("flag"):
		return "banner"
	if lowered.contains("stone") or lowered.contains("altar"):
		return "stone"
	return "marker"

func _mesh_for(model_name: String) -> Mesh:
	var shape: String = shape_name_for(model_name)
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
	match shape:
		"totem":
			material.albedo_color = Color(0.62, 0.44, 0.26)
			var totem := CylinderMesh.new()
			totem.top_radius = 0.34
			totem.bottom_radius = 0.52
			totem.height = 3.4
			totem.material = material
			return totem
		"banner":
			material.albedo_color = Color(0.15, 0.35, 0.9) if model_name == "ctf_blue_flag" else Color(0.72, 0.24, 0.28)
			var banner := BoxMesh.new()
			banner.size = Vector3(0.12, 3.0, 1.1)
			banner.material = material
			return banner
		"stone":
			material.albedo_color = Color(0.55, 0.57, 0.62)
			var stone := BoxMesh.new()
			stone.size = Vector3(1.3, 1.6, 1.3)
			stone.material = material
			return stone
		_:
			# A name this client has no shape for. A short bright post, so it
			# is obvious that something is there and equally obvious that the
			# client does not know what.
			material.albedo_color = Color(0.85, 0.78, 0.35)
			material.emission_enabled = true
			material.emission = Color(0.5, 0.45, 0.15)
			var marker := CylinderMesh.new()
			marker.top_radius = 0.22
			marker.bottom_radius = 0.22
			marker.height = 1.8
			marker.material = material
			return marker
