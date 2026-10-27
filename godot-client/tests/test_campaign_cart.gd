extends SceneTree
const Cart := preload("res://src/world/campaign_cart.gd")
var checks := 0
var failures := 0

static func snapshot() -> Dictionary:
	return {"version":1,"content_revision":2,"kind":"opening","active":true,"run_id":"cart-run","map":"greenlight",
		"anchors":{"cart_anchor":[422,316],"cart_post":[426,316],"cart_release":[420,316],
			"cart_fulcrum":[424,318],"cart_unload_1":[428,315],"cart_unload_2":[429,316],
			"cart_rope_1":[424,314],"cart_rope_2":[427,315],"cart_hold":[426,318],
			"worker_far":[425,316],"muster":[441,325]},
		"cart":{"id":"last_cart","tile":[422,316],"facing":[1,0],"footprint":[5,3],
			"tilt_deg":17,"route":"","state":"trapped","load_units":2,"unloaded":0,
			"fulcrum_ready":false,"rope_ends":0,"holder_active":true,"released":false,"treated":false,"worker_safe":false,
			"worker_tile":[425,316],"safe_tile":[441,325]}}

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func imported_unchanged(instance: Node3D, pristine: Node3D) -> bool:
	var actual: Array[Node] = [instance]
	actual.append_array(instance.find_children("*","Node3D",true,false))
	var source: Array[Node] = [pristine]
	source.append_array(pristine.find_children("*","Node3D",true,false))
	if actual.size() != source.size():
		return false
	for index: int in actual.size():
		if not (actual[index] as Node3D).transform.is_equal_approx((source[index] as Node3D).transform):
			return false
		if actual[index] is MeshInstance3D:
			var mesh := actual[index] as MeshInstance3D
			var original := source[index] as MeshInstance3D
			if mesh.mesh != original.mesh or mesh.material_override != null or mesh.layers != 2:
				return false
	return true

