extends RefCounted
## Slot trim is separate from the floating bar's background and outer frame.
const Chrome := preload("res://src/ui/hud_panel_chrome.gd")

static func native_border_visible(config: Dictionary) -> bool:
	return config.get("slot_border_style", "match_hud") == "match_hud" and config.get("show_border", true)

static func apply(button: Button, config: Dictionary) -> void:
	var design: String = config.get("slot_border_style", "match_hud")
	var trim := button.get_node_or_null("_HudSlotTrim") as Node2D
	if design not in ["beveled", "ornate"]:
		if trim != null: trim.hide()
		return
	if trim == null:
		trim = Chrome.new()
		trim.name = "_HudSlotTrim"
		button.add_child(trim)
		trim.show_behind_parent = false
	trim.config = {"show_background":false, "show_border":true,
		"border_color":config.get("slot_border_color", Color("aa8d50")), "hud_border_style":design}
	trim.show()
	trim.queue_redraw()

static func clear(button: Button) -> void:
	var trim := button.get_node_or_null("_HudSlotTrim") as Node2D
	if trim != null: trim.hide()
	button.self_modulate.a = 1.0
