class_name OverheadLayer
extends Control
## Overhead text and banners as one 2D layer over the game view (wave 2 OV-1).
##
## Today's overhead content is Label3D and billboard quads on render layer 20,
## drawn by a second camera into a native-size SubViewport and blended over the
## game (src/ui/world_text_overlay.gd). This layer draws OverheadItems as
## retained RenderingServer canvas items under one Control instead, placed
## where that overlay's TextureRect sits. Not wired in stage B: OV-3 switches
## the actors to it, OV-5 the world labels, OV-6 removes the 3D pass.
##
## Structure: the Control's canvas item -> the layer's content root -> one
## parent per pass (OverheadStyle.PASSES, created on demand, in priority order)
## -> per item and pass, one child holding that item's recorded commands. The
## content root is what the layer hides while it is not drawing; the Control's
## own canvas item stays its owner's (CanvasItem.set_visible writes that one at
## the server, so hiding it would be undone by any hide/show cycle). So every backing of
## every item draws before any bar and every outline before any letter, as the
## render priorities order the 3D labels today (LAYERED). Within a pass,
## children are ranked far to near with canvas_item_set_draw_index, called
## only when an item's rank changes. ORDER_PER_BANNER (owner option O2) gives
## each item one root holding its passes instead.
##
## Each frame, in RenderingServer.frame_pre_draw (after scripts have moved
## bodies, as WorldTextOverlay._sync_camera), the layer:
## 1. reads the world viewport's current camera (campaign cut cameras included);
## 2. derives the fixed-size scale: one design pixel is
##    `OVERHEAD_PIXEL * P[1][1] * H / 2` pixels of the world view (orthographic:
##    `OVERHEAD_PIXEL * H / 2`, as the fixed-size shader scales), then maps
##    world-view pixels onto this Control (the view control's rect);
## 3. re-records changed items, inside a time budget, shaping text inside the
##    text cache's budget (an item whose text is not shaped yet waits);
## 4. projects each anchor once (Camera3D.unproject_position's arithmetic),
##    hides anchors behind the near plane (is_position_behind), applies each
##    item's distance range (GeometryInstance3D visibility_range_end: camera
##    distance, hidden beyond it, margin hysteresis) and culls items whose
##    extent is off screen;
## 5. sorts the drawn items far to near (Godot's transparent order: distance
##    from the camera, planar depth for orthographic) with a native sort, and
##    sends only what changed: visibility, draw index, transform, modulate.
## Glyphs are rasterised at their final size: text is drawn with an explicit
## oversampling of the native pixels per design pixel (quantised to 1/16),
## times the item's own scale for a scaled item such as the combat pointer.
## While that scale changes (resize, UI scale, a FOV lerp) the transform
## follows at once and the text is re-rasterised once the scale has held for
## SCALE_SETTLE_USEC, so a camera move does not re-record every item.
##
## Batch groups (`batch_groups`, default on). Godot 4.7.2 batches
## consecutive 2D draws only while they share a texture, and every font size
## (and outline size) has its own glyph texture, as has every status icon. With
## one parent per pass, a name (12) and its health numbers (11) alternate
## textures from banner to banner: the windowed probe measured 1190 canvas
## draw calls for 300 banners. So inside each pass the layer keeps one
## sub-parent per font size (text) and per texture (texture rects), in a fixed
## order, and ranks far to near inside each. Outlines still all draw before
## any letter and backings before bars; the one ordering change is between
## letters of different sizes (or icons of different kinds) of two
## overlapping banners, where the smaller size (the earlier texture) now
## always draws first instead of the farther banner. Off restores the strict
## per-pass far-to-near order (a candidate for owner option O2).
##
## Data layout: the per-frame pass reads only packed arrays the layer keeps
## per item slot and per anchor slot; items hand their property changes over
## when they happen, and anchors' tree membership, world and tree visibility
## arrive through the anchor nodes' signals. Removed items leave holes that
## are compacted, in order, once there are many of them.
##
## Runtime switch, for a within-run A/B: OverheadLayer.set_enabled(on) turns
## every layer that follows the switch on or off at once and tells producers
## through events().switched; `active` does it for one layer. An inactive
## layer does no work in frame_pre_draw and hides its content root at the
## server (the Control's `visible` stays its owner's), keeping its items and
## recordings so switching back costs no re-record. The launch default comes
## from RABBITLANDS_OVERHEAD_2D or `--overhead-2d=` (on/off; 2d/3d), see
## switch_request(). Headless runs never draw a frame, so frame_pre_draw never
## fires there; `update_when_headless` updates on SceneTree.process_frame
## instead, so a headless benchmark still accounts the placement work.
##
## Instrumentation for the crowd benchmark: last_update_usec (also split into
## last_record_usec, last_place_usec, last_apply_usec), items_drawn,
## rerecords_this_frame, rs_calls_this_frame (every RenderingServer call the
## update made; 0 when nothing changed), and stats().

const Style := preload("res://src/ui/overhead/overhead_style.gd")
const TextCache := preload("res://src/ui/overhead/overhead_text_cache.gd")
const Item := preload("res://src/ui/overhead/overhead_item.gd")
const HardwareTier := preload("res://src/runtime/hardware_tier.gd")

const SWITCH_VARIABLE := "RABBITLANDS_OVERHEAD_2D"
const SWITCH_ARGUMENT := "--overhead-2d="
## The layer's state when nothing asks otherwise. Nothing draws through the
## layer before OV-3, so this changes no picture in stage B.
const DEFAULT_ENABLED := true
const ON_SPELLINGS: Array[String] = ["2d"]
const OFF_SPELLINGS: Array[String] = ["3d"]

## Sort keys: quantised distance (1/1024 m) above 20 bits of item slot.
const INDEX_BITS := 20
const INDEX_MASK := (1 << INDEX_BITS) - 1
const DEPTH_STEPS_PER_METRE := 1024.0
const DEPTH_SPAN := 1 << 40
## Batch group keys: pass position above 20 bits of group (_group_key). Text
## groups are font sizes; texture groups start at TEXTURE_GROUP_BASE.
const GROUP_BITS := 20
const TEXTURE_GROUP_BASE := 4096

# Item slot flags.
const F_VISIBLE := 1
const F_ALPHA := 2
const F_RECORDED := 4
const F_DIRTY := 8
const F_FOLLOW_TREE := 16
const F_RANGE := 32
const F_PULSE := 64
const F_IN_RANGE := 128
const F_SHOWN := 256
const F_HAS_TEXT := 512
const F_MODULATE := 1024
const F_READY := F_VISIBLE | F_ALPHA | F_RECORDED
# Anchor slot state.
const A_IN_WORLD := 1
const A_TREE_VISIBLE := 2
const A_OK := 4

class SwitchEvents extends RefCounted:
	## The overhead switch changed (set_enabled / reset_switch).
	signal switched(enabled: bool)

static var _events: SwitchEvents
## -1: the launch request decides; 0/1: set_enabled() said off/on.
static var _switch_override := -1
static var _layers: Array[OverheadLayer] = []

## The 3D world this layer draws for (anchors must be in its World3D).
var world_viewport: Viewport
## The Control the world viewport is shown through (main.gd viewport_container);
## null: the world view covers this layer's own rect.
var view_control: Control
## Owner option O2. Set before the first item is recorded (canvas items are
## parented by it when they are created).
var order_mode := Style.ORDER_LAYERED
## Group a pass's draws by font size and texture so they batch (header).
## Set before the first item is recorded.
var batch_groups := true
## Owner option O3: snap each item's origin to whole device pixels.
var snap_origins := true
## Follow OverheadLayer.set_enabled(); false keeps `active` for this layer only.
var follow_switch := true
## Headless only: update on SceneTree.process_frame (see the header).
var update_when_headless := false: set = set_update_when_headless
var shape_budget_usec := Style.SHAPE_BUDGET_USEC
var rerecord_budget_usec := Style.RERECORD_BUDGET_USEC
var scale_settle_usec := Style.SCALE_SETTLE_USEC
var cull_margin := Style.CULL_MARGIN
var text_cache: TextCache
## Tests: a fixed clock (microseconds) for settle and pulse timing.
var now_usec_override := -1
var active := true: set = set_active

# Instrumentation of the last update.
var last_update_usec := 0
var last_record_usec := 0
var last_place_usec := 0
var last_apply_usec := 0
var items_drawn := 0
var rerecords_this_frame := 0
var rerecords_deferred := 0
var rs_calls_this_frame := 0
var rank_changes_this_frame := 0
var anchors_projected := 0
## Whether the last update drew (active, visible, a camera).
var drawing := false
var frames_updated := 0
var update_usec_total := 0
var rerecords_total := 0

var _configured := false
var _world: World3D
var _pass_parents: Dictionary = {}
var _pass_draw_index: Dictionary = {}
## Sub-parents per pass and batch group, by group key (_group_key).
var _group_parents: Dictionary = {}
## Texture RID id -> its batch group number (first come, first numbered).
var _texture_groups: Dictionary = {}
## Parent of every pass parent and of the PER_BANNER parent (see the header).
var _content_root := RID()
var _banner_parent := RID()
var _frame := 0
var _keys := PackedInt64Array()
var _oversampling := 0.0
var _pending_oversampling := 0.0
var _pending_since_usec := 0
var _k := 0.0
var _canvas_scale := 0.0
var _device_scale := 1.0
var _server_visible := true
## Some slot may carry F_DIRTY (skips the record scan on quiet frames).
var _dirty_pending := false

# Item slots (index = OverheadItem._index). Holes: null item, flags 0.
var _items: Array = []
var _holes := 0
var _flags := PackedInt32Array()
var _anchor_of := PackedInt32Array()
var _alpha := PackedFloat64Array()
var _offset := PackedVector2Array()
var _scales := PackedFloat64Array()
var _range := PackedFloat64Array()
var _range_margin := PackedFloat64Array()
var _extent_position := PackedVector2Array()
var _extent_size := PackedVector2Array()
var _origin := PackedVector2Array()
var _applied_scale := PackedFloat64Array()
var _applied_alpha := PackedFloat64Array()
var _rank := PackedInt32Array()
var _next_origin := PackedVector2Array()
var _next_scale := PackedFloat64Array()
var _slot_rids: Array = []
var _slot_roots: Array[RID] = []

# Anchor slots (index = OverheadItem.Anchor._slot), reused through a free list.
var _anchor_objects: Array = []
var _anchor_nodes: Array[Node3D] = []
var _anchor_points := PackedVector3Array()
var _anchor_state := PackedInt32Array()
var _anchor_frame := PackedInt32Array()
var _anchor_screen := PackedVector2Array()
var _anchor_distance := PackedFloat64Array()
var _anchor_sort := PackedFloat64Array()
var _anchor_users := PackedInt32Array()
var _anchor_free := PackedInt32Array()
## The instance id of each anchor slot's node (0: none), and per watched node
## {node, slots, callables} (_watch_node).
var _anchor_node_ids := PackedInt64Array()
var _watched_nodes: Dictionary = {}

# --- Switch ------------------------------------------------------------------------

static func events() -> SwitchEvents:
	if _events == null:
		_events = SwitchEvents.new()
	return _events

## What the launch asks for: {"mode": "on"|"off"|"", "source": "argument"|
## "environment"|"", "rejected": PackedStringArray}. A valid `--overhead-2d=`
## user argument wins over RABBITLANDS_OVERHEAD_2D, the last one when repeated.
static func switch_request() -> Dictionary:
	return resolve_switch(OS.get_environment(SWITCH_VARIABLE), OS.get_cmdline_user_args())

## Pure form of switch_request. On: on/1/true/yes/2d. Off: off/0/false/no/
## legacy/3d (HardwareTier's spellings plus 2d/3d).
static func resolve_switch(environment_value: String, arguments: PackedStringArray) -> Dictionary:
	var mode := ""
	var source := ""
	var rejected := PackedStringArray()
	var candidates: Array[Array] = [[environment_value, "environment"]]
	for argument: String in arguments:
		if argument.begins_with(SWITCH_ARGUMENT):
			candidates.append([argument.trim_prefix(SWITCH_ARGUMENT), "argument"])
	for candidate: Array in candidates:
		var value := str(candidate[0]).strip_edges().to_lower()
		if value.is_empty():
			continue
		if value in HardwareTier.ON_SPELLINGS or value in ON_SPELLINGS:
			mode = "on"
			source = str(candidate[1])
		elif value in HardwareTier.OFF_SPELLINGS or value in OFF_SPELLINGS:
			mode = "off"
			source = str(candidate[1])
		else:
			rejected.append(value)
	return {"mode": mode, "source": source, "rejected": rejected}

## Whether overhead content should draw through the 2D layer now: the last
## set_enabled() if any, else the launch request, else DEFAULT_ENABLED.
static func enabled() -> bool:
	if _switch_override >= 0:
		return _switch_override == 1
	var request := switch_request()
	if str(request.mode).is_empty():
		return DEFAULT_ENABLED
	return request.mode == "on"

## The within-run A/B switch: every layer that follows the switch turns on or
## off now, and producers hear it through events().switched.
static func set_enabled(on: bool) -> void:
	var changed := enabled() != on
	_switch_override = 1 if on else 0
	if changed:
		events().switched.emit(on)

## Back to the launch request (tests). Always tells the layers and producers,
## since the request itself (the environment) may have changed meanwhile.
static func reset_switch() -> void:
	_switch_override = -1
	events().switched.emit(enabled())

## The most recently configured layer still in the tree, or null.
static func current() -> OverheadLayer:
	for index: int in range(_layers.size() - 1, -1, -1):
		var layer: OverheadLayer = _layers[index]
		if is_instance_valid(layer) and layer.is_inside_tree():
			return layer
	return null

## The layer drawing for `world`, or null.
static func for_world(world: World3D) -> OverheadLayer:
	if world == null:
		return null
	for index: int in range(_layers.size() - 1, -1, -1):
		var layer: OverheadLayer = _layers[index]
		if is_instance_valid(layer) and layer.is_inside_tree() and layer._world == world:
			return layer
	return null

# --- Set-up ------------------------------------------------------------------------

## Draw for `world` (its current camera) over this Control. `view` is the
## Control that shows the world viewport (null: this layer's own rect).
## Place the layer where WorldTextOverlay sits: in GameView, full rect, just
## above the viewport container.
func configure(world: Viewport, view: Control = null) -> void:
	world_viewport = world
	view_control = view
	_world = world.find_world_3d() if is_instance_valid(world) else null
	if str(name).is_empty() or str(name).begins_with("@"):
		name = "OverheadLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	focus_mode = Control.FOCUS_NONE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	clip_contents = true
	if text_cache == null:
		text_cache = TextCache.new(Style.font())
	# A layer configured again for another world re-judges its anchors (their
	# signals only report later changes).
	for slot: int in range(_anchor_objects.size()):
		if _anchor_objects[slot] != null:
			_refresh_anchor(slot)
	_configured = true
	if follow_switch:
		active = enabled()
	if not events().switched.is_connected(_on_switched):
		events().switched.connect(_on_switched)
	if is_inside_tree():
		_start()

func _enter_tree() -> void:
	if _configured:
		_start()

func _exit_tree() -> void:
	if RenderingServer.frame_pre_draw.is_connected(update_now):
		RenderingServer.frame_pre_draw.disconnect(update_now)
	var tree := get_tree()
	if tree != null and tree.process_frame.is_connected(update_now):
		tree.process_frame.disconnect(update_now)
	_layers.erase(self)

func _notification(what: int) -> void:
	if what == NOTIFICATION_PREDELETE:
		_layers.erase(self)
		for item: Variant in _items:
			if item != null:
				_release_item(item as Item, true)
		_items.clear()
		for rid: RID in _group_parents.values():
			RenderingServer.free_rid(rid)
		_group_parents.clear()
		for rid: RID in _pass_parents.values():
			RenderingServer.free_rid(rid)
		_pass_parents.clear()
		if _banner_parent.is_valid():
			RenderingServer.free_rid(_banner_parent)
			_banner_parent = RID()
		if _content_root.is_valid():
			RenderingServer.free_rid(_content_root)
			_content_root = RID()

func _start() -> void:
	if not RenderingServer.frame_pre_draw.is_connected(update_now):
		RenderingServer.frame_pre_draw.connect(update_now)
	_sync_headless_updates()
	_layers.erase(self)
	_layers.append(self)

func set_update_when_headless(value: bool) -> void:
	update_when_headless = value
	if is_inside_tree():
		_sync_headless_updates()

func _sync_headless_updates() -> void:
	var tree := get_tree()
	var wanted := update_when_headless and DisplayServer.get_name() == "headless"
	if wanted and not tree.process_frame.is_connected(update_now):
		tree.process_frame.connect(update_now)
	elif not wanted and tree.process_frame.is_connected(update_now):
		tree.process_frame.disconnect(update_now)

func _on_switched(on: bool) -> void:
	if follow_switch:
		active = on

func set_active(value: bool) -> void:
	if active == value:
		return
	active = value
	if not active:
		_set_server_visible(false)
		drawing = false

## Whether `node` is in the world this layer draws (preview and portrait
## actors in their own worlds never draw, as the layer-20 camera never saw them).
func accepts(node: Node3D) -> bool:
	return is_instance_valid(node) and node.is_inside_tree() and _world != null \
		and node.get_world_3d() == _world

# --- Items -------------------------------------------------------------------------

func add_item(item: Item) -> void:
	if item == null or item._layer == self:
		return
	var previous: Object = item.layer()
	if previous != null:
		previous.call("remove_item", item)
	var slot := _items.size()
	item._layer = self
	item._index = slot
	item._dirty_sent = true
	_dirty_pending = true
	_items.append(item)
	var flags := F_DIRTY
	if item.visible:
		flags |= F_VISIBLE
	if item.fade > 0.0:
		flags |= F_ALPHA
	if item.follow_tree_visibility:
		flags |= F_FOLLOW_TREE
	if item.range_end > 0.0:
		flags |= F_RANGE | F_IN_RANGE
	else:
		flags |= F_IN_RANGE
	if item.has_pulse():
		flags |= F_PULSE
	_flags.append(flags)
	_anchor_of.append(_acquire_anchor(item))
	_alpha.append(clampf(item.fade, 0.0, 1.0))
	_offset.append(item.offset)
	_scales.append(item.scale)
	_range.append(item.range_end)
	_range_margin.append(item.range_end_margin)
	_extent_position.append(Vector2.ZERO)
	_extent_size.append(Vector2.ZERO)
	_origin.append(Vector2(INF, INF))
	_applied_scale.append(-1.0)
	_applied_alpha.append(-1.0)
	_rank.append(-1)
	_next_origin.append(Vector2.ZERO)
	_next_scale.append(0.0)
	_slot_rids.append(item._rid_list)
	_slot_roots.append(RID())

func remove_item(item: Item) -> void:
	if item == null or item._layer != self:
		return
	var slot := item._index
	if slot >= 0 and slot < _items.size() and _items[slot] == item:
		var no_rids: Array[RID] = []
		_items[slot] = null
		_flags[slot] = 0
		_anchor_of[slot] = -1
		_slot_rids[slot] = no_rids
		_slot_roots[slot] = RID()
		_holes += 1
	_release_item(item, true)

func has_item(item: Item) -> bool:
	return item != null and item._layer == self

func item_count() -> int:
	return _items.size() - _holes

## Native pixels of the world view per design pixel, from the last update.
func scale_k() -> float:
	return _k

## Canvas units of this Control per design pixel, from the last update.
func canvas_scale() -> float:
	return _canvas_scale

## Device pixels per canvas unit of this Control, from the last update.
func device_scale() -> float:
	return _device_scale

## The glyph raster scale text is currently recorded at.
func oversampling() -> float:
	return _oversampling

## Passes whose parent exists, in their draw order (tests).
func pass_order() -> Array[int]:
	var order: Array[int] = []
	for pass_id: int in _pass_draw_index.keys():
		order.append(pass_id)
	order.sort_custom(func(a: int, b: int) -> bool:
		return int(_pass_draw_index[a]) < int(_pass_draw_index[b]))
	return order

func pass_parent(pass_id: int) -> RID:
	return _pass_parents.get(pass_id, RID())

## The canvas item every pass hangs from, the one hidden while the layer is not
## drawing (created with the first recording; tests).
func content_root() -> RID:
	return _content_root

## Whether the content root is shown at the server (tests).
func content_shown() -> bool:
	return _server_visible

func anchor_count() -> int:
	return _anchor_objects.size() - _anchor_free.size()

func stats() -> Dictionary:
	return {"active": active, "drawing": drawing, "items": item_count(),
		"anchors": anchor_count(), "items_drawn": items_drawn,
		"last_update_usec": last_update_usec, "last_record_usec": last_record_usec,
		"last_place_usec": last_place_usec, "last_apply_usec": last_apply_usec,
		"rerecords_this_frame": rerecords_this_frame, "rerecords_deferred": rerecords_deferred,
		"rs_calls_this_frame": rs_calls_this_frame,
		"rank_changes_this_frame": rank_changes_this_frame,
		"anchors_projected": anchors_projected, "frames_updated": frames_updated,
		"update_usec_total": update_usec_total, "rerecords_total": rerecords_total,
		"k": _k, "canvas_scale": _canvas_scale, "oversampling": _oversampling,
		"order_mode": "per_banner" if order_mode == Style.ORDER_PER_BANNER else "layered",
		"text": text_cache.stats() if text_cache != null else {}}

func now_usec() -> int:
	return now_usec_override if now_usec_override >= 0 else Time.get_ticks_usec()

# Item hand-overs (OverheadItem's setters call these with the item's slot).

func _item_visible(slot: int, value: bool) -> void:
	_set_flag(slot, F_VISIBLE, value)
	if value and (_flags[slot] & F_DIRTY) != 0:
		_dirty_pending = true

func _item_fade(slot: int, value: float) -> void:
	_alpha[slot] = clampf(value, 0.0, 1.0)
	_set_flag(slot, F_ALPHA, value > 0.0)
	if value > 0.0 and (_flags[slot] & F_DIRTY) != 0:
		_dirty_pending = true

func _item_offset(slot: int, value: Vector2) -> void:
	_offset[slot] = value

func _item_scale(slot: int, value: float) -> void:
	_scales[slot] = value
	if _flags[slot] & F_HAS_TEXT:
		# Its text is rasterised at the scale it is drawn at (_record).
		_flags[slot] = _flags[slot] | F_DIRTY
		_dirty_pending = true

func _item_range(slot: int, end: float, margin: float) -> void:
	_range[slot] = end
	_range_margin[slot] = margin
	_set_flag(slot, F_RANGE, end > 0.0)

func _item_follow_tree(slot: int, value: bool) -> void:
	_set_flag(slot, F_FOLLOW_TREE, value)

func _item_dirty(slot: int) -> void:
	_flags[slot] = _flags[slot] | F_DIRTY
	_dirty_pending = true

func _item_modulate(slot: int) -> void:
	_flags[slot] = _flags[slot] | F_MODULATE

func _item_pulse(slot: int, on: bool) -> void:
	_set_flag(slot, F_PULSE, on)
	_flags[slot] = _flags[slot] | F_MODULATE

func _item_anchor_changed(item: Item, previous: Item.Anchor) -> void:
	_release_anchor(previous)
	_anchor_of[item._index] = _acquire_anchor(item)

func _set_flag(slot: int, flag: int, on: bool) -> void:
	_flags[slot] = (_flags[slot] | flag) if on else (_flags[slot] & ~flag)

# Slot reads for OverheadItem's state accessors.

func _slot_shown(slot: int) -> bool:
	return drawing and slot >= 0 and slot < _flags.size() and (_flags[slot] & F_SHOWN) != 0

func _slot_recorded(slot: int) -> bool:
	return slot >= 0 and slot < _flags.size() and (_flags[slot] & F_RECORDED) != 0

func _slot_rank(slot: int) -> int:
	return _rank[slot]

func _slot_origin(slot: int) -> Vector2:
	return _origin[slot]

func _slot_scale(slot: int) -> float:
	return _applied_scale[slot]

func _slot_extent(slot: int) -> Rect2:
	return Rect2(_extent_position[slot], _extent_size[slot])

# --- Anchors -----------------------------------------------------------------------

func _acquire_anchor(item: Item) -> int:
	var anchor: Item.Anchor = item.anchor
	if anchor == null:
		return -1
	if anchor._layer != null and anchor._layer != self:
		# An anchor follows one layer; give this item its own.
		anchor = Item.Anchor.new(anchor.node, anchor.point)
		item.anchor = anchor
	if anchor._layer == self and anchor._slot >= 0:
		_anchor_users[anchor._slot] += 1
		return anchor._slot
	var slot: int
	if not _anchor_free.is_empty():
		slot = _anchor_free[_anchor_free.size() - 1]
		_anchor_free.resize(_anchor_free.size() - 1)
	else:
		slot = _anchor_objects.size()
		_anchor_objects.append(null)
		_anchor_nodes.append(null)
		_anchor_points.append(Vector3.ZERO)
		_anchor_state.append(0)
		_anchor_frame.append(-1)
		_anchor_screen.append(Vector2.ZERO)
		_anchor_distance.append(0.0)
		_anchor_sort.append(0.0)
		_anchor_users.append(0)
		_anchor_node_ids.append(0)
	anchor._layer = self
	anchor._slot = slot
	_anchor_objects[slot] = anchor
	_anchor_points[slot] = anchor.point
	_anchor_frame[slot] = -1
	_anchor_users[slot] = 1
	var node: Node3D = anchor.node if is_instance_valid(anchor.node) else null
	_anchor_nodes[slot] = node
	_anchor_state[slot] = 0
	if node != null:
		_watch_node(node, slot)
		_refresh_anchor(slot)
	return slot

func _release_anchor(anchor: Item.Anchor) -> void:
	if anchor == null or anchor._layer != self or anchor._slot < 0:
		return
	var slot := anchor._slot
	_anchor_users[slot] -= 1
	if _anchor_users[slot] > 0:
		return
	_unwatch_node(_anchor_node_ids[slot], slot)
	_anchor_node_ids[slot] = 0
	anchor._layer = null
	anchor._slot = -1
	_anchor_objects[slot] = null
	_anchor_nodes[slot] = null
	_anchor_state[slot] = 0
	_anchor_users[slot] = 0
	_anchor_free.append(slot)

