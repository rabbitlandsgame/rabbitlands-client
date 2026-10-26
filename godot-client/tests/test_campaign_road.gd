extends SceneTree
const Fixture := preload("res://tests/test_campaign_scene.gd")
const Presentation := preload("res://src/world/campaign_scene.gd")
const Works := preload("res://src/world/campaign_road_works.gd")
const Hud := preload("res://src/ui/campaign_hud.gd")
var checks := 0
var failures := 0

func _init() -> void:
    run.call_deferred()

func expect(ok: bool, message: String) -> void:
    checks += 1
    if ok: print("PASS: ", message)
    else:
        failures += 1
        push_error(message)

static func anchors(checkpoint := false) -> Dictionary:
    return JSON.parse_string('''{"entry": [258, 64], "recovery": [258, 64], "briefing": [266, 70], "cart_start": [273, 80], "discovery_1": [273, 80], "discovery_2": [280, 80], "discovery_3": [288, 80], "inspection": [296, 80], "casks": [291, 72], "fitting": [296, 72], "holding": [286, 68], "seal": [294, 77], "weight": [298, 77], "fittings": [298, 79], "agreement": [291, 76], "custody": [291, 79], "witness": [291, 77], "carrier": [296, 76]}''' if checkpoint else '''{"entry": [202, 92], "recovery": [202, 92], "briefing": [207, 97], "meal": [206, 96], "load": [207, 105], "rear_load": [199, 105], "feed": [214, 98], "rope": [214, 102], "pantry": [218, 97], "warning_1": [218, 102], "warning_2": [240, 102], "stable_1": [221, 102], "stable_2": [245, 102], "anchor_1": [216, 103], "anchor_2": [239, 103], "diversion_1": [226, 102], "diversion_2": [249, 102], "unload_1": [218, 108], "unload_2": [242, 109], "crew_1": [210, 103], "crew_2": [238, 102], "herd": [226, 103], "supper": [193, 92], "animal": [191, 95], "supper_safe": [202, 99], "last_bowl": [212, 96], "departure": [261, 103], "rear_slip_1": [212, 105], "rear_slip_2": [236, 105]}''')

static func state(checkpoint := false) -> Dictionary:
    return {"version":1,"kind":"road","active":true,"started":true,"run_id":"road-fixture",
        "map":"brambleshaw" if checkpoint else "hearthcroft","title":"A Road Full of Hungry People",
        "key":"consignment" if checkpoint else "prepare","stage":0,"hint":"Inspect the actual crew and prepare both carts.",
        "actors":{"odo":2,"worker":3,"oyun":4,"tobin":5,"carrier":6},"anchors":anchors(checkpoint),
        "scene":{"id":"measure.road.consignment" if checkpoint else "measure.road.departure","token":"road-start","requires_ack":true},
        "targets":[{"id":"hazard_walk","object_id":0,"label":"Guide the next physical work leg","tile":[226,102],"enabled":true,"completed":false}],
        "party":{"owner":"Aster","role":"owner","members":[{"name":"Aster","role":"owner","present":true,"online":true,"adoption":""}]},"adoption":{},
        "road":{"stage":"inspection" if checkpoint else "prepare","preparation":"","hazard":{"index":1,"kind":"herd","state":"warning","solution":""},
        "carts":[{"id":"consignment" if checkpoint else "lead","tile":[273,80] if checkpoint else [207,105],"route_index":0,"route_total":24 if checkpoint else 53,"state":"waiting","cargo_units":1 if checkpoint else 6,"facing":[1,0],"motion_seq":0,"step_ms":250}],
        "checkpoint":{"id":"0","tile":[258,64] if checkpoint else [202,92]},"stock":{"remaining":8,"spent":0,"reserved_last_bowl":2},
        "consignment":{"id":"current-greenlight-fitting","method":"","agreement":false,"inspected":false,"custody":""},
        "convoy":{"mode":"wait","status":"Carts hold at safe work anchors.","can_command":true},
        "optional":{"supper":"found","last_bowl":"portioned"}}}

func height(point: Vector3) -> float:
    return 98.125 + point.x * 0.01

