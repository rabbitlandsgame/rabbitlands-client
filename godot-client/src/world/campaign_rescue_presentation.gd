extends Node3D
## Reversible dressing for an owned rescue. Imported geometry and server actors
## stay authoritative; this node never completes work or changes an actor body.
const FencePool := preload("res://src/world/external_mesh_pool.gd")
const Dissolve := preload("res://src/actors/creature_dissolve.gd")
const FENCE_ID := "11ec54ffb8d8eb66b5a8de1e0bdb3da278b75459c880a07fc46acfcf1e9f4c65"
const FENCE_PATH := "res://../eloria-assets/maps/_shared/meshes/"+FENCE_ID+".glb"
const LANTERN_TILES := [[49.6,29.5],[60.4,29.5],[43,49],[67.5,54],[60,62.5],[24.5,60],[88,61],[73,70],[46.5,86],[63.5,82]]

var cage: Node3D
var gate: Node3D
var panels: Array[MeshInstance3D] = []
var lamps: Array[OmniLight3D] = []
var points: Dictionary = {}
var labels: Dictionary = {}
var _snapshot: Dictionary = {}
var _identity := ""
var _map := ""
var _geometry := ""
var _sample: Callable
var _adapter: CoordinateAdapter
var _world: World3D
var _readouts_visible := true
var _gate_origin := Vector3.ZERO
var _accepted_gate := 0.0
var _scene_id := ""
var _scene_elapsed := 0.0
var _scene_replaying := false
var _effects: Dictionary = {}
var _dissolves: Dictionary = {}
var _dissolve_targets: Dictionary = {}
var _dissolve_progress: Dictionary = {}
var _completed_burns: Array[Dictionary] = []
var _clip_leases: Dictionary = {}
var _bound_actors: Dictionary = {}
var _downed_mother: WeakRef
var _scales: Dictionary = {}
var _aliases: Dictionary = {}
var _fade_layer: CanvasLayer
var _fade: ColorRect
var _handoff_token := ""
var _handoff_deadline_ms := 0
var _expired_handoff_token := ""
var _saved_environment: Environment
var _dark_environment: Environment
var _environment_owner: WeakRef
var _environment_binding: WeakRef
var _saved_lights: Dictionary = {}
var _directional_inputs: Array[WeakRef] = []
var _darkness_started := false
var _darkness_requested := false

func apply_snapshot(snapshot: Dictionary, adapter: CoordinateAdapter, current_map: String,
		surface_sample: Callable) -> void:
	var map := EloriaProtocol.map_id_from_reference(current_map)
	if not is_inside_tree() or not bool(snapshot.get("active",false)) or str(snapshot.get("kind",""))!="rescue" \
			or str(snapshot.get("run_id","")).is_empty() or adapter==null or not surface_sample.is_valid() \
			or map not in ["landfall","landfall_insides"] \
			or EloriaProtocol.map_id_from_reference(str(snapshot.get("map","")))!=map:
		clear()
		return
	var identity := str(snapshot.run_id)+":"+map
	var geometry := JSON.stringify(snapshot.get("anchors",{}))
	if identity!=_identity or _world!=get_world_3d() or geometry!=_geometry:
		clear()
		_identity=identity;_map=map;_geometry=geometry;_world=get_world_3d()
	_adapter=adapter;_sample=surface_sample;_snapshot=snapshot.duplicate(true)
	var stage:=str(snapshot.get("rescue",{}).get("stage",""))
	if stage in ["boss_defeated","daughter_freed","reward","aftermath","complete"] \
			or stage=="boss_confrontation" and not bool(snapshot.get("scene",{}).get("requires_ack",true)):
		_darkness_started=true
	_darkness_requested=_darkness_started
	points.clear()
	for key: String in snapshot.get("anchors",{}):
		var tile: Variant = snapshot.anchors[key]
		if tile is Array and tile.size()==2:
			var at:=_ground(adapter.tile_center(int(tile[0]),int(tile[1])))
			if at.is_finite(): points[key]=at
	if _map=="landfall_insides":
		if not points.has("cage"):
			clear();return
		if not is_instance_valid(cage):
			if not _build_cage(points.cage):return
			_build_lights()
		_accepted_gate=1.0 if bool(snapshot.get("rescue",{}).get("daughter",{}).get("rescued",false)) else 0.0
		if _scene_id.is_empty():_set_gate(_accepted_gate)
		_sync_darkness()
		if labels.has("cage"):
			labels.cage.text="Liora's holding cage · "+("open" if _accepted_gate>0.5 else "locked")
	show()

