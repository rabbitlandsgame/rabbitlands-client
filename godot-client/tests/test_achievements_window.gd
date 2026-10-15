extends SceneTree
## The achievements window and the title line over an actor's head.
##
## Both are driven entirely by what the server sends: the window's pages are
## whatever categories the catalogue packet happens to carry, and the title is
## its own packet rather than a fourth field crammed into the display name.
## So every payload below is the exact output of the server's own builders in
## eloria/protocol.py, and a window can only pass here if it reads what the
## real server sends.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	var game_view: Control = main.get_node("GameView") as Control
	game_view.show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	var windows: Control = main.get("extension_windows") as Control
	var resource_rail: Control = main.get_node("GameView/ResourceHud") as Control
	if not _expect(windows != null, "the extension windows are built"):
		quit(failures)
		return
	await process_frame

	# Four of the catalogue over two categories: one finished with no title,
	# one part-way that grants one, one finished that grants the title being
	# worn, and one on a second page.
	app_state.call("_on_packet", 219, _hex(
		"576f6c667362616e6500040001000000010000000166697273745f626c6f6f6400"
		+ "466972737420426c6f6f6400436f6d626174004b696c6c20736f6d657468696e67"
		+ "2e000004000000640000000063756c6c65720043756c6c6572206f662074686520"
		+ "57696c647300436f6d62617400412068756e647265642063726561747572657320"
		+ "646f776e2e007468652043756c6c657200320000003200000001776f6c66736261"
		+ "6e6500576f6c667362616e6500436f6d62617400466966747920776f6c76657320"
		+ "616e6420686f756e64732e00576f6c667362616e6500000000000100000000" +
		"66697273745f68616e6466756c0046697273742048616e6466756c00476174686572"
		+ "696e670050756c6c20736f6d657468696e67206f7574206f6620746865206772"
		+ "6f756e642e0000"))
	await process_frame
	_expect(int((app_state.get("achievements_catalog") as Dictionary)
			.get("entries", []).size()) == 4,
		"the catalogue packet reaches the state slice")

	windows.call("toggle_achievements")
	await process_frame
	var panel: PanelContainer = windows.get("achievements_panel") as PanelContainer
	_expect(panel != null and panel.visible, "the achievements window opens")

	# The header counts what is finished against the whole catalogue, which is
	# the number a player wants before they read a single row.
	var header: Label = windows.get("achievements_header") as Label
	_expect(header != null and header.text == "2 of 4 earned",
		"the header states how much of the catalogue is done: " + str(
			header.text if header != null else "<missing>"))

	# One page per category the server sent, in the order it sent them. The
	# client holds no list of categories, so a catalogue that grows one shows
	# it without this file changing.
	var tabs: HBoxContainer = windows.get("achievements_tabs") as HBoxContainer
	var pages: Array[String] = []
	for child: Node in tabs.get_children():
		pages.append((child as Button).text)
	_expect(pages.size() == 2 and pages[0] == "Combat"
		and pages[1] == "Gathering",
		"a page per category the server sent, in its order: " + str(pages))

	# The first page's rows, with a bar apiece.
	var rows: VBoxContainer = windows.get("achievements_rows") as VBoxContainer
	_expect(rows.get_child_count() == 3,
		"the Combat page draws its three rows, not the whole catalogue")
	var culler: Control = rows.get_node_or_null("Achievementculler") as Control
	_expect(culler != null, "each row is named for the key it draws")
	if culler != null:
		var bar: ProgressBar = culler.get_node("Progress") as ProgressBar
		_expect(is_equal_approx(bar.value, 4.0)
			and is_equal_approx(bar.max_value, 100.0),
			"an unfinished row's bar is its progress against its threshold")
		_expect((culler.get_node("Header/Count") as Label).text == "4 / 100",
			"and the same numbers are written out beside it")
		_expect((culler.get_node("Header/Done") as Label).text == "",
			"an unfinished row carries no tick")
		_expect((culler.get_node("Description") as Label).text.begins_with(
				"A hundred"),
			"the blurb is the server's, so the catalogue can be browsed")
		_expect((culler.get_node("Grants") as Label).text.contains("the Culler"),
			"a row that grants a title says which")
	var blooded: Control = rows.get_node_or_null("Achievementfirst_blood") as Control
	_expect(blooded != null
		and (blooded.get_node("Header/Done") as Label).text != "",
		"a finished row is ticked")
	_expect(rows.get_node_or_null("Achievementfirst_handful") == null,
		"the other page's rows are not on this one")

	# Switching pages is the client's own business - which page is showing is
	# the player's choice about their own window - but what is on each is not.
	for child: Node in tabs.get_children():
		if (child as Button).text == "Gathering":
			(child as Button).pressed.emit()
	await process_frame
	rows = windows.get("achievements_rows") as VBoxContainer
	_expect(rows.get_child_count() == 1
		and rows.get_node_or_null("Achievementfirst_handful") != null,
		"choosing a page draws that page")

	# The picker offers exactly the earned titles and nothing else: the server
	# refuses any other, and a menu of things it would refuse is worse than a
	# short menu. "Culler of the Wilds" is not finished, so its title is not on
	# offer even though the packet named it.
	var picker: OptionButton = windows.get("achievements_title_picker") as OptionButton
	var offered: Array[String] = []
	for index: int in range(picker.item_count):
		offered.append(picker.get_item_text(index))
	_expect(offered.size() == 2 and offered[0] == "(none)"
		and offered[1] == "Wolfsbane",
		"only earned titles are on offer: " + str(offered))
	_expect(picker.get_item_text(picker.selected) == "Wolfsbane",
		"the picker starts on the title actually being worn")

	# Nothing may cover the fixed resource rail down the right-hand edge, and
	# the window has to fit the smallest window the client supports.
	var box: Rect2 = Rect2(panel.global_position, panel.size)
	_expect(box.position.x >= 0.0 and box.position.y >= 0.0
		and box.end.x <= 1280.0 and box.end.y <= 720.0,
		"the achievements window fits 1280x720: " + str(box))
	_expect(not box.intersects(Rect2(resource_rail.global_position,
			resource_rail.size)),
		"and stays clear of the resource rail")

	# A catalogue that has not arrived is a window that says so rather than an
	# empty box that looks broken.
	app_state.call("_on_packet", 219, _hex("000000"))
	await process_frame
	_expect((windows.get("achievements_header") as Label).text
			== "No achievements yet",
		"a world with no achievements is stated, not left blank")

	# ------------------------------------------------------- the title line
	#
	# An enhanced actor for Bob, then the title packet naming him. The title
	# rides its own packet because the display name already packs a colour
	# byte, the name and the guild tag into one string.
	app_state.call("_on_packet", 51, _hex(
		"5c000203e1010000000001000001020304050b001e14071400"
		+ "12000190426f62000040ff0600"))
	await process_frame
	main.call("_sync_world")
	await process_frame
	var actors: Dictionary = main.get("actor_nodes") as Dictionary
	var bob: Node3D = actors.get(92) as Node3D
	if not _expect(bob != null, "the actor the title belongs to exists"):
		quit(failures)
		return
	_expect(bob.get_node_or_null("TitleLine") == null,
		"an actor wearing no title carries no label for one")

	app_state.call("_on_packet", 211, _hex("01005c007468652043756c6c657200"))
	await process_frame
	var worn: Label3D = bob.get_node_or_null("TitleLine") as Label3D
	_expect(worn != null and worn.text == "the Culler" and worn.visible,
		"the worn title is drawn over the actor wearing it")
	if worn != null:
		var plate: Label3D = bob.get_node("Nameplate") as Label3D
		_expect(worn.position.y == plate.position.y and worn.offset.y > 0.0,
			"and sits above the name rather than over the health bar")
		_expect(worn.text != plate.text and plate.text == "Bob",
			"the name itself is untouched")
		_expect(worn.fixed_size and is_equal_approx(worn.pixel_size,
				plate.pixel_size),
			"drawn in the same screen pixels as the rest of the block, or the "
			+ "two would drift apart as the camera zoomed")

	# Taking a title off is an empty row rather than a missing one, so the
	# label goes away instead of keeping the last thing that was worn.
	app_state.call("_on_packet", 211, _hex("01005c0000"))
	await process_frame
	_expect(bob.get_node_or_null("TitleLine") == null
		or not (bob.get_node("TitleLine") as Label3D).visible,
		"an empty title takes the label off the actor")

	# Hiding the overhead block hides the title with it, or a player who turned
	# names off would still see half of one.
	app_state.call("_on_packet", 211, _hex("01005c007468652043756c6c657200"))
	await process_frame
	bob.call("set_nameplate_visible", false)
	_expect(not (bob.get_node("TitleLine") as Label3D).visible,
		"the title follows the nameplate's own visibility")

	print("achievements window tests: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _hex(value: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		bytes.append(value.substr(index, 2).hex_to_int())
	return bytes

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error(label)
	return value
