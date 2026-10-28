class_name SpellCatalog
extends RefCounted

var default_quick_slots: Array[int] = []
var _spells: Dictionary = {}
var _aliases: Dictionary = {}
## Buff ids are a separate namespace from spell ids: the server reports an
## active effect by buff id, and several spells and potions share one.
var _buffs: Dictionary = {}
## Effect to the family's row from the server's magic book: its name and the
## tome it is learned from (none for the families every mage starts with).
var _families: Dictionary = {}
## Knowledge names in the server's index order. The server reports what a
## character has read as indices into this list; a family is known when its
## tome's index is among them.
var _knowledge: Array = []
var _knowledge_loaded := false
var _atlas_path := ""
var _atlas_texture: Texture2D
var _columns := 8
var _cell_size := Vector2(64.0, 64.0)

func configure(config: Dictionary) -> void:
	default_quick_slots.clear()
	_spells.clear()
	_aliases = config.get("spellAliases", {})
	_buffs.clear()
	_families = config.get("spellFamilies", {})
	_atlas_texture = null
	_atlas_path = str(config.get("atlas", ""))
	_columns = maxi(1, int(config.get("columns", 8)))
	var cell_value: Variant = config.get("cellSize", [64, 64])
	if cell_value is Array:
		var cell_values: Array = cell_value as Array
		if cell_values.size() >= 2:
			_cell_size = Vector2(float(cell_values[0]), float(cell_values[1]))
	var default_value: Variant = config.get("defaultQuickSlots", [])
	if default_value is Array:
		for raw_id: Variant in default_value:
			default_quick_slots.append(int(raw_id))
	var spells_value: Variant = config.get("spells", [])
	if spells_value is Array:
		for raw_spell: Variant in spells_value:
			if raw_spell is Dictionary:
				var spell: Dictionary = raw_spell as Dictionary
				_spells[int(spell.get("id", -1))] = spell

	var buffs_value: Variant = config.get("buffs", [])
	if buffs_value is Array:
		for raw_buff: Variant in buffs_value:
			if raw_buff is Dictionary:
				var buff: Dictionary = raw_buff as Dictionary
				_buffs[int(buff.get("id", -1))] = buff

## The tome a spell's family is learned from, or "" for the families every
## mage starts with.
func knowledge_for(spell_id: int) -> String:
	var family: Variant = _families.get(effect_for(spell_id), {})
	if not family is Dictionary:
		return ""
	var tome: Variant = (family as Dictionary).get("tome")
	return str(tome) if tome != null else ""

## Whether the character has read what this spell's family needs. Known is
## the server's list of read knowledge indices.
func knows(spell_id: int, known_knowledge: Array[int]) -> bool:
	var tome := knowledge_for(spell_id)
	return tome.is_empty() or known_knowledge.has(knowledge_index(tome))

## Where a knowledge name sits in the client's knowledge catalog, which is
## the order the server numbers it in; -1 if it is not there.
func knowledge_index(name: String) -> int:
	if not _knowledge_loaded:
		_knowledge_loaded = true
		var parsed: Variant = JSON.parse_string(
			FileAccess.get_file_as_string("res://data/knowledge/catalog.json"))
		if parsed is Dictionary and (parsed as Dictionary).get("entries") is Array:
			_knowledge = (parsed as Dictionary).get("entries") as Array
	return _knowledge.find(name)

## The name and icon for one of the server's buff ids. The server states which
## buffs are active and for how long; only the label lives here, the same way
## the spell names and sigil icons already do.
func buff(buff_id: int) -> Dictionary:
	var value: Variant = _buffs.get(buff_id)
	return value as Dictionary if value is Dictionary else {}

func buff_icon(buff_id: int) -> Texture2D:
	return _icon(int(buff(buff_id).get("icon", -1)))

## The server's own name for what a spell does, where it has one. Power is
## stated per effect rather than per spell, because several spells share one.
func effect_for(spell_id: int) -> String:
	return str(spell(spell_id).get("effect", ""))

## Every catalogued spell id, in catalog order.
func spell_ids() -> Array[int]:
	var ids: Array[int] = []
	for key: Variant in _spells:
		ids.append(int(key))
	return ids

func spell(spell_id: int) -> Dictionary:
	var value: Variant = _spells.get(int(_aliases.get(str(spell_id), spell_id)))
	return value as Dictionary if value is Dictionary else {}