func _build_cage(at: Vector3) -> bool:
	# Each panel is the unchanged current imported split-rail mesh. The pool
	# resolves its three shipped textures and rejects retired prototype IDs.
	var mesh: Mesh = FencePool.acquire(FENCE_ID,ProjectSettings.globalize_path(FENCE_PATH))
	if mesh==null:return false
	for offset: Vector3 in [Vector3(-2,0,-2),Vector3(2,0,-2),Vector3(-2,0,2),Vector3(2,0,2)]:
		var floor:=_ground(at+offset)
		if not floor.is_finite() or absf(floor.y-at.y)>0.2:return false
	cage=Node3D.new();cage.name="RescueImportedHoldingCage";add_child(cage);cage.global_position=at
	for tier: int in range(2):
		_panel(cage,mesh,Vector3(-2,tier*1.2,0),Vector3(0,PI/2,0))
		_panel(cage,mesh,Vector3(2,tier*1.2,0),Vector3(0,PI/2,0))
		_panel(cage,mesh,Vector3(0,tier*1.2,-2),Vector3.ZERO)
	# Three complete source panels form a slatted roof. Their 1.2m source
	# height becomes roof depth; no source vertex, UV or material is edited.
	for offset: float in [-2.0,-0.6,0.8]:
		_panel(cage,mesh,Vector3(0,2.5,offset),Vector3(PI/2,0,0))
	gate=Node3D.new();gate.name="RescueLiftGate";cage.add_child(gate)
	_gate_origin=Vector3(0,0,2)
	for tier: int in range(2):_panel(gate,mesh,Vector3(0,tier*1.2,0),Vector3.ZERO)
	_set_gate(_accepted_gate)
	var label:=Label3D.new();label.name="CageStatus";label.font_size=36;label.pixel_size=0.008
	label.billboard=BaseMaterial3D.BILLBOARD_ENABLED;label.no_depth_test=false;label.layers=2
	cage.add_child(label);label.position=Vector3(0,3.1,0);labels.cage=label
	set_readouts_visible(_readouts_visible)
	return true

func _panel(parent: Node3D, mesh: Mesh, at: Vector3, rotation_value: Vector3) -> void:
	var part:=MeshInstance3D.new();part.name="ImportedFencePanel";part.mesh=mesh;part.layers=2
	parent.add_child(part);part.position=at;part.rotation=rotation_value;panels.append(part)

func _build_lights() -> void:
	for tile: Array in LANTERN_TILES:
		# These are the already-authored mine lanterns, not invented wall lamps.
		# Source prop coordinates are fractional; preserve their half-tile detail.
		var at:=_adapter.tile_center(int(floor(tile[0])),int(floor(tile[1])))
		at.x+=float(tile[0])-floor(float(tile[0]))-0.5
		at.z-=float(tile[1])-floor(float(tile[1]))-0.5
		at=_ground(at)
		if not at.is_finite():continue
		var lamp:=OmniLight3D.new();lamp.name="ExistingMineLanternLight";add_child(lamp)
		lamp.global_position=at+Vector3.UP*1.9;lamp.light_color=Color("ffd095")
		lamp.light_energy=2.2;lamp.omni_range=11.0;lamp.omni_attenuation=0.7;lamp.shadow_enabled=false
		lamp.visible=_darkness_requested;lamps.append(lamp)

