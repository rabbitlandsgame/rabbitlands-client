extends SceneTree
## Native small facial partitions must stay renderable when a living actor
## bends below its resting AABB. No geometry, materials or poses are replaced.
## At High a Human draws the RL head instead of the body's scalp, eyes and
## brows (hidden, still present and bounded): its head, beard and hair meshes
## must carry the same animated-head envelope.
var checks := 0
var failures := 0
func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ",message)
	else: failures += 1;push_error(message)
func run() -> void:
	create_timer(75).timeout.connect(func()->void:push_error("Animated head bounds timed out");quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	var models: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var model: Dictionary=models.models[models.actorTypes["308"]]
	var source_hash:=FileAccess.get_sha256(model.scene)
	var actor:=ReplicatedActor3D.new();root.add_child(actor)
	var dto:={"actor_id":308,"actor_type":308,"name":"Dock foreman","kind":2,"x":0,"y":0,"rotation":0,
		"health":20,"max_health":20,"appearance":{},"equipment_visuals":{}}
	var errors:=actor.configure(dto,CoordinateAdapter.new({"walkingHeight":0}),model,
		JSON.parse_string(FileAccess.get_file_as_string(model.animationMap)),JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json")))
	expect(errors.is_empty(),"the real bald foreman configures from his approved native model and animation library")
	var native:=actor.get_node("NativeModel") as Node3D
	var skeleton:=actor.get_skeleton()
	var head:=skeleton.find_bone("Head")
	expect(head>=0,"the foreman's bound native Head drives the proof")
	actor.play_action(&"defend")
	var clip_name:=actor.resolver.clip_for_action(&"defend")
	var clip:=actor.animation_player.get_animation(clip_name)
	actor.animation_player.callback_mode_process=AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var movement:=0.0
	var bent_time:=0.0
	for fraction:float in [0.0,.25,.5,.75,.99]:
		actor.animation_player.play(clip_name,0)
		actor.animation_player.seek(clip.length*fraction,true);actor.animation_player.advance(0)
		skeleton.force_update_all_bone_transforms()
		var displaced:=skeleton.get_bone_global_pose(head).origin.distance_to(skeleton.get_bone_global_rest(head).origin)
		if displaced>movement:movement=displaced;bent_time=clip.length*fraction
	actor.animation_player.seek(bent_time,true);actor.animation_player.advance(0)
	skeleton.force_update_all_bone_transforms()
	expect(movement>.2,"the actual defend clip bends the head away from its standing bounds")
	var rl:=actor.rl_head()!=null
	expect(rl==(actor.render_quality()==ActorRenderQuality.Quality.HIGH and not ReplicatedActor3D.rl_heads_classic()),
		"the foreman draws the RL head exactly at High")
	if rl:
		var rl_meshes:=actor.rl_head().all_meshes()
		expect(not rl_meshes.is_empty(),"the RL head has meshes")
		for mesh:MeshInstance3D in rl_meshes:
			expect(mesh.skin!=null and mesh.extra_cull_margin>movement+.1,"RL "+str(mesh.name)+" bounds cover the real bent-head displacement")
	var face:Dictionary={}
	for name:String in ["scalp","eyes","eyebrows"]:
		var mesh:=native.find_child(name,true,false) as MeshInstance3D
		expect(mesh!=null and mesh.skin!=null and mesh.visible!=rl,"the actual "+name+" partition remains present and skinned"+(" (hidden under the RL head)" if rl else ""))
		if mesh!=null:
			face[name]=mesh
			expect(mesh.extra_cull_margin>movement+.1,"the "+name+" bounds cover the real bent-head displacement")
	var body:=native.find_child("body",true,false) as MeshInstance3D
	body.extra_cull_margin=.125
	var scalp:=face.scalp as MeshInstance3D
	scalp.extra_cull_margin=4
	var source_mesh:Mesh=scalp.mesh
	var source_skin:Skin=scalp.skin
	var source_material:Material=scalp.get_active_material(0)
	var source_bounds:=scalp.get_aabb()
	var source_layers:=scalp.layers
	var pose:=skeleton.get_bone_global_pose(head)
	var world:=actor.global_transform
	var server:=actor.server_target
	actor.call("_expand_animated_face_bounds",native)
	actor.call("_expand_animated_face_bounds",native)
	expect(scalp.extra_cull_margin==4,"larger authored or existing facial margins are never reduced or compounded")
	expect(body.extra_cull_margin==.125,"the large body mesh keeps its existing culling policy")
	expect(scalp.mesh==source_mesh and scalp.skin==source_skin and scalp.get_active_material(0)==source_material \
		and scalp.get_aabb()==source_bounds and scalp.layers==source_layers and scalp.visible!=rl,"bound expansion preserves native geometry, skin, material, visibility and render layers")
	expect(skeleton.get_bone_global_pose(head)==pose and actor.global_transform==world and actor.server_target==server,"culling bounds never pose or move the authoritative actor")
	var non_skinned:=MeshInstance3D.new();non_skinned.name="scalp";native.add_child(non_skinned)
	actor.call("_expand_animated_face_bounds",native)
	expect(non_skinned.extra_cull_margin==0,"an unrelated unskinned node with the same name is untouched")
	non_skinned.free()
	actor.apply_appearance_variants({"hair":106})
	var hair_count:=0
	for child:Node in skeleton.get_children():
		if not str(child.name).begins_with("AppearanceHair_"):continue
		for node:Node in child.find_children("*","MeshInstance3D",true,false):
			var mesh:=node as MeshInstance3D
			if mesh.skin==null:continue
			hair_count+=1
			expect(mesh.extra_cull_margin>movement+.1,"a real fitted hairstyle receives the same animated head envelope")
	expect(hair_count>0,"the short brown native hairstyle is actually instantiated for the hair regression")
	actor.apply_render_quality(ActorRenderQuality.Quality.LOW)
	actor.apply_render_quality(ActorRenderQuality.Quality.HIGH)
	expect(scalp.extra_cull_margin==4,"graphics-quality changes preserve the safe facial bounds")
	actor.apply_appearance_variants({"hair":0})
	rl=actor.rl_head()!=null
	expect(scalp.visible!=rl and scalp.extra_cull_margin==4,"returning to bald appearance preserves the closed scalp and its bounds")
	if rl:
		var cranium:=actor.rl_head().mesh_nodes()["head"] as Array
		expect(not cranium.is_empty() and (cranium[0][0] as MeshInstance3D).visible,"bald under the RL head shows the RL cranium")
	expect(FileAccess.get_sha256(model.scene)==source_hash,"the approved source model remains byte-identical")
	actor.queue_free()
	await process_frame
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("animated head culling: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
