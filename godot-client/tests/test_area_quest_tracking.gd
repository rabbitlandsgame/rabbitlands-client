extends SceneTree
var checks:=0
var failures:=0
func _init()->void:run.call_deferred()
func expect(value:bool,message:String)->void:
	checks+=1
	if not value:failures+=1;push_error(message)
func last_focus(network:Node)->Array:
	if network.sent_frames.is_empty():return ["missing report"]
	var text:String=(network.sent_frames.back() as PackedByteArray).slice(3).get_string_from_utf8()
	return JSON.parse_string(text.trim_prefix("#questfocus ")) if text.begins_with("#questfocus ") else [text]
func run()->void:
	create_timer(60).timeout.connect(func()->void:push_error("Area quest tracking checks timed out");quit(1))
	var network:=root.get_node("Network");network.block_for_hud_preview()
	var recorder:=GDScript.new()
	recorder.source_code='extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload()==OK,"the native request recorder compiles")
	network.set_script(recorder);network.block_for_hud_preview()
	var app:=root.get_node("AppState");app.authenticated=false;app.campaign={};app.lantern_tutorial={};app.quest_journal.clear()
	var main:Control=load("res://src/app/main.tscn").instantiate();root.add_child(main)
	main.set_process(false);main.set_physics_process(false);await process_frame
	var windows:Control=main.extension_windows;var guide:Control=main.lantern_guide
	app.authenticated=true
	expect(network.report_quest_tracking([])==ERR_UNAVAILABLE,"offline previews do not report UI preferences to a server")
	network.offline_hud_preview=false
	expect(network.report_quest_tracking([])==ERR_UNAVAILABLE,"tracking waits until capabilities have been sent")
	network.send_client_capabilities();network.sent_frames.clear();windows.report_quest_tracking()
	expect(last_focus(network)==[] and network.sent_frames.size()==1,"login explicitly reports that no quest is tracked")
	windows.report_quest_tracking();expect(network.sent_frames.size()==1,"unchanged tracking does not send repeated reports")
	app.quest_journal.clear();app.quest_journal.append({"title":"Ordinary quest","objective":"Gather supplies","location":"Four Gates","current":0,"target":3,"ready":false})
	windows._sync_quests();windows._on_quest_track_pressed()
	expect(last_focus(network)==["Ordinary quest"],"the actual ordinary Track button reports the selected quest")
	var sent:int=network.sent_frames.size();windows._on_quest_hide_pressed()
	expect(windows.tracked_quest_titles()==["Ordinary quest"] and network.sent_frames.size()==sent,"Hide retains tracking and cannot enable an automatic area start")
	windows._on_quest_untrack_pressed();expect(last_focus(network)==[],"the actual ordinary Untrack button clears the server preference")
	guide.apply_campaign({"kind":"shelves","active":true,"started":true,"run_id":"tracking-probe","title":"A Field Worth Saving","hint":"Gather the growers’ shipment.","map":"landfall","scene":{}})
	expect(last_focus(network)==["A Field Worth Saving"],"campaign tracking is reported through the same quest window")
	sent=network.sent_frames.size();guide.hide_window()
	expect(windows.tracked_quest_titles()==["A Field Worth Saving"] and network.sent_frames.size()==sent,"a hidden campaign window remains tracked")
	guide.set_campaign_tracked(false);expect(last_focus(network)==[],"campaign Untrack releases the area-start guard")
	guide.apply_state({"active":true,"tutorial":"signed_ashore","title":"A tutorial step","text":"Learn to move."})
	expect(last_focus(network)==["Signed Ashore"],"tutorial tracking reports its stable journal title")
	guide.set_quest_tracked(false);expect(last_focus(network)==[],"tutorial Untrack clears tracking")
	windows.quest_list.select(0);windows._on_quest_track_pressed()
	expect(last_focus(network)==["Ordinary quest"],"ordinary tracking still works after choosing another guide")
	app.quest_journal.clear();windows._sync_quests()
	expect(last_focus(network)==[],"removing a completed quest from the journal clears its tracking report")
	network._set_state("disconnected",true)
	expect(network.report_quest_tracking([])==ERR_UNAVAILABLE,"disconnect invalidates tracking negotiation")
	app.authenticated=true
	network.send_client_capabilities();network.sent_frames.clear();windows.report_quest_tracking()
	expect(network.sent_frames.size()==1 and last_focus(network)==[],"a reconnect resends even an unchanged empty selection")
	sent=network.sent_frames.size()
	expect(network.report_quest_tracking(["bad\nname"])==ERR_INVALID_PARAMETER and network.sent_frames.size()==sent,"malformed title updates are not transmitted")
	network.offline_hud_preview=true;app.authenticated=false
	main._clear_world_presentation();main.queue_free();await process_frame
	print("Area quest tracking: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
