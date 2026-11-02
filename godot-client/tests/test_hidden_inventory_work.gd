extends SceneTree
## Per-packet work that has nothing to show while its window is closed: the
## reagent pouch catches up when the inventory is shown instead of resyncing on
## every inventory and actor packet; display names are sorted once, with the
## same result as sorting on every call; chat URL patterns are compiled once,
## with the same matches.
const ItemNames := preload("res://src/state/item_names.gd")
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: " + message)
	else:
		failures += 1
		push_error("FAIL: " + message)

## in_text as it was: every alias, longest first, sorted on each call.
static func in_text_unsorted(value: String) -> String:
	var names: Array = ItemNames.aliases().keys()
	names.sort_custom(func(a: String, b: String) -> bool: return a.length() > b.length())
	for name: String in names: value = value.replace(name, ItemNames.display(name))
	return value

func _run() -> void:
	var state := root.get_node("AppState")
	state.inventory = {133: {"image_id": 584, "quantity": 5}}
	state.inventory_names = {133: "Life Essence"}
	var inventory := Control.new()
	root.add_child(inventory)
	var pouch = load("res://src/ui/reagent_pouch.gd").new()
	inventory.add_child(pouch)
	await process_frame
	expect(str(pouch.references) == "[133]" and pouch.counts[0].text == "5", "a shown pouch lists its supplies")
	inventory.hide()
	state.inventory = {133: {"image_id": 584, "quantity": 7}, 134: {"image_id": 585, "quantity": 2}}
	state.state_changed.emit(&"inventory")
	state.state_changed.emit(&"actors")
	expect(str(pouch.references) == "[133]" and pouch.counts[0].text == "5" and pouch._sync_pending,
		"a hidden pouch defers inventory and actor packets")
	inventory.show()
	expect(str(pouch.references) == "[133, 134]" and pouch.counts[0].text == "7" and not pouch._sync_pending,
		"showing the inventory catches it up at once")
	state.inventory = {}
	state.state_changed.emit(&"inventory")
	expect(pouch.references.is_empty(), "a shown pouch still follows every packet")
	inventory.queue_free()
	await process_frame

	var names: Array = ItemNames.aliases().keys()
	expect(not names.is_empty(), "display names load")
	var sample := " / ".join(names.slice(0, 40)) + " and " + " ".join(names.slice(40))
	expect(ItemNames.in_text(sample) == in_text_unsorted(sample)
		and ItemNames.in_text("no item here") == "no item here",
		"in_text replaces names exactly as sorting on each call did")

	var line := "see https://rabbitlandsgame.com/news. (or www.example.org/a_(b)), not mail@www.x.org"
	var first: Array[String] = ConsoleCommands.urls_in(line)
	expect(first == ConsoleCommands.urls_in(line) and first.size() == 2
		and ConsoleCommands.web_url("https://bad host") == "" and ConsoleCommands.web_url("www.example.org") == "https://www.example.org",
		"chat URLs match the same with the patterns compiled once: %s" % [first])
	print("hidden inventory work: ", failures, " failures")
	quit(failures)