func icon_for(spell_id: int) -> Texture2D:
	var definition: Dictionary = spell(spell_id)
	if definition.is_empty():
		return null
	return _icon(int(definition.get("icon", -1)))

## The sigil sheet and the rectangle inside it for one spell, for the same
## reason ItemAtlas.icon_source() exists: bbcode takes a path and a region,
## never a texture.
func icon_source(spell_id: int) -> Dictionary:
	var definition: Dictionary = spell(spell_id)
	if definition.is_empty() or _atlas_path.is_empty():
		return {}
	var icon_id: int = int(definition.get("icon", -1))
	if icon_id < 0:
		return {}
	return {"path": _atlas_path, "region": Rect2(
		float(icon_id % _columns) * _cell_size.x,
		float(floori(float(icon_id) / float(_columns))) * _cell_size.y,
		_cell_size.x, _cell_size.y)}

func _icon(icon_id: int) -> Texture2D:
	if icon_id < 0:
		return null
	if _atlas_texture == null:
		var resource: Resource = load(_atlas_path)
		if not resource is Texture2D:
			return null
		_atlas_texture = resource as Texture2D
	var atlas_texture: AtlasTexture = AtlasTexture.new()
	atlas_texture.atlas = _atlas_texture
	atlas_texture.region = Rect2(float(icon_id % _columns) * _cell_size.x,
		float(floori(float(icon_id) / float(_columns))) * _cell_size.y,
		_cell_size.x, _cell_size.y)
	return atlas_texture

## Why a spell cannot be cast, as the server would say it, or nothing. The
## server decides; this is only so the window can dim what is out of reach.
func unavailable_reasons(spell_id: int, known_knowledge: Array[int], stats: Dictionary,
		inventory: Dictionary) -> Array[String]:
	var definition: Dictionary = spell(spell_id)
	if definition.is_empty():
		return ["Unknown spell"]
	var reasons: Array[String] = []
	if not knows(spell_id, known_knowledge):
		reasons.append("Read the %s" % knowledge_for(spell_id))
	var required_level: int = int(definition.get("level", 0))
	var current_level: int = int(stats.get("magic", 0))
	if current_level < required_level:
		reasons.append("Requires Magic %d (current %d)" % [required_level, current_level])
	var required_mana: int = int(definition.get("mana", 0))
	var current_mana: int = int(stats.get("ether", 0))
	if current_mana < required_mana:
		reasons.append("Requires %d mana (current %d)" % [required_mana, current_mana])
	var reagents_value: Variant = definition.get("reagents", [])
	if reagents_value is Array:
		for raw_reagent: Variant in reagents_value:
			if not raw_reagent is Dictionary:
				continue
			var reagent: Dictionary = raw_reagent as Dictionary
			var required_quantity: int = int(reagent.get("quantity", 0))
			var available_quantity: int = reagent_quantity(reagent, inventory)
			if available_quantity < required_quantity:
				reasons.append("Requires %d %s (have %d)" % [
					required_quantity, reagent_name(reagent), available_quantity])
	return reasons

## What one reagent is called, for anything that writes a requirement where a
## player reads it. The catalog carries the server's own item name; only a
## reagent the catalog has failed to name falls back to its number.
static func reagent_name(reagent: Dictionary) -> String:
	var named: String = str(reagent.get("name", ""))
	return named if not named.is_empty() else "item %d" % int(
		reagent.get("item_id", -1))

## How many of one reagent the backpack holds. Reagents are matched by the
## image id, because that is the only identity the inventory packet carries -
## the item id beside it is the server's, for its own accounting.
func reagent_quantity(reagent: Dictionary, inventory: Dictionary) -> int:
	return inventory_quantity(int(reagent.get("image_id", -1)), inventory)

func inventory_quantity(image_id: int, inventory: Dictionary) -> int:
	var total := 0
	for raw_slot: Variant in inventory:
		if int(raw_slot) >= 24 and int(raw_slot) < 127:
			continue
		var raw_item: Variant = inventory[raw_slot]
		if raw_item is Dictionary:
			var item: Dictionary = raw_item as Dictionary
			if int(item.get("image_id", -1)) == image_id:
				total += int(item.get("quantity", 0))
	return total
