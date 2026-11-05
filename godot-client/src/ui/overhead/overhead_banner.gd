class_name OverheadBanner
extends RefCounted
## An actor's overhead banner as 2D overhead-layer content (wave 2 OV-2).
##
## Today ReplicatedActor3D draws its banner as Label3D and billboard quads on
## render layer 20: the name and guild tag, title, occupation, health bar and
## numbers, the translucent backing, status icons, the boss tag, the quest
## "!", the speech line, and (combat_target_marker_3d.gd) the target pointer.
## This model holds the same state and produces the same layout as five
## OverheadItems for the 2D layer (src/ui/overhead/overhead_layer.gd):
##
## - Block: backing, health bar and fill, status icons, name, guild tag,
##   title, occupation and health numbers. Visible while shown(); faded with
##   the banner (set_fade), so a fade never re-records.
## - Boss: the BOSS / MINIBOSS tag. It ignores crowding and the name setting
##   but is faded; it hangs at its own height (see set_boss_rank).
## - Quest: the quest-offer "!". It ignores crowding and the name setting, is
##   hidden at fade 0 and otherwise not faded, and pulses by formula
##   (OverheadItem.set_pulse) instead of a looping Tween per quest giver.
## - Speech: the speech line. It ignores fade and crowding.
## - Pointer: the combat target "▼" (the ground ring stays 3D).
## Everything is hidden while the actor is not drawn (set_drawn) and, through
## the layer, while the actor node is hidden in the tree.
##
## Not wired in stage B: OV-3 makes the actor's overhead setters write here
## instead of into nodes. Each setter below is named after, and keeps the
## rules of, the actor setter that forwards to it (tests/test_overhead_banner_parity.gd
## drives both from the same states and compares every part). Layout is a
## line-for-line port of ReplicatedActor3D._layout_overhead,
## _layout_status_effects and _sync_nameplate_text, in design pixels
## (OverheadStyle), y down, relative to the anchor's projected point: a
## Label3D `offset / RASTER_SCALE` and a QuadMesh `center_offset /
## OVERHEAD_PIXEL`, with y flipped.
##
## Text widths for layout are measured as the 3D banner measures them: at the
## Label3D raster size (MEASURE_SCALE times the font size) and divided back, so
## the backing, the guild split and the health row keep today's sizes to the
## float. The layer then shapes and rasterises each text at its own size.
##
## part(name) answers in today's node names (&"Nameplate", &"HealthBarFill",
## &"StatusIcons/poison", ...) for tests and diagnostics; it is not a per-frame
## call. Main thread only, like the actor.

const Style := preload("res://src/ui/overhead/overhead_style.gd")
const Item := preload("res://src/ui/overhead/overhead_item.gd")
const TextColors := preload("res://src/ui/text_colors.gd")
const StatusIcons := preload("res://src/ui/status_effect_icons.gd")
const TargetMarkerStyle := preload("res://src/actors/target_marker_style.gd")

## Part names: the node names ReplicatedActor3D and CombatTargetMarker use today.
const NAMEPLATE := &"Nameplate"
const GUILD_TAG := &"GuildTag"
const TITLE_LINE := &"TitleLine"
const OCCUPATION_LINE := &"OccupationLine"
const HEALTH_NUMBERS := &"HealthNumbers"
const HEALTH_BAR_BACKGROUND := &"HealthBarBackground"
const HEALTH_BAR_FILL := &"HealthBarFill"
const OVERHEAD_BACKGROUND := &"OverheadBackground"
const STATUS_ICONS := &"StatusIcons"
const QUEST_MARKER := &"QuestOfferMarker"
const SPEECH_BUBBLE := &"SpeechBubble"
const BOSS_RANK := &"BossRank"
const POINTER := &"Pointer"
## Every fixed part (status icons add "StatusIcons/<effect>" per icon).
const PARTS: Array[StringName] = [NAMEPLATE, GUILD_TAG, TITLE_LINE, OCCUPATION_LINE,
	HEALTH_NUMBERS, HEALTH_BAR_BACKGROUND, HEALTH_BAR_FILL, OVERHEAD_BACKGROUND,
	STATUS_ICONS, QUEST_MARKER, SPEECH_BUBBLE, BOSS_RANK, POINTER]

## Item names.
const ITEM_BLOCK := &"Block"
const ITEM_BOSS := &"Boss"
const ITEM_QUEST := &"Quest"
const ITEM_SPEECH := &"Speech"
const ITEM_POINTER := &"Pointer"

## The Label3D raster factor of world_label_style.gd (RASTER_SCALE): text is
## measured at this multiple of its size and divided back, as today.
const MEASURE_SCALE := 4
## Widths remembered per size and text (main.gd keeps the same kind of table
## for declutter); emptied when it grows past this.
const WIDTH_CACHE_LIMIT := 4096

## ReplicatedActor3D.NAMEPLATE_HEIGHT and CREATURE_ACTOR_KIND.
const NAMEPLATE_HEIGHT := 2.15
const CREATURE_ACTOR_KIND := 5

