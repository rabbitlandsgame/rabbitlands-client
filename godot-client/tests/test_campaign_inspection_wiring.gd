extends SceneTree
## Native inspection requests are modal, not movement or interaction shortcuts.
var checks := 0
var failures := 0
var main: Node
var controller: Node
var app: Node
var network: Node
var local: Node3D
var odo: Node3D

static func snapshot() -> Dictionary:
	return {"version":1,"active":true,"run_id":"inspect-run","map":"greenlight","title":"The Ferry That Arrived Twice",
		"actors":{"odo":20},"targets":[],"party":{"role":"owner"},
		"scene":{"id":"measure.landing.arrival","token":"inspect-run:measure.landing.arrival","actors":{"odo":20,"protagonist":1},
			"inspection":{"id":"landing_overview","status":"pending","actor_id":1,"object_id":61001,
				"path":[[449,309],[448,310]],"approach":[448,310],"can_start":true}}}

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ", message)
	else:
		failures += 1
		push_error(message)
func decode(state: Dictionary) -> Dictionary:
	return EloriaProtocol.decode_campaign(JSON.stringify(state).to_utf8_buffer())
func reset_main() -> void:
	app.authenticated=true;app.death={};app.local_actor_id=1;app.current_map="greenlight";app.campaign=snapshot()
	app.actors.clear();app.actors[1]={"kind":1,"health":20,"x":450,"y":308};app.actors[20]={"kind":2,"health":20}
	main.set("actor_nodes",{1:local,20:odo});main.set("_disconnect_console_active",false)
	(main.get("_grounded_actors") as Dictionary).clear();(main.get("_grounded_actors") as Dictionary)[1]=true
	controller.set("playing",true);controller.set("replay",false);controller.set("retries",0)
	controller.set("context",{"run_id":"inspect-run","token":"inspect-run:measure.landing.arrival","id":"landing_overview","waiting":true})
	(network.get("sent_frames") as Array).clear();network.set("fail_send",false)

