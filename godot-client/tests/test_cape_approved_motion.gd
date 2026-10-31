extends SceneTree
## Actual actor/equipment integration for the visually approved cape fit.
## Legacy Verlet tests remain separate; authored cages need not keep link lengths.

const STEP := 1.0 / 60.0
const CATALOG := "res://data/actors/cape_motion/catalog.json"
const CAPE_PREFIX := "EquipmentSkin_2_"
var _checks := 0
var _failures: Array[String] = []
var _rows: Array = []
var _models: Dictionary
var _equipment: Dictionary
var _next_id := 9760
var _source_body_rests: Dictionary = {}

func _init() -> void:
	call_deferred("_run")

func _check(ok: bool, message: String) -> void:
	_checks += 1
	if not ok:
		_failures.append(message)
		push_error("approved cape: " + message)

func _json(path: String) -> Dictionary:
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return value as Dictionary if value is Dictionary else {}

func _run() -> void:
	var catalog := _json(CATALOG)
	_check(not catalog.is_empty(), "portable approved-motion catalog is installed")
	if catalog.is_empty():
		_finish();return
	var names: Array = catalog.get("bones", [])
	_check(names.size() == 17, "approved fit retains twelve cape and five body bind names")
	_models = _json("res://data/actors/models.json").get("models", {})
	_equipment = _json("res://data/actors/equipment.json")
	var human: Dictionary = {}
	for row: Dictionary in _json("res://data/actors/rl_head_archetypes.json").get("archetypes", []):
		var sex := str(row.get("sex", ""))
		if human.has(sex):continue
		var appearance: Dictionary = (row.get("appearance_pc3", {}) as Dictionary).duplicate(true)
		# This fixture checks the current Human head/body fit without bringing
		# unrelated hairstyle texture imports into the cape regression.
		appearance["facial_hair"] = 0
		appearance["rl_head"] = {"preset":str(row.get("id", "")), "hair":"none", "beard":"none"}
		human[sex] = appearance
	for sex: String in ["male", "female"]:
		for appearance_kind: String in ["luminous", "human"]:
			for torso: int in [0, 184]:
				var app: Dictionary = human.get(sex, {}) if appearance_kind == "human" else {}
				await _reference_case("luminous_" + sex, torso, app, appearance_kind)
	for rig: String in ["orun_male", "orun_female", "ssarathi_male", "ssarathi_female"]:
		await _guard_case(rig)
	await _lifecycle_case()
	_finish()

func _spawn(rig: String, torso: int, appearance: Dictionary = {}) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	_next_id += 1
	var config: Dictionary = _models.get(rig, {})
	if not _source_body_rests.has(rig):
		# Read the native asset before actor construction, so an accidental
		# canonical-body rest edit during cape installation is observable.
		var source := GlbSceneCache.instantiate(str(config.get("scene", "")))
		var skeletons := source.find_children("*", "Skeleton3D", true, false) if source != null else []
		_check(skeletons.size()==1, rig+" native baseline has one canonical skeleton")
		_source_body_rests[rig] = _body_poses(skeletons[0] as Skeleton3D,true) if skeletons.size()==1 else []
		if source != null:source.free()
	var gear := {"2":5}
	if torso > 0:gear.merge({"0":114,"1":106,"4":171,"5":torso,"6":192})
	var errors := actor.configure({"actor_id":_next_id,"x":0,"y":0,"rotation":0,"kind":1,
		"name":"cape-qualified-test","appearance":appearance,"equipment_visuals":gear},
		CoordinateAdapter.new({"walkingHeight":0.0}), config,
		_json(str(config.get("animationMap", ""))), _equipment)
	_check(errors.is_empty(), rig + " configures actual equipped actor: " + str(errors))
	_check(_transform_error(_source_body_rests.get(rig,[]),_body_poses(actor.get_skeleton(),true))<0.000001,
		rig+" cape integration preserves native canonical body rests")
	actor.set_process(false);actor.set_physics_process(false)
	actor.apply_render_quality(ActorRenderQuality.Quality.HIGH, false)
	var cloth := actor.get_skeleton().get_node_or_null("CapeCloth") as SkeletonModifier3D
	_check(cloth != null and cloth.has_method("approved_motion_stats"), rig + " has approved cape layer")
	if cloth != null:cloth.active = false
	return actor

func _stats(actor: ReplicatedActor3D) -> Dictionary:
	var cloth := actor.get_skeleton().get_node_or_null("CapeCloth")
	if cloth == null or not cloth.has_method("approved_motion_stats"):return {}
	return cloth.call("approved_motion_stats") as Dictionary