func apply_cinematic(state: Dictionary, actor_nodes: Dictionary) -> void:
	if _identity.is_empty():return
	_update_handoff_fade(state)
	_bound_actors=state.get("actors",{}).duplicate()
	_retire_completed_burns()
	_apply_role_scales(actor_nodes)
	var boss_film:=str(state.get("id",""))=="measure.rescue.boss"
	var replaying:=bool(state.get("replaying",false))
	var closed:=str(state.get("return_reason","")) in ["finished","skipped"]
	if boss_film and not replaying and closed:
		_darkness_started=true # Skip enters the same dark fight as a completed film.
	_darkness_requested=_darkness_started
	if boss_film and replaying and bool(state.get("playing",false)) and not bool(state.get("returning",false)):
		_darkness_requested=false # Reconstruct the taunt before its local blackout.
	for event:Dictionary in state.get("events",[]):
		if str(event.get("type",""))=="darkness":
			_darkness_requested=true
			if not replaying:_darkness_started=true
	_sync_darkness()
	var active:=bool(state.get("playing",false)) and not bool(state.get("returning",false)) \
		and str(state.get("id","")).begins_with("measure.rescue.")
	if bool(state.get("playing",false)):
		_downed_mother=null # The scene now owns its own bound pose.
	else:
		_apply_downed_mother(actor_nodes)
	if not active:
		if bool(state.get("playing",false)) and bool(state.get("returning",false)) \
				and _scene_id=="measure.rescue.shadow" and _scene_replaying:
			_set_fade(0)
			return # Keep its local clone dissolved until replay teardown, then restore.
		_clear_cinematic(_scene_id=="measure.rescue.shadow" and not _scene_replaying)
		return
	var id:=str(state.id);var time:=maxf(0,float(state.get("elapsed",0)))
	if id!=_scene_id or replaying!=_scene_replaying or time<_scene_elapsed-0.01:_clear_cinematic()
	_scene_id=id;_scene_elapsed=time;_scene_replaying=replaying
	var gate_value:=_accepted_gate
	var fade_value:=0.0
	var wanted_effects: Dictionary={};var wanted_dissolves: Dictionary={};var wanted_clips: Dictionary={}
	var events: Array = state.get("events",[])
	for index: int in events.size():
		var event: Dictionary=events[index]
		var start:=float(event.get("at",0));var end:=maxf(start+0.001,float(event.get("until",start+1)))
		if time<start:continue
		if bool(event.get("replay_only",false)) and not replaying:continue
		# CampaignScene has already filtered branch/choice conditions.
		var duration:=maxf(0.001,float(event.get("duration",end-start)))
		var progress:=clampf((time-start)/duration,0,1)
		var key:=str(event.get("id",JSON.stringify(event)))
		match str(event.get("type","")):
			"gate":gate_value=lerpf(float(event.get("from",0)),float(event.get("to",1)),progress)
			"fade":fade_value=lerpf(float(event.get("from",0)),float(event.get("to",1)),progress)
			"native_clip":
				var target:=_actor(str(event.get("actor","")),actor_nodes)
				if target!=null:
					wanted_clips[key]=true
					_apply_native_clip(key,target,event,time)
			"effect":
				if time>end:continue
				wanted_effects[key]=true
				var source:=_actor(str(event.get("source","")),actor_nodes)
				var target:=_actor(str(event.get("target","")),actor_nodes)
				if source==null or target==null:continue
				if not _effects.has(key) or not is_instance_valid(_effects[key]):
					var effect:=WorldEffect3D.new();add_child(effect)
					effect.configure(int(event.get("effect",5)),source.global_position,target.global_position,int(event.get("power",1)))
					effect.bind_actors(source,target);effect.set_process(false);_effects[key]=effect
				var effect:WorldEffect3D=_effects[key]
				effect.elapsed=time-start;effect._process(0.0)
			"dissolve":
				var target:=_actor(str(event.get("actor","goblin_boss")),actor_nodes)
				if target==null:continue
				wanted_dissolves[key]=true
				if not _dissolves.has(key):
					var dissolve:=Dissolve.new();dissolve.begin(target,duration,int(target.get_instance_id()))
					_dissolves[key]=dissolve
					_dissolve_targets[key]=weakref(target)
				_dissolves[key].update(progress)
				_dissolve_progress[key]=progress
	_set_gate(gate_value)
	_set_fade(1.0 if _handoff_deadline_ms>0 else fade_value)
	for key: String in _effects.keys():
		if not wanted_effects.has(key):
			if is_instance_valid(_effects[key]):_effects[key].queue_free()
			_effects.erase(key)
	for key: String in _dissolves.keys():
		if not wanted_dissolves.has(key):
			_dissolves[key].reset();_dissolves.erase(key);_dissolve_targets.erase(key);_dissolve_progress.erase(key)
	for key: String in _clip_leases.keys():
		if not wanted_clips.has(key):_release_native_clip(key)