## Boss tag (replicated_actor_3d.gd set_boss_rank): 16 px, 2 px black
## outline, 26 design pixels over its anchor.
const BOSS_FONT_SIZE := 16
const BOSS_OUTLINE_SIZE := 2
const BOSS_RISE := 26.0
const BOSS_COLOUR := Color("ffd166")
const MINIBOSS_COLOUR := Color("ff9c66")
const QUEST_TEXT := "!"
## combat_target_marker_3d.gd's pointer: text, colours, and its 48-point
## glyph and 6-point outline at 100 % triangle size and thickness.
const POINTER_TEXT := "▼"
const POINTER_COLOUR := Color("ff755f")
const POINTER_BORDER := Color.BLACK
## The health bar's backing (bar plus its border) and a status icon, in design pixels.
const BAR_BACK_SIZE := Vector2(Style.HEALTH_BAR_WIDTH + Style.HEALTH_BAR_BORDER,
	Style.HEALTH_BAR_THICKNESS + Style.HEALTH_BAR_BORDER)
const ICON_SIZE := Vector2(Style.NEGATIVE_STATUS_SIZE, Style.NEGATIVE_STATUS_SIZE)

static var _widths: Dictionary = {}
static var _health_gradient: GradientTexture2D

var _block: Item
var _boss: Item
var _quest: Item
var _speech: Item
var _pointer: Item
var _layer: Object = null
## Ops per item, by the part each came from (tests and diagnostics).
var _sources: Dictionary = {}

# State, mirroring ReplicatedActor3D's overhead fields.
var _name_info: Dictionary = {}
var _is_creature := false
var _title := ""
var _occupation := ""
var _health_current := -1
var _health_maximum := -1
var _health_shown := false
var _overhead_visible := true
var _banner_names := true
var _banner_health_bar := true
var _banner_health_numbers := true
var _banner_status_icons := true
var _banner_background := true
var _fade := 1.0
var _crowded := false
var _drawn := true
var _crowd_hidden := false
var _status_effects: Array[String] = []
var _boss_rank := 0
var _quest_available := false
var _quest_start_usec := 0
var _quest_colour := Color.WHITE
var _speech_shown := false
var _speech_text := ""
var _speech_base := Color.WHITE
var _pointer_enabled := false
var _pointer_font_size := Style.POINTER_FONT_SIZE
var _pointer_outline_size := Style.POINTER_OUTLINE_SIZE
var _pointer_colour := POINTER_COLOUR
## Anchor heights (actor-local metres): the block's (with the quest and
## speech), the boss tag's and the pointer's.
var _height := NAMEPLATE_HEIGHT
var _boss_height := NAMEPLATE_HEIGHT
var _pointer_height := NAMEPLATE_HEIGHT

## "StatusIcons/<effect>" for each current effect (part names, op sources).
var _icon_names: Array[StringName] = []

var _content_revision := 1
var _layout_revision := 0
var _layout_parts: Dictionary = {}
var _metrics_cache: Metrics
## Block builds so far (diagnostics: a fade or crowding change must not build).
var builds := 0

func _init() -> void:
	_metrics_cache = Metrics.new()
	_block = Item.new(null, Vector3.ZERO, ITEM_BLOCK)
	_block.builder = _build_block
	_boss = Item.new(null, Vector3.ZERO, ITEM_BOSS)
	_quest = Item.new(null, Vector3.ZERO, ITEM_QUEST)
	_speech = Item.new(null, Vector3.ZERO, ITEM_SPEECH)
	_pointer = Item.new(null, Vector3.ZERO, ITEM_POINTER)
	_pointer.scale = Style.design_scale(Style.POINTER_PIXEL)
	_write_pointer()
	_sync()

# --- Static helpers (ports of ReplicatedActor3D's) ------------------------------

## The name fields of an actor packet (ReplicatedActor3D._name_info).
static func name_info(dto: Dictionary) -> Dictionary:
	var result := {}
	for field: String in ["name", "kind", "name_colour", "guild_tag", "guild_colour", "enhanced", "map_type"]:
		if dto.has(field):
			result[field] = dto[field]
	return result

## ReplicatedActor3D.name_color_role.
static func name_colour_role(info: Dictionary) -> String:
	var kind := int(info.get("kind", 0))
	if kind == 2:
		return "world_npc"
	if kind == 4 or (kind == 5 and bool(info.get("enhanced", false))):
		return "world_pk"
	if kind == CREATURE_ACTOR_KIND:
		return "world_creature"
	return "world_special_map" if int(info.get("map_type", 0)) == 2 else "world_player"

## ReplicatedActor3D._nameplate_colour: the server's colour unless the player
## overrode the role.
static func name_colour(info: Dictionary) -> Color:
	var role := name_colour_role(info)
	var index: int = int(info.get("name_colour", 0))
	if index > 0 and not TextColors.is_overridden(role):
		return EloriaProtocol.el_text_colour(index)
	return TextColors.color(role)

## ReplicatedActor3D.guild_tag_color.
static func guild_tag_colour(info: Dictionary) -> Color:
	var index := int(info.get("guild_colour", 0))
	return (EloriaProtocol.el_text_colour(index) if index > 0 and not TextColors.is_overridden("world_guild")
		else TextColors.color("world_guild"))

## ReplicatedActor3D._health_colour.
static func health_colour(ratio: float) -> Color:
	var fraction := clampf(ratio, 0.0, 1.0)
	return Color(clampf((1.0 - fraction) * 2.0, 0.0, 1.0),
		clampf(fraction / 1.25 * 2.0, 0.0, 1.0), 0.0)

