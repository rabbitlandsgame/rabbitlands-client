extends Node3D
## Accepted supply objects and cart positions only; never awards work or predicts a route.
const CART := "res://assets/world/campaign/road_handcart.glb"
const CRATE := "res://assets/world/underground/supply_crate.glb"
const SACK := "res://assets/world/underground/feed_sacks.glb"
const BARRELS := "res://assets/world/underground/barrel_stack.glb"
const PLANTER := "res://assets/world/underground/flower_planter.glb"
const DRYING_RACK := "res://assets/world/underground/herb_drying_rack.glb"
var props: Dictionary={}
var _identity:=""
var _adapter:CoordinateAdapter
var _sample:Callable
var _cart_from:=Vector3.ZERO
var _cart_to:=Vector3.ZERO
var _cart_elapsed:=1.0
var _worker_nodes: Dictionary={}

func apply_workers(snapshot:Dictionary,actors:Dictionary)->void:
	_worker_nodes.clear()
	var rows:Array=((snapshot.get("shelves",{}) as Dictionary).get("growers",(snapshot.get("shelves",{}) as Dictionary).get("fire",{})) as Dictionary).get("workers",[])
	var wanted:Dictionary={}
	for worker:Dictionary in rows:
		var actor:=actors.get(int(worker.actor_id)) as ReplicatedActor3D
		if not is_instance_valid(actor):continue
		var key:="bag_"+str(worker.actor_id)
		var fire:Dictionary=(snapshot.get("shelves",{}) as Dictionary).get("fire",{})
		var hauls_cart:bool=(fire.get("carts",[]) as Array).any(func(cart:Dictionary)->bool:return int(cart.actor_id)==int(worker.actor_id))
		if int(worker.cargo)>0 and not bool(worker.downed) and not hauls_cart:
			wanted[key]=true;_worker_nodes[key]=actor
			if not is_instance_valid(props.get(key)):
				var bag:=_asset(SACK)
				if bag!=null:bag.scale=Vector3.ONE*0.22;add_child(bag);props[key]=bag
		if bool(worker.downed):continue
		if bool(worker.harvesting) and not actor.is_model_deferred():
			actor.play_action(&"harvest",actor.animation_player!=null and not actor.animation_player.is_playing())
		elif actor.current_action==&"harvest":actor.play_action(&"idle")
	for key:String in props.keys():
		if key.begins_with("bag_") and not wanted.has(key):
			if is_instance_valid(props[key]):props[key].queue_free()
			props.erase(key)

func apply_snapshot(snapshot:Dictionary,adapter:CoordinateAdapter,current_map:String,sample:Callable)->void:
	var here:=EloriaProtocol.map_id_from_reference(current_map)
	if str(snapshot.get("kind",""))!="shelves" or adapter==null \
			or EloriaProtocol.map_id_from_reference(str(snapshot.get("map","")))!=here \
			or not (snapshot.get("travel",{}) as Dictionary).is_empty():
		clear();return
	var ledger:Dictionary=snapshot.get("shelves",{})
	if ledger.is_empty():clear();return
	_adapter=adapter;_sample=sample
	var identity:=str(snapshot.get("run_id",""))+":"+here+":"+str(ledger.get("chapter",""))
	if identity!=_identity:clear();_identity=identity
	var anchors:Dictionary={} if ledger.has("fire") else snapshot.get("anchors",{})
	if anchors.has("stock_display"):
		for index:int in (ledger.get("unlocked",[]) as Array).size():
			var key:="shelf_"+str(index)
			if props.has(key):continue
			var point:=_ground(_adapter.tile_center(int(anchors.stock_display[0]),int(anchors.stock_display[1])))
			if not point.is_finite():continue
			var body:=_asset(CRATE if index%2==0 else SACK)
			if body==null:continue
			add_child(body);body.global_position=point+Vector3((index%4)*0.8,(index/4)*0.65,0);props[key]=body
	for key:String in anchors:
		if key in ["return","practice","finish","repair_cart","worker_stop","worker_entry","stock_display"] or props.has(key):continue
		var point:=_ground(_adapter.tile_center(int(anchors[key][0]),int(anchors[key][1])))
		if not point.is_finite():continue
		var path:=BARRELS if key in ["upper","middle","lower","bypass","intake","seal","loop","restart"] else SACK if key in ["stock","load","unload"] else CRATE
		if key.begins_with("crop_"):path=PLANTER
		elif key in ["racks","shelter"]:path=DRYING_RACK
		var body:=_asset(path)
		if body==null:continue
		add_child(body);body.global_position=point+Vector3(0.8,0,0.8);props[key]=body
	if str(ledger.get("chapter",""))=="earth" and bool(snapshot.get("active",false)):
		var tile:Array=ledger.get("cart_tile",[])
		if tile.size()!=2:return
		var point:=_ground(_adapter.tile_center(int(tile[0]),int(tile[1])))
		if not point.is_finite():return
		if not props.has("cart"):
			var body:=_asset(CART)
			if body==null:return
			add_child(body);body.global_position=point;props.cart=body;_cart_to=point
		if not point.is_equal_approx(_cart_to):
			_cart_from=(props.cart as Node3D).global_position;_cart_to=point;_cart_elapsed=0.0

func _process(delta:float)->void:
	for key:String in _worker_nodes:
		var actor:=_worker_nodes[key] as Node3D
		if is_instance_valid(actor) and is_instance_valid(props.get(key)):
			(props[key] as Node3D).global_transform=actor.global_transform.translated_local(Vector3(-0.3,0.85,0.15)).scaled_local(Vector3.ONE*0.22)
	if not props.has("cart") or _cart_elapsed>=1.0:return
	_cart_elapsed=minf(1.0,_cart_elapsed+delta)
	var point:=_ground(_cart_from.lerp(_cart_to,_cart_elapsed))
	if point.is_finite():(props.cart as Node3D).global_position=point

func _ground(point:Vector3)->Vector3:
	var height:Variant=_sample.call(point) if _sample.is_valid() else NAN
	if typeof(height) not in [TYPE_FLOAT,TYPE_INT] or not is_finite(float(height)):return Vector3.INF
	point.y=float(height);return point

func _asset(path:String)->Node3D:
	var model:=GlbSceneCache.instantiate(path)
	if model==null:return null
	var wrapper:=Node3D.new();var pivot:=Node3D.new();wrapper.add_child(pivot);pivot.add_child(model)
	if path==CART:pivot.position=Vector3(-0.824876,0.043751,0)
	return wrapper

func clear()->void:
	for body:Node3D in props.values():
		if is_instance_valid(body):body.queue_free()
	props.clear();_identity="";_cart_elapsed=1.0
	_worker_nodes.clear()
