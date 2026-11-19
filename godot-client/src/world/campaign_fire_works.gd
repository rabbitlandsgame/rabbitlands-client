extends Node3D
## Approved mine props and server-owned blast warnings. Never predicts damage.
const MineWorks=preload("res://src/world/campaign_shelves_works.gd")
const Marker=preload("res://src/actors/combat_target_marker_3d.gd")
const STOCK_LOAD_POSITIONS=[Vector3(-1.175,0.85,-0.3),Vector3(-1.175,0.85,0.3),
	Vector3(-0.475,0.85,-0.3),Vector3(-0.475,0.85,0.3)]
var props: Dictionary={}
var _identity:=""
var _carts:Dictionary={}
var _actor_nodes:Dictionary={}
var _warning:Node3D
var _warning_key:=""
var _explosion_key:=""
var _stock_loads:Dictionary={}

static func stock_display_units(ledger:Dictionary)->int:
	var goal:=int(ledger.get("recovered_goal",0))
	if goal<=0:return 0
	var remaining:=maxi(0,goal-int(ledger.get("recovered",0)))
	return clampi(ceili(float(remaining)*float(STOCK_LOAD_POSITIONS.size())/float(goal)),0,STOCK_LOAD_POSITIONS.size())

func _stranded_stock(ledger:Dictionary,anchors:Dictionary,adapter:CoordinateAdapter,sample:Callable)->void:
	var key:="stranded_cart"
	if not anchors.has(key) or str(ledger.stage) not in ["fire","fire_coal"]:
		if is_instance_valid(props.get(key)):props[key].hide()
		return
	var raw:Array=anchors[key]
	var point:=adapter.tile_center(int(raw[0]),int(raw[1]))
	var height:Variant=sample.call(point) if sample.is_valid() else NAN
	if typeof(height) not in [TYPE_FLOAT,TYPE_INT] or not is_finite(float(height)):return
	point.y=float(height)
	if not is_instance_valid(props.get(key)):
		var model:=GlbSceneCache.instantiate(MineWorks.CART)
		if model==null:return
		var body:=Node3D.new();body.name="StrandedStockWagon"
		var pivot:=Node3D.new();body.add_child(pivot);pivot.add_child(model)
		# Reuse the already accepted Road handcart's centred frame and open bed.
		pivot.position=Vector3(-0.824876,0.043751,0)
		for cover:Node in model.find_children("*sun_textile","MeshInstance3D",true,false):(cover as MeshInstance3D).hide()
		add_child(body);props[key]=body
	var wagon:=props[key] as Node3D
	wagon.show();wagon.global_position=point
	if anchors.has("release"):
		var gate:Array=anchors.release
		var direction:=adapter.tile_center(int(gate[0]),int(gate[1]))-point
		if Vector2(direction.x,direction.z).length()>0.05:
			# This imported cart's shafts point along its local positive X axis.
			wagon.global_rotation.y=atan2(-direction.z,direction.x)
	var units:=stock_display_units(ledger)
	for index:int in STOCK_LOAD_POSITIONS.size():
		if not is_instance_valid(_stock_loads.get(index)):
			var crate:=GlbSceneCache.instantiate(MineWorks.CRATE)
			var sacks:=GlbSceneCache.instantiate(MineWorks.SACK)
			if crate==null or sacks==null:
				if crate!=null:crate.free()
				if sacks!=null:sacks.free()
				continue
			var bundle:=Node3D.new();bundle.name="RecoveredStockLoad%d"%index
			wagon.add_child(bundle);bundle.position=STOCK_LOAD_POSITIONS[index]
			bundle.add_child(crate);crate.scale=Vector3.ONE*0.52
			# The accepted crate sits on the cart bed; pale sacks rest on its
			# measured0.52m top, making a supported load visible above the rim.
			bundle.add_child(sacks);sacks.scale=Vector3.ONE*0.48;sacks.position.y=0.52
			_stock_loads[index]=bundle
		# Symbolic load groups follow secured recovery receipts. Picking up
		# bags, mining new Flint or replaying a scene cannot spend this stock.
		(_stock_loads[index] as Node3D).visible=index<units

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
		elif key=="stock":
			if anchors.has("stranded_cart") and str(ledger.stage) in ["fire","fire_coal"]:
				if is_instance_valid(props.get(key)):props[key].hide()
				continue
			path=MineWorks.CRATE
		elif key=="storage":path=MineWorks.CRATE
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
	if str(ledger.stage)=="fire" and is_instance_valid(props.get("release")):
		(props.release as Node3D).visible=str(ledger.get("step",""))!="extract"
		if anchors.has("entry") and anchors.has("release"):
			var entry:Array=anchors.entry;var gate:Array=anchors.release
			var outward:=adapter.tile_center(int(entry[0]),int(entry[1]))-adapter.tile_center(int(gate[0]),int(gate[1]))
			var across:=Vector3(-outward.z,0,outward.x)
			if across.length()>0.05:(props.release as Node3D).global_rotation.y=atan2(-across.z,across.x)
	if str(ledger.stage) in ["fire","fire_coal"]:
		if is_instance_valid(props.get("stock")):
			(props.stock as Node3D).visible=not anchors.has("stranded_cart") and stock_display_units(ledger)>0
		_stranded_stock(ledger,anchors,adapter,sample)
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
	_stock_loads.clear()
