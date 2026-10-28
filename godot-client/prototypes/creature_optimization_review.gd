extends SceneTree
## Unified actual-client reviewer. No runtime asset writes or promotions.
class InputRelay extends Node:
	var callback: Callable
	func _input(event: InputEvent) -> void: callback.call(event)

var job: Dictionary
var catalog: Dictionary = {}
var catalog_sha := ""
var entries: Array = []
var index := 0
var loaded_entry: Dictionary = {}
var loaded_variant: Dictionary = {}
var variants: Array = []
var actors: Array[ReplicatedActor3D] = []
var players: Array[AnimationPlayer] = []
var stages: Array[Node3D] = []
var cameras: Array[Camera3D] = []
var panes: Array[SubViewportContainer] = []
var heading: Label
var status: Label
var metrics: RichTextLabel
var source_label: Label
var candidate_label: Label
var clip_picker: OptionButton
var variant_picker: OptionButton
var timeline: HSlider
var time_label: Label
var pause_button: Button
var approve_button: Button
var previous_button: Button
var next_button: Button
var comment_button: Button
var repeat_actions: CheckBox
var blend: CheckBox
var modal: ConfirmationDialog
var comment_edit: TextEdit
var comment_context: Dictionary = {}
var clips: Array = []
var clip := "Walk"
var clock := 0.0
var ready_to_play := false
var loading := false
var closing := false
var running := true
var speed := 1.0
var yaw := 2.2
var pitch := .18
var distance := 3.0
var default_distance := 3.0
var focus := Vector3(0,.6,0)
var default_focus := Vector3(0,.6,0)
var dragging := false
var poll_clock := 0.0
var notice := ""
var approvals: Dictionary = {}
var comment_counts: Dictionary = {}
var journal_sha := ""

func _initialize() -> void: run.call_deferred()

func label_for(text: String, size := 16) -> Label:
	var label := Label.new()
	label.text=text
	label.add_theme_font_size_override("font_size",size)
	return label

func button_for(text: String, parent: Node, callback: Callable) -> Button:
	var button := Button.new()
	button.text=text
	button.focus_mode=Control.FOCUS_NONE
	button.pressed.connect(callback)
	parent.add_child(button)
	return button

func fixture_path(fixture: Dictionary) -> String:
	var path := str(fixture.path)
	return path if path.is_absolute_path() else str(job.catalog).get_base_dir().path_join(path).simplify_path()

func current_key() -> String:
	return str(loaded_entry.get("id",""))+"|"+str(loaded_entry.get("source",{}).get("sha256",""))+"|"+str(loaded_variant.get("id",""))+"|"+str(loaded_variant.get("sha256",""))

func store_path() -> String:
	var path := str(catalog.get("review_store",".local/review-events.jsonl"))
	return path if path.is_absolute_path() else str(job.catalog).get_base_dir().path_join(path).simplify_path()

func read_journal() -> void:
	approvals.clear()
	comment_counts.clear()
	journal_sha=FileAccess.get_sha256(store_path()) if FileAccess.file_exists(store_path()) else ""
	if not FileAccess.file_exists(store_path()): return
	for line: String in FileAccess.get_file_as_string(store_path()).split("\n",false):
		var event = JSON.parse_string(line)
		if not event is Dictionary: continue
		var key := str(event.get("actor",""))+"|"+str(event.get("source_sha256",""))+"|"+str(event.get("variant",""))+"|"+str(event.get("candidate_sha256",""))
		if event.get("type")=="approve": approvals[key]=true
		if event.get("type")=="comment": comment_counts[key]=int(comment_counts.get(key,0))+1

func reload_catalog() -> bool:
	var changed_sha := FileAccess.get_sha256(job.catalog)
	if changed_sha==catalog_sha: return false
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(job.catalog))
	if not parsed is Dictionary or not parsed.get("entries") is Array or not parsed.get("complete") is bool:
		notice="Catalog update is incomplete; retaining displayed version."
		return false
	catalog=parsed
	catalog_sha=changed_sha
	entries=catalog.entries
	index=clampi(index,0,maxi(0,entries.size()-1))
	if not loaded_entry.is_empty():
		var retained := false
		for i in entries.size():
			if entries[i].id==loaded_entry.id: index=i; retained=true; break
		if not retained and not entries.is_empty():
			load_entry.call_deferred(0,"")
		# Refresh choices only; the displayed actor/version stays pinned.
		refresh_variant_picker()
		notice="Catalog refreshed. Displayed files stay pinned; choose a variant or Reload displayed to load a newer version."
	read_journal()
	refresh_status()
	return true

func loaded_is_current() -> bool:
	if loaded_entry.is_empty() or loaded_variant.is_empty(): return false
	for entry: Dictionary in entries:
		if entry.id!=loaded_entry.id or entry.source.sha256!=loaded_entry.source.sha256 or fixture_path(entry.source)!=fixture_path(loaded_entry.source): continue
		for variant: Dictionary in entry.get("variants",[]):
			if variant.id==loaded_variant.id and variant.sha256==loaded_variant.sha256 and fixture_path(variant)==fixture_path(loaded_variant): return true
	return false

func refresh_variant_picker() -> void:
	variants=[]
	if not entries.is_empty(): variants=entries[index].get("variants",[])
	variant_picker.clear()
	for variant: Dictionary in variants: variant_picker.add_item(str(variant.get("label",variant.id)))
	var selected := -1
	for i in variants.size():
		if variants[i].get("id")==loaded_variant.get("id"): selected=i
	if selected>=0: variant_picker.select(selected)
	variant_picker.disabled=loading or variants.is_empty()

func refresh_status() -> void:
	if heading==null: return
	var progress: Dictionary = catalog.get("progress",{})
	var title := str(loaded_entry.get("display_name",loaded_entry.get("id","No creature loaded")))
	heading.text="%d / %d   %s" % [index+1 if not entries.is_empty() else 0,entries.size(),title]
	var state := "PROCESSING — approval disabled" if not catalog.get("complete",false) else "Ready for review"
	if approvals.has(current_key()): state+=" · APPROVED exact candidate / all clips"
	if not loaded_variant.is_empty() and not loaded_is_current(): state+=" · displayed version is stale"
	status.text="%s  |  sampled %s / %s  ·  baked %s  |  %d comments\n%s" % [state,str(progress.get("sampled","?")),str(progress.get("total",entries.size())),str(progress.get("baked","?")),int(comment_counts.get(current_key(),0)),notice]
	approve_button.disabled=not ready_to_play or not catalog.get("complete",false) or not loaded_is_current() or approvals.has(current_key())
	approve_button.text="Approved · all clips" if approvals.has(current_key()) else "Approve exact candidate · Space"
	previous_button.disabled=loading or entries.size()<2
	next_button.disabled=previous_button.disabled
	comment_button.disabled=not ready_to_play or loaded_variant.is_empty()

func run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty(): push_error("Launch through review_creature_runtime_optimization.py"); quit(1); return
	job=JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	assert(FileAccess.get_sha256(get_script().resource_path)==str(job.prototype_sha256),"Stale prepared reviewer")
	root.title="Rabbit Lands | Creature optimization review"
	root.size=Vector2i(1500,1000)
	set_auto_accept_quit(false)
	root.close_requested.connect(close_preview)
	Engine.max_fps=120
	var relay := InputRelay.new()
	relay.callback=handle_input
	root.add_child(relay)
	var background := ColorRect.new()
	background.color=Color("141d28")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(background)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left","right","top","bottom"]: margin.add_theme_constant_override("margin_"+side,16)
	root.add_child(margin)
	var layout := VBoxContainer.new()
	margin.add_child(layout)
	heading=label_for("Creature optimization review",24)
	layout.add_child(heading)
	status=label_for("Loading…",15)
	status.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
	layout.add_child(status)
	var navigation := HBoxContainer.new()
	layout.add_child(navigation)
	previous_button=button_for("← Creature",navigation,func(): navigate(-1))
	next_button=button_for("Creature →",navigation,func(): navigate(1))
	navigation.add_child(label_for(" Candidate "))
	variant_picker=OptionButton.new()
	variant_picker.focus_mode=Control.FOCUS_NONE
	variant_picker.item_selected.connect(func(i: int): load_entry(index,str(variants[i].id)))
	navigation.add_child(variant_picker)
	button_for("Reload displayed",navigation,func(): load_entry(index,str(loaded_variant.get("id",""))))
	approve_button=button_for("Approve exact candidate · Space",navigation,approve)
	comment_button=button_for("Comment · T",navigation,open_comment)
	var controls := HBoxContainer.new()
	layout.add_child(controls)
	controls.add_child(label_for("Animation ↑ / ↓ "))
	clip_picker=OptionButton.new()
	clip_picker.focus_mode=Control.FOCUS_NONE
	clip_picker.item_selected.connect(func(i: int): select_clip(str(clips[i])))
	controls.add_child(clip_picker)
	pause_button=button_for("Pause · P",controls,toggle_pause)
	button_for("Restart",controls,func(): seek_both(0.0))
	var speeds := OptionButton.new()
	for value in [.1,.25,.5,1.,2.]: speeds.add_item(str(value)+"x")
	speeds.select(3)
	speeds.focus_mode=Control.FOCUS_NONE
	speeds.item_selected.connect(func(i: int): speed=[.1,.25,.5,1.,2.][i])
	controls.add_child(speeds)
	blend=CheckBox.new()
	blend.text="Blend switches (0.15 s)"
	blend.button_pressed=true
	blend.focus_mode=Control.FOCUS_NONE
	controls.add_child(blend)
	repeat_actions=CheckBox.new()
	repeat_actions.text="Repeat one-shots"
	repeat_actions.focus_mode=Control.FOCUS_NONE
	controls.add_child(repeat_actions)
	var panels := HBoxContainer.new()
	panels.size_flags_vertical=Control.SIZE_EXPAND_FILL
	layout.add_child(panels)
	for side in 2:
		var column := VBoxContainer.new()
		column.size_flags_horizontal=Control.SIZE_EXPAND_FILL
		panels.add_child(column)
		var label := label_for("Original source" if side==0 else "Candidate",14)
		label.autowrap_mode=TextServer.AUTOWRAP_ARBITRARY
		column.add_child(label)
		if side==0: source_label=label
		else: candidate_label=label
		var container := SubViewportContainer.new()
		container.stretch=true
		container.size_flags_vertical=Control.SIZE_EXPAND_FILL
		container.custom_minimum_size=Vector2(300,300)
		container.gui_input.connect(orbit_input)
		column.add_child(container)
		panes.append(container)
		var viewport := SubViewport.new()
		viewport.own_world_3d=true
		container.add_child(viewport)
		stages.append(make_stage(viewport))
	metrics=RichTextLabel.new()
	metrics.custom_minimum_size.y=92
	metrics.selection_enabled=true
	layout.add_child(metrics)
	var scrub := HBoxContainer.new()
	layout.add_child(scrub)
	timeline=HSlider.new()
	timeline.step=.0001
	timeline.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	timeline.value_changed.connect(seek_both)
	scrub.add_child(timeline)
	time_label=label_for("",16)
	time_label.custom_minimum_size.x=190
	scrub.add_child(time_label)
	var views := HBoxContainer.new()
	layout.add_child(views)
	button_for("Front",views,func(): yaw=PI; pitch=.18; update_cameras())
	button_for("Side",views,func(): yaw=PI/2; pitch=.12; update_cameras())
	button_for("Rear",views,func(): yaw=0.; pitch=.18; update_cameras())
	button_for("Above",views,func(): pitch=1.; update_cameras())
	button_for("Reset camera",views,func(): distance=default_distance; focus=default_focus; yaw=2.2; pitch=.18; update_cameras())
	views.add_child(label_for("Drag: orbit · Wheel: zoom · Space approves ALL clips · P pauses",14))
	build_modal()
	reload_catalog()
	if not entries.is_empty(): await load_entry(0,"")
	print("CREATURE_OPTIMIZATION_REVIEW_READY")
	if job.get("capture",false):
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(str(job.output).path_join("review.png"))
	if job.get("smoke",false): await smoke_test()

func make_stage(viewport: SubViewport) -> Node3D:
	var stage := Node3D.new()
	viewport.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment=Environment.new()
	world.environment.background_mode=Environment.BG_COLOR
	world.environment.background_color=Color("263443")
	world.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color=Color("c2d0e1")
	world.environment.ambient_light_energy=.65
	stage.add_child(world)
	var light := DirectionalLight3D.new()
	light.rotation_degrees=Vector3(-50,-35,0)
	light.light_energy=1.4
	stage.add_child(light)
	var floor_mesh := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size=Vector2(20,20)
	var material := StandardMaterial3D.new()
	material.albedo_color=Color("45535c")
	plane.material=material
	floor_mesh.mesh=plane
	stage.add_child(floor_mesh)
	var camera := Camera3D.new()
	camera.cull_mask=1 # Body/floor only; gameplay overhead furniture uses layer 20.
	camera.fov=38
	camera.near=.02
	camera.current=true
	stage.add_child(camera)
	cameras.append(camera)
	return stage

func unload_pair() -> void:
	ready_to_play=false
	for actor in actors: actor.queue_free()
	actors.clear()
	players.clear()
	await process_frame
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await process_frame

func load_entry(next_index: int, wanted_variant: String) -> void:
	if loading or modal.visible or entries.is_empty(): return
	loading=true
	index=posmod(next_index,entries.size())
	refresh_status()
	await unload_pair()
	if closing: return
	loaded_entry=entries[index].duplicate(true)
	variants=loaded_entry.get("variants",[])
	loaded_variant={}
	var desired := wanted_variant if not wanted_variant.is_empty() else "zero-bake"
	for variant: Dictionary in variants:
		if variant.id==desired: loaded_variant=variant.duplicate(true)
	if loaded_variant.is_empty() and not variants.is_empty(): loaded_variant=variants[0].duplicate(true)
	refresh_variant_picker()
	clips=loaded_entry.clips.duplicate()
	clip_picker.clear()
	for name: String in clips: clip_picker.add_item(name.replace("_"," "))
	if not clips.has(clip): clip=str(clips[0])
	source_label.text="ORIGINAL · %s bytes\nSHA256 %s" % [str(loaded_entry.source.bytes),str(loaded_entry.source.sha256)]
	candidate_label.text="Processing — candidate not ready"
	metrics.text="Source review status retained: installed=%s · selected local draft=%s" % [str(loaded_entry.get("was_installed",false)),str(loaded_entry.get("selected_local_draft",false))]
	if loaded_variant.is_empty():
		loading=false
		notice="This creature is still processing. Choose another creature or wait for the catalog update."
		refresh_status()
		return
	candidate_label.text="%s · %s bytes\nSHA256 %s" % [str(loaded_variant.get("label",loaded_variant.id)),str(loaded_variant.bytes),str(loaded_variant.sha256)]
	metrics.text+="\n"+JSON.stringify(loaded_variant.get("metrics",{}),"  ")
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var config: Dictionary = registry[str(loaded_entry.get("actor",loaded_entry.id))]
	var animation_map: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	for i in clips.size(): animation_map.actions["__review_native_"+str(i)]=clips[i]
	for side in 2:
		var fixture: Dictionary = loaded_entry.source if side==0 else loaded_variant
		var path := fixture_path(fixture)
		if FileAccess.get_sha256(path)!=str(fixture.sha256):
			loading=false; notice="Input changed; refusing to load "+path; refresh_status(); return
		var packed := GlbSceneCache._build_raw(path)
		if packed==null: loading=false; notice="Raw client could not load "+path; refresh_status(); return
		GlbSceneCache.install_prepared({path:packed})
		var actor := ReplicatedActor3D.new()
		stages[side].add_child(actor)
		var local_config := config.duplicate(true)
		local_config.scene=path
		local_config.animationLibrary=path
		var errors := actor.configure({"actor_id":side+1,"kind":ReplicatedActor3D.CREATURE_ACTOR_KIND,"name":"","x":0,"y":0,"rotation":0,"health":100,"max_health":100,"appearance":{},"equipment_visuals":{}},CoordinateAdapter.new({"metresPerTile":1.0}),local_config,animation_map)
		actors.append(actor)
		if not errors.is_empty(): loading=false; notice=str(errors); refresh_status(); return
		actor.position=Vector3.ZERO
		actor.rotation=Vector3.ZERO
		actor.set_process(false)
		actor.set_physics_process(false)
		actor.set_nameplate_visible(false)
		actor.set_health_visible(true)
		actor.set_health_visible(false)
		for furniture in ["HealthBarBackground","HealthBarFill","HealthNumbers","OverheadBackground","BossRank","StatusIcons"]:
			var overhead := actor.get_node_or_null(furniture) as Node3D
			if overhead: overhead.visible=false
		var player := actor.animation_player
		if player.animation_finished.is_connected(actor._on_animation_finished): player.animation_finished.disconnect(actor._on_animation_finished)
		for node in actor.find_children("*","AnimationPlayer",true,false):
			(node as AnimationPlayer).callback_mode_process=AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		for name: String in clips:
			if not player.has_animation(name): loading=false; notice="Missing source clip: "+name; refresh_status(); return
		players.append(player)
		if side==0:
			var native := actor.get_node("NativeModel") as Node3D
			var bounds: AABB = native.global_transform*actor._native_body_bounds
			default_focus=bounds.get_center()
			default_distance=maxf(3.,bounds.size.length()*1.3)
	focus=default_focus
	distance=default_distance
	loading=false
	ready_to_play=true
	notice="Approvals apply to this exact candidate across ALL clips. No model is installed by this viewer."
	select_clip(clip)
	read_journal()
	refresh_variant_picker()
	refresh_status()
	update_cameras()

func navigate(direction: int) -> void:
	if loading or modal.visible or entries.is_empty(): return
	load_entry(index+direction,str(loaded_variant.get("id","")))

func select_clip(name: String) -> void:
	if not ready_to_play: return
	clip=name
	clock=0.
	clip_picker.select(clips.find(name))
	for player in players:
		var restarting := player.assigned_animation==clip
		if restarting: player.stop()
		player.play(clip,.15 if blend.button_pressed and running and not restarting else 0.)
		player.advance(0.)
	timeline.max_value=players[0].get_animation(clip).length
	refresh_time()

func seek_both(value: float) -> void:
	if not ready_to_play: return
	clock=value
	for player in players:
		player.play("RESET",0.)
		player.seek(0.,true)
		player.play(clip,0.)
		player.seek(clock,true)
	for actor in actors: actor.get_skeleton().force_update_all_bone_transforms()
	refresh_time()

func refresh_time() -> void:
	timeline.set_value_no_signal(clock)
	time_label.text="%.4f / %.4f s" % [clock,timeline.max_value]

func toggle_pause() -> void:
	running=not running
	pause_button.text="Pause · P" if running else "Play · P"

func update_cameras() -> void:
	var offset := Vector3(sin(yaw)*cos(pitch),sin(pitch),cos(yaw)*cos(pitch))*distance
	for camera in cameras: camera.look_at_from_position(focus+offset,focus)

func orbit_input(event: InputEvent) -> void:
	if modal.visible: return
	if event is InputEventMouseButton:
		if event.button_index in [MOUSE_BUTTON_LEFT,MOUSE_BUTTON_RIGHT]: dragging=event.pressed
		if event.pressed and event.button_index==MOUSE_BUTTON_WHEEL_UP: distance=maxf(.1,distance*.9)
		if event.pressed and event.button_index==MOUSE_BUTTON_WHEEL_DOWN: distance=minf(200.,distance/.9)
	if event is InputEventMouseMotion and dragging:
		yaw-=event.relative.x*.008
		pitch=clampf(pitch+event.relative.y*.006,-.2,1.45)
	update_cameras()

func event_context(kind: String) -> Dictionary:
	return {"type":kind,"actor":loaded_entry.id,"source_path":fixture_path(loaded_entry.source),"source_sha256":loaded_entry.source.sha256,"candidate_path":fixture_path(loaded_variant),"candidate_sha256":loaded_variant.sha256,"variant":loaded_variant.id,"clip":clip,"time_seconds":clock}

func persist(request: Dictionary) -> bool:
	var folder := str(job.output).path_join("requests")
	DirAccess.make_dir_recursive_absolute(folder)
	var path := folder.path_join(str(Time.get_ticks_usec())+"-"+str(randi())+".json")
	FileAccess.open(path,FileAccess.WRITE).store_string(JSON.stringify(request))
	var response := []
	var result := OS.execute(job.python,PackedStringArray([job.helper,"--catalog",job.catalog,"--append-event",path]),response,true,false)
	if result!=0:
		notice="Review was NOT saved. Check the journal or retry."
		for block: String in response:
			for line: String in block.split("\n",false):
				var parsed = JSON.parse_string(line)
				if parsed is Dictionary and parsed.has("error"): notice="Review was NOT saved: "+str(parsed.error)
		refresh_status()
		return false
	read_journal()
	notice="Saved exact-version approval (all clips)." if request.type=="approve" else "Comment saved for this exact version."
	refresh_status()
	return true

func approve() -> void:
	if not ready_to_play or modal.visible: return
	reload_catalog()
	if not catalog.get("complete",false): notice="Processing is incomplete; approval is disabled."; refresh_status(); return
	if not loaded_is_current(): notice="Displayed version is stale. Explicitly reload the candidate before approving."; refresh_status(); return
	if approvals.has(current_key()): notice="This exact version is already approved across all clips."; refresh_status(); return
	if FileAccess.get_sha256(fixture_path(loaded_variant))!=str(loaded_variant.sha256) or FileAccess.get_sha256(fixture_path(loaded_entry.source))!=str(loaded_entry.source.sha256):
		notice="A displayed file changed. No approval saved."; refresh_status(); return
	persist(event_context("approve"))

func build_modal() -> void:
	modal=ConfirmationDialog.new()
	modal.title="Comment on the displayed exact candidate"
	modal.exclusive=true
	modal.min_size=Vector2i(760,420)
	modal.get_ok_button().text="Save comment · Ctrl+Enter"
	modal.confirmed.connect(save_comment)
	modal.canceled.connect(func(): modal.hide())
	root.add_child(modal)
	var box := VBoxContainer.new()
	modal.add_child(box)
	box.add_child(label_for("Multiline comment. Arrows / Space / T edit text here. Ctrl+Enter saves; Esc cancels.",14))
	comment_edit=TextEdit.new()
	comment_edit.custom_minimum_size=Vector2(720,290)
	comment_edit.size_flags_vertical=Control.SIZE_EXPAND_FILL
	comment_edit.gui_input.connect(comment_input)
	box.add_child(comment_edit)
	modal.dialog_hide_on_ok=false

func open_comment() -> void:
	if not ready_to_play or loaded_variant.is_empty(): return
	comment_context=event_context("comment")
	running=false
	pause_button.text="Play · P"
	comment_edit.text=""
	modal.popup_centered()
	comment_edit.grab_focus()

func save_comment() -> void:
	if not modal.visible: return
	if comment_edit.text.strip_edges().is_empty(): return
	comment_context.text=comment_edit.text
	if persist(comment_context): modal.hide()

func comment_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo: return
	if event.keycode==KEY_ENTER and (event.ctrl_pressed or event.meta_pressed): save_comment(); modal.set_input_as_handled()
	elif event.keycode==KEY_ESCAPE: modal.hide(); modal.set_input_as_handled()

func handle_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and not event.pressed: dragging=false
	if modal!=null and modal.visible:
		comment_input(event)
		return # TextEdit owns ALL normal keys; never navigate or approve here.
	if not event is InputEventKey or not event.pressed or event.echo: return
	if not ready_to_play and not event.keycode in [KEY_LEFT,KEY_RIGHT]: return
	if clip_picker.get_popup().visible or variant_picker.get_popup().visible: return
	match event.keycode:
		KEY_LEFT: navigate(-1)
		KEY_RIGHT: navigate(1)
		KEY_UP: select_clip(str(clips[posmod(clips.find(clip)-1,clips.size())]))
		KEY_DOWN: select_clip(str(clips[posmod(clips.find(clip)+1,clips.size())]))
		KEY_SPACE: approve()
		KEY_T: open_comment()
		KEY_P: toggle_pause()
		_: return
	root.set_input_as_handled()

func _process(delta: float) -> bool:
	if closing: return false
	poll_clock+=delta
	if poll_clock>1. and not loading and (modal==null or not modal.visible):
		poll_clock=0.
		reload_catalog()
		var current_journal_sha := FileAccess.get_sha256(store_path()) if FileAccess.file_exists(store_path()) else ""
		if current_journal_sha!=journal_sha: read_journal(); refresh_status()
	if ready_to_play and running and not modal.visible:
		var length := players[0].get_animation(clip).length
		if clock>=length and repeat_actions.button_pressed: select_clip(clip)
		var step := delta*speed
		for player in players: player.advance(step)
		for actor in actors: actor.get_skeleton().force_update_all_bone_transforms()
		clock=fmod(clock+step,length) if length>0 and players[0].get_animation(clip).loop_mode!=Animation.LOOP_NONE else minf(clock+step,length)
		refresh_time()
	return false

func close_preview() -> void:
	if closing: return
	closing=true
	await unload_pair()
	quit()

func key(code: int, echo := false, ctrl := false) -> InputEventKey:
	var event := InputEventKey.new()
	event.keycode=code
	event.pressed=true
	event.echo=echo
	event.ctrl_pressed=ctrl
	return event