func run() -> void:
	create_timer(75).timeout.connect(func()->void: push_error("Inspection wiring checks timed out");quit(1))
	var state := snapshot()
	expect(decode(state).get("type")=="campaign","the full native inspection contract decodes")
	var legacy := state.duplicate(true);legacy.scene.erase("inspection");legacy.scene.actors.erase("protagonist")
	expect(decode(legacy).get("type")=="campaign","older scene packets without inspection remain compatible")
	for status: String in ["pending","walking","complete","blocked","waiting_owner"]:
		var row := state.duplicate(true);row.scene.inspection.status=status;row.scene.inspection.can_start=false
		expect(decode(row).get("type")=="campaign","native inspection state "+status+" remains readable")
	var absent := state.duplicate(true);absent.scene.inspection.actor_id=0;absent.scene.inspection.can_start=false;absent.scene.actors.erase("protagonist")
	expect(decode(absent).get("type")=="campaign","helpers can observe a temporarily absent owner without binding themselves")
	for bad: Dictionary in [{"id":"repair_damage"},{"status":"teleported"},{"actor_id":-1},{"actor_id":1.5},{"object_id":0},{"object_id":65536},{"can_start":1},{"path":[]},{"path":[[449,309.5],[448,310]]},{"path":[[448,309]]},{"approach":[448]},{"status":"complete"},{"actor_id":0}]:
		var row := state.duplicate(true);row.scene.inspection.merge(bad,true)
		expect(decode(row).get("type")=="invalid","malformed inspection identity, path or permission is rejected")
	var unbound := state.duplicate(true);unbound.scene.actors.protagonist=2
	expect(decode(unbound).get("type")=="invalid","inspection actor and real protagonist binding must agree")
	var oversized := state.duplicate(true);oversized.scene.inspection.path.resize(33)
	expect(decode(oversized).get("type")=="invalid","inspection path size is bounded before staging")
	network=root.get_node("Network")
	var recorder := GDScript.new()
	recorder.source_code='extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nvar fail_send:=false\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tif fail_send:return ERR_UNAVAILABLE\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload()==OK,"isolated inspection transport recorder compiles")
	network.set_script(recorder);network.call("block_for_hud_preview")
	var frames: Array = network.get("sent_frames")
	for action: String in ["start","cancel"]:
		frames.clear()
		expect(network.call("campaign_scene_inspect","inspect-run","inspect-run:measure.landing.arrival",action)==OK and frames==[EloriaProtocol.chat("#campaign scene_inspect inspect-run inspect-run:measure.landing.arrival "+action)],"inspection "+action+" is an exact scene-bound command, never MOVE or USE")
	for args: Array in [["bad run","token","start"],["run","bad token","cancel"],["run","token","teleport"],["","token","start"]]:
		frames.clear()
		expect(network.call("campaign_scene_inspect",args[0],args[1],args[2])==ERR_INVALID_PARAMETER and frames.is_empty(),"malformed inspection requests never reach the wire")
	main=(load("res://src/app/main.tscn") as PackedScene).instantiate();root.add_child(main);main.set_process(false);main.hide()
	var double_script := GDScript.new()
	double_script.source_code='extends "res://src/world/campaign_scene.gd"\nvar context:Dictionary={}\nvar replay:=false\nvar retries:=0\nfunc inspection_context()->Dictionary:return context\nfunc is_replaying()->bool:return replay\nfunc inspection_send_failed()->void:retries+=1\n'
	expect(double_script.reload()==OK,"inspection fixture provides controller context and failure recovery")
	var previous: Node = main.get("campaign_scene");controller=double_script.new();main.add_child(controller);main.set("campaign_scene",controller);previous.queue_free()
	local=Node3D.new();root.add_child(local);local.position=Vector3(100,0,100)
	odo=Node3D.new();root.add_child(odo);app=root.get_node("AppState");reset_main()
	expect(bool(main.call("_world_input_blocked")),"ordinary walking and interaction remain blocked during inspection")
	var before := JSON.stringify(app.actors[1]);main.call("_on_campaign_scene_inspection","start")
	expect(frames==[EloriaProtocol.chat("#campaign scene_inspect inspect-run inspect-run:measure.landing.arrival start")],"a current grounded owner can request native inspection while world input is blocked")
	expect(JSON.stringify(app.actors[1])==before and app.campaign.scene.inspection.status=="pending","requesting inspection never changes the authoritative actor tile or quest proof locally")
	for blocker: String in ["replay","helper","stale_run","stale_token","stale_event","not_waiting","wrong_scene","foreign_map","travel","inactive","dead","zero_health","disconnect","signed_out","ungrounded","not_playing","missing_player","non_player","foreign_protagonist","foreign_actor","cannot_start","walking","unknown_action"]:
		reset_main()
		match blocker:
			"replay":controller.set("replay",true)
			"helper":app.campaign.party.role="helper"
			"stale_run":controller.get("context").run_id="old-run"
			"stale_token":controller.get("context").token="old-token"
			"stale_event":controller.get("context").id="old-event"
			"not_waiting":controller.get("context").waiting=false
			"wrong_scene":app.campaign.scene.id="measure.landing.plan"
			"foreign_map":app.current_map="twinbrook"
			"travel":app.campaign.travel={"map":"twinbrook"}
			"inactive":app.campaign.active=false
			"dead":app.death={"dead":true}
			"zero_health":app.actors[1].health=0
			"disconnect":main.set("_disconnect_console_active",true)
			"signed_out":app.authenticated=false
			"ungrounded":(main.get("_grounded_actors") as Dictionary).clear()
			"not_playing":controller.set("playing",false)
			"missing_player":(main.get("actor_nodes") as Dictionary).erase(1)
			"non_player":app.actors[1].kind=2
			"foreign_protagonist":app.campaign.scene.actors.protagonist=2
			"foreign_actor":app.campaign.scene.inspection.actor_id=2
			"cannot_start":app.campaign.scene.inspection.can_start=false
			"walking":app.campaign.scene.inspection.status="walking";app.campaign.scene.inspection.can_start=false
		main.call("_on_campaign_scene_inspection","teleport" if blocker=="unknown_action" else "start")
		expect(frames.is_empty(),blocker+" blocks an inspection start without any movement, resource or progress side effect")
	reset_main();controller.set("playing",false);controller.get("context").waiting=false;app.campaign.scene.inspection.status="walking";app.campaign.scene.inspection.can_start=false
	(main.get("_grounded_actors") as Dictionary).clear();main.call("_on_campaign_scene_inspection","cancel")
	expect(frames==[EloriaProtocol.chat("#campaign scene_inspect inspect-run inspect-run:measure.landing.arrival cancel")],"skip or terrain failure may cancel an owned walk after the controller stops playing")
	for blocker: String in ["replay","helper","stale_token","foreign_actor","public_map","dead"]:
		reset_main();controller.set("playing",false)
		match blocker:
			"replay":controller.set("replay",true)
			"helper":app.campaign.party.role="helper"
			"stale_token":controller.get("context").token="old-token"
			"foreign_actor":app.campaign.scene.inspection.actor_id=2
			"public_map":app.current_map="twinbrook"
			"dead":app.death={"dead":true}
		main.call("_on_campaign_scene_inspection","cancel")
		expect(frames.is_empty(),blocker+" cannot cancel another native scene task")
	reset_main();app.campaign.erase("party");main.call("_on_campaign_scene_inspection","start")
	expect(frames.size()==1,"legacy solo ownership needs no invented party metadata")
	reset_main();network.set("fail_send",true);main.call("_on_campaign_scene_inspection","start")
	expect(frames.is_empty() and int(controller.get("retries"))==1,"transport failure releases the pending inspection request for retry")
	main.set("actor_nodes",{});app.authenticated=false;main.queue_free();local.queue_free();odo.queue_free()
	await process_frame;await process_frame
	print("campaign inspection wiring: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
