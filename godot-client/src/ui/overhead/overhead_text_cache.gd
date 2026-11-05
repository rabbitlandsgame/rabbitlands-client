extends RefCounted
## Shaped text for the 2D overhead layer (wave 2 OV-1).
##
## Why a cache: `Font.draw_string` keeps its own shaped-text LRU, and that LRU
## thrashes somewhere between 50 and 160 distinct strings (design probe E: 160
## names drawn through it cost 1.61 ms against 0.38 ms from kept TextLines).
## Overhead text is a few hundred distinct names, numbers and titles, so the
## layer keeps one TextLine (one line) or TextParagraph (wrapped or several
## lines) per distinct text and draws from it.
##
## - Keyed `"size|wrap|alignment|text"` (key_for). The font is the cache's.
## - Reference-counted by what the layer currently has recorded; an entry
##   nobody holds is dropped after `idle_usec` (sweep).
## - Shaping is lazy and budgeted: `shape()` shapes an entry unless this
##   frame's budget is spent, and always lets the first one of a frame through,
##   so a burst of arrivals is spread over frames instead of one long frame
##   (probe F: ~14 us a name). `measure()` shapes at once, for layout code that
##   needs a width now; forced shapes count towards the frame's time.
## Main thread only, like every canvas item the layer records.

const Style := preload("res://src/ui/overhead/overhead_style.gd")

## Line breaking of wrapped text: Label3D's AUTOWRAP_WORD_SMART with its
## default `autowrap_trim_flags` (start and end edge spaces).
const WRAP_BREAK_FLAGS := TextServer.BREAK_MANDATORY | TextServer.BREAK_WORD_BOUND \
	| TextServer.BREAK_ADAPTIVE | TextServer.BREAK_TRIM_START_EDGE_SPACES \
	| TextServer.BREAK_TRIM_END_EDGE_SPACES

## One distinct text. `size` is the shaped block (widest line, total height);
## `box_width` is the width lines are aligned within: the wrap width when the
## text wraps, else the widest line. Draw positions are the block's top left.
class Entry extends RefCounted:
	var key := ""
	var text := ""
	var font_size := 0
	var wrap_width := 0
	var alignment := HORIZONTAL_ALIGNMENT_CENTER
	var line: TextLine
	var paragraph: TextParagraph
	var size := Vector2.ZERO
	var box_width := 0.0
	var shaped := false
	var refs := 0
	var idle_since_usec := 0

	func draw(canvas: RID, position: Vector2, colour: Color, oversampling: float) -> void:
		if line != null:
			line.draw(canvas, position, colour, oversampling)
		elif paragraph != null:
			paragraph.draw(canvas, position, colour, colour, oversampling)

	func draw_outline(canvas: RID, position: Vector2, outline_size: int, colour: Color,
			oversampling: float) -> void:
		if line != null:
			line.draw_outline(canvas, position, outline_size, colour, oversampling)
		elif paragraph != null:
			paragraph.draw_outline(canvas, position, outline_size, colour, colour, oversampling)

var font: Font
var budget_usec := Style.SHAPE_BUDGET_USEC
var idle_usec := Style.TEXT_IDLE_USEC
## Tests: a fixed clock in microseconds instead of Time.get_ticks_usec().
var now_usec_override := -1

var shaped_this_frame := 0
var shape_usec_this_frame := 0
var deferred_this_frame := 0
var shapes_total := 0
var forced_total := 0
var evictions_total := 0

var _entries: Dictionary = {}
## Entries nobody holds, by key: the only ones sweep() looks at.
var _idle: Dictionary = {}
var _budgeted_this_frame := 0
var _last_sweep_usec := 0

func _init(cache_font: Font = null) -> void:
	font = cache_font if cache_font != null else Style.font()

static func key_for(text: String, font_size: int, wrap_width := 0,
		alignment := HORIZONTAL_ALIGNMENT_CENTER) -> String:
	return "%d|%d|%d|%s" % [font_size, wrap_width, alignment, text]

func now_usec() -> int:
	return now_usec_override if now_usec_override >= 0 else Time.get_ticks_usec()

## The entry for this text, created unshaped (and idle) when new.
func entry(text: String, font_size: int, wrap_width := 0,
		alignment := HORIZONTAL_ALIGNMENT_CENTER) -> Entry:
	var key := key_for(text, font_size, wrap_width, alignment)
	var found: Entry = _entries.get(key)
	if found != null:
		return found
	var created := Entry.new()
	created.key = key
	created.text = text
	created.font_size = font_size
	created.wrap_width = maxi(0, wrap_width)
	created.alignment = alignment
	created.idle_since_usec = now_usec()
	_entries[key] = created
	_idle[key] = created
	return created

