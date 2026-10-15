extends SceneTree
## The guide card for Signed Ashore (`signed_ashore_v1`), fed through the real
## decoder: its chapter label, Nesh's help button, a progress count for any
## fact that needs more than one, and a manufacture highlight that follows
## the recipe the server names. The Lantern's own card must not change.

var failures := 0
var main: Control

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func card(value: Dictionary) -> Dictionary:
	var decoded: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ELORIA_LANTERN_STATE, JSON.stringify(value).to_utf8_buffer())
	expect(decoded.get("type") == "lantern_tutorial", "the fixture frame decodes: " + str(decoded.get("error", "")))
	return decoded.get("state", {})

func run() -> void:
	create_timer(30).timeout.connect(func(): push_error("signed ashore guide fixture timed out"); quit(1))
	root.size = Vector2i(1280, 720)
	main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	var state: Node = root.get_node("AppState")
	root.get_node("Network").set_process(false)
	main.get_node("LoginPanel").hide()
	main.get_node("GameView").show()
	state.authenticated = true
	var guide: Control = main.lantern_guide

	var ashore := {"version": 1, "active": true, "tutorial": "signed_ashore", "chapter": "SIGNED ASHORE",
		"stage": 2, "total": 10, "scene": 2, "key": "grove", "title": "The Palace Grove",
		"hint": "Click an olive bush once.", "control": "world", "item": "Olive", "map": "landfall",
		"target_id": "olive_grove", "target": [124, 262], "required": 5, "count": 2,
		"flags": {"grove": false, "temple": false, "gate": false, "light": false}}
	guide.apply_state(card(ashore))
	expect(guide.visible and guide.card.visible, "an active chapter shows the card")
	expect(guide.chapter.text == "SIGNED ASHORE  ·  2 / 10", "chapter label is the chapter and its step: " + guide.chapter.text)
	expect(guide.help.visible and guide.help.text == "Ask Nesh", "Nesh answers for the chapter")
	expect(guide.skip.text == "Skip tutorial…", "the chapter is skipped, not left")
	expect(guide.instruction.text.ends_with("\nProgress: 2 / 5"), "a five-Olive fact counts: " + guide.instruction.text)
	var single := ashore.duplicate(true)
	single.required = 1
	guide.apply_state(card(single))
	expect(not guide.instruction.text.contains("Progress:"), "a single-action fact shows no count")

	# Step 6 mixes a Wood Plank before its Torch: the highlight follows the
	# named recipe, where the Lantern's card always means the Torch.
	var panel: Control = main.get_node("%ManufacturingPanel")
	var list: ItemList = main.get_node("%ManufacturingList")
	var mix_one: Control = main.get("manufacturing_mix_one")
	panel.show()
	list.clear()
	# Rows as main.gd labels them: readiness, output, skill and level.
	list.add_item("[Ready]  Wood Plank — Manufacturing 0")
	list.add_item("[Ready]  Torch — Manufacturing 0")
	var plank := ashore.duplicate(true)
	plank.merge({"stage": 6, "key": "made_by_hand", "title": "Made by Hand", "control": "manufacture",
		"item": "Wood Plank", "required": 1, "count": 0}, true)
	guide.apply_state(card(plank))
	list.select(1)
	expect(guide.control_for_step() == list, "with the Torch selected the card points back at the list")
	list.select(0)
	expect(guide.control_for_step() == mix_one, "with the Wood Plank selected the card points at Mix")
	var torch := plank.duplicate(true)
	torch.item = "Torch"
	guide.apply_state(card(torch))
	expect(guide.control_for_step() == list, "the Torch step waits for the Torch to be selected")
	list.select(1)
	expect(guide.control_for_step() == mix_one, "and then points at Mix")

	# The Lantern's card is unchanged: its label, no help button, the Torch
	# highlight whatever it names, and a count only on its four counted steps.
	var lantern := {"version": 1, "active": true, "stage": 7, "total": 28, "scene": 4,
		"key": "store_reed", "title": "Store the Reed", "hint": "Select Reed and Deposit.",
		"control": "manufacture", "item": "Wood Plank", "map": "lantern_reach", "target_id": "lower_cache",
		"target": [44, 70], "required": 3, "count": 0,
		"flags": {"crafted": false, "prepared": false, "repaired": false, "lit": false}}
	guide.apply_state(card(lantern))
	expect(guide.chapter.text == "THE LAST LANTERN  ·  7 / 28", "the Lantern keeps its label")
	expect(not guide.help.visible, "the Lantern's card has no help button")
	expect(not guide.instruction.text.contains("Progress:"), "the Lantern counts only its four counted steps")
	expect(guide.control_for_step() == mix_one, "the Lantern's manufacture step still means the Torch")
	panel.hide()

	print("signed ashore guide: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	quit(failures)
