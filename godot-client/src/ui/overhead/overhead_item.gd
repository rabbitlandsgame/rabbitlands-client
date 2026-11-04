class_name OverheadItem
extends RefCounted
## One drawable group of the 2D overhead layer (wave 2 OV-1): a banner block,
## a quest mark, a speech line, a pointer or a world label. It hangs from an
## anchor (a Node3D and a local point), and has its own visibility, fade,
## pixel offset, scale, distance range and optional pulse.
##
## Content is a list of draw operations in design pixels, y down, relative to
## the anchor's projected point: rectangles, texture rectangles and text with
## an optional outline, each on one of OverheadStyle.PASSES. A producer either
## rewrites the list itself (clear() then add_*()) or sets a `builder` that
## the layer calls when the item is next recorded, so a layout that needs
## text measurements runs lazily, inside the layer's shaping budget, only for
## items that are drawn. Changing the content marks the item dirty; the layer
## re-records its canvas items once (OverheadLayer._record), never per frame.
##
## Visibility, fade, offset, scale and range are properties whose setters
## hand the new value to the layer at once, so the layer's per-frame pass
## reads its own packed arrays and never this object (design probe B: the
## placement budget is well under a microsecond an item). Set them freely;
## setting an unchanged value costs nothing.
##
## Fields without a leading underscore belong to the producer. Fields with one
## belong to the layer, which keeps the item's canvas items (RIDs).

const Style := preload("res://src/ui/overhead/overhead_style.gd")

const OP_RECT := 0
const OP_TEXTURE_RECT := 1
const OP_TEXT := 2

## Where an item hangs: `node.to_global(point)`. Items may share one
## (OverheadItem.share_anchor) so the layer projects it once a frame: a
## banner's block, quest mark and speech line all hang from the same spot.
## The node is fixed at creation; attach() an item to a new anchor to move it
## to another node. The layer follows the node's tree membership, world and
## tree visibility through its signals (no per-frame checks).
class Anchor extends RefCounted:
	var node: Node3D
	var point := Vector3.ZERO: set = set_point
	# Layer-owned.
	var _layer: Object = null
	var _slot := -1
	var _callables: Array[Callable] = []

	func _init(anchor_node: Node3D = null, local_point := Vector3.ZERO) -> void:
		node = anchor_node
		point = local_point

	func set_point(value: Vector3) -> void:
		if point == value:
			return
		point = value
		if _layer != null and _slot >= 0:
			_layer.call("_anchor_moved", _slot, value)

var anchor: Anchor
## Shown at all (the producer's own rules: nameplate setting, crowding, drawn).
var visible := true: set = set_visible
## 0..1 alpha applied to every pass without a re-record; 0 hides the item.
var fade := 1.0: set = set_fade
## Extra offset from the anchor's projected point, in design pixels (y down).
var offset := Vector2.ZERO: set = set_offset
## Size relative to a design pixel (OverheadStyle.design_scale), e.g. the pointer.
var scale := 1.0: set = set_scale
## Camera distance beyond which the item hides (Label3D visibility_range_end
## semantics: hidden while the distance exceeds it); 0 for no limit.
var range_end := 0.0: set = set_range_end
## Hysteresis around range_end, as GeometryInstance3D.visibility_range_end_margin.
var range_end_margin := 0.0: set = set_range_end_margin
## Also hide while the anchor node is hidden in the tree. A producer that
## forwards NOTIFICATION_VISIBILITY_CHANGED itself may turn it off.
var follow_tree_visibility := true: set = set_follow_tree_visibility
## For tests and diagnostics, e.g. &"Block", &"Quest", &"Speech", &"Pointer".
var name := &""
## Optional `func(item: OverheadItem, cache) -> bool` that rewrites the content
## when the layer records it after invalidate(); false = not ready (text not
## shaped within this frame's budget), try again next frame.
var builder: Callable

var _ops: Array = []
var _revision := 1
var _build_revision := 1
var _pass_modulate: Dictionary = {}
var _pulse: Dictionary = {}

# Layer-owned state.
var _layer: Object = null
var _index := -1
var _dirty_sent := false
var _rids: Dictionary = {}
var _rid_list: Array[RID] = []
var _root := RID()
var _built_revision := 0
var _entries: Array = []

func _init(anchor_node: Node3D = null, local_point := Vector3.ZERO, item_name := &"") -> void:
	if anchor_node != null:
		anchor = Anchor.new(anchor_node, local_point)
	name = item_name

