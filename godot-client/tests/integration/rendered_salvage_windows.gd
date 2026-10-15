extends SceneTree
## Rendered evidence for the party window and the quest journal's finished half.
##
## Every payload below is the exact output of the server's own builder in
## eloria/protocol.py, so a window can only appear here if it is drawing what
## the real server sends. Each frame is checked for real colour variation, so a
## dummy or black frame cannot pass as evidence.

const SCREEN_SIZE := Vector2i(1280, 720)

var _artifacts := ""
var _failures := 0
var _main: Control
var _app_state: Node
var _windows: Control

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/salvage")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	await _open_client()

	# A party of four across three maps, one of them offline. The window's
	# whole reason to exist is the member who is not on your screen. The
	# offline row carries zeros and no map because that is exactly what
	# `party_rows` sends for a member with no session behind them.
	_send(240,
		"0104077800b40028003c000003e0014b656c6c616e00666f75725f6761746573"
		+ "00015a0096000a0037009a00b6004d6172656e006d6972726f72686f6c640001"
		+ "1e00c8000000450019029601546f6d61205265656400677265795f6d6f6f7273"
		+ "00000000000000000000000000004976657420536f6d65720000000000")
	await _settle()
	_expect(_windows.party_panel.visible
		and _windows.party_rows.get_child_count() == 4,
		"the party window is on screen with all four members")
	await _capture("party-window.png",
		"a party of four: vitals and location for people on three other maps,"
			+ " and one member dimmed and marked offline")

	# An invitation with no party: the window carries only the two answers.
	_send(240, "00004b656c6c616e004b00")
	await _settle()
	_expect(_windows.party_invite_row.visible,
		"a pending invitation is on screen")
	await _capture("party-invitation.png",
		"an invitation with no party behind it yet, offering only accept and"
			+ " decline")

	_windows.close_all()
	_send(241,
		"0300426567696e6e6572205475746f7269616c0049736c61205072696d6100"
		+ "596f75206c6561726e656420746f206d6f76652c2066696768742c20676174686572"
		+ "20616e64206d69782e0054686520466f75722047617465732077616c6b7468726f75"
		+ "676800466f757220476174657300596f7520776572652073686f776e207468652063"
		+ "69747920616e64207768617420697420697320666f722e00546865205765737465726e"
		+ "20526f6164004e796d61726100596f752077616c6b65642074686520726f6164207765"
		+ "737420616e642063616d65206261636b2e00")
	_send(224, "0000")
	await _settle()
	_windows.toggle_quest_journal()
	_windows._on_quest_view(true)
	await _settle()
	_expect(_windows.quest_panel.visible and _windows.quest_list.item_count == 3,
		"the completed half of the journal is on screen")
	await _capture("quest-archive.png",
		"the journal's finished half: three completions the server holds, so"
			+ " they survive a reinstall")

	# Worn goods. Command 19 fills the inventory; 243 states which of those
	# slots hold something that has worn down. Slots 0, 2 and 5 are marked, so
	# the cuirass, the cloak and the bones are drawn mirrored with the orange
	# mark while their neighbours are untouched - which is the comparison the
	# screenshot exists to make.
	_windows.close_all()
	# Regenerated after config/eloria/items.txt renumbered 57 image ids: Green
	# Cloak moved 52 -> 49 and Healing Tonic 4 -> 3. A hex fixture encodes ids
	# rather than names, so a renumber silently repoints it at whatever
	# artwork now sits at the old number - the assertions cannot tell, which
	# is why this one is regenerated from the catalog rather than hand-edited.
	#
	# Run `godot --headless --path . --import` before rendering this. All 21
	# atlas sheets are committed, but `.import` files are gitignored
	# project-wide on purpose - the project is imported by CI - so a fresh
	# checkout has no import metadata for any asset and high image ids
	# resolve to nothing until that step has run. The sword here is id 374,
	# in sheet 15, which is exactly the range that needs it.
	_send(19, "0676000100000000027601010000000102310001000000020201000c000000"
		+ "030e03000100000004060b00010000000506")
	_send(243, "2500000000000000")
	await _settle()
	_main.call("_sync_inventory")
	var inventory_panel: Control = _main.get("inventory_panel") as Control
	if inventory_panel != null:
		inventory_panel.show()
	await _settle()
	_expect(_app_state.get("worn_slots_mask") == 37,
		"the worn-slot mask arrived")
	await _capture("worn-items.png",
		"three worn items among six: mirrored artwork with an orange"
			+ " exclamation in the lower-right corner, as Eternal Lands draws it")

	_app_state.set("authenticated", false)
	_main.queue_free()
	await process_frame
	print("rendered salvage windows: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

func _open_client() -> void:
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	(_main.get_node("GameView") as Control).show()
	(_main.get_node("LoginPanel") as Control).hide()
	_app_state = root.get_node("/root/AppState")
	_app_state.set("authenticated", true)
	_windows = _main.get("extension_windows") as Control
	_expect(_windows != null, "the extension windows are built")
	await _settle()

func _send(command: int, hex: String) -> void:
	_app_state.call("_on_packet", command, _hex_bytes(hex))

func _settle() -> void:
	for _frame: int in range(4):
		await process_frame

func _hex_bytes(value: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		bytes.append(value.substr(index, 2).hex_to_int())
	return bytes

func _capture(name: String, description: String) -> void:
	await process_frame
	var image: Image = root.get_texture().get_image()
	_expect(image != null and image.get_size() == SCREEN_SIZE,
		"%s is a full %dx%d frame" % [name, SCREEN_SIZE.x, SCREEN_SIZE.y])
	if image == null:
		return
	_expect(_has_colour_variation(image),
		"%s contains rendered colour variation rather than a dummy frame" % name)
	_expect(image.save_png(_artifacts.path_join(name)) == OK,
		"%s is written" % name)
	print("capture ", name, ": ", description)

func _has_colour_variation(image: Image) -> bool:
	var lowest := 2.0
	var highest := -1.0
	for y: int in range(0, image.get_height(), 8):
		for x: int in range(0, image.get_width(), 8):
			var luminance: float = image.get_pixel(x, y).get_luminance()
			lowest = minf(lowest, luminance)
			highest = maxf(highest, luminance)
	return highest - lowest > 0.02

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
