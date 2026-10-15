extends SceneTree
## Pure harness checks: no login, world scene, actor fabrication or GPU render.
const Walk := preload("res://tests/integration/rendered_landscape_walk.gd")
var failures := 0

func _init() -> void:
	var step := {"useNpc": "Wayfinder Nesh", "expectDialogue": "Wayfinder Nesh",
		"expectDialogueText": "tutorial NPC designed to help you"}
	_expect(Walk._npc_fixture_error(step).is_empty(), "explicit NPC schema accepted")
	var missing := step.duplicate()
	missing.erase("expectDialogueText")
	_expect(not Walk._npc_fixture_error(missing).is_empty(), "positive reply text is required")
	var mixed := step.duplicate()
	mixed["useObject"] = 123
	_expect(not Walk._npc_fixture_error(mixed).is_empty(), "object action cannot masquerade as NPC use")
	var actors := {1: {"kind": 1, "name": "Wayfinder Nesh"},
		40: {"kind": 2, "name": "Wayfinder Nesh"},
		41: {"kind": 2, "name": "Wayfinder Nesh the Younger"}}
	_expect(Walk._npc_actor_identity(actors, 1, "Wayfinder Nesh") == 40, "exact live NPC identity excludes player and partial name")
	_expect(Walk._npc_actor_identity(actors, 1, "wayfinder nesh") == -1, "name match is exact")
	actors[42] = {"kind": 2, "name": "Wayfinder Nesh"}
	_expect(Walk._npc_actor_identity(actors, 1, "Wayfinder Nesh") == -1, "duplicate live names fail explicitly")
	var text := "You guess this is a tutorial NPC designed to help you."
	var dialogue := {"open": true, "name": "Wayfinder Nesh", "text": text}
	var reply: Dictionary = {}
	_expect(not Walk._npc_reply_matches(reply, 40, step, dialogue, true, "Wayfinder Nesh", text), "stale visible dialogue alone cannot pass")
	var name_payload := "Wayfinder Nesh".to_utf8_buffer()
	name_payload.resize(20)
	Walk._observe_npc_reply(reply, EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.SEND_NPC_INFO, name_payload))
	Walk._observe_npc_reply(reply, EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.NPC_TEXT, text.to_utf8_buffer()))
	Walk._observe_npc_reply(reply, {"type": "npc_options", "options": [{"actor_id": 41, "response_id": 900}]})
	_expect(not Walk._npc_reply_matches(reply, 40, step, dialogue, true, "Wayfinder Nesh", text), "another actor's options cannot prove the interaction")
	Walk._observe_npc_reply(reply, {"type": "npc_options", "options": [{"actor_id": 40, "response_id": 900}]})
	_expect(Walk._npc_reply_matches(reply, 40, step, dialogue, true, "Wayfinder Nesh", text), "fresh reply and actual matching UI pass")
	_expect(Walk._npc_reply_matches(reply, 40, step, dialogue, true, "Wayfinder Nesh  [Quest 1]", text), "normal quest label suffix remains compatible")
	_expect(Walk._npc_reply_matches(reply, 40, step, dialogue, true, "Wayfinder Nesh  <Guide>  [Quest 1]", text), "an occupation in the header remains compatible")
	_expect(not Walk._npc_reply_matches(reply, 40, step, dialogue, false, "Wayfinder Nesh", text), "hidden panel fails")
	_expect(not Walk._npc_reply_matches(reply, 40, step, dialogue, true, "Other NPC", text), "wrong visible speaker fails")
	_expect(not Walk._npc_reply_matches(reply, 40, step, dialogue, true, "Wayfinder Nesh", "Loading"), "unrendered expected reply fails")
	dialogue["open"] = false
	_expect(not Walk._npc_reply_matches(reply, 40, step, dialogue, true, "Wayfinder Nesh", text), "closed authoritative dialogue fails")
	print("Landscape NPC harness: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _expect(condition: bool, label: String) -> void:
	if condition:
		print("PASS: ", label)
	else:
		failures += 1
		push_error(label)
