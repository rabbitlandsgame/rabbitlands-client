extends SceneTree
const Hud := preload("res://src/ui/campaign_hud.gd")
var checks := 0
var failures := 0
var guide: Control
var hud: Control
var windows: Control
var app: Node
var output := ""

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ",message)
	else:
		failures += 1
		push_error(message)
func settle() -> void:
	for frame: int in range(4): await process_frame
func show_state(state: Dictionary, map := "greenlight") -> void:
	hud.apply_state(state,Vector2i(450,308),map,false,false)
	guide.apply_campaign(state)
	await settle()
func campaign_row() -> int:
	for index: int in windows._quest_entries.size():
		if bool(windows._quest_entries[index].get("_campaign",false)): return index
	return -1
func select_row(index: int) -> void:
	windows.quest_list.select(index)
	windows.quest_list.item_selected.emit(index)
func sample() -> Dictionary:
	return {"version":1,"active":true,"started":true,"available":false,"run_id":"opening-a","map":"greenlight","title":"The Ferry That Arrived Twice","key":"assess","hint":"Inspect the landing before choosing how to rescue the worker.","scene":{"id":"measure.landing.arrival","token":"arrival"},"targets":[{"id":"assess","object_id":61001,"label":"Inspect the landing","tile":[450,310],"enabled":true,"completed":false}],"party":{},"adoption":{}}
func capture(name: String) -> void:
	if output.is_empty() or DisplayServer.get_name()=="headless": return
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(output.path_join(name+".png"))==OK,"captured "+name)

