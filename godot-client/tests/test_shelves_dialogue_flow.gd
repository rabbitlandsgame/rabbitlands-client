extends SceneTree
## Manual reading and delayed native replies keep one visible conversation.
const Ready := preload("res://tests/test_campaign_scene_recovery.gd")
const Scene := preload("res://src/world/campaign_scene.gd")
const Supplies := preload("res://tests/test_campaign_shelves.gd")
const Hud := preload("res://src/ui/campaign_hud.gd")
const Mini := preload("res://src/ui/minimap_marker_overlay.gd")
var checks:=0
var failures:=0
func _init()->void:run.call_deferred()
func expect(ok:bool,message:String)->void:
	checks+=1
	if not ok:failures+=1;push_error(message)
func fixture(id:String)->Dictionary:
	var rig:=IsometricCameraController.new();var camera:=Camera3D.new();camera.name="Camera"
	rig.add_child(camera);camera.owner=rig;camera.unique_name_in_owner=true;root.add_child(rig)
	var player:=Ready.Actor.new();var mentor:=Ready.Actor.new();root.add_child(player);root.add_child(mentor)
	mentor.position=Vector3(3,0,0);mentor.server_target=mentor.position;rig.set_focus(player.position)
	var scene:=Scene.new();root.add_child(scene);scene.set_auto_dialogue(false,false)
	scene._definitions=Scene.scene_definitions();scene._definition=scene._definitions[id].duplicate(true)
	scene._scene_id=id;scene._token="one";scene._run="supplies";scene._map="landfall_town"
	var actors:Dictionary={"mentor":2,"protagonist":1,"recipient":1}
	var nodes:Dictionary={1:player,2:mentor}
	scene._start(rig,rig.camera,player,nodes,actors)
	var state:Dictionary={"active":true,"kind":"shelves","run_id":"supplies","map":"landfall_town",
		"scene":{"id":id,"token":"one","requires_ack":true,"actors":actors}}
	var acks:Array=[];scene.presentation_finished.connect(func(token:String,_reason:String)->void:acks.append(token))
	return {"scene":scene,"rig":rig,"player":player,"mentor":mentor,"nodes":nodes,"state":state,"acks":acks}
func tick(f:Dictionary,seconds:=0.016)->void:
	f.scene.update(seconds,f.state,f.rig,f.nodes,1,"landfall_town",true)
func dispose(f:Dictionary)->void:
	f.scene.cancel("test_done");f.scene.queue_free();f.rig.queue_free();f.player.queue_free();f.mentor.queue_free()
func run()->void:
	root.get_node("Network").block_for_hud_preview()
	var transitions:Dictionary={"gathered":["mixing_life","mixing_fire","mixing_water"],
		"delivery":["accepted_fire","accepted_water","trainer"]}
	for current:String in transitions:
		for following:String in transitions[current]:
			var f:=fixture("measure.shelves.basics."+current)
			expect(f.scene._dialogue.visible and not f.scene._dialogue.body_label.text.is_empty(),current+" shows its first line immediately")
			var last:String=f.scene._dialogue.body_label.text
			expect(f.scene.continue_dialogue(),current+" accepts Continue immediately")
			expect(f.acks==["one"] and f.scene.blocks_input(),current+" acknowledges once while holding the conversation")
			for _i:int in range(5):tick(f,0.2)
			expect(f.scene._layer.visible and f.scene._dialogue.visible and f.scene._dialogue.body_label.text==last,current+" retains its portrait and text during the native reply")
			f.state.scene={"id":"measure.shelves.basics."+following,"token":"two","requires_ack":true,"actors":f.state.scene.actors}
			tick(f)
			expect(f.scene.playing and f.scene._dialogue.visible and f.scene._dialogue.body_label.text!=last,following+" continues directly into the next line")
			tick(f,60)
			expect(f.scene.playing and f.scene._line_continue.visible,following+" waits for the player to finish reading")
			expect(f.scene.continue_dialogue() and not f.scene.blocks_input() and f.acks==["one","two"],following+" returns to play with one Continue after the new instructions")
			dispose(f)
	var f:=fixture("measure.shelves.basics.delivery");f.scene._replaying=true
	f.scene.continue_dialogue()
	expect(not f.scene.blocks_input() and f.acks.is_empty(),"replay finishes without acknowledging or waiting for a new reward")
	dispose(f)
	f=fixture("measure.shelves.basics.offer")
	var choice:Dictionary={"id":"shelves_basics","title":"Can you help?","owner":"Learner","owner_is_you":true,
		"selected":"","can_choose":true,"response":"","options":[
			{"id":"basics_accept","label":"What do you need?","detail":"Help"},
			{"id":"basics_defer","label":"Not right now","detail":"Later"}]}
	f.state.scene.choice=choice;tick(f)
	expect(f.scene._dialogue.visible and f.scene._line_continue.visible,"Ilka's opening line and Continue appear immediately")
	f.scene.continue_dialogue();tick(f)
	expect(f.scene._choice_waiting and f.acks.is_empty(),"one Continue opens the real decision without timed waits or acknowledging an unanswered choice")
	choice.selected="basics_accept";choice.can_choose=false;choice.response="Please gather the herbs."
	tick(f)
	expect(f.scene._dialogue.body_label.text==choice.response,"the native answer goes directly to Ilka's reply")
	f.scene.continue_dialogue()
	expect(not f.scene.blocks_input() and f.acks==["one"],"one Continue after the answer ends the conversation without repeating its opening")
	dispose(f)
	var hud:=Hud.new();root.add_child(hud)
	var state:=Supplies.snapshot();state.scene={};state.shelves.current_supply="Fire";state.shelves.unlocked=["Life"]
	state.shelves.objectives=[{"id":"flint","label":"Gather Flint","current":38,"target":50,"personal":true}]
	hud.apply_state(state,Vector2i.ZERO,"landfall")
	expect(hud._shelves.text.contains("Current supply: Fire Essence") and hud._shelves.text.contains("Restored stock: Life"),"the current Fire assignment is distinct from the restored Life stock")
	expect(not hud._shelves.text.contains("your practice"),"gathering objectives omit the practice suffix")
	expect(EloriaProtocol.decode_campaign(JSON.stringify(state).to_utf8_buffer()).type=="campaign","the current supply passes the native decoder")
	state.shelves.current_supply="Wood"
	expect(EloriaProtocol.decode_campaign(JSON.stringify(state).to_utf8_buffer()).type=="invalid","an unknown supply is rejected")
	state.shelves.current_supply="Fire";state.shelves.private_practice=true
	hud.apply_state(state,Vector2i(238,160),"landfall_town")
	expect(hud._leave.visible,"private temple practice retains its Return control inside the town map")
	var overlay:=Mini.new()
	var quest:Dictionary={"type":&"marker","quest":true,"label":"Coal"}
	var cave:Dictionary={"type":&"entrance","label":"Lantern Caves"}
	var own:Dictionary={"type":&"self"}
	var marks:Array[Dictionary]=[quest,own,cave]
	expect(overlay.draw_order(marks)==[cave,quest,own],"the coal quest marker draws above Lantern Caves while retaining the player's own mark")
	overlay.free();hud.queue_free()
	for _i:int in range(2):await process_frame
	print("Supply dialogue flow: %d checks; %d failures"%[checks,failures])
	quit(1 if failures else 0)
