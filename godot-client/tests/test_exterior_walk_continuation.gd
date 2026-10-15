extends SceneTree

## No asset loading or network. Authoritative movement packets are reduced by
## the real ActorReducer; the fake server enforces its real 512-step prefix.
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, description: String) -> void:
	if ok:
		print("PASS: ", description)
	else:
		failures += 1
		push_error(description)

func _actor(x := 0, sequence := 0) -> Dictionary:
	return {"x":x,"y":0,"command_sequence":sequence,"alive":true}

func _begin(stream: ExteriorRegionStream, final_map := "c", target := Vector2i(600,0)) -> void:
	stream.pending_walk = {"map":final_map,"tile":target,"run":true,"routed":true,"next_map":"b"}
	stream._arm_walk_leg("a",Vector2i(600,0),_actor())

func _walk_prefixes(stream: ExteriorRegionStream, map_id: String, actor: Dictionary, target: Vector2i) -> int:
	var remaining := 512
	var renewals := 0
	while int(actor.x) < target.x and remaining > 0:
		actor = ActorReducer.apply_command(actor,22)
		remaining -= 1
		# Normal frame reduction may coalesce many authoritative commands.
		if int(actor.command_sequence) % 64 == 0 or int(actor.x) == target.x:
			var continuation := stream.take_continuation(map_id,actor)
			if not continuation.is_empty():
				_expect(continuation.tile == target and bool(continuation.run), "renewal preserves exact target and run intent")
				remaining = 512
				renewals += 1
	_expect(int(actor.x) == target.x, "one click completes a leg longer than the server's 512-step prefix")
	return renewals