func run() -> void:
	create_timer(90).timeout.connect(func()->void:push_error("The campaign quest UI probe timed out");quit(1))
	root.size=Vector2i(1280,720)
	output=OS.get_environment("RL_CAMPAIGN_QUEST_UI_OUT")
	if not output.is_empty():DirAccess.make_dir_recursive_absolute(output)
	app=root.get_node("AppState");app.authenticated=true
	var network:=root.get_node("Network");var recorder:=GDScript.new()
	recorder.source_code='extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload()==OK,"the offline transport recorder compiles")
	network.set_script(recorder);network.call("block_for_hud_preview")
	var owner:=Control.new();root.add_child(owner)
	guide=(load("res://src/ui/lantern_guide.gd") as GDScript).new();root.add_child(guide);guide.configure(owner);guide.set_process(false)
	hud=Hud.new();root.add_child(hud);guide.attach_campaign(hud)
	windows=(load("res://src/ui/extension_windows.gd") as GDScript).new();root.add_child(windows);windows.configure(null,guide)
	app.quest_journal.clear();app.quest_journal.append({"title":"Ordinary work","objective":"Find the lost bundle.","location":"Four Gates","current":0,"target":1,"ready":false})
	app.state_changed.emit(&"quest_journal")
	var state:=sample();state.active=false;state.started=false;state.available=true;state.erase("run_id")
	await show_state(state)
	expect(campaign_row()>=0 and not guide.is_campaign_tracked() and not guide.visible,"an available contact gets a journal entry without opening a second field window")
	state=sample();await show_state(state)
	expect(guide.is_campaign_tracked() and guide.using_campaign() and guide.card.is_visible_in_tree(),"a newly accepted active expedition uses the existing quest card automatically")
	expect(hud is Control and guide.card.is_ancestor_of(hud) and hud._panel.get_parent()==hud,"all interactive controls live inside the existing guide card, with no campaign CanvasLayer")
	expect(guide.instruction.is_visible_in_tree() and guide.instruction.text.contains("Inspect the landing"),"expanded field instructions retain the current objective inside the bounded shared card")
	state.map="maps/nymara/greenlight.elm";await show_state(state)
	expect(guide.campaign_entry().location=="Greenlight","journal locations display the world name instead of internal compatibility paths")
	expect(app.quest_journal.size()==1 and not app.quest_journal[0].has("_campaign"),"the current-expedition row does not alter the server's journal")
	expect(windows._quest_entries.size()==2,"a campaign with no exact row is represented once beside ordinary quests")
	select_row(campaign_row());expect(windows.quest_track_button.text=="Untrack","the existing journal recognizes the automatically tracked campaign")
	guide.collapse.pressed.emit();await settle()
	expect(guide.compact and not hud.visible and guide.collapse.text=="Instructions","the existing Less control minimizes the campaign instructions")
	state.hint="Check the cargo seal.";state.scene.token="evidence";state.key="seal";state.title="One Cargo Two Claims"
	await show_state(state)
	expect(guide.compact and guide.is_campaign_tracked() and not hud.visible,"progress and a new scene preserve the minimized choice for the same run")
	expect(bool(windows._quest_entries[windows.quest_list.get_selected_items()[0]].get("_campaign",false)),"progress retains the selected expedition row when its title changes")
	guide.collapse.pressed.emit();guide.untrack.pressed.emit();await settle()
	expect(not guide.is_campaign_tracked() and not guide.card.visible and windows.quest_track_button.text=="Track","the same Untrack button hides the campaign and updates the journal")
	await show_state(state)
	expect(not guide.visible,"restating the campaign never reopens an explicitly untracked card")
	select_row(campaign_row());windows.quest_track_button.pressed.emit();await settle()
	expect(guide.visible and guide.heading.text=="One Cargo Two Claims" and hud.visible,"Track restores the latest shared work in the existing card")
	var frames:Array=network.get("sent_frames")
	expect(frames.is_empty(),"campaign tracking and minimizing never send a dispatch tracking or gameplay command")
	state.map="twinbrook";state.phase="brook";state.scene.token="brook-arrival";await show_state(state,"twinbrook")
	expect(guide.is_campaign_tracked(),"a normal phase/map transition retains run-stable tracking")
	state.travel={"map":"landfall","npc":"Ammet Sorrel","route":"Follow the public roads."};await show_state(state,"greenlight")
	expect(not hud._scroll.visible and hud._targets.get_child_count()>0,"travel hides physical interaction controls while retaining their saved state")
	state.erase("travel");await show_state(state,"greenlight")
	expect(not hud.presentation_available() and not guide.card.visible,"a foreign-map state cannot expose campaign use or movement controls")
	state=sample();state.kind="bank";state.run_id="grove-a";state.title="The Brook's Other Bank";state.scene={};state.targets[0].label="Inspect the remaining tree care"
	app.quest_journal.clear();app.state_changed.emit(&"quest_journal");await show_state(state)
	expect(windows._quest_entries.size()==1 and campaign_row()==0,"optional work stays accessible when there is no main journal row")
	state.adoption={"state":"pending","run_id":"grove-a","revision":3,"can_adopt":false,"summary":"Record the earlier route only if you agree.","reason":"Complete your own observation first."};await show_state(state)
	select_row(0)
	expect(windows.quest_detail.text.contains("earlier route") and windows.quest_detail.text.contains("own observation"),"a learner's earlier personal account stays distinct from the current shared work")
	app.quest_archive.clear();app.quest_archive.append({"title":"An old account","location":"Coast","detail":"Recorded earlier."});windows._on_quest_view(true)
	expect(windows.quest_list.item_count==1 and not windows.quest_replay_button.visible,"a dynamic expedition entry is never fabricated into the completed archive")
	windows._on_quest_view(false)
	var replayed:=[0];hud.replay_requested.connect(func()->void:replayed[0]+=1)
	hud.set_replay_available(false);windows.sync_campaign_replay()
	expect(windows.quest_replay_button.visible and windows.quest_replay_button.disabled,"journal replay is visible but unavailable before the scene is ready")
	hud.set_replay_available(true);windows.sync_campaign_replay();windows.quest_replay_button.pressed.emit()
	expect(replayed[0]==1,"the existing quest journal requests a local replay without a tracking prerequisite")
	expect(frames.is_empty(),"a replay button sends no network acknowledgment or reward request")
	guide.apply_state({"active":true,"tutorial":"signed_ashore","title":"Speak to Nash","hint":"Meet the guide."})
	guide.set_campaign_tracked(false);await settle()
	expect(guide.visible and guide.quest_title()=="Signed Ashore","untracking an expedition restores the existing tutorial preference")
	guide.set_campaign_tracked(true)
	app.quest_journal.clear();app.quest_journal.append({"title":"Signed Ashore","objective":"Speak to Nash","location":"Greenlight","current":0,"target":1,"ready":false});app.state_changed.emit(&"quest_journal")
	select_row(0);expect(windows.quest_track_button.text=="Track","the journal offers to select the standard guide behind an expedition")
	windows.quest_track_button.pressed.emit();await show_state(state)
	expect(guide.quest_title()=="Signed Ashore" and guide.visible and guide.is_quest_tracked() and not guide.using_campaign(),"the real journal Track button restores a still-tracked standard guide without toggling it off")
	expect(frames.is_empty(),"switching to an already tracked standard guide does not issue a redundant dispatch command")
	select_row(campaign_row());expect(windows.quest_track_button.text=="Track","the background expedition offers Track when the standard guide owns the card")
	windows.quest_track_button.pressed.emit();await settle()
	expect(guide.using_campaign() and guide.card.visible and windows.quest_track_button.text=="Untrack","the real journal button restores the saved expedition in one click")
	guide.set_campaign_tracked(true);state.run_id="grove-b";await show_state(state)
	expect(guide.is_campaign_tracked(),"a separately accepted active run opens once with its own tracking choice")
	guide.set_campaign_tracked(false);state.run_id="grove-a";await show_state(state)
	expect(guide.is_campaign_tracked(),"returning to the prior run restores that run's independent choice")
	app.quest_journal.append({"title":"Another ordinary quest","objective":"Gather three supplies","location":"Four Gates","current":1,"target":3,"ready":false});app.state_changed.emit(&"quest_journal")
	select_row(1);windows.quest_track_button.pressed.emit();guide.set_campaign_tracked(true);await settle()
	expect(windows._tracked_quest_title=="Another ordinary quest" and not windows.tracked_quest.visible,"the expedition temporarily yields the one guide surface without deleting an ordinary pinned note")
	var public_complete:=state.duplicate(true);public_complete.active=false;public_complete.started=true;public_complete.available=false;public_complete.travel={};public_complete.party={"can_join":false,"can_start_own":false}
	await show_state(public_complete)
	expect(not guide.has_campaign() and campaign_row()==-1 and guide.quest_title()=="Signed Ashore","a fully quiescent public completion removes the expedition row and restores the standard guide")
	expect(windows.tracked_quest.visible and windows.tracked_quest_text.text.contains("Another ordinary quest"),"the ordinary pinned quest returns after the expedition becomes quiescent")
	public_complete.travel={"map":"landfall","npc":"Ammet Sorrel","route":"Return for optional field work."};await show_state(public_complete)
	expect(guide.has_campaign() and campaign_row()>=0,"unfinished optional travel retains its real expedition entry")
	await show_state(state)
	expect(guide.has_campaign(),"an active private ending remains available for local replay even after main rewards")
	app.quest_journal.clear();app.quest_journal.append({"title":"The Ferry That Arrived Twice","objective":"Original server objective","location":"Greenlight","current":0,"target":3,"ready":false});app.state_changed.emit(&"quest_journal")
	state=sample();await show_state(state)
	expect(windows._quest_entries.size()==1 and campaign_row()==0,"an exact opening title reuses its existing journal row")
	guide.set_campaign_tracked(true);hud.set_replay_available(true)
	await capture("campaign-existing-quest-card-1280x720")
	windows.toggle_quest_journal();select_row(campaign_row());windows.sync_campaign_replay();await settle();await capture("campaign-existing-journal-replay-1280x720")
	windows.quest_panel.hide();root.size=Vector2i(720,480);root.content_scale_factor=1.5
	await show_state(state);guide._process(0);await settle();hud._body_scroll.ensure_control_visible(hud._replay);await settle()
	var clip:Rect2=hud._body_scroll.get_global_rect().intersection(root.get_visible_rect())
	expect(clip.encloses(hud._replay.get_global_rect()),"replay remains reachable by scrolling in a small 150-percent window")
	expect(root.get_visible_rect().encloses(guide.card.get_global_rect()),"the shared quest card fits the small scaled viewport")
	await capture("campaign-existing-quest-card-720x480-150-percent")
	guide.apply_campaign({});await settle()
	expect(not guide.has_campaign() and not windows._quest_entries[0].get("_campaign",false),"clearing the expedition removes only its local journal presentation")
	for node:Node in [guide,windows,owner]:node.queue_free()
	await process_frame;await process_frame
	print("campaign quest UI: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
