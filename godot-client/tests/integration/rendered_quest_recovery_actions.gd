extends SceneTree
## Read-only native-state UI layout fixture; no gameplay or healing is simulated.
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()

func expect(ok: bool, text: String) -> void:
	checks+=1
	if not ok:failures+=1;push_error(text)

func run() -> void:
	Engine.max_fps=30;root.size=Vector2i(1280,720)
	var output:=OS.get_environment("RL_RECOVERY_RENDER_OUT")
	if output.is_empty():quit(1);return
	DirAccess.make_dir_recursive_absolute(output)
	root.get_node("Network").block_for_hud_preview()
	var backdrop:=ColorRect.new();root.add_child(backdrop)
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT);backdrop.color=Color("152126")
	var banner:=Label.new();root.add_child(banner);banner.position=Vector2(12,12)
	banner.text="AUTOMATED NATIVE-STATE UI FIXTURE\nLayout only · no live quest or healing"
	var hud:Control=load("res://src/ui/campaign_hud.gd").new();root.add_child(hud)
	var supply:Array=JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("RL_SUPPLY_RECOVERY_EVIDENCE")))
	var rescue:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("RL_RESCUE_FIELD_EVIDENCE")))
	var elen:Dictionary=(rescue.snapshots as Array).filter(func(row:Dictionary)->bool:return row.capture_label=="downed-boss-owner-assisted")[0]
	var captures:Array=[]
	for dimensions:Vector2i in [Vector2i(1280,720),Vector2i(900,460)]:
		root.size=dimensions
		for pair:Array in [["water-worker",supply[7]],["elen",elen]]:
			var state:Dictionary=pair[1]
			var original:=JSON.stringify(state)
			var decoded:=EloriaProtocol.decode_campaign(original.to_utf8_buffer())
			expect(decoded.type=="campaign","native recovery state decodes")
			if decoded.type!="campaign":quit(1);return
			hud.apply_state(decoded.state,Vector2i(430,300),str(state.map))
			for _frame in 8:await process_frame
			expect(hud._recovery_actions.get_child_count()==1,"one actual fallen ally produces one action")
			var button:Button=hud._recovery_actions.get_child(0)
			expect(button.is_visible_in_tree() and not button.disabled and "Heal Target" in button.text,"the recovery action is readable and available")
			expect(hud._body_scroll.get_global_rect().encloses(button.get_global_rect()),"recovery stays inside the first visible card page")
			expect(root.get_visible_rect().encloses(button.get_global_rect()),"the entire action stays inside the visible logical viewport at this window size")
			expect(JSON.stringify(state)==original,"rendering changes no quest state")
			await RenderingServer.frame_post_draw
			var filename:="%s-%dx%d.png"%[pair[0],dimensions.x,dimensions.y]
			expect(root.get_texture().get_image().save_png(output.path_join(filename))==OK,"recovery capture saves")
			captures.append(filename)
	var report:=FileAccess.open(output.path_join("report.json"),FileAccess.WRITE)
	report.store_string(JSON.stringify({"checks":checks,"failures":failures,"captures":captures,
		"scope":"Automated native-state quest-card layout only; no live playthrough or healing acceptance"},"  "))
	report.close();hud.queue_free()
	for _frame in 3:await process_frame
	print("Recovery action rendering: %d checks; %d failures"%[checks,failures]);quit(0 if failures==0 else 1)
