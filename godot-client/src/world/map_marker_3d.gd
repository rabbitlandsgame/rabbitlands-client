class_name MapMarker3D
extends Node3D
const WORLD_LABEL_STYLE := preload("res://src/ui/world_label_style.gd")
## A navigation marker on the map and in the gameplay viewport. The world
## effect is a green ground glow, rising sparks and a floating label; the
## full map keeps its larger gold pin. Personal annotations use the same
## world effect, with their map symbol supplied by the existing 2D overlay.
## This presentation never decides that a server marker has been reached.

## The visual layer the full-map camera renders, shared with world objects.
const MAP_MARKER_LAYER := 4
const MARKER_COLOUR := Color(0.98, 0.78, 0.22)
const GAMEPLAY_LAYER := 2
const WORLD_COLOUR := Color(0.4, 1.0, 0.08)
const WORLD_RANGE := 90.0

var marker_id: int = -1
var server_tile: Vector2i = Vector2i.ZERO
var label: String = ""
var _ground_glow: MeshInstance3D
var _flat_glow: ArrayMesh
var _world_label: Label3D

func configure(dto: Dictionary, adapter: CoordinateAdapter, draw_map_pin := true) -> void:
	marker_id = int(dto.get("marker_id", -1))
	server_tile = Vector2i(int(dto.get("x", 0)), int(dto.get("y", 0)))
	label = str(dto.get("label", ""))
	name = "MapMarker_%d" % marker_id
	position = adapter.tile_center(server_tile.x, server_tile.y)
	if _world_label == null:
		_build_world_visual()
	if draw_map_pin and not has_node("Pin"):
		_build_map_pin()
	_world_label.text = label if not label.is_empty() else "Marker"

func set_surface_height(height: float) -> void:
	global_position.y = height
	var draped: ArrayMesh = GroundDrape.drape(_ground_glow, _flat_glow)
	_ground_glow.mesh = draped if draped != null else _flat_glow

func _build_map_pin() -> void:
	var material := StandardMaterial3D.new()
	material.albedo_color = MARKER_COLOUR
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.no_depth_test = true
	# Sized to read on the full map, which covers a whole map at once: a pin
	# scaled for the gameplay view is a single pixel there.
	# A full map frames 1600 metres in under a thousand pixels, so 2.6 metres
	# of pin was a pixel and a half and read as nothing at all.
	var pin_mesh := CylinderMesh.new()
	pin_mesh.top_radius = 0.0
	pin_mesh.bottom_radius = 9.0
	pin_mesh.height = 6.0
	pin_mesh.radial_segments = 4
	pin_mesh.material = material
	var pin := MeshInstance3D.new()
	pin.name = "Pin"
	pin.mesh = pin_mesh
	pin.layers = MAP_MARKER_LAYER
	pin.position.y = 5.0
	pin.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(pin)

func _build_world_visual() -> void:
	var glow_material := StandardMaterial3D.new()
	glow_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	glow_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	glow_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	glow_material.vertex_color_use_as_albedo = true
	glow_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	_flat_glow = _glow_mesh()
	_ground_glow = MeshInstance3D.new()
	_ground_glow.name = "GroundGlow"
	_ground_glow.mesh = _flat_glow
	_ground_glow.material_override = glow_material
	_ground_glow.layers = GAMEPLAY_LAYER
	_ground_glow.visibility_range_end = WORLD_RANGE
	_ground_glow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_ground_glow)

	var spark_material := StandardMaterial3D.new()
	spark_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	spark_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	spark_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	spark_material.vertex_color_use_as_albedo = true
	spark_material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	var spark_mesh := QuadMesh.new()
	spark_mesh.size = Vector2(0.15, 0.15)
	spark_mesh.material = spark_material
	var particles := ParticleProcessMaterial.new()
	particles.direction = Vector3.UP
	particles.spread = 8.0
	particles.gravity = Vector3.ZERO
	particles.initial_velocity_min = 1.0
	particles.initial_velocity_max = 1.4
	particles.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	particles.emission_sphere_radius = 0.35
	var gradient := Gradient.new()
	var colours := PackedColorArray()
	var offsets := PackedFloat32Array()
	# Ease into and out of each spark's life with zero opacity and slope
	# at the wrap. Overlapping ages keep the stream continuously populated.
	for sample: int in range(65):
		var age: float = float(sample) / 64.0
		var alpha: float = smoothstep(0.0, 0.16, age) * (1.0 - smoothstep(0.35, 1.0, age))
		colours.append(Color(WORLD_COLOUR, alpha))
		offsets.append(age)
	gradient.colors = colours
	gradient.offsets = offsets
	var ramp := GradientTexture1D.new()
	ramp.gradient = gradient
	particles.color_ramp = ramp
	var sparks := GPUParticles3D.new()
	sparks.name = "RisingSparks"
	sparks.amount = 24
	sparks.lifetime = 2.4
	sparks.preprocess = 2.4
	sparks.one_shot = false
	sparks.explosiveness = 0.0
	sparks.randomness = 0.0
	sparks.fixed_fps = 60
	sparks.interpolate = true
	sparks.local_coords = true
	sparks.position.y = 0.4
	sparks.process_material = particles
	sparks.draw_pass_1 = spark_mesh
	sparks.layers = GAMEPLAY_LAYER
	sparks.visibility_range_end = WORLD_RANGE
	sparks.visibility_aabb = AABB(Vector3(-1.5, -0.5, -1.5), Vector3(3, 4.5, 3))
	sparks.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(sparks)

	_world_label = Label3D.new()
	_world_label.name = "WorldLabel"
	_world_label.position.y = 3.7
	_world_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_world_label.fixed_size = true
	# Match the actor labels' pixel calibration for the 50-degree game camera.
	WORLD_LABEL_STYLE.apply(_world_label, 16, 0.0012953, 5)
	_world_label.no_depth_test = true
	_world_label.layers = GAMEPLAY_LAYER
	_world_label.visibility_range_end = WORLD_RANGE
	add_child(_world_label)

## A soft ring, with transparent edges. The ground draper lifts each vertex
## onto slopes once the map's navigation surface is ready.
static func _glow_mesh() -> ArrayMesh:
	var vertices := PackedVector3Array()
	var colours := PackedColorArray()
	var radii := [0.35, 0.6, 0.85]
	var alpha := [0.0, 0.75, 0.0]
	for band: int in range(2):
		for segment: int in range(32):
			for corner: Vector2i in [Vector2i(0, 0), Vector2i(1, 0), Vector2i(1, 1),
					Vector2i(0, 0), Vector2i(1, 1), Vector2i(0, 1)]:
				var angle: float = TAU * float(segment + corner.x) / 32.0
				var radius: float = radii[band + corner.y]
				vertices.append(Vector3(cos(angle) * radius, 0.0, sin(angle) * radius))
				colours.append(Color(WORLD_COLOUR, alpha[band + corner.y]))
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_COLOR] = colours
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh

