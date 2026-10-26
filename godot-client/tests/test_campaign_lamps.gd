extends SceneTree
const Fixture:=preload("res://tests/test_campaign_scene.gd")
const Scene:=preload("res://src/world/campaign_scene.gd")
const Works:=preload("res://src/world/campaign_lamps_works.gd")
const Hud:=preload("res://src/ui/campaign_hud.gd")
var checks:=0
var failures:=0
func _init()->void:run.call_deferred()
func expect(ok:bool,message:String)->void:
    checks+=1
    if ok:print("PASS: ",message)
    else:failures+=1;push_error(message)
static func state()->Dictionary:
    return {"version":1,"kind":"lamps","active":true,"started":true,"run_id":"lamps-fixture","map":"greenlight","stage":0,"key":"calibration","title":"When the Lamps Answer","hint":"Change one setting, then advance and compare its actual response.",
        "anchors":JSON.parse_string('''{"entry": [338, 427], "recovery": [336, 425], "briefing": [337, 431], "marker": [330, 412], "lamp": [324, 416], "indicator": [337, 416], "gate": [333, 417], "control": [329, 416], "worker_trapped": [315, 411], "worker_safe": [340, 424], "refuge_1": [322, 416], "refuge_2": [330, 422], "equipment": [337, 411], "holding": [340, 417], "hold": [333, 419], "edda_work": [333, 419], "service_lamp": [326, 428], "board": [319, 424], "lamp_supply": [317, 424], "lamp_view": [323, 429], "board_test": [322, 426], "observation": [328, 412], "challenge": [326, 412], "isolate": [336, 414], "measure": [338, 420], "terms": [335, 412], "return": [339, 431], "companion_start": [336, 431], "companion_wait": [342, 424], "brace_stock": [319, 418]}'''),"actors":{"edda":2,"worker":3,"voss":4},"scene":{"id":"measure.lamps.arrival","token":"arrival","variant":"safe_hold","requires_ack":true},
        "targets":[{"id":"cycle_step","object_id":61805,"label":"Advance the controlled cycle","tile":[329,416],"approach":[328,416],"enabled":true,"completed":false}],
        "companion":{"name":"Edda Tine","mode":"wait","status":"Waiting at the work bay.","can_command":true},
        "party":{"owner":"Aster","role":"eligible","members":[{"name":"Aster","role":"owner","online":true,"present":true,"adoption":""}]},"adoption":{},
        "lamps":{"settings":{"marker":1,"shutter":0,"bleed":0},"cycle":1,"tide":1,"load":0,"water":1,"marker_number":2,"beam_height":1,"clearance":1,"lamp_word":"ALIGNED","lamp_shape":"circle","indicator":"level","challenge":false,"observations":[],
            "prediction":{"candidate":null,"revision":4,"status":"unselected","feedback":"","can_choose":false},"approach":"","holder":"","holder_active":false,"worker_status":"trapped","refuge_step":0,"route_ready":false,"evidence_method":"","evidence_secure":false,"equipment_tile":[337,411],"terms":"","inherited_custody":"safe_hold","lamp_done":false,"board_done":false}}
func height(_point:Vector3)->float:return 0.625
func run()->void:
    var s:=state()
    expect("campaign_lamps_v1" in EloriaProtocol.CLIENT_CAPABILITIES,"the new chapter is negotiated additively")
    expect(EloriaProtocol.decode_campaign(JSON.stringify(s).to_utf8_buffer()).get("type")=="campaign","server-shaped lamp settings and personal prediction decode")
    var registry:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
    var native_actions:Dictionary={}
    for role:String in ["edda","worker","voss"]:
        var type_id:int={"edda":323,"worker":308,"voss":348}[role]
        var model:Dictionary=registry.models[registry.actorTypes[str(type_id)]]
        native_actions[role]=(JSON.parse_string(FileAccess.get_file_as_string(str(model.animationMap))) as Dictionary).get("actions",{})
    var all_mapped:=true
    for id:String in Scene.scene_definitions():
        if id.begins_with("measure.lamps."):
            for cue:Dictionary in Scene.scene_definitions()[id].get("cues",[]):
                all_mapped=all_mapped and (native_actions[cue.actor] as Dictionary).has(str(cue.action))
    expect(all_mapped,"every new NPC cue names a real approved animation in that character's native map")
    for malformed:Dictionary in [{"settings":{"marker":3}},{"cycle":4},{"water":"one"},{"prediction":{"revision":-1}},{"prediction":{"candidate":4}},{"prediction":{"can_choose":1}},{"observations":[{"cycle":4}]},{"evidence_secure":"yes"},{"equipment_tile":[1.5,2]},{"safe_phase":1},{"correct_candidate":0}]:
        var bad:=s.duplicate(true);bad.lamps.merge(malformed,true)
        expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).get("type")=="invalid","malformed readings, prediction or hidden answer fields are rejected")
    for approach:String in ["protect","brace","maintenance"]:
        for method:String in ["isolate","witnessed_move","independent_measure"]:
            s.lamps.approach=approach;s.lamps.evidence_method=method
            expect(EloriaProtocol.decode_campaign(JSON.stringify(s).to_utf8_buffer()).get("type")=="campaign",approach+" / "+method+" remains an available physical path")
    var adapter:=CoordinateAdapter.new({"serverOrigin":[435,448],"metresPerTile":1.0,"walkingHeight":2.5})
    var works:=Works.new();root.add_child(works)
    var resident:=[false]
    var sample:=func(point:Vector3)->float:return height(point) if resident[0] else NAN
    works.apply_snapshot(s,adapter,"greenlight",sample)
    expect(works.lamp==null and not works.visible,"a cold bay never receives floating apparatus at fallback height")
    resident[0]=true;works.apply_snapshot(s,adapter,"greenlight",sample);works._process(1)
    expect(works.lamp!=null and works.gate!=null and works.equipment!=null,"approved native lamp, gate and local equipment form the apparatus")
    expect(works.lamp.scale.is_equal_approx(Vector3.ONE),"the native lantern keeps its original transform under a unit wrapper")
    expect(absf(works.lamp.global_position.y-height(Vector3.ZERO))<0.01,"the existing lamp stands on actual bay ground")
    expect(works.labels.lamp.text.contains("○") and works.labels.lamp.text.contains("ALIGNED"),"shape and words duplicate the light signal")
    var bright:float=works.lamp_light.light_energy
    var marker_before:Vector3=works.threshold_mark.global_position
    s.lamps.marker_number=1;s.lamps.settings.marker=0;s.lamps.water=2;s.lamps.lamp_word="ABOVE MARK";s.lamps.lamp_shape="triangle";s.lamps.indicator="raised"
    works.apply_snapshot(s,adapter,"greenlight",sample);works._process(1)
    expect(works.threshold_mark.global_position.y<marker_before.y,"the marker setting changes a visible physical threshold")
    expect(works.labels.lamp.text.contains("△") and works.lamp_light.light_energy<bright,"a contradiction changes shape, text and actual light energy")
    s.lamps.beam_height=2;s.lamps.settings.shutter=1
    works.apply_snapshot(s,adapter,"greenlight",sample)
    expect(absf(works.beam_mark.global_position.y-works.points.indicator.y-1.1)<0.01,"the lamp-height setting moves the visible beam reference")
    s.lamps.settings.bleed=2;s.lamps.water=0;s.lamps.lamp_word="OFF BEAM";s.lamps.lamp_shape="square"
    works.apply_snapshot(s,adapter,"greenlight",sample,true)
    expect(absf(works.gauge_marker.global_position.y-works._gauge_base.y-0.3)<0.01,"drain readings change the water marker immediately in reduced motion")
    var cycle:int=s.lamps.cycle;works._process(60)
    expect(s.lamps.cycle==cycle and works.lamps.cycle==cycle,"elapsed time never advances the controlled experiment")
    s.lamps.evidence_method="witnessed_move";works.apply_snapshot(s,adapter,"greenlight",sample)
    expect(adapter.godot_to_server(works.equipment.global_position)==Vector2i(337,411),"naming a move does not teleport the physical fitting")
    s.lamps.equipment_tile=[337,412];works.apply_snapshot(s,adapter,"greenlight",sample)
    expect(adapter.godot_to_server(works.equipment.global_position)==Vector2i(337,412),"the local fixture follows only a new accepted physical position")
    expect(works.service_light.light_energy==0,"a supplied holder is unlit before its real wick work")
    s.lamps.supplies={"lamp_built":true,"lamp_fat":0}
    works.apply_snapshot(s,adapter,"greenlight",sample)
    expect(works.service_light.light_energy>0 and not s.lamps.lamp_done,"the shared physical wick lights before a person's optional receipt is earned")
    s.lamps.lamp_done=true;works.apply_snapshot(s,adapter,"greenlight",sample)
    expect(works.service_light.light_energy>0 and works.labels.service_lamp.text.contains("tested"),"the optional completed service wick gives visible light")
    works.set_readouts_visible(false)
    expect(not works.labels.lamp.visible and not works.pointer.visible and not works.gauge_marker.visible,"speaking shots suppress all field labels and indicator geometry")
    var hud:=Hud.new();root.add_child(hud);hud.apply_state(s,Vector2i(325,412),"greenlight")
    expect(hud._lamps.text.contains("minimum 0") and hud._lamps.text.contains("lamp height"),"the guide explains the nonnegative water reading in ordinary words")
    s.lamps.challenge=true;s.lamps.prediction.can_choose=true
    hud.apply_state(s,Vector2i(325,412),"greenlight")
    var all_equal:=true
    for button:Button in hud._prediction_buttons:all_equal=all_equal and not button.disabled
    expect(hud._prediction_actions.visible and hud._prediction_buttons.size()==4 and all_equal,"all four candidate intervals are equally available at the physical test station")
    var choices:Array=[];hud.prediction_requested.connect(func(id:String,revision:int,candidate:int)->void:choices.append([id,revision,candidate]))
    for button:Button in hud._prediction_buttons:button.pressed.emit()
    expect(choices.size()==4 and choices[3]==["lamps-fixture",4,3],"choosing an interval sends only the person's candidate and current trial epoch")
    expect(s.lamps.prediction.status=="unselected","a local button never verifies its own prediction")
    s.lamps.prediction.can_choose=false;hud.apply_state(s,Vector2i.ZERO,"greenlight");hud._request_prediction(0)
    expect(choices.size()==4,"a person outside the eligible station cannot send a prediction")
    hud.apply_state(s,Vector2i.ZERO,"twinbrook")
    expect(not hud._prediction_actions.is_visible_in_tree(),"stale foreign-map puzzle controls are hidden")
    s.lamps.prediction.can_choose=true;s.lamps.prediction.status="contradicted";s.lamps.prediction.feedback="Water2 differs from beam1; retry freely."
    hud.apply_state(s,Vector2i(325,412),"greenlight")
    expect(hud._lamps.text.contains("retry freely"),"wrong predictions explain the observed contradiction without deleting work")
    s.lamps.evidence_readings=[{"post":"fitting","value":1,"claimed":2}]
    s.lamps.inheritance={"worker_ally":true,"refuge_provisions":true}
    hud.apply_state(s,Vector2i(325,412),"greenlight")
    expect(hud._lamps.text.contains("measured 1 / claimed 2") and hud._lamps.text.contains("Nessa") and hud._lamps.text.contains("Oyun"),"independent equipment readings and bounded Road callbacks remain visible")
    s.lamps.unsafe_zones=[{"key":"outer_work","bounds":[312,408,318,414],"active":true}]
    works.apply_snapshot(s,adapter,"greenlight",sample)
    expect(works.zones.size()==1 and works.labels.zone_outer_work.text.contains("STOP"),"current closed work strips have written and physical boundary indicators")
    works.set_readouts_visible(false)
    expect(not works.zones.outer_work.visible,"speaker closeups suppress hazard overlays as well as other readouts")
    var rig:=Fixture.Rig.new();root.add_child(rig);var camera:=Camera3D.new();rig.add_child(camera);rig.camera=camera;camera.position=Vector3(4,14,12);var before:=camera.global_transform
    var actors:Dictionary={}
    for row:Array in [[1,338,427],[2,336,431],[3,315,411],[4,334,414]]:
        var actor:=Fixture.Actor.new();root.add_child(actor);actor.position=adapter.tile_center(row[1],row[2]);actor.position.y=height(actor.position);actor.post=actor.global_transform;actors[row[0]]=actor
    var scene:=Scene.new();root.add_child(scene);scene.set_reduced_motion(false,false)
    scene.update(0,s,rig,actors,1,"greenlight",true,adapter,sample)
    expect(scene.playing and scene.transcript_text().contains("stays under witnessed hold"),"the held Road fitting remains held in Edda's actual opening dialogue")
    scene.update(11,s,rig,actors,1,"greenlight",true,adapter,sample)
    expect(scene.work_readouts_visible(),"the practical apparatus cut reveals its readings")
    scene.skip()
    expect(not scene.blocks_input() and camera.global_transform.is_equal_approx(before) and actors[2].restored,"skip restores camera, input and staged Edda")
    s.scene={"id":"measure.lamps.admission","token":"admission"};s.lamps.evidence_secure=false
    scene.update(0,s,rig,actors,1,"greenlight",true,adapter,sample)
    expect(not scene.is_active(),"Voss cannot begin his admission before equipment evidence is secured")
    s.lamps.evidence_secure=true;scene.update(0,s,rig,actors,1,"greenlight",true,adapter,sample)
    expect(scene.playing and scene.transcript_text().contains("I hid which crew would wait"),"secured independent evidence precedes Voss's responsibility exchange")
    expect(scene.get("_anchors").get("equipment_current")==works.equipment.global_position,"the evidence camera binds the currently accepted crate position rather than its old installation post")
    scene.skip();s.scene={};s.lamps.holder="Edda Tine";s.lamps.holder_active=true
    scene.update_ambient(s,actors,adapter,sample,1)
    expect(actors[2].global_position.distance_to(adapter.tile_center(336,431))<2,"a distant Edda never teleports to a requested holding post")
    actors[2].position=adapter.tile_center(333,419);actors[2].position.y=height(Vector3.ZERO);actors[2].post=actors[2].global_transform
    scene.update_ambient(s,actors,adapter,sample,1)
    expect(adapter.godot_to_server(actors[2].global_position)==Vector2i(333,418) and actors[2].action==&"defend","a physically arrived Edda takes the reversible one-metre hand-contact stance")
    s.lamps.holder="";s.lamps.holder_active=false;scene.update_ambient(s,actors,adapter,sample,1)
    expect(actors[2].global_transform.is_equal_approx(actors[2].post),"releasing Edda restores her real held-post pose")
    var network:=root.get_node("Network");var recorder:=GDScript.new()
    recorder.source_code='extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
    expect(recorder.reload()==OK,"the offline production transport recorder compiles")
    network.set_script(recorder);network.call("block_for_hud_preview")
    expect(network.call("campaign_predict","lamps-fixture",4,3)==OK,"the native prediction command uses its explicit run and epoch")
    expect(network.call("campaign_predict","lamps-fixture",4,4)==ERR_INVALID_PARAMETER and network.call("campaign_predict","bad id",4,0)==ERR_INVALID_PARAMETER,"invalid candidates or identities never reach the transport")
    var main:Node=(load("res://src/app/main.tscn") as PackedScene).instantiate();root.add_child(main);await process_frame;main.hide()
    var app:=root.get_node("AppState");app.set("campaign",s);app.set("current_map","greenlight");s.lamps.prediction.can_choose=true
    var frames:Array=network.get("sent_frames");frames.clear();main.call("_on_campaign_prediction","lamps-fixture",4,0)
    expect(frames.size()==1,"Main accepts a current eligible physical-station prediction")
    main.call("_on_campaign_prediction","lamps-fixture",3,0);main.call("_on_campaign_prediction","old-run",4,0)
    expect(frames.size()==1,"Main rejects stale trial epochs and other encounter identities")
    app.set("current_map","twinbrook");main.call("_on_campaign_prediction","lamps-fixture",4,0)
    expect(frames.size()==1,"Main rejects cross-map predictions")
    works.apply_snapshot(s,adapter,"twinbrook",sample)
    expect(not works.visible and works.lamp==null and works.equipment==null,"leaving the bay removes every private prop and readout")
    main.queue_free()
    for node:Node in [hud,scene,works,rig]:node.queue_free()
    for actor:Node in actors.values():actor.queue_free()
    await process_frame;await process_frame
    print("campaign lamps: ",checks," checks; ",failures," failures")
    quit(1 if failures else 0)
