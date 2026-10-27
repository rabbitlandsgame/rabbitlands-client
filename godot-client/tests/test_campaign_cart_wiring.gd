extends SceneTree
const HUD := preload("res://src/ui/campaign_hud.gd")
const Guidance := preload("res://src/world/campaign_guidance.gd")
var checks := 0
var failures := 0
var main: Node
var controller: Node
var app: Node
var network: Node
var player: Node3D
var odo: Node3D

static func snapshot() -> Dictionary:
	return {"version":1,"content_revision":2,"active":true,"run_id":"cart-run","map":"greenlight","title":"The Last Cart",
		"actors":{"odo":20},"targets":[],"party":{"role":"owner"},"crossing":{},
		"cart":{"id":"last_cart","tile":[422,316],"facing":[1,0],"footprint":[5,3],"tilt_deg":17.0,"route":"","state":"trapped",
			"load_units":2,"unloaded":0,"fulcrum_ready":false,"rope_ends":0,"holder_active":true,"released":false,"treated":false,"worker_safe":false,"worker_tile":[425,316],"safe_tile":[441,325]},
		"inquiry":{"lead":"","physical_verified":false,"chronology_verified":false,"records_verified":false,"finding":"unresolved","claims":["The pump was completed.","The second work was completed."]},
		"scene":{"id":"measure.cart.arrival","token":"cart-run:measure.cart.arrival","actors":{"odo":20,"protagonist":1},
			"inspection":{"id":"cart_assessment","status":"pending","actor_id":1,"object_id":62001,"path":[[438,321],[428,319]],"approach":[428,319],"can_start":true},
			"choice":{"id":"cart_release","title":"Choose how to free the worker","selected":"","response":"","owner":"Aster","owner_is_you":true,"can_choose":false,
				"options":[{"id":"unload","label":"Lighten the cart","detail":"Set down both loads before lifting."},{"id":"lever","label":"Brace and lift","detail":"Place the fulcrum and use the lever."},{"id":"haul","label":"Secure and haul","detail":"Rig both anchors and keep the cart held."}]}}}

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ", message)
	else:
		failures += 1
		push_error(message)
func decode(value: Dictionary) -> Dictionary:
	return EloriaProtocol.decode_campaign(JSON.stringify(value).to_utf8_buffer())
func reset_main() -> void:
	app.authenticated=true;app.death={};app.local_actor_id=1;app.current_map="greenlight";app.campaign=snapshot()
	app.actors.clear();app.actors[1]={"kind":1,"health":20,"x":444,"y":322};app.actors[20]={"kind":2,"health":20}
	main.set("actor_nodes",{1:player,20:odo});main.set("_disconnect_console_active",false)
	(main.get("_grounded_actors") as Dictionary).clear();(main.get("_grounded_actors") as Dictionary)[1]=true
	controller.set("playing",true);controller.set("replay",false);controller.set("inspection_retries",0);controller.set("choice_retries",0)
	controller.set("inspection_test",{"run_id":"cart-run","token":"cart-run:measure.cart.arrival","id":"cart_assessment","waiting":true})
	controller.set("choice_test",{"run_id":"cart-run","token":"cart-run:measure.cart.arrival","id":"cart_release","waiting":true})
	(network.get("sent_frames") as Array).clear();network.set("fail_send",false)
func allow_choice() -> void:
	app.campaign.scene.inspection.status="complete";app.campaign.scene.inspection.can_start=false;app.campaign.scene.choice.can_choose=true
	app.actors[1].x=428;app.actors[1].y=319

func allow_inquiry() -> void:
	app.campaign.cart.worker_safe=true;app.campaign.cart.state="safe";app.campaign.cart.released=true;app.campaign.cart.treated=true
	app.campaign.scene.id="measure.claims.inquiry";app.campaign.scene.token="cart-run:measure.claims.inquiry";app.campaign.scene.inspection={}
	app.campaign.scene.choice={"id":"claims_lead","title":"Which lead first?","owner":"Aster","owner_is_you":true,"can_choose":true,"selected":"","response":"",
		"options":[{"id":"physical","label":"Follow the physical work","detail":"Compare the actual kit and fittings."},{"id":"chronology","label":"Reconstruct the sequence","detail":"Check what could have happened first."},{"id":"records","label":"Compare the records","detail":"Trace the two completion claims."}]}
	controller.set("choice_test",{"run_id":"cart-run","token":"cart-run:measure.claims.inquiry","id":"claims_lead","waiting":true})

