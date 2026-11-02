extends RefCounted
## The game only opens HTML settings. Folder permissions are requested by the
## overlay's own browser click handlers, preserving their user activation.

static func attach_to(parent: Control, browser := OS.has_feature("web"),
		action := Callable()) -> Button:
	if not browser:
		return null
	var button := Button.new()
	button.name = "BrowserAssetStorage"
	button.text = "Asset storage & shortcut"
	button.tooltip_text = "Choose where game files are saved and download a website shortcut."
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	button.pressed.connect(action if action.is_valid() else _show_settings)
	parent.add_child(button)
	return button

static func _show_settings() -> void:
	if not OS.has_feature("web"):
		return
	var settings := JavaScriptBridge.get_interface("RabbitLandsAssetStorage")
	if settings != null:
		settings.show_settings()
	else:
		push_warning("Browser asset settings are unavailable.")