func _fallback(stats: Dictionary) -> bool:
	var value: Variant = stats.get("fallback", false)
	if value is String or value is StringName:return str(value) not in ["", "none", "false"]
	return bool(value)

func _body_poses(rig: Skeleton3D, rests := false) -> Array:
	var result: Array = []
	for i: int in rig.get_bone_count():
		if rig.get_bone_name(i).begins_with("cape_"):continue
		result.append(rig.get_bone_global_rest(i) if rests else rig.get_bone_global_pose(i))
	return result

func _transform_error(a: Array, b: Array) -> float:
	if a.size() != b.size():return INF
	var worst := 0.0
	for i: int in a.size():
		var x: Transform3D = a[i];var y: Transform3D = b[i]
		worst = maxf(worst, x.origin.distance_to(y.origin))
		for axis: int in 3:worst = maxf(worst, x.basis[axis].distance_to(y.basis[axis]))
	return worst

func _sample(actor: ReplicatedActor3D, action: StringName, time: float, rate := 1.0, restart := false) -> Dictionary:
	actor.play_action(action, restart)
	var player := actor.animation_player
	player.speed_scale = rate
	var cloth := actor.get_skeleton().get_node("CapeCloth")
	cloth.set("active", false)
	# Let the body and cape crossfades finish while preserving this exact clip phase.
	for i: int in 32:
		player.seek(time, true);player.advance(STEP);player.seek(time, true);player.pause()
		var before := _body_poses(actor.get_skeleton())
		cloth.call("_process_modification_with_delta", STEP)
		if i == 31:
			_check(_transform_error(before, _body_poses(actor.get_skeleton())) < 0.000002,
				"cape layer leaves all canonical body poses unchanged for " + str(action))
	return _stats(actor)

func _cape_meshes(rig: Skeleton3D) -> Array[MeshInstance3D]:
	var result: Array[MeshInstance3D] = []
	for node: Node in rig.get_children():
		var mesh := node as MeshInstance3D
		if mesh != null and str(mesh.name).begins_with(CAPE_PREFIX) and mesh.mesh != null and mesh.skin != null:
			result.append(mesh)
	return result

func _cape_surface_contract(rig: Skeleton3D) -> Dictionary:
	var materials: Array = [];var weights: Array = [];var bones: Array = []
	for mesh: MeshInstance3D in _cape_meshes(rig):
		for surface: int in mesh.mesh.get_surface_count():
			var arrays := mesh.mesh.surface_get_arrays(surface)
			weights.append((arrays[Mesh.ARRAY_WEIGHTS] as PackedFloat32Array).to_byte_array())
			bones.append((arrays[Mesh.ARRAY_BONES] as PackedInt32Array).to_byte_array())
			var material := mesh.get_active_material(surface) as BaseMaterial3D
			var value: Dictionary = {"surface":mesh.mesh.surface_get_name(surface),"present":material!=null}
			if material != null:
				value.merge({"name":material.resource_name,"albedo":material.albedo_color,
					"texture":material.albedo_texture,"roughness":material.roughness,
					"metallic":material.metallic,"specular":material.metallic_specular,
					"normal_enabled":material.normal_enabled,"normal":material.normal_texture,
					"normal_scale":material.normal_scale,"emission_enabled":material.emission_enabled,
					"emission":material.emission,"emission_texture":material.emission_texture,
					"transparency":material.transparency,"cull":material.cull_mode})
			materials.append(value)
	return {"materials":materials,"weights":weights,"bones":bones}

func _samples(rig: Skeleton3D) -> Dictionary:
	var groups: Array = []
	var anchor_count := 0
	var free_count := 0
	for mesh: MeshInstance3D in _cape_meshes(rig):
		var bind_bones := PackedInt32Array()
		var bind_poses: Array[Transform3D] = []
		for bind: int in mesh.skin.get_bind_count():
			var bone := rig.find_bone(mesh.skin.get_bind_name(bind))
			if bone < 0:bone = mesh.skin.get_bind_bone(bind)
			_check(bone >= 0 and bone < rig.get_bone_count(), "cape bind resolves by canonical name")
			bind_bones.append(bone);bind_poses.append(mesh.skin.get_bind_pose(bind))
		for surface: int in mesh.mesh.get_surface_count():
			var arrays := mesh.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			var slots := bones.size() / maxi(1, vertices.size())
			_check(slots == 8 and weights.size() == bones.size(), "actual engine cape surface retains eight influence slots")
			var anchors := PackedInt32Array();var free := PackedInt32Array()
			var finite_weights := true;var normalized := true
			for v: int in vertices.size():
				var total := 0.0;var cape_share := 0.0
				for slot: int in slots:
					var at := v * slots + slot
					finite_weights = finite_weights and is_finite(weights[at]) and weights[at] >= 0.0
					total += weights[at]
					if weights[at] > 0.0 and bones[at] < bind_bones.size() and bind_bones[bones[at]] >= 0:
						if rig.get_bone_name(bind_bones[bones[at]]).begins_with("cape_"):cape_share += weights[at]
				normalized = normalized and absf(total - 1.0) < 0.001
				if cape_share <= 0.000001 and v % 8 == 0:anchors.append(v)
				if cape_share >= 0.99 and v % 24 == 0:free.append(v)
			_check(finite_weights and normalized, "cape weights are finite and normalized")
			anchor_count += anchors.size();free_count += free.size()
			groups.append({"vertices":vertices,"bones":bones,"weights":weights,"slots":slots,
				"bind_bones":bind_bones,"bind_poses":bind_poses,"anchors":anchors,"free":free})
	_check(anchor_count > 30, "body-owned neckline/attachment samples are retained")
	_check(free_count > 30, "free cloth samples are retained")
	return {"groups":groups,"anchors":anchor_count,"free":free_count}

func _posed(rig: Skeleton3D, samples: Dictionary, which: String, rest := false) -> PackedVector3Array:
	var out := PackedVector3Array()
	for group: Dictionary in samples.groups:
		var transforms: Array[Transform3D] = []
		var bind_bones: PackedInt32Array = group.bind_bones
		var bind_poses: Array = group.bind_poses
		for bind: int in bind_bones.size():
			transforms.append((rig.get_bone_global_rest(bind_bones[bind]) if rest else rig.get_bone_global_pose(bind_bones[bind])) * bind_poses[bind])
		var vertices: PackedVector3Array = group.vertices
		var bones: PackedInt32Array = group.bones
		var weights: PackedFloat32Array = group.weights
		for vertex: int in group[which]:
			var p := Vector3.ZERO;var total := 0.0
			for slot: int in group.slots:
				var at: int = vertex * int(group.slots) + slot
				if weights[at] <= 0.0:continue
				p += transforms[bones[at]] * vertices[vertex] * weights[at];total += weights[at]
			out.append(p / maxf(total, 0.001))
	return out

func _points_error(a: PackedVector3Array, b: PackedVector3Array) -> float:
	if a.size() != b.size():return INF
	var worst := 0.0
	for i: int in a.size():worst = maxf(worst, a[i].distance_to(b[i]))
	return worst

func _fit_surface_arrays(samples: Dictionary, profile: String, label: String) -> void:
	# Read the portable vertex payload independently of CapeApprovedData.
	# This catches later garment finishing accidentally refitting the cape.
	var fit: Dictionary = _json(CATALOG).get("fits",{}).get(profile,{})
	var bytes := FileAccess.get_file_as_bytes(CATALOG.get_base_dir().path_join(str(fit.get("file",""))))
	var surfaces: Array = fit.get("surfaces",[])
	_check(surfaces.size()==samples.groups.size(),label+" retains approved cape surface count")
	for surface: int in mini(surfaces.size(),samples.groups.size()):
		var descriptor: Dictionary = surfaces[surface].get("positions",{})
		var offset := int(descriptor.get("offset",0))
		var values := bytes.slice(offset,offset+int(descriptor.get("count",0))*4).to_float32_array()
		var expected := PackedVector3Array()
		for vertex: int in values.size()/3:expected.append(Vector3(values[vertex*3],values[vertex*3+1],values[vertex*3+2]))
		_check(_points_error(expected,samples.groups[surface].vertices)<0.000002,
			label+" surface"+str(surface)+" keeps approved vertices through actor finishing")

func _anchor_ownership(rig: Skeleton3D, samples: Dictionary, label: String) -> void:
	var before := _posed(rig, samples, "anchors")
	var stored: Array = []
	for bone: int in rig.get_bone_count():
		if not rig.get_bone_name(bone).begins_with("cape_"):continue
		stored.append([bone,rig.get_bone_pose_position(bone),rig.get_bone_pose_rotation(bone)])
		rig.set_bone_pose_position(bone,rig.get_bone_pose_position(bone)+Vector3(.03,.02,.04))
	var after := _posed(rig, samples, "anchors")
	_check(_points_error(before,after)<0.000001,label+" neckline cannot detach when cape controls move")
	for row: Array in stored:
		rig.set_bone_pose_position(row[0],row[1]);rig.set_bone_pose_rotation(row[0],row[2])

