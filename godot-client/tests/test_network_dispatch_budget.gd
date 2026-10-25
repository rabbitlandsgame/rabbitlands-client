extends SceneTree
var failures := 0
func _init() -> void: run.call_deferred()
func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error(label)
func frame(sequence: int) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.resize(4)
	payload.encode_u32(0, sequence)
	return EloriaProtocol.encode(EloriaProtocol.ServerMessage.PONG, payload)
func run() -> void:
	# Load after AppState has entered the tree: the shipping network script
	# contains context checks against that autoload.
	var network: Variant = load("res://tests/fixtures/buffered_network_client.gd").new()
	root.add_child(network)
	network.set_process(false)
	var received: Array[int] = []
	network.packet_received.connect(func(_command: int, payload: PackedByteArray) -> void:
		received.append(payload.decode_u32(0))
		OS.delay_usec(1600))
	var burst := PackedByteArray()
	for i in 40: burst.append_array(frame(i))
	var partial := frame(40)
	burst.append_array(partial.slice(0, 5))
	network._rx = burst
	network._drain_packets()
	var first_count := received.size()
	expect(first_count > 0 and first_count < 40, "expensive packet callbacks yield with data still queued")
	network._drain_packets()
	expect(received.size() == first_count, "late read cannot renew the same-frame allowance")
	var deadline := Time.get_ticks_msec() + 10000
	while received.size() < 40 and Time.get_ticks_msec() < deadline:
		await process_frame
		network._read_link() # Empty transport: queued bytes must still drain.
	expect(received == range(40), "every complete queued packet resumes in wire order without another socket read")
	expect(network._rx == partial.slice(0, 5), "partial final packet is retained exactly")
	network._rx.append_array(partial.slice(5))
	await process_frame
	await process_frame
	network._read_link()
	expect(received == range(41) and network._rx.is_empty(), "the final fragment completes without duplication")
	network.free()
	print("network dispatch budget: ", failures, " failures")
	quit(failures)
