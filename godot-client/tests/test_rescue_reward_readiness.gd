extends "res://tests/test_quest_first_pass_cinematics.gd"
## An unclaimed reward without participation must not become an unanswered,
## disabled weapon question. Native eligibility and recorded rewards stay native.
const Rescue := preload("res://tests/test_campaign_rescue.gd")

func reward_choice(selected := "", available := false) -> Dictionary:
	return {"id":"rescue_reward", "title":"Choose your rescue reward", "owner":"Guest",
		"owner_is_you":true, "can_choose":available, "selected":selected,
		"response":"The sword is yours." if selected == "sword" else "",
		"options":[{"id":"sword","label":"Sword","detail":"Melee weapon"},
			{"id":"bow","label":"Bow","detail":"Ranged weapon"},
			{"id":"wand","label":"Wand","detail":"Magic weapon"}]}

func records() -> Array:
	var path := OS.get_environment("RL_RESCUE_REWARD_READINESS_EVIDENCE")
	if not path.is_empty():
		var bundle: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
		return bundle.get("records", [])
	var state := Rescue.snapshot()
	state.stage = "reward"; state.rescue.stage = "reward"
	state.rescue.daughter = {"caged":false,"rescued":true}
	state.actors = {"mother":20,"daughter":21,"protagonist":1,"recipient":1}
	state.scene = {}
	return [{"label":"reward-outside-no-contribution","snapshot":state}]

func bind_native(f: Dictionary, state: Dictionary) -> int:
	var bindings: Dictionary = state.get("actors", {})
	var local_id := int(bindings.get("recipient", bindings.get("protagonist", 1)))
	f.nodes = {local_id:f.player}
	for role: String in bindings:
		var id := int(bindings[role])
		if f.nodes.has(id): continue
		if role == "mother": f.nodes[id] = f.mentor
		else:
			var body := Ready.Actor.new(); f.scene.add_child(body); f.nodes[id] = body
	return local_id

func run() -> void:
	create_timer(45).timeout.connect(func() -> void: push_error("Rescue reward readiness timed out"); quit(1))
	root.get_node("Network").block_for_hud_preview()
	var covered := false
	for record: Dictionary in records():
		var label := str(record.get("label", ""))
		if label not in ["reward-outside-no-contribution", "reward-selected-contributor",
				"reward-aftermath-no-contribution", "reward-complete-no-contribution"]: continue
		var native: Dictionary = record.snapshot
		var native_before := JSON.stringify(native)
		var packet := JSON.stringify(native).to_utf8_buffer()
		if record.has("packet191_base64"):
			var wire := Marshalls.base64_to_raw(str(record.packet191_base64))
			packet = wire.slice(3)
		var decoded := EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_CAMPAIGN_STATE, packet)
		expect(decoded.type == "campaign", label + " passes the actual command-191 packet decoder: " + str(decoded.get("error", "valid")))
		if decoded.type != "campaign": continue
		var state: Dictionary = decoded.state
		var before := JSON.stringify(state)
		var f := fixture(); f.scene.cancel("replace_fixture"); f.scene.reset_session(); f.acks.clear()
		var local_id := bind_native(f, state)
		var actions: Array = []
		f.scene.choice_requested.connect(func(id: String) -> void: actions.append(id))
		f.scene.event_requested.connect(func(id: String) -> void: actions.append(id))
		f.scene.inspection_requested.connect(func(action: String) -> void: actions.append(action))
		if label == "reward-outside-no-contribution":
			covered = true
			expect(not bool(state.rescue.reward.can_choose) and not bool(state.rescue.reward.claimed)
				and str(state.rescue.reward.choice).is_empty() and (state.scene as Dictionary).is_empty(),
				"the ineligible native helper has no unanswerable weapon-choice scene")
			f.scene.update(0, state, f.rig, f.nodes, local_id, str(state.map), true)
			expect(not f.scene.is_active() and not f.scene.blocks_input() and f.acks.is_empty(),
				"a late helper remains in normal play without an invented completion acknowledgement")
			# Model a film already open before this authoritative replacement.
			# The pending-view copy is a presentation fixture, never native proof.
			f.scene.reset_session(); f.acks.clear()
			var viewing: Dictionary = state.duplicate(true)
			viewing.scene = {"id":"measure.rescue.resolved", "token":str(state.run_id) + ":measure.rescue.resolved",
				"requires_ack":true, "actors":state.actors, "choice":reward_choice()}
			f.scene.update(0, viewing, f.rig, f.nodes, local_id, str(state.map), true)
			f.scene.skip(); f.scene.update(0, viewing, f.rig, f.nodes, local_id, str(state.map), true)
			expect(f.scene._choice_waiting and actions.is_empty(),
				"the pre-existing unavailable-question fixture reaches its real choice barrier without choosing")
			f.acks.clear()
			f.scene.update(0, state, f.rig, f.nodes, local_id, str(state.map), true)
			expect(not f.scene.is_active() and not f.scene.blocks_input() and not f.scene._choice_dialog.visible
				and f.scene._scene_handoff.is_empty(),
				"the native omission releases an already-open question without a successor fade")
			expect(f.acks == [[viewing.scene.token,"replaced"]] and actions.is_empty(),
				"replacement supplies no successful-viewing acknowledgement or native reward request")
		elif label == "reward-selected-contributor":
			expect(state.scene.id == "measure.rescue.resolved" and state.scene.choice.selected == "sword"
				and not bool(state.scene.choice.can_choose) and bool(state.rescue.reward.claimed),
				"an earned selected reward keeps its actual recorded weapon and response")
			f.scene.set_auto_dialogue(true, false)
			f.scene.update(30, state, f.rig, f.nodes, local_id, str(state.map), true)
			expect(f.scene.playing and f.scene._choice_completed and not f.scene._choice_waiting
				and f.scene._caption.text == state.scene.choice.response,
				"a pending native selected reward resumes its real reply without another weapon question")
			expect(actions.is_empty() and f.acks.is_empty(),
				"reading the selected reply cannot request another weapon or invent a viewing acknowledgement")
		else:
			expect(state.scene.id == "measure.rescue.shadow" and not state.scene.has("choice"),
				label + " preserves the shared Shadow without inventing a personal reward")
			f.scene.update(0, state, f.rig, f.nodes, local_id, str(state.map), false)
			expect(f.scene.pending == bool(state.scene.requires_ack) and not f.scene._choice_waiting
				and actions.is_empty() and f.acks.is_empty(),
				label + " respects native pending versus acknowledged history while its real cutaway loads")
		expect(JSON.stringify(state) == before and JSON.stringify(native) == native_before,
			label + " presentation changes no reward, participation proof or authoritative packet")
		dispose(f); await process_frame
	expect(covered, "the late helper's actual outdoor reward checkpoint is exercised")
	print("Rescue reward readiness: %d checks; %d failures" % [checks, failures])
	quit(1 if failures else 0)
