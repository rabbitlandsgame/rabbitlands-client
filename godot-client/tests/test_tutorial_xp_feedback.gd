extends SceneTree

const P := preload("res://src/network/protocol.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var state := load("res://src/state/app_state.gd").new() as Node
	var hud := load("res://tests/fixtures/tutorial_feedback_hud.gd").new() as Control
	var feedback: Array[Dictionary] = []
	state.floating_feedback_requested.connect(func(event: Dictionary) -> void:
		feedback.append(event)
		hud.call("_on_floating_feedback_requested", event))
	var practice := {"magic_exp":9876543210, "overall_exp":9876543250}
	var guide := {"version":1, "active":true, "key":"recall"}
	state.set("stats", practice.duplicate(true))
	state.set("lantern_tutorial", guide.duplicate(true))
	_expect(P.CLIENT_CAPABILITIES.has("tutorial_rewards_v1"), "bonus capability advertised")

	# The final Recall pays 60 Magic, its matching Overall, and 150 extra Overall.
	var award := {"version":1, "event":"experience", "permanent":true,
		"rewards":[{"skill":"magic", "amount":60}, {"skill":"overall", "amount":210}]}
	_send(state, award)
	_expect(feedback == [
		{"kind":"experience", "skill":"magic", "amount":60, "bonus":true, "permanent":true},
		{"kind":"experience", "skill":"overall", "amount":150, "bonus":true, "permanent":true}],
		"permanent bonus floats exact skill XP and only additional Overall XP")
	_expect(state.get("stats") == practice, "permanent feedback preserves borrowed XP, even above 32 bits")
	_expect(state.get("lantern_tutorial") == guide, "feedback does not replace or dismiss the guide")

	# Ordinary XP in the same frame must not hide a separate Overall bonus.
	hud.call("_on_floating_feedback_requested", {"kind":"experience", "skill":"magic", "amount":4})
	hud.call("_on_floating_feedback_requested", {"kind":"experience", "skill":"overall", "amount":4})
	await process_frame
	await process_frame
	_expect(hud.spawned.size() == 3, "normal skill XP and both bonuses float; derived Overall stays hidden: %s" % [hud.spawned])
	_expect(hud.spawned[1].skill == "overall" and hud.spawned[1].amount == 150,
		"bonus Overall survives normal XP suppression")
	hud.spawned.clear()
	feedback.clear()
	award.permanent = false
	award.rewards = [{"skill":"overall", "amount":20}]
	_send(state, award)
	await process_frame
	await process_frame
	_expect(hud.spawned.size() == 1 and hud.spawned[0].amount == 20,
		"pure Overall milestone also floats inside the normal XP grace period")

	feedback.clear()
	award.rewards = [{"skill":"attack", "amount":90}, {"skill":"defense", "amount":90},
		{"skill":"overall", "amount":180}]
	_send(state, award)
	_expect(feedback.size() == 2 and feedback[0].skill == "attack" and feedback[1].skill == "defense",
		"combat bonus floats both skills without repeating their Overall sum")
	var count := feedback.size()
	var snapshot := PackedByteArray()
	snapshot.resize(230)
	state.call("_on_packet", P.ServerMessage.HERE_YOUR_STATS, snapshot)
	_expect(feedback.size() == count, "following authoritative stats refresh does not repeat bonus floats")

	# Validate the whole message before emitting anything, including a bad second entry.
	for invalid: Variant in [null, {}, [], [{"skill":"unknown", "amount":20}],
			[{"skill":"magic", "amount":40}, {"skill":"magic", "amount":40}],
			[{"skill":"magic", "amount":40}, {"skill":"overall", "amount":-1}]]:
		award.rewards = invalid
		_expect(P.decode_lantern(JSON.stringify(award).to_utf8_buffer()).type == "invalid", "invalid reward list rejected")
		_send(state, award)
	for amount: Variant in [null, true, "40", 0, -1, 1.5, 4294967296]:
		award.rewards = [{"skill":"magic", "amount":amount}]
		_expect(P.decode_lantern(JSON.stringify(award).to_utf8_buffer()).type == "invalid", "invalid reward amount rejected")
		_send(state, award)
	award.rewards = [{"skill":"magic", "amount":40}]
	for field: String in ["version", "event", "permanent"]:
		var invalid: Dictionary = award.duplicate(true)
		invalid[field] = "invalid"
		_expect(P.decode_lantern(JSON.stringify(invalid).to_utf8_buffer()).type == "invalid", "invalid envelope rejected")
		_send(state, invalid)
	_expect(feedback.size() == count, "malformed messages never produce partial feedback")
	await process_frame
	state.free()
	hud.free()
	print("tutorial XP feedback: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _send(state: Node, value: Dictionary) -> void:
	state.call("_on_packet", P.ServerMessage.ELORIA_LANTERN_STATE, JSON.stringify(value).to_utf8_buffer())

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)