## Hang the item from `node` at `local_point` (a new anchor of its own).
func attach(node: Node3D, local_point := Vector3.ZERO) -> void:
	if anchor != null and anchor.node == node:
		anchor.point = local_point
		return
	_set_anchor(Anchor.new(node, local_point))

## Hang from the same anchor object as `other`, projected once for both.
func share_anchor(other: OverheadItem) -> void:
	_set_anchor(other.anchor)

## Moves the anchor's local point (every item sharing it follows).
func set_anchor_point(local_point: Vector3) -> void:
	if anchor != null:
		anchor.point = local_point

func _set_anchor(next: Anchor) -> void:
	if next == anchor:
		return
	var previous := anchor
	anchor = next
	if _layer != null:
		_layer.call("_item_anchor_changed", self, previous)

# --- Properties --------------------------------------------------------------------

func set_visible(value: bool) -> void:
	if visible == value:
		return
	visible = value
	if _layer != null:
		_layer.call("_item_visible", _index, value)

func set_fade(value: float) -> void:
	if fade == value:
		return
	fade = value
	if _layer != null:
		_layer.call("_item_fade", _index, value)

func set_offset(value: Vector2) -> void:
	if offset == value:
		return
	offset = value
	if _layer != null:
		_layer.call("_item_offset", _index, value)

func set_scale(value: float) -> void:
	if scale == value:
		return
	scale = value
	if _layer != null:
		_layer.call("_item_scale", _index, value)

func set_range_end(value: float) -> void:
	if range_end == value:
		return
	range_end = value
	if _layer != null:
		_layer.call("_item_range", _index, range_end, range_end_margin)

func set_range_end_margin(value: float) -> void:
	if range_end_margin == value:
		return
	range_end_margin = value
	if _layer != null:
		_layer.call("_item_range", _index, range_end, range_end_margin)

func set_follow_tree_visibility(value: bool) -> void:
	if follow_tree_visibility == value:
		return
	follow_tree_visibility = value
	if _layer != null:
		_layer.call("_item_follow_tree", _index, value)

# --- Content -----------------------------------------------------------------------

func clear() -> void:
	if _ops.is_empty():
		return
	_ops.clear()
	_changed()

func add_rect(pass_id: int, rect: Rect2, colour: Color) -> void:
	if not _valid_pass(pass_id):
		return
	_ops.append([OP_RECT, pass_id, rect, colour])
	_changed()

func add_texture_rect(pass_id: int, rect: Rect2, texture: Texture2D,
		modulate := Color.WHITE) -> void:
	if not _valid_pass(pass_id) or texture == null:
		return
	_ops.append([OP_TEXTURE_RECT, pass_id, rect, texture, modulate])
	_changed()

## Text with Label3D's alignment rules around `at` (design pixels, y down):
## each line is centred on at.x (LEFT starts there, RIGHT ends there) and the
## block's middle (TOP its top, BOTTOM its bottom) is at at.y. `outline_size`
## is in design pixels like Label3D's before the raster factor; 0 draws no
## outline. `wrap_width` > 0 wraps as AUTOWRAP_WORD_SMART at that width.
func add_text(text: String, font_size: int, at: Vector2, colour: Color,
		outline_size := 0, outline_colour := Color.BLACK, wrap_width := 0,
		horizontal := HORIZONTAL_ALIGNMENT_CENTER, vertical := VERTICAL_ALIGNMENT_CENTER,
		fill_pass := Style.PASS_TEXT, outline_pass := Style.PASS_TEXT_OUTLINE) -> void:
	if text.is_empty() or font_size <= 0 or not _valid_pass(fill_pass) \
			or (outline_size > 0 and not _valid_pass(outline_pass)):
		return
	_ops.append([OP_TEXT, fill_pass, at, colour, text, font_size, wrap_width,
		horizontal, vertical, outline_size, outline_colour, outline_pass])
	_changed()

## Content changed: ask the builder again at the next record (builder items),
## or re-record the current operations.
func invalidate() -> void:
	_build_revision += 1
	_changed()

## The current operations (read-only use: tests, parity checks).
func ops() -> Array:
	return _ops

func revision() -> int:
	return _revision

