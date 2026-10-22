extends Label
## "+N nearby": how many players and creatures near the player the server is
## not sending, because the actor cap is reached.
##
## The cap keeps a crowded market or a dense invasion within what the client
## can draw; the nearest actors, the player's target, attackers, party and
## selection are always sent. What the cap leaves out would otherwise simply
## not be there, so this says that it is. It sits in the lower corner of the
## minimap, where a player already looks to see who is about, and is hidden at
## zero - which is always, on a server or a map that never reaches the cap.

const FONT_SIZE := 12
const OUTLINE_SIZE := 4
const COLOUR := Color(1.0, 0.93, 0.72)
const OUTLINE_COLOUR := Color(0.04, 0.04, 0.05, 0.95)

var count := 0

func _ready() -> void:
	name = "NearbyIndicator"
	horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
	# A tooltip needs the pointer; PASS hands the press on to the minimap so
	# dragging and its right-click menu still work over the label.
	mouse_filter = Control.MOUSE_FILTER_PASS
	add_theme_font_size_override("font_size", FONT_SIZE)
	add_theme_constant_override("outline_size", OUTLINE_SIZE)
	add_theme_color_override("font_color", COLOUR)
	add_theme_color_override("font_outline_color", OUTLINE_COLOUR)
	# The bottom-left corner: the compass letters take the middle of each
	# edge of the classic frame.
	set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	grow_horizontal = Control.GROW_DIRECTION_END
	grow_vertical = Control.GROW_DIRECTION_BEGIN
	offset_left = 4.0
	offset_bottom = -2.0
	show_count(count)

func show_count(hidden_nearby: int) -> void:
	count = maxi(0, hidden_nearby)
	visible = count > 0
	text = tr("ELORIA_NEARBY_HIDDEN").format({"count": count})
	tooltip_text = tr("ELORIA_NEARBY_HIDDEN_HINT")