func _update_handoff_fade(state: Dictionary) -> void:
	_expire_handoff_fade()
	var token:=str(state.get("token",""))
	var id:=str(state.get("id",""))
	var playing:=bool(state.get("playing",false))
	var returning:=bool(state.get("returning",false))
	var reason:=str(state.get("return_reason",""))
	var same_run:=str(state.get("run_id",""))==str(_snapshot.get("run_id",""))
	if _handoff_deadline_ms>0:
		if not reason.is_empty() and reason not in ["finished","skipped"] \
				or playing and not returning and token!=_handoff_token:
			# A newly authenticated entrance film owns its own fade-in. Any
			# other replacement/error relinquishes the local blackout as well.
			_handoff_deadline_ms=0;_handoff_token=""
			_set_fade(0)
	if bool(state.get("handoff_fade",false)) and same_run and not bool(state.get("replaying",false)) \
			and id=="measure.rescue.commitment" and not token.is_empty() and token!=_expired_handoff_token \
			and (returning or not playing) and reason in ["finished","skipped"]:
		if _handoff_deadline_ms==0:
			_handoff_token=token;_handoff_deadline_ms=Time.get_ticks_msec()+12000
		_set_fade(1)

func _expire_handoff_fade() -> void:
	if _handoff_deadline_ms>0 and Time.get_ticks_msec()>=_handoff_deadline_ms:
		_expired_handoff_token=_handoff_token;_handoff_token="";_handoff_deadline_ms=0
		_set_fade(0)

func _process(_delta: float) -> void:
	_expire_handoff_fade()

func _actor(role: String, actor_nodes: Dictionary) -> Node3D:
	var bound:Variant=_bound_actors.get(role)
	if is_instance_valid(bound) and bound is Node3D:return bound as Node3D
	var direct:Variant=actor_nodes.get(role)
	if is_instance_valid(direct) and direct is Node3D:return direct as Node3D
	var identity: Variant=_snapshot.get("actors",{}).get(role)
	if identity==null:return null
	var id:=int(identity)
	var actor: Variant=actor_nodes.get(id,actor_nodes.get(str(id)))
	return actor as Node3D if is_instance_valid(actor) else null

func _apply_downed_mother(actor_nodes: Dictionary) -> void:
	var actor:=_actor("mother",actor_nodes)
	var downed:=bool(_snapshot.get("rescue",{}).get("mother",{}).get("downed",false))
	var previous:Node3D=_downed_mother.get_ref() as Node3D if _downed_mother!=null else null
	if not downed or actor==null or previous!=null and previous!=actor:
		_release_downed_mother()
	if not downed or actor==null or not actor.has_method("set_cinematic_presentation"):return
	if actor.get("current_action")==&"death":return # Never revive a native dead actor for presentation.
	var point:Vector3=actor.get("server_target")
	var ground:=_ground(point)
	if not ground.is_finite():return
	var yaw:float=float(actor.get("_target_yaw"))
	actor.call("set_cinematic_presentation",ground,yaw,&"injury_pinned")
	_downed_mother=weakref(actor)

