extends CanvasLayer
## The loading screen between signing in (or a far arrival) and the first frame
## the player's character stands on loaded ground: black, the Rabbit Lands logo
## and a short progress bar. main.gd raises it, reports the arrival's progress
## (ContinentChunkStream.arrival_progress) and lowers it once the character is
## spawned and grounded; the world is built behind it, never in front of the
## player. The new-character intro has its own curtain (layer 120) above this.

const LOGO := preload("res://assets/branding/rabbitlands-logo.png")
const LAYER := 115
const FADE_SECONDS := 0.35
## The bar eases toward the reported value, so one large cell arriving reads as
## motion rather than a jump, and never moves backwards.
const EASE_PER_SECOND := 3.0
const BACKGROUND := Color(0.0, 0.0, 0.0, 1.0)
const BAR_FILL := Color(0.86, 0.68, 0.36, 1.0)
const BAR_TRACK := Color(0.16, 0.14, 0.12, 1.0)
const TEXT_COLOUR := Color(0.88, 0.82, 0.7, 1.0)

var _root: Control
var _logo: TextureRect
var _bar: ProgressBar
var _label: Label
var _target := 0.0
var _shown := 0.0
var _began_msec := 0
var _drawn_frames := 0
var _fading := false
var _tween: Tween

func _ready() -> void:
	name = "ArrivalCurtain"
	layer = LAYER
	_root = Control.new()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	# Swallows clicks meant for the world while it is up.
	_root.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_root)
	var background := ColorRect.new()
	background.color = BACKGROUND
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(background)
	var centre := CenterContainer.new()
	centre.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	centre.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(centre)
	var column := VBoxContainer.new()
	column.alignment = BoxContainer.ALIGNMENT_CENTER
	column.add_theme_constant_override("separation", 22)
	column.mouse_filter = Control.MOUSE_FILTER_IGNORE
	centre.add_child(column)
	_logo = TextureRect.new()
	_logo.texture = LOGO
	_logo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_logo.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_logo.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.add_child(_logo)
	_bar = ProgressBar.new()
	_bar.min_value = 0.0
	_bar.max_value = 1.0
	_bar.step = 0.0
	_bar.show_percentage = false
	_bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var fill := StyleBoxFlat.new()
	fill.bg_color = BAR_FILL
	fill.set_corner_radius_all(3)
	var track := StyleBoxFlat.new()
	track.bg_color = BAR_TRACK
	track.set_corner_radius_all(3)
	_bar.add_theme_stylebox_override("fill", fill)
	_bar.add_theme_stylebox_override("background", track)
	column.add_child(_bar)
	_label = Label.new()
	_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_label.add_theme_color_override("font_color", TEXT_COLOUR)
	_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.add_child(_label)
	get_viewport().size_changed.connect(_fit)
	_fit()
	visible = false

## Sizes the logo and bar to the window: about 40 % of its width, never larger
## than the logo's own pixels.
func _fit() -> void:
	if _logo == null:
		return
	var size := get_viewport().get_visible_rect().size
	var width := clampf(size.x * 0.4, 240.0, float(LOGO.get_width()))
	width = minf(width, size.y * 0.55 * float(LOGO.get_width()) / float(LOGO.get_height()))
	_logo.custom_minimum_size = Vector2(width, width * float(LOGO.get_height()) / float(LOGO.get_width()))
	_bar.custom_minimum_size = Vector2(width * 0.8, 8.0)

func begin(text: String) -> void:
	if _tween != null:
		_tween.kill()
		_tween = null
	_fading = false
	if not visible:
		_target = 0.0
		_shown = 0.0
		_began_msec = Time.get_ticks_msec()
		_drawn_frames = 0
	_root.modulate.a = 1.0
	_label.text = text
	_bar.value = _shown
	visible = true

func set_text(text: String) -> void:
	_label.text = text

func set_progress(value: float) -> void:
	_target = maxf(_target, clampf(value, 0.0, 1.0))

## Fills the bar and fades out; input is released as the fade starts.
func finish() -> void:
	if not visible or _fading:
		return
	_fading = true
	_target = 1.0
	_shown = 1.0
	_bar.value = 1.0
	_tween = create_tween()
	_tween.tween_property(_root, "modulate:a", 0.0, FADE_SECONDS)
	_tween.tween_callback(_hidden)

func cancel() -> void:
	if _tween != null:
		_tween.kill()
		_tween = null
	_hidden()

func _hidden() -> void:
	visible = false
	_fading = false
	_tween = null

func is_showing() -> bool:
	return visible and not _fading

func blocks_input() -> bool:
	return is_showing()

## True once the curtain has been on screen for a couple of drawn frames, so a
## synchronous build started now happens behind it.
func has_drawn() -> bool:
	return visible and _drawn_frames >= 2

func elapsed_msec() -> int:
	return Time.get_ticks_msec() - _began_msec if visible else 0

func progress() -> float:
	return _shown

func _process(delta: float) -> void:
	if not visible:
		return
	_drawn_frames += 1
	if _shown < _target:
		_shown = minf(_target, _shown + delta * EASE_PER_SECOND * maxf(0.15, _target - _shown))
		_bar.value = _shown
