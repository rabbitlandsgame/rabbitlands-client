extends "res://tests/test_campaign_scene_recovery.gd"
## Exercise the real dialogue controller with explicit native chapter variants.
const SupplyFixture := preload("res://tests/test_campaign_shelves.gd")

func essence_fixture(chapter: String, identity: String) -> Dictionary:
	var f := fixture()
	f.scene.set_auto_dialogue(false,false)
	f.state = SupplyFixture.snapshot()
	f.state.key = chapter
	f.state.run_id = "essence-dialogue-" + chapter
	f.state.stage = "arrival"
	f.state.shelves.chapter = chapter
	f.state.shelves.phase = "arrival"
	f.state.actors = {"mentor":20,"worker":20,"protagonist":1,"recipient":1}
	f.state.scene = {"id":identity,"token":chapter+":"+identity,"requires_ack":true,
		"variant":chapter,"actors":f.state.actors.duplicate(true)}
	return f

func check_dialogue(chapter: String, identity: String, expected: String) -> void:
	var f := essence_fixture(chapter,identity)
	var before: Transform3D = f.rig.camera.global_transform
	var native := JSON.stringify(f.state)
	tick(f,0.1)
	expect(f.scene.playing and f.scene._caption.text.contains(expected) and f.scene._line_continue.visible,chapter+" selects its actual "+identity.get_slice(".",3)+" dialogue with immediate Continue")
	expect(f.scene._uses_gameplay_camera() and f.rig.camera.global_transform.is_equal_approx(before),chapter+" keeps the established gameplay framing")
	tick(f,30)
	expect(f.scene.is_dialogue_waiting() and f.scene._line_continue.visible,chapter+" retains manual Continue instead of consuming the line")
	expect(JSON.stringify(f.state)==native,chapter+" presentation does not alter native quest progress")
	dispose(f)
	await process_frame

func native_dialogue_checks() -> void:
	var path := OS.get_environment("RL_ESSENCE_DIALOGUE_NATIVE")
	if path.is_empty():return
	var records: Array = JSON.parse_string(FileAccess.get_file_as_string(path))
	expect(not records.is_empty(),"native essence scene captures are present")
	for row: Dictionary in records:
		var native: Dictionary = row.get("snapshot",row)
		var decoded := EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
		expect(decoded.type=="campaign","native "+str(native.get("key",""))+" scene passes the actual decoder: "+str(decoded.get("error","")))
		if decoded.type!="campaign":continue
		var state: Dictionary = decoded.state
		var scene: Dictionary = state.get("scene",{})
		if scene.is_empty():continue
		expect(str(scene.get("variant",""))==str(state.key),"native live/replayed scene carries its chapter variant")
		var definitions: Dictionary = Scene.scene_definitions()
		if not definitions.has(str(scene.id)):continue
		var lines: Array = (definitions[str(scene.id)] as Dictionary).get("lines",[])
		if lines.is_empty():continue
		var variants: Dictionary = (lines[0] as Dictionary).get("variants",{})
		if not variants.has(str(state.key)):continue
		var f := essence_fixture(str(state.key),str(scene.id))
		# Keep the real packet's scene text/variant and choice context while binding
		# its native logical roles to the ready headless fixture bodies.
		f.state = state.duplicate(true)
		f.state.actors = {"mentor":20,"worker":20,"protagonist":1,"recipient":1}
		f.state.scene.actors = f.state.actors.duplicate(true)
		f.state.scene.requires_ack = true
		tick(f,0.1,str(state.map))
		expect(f.scene.playing and f.scene._caption.text==str(variants[str(state.key)]),"actual native "+str(state.key)+" packet selects the authored chapter text")
		dispose(f)
		await process_frame

func run() -> void:
	create_timer(90).timeout.connect(func() -> void:push_error("Essence dialogue checks timed out");quit(1))
	root.size = Vector2i(1280,720)
	root.get_node("Network").block_for_hud_preview()
	for family: String in ["fire","water"]:
		var chapters: Array = ["fire","fire_coal","fire_sapper"] if family=="fire" else ["water","water_cutters","water_barge","water_keeper"]
		var expected_briefs: Array = ["stranded inside Blackcut","Coal out of Lantern Mine","Krek Cinderhook"] if family=="fire" \
			else ["charging the cutters","first 400 Kelp","shipment home","upper gatehouse"]
		for index: int in chapters.size():
			await check_dialogue(str(chapters[index]),"measure.shelves."+family+".brief",str(expected_briefs[index]))
	for row: Array in [
		["fire","Flint we've secured"],["fire_coal","marked lift repairs"],["fire_sapper","Krek is still"],
		["water","marked stations"],["water_cutters","Work starts the cutting"],
		["water_barge","boat is where we left it"],["water_keeper","Veyra still holds"]]:
		var family := "fire" if str(row[0]).begins_with("fire") else "water"
		await check_dialogue(str(row[0]),"measure.shelves."+family+".resume",str(row[1]))
	for row: Array in [
		["fire_coal","fire","Ten thousand Coal"],["water_cutters","water","Four hundred Kelp"],
		["water_barge","water","cargo arrived"]]:
		await check_dialogue(str(row[0]),"measure.shelves."+str(row[1])+".report",str(row[2]))
	for row: Array in [
		["fire_coal","fire","last Coal load"],["fire_sapper","fire","Krek is finished"],
		["water_cutters","water","Kelp and Watercress shipment"],["water_barge","water","final landing"]]:
		await check_dialogue(str(row[0]),"measure.shelves."+str(row[1])+".done",str(row[2]))
	var barge := essence_fixture("water_barge","measure.shelves.water.entry_water_barge")
	barge.state.scene.choice = {"id":"shelves_water_route","title":"Which passage?","owner":"Aster", "owner_is_you":true,
		"can_choose":true,"selected":"","response":"","options":[
			{"id":"sheltered","label":"Sheltered","detail":"Defended obstructions"},
			{"id":"coastal","label":"Coastal","detail":"Exposed ambushes"}]}
	var before: Transform3D = barge.rig.camera.global_transform
	tick(barge,0.1)
	expect(barge.scene._caption.text.contains("Heal Target helps the crew, not the hull") \
		and barge.scene._caption.text.contains("Halt and clear the attackers") \
		and barge.scene._caption.text.contains("One Wood Plank restores forty hull"),"the settled barge briefing teaches actual pilot and repair conditions")
	expect(barge.scene._caption.text.contains("She needs to be on her feet to pilot"),"Ada's departure requirement is explained before choosing the route")
	root.size = Vector2i(720,480)
	for _i: int in range(4):await process_frame
	tick(barge,0)
	expect(root.get_visible_rect().encloses(barge.scene._bottom.get_global_rect()) \
		and root.get_visible_rect().encloses(barge.scene._caption.get_global_rect()),"the complete barge briefing and its actions fit a small viewport")
	expect(barge.scene._line_continue.visible and barge.scene.continue_dialogue(),"the added instructions remain one line that can be continued immediately")
	tick(barge,0.1)
	expect(barge.scene.choice_context().waiting and barge.scene._choice_dialog.option_buttons.size()==2,"the existing two route choices remain interactive after the instruction")
	barge.scene._choice_dialog.option_buttons.sheltered.pressed.emit()
	expect(barge.events.choices==["sheltered"] and str(barge.state.scene.choice.selected).is_empty(),"the route button emits only its ordinary native choice request")
	expect(barge.rig.camera.global_transform.is_equal_approx(before),"the briefing and player options share the same settled camera")
	dispose(barge)
	await process_frame
	await native_dialogue_checks()
	print("Essence scene dialogue: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