## An anchor counts as in the world while its node is inside the tree of this
## layer's World3D; its tree visibility is the node's is_visible_in_tree().
func _refresh_anchor(slot: int) -> void:
	var node: Node3D = _anchor_nodes[slot]
	var state := 0
	if node != null and node.is_inside_tree() and node.get_world_3d() == _world:
		state = A_IN_WORLD
		if node.is_visible_in_tree():
			state |= A_TREE_VISIBLE
	_anchor_state[slot] = state

## Follows a node's tree membership and visibility for one more anchor slot.
## Godot counts one method bound to different arguments as one connection, so
## each node is connected once, bound to its instance id, and its handlers
## refresh every anchor slot it carries (a banner hangs its block, boss tag and
## pointer from the same actor at three heights).
func _watch_node(node: Node3D, slot: int) -> void:
	var id := node.get_instance_id()
	_anchor_node_ids[slot] = id
	var entry: Dictionary = _watched_nodes.get(id, {})
	if entry.is_empty():
		var callables: Array[Callable] = [_on_node_entered.bind(id), _on_node_exiting.bind(id),
			_on_node_visibility.bind(id)]
		node.tree_entered.connect(callables[0])
		node.tree_exiting.connect(callables[1])
		node.visibility_changed.connect(callables[2])
		entry = {"node": node, "slots": PackedInt32Array(), "callables": callables}
		_watched_nodes[id] = entry
	var slots: PackedInt32Array = entry.slots
	slots.append(slot)
	entry.slots = slots

func _unwatch_node(id: int, slot: int) -> void:
	var entry: Dictionary = _watched_nodes.get(id, {})
	if entry.is_empty():
		return
	var slots: PackedInt32Array = entry.slots
	var at := slots.find(slot)
	if at >= 0:
		slots.remove_at(at)
	entry.slots = slots
	if not slots.is_empty():
		return
	_watched_nodes.erase(id)
	var node: Variant = entry.node
	if not is_instance_valid(node):
		return
	var callables: Array[Callable] = entry.callables
	var watched := node as Node3D
	if watched.tree_entered.is_connected(callables[0]):
		watched.tree_entered.disconnect(callables[0])
	if watched.tree_exiting.is_connected(callables[1]):
		watched.tree_exiting.disconnect(callables[1])
	if watched.visibility_changed.is_connected(callables[2]):
		watched.visibility_changed.disconnect(callables[2])

func _node_slots(id: int) -> PackedInt32Array:
	var entry: Dictionary = _watched_nodes.get(id, {})
	return entry.slots if not entry.is_empty() else PackedInt32Array()

func _on_node_entered(id: int) -> void:
	for slot: int in _node_slots(id):
		_refresh_anchor(slot)

func _on_node_exiting(id: int) -> void:
	for slot: int in _node_slots(id):
		_anchor_state[slot] = 0

func _on_node_visibility(id: int) -> void:
	for slot: int in _node_slots(id):
		if (_anchor_state[slot] & A_IN_WORLD) != 0:
			_refresh_anchor(slot)

## Nodes the layer follows (tests): one per node, however many anchors it carries.
func watched_node_count() -> int:
	return _watched_nodes.size()

func _anchor_moved(slot: int, point: Vector3) -> void:
	_anchor_points[slot] = point
	_anchor_frame[slot] = -1

# --- Per frame ---------------------------------------------------------------------

