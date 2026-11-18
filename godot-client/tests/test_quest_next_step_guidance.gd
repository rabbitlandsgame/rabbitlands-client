extends "res://tests/test_campaign_field_readout.gd"
const Guidance := preload("res://src/world/campaign_guidance.gd")

func settle() -> void:
	for _i: int in range(4):await process_frame

func raid_snapshot() -> Dictionary:
	var state: Dictionary=Supplies.snapshot()
	state.key="life_raid";state.title="Where the Raids Begin";state.stage="work";state.scene={}
	state.hint="Explore the Old Warren. Defeat the goblin and wolf packs, then find the raiders' leader."
	state.shelves.merge({"chapter":"life_raid","phase":"work","current_supply":"Life","unlocked":[],
		"objectives":[{"id":"orc","label":"Defeat the raiders' leader","current":0,"target":1,"personal":false}],
		"growers":{"field":"sage","raid":true,"stored":{"sage":10000,"root":5000},"carried":0,"wave":0,"workers":[]}},true)
	state.targets=[{"id":"return","object_id":61990,"tile":[100,100],"label":"Pause assignment","enabled":true},
		{"id":"storage","object_id":61992,"tile":[101,100],"label":"Personal supply cache","enabled":true}]
	return state

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	var app: Node=root.get_node("AppState");app.authenticated=true;app.current_map="landfall"
	var raid := raid_snapshot()
	expect(Guidance.work_targets(raid).size()==1, "the optional cache remains accessible without duplicating Return")
	expect(Guidance.legend(raid).begins_with("Follow the objective") and not Guidance.legend(raid).contains("Next: Personal"),
		"the raid objective stays ahead of a support-only cache")
	var waiting := raid.duplicate(true);waiting.party={"waiting_for_scene":true}
	expect(Guidance.legend(waiting).begins_with("Waiting for the party"), "a party scene barrier is explained even while its personal cache stays available")
	var preferred := raid.duplicate(true);preferred.preferred_targets=["storage"]
	expect(not Guidance.is_support_target(preferred,preferred.targets[1]) and Guidance.legend(preferred).begins_with("Next:"),
		"an explicit authoritative storage objective still takes priority")
	var hud: Control=load("res://src/ui/campaign_hud.gd").new();root.add_child(hud)
	var uses: Array=[];var actions: Array=[]
	hud.target_requested.connect(func(id: int,_tile: Vector2i,_near: bool) -> void:uses.append(id))
	hud.action_requested.connect(func(action: String) -> void:actions.append(action))
	hud.apply_state(raid,Vector2i(100,100),"landfall")
	expect(hud._guidance.visible and hud._guidance.text==Guidance.legend(raid), "the shared field card uses the objective-led raid guidance")
	expect(hud._targets.get_child(0).text=="Optional · Personal supply cache", "the optional cache does not look like the required next action")
	hud._request_target("storage",61992)
	expect(uses==[61992], "marking the cache as optional preserves its ordinary interaction")
	for chapter: String in ["magic","intro"]:
		var recovery := raid.duplicate(true);recovery.key=chapter;recovery.shelves.chapter=chapter
		recovery.targets[1]={"id":"practice","object_id":61991,"tile":[101,100],"label":"Resume the spider hunt" if chapter=="magic" else "Reopen spell practice","enabled":true}
		expect(not Guidance.is_support_target(recovery,recovery.targets[1]) and Guidance.legend(recovery).begins_with("Next:"),
			chapter+" recovery remains an actionable next step without requiring a server preference")
		hud.apply_state(recovery,Vector2i(100,100),"landfall")
		expect(not hud._targets.get_child(0).text.begins_with("Optional") and hud._targets.get_child(0).text==recovery.targets[1].label,
			chapter+" recovery keeps its normal field action")
	var objects := {};var adapter := CoordinateAdapter.new()
	var cache := MapObject3D.new();root.add_child(cache)
	cache.configure({"object_id":61992,"kind":EloriaProtocol.MAP_OBJECT_INTERACTIVE,"x":101,"y":100,"label":"Personal supply cache"},adapter,{"interactives":{"roles":{},"models":{}}})
	objects[61992]=cache
	var guidance := Guidance.new();root.add_child(guidance)
	guidance.apply_snapshot(raid,objects,{},"landfall",Vector2i(100,100),true,false)
	expect(guidance._labels.storage.text.begins_with("OPTIONAL") and not guidance._labels.storage.text.contains("NEXT"),
		"the world label also keeps the cache separate from the raid objective")
	expect(cache.collision_layer==MapObject3D.PICK_LAYER and cache.get_node("Ring").visible,
		"the useful optional cache remains visible and clickable")
	guidance.apply_snapshot(preferred,objects,{},"landfall",Vector2i(100,100),true,false)
	expect(guidance._labels.storage.text.begins_with("NEXT"), "the world label respects an explicit server preference")
	var lesson: Dictionary=Supplies.snapshot();lesson.scene={};lesson.stage="work";lesson.map="landfall_town"
	lesson.title="Practicing the Basics"
	lesson.hint="Cast Fire Bolt at the practice target."
	lesson.shelves.merge({"phase":"work","private_practice":true,"lesson_window":"spells",
		"objectives":[{"id":"lesson","label":"Cast Fire Bolt at the practice target","current":0,"target":1,"personal":true}]},true)
	lesson.targets=[{"id":"return","object_id":61990,"tile":[200,160],"label":"Leave temple practice","enabled":true}]
	hud.apply_state(lesson,Vector2i(200,160),"landfall_town")
	expect(hud._guidance.text.contains("Ostrid") and hud._guidance.text.contains("Open Magic") \
		and not hud._guidance.text.contains("work sites"), "a spell lesson explains casting instead of promising work circles")
	expect(hud._lesson_window.visible and hud._lesson_window.text=="Open Magic", "the lesson guidance names the existing available control")
	var helper := raid.duplicate(true);helper.map="landfall_town";helper.stage="report";helper.available=true
	helper.shelves.phase="report";helper.shelves.can_begin=false
	helper.hint="Return to Ilka at The True Note to finish helping the crew."
	helper.travel={"map":"landfall_town","tile":[178,26],"label":"Ilka Tarn — The True Note","route":helper.hint}
	helper.party={"role":"helper","owner":"Aster","members":[{"name":"Guest","role":"helper","online":true,"present":true,"adoption":"adopted"},
		{"name":"Aster","role":"owner","online":true,"present":true,"adoption":"adopted"}]}
	hud.apply_state(helper,Vector2i(178,26),"landfall_town")
	expect(hud._entry.text=="Finish helping at Ilka" and not hud._entry.tooltip_text.contains("reward"),
		"a helper's finish action promises a return to their own assignment")
	expect(hud._party.text.contains("Guest · helping") and not hud._party.text.contains("outcome recorded"),
		"a helper's participation is not misrepresented as personal story progress")
	expect(hud._party.text.contains("Aster · participating"), "an active supply owner is not described as having already recorded the unfinished quest")
	hud._request_entry();expect(actions==["shelves"], "a helper finishes through the existing authoritative report action")
	var captures: Dictionary={"raid":raid,"lesson":lesson}
	for variable: String in ["RL_BASICS_POLISH_EVIDENCE","RL_LIFE_POLISH_EVIDENCE"]:
		var path := OS.get_environment(variable)
		if path.is_empty():continue
		var records: Array=JSON.parse_string(FileAccess.get_file_as_string(path))
		expect(not records.is_empty(), "native next-step evidence is present")
		for record: Dictionary in records:
			var native: Dictionary=record.get("snapshot",record)
			var decoded := EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
			expect(decoded.type=="campaign", "native quest guidance decodes: "+str(decoded.get("error","")))
			var current_map := str(record.get("current_map",native.get("map","landfall")))
			var pins := Guidance.navigation_targets(native,current_map,true)
			expect(pins.all(func(pin: Dictionary) -> bool:return EloriaProtocol.map_id_from_reference(str(pin.get("map",current_map)))==EloriaProtocol.map_id_from_reference(current_map)),
				"native guidance keeps destination pins on their actual map")
			expect(Guidance.navigation_targets(native,current_map,false).is_empty(), "Untrack removes native quest markers")
			hud.apply_state(native,Vector2i.ZERO,current_map)
			var ledger: Dictionary=native.get("shelves",{})
			if bool(ledger.get("can_begin",false)) and not (native.get("travel",{}) as Dictionary).is_empty():
				expect(hud._entry.text==str(ledger.start_label), "nearby NPC guidance exposes the actual begin/resume action")
				actions.clear();hud._request_entry()
				expect(actions==["shelves"], "the native ready NPC action uses the existing supply quest dispatcher")
			if str(ledger.get("phase",""))=="report" and bool(native.get("available",false)) \
					and EloriaProtocol.map_id_from_reference(current_map)=="landfall_town":
				actions.clear();hud._request_entry()
				expect(actions==["shelves"], "the native final report action stays authoritative for owners and helpers")
			if str((native.get("party",{}) as Dictionary).get("role",""))=="helper" and str(ledger.get("phase",""))=="report" \
					and bool(native.get("available",false)) and EloriaProtocol.map_id_from_reference(current_map)=="landfall_town":
				expect(hud._entry.text=="Finish helping at Ilka" and not hud._entry.tooltip_text.contains("reward"), "native helper reporting keeps its own story and rewards separate")
			if bool(ledger.get("private_practice",false)) and str(ledger.get("lesson_window",""))=="spells" \
					and (native.get("travel",{}) as Dictionary).is_empty():
				expect(hud._guidance.text.contains("Open Magic") and not hud._guidance.text.contains("work sites"), "native Ostrid casting guidance names the working spell control")
				if not bool(ledger.get("sparring",false)) and str(ledger.get("phase",""))=="work" \
						and (native.get("travel",{}) as Dictionary).is_empty():captures.lesson=native
			if str(ledger.get("lesson_window",""))=="mixing":
				expect(hud._lesson_window.visible and hud._lesson_window.text=="Open Mixing", "the native mixing step offers its actual mixing window")
			if str(ledger.get("chapter",""))=="life_raid" and str(ledger.get("phase",""))=="work" and not (native.get("travel",{}) as Dictionary).is_empty():continue
			if str(ledger.get("chapter",""))=="life_raid" and str(ledger.get("phase",""))=="work":
				expect(not hud._guidance.text.begins_with("Next: Personal"), "native mine exploration does not nominate the personal cache as its destination")
				captures.raid=native
	var owner := Control.new();root.add_child(owner)
	var guide: Control=load("res://src/ui/lantern_guide.gd").new();root.add_child(guide)
	guide.configure(owner);guide.set_process(false);guide.attach_campaign(hud)
	root.size=Vector2i(720,480);root.content_scale_factor=1.5
	for key: String in captures:
		var state: Dictionary=captures[key]
		hud.apply_state(state,Vector2i.ZERO,str(state.map));guide.apply_campaign(state);guide._process(0);await settle()
		hud._body_scroll.ensure_control_visible(hud._guidance);await settle()
		expect(root.get_visible_rect().encloses(guide.card.get_global_rect()) and root.get_visible_rect().encloses(guide._buttons.get_global_rect()),
			key+" guidance and normal footer remain bounded in a small scaled window")
		var output := OS.get_environment("RL_NEXT_STEP_GUIDANCE_OUT")
		if not output.is_empty() and DisplayServer.get_name()!="headless":
			DirAccess.make_dir_recursive_absolute(output);await RenderingServer.frame_post_draw
			expect(root.get_texture().get_image().save_png(output.path_join(key+"-guidance-small.png"))==OK,"captured "+key+" next-step guidance")
	guidance.clear()
	for node: Node in [guide,owner,guidance,cache]:node.queue_free()
	await process_frame;await process_frame
	print("Quest next-step guidance: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