## The bar fill's shading, built as ReplicatedActor3D._health_bar_texture
## builds it (OV-3 makes the actor return this one).
static func health_bar_texture() -> GradientTexture2D:
	if _health_gradient == null:
		_health_gradient = GradientTexture2D.new()
		_health_gradient.width = 1
		_health_gradient.height = 16
		_health_gradient.fill_from = Vector2.ZERO
		_health_gradient.fill_to = Vector2(0.0, 1.0)
		_health_gradient.gradient = Gradient.new()
		_health_gradient.gradient.colors = PackedColorArray([
			Color.WHITE, Color(0.45, 0.45, 0.45)])
	return _health_gradient

## A text's width in design pixels as the 3D banner's layout measures it.
static func text_width(text: String, font_size: int) -> float:
	var key := "%d|%s" % [font_size, text]
	var found: Variant = _widths.get(key)
	if found != null:
		return found
	if _widths.size() >= WIDTH_CACHE_LIMIT:
		_widths.clear()
	var width: float = Style.font().get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1,
		font_size * MEASURE_SCALE).x / float(MEASURE_SCALE)
	_widths[key] = width
	return width

## The pointer's glyph and outline sizes for a target-marker style (normalised
## or not), as CombatTargetMarker.configure sizes its Label3D.
static func pointer_style(appearance: Dictionary) -> Dictionary:
	var style := TargetMarkerStyle.normalise(appearance)
	return {"font_size": roundi(48.0 * float(style.triangle_size) / 100.0),
		"outline_size": maxi(1, roundi(6.0 * float(style.triangle_size) / 100.0
			* float(style.triangle_thickness) / 100.0)),
		"colour": style.triangle_color as Color}

# --- Producer setters (OV-3: ReplicatedActor3D forwards each one) -------------------

## Hang the items from `node` (the actor). Call once before register().
func attach(node: Node3D) -> void:
	_block.attach(node, Vector3(0.0, _height, 0.0))
	_quest.share_anchor(_block)
	_speech.share_anchor(_block)
	_boss.attach(node, Vector3(0.0, _boss_height, 0.0))
	_pointer.attach(node, Vector3(0.0, _pointer_height, 0.0))
	_sync()

## Draw through `layer` (an OverheadLayer whose accepts(node) holds: the actor
## is in the game world, not a preview or portrait world). Items join the layer
## when they are first shown, so an actor that never speaks, offers a quest or
## is targeted costs the layer one item.
func register(target_layer: Object) -> void:
	if target_layer == _layer:
		return
	unregister()
	_layer = target_layer
	_sync()

func unregister() -> void:
	for candidate: Item in items():
		var current: Object = candidate.layer()
		if current != null:
			current.call("remove_item", candidate)
	_layer = null

func layer() -> Object:
	return _layer if is_instance_valid(_layer) else null

## configure(): which role colours the name and whether death hides the block.
func set_creature(value: bool) -> void:
	if value == _is_creature:
		return
	_is_creature = value
	_sync()

## _add_nameplate and the name refresh in apply_server_state (name_info(dto)).
func set_name_info(info: Dictionary) -> void:
	if info == _name_info:
		return
	_name_info = info.duplicate()
	_content_changed()

func set_title(title: String) -> void:
	if title == _title:
		return
	_title = title
	_content_changed()

## The occupation without brackets; "" takes the line off.
func set_occupation(value: String) -> void:
	var text := value.strip_edges()
	if text == _occupation:
		return
	_occupation = text
	_content_changed()

## apply_vitals' overhead half.
func set_vitals(current: int, maximum: int) -> void:
	if current == _health_current and maximum == _health_maximum:
		return
	_health_current = current
	_health_maximum = maximum
	_content_changed()

func set_health_visible(enabled: bool) -> void:
	if enabled == _health_shown:
		return
	_health_shown = enabled
	_content_changed()

func set_nameplate_visible(enabled: bool) -> void:
	if enabled == _overhead_visible:
		return
	_overhead_visible = enabled
	_sync()

## set_banner_parts: names, health_bar, health_numbers, status_icons, background.
func set_banner_parts(options: Dictionary) -> void:
	var names := bool(options.get("names", true))
	var health_bar := bool(options.get("health_bar", true))
	var health_numbers := bool(options.get("health_numbers", true))
	var status_icons := bool(options.get("status_icons", true))
	var background := bool(options.get("background", true))
	if names == _banner_names and health_bar == _banner_health_bar \
			and health_numbers == _banner_health_numbers and status_icons == _banner_status_icons \
			and background == _banner_background:
		return
	_banner_names = names
	_banner_health_bar = health_bar
	_banner_health_numbers = health_numbers
	_banner_status_icons = status_icons
	_banner_background = background
	_content_changed()

## set_overhead_fade: block and boss alpha, without a re-record.
func set_fade(value: float) -> void:
	var next := clampf(value, 0.0, 1.0)
	if next == _fade:
		return
	_fade = next
	_sync()

## set_overhead_crowded (declutter).
func set_crowded(value: bool) -> void:
	if value == _crowded:
		return
	_crowded = value
	_sync()

func set_drawn(enabled: bool) -> void:
	if enabled == _drawn:
		return
	_drawn = enabled
	_sync()

func set_crowd_hidden(hidden: bool) -> void:
	if hidden == _crowd_hidden:
		return
	_crowd_hidden = hidden
	_sync()

