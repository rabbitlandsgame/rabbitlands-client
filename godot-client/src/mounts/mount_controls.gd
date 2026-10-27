extends PanelContainer
## A compact status row inside the local character's resource banner.
signal display_changed

# Retain the saved show_banner key so existing visibility preferences survive.
const OPTION_LABELS := {
	"show_banner": "Show mount status below character bars",
	"status": "Show trot / gallop and calling status",
	"endurance": "Show available gallop time",
}
var options: Dictionary = default_options()
var status := Label.new()

func _init() -> void:
	# Own the label even if this helper is freed before entering the tree.
	add_child(status)

func _ready() -> void:
	name = "MountStatus"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	status.add_theme_font_size_override("font_size", 11)
	status.add_theme_color_override("font_color", Color.WHITE)
	status.add_theme_color_override("font_outline_color", Color.BLACK)
	status.add_theme_constant_override("outline_size", 4)
	status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	status.mouse_filter = Control.MOUSE_FILTER_IGNORE
	tooltip_text = "Gallop time available before returning to trot. Recharges while trotting. Right-click to change the display."
	AppState.state_changed.connect(_changed)
	_refresh()

static func default_options() -> Dictionary:
	var defaults := {}
	for key: String in OPTION_LABELS:
		defaults[key] = true
	return defaults

func set_options(values: Dictionary) -> void:
	for key: String in OPTION_LABELS:
		options[key] = bool(values.get(key, true))
	_refresh()

func wants_banner() -> bool:
	return visible

func _changed(section: StringName) -> void:
	if section in [&"mount_states", &"mount_deltas", &"mount_countdowns", &"map", &"authentication", &"local_actor"]:
		_refresh()

func _refresh() -> void:
	var state: Dictionary = AppState.actor_mounts.get(AppState.local_actor_id, {})
	var mode: String = state.get("mode", "on_foot")
	var details: Array[String] = []
	if mode == "summoning" and options.status:
		details.append("Calling… %.1fs" % (float(state.get("summon_remaining_ms", 0)) / 1000.0))
	elif mode == "mounted":
		var galloping: bool = state.get("gait", "cruise") == "burst"
		if options.status:
			details.append("Gallop" if galloping else "Trot")
		if options.endurance:
			var seconds := maxf(0.0, float(state.get("endurance_ms", 0)) / 1000.0)
			if galloping:
				details.append("%.1fs left" % seconds)
			else:
				# A riding delta states the gallop's own maximum; a complete
				# table does not, and its gallop holds 8 s.
				var full: float = float(state.get("endurance_max_ms", 8000)) / 1000.0
				details.append("Gallop ready" if seconds >= full else "Gallop %.1fs" % seconds)
	var text := " · ".join(details)
	var shown := AppState.authenticated and bool(options.show_banner) and not text.is_empty()
	var changed := status.text != text or visible != shown
	status.text = text
	visible = shown
	if changed:
		reset_size()
		display_changed.emit()