func _reference_case(key: String, torso: int, appearance: Dictionary, kind: String) -> void:
	var actor := _spawn(key, torso, appearance)
	var rig := actor.get_skeleton();var label := "%s/%s/%d" % [kind,key,torso]
	if not rig.get_node("CapeCloth").has_method("approved_motion_stats"):
		actor.free();return
	var body_rests := _body_poses(rig,true)
	_check(body_rests.size()==65 and rig.get_bone_count()==77,label+" retains65body and12cape bones")
	var stats := _sample(actor,&"idle",.4)
	_check(bool(stats.get("enabled",false)),label+" enables approved playback")
	_check(str(stats.get("profile","")) == ("armour" if torso>0 else "wardrobe"),label+" selects correct fit profile")
	var samples := _samples(rig)
	_fit_surface_arrays(samples,"armour" if torso>0 else "wardrobe",label)
	_anchor_ownership(rig,samples,label)
	var metrics: Dictionary = {}
	for action: StringName in [&"walk",&"run"]:
		actor.play_action(action,true)
		var clip := actor.resolver.clip_for_action(action)
		var duration := actor.animation_player.get_animation(clip).length
		# Finish entry-only hand clearance on the native body clock before
		# comparing steady loop endpoints. Holding phase zero cannot age it.
		for cycle: int in 2:
			_sample(actor,action,duration*.9)
			_sample(actor,action,0.0)
		var minimum := INF;var maximum := -INF;var first := PackedVector3Array();var wrap := PackedVector3Array()
		var anchor := rig.find_bone("spine_03");var inv_rest := rig.get_bone_global_rest(anchor).affine_inverse()
		var rest_points := _posed(rig,samples,"free",true)
		for phase: int in 9:
			stats = _sample(actor,action,duration*float(phase)/8.0)
			_check(not _fallback(stats),label+" authored "+str(action)+" stays out of fallback")
			var points := _posed(rig,samples,"free")
			var inverse := (rig.get_bone_global_pose(anchor)*inv_rest).affine_inverse()
			var rear := 0.0;var count := 0;var finite_pose := true;var normalized := PackedVector3Array()
			for i: int in points.size():
				finite_pose = finite_pose and points[i].is_finite()
				normalized.append(inverse*points[i])
				if rest_points[i].y > .65:continue
				rear -= (inverse*points[i]-rest_points[i]).z;count+=1
			rear/=maxi(count,1);minimum=minf(minimum,rear);maximum=maxf(maximum,rear)
			_check(finite_pose and count>0,label+" finite sampled "+str(action)+" hem")
			if phase==0:first=normalized
			if phase==8:wrap=normalized
		metrics[str(action)]={"rear_min_m":minimum,"rear_max_m":maximum,"rear_cycle_range_m":maximum-minimum,"wrap_error_m":_points_error(first,wrap)}
		_check(maximum-minimum > (.015 if action==&"walk" else .035),label+" "+str(action)+" retains visible cloth rhythm")
		_check(maximum > (.025 if action==&"walk" else .08),label+" "+str(action)+" billows behind its resting sheet")
		_check(_points_error(first,wrap)<.003,label+" "+str(action)+" closes its native clip loop")
		var t := duration*.37
		_sample(actor,action,t,.35);var slow := _posed(rig,samples,"free")
		_sample(actor,action,t,3.5);var fast := _posed(rig,samples,"free")
		_check(_points_error(slow,fast)<.003,label+" "+str(action)+" samples native clip phase at different playback rates")
	for action: StringName in [&"attack_primary",&"attack_secondary"]:
		stats = _sample(actor,action,.3,1.0,true)
		_check(not _fallback(stats),label+" authored "+str(action)+" plays")
		stats = _sample(actor,action,.3,1.0,true)
		_check(not _fallback(stats),label+" repeated attack alias resolves canonical cape clip")
	_sample(actor,&"idle",.4)
	_anchor_ownership(rig,samples,label+" after attacks")
	_check(_transform_error(body_rests,_body_poses(rig,true))<.000001,label+" leaves canonical body rests unchanged")
	_rows.append({"case":label,"stats":_stats(actor),"samples":{"anchors":samples.anchors,"free":samples.free},"metrics":metrics})
	actor.queue_free();await process_frame

