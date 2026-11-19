extends "res://tests/test_quest_next_step_guidance.gd"

func click_button(button: Button) -> void:
	var point := button.get_global_rect().get_center()
	var motion := InputEventMouseMotion.new(); motion.position = point; root.push_input(motion,true)
	for pressed: bool in [true,false]:
		var event := InputEventMouseButton.new(); event.position = point
		event.button_index = MOUSE_BUTTON_LEFT; event.pressed = pressed; root.push_input(event,true)
	await settle()

func run() -> void:
	root.size = Vector2i(1280,720)
	root.get_node("Network").block_for_hud_preview()
	var app: Node = root.get_node("AppState"); app.authenticated = true; app.current_map = "landfall"
	var owner := Control.new(); root.add_child(owner)
	var hud: Control = load("res://src/ui/campaign_hud.gd").new(); root.add_child(hud)
	var guide: Control = load("res://src/ui/lantern_guide.gd").new(); root.add_child(guide)
	guide.configure(owner); guide.set_process(false); guide.attach_campaign(hud)
	var state := raid_snapshot(); state.key = "life"; state.title = "A Harvest Worth Defending"
	state.shelves.chapter = "life"; state.shelves.growers.raid = false
	state.shelves.growers.stored.sage = 6240; state.shelves.growers.carried = 760
	state.shelves.objectives = [{"id":"sage","label":"Store Sage with the crew","current":6240,"target":10000,"personal":false}]
	state.hint = "Protect the four harvesters until 10,000 Sage reaches crew storage."
	var before := state.duplicate(true)
	hud.apply_state(state,Vector2i(100,100),"landfall"); guide.apply_campaign(state); guide._process(0)
	await settle()
	var tracker: Control = guide.card
	expect(guide.visible and not guide.compact and not hud.is_visible_in_tree(), "gameplay begins with the slim card and keeps the full ledger closed")
	expect(tracker.objective.text == "Protect the Sage harvesters" and tracker.counter.text.contains("6,240 / 10,000") \
		and is_equal_approx(tracker.progress.value,62.4), "the small card shows the current action and real delivered progress")
	expect(tracker.size.y < 165 and not guide.chapter.is_visible_in_tree(), "the gameplay card omits the old expedition heading and large instruction stack: " + str(tracker.size))
	await click_button(guide.collapse); guide._process(0); await settle()
	expect(guide.compact and tracker.heading.text == "Guard Sage crew" and not tracker.objective.visible \
		and tracker._ribbon_counter.visible and tracker.size.y < 70, "collapse produces a one-line objective ribbon with its counter")
	await click_button(tracker.more)
	expect(tracker.more_is_open() and root.get_visible_rect().encloses(tracker._menu.get_global_rect()), "the real More button opens a bounded anchored menu")
	expect(tracker.instructions_button.visible and tracker.replay_button.visible and tracker.hide_button.visible \
		and tracker.untrack_button.visible and tracker.replay_button.disabled, "all four controls remain accessible and unavailable replay is explained")
	expect([tracker.instructions_button,tracker.replay_button,tracker.hide_button,tracker.untrack_button].all(
		func(button: Button) -> bool: return button.icon != null and button.icon.get_size() == Vector2(16,16)),
		"the selected icon list keeps a crisp native icon beside every named action")
	var replays: Array = []; hud.replay_requested.connect(func() -> void: replays.append(true))
	hud.set_replay_available(true,true); guide.apply_campaign(state); await settle()
	expect(tracker.more_is_open() and not tracker.replay_button.disabled and tracker.replay_button.text == "Retry scene", "snapshot refreshes preserve the open menu and update actual retry readiness")
	await click_button(tracker.replay_button)
	expect(replays == [true] and not tracker.more_is_open(), "the menu replay uses the existing local cinematic request once")
	await click_button(tracker.more); await click_button(tracker.instructions_button)
	expect(not guide.compact and guide._details_open and hud.is_visible_in_tree() and guide.instruction.is_visible_in_tree(), "Instructions expands the real quest controls from the ribbon")
	expect(tracker.details_close.is_visible_in_tree() and not hud._shelves.is_visible_in_tree() \
		and hud._inline_ledger.is_visible_in_tree() and hud._map_button.is_visible_in_tree(),
		"the inline foldout replaces duplicate field prose with facts and keeps its map action and close control")
	await click_button(tracker.details_close)
	expect(guide.visible and guide.is_campaign_tracked() and not guide._details_open and not hud.is_visible_in_tree(),
		"Close Instructions returns to the slim card without hiding or untracking the quest")
	await click_button(tracker.more); await click_button(tracker.instructions_button)
	var uses: Array = []; hud.target_requested.connect(func(id: int,_tile: Vector2i,_near: bool) -> void: uses.append(id))
	hud._request_target("storage",61992)
	expect(uses == [61992], "full instructions preserve the ordinary work dispatcher")
	state.targets[1].enabled = false
	hud.apply_state(state,Vector2i(100,100),"landfall"); guide.apply_campaign(state)
	hud._request_target("storage",61992)
	expect(uses == [61992], "an authoritative disabled update still rejects stale work requests")
	await click_button(tracker.more); await click_button(tracker.hide_button)
	expect(not guide.visible and guide.is_campaign_tracked(), "More Hide removes the card without untracking the quest")
	guide.apply_campaign(state); expect(not guide.visible,"a snapshot does not reopen a hidden tracker")
	guide.show_window(); await settle()
	await click_button(tracker.more); await click_button(tracker.untrack_button)
	expect(not guide.is_campaign_tracked() and not guide.visible, "More Untrack follows the original journal tracking behavior")
	guide.set_campaign_tracked(true); guide._details_open = false; guide._refresh(); await settle()
	for dimensions: Vector2i in [Vector2i(900,460),Vector2i(720,480)]:
		root.size = dimensions; root.content_scale_factor = 1.5
		guide._process(0); await settle(); tracker.open_more(); await settle()
		expect(root.get_visible_rect().encloses(tracker.get_global_rect()) \
			and root.get_visible_rect().encloses(tracker._menu.get_global_rect()), "the slim card and More fit a small scaled viewport")
		tracker.close_more()
	expect(before.shelves.growers.stored.sage == state.shelves.growers.stored.sage \
		and before.shelves.objectives == state.shelves.objectives, "presentation controls do not change native delivery progress")
	var evidence := OS.get_environment("RL_SLIM_RECOVERY_EVIDENCE")
	if not evidence.is_empty():
		var bundle: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(evidence))
		var records: Array = bundle.get("records",[])
		var native: Dictionary = records.filter(func(row: Dictionary) -> bool: return row.label == "downed-cage-owner")[0].snapshot
		var decoded := EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
		expect(decoded.type == "campaign","the current native downed-Elen state passes the actual decoder")
		if decoded.type == "campaign":
			state = decoded.state; app.current_map = state.map; root.size = Vector2i(1280,720); root.content_scale_factor = 1
			guide.compact = false; guide._details_open = false
			hud.apply_state(state,Vector2i.ZERO,state.map); guide.apply_campaign(state); guide._process(0); await settle()
			var heals: Array = []; hud.ally_heal_requested.connect(func(run_id: String,actor: int) -> void: heals.append([run_id,actor]))
			var patient: Dictionary = load("res://src/ui/campaign_ally_recovery.gd").patients(state,state.map)[0]
			expect(not hud.is_visible_in_tree() and hud._recovery_actions.is_visible_in_tree(), "the original guarded recovery control stays visible outside the closed ledger")
			await click_button(hud._recovery_actions.get_child(0))
			expect(heals == [[state.run_id,patient.actor_id]], "the slim Heal Target button emits the exact current native run and patient")
			guide.compact = true; guide._refresh(); await settle()
			expect(tracker.heading.text == "Heal " + str(patient.name),"a downed rescue ally retains a short actionable ribbon objective")
			await click_button(hud._recovery_actions.get_child(0))
			expect(heals.size() == 2, "an urgent recovery remains usable with the ribbon collapsed")
			hud._request_ally_heal("stale-run",patient.actor_id)
			expect(heals.size() == 2, "a stale run cannot dispatch from the recovery shortcut")
			hud.apply_state(state,Vector2i.ZERO,state.map,false,true); guide.apply_campaign(state)
			hud._request_ally_heal(state.run_id,patient.actor_id)
			expect(heals.size() == 2 and not guide.visible, "cinematic or other input blocking hides the card and rejects the shortcut")
	for node: Node in [guide,owner]: node.queue_free()
	await process_frame; await process_frame
	print("Slim quest tracker: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
