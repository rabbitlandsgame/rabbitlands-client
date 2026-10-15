class_name GroundBag3D
extends StaticBody3D

const PICK_LAYER := 16
## Layer 2 is visible to the world camera and excluded by both map cameras.
const WORLD_VISUAL_LAYER := 2

var bag_id: int = -1
var server_tile: Vector2i = Vector2i.ZERO

func configure(dto: Dictionary, adapter: CoordinateAdapter) -> void:
	bag_id = int(dto.get("bag_id", -1))
	server_tile = Vector2i(int(dto.get("x", 0)), int(dto.get("y", 0)))
	name = "GroundBag_%d" % bag_id
	collision_layer = PICK_LAYER
	collision_mask = 0
	# Configure before the node enters the scene tree; its parent WorldRoot uses
	# the same authored coordinate space, so a local transform is correct here.
	# Centered on the tile like the actor who dropped it, who stands at the
	# tile's center - a bag at the corner sat half a tile away from its owner.
	position = adapter.tile_center(server_tile.x, server_tile.y)
	_build_visual()

func set_surface_height(height: float) -> void:
	# Half the sack's own height, so it rests on the ground.
	global_position.y = height + 0.123

## Sized for the person who dropped it: the sack reads at 0.40 m across
## beside a 1.87 m body, knee high, rather than the 0.72 m boulder it was.
## Every part shares one scale so the shape is the authored one.
##
## The reference sack: a round-bellied bag of warm tan cloth, gathered into a
## short neck, tied with a dark cord, a small puff of cloth above the knot.
## The belly is a barely squashed sphere - the shape that reads as "full bag"
## at a glance - and every part shares the one cloth material so the light
## models the folds rather than a palette.
func _build_visual() -> void:
	if get_child_count() > 0:
		return
	var cloth: StandardMaterial3D = StandardMaterial3D.new()
	cloth.albedo_color = Color(0.8, 0.55, 0.32, 1.0)
	cloth.roughness = 0.95
	var body_mesh: SphereMesh = SphereMesh.new()
	body_mesh.radius = 0.20
	body_mesh.height = 0.40
	body_mesh.radial_segments = 24
	body_mesh.rings = 12
	body_mesh.material = cloth
	var body: MeshInstance3D = MeshInstance3D.new()
	body.name = "LegacyBagFallback"
	body.mesh = body_mesh
	body.layers = WORLD_VISUAL_LAYER
	# Almost a full sphere: barely settled under its own weight, and sunk a
	# touch into the ground so it sits rather than floats.
	body.scale = Vector3(1.0, 0.9, 1.0)
	body.position.y = 0.045
	add_child(body)

	var neck_mesh: CylinderMesh = CylinderMesh.new()
	neck_mesh.bottom_radius = 0.09
	neck_mesh.top_radius = 0.056
	neck_mesh.height = 0.078
	neck_mesh.material = cloth
	var neck: MeshInstance3D = MeshInstance3D.new()
	neck.name = "BagNeck"
	neck.mesh = neck_mesh
	neck.layers = WORLD_VISUAL_LAYER
	neck.position.y = 0.218
	add_child(neck)

	var cord_material: StandardMaterial3D = StandardMaterial3D.new()
	cord_material.albedo_color = Color(0.33, 0.19, 0.09, 1.0)
	cord_material.roughness = 0.9
	var cord_mesh: CylinderMesh = CylinderMesh.new()
	cord_mesh.bottom_radius = 0.064
	cord_mesh.top_radius = 0.064
	cord_mesh.height = 0.025
	cord_mesh.material = cord_material
	var cord: MeshInstance3D = MeshInstance3D.new()
	cord.name = "BagTie"
	cord.mesh = cord_mesh
	cord.layers = WORLD_VISUAL_LAYER
	cord.position.y = 0.255
	add_child(cord)

	var puff_mesh: SphereMesh = SphereMesh.new()
	puff_mesh.radius = 0.07
	puff_mesh.height = 0.14
	puff_mesh.material = cloth
	var puff: MeshInstance3D = MeshInstance3D.new()
	puff.name = "BagPuff"
	puff.mesh = puff_mesh
	puff.layers = WORLD_VISUAL_LAYER
	puff.scale = Vector3(1.0, 0.65, 1.0)
	puff.position.y = 0.277
	add_child(puff)

	var shape: CapsuleShape3D = CapsuleShape3D.new()
	shape.radius = 0.32
	shape.height = 0.62
	var collision: CollisionShape3D = CollisionShape3D.new()
	collision.name = "BagPickShape"
	collision.shape = shape
	add_child(collision)
