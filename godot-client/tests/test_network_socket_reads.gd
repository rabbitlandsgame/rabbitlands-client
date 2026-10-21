extends SceneTree
## Guards how the game socket is read, over a real loopback TLS session.
##
## StreamPeerTLS decrypts one TLS record per poll() and the client polled once
## a frame, so it took at most one record a frame. The server writes a record
## per 50-ms flush plus one for every immediate send, so at 20 FPS a busy view
## arrived faster than it was read and fell further behind every second. Now
## one read takes every waiting record, a second read late in the frame catches
## what arrived during it, and packets keep their order across records.

const CMD := 250
const CERTIFICATE_PATH := "user://test_network_socket_reads.crt"

class LateProbe extends Node:
	## Runs after Network's _process (tree order) and before its late read.
	var write: Callable
	var check: Callable
	var done := false
	func _process(_delta: float) -> void:
		if write.is_valid():
			write.call()
			write = Callable()
			_check.call_deferred()
	func _check() -> void:
		check.call()
		done = true

var failures := 0
var received: Array[int] = []

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	var crypto := Crypto.new()
	var key := crypto.generate_rsa(2048)
	var certificate := crypto.generate_self_signed_certificate(key,
		"CN=127.0.0.1,O=Rabbit Lands Test,C=US")
	_expect(certificate.save(CERTIFICATE_PATH) == OK, "the test certificate is saved")
	var server := TCPServer.new()
	_expect(server.listen(0, "127.0.0.1") == OK, "the loopback TLS fixture listens")
	var network: Node = (load("res://src/network/network_client.gd") as GDScript).new()
	network.name = "SocketReadNetwork"
	root.add_child(network)
	network.packet_received.connect(func(command: int, payload: PackedByteArray) -> void:
		if command == CMD:
			received.append(payload.decode_u32(0)))
	_expect(network.call("connect_to_server", "127.0.0.1", server.get_local_port(), true,
		CERTIFICATE_PATH) == OK, "the client starts a TLS connection")
	var tls := StreamPeerTLS.new()
	var accepted := false
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		if not accepted and server.is_connection_available():
			accepted = tls.accept_stream(server.take_connection(),
				TLSOptions.server(key, certificate)) == OK
		if accepted:
			tls.poll()
			if tls.get_status() == StreamPeerTLS.STATUS_CONNECTED \
					and str(network.get("_state")) == "connected":
				break
		await process_frame
	if not _expect(str(network.get("_state")) == "connected" and network.call("is_secure"),
			"the TLS session is established"):
		_finish(network, server, tls)
		return
	_expect(network.get("_no_delay_set") == true,
		"TCP no-delay is set on the connection's socket")
	var late_read: Node = network.get("_late_read")
	_expect(late_read != null and late_read.process_priority > 0,
		"the late read runs after the default process priority")

	# Thirteen records waiting before the client reads; the last frame is split
	# across two of them. One read takes them all, in order.
	network.set_process(false)
	var expected: Array[int] = []
	for sequence in 12:
		tls.put_data(_frame(sequence))
		expected.append(sequence)
	var split := _frame(12)
	tls.put_data(split.slice(0, 5))
	tls.put_data(split.slice(5))
	expected.append(12)
	OS.delay_msec(100)
	received.clear()
	network.call("_process", 0.0)
	_expect(received == expected,
		"one read takes every waiting TLS record in order: %s" % [received])

	# Paused, the network reads nothing - neither read runs.
	received.clear()
	tls.put_data(_frame(200))
	OS.delay_msec(50)
	await process_frame
	await process_frame
	_expect(received.is_empty(), "set_process(false) stops the late read too")
	network.set_process(true)
	await process_frame
	_expect(received == [200], "resumed processing reads what waited: %s" % [received])

	# A packet arriving after the frame's first read is dispatched before the
	# frame's deferred calls - where Main presents the world - not a frame later.
	received.clear()
	var seen_in_frame := [false]
	var probe := LateProbe.new()
	probe.write = func() -> void:
		tls.put_data(_frame(300))
		OS.delay_msec(50)
	probe.check = func() -> void:
		seen_in_frame[0] = received.has(300)
	root.add_child(probe)
	deadline = Time.get_ticks_msec() + 3000
	while not probe.done and Time.get_ticks_msec() < deadline:
		await process_frame
	_expect(probe.done and bool(seen_in_frame[0]),
		"a packet arriving mid-frame is dispatched before that frame's deferred world sync")
	probe.queue_free()
	_finish(network, server, tls)

func _frame(sequence: int) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.resize(4)
	payload.encode_u32(0, sequence)
	return EloriaProtocol.encode(CMD, payload)

func _finish(network: Node, server: TCPServer, tls: StreamPeerTLS) -> void:
	network.call("disconnect_from_server")
	tls.disconnect_from_stream()
	server.stop()
	network.queue_free()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(CERTIFICATE_PATH))
	await process_frame
	print("network socket read tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
