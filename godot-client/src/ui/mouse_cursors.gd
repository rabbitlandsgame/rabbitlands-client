class_name MouseCursors
extends RefCounted
## The action pointer set: the cursor states what a click will do.
##
## Eternal Lands swaps the hardware pointer as it moves - an eye over something
## inspectable, a speech bubble over an NPC, a sword over an enemy, a sack over
## a dropped bag - so the pointer itself answers "what happens if I click
## here?" before the click is spent. This class owns both halves of that:
## the glyph set (original Eloria art, drawn by tools/make_action_cursors.py
## in the legacy white-fill black-outline language) and the decision table,
## ported from the legacy client's check_cursor_change (gamewin.c).
##
## The ids mirror cursors.h in the legacy client so a mode here can be read
## against the reference without a translation table.

const EYE := 0
const TALK := 1
const ATTACK := 2
const ENTER := 3
const PICK := 4
const HARVEST := 5
const WALK := 6
const ARROW := 7
const TRADE := 8
const USE_WITEM := 9
const USE := 10
const WAND := 11
const TEXT := 12
## Eloria's own, past the legacy thirteen: the grasping hand over an item the
## click will move - place the carry, pick up, equip, unequip, or drop.
const GRAB := 13

const CURSOR_COUNT := 14

## The item-slot pointers, which live on the interface rather than in the
## world: the inventory's tool in hand decides which of the three a slot
## promises, so the pointer says "move", "use" or "look" before the click.
const SLOT_CURSORS := {"item_grab": GRAB, "item_use": USE, "item_inspect": EYE}

var _textures: Array = []
var _hotspots: Array = []
var _names: Array[String] = []
var _current := -1

## Loads the cursor sheet manifest and its glyphs. Returns false - leaving the
## operating system pointer alone - when anything is missing, so a broken asset
## degrades to a working default cursor rather than an invisible one.
func configure(manifest_path: String) -> bool:
	_textures.clear()
	_hotspots.clear()
	_names.clear()
	_current = -1
	var manifest_text: String = FileAccess.get_file_as_string(
		ProjectSettings.globalize_path(manifest_path))
	if manifest_text.is_empty():
		push_warning("Cursor manifest missing: " + manifest_path)
		return false
	var manifest_value: Variant = JSON.parse_string(manifest_text)
	if not manifest_value is Dictionary:
		push_warning("Cursor manifest unreadable: " + manifest_path)
		return false
	var entries: Variant = (manifest_value as Dictionary).get("cursors", [])
	if not entries is Array or (entries as Array).size() != CURSOR_COUNT:
		push_warning("Cursor manifest does not describe all %d cursors" % CURSOR_COUNT)
		return false
	var base_dir: String = manifest_path.get_base_dir()
	for entry_value: Variant in entries as Array:
		if not entry_value is Dictionary:
			return false
		var entry: Dictionary = entry_value as Dictionary
		var image := Image.new()
		var image_path: String = base_dir.path_join(str(entry.get("file", "")))
		if image.load(ProjectSettings.globalize_path(image_path)) != OK or image.is_empty():
			push_warning("Cursor image failed to load: " + image_path)
			return false
		var hotspot_value: Variant = entry.get("hotspot", [])
		if not hotspot_value is Array or (hotspot_value as Array).size() != 2:
			return false
		var hotspot := Vector2(float((hotspot_value as Array)[0]),
			float((hotspot_value as Array)[1]))
		if hotspot.x < 0.0 or hotspot.y < 0.0 \
				or hotspot.x >= float(image.get_width()) \
				or hotspot.y >= float(image.get_height()):
			push_warning("Cursor hotspot outside its image: " + image_path)
			return false
		_textures.append(ImageTexture.create_from_image(image))
		_hotspots.append(hotspot)
		_names.append(str(entry.get("name", "")))
	return true

func loaded() -> bool:
	return _textures.size() == CURSOR_COUNT

func name_of(cursor_id: int) -> String:
	return _names[cursor_id] if cursor_id >= 0 and cursor_id < _names.size() else ""