func _guard_case(key: String) -> void:
	var actor := _spawn(key,184)
	for action: StringName in [&"idle",&"walk",&"run"]:
		var stats := _sample(actor,action,.3)
		_check(bool(stats.get("enabled",false)),key+" has approved geometry/motion with body guard")
		var finite_pose := true
		for p: Vector3 in _posed(actor.get_skeleton(),_samples(actor.get_skeleton()),"free"):
			finite_pose = finite_pose and p.is_finite() and p.length()<4.0
		_check(finite_pose,key+" guarded pose stays finite/bounded")
	actor.queue_free();await process_frame

func _lifecycle_case() -> void:
	var actor := _spawn("luminous_male",0)
	_sample(actor,&"walk",.4)
	actor.apply_equipment_visuals({2:5,5:184,4:171,6:192})
	_check(str(_sample(actor,&"idle",.4).get("profile",""))=="armour","equipping torso updates cape fit")
	actor.apply_equipment_visuals({2:5})
	_check(str(_sample(actor,&"idle",.4).get("profile",""))=="wardrobe","removing torso restores bare fit")
	actor.apply_equipment_visuals({})
	_check(not actor.wears_cape_cloth(),"removing cape stops its layer")
	actor.apply_equipment_visuals({2:140})
	_check(bool(_sample(actor,&"idle",.4).get("enabled",false)),"tinted/emblem cape retains approved generic geometry")
	actor.apply_render_quality(ActorRenderQuality.Quality.LOW,false)
	_check(not actor.cape_cloth_should_simulate(),"nonlocal low quality disables per-frame cape work")
	var rig := actor.get_skeleton();var before := _body_poses(rig);var held := []
	for bone: int in rig.get_bone_count():held.append(rig.get_bone_global_pose(bone))
	_check(not actor._cape_cloth.active,"nonlocal low quality disables automatic modifier")
	await process_frame;await process_frame
	var after := []
	for bone: int in rig.get_bone_count():after.append(rig.get_bone_global_pose(bone))
	_check(_transform_error(before,_body_poses(rig))<.000001,"disabled cape does not alter body pose")
	_check(_transform_error(held,after)<.000001,"disabled quality holds one cape pose without frame updates")
	actor.apply_render_quality(ActorRenderQuality.Quality.HIGH,false)
	_check(actor.cape_cloth_should_simulate(),"quality wake restores cape permission")
	_sample(actor,&"idle",.4)
	var unsupported := &"cast"
	if actor.resolver.action_to_clip.has(String(unsupported)):
		var stats := _sample(actor,unsupported,.3)
		_check(_fallback(stats),"unreviewed action retains finite legacy fallback")
	var original := _cape_surface_contract(rig)
	_check(original.materials.size()==3,"styled cape has three material surfaces before mounting")
	actor.set_mount_state({"mode":"mounted","mount_id":"moor_pony","gait":"walk","step_us":600000},_models)
	_check(is_instance_valid(actor._mount_visual),"mount presentation configures")
	_check(not actor._cape_cloth.active,"mounted owner suppresses automatic cape pass")
	_check(not bool(_stats(actor).get("enabled",true)),"mounted cape selects the legacy mesh and disables approved playback")
	_check(_cape_surface_contract(rig).materials==original.materials,"mounting preserves the styled cape's three material slots")
	if is_instance_valid(actor._mount_visual):
		actor._mount_visual.call("_process",STEP)
		_check(_fallback(_stats(actor)),"mounted mode suspends authored action playback")
	actor.set_mount_state({},_models)
	var restored := _sample(actor,&"idle",.4)
	_check(bool(restored.get("enabled",false)),"dismount restores approved idle")
	_check(str(restored.get("profile",""))=="wardrobe","dismount restores the correct approved fit profile")
	var contract := _cape_surface_contract(rig)
	_check(contract.materials==original.materials,"dismount preserves all three styled cape material slots")
	_check(contract.weights==original.weights and contract.bones==original.bones,"dismount restores approved eight-slot weights and bone indices exactly")
	actor.queue_free();await process_frame

func _finish() -> void:
	var folder := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if folder.is_empty():folder=ProjectSettings.globalize_path("res://test-artifacts/cape-approved-motion")
	DirAccess.make_dir_recursive_absolute(folder)
	var out := FileAccess.open(folder.path_join("approved-motion.json"),FileAccess.WRITE)
	out.store_string(JSON.stringify({"checks":_checks,"failures":_failures,"cases":_rows},"\t"))
	print("APPROVED_CAPE_MOTION ",_checks," checks; failures=",_failures)
	quit(0 if _failures.is_empty() else 1)