func _release_downed_mother() -> void:
	var actor:Node3D=_downed_mother.get_ref() as Node3D if _downed_mother!=null else null
	if is_instance_valid(actor) and actor.has_method("end_cinematic_presentation"):
		actor.call("end_cinematic_presentation")
	_downed_mother=null

func _apply_native_clip(key: String, actor: Node3D, event: Dictionary, time: float) -> void:
	# Only an already-defeated goblin's real native death clip is leased. The
	# scene can hold its fallen pose for last words, then finish that same fall;
	# health, death latch, collision and server position never change.
	if str(event.get("actor",""))!="goblin_boss" or str(event.get("clip",""))!="Death_A" \
			or actor.get("current_action")!=&"death":return
	var player:=actor.get("animation_player") as AnimationPlayer
	if player==null or not player.has_animation(&"Death_A"):return
	if not _clip_leases.has(key):
		_clip_leases[key]={"actor":weakref(actor),"player":weakref(player),"mode":player.callback_mode_process,
			"speed":player.speed_scale,"processing":actor.is_processing()}
	var saved:Dictionary=_clip_leases[key]
	if actor.is_processing():saved.processing=true
	actor.set_process(false)
	player.callback_mode_process=AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	player.speed_scale=1.0
	var hold:=clampf(float(event.get("hold",0.35)),0.0,player.get_animation(&"Death_A").length-0.001)
	var resume:=float(event.get("resume_at",12))
	var pose:=minf(player.get_animation(&"Death_A").length-0.001,hold+maxf(0,time-resume))
	player.stop(true);player.play(&"Death_A",0.0);player.seek(pose,true);player.advance(0.0);player.pause()

func _release_native_clip(key: String) -> void:
	var saved:Dictionary=_clip_leases[key]
	var actor:Node3D=saved.actor.get_ref();var player:AnimationPlayer=saved.player.get_ref()
	if is_instance_valid(player):player.callback_mode_process=int(saved.mode);player.speed_scale=float(saved.speed)
	if is_instance_valid(actor):
		if actor.get("current_action")==&"death" and actor.has_method("_hold_death_pose"):actor.call("_hold_death_pose")
		actor.set_process(bool(saved.processing))
	_clip_leases.erase(key)

func _retire_completed_burns() -> void:
	for index:int in range(_completed_burns.size()-1,-1,-1):
		var row:Dictionary=_completed_burns[index]
		var actor:Node3D=row.actor.get_ref()
		var accepted:=bool(_snapshot.get("rescue",{}).get("burned",false)) \
			or str(_snapshot.get("rescue",{}).get("stage",""))=="complete"
		if not is_instance_valid(actor) or actor.is_queued_for_deletion() \
				or (accepted and float(actor.get("_corpse_transparency"))>=0.999):
			row.effect.reset();_completed_burns.remove_at(index)

func _apply_role_scales(actor_nodes: Dictionary) -> void:
	_ensure_mother_kneel(_actor("mother",actor_nodes))
	var actor:=_actor("daughter",actor_nodes)
	if actor==null or not actor.has_method("set_server_scale"):return
	var id:=actor.get_instance_id()
	if not _scales.has(id):_scales[id]={"actor":weakref(actor),"scale":float(actor.get("server_scale"))}
	# Usually the actual NPC DTO already carries0.65. Reapplying it is a no-op;
	# it scales the imported visual/nameplate only and preserves native physics.
	actor.call("set_server_scale",0.65)

