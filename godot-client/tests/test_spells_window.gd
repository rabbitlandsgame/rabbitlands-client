extends SceneTree
## Guards the Spells window.
##
## The window is a view of two honest sources: the client's own spell
## catalog, and the server's state in AppState - read knowledge, stats,
## inventory. It aligns effect rows with target columns within spell groups,
## dims what the client can see no way to cast, writes the first blocking
## reason beside the name, and its Cast button only asks: the id goes to a
## Callable and the server decides. Everything below checks that the window
## says exactly what those sources say and nothing more.

var failures := 0
var cast_ids: Array[int] = []

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var app_state: Node = root.get_node("/root/AppState")
	var catalog := SpellCatalog.new()
	catalog.configure(_json("res://data/spells/catalog.json"))
	_expect(catalog.spell_ids().size() == 89,
		"the real catalog carries the eighty-nine Eloria spells: %d"
		% catalog.spell_ids().size())
	var window: Control = (load("res://src/ui/spells_window.gd")
		as GDScript).new() as Control
	root.add_child(window)
	await process_frame
	window.call("configure", catalog,
		func(spell_id: int) -> void: cast_ids.append(spell_id))
	var panel: PanelContainer = window.get_node("SpellsWindow") as PanelContainer

	_expect(not panel.visible, "the spells window starts closed")
	window.call("toggle")
	await process_frame
	_expect(panel.visible and bool(window.call("is_open")), "toggle opens it")
	var rect: Rect2 = panel.get_global_rect()
	_expect(rect.position.x >= 0.0 and rect.position.y >= 0.0
		and rect.end.x <= 1280.0 - float(window.get("RESERVED_RIGHT_RAIL"))
		and rect.end.y <= 720.0,
		"it fits 1280x720 clear of the resource rail: %s" % rect)

	# Every spell appears, each exactly once, across the four groups.
	var body := "SpellsWindow/SpellsBody/SpellContentScroll/SpellContent/"
	var listed: Array[int] = []
	for group: String in ["Health", "General", "Attack", "Defense"]:
		var section: VBoxContainer = window.get_node(
			body + "SpellScroll/SpellBrowser/SpellGroups/%sSpells" % group) as VBoxContainer
		for child: Node in section.find_children("SpellButton*", "Button", true, false):
			listed.append(int(str(child.name).trim_prefix("SpellButton")))
	_expect(listed.size() == 89,
		"all eighty-nine spells are on the window: %d" % listed.size())
	for spell_id: int in catalog.spell_ids():
		_expect(listed.has(spell_id), "spell %d is listed" % spell_id)

	# The documented grouping, spot-checked by effect.
	_expect(str(window.call("group_of", 0)) == "Health",
		"Heal is a health spell")
	_expect(str(window.call("group_of", 6)) == "Attack",
		"Magic Bolt is an attack spell")
	_expect(str(window.call("group_of", 3)) == "Defense",
		"Stoneward is a defense spell")
	_expect(str(window.call("group_of", 5)) == "General",
		"Blink, an effect no group names, is a general spell")
	_expect(str(window.call("group_of", 21)) == "Health",
		"Hearthcircle, the party heal, is a health spell")
	_expect(str(window.call("group_of", 20)) == "Attack",
		"Ruinfall, which is a Harm on everything nearby, is an attack spell")
	_expect(str(window.call("group_of", 11)) == "Defense",
		"Null Mantle is a defense spell")
	_expect(str(window.call("group_of", 88)) == "Health",
		"Restore Ether gives back what was spent, so it sits with the renewal spells")
	# Swiftwend, Duskveil, Glassgaze and Thriceward name effects the window's
	# own table does not, so they fall to General. Eternal Lands keeps haste,
	# invisibility and true sight there too; the elemental ward belongs under
	# Defense and needs a row in EFFECT_GROUPS to get there.
	_expect(str(window.call("group_of", 17)) == "General",
		"Swiftwend is a general spell")
	var heal_button: Button = window.get_node(
		body + "SpellScroll/SpellBrowser/SpellGroups/HealthSpells/HealEffectRow/SelfCell/SpellButton0") as Button
	_expect(heal_button != null, "Heal sits at the Heal effect and Self target")
	_expect(heal_button.tooltip_text == "Heal",
		"a spell button says which spell it is: " + heal_button.tooltip_text)
	_expect(heal_button.icon is Texture2D,
		"and carries its sigil-atlas icon")
	# Every variant shares its effect row and lines up with its target heading.
	await process_frame
	await process_frame
	var headings: HBoxContainer = window.get_node(
		body + "SpellTargetHeadings/TargetHeadings") as HBoxContainer
	var effect_rows: Dictionary = {}
	for spell_id: int in catalog.spell_ids():
		var button := window.find_child("SpellButton%d" % spell_id, true, false) as Button
		var definition := catalog.spell(spell_id)
		var effect := str(definition.effect)
		var scope := str(definition.scope)
		var target := scope if scope in ["self", "target", "allies", "burst"] else "utility"
		var cell := button.get_parent() as Control
		var row := cell.get_parent()
		_expect(str(cell.name) == "%sCell" % target.capitalize(),
			"spell %d is in its target column" % spell_id)
		if effect_rows.has(effect):
			_expect(effect_rows[effect] == row, "all %s variants share a row" % effect)
		else:
			effect_rows[effect] = row
		var heading := headings.get_node(NodePath(cell.name)) as Control
		_expect(is_equal_approx(cell.global_position.x, heading.global_position.x),
			"spell %d aligns with its fixed target heading" % spell_id)
	var heal_row: HBoxContainer = effect_rows["heal"]
	var target_x := (heal_row.get_node("TargetCell") as Control).global_position.x
	var search: LineEdit = window.get("search") as LineEdit
	var scope_filter: OptionButton = window.get("scope_filter") as OptionButton
	search.text = "heal"
	scope_filter.select(2)
	window.call("_filter_spells")
	await process_frame
	await process_frame
	_expect(not heal_button.visible, "target filtering hides the Self variant")
	var target_heal := heal_row.get_node("TargetCell/SpellButton1") as Button
	_expect(target_heal.is_visible_in_tree(), "target filtering retains Heal Target")
	_expect(is_equal_approx((target_heal.get_parent() as Control).global_position.x, target_x),
		"filtering keeps the Target column in place")
	_expect(not (effect_rows["shield"] as Control).visible, "search hides empty effect rows")
	search.text = "no such spell"
	window.call("_filter_spells")
	_expect((window.find_child("NoMatchingSpells", true, false) as Label).is_visible_in_tree(),
		"an empty search result is explained")
	search.clear()
	scope_filter.select(5)
	window.call("_filter_spells")
	var utility_count := 0
	for button: Button in (window.get("_buttons") as Dictionary).values():
		if button.is_visible_in_tree():
			utility_count += 1
	_expect(utility_count == 3, "utility includes Blink, Transmute and Recall")
	scope_filter.select(0)
	window.call("_filter_spells")

	# With nothing owned, nothing is castable: dimmed, not hidden, and still
	# there to inspect.
	(app_state.get("known_knowledge") as Array).clear()
	(app_state.get("stats") as Dictionary).clear()
	(app_state.get("inventory") as Dictionary).clear()
	window.call("sync")
	var blocked_alpha: float = float(window.get("BLOCKED_ALPHA"))
	_expect(is_equal_approx(heal_button.modulate.a, blocked_alpha),
		"an uncastable spell is dimmed: %f" % heal_button.modulate.a)
	var cast: Button = window.get("cast_button") as Button
	_expect(cast.disabled, "Cast is disabled while nothing is selected")
	_expect(int(window.get("selected_spell_id")) == -1,
		"and no spell starts selected")
	_expect(window.get("effect_preview").viewport == null,
		"an unselected spellbook does not allocate a preview world")
	var blinkstep: Button = window.get_node(
		body + "SpellScroll/SpellBrowser/SpellGroups/GeneralSpells/BlinkEffectRow/UtilityCell/SpellButton5") as Button
	blinkstep.pressed.emit()
	await process_frame
	_expect(int(window.get("selected_spell_id")) == 5,
		"clicking a spell selects it")
	var name_label: Label = window.get("name_label") as Label
	_expect(name_label.text == "Blink (Read the Tome of Blink)",
		"the blocked name carries the first blocking reason: " + name_label.text)
	_expect(name_label.get_theme_color("font_color")
			== (window.get("BLOCKED_COLOR") as Color),
		"and is drawn red")
	var knowledge_label: Label = window.get("knowledge_label") as Label
	_expect(knowledge_label.text == "Knowledge: !Tome of Blink",
		"an unread tome is named and marked with !: " + knowledge_label.text)
	# Reading the tome is the server's to report; the window follows it.
	var known: Array = app_state.get("known_knowledge") as Array
	known.append(catalog.knowledge_index("Tome of Blink"))
	app_state.emit_signal("state_changed", &"knowledge")
	await process_frame
	_expect(knowledge_label.text == "Knowledge: Tome of Blink",
		"a read tome is named plainly: " + knowledge_label.text)
	_expect(name_label.text.begins_with("Blink (") and not name_label.text.contains("Tome"),
		"and the name's reason moves on to what still blocks it: " + name_label.text)
	# The reagents line answers the same question the knowledge line does, in
	# the same shape: what the spell wants, by name, and what is short.
	var blocked_reagents: Label = window.get("reagents_label") as Label
	_expect(blocked_reagents.text
			== "Reagents: !Air Distillate x1, Portal Shard from Power 4",
		"reagents nothing carries are named and marked: "
			+ blocked_reagents.text)
	_expect(not cast.disabled, "selecting a spell enables Cast")
	cast.pressed.emit()
	_expect(cast_ids == [5],
		"Cast asks with the selected id: %s" % str(cast_ids))

	# Every mage knows Heal; the server grants the rest it needs.
	var stats: Dictionary = app_state.get("stats") as Dictionary
	stats["magic"] = 5
	stats["ether"] = 50
	var inventory: Dictionary = app_state.get("inventory") as Dictionary
	inventory[0] = {"image_id": 584, "quantity": 10}
	inventory[1] = {"image_id": 67, "quantity": 10}
	app_state.emit_signal("state_changed", &"stats")
	await process_frame
	_expect(is_equal_approx(heal_button.modulate.a, 1.0),
		"a castable spell is drawn at full strength: %f" % heal_button.modulate.a)
	heal_button.pressed.emit()
	await process_frame
	_expect(name_label.text == "Heal",
		"a castable name carries no reason: " + name_label.text)
	_expect(name_label.get_theme_color("font_color")
			== (window.get("CASTABLE_COLOR") as Color),
		"and is drawn green-white")
	var description: Label = window.get("description_label") as Label
	_expect(not description.text.strip_edges().is_empty(),
		"the description line is filled")
	var numbers: Label = window.get("numbers_label") as Label
	_expect(numbers.text == "Magic 0   Base ether 5",
		"the level and mana are stated: " + numbers.text)
	_expect(knowledge_label.text == "Knowledge: every mage knows this",
		"a family every mage starts with needs no tome: " + knowledge_label.text)
	var reagents: Label = window.get("reagents_label") as Label
	_expect(reagents.text
			== "Reagents: Life Distillate x1, Woven Charm from Power 4",
		"reagents are named and counted: " + reagents.text)
	cast.pressed.emit()
	_expect(cast_ids == [5, 0],
		"Cast asks with the new selection: %s" % str(cast_ids))

	# Every selection, including unavailable spells, has its own description
	# and a production effect confined to a separate preview world.
	var preview = window.get("effect_preview")
	for id: int in catalog.spell_ids():
		window.call("_on_spell_pressed", id)
		var spell := catalog.spell(id)
		_expect(description.text == spell.description and not description.text.is_empty(),
			"spell %d shows its catalog description" % id)
		_expect(preview.effects.get_child_count() > 0,
			"spell %d has an animated effect" % id)
		for effect: WorldEffect3D in preview.effects.get_children():
			_expect(effect.effect_id == int(spell.visual), "spell %d previews its production visual" % id)
			_expect(effect.area_radius > 0 if spell.scope == "burst" else effect.area_radius == 0,
				"spell %d distinguishes an area from a single recipient" % id)
		_expect(preview.effects.get_child_count() == (3 if spell.scope == "allies" else 1),
			"spell %d demonstrates the correct recipient group" % id)
	_expect(preview.viewport.own_world_3d and preview.viewport.world_3d != root.world_3d,
		"the preview cannot add effects to the game world")
	_expect(cast_ids == [5, 0], "inspecting every spell never casts one")
	window.set("requested_power", 10)
	window.call("_refresh_details")
	_expect(preview.power_level == 10 and preview.effects.get_child(0).power_level == 10,
		"changing power updates the preview")
	preview.clock = 1.0
	window.call("sync")
	_expect(preview.clock == 1.0, "state refreshes do not interrupt the preview")
	window.call("_on_spell_pressed", int(window.get("selected_spell_id")))
	_expect(preview.clock == 0.0, "clicking the same spell replays its effect immediately")
	preview.call("_process", 3.0)
	_expect(preview.clock == 0 and preview.effects.get_child_count() > 0,
		"the effect automatically replays")
	await process_frame
	await process_frame
	var pinned: Control = panel.find_child("SpellDetails", true, false) as Control
	var before := pinned.get_global_rect()
	(window.get("_content_scroll") as ScrollContainer).scroll_vertical = 400
	await process_frame
	_expect(pinned.get_global_rect() == before and panel.get_global_rect().encloses(before),
		"the description and preview stay visible while browsing spells")
	search.text = "no such spell"
	window.call("_filter_spells")
	_expect(preview.definition.is_empty() and not preview.is_processing()
		and preview.effects.get_child_count() == 0,
		"filtering away the selection clears and stops its preview")
	search.clear()
	window.call("_filter_spells")
	window.call("_on_spell_pressed", 0)
	window.call("close")
	_expect(not preview.is_processing() and preview.effects.get_child_count() == 0
		and preview.viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"closing the spellbook stops rendering and clears its animation")
	window.call("toggle")
	_expect(preview.is_processing() and preview.effects.get_child_count() == 1,
		"reopening resumes the selected spell preview")
	window.call("close")
	# The selected-power quote supersedes base-cost guesses, including foci.
	window.set("selected_spell_id",0)
	window.set("requested_power",2)
	window.call("_quote_state",{"kind":"preview","id":0,"requested":2,"power":2,"limit":4,"mana":8,
		"ready":true,"focus":"Hearthstone Focus","reagents":[{"name":"Attunement Charge","quantity":1,"have":1}]})
	_expect(not cast.disabled and numbers.text.contains("Ether 8"),"selected power uses the server cost")
	_expect(reagents.text.contains("Hearthstone Focus"),"focus substitution is visible")
	window.call("_quote_state",{"kind":"preview","id":0,"requested":1,"power":1,"limit":4,"mana":5,"ready":false})
	_expect(not cast.disabled,"stale quote for another power is ignored")
	window.call("_quote_state",{"kind":"preview","id":0,"requested":2,"power":2,"limit":4,"mana":8,
		"ready":false,"reason":"Missing materials.","reagents":[]})
	_expect(cast.disabled and name_label.text.contains("Missing materials"),"server rejection remains visible")
	_expect(not panel.visible and not bool(window.call("is_open")),
		"close hides it")

	# Leave AppState as this suite found it.
	known.clear()
	stats.clear()
	inventory.clear()

	print("spells window tests: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	window.queue_free()
	await process_frame
	quit(failures)

func _json(path: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed as Dictionary if parsed is Dictionary else {}

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
