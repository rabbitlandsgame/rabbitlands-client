extends "res://src/world/campaign_works.gd"
## Existing coastal props and flow effects. Cargo, routes and damage are server-owned.
const NativeMarker=preload("res://src/actors/combat_target_marker_3d.gd")
const UNDERGROUND="res://assets/world/underground/"
const COASTAL_WATER=preload("res://src/world/continent_water.gdshader")
const CoastLook=preload("res://src/world/look/look_profile.gd")
var water_props:Dictionary={}
var _streams:Dictionary={}
var _materials:Dictionary={}
var _boat_from:=Vector3.ZERO
var _boat_to:=Vector3.ZERO
var _boat_clock:=1.0
var _wave_clock:=0.0
var _boat_yaw:=0.0
var _reduced:=false
var _surge:Node3D
var _surge_key:=""
var _impact_key:=""

func apply_controls(snapshot:Dictionary,adapter:CoordinateAdapter,current_map:String,sample:Callable,objects:Dictionary,blocked:bool)->bool:
	var water:Dictionary=(snapshot.get("shelves",{}) as Dictionary).get("water",{})
	if water.is_empty() or adapter==null or not bool(snapshot.get("active",false)) \
			or not (snapshot.get("travel",{}) as Dictionary).is_empty() \
			or EloriaProtocol.map_id_from_reference(str(snapshot.get("map","")))!=EloriaProtocol.map_id_from_reference(current_map):return false
	var targets:Dictionary={}
	for row:Dictionary in snapshot.get("targets",[]):
		if bool(row.get("enabled",true)) and not bool(row.get("completed",false)):targets[int(row.get("object_id",0))]=row
	var changed:=false
	for id:int in range(61840,61852)+[61990]:
		var node:=objects.get(id) as MapObject3D
		if not is_instance_valid(node):continue
		var enabled:=targets.has(id)
		# Commands share a station; one world pick avoids overlapping labels.
		# All available commands remain accessible in the quest window.
		if str(water.stage)=="water_cutters" and id in [61845,61846,61847]:
			enabled=enabled and id==(61847 if str(water.command)=="work" else 61845)
		if str(water.stage)=="water_barge" and id in [61843,61847,61848,61849]:
			var primary:=61843 if targets.has(61843) else 61847 if bool(water.sailing) else 61848
			enabled=enabled and id==primary
		var was_visible:=node.visible
		if was_visible!=enabled:node.visible=enabled;changed=true
		node.collision_layer=MapObject3D.PICK_LAYER if enabled and not blocked else 0
		node.set_meta("campaign_work_available",enabled and not blocked)
		if not enabled:continue
		var row:Dictionary=targets[id];var raw:Array=row.get("tile",[0,0])
		var tile:=Vector2i(int(raw[0]),int(raw[1]))
		if node.server_tile!=tile or not was_visible:
			var point:=adapter.tile_center(tile.x,tile.y)
			var height:float=sample.call(point)
			if is_finite(height):point.y=height
			node.server_tile=tile;node.global_position=point;changed=true
		node.label=str(row.get("label",node.label))
	return changed