## The frame's placement (connected to RenderingServer.frame_pre_draw; tests
## call it directly).
func update_now() -> void:
	var started := Time.get_ticks_usec()
	_frame += 1
	items_drawn = 0
	rerecords_this_frame = 0
	rerecords_deferred = 0
	rs_calls_this_frame = 0
	rank_changes_this_frame = 0
	anchors_projected = 0
	last_record_usec = 0
	last_place_usec = 0
	last_apply_usec = 0
	if _holes > 0 and _holes * 4 >= _items.size():
		_compact()
	var camera: Camera3D = world_viewport.get_camera_3d() \
		if active and is_instance_valid(world_viewport) else null
	var visible_size := world_viewport.get_visible_rect().size if camera != null else Vector2.ZERO
	drawing = camera != null and camera.is_inside_tree() and is_visible_in_tree() \
		and visible_size.x > 0.0 and visible_size.y > 0.0
	_set_server_visible(drawing)
	if not drawing:
		_finish(started)
		return
	var now := now_usec()
	text_cache.now_usec_override = now_usec_override
	text_cache.begin_frame(shape_budget_usec)

	# Scale: design px -> world-view px -> canvas units -> device px.
	var view := _view_rect()
	var view_scale := view.size / visible_size
	var projection := camera.get_camera_projection()
	var orthographic := projection.w.w != 0.0
	_k = Style.OVERHEAD_PIXEL * (1.0 if orthographic else absf(projection.y.y)) \
		* visible_size.y * 0.5
	var sx := _k * view_scale.y
	_canvas_scale = sx
	var device := get_viewport().get_final_transform() * get_global_transform_with_canvas()
	var device_scale := absf(device.get_scale().y)
	if device_scale <= 0.0:
		device_scale = 1.0
	_device_scale = device_scale
	var device_origin := device.origin
	_update_oversampling(sx * device_scale, now)

	# Records (budgeted). A slot stays dirty while its text or builder waits.
	var count := _items.size()
	var record_started := Time.get_ticks_usec()
	if _dirty_pending:
		var record_open := true
		var still_dirty := false
		for slot: int in range(count):
			var dirty_flags := _flags[slot]
			if (dirty_flags & F_DIRTY) == 0:
				continue
			if (dirty_flags & (F_VISIBLE | F_ALPHA)) != (F_VISIBLE | F_ALPHA):
				# Hidden items are recorded when shown (_item_visible, _item_fade).
				continue
			if record_open:
				if _record(_items[slot] as Item, slot):
					rerecords_this_frame += 1
				else:
					still_dirty = true
				if Time.get_ticks_usec() - record_started >= rerecord_budget_usec:
					record_open = false
			else:
				rerecords_deferred += 1
				still_dirty = true
		_dirty_pending = still_dirty
	var place_started := Time.get_ticks_usec()
	last_record_usec = place_started - record_started

	# Camera, as Camera3D.unproject_position / is_position_behind read it.
	var camera_view := camera.get_camera_transform()
	var eye := camera_view.origin
	var camera_global := camera.global_transform
	var forward := -camera_global.basis.z.normalized()
	var camera_origin := camera_global.origin
	var near := camera.near
	var view_origin := view.position
	var width := visible_size.x
	var height := visible_size.y
	var cull := Rect2(Vector2.ZERO, size).grow(cull_margin)
	var frame := _frame
	_keys.resize(0)
	for slot: int in range(count):
		var flags := _flags[slot]
		if (flags & F_READY) != F_READY:
			if flags & F_SHOWN:
				_show(slot, false)
			continue
		var anchor := _anchor_of[slot]
		if anchor < 0:
			if flags & F_SHOWN:
				_show(slot, false)
			continue
		if _anchor_frame[anchor] != frame:
			_anchor_frame[anchor] = frame
			anchors_projected += 1
			var state := _anchor_state[anchor] & ~A_OK
			if state & A_IN_WORLD:
				var point := _anchor_nodes[anchor].to_global(_anchor_points[anchor])
				if forward.dot(point - camera_origin) >= near:
					var local: Vector3 = point * camera_view
					var clip: Vector4 = projection * Vector4(local.x, local.y, local.z, 1.0)
					if clip.w != 0.0:
						var inverse_w := 1.0 / clip.w
						_anchor_screen[anchor] = view_origin + Vector2(
							(clip.x * inverse_w * 0.5 + 0.5) * width,
							(-clip.y * inverse_w * 0.5 + 0.5) * height) * view_scale
						var distance := eye.distance_to(point)
						_anchor_distance[anchor] = distance
						_anchor_sort[anchor] = forward.dot(point - eye) if orthographic else distance
						state |= A_OK
			_anchor_state[anchor] = state
		var anchor_state := _anchor_state[anchor]
		if (anchor_state & A_OK) == 0 \
				or ((flags & F_FOLLOW_TREE) != 0 and (anchor_state & A_TREE_VISIBLE) == 0):
			if flags & F_SHOWN:
				_show(slot, false)
			continue
		if flags & F_RANGE:
			var limit := _range[slot] + (_range_margin[slot] if (flags & F_IN_RANGE) != 0
				else -_range_margin[slot])
			var inside := _anchor_distance[anchor] <= limit
			if inside != ((flags & F_IN_RANGE) != 0):
				flags ^= F_IN_RANGE
				_flags[slot] = flags
			if not inside:
				if flags & F_SHOWN:
					_show(slot, false)
				continue
		var item_scale := sx * _scales[slot]
		var lift := _offset[slot]
		if flags & F_PULSE:
			lift += (_items[slot] as Item)._apply_pulse(now)
		var origin: Vector2 = _anchor_screen[anchor] + lift * item_scale
		if snap_origins:
			origin = ((device_origin + origin * device_scale).round() - device_origin) / device_scale
		if not cull.intersects(Rect2(origin + _extent_position[slot] * item_scale,
				_extent_size[slot] * item_scale)):
			if flags & F_SHOWN:
				_show(slot, false)
			continue
		_next_origin[slot] = origin
		_next_scale[slot] = item_scale
		var depth_steps := clampi(int(_anchor_sort[anchor] * DEPTH_STEPS_PER_METRE), 0, DEPTH_SPAN - 1)
		_keys.append(((DEPTH_SPAN - 1 - depth_steps) << INDEX_BITS) | slot)
	var apply_started := Time.get_ticks_usec()
	last_place_usec = apply_started - place_started

	# Far to near: the farthest draws first, within every pass.
	_keys.sort()
	var rank := 0
	var per_banner := order_mode == Style.ORDER_PER_BANNER
	for key: int in _keys:
		var slot := key & INDEX_MASK
		var flags := _flags[slot]
		if (flags & F_SHOWN) == 0:
			_show(slot, true)
		# PER_BANNER: an item without content has no root yet, so nothing to send.
		var root: RID = _slot_roots[slot] if per_banner else RID()
		var rooted := per_banner and root.is_valid()
		if _rank[slot] != rank:
			_rank[slot] = rank
			rank_changes_this_frame += 1
			if per_banner:
				if rooted:
					RenderingServer.canvas_item_set_draw_index(root, rank)
					rs_calls_this_frame += 1
			else:
				var rids: Array[RID] = _slot_rids[slot]
				for rid: RID in rids:
					RenderingServer.canvas_item_set_draw_index(rid, rank)
				rs_calls_this_frame += rids.size()
		var origin := _next_origin[slot]
		var item_scale := _next_scale[slot]
		if origin != _origin[slot] or item_scale != _applied_scale[slot]:
			_origin[slot] = origin
			_applied_scale[slot] = item_scale
			var placed := Transform2D(0.0, Vector2(item_scale, item_scale), 0.0, origin)
			if per_banner:
				if rooted:
					RenderingServer.canvas_item_set_transform(root, placed)
					rs_calls_this_frame += 1
			else:
				var rids: Array[RID] = _slot_rids[slot]
				for rid: RID in rids:
					RenderingServer.canvas_item_set_transform(rid, placed)
				rs_calls_this_frame += rids.size()
		var alpha := _alpha[slot]
		if alpha != _applied_alpha[slot] or (flags & F_MODULATE) != 0:
			_apply_modulate(slot, alpha, per_banner)
		rank += 1
	items_drawn = rank
	last_apply_usec = Time.get_ticks_usec() - apply_started
	text_cache.sweep()
	_finish(started)

func _finish(started: int) -> void:
	last_update_usec = Time.get_ticks_usec() - started
	frames_updated += 1
	update_usec_total += last_update_usec
	rerecords_total += rerecords_this_frame

func _view_rect() -> Rect2:
	if not is_instance_valid(view_control) or not view_control.is_inside_tree():
		return Rect2(Vector2.ZERO, size)
	var to_layer := get_global_transform_with_canvas().affine_inverse() \
		* view_control.get_global_transform_with_canvas()
	return Rect2(to_layer.origin, view_control.size * to_layer.get_scale())

## Text is rasterised at the native pixels per design pixel, to 1/16. A new
## scale is adopted at once the first time and after it has held for
## scale_settle_usec otherwise; adopting it re-records every text item.
func _update_oversampling(native_per_design: float, now: int) -> void:
	var quantised := maxf(Style.OVERSAMPLING_STEP,
		snappedf(native_per_design, Style.OVERSAMPLING_STEP))
	if _oversampling > 0.0 and is_equal_approx(quantised, _oversampling):
		_pending_oversampling = 0.0
		return
	if _oversampling > 0.0:
		if not is_equal_approx(quantised, _pending_oversampling):
			_pending_oversampling = quantised
			_pending_since_usec = now
			return
		if now - _pending_since_usec < scale_settle_usec:
			return
	_oversampling = quantised
	_pending_oversampling = 0.0
	for slot: int in range(_flags.size()):
		if _flags[slot] & F_HAS_TEXT:
			_flags[slot] = _flags[slot] | F_DIRTY
			_dirty_pending = true

func _set_server_visible(value: bool) -> void:
	if _server_visible == value:
		return
	_server_visible = value
	if _content_root.is_valid():
		RenderingServer.canvas_item_set_visible(_content_root, value)
		rs_calls_this_frame += 1

## The content root, created on first use with the current server visibility.
func _root_canvas_item() -> RID:
	if not _content_root.is_valid():
		_content_root = RenderingServer.canvas_item_create()
		RenderingServer.canvas_item_set_parent(_content_root, get_canvas_item())
		rs_calls_this_frame += 2
		if not _server_visible:
			RenderingServer.canvas_item_set_visible(_content_root, false)
			rs_calls_this_frame += 1
	return _content_root

