extends Node3D
## Approved mine props and server-owned blast warnings. Never predicts damage.
const MineWorks=preload("res://src/world/campaign_shelves_works.gd")
const Marker=preload("res://src/actors/combat_target_marker_3d.gd")
var props: Dictionary={}
var _identity:=""
var _carts:Dictionary={}
var _actor_nodes:Dictionary={}
var _warning:Node3D
var _warning_key:=""
var _explosion_key:=""

func apply_snapshot(snapshot:Dictionary,adapter:CoordinateAdapter,current_map:String,sample:Callable,actors:Dictionary={})->void:
	var ledger:Dictionary=(snapshot.get("shelves",{}) as Dictionary).get("fire",{})
	if ledger.is_empty() or adapter==null or not bool(snapshot.get("active",false)) \
			or not (snapshot.get("travel",{}) as Dictionary).is_empty() \
			or EloriaProtocol.map_id_from_reference(str(snapshot.get("map","")))!=EloriaProtocol.map_id_from_reference(current_map):clear();return
	var identity:=str(snapshot.get("run_id",""))+":"+str(ledger.stage)
	if identity!=_identity:clear();_identity=identity
	_actor_nodes=actors
	var anchors:Dictionary=snapshot.get("anchors",{})
	for key:String in anchors:
		var path:=""
		if key=="lift" and str(ledger.stage)=="fire_coal":path="res://assets/world/underground/mine_headframe.glb"
		elif key=="signal":path="res://assets/world/underground/net_mending_frame.glb"
		elif key=="water":path="res://assets/world/underground/timber_sluice_gate.glb"
		elif key.begins_with("passage_") and str(ledger.stage)=="fire_coal":path="res://assets/world/underground/stone_windbreak.glb"
		elif key in ["stock","storage"]:path=MineWorks.CRATE
		elif key=="release" and str(ledger.stage)=="fire":path="res://assets/world/underground/stone_windbreak.glb"
		if path.is_empty() or props.has(key):continue
		var point:=adapter.tile_center(int(anchors[key][0]),int(anchors[key][1]))
		var height:Variant=sample.call(point) if sample.is_valid() else NAN
		if typeof(height) not in [TYPE_FLOAT,TYPE_INT] or not is_finite(float(height)):continue
		point.y=float(height)
		var body:=GlbSceneCache.instantiate(path)
		if body==null:continue
		add_child(body);props[key]=body
		body.global_position=point
		# Keep interactive approaches clear; the authoritative walkable tile is
		# beside the imported equipment rather than inside its mesh.
		body.position+=Vector3(0.8,0,0.8)
	if str(ledger.stage)!="fire_sapper":
		for index:int in (ledger.carts as Array).size():
			var cart_state:Dictionary=ledger.carts[index]
			var key:="cart" if index==0 else "cart_two"
			var point:=adapter.tile_center(int(cart_state.tile[0]),int(cart_state.tile[1]))
			var height:Variant=sample.call(point) if sample.is_valid() else NAN
			if typeof(height) not in [TYPE_FLOAT,TYPE_INT] or not is_finite(float(height)):continue
			point.y=float(height)+float(cart_state.height)
			point+=Vector3(0.6,0,-0.5)
			if not props.has(key):
				var cart:=GlbSceneCache.instantiate("res://assets/world/underground/ore_cart.glb")
				if cart==null:continue
				add_child(cart);props[key]=cart;cart.global_position=point
			_carts[key]={"from":(props[key] as Node3D).global_position,"to":point,"clock":0.0,"actor_id":int(cart_state.actor_id),"height":float(cart_state.height)}
	var warning:Dictionary={}
	for hazard:Dictionary in ledger.get("hazards",[]):
		var point:=adapter.tile_center(int(hazard.tile[0]),int(hazard.tile[1]))
		var height:Variant=sample.call(point) if sample.is_valid() else NAN
		if typeof(height) in [TYPE_FLOAT,TYPE_INT] and is_finite(float(height)):point.y=float(height)
		if str(hazard.kind)=="warning":
			warning=hazard
			var token:=str(hazard.tile)+":"+str(hazard.radius)
			if token!=_warning_key:
				if is_instance_valid(_warning):_warning.queue_free()
				_warning=Marker.new();add_child(_warning);_warning.global_position=point
				_warning.configure(true,Vector2.ONE*float(hazard.radius)*2.0*adapter.metres_per_tile,0.4)
				_warning.get("pointer").text="BLAST — MOVE"
				_warning_key=token
		elif str(hazard.kind)=="explosion":
			var token:=str(hazard.tile)
			if token!=_explosion_key:
				var effect:=WorldEffect3D.new();add_child(effect);effect.configure(89,point,null,3)
				effect.configure_area(float(hazard.radius)*adapter.metres_per_tile,"area")
				_explosion_key=token
	if warning.is_empty():
		if is_instance_valid(_warning):_warning.queue_free()
		_warning=null;_warning_key=""
	if not (ledger.hazards as Array).any(func(v:Dictionary)->bool:return str(v.kind)=="explosion"):_explosion_key=""

func _process(delta:float)->void:
	for key:String in _carts:
		if not is_instance_valid(props.get(key)):continue
		var state:Dictionary=_carts[key]
		var owner_actor:=_actor_nodes.get(int(state.actor_id)) as Node3D
		if is_instance_valid(owner_actor):
			(props[key] as Node3D).global_position=owner_actor.global_position+owner_actor.global_basis*Vector3(0.6,float(state.height),-0.5)
			(props[key] as Node3D).global_basis=owner_actor.global_basis
		else:
			state.clock=minf(1,float(state.clock)+delta)
			(props[key] as Node3D).global_position=(state.from as Vector3).lerp(state.to,float(state.clock))

func clear()->void:
	for child:Node in get_children():child.queue_free()
	props.clear();_identity="";_warning=null;_warning_key="";_explosion_key=""
	_carts.clear();_actor_nodes={}
