extends SceneTree
const Crossing := preload("res://src/world/campaign_crossing.gd")
var checks := 0
var failures := 0

static func snapshot() -> Dictionary:
	return {"version":1,"active":true,"run_id":"pier-run","map":"maps/nymara/greenlight.elm","targets":[],
		"crossing":{"id":"greenlight_inner_pier","damage_tile":[433,319],"work_tile":[430,318],"far_tile":[425,316],"muster_tile":[441,325],
			"single_file":true,"braced":false,"load_tested":false,"rope_secured":false,"worker_safe":false}}

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ", message)
	else:
		failures += 1
		push_error(message)
func decode(value: Dictionary) -> Dictionary:
	return EloriaProtocol.decode_campaign(JSON.stringify(value).to_utf8_buffer())
func run() -> void:
	create_timer(60).timeout.connect(func()->void:push_error("Crossing checks timed out");quit(1))
	var state := snapshot()
	expect(decode(state).get("type")=="campaign","the additive real-pier crossing contract decodes")
	var legacy := state.duplicate(true);legacy.erase("crossing")
	expect(decode(legacy).get("type")=="campaign","legacy campaign snapshots do not require crossing metadata")
	for field: String in ["id","damage_tile","work_tile","far_tile","muster_tile","single_file","braced","load_tested","rope_secured","worker_safe"]:
		var invalid := state.duplicate(true);invalid.crossing.erase(field)
		expect(decode(invalid).get("type")=="invalid","crossing "+field+" is required whenever the structure is declared")
	for patch: Dictionary in [{"id":"public_bridge"},{"damage_tile":[433.5,319]},{"work_tile":[430]},{"far_tile":[425,316,0]},{"muster_tile":["441",325]},{"single_file":1},{"braced":"yes"},{"load_tested":null},{"rope_secured":[]},{"worker_safe":{}}]:
		var invalid := state.duplicate(true);invalid.crossing.merge(patch,true)
		expect(decode(invalid).get("type")=="invalid","malformed crossing identities, coordinates and flags are rejected")
	var works := Crossing.new();root.add_child(works)
	# Pin this fixture's placement independently of native-survey refinements.
	works.debris_offset=Vector3(1.25,-1.15,1.4);works.debris_scale=0.6
	works.debris_yaw_degrees=-160.0;works.debris_roll_degrees=8.0
	var adapter := CoordinateAdapter.new({"metresPerTile":1.0,"serverOrigin":[435,448],"walkingHeight":2.5,"invertServerY":true})
	var resident := [false]
	var sample := func(_point:Vector3)->float:return 2.5 if resident[0] else NAN
	works.apply_snapshot(state,adapter,"greenlight",sample)
	expect(works.native==null and not works.visible,"debris waits for actual native pier surface, without a fallback floating pose")
	resident[0]=true;var before:=JSON.stringify(state);works.apply_snapshot(state,adapter,"greenlight",sample)
	expect(is_instance_valid(works.native) and works.visible,"the active private encounter reuses the approved packaged driftwood")
	expect(works.debris.global_position.is_equal_approx(works.points.damage_tile+Vector3(1.25,-1.15,1.4)),"placement is derived from the supplied damage tile and sampled deck height")
	var pristine:Node3D=GlbSceneCache.instantiate(Crossing.DRIFTWOOD_ASSET)
	var normalization:=works.native.transform.is_equal_approx(pristine.transform)
	var source_nodes:=pristine.find_children("*","Node3D",true,false)
	var presented_nodes:=works.native.find_children("*","Node3D",true,false)
	normalization=normalization and source_nodes.size()==presented_nodes.size()
	for index:int in range(mini(source_nodes.size(),presented_nodes.size())):
		normalization=normalization and (source_nodes[index] as Node3D).transform.is_equal_approx((presented_nodes[index] as Node3D).transform)
	expect(works.debris.scale.is_equal_approx(Vector3.ONE*0.6) and normalization,"outer placement scale preserves every imported baked transform")
	pristine.free()
	expect(is_equal_approx(works.debris.rotation_degrees.y,-160.0) and is_equal_approx(works.debris.rotation_degrees.z,8.0),"the lodged debris uses the agreed pier alignment and slight lean")
	var meshes:=works.native.find_children("*","MeshInstance3D",true,false)
	expect(not meshes.is_empty(),"the presentation contains actual imported mesh geometry")
	for mesh: MeshInstance3D in meshes:
		expect(mesh.layers==2 and mesh.material_override==null and mesh.mesh.surface_get_material(0)!=null,"native geometry keeps embedded materials and stays out of portrait layer1")
	expect(works.find_children("*","CollisionObject3D",true,false).is_empty(),"the private visual adds no collider, floor or walkable shortcut")
	expect(works.status_label.layers==(1<<19) and works.status_label.text=="Loose support · one person at a time","the ordinary world-text layer explains the unsafe single-file support")
	works.set_readouts_visible(false)
	expect(not works.status_label.visible and works.debris.visible,"untracking or a close cinematic hides labels while physical debris remains")
	works.set_readouts_visible(true)
	var braced:=state.duplicate(true);braced.crossing.braced=true;works.apply_snapshot(braced,adapter,"greenlight",sample)
	expect(not works.debris.visible and works.status_label.text=="Access braced · load test next","only a confirmed brace clears the debris presentation and requests a test")
	braced.crossing.load_tested=true;works.apply_snapshot(braced,adapter,"greenlight",sample)
	expect(works.status_label.text=="Load test passed","the load-test caption follows the server proof")
	var rope:=state.duplicate(true);rope.crossing.rope_secured=true;works.apply_snapshot(rope,adapter,"greenlight",sample)
	expect(not works.debris.visible and works.status_label.text=="Handline secured · single file","the handline resolution has its own truthful access status")
	expect(JSON.stringify(state)==before,"presentation never mutates crossing progress or the incoming snapshot")
	for invalid: String in ["inactive","travel","foreign_map","foreign_snapshot","other_chapter","missing_run","missing_metadata"]:
		works.apply_snapshot(state,adapter,"greenlight",sample)
		var row:=state.duplicate(true);var here:="greenlight"
		match invalid:
			"inactive":row.active=false
			"travel":row.travel={"map":"twinbrook"}
			"foreign_map":here="twinbrook"
			"foreign_snapshot":row.map="twinbrook"
			"other_chapter":row.kind="bank"
			"missing_run":row.run_id=""
			"missing_metadata":row.erase("crossing")
		works.apply_snapshot(row,adapter,here,sample)
		expect(works.native==null and not works.visible,invalid+" clears all private crossing visuals")
	works.apply_snapshot(state,adapter,"greenlight",sample)
	var old_native:Node3D=works.native;var next:=state.duplicate(true);next.run_id="another-pier-run";works.apply_snapshot(next,adapter,"greenlight",sample)
	expect(works.native!=old_native and works._identity=="another-pier-run","a new run cannot inherit the old crossing instance")
	var second:=SubViewport.new();second.own_world_3d=true;root.add_child(second);works.reparent(second)
	var previous_world:World3D=works._world;works.apply_snapshot(next,adapter,"greenlight",sample)
	expect(works._world==works.get_world_3d() and works._world!=previous_world,"changing the world rebuilds the private visual rather than retaining foreign-world nodes")
	works.clear();expect(works.native==null and works.status_label==null and works.points.is_empty(),"clear releases the model, text, world and anchors")
	second.queue_free();await process_frame;await process_frame
	print("campaign crossing: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