func hotspot_of(cursor_id: int) -> Vector2:
	if cursor_id >= 0 and cursor_id < _hotspots.size():
		return _hotspots[cursor_id] as Vector2
	return Vector2.ZERO

func current() -> int:
	return _current

## Swaps the pointer. Repeated calls with the same cursor are free, so callers
## can state the wanted cursor every refresh without bookkeeping.
func apply(cursor_id: int) -> void:
	if not loaded() or cursor_id == _current:
		return
	if cursor_id < 0 or cursor_id >= CURSOR_COUNT:
		return
	Input.set_custom_mouse_cursor(_textures[cursor_id] as Texture2D,
		Input.CURSOR_ARROW, _hotspots[cursor_id] as Vector2)
	_current = cursor_id

## The caret glyph rides the I-beam shape instead of the arrow, so every text
## field in the interface shows it without any per-field wiring.
func install_text_caret() -> void:
	if not loaded():
		return
	Input.set_custom_mouse_cursor(_textures[TEXT] as Texture2D,
		Input.CURSOR_IBEAM, _hotspots[TEXT] as Vector2)

## The decision table, ported from check_cursor_change (gamewin.c) and reduced
## to the interactions this client has. Pure so the whole matrix is testable.
##
## Context keys, all optional:
##   over_world: bool - the pointer is over the 3D scene, not a window or HUD.
##   target: "" | "npc" | "player" | "self" | "creature" | "bag" | "harvest"
##       | "portal" | "interactive" - what the pick rays found, first hit wins
##       in the click handler's own order (actors, then bags, then objects) -
##       or one of SLOT_CURSORS' keys, the targets that live on the interface
##       instead: an item slot whose click will move, use or look at the item.
##   alive: bool - the hovered actor is alive.
##   mode: "walk" | "attack" | "trade" - the icon bar's interaction mode.
##   alt: bool - Alt is held, the click-to-attack preview.
##   spell_target: "" | "actor" | "location" - a cast is waiting for a target.
static func choose(context: Dictionary) -> int:
	var slot_cursor: Variant = SLOT_CURSORS.get(str(context.get("target", "")))
	if slot_cursor is int:
		return int(slot_cursor)
	if not bool(context.get("over_world", false)):
		return ARROW
	var target: String = str(context.get("target", ""))
	var mode: String = str(context.get("mode", "walk"))
	var spell: String = str(context.get("spell_target", ""))
	var alive: bool = bool(context.get("alive", true))
	# A spell waiting for an actor claims every actor under the pointer: the
	# click will cast at them, whoever they are (TOUCH_PLAYER in the click
	# handler), so nothing else the pointer could say matters.
	if spell == "actor" and target in ["npc", "player", "self", "creature"]:
		return WAND
	match target:
		"npc":
			# The legacy client talks to NPCs in every mode short of look mode,
			# which this client does not carry: a click is always a greeting.
			return TALK
		"creature":
			# An alive creature defaults to attack-on-click even in walk mode
			# (UNDER_MOUSE_ANIMAL in the reference); a dead one is scenery.
			return ATTACK if alive else WALK
		"summon":
			# Your own summon is a creature kind, but a plain click gives it
			# an order rather than a blow - TOUCH_PLAYER opens its behaviour
			# popup. Only a mode or a held Alt turns the pointer on it.
			if (mode == "attack" or bool(context.get("alt", false))) and alive:
				return ATTACK
			return TALK
		"player":
			if mode == "trade" and alive:
				return TRADE
			if (mode == "attack" or bool(context.get("alt", false))) and alive:
				return ATTACK
			return EYE
		"self":
			return EYE
		"bag":
			return PICK
		"harvest":
			return HARVEST
		"portal":
			return EYE if bool(context.get("alt", false)) else ENTER
		"interactive":
			return USE
	# Bare ground: a location cast claims the click, otherwise it walks.
	if spell == "location":
		return WAND
	return WALK