func run() -> void:
	create_timer(90).timeout.connect(func()->void:push_error("Cart wiring checks timed out");quit(1))
	var state:=snapshot()
	expect("campaign_cart_v1" in EloriaProtocol.CLIENT_CAPABILITIES,"the client explicitly negotiates the new cart content")
	expect(decode(state).get("type")=="campaign","the full revision2 cart, inquiry and cinematic contract decodes: "+str(decode(state).get("error","ok")))
	expect(decode({"version":1,"active":false,"targets":[]}).get("type")=="campaign","saved revision1 clients retain the optional legacy shape")
	for field: String in state.cart.keys():
		var bad:=state.duplicate(true);bad.cart.erase(field)
		expect(decode(bad).get("type")=="invalid","nonempty cart metadata requires "+field)
	for patch: Dictionary in [{"id":"other_cart"},{"route":"repair"},{"state":"teleported"},{"tile":[422.5,316]},{"facing":[0,0]},{"footprint":[3,3]},{"tilt_deg":31},{"tilt_deg":true},{"load_units":3},{"unloaded":1.5},{"rope_ends":-1},{"holder_active":1}]:
		var bad:=state.duplicate(true);bad.cart.merge(patch,true)
		expect(decode(bad).get("type")=="invalid","invalid cart state, geometry or safety flag is rejected")
	for field: String in state.inquiry.keys():
		var bad:=state.duplicate(true);bad.inquiry.erase(field)
		expect(decode(bad).get("type")=="invalid","nonempty inquiry metadata requires "+field)
	for patch: Dictionary in [{"lead":"guess"},{"finding":"two_kits"},{"physical_verified":1},{"claims":[42]}]:
		var bad:=state.duplicate(true);bad.inquiry.merge(patch,true)
		expect(decode(bad).get("type")=="invalid","inquiry metadata cannot invent a lead or confirmed finding")
	for revision: Variant in [0,3,2.5,true]:
		var bad:=state.duplicate(true);bad.content_revision=revision
		expect(decode(bad).get("type")=="invalid","content revision is a supported integral version")
	var unversioned:=state.duplicate(true);unversioned.erase("content_revision")
	expect(decode(unversioned).get("type")=="invalid","new content cannot masquerade as an old saved campaign")
	var anchored:=state.duplicate(true);anchored.anchors={}
	for index:int in range(35):anchored.anchors["post_"+str(index)]=[422+index,316]
	expect(decode(anchored).get("type")=="campaign","revision2 accepts the real scene's35 bounded native anchors")
	for index:int in range(35,65):anchored.anchors["post_"+str(index)]=[422+index,316]
	expect(decode(anchored).get("type")=="invalid","revision2 anchor collections remain bounded at64")
	var legacy_anchors:={"version":1,"active":false,"targets":[],"anchors":{}}
	for index:int in range(33):legacy_anchors.anchors["post_"+str(index)]=[422,316]
	expect(decode(legacy_anchors).get("type")=="invalid","legacy snapshots retain their existing32-anchor limit")
	for offset:Array in [[-0.43,0,0],[0,0,0],[0.5,0,0],[-0.48,0,0.32]]:
		var posed:=state.duplicate(true);posed.cart.worker_presentation_offset=offset
		expect(decode(posed).get("type")=="campaign","a small horizontal worker pose offset has no movement authority")
	for offset:Variant in [[-0.51,0,0],[0,0.1,0],[0,0,0.51],[0,0],[true,0,0],null]:
		var posed:=state.duplicate(true);posed.cart.worker_presentation_offset=offset
		expect(decode(posed).get("type")=="invalid","vertical, foreign-axis, malformed or excessive worker offsets are rejected")
	for holder:String in ["foreman","Aster"]:
		var held:=state.duplicate(true);held.cart.holder=holder;held.cart.route="haul"
		expect(decode(held).get("type")=="campaign" and HUD.opening_details(held).contains("dock foreman" if holder=="foreman" else "Aster"),"the actual NPC or human brake holder is displayed truthfully")
	for holder:Variant in ["","x".repeat(65),42,null]:
		var held:=state.duplicate(true);held.cart.holder=holder
		expect(decode(held).get("type")=="invalid","a declared brake holder must be bounded plain text")
	for bad_choice: Dictionary in [{"selected":"repair"},{"options":[{"id":"defend","label":"Old","detail":"Old"},{"id":"lever","label":"Lift","detail":"Lift"},{"id":"haul","label":"Haul","detail":"Haul"}]}]:
		var bad:=state.duplicate(true);bad.scene.choice.merge(bad_choice,true)
		expect(decode(bad).get("type")=="invalid","legacy route IDs cannot cross into the cart decision")
	var ordered:=state.duplicate(true)
	ordered.targets=[{"id":"first","object_id":62002,"label":"Set down the first load","tile":[428,315],"enabled":true},{"id":"second","object_id":62003,"label":"Set down the second load","tile":[429,316],"enabled":true}]
	ordered.preferred_targets=["second","first"]
	expect(decode(ordered).get("type")=="campaign" and Guidance.work_targets(ordered)[0].id=="second","server-declared priorities drive the existing field checklist")
	expect(Guidance.legend(ordered).begins_with("Next: Set down the second load"),"the guide names the actual preferred action rather than an unrelated route")
	for ids: Array in [["unknown"],["first","first"],[1]]:
		var bad:=ordered.duplicate(true);bad.preferred_targets=ids
		expect(decode(bad).get("type")=="invalid","preferred actions must be unique declared target identities")
	ordered.targets[1].enabled=false
	expect(Guidance.work_targets(ordered)[0].id=="first","a disabled preferred target never becomes an actionable pin")
	var text:=HUD.opening_details(state)
	expect(text.contains("worker is pinned") and not text.contains("Claims to check") and not text.contains("Verified:"),"the field card does not spoil the follow-up inquiry before rescue")
	var next:=state.duplicate(true);next.cart.worker_safe=true;next.cart.state="safe";next.inquiry.lead="physical"
	text=HUD.opening_details(next)
	expect(text.contains("safely ashore") and text.contains("physical work") and text.contains("Claims to check") and not text.contains("Verified:"),"the same quest card distinguishes unverified claims from physical evidence")
	next.inquiry.finding="one_kit_two_completions"
	expect(HUD.opening_details(next).contains("Verified: one fitting kit"),"only a confirmed finding becomes a verified account")
	network=root.get_node("Network");var recorder:=GDScript.new()
	recorder.source_code='extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nvar fail_send:=false\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tif fail_send:return ERR_UNAVAILABLE\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload()==OK,"the isolated production transport recorder compiles")
	network.set_script(recorder);network.call("block_for_hud_preview")
	var frames:Array=network.get("sent_frames")
	for route: String in ["unload","lever","haul"]:
		frames.clear();var error:Error=network.call("campaign_scene_choice","cart-run","cart-run:measure.cart.arrival",route)
		expect(error==OK and frames==[EloriaProtocol.chat("#campaign scene_choice cart-run cart-run:measure.cart.arrival "+route)],"the exact scene-bound "+route+" transport is supported")
	frames.clear();network.call("campaign_request","cart")
	expect(frames==[EloriaProtocol.chat("#campaign cart")],"an explicit new-content visit has its dedicated supported command")
	main=(load("res://src/app/main.tscn") as PackedScene).instantiate();root.add_child(main);main.set_process(false);main.hide()
	var fixture:=GDScript.new()
	fixture.source_code='extends "res://src/world/campaign_scene.gd"\nvar inspection_test:Dictionary={}\nvar choice_test:Dictionary={}\nvar replay:=false\nvar inspection_retries:=0\nvar choice_retries:=0\nfunc inspection_context()->Dictionary:return inspection_test\nfunc choice_context()->Dictionary:return choice_test\nfunc is_replaying()->bool:return replay\nfunc inspection_send_failed()->void:inspection_retries+=1\nfunc choice_send_failed()->void:choice_retries+=1\n'
	expect(fixture.reload()==OK,"the modal Main fixture exposes only current read-only controller contexts")
	var prior:Node=main.get("campaign_scene");controller=fixture.new();main.add_child(controller);main.set("campaign_scene",controller);prior.queue_free()
	player=Node3D.new();root.add_child(player);player.position=Vector3(100,2.5,100);odo=Node3D.new();root.add_child(odo);app=root.get_node("AppState")
	reset_main();main.call("_on_campaign_scene_inspection","start")
	expect(frames==[EloriaProtocol.chat("#campaign scene_inspect cart-run cart-run:measure.cart.arrival start")],"the actual owner may request native cart assessment while cinematic input stays blocked")
	frames.clear();main.call("_on_campaign_scene_choice","unload")
	expect(frames.is_empty(),"a rendered approach never grants pre-inspection route choice")
	for route: String in ["unload","lever","haul"]:
		reset_main();allow_choice();main.call("_on_campaign_scene_choice",route)
		expect(frames==[EloriaProtocol.chat("#campaign scene_choice cart-run cart-run:measure.cart.arrival "+route)],"confirmed cart inspection permits the owner's "+route+" plan")
	for blocker: String in ["replay","helper","stale_run","stale_token","wrong_revision","legacy_choice","legacy_inspection","wrong_scene","foreign_map","travel","inactive","dead","signed_out","ungrounded","non_player","not_owner","missing_odo","not_playing","unknown_route"]:
		reset_main();allow_choice()
		match blocker:
			"replay":controller.set("replay",true)
			"helper":app.campaign.party.role="helper"
			"stale_run":controller.get("choice_test").run_id="old-run";controller.get("inspection_test").run_id="old-run"
			"stale_token":controller.get("choice_test").token="old-token";controller.get("inspection_test").token="old-token"
			"wrong_revision":app.campaign.content_revision=1
			"legacy_choice":app.campaign.scene.choice.id="opening_rescue"
			"legacy_inspection":app.campaign.scene.inspection.id="landing_overview"
			"wrong_scene":app.campaign.scene.id="measure.claims.inquiry"
			"foreign_map":app.current_map="twinbrook"
			"travel":app.campaign.travel={"map":"twinbrook"}
			"inactive":app.campaign.active=false
			"dead":app.death={"dead":true}
			"signed_out":app.authenticated=false
			"ungrounded":(main.get("_grounded_actors") as Dictionary).clear()
			"non_player":app.actors[1].kind=2
			"not_owner":app.campaign.scene.choice.owner_is_you=false;app.campaign.scene.choice.can_choose=false
			"missing_odo":(main.get("actor_nodes") as Dictionary).erase(20)
			"not_playing":controller.set("playing",false)
		main.call("_on_campaign_scene_choice","repair" if blocker=="unknown_route" else "unload")
		expect(frames.is_empty(),blocker+" cannot submit a stale or unauthorized cart plan")
	reset_main();controller.set("playing",false);controller.get("inspection_test").waiting=false
	app.campaign.scene.inspection.status="walking";app.campaign.scene.inspection.can_start=false;main.call("_on_campaign_scene_inspection","cancel")
	expect(frames==[EloriaProtocol.chat("#campaign scene_inspect cart-run cart-run:measure.cart.arrival cancel")],"skipping the new scene can cancel its owned native walk after playback stops")
	reset_main();network.set("fail_send",true);main.call("_on_campaign_scene_inspection","start")
	expect(frames.is_empty() and int(controller.get("inspection_retries"))==1,"a failed native assessment send releases local retry state")
	reset_main();allow_choice();network.set("fail_send",true);main.call("_on_campaign_scene_choice","lever")
	expect(frames.is_empty() and int(controller.get("choice_retries"))==1 and str(app.campaign.cart.route).is_empty(),"a failed cart-plan send never manufactures a selected route or progress")
	for lead:String in ["physical","chronology","records"]:
		reset_main();allow_inquiry()
		expect(decode(app.campaign).get("type")=="campaign","the owner receives all three equally offered inquiry leads")
		main.call("_on_campaign_scene_choice",lead)
		expect(frames==[EloriaProtocol.chat("#campaign scene_choice cart-run cart-run:measure.claims.inquiry "+lead)],"the guidance-only "+lead+" lead uses the current scene-bound command")
		expect(str(app.campaign.inquiry.finding)=="unresolved" and str(app.campaign.scene.choice.selected).is_empty(),"requesting a lead does not invent evidence or a confirmed plan locally")
	for blocker:String in ["replay","helper","wrong_scene","foreign_map","installation","missing_inquiry","invalid_inquiry","foreign_actor","selected","stale_token"]:
		reset_main();allow_inquiry()
		match blocker:
			"replay":controller.set("replay",true)
			"helper":app.campaign.party.role="helper"
			"wrong_scene":app.campaign.scene.id="measure.claims.verified"
			"foreign_map":app.current_map="twinbrook";app.campaign.map="twinbrook"
			"installation":app.campaign.scene.variant="installation"
			"missing_inquiry":app.campaign.inquiry={}
			"invalid_inquiry":app.campaign.inquiry.lead="guess"
			"foreign_actor":app.campaign.scene.actors.protagonist=2
			"selected":app.campaign.scene.choice.selected="physical";app.campaign.scene.choice.can_choose=false
			"stale_token":controller.get("choice_test").token="old-token"
		main.call("_on_campaign_scene_choice","physical")
		expect(frames.is_empty(),blocker+" cannot submit a stale or unauthorized inquiry plan")
	expect(HUD.tracking_identity(snapshot())=="opening:cart-run","new journal quest numbers do not replace the standard run-stable tracking identity")
	main.set("actor_nodes",{});app.authenticated=false;main.queue_free();player.queue_free();odo.queue_free();await process_frame;await process_frame
	print("campaign cart wiring: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
