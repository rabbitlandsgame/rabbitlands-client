extends SceneTree
## Exercises shared text roles through actual UI builders and state refreshes.
const Colors := preload("res://src/ui/text_colors.gd")
const EntryStyle := preload("res://src/ui/oldcraft_entry_style.gd")
const DialogueStyle := preload("res://src/ui/oldcraft_dialogue_style.gd")
const BookUI := preload("res://src/ui/action_book_ui.gd")
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _named(host: Node, node: Node, title: String) -> Node:
	node.name = title
	host.add_child(node)
	node.owner = host
	node.unique_name_in_owner = true
	return node

func _run() -> void:
	Colors.reset()
	var host := Control.new()
	root.add_child(host)
	var login := _named(host, PanelContainer.new(), "LoginPanel") as PanelContainer
	_named(host, PanelContainer.new(), "CreationPanel")
	var input := LineEdit.new()
	login.add_child(input)
	var label := Label.new()
	login.add_child(label)
	_named(host, Label.new(), "Status")
	EntryStyle.apply(host)
	_expect(input.get_theme_color("font_color") == Color(0, 0.9, 1), "login uses EL cyan")
	_expect(label.get_theme_color("font_color") == Color.WHITE, "login labels use EL white")
	Colors.set_color("login_input", Color.MAGENTA)
	_expect(input.get_theme_color("font_color") == Color.MAGENTA, "login text updates while the screen exists")
	var panel := _named(host, PanelContainer.new(), "DialoguePanel") as PanelContainer
	var speaker := _named(host, Label.new(), "DialogueName") as Label
	var body := _named(host, RichTextLabel.new(), "DialogueText") as RichTextLabel
	_named(host, Panel.new(), "DialogueBackdrop")
	var game := _named(host, Control.new(), "GameView") as Control
	game.size = Vector2(1280, 720)
	DialogueStyle.apply(host)
	_expect(speaker.get_theme_color("font_color") == Color.WHITE, "NPC speaker uses white")
	_expect(body.get_theme_color("default_color") == Color.WHITE, "NPC body uses white")
	var reply := Button.new()
	host.add_child(reply)
	DialogueStyle.style_option(reply, true, 0)
	_expect(reply.get_theme_color("font_color") == Color.YELLOW, "quest reply uses EL yellow")
	_expect(reply.get_theme_color("font_hover_color") == Color(1, 0.5, 0), "reply hover uses EL orange")
	Colors.set_color("npc_reply", Color.CYAN)
	_expect(reply.get_theme_color("font_color") == Color.CYAN, "NPC replies update live")
	var paper := (host.get_node("DialogueBackdrop") as Panel).get_theme_stylebox("panel") as StyleBoxTexture
	_expect(paper.modulate_color.r < 0.2 and paper.modulate_color.g < 0.2, "existing dialogue artwork is dark enough for white and yellow")
	var requirements := VBoxContainer.new()
	host.add_child(requirements)
	var row := BookUI.requirement(requirements, "Ether", "20 / 20", true)
	_expect((row.get_child(0) as Label).get_theme_color("font_color") == Color.GREEN, "spell availability uses EL green")
	Colors.set_color("spell_ready", Color.CYAN)
	_expect((row.get_child(0) as Label).get_theme_color("font_color") == Color.CYAN, "spell requirement changes live")
	var storage_script := load("res://src/ui/classic_storage_workspace.gd")
	var skin: Theme = storage_script.classic_theme()
	_expect(skin.get_color("font_color", "ItemList") == Color(0.77, 0.57, 0.39), "inventory list uses EL GUI brown")
	_expect(skin.get_color("font_selected_color", "ItemList") == Color(0.95, 0.76, 0.52), "inventory selected uses EL bright GUI")
	var encyclopedia := load("res://src/ui/encyclopedia_view.gd").new() as Control
	host.add_child(encyclopedia)
	await process_frame
	Colors.set_color("encyclopedia_link", Color.RED)
	var markup: String = encyclopedia.call("_link", "test", "test")
	_expect(markup.contains("#ff0000"), "encyclopedia markup follows customized link color")
	# Load real screen scripts after autoload registration to catch cross-module
	# compile errors without instantiating the world or contacting a server.
	for path: String in ["extension_windows", "reference_window", "spells_window", "techniques_panel", "summoning_window", "invasion_assistant", "lantern_guide"]:
		var script := load("res://src/ui/%s.gd" % path) as GDScript
		_expect(script != null and script.can_instantiate(), "%s compiles with live color bindings" % path)
	var state: Node = root.get_node("AppState")
	var saved_quests: Array = state.get("quest_journal")
	var saved_archive: Array = state.get("quest_archive")
	var saved_detail: Dictionary = state.get("item_detail")
	var quests: Array[Dictionary] = [{"title": "Lantern road", "objective": "Relight the stones", "ready": true}]
	var archive: Array[Dictionary] = [{"title": "Completed road", "detail": "The stones shine again."}]
	state.set("quest_journal", quests)
	state.set("quest_archive", archive)
	var extensions := load("res://src/ui/extension_windows.gd").new() as Control
	host.add_child(extensions)
	await process_frame
	var quest_list: ItemList = extensions.get("quest_list")
	_expect(quest_list.get_item_custom_fg_color(0) == Color.WHITE, "active quests use EL white")
	Colors.set_color("quest_active", Color.RED)
	_expect(quest_list.get_item_custom_fg_color(0) == Color.RED, "quest list refreshes its per-item colors live")
	Colors.set_color("quest_heading", Color.CYAN)
	_expect((extensions.get("quest_detail") as RichTextLabel).text.contains("#00ffff"), "quest headings rebuild their inline palette")
	extensions.call("_on_quest_view", true)
	_expect(quest_list.get_item_custom_fg_color(0) == Color("999999"), "completed quests use EL gray")
	Colors.set_color("quest_completed", Color.MAGENTA)
	_expect(quest_list.get_item_custom_fg_color(0) == Color.MAGENTA, "completed quest rows update live")
	var health := extensions.call("_party_number", "HealthNumber", 10, 100, Color.RED, true) as Label
	host.add_child(health)
	_expect(health.get_theme_color("font_color") == Color("b74935"), "party low-health text retains its RL color")
	Colors.set_color("party_health_low", Color.CYAN)
	_expect(health.get_theme_color("font_color") == Color.CYAN, "party resource text updates live")
	state.set("item_detail", {"open": true, "name": "Lantern", "equipped": true})
	extensions.call("_sync_detail")
	Colors.set_color("inventory_equipped", Color.CYAN)
	_expect((extensions.get("detail_text") as RichTextLabel).text.contains("#00ffff"), "equipped notice rebuilds from its own role")
	var invasion := load("res://src/ui/invasion_assistant.gd").new() as Window
	host.add_child(invasion)
	await process_frame
	invasion.call("_rebuild_roster")
	Colors.set_color("invasion_muted", Color.RED)
	_expect((invasion.get("map_roster") as RichTextLabel).text.contains("#ff0000"), "invasion roster updates embedded colors")
	Colors.reset()
	_expect(reply.get_theme_color("font_color") == Color.YELLOW, "reset restores existing controls")
	_expect((invasion.get("map_roster") as RichTextLabel).text.contains("#8296a3"), "reset restores existing invasion markup")
	state.set("quest_journal", saved_quests)
	state.set("quest_archive", saved_archive)
	state.set("item_detail", saved_detail)
	host.free()
	print("Interface text colors: %d checks, %d failures" % [checks, failures])
	quit(0 if failures == 0 else 1)
