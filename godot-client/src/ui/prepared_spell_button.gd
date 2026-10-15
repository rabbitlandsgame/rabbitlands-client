extends Button
## The book and casting bar share the same drag payload.
signal spell_dropped(spell_id: int, power: int)
var spell_id := -1
var power := 1
var accepts_spells := false
var power_provider: Callable

func _get_drag_data(_position: Vector2) -> Variant:
	if spell_id < 0: return null
	var drag_power := int(power_provider.call()) if power_provider.is_valid() else power
	var preview := Label.new()
	preview.text = tooltip_text.get_slice("\n", 0) + " · P%d" % drag_power
	set_drag_preview(preview)
	return {"kind": "prepared_spell", "id": spell_id, "power": drag_power}

func _can_drop_data(_position: Vector2, data: Variant) -> bool:
	return accepts_spells and data is Dictionary and data.get("kind") == "prepared_spell" \
		and data.get("id") is int and data.get("power") is int

func _drop_data(position: Vector2, data: Variant) -> void:
	if _can_drop_data(position, data):
		spell_dropped.emit(int(data.id), int(data.power))