## set_status_effects: any effect list; unknown names are dropped and the
## icons keep StatusEffectIcons' stable order.
func set_status_effects(effects: Array) -> void:
	var next: Array[String] = StatusIcons.known(effects)
	if next == _status_effects:
		return
	_status_effects = next
	_icon_names.clear()
	for effect: String in next:
		_icon_names.append(StringName("%s/%s" % [STATUS_ICONS, effect]))
	_content_changed()

## set_boss_rank. `height` is where the actor puts the tag when the rank
## changes: banner_head_height() + NAMEPLATE_CLEARANCE; lift() moves it with
## the block afterwards, as _lift_overhead moves the BossRank label.
func set_boss_rank(value: int, height: float) -> void:
	var rank := clampi(value, 0, 2)
	if rank == _boss_rank:
		return
	_boss_rank = rank
	_set_boss_height(height)
	_layout_revision = 0
	_boss.clear()
	if rank > 0:
		_boss.add_text(_boss_text(), BOSS_FONT_SIZE, Vector2(0.0, -BOSS_RISE), _boss_colour(),
			BOSS_OUTLINE_SIZE, Color.BLACK)
	_sources[ITEM_BOSS] = [BOSS_RANK] if rank > 0 else []
	_sync()

## set_quest_available. The pulse starts at `now_usec` (the layer's clock,
## Time.get_ticks_usec when -1), as the Tween starts when the marker appears.
func set_quest_available(available: bool, now_usec := -1) -> void:
	if available == _quest_available:
		return
	_quest_available = available
	if available:
		_start_quest(now_usec)
	else:
		_quest.clear_pulse()
		_quest.clear()
		_sources[ITEM_QUEST] = []
		_layout_revision = 0
	_sync()

## show_speech_bubble (the actor keeps the expiry and calls clear_speech()).
func show_speech(text: String, colour := Color.WHITE) -> void:
	_speech_base = colour
	_speech_text = text
	_speech_shown = true
	_write_speech()
	_sync()

func clear_speech() -> void:
	if not _speech_shown:
		return
	_speech_shown = false
	_sync()

## _lift_overhead: one height for the block, the quest mark, the speech line
## and the boss tag.
func lift(height: float) -> void:
	if height != _height:
		_height = height
		_block.set_anchor_point(Vector3(0.0, height, 0.0))
		_layout_revision = 0
	_set_boss_height(height)

## _sync_combat_target_marker: CombatTargetMarker.configure(enabled,
## footprint, head_height, appearance). The pointer hangs 0.75 m over the head.
func set_pointer(enabled: bool, head_height: float, appearance: Dictionary = {}) -> void:
	if head_height + Style.POINTER_LIFT != _pointer_height:
		_pointer_height = head_height + Style.POINTER_LIFT
		_pointer.set_anchor_point(Vector3(0.0, _pointer_height, 0.0))
		_layout_revision = 0
	var style := pointer_style(appearance)
	if int(style.font_size) != _pointer_font_size or int(style.outline_size) != _pointer_outline_size \
			or (style.colour as Color) != _pointer_colour:
		_pointer_font_size = int(style.font_size)
		_pointer_outline_size = int(style.outline_size)
		_pointer_colour = style.colour
		_write_pointer()
	if enabled != _pointer_enabled:
		_pointer_enabled = enabled
		_sync()

## TextColors changed (ReplicatedActor3D._on_text_colors_changed).
func refresh_colours(role := "") -> void:
	if not role.is_empty() and not role.begins_with("world_"):
		return
	_content_changed()
	if _speech_shown or not _speech_text.is_empty():
		_write_speech()
	if _quest_available:
		# The actor restarts the marker's Tween with the new colour.
		_start_quest(-1)

# --- Queries ---------------------------------------------------------------------

## ReplicatedActor3D._overhead_shown: whether the block is drawn at all.
func shown() -> bool:
	return _overhead_visible and not _crowded and _fade > 0.0 and _drawn \
		and not _crowd_hidden and not (_is_creature and _health_current == 0)

func crowded() -> bool:
	return _crowded

func fade() -> float:
	return _fade

func occupation() -> String:
	return _occupation

func status_effect_count() -> int:
	return _status_effects.size() if _health_current > 0 else 0

## When the quest mark's pulse started (layer clock), for its phase.
func quest_start_usec() -> int:
	return _quest_start_usec

## How far below the name the health row sits (ReplicatedActor3D.health_drop).
func health_drop() -> float:
	return Style.HEALTH_BAR_DROP + (Style.OCCUPATION_DROP if not _occupation.is_empty() else 0.0) \
		if _banner_names else 0.0

func items() -> Array[Item]:
	return [_block, _boss, _quest, _speech, _pointer]

func item(item_name: StringName) -> Item:
	for candidate: Item in items():
		if candidate.name == item_name:
			return candidate
	return null

## The part each of an item's current ops came from, in op order.
func op_sources(item_name: StringName) -> Array[StringName]:
	var found: Array[StringName] = []
	found.assign(_sources.get(item_name, []))
	return found

## Rebuilds the block now (tests and diagnostics; the layer builds it lazily
## when it records the item).
func build_now() -> void:
	_build_block(_block, null)

## Every part name currently defined, fixed parts first, then the icons.
func part_names() -> Array[StringName]:
	var names: Array[StringName] = PARTS.duplicate()
	names.append_array(_icon_names)
	return names