func run() -> void:
	create_timer(60).timeout.connect(func()->void:push_error("Cart checks timed out");quit(1))
	var state := snapshot()
	expect(Cart.valid_cart(state.cart), "the native Last Cart shape has a bounded pose and two counted crates")
	var decoded:=EloriaProtocol.decode_campaign(JSON.stringify(state).to_utf8_buffer())
	expect(decoded.get("type")=="campaign", "the visual fixture uses the actual negotiated revision-two cart wire contract: "+str(decoded.get("error","valid")))
	for patch: Dictionary in [{"id":"public_cart"},{"tile":[422.5,316]},{"facing":[0,1]},
			{"footprint":[3,3]},{"route":"fight"},{"state":"rewarded"},{"tilt_deg":27},
			{"load_units":3},{"unloaded":-1},{"rope_ends":0.5},{"fulcrum_ready":1},{"holder_active":"yes"}]:
		var invalid: Dictionary = state.cart.duplicate(true)
		invalid.merge(patch,true)
		expect(not Cart.valid_cart(invalid), "a malformed or unaudited cart pose cannot manufacture physical work")
	var adapter := CoordinateAdapter.new({"metresPerTile":1.0,"serverOrigin":[435,448],"walkingHeight":2.5,"invertServerY":true})
	var works := Cart.new()
	root.add_child(works)
	var resident := [false]
	var sample := func(_point:Vector3)->float:return 2.5 if resident[0] else NAN
	works.apply_snapshot(state,adapter,"greenlight",sample)
	expect(works.native == null and not works.visible, "cold pier navigation never creates a floating rescue cart")
	resident[0] = true
	var before := JSON.stringify(state)
	works.apply_snapshot(state,adapter,"greenlight",sample)
	expect(is_instance_valid(works.native) and works.loads.size() == 2 and works.props.has("post"), "the private pier displays the approved cart, separate load and native mooring post")
	var pristine: Node3D = GlbSceneCache.instantiate(Cart.CART_ASSET)
	expect(imported_unchanged(works.native,pristine), "cart placement preserves every imported vertex, material and source-node transform")
	expect(works.cart_body.scale == Vector3.ONE and works.native.scale == pristine.scale, "the native cart keeps its unit authored size inside the five-by-three server body")
	expect(works.find_children("*","CollisionObject3D",true,false).size() == pristine.find_children("*","CollisionObject3D",true,false).size(), "the presenter adds no collider, platform or new walkable crossing")
	pristine.free()
	for key: String in ["lever","crib"]:
		expect(works.props.has(key), "the "+key+" reuses an actual separable imported timber component")
		if not works.props.has(key):continue
		var part: MeshInstance3D = works.props[key].find_children("*","MeshInstance3D",true,false)[0]
		var original: Mesh = part.get_meta("source_mesh")
		var ids: PackedInt32Array = part.get_meta("source_vertex_ids")
		var selected: Array = part.mesh.surface_get_arrays(0)
		var original_arrays: Array = original.surface_get_arrays(0)
		var submitted: Array = part.get_meta("source_arrays")
		var unchanged := ids.size()==24 and (part.get_meta("source_triangles") as Array).size()==12
		for channel: int in [Mesh.ARRAY_VERTEX,Mesh.ARRAY_NORMAL,Mesh.ARRAY_TEX_UV]:
			for index: int in ids.size():
				unchanged=unchanged and submitted[channel][index]==original_arrays[channel][ids[index]]
				if channel==Mesh.ARRAY_NORMAL:
					unchanged=unchanged and selected[channel][index].distance_to(submitted[channel][index])<0.0001
				else:
					unchanged=unchanged and selected[channel][index]==submitted[channel][index]
		expect(unchanged and part.mesh.surface_get_material(0)==original.surface_get_material(0) \
			and part.material_override==null and part.layers==2, "the "+key+" keeps original shaft triangle vertices, normals, UVs and material rather than a generated beam")
		expect(part.mesh.get_aabb().size.x>1.70 and part.mesh.get_aabb().size.x<1.72 \
			and works.props[key].scale==Vector3.ONE, "the "+key+" retains the native 1.71-metre timber length")
	var minimum := INF
	var shaft_low := INF
	var shaft_high := -INF
	var shaft_forward := -INF
	for vertex: Vector3 in works._vertices:
		var world: Vector3 = works.axle.global_transform * (vertex-Cart.RAW_AXLE)
		minimum = minf(minimum,world.y)
		if vertex.x > 2.89:
			shaft_low = minf(shaft_low,world.y-2.5)
			shaft_high = maxf(shaft_high,world.y-2.5)
			shaft_forward = maxf(shaft_forward,world.x-adapter.tile_center(422,316).x)
	expect(is_equal_approx(minimum,2.5) and shaft_low > 0.04 and shaft_high < 0.17, "rotation about the real axle puts the shaft at ankle height while native geometry touches the actual deck")
	expect(shaft_forward > 2.3 and shaft_forward < 2.5, "the shaft reaches toward the worker while staying inside the authored five-tile footprint")
	expect(works._display_tilt == 17 and works.cart_body.global_position.is_equal_approx(adapter.tile_center(422,316)+Cart.PLACEMENT_OFFSET), "reconnect starts directly at the accepted tipped pose rather than replaying the accident")
	var accepted := JSON.stringify(works.cart)
	works.set_cinematic_accident(0)
	expect(is_zero_approx(works._display_tilt) and works.cart_body.global_position.is_equal_approx(adapter.tile_center(422,316)+Cart.PLACEMENT_OFFSET+Vector3(-0.35,0,0)), "the optional cinematic starts with the actual level cart held just behind its trapped pose")
	works.set_cinematic_accident(0.5)
	expect(is_equal_approx(works._display_tilt,8.5) and JSON.stringify(works.cart)==accepted and JSON.stringify(state)==before, "the visible accident rolls and tips halfway without altering accepted rescue state")
	works.set_cinematic_accident(1)
	expect(is_equal_approx(works._display_tilt,17) and works.cart_body.global_position.is_equal_approx(adapter.tile_center(422,316)+Cart.PLACEMENT_OFFSET), "the staged accident meets the real accepted trapped pose")
	works.clear_cinematic_presentation()
	expect(works._accident_progress<0 and JSON.stringify(works.cart)==accepted, "ending the accident leaves all authoritative flags untouched")
	var first_native: Node3D = works.native
	var unloaded := state.duplicate(true)
	unloaded.cart.route = "unload"
	unloaded.cart.load_units = 1
	unloaded.cart.unloaded = 1
	works.apply_snapshot(unloaded,adapter,"greenlight",sample)
	expect(works.native == first_native and works.loads[0].visible and not works.loads[1].visible \
		and works.props.unload_1.visible and not works.props.unload_2.visible, "one accepted unloading step moves exactly one visible crate into its safe bay")
	unloaded.cart.load_units = 0
	unloaded.cart.unloaded = 2
	unloaded.cart.state = "prepared"
	works.apply_snapshot(unloaded,adapter,"greenlight",sample)
	expect(not works.loads[0].visible and not works.loads[1].visible and works.props.unload_1.visible and works.props.unload_2.visible, "both physical loads disappear only after both server-counted unloading steps")
	var still_tipped: Transform3D = works.axle.global_transform
	works._process(10)
	expect(works.axle.global_transform.is_equal_approx(still_tipped) and works.cart.state == "prepared", "elapsed rendering time cannot release a prepared cart")
	var released := unloaded.duplicate(true)
	released.cart.tile = [421,316]
	released.cart.tilt_deg = 0
	released.cart.state = "released"
	released.cart.released = true
	released.cart.holder_active = false
	works.apply_snapshot(released,adapter,"greenlight",sample)
	works._process(0.35)
	var midway: Vector3 = works.cart_body.global_position
	expect(midway.x < adapter.tile_center(422,316).x+0.4 and midway.x > adapter.tile_center(421,316).x+0.4 \
		and works._display_tilt > 0 and works._display_tilt < 17, "a committed release visibly backs and lifts the shaft through an intermediate native pose")
	works.apply_snapshot(released,adapter,"greenlight",sample)
	works._process(0.35)
	expect(works.cart_body.global_position.is_equal_approx(adapter.tile_center(421,316)+Cart.PLACEMENT_OFFSET) and is_zero_approx(works._display_tilt), "repeated snapshots do not restart or extend the accepted release movement")
	works._process(10)
	expect(works.cart_body.global_position.is_equal_approx(adapter.tile_center(421,316)+Cart.PLACEMENT_OFFSET), "the visual never predicts a second backing step or a rescue completion")
	released.cart.tile = [420,316]
	works.apply_snapshot(released,adapter,"greenlight",sample)
	works._process(1)
	expect(works.cart_body.global_position.is_equal_approx(adapter.tile_center(420,316)+Cart.PLACEMENT_OFFSET), "the second backing step also follows its committed server tile")
	works.set_cinematic_accident(0.5)
	expect(works.loads[0].visible and works.loads[1].visible and not works.props.unload_1.visible, "a local replay may show the original cargo during its clearly staged accident")
	works.clear_cinematic_presentation()
	expect(works.cart_body.global_position.is_equal_approx(adapter.tile_center(420,316)+Cart.PLACEMENT_OFFSET) \
		and is_zero_approx(works._display_tilt) and not works.loads[0].visible and works.props.unload_1.visible, "replay cleanup restores the latest released pose and actual unloaded cargo, rather than the old trapped presentation")
	for stage: String in ["treated","escorting","safe"]:
		released.cart.state = stage
		released.cart.treated=true
		released.cart.worker_safe=stage=="safe"
		works.apply_snapshot(released,adapter,"greenlight",sample)
		expect((works.labels.cart as Label3D).text == Cart.status_text(released.cart) and not works.labels.hold.visible, "the "+stage+" state displays common aid or escort proof without inventing an NPC action")
	var haul := state.duplicate(true)
	haul.cart.route = "haul"
	haul.cart.rope_ends = 1
	works.apply_snapshot(haul,adapter,"greenlight",sample)
	expect(works.labels.rope_1.visible and works.labels.rope_1.text.contains("secured") and works.labels.rope_2.text.contains("attachment 2"), "the hauling route distinguishes each server-confirmed line attachment")
	var lever := state.duplicate(true)
	lever.cart.route = "lever"
	lever.cart.fulcrum_ready = true
	works.apply_snapshot(lever,adapter,"greenlight",sample)
	expect(works.labels.fulcrum.visible and works.labels.fulcrum.text.contains("ready") and not works.labels.rope_1.visible, "the lever route identifies its prepared work post without claiming an unrelated hauling action")
	works.set_readouts_visible(false)
	var all_hidden := true
	for label: Label3D in works.labels.values():all_hidden = all_hidden and not label.visible
	expect(all_hidden and works.cart_body.visible, "hiding world readouts leaves the physical rescue setup in place")
	works.set_readouts_visible(true)
	expect(works.labels.cart.visible and works.labels.fulcrum.visible, "restoring readouts respects the current route")
	expect(JSON.stringify(state) == before, "presentation cannot mutate the incoming run or mark the worker safe")
	for invalid: String in ["inactive","travel","foreign_map","foreign_snapshot","other_chapter","missing_run","missing_cart","missing_anchor","cold_pose"]:
		works.apply_snapshot(state,adapter,"greenlight",sample)
		var row := state.duplicate(true)
		var here := "greenlight"
		match invalid:
			"inactive":row.active=false
			"travel":row.travel={"map":"twinbrook"}
			"foreign_map":here="twinbrook"
			"foreign_snapshot":row.map="twinbrook"
			"other_chapter":row.kind="bank"
			"missing_run":row.run_id=""
			"missing_cart":row.erase("cart")
			"missing_anchor":row.anchors.erase("cart_post")
			"cold_pose":resident[0]=false
		works.apply_snapshot(row,adapter,here,sample)
		expect(works.native == null and not works.visible, invalid+" clears all private cart props without touching public scenery")
		resident[0]=true
	works.apply_snapshot(state,adapter,"greenlight",sample)
	var old_native: Node3D = works.native
	var next := state.duplicate(true)
	next.run_id = "other-cart-run"
	works.apply_snapshot(next,adapter,"greenlight",sample)
	expect(works.native != old_native and works._identity == "other-cart-run", "a new run cannot inherit the old cart instance or rescue pose")
	var second := SubViewport.new()
	second.own_world_3d = true
	root.add_child(second)
	works.reparent(second)
	var old_world: World3D = works._world
	works.apply_snapshot(next,adapter,"greenlight",sample)
	expect(works._world == works.get_world_3d() and works._world != old_world, "a different World3D rebuilds all run-owned cart presentation")
	works.clear()
	expect(works.native == null and works.props.is_empty() and works.labels.is_empty() and works._vertices.is_empty(), "clear releases models, text, pose and imported vertex references")
	second.queue_free()
	await process_frame
	await process_frame
	print("campaign cart: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