## A colour multiplied into one pass of this item without a re-record (the
## quest mark's pulse uses it on its letter pass).
func set_pass_modulate(pass_id: int, colour: Color) -> void:
	if _pass_modulate.get(pass_id, Color.WHITE) == colour:
		return
	if colour == Color.WHITE:
		_pass_modulate.erase(pass_id)
	else:
		_pass_modulate[pass_id] = colour
	if _layer != null:
		_layer.call("_item_modulate", _index)

func pass_modulate(pass_id: int) -> Color:
	return _pass_modulate.get(pass_id, Color.WHITE)

## A looping bob and colour pulse, evaluated by the layer from `start_usec`
## (the layer's clock, Time.get_ticks_usec): over `half_seconds` the offset
## eases (sine in-out) from `offset_from` to `offset_to` while the colour of
## `passes` goes linearly from `colour_from` to `colour_to`, then both return.
## The quest mark's Tween as a formula: no Tween per quest giver.
func set_pulse(start_usec: int, half_seconds: float, offset_from: Vector2,
		offset_to: Vector2, colour_from: Color, colour_to: Color,
		passes: Array[int] = [Style.PASS_TEXT]) -> void:
	_pulse = {"start": start_usec, "half": maxf(0.001, half_seconds),
		"from": offset_from, "to": offset_to, "colour_from": colour_from,
		"colour_to": colour_to, "passes": passes.duplicate()}
	if _layer != null:
		_layer.call("_item_pulse", _index, true)

func clear_pulse() -> void:
	if _pulse.is_empty():
		return
	var passes: Array = _pulse.passes
	_pulse = {}
	for pass_id: int in passes:
		set_pass_modulate(pass_id, Color.WHITE)
	if _layer != null:
		_layer.call("_item_pulse", _index, false)

func has_pulse() -> bool:
	return not _pulse.is_empty()

## The pulse at `now_usec`: [offset, colour], the formula the layer applies.
func pulse_state(now_usec: int) -> Array:
	if _pulse.is_empty():
		return [Vector2.ZERO, Color.WHITE]
	var half: float = _pulse.half
	var elapsed := float(now_usec - int(_pulse.start)) / 1000000.0
	var phase := fposmod(elapsed, half * 2.0)
	var u := phase / half if phase < half else 2.0 - phase / half
	var eased := (1.0 - cos(PI * u)) * 0.5
	var moved: Vector2 = (_pulse.from as Vector2).lerp(_pulse.to, eased)
	var colour: Color = (_pulse.colour_from as Color).lerp(_pulse.colour_to, u)
	return [moved, colour]

## Applies the pulse at `now_usec` (the layer calls it for drawn pulsing
## items); returns the offset to add.
func _apply_pulse(now_usec: int) -> Vector2:
	var state := pulse_state(now_usec)
	var colour: Color = state[1]
	for pass_id: int in _pulse.passes:
		set_pass_modulate(pass_id, colour)
	return state[0]

# --- Layer state, read-only for producers and tests ---------------------------------

## The layer this item is registered with, or null.
func layer() -> Object:
	return _layer if is_instance_valid(_layer) else null

## Drawn in the layer's last update.
func is_drawn() -> bool:
	return layer() != null and bool(_layer.call("_slot_shown", _index))

## Far-to-near draw rank in the last update (0 = farthest), or -1.
func rank() -> int:
	return int(_layer.call("_slot_rank", _index)) if is_drawn() else -1

## The layer-local origin the item was last drawn at (anchor point, snapped).
func drawn_origin() -> Vector2:
	return _layer.call("_slot_origin", _index) if layer() != null else Vector2(INF, INF)

## Canvas units per design pixel the item was last drawn with.
func drawn_scale() -> float:
	return float(_layer.call("_slot_scale", _index)) if layer() != null else -1.0

## The recorded content's bounds in design pixels around the origin.
func extent() -> Rect2:
	return _layer.call("_slot_extent", _index) if layer() != null else Rect2()

func is_recorded() -> bool:
	return layer() != null and bool(_layer.call("_slot_recorded", _index))

func canvas_items() -> Array[RID]:
	return _rid_list

func _changed() -> void:
	_revision += 1
	if _layer != null and not _dirty_sent:
		_dirty_sent = true
		_layer.call("_item_dirty", _index)

func _valid_pass(pass_id: int) -> bool:
	if Style.pass_index(pass_id) >= 0:
		return true
	push_error("OverheadItem: unknown pass %d (OverheadStyle.PASSES)" % pass_id)
	return false
