extends "res://tests/test_quest_first_pass_cinematics.gd"
## Retained supply rewards are delivered at Ilka's shop. Their dialogue must
## close that visit without sending the player back to the same shop again.
const Supplies := preload("res://tests/test_campaign_shelves.gd")

func review_rows() -> Array:
	var path := OS.get_environment("RL_SHELVES_READINESS_EVIDENCE")
	if not path.is_empty():
		var native: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		expect(native is Array, "the optional native evidence is a raw snapshot list")
		return native if native is Array else []
	var rows: Array = []
	for chapter: String in ["wind", "magic"]:
		var state := Supplies.snapshot()
		state.key = chapter; state.map = "landfall_town"; state.stage = "review"
		state.shelves.chapter = chapter; state.shelves.phase = "review"
		state.scene = {"id":"measure.shelves.resolved", "token":"review:" + chapter,
			"requires_ack":true, "variant":chapter,
			"actors":{"mentor":20,"protagonist":1,"recipient":1}}
		rows.append(state)
	return rows

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	var definition: Dictionary = Scene.scene_definitions()["measure.shelves.resolved"]
	for chapter: String in ["school", "wind", "magic", "death", "frost"]:
		var line: String = definition.lines[0].variants[chapter]
		expect(not "return to The True Note" in line,
			chapter + " thanks the player at Ilka's shop without sending them back there")
	expect(not "ordinary mixes" in str(definition.lines[0].variants.magic),
		"Ilka's spoken thanks does not interrupt the reward with mixing-odds bookkeeping")
	var covered: Dictionary = {}
	for raw: Dictionary in review_rows():
		if str(raw.get("scene", {}).get("id", "")) != "measure.shelves.resolved": continue
		var chapter := str(raw.get("key", ""))
		if chapter not in ["wind", "magic"]: continue
		covered[chapter] = true
		var decoded := EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_CAMPAIGN_STATE,
			JSON.stringify(raw).to_utf8_buffer())
		expect(decoded.type == "campaign", chapter + " hub reward passes the actual packet decoder")
		if decoded.type != "campaign": continue
		var state: Dictionary = decoded.state
		expect(state.map == "landfall_town" and state.stage == "review"
			and state.shelves.phase == "review" and state.scene.variant == chapter,
			chapter + " reward is already at the shop in the authoritative snapshot")
		var f := fixture(); f.scene.cancel("replace_fixture"); f.scene.reset_session(); f.acks.clear()
		f.state = state
		var bindings: Dictionary = state.scene.get("actors", state.actors)
		var local_id := int(bindings.protagonist)
		f.nodes = {local_id:f.player, int(bindings.mentor):f.mentor}
		var actions: Array = []
		f.scene.choice_requested.connect(func(id: String) -> void: actions.append(id))
		f.scene.inspection_requested.connect(func(action: String) -> void: actions.append(action))
		var unchanged := JSON.stringify(state)
		var held: Transform3D = f.rig.camera.global_transform
		f.scene.update(0, state, f.rig, f.nodes, local_id, "landfall_town", true)
		expect(f.scene.playing and f.scene._dialogue.portrait_visible()
			and f.scene._dialogue.speaker_label.text == "Ilka Tarn"
			and f.scene._dialogue._actor.get_ref() == f.mentor,
			chapter + " reward immediately shows Ilka's existing portrait")
		expect(f.scene._caption.text == definition.lines[0].variants[chapter]
			and not "return to The True Note" in f.scene._caption.text,
			chapter + " native reward selects the corrected authored thanks")
		expect(f.rig.camera.global_transform.is_equal_approx(held) and f.scene._line_continue.visible,
			chapter + " reward keeps the established view and immediately offers Continue")
		expect(f.scene.continue_dialogue() and not f.scene.continue_dialogue()
			and f.acks == [[state.scene.token, "finished"]] and not f.scene.blocks_input()
			and f.scene._scene_handoff.is_empty(),
			chapter + " one Continue closes this completed visit once without a false handoff")
		expect(actions.is_empty() and JSON.stringify(state) == unchanged,
			chapter + " presentation changes no native reward or quest proof")
		expect(f.scene.request_replay(state, "landfall_town"),
			chapter + " completed thanks remains available for explicit replay")
		f.scene.update(0, state, f.rig, f.nodes, local_id, "landfall_town", true)
		expect(f.scene.playing and f.scene.is_replaying()
			and f.scene._caption.text == definition.lines[0].variants[chapter],
			chapter + " replay retains the corrected reward line")
		f.scene.continue_dialogue()
		expect(f.acks.size() == 1 and actions.is_empty() and JSON.stringify(state) == unchanged,
			chapter + " replay neither claims another reward nor acknowledges the original again")
		dispose(f); await process_frame
	expect(covered.has("wind") and covered.has("magic"), "both retained Wind and Magic hub rewards are exercised")
	print("Supply hub review: %d checks; %d failures" % [checks, failures])
	quit(1 if failures else 0)