func _run() -> void:
	var stream := ExteriorRegionStream.new()
	var config := {"serverOrigin":[0,0]}
	stream.links = [{"seamless":true,"ends":[
		{"map":"b","position":[600.5,0,-.5],"coordinateTransform":config},
		{"map":"c","position":[.5,0,-.5],"coordinateTransform":config}]}]
	_begin(stream)
	_expect(_walk_prefixes(stream,"a",_actor(),Vector2i(600,0)) == 1, "first road leg renews once, before exhaustion")
	_expect(not stream.pending_walk.is_empty(), "arrival at first gate keeps the far click")
	var middle := stream.take_continuation("b",_actor())
	_expect(middle.get("tile") == Vector2i(600,0), "intermediate map gets its actual road target")
	_expect(_walk_prefixes(stream,"b",_actor(),Vector2i(600,0)) == 1, "intermediate road leg also survives truncation")
	var last := stream.take_continuation("c",_actor())
	_expect(last.get("tile") == Vector2i(600,0), "final map receives the original clicked tile")
	_expect(_walk_prefixes(stream,"c",_actor(),Vector2i(600,0)) == 1, "long final continuation survives truncation")
	_expect(stream.pending_walk.is_empty(), "only exact authoritative arrival releases the intent")
	_expect(stream.take_continuation("c",_actor(600,700)).is_empty(), "completed click never sends another request")

	# Intermediate continuation chooses an open point along the next border in
	# the intermediate map's frame. Neither the stale active map nor click-frame
	# positions describe an actor who has already crossed into that map.
	var routed := ExteriorRegionStream.new()
	routed.active_map = "amberwood"
	routed._last_position = Vector3(9000,0,9000)
	routed.registry = {
		"mirrorhold": {
			"coordinateTransform": {"serverOrigin":[100,80]},
			"continentGeography": {"translation":[100,0,200]}},
		"whitehorn_range": {
			"coordinateTransform": {"serverOrigin":[0,0]},
			"continentGeography": {"translation":[140,0,240]}}}
	routed.links = [
		{"seamless":true,"ends":[
			{"map":"amberwood","position":[0.5,0,-0.5],"coordinateTransform":{"serverOrigin":[0,0]}},
			{"map":"mirrorhold","position":[0.5,0,-0.5],"coordinateTransform":{"serverOrigin":[100,80]}}]},
		{"seamless":true,"ends":[
			{"map":"mirrorhold","position":[20.5,0,-0.5],"coordinateTransform":{"serverOrigin":[100,80]},
				"crossingRuns":{"axis":"y","runs":[[120,80,90]]}},
			{"map":"whitehorn_range","position":[0.5,0,-0.5],"coordinateTransform":{"serverOrigin":[0,0]}}]}]
	routed.pending_walk = {"map":"whitehorn_range","tile":Vector2i(5,46),"run":true,
		"routed":true,"next_map":"mirrorhold","world_point":Vector3(-8000,0,-8000)}
	routed._arm_walk_leg("amberwood",Vector2i(0,0),_actor())
	var routed_middle := routed.take_continuation("mirrorhold",
		{"x":100,"y":86,"command_sequence":1,"alive":true})
	_expect(routed_middle.get("tile") == Vector2i(120,86) and bool(routed_middle.get("run",false)),
		"intermediate continuation uses fresh actor and final-map frames to choose the open crossing")
	_expect(routed.take_continuation("mirrorhold",{"x":100,"y":86,"command_sequence":1,"alive":true}).is_empty(),
		"frame-aware intermediate crossing is issued only once")
	var routed_final := routed.take_continuation("whitehorn_range",
		{"x":0,"y":0,"command_sequence":2,"alive":true})
	_expect(routed_final.get("tile") == Vector2i(5,46) and bool(routed_final.get("run",false)),
		"frame-aware crossing preserves the exact final tile and run intent")
	routed.take_continuation("whitehorn_range",{"x":5,"y":46,"command_sequence":3,"alive":true})
	_expect(routed.pending_walk.is_empty(), "authoritative final arrival clears the frame-aware continuation")
	routed.registry.erase("whitehorn_range")
	routed.pending_walk = {"map":"whitehorn_range","tile":Vector2i(5,46),"run":true,
		"routed":true,"next_map":"mirrorhold"}
	routed._arm_walk_leg("amberwood",Vector2i(0,0),_actor())
	var fallback_middle := routed.take_continuation("mirrorhold",
		{"x":100,"y":86,"command_sequence":4,"alive":true})
	_expect(fallback_middle.get("tile") == Vector2i(120,80),
		"missing destination geography keeps the surveyed gate fallback even when crossings are shipped")
	routed.free()

	_begin(stream)
	_expect(stream.take_continuation("a",_actor(100,100)).is_empty(), "short ordinary movement does not renew")
	_expect(stream.take_continuation("a",_actor(100,3000)).is_empty(), "stationary commands cannot cause retries")
	_expect(stream.take_continuation("a",_actor(101,1)).is_empty(), "actor sequence reset cannot create a huge renewal count")
	stream.pending_walk.clear()
	_expect(stream.take_continuation("a",_actor(500,700)).is_empty(), "new click/keyboard cancellation leaves no deferred movement")
	for state: String in ["in_combat","sitting","dead"]:
		_begin(stream)
		var actor := _actor(449,449)
		if state == "dead": actor.alive = false
		else: actor[state] = true
		_expect(stream.take_continuation("a",actor).is_empty() and stream.pending_walk.is_empty(), state + " cancels road continuation")
	_begin(stream)
	_expect(stream.take_continuation("unrelated_room",_actor()).is_empty() and stream.pending_walk.is_empty(),
		"an incidental doorway cannot redirect the retained click through an unrelated map")
	_begin(stream,"b",Vector2i(607,0))
	var warm_target := stream.take_continuation("b",_actor())
	_expect(warm_target.get("tile") == Vector2i(607,0) and not stream.pending_walk.has("next_map"),
		"expected final arrival starts the exact last leg with no further map transition")
	stream.take_continuation("b",_actor(100,100))
	# A warm resident adoption does not invoke clear(), unlike a cold load.
	# c has a real road back to b; accepting it would revive the old click.
	_expect(stream.take_continuation("c",_actor()).is_empty() and stream.pending_walk.is_empty(),
		"an unexpected warm transition during the final leg cancels instead of routing back")
	var state := root.get_node("AppState")
	var saved_map: String = state.get("current_map")
	_begin(stream,"b",Vector2i(607,0))
	state.set("current_map","b")
	stream.clear(true)
	_expect(not stream.pending_walk.is_empty(), "expected cold arrival preserves one-click intent after a preload miss")
	var cold_target := stream.take_continuation("b",_actor())
	_expect(cold_target.get("tile") == Vector2i(607,0) and bool(cold_target.get("run",false)),
		"expected cold arrival resumes the exact final target and run intent")
	stream.take_continuation("b",_actor(607,607))
	_expect(stream.pending_walk.is_empty(), "cold-arrival continuation completes at the exact target")
	_begin(stream)
	state.set("current_map","b")
	stream.clear()
	_expect(stream.pending_walk.is_empty(), "explicit teleport/logout clear cancels even an expected destination")
	_begin(stream)
	state.set("current_map","unrelated_room")
	stream.clear(true)
	_expect(stream.pending_walk.is_empty(), "cold unrelated map cannot inherit an expected road click")
	state.set("current_map",saved_map)
	_begin(stream,"c",Vector2i(100000,0))
	stream.pending_walk.leg_tile = Vector2i(100000,0)
	for index: int in ExteriorRegionStream.MAX_WALK_RENEWALS_PER_LEG + 1:
		stream.take_continuation("a",_actor((index+1)*448,(index+1)*448))
	_expect(stream.pending_walk.is_empty(), "one leg has a finite renewal budget")
	stream.free()
	print("exterior walk continuation: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
