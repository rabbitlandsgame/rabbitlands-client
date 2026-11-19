extends "res://tests/test_quest_next_step_guidance.gd"

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	var app: Node = root.get_node("AppState")
	app.authenticated = true; app.current_map = "landfall"
	var state := raid_snapshot()
	state.key = "magic"; state.shelves.chapter = "magic"
	var blocker := "Mix the stabilizer before fitting it to the apparatus."
	state.targets.append({"id":"install", "object_id":61994, "tile":[101,100],
		"label":"Fit the stabilizer", "enabled":false, "detail":blocker})
	state.targets.append({"id":"done", "object_id":61995, "tile":[101,100],
		"label":"Check the apparatus", "enabled":false, "completed":true, "detail":"Already checked."})
	state.targets.append({"id":"wait", "object_id":61996, "tile":[101,100],
		"label":"Wait (current order)", "enabled":false})
	state.targets[0].detail = "Return to Ilka."
	var original := state.duplicate(true)
	expect(Guidance.work_targets(state).map(func(row: Dictionary) -> String: return str(row.id)) == ["storage"],
		"blocked prerequisites never become ready world actions")
	expect(Guidance.card_targets(state).map(func(row: Dictionary) -> String: return str(row.id)) == ["storage", "install"],
		"the card includes only unfinished blocked actions with an authoritative explanation")
	var hud: Control = load("res://src/ui/campaign_hud.gd").new(); root.add_child(hud)
	var uses: Array = []
	hud.target_requested.connect(func(id: int, _tile: Vector2i, _near: bool) -> void: uses.append(id))
	hud.apply_state(state, Vector2i(100,100), "landfall")
	expect(hud._targets.get_child_count() == 2, "completed sites, existing orders and Return do not clutter the card")
	var blocked: Button = hud._targets.get_child(1)
	expect(blocked.disabled and blocked.text == "Not ready · Fit the stabilizer\n" + blocker,
		"a blocked action names its actual prerequisite without offering to walk there")
	expect(blocked.tooltip_text == blocker, "the same native reason remains available as a tooltip")
	hud._request_target("install",61994)
	expect(uses.is_empty(), "a stale or manually dispatched blocked action cannot emit a work request")
	var object := MapObject3D.new(); root.add_child(object)
	object.configure({"object_id":61994,"kind":EloriaProtocol.MAP_OBJECT_INTERACTIVE,"x":101,"y":100,
		"label":"Fit the stabilizer"}, CoordinateAdapter.new(), {"interactives":{"roles":{},"models":{}}})
	var guidance := Guidance.new(); root.add_child(guidance)
	guidance.apply_snapshot(state,{61994:object},{},"landfall",Vector2i(100,100),true,false)
	expect(not object.get_node("Ring").visible and object.collision_layer == 0 \
		and not bool(object.get_meta("campaign_work_available",true)),
		"explaining a blocker in the card leaves the world circle and collision unavailable")
	expect(state == original, "readiness presentation never changes authoritative quest state")
	state.targets[2].enabled = true
	hud.apply_state(state,Vector2i(100,100),"landfall")
	expect(not hud._targets.get_child(1).disabled and hud._targets.get_child(1).text == "Fit the stabilizer",
		"the next native update makes the action ordinarily usable")
	hud._request_target("install",61994)
	expect(uses == [61994], "the newly ready action uses the normal work request")
	guidance.apply_snapshot(state,{61994:object},{},"landfall",Vector2i(100,100),true,false)
	expect(object.get_node("Ring").visible and object.collision_layer == MapObject3D.PICK_LAYER,
		"world work becomes available only after native readiness changes")
	for variable: String in ["RL_SHELVES_READINESS_EVIDENCE", "RL_RESCUE_READINESS_EVIDENCE"]:
		var path := OS.get_environment(variable)
		if path.is_empty(): continue
		var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		var records: Array = raw.get("records",[]) if raw is Dictionary else raw if raw is Array else []
		expect(not records.is_empty(), "current native readiness evidence is present")
		for record: Dictionary in records:
			var native: Dictionary = record.get("snapshot",record)
			var label := str(record.get("label",record.get("case","native")))
			var decoded := EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
			expect(decoded.type == "campaign", label + " decodes through the actual campaign protocol: " + str(decoded.get("error","")))
			if decoded.type != "campaign": continue
			var current_map := str(record.get("current_map",native.get("map","landfall")))
			var decoded_state: Dictionary = decoded.state
			hud.apply_state(decoded_state,Vector2i.ZERO,current_map)
			var cards := Guidance.card_targets(decoded_state)
			var ready := Guidance.work_targets(decoded_state)
			for target: Dictionary in cards:
				if bool(target.get("enabled",true)): continue
				expect(target not in ready and not bool(target.get("completed",false)) \
					and not str(target.get("detail","")).is_empty(), label + " blocked card stays separate from ready world actions")
				var found := false
				for child: Node in hud._targets.get_children():
					if child is Button and child.text.begins_with("Not ready · " + str(target.get("label","")) + "\n"):
						found = true
						expect(child.disabled and child.text.contains(str(target.detail)) \
							and not child.text.contains("Go to ·"),label + " visibly explains its native blocker")
				expect(found,label + " keeps the blocked next step readable")
	guidance.clear()
	for node: Node in [guidance,object,hud]: node.queue_free()
	await process_frame; await process_frame
	print("Quest readiness card: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
