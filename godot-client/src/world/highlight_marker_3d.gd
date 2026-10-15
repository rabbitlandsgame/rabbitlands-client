class_name HighlightMarker3D
extends Node3D
## The click-to-walk cross: four corner wedges that collapse into the tile a
## click ordered the player to, after the marker the legacy client draws in
## `highlight.c`.
##
## The reference behaviour, kept exactly: the marker lives for half a second;
## its corners start pushed half a tile outwards and slide into the centre at
## a rate of age² so the collapse starts fast and lands softly; the whole
## cross appears 0.3 m off the ground and settles onto it as it ages; and it
## fades with age, drawn additively so it reads as light on the ground rather
## than paint. A walking destination is green. The legacy client's other
## marker colours - spell target, attack target, lock - can join later
## through `configure`'s colour.

## Layer 2: the gameplay camera renders it, neither map camera does, and the
## minimap's marker overlay does not mark it. The legacy client never draws the
## cross on its maps either.
const GAMEPLAY_ONLY_VISUAL_LAYER := 2
const LIFESPAN_SECONDS := 0.5
## Metres the cross floats above the ground when it appears.
const LIFT_METRES := 0.3
const WALK_COLOUR := Color(0.0, 1.0, 0.0)
## Which quadrant each wedge slides through, in the order of their 90 degree
## rotations: rotating the (-x, -z) wedge by k * 90 degrees lands it in these
## quadrants, so wedge k's outward push is DIAGONALS[k] * offset.
const DIAGONALS: Array[Vector2] = [
	Vector2(-1.0, -1.0), Vector2(-1.0, 1.0), Vector2(1.0, 1.0), Vector2(1.0, -1.0)]

var _wedges: Array[MeshInstance3D] = []
var _material: StandardMaterial3D
var _time_left := LIFESPAN_SECONDS
var _half_tile := 0.5
var _ground_height := 0.0

## Builds the cross at `destination` (a tile centre at ground height) sized
## for `tile_metres`, and starts its half-second life. The transform is
## local: the parent WorldRoot uses the same authored coordinate space, the
## way the other tile-anchored nodes are placed.
func configure(destination: Vector3, tile_metres: float,
		colour: Color = WALK_COLOUR) -> void:
	position = destination
	_ground_height = destination.y
	_half_tile = tile_metres * 0.5
	_material = StandardMaterial3D.new()
	_material.albedo_color = colour
	_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	var mesh := _wedge_mesh(tile_metres / 6.0)
	for index in DIAGONALS.size():
		var wedge := MeshInstance3D.new()
		wedge.name = "Wedge%d" % index
		wedge.mesh = mesh
		wedge.material_override = _material
		wedge.rotation.y = index * PI / 2.0
		wedge.layers = GAMEPLAY_ONLY_VISUAL_LAYER
		wedge.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(wedge)
		_wedges.append(wedge)
	_present(1.0)

## A second click on the same tile restarts the mark there rather than
## stacking a brighter copy over it, like the reference's per-tile markers.
func restart() -> void:
	_time_left = LIFESPAN_SECONDS
	_present(1.0)

func _process(delta: float) -> void:
	_time_left -= delta
	if _time_left <= 0.0:
		queue_free()
		return
	_present(_time_left / LIFESPAN_SECONDS)

## `age` runs 1 -> 0 over the marker's life and drives everything at once:
## how far out the corners sit (age², so the collapse starts fast), how high
## the cross floats, and how bright it is.
func _present(age: float) -> void:
	var offset := _half_tile * age * age
	for index in _wedges.size():
		var diagonal: Vector2 = DIAGONALS[index]
		_wedges[index].position = Vector3(
			diagonal.x * offset, 0.0, diagonal.y * offset)
	position.y = _ground_height + LIFT_METRES * age
	_material.albedo_color.a = age

## One corner of the cross, the (-x, -z) quadrant of the reference's diagram,
## with the tile centre at the origin:
##
##   A---B---+
##   |   |   |
##   D---+---+
##   |   |   |
##   +---+---C(entre)
##
## An arm step is a sixth of a tile, so the resting cross spans two thirds of
## the tile it marks. The other three corners are this mesh rotated about the
## centre.
static func _wedge_mesh(arm: float) -> ArrayMesh:
	var a := Vector3(-2.0 * arm, 0.0, -2.0 * arm)
	var b := Vector3(-arm, 0.0, -2.0 * arm)
	var d := Vector3(-2.0 * arm, 0.0, -arm)
	var vertices := PackedVector3Array([
		a, b, Vector3.ZERO,
		a, Vector3.ZERO, d])
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh
