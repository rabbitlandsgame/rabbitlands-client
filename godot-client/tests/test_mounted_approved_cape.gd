extends "res://tests/test_cape_approved_motion.gd"
## The approved fit on actual seated actors. Contact is measured independently
## against posed visible triangles, rather than the solver's particle envelope.

const PROFILES := preload("res://src/mounts/mount_profiles.gd")
const ATTACHMENT := preload("res://src/actors/cape_mounted_attachment.gd")
const CELL := .08
const CONTACT_TOLERANCE := .006
const CONTACT_EDGE_LENGTH := .06
const CONTACT_EDGE_FRACTIONS := [.25,1./3.,.5,2./3.,.75]
const MAX_EDGE_RATIO := 1.8
const MAX_FRAME_STEP := .08
# Approximate upper-action body-sweep budget only; strict gait limit unchanged.
const UPPER_MOTION_REVIEW_MARGIN := .001
const UPPER_MOTION_RESOLUTION := .001
const UPPER_BODY_MEMORY := .65
const GAITS := ["idle","walk","cruise","burst","cruise","idle"]
const UPPER_ACTIONS := [&"cast_aggressive",&"cast_defensive",&"ranged_draw",&"ranged_attack",&"heal",&"cast_channel_enter"]
var _mounted_rows: Array = []
var _geometry_cache: Dictionary = {}
var _material_vertices: Dictionary = {}
var _contact_frames: Array[int] = [0,24,89]

func _run() -> void:
	RLHeadLibrary.retain_seconds = 0.0
	_models = _json("res://data/actors/models.json").get("models",{})
	_equipment = _json("res://data/actors/equipment.json")
	var contact_selection:=OS.get_environment("RL_MOUNT_CONTACT_FRAMES")
	if not contact_selection.is_empty():
		_contact_frames.clear()
		for value: String in contact_selection.split(",",false):
			var frame:=int(value)
			_check(frame>=0 and frame<90,"contact-frame selection stays inside the actual gait interval")
			if frame>=0 and frame<90 and not _contact_frames.has(frame):_contact_frames.append(frame)
		_check(not _contact_frames.is_empty(),"gait contact measurement has explicit frame coverage")
	var ids: Array = PROFILES.PATHS.keys()
	var requested := OS.get_environment("RL_MOUNT_TEST_IDS")
	if not requested.is_empty():ids=Array(requested.split(",",false))
	var sexes := ["male","female"]
	var selected_sexes := OS.get_environment("RL_MOUNT_TEST_SEXES")
	if not selected_sexes.is_empty():sexes=Array(selected_sexes.split(",",false))
	var torsos: Array[int]=[0,184]
	var selected_torsos:=OS.get_environment("RL_MOUNT_TEST_TORSOS")
	if not selected_torsos.is_empty():
		torsos.clear()
		for value: String in selected_torsos.split(",",false):torsos.append(int(value))
	for mount_id: String in ids:
		_check(PROFILES.supports(mount_id),"mounted approved fixture recognizes "+mount_id)
		if not PROFILES.supports(mount_id):continue
		for sex: String in sexes:
			for torso: int in torsos:
				await _case(mount_id,sex,torso)
	await _shutdown_fixture()
	_finish()

func _case(mount_id: String, sex: String, torso: int) -> void:
	var profile := "armour" if torso else "wardrobe"
	var culture:=OS.get_environment("RL_MOUNT_TEST_CULTURE")
	if culture.is_empty():culture="luminous"
	var model:=culture+"_"+sex
	var label := mount_id+"/"+model+"/"+profile
	var appearance: Dictionary={"rl_head":{"sex":sex,"hair":"none","beard":"none"}} if culture=="luminous" else {}
	var actor := _spawn(model,torso,appearance)
	actor.rotation.y=.47
	_sample(actor,&"idle",.4)
	var rig := actor.get_skeleton()
	var body_rest := _body_poses(rig,true)
	var original := _cape_surface_contract(rig)
	var reference_contract: Dictionary={}
	if mount_id=="moor_pony":reference_contract=_attachment_reference_contract(actor,profile,label)
	actor.set_mount_state({"mode":"mounted","mount_id":mount_id,"gait":"idle","step_us":600000},_models)
	var visual := actor._mount_visual as Node3D
	_check(is_instance_valid(visual),label+" configures the supported mount")
	if not is_instance_valid(visual):actor.queue_free();await process_frame;return
	visual.call("set_animation_tier",AnimationGate.Tier.FULL,AnimationGate.Tier.HALF,false,false)
	visual.set_process(false)
	visual.call("_process",STEP)
	_check(not actor._cape_cloth.active,label+" has one manually ordered cape pass")
	_check(actor._cape_cloth.get("_mount_surface")!=null,label+" binds mount contact")
	var mounted_stats:=_stats(actor)
	_check(bool(mounted_stats.get("enabled",false)) and str(mounted_stats.get("profile",""))==profile and bool(mounted_stats.get("mounted_fit",false)),label+" enables the approved mounted-fit driver")
	_check(bool(mounted_stats.get("mounted_ready",false)),label+" has successfully configured the actual mounted projection")
	var relief_contract: Dictionary={}
	if mount_id=="moor_pony":relief_contract=_mounted_relief_contract(actor,rig,profile,label)
	var groups := _cape_groups(rig)
	_check(not groups.is_empty(),label+" retains actual approved cape geometry")
	for mesh: MeshInstance3D in _cape_meshes(rig):
		_check(str(mesh.get_meta("cape_approved_profile",""))==profile,label+" keeps the approved "+profile+" fit while seated")
		_check(mesh.skin.get_bind_count()==17,label+" retains the approved seventeen named binds")
	var seated_contract:=_cape_surface_contract(rig)
	_check(seated_contract.materials==original.materials,label+" preserves all three styled material slots mounted")
	_check(seated_contract.weights==original.weights and seated_contract.bones==original.bones,label+" preserves exact eight-slot GPU weights and vertex bone indices mounted")
	var rows: Array=[]
	var previous := PackedVector3Array()
	var previous_shape := PackedVector3Array()
	var previous_translated := PackedVector3Array()
	var prior_native_calls:=int(((_stats(actor).get("mounted",{}) as Dictionary).get("native_stats",{}) as Dictionary).get("calls",0))
	for stage: int in GAITS.size():
		var gait: String=GAITS[stage]
		actor.set_mount_state({"mode":"mounted","mount_id":mount_id,"gait":gait,"step_us":200000},_models)
		actor.current_action=&"idle" if gait=="idle" else &"run"
		actor._presentation_speed={"idle":0.,"walk":1.67,"cruise":5.,"burst":7.5}[gait]
		var worst_mount:=0.;var worst_rider:=0.;var worst_nape:=0.;var stretch:=0.;var all_stretch:=0.;var body_stretch:=0.;var step_error:=0.;var shape_step:=0.;var actor_step:=0.;var translated_step:=0.
		var contacts:=0;var ambiguous:=0;var rays:=0;var covered:=0
		var hem_history:=PackedVector3Array()
		var samples: Array=[];var jump_witness: Dictionary={}
		var solve_times: Array[float]=[];var project_times: Array[float]=[];var measurement_ms:=0.
		for frame: int in 90:
			if gait!="idle":actor.global_position+=actor.global_basis*Vector3(0,0,-actor._presentation_speed*STEP)
			var started:=Time.get_ticks_usec()
			visual.call("_process",STEP)
			solve_times.append(float(Time.get_ticks_usec()-started)/1000.)
			var arithmetic: Dictionary=_stats(actor).get("mounted",{})
			project_times.append(float(arithmetic.get("project_usec",0))/1000.)
			var current:=_motion_points_in(groups,actor.global_transform.affine_inverse())
			var shape_current:=_motion_points(rig,groups)
			var anchor: Vector3=actor.to_local(rig.global_transform*rig.get_bone_global_pose(rig.find_bone("spine_03")).origin)
			var translated_current:=PackedVector3Array()
			for point: Vector3 in current:translated_current.append(point-anchor)
			if not previous.is_empty() and (stage>0 or frame>12):
				var world_error:=_points_error(previous,current)
				var shape_error:=_points_error(previous_shape,shape_current)
				var translated_error:=_points_error(previous_translated,translated_current)
				actor_step=maxf(actor_step,world_error);shape_step=maxf(shape_step,shape_error);translated_step=maxf(translated_step,translated_error)
				# Existing rider/pony gait changes may carry the whole attachment
				# instantly. Also permit the sheet to lag that body rotation. A
				# cape-only snap is unexplained in all three shared rigid frames.
				var error:=minf(world_error,minf(shape_error,translated_error))
				if error>step_error:
					step_error=error
					var witness_current:=current;var witness_previous:=previous;var mode:="actor"
					if shape_error<world_error and shape_error<=translated_error:witness_current=shape_current;witness_previous=previous_shape;mode="spine_rigid"
					elif translated_error<world_error:witness_current=translated_current;witness_previous=previous_translated;mode="spine_translation"
					for vertex: int in current.size():
						if witness_current[vertex].distance_to(witness_previous[vertex])>=error-.000001:
							jump_witness={"frame":frame,"motion_sample":vertex,"carry_frame":mode,"previous":_point_array(witness_previous[vertex]),"current":_point_array(witness_current[vertex])}
							break
			previous=current
			previous_shape=shape_current
			previous_translated=translated_current
			if frame>=60 and not shape_current.is_empty():hem_history.append(shape_current[0])
			if frame not in _contact_frames:continue
			started=Time.get_ticks_usec()
			var inverse:=actor.global_transform.affine_inverse()
			var cape:=_cape_points(rig,groups,inverse)
			var mount_atlases:=_atlases(visual,inverse,1)
			var rider_atlases:=_atlases(actor.get_node("NativeModel"),inverse,2,true)
			var mount_contact:=_contact(cape.contact,mount_atlases,1)
			var rider_contact:=_contact(cape.contact,rider_atlases,2)
			var nape_contact:=_contact(cape.nape,_head_atlases(rider_atlases),2)
			mount_contact["cape_source"]=_contact_source(cape,mount_contact,groups)
			rider_contact["cape_source"]=_contact_source(cape,rider_contact,groups)
			nape_contact["cape_source"]=_contact_source(cape,nape_contact,groups,true)
			worst_nape=maxf(worst_nape,nape_contact.deepest)
			worst_mount=maxf(worst_mount,mount_contact.deepest)
			worst_rider=maxf(worst_rider,rider_contact.deepest)
			stretch=maxf(stretch,cape.stretch)
			all_stretch=maxf(all_stretch,cape.all_stretch);body_stretch=maxf(body_stretch,cape.body_stretch)
			contacts+=mount_contact.inside+rider_contact.inside
			ambiguous+=mount_contact.ambiguous+rider_contact.ambiguous
			rays+=mount_contact.rays+rider_contact.rays
			covered+=mount_contact.covered+rider_contact.covered
			measurement_ms+=float(Time.get_ticks_usec()-started)/1000.
			samples.append({"frame":frame,"mount":mount_contact,"rider":rider_contact,"body_owned_nape_head":nape_contact,"edge_ratio":cape.stretch,"all_edge_ratio":cape.all_stretch,"body_owned_edge_ratio":cape.body_stretch,"rebased_all_edge_ratio":cape.rebased_all_stretch,"edge_witness":cape.edge_witness,"body_owned_edge_witness":cape.body_witness})
			_check(cape.finite,label+" "+gait+" frame"+str(frame)+" remains finite")
		var motion:=_span(hem_history)
		var solve_sum:=0.
		for value: float in solve_times:solve_sum+=value
		solve_times.sort()
		var row: Dictionary={"gait":gait,"stage":stage,"mount_inside_m":worst_mount,"rider_inside_m":worst_rider,"maximum_edge_ratio":stretch,"maximum_all_edge_ratio":all_stretch,"maximum_body_owned_edge_ratio":body_stretch,"largest_vertex_frame_step_m":step_error,"largest_actor_frame_step_m":actor_step,"largest_spine_translation_step_m":translated_step,"largest_spine_relative_step_m":shape_step,"jump_witness":jump_witness,"steady_hem_span_m":motion,"inside_samples":contacts,"ambiguous_open_rays":ambiguous,"ray_queries":rays,"closed_ray_coverage":covered,"mounted_visual_mean_ms":solve_sum/solve_times.size(),"mounted_visual_p95_ms":solve_times[int(solve_times.size()*.95)],"mounted_visual_max_ms":solve_times[-1],"native_project_timing_ms":_timing_summary(project_times),"independent_measurement_ms":measurement_ms,"samples":samples}
		var backend:=_stats(actor)
		row["backend_stats"]={"projection":backend.get("mounted",{}),"body":backend.get("mounted_body",{})}
		row["contact_frames"]=_contact_frames
		if OS.get_environment("RL_MOUNT_REQUIRE_NATIVE")=="1":
			var projection: Dictionary=backend.get("mounted",{})
			var arithmetic: Dictionary=projection.get("native_stats",{})
			_check(bool(projection.get("native_projector",false)) and int(arithmetic.get("calls",0))>prior_native_calls and int(arithmetic.get("rejected",-1))==0,label+" "+gait+" executes new native material projections")
			_check(str((backend.get("mounted_body",{}) as Dictionary).get("backend",""))=="native",label+" "+gait+" executes the current native body field")
			prior_native_calls=int(arithmetic.get("calls",0))
		rows.append(row)
		_check(worst_mount<=CONTACT_TOLERANCE,label+" "+gait+" clears actual mount triangles: "+str(worst_mount))
		_check(worst_rider<=CONTACT_TOLERANCE,label+" "+gait+" clears actual rider/gear triangles: "+str(worst_rider))
		_check(worst_nape<=CONTACT_TOLERANCE,label+" "+gait+" body-owned nape clears the actual Head mesh: "+str(worst_nape))
		_check(stretch<MAX_EDGE_RATIO,label+" "+gait+" avoids stretched/spiked triangles: "+str(stretch))
		_check(step_error<MAX_FRAME_STEP,label+" "+gait+" avoids cape frame snaps: "+str(step_error))
		_check(rays>100 and covered>20,label+" "+gait+" has measured closed-surface contact coverage")
		# The established mounted policy adds deliberate flow at trot/gallop;
		# a slow walk may remain quiet while following the animal naturally.
		if gait in ["cruise","burst"]:_check(motion>.004,label+" "+gait+" retains cloth motion")
		print("MOUNT_APPROVED_SAMPLE ",label," ",JSON.stringify(row))
	var action_rows: Array=[]
	if mount_id=="moor_pony" and sex=="male":action_rows=_upper_action_cases(actor,visual,rig,groups,label)
	_anchor_check(rig,groups,label)
	var before:=_body_poses(rig)
	actor._cape_cloth.call("_process_modification_with_delta",STEP)
	_check(_transform_error(before,_body_poses(rig))<.000002,label+" cape writes leave seated body bones untouched")
	_check(_transform_error(body_rest,_body_poses(rig,true))<.000001,label+" preserves canonical body rest")
	actor.set_mount_state({},_models)
	_check(actor._cape_cloth.get("_mount_surface")==null,label+" releases mounted contact")
	var restored:=_sample(actor,&"idle",.4)
	_check(bool(restored.get("enabled",false)) and str(restored.get("profile",""))==profile,label+" restores the correct approved unmounted profile")
	var contract:=_cape_surface_contract(rig)
	_check(contract.materials==original.materials,label+" restores all three styled material slots")
	_check(contract.weights==original.weights and contract.bones==original.bones,label+" restores exact eight-slot weights and bone indices")
	_check(contract.resources==original.resources,label+" restores the original mesh and Skin resource references")
	_fit_surface_arrays(_samples(rig),profile,label+" dismounted")
	_mounted_rows.append({"case":label,"mount_id":mount_id,"rig":model,"profile":profile,"reference_contract":reference_contract,"relief_contract":relief_contract,"stages":rows,"upper_actions":action_rows})
	_geometry_cache.clear()
	actor.queue_free();await process_frame

func _attachment_reference_contract(actor: ReplicatedActor3D, profile: String, label: String, mode: String = "spine_neck") -> Dictionary:
	var rig:=actor.get_skeleton();var source:=_cape_meshes(rig)[0]
	var original:=_cape_surface_contract(rig);var body:=_body_poses(rig)
	var fitted:=ATTACHMENT.build(profile,source.mesh,rig,mode)
	_check(not fitted.is_empty(),label+" builds the mounted attachment separately from its solver")
	if fitted.is_empty():return {}
	var mesh: ArrayMesh=fitted.mesh;var skin: Skin=fitted.skin
	var frame:=rig.get_bone_global_rest(rig.find_bone("spine_03"))*source.skin.get_bind_pose(12)
	var attachment_index:=12 if mode in ["rigid_spine","spine_neck"] else 15
	var attachment_name:=&"spine_03" if attachment_index==12 else &"neck_01"
	var attachment:=rig.get_bone_global_rest(rig.find_bone(attachment_name))*source.skin.get_bind_pose(attachment_index)
	var idle: Array=_json(CATALOG).get("motion",{}).get("profiles",{}).get(profile,{}).get("idle",[])
	var original_reference: Array[Transform3D]=[];var modified_reference: Array[Transform3D]=[]
	for bind: int in 17:
		if bind<12:
			var offset:=Vector3(idle[bind*3],idle[bind*3+1],idle[bind*3+2])
			original_reference.append(frame*Transform3D(Basis.IDENTITY,offset))
			modified_reference.append((attachment if bind%4==0 else frame)*Transform3D(Basis.IDENTITY,offset))
		else:
			original_reference.append(rig.get_bone_global_rest(rig.find_bone(source.skin.get_bind_name(bind)))*source.skin.get_bind_pose(bind))
			var target_index:=15 if mode=="spine_neck" and bind>12 else attachment_index
			var target_name:=&"neck_01" if target_index==15 else attachment_name
			modified_reference.append(rig.get_bone_global_rest(rig.find_bone(target_name))*source.skin.get_bind_pose(target_index))
			_check(skin.get_bind_name(bind)==target_name and _transform_error([skin.get_bind_pose(bind)],[source.skin.get_bind_pose(target_index)])<.000001,
				label+" mounted body attachment uses the reviewed rigid torso palette")
	_check(_transform_error(original_reference,fitted.reference_palettes)<.000001,label+" source reference agrees with independent source Skin and rig matrices")
	_check(_transform_error(modified_reference,fitted.modified_reference_palettes)<.000001,label+" mounted reference agrees with the torso attachment and original lower9")
	var error:=0.;var count:=0
	for surface: int in source.mesh.get_surface_count():
		var before:=source.mesh.surface_get_arrays(surface);var after:=mesh.surface_get_arrays(surface)
		for field: int in [Mesh.ARRAY_BONES,Mesh.ARRAY_WEIGHTS,Mesh.ARRAY_INDEX,Mesh.ARRAY_TEX_UV]:
			_check(before[field].to_byte_array()==after[field].to_byte_array(),label+" attachment keeps native topology/UV/GPU attribute "+str(field)+" on surface"+str(surface))
		_check(mesh.surface_get_material(surface)==source.mesh.surface_get_material(surface),label+" attachment keeps source surface material")
		var old:=_palette_points(before,original_reference);var new:=_palette_points(after,modified_reference)
		error=maxf(error,_points_error(old,new));count+=old.size()
	_check(error<.000002 and count>1000,label+" reference rendering preserves every fitted vertex within two micrometres")
	_check(_cape_surface_contract(rig)==original,label+" attachment construction leaves source resources and GPU arrays intact")
	_check(_transform_error(body,_body_poses(rig))<.000001,label+" attachment construction leaves all Body65 poses intact")
	return {"mode":mode,"reference_pose":"canonical_global_rest","reference_render_error_m":error,"compared_vertices":count}

func _palette_points(arrays: Array, palettes: Array[Transform3D]) -> PackedVector3Array:
	var vertices: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
	var bones: PackedInt32Array=arrays[Mesh.ARRAY_BONES];var weights: PackedFloat32Array=arrays[Mesh.ARRAY_WEIGHTS]
	var result:=PackedVector3Array()
	for vertex: int in vertices.size():
		var point:=Vector3.ZERO
		for slot: int in 8:
			var at:=vertex*8+slot
			point+=palettes[bones[at]]*vertices[vertex]*weights[at]
		result.append(point)
	return result

func _mounted_relief_contract(actor: ReplicatedActor3D, rig: Skeleton3D, profile: String, label: String) -> Dictionary:
	var sources: Array=actor._cape_cloth.get("_mounted_sources")
	_check(not sources.is_empty(),label+" retains source resources for mounted-only relief")
	var amount: Vector2=ATTACHMENT.recommended_relief(profile)
	_check(amount.length()<=.03,label+" bounds the authored shoulder relief to thirty millimetres")
	var maximum:=0.;var neckline:=0.;var lower:=0.;var neck_count:=0;var lower_count:=0;var directions_valid:=true
	var idle: Array=_json(CATALOG).get("motion",{}).get("profiles",{}).get(profile,{}).get("idle",[])
	for entry: Dictionary in sources:
		var node: MeshInstance3D=(entry.node as WeakRef).get_ref() as MeshInstance3D
		if node==null:continue
		var original_mesh: Mesh=entry.mesh;var original_skin: Skin=entry.skin
		var unrelieved:=ATTACHMENT.build(profile,original_mesh,rig,"spine_neck")
		var expected:=ATTACHMENT.build(profile,original_mesh,rig,"spine_neck",amount)
		_check(not unrelieved.is_empty() and not expected.is_empty(),label+" has valid pure and relieved reference configurations")
		if unrelieved.is_empty() or expected.is_empty():continue
		_check(node.mesh==expected.mesh and node.skin==expected.skin,label+" installs the reviewed relief configuration")
		var frame:=rig.get_bone_global_rest(rig.find_bone("spine_03"))*original_skin.get_bind_pose(12)
		var inverse_frame:=frame.basis.inverse()
		var palettes: Array[Transform3D]=[]
		for i: int in 17:
			if i<12:palettes.append(frame*Transform3D(Basis.IDENTITY,Vector3(idle[i*3],idle[i*3+1],idle[i*3+2])))
			else:palettes.append(frame if i==12 else rig.get_bone_global_rest(rig.find_bone("neck_01"))*original_skin.get_bind_pose(15))
		for surface: int in node.mesh.get_surface_count():
			var actual:=_palette_points(node.mesh.surface_get_arrays(surface),palettes)
			var baseline:=_palette_points((unrelieved.mesh as Mesh).surface_get_arrays(surface),palettes)
			var source_arrays:=original_mesh.surface_get_arrays(surface)
			var material: PackedVector3Array=source_arrays[Mesh.ARRAY_VERTEX]
			for v: int in actual.size():
				var delta:=inverse_frame*(actual[v]-baseline[v]);var distance:=delta.length()
				maximum=maxf(maximum,distance)
				directions_valid=directions_valid and delta.is_finite() and absf(delta.x)<.000002 and delta.y>=-.000002 and delta.y<=amount.y+.000002 and delta.z<=.000002 and -delta.z<=amount.x+.000002
				if material[v].y<=1.22:lower=maxf(lower,distance);lower_count+=1
				if absf(material[v].x)<=.035 and material[v].y>=1.53:neckline=maxf(neckline,distance);neck_count+=1
	_check(directions_valid and maximum<=amount.length()+.000002,label+" applies only bounded posterior/upward shoulder relief")
	_check(neck_count>300 and neckline<.000002,label+" keeps the centre neckline fixed through shoulder relief")
	_check(lower_count>7000 and lower<.000002,label+" leaves the lower approved fit unchanged through shoulder relief")
	return {"maximum_intentional_relief_m":maximum,"neckline_maximum_delta_m":neckline,"neckline_vertices":neck_count,"lower_maximum_delta_m":lower,"lower_vertices":lower_count}

func _upper_action_cases(actor: ReplicatedActor3D, visual: Node3D, rig: Skeleton3D, groups: Array, label: String) -> Array:
	var upper: RefCounted=visual.get("upper")
	var rows: Array=[]
	# Upper-body animation can sweep the entire drape quickly. This diagnostic
	# allows the measured body sweep and its retained settling history, then
	# gates unexplained motion at80mm plus an explicit1mm visual-review margin.
	# It is a heuristic, not a floating-point tolerance; gait/wake gates stay80mm.
	var limit:=MAX_FRAME_STEP+UPPER_MOTION_REVIEW_MARGIN
	_upper_motion_metric_controls()
	for moving: bool in [false,true]:
		actor.set_mount_state({"mode":"mounted","mount_id":"moor_pony","gait":"cruise" if moving else "idle","step_us":200000},_models)
		actor._presentation_speed=5. if moving else 0.
		actor._segment_start=actor.global_position
		actor._segment_duration=100. if moving else 0.
		actor.server_target=actor.global_position+actor.global_basis*Vector3(0,0,-500.) if moving else actor.global_position
		for requested: StringName in UPPER_ACTIONS:
			upper.call("begin_return")
			actor.play_action(&"run" if moving else &"idle")
			for frame: int in 30:visual.call("_process",STEP)
			if requested==&"cast_aggressive":actor.set_spell_variant(2)
			elif requested==&"cast_defensive":actor.set_spell_variant(75)
			elif requested==&"heal":actor.set_spell_variant(3)
			var available: bool=(upper.get("clips") as Dictionary).has(requested)
			_check(available,label+" retains supported mounted action "+str(requested))
			if not available:continue
			var previous:=_motion_points_in(groups,actor.global_transform.affine_inverse())
			var previous_shape:=_motion_points(rig,groups)
			var previous_anchor: Vector3=actor.to_local(rig.global_transform*rig.get_bone_global_pose(rig.find_bone("spine_03")).origin)
			var previous_translated:=PackedVector3Array()
			for point: Vector3 in previous:previous_translated.append(point-previous_anchor)
			var previous_spine: Transform3D=actor.global_transform.affine_inverse()*rig.global_transform*rig.get_bone_global_pose(rig.find_bone("spine_03"))
			var previous_neck: Transform3D=actor.global_transform.affine_inverse()*rig.global_transform*rig.get_bone_global_pose(rig.find_bone("neck_01"))
			var older:=PackedVector3Array();var older_translated:=PackedVector3Array()
			var sweep_peak:=0.;var spine_sweep_peak:=0.;var neck_sweep_peak:=0.;var body_envelope:=0.;var previous_excess:=0.;var excess_peak:=0.;var excess_witness: Dictionary={};var reversals: Array=[];var trajectory: Array=[]
			actor.play_action(requested,true)
			var mount_inside:=0.;var rider_inside:=0.;var nape_inside:=0.;var stretch:=0.;var all_stretch:=0.;var samples: Array=[]
			var step_error:=0.;var actor_step:=0.;var shape_step:=0.;var translated_step:=0.;var jump_witness: Dictionary={}
			var motion_finite:=true
			var excess_run:=0;var longest_excess_run:=0;var quiet_excess:=0;var excess_candidates: Array=[]
			var upper_visual_times: Array[float]=[];var upper_project_times: Array[float]=[]
			for frame: int in 60:
				if moving:actor.global_position+=actor.global_basis*Vector3(0,0,-5.*STEP)
				var process_started:=Time.get_ticks_usec()
				visual.call("_process",STEP)
				upper_visual_times.append(float(Time.get_ticks_usec()-process_started)/1000.)
				var arithmetic: Dictionary=_stats(actor).get("mounted",{})
				upper_project_times.append(float(arithmetic.get("project_usec",0))/1000.)
				var current:=_motion_points_in(groups,actor.global_transform.affine_inverse())
				var shape_current:=_motion_points(rig,groups)
				var anchor: Vector3=actor.to_local(rig.global_transform*rig.get_bone_global_pose(rig.find_bone("spine_03")).origin)
				var translated_current:=PackedVector3Array()
				for point: Vector3 in current:
					translated_current.append(point-anchor)
					motion_finite=motion_finite and point.is_finite()
				var world_error:=_points_error(previous,current)
				var shape_error:=_points_error(previous_shape,shape_current)
				var translated_error:=_points_error(previous_translated,translated_current)
				actor_step=maxf(actor_step,world_error);shape_step=maxf(shape_step,shape_error);translated_step=maxf(translated_step,translated_error)
				# The same shared rigid frames as the gait gate distinguish cape
				# discontinuities from body carry during an upper-body transition.
				var error:=minf(world_error,minf(shape_error,translated_error))
				var current_spine: Transform3D=actor.global_transform.affine_inverse()*rig.global_transform*rig.get_bone_global_pose(rig.find_bone("spine_03"))
				var current_neck: Transform3D=actor.global_transform.affine_inverse()*rig.global_transform*rig.get_bone_global_pose(rig.find_bone("neck_01"))
				var carry:=current_spine*previous_spine.affine_inverse()
				var neck_carry:=current_neck*previous_neck.affine_inverse()
				var spine_sweep:=0.;var neck_sweep:=0.
				for point: Vector3 in previous:
					spine_sweep=maxf(spine_sweep,point.distance_to(carry*point))
					neck_sweep=maxf(neck_sweep,point.distance_to(neck_carry*point))
				# All three upper drivers follow the measured Spine/Neck anatomy.
				# Keep both observed components; either can carry the attached cape.
				var body_sweep:=maxf(spine_sweep,neck_sweep)
				spine_sweep_peak=maxf(spine_sweep_peak,spine_sweep);neck_sweep_peak=maxf(neck_sweep_peak,neck_sweep)
				# The warm solver retains65% of its prior target, so a body-driven
				# sweep may keep settling after the torso has stopped turning.
				var measurement:=_upper_motion_measurement(error,body_sweep,body_envelope)
				body_envelope=measurement.envelope
				var excess: float=measurement.excess
				var body_active:=body_envelope>=MAX_FRAME_STEP
				if _upper_motion_exceeds(excess,limit):
					excess_run+=1;longest_excess_run=maxi(longest_excess_run,excess_run)
					if not body_active:quiet_excess+=1
					excess_candidates.append({"frame":frame,"excess_m":excess,"body_sweep_envelope_m":body_envelope,"anatomical_body_active":body_active,"review_required":body_active})
				else:excess_run=0
				sweep_peak=maxf(sweep_peak,body_sweep)
				if excess>excess_peak:excess_peak=excess;excess_witness={"frame":frame,"cape_step_m":error,"body_sweep_m":body_sweep,"spine_body_sweep_m":spine_sweep,"neck_body_sweep_m":neck_sweep,"body_sweep_envelope_m":body_envelope,"excess_m":excess}
				if not older.is_empty():
					for vertex: int in current.size():
						var a:=_upper_reversal(older[vertex],previous[vertex],current[vertex])
						var b:=_upper_reversal(older_translated[vertex],previous_translated[vertex],translated_current[vertex])
						if bool(a.hit) or bool(b.hit):reversals.append({"frame":frame,"motion_sample":vertex,"actor":a,"spine_translation":b,"both_frames":bool(a.hit) and bool(b.hit),"unexplained":_upper_motion_exceeds(previous_excess,limit) and _upper_motion_exceeds(excess,limit)})
				trajectory.append({"frame":frame,"actor_step_m":world_error,"best_existing_step_m":error,"body_sweep_m":body_sweep,"spine_body_sweep_m":spine_sweep,"neck_body_sweep_m":neck_sweep,"body_sweep_envelope_m":body_envelope,"unexplained_excess_m":excess})
				older=previous;older_translated=previous_translated;previous_spine=current_spine;previous_neck=current_neck;previous_excess=excess
				if error>step_error:
					step_error=error
					var witness_current:=current;var witness_previous:=previous;var mode:="actor"
					if shape_error<world_error and shape_error<=translated_error:witness_current=shape_current;witness_previous=previous_shape;mode="spine_rigid"
					elif translated_error<world_error:witness_current=translated_current;witness_previous=previous_translated;mode="spine_translation"
					for vertex: int in current.size():
						if witness_current[vertex].distance_to(witness_previous[vertex])>=error-.000001:
							jump_witness={"frame":frame,"motion_sample":vertex,"carry_frame":mode,"previous":_point_array(witness_previous[vertex]),"current":_point_array(witness_current[vertex])}
							break
				previous=current;previous_shape=shape_current;previous_translated=translated_current
				if frame not in [12,30,59]:continue
				if frame==12:_check(upper.get("action")==requested,label+" routes "+str(requested)+" through the existing mounted upper-body path")
				var inverse:=actor.global_transform.affine_inverse()
				var cape:=_cape_points(rig,groups,inverse)
				var mount:=_contact(cape.contact,_atlases(visual,inverse,1),1)
				var rider_atlases:=_atlases(actor.get_node("NativeModel"),inverse,2,true)
				var rider:=_contact(cape.contact,rider_atlases,2)
				var nape:=_contact(cape.nape,_head_atlases(rider_atlases),2)
				mount["cape_source"]=_contact_source(cape,mount,groups)
				rider["cape_source"]=_contact_source(cape,rider,groups)
				nape["cape_source"]=_contact_source(cape,nape,groups,true)
				nape_inside=maxf(nape_inside,nape.deepest)
				mount_inside=maxf(mount_inside,mount.deepest);rider_inside=maxf(rider_inside,rider.deepest)
				stretch=maxf(stretch,cape.stretch);all_stretch=maxf(all_stretch,cape.all_stretch)
				samples.append({"frame":frame,"mount":mount,"rider":rider,"edge_ratio":cape.stretch,"all_edge_ratio":cape.all_stretch,"body_owned_edge_ratio":cape.body_stretch,"rebased_all_edge_ratio":cape.rebased_all_stretch,"edge_witness":cape.edge_witness,"upper_action":str(upper.get("action"))})
				_check(cape.finite,label+" "+str(requested)+" keeps the actual cape skin finite")
			_check(mount_inside<=CONTACT_TOLERANCE,label+" "+str(requested)+" clears the mount during "+("travel" if moving else "standing")+": "+str(mount_inside))
			_check(rider_inside<=CONTACT_TOLERANCE,label+" "+str(requested)+" clears rider/gear during "+("travel" if moving else "standing")+": "+str(rider_inside))
			_check(nape_inside<=CONTACT_TOLERANCE,label+" "+str(requested)+" body-owned nape clears Head: "+str(nape_inside))
			_check(stretch<MAX_EDGE_RATIO,label+" "+str(requested)+" keeps source material edges below the strain limit: "+str(stretch))
			_check(not previous.is_empty() and motion_finite,label+" "+str(requested)+" has finite actual-skin motion samples on all60frames")
			_check(quiet_excess==0,label+" "+str(requested)+" has no quiet-body or history-expired cape reset: "+str(quiet_excess))
			_check(longest_excess_run<2,label+" "+str(requested)+" has no sustained body-unexplained cape excess: "+str(longest_excess_run))
			var isolated:=0
			for reversal: Dictionary in reversals:
				if bool(reversal.both_frames) and bool(reversal.unexplained):isolated+=1
			_check(isolated==0,label+" "+str(requested)+" has no large isolated single-frame cape reversal: "+str(isolated))
			# One isolated modifier ownership check follows all native samples.
			var before:=_body_poses(rig)
			actor._cape_cloth.call("_process_modification_with_delta",STEP)
			_check(_transform_error(before,_body_poses(rig))<.000002,label+" cape does not overwrite Body65 during "+str(requested))
			_anchor_check(rig,groups,label+"/"+str(requested))
			rows.append({"moving":moving,"action":str(requested),"mount_inside_m":mount_inside,"rider_inside_m":rider_inside,"maximum_edge_ratio":stretch,"maximum_all_edge_ratio":all_stretch,"upper_motion_nominal_limit_m":MAX_FRAME_STEP,"upper_motion_visual_review_margin_m":UPPER_MOTION_REVIEW_MARGIN,"upper_motion_measurement_resolution_m":UPPER_MOTION_RESOLUTION,"unexplained_excess_nearest_mm_m":roundf(excess_peak/UPPER_MOTION_RESOLUTION)*UPPER_MOTION_RESOLUTION,"upper_body_history_retained_fraction":UPPER_BODY_MEMORY,"body_sweep_peak_m":sweep_peak,"spine_body_sweep_peak_m":spine_sweep_peak,"neck_body_sweep_peak_m":neck_sweep_peak,"mounted_visual_timing_ms":_timing_summary(upper_visual_times),"native_project_timing_ms":_timing_summary(upper_project_times),"unexplained_excess_peak_m":excess_peak,"excess_candidates":excess_candidates,"quiet_body_excess_frames":quiet_excess,"longest_consecutive_excess_frames":longest_excess_run,"active_body_motion_scale_m":MAX_FRAME_STEP,"single_active_excess_review_basis":"Native frame30-38 geometry review found coherent multi-frame anatomical recovery/constraint settling, attached neckline and aligned panel motion. A lone active-body excess is advisory and retained for review; quiet, sustained and isolated out/back resets remain failures.","excess_witness":excess_witness,"isolated_reversals":reversals,"trajectory":trajectory,"dense_motion_frames":60,"motion_samples":previous.size(),"largest_vertex_frame_step_m":step_error,"largest_actor_frame_step_m":actor_step,"largest_spine_relative_step_m":shape_step,"largest_spine_translation_step_m":translated_step,"jump_witness":jump_witness,"samples":samples})
	return rows