func _show(slot: int, value: bool) -> void:
	_set_flag(slot, F_SHOWN, value)
	if order_mode == Style.ORDER_PER_BANNER:
		var root: RID = _slot_roots[slot]
		if root.is_valid():
			RenderingServer.canvas_item_set_visible(root, value)
			rs_calls_this_frame += 1
	else:
		var rids: Array[RID] = _slot_rids[slot]
		for rid: RID in rids:
			RenderingServer.canvas_item_set_visible(rid, value)
		rs_calls_this_frame += rids.size()
	if not value:
		_rank[slot] = -1

func _apply_modulate(slot: int, alpha: float, per_banner: bool) -> void:
	_applied_alpha[slot] = alpha
	_flags[slot] = _flags[slot] & ~F_MODULATE
	var item: Item = _items[slot]
	if per_banner:
		var root: RID = _slot_roots[slot]
		if not root.is_valid():
			return
		RenderingServer.canvas_item_set_modulate(root, Color(1.0, 1.0, 1.0, alpha))
		rs_calls_this_frame += 1
		for key: int in item._rids.keys():
			RenderingServer.canvas_item_set_modulate(item._rids[key],
				item.pass_modulate(Style.PASSES[key >> GROUP_BITS]))
			rs_calls_this_frame += 1
		return
	for key: int in item._rids.keys():
		var tint := item.pass_modulate(Style.PASSES[key >> GROUP_BITS])
		RenderingServer.canvas_item_set_modulate(item._rids[key],
			Color(tint.r, tint.g, tint.b, tint.a * alpha))
		rs_calls_this_frame += 1

# --- Recording ---------------------------------------------------------------------

## Re-records one item's canvas items from its operations. False (and the old
## recording kept) while its builder or any of its text is not ready.
func _record(item: Item, slot: int) -> bool:
	if item._built_revision != item._build_revision:
		if item.builder.is_valid() and not bool(item.builder.call(item, text_cache)):
			return false
		item._built_revision = item._build_revision
	var ops: Array = item._ops
	var entries: Array = []
	for op: Array in ops:
		if int(op[0]) == Item.OP_TEXT:
			var text_entry: TextCache.Entry = text_cache.entry(str(op[4]), int(op[5]),
				int(op[6]), int(op[7]))
			if not text_cache.shape(text_entry):
				return false
			entries.append(text_entry)
	for text_entry: TextCache.Entry in entries:
		text_cache.acquire(text_entry)
	for text_entry: TextCache.Entry in item._entries:
		text_cache.release(text_entry)
	item._entries = entries
	for rid: RID in item._rid_list:
		RenderingServer.canvas_item_clear(rid)
	rs_calls_this_frame += item._rid_list.size()
	var extent := Rect2()
	var bounded := false
	var entry_index := 0
	# A scaled item (the pointer) is drawn at its scale times the layer's, so its
	# glyphs are rasterised at that size too, not minified from the layer's.
	var raster := _oversampling
	var item_scale := _scales[slot]
	if item_scale != 1.0 and item_scale > 0.0:
		raster = maxf(Style.OVERSAMPLING_STEP, snappedf(_oversampling * item_scale,
			Style.OVERSAMPLING_STEP))
	# Canvas items this recording draws into; the others are freed below.
	var used: Dictionary = {}
	for op: Array in ops:
		var kind := int(op[0])
		var group := 0
		if batch_groups:
			if kind == Item.OP_TEXT:
				group = clampi(int(op[5]), 1, TEXTURE_GROUP_BASE - 1)
			elif kind == Item.OP_TEXTURE_RECT:
				group = _texture_group(op[3] as Texture2D)
		var rid := _rid_for(item, slot, int(op[1]), group)
		used[rid] = true
		if kind == Item.OP_RECT:
			var rect: Rect2 = op[2]
			RenderingServer.canvas_item_add_rect(rid, rect, op[3])
			rs_calls_this_frame += 1
			extent = rect if not bounded else extent.merge(rect)
			bounded = true
		elif kind == Item.OP_TEXTURE_RECT:
			var rect: Rect2 = op[2]
			# Texture2D.draw_rect, not the texture's RID: an AtlasTexture's RID
			# is its whole atlas, and only draw_rect draws its region.
			(op[3] as Texture2D).draw_rect(rid, rect, false, op[4])
			rs_calls_this_frame += 1
			extent = rect if not bounded else extent.merge(rect)
			bounded = true
		elif kind == Item.OP_TEXT:
			var text_entry: TextCache.Entry = entries[entry_index]
			entry_index += 1
			var at: Vector2 = op[2]
			var top_left := at - Vector2(
				text_entry.box_width * _alignment_fraction(int(op[7])),
				text_entry.size.y * _alignment_fraction(int(op[8])))
			var outline_size := int(op[9])
			if outline_size > 0:
				var outline_rid := _rid_for(item, slot, int(op[11]), group)
				used[outline_rid] = true
				text_entry.draw_outline(outline_rid, top_left, outline_size, op[10], raster)
				rs_calls_this_frame += 1
			text_entry.draw(rid, top_left, op[3], raster)
			rs_calls_this_frame += 1
			var box := Rect2(top_left, Vector2(text_entry.box_width, text_entry.size.y)) \
				.grow(float(outline_size))
			extent = box if not bounded else extent.merge(box)
			bounded = true
	if used.size() < item._rid_list.size():
		_free_unused(item, used)
	_extent_position[slot] = extent.position
	_extent_size[slot] = extent.size
	var flags := (_flags[slot] | F_RECORDED) & ~(F_DIRTY | F_HAS_TEXT)
	if not entries.is_empty():
		flags |= F_HAS_TEXT
	_flags[slot] = flags
	item._dirty_sent = false
	return true

## Frees the item's canvas items that the last recording left empty (a status
## icon or a text size the item no longer shows), so an item does not collect
## one empty canvas item per icon kind it has ever shown, each still moved,
## shown and ranked every frame. `_rid_list` is shared with `_slot_rids`, so
## it is edited in place.
func _free_unused(item: Item, used: Dictionary) -> void:
	for key: int in item._rids.keys():
		var rid: RID = item._rids[key]
		if used.has(rid):
			continue
		item._rids.erase(key)
		item._rid_list.erase(rid)
		RenderingServer.free_rid(rid)
		rs_calls_this_frame += 1

static func _alignment_fraction(alignment: int) -> float:
	# HORIZONTAL_ALIGNMENT_LEFT/CENTER/RIGHT and VERTICAL_ALIGNMENT_TOP/
	# CENTER/BOTTOM share the values 0/1/2; FILL is laid out as CENTER.
	match alignment:
		0:
			return 0.0
		2:
			return 1.0
		_:
			return 0.5

