@tool
class_name TerrainHeightHandle
extends Marker3D

## Radius of this handle's smooth terrain height influence in world metres.
@export_range(1.0, 16.0, 0.25) var influence_radius := 6.0

## The saved local Y that represents zero height offset. Moving the handle in
## Y raises or lowers terrain relative to this neutral authoring position.
@export_storage var neutral_y := 0.0


func authored_height_offset() -> float:
	return position.y - neutral_y
