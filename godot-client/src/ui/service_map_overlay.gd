extends "res://src/ui/picture_marker_overlay.gd"
## Permanent shop and tavern dots on region previews and the continent picture,
## and the one table of the colours a shop's category is drawn in.

const DotOverlayScript := preload("res://src/ui/minimap_marker_overlay.gd")
const EntranceOverlayScript := preload("res://src/ui/entrance_map_overlay.gd")
## A shop's map category -> the colour of its dot: the shopkeeper's own dot on
## every map, and the door of the building the shop is in. The publisher's copy
## is eloria-assets/maps/continent-v2/_continent_v2/map_categories.py, which
## refuses any other category, and the map legend (main.tscn, MapLegend) names
## each with a round dot in its colour; godot-client/tests/
## test_continent_v2_cartography.py keeps the three equal. Diamonds stay the
## server's pins, so a shop is always round.
const CATEGORY_COLOURS := {
	"tavern": Color("ef795f"),
	"general_store": Color("4fc67a"),
	"flower_shop": Color("e687da"),
	"magic_shop": Color("e2cf48"),
	"blacksmith": Color("9d73d8"),
	"bookshop": Color("e75252"),
}
const SHOP_COLOUR := Color("4fc67a")
const TAVERN_COLOUR := Color("ef795f")

## A shopkeeper's dot: its category's colour, or the general store's green for
## a category the table does not hold (the publisher refuses those).
static func dot_colour(mark: Dictionary) -> Color:
	return CATEGORY_COLOURS.get(str(mark.get("category", "")), SHOP_COLOUR) as Color

## A door's dot: the colour of the shop behind it, or the tan entrance dot for
## a door that leads into no shop (a cave, a house, the keep).
static func door_colour(mark: Dictionary) -> Color:
	return CATEGORY_COLOURS.get(str(mark.get("category", "")), EntranceOverlayScript.DOT_COLOUR) as Color

func _draw() -> void:
	for value: Variant in _marks:
		var mark: Dictionary = value as Dictionary
		var point: Variant = mark_point(mark)
		if not point is Vector2:
			continue
		draw_circle(point as Vector2, DotOverlayScript.BASE_RADIUS + DotOverlayScript.OUTLINE_WIDTH,
			DotOverlayScript.OUTLINE_COLOUR)
		draw_circle(point as Vector2, DotOverlayScript.BASE_RADIUS, dot_colour(mark))