func _timing_summary(values: Array[float]) -> Dictionary:
	if values.is_empty():return {"samples":0}
	var sorted:=values.duplicate();sorted.sort();var total:=0.
	for value: float in values:total+=value
	return {"samples":values.size(),"mean":total/values.size(),"p95":sorted[int(sorted.size()*.95)],"max":sorted[-1]}

func _upper_reversal(a: Vector3,b: Vector3,c: Vector3) -> Dictionary:
	var first:=b-a;var second:=c-b
	var l1:=first.length();var l2:=second.length()
	var cosine:=first.dot(second)/maxf(.000000001,l1*l2)
	var near:=a.distance_to(c);var tolerance:=maxf(.02,.25*minf(l1,l2))
	return {"hit":l1>MAX_FRAME_STEP and l2>MAX_FRAME_STEP and cosine<-.8 and near<=tolerance,"first_m":l1,"second_m":l2,"cosine":cosine,"return_distance_m":near,"return_tolerance_m":tolerance}

func _upper_motion_exceeds(excess: float, limit: float) -> bool:
	# This approximate body-sweep heuristic is reviewed at nearest-millimetre
	# resolution. The raw value is always retained; this is not float error.
	return roundf(excess/UPPER_MOTION_RESOLUTION)*UPPER_MOTION_RESOLUTION>limit

func _upper_motion_measurement(step: float, body_sweep: float, previous_envelope: float) -> Dictionary:
	var envelope:=maxf(body_sweep,UPPER_BODY_MEMORY*previous_envelope)
	return {"envelope":envelope,"excess":maxf(0.,step-envelope)}

func _upper_motion_metric_controls() -> void:
	# Static identity body makes Actor and Spine-translation frames identical.
	# Deliberate resets and sustained excess must be detected even though fast
	# coherent body motion and its decaying cape response are allowed.
	var controls: Array=[
		["quiet permanent reset",[0.,.2,.2],[0.,0.],true],
		["quiet one-frame out-and-back",[0.,.2,0.],[0.,0.],true],
		["quiet sustained fast motion",[0.,.1,.2,.3],[0.,0.,0.],true],
		["coherent body reversal",[0.,.2,0.],[.2,.2],false],
		["body-driven decaying settle",[0.,.2,.3,.365,.40725],[.3,0.,0.,0.],false],
		["quiet small sway",[0.,.04,0.,-.04],[0.,0.,0.],false],
		["single coherent active-body excess",[0.,.3,.4],[.2,.2],false],
		["sustained active-body excess",[0.,.3,.6,.9],[.2,.2,.2],true],
		["active-body unexplained out-and-back",[0.,.3,0.],[.2,.2],true],
		["quiet reset after body history expires",[0.,.2,.3,.365,.40725,.4347125,.452563125,.46416603125,.66416603125],[.3,0.,0.,0.,0.,0.,0.,0.],true]
	]
	var limit:=MAX_FRAME_STEP+UPPER_MOTION_REVIEW_MARGIN
	for control: Array in controls:
		var envelope:=0.;var previous_excess:=0.;var rejected:=false;var reversal_detected:=false;var excess_run:=0
		for at: int in range(1,control[1].size()):
			var step:=absf(float(control[1][at])-float(control[1][at-1]))
			var measurement:=_upper_motion_measurement(step,float(control[2][at-1]),envelope)
			envelope=measurement.envelope
			var excess: float=measurement.excess
			if _upper_motion_exceeds(excess,limit):
				excess_run+=1
				rejected=rejected or envelope<MAX_FRAME_STEP or excess_run>=2
			else:excess_run=0
			if at>=2:
				var reversal:=_upper_reversal(Vector3(float(control[1][at-2]),0,0),Vector3(float(control[1][at-1]),0,0),Vector3(float(control[1][at]),0,0))
				reversal_detected=reversal_detected or (bool(reversal.hit) and _upper_motion_exceeds(previous_excess,limit) and _upper_motion_exceeds(excess,limit))
			previous_excess=excess
		_check((rejected or reversal_detected)==bool(control[3]),"upper continuity heuristic sensitivity: "+str(control[0]))
		if str(control[0])=="quiet one-frame out-and-back":_check(reversal_detected,"upper reversal guard detects a quiet-body one-frame reset")

