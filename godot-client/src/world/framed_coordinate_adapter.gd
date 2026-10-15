class_name FramedCoordinateAdapter
extends CoordinateAdapter
## A neighbouring map's coordinate adapter expressed in the active map's world.
##
## An actor on a map adjoining the player's across a land seam reports its tile
## in that map's own server frame. The exterior stream keeps the neighbour's
## scene resident under a rigid transform that lines its seam up with the
## active map's; this adapter turns the neighbour's tile into the neighbour's
## own metres and then carries the result through that frame, so the actor
## stands on the ground the player can see across the seam. Rotations gain the
## frame's yaw, and the inverse conversion undoes the frame first.

var frame: Transform3D = Transform3D.IDENTITY

func _init(config := {}, world_frame := Transform3D.IDENTITY) -> void:
	super(config)
	frame = world_frame

## The same adapter as `base`, carried through `world_frame`.
static func wrap(base: CoordinateAdapter, world_frame: Transform3D) -> FramedCoordinateAdapter:
	var framed := FramedCoordinateAdapter.new({}, world_frame)
	framed.metres_per_tile = base.metres_per_tile
	framed.origin = base.origin
	framed.server_origin = base.server_origin
	framed.walking_height = base.walking_height
	framed.invert_server_y = base.invert_server_y
	return framed

func server_to_godot(server_x: float, server_y: float, elevation := NAN) -> Vector3:
	return frame * super.server_to_godot(server_x, server_y, elevation)

func godot_to_server(position: Vector3) -> Vector2i:
	return super.godot_to_server(frame.affine_inverse() * position)

func rotation_to_godot(server_rotation: int) -> float:
	return super.rotation_to_godot(server_rotation) + frame.basis.get_euler().y

func direction_to_godot(direction: Vector2i) -> float:
	return super.direction_to_godot(direction) + frame.basis.get_euler().y

## The height an actor falls back to when no ground is found under it: the
## neighbour's walking height, where the frame puts it.
func fallback_height() -> float:
	return (frame * Vector3(0.0, walking_height, 0.0)).y
