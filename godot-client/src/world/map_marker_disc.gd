class_name MapMarkerDisc
extends RefCounted
## The coloured disc a mark shows on the full map.
##
## Every circular mark on the full map is the same disc in a different colour
## and size - the actor dots, the harvest nodes and interactives, a dropped
## bag, the player's own position - so it is built here rather than four times
## over. The diamond pins the server places are not discs and are not built
## here; `map_marker_3d.gd` still draws those. The minimap once shared these
## discs and no longer does: a disc measured in metres is a different size at
## every zoom, so the minimap draws its marks in pixels instead. See
## `minimap_marker_overlay.gd`.
##
## The discs carry a black outline because the map they are read against is
## not a flat background: a green harvest node sits on parkland and a light
## blue actor dot sits on water, and at the sizes these draw at, a disc that
## shares a tone with the ground under it is not a mark, it is a texture.
##
## The discs draw with no depth test so that a building cannot hide the marker
## standing on it. That also means "put the outline underneath" is not
## something depth can decide - it never runs. Both materials are transparent
## instead, and `render_priority` orders them, which keeps every outline behind
## every fill no matter which way the map camera is facing.

## The visual layer the full-map camera renders, and nothing else does.
const MAP_MARKER_LAYER := 4
## How far the outline stands out past the disc, in metres. The full map frames
## 1600 metres across, so this is about a pixel there: enough to hold a disc
## off the ground it shares a tone with, without the outline closing over the
## colour it is meant to frame.
const OUTLINE_WIDTH := 1.6
const OUTLINE_COLOUR := Color(0.04, 0.04, 0.05)
## Thin enough that the disc reads as a mark drawn on the map rather than as a
## prop standing on it, which is what the map cameras look straight down at.
const DISC_HEIGHT := 0.08
const OUTLINE_PRIORITY := 0
const FILL_PRIORITY := 1

## A disc of `radius` metres in `colour`, outlined in black.
##
## The outline is a child of the disc, so a caller that moves, hides or frees
## the disc takes the outline with it and cannot leave a black ring behind on
## the map. Both are on the map layer; the caller sets the height.
static func build(node_name: String, radius: float, colour: Color,
		height: float = DISC_HEIGHT) -> MeshInstance3D:
	var disc: MeshInstance3D = _disc(
		node_name, radius, colour, FILL_PRIORITY, height)
	disc.add_child(_disc("%sOutline" % node_name, radius + OUTLINE_WIDTH,
		OUTLINE_COLOUR, OUTLINE_PRIORITY, height))
	return disc

static func _disc(node_name: String, radius: float, colour: Color,
		priority: int, height: float) -> MeshInstance3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = colour
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.no_depth_test = true
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.render_priority = priority
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = height
	mesh.material = material
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.layers = MAP_MARKER_LAYER
	return node