func smoke_test() -> void:
	assert(catalog.get("test_only",false),"Smoke must use an isolated TEST catalog")
	assert(ready_to_play and entries.size()==2)
	running=false
	for name: String in clips:
		select_clip(name)
		seek_both(timeline.max_value*.47)
		for player in players: assert(player.current_animation==name)
	select_clip(str(clips[0]))
	var first_clip := clip
	handle_input(key(KEY_DOWN))
	assert(clip==str(clips[1]))
	handle_input(key(KEY_UP))
	assert(clip==first_clip)
	var before_index := index
	handle_input(key(KEY_RIGHT))
	while loading: await process_frame
	assert(index!=before_index and clip==first_clip,"Creature navigation/preserved clip failed")
	handle_input(key(KEY_LEFT))
	while loading: await process_frame
	assert(index==before_index)
	var before_running := running
	handle_input(key(KEY_P))
	assert(running!=before_running)
	handle_input(key(KEY_P))
	handle_input(key(KEY_T))
	assert(modal.visible)
	comment_edit.text="First line: T and spaces\nSecond line: arrows stay inside the editor"
	for code in [KEY_LEFT,KEY_RIGHT,KEY_UP,KEY_DOWN,KEY_SPACE,KEY_T]: handle_input(key(code))
	assert(index==before_index and clip==first_clip and not approvals.has(current_key()))
	handle_input(key(KEY_ENTER,false,true))
	assert(not modal.visible and int(comment_counts.get(current_key(),0))==1)
	var saved_comment_bytes := FileAccess.get_file_as_bytes(store_path())
	handle_input(key(KEY_T))
	comment_edit.text="Canceled comment"
	handle_input(key(KEY_ESCAPE))
	assert(not modal.visible and FileAccess.get_file_as_bytes(store_path())==saved_comment_bytes)
	handle_input(key(KEY_T))
	comment_edit.text="Save-button comment"
	modal.confirmed.emit()
	assert(not modal.visible and int(comment_counts.get(current_key(),0))==2)
	var original_variant := str(loaded_variant.id)
	var other_variant := 1 if variant_picker.selected==0 else 0
	variant_picker.item_selected.emit(other_variant)
	while loading: await process_frame
	assert(str(loaded_variant.id)!=original_variant and clip==first_clip)
	for i in variants.size():
		if str(variants[i].id)==original_variant:
			variant_picker.item_selected.emit(i)
			break
	while loading: await process_frame
	assert(str(loaded_variant.id)==original_variant)
	var before_bytes := FileAccess.get_file_as_bytes(store_path())
	handle_input(key(KEY_SPACE,true))
	assert(FileAccess.get_file_as_bytes(store_path())==before_bytes,"Key echo wrote an approval")
	var temporary := catalog.duplicate(true)
	temporary.complete=false
	FileAccess.open(job.catalog,FileAccess.WRITE).store_string(JSON.stringify(temporary))
	reload_catalog()
	handle_input(key(KEY_SPACE))
	assert(not approvals.has(current_key()) and approve_button.disabled)
	temporary.complete=true
	FileAccess.open(job.catalog,FileAccess.WRITE).store_string(JSON.stringify(temporary))
	reload_catalog()
	handle_input(key(KEY_SPACE))
	assert(approvals.has(current_key()))
	var pinned_sha := str(loaded_variant.sha256)
	var pinned_actor := actors[0].get_instance_id()
	var current := catalog.duplicate(true)
	for variant: Dictionary in current.entries[index].variants:
		if str(variant.id)==str(loaded_variant.id): variant.sha256="0".repeat(64)
	FileAccess.open(job.catalog,FileAccess.WRITE).store_string(JSON.stringify(current))
	reload_catalog()
	assert(str(loaded_variant.sha256)==pinned_sha and not loaded_is_current() and approve_button.disabled,"Catalog silently replaced loaded version")
	assert(actors[0].get_instance_id()==pinned_actor)
	var completed := loaded_variant.duplicate(true)
	completed.id="newly-completed-smoke-variant"
	current.entries[index].variants.append(completed)
	FileAccess.open(job.catalog,FileAccess.WRITE).store_string(JSON.stringify(current))
	reload_catalog()
	assert(variant_picker.item_count==current.entries[index].variants.size() and actors[0].get_instance_id()==pinned_actor)
	FileAccess.open(job.catalog,FileAccess.WRITE).store_string(JSON.stringify(temporary))
	reload_catalog()
	var old_yaw := yaw
	var mouse := InputEventMouseButton.new()
	mouse.button_index=MOUSE_BUTTON_LEFT
	mouse.pressed=true
	orbit_input(mouse)
	var motion := InputEventMouseMotion.new()
	motion.relative=Vector2(30,10)
	orbit_input(motion)
	assert(yaw!=old_yaw)
	mouse.pressed=false
	orbit_input(mouse)
	var old_distance := distance
	mouse.button_index=MOUSE_BUTTON_WHEEL_UP
	mouse.pressed=true
	orbit_input(mouse)
	assert(distance<old_distance)
	for stage in stages:
		var count := 0
		for child in stage.get_children():
			if child is ReplicatedActor3D: count+=1
		assert(count==1,"Old actors accumulated across switches")
	var report := {"headless":DisplayServer.get_name()=="headless","key_handler_navigation":true,"all_native_clips_played":true,"preserved_animation":true,"pause_p":true,"modal_guards_arrows_space_t":true,"multiline_comment_ctrl_enter":true,"comment_cancel_and_save_button":true,"variant_dropdown_switch":true,"echo_approval_ignored":true,"incomplete_catalog_approval_blocked":true,"append_only_exact_version_approval":true,"catalog_reload_keeps_displayed_version":true,"new_completed_variants_discovered":true,"orbit_zoom_handlers":true,"journal":store_path(),"actor_count_after_switches":actors.size(),"prototype_sha256":job.prototype_sha256}
	FileAccess.open(str(job.output).path_join("review-smoke.json"),FileAccess.WRITE).store_string(JSON.stringify(report,"  "))
	print("CREATURE_OPTIMIZATION_REVIEW_SMOKE_PASS")
	await close_preview()
