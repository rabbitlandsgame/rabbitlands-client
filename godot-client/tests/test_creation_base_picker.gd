extends SceneTree
## Modal selection, combined filters, responsive bounds and keyboard focus.
const Picker := preload("res://src/ui/creation_base_picker.gd")
const Library := preload("res://src/ui/creation_base_library.gd")
var failures: Array[String] = []
var chosen: Array[String] = []
var previews: Array[String] = []
var dismissals := 0

func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error(message)

func _initialize() -> void:
	call_deferred("run")

func settle() -> void:
	for frame: int in 4:
		await process_frame

func check_static_cards(picker: CreationBasePicker, phase: String) -> void:
	check(picker.find_children("*", "SubViewport", true, false).is_empty(), phase + ": cards create no render viewports")
	check(picker.find_children("*", "Node3D", true, false).is_empty(), phase + ": cards create no actors or 3D stages")

func run() -> void:
	var host := Control.new()
	host.size = Vector2(1366, 768)
	root.add_child(host)
	var outside := Button.new()
	outside.text = "Editor"
	host.add_child(outside)
	outside.grab_focus()
	var picker := Picker.new()
	host.add_child(picker)
	picker.basis_selected.connect(func(id: String) -> void: chosen.append(id))
	picker.preview_requested.connect(func(id: String) -> void: previews.append(id))
	picker.dismissed.connect(func() -> void: dismissals += 1)
	var rows: Array[Dictionary] = [
		{"id":"waves", "label":"Silver waves", "race_id":"human", "race_label":"Human", "sex":"female", "hair_tags":["Long", "Wavy"], "search_text":"silver elder", "look":{}},
		{"id":"crop", "label":"Short curls", "race_id":"human", "race_label":"Human", "sex":"male", "hair_tags":["Short", "Curly"], "search_text":"black curls", "look":{}},
		{"id":"ssarathi", "label":"Desert traveller", "race_id":"ssarathi", "race_label":"Lizardfolk", "sex":"female", "hair_tags":["Bald"], "search_text":"Ssarathi reptile", "look":{}},
	]
	var original := rows.duplicate(true)
	picker.setup(rows, "waves")
	check(not picker.is_open(), "setup must not open the picker")
	check(picker.filtered_ids().size() == 3, "all starting looks available")
	picker.open()
	await settle()
	check(picker.is_open() and picker.search.has_focus(), "opening focuses search")
	check(picker.selected_id() == "waves" and not picker.use_button.disabled, "default basis highlighted")
	check(chosen.is_empty(), "opening does not commit an appearance")
	check_static_cards(picker, "open")
	picker.search.text = "silver human"
	picker._filter_rows()
	check(picker.filtered_ids() == PackedStringArray(["waves"]), "search matches all words across row fields")
	check_static_cards(picker, "filter")
	picker._reset_filters()
	picker._select_filter(picker.sex_filter, "female")
	picker._select_filter(picker.race_filter, "ssarathi")
	picker._select_filter(picker.hair_filter, "Bald")
	picker._filter_rows()
	check(picker.filtered_ids() == PackedStringArray(["ssarathi"]), "sex, race and hair filters combine")
	check(picker.use_button.disabled, "filtered-out selection cannot accidentally be committed")
	picker._select_card("ssarathi")
	check(previews == ["ssarathi"] and chosen.is_empty(), "selection emits only preview")
	check_static_cards(picker, "select")
	picker._use_basis()
	await settle()
	check(chosen == ["ssarathi"] and not picker.is_open(), "Use emits the chosen basis once and closes")
	check(outside.has_focus(), "closing restores editor focus")
	check(rows == original, "picker never mutates catalog looks or creation data")
	picker.setup(rows, "crop")
	picker.open()
	await settle()
	picker.search.text = "no such look"
	picker._filter_rows()
	check(picker.empty_message.visible and picker.use_button.disabled and not picker.clear_filters.disabled, "empty state keeps filter recovery available")
	picker._reset_filters()
	await settle()
	outside.grab_focus()
	await settle()
	check(picker.is_ancestor_of(root.gui_get_focus_owner()), "modal focus cannot leave for controls underneath")
	for step: int in 18:
		picker._cycle_focus(1)
		check(picker.is_ancestor_of(root.gui_get_focus_owner()), "Tab stays inside the popup")
	for resolution: Vector2 in [Vector2(1920,1080), Vector2(1366,768), Vector2(1280,720), Vector2(1024,768), Vector2(800,600), Vector2(640,480)]:
		host.size = resolution
		picker.size = resolution
		picker._layout()
		await settle()
		var bounds := Rect2(Vector2.ZERO, resolution)
		check(bounds.encloses(picker.panel.get_rect()), "popup stays inside %s: rect %s minimum %s" % [resolution, picker.panel.get_rect(), picker.panel.get_combined_minimum_size()])
		check(picker.panel.get_global_rect().encloses(picker.cancel_button.get_global_rect()), "Cancel remains visible at %s" % resolution)
		check(picker.panel.get_global_rect().encloses(picker.use_button.get_global_rect()), "Use remains visible at %s" % resolution)
	check(picker.grid.columns >= 1 and picker.grid.columns <= 4, "responsive portrait columns")
	var named_rows: Array[Dictionary] = []
	for index: int in 8:
		var row := rows[0].duplicate(true)
		row.id = "name_%d" % index
		row.label = ["Mira", "Rowan", "Tavi", "Amara", "Idris", "Aldric", "Anika", "Kellan"][index]
		named_rows.append(row)
	host.size = Vector2(1280,720)
	picker.size = host.size
	picker.setup(named_rows,"name_4")
	picker._layout()
	await settle()
	check(picker.grid.columns == 4, "common logical resolution uses four portrait columns")
	for row: Dictionary in named_rows:
		var card := picker._cards[str(row.id)] as Button
		var caption := card.get_meta("caption") as Label
		check(picker.scroll.get_global_rect().encloses(card.get_global_rect()), "both rows fit without clipping %s" % row.label)
		check(card.get_global_rect().encloses(caption.get_global_rect()), "name stays inside its card: %s" % row.label)
		check((card.get_meta("portrait") as TextureRect).size.y >= 96, "portrait remains legible: %s" % row.label)
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var catalog := Library.rows(registry)
	picker.setup(catalog, "human_34", {"portrait_manifest_path": "user://no_creation_portrait_manifest.json"})
	await settle()
	check(picker._cards.size() == 25, "All 25 catalog cards exist without live portrait stages")
	check_static_cards(picker, "all25")
	for id: String in picker._cards:
		var card := picker._cards[id] as Button
		check((card.get_meta("portrait") as TextureRect).texture == null and (card.get_meta("placeholder") as Label).visible,
			"Missing portrait is a static placeholder: " + id)
	picker.scroll.scroll_vertical = int(picker.scroll.get_v_scroll_bar().max_value)
	await settle()
	check_static_cards(picker, "scroll25")
	picker._select_filter(picker.race_filter, "luminous")
	picker._filter_rows()
	await settle()
	check(picker._cards.size() == 11, "Static filtering retains all 11 Human choices")
	check_static_cards(picker, "filter11")
	picker._select_card("human_01")
	check_static_cards(picker, "select and reopen")
	var cancel := InputEventAction.new()
	cancel.action = "ui_cancel"
	cancel.pressed = true
	picker._input(cancel)
	await settle()
	check(dismissals == 1 and chosen == ["ssarathi"] and not picker.is_open(), "Escape dismisses without committing another look")
	picker.queue_free()
	host.queue_free()
	await process_frame
	print("Creation basis picker: %d failures" % failures.size())
	quit(0 if failures.is_empty() else 1)
