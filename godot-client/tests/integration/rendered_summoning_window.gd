extends SceneTree
## Rendered evidence for the summoning window.
##
## The headless suite proves what the window says; this proves it can be read.
## The window is built entirely in code - the rows are Buttons with a container
## pinned across each one - so nothing but a frame shows whether the icon, the
## name, the requirements and the costs actually land in their four places
## instead of on top of each other.
##
## Three states are captured, because telling them apart is the window's job:
## a summoner who can afford one of the three and not the other two; the same
## window once the server has granted the skill, the nexus and the reagents
## for all three; and the same again against a server that does not name the
## inventory slots, where a reagent whose artwork is shared cannot be picked
## and the window says so rather than guessing.

const SCREEN_SIZE := Vector2i(1280, 720)

var _artifacts := ""
var _failures := 0
var _main: Control
var _app_state: Node
var _window: Control

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/summoning")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	await _open_client()

	# A novice summoner: the skill for the otter, none of the nexus the turtle
	# wants, and nothing on hand for the stag. All three rows are drawn; two
	# are dimmed and say why where their ingredients would be.
	_stats({"summoning": 5, "animal_nexus": 0, "food": 40, "ether": 60})
	# The otter's reagents only, taken from the catalog rather than written
	# out: the server has renumbered its image ids before now, and a fixture
	# that spells them out keeps passing against artwork nobody uses.
	_stock([0])
	_main.call("_on_summoning_button_pressed")
	await _settle()
	_expect(bool(_window.call("is_open")), "the summoning window opened")
	var rows: VBoxContainer = _window.get_node(
		"SummoningWindow/SummoningBody/SummoningScroll/SummonRows") as VBoxContainer
	_expect(rows.get_child_count() == 3, "all three summons are drawn")
	await _capture("summoning-window.png",
		"three summons: the otter affordable and lit, the stag and the turtle"
			+ " dimmed with the reason where their ingredients would be")

	# The server grants the skill, the nexus and every reagent, and names the
	# slots. All three light - including the stag, whose Medium Hide shares its
	# picture with four other pelts and whose Sage shares one with
	# Rosemary. Before the slot names it was refused outright, because a
	# client told only an image id cannot say which pelt it is holding.
	_stats({"summoning": 30, "animal_nexus": 2, "food": 40, "ether": 60})
	_stock([0, 1, 2])
	_window.call("sync")
	await _settle()
	for row: Node in rows.get_children():
		_expect(not (row as Button).disabled,
			"%s is clickable once the server has granted everything" % row.name)
		# The window is only worth opening if the costs can be read off it. Both
		# lines trim with an ellipsis rather than overflowing, so a panel too
		# narrow for the longest reagent list fails quietly - here is where that
		# is caught, with the layout settled and the real font measured.
		for line: String in ["Requirements", "Cost"]:
			var label: Label = row.get_node("Row/Asks/" + line) as Label
			var needed: float = label.get_theme_font("font").get_string_size(
				label.text, HORIZONTAL_ALIGNMENT_LEFT, -1.0,
				label.get_theme_font_size("font_size")).x
			_expect(needed <= label.size.x,
				"%s's %s fits without an ellipsis: %.0f of %.0f px for %s"
				% [row.name, line, needed, label.size.x, label.text])
	await _capture("summoning-window-stocked.png",
		"the same window with the skill, the nexus, the reagents in hand and"
			+ " the slots named: every row lit and listing what it spends,"
			+ " the stag included")

	# Without the slot names the stag is refused rather than guessed at, which
	# is what a server that does not send them still gets.
	var stag: Button = rows.get_node("SummonRow%d" % (
		(_window.call("summon_recipes") as Array[int])[1])) as Button
	(_app_state.get("inventory_names") as Dictionary).clear()
	_window.call("sync")
	await _settle()
	_expect(stag.disabled
		and str((stag.get_node("Row/Asks/Requirements") as Label).text)
			.contains("shares legacy artwork"),
		"the stag says what holds it back when the slots are unnamed")
	await _capture("summoning-window-unnamed.png",
		"the same window against a server that does not name the slots: the"
			+ " stag refused rather than guessed at, because five pelts share"
			+ " one picture")

	_app_state.set("authenticated", false)
	_main.queue_free()
	await process_frame
	print("rendered summoning window: ",
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
	_window = _main.get("summoning_window") as Control
	_expect(_window != null, "the summoning window is built")
	await _settle()

## The server's last word about the player, as the window reads it.
func _stats(values: Dictionary) -> void:
	var stats: Dictionary = _app_state.get("stats") as Dictionary
	stats.clear()
	stats.merge(values)

## Inventory as AppState holds it, stocked for the summons named by their
## position in the window's own list: every reagent those recipes ask for, one
## to a slot, at the image id the catalog carries.
func _stock(rows: Array[int]) -> void:
	var inventory: Dictionary = _app_state.get("inventory") as Dictionary
	inventory.clear()
	var names: Dictionary = _app_state.get("inventory_names") as Dictionary
	names.clear()
	var listed: Array[int] = _window.call("summon_recipes") as Array[int]
	var catalog: ManufacturingCatalog = _window.get("catalog") as ManufacturingCatalog
	var seen: Dictionary = {}
	for row: int in rows:
		for ingredient_value: Variant in catalog.recipe(
				listed[row]).get("ingredients", []) as Array:
			var ingredient: Dictionary = ingredient_value as Dictionary
			var item: String = str(ingredient.get("name", ""))
			if seen.has(item):
				continue
			seen[item] = true
			var slot: int = inventory.size()
			inventory[slot] = {
				"image_id": int(ingredient.get("imageId", -1)), "quantity": 20}
			# The server names every slot it sends; that is what lets two items
			# sharing one picture be told apart.
			names[slot] = item

func _settle() -> void:
	for _frame: int in range(4):
		await process_frame

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