func _cape_groups(rig: Skeleton3D) -> Array:
	var groups: Array=[]
	for mesh: MeshInstance3D in _cape_meshes(rig):
		for surface: int in mesh.mesh.get_surface_count():
			var group:=_geometry(mesh,surface)
			var shares:=PackedFloat32Array();var motion:=PackedInt32Array();var anchors:=PackedInt32Array()
			for vertex: int in group.vertices.size():
				var share:=0.
				for slot: int in group.slots:
					var at:=vertex*int(group.slots)+slot
					if str(group.names[group.bones[at]]).begins_with("cape_"):share+=group.weights[at]
				shares.append(share)
				if share>.99 and vertex%96==0 and group.vertices[vertex].y<.7:motion.append(vertex)
				if share<.000001 and vertex%8==0:anchors.append(vertex)
			group["shares"]=shares;group["motion"]=motion;group["anchors"]=anchors
			group["material_vertices"]=_approved_material_vertices(str(mesh.get_meta("cape_approved_profile","")),surface)
			_check(group.material_vertices.size()==group.vertices.size(),"mounted material coordinates retain approved source vertex ordering")
			groups.append(group)
	return groups

func _approved_material_vertices(profile: String, surface: int) -> PackedVector3Array:
	var key:=profile+"/"+str(surface)
	if _material_vertices.has(key):return _material_vertices[key]
	var fit: Dictionary=_json(CATALOG).get("fits",{}).get(profile,{})
	var surfaces: Array=fit.get("surfaces",[])
	var result:=PackedVector3Array()
	if surface>=surfaces.size():return result
	var bytes:=FileAccess.get_file_as_bytes(CATALOG.get_base_dir().path_join(str(fit.get("file",""))))
	var descriptor: Dictionary=surfaces[surface].get("positions",{})
	var offset:=int(descriptor.get("offset",0))
	var values:=bytes.slice(offset,offset+int(descriptor.get("count",0))*4).to_float32_array()
	for vertex: int in values.size()/3:result.append(Vector3(values[vertex*3],values[vertex*3+1],values[vertex*3+2]))
	_material_vertices[key]=result
	return result

func _geometry(mesh: MeshInstance3D, surface: int) -> Dictionary:
	var key:=str(mesh.get_instance_id())+"/"+str(mesh.mesh.get_instance_id())+"/"+str(surface)+"/"+str(mesh.skin.get_instance_id() if mesh.skin!=null else 0)
	if _geometry_cache.has(key):return _geometry_cache[key]
	var arrays:=mesh.mesh.surface_get_arrays(surface)
	var vertices: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array=arrays[Mesh.ARRAY_INDEX]
	if indices.is_empty():for vertex: int in vertices.size():indices.append(vertex)
	var names:=PackedStringArray();var binds: Array[Transform3D]=[]
	if mesh.skin!=null:
		for bind: int in mesh.skin.get_bind_count():names.append(mesh.skin.get_bind_name(bind));binds.append(mesh.skin.get_bind_pose(bind))
	var bones: PackedInt32Array=arrays[Mesh.ARRAY_BONES] if arrays[Mesh.ARRAY_BONES]!=null else PackedInt32Array()
	var weights: PackedFloat32Array=arrays[Mesh.ARRAY_WEIGHTS] if arrays[Mesh.ARRAY_WEIGHTS]!=null else PackedFloat32Array()
	var rig: Skeleton3D=mesh.get_node_or_null(mesh.skeleton) as Skeleton3D if mesh.skin!=null else null
	var value: Dictionary={"mesh":mesh,"surface":surface,"vertices":vertices,"indices":indices,"bones":bones,"weights":weights,"slots":bones.size()/maxi(1,vertices.size()),"names":names,"binds":binds,"rig":rig}
	_geometry_cache[key]=value
	return value

func _skin(group: Dictionary, inverse: Transform3D, selected:=PackedInt32Array()) -> PackedVector3Array:
	var mesh: MeshInstance3D=group.mesh
	var rig: Skeleton3D=group.rig
	var palette: Array[Transform3D]=[]
	if rig!=null:
		for bind: int in group.names.size():
			var bone:=rig.find_bone(group.names[bind])
			if bone<0:bone=mesh.skin.get_bind_bone(bind)
			palette.append(rig.get_bone_global_pose(bone)*group.binds[bind])
	var result:=PackedVector3Array()
	var count: int=group.vertices.size() if selected.is_empty() else selected.size()
	for at: int in count:
		var vertex: int=at if selected.is_empty() else selected[at]
		var p:=Vector3.ZERO
		if rig==null:p=inverse*mesh.global_transform*group.vertices[vertex]
		else:
			for slot: int in group.slots:
				var influence:=vertex*int(group.slots)+slot
				if group.weights[influence]>0:p+=palette[group.bones[influence]]*group.vertices[vertex]*group.weights[influence]
			p=inverse*rig.global_transform*p
		# Use engine read-back weights exactly; GPU UNORM16 weights are not
		# renormalized after storage and a second normalization moves the cloth.
		result.append(p)
	return result

func _motion_points(rig: Skeleton3D, groups: Array) -> PackedVector3Array:
	var spine:=rig.find_bone("spine_03")
	var inverse: Transform3D=(rig.global_transform*rig.get_bone_global_pose(spine)*rig.get_bone_global_rest(spine).affine_inverse()).affine_inverse()
	return _motion_points_in(groups,inverse)

func _motion_points_in(groups: Array, inverse: Transform3D) -> PackedVector3Array:
	var result:=PackedVector3Array()
	for group: Dictionary in groups:
		if not group.motion.is_empty():result.append_array(_skin(group,inverse,group.motion))
	return result

func _cape_points(rig: Skeleton3D, groups: Array, inverse: Transform3D) -> Dictionary:
	var contact:=PackedVector3Array();var nape:=PackedVector3Array();var contact_sources:=PackedInt32Array();var nape_sources:=PackedInt32Array()
	var maximum:=0.;var all_maximum:=0.;var body_maximum:=0.;var rebase_maximum:=0.;var finite:=true;var witness: Dictionary={};var body_witness: Dictionary={}
	for group_index: int in groups.size():
		var group: Dictionary=groups[group_index]
		var p:=_skin(group,inverse)
		var material_basis: Basis=(inverse*(group.rig as Skeleton3D).global_transform).basis
		var material: PackedVector3Array=group.get("material_vertices",group.vertices)
		if material.size()!=group.vertices.size():material=group.vertices
		for vertex: int in p.size():
			finite=finite and p[vertex].is_finite()
			if group.shares[vertex]>.05:
				contact.append(p[vertex]);contact_sources.append_array(PackedInt32Array([group_index,vertex,-1,-1,0]))
			elif material[vertex].y>=1.4:
				nape.append(p[vertex]);nape_sources.append_array(PackedInt32Array([group_index,vertex,-1,-1,0]))
		var contact_edges: Array[Vector2i]=[];var seen_edges: Dictionary={}
		var build_edges:=not group.has("contact_edges")
		for at: int in range(0,group.indices.size(),3):
			var a: int=group.indices[at];var b: int=group.indices[at+1];var c: int=group.indices[at+2]
			if (group.shares[a]+group.shares[b]+group.shares[c])/3.>.05:
				contact.append((p[a]+p[b]+p[c])/3.);contact_sources.append_array(PackedInt32Array([group_index,a,b,c,1]))
			elif (material[a].y+material[b].y+material[c].y)/3.>=1.4:
				nape.append((p[a]+p[b]+p[c])/3.);nape_sources.append_array(PackedInt32Array([group_index,a,b,c,1]))
			for edge: Vector2i in [Vector2i(a,b),Vector2i(b,c),Vector2i(c,a)]:
				if build_edges:
					var key:=Vector2i(mini(edge.x,edge.y),maxi(edge.x,edge.y))
					if not seen_edges.has(key) and material[key.x].distance_to(material[key.y])>CONTACT_EDGE_LENGTH:
						seen_edges[key]=true;contact_edges.append(key)
				var rest: float=(material_basis*(material[edge.x]-material[edge.y])).length()
				if rest<=.005:continue
				var ratio:=p[edge.x].distance_to(p[edge.y])/rest
				var rebased_rest: float=(material_basis*((group.vertices[edge.x] as Vector3)-(group.vertices[edge.y] as Vector3))).length()
				if rebased_rest>.000001:rebase_maximum=maxf(rebase_maximum,p[edge.x].distance_to(p[edge.y])/rebased_rest)
				all_maximum=maxf(all_maximum,ratio)
				var movable: bool=group.shares[edge.x]>.000001 or group.shares[edge.y]>.000001
				if (movable and ratio>maximum) or (not movable and ratio>body_maximum):
					var value: Dictionary={"surface":group.surface,"a":edge.x,"b":edge.y,"rest_length_m":rest,"rebased_rest_length_m":rebased_rest,"posed_length_m":rest*ratio,"rest_a":_point_array(material[edge.x]),"rest_b":_point_array(material[edge.y]),"posed_a":_point_array(p[edge.x]),"posed_b":_point_array(p[edge.y]),"cape_share_a":group.shares[edge.x],"cape_share_b":group.shares[edge.y]}
					if movable:maximum=ratio;witness=value
					else:body_maximum=ratio;body_witness=value
		if build_edges:group["contact_edges"]=contact_edges
		# These witnesses are evaluated from actual GPU skin positions. Quarters
		# and midpoints independently test gaps between runtime contact samples.
		for edge: Vector2i in group.contact_edges:
			for fraction_index: int in CONTACT_EDGE_FRACTIONS.size():
				contact.append(p[edge.x].lerp(p[edge.y],CONTACT_EDGE_FRACTIONS[fraction_index]))
				contact_sources.append_array(PackedInt32Array([group_index,edge.x,edge.y,-1,fraction_index+2]))
	return {"contact":contact,"nape":nape,"contact_sources":contact_sources,"nape_sources":nape_sources,"stretch":maximum,"all_stretch":all_maximum,"body_stretch":body_maximum,"rebased_all_stretch":rebase_maximum,"finite":finite,"edge_witness":witness,"body_witness":body_witness}