func apply_snapshot(snapshot:Dictionary,adapter:CoordinateAdapter,current_map:String,surface_sample:Callable,reduced_motion:=false)->void:
	var water:Dictionary=(snapshot.get("shelves",{}) as Dictionary).get("water",{})
	if water.is_empty() or adapter==null or not bool(snapshot.get("active",false)) \
			or not (snapshot.get("travel",{}) as Dictionary).is_empty() \
			or EloriaProtocol.map_id_from_reference(str(snapshot.get("map","")))!=EloriaProtocol.map_id_from_reference(current_map):clear();return
	var identity:=str(snapshot.get("run_id",""))+":"+str(water.stage)+":"+str(water.route)
	if identity!=_identity:clear();_identity=identity
	_adapter=adapter;_sample=surface_sample;_reduced=reduced_motion;show()
	var anchors:Dictionary=snapshot.get("anchors",{})
	var grounded:Dictionary={}
	for key:String in anchors:
		var point:=_ground(adapter.tile_center(int(anchors[key][0]),int(anchors[key][1])))
		if not point.is_finite():continue
		grounded[key]=point
		var stage:=str(water.stage)
		if stage=="water_keeper" and key not in ["north","south","storage"] and not key.begins_with("kelp_") and not key.begins_with("cress"):continue
		if stage!="water_keeper" and key in ["north","south"]:continue
		var path:=""
		if key in ["upper","sea","drain","north","south"]:path=UNDERGROUND+"timber_sluice_gate.glb"
		elif stage=="water_barge" and (key in ["entry","landing_end"] or key in (["landing_one","landing_two"] if str(water.route)=="sheltered" else ["landing_coast_one","landing_coast_two"])):path=UNDERGROUND+"plank_jetty.glb"
		elif key in ["bin","bin_two","storage"]:path=UNDERGROUND+"supply_crate.glb"
		elif key.begins_with("kelp_"):path="res://assets/world/harvestables/kelp_strand_a.glb"
		elif key.begins_with("cress"):path="res://assets/world/harvestables/watercress_mat_a.glb"
		elif key=="breach":path=UNDERGROUND+"stone_windbreak.glb"
		if path.is_empty() or water_props.has(key):continue
		var body:=GlbSceneCache.instantiate(path)
		if body==null:continue
		add_child(body);water_props[key]=body;body.global_position=point+Vector3(1.5,0,0)
		if path.ends_with("plank_jetty.glb"):body.position+=Vector3(0,-2.476246,0) # Approved deck is 2.576246 m above its bottom-normalized root.
		if key.begins_with("kelp_") or key.begins_with("cress"):body.global_position=point
		if key in ["north","south"]:body.rotation.y=PI*0.5
		if key in ["upper","sea","drain","north","south"]:
			_label(key,point+Vector3(0,2.3,0))
		if key.begins_with("kelp_") or key.begins_with("cress"):
			flow_material=_water_material()
			_flow_segment(point-Vector3(0.8,0,0),point+Vector3(0.8,0,0),1.1)
	for key:String in ["upper","sea","drain"]:
		if not labels.has(key):continue
		var index:int=["upper","sea","drain"].find(key)
		(labels[key] as Label3D).text=("Fresh" if index==0 else "Tide" if index==1 else "Drain")+" gate · "+str(int(water.flow[index]))+"/2"
	for key:String in ["north","south"]:
		if labels.has(key):(labels[key] as Label3D).text=key.capitalize()+" gate · "+("closed — guards isolated" if water[key] and not water.boss_defeated else "open")
	if water_props.has("breach"):(water_props.breach as Node3D).visible=not (str(water.route)=="breach" and bool(water.channels))
	for pair:Array in ([] if str(water.stage)=="water_keeper" else [["upper","cress"],["sea","kelp_a"],["upper","cress_two"],["sea","kelp_a_two"]]):
		if not grounded.has(pair[0]) or not grounded.has(pair[1]):continue
		var key:=str(pair)
		if not _streams.has(key):
			var material:=_water_material();_materials[key]=material;flow_material=material
			_flow_segment(grounded[pair[0]],grounded[pair[1]],0.7);_streams[key]=true
		var index:=0 if pair[0]=="upper" else 1
		(_materials[key] as ShaderMaterial).set_shader_parameter("flow_strength",float(water.flow[index])/2.0)
	if str(water.stage)=="water_barge":
		var route:Array=water.path
		for index:int in range(route.size()-1):
			var key:="tow_"+str(index)
			if _streams.has(key):continue
			var a:=_ground(adapter.tile_center(int(route[index][0]),int(route[index][1]))+Vector3(4,0,0))
			var b:=_ground(adapter.tile_center(int(route[index+1][0]),int(route[index+1][1]))+Vector3(4,0,0))
			if not a.is_finite() or not b.is_finite():continue
			if not _materials.has("tow"):_materials.tow=_water_material()
			flow_material=_materials.tow;_flow_segment(a,b,2.2);_streams[key]=true
		var point:=_ground(adapter.tile_center(int(water.boat_tile[0]),int(water.boat_tile[1]))+Vector3(4,0,0))
		if point.is_finite():
			point.y-=0.2
			if not water_props.has("boat"):
				var boat:=GlbSceneCache.instantiate(UNDERGROUND+"rowing_boat.glb")
				if boat!=null:
					add_child(boat);water_props.boat=boat;boat.global_position=point;_boat_to=point;_boat_from=point
					var cargo:=GlbSceneCache.instantiate(UNDERGROUND+"supply_crate.glb")
					if cargo!=null:boat.add_child(cargo);cargo.scale=Vector3.ONE*0.45;cargo.position=Vector3(0,0.35,0)
					_label("hull",point+Vector3.UP*2.2)
			if not point.is_equal_approx(_boat_to) and water_props.has("boat"):
				_boat_from=(water_props.boat as Node3D).global_position
				var direction:=point-_boat_to
				if direction.length_squared()>0.01:_boat_yaw=atan2(direction.x,direction.z)
				_boat_to=point;_boat_clock=0.0
			if labels.has("hull"):(labels.hull as Label3D).text="Shipment barge · %d/100 hull" % int(water.hull)
	var hazards:Array=water.hazards
	var warning:Dictionary={}
	var impact_found:=false
	for hazard:Dictionary in hazards:
		if str(hazard.kind)=="warning":warning=hazard
		elif str(hazard.kind)=="impact":
			impact_found=true
			var token:=str(hazard.tile)
			if token!=_impact_key:
				var point:=_ground(adapter.tile_center(int(hazard.tile[0]),int(hazard.tile[1])))
				if point.is_finite():
					var effect:=WorldEffect3D.new();add_child(effect);effect.configure(90,point,null,3)
					effect.configure_area(float(hazard.radius)*adapter.metres_per_tile,"area");_impact_key=token
	if not impact_found:_impact_key=""
	if warning.is_empty():
		if is_instance_valid(_surge):_surge.queue_free()
		_surge=null;_surge_key=""
	else:
		var hazard:Dictionary=warning;var key:=str(hazard.tile)
		if key!=_surge_key:
			var point:=_ground(adapter.tile_center(int(hazard.tile[0]),int(hazard.tile[1])))
			if point.is_finite():
				if is_instance_valid(_surge):_surge.queue_free()
				_surge=NativeMarker.new();add_child(_surge);_surge.global_position=point
				_surge.configure(true,Vector2.ONE*float(hazard.radius)*2.0*adapter.metres_per_tile,0.4)
				_surge.get("pointer").text="SURGE — MOVE";_surge_key=key