func _ensure_mother_kneel(actor: Node3D) -> void:
	if actor==null or _aliases.has(actor.get_instance_id()):return
	var player:=actor.get("animation_player") as AnimationPlayer
	var resolver:AnimationResolver=actor.get("resolver")
	var skeleton:=actor.get("_native_skeleton") as Skeleton3D
	var model:Dictionary=actor.get("_model_config")
	if player==null or resolver==null or skeleton==null or not model.has("culture"):return
	if not player.has_animation_library(&"rescue"):
		var path:String=actor.call("_external_path",str(model.get("animationLibrary","")))
		var result:=NativeAnimationImporter.import_library(actor,path,skeleton,model.get("boneAliases",{}),
			PackedStringArray(["Kneeling_Tired"]),PackedStringArray(["Kneeling_Tired"]))
		var extra:=result.get("player") as AnimationPlayer
		if extra==null:return
		if not (result.get("errors",PackedStringArray()) as PackedStringArray).is_empty():extra.free();return
		player.add_animation_library(&"rescue",extra.get_animation_library(&""));extra.free()
	var action:="rescue_kneel"
	_aliases[actor.get_instance_id()]={"actor":weakref(actor),"had":resolver.action_to_clip.has(action),"old":resolver.action_to_clip.get(action)}
	resolver.action_to_clip[action]=&"rescue/Kneeling_Tired"

func _apply_darkness() -> void:
	if _world==null:return
	if _dark_environment==null or _world.environment!=_dark_environment:
		_saved_environment=_world.environment
		_dark_environment=_saved_environment.duplicate(true) if _saved_environment!=null else Environment.new()
		_dark_environment.background_mode=Environment.BG_COLOR
		_dark_environment.background_color=Color("080a13")
		_dark_environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
		_dark_environment.ambient_light_color=Color("8a91a6");_dark_environment.ambient_light_energy=0.10
		_world.environment=_dark_environment
	_dark_environment.background_mode=Environment.BG_COLOR
	_dark_environment.background_color=Color("080a13")
	_dark_environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
	_dark_environment.ambient_light_energy=0.10
	_dark_environment.fog_enabled=false

func apply_environment(owner: WorldEnvironment, sun: DirectionalLight3D = null,
		moon: DirectionalLight3D = null) -> void:
	# Main calls this after its ordinary day/night grading. Restrict the lease
	# to this owned mine; portrait lights and unrelated world lights are untouched.
	if _identity.is_empty() or _map!="landfall_insides" or not is_instance_valid(owner):return
	_environment_binding=weakref(owner)
	_environment_owner=weakref(owner)
	_directional_inputs.clear()
	for light:DirectionalLight3D in [sun,moon]:
		_directional_inputs.append(weakref(light) if is_instance_valid(light) else null)
	if not _darkness_requested:
		_restore_darkness()
		_environment_owner=weakref(owner)
		return
	if owner.environment!=_dark_environment:
		_saved_environment=owner.environment
		_dark_environment=_saved_environment.duplicate(true) if _saved_environment!=null else Environment.new()
	owner.environment=_dark_environment
	_apply_darkness()
	for light:DirectionalLight3D in [sun,moon]:
		if not is_instance_valid(light):continue
		var id:=light.get_instance_id()
		if not _saved_lights.has(id) or not is_equal_approx(light.light_energy,0.025):
			_saved_lights[id]={"light":weakref(light),"energy":light.light_energy}
		light.light_energy=0.025

func _sync_darkness() -> void:
	for lamp:OmniLight3D in lamps:lamp.visible=_darkness_requested
	if _map!="landfall_insides":return
	if not _darkness_requested:
		_restore_darkness();return
	var owner:WorldEnvironment=_environment_binding.get_ref() as WorldEnvironment if _environment_binding!=null else null
	if is_instance_valid(owner):
		var sun:DirectionalLight3D=_directional_inputs[0].get_ref() as DirectionalLight3D if _directional_inputs.size()>0 and _directional_inputs[0]!=null else null
		var moon:DirectionalLight3D=_directional_inputs[1].get_ref() as DirectionalLight3D if _directional_inputs.size()>1 and _directional_inputs[1]!=null else null
		apply_environment(owner,sun,moon)
	else:_apply_darkness()

func _restore_darkness() -> void:
	var owner: WorldEnvironment=_environment_owner.get_ref() as WorldEnvironment if _environment_owner!=null else null
	if is_instance_valid(owner) and owner.environment==_dark_environment:owner.environment=_saved_environment
	if _world!=null and _world.environment==_dark_environment:_world.environment=_saved_environment
	for row:Dictionary in _saved_lights.values():
		var light:DirectionalLight3D=row.light.get_ref()
		if is_instance_valid(light):light.light_energy=float(row.energy)
	_saved_lights.clear();_saved_environment=null;_dark_environment=null;_environment_owner=null

