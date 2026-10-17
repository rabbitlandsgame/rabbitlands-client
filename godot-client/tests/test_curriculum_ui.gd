extends SceneTree

var failures := 0

func check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error(label)

func _init() -> void:
	call_deferred("run")

func run() -> void:
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	var state := root.get_node("AppState")
	state.authenticated = true
	main.reference_window.toggle()
	var button: Button = main.reference_window.find_child("PracticeAdventures", true, false)
	check(button.text == "Ask about watch work", "Help directs the player to the NPC conversation")
	var combat := PackedByteArray([4,102,0,250,0,250,0,60,0,80,0,0,0,0])
	state._on_packet(227,combat)
	check(state.combat_state.active, "dodging keeps the encounter active")
	combat[0]=5
	state._on_packet(227,combat)
	check(not state.combat_state.active, "the server's end event clears combat before another summon")
	var guide: Control = main.lantern_guide
	guide.apply_state({"active":true,"tutorial":"followup","adventure":"The Watch Must Eat",
		"guide":"Ostrid","stage":1,"total":9,"key":"t01_0_harvest","title":"Gather Olive",
		"hint":"Gather the order.","control":"world","item":"Olive","required":5,"count":3})
	check(guide.instruction.text.contains("3 / 5"), "all counted line objectives show progress")
	check(guide.chapter.text.contains("THE WATCH MUST EAT"), "short quest title is visible")
	guide.apply_state({"active":true,"tutorial":"field_dispatch","stage":2,"total":7,
		"title":"The Watch Must Eat","hint":"Gather the order.","control":"world",
		"item":"Olive","required":6,"count":4})
	check(guide.chapter.text.contains("MAIN WORLD DISPATCH"), "public quests identify the main world")
	check(guide.instruction.text.contains("4 / 6"), "public quest counters are visible")
	check(not guide.instruction.text.contains("Separate practice"), "public quests show real-character instructions")
	check(guide.skip.text == "Hide guide", "hiding the guide does not abandon a public quest")
	var road := preload("res://src/world/road_scene.gd").new()
	root.add_child(road)
	var label := Label3D.new()
	road.add_child(label)
	road.resource_labels["7310"] = label
	road.apply_state({"resource_labels":{"7310":"Sage"}})
	check(label.visible and label.text == "Sage", "rebound practice resources have their actual names")
	road.apply_state({})
	check(not label.visible, "resource labels clear on departure")
	road.free()
	state.authenticated = false
	for i in range(4):await process_frame
	main.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("tutorial curriculum UI: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
