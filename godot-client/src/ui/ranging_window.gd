extends Control
## The ranging window: this session's archery, counted shot by shot.
##
## The legacy client's Ranging window showed six read-only rows - total shots,
## successful hits, missed hits, the success and critical rates and the
## experience per arrow - and this client can count most of them honestly. A
## shot is one `missile_fired` event whose shooter is the local actor; a hit is
## one ranging experience award from `floating_feedback_requested`, because the
## server grants ranging experience exactly when an arrow lands. Misses and the
## two ratios are arithmetic on those counts. Nothing here is read back out of
## the server's statistics: the window is a session tally the client keeps for
## itself, and the server stays authoritative about what each shot actually did.
##
## The critical-rate row renders a plain "-". The server never says which hits
## were critical, and a written-out zero would be a claim about the world
## rather than an honest absence.
##
## Counting runs whether or not the panel is showing - a session stat that only
## counted while watched would lie - and the Reset button clears it. The legacy
## client reset these rows from a context menu; a button is this client's idiom.
##
## The script declares no `class_name`: a global class is parsed before the
## autoload singletons are registered, and this reads `AppState` directly.

const PANEL_SIZE := Vector2(300.0, 240.0)
## Nothing may cover the fixed resource rail down the right-hand edge.
const RESERVED_RIGHT_RAIL := 96.0

## The session tally. Counted here and nowhere else, so a reset is honest:
## it forgets what this window counted, not anything the server knows.
var shots: int = 0
var hits: int = 0
var ranging_exp: int = 0

var panel: PanelContainer
var total_label: Label
var hits_label: Label
var missed_label: Label
var success_label: Label
var critical_label: Label
var exp_label: Label

func _ready() -> void:
	name = "RangingLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	AppState.missile_fired.connect(_on_missile_fired)
	AppState.floating_feedback_requested.connect(_on_floating_feedback)
	sync()

func is_open() -> bool:
	return panel.visible

func toggle() -> void:
	panel.visible = not panel.visible
	if panel.visible:
		panel.move_to_front()
		sync()

func close() -> void:
	panel.hide()

## Back to a fresh session, by the player's own hand.
func reset() -> void:
	shots = 0
	hits = 0
	ranging_exp = 0
	sync()

## One arrow loosed by the local actor. Everyone else's arrows are theirs.
func _on_missile_fired(shot: Dictionary) -> void:
	var shooter: int = int(shot.get("source_actor_id", -1))
	if shooter < 0 or shooter != AppState.local_actor_id:
		return
	shots += 1
	sync()

## One arrow that landed: the server awards ranging experience per successful
## hit, so the award is the hit. A ranging level-up is not one.
func _on_floating_feedback(feedback: Dictionary) -> void:
	if str(feedback.get("kind", "")) != "experience" or bool(feedback.get("bonus", false)):
		return
	if str(feedback.get("skill", "")) != "ranging":
		return
	hits += 1
	ranging_exp += int(feedback.get("amount", 0))
	sync()

func sync() -> void:
	if not panel.visible:
		return
	var missed: int = maxi(shots - hits, 0)
	var rate: float = 0.0 if shots == 0 else float(hits) / float(shots) * 100.0
	var per_arrow: float = 0.0 if shots == 0 else float(ranging_exp) / float(shots)
	total_label.text = "Total shots %d" % shots
	hits_label.text = "Successful hits %d" % hits
	missed_label.text = "Missed hits %d" % missed
	success_label.text = "Success rate %.2f %%" % rate
	critical_label.text = "Critical rate -"
	exp_label.text = "Exp/arrows %.2f exp" % per_arrow

func _build() -> void:
	panel = PanelContainer.new()
	panel.name = "RangingWindow"
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.position = Vector2(24.0, 60.0)
	panel.custom_minimum_size = PANEL_SIZE
	panel.size = PANEL_SIZE
	panel.hide()
	add_child(panel)

	var column := VBoxContainer.new()
	column.name = "RangingBody"
	panel.add_child(column)
	var header := HBoxContainer.new()
	header.name = "RangingHeader"
	column.add_child(header)
	WindowDrag.attach(panel, header)
	var title := Label.new()
	title.name = "RangingTitle"
	title.text = "Ranging"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	header.add_child(title)
	var close_button := Button.new()
	close_button.name = "RangingClose"
	close_button.text = "X"
	close_button.pressed.connect(close)
	header.add_child(close_button)

	total_label = _row(column, "TotalShots")
	hits_label = _row(column, "SuccessfulHits")
	missed_label = _row(column, "MissedHits")
	success_label = _row(column, "SuccessRate")
	critical_label = _row(column, "CriticalRate")
	exp_label = _row(column, "ExpPerArrow")

	var reset_button := Button.new()
	reset_button.name = "RangingReset"
	reset_button.text = "Reset"
	reset_button.pressed.connect(reset)
	column.add_child(reset_button)

func _row(into: VBoxContainer, row_name: String) -> Label:
	var label := Label.new()
	label.name = row_name
	into.add_child(label)
	return label
