extends Button
## The book and casting bar share the same drag payload.
signal spell_dropped(spell_id: int, power: int)
signal technique_dropped(key: String)
var spell_id := -1
## A quick slot holding a combat technique instead of a spell.
var technique := ""
var power := 1
var accepts_spells := false
var power_provider: Callable

func _get_drag_data(_position: Vector2) -> Variant:
	if not technique.is_empty():
		var picture := TextureRect.new()
		picture.texture = icon
		picture.custom_minimum_size = Vector2(36, 36)
		picture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		set_drag_preview(picture)
		return {"kind": "technique", "key": technique}
	if spell_id < 0: return null
	var drag_power := int(power_provider.call()) if power_provider.is_valid() else power
	var preview := Label.new()
	preview.text = tooltip_text.get_slice("\n", 0) + " · P%d" % drag_power
	set_drag_preview(preview)
	return {"kind": "prepared_spell", "id": spell_id, "power": drag_power}

func _can_drop_data(_position: Vector2, data: Variant) -> bool:
	if not accepts_spells or not data is Dictionary:
		return false
	if data.get("kind") == "technique":
		return data.get("key") is String and not str(data.key).is_empty()
	return data.get("kind") == "prepared_spell" \
		and data.get("id") is int and data.get("power") is int

func _drop_data(position: Vector2, data: Variant) -> void:
	if not _can_drop_data(position, data):
		return
	if data.get("kind") == "technique":
		technique_dropped.emit(str(data.key))
	else:
		spell_dropped.emit(int(data.id), int(data.power))