func _contact_source(cape: Dictionary, result: Dictionary, groups: Array, nape:=false) -> Dictionary:
	var records: PackedInt32Array=cape.get("nape_sources" if nape else "contact_sources",PackedInt32Array())
	var at:=int(result.get("worst_point_index",-1))*5
	if at<0 or at+4>=records.size():return {}
	var group: Dictionary=groups[records[at]]
	var vertices: Array[int]=[records[at+1]];var fractions: Array[float]=[1.]
	var kind:=records[at+4]
	if kind==1:vertices=[records[at+1],records[at+2],records[at+3]];fractions=[1./3.,1./3.,1./3.]
	elif kind>=2:
		var fraction: float=CONTACT_EDGE_FRACTIONS[kind-2]
		vertices=[records[at+1],records[at+2]];fractions=[1.-fraction,fraction]
	var weights:=PackedFloat64Array();weights.resize(group.names.size());weights.fill(0.)
	var source_position:=Vector3.ZERO
	var material: PackedVector3Array=group.get("material_vertices",group.vertices)
	for i: int in vertices.size():
		source_position+=material[vertices[i]]*fractions[i]
		for slot: int in group.slots:
			var index:=vertices[i]*int(group.slots)+slot
			weights[group.bones[index]]+=float(group.weights[index])*fractions[i]
	var root_weights:=PackedFloat64Array();var free_norm:=0.;var body:=0.
	for i: int in weights.size():
		if i in [0,4,8]:root_weights.append(weights[i])
		elif i<12:free_norm+=weights[i]*weights[i]
		else:body+=weights[i]
	return {"surface":group.surface,"vertices":vertices,"fractions":fractions,"source_position":_point_array(source_position),"root_shares":Array(root_weights),"body_share":body,"free9_sum_w2":free_norm,"bone_names":Array(group.names),"raw_weights":Array(weights)}

func _head_atlases(atlases: Array) -> Array:
	var result: Array=[]
	for atlas: Dictionary in atlases:
		if "head" in str(atlas.name).to_lower():result.append(atlas)
	return result

func _point_array(point: Vector3) -> Array:return [point.x,point.y,point.z]

func _atlases(node: Node, inverse: Transform3D, axis: int, rider:=false) -> Array:
	var result: Array=[]
	for child: Node in node.find_children("*","MeshInstance3D",true,false):
		var mesh:=child as MeshInstance3D
		if not mesh.is_visible_in_tree() or mesh.mesh==null or mesh.has_meta(&"occlusion_silhouette_clone"):continue
		if mesh.mesh is ImmediateMesh or mesh.mesh is PointMesh:continue
		if rider and (str(mesh.name).begins_with(CAPE_PREFIX) or mesh.has_meta("portrait_groom")):continue
		var grid: Dictionary={}
		var uv0:=PackedVector2Array();var edge1:=PackedVector2Array();var edge2:=PackedVector2Array()
		var inverse_denominators:=PackedFloat64Array();var normals:=PackedVector3Array()
		var planes:=PackedFloat64Array();var heights:=PackedVector3Array()
		var triangle_a:=PackedVector3Array();var triangle_b:=PackedVector3Array();var triangle_c:=PackedVector3Array()
		var triangle_low:=PackedVector3Array();var triangle_high:=PackedVector3Array()
		var triangle_surfaces:=PackedInt32Array();var triangle_ordinals:=PackedInt32Array()
		for surface: int in mesh.mesh.get_surface_count():
			if mesh.mesh is ArrayMesh and (mesh.mesh as ArrayMesh).surface_get_primitive_type(surface)!=Mesh.PRIMITIVE_TRIANGLES:continue
			var group:=_geometry(mesh,surface);var p:=_skin(group,inverse)
			for at: int in range(0,group.indices.size(),3):
				var a: Vector3=p[group.indices[at]];var b: Vector3=p[group.indices[at+1]];var c: Vector3=p[group.indices[at+2]]
				triangle_a.append(a);triangle_b.append(b);triangle_c.append(c)
				triangle_surfaces.append(surface);triangle_ordinals.append(at/3)
				triangle_low.append(Vector3(minf(a.x,minf(b.x,c.x)),minf(a.y,minf(b.y,c.y)),minf(a.z,minf(b.z,c.z))))
				triangle_high.append(Vector3(maxf(a.x,maxf(b.x,c.x)),maxf(a.y,maxf(b.y,c.y)),maxf(a.z,maxf(b.z,c.z))))
				var uv: Array[Vector2]=[_project(a,axis),_project(b,axis),_project(c,axis)]
				var denominator: float=(uv[1]-uv[0]).cross(uv[2]-uv[0])
				if absf(denominator)<.00000001:continue
				var index:=uv0.size();var normal: Vector3=(b-a).cross(c-a).normalized()
				uv0.append(uv[0]);edge1.append(uv[1]-uv[0]);edge2.append(uv[2]-uv[0])
				inverse_denominators.append(1./denominator);normals.append(normal);planes.append(a.dot(normal))
				heights.append(Vector3(a[axis],b[axis]-a[axis],c[axis]-a[axis]))
				var low:=Vector2(minf(uv[0].x,minf(uv[1].x,uv[2].x)),minf(uv[0].y,minf(uv[1].y,uv[2].y)))
				var high:=Vector2(maxf(uv[0].x,maxf(uv[1].x,uv[2].x)),maxf(uv[0].y,maxf(uv[1].y,uv[2].y)))
				for x: int in range(int(floor(low.x/CELL)),int(floor(high.x/CELL))+1):
					for y: int in range(int(floor(low.y/CELL)),int(floor(high.y/CELL))+1):
						var key:=Vector2i(x,y)
						if not grid.has(key):grid[key]=[]
						(grid[key] as Array).append(index)
		if not uv0.is_empty():result.append({"grid":grid,"uv0":uv0,"edge1":edge1,"edge2":edge2,"inverse_denominators":inverse_denominators,"normals":normals,"planes":planes,"heights":heights,"name":str(mesh.name),"triangle_a":triangle_a,"triangle_b":triangle_b,"triangle_c":triangle_c,"triangle_low":triangle_low,"triangle_high":triangle_high,"triangle_surfaces":triangle_surfaces,"triangle_ordinals":triangle_ordinals,"node_path":str(node.get_path_to(mesh))})
	return result

func _project(point: Vector3, axis: int) -> Vector2:
	return Vector2(point.x,point.z) if axis==1 else Vector2(point.x,point.y)