func run() -> void:
    var snapshot := state()
    expect("campaign_road_v1" in EloriaProtocol.CLIENT_CAPABILITIES,"road support negotiates an additive capability")
    expect(EloriaProtocol.decode_campaign(JSON.stringify(snapshot).to_utf8_buffer()).get("type") == "campaign","server-shaped road state decodes")
    for row: Dictionary in [{"preparation":"free"},{"stock":{"remaining":11}},{"convoy":{"can_command":"yes"}},
            {"hazard":{"index":3}},{"optional":{"supper":"kill"}},{"consignment":{"agreement":1}},
            {"consignment":{"custody":"confiscate"}},{"carts":[{"id":"lead","tile":[1.5,2]}]}]:
        var bad := snapshot.duplicate(true)
        bad.road.merge(row,true)
        expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).get("type") == "invalid","invalid road branch, stock, pose or authority is rejected")
    for preparation: String in ["brace","protect","shared_load"]:
        for solution: String in ["anchor","diversion","rebalance"]:
            snapshot.road.preparation=preparation
            snapshot.road.hazard.solution=solution
            expect(EloriaProtocol.decode_campaign(JSON.stringify(snapshot).to_utf8_buffer()).get("type") == "campaign",preparation+" / "+solution+" remains a valid physical branch")
    var adapter := CoordinateAdapter.new({"serverOrigin":[425,269],"metresPerTile":1.0,"walkingHeight":98.1})
    var works := Works.new()
    root.add_child(works)
    var resident := [false]
    var sample := func(point:Vector3)->float:return height(point) if resident[0] else NAN
    works.apply_snapshot(snapshot,adapter,"hearthcroft",sample)
    expect(works.carts.is_empty() and works.props.is_empty(),"cold terrain never creates floating carts or field props")
    resident[0]=true
    works.apply_snapshot(snapshot,adapter,"hearthcroft",sample)
    expect(works.carts.size()==1 and works.props.size()==3,"approved cart, sacks, rope and pantry appear only over real terrain")
    expect((works.carts.lead as Node3D).scale.is_equal_approx(Vector3.ONE),"unit placement retains the cart's baked native scale")
    var pivot:=works.carts.lead.get_child(0) as Node3D
    expect(pivot.position.is_equal_approx(Works.CART_CENTRE) and pivot.scale.is_equal_approx(Vector3.ONE),"the existing road cart is centered and grounded without changing its native transform")
    expect(absf(works.props.feed.rotation.z)>0.001,"static supplies follow the sampled ground plane")
    var original:Vector3=works.carts.lead.global_position
    snapshot.road.carts[0].tile=[208,105]
    snapshot.road.carts[0].route_index=1
    snapshot.road.carts[0].motion_seq=1
    snapshot.road.carts[0].state="moving"
    works.apply_snapshot(snapshot,adapter,"hearthcroft",sample)
    works._process(0.125)
    expect(absf(works.carts.lead.global_position.x-original.x-0.5)<0.01,"only the accepted adjacent persisted step is interpolated")
    works._process(5)
    expect(absf(works.carts.lead.global_position.x-original.x-1)<0.01,"a stopped snapshot never predicts another cart step")
    snapshot.road.carts[0].motion_seq=0
    snapshot.road.carts[0].tile=[207,105]
    works.apply_snapshot(snapshot,adapter,"hearthcroft",sample)
    expect(works.poses.lead.seq==1,"stale poses cannot rewind a persisted cart")
    snapshot.road.carts[0].motion_seq=4
    snapshot.road.carts[0].tile=[220,105]
    snapshot.road.carts[0].state="recovering"
    works.apply_snapshot(snapshot,adapter,"hearthcroft",sample)
    expect(works.poses.lead.duration==0 and adapter.godot_to_server(works.carts.lead.global_position)==Vector2i(220,105),"recovery and missed path corners snap to the saved legal pose")
    snapshot.road.carts[0].motion_seq=5
    snapshot.road.carts[0].tile=[221,105]
    snapshot.road.carts[0].state="moving"
    works.apply_snapshot(snapshot,adapter,"hearthcroft",sample,true)
    expect(works.poses.lead.duration==0,"reduced motion preserves the exact accepted position without smoothing")
    snapshot.road.carts[0].motion_seq=6
    snapshot.road.carts[0].tile=[220,105]
    snapshot.road.carts[0].facing=[-1,0]
    works.apply_snapshot(snapshot,adapter,"hearthcroft",sample)
    expect(is_zero_approx(works.carts.lead.rotation.y),"backing keeps the long shaft axis inside the validated five-by-three lane")
    var bundle_count:=0
    for bundle:Node3D in works.carts.lead.get_node("AcceptedCargo").get_children():
        if bundle.visible:bundle_count+=1
    snapshot.road.carts[0].cargo_units=2
    works.apply_snapshot(snapshot,adapter,"hearthcroft",sample)
    var smaller_count:=0
    for bundle:Node3D in works.carts.lead.get_node("AcceptedCargo").get_children():
        if bundle.visible:smaller_count+=1
    expect(smaller_count<bundle_count,"accepted load reduction removes native cargo bundles instead of only changing a number")
    expect(works.checkpoint.visible and adapter.godot_to_server(works.checkpoint.global_position)==Vector2i(226,102),"a grounded field ring marks the actual navigation-only next leg")
    works.set_readouts_visible(false)
    expect(not works.labels.cart_lead.visible and not works.labels.feed.visible,"speaking closeups can hide all field readouts")
    var hud := Hud.new()
    root.add_child(hud)
    hud.apply_state(snapshot,Vector2i(202,92),"hearthcroft")
    expect(hud._road.text.contains("8 portions") and hud._road.text.contains("2 kept"),"the guide shows finite available and reserved food separately")
    expect(hud._road.text.contains("injured animal") and hud._road.text.contains("portions kept"),"optional work states stay concrete and recoverable")
    var orders:Array=[]
    hud.convoy_requested.connect(func(command:String)->void:orders.append(command))
    hud._convoy_buttons.follow.pressed.emit()
    expect(orders==["follow"],"the owner can direct the physical carts independently of Odo")
    snapshot.road.convoy.can_command=false
    hud.apply_state(snapshot,Vector2i(202,92),"hearthcroft")
    hud._request_convoy("regroup")
    expect(orders.size()==1 and hud._convoy_buttons.follow.disabled,"a helper cannot issue owner-only cart orders")
    var rig := Fixture.Rig.new()
    root.add_child(rig)
    var camera:=Camera3D.new()
    rig.add_child(camera)
    rig.camera=camera
    camera.position=Vector3(4,14,12)
    var before:=camera.global_transform
    var actors:Dictionary={}
    for id:int in range(1,7):
        var actor:=Fixture.Actor.new()
        root.add_child(actor)
        actor.position=adapter.tile_center(208+id,98)
        actor.post=actor.global_transform
        actors[id]=actor
    var scene:=Presentation.new()
    root.add_child(scene)
    scene.set_reduced_motion(false,false)
    snapshot.scene.token="departure"
    scene.update(0,snapshot,rig,actors,1,"hearthcroft",true,adapter,sample)
    expect(scene.playing and scene.blocks_input(),"the crew briefing takes temporary camera and input ownership")
    expect(scene.transcript_text().contains("Soup buys no service") and scene.transcript_text().contains("six workers"),"Oyun's freely offered meal and real headcount are in the authored account")
    scene.update(12,snapshot,rig,actors,1,"hearthcroft",true,adapter,sample)
    expect(scene.work_readouts_visible() and actors[3].action==&"emote_point","a clean work cut reveals the actual loads while the crew gestures")
    scene.skip()
    expect(not scene.blocks_input() and camera.global_transform.is_equal_approx(before) and actors[2].restored,"skip restores the camera, input and reversible NPC staging")
    var checkpoint:=state(true)
    checkpoint.scene.token="consignment"
    scene.update(0,checkpoint,rig,actors,1,"brambleshaw",true,adapter,sample)
    expect(scene.transcript_text().contains("witnessed terms on this shipment") and scene.transcript_text().contains("palace stores remain sealed"),"the carrier's current agreement defines inspection authority")
    scene.update(7,checkpoint,rig,actors,1,"brambleshaw",true,adapter,sample)
    expect(camera.global_position.distance_to(actors[6].global_position)<10,"the carrier's speaking camera follows the actual actor rather than its future delivery post")
    scene.skip()
    checkpoint.scene.token="remembered-palace"
    checkpoint.scene.variant="remembered_palace"
    scene.update(0,checkpoint,rig,actors,1,"brambleshaw",true,adapter,sample)
    expect(scene.transcript_text().contains("They stay sealed"),"personal old observations acknowledge Tobin without granting palace authority")
    var revisit:=state()
    revisit.scene={}
    revisit.key="complete"
    revisit.road.stage="complete"
    scene.update(0,revisit,rig,actors,1,"hearthcroft",true,adapter,sample)
    works.apply_snapshot(revisit,adapter,"hearthcroft",sample)
    expect(not scene.blocks_input() and works.carts.has("lead"),"an active optional-only field return keeps its work presentation without replaying the remote ending")
    hud.apply_state(revisit,Vector2i(202,92),"hearthcroft")
    expect(hud.visible and hud._scroll.visible,"a scene-free optional return retains reachable field actions")
    checkpoint.travel={"map":"brambleshaw","npc":"Tobin Ware"}
    checkpoint.active=false
    scene.update(0,checkpoint,rig,actors,1,"hearthcroft",true,adapter,sample)
    expect(not scene.blocks_input(),"public travel cancels the private camera cleanly")
    hud.apply_state(checkpoint,Vector2i(202,92),"hearthcroft")
    expect(hud.visible and not hud._scroll.visible,"ordinary public travel shows contact instructions without foreign-map target buttons")
    works.apply_snapshot(checkpoint,adapter,"hearthcroft",sample)
    expect(works.carts.is_empty() and works.props.is_empty(),"map exit removes every private cart, prop and readout")
    var network:=root.get_node("Network")
    var recorder:=GDScript.new()
    recorder.source_code='extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
    expect(recorder.reload()==OK,"the native offline transport recorder compiles")
    network.set_script(recorder)
    expect(network.call("campaign_convoy","follow")==OK and network.call("campaign_companion","wait")==OK,"cart and guide orders use distinct validated native commands")
    expect(network.call("campaign_convoy","teleport")==ERR_INVALID_PARAMETER,"unknown convoy orders never reach the transport")
    expect(network.call("campaign_request","road")==OK,"the new entry uses its dedicated contact command")
    for node:Node in [hud,scene,works,rig]:node.queue_free()
    for actor:Node in actors.values():actor.queue_free()
    await process_frame
    await process_frame
    print("campaign road: ",checks," checks; ",failures," failures")
    quit(1 if failures else 0)