## One part as drawn now, in design pixels (y down, relative to its anchor):
## visible, text, colour and outline_colour (alpha includes the fade), alpha,
## offset (the centre: Label3D's alignment point, a quad's centre), size,
## font_size and outline_size (design pixels), wrap_width, anchor (actor-local
## point), texture, item, and for &"StatusIcons" `icons` and `count`.
## Unknown names return {}.
func part(part_name: StringName) -> Dictionary:
	var parts := _layout()
	if not parts.has(part_name):
		return {}
	var source: Dictionary = parts[part_name]
	var item_name: StringName = source.item
	var visible := bool(source.content)
	var faded := false
	match item_name:
		ITEM_BLOCK:
			visible = visible and _block.visible
			faded = true
		ITEM_BOSS:
			visible = visible and _boss.visible
			faded = true
		ITEM_QUEST:
			visible = visible and _quest.visible
		ITEM_SPEECH:
			visible = visible and _speech.visible
		ITEM_POINTER:
			visible = visible and _pointer.visible
	var colour: Color = source.colour
	var outline: Color = source.outline_colour
	if faded:
		colour.a *= _fade
		outline.a *= _fade
	var scale: float = source.get("scale", 1.0)
	var result := {"visible": visible, "text": source.get("text", ""), "colour": colour,
		"outline_colour": outline, "alpha": colour.a, "offset": source.centre,
		"size": source.size, "font_size": float(source.get("font_size", 0)) * scale,
		"outline_size": float(source.get("outline_size", 0)) * scale,
		"wrap_width": float(source.get("wrap", 0)) * scale, "anchor": source.anchor,
		"texture": source.get("texture"), "item": item_name}
	if part_name == STATUS_ICONS:
		result.icons = _status_effects.duplicate()
		result.count = status_effect_count()
	if str(source.kind) == "text" and result.size == Vector2.ZERO:
		result.size = _text_size(str(result.text), int(source.font_size), int(source.get("wrap", 0)),
			scale, bool(source.get("raster", true)))
	return result

# --- Layout ----------------------------------------------------------------------

## The block's numbers (design pixels, y down) and colours: a line-for-line
## port of _sync_nameplate_text, _layout_overhead and _layout_status_effects.
## Shared by the builder (every content change) and part() (diagnostics), and
## recomputed only when content changes.
class Metrics extends RefCounted:
	var revision := -1
	var names := true
	var name_text := ""
	var tag_text := ""
	var name_width := 0.0
	var tag_width := 0.0
	var plate_colour := Color.WHITE
	var guild_colour := Color.WHITE
	var title_colour := Color.WHITE
	var occupied := false
	var occupation_text := ""
	var occupation_colour := Color.WHITE
	var drop := 0.0
	var health_row := false
	var numbers_text := ""
	var numbers_colour := Color.WHITE
	var numbers_x := 0.0
	var bar_center := 0.0
	var fill_width := 0.0
	var fill_colour := Color.WHITE
	var has_health := false
	var backing := false
	var backing_centre := Vector2.ZERO
	var backing_size := Vector2.ZERO
	var icons := false
	var rise := 0.0

func _metrics() -> Metrics:
	var m := _metrics_cache
	if m.revision == _content_revision:
		return m
	m.revision = _content_revision
	var names := _banner_names
	m.names = names
	m.name_text = str(_name_info.get("name", "Unknown actor"))
	var tag := str(_name_info.get("guild_tag", ""))
	m.tag_text = "  [%s]" % tag if not tag.is_empty() else ""
	m.name_width = text_width(m.name_text, Style.NAMEPLATE_FONT_SIZE)
	m.tag_width = text_width(m.tag_text, Style.NAMEPLATE_FONT_SIZE) if not m.tag_text.is_empty() else 0.0
	m.plate_colour = name_colour(_name_info)
	m.guild_colour = guild_tag_colour(_name_info)
	m.title_colour = TextColors.color("world_title")
	m.occupied = names and not _occupation.is_empty()
	m.occupation_text = "<%s>" % _occupation if not _occupation.is_empty() else ""
	m.occupation_colour = TextColors.color("world_occupation")
	# _layout_overhead.
	var name_width := m.name_width + m.tag_width if names else 0.0
	if m.occupied:
		name_width = maxf(name_width, text_width(m.occupation_text, Style.OCCUPATION_FONT_SIZE))
	m.drop = health_drop()
	var has_maximum := _health_maximum > 0
	var clamped := clampi(_health_current, 0, _health_maximum) if has_maximum else 0
	var ratio := float(clamped) / float(_health_maximum) if has_maximum else 0.0
	m.numbers_text = "%d/%d" % [clamped, _health_maximum] if has_maximum else ""
	# The full pair is reserved so a digit boundary does not slide the bar.
	var number_width := maxf(text_width(m.numbers_text, Style.HEALTH_NUMBER_FONT_SIZE),
		text_width("%d/%d" % [_health_maximum, _health_maximum], Style.HEALTH_NUMBER_FONT_SIZE))
	var row_width := (Style.HEALTH_BAR_WIDTH if _banner_health_bar else 0.0) \
		+ (number_width if _banner_health_numbers else 0.0) \
		+ (Style.HEALTH_NUMBER_GAP if _banner_health_bar and _banner_health_numbers else 0.0)
	m.bar_center = -(Style.HEALTH_NUMBER_GAP + number_width) * 0.5 if _banner_health_numbers else 0.0
	m.numbers_x = (Style.HEALTH_BAR_WIDTH + Style.HEALTH_NUMBER_GAP) * 0.5 if _banner_health_bar else 0.0
	m.health_row = _health_shown and has_maximum
	m.numbers_colour = TextColors.color("world_health") if TextColors.is_overridden("world_health") \
		else health_colour(ratio)
	# The fill drains from the right: its left edge stays on the bar's.
	m.fill_width = Style.HEALTH_BAR_WIDTH * ratio
	m.fill_colour = health_colour(ratio)
	m.has_health = m.health_row and (_banner_health_bar or _banner_health_numbers)
	var bottom := m.drop + 8.0 if m.has_health else 10.0 + (Style.OCCUPATION_DROP if m.occupied else 0.0)
	m.backing = _banner_background and (names or m.has_health)
	m.backing_centre = Vector2(0.0, -(10.0 - bottom) * 0.5)
	m.backing_size = Vector2(maxf(name_width, row_width if m.has_health else 0.0) + 8.0, 10.0 + bottom)
	# _layout_status_effects: rows of six above the name, a title's height
	# higher when a title is drawn.
	m.icons = _banner_status_icons and status_effect_count() > 0
	m.rise = Style.NEGATIVE_STATUS_RISE + (Style.TITLE_RISE if names and not _title.is_empty() else 0.0)
	return m

