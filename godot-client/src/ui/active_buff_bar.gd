extends Control
## The strip of effects currently on the player.
##
## The server states which buffs are active and for how long: `GET_ACTIVE_SPELL`
## carries the buff id and its duration, `GET_ACTIVE_SPELL_LIST` restates the
## whole set on resync, and `REMOVE_ACTIVE_SPELL` takes one away. The reducer
## turns each duration into the moment it ends, and this counts down to that
## moment - the same thing the quick-slot cooldown art does with the duration
## the server states for an item.
##
## An entry whose stated time has run out is dropped here rather than waiting
## for a packet, because the server already said when it ends; nothing else
## about a buff is decided locally.
##
## Names and icons come from the client's spell catalog, which is where the
## spell names and sigil art already live. The server sends buff ids and no
## labels, so the labels are presentation, not state.

const ICON_SIZE := Vector2(28.0, 28.0)
const BOTTOM_BAR_GAP := 10.0

var catalog: SpellCatalog
var row: HBoxContainer
var bottom_hud: Control

var _entries: Dictionary = {}

func _ready() -> void:
	name = "ActiveBuffBar"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	row = HBoxContainer.new()
	row.name = "ActiveBuffRow"
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_theme_constant_override("separation", 8)
	add_child(row)
	row.resized.connect(_layout)
	if bottom_hud != null:
		bottom_hud.item_rect_changed.connect(_layout)
	AppState.state_changed.connect(_on_state_changed)
	sync()
	_layout()

func _layout() -> void:
	if bottom_hud != null:
		# Both controls share the HUD canvas, so resizing and UI scaling keep
		# the effects just above the bottom bar.
		position = Vector2(12.0, bottom_hud.position.y - row.size.y - BOTTOM_BAR_GAP)

func configure(spell_catalog: SpellCatalog) -> void:
	catalog = spell_catalog
	sync()

## The buff ids on screen, in the order they are drawn.
func shown_buff_ids() -> Array[int]:
	var ids: Array[int] = []
	for child: Node in row.get_children():
		ids.append(int((child as Control).get_meta("buff_id", -1)))
	return ids

func _on_state_changed(path: StringName) -> void:
	if path == &"spells" or path == &"connection":
		sync()

func _process(_delta: float) -> void:
	if _entries.is_empty():
		return
	sync()

func sync() -> void:
	var now: int = Time.get_ticks_msec()
	var active: Array[int] = []
	for raw_id: Variant in AppState.active_spells:
		var buff_id: int = int(raw_id)
		var entry: Dictionary = AppState.active_spells[raw_id] as Dictionary
		var end_msec: int = int(entry.get("end_msec", 0))
		# A resync list states which buffs are on without restating how long
		# they last; those have no end to count down to and simply stay.
		if end_msec > 0 and end_msec <= now:
			continue
		active.append(buff_id)
	active.sort()
	if active != shown_buff_ids():
		_rebuild(active)
	for child: Node in row.get_children():
		var chip: Control = child as Control
		var end_msec: int = int(chip.get_meta("end_msec", 0))
		var label: Label = chip.get_node("BuffRemaining") as Label
		label.text = ("%ds" % maxi(0, int(ceilf(float(end_msec - now) / 1000.0)))
			if end_msec > 0 else "")

func _rebuild(active: Array[int]) -> void:
	_entries.clear()
	for child: Node in row.get_children():
		row.remove_child(child)
		child.queue_free()
	for buff_id: int in active:
		var entry: Dictionary = AppState.active_spells[buff_id] as Dictionary
		var definition: Dictionary = (catalog.buff(buff_id) if catalog != null
			else {})
		var label_text: String = str(definition.get("name",
			"Effect %d" % buff_id))
		var chip := VBoxContainer.new()
		chip.name = "Buff_%d" % buff_id
		chip.mouse_filter = Control.MOUSE_FILTER_IGNORE
		chip.set_meta("buff_id", buff_id)
		chip.set_meta("end_msec", int(entry.get("end_msec", 0)))
		chip.tooltip_text = label_text
		var icon := TextureRect.new()
		icon.name = "BuffIcon"
		icon.custom_minimum_size = ICON_SIZE
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		if catalog != null:
			icon.texture = catalog.buff_icon(buff_id)
		chip.add_child(icon)
		var caption := Label.new()
		caption.name = "BuffName"
		caption.text = label_text.trim_suffix(" Ward")
		caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		caption.add_theme_font_size_override("font_size", 11)
		chip.add_child(caption)
		var remaining := Label.new()
		remaining.name = "BuffRemaining"
		remaining.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		remaining.add_theme_font_size_override("font_size", 11)
		chip.add_child(remaining)
		row.add_child(chip)
		_entries[buff_id] = chip