func _set_gate(value: float) -> void:
	if is_instance_valid(gate):gate.position=_gate_origin+Vector3.UP*(2.9*clampf(value,0,1))

func _set_fade(value: float) -> void:
	var alpha:=clampf(value,0,1)
	if alpha>0 and not is_instance_valid(_fade):
		_fade_layer=CanvasLayer.new();_fade_layer.name="RescueWorldFade";_fade_layer.layer=118;add_child(_fade_layer)
		_fade=ColorRect.new();_fade.name="RescueBlackout";_fade.mouse_filter=Control.MOUSE_FILTER_IGNORE
		_fade_layer.add_child(_fade);_fade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	if is_instance_valid(_fade):
		_fade.color=Color(0,0,0,alpha);_fade.visible=alpha>0.001

func set_readouts_visible(value: bool) -> void:
	_readouts_visible=value
	for label:Label3D in labels.values():label.visible=value

func _ground(point: Vector3) -> Vector3:
	if not _sample.is_valid():return Vector3(INF,INF,INF)
	var height:Variant=_sample.call(point)
	if typeof(height) not in [TYPE_FLOAT,TYPE_INT] or not is_finite(float(height)):return Vector3(INF,INF,INF)
	point.y=float(height);return point

func _clear_cinematic(preserve_completed_burn := false) -> void:
	for effect:Node in _effects.values():
		if is_instance_valid(effect):effect.queue_free()
	_effects.clear()
	for key:String in _dissolves:
		if preserve_completed_burn and float(_dissolve_progress.get(key,0))>=0.999:
			_completed_burns.append({"effect":_dissolves[key],"actor":_dissolve_targets[key]})
		else:_dissolves[key].reset()
	_dissolves.clear();_dissolve_targets.clear();_dissolve_progress.clear()
	for key:String in _clip_leases.keys():_release_native_clip(key)
	_scene_id="";_scene_elapsed=0;_scene_replaying=false
	_set_gate(_accepted_gate)
	_set_fade(1.0 if _handoff_deadline_ms>0 else 0.0)

func clear() -> void:
	_handoff_token="";_handoff_deadline_ms=0;_expired_handoff_token=""
	_darkness_started=false;_darkness_requested=false
	_clear_cinematic();_restore_darkness()
	_directional_inputs.clear();_environment_binding=null
	_release_downed_mother()
	for row:Dictionary in _completed_burns:row.effect.reset()
	_completed_burns.clear();_bound_actors.clear()
	for row:Dictionary in _aliases.values():
		var actor:Node3D=row.actor.get_ref()
		if not is_instance_valid(actor):continue
		var resolver:AnimationResolver=actor.get("resolver")
		if resolver==null:continue
		if actor.get("current_action")==&"rescue_kneel" and not bool(actor.get("_cinematic_active")):
			actor.call("play_action",&"idle")
		if bool(row.had):resolver.action_to_clip["rescue_kneel"]=row.old
		else:resolver.action_to_clip.erase("rescue_kneel")
	_aliases.clear()
	for row:Dictionary in _scales.values():
		var actor:Node3D=row.actor.get_ref()
		if is_instance_valid(actor):actor.call("set_server_scale",float(row.scale))
	_scales.clear()
	if is_instance_valid(cage):cage.queue_free()
	for lamp:OmniLight3D in lamps:
		if is_instance_valid(lamp):lamp.queue_free()
	if is_instance_valid(_fade_layer):_fade_layer.queue_free()
	_fade=null;_fade_layer=null
	cage=null;gate=null;panels.clear();lamps.clear();labels.clear();points.clear()
	_identity="";_geometry="";_map="";_snapshot.clear();_world=null;hide()

func _exit_tree() -> void:
	clear()