func _water_material()->ShaderMaterial:
	var material:=ShaderMaterial.new();material.shader=COASTAL_WATER
	material.set_shader_parameter("water_to_continent",Transform3D.IDENTITY)
	material.set_shader_parameter("flow_strength",1.0)
	if RenderingServer.get_current_rendering_method()!="gl_compatibility":
		material.set_shader_parameter("look_decode_albedo",true)
		material.set_shader_parameter("look_sea_value",CoastLook.CONTINENT_SEA_VALUE)
		material.set_shader_parameter("look_sea_chroma",CoastLook.CONTINENT_SEA_CHROMA)
	material.set_shader_parameter("reduced_motion",_reduced)
	return material

func _process(delta:float)->void:
	if not is_instance_valid(water_props.get("boat")):return
	_boat_clock=minf(1.0,_boat_clock+delta);_wave_clock+=delta
	var boat:=water_props.boat as Node3D
	boat.global_position=_boat_from.lerp(_boat_to,_boat_clock)+Vector3.UP*(0.0 if _reduced else sin(_wave_clock*1.4)*0.025)
	boat.rotation.y=lerp_angle(boat.rotation.y,_boat_yaw,minf(1,delta*3))
	if labels.has("hull"):(labels.hull as Label3D).global_position=boat.global_position+Vector3.UP*2.2

func clear()->void:
	super.clear();water_props.clear();_streams.clear();_materials.clear()
	_surge=null;_surge_key="";_impact_key="";_boat_clock=1.0;_wave_clock=0.0;_boat_yaw=0.0