func has_entry(text: String, font_size: int, wrap_width := 0,
		alignment := HORIZONTAL_ALIGNMENT_CENTER) -> bool:
	return _entries.has(key_for(text, font_size, wrap_width, alignment))

func acquire(item: Entry) -> void:
	item.refs += 1
	if item.refs == 1:
		_idle.erase(item.key)

func release(item: Entry) -> void:
	item.refs -= 1
	if item.refs <= 0:
		item.refs = 0
		item.idle_since_usec = now_usec()
		if _entries.get(item.key) == item:
			_idle[item.key] = item

## Starts a frame's shaping budget (the layer calls it once per update).
func begin_frame(frame_budget_usec := -1) -> void:
	if frame_budget_usec >= 0:
		budget_usec = frame_budget_usec
	shaped_this_frame = 0
	shape_usec_this_frame = 0
	deferred_this_frame = 0
	_budgeted_this_frame = 0

## Shapes `item` unless this frame's budget is spent (the first budgeted shape
## of a frame always runs). `force` shapes regardless. True once shaped.
func shape(item: Entry, force := false) -> bool:
	if item.shaped:
		return true
	if not force and _budgeted_this_frame > 0 and shape_usec_this_frame >= budget_usec:
		deferred_this_frame += 1
		return false
	var started := Time.get_ticks_usec()
	_shape(item)
	shape_usec_this_frame += Time.get_ticks_usec() - started
	shaped_this_frame += 1
	shapes_total += 1
	if force:
		forced_total += 1
	else:
		_budgeted_this_frame += 1
	return true

## The shaped size of a text, shaping it now if needed (layout code).
func measure(text: String, font_size: int, wrap_width := 0,
		alignment := HORIZONTAL_ALIGNMENT_CENTER) -> Vector2:
	var item := entry(text, font_size, wrap_width, alignment)
	shape(item, true)
	return item.size

func _shape(item: Entry) -> void:
	if item.wrap_width <= 0 and not item.text.contains("\n"):
		var line := TextLine.new()
		line.add_string(item.text, font, item.font_size)
		item.line = line
		item.size = line.get_size()
		item.box_width = item.size.x
	else:
		var paragraph := TextParagraph.new()
		paragraph.alignment = item.alignment
		if item.wrap_width > 0:
			paragraph.break_flags = WRAP_BREAK_FLAGS
			paragraph.width = item.wrap_width
		else:
			paragraph.break_flags = TextServer.BREAK_MANDATORY
		paragraph.add_string(item.text, font, item.font_size)
		var widest := 0.0
		for index: int in range(paragraph.get_line_count()):
			widest = maxf(widest, paragraph.get_line_width(index))
		if item.wrap_width <= 0:
			# Lines are aligned within the paragraph's width; without a wrap
			# width that is the widest line, as Label3D aligns each line.
			paragraph.width = widest
		item.paragraph = paragraph
		item.size = Vector2(widest, paragraph.get_size().y)
		item.box_width = float(item.wrap_width) if item.wrap_width > 0 else widest
	item.shaped = true

## Drops entries nobody has held for `idle_usec`. Cheap to call every frame:
## it looks at the idle set at most twice a second.
func sweep(force := false) -> int:
	var now := now_usec()
	if not force and now - _last_sweep_usec < 500000:
		return 0
	_last_sweep_usec = now
	var dropped := 0
	for key: String in _idle.keys():
		var item: Entry = _idle[key]
		if item.refs <= 0 and now - item.idle_since_usec >= idle_usec:
			_idle.erase(key)
			_entries.erase(key)
			dropped += 1
	evictions_total += dropped
	return dropped

func clear() -> void:
	_entries.clear()
	_idle.clear()

func size() -> int:
	return _entries.size()

func idle_count() -> int:
	return _idle.size()

func stats() -> Dictionary:
	return {"entries": _entries.size(), "idle": _idle.size(),
		"shaped_this_frame": shaped_this_frame, "shape_usec_this_frame": shape_usec_this_frame,
		"deferred_this_frame": deferred_this_frame, "shapes_total": shapes_total,
		"forced_total": forced_total, "evictions_total": evictions_total,
		"budget_usec": budget_usec}
