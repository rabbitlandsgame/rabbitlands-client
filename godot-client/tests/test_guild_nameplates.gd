extends SceneTree
## Feed the actor refresh used by guild creation through the real UI, including
## REMOVE_ACTOR and its replacement arriving before the next presentation pass.

var failures := 0
var checks := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 720)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.login_panel.hide()
	main.game_view.show()
	var state := root.get_node("AppState")
	state.authenticated = true
	state.local_actor_id = 91
	main.adapter = CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})
	for id: int in [91, 92]:
		state._on_packet(51, _actor_packet(id, ""))
		var actor := ReplicatedActor3D.new()
		main.world_root.add_child(actor)
		actor.configure(state.actors[id], main.adapter, {}, {}, {}, false)
		main.actor_nodes[id] = actor
	main._sync_world()
	_expect(main.overhead_player_name.text == "Alice", "guildless local name")
	var remote: ReplicatedActor3D = main.actor_nodes[92]
	var plate: Label3D = remote.get_node("Nameplate")
	_expect(plate.text == "Alice", "guildless remote name")
	remote.set_overhead_fade(0.5)

	for tag: String in ["ELO", "TEST", ""]:
		# The server re-sends the actor on creation, acceptance, tag changes and
		# removal. Coalesce both packets, just as a single socket read does.
		for id: int in [91, 92]:
			state._on_packet(6, PackedByteArray([id, 0]))
			state._on_packet(51, _actor_packet(id, tag))
		main._sync_world(state.take_changed_actors())
		var expected := "Alice" + ("  [%s]" % tag if not tag.is_empty() else "")
		_expect(main.overhead_player_name.text == expected, "local tag updates to '%s'" % tag)
		_expect(plate.text == expected, "remote tag updates to '%s'" % tag)
		_expect(main.actor_nodes[92] == remote, "a tag refresh reuses the remote body")
		_expect(is_equal_approx(plate.modulate.a, 0.5), "tag refresh preserves distance fade")

	state.actors[92].name_colour = 3
	state.mark_actor_changed(92)
	main._sync_world(state.take_changed_actors())
	_expect(plate.modulate.is_equal_approx(Color(EloriaProtocol.el_text_colour(3), 0.5)),
		"a name colour refresh preserves the distance fade")

	main.queue_free()
	await process_frame
	print("Guild nameplates: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func _actor_packet(id: int, tag: String) -> PackedByteArray:
	# Enhanced actor header from the protocol fixture, followed by the server's
	# legacy display-name encoding and ordinary actor tail.
	var payload := "5b000a000a000000000001000001020304050b001e14071400120001".hex_decode()
	payload.encode_u16(0, id)
	payload.append_array("Alice".to_ascii_buffer())
	if not tag.is_empty():
		payload.append_array(PackedByteArray([32, 131]))
		payload.append_array(tag.to_ascii_buffer())
	payload.append_array(PackedByteArray([0, 0, 64, 255, 6, 0]))
	return payload

func _expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)