## The centre of status icon `index` (design pixels, y down).
func _icon_centre(index: int, rise: float) -> Vector2:
	var pitch := Style.NEGATIVE_STATUS_SIZE + Style.NEGATIVE_STATUS_GAP
	var row: int = index / StatusIcons.COLUMNS
	var columns := mini(StatusIcons.COLUMNS, _status_effects.size() - row * StatusIcons.COLUMNS)
	return Vector2((index % StatusIcons.COLUMNS - (columns - 1) * 0.5) * pitch, -(rise + row * pitch))

## Every part's geometry and base colour (no fade, no visibility rules beyond
## the content's own), for part(). Built from _metrics().
func _layout() -> Dictionary:
	if _layout_revision == _content_revision:
		return _layout_parts
	var m := _metrics()
	var parts: Dictionary = {}
	var block_anchor := Vector3(0.0, _height, 0.0)
	parts[NAMEPLATE] = _text_part(ITEM_BLOCK, m.names, m.name_text, Style.NAMEPLATE_FONT_SIZE, 0,
		Vector2(-m.tag_width * 0.5, 0.0), m.plate_colour, Color(0.0, 0.0, 0.0, m.plate_colour.a),
		block_anchor)
	parts[GUILD_TAG] = _text_part(ITEM_BLOCK, m.names and not m.tag_text.is_empty(), m.tag_text,
		Style.NAMEPLATE_FONT_SIZE, 0, Vector2(m.name_width * 0.5, 0.0), m.guild_colour,
		Color(0.0, 0.0, 0.0, m.guild_colour.a), block_anchor)
	parts[TITLE_LINE] = _text_part(ITEM_BLOCK, m.names and not _title.is_empty(), _title,
		Style.TITLE_FONT_SIZE, Style.OVERHEAD_OUTLINE_SIZE, Vector2(0.0, -Style.TITLE_RISE),
		m.title_colour, Color(0.0, 0.0, 0.0, m.title_colour.a), block_anchor)
	parts[OCCUPATION_LINE] = _text_part(ITEM_BLOCK, m.occupied, m.occupation_text,
		Style.OCCUPATION_FONT_SIZE, 0, Vector2(0.0, Style.OCCUPATION_DROP), m.occupation_colour,
		Color(0.0, 0.0, 0.0, m.occupation_colour.a), block_anchor)
	parts[HEALTH_NUMBERS] = _text_part(ITEM_BLOCK, m.health_row and _banner_health_numbers, m.numbers_text,
		Style.HEALTH_NUMBER_FONT_SIZE, 0, Vector2(m.numbers_x, m.drop), m.numbers_colour,
		Color(0.0, 0.0, 0.0, m.numbers_colour.a), block_anchor)
	parts[HEALTH_BAR_BACKGROUND] = _rect_part(m.health_row and _banner_health_bar,
		Vector2(m.bar_center, m.drop), BAR_BACK_SIZE, Style.HEALTH_BAR_BACKING, block_anchor, null)
	parts[HEALTH_BAR_FILL] = _rect_part(m.health_row and _banner_health_bar and _health_current > 0,
		Vector2(m.bar_center - (Style.HEALTH_BAR_WIDTH - m.fill_width) * 0.5, m.drop),
		Vector2(m.fill_width, Style.HEALTH_BAR_THICKNESS), m.fill_colour, block_anchor,
		health_bar_texture())
	parts[OVERHEAD_BACKGROUND] = _rect_part(m.backing, m.backing_centre, m.backing_size,
		Style.OVERHEAD_BACKING, block_anchor, null)
	parts[STATUS_ICONS] = {"item": ITEM_BLOCK, "kind": "group", "content": m.icons,
		"colour": Color.WHITE, "outline_colour": Color.WHITE, "centre": Vector2.ZERO,
		"size": Vector2.ZERO, "anchor": block_anchor}
	for index: int in range(_status_effects.size()):
		parts[_icon_names[index]] = _rect_part(m.icons, _icon_centre(index, m.rise), ICON_SIZE,
			Color.WHITE, block_anchor, StatusIcons.TEXTURES[_status_effects[index]])
	# The separate items.
	parts[BOSS_RANK] = _text_part(ITEM_BOSS, _boss_rank > 0, _boss_text(), BOSS_FONT_SIZE,
		BOSS_OUTLINE_SIZE, Vector2(0.0, -BOSS_RISE), _boss_colour(), Color.BLACK,
		Vector3(0.0, _boss_height, 0.0))
	parts[QUEST_MARKER] = _text_part(ITEM_QUEST, _quest_available, QUEST_TEXT if _quest_available else "",
		Style.QUEST_FONT_SIZE, Style.QUEST_OUTLINE_SIZE, Vector2(0.0, -Style.QUEST_RISE_FROM),
		_quest_colour, Style.QUEST_OUTLINE, block_anchor)
	var speech := _text_part(ITEM_SPEECH, _speech_shown, _speech_text, Style.SPEECH_BUBBLE_FONT_SIZE,
		Style.SPEECH_OUTLINE_SIZE, Vector2(0.0, -Style.SPEECH_BUBBLE_RISE), _speech_colour(),
		Style.SPEECH_BUBBLE_SURROUND, block_anchor)
	speech.wrap = int(Style.SPEECH_BUBBLE_WIDTH)
	parts[SPEECH_BUBBLE] = speech
	var pointer := _text_part(ITEM_POINTER, true, POINTER_TEXT, _pointer_font_size,
		_pointer_outline_size, Vector2.ZERO, _pointer_colour, POINTER_BORDER,
		Vector3(0.0, _pointer_height, 0.0))
	pointer.scale = Style.design_scale(Style.POINTER_PIXEL)
	pointer.raster = false
	parts[POINTER] = pointer
	_layout_parts = parts
	_layout_revision = _content_revision
	return parts

