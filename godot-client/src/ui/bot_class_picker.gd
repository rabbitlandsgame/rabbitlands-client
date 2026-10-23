extends MenuButton
## One shared class picker for the party and gauntlet prepare windows.

signal class_chosen(class_id: int)

const CLASSES := ["Vanguard · Tank", "Ranger · Ranged damage", "Arcanist · Spell damage", "Warden · Healer"]

func _ready() -> void:
	text = "Add bot"
	tooltip_text = "Choose a bot's class. Bots count toward difficulty and receive no loot share."
	for class_id: int in range(CLASSES.size()):
		get_popup().add_item(CLASSES[class_id], class_id)
	get_popup().id_pressed.connect(func(class_id: int) -> void: class_chosen.emit(class_id))
	get_popup().about_to_popup.connect(func() -> void: _fit_popup.call_deferred())

func _fit_popup() -> void:
	var popup := get_popup()
	if not popup.visible: return
	var bounds: Rect2i
	var button_rect: Rect2
	if popup.is_embedded():
		bounds = Rect2i(get_viewport().get_visible_rect())
		button_rect = get_global_transform_with_canvas() * Rect2(Vector2.ZERO, size)
	else:
		bounds = Rect2i(get_viewport().get_screen_transform() * get_viewport().get_visible_rect())
		var screen := DisplayServer.screen_get_usable_rect(get_window().current_screen)
		if screen.has_area(): bounds = bounds.intersection(screen)
		button_rect = get_screen_transform() * Rect2(Vector2.ZERO, size)
	# MenuButton places the popup first; retain its theme and HUD scaling, then
	# open above the button when the four choices do not fit below it.
	popup.max_size = bounds.size
	var target := Vector2i(button_rect.position.x, button_rect.end.y)
	if target.y + popup.size.y > bounds.end.y:
		target.y = floori(button_rect.position.y) - popup.size.y
	popup.position = target.clamp(bounds.position, (bounds.end - popup.size).max(bounds.position))
