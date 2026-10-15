extends SceneTree

## The manufacture queue works down its list a batch at a time, and moves on
## when the server says a batch has ended - its last mix state, with `running`
## clear, the name of what it made and how many came out.
##
## It stops instead when that state says another action interrupted the batch.
## Starting a harvest stops a mix and starting a mix stops a harvest, so a
## queue that answered an interrupted batch with its next one would end the
## harvest the player had just started, and the two would take turns.
##
## The client's requests go to a local socket and are read back off it; the
## server's answers are fed in as the packets it sends.

var failures := 0
var main: Control
var app_state: Node
var receiver: StreamPeerTCP

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	app_state = root.get_node("AppState")
	var scene: PackedScene = load("res://src/app/main.tscn") as PackedScene
	_expect(scene != null and scene.can_instantiate(), "the main scene loads")
	if failures:
		quit(failures)
		return
	main = scene.instantiate()
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	app_state.set("authenticated", true)
	var fixture: Dictionary = await _open_fixture()
	if not fixture.is_empty():
		receiver = fixture["receiver"] as StreamPeerTCP
		_check_queue()
		_close_fixture(fixture)
	main.queue_free()
	await process_frame
	print("PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _check_queue() -> void:
	var catalog: ManufacturingCatalog = main.get("manufacturing_catalog")
	var first := 0
	var second := -1
	var first_output: String = str(catalog.recipe(first).get("output", ""))
	for index: int in range(1, catalog.count()):
		if str(catalog.recipe(index).get("output", "")) != first_output:
			second = index
			break
	if not _expect(not first_output.is_empty() and second > 0,
			"the served catalog has two recipes that make different things"):
		return
	var second_output: String = str(catalog.recipe(second).get("output", ""))
	main.call("_on_manufacturing_button_pressed")
	_queue(first, 3)
	_queue(second, 2)
	_queue(first, 1)
	_take_requests()
	var queue: Array = main.get("manufacturing_queue") as Array

	main.call("_on_manufacturing_queue_start_pressed")
	_expect(_take_requests() == [[first, 3]],
		"Start asks for the first entry, all of it")
	_serve(true, 3, 0, first_output)
	_expect(_take_requests().is_empty(),
		"nothing more is asked for while that batch is running")

	# The bug this guards: every end-of-run state said the run was still
	# going, so the queue never got past its first batch.
	_serve(false, 0, 3, first_output)
	_expect(int((queue[0] as Dictionary).get("made", 0)) == 3
		and int(main.get("manufacturing_queue_index")) == 1,
		"a finished batch is credited to its entry and the queue moves on")
	_expect(_take_requests() == [[second, 2]],
		"and the next entry's batch is asked for at once")

	_serve(true, 2, 0, second_output)
	_serve(false, 0, 1, second_output, true)
	_expect(not bool(main.get("manufacturing_queue_running")),
		"a batch another action interrupted stops the queue")
	_expect(_take_requests().is_empty(),
		"rather than sending the next batch into that action")
	_expect(int((queue[1] as Dictionary).get("made", 0)) == 1
		and int(main.get("manufacturing_queue_index")) == 1,
		"the interrupted entry is credited what it made and keeps its place")
	_expect(str(main.get("manufacturing_server_status")).contains("interrupted")
		and (main.get("manufacturing_status") as Label).text.contains(
			"interrupted"),
		"the status line says mixing was interrupted: "
			+ (main.get("manufacturing_status") as Label).text)

	main.call("_on_manufacturing_queue_start_pressed")
	_expect(bool(main.get("manufacturing_queue_running"))
		and _take_requests() == [[second, 1]],
		"Start picks the interrupted entry up again, for what is left of it")

	# Mix Now cutting a queued batch short is not an interruption: the entry
	# keeps its place and the queue carries on once Mix Now's batch is done.
	main.set("selected_manufacturing_recipe", first)
	main.call("_set_manufacturing_quantity", 1)
	main.call("_mix_selected_now")
	_expect(_take_requests() == [[first, 1]], "Mix Now goes straight out")
	_serve(false, 0, 0, second_output)
	_serve(true, 1, 0, first_output)
	_expect(bool(main.get("manufacturing_queue_running"))
		and int(main.get("manufacturing_queue_index")) == 1
		and _take_requests().is_empty(),
		"the batch Mix Now cut short keeps its place while Mix Now runs")
	_serve(false, 0, 1, first_output)
	_expect(_take_requests() == [[second, 1]],
		"and is asked for again once Mix Now's batch ends")

	# An older server sends no byte after the name; that is not an
	# interruption, so the queue moves on as it always did.
	_serve(false, 0, 1, second_output, false, false)
	_expect(int((queue[1] as Dictionary).get("made", 0)) == 2
		and _take_requests() == [[first, 1]],
		"an end with no interruption byte counts as finished")
	_serve(false, 0, 1, first_output)
	_expect(not bool(main.get("manufacturing_queue_running"))
		and str(main.get("manufacturing_server_status")) == "Queue finished.",
		"and the queue finishes at the end of its list: "
			+ str(main.get("manufacturing_server_status")))
	main.call("_on_manufacturing_queue_clear_pressed")

func _queue(recipe: int, wanted: int) -> void:
	main.set("selected_manufacturing_recipe", recipe)
	main.call("_set_manufacturing_quantity", wanted)
	main.call("_enqueue_selected")

## A mix state as the server sends it: the byte after the name's terminator
## is `interrupted`, and `with_flag` false leaves it off as an older server did.
func _serve(running: bool, remaining: int, made: int, output: String,
		interrupted := false, with_flag := true) -> void:
	var payload := PackedByteArray([0, 1 if running else 0, 0, 0, 0, 0])
	payload.encode_u16(2, remaining)
	payload.encode_u16(4, made)
	payload.append_array(output.to_utf8_buffer())
	payload.append(0)
	if with_flag:
		payload.append(1 if interrupted else 0)
	app_state.call("_on_packet", EloriaProtocol.ServerMessage.ELORIA_MIX_STATE,
		payload)

## The mix requests sent since the last call, each as [recipe, wanted].
func _take_requests() -> Array:
	var bytes: PackedByteArray = _take()
	var found: Array = []
	var offset := 0
	while offset + 3 <= bytes.size():
		var length: int = bytes.decode_u16(offset + 1)
		if bytes[offset] == EloriaProtocol.ClientMessage.ELORIA_MIX_REQUEST:
			found.append([bytes.decode_u16(offset + 3),
				bytes.decode_u16(offset + 5)])
		offset += 2 + length
	return found

## Everything the client has sent since the last call. Loopback delivery is
## quick but not instant, so an empty read waits briefly before believing it.
func _take() -> PackedByteArray:
	for attempt: int in range(25):
		receiver.poll()
		if receiver.get_available_bytes() > 0:
			break
		OS.delay_usec(2000)
	var available: int = receiver.get_available_bytes()
	if available <= 0:
		return PackedByteArray()
	return receiver.get_data(available)[1] as PackedByteArray

## Points the Network singleton at a local socket so sent frames can be read.
func _open_fixture() -> Dictionary:
	var network: Node = root.get_node("Network")
	var old_peer: StreamPeerTCP = network.get("_peer") as StreamPeerTCP
	var peer := StreamPeerTCP.new()
	var server := TCPServer.new()
	if not _expect(server.listen(0, "127.0.0.1") == OK, "the local socket listens"):
		return {}
	network.set_process(false)
	network.set("_peer", peer)
	peer.connect_to_host("127.0.0.1", server.get_local_port())
	for attempt: int in range(20):
		peer.poll()
		if server.is_connection_available():
			break
		await process_frame
	var taken: StreamPeerTCP = server.take_connection()
	var fixture: Dictionary = {"server": server, "peer": peer,
		"receiver": taken, "old_peer": old_peer}
	if not _expect(taken != null, "the local socket connects"):
		_close_fixture(fixture)
		return {}
	peer.poll()
	return fixture

func _close_fixture(fixture: Dictionary) -> void:
	var network: Node = root.get_node("Network")
	(fixture["peer"] as StreamPeerTCP).disconnect_from_host()
	if fixture["receiver"] != null:
		(fixture["receiver"] as StreamPeerTCP).disconnect_from_host()
	(fixture["server"] as TCPServer).stop()
	network.set("_peer", fixture["old_peer"])
	network.set_process(true)

func _expect(condition: bool, label: String) -> bool:
	if not condition:
		failures += 1
		push_error(label)
	return condition