static func _text_part(item_name: StringName, content: bool, text: String, font_size: int,
		outline_size: int, centre: Vector2, colour: Color, outline_colour: Color,
		anchor: Vector3) -> Dictionary:
	# Visible as the label would be, even for an empty text (which draws nothing).
	return {"item": item_name, "kind": "text", "content": content,
		"text": text, "font_size": font_size, "outline_size": outline_size, "wrap": 0,
		"centre": centre, "size": Vector2.ZERO, "colour": colour, "outline_colour": outline_colour,
		"anchor": anchor}

static func _rect_part(content: bool, centre: Vector2, size: Vector2, colour: Color,
		anchor: Vector3, texture: Texture2D) -> Dictionary:
	return {"item": ITEM_BLOCK, "kind": "texture" if texture != null else "rect",
		"content": content, "centre": centre, "size": size, "colour": colour,
		"outline_colour": colour, "anchor": anchor, "texture": texture}

## A text's size in design pixels: the Label3D-raster measure for overhead
## text (raster), the glyph's own size times its scale for the pointer.
static func _text_size(text: String, font_size: int, wrap: int, scale: float, raster: bool) -> Vector2:
	var font := Style.font()
	var factor := float(MEASURE_SCALE) if raster else 1.0
	var size_px := roundi(font_size * factor)
	var measured: Vector2
	if wrap > 0:
		measured = font.get_multiline_string_size(text, HORIZONTAL_ALIGNMENT_CENTER,
			wrap * factor, size_px, -1, TextServer.BREAK_MANDATORY | TextServer.BREAK_WORD_BOUND
				| TextServer.BREAK_ADAPTIVE)
	else:
		measured = Vector2(font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size_px).x,
			font.get_height(size_px))
	return measured / factor * scale

func _boss_text() -> String:
	return "BOSS" if _boss_rank == 2 else ("MINIBOSS" if _boss_rank == 1 else "")

func _boss_colour() -> Color:
	return BOSS_COLOUR if _boss_rank == 2 else MINIBOSS_COLOUR

func _speech_colour() -> Color:
	return TextColors.color("world_speech") if TextColors.is_overridden("world_speech") else _speech_base

# --- Items -----------------------------------------------------------------------

func _content_changed() -> void:
	_content_revision += 1
	_block.invalidate()
	_sync()

func _set_boss_height(height: float) -> void:
	if height == _boss_height:
		return
	_boss_height = height
	_boss.set_anchor_point(Vector3(0.0, height, 0.0))
	_layout_revision = 0

## Item visibility and fade from the state, and lazy layer membership.
func _sync() -> void:
	_block.visible = shown()
	_block.fade = _fade
	_boss.visible = _drawn and not _crowd_hidden and _fade > 0.0 and _boss_rank > 0
	_boss.fade = _fade
	_quest.visible = _drawn and not _crowd_hidden and _fade > 0.0 and _quest_available
	_speech.visible = _speech_shown and _drawn
	_pointer.visible = _pointer_enabled and _drawn
	if not is_instance_valid(_layer):
		return
	for candidate: Item in items():
		if candidate.visible and candidate.layer() == null and candidate.anchor != null:
			_layer.call("add_item", candidate)

