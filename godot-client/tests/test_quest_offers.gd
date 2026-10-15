extends SceneTree

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_expect(EloriaProtocol.CLIENT_CAPABILITIES.has("quest_offers_v1"), "capability advertised")
	var payload := PackedByteArray([2, 0, 10, 0, 11, 0])
	var decoded := EloriaProtocol.decode_server(199, payload)
	_expect(decoded.get("actor_ids") == [10, 11], "server actor ids decoded")
	_expect(EloriaProtocol.decode_server(199, PackedByteArray([1, 0])).type == "invalid", "truncated packet refused")
	var state: Node = root.get_node("AppState")
	state.call("_on_packet", 199, payload)
	_expect((state.get("quest_offer_actors") as Dictionary).has(10), "snapshot stored")
	state.call("_on_packet", 199, PackedByteArray([0, 0]))
	_expect((state.get("quest_offer_actors") as Dictionary).is_empty(), "empty snapshot removes offers")
	state.call("_on_packet", 199, payload)
	state.call("_on_packet", 6, PackedByteArray([10, 0]))
	_expect(not (state.get("quest_offer_actors") as Dictionary).has(10), "actor removal forgets offer")
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	actor.configure({"actor_id": 10, "name": "Nash", "kind": 2, "x": 0, "y": 0,
		"rotation": 0, "health": 20, "max_health": 20}, CoordinateAdapter.new({"metresPerTile": 1.0}), {}, {})
	actor.set_occupation("Wayfinder")
	actor.set_quest_available(true)
	var marker := actor.get_node("QuestOfferMarker") as Label3D
	_expect(marker.text == "!" and marker.visible and marker.offset.y > 0, "gold exclamation appears above head")
	_expect((actor.get_node("OccupationLine") as Label3D).text == "<Wayfinder>", "Nash has the Wayfinder occupation")
	actor.set_nameplate_visible(false)
	_expect(marker.visible, "quest offer survives hidden names")
	actor.set_drawn(false)
	_expect(not marker.visible, "out of range actor hides marker")
	actor.set_quest_available(false)
	actor.set_drawn(true)
	_expect(not marker.visible, "accepted quest stays hidden after actor returns")
	actor.set_quest_available(true)
	_expect(marker.visible, "newly available quest shows again")
	actor.queue_free()
	await process_frame
	print("quest offer tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _expect(ok: bool, description: String) -> void:
	if not ok:
		failures += 1
		push_error(description)
