extends SceneTree
## Actual imported quest props; symbolic stock bands never change native work.
const Works:=preload("res://src/world/campaign_fire_works.gd")
const Supplies:=preload("res://tests/test_campaign_shelves.gd")
var checks:=0
var failures:=0

func _init()->void:run.call_deferred()
func expect(ok:bool,message:String)->void:
	checks+=1
	if not ok:failures+=1;push_error(message)

func snapshot()->Dictionary:
	var state:=Supplies.snapshot();state.scene={};state.stage="work";state.key="fire"
	state.shelves.phase="work";state.shelves.chapter="fire"
	state.shelves.fire={"stage":"fire","route":"silence","step":"route","recovered":0,"mined":0,
		"recovered_goal":4000,"mined_goal":1000,"carried":0,"repair":0,"passages":0,"signal":false,
		"water":false,"powder":false,"wave":0,"cart_tile":[47,219],"carts":[],"workers":[],"hazards":[]}
	state.anchors={"entry":[54,213],"stock":[47,219],"release":[47,216],"stranded_cart":[44,212],"storage":[57,216]}
	return state

func visible_loads(works:Node)->int:
	var count:=0
	for body:Node3D in works._stock_loads.values():
		if body.is_visible_in_tree():count+=1
	return count

func run()->void:
	root.get_node("Network").block_for_hud_preview()
	var state:=snapshot();var ledger:Dictionary=state.shelves.fire
	for pair:Array in [[0,4],[999,4],[1000,3],[2000,2],[3999,1],[4000,0]]:
		ledger.recovered=pair[0]
		expect(Works.stock_display_units(ledger)==pair[1],"stock display follows delivered recovery bands")
	ledger.recovered=0
	var works:=Works.new();root.add_child(works)
	var adapter:=CoordinateAdapter.new()
	works.apply_snapshot(state,adapter,"landfall",func(_point:Vector3)->float:return NAN)
	expect(not works.props.has("stranded_cart"),"unloaded terrain never grounds a wagon at a guessed height")
	var before:=JSON.stringify(state)
	works.apply_snapshot(state,adapter,"landfall",func(_point:Vector3)->float:return 2.5)
	expect(JSON.stringify(state)==before,"building the opening props never mutates its authoritative snapshot")
	expect(works.props.has("stranded_cart") and visible_loads(works)==4,
		"the held opening visibly contains an imported wagon with all cut-stock groups")
	expect(works.props.stranded_cart.find_children("*","MeshInstance3D",true,false).size()>4,
		"the stock setup uses actual imported cart and crate meshes")
	expect(works.props.release.visible and not works.props.has("stock") and not works.props.has("cart"),
		"the barricade holds while the wagon replaces an unchanging stock crate and moving carts wait")
	var wagon:Node3D=works.props.stranded_cart
	expect(is_equal_approx(wagon.global_position.y,2.5),"the wagon uses the actual provided ground height")
	var outward:=adapter.tile_center(54,213)-adapter.tile_center(47,216)
	expect(absf((works.props.release.global_basis.x as Vector3).normalized().dot(outward.normalized()))<0.001,
		"the imported gate spans across the actual exit direction")
	var camera:=Camera3D.new();root.add_child(camera);camera.position=Vector3(5,3,7)
	var camera_pose:=camera.global_transform;var wagon_pose:=wagon.global_transform
	ledger.carried=1000;ledger.mined=1000
	works.apply_snapshot(state,adapter,"landfall",func(_point:Vector3)->float:return 2.5)
	expect(visible_loads(works)==4,"carried bags and newly mined material cannot deplete already-cut stock")
	ledger.step="extract"
	works.apply_snapshot(state,adapter,"landfall",func(_point:Vector3)->float:return 2.5)
	expect(not works.props.release.visible and visible_loads(works)==4,"opening the gate clears the barrier without pretending stock is delivered")
	ledger.recovered=2000
	works.apply_snapshot(state,adapter,"landfall",func(_point:Vector3)->float:return 2.5)
	expect(visible_loads(works)==2,"half the secured stock leaves half the symbolic cart load")
	ledger.recovered=4000
	works.apply_snapshot(state,adapter,"landfall",func(_point:Vector3)->float:return 2.5)
	expect(visible_loads(works)==0 and wagon.visible,"the completed recovery leaves an empty wagon")
	expect(camera.global_transform.is_equal_approx(camera_pose) and wagon.global_transform.is_equal_approx(wagon_pose),
		"ordinary stock updates neither move the camera nor shift the accepted wagon anchor")
	state=snapshot();state.anchors.erase("stranded_cart");state.run_id="older-server"
	works.apply_snapshot(state,adapter,"landfall",func(_point:Vector3)->float:return 0.0)
	expect(works.props.has("stock") and not works.props.has("stranded_cart"),
		"older servers keep their existing stock prop without inventing a wagon location")
	var definitions:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/campaign/shelves_scenes.json")).scenes
	var entry:Dictionary=definitions["measure.shelves.fire.entry_quarry"]
	expect(entry.shots.size()==1 and entry.shots[0].anchor=="release" and entry.required_actors==["mentor"],
		"one establishing view shows the gate while older casts still have their original readiness requirement")
	for role:String in ["crew_one","crew_two","crew_three"]:
		expect(role in entry.cast_roles and role in entry.native_roles,"all three held haulers keep their real native conversation positions")
	var path:=OS.get_environment("RL_FIRE_STAGING_EVIDENCE")
	if not path.is_empty():
		var bundle:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(path))
		for record:Dictionary in bundle.records:
			var native:Dictionary=record.snapshot
			var decoded:=EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
			expect(decoded.type=="campaign","the actual native staging packet decodes")
			if decoded.type!="campaign":continue
			var unchanged:=JSON.stringify(native)
			works.apply_snapshot(decoded.state,adapter,str(native.map),func(_point:Vector3)->float:return 0.0)
			expect(visible_loads(works)==Works.stock_display_units(native.shelves.fire),"actual native recovery receipts control the visible imported stock")
			expect(works.props.release.visible==(str(native.shelves.fire.step)!="extract"),"actual native release state controls the barricade")
			expect(JSON.stringify(native)==unchanged,"visual staging changes no native progress or party proof")
			await process_frame
	works.clear();await process_frame;await process_frame
	expect(works.get_child_count()==0 and works._stock_loads.is_empty(),"leaving the worksite releases stock props without leftover load state")
	works.queue_free();camera.queue_free();await process_frame
	GlbSceneCache.clear()
	print("Fire quarry visual setup: %d checks; %d failures"%[checks,failures])
	quit(1 if failures else 0)
