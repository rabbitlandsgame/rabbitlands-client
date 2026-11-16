extends "res://tests/test_shelves_dialogue_flow.gd"
## Exercise actual choice buttons, Main and the production transport together.

const DECISIONS:Dictionary={
	"shelves_fire_quarry":["measure.shelves.fire.entry_quarry","fire",["assault","silence"]],
	"shelves_fire_coal":["measure.shelves.fire.entry_coal","fire_coal",["lift","haul"]],
	"shelves_fire_retry":["measure.shelves.fire.retry","fire",["retry","cancel"]],
	"shelves_water_gates":["measure.shelves.water.entry_water","water",["repair","breach"]],
	"shelves_water_route":["measure.shelves.water.entry_water_barge","water_barge",["sheltered","coastal"]],
	"shelves_water_retry":["measure.shelves.water.retry","water",["retry","cancel"]],
	"shelves_patrol_retry":["measure.shelves.growers.retry","life",["retry","cancel"]]}

func run()->void:
	var network:Node=root.get_node("Network")
	var recorder:=GDScript.new()
	recorder.source_code='extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload()==OK,"the production transport recorder compiles")
	network.set_script(recorder);network.call("block_for_hud_preview")
	var frames:Array=network.get("sent_frames")
	var app:Node=root.get_node("AppState")
	var main:Node=load("res://src/app/main.gd").new()
	for identity:String in DECISIONS:
		var definition:Array=DECISIONS[identity]
		for option:String in definition[2]:
			var f:=fixture(str(definition[0]))
			f.state.key=str(definition[1])
			var choices:Array=[]
			for offered:String in definition[2]:choices.append({"id":offered,"label":offered.capitalize(),"detail":"Use this plan."})
			f.state.scene.choice={"id":identity,"title":"Choose our plan","owner":"You","owner_is_you":true,
				"can_choose":true,"selected":"","response":"","options":choices}
			app.authenticated=true;app.death={};app.current_map="landfall_town";app.campaign=f.state
			main.set("campaign_scene",f.scene)
			f.scene.choice_requested.connect(main._on_campaign_scene_choice)
			tick(f);f.scene.skip();tick(f)
			expect(f.scene._choice_waiting,identity+" opens the actual decision")
			frames.clear()
			(f.scene._choice_dialog.option_buttons[option] as Button).pressed.emit()
			expect(frames==[EloriaProtocol.chat("#campaign shelves_choice supplies one "+option)],option+" sends the exact scene-bound request")
			expect(f.scene._choice_pending_at>=0 and f.scene._choice_error.is_empty(),option+" waits for confirmation without a false send error")
			expect(str(f.state.scene.choice.selected).is_empty(),option+" does not invent a local outcome")
			(f.scene._choice_dialog.option_buttons[option] as Button).pressed.emit()
			expect(frames.size()==1,option+" cannot send twice while awaiting confirmation")
			f.state.scene.choice.selected=option;f.state.scene.choice.can_choose=false
			f.state.scene.choice.response="The crew acknowledges "+option+" and explains the next step."
			tick(f)
			expect(f.scene._dialogue.body_label.text==f.state.scene.choice.response and f.scene._choice_pending_at<0,option+" displays the confirmed NPC reply")
			main.set("campaign_scene",null);dispose(f)
	for identity:String in EloriaProtocol.SHELVES_CHOICE_OPTIONS:
		for option:String in EloriaProtocol.SHELVES_CHOICE_OPTIONS[identity]:
			frames.clear()
			expect(network.call("campaign_shelves_choice","supplies","one",option)==OK and frames==[EloriaProtocol.chat("#campaign shelves_choice supplies one "+option)],identity+" keeps its decoded options sendable")
	for args:Array in [["bad run","one","assault"],["supplies","bad token","silence"],["supplies","one","steal"]]:
		frames.clear()
		expect(network.call("campaign_shelves_choice",args[0],args[1],args[2])==ERR_INVALID_PARAMETER and frames.is_empty(),"invalid identities or options never reach the wire")
	app.authenticated=false;app.campaign={};app.death={}
	main.free();await process_frame;await process_frame
	print("Supply choice wiring: %d checks; %d failures" % [checks,failures])
	quit(1 if failures else 0)