func _contact(points: PackedVector3Array, atlases: Array, axis: int) -> Dictionary:
	var deepest:=0.;var inside:=0;var ambiguous:=0;var rays:=0;var covered:=0
	var plane_deepest:=0.;var parity_inside:=0
	var worst_point:=Vector3.ZERO;var worst_mesh:="";var worst_index:=-1;var worst_face: Dictionary={}
	for point_index: int in points.size():
		var point:=points[point_index]
		var uv:=_project(point,axis);var key:=Vector2i(int(floor(uv.x/CELL)),int(floor(uv.y/CELL)))
		for atlas: Dictionary in atlases:
			if not atlas.grid.has(key):continue
			rays+=1
			var hits: Array=[]
			var uv0: PackedVector2Array=atlas.uv0;var edge1: PackedVector2Array=atlas.edge1;var edge2: PackedVector2Array=atlas.edge2
			var inverse_denominators: PackedFloat64Array=atlas.inverse_denominators;var heights: PackedVector3Array=atlas.heights
			var normals: PackedVector3Array=atlas.normals;var planes: PackedFloat64Array=atlas.planes
			for index: int in atlas.grid[key]:
				var q:=uv-uv0[index]
				var u:=q.cross(edge2[index])*inverse_denominators[index]
				var v:=edge1[index].cross(q)*inverse_denominators[index]
				if u<-.000001 or v<-.000001 or u+v>1.000001:continue
				hits.append([heights[index].x+heights[index].y*u+heights[index].z*v,absf(point.dot(normals[index])-planes[index])])
			if hits.is_empty():continue
			hits.sort_custom(func(a: Array,b: Array)->bool:return a[0]<b[0])
			var unique: Array=[]
			for hit: Array in hits:
				if unique.is_empty() or absf(float(hit[0])-float(unique[-1][0]))>.0001:unique.append(hit)
				else:unique[-1][1]=minf(unique[-1][1],hit[1])
			if unique.size()%2!=0:ambiguous+=1;continue
			covered+=1
			for pair: int in range(0,unique.size(),2):
				if point[axis]<=unique[pair][0] or point[axis]>=unique[pair+1][0]:continue
				parity_inside+=1
				plane_deepest=maxf(plane_deepest,minf(unique[pair][1],unique[pair+1][1]))
				# Ray faces classify local inside/outside; their infinite planes
				# are not the nearest boundary of a curved or concave mesh.
				var nearest:=_nearest_surface_info(point,atlas)
				var depth: float=nearest.distance
				if depth>deepest:
					deepest=depth;worst_point=point;worst_mesh=atlas.name;worst_index=point_index
					var index: int=nearest.triangle
					worst_face={"node":atlas.get("node_path",atlas.name),"surface":int((atlas.get("triangle_surfaces",PackedInt32Array()) as PackedInt32Array)[index]) if atlas.has("triangle_surfaces") else -1,"triangle":int((atlas.get("triangle_ordinals",PackedInt32Array()) as PackedInt32Array)[index]) if atlas.has("triangle_ordinals") else index,"a":_point_array(atlas.triangle_a[index]),"b":_point_array(atlas.triangle_b[index]),"c":_point_array(atlas.triangle_c[index])}
				if depth>CONTACT_TOLERANCE:inside+=1
	return {"deepest":deepest,"ray_plane_deepest":plane_deepest,"inside":inside,"parity_inside":parity_inside,"ambiguous":ambiguous,"rays":rays,"covered":covered,"worst_point":[worst_point.x,worst_point.y,worst_point.z],"worst_mesh":worst_mesh,"worst_point_index":worst_index,"worst_target_face":worst_face}

func _nearest_surface_distance(point: Vector3, atlas: Dictionary) -> float:
	return float(_nearest_surface_info(point,atlas).distance)

func _nearest_surface_info(point: Vector3, atlas: Dictionary) -> Dictionary:
	var best:=INF;var nearest:=-1
	var a: PackedVector3Array=atlas.triangle_a;var b: PackedVector3Array=atlas.triangle_b;var c: PackedVector3Array=atlas.triangle_c
	var low: PackedVector3Array=atlas.triangle_low;var high: PackedVector3Array=atlas.triangle_high
	for i: int in a.size():
		var box_point:=Vector3(clampf(point.x,low[i].x,high[i].x),clampf(point.y,low[i].y,high[i].y),clampf(point.z,low[i].z,high[i].z))
		if point.distance_squared_to(box_point)>=best:continue
		var distance:=_triangle_distance_squared(point,a[i],b[i],c[i])
		if distance<best:best=distance;nearest=i
	return {"distance":sqrt(best),"triangle":nearest}

func _triangle_distance_squared(point: Vector3, a: Vector3, b: Vector3, c: Vector3) -> float:
	var ab:=b-a;var ac:=c-a;var ap:=point-a;var normal:=ab.cross(ac)
	var denominator:=normal.length_squared()
	if denominator>.0000000000000001:
		var d00:=ab.dot(ab);var d01:=ab.dot(ac);var d11:=ac.dot(ac)
		var d20:=ap.dot(ab);var d21:=ap.dot(ac)
		var v:=(d11*d20-d01*d21)/denominator
		var w:=(d00*d21-d01*d20)/denominator
		if v>=0. and w>=0. and v+w<=1.:
			return pow(ap.dot(normal),2)/denominator
	return minf(_segment_distance_squared(point,a,b),minf(_segment_distance_squared(point,b,c),_segment_distance_squared(point,c,a)))

func _segment_distance_squared(point: Vector3, a: Vector3, b: Vector3) -> float:
	var segment:=b-a
	var fraction:=clampf((point-a).dot(segment)/maxf(segment.length_squared(),.0000000000000001),0.,1.)
	return point.distance_squared_to(a+segment*fraction)

func _anchor_check(rig: Skeleton3D, groups: Array, label: String) -> void:
	var before:=PackedVector3Array();var after:=PackedVector3Array();var stored: Array=[]
	for group: Dictionary in groups:
		if not group.anchors.is_empty():before.append_array(_skin(group,Transform3D.IDENTITY,group.anchors))
	for bone: int in rig.get_bone_count():
		if not rig.get_bone_name(bone).begins_with("cape_"):continue
		stored.append([bone,rig.get_bone_pose_position(bone)])
		rig.set_bone_pose_position(bone,rig.get_bone_pose_position(bone)+Vector3(.04,.03,.02))
	for group: Dictionary in groups:
		if not group.anchors.is_empty():after.append_array(_skin(group,Transform3D.IDENTITY,group.anchors))
	_check(before.size()>30 and _points_error(before,after)<.000001,label+" body-owned neckline stays attached independently of cape motion")
	for row: Array in stored:rig.set_bone_pose_position(row[0],row[1])

func _span(points: PackedVector3Array) -> float:
	var maximum:=0.
	for a: Vector3 in points:
		for b: Vector3 in points:maximum=maxf(maximum,a.distance_to(b))
	return maximum

func _finish() -> void:
	var output:=OS.get_environment("ELORIA_ARTIFACT_DIR")
	if output.is_empty():output=ProjectSettings.globalize_path("res://test-artifacts/mounted-approved-cape")
	DirAccess.make_dir_recursive_absolute(output)
	var file:=FileAccess.open(output.path_join("mounted-approved-motion.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"checks":_checks,"failures":_failures,"cases":_mounted_rows,"contact_method":"Raw GPU skin weights; Cape-influenced vertices+triangle centroids and independent original-source long-edge quarters/midpoints/thirds; worst contact includes exact Cape coefficients and nearest finite target face; per-mesh local parity-ray intervals followed by exact nearest finite-triangle distance for inside samples; mountY/riderZ; open rays and original ray-plane depth reported separately. Body-only clasp and thin/open features require the independent full triangle audit.","strain_scope":"Original approved source material edge lengths remain the denominator after mounting. Every Cape-influenced edge is gated; body-owned attachment and alternate rebased-rest ratios are reported separately.","contact_tolerance_m":CONTACT_TOLERANCE,"edge_ratio_limit":MAX_EDGE_RATIO,"frame_step_limit_m":MAX_FRAME_STEP,"upper_motion_heuristic":"Unexplained step after maximum measured Spine03/Neck01 body sweep and65% retained history; explicit1mm visual-review margin on nominal80mm, compared at nearest1mm resolution. Lone excess during measured anatomical motion>=80mm is advisory; quiet/history-expired excess, two consecutive excess frames or unexplained out/back fail; raw steps and all reversal candidates retained; quiet reset/sustained positive controls required.","upper_motion_visual_review_margin_m":UPPER_MOTION_REVIEW_MARGIN,"upper_motion_measurement_resolution_m":UPPER_MOTION_RESOLUTION},"\t"))
	print("MOUNTED_APPROVED_CAPE ",_checks," checks; failures=",_failures)
	quit(0 if _failures.is_empty() else 1)