## Key of a pass and batch group: draw order (pass first, then group).
static func _group_key(pass_id: int, group: int) -> int:
	return (Style.pass_index(pass_id) << GROUP_BITS) | group

func _texture_group(texture: Texture2D) -> int:
	var id := texture.get_rid().get_id()
	var found: Variant = _texture_groups.get(id)
	if found != null:
		return int(found)
	var group := mini(TEXTURE_GROUP_BASE + _texture_groups.size(), (1 << GROUP_BITS) - 1)
	_texture_groups[id] = group
	return group

## The item's canvas item for a pass and batch group, created (hidden) on
## first use; the item is then placed, ranked and tinted afresh on its next
## placement.
func _rid_for(item: Item, slot: int, pass_id: int, group := 0) -> RID:
	var key := _group_key(pass_id, group)
	var existing: RID = item._rids.get(key, RID())
	if existing.is_valid():
		return existing
	var rid := RenderingServer.canvas_item_create()
	rs_calls_this_frame += 1
	if order_mode == Style.ORDER_PER_BANNER:
		if not item._root.is_valid():
			if not _banner_parent.is_valid():
				_banner_parent = RenderingServer.canvas_item_create()
				RenderingServer.canvas_item_set_parent(_banner_parent, _root_canvas_item())
				rs_calls_this_frame += 2
			item._root = RenderingServer.canvas_item_create()
			RenderingServer.canvas_item_set_parent(item._root, _banner_parent)
			RenderingServer.canvas_item_set_visible(item._root, false)
			rs_calls_this_frame += 3
			_slot_roots[slot] = item._root
		RenderingServer.canvas_item_set_parent(rid, item._root)
		RenderingServer.canvas_item_set_draw_index(rid, key)
		rs_calls_this_frame += 2
	else:
		RenderingServer.canvas_item_set_parent(rid, _group_parent(pass_id, group))
		RenderingServer.canvas_item_set_visible(rid, false)
		rs_calls_this_frame += 2
	if _flags[slot] & F_SHOWN:
		_show(slot, false)
	item._rids[key] = rid
	item._rid_list.append(rid)
	_rank[slot] = -1
	_origin[slot] = Vector2(INF, INF)
	_applied_scale[slot] = -1.0
	_applied_alpha[slot] = -1.0
	return rid

func _pass_parent(pass_id: int) -> RID:
	var existing: RID = _pass_parents.get(pass_id, RID())
	if existing.is_valid():
		return existing
	var rid := RenderingServer.canvas_item_create()
	RenderingServer.canvas_item_set_parent(rid, _root_canvas_item())
	var position_index := Style.pass_index(pass_id)
	RenderingServer.canvas_item_set_draw_index(rid, position_index)
	rs_calls_this_frame += 3
	_pass_parents[pass_id] = rid
	_pass_draw_index[pass_id] = position_index
	return rid

## A pass's sub-parent for one batch group, ordered by group inside the pass.
func _group_parent(pass_id: int, group: int) -> RID:
	var key := _group_key(pass_id, group)
	var existing: RID = _group_parents.get(key, RID())
	if existing.is_valid():
		return existing
	var rid := RenderingServer.canvas_item_create()
	RenderingServer.canvas_item_set_parent(rid, _pass_parent(pass_id))
	RenderingServer.canvas_item_set_draw_index(rid, group)
	rs_calls_this_frame += 3
	_group_parents[key] = rid
	return rid

## Batch groups that exist in a pass, in draw order (tests).
func pass_groups(pass_id: int) -> Array[int]:
	var groups: Array[int] = []
	for key: int in _group_parents.keys():
		if key >> GROUP_BITS == Style.pass_index(pass_id):
			groups.append(key & ((1 << GROUP_BITS) - 1))
	groups.sort()
	return groups

## Frees the item's canvas items, lets go of its text and its anchor.
func _release_item(item: Item, release_anchor: bool) -> void:
	for rid: RID in item._rid_list:
		RenderingServer.free_rid(rid)
	if item._root.is_valid():
		RenderingServer.free_rid(item._root)
	if text_cache != null:
		for text_entry: TextCache.Entry in item._entries:
			text_cache.release(text_entry)
	if release_anchor:
		_release_anchor(item.anchor)
	item._entries = []
	item._rids = {}
	item._rid_list = []
	item._root = RID()
	item._layer = null
	item._index = -1
	item._dirty_sent = false
	item._built_revision = 0

## Drops removed slots, keeping registration order (the sort's tie-break).
func _compact() -> void:
	var keep := PackedInt32Array()
	for slot: int in range(_items.size()):
		if _items[slot] != null:
			keep.append(slot)
	var items: Array = []
	var slot_rids: Array = []
	var slot_roots: Array[RID] = []
	for new_slot: int in range(keep.size()):
		var old := keep[new_slot]
		var item: Item = _items[old]
		item._index = new_slot
		items.append(item)
		slot_rids.append(_slot_rids[old])
		slot_roots.append(_slot_roots[old])
	_items = items
	_slot_rids = slot_rids
	_slot_roots = slot_roots
	_flags = _pick_int(_flags, keep)
	_anchor_of = _pick_int(_anchor_of, keep)
	_rank = _pick_int(_rank, keep)
	_alpha = _pick_float(_alpha, keep)
	_scales = _pick_float(_scales, keep)
	_range = _pick_float(_range, keep)
	_range_margin = _pick_float(_range_margin, keep)
	_applied_scale = _pick_float(_applied_scale, keep)
	_applied_alpha = _pick_float(_applied_alpha, keep)
	_next_scale = _pick_float(_next_scale, keep)
	_offset = _pick_vector(_offset, keep)
	_extent_position = _pick_vector(_extent_position, keep)
	_extent_size = _pick_vector(_extent_size, keep)
	_origin = _pick_vector(_origin, keep)
	_next_origin = _pick_vector(_next_origin, keep)
	_holes = 0

static func _pick_int(source: PackedInt32Array, keep: PackedInt32Array) -> PackedInt32Array:
	var result := PackedInt32Array()
	result.resize(keep.size())
	for index: int in range(keep.size()):
		result[index] = source[keep[index]]
	return result

static func _pick_float(source: PackedFloat64Array, keep: PackedInt32Array) -> PackedFloat64Array:
	var result := PackedFloat64Array()
	result.resize(keep.size())
	for index: int in range(keep.size()):
		result[index] = source[keep[index]]
	return result

static func _pick_vector(source: PackedVector2Array, keep: PackedInt32Array) -> PackedVector2Array:
	var result := PackedVector2Array()
	result.resize(keep.size())
	for index: int in range(keep.size()):
		result[index] = source[keep[index]]
	return result