## Writes the block's operations from _metrics() (OverheadItem.builder: the
## layer calls it when it next records the block, so a burst of setters builds
## once, and only for a banner that is drawn). part() describes the same
## parts from the same metrics; tests/test_overhead_banner_parity.gd checks
## every operation against its part in every state.
func _build_block(target: Item, _cache: Variant) -> bool:
	var m := _metrics()
	builds += 1
	var sources: Array[StringName] = []
	target.clear()
	if m.backing:
		target.add_rect(Style.PASS_BACKING, Rect2(m.backing_centre - m.backing_size * 0.5, m.backing_size),
			Style.OVERHEAD_BACKING)
		sources.append(OVERHEAD_BACKGROUND)
	if m.health_row and _banner_health_bar:
		var bar_left := m.bar_center - Style.HEALTH_BAR_WIDTH * 0.5
		target.add_rect(Style.PASS_BAR_BACK, Rect2(Vector2(m.bar_center, m.drop) - BAR_BACK_SIZE * 0.5,
			BAR_BACK_SIZE), Style.HEALTH_BAR_BACKING)
		sources.append(HEALTH_BAR_BACKGROUND)
		if _health_current > 0:
			target.add_texture_rect(Style.PASS_BAR_FILL, Rect2(bar_left,
				m.drop - Style.HEALTH_BAR_THICKNESS * 0.5, m.fill_width, Style.HEALTH_BAR_THICKNESS),
				health_bar_texture(), m.fill_colour)
			sources.append(HEALTH_BAR_FILL)
	if m.icons:
		var half := ICON_SIZE * 0.5
		for index: int in range(_status_effects.size()):
			target.add_texture_rect(Style.PASS_ICONS, Rect2(_icon_centre(index, m.rise) - half, ICON_SIZE),
				StatusIcons.TEXTURES[_status_effects[index]], Color.WHITE)
			sources.append(_icon_names[index])
	if m.names:
		if not _title.is_empty():
			target.add_text(_title, Style.TITLE_FONT_SIZE, Vector2(0.0, -Style.TITLE_RISE), m.title_colour,
				Style.OVERHEAD_OUTLINE_SIZE, Color(0.0, 0.0, 0.0, m.title_colour.a))
			sources.append(TITLE_LINE)
		if m.tag_text.is_empty():
			if not m.name_text.is_empty():
				target.add_text(m.name_text, Style.NAMEPLATE_FONT_SIZE, Vector2.ZERO, m.plate_colour)
				sources.append(NAMEPLATE)
		else:
			# The name ends and the tag starts at one point, whatever widths the
			# 2D shaping gives them (the 3D labels centre each at its half).
			var split := Vector2((m.name_width - m.tag_width) * 0.5, 0.0)
			if not m.name_text.is_empty():
				target.add_text(m.name_text, Style.NAMEPLATE_FONT_SIZE, split, m.plate_colour, 0,
					Color.BLACK, 0, HORIZONTAL_ALIGNMENT_RIGHT)
				sources.append(NAMEPLATE)
			target.add_text(m.tag_text, Style.NAMEPLATE_FONT_SIZE, split, m.guild_colour, 0,
				Color.BLACK, 0, HORIZONTAL_ALIGNMENT_LEFT)
			sources.append(GUILD_TAG)
		if m.occupied:
			target.add_text(m.occupation_text, Style.OCCUPATION_FONT_SIZE, Vector2(0.0, Style.OCCUPATION_DROP),
				m.occupation_colour)
			sources.append(OCCUPATION_LINE)
	if m.health_row and _banner_health_numbers:
		target.add_text(m.numbers_text, Style.HEALTH_NUMBER_FONT_SIZE, Vector2(m.numbers_x, m.drop),
			m.numbers_colour)
		sources.append(HEALTH_NUMBERS)
	_sources[ITEM_BLOCK] = sources
	return true

func _start_quest(now_usec: int) -> void:
	_quest_colour = TextColors.color("world_quest")
	_quest_start_usec = now_usec if now_usec >= 0 else Time.get_ticks_usec()
	_quest.clear()
	_quest.add_text(QUEST_TEXT, Style.QUEST_FONT_SIZE, Vector2.ZERO, Color.WHITE,
		Style.QUEST_OUTLINE_SIZE, Style.QUEST_OUTLINE)
	_quest.set_pulse(_quest_start_usec, Style.QUEST_PULSE_HALF_SECONDS,
		Vector2(0.0, -Style.QUEST_RISE_FROM), Vector2(0.0, -Style.QUEST_RISE_TO),
		_quest_colour, _quest_colour.lightened(Style.QUEST_LIGHTEN))
	_sources[ITEM_QUEST] = [QUEST_MARKER]
	_layout_revision = 0

func _write_speech() -> void:
	_speech.clear()
	_speech.add_text(_speech_text, Style.SPEECH_BUBBLE_FONT_SIZE, Vector2(0.0, -Style.SPEECH_BUBBLE_RISE),
		_speech_colour(), Style.SPEECH_OUTLINE_SIZE, Style.SPEECH_BUBBLE_SURROUND,
		int(Style.SPEECH_BUBBLE_WIDTH))
	_sources[ITEM_SPEECH] = [SPEECH_BUBBLE] if not _speech_text.is_empty() else []
	_layout_revision = 0

func _write_pointer() -> void:
	_pointer.clear()
	_pointer.add_text(POINTER_TEXT, _pointer_font_size, Vector2.ZERO, _pointer_colour,
		_pointer_outline_size, POINTER_BORDER, 0, HORIZONTAL_ALIGNMENT_CENTER,
		VERTICAL_ALIGNMENT_CENTER, Style.PASS_BACKING, Style.PASS_POINTER_OUTLINE)
	_sources[ITEM_POINTER] = [POINTER]
	_layout_revision = 0
