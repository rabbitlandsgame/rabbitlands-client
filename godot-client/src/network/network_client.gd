class_name EloriaNetworkClient
extends Node

const Diagnostics = preload("res://src/diagnostics/client_diagnostics.gd")

signal connection_state_changed(state: String)
signal packet_received(command: int, payload: PackedByteArray)
signal protocol_error(message: String)
signal magic_selection_completed
signal coordinate_intents_invalidated
signal coordinate_route_cancelled
signal movement_requested(tile: Vector2i)
const CoordinateContext = preload("res://src/network/coordinate_context.gd")
var coordinates = CoordinateContext.new()
var magic_pending: Dictionary = {}
var magic_scope := ""
var magic_token: Dictionary = {}
var coordinate_registry_error := ""

func configure_coordinate_profiles(catalog: Variant, names: Variant = {}, registry_maps: Variant = {}) -> Dictionary:
	var result: Dictionary
	if not catalog is Dictionary or not names is Dictionary or not registry_maps is Dictionary:
		result = {"ok": false, "error": "coordinate_registry_shape"}
	else:
		result = coordinates.configure(catalog, names)
		if result.ok:
			for map_id: Variant in registry_maps:
				var entry: Variant = registry_maps[map_id]
				if not entry is Dictionary:
					continue
				var transform: Variant = entry.get("coordinateTransform", {})
				if not transform is Dictionary:
					continue
				var minimum: Variant = _registry_tile_min(transform.get("serverTileMin", [0, 0]))
				if minimum == null or minimum != [0, 0] and (not coordinates.expected.has(map_id) or coordinates.expected[map_id].serverTileMin != minimum):
					result = {"ok": false, "error": "coordinate_catalog_offset_missing_or_mismatched"}
					break
	coordinate_registry_error = "" if result.ok else str(result.error)
	return result

## A registry map's serverTileMin as integers, as the published profiles hold it
## (CoordinateProfile.from_registry). The registry is read with JSON.parse_string,
## which makes every number a float, and Godot compares arrays element by element
## including type, so a registry's [0.0, 0.0] is not [0, 0]. Null for anything
## that is not two integral numbers.
static func _registry_tile_min(value: Variant) -> Variant:
	if not value is Array or value.size() != 2:
		return null
	var result: Array = []
	for item: Variant in value:
		if not typeof(item) in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(item)) or floor(float(item)) != float(item):
			return null
		result.append(int(item))
	return result

func clear_coordinate_intents() -> void:
	magic_pending.clear()
	magic_scope = ""
	magic_token.clear()
	coordinate_intents_invalidated.emit()

func _reset_coordinate_session() -> void:
	coordinates.reset()
	clear_coordinate_intents()
	coordinate_route_cancelled.emit()
	_rx.clear()

func fail_coordinate_context(reason: String) -> void:
	_reconnect_enabled = false
	_drop_connection(reason)

func begin_magic_selection(request: Dictionary, scope: String) -> void:
	magic_pending = request.duplicate(true)
	magic_scope = scope
	magic_token = coordinates.token()

func _send_map_payload(command: int, payload: PackedByteArray) -> Error:
	if not coordinates.selected:
		return send_frame(EloriaProtocol.encode(command, payload))
	if not coordinates.ready():
		return ERR_UNCONFIGURED
	var framed: Dictionary = EloriaProtocol.map_command(coordinates.epoch, command, payload)
	return send_frame(framed.frame) if framed.ok else ERR_INVALID_PARAMETER

func magic_request(data: Dictionary) -> Error:
	if coordinates.selected:
		if not coordinates.ready():
			return ERR_UNCONFIGURED
		if data.has("x") or data.has("y"):
			var valid: Dictionary = coordinates.logical_point(coordinates.map_id, data.get("x"), data.get("y"))
			if not valid.ok:
				return ERR_INVALID_PARAMETER
	if data.get("op") == "cast":
		Diagnostics.record("spell_cast_requested", {"spell_id": int(data.get("id", -1)),
			"power": int(data.get("power", 1)), "target_actor_id": int(data.get("target_id", -1))})
	return _send_map_payload(202, JSON.stringify(data).to_utf8_buffer())

func _finish_magic_selection(selection: Dictionary) -> Error:
	if coordinates.selected and not coordinates.matches(magic_token):
		clear_coordinate_intents()
		return ERR_INVALID_PARAMETER
	var request := magic_pending.duplicate()
	var captured := coordinates.token()
	request.merge(selection, true)
	magic_pending.clear()
	magic_selection_completed.emit()
	if not coordinates.matches(captured):
		return ERR_INVALID_PARAMETER
	return magic_request(request)


const PROTOCOL_MAJOR := 10
const PROTOCOL_MINOR := 31
const ClientRelease = preload("res://src/updates/release.gd")
static var client_version: PackedByteArray = PackedByteArray([1, 9, 7, 0])

func _send_release_identity() -> void:
	var identity := ClientRelease.read_json("res://data/client_release.json")
	var history: Array = identity.get("ancestors", [])
	var offset := 0
	while true:
		var end := mini(offset + 512, history.size())
		var body := {"schema": 1, "commit": identity.get("commit", ""),
			"platform": identity.get("platform", "source"),
			"distribution": ClientRelease.update_owner(identity),
			"ancestors": history.slice(offset, end), "offset": offset,
			"complete": end == history.size()}
		if send_frame(EloriaProtocol.encode(205, JSON.stringify(body).to_utf8_buffer())) != OK:
			return
		if end == history.size():
			return
		offset = end

## The legacy client sends a heartbeat every 25 seconds because a server may
## drop a connection that has been silent for 30. Eloria's server closes a
## logged-in connection after `client_idle_timeout_seconds`, which exists so a
## half-open socket cannot hold a character hostage; this is what keeps a
## parked client on the right side of it.
const HEARTBEAT_INTERVAL_MSEC := 25000
## Backoff for an unexpected drop. A deliberate disconnect never reconnects.
const RECONNECT_DELAYS_MSEC: Array[int] = [1000, 2000, 4000, 8000, 15000]

signal reconnect_progress(attempt: int, total: int, delay_msec: int)

var _peer := StreamPeerTCP.new()
var _tls := StreamPeerTLS.new()
var _rx := PackedByteArray()
var _state := "disconnected"
var _host := ""
var _port := 0
var _reconnect_enabled := false
var _reconnect_attempt := 0
var _reconnect_at_msec := 0
var _last_heartbeat_msec := 0

## Whether this session wraps the socket in TLS. The protocol is identical
## either way: only the bytes between this client and the socket change, so
## nothing above `send_frame` and `_drain_packets` knows the difference.
var _secure := true
## A certificate to trust in addition to the system store. A development
## server signs its own certificate, which no trust store will ever accept;
## pointing at that file is what lets a laptop connect without turning
## verification off for real servers too.
var _trusted_certificate_path := ""
var _handshaking := false

## True once the socket is usable for protocol traffic. With TLS that means
## the handshake finished, not merely that TCP connected.
func _link_ready() -> bool:
	if _secure:
		return _tls.get_status() == StreamPeerTLS.STATUS_CONNECTED
	return _peer.get_status() == StreamPeerTCP.STATUS_CONNECTED

func _link() -> StreamPeer:
	return _tls if _secure else _peer

func connect_to_server(host: String, port: int, secure := true,
		trusted_certificate_path := "") -> Error:
	Diagnostics.record("connection_requested", {"host": host, "port": port, "tls": secure})
	_reset_coordinate_session()
	_host = host
	_port = port
	_secure = secure
	_trusted_certificate_path = trusted_certificate_path
	_handshaking = false
	_set_state("connecting")
	var error := _peer.connect_to_host(host, port)
	if error != OK:
		Diagnostics.record("connection_start_failed", {"error": error_string(error)})
		_set_state("disconnected")
	return error

func is_secure() -> bool:
	return _secure and _link_ready()

## Starts the TLS handshake over the freshly opened TCP socket.
func _begin_handshake() -> bool:
	var options: TLSOptions = null
	if not _trusted_certificate_path.is_empty():
		var certificate := X509Certificate.new()
		if certificate.load(_trusted_certificate_path) != OK:
			_drop_connection("tls_certificate_unreadable")
			return false
		options = TLSOptions.client(certificate)
	else:
		options = TLSOptions.client()
	# The common name is checked against the certificate, so a server whose
	# certificate does not name the host the player typed is refused rather
	# than silently accepted.
	if _tls.connect_to_stream(_peer, _host, options) != OK:
		_drop_connection("tls_handshake_failed")
		return false
	_handshaking = true
	_set_state("securing")
	return true

## A disconnect the player asked for. Cancels any pending reconnect, so the
## client does not fight the person who just pressed the button.
func disconnect_from_server() -> void:
	_reset_coordinate_session()
	_reconnect_enabled = false
	_reconnect_attempt = 0
	_reconnect_at_msec = 0
	if _secure:
		_tls.disconnect_from_stream()
	_handshaking = false
	_peer.disconnect_from_host()
	_rx.clear()
	_set_state("disconnected")

func is_reconnecting() -> bool:
	return _reconnect_at_msec > 0

func reconnect_attempt() -> int:
	return _reconnect_attempt

## Rebuilds authoritative state on a connection whose continuity is in doubt.
## Actors, statistics and inventory are the three snapshots the server will
## resend on request; everything else follows from them.
func request_resync() -> Error:
	var actors_error: Error = send_frame(EloriaProtocol.encode(
		EloriaProtocol.ClientMessage.SEND_ME_MY_ACTORS))
	var stats_error: Error = send_frame(EloriaProtocol.encode(
		EloriaProtocol.ClientMessage.SEND_MY_STATS))
	var inventory_error: Error = send_frame(EloriaProtocol.encode(
		EloriaProtocol.ClientMessage.SEND_MY_INVENTORY))
	if actors_error != OK:
		return actors_error
	if stats_error != OK:
		return stats_error
	return inventory_error

## Called when the socket drops without the player asking for it.
func _schedule_reconnect() -> void:
	if not _reconnect_enabled or _host.is_empty():
		return
	if _reconnect_attempt >= RECONNECT_DELAYS_MSEC.size():
		_reconnect_enabled = false
		_reconnect_at_msec = 0
		return
	var delay: int = RECONNECT_DELAYS_MSEC[_reconnect_attempt]
	_reconnect_attempt += 1
	_reconnect_at_msec = Time.get_ticks_msec() + delay
	_set_state("reconnecting")
	reconnect_progress.emit(_reconnect_attempt, RECONNECT_DELAYS_MSEC.size(), delay)

func _drop_connection(reason: String) -> void:
	Diagnostics.record("connection_dropped", {"reason": reason})
	_reset_coordinate_session()
	protocol_error.emit(reason)
	if _secure:
		_tls.disconnect_from_stream()
	_handshaking = false
	_peer.disconnect_from_host()
	_rx.clear()
	_set_state("disconnected")
	_schedule_reconnect()

func send_frame(frame: PackedByteArray, sensitive := false) -> Error:
	if not _link_ready():
		return ERR_UNCONFIGURED
	# hex_encode() allocates a string for every outgoing packet; print_debug is
	# a no-op outside debug builds but its arguments were evaluated regardless.
	if not sensitive and OS.is_debug_build():
		print_debug("protocol tx bytes=", frame.hex_encode())
	return _link().put_data(frame)

func login(username: String, password: String) -> Error:
	Diagnostics.record("login_requested")
	if not coordinate_registry_error.is_empty():
		protocol_error.emit(coordinate_registry_error)
		return ERR_INVALID_DATA
	var error := send_frame(EloriaProtocol.login(username, password), true)
	Diagnostics.record("login_sent", {"error": error_string(error)})
	return error

func move_to(tile: Vector2i, run := false) -> Error:
	if not magic_pending.is_empty() and magic_scope in ["burst", "location"]:
		return _finish_magic_selection({"x": tile.x, "y": tile.y})
	var error: Error = (send_frame(EloriaProtocol.move_to(tile.x, tile.y, run))
		if not coordinates.selected else _send_point(6 if run else 1, tile))
	if error == OK:
		movement_requested.emit(tile)
	return error

func _send_point(command: int, tile: Vector2i) -> Error:
	if not coordinates.ready():
		return ERR_UNCONFIGURED
	var converted: Dictionary = coordinates.logical_point(coordinates.map_id, tile.x, tile.y)
	if not converted.ok:
		return ERR_INVALID_PARAMETER
	var payload := PackedByteArray()
	payload.resize(4)
	payload.encode_u16(0, converted.tile.x)
	payload.encode_u16(2, converted.tile.y)
	return _send_map_payload(command, payload)

func set_sitting(sitting: bool) -> Error:
	return send_frame(EloriaProtocol.set_sitting(sitting))

func turn(left: bool) -> Error:
	return send_frame(EloriaProtocol.turn(left))

func send_client_capabilities() -> Error:
	return send_frame(EloriaProtocol.client_capabilities())

func send_chat(text: String) -> Error:
	return send_frame(EloriaProtocol.chat(text))

func set_active_channel(slot: int) -> Error:
	return send_frame(EloriaProtocol.set_active_channel(slot))

func locate_me() -> Error:
	return send_frame(EloriaProtocol.locate_me())

func request_server_date() -> Error:
	return send_frame(EloriaProtocol.get_date())

func request_server_time() -> Error:
	return send_frame(EloriaProtocol.get_time())

func send_private_message(text: String) -> Error:
	return send_frame(EloriaProtocol.private_message(text))

func touch_actor(actor_id: int) -> Error:
	if not magic_pending.is_empty() and magic_scope == "target":
		return _finish_magic_selection({"target_id": actor_id})
	return send_frame(EloriaProtocol.touch_actor(actor_id))

func respond_to_npc(actor_id: int, response_id: int) -> Error:
	return send_frame(EloriaProtocol.npc_response(actor_id, response_id))

func look_at_inventory_item(slot: int) -> Error:
	return send_frame(EloriaProtocol.look_at_inventory_item(slot))

func use_inventory_item(slot: int) -> Error:
	return send_frame(EloriaProtocol.use_inventory_item(slot))

func fire_missile_at_object(x: int, y: int) -> Error:
	if coordinates.selected:
		return _send_point(51, Vector2i(x, y))
	return send_frame(EloriaProtocol.fire_missile_at_object(x, y))

func what_quest_is_this_id(quest_id: int) -> Error:
	return send_frame(EloriaProtocol.what_quest_is_this_id(quest_id))

func do_emote(name: String) -> Error:
	return send_frame(EloriaProtocol.do_emote(name))

func item_on_item(source_slot: int, target_slot: int) -> Error:
	return send_frame(EloriaProtocol.item_on_item(source_slot, target_slot))

func move_inventory_item(source: int, destination: int) -> Error:
	return send_frame(EloriaProtocol.move_inventory_item(source, destination))

func cast_spell(sigils: Array[int], power: int = 0) -> Error:
	return send_frame(EloriaProtocol.cast_spell(sigils, power))

func popup_reply(popup_id: int, answers: Dictionary) -> Error:
	return send_frame(EloriaProtocol.popup_reply(popup_id, answers))

func harvest(object_id: int) -> Error:
	return send_frame(EloriaProtocol.harvest(object_id))

func use_map_object(object_id: int) -> Error:
	return send_frame(EloriaProtocol.use_map_object(object_id))

func tutorial_ui(action: int) -> Error:
	if action not in [1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]:
		return ERR_INVALID_PARAMETER
	return send_frame(EloriaProtocol.encode(
		EloriaProtocol.ClientMessage.ELORIA_TUTORIAL_UI, PackedByteArray([action])))

func look_at_ground_item(slot: int) -> Error:
	return send_frame(EloriaProtocol.look_at_ground_item(slot))

func look_at_player(actor_id: int) -> Error:
	return send_frame(EloriaProtocol.look_at_player(actor_id))

func look_at_map_object(object_id: int) -> Error:
	return send_frame(EloriaProtocol.look_at_map_object(object_id))

func attack_actor(actor_id: int) -> Error:
	return send_frame(EloriaProtocol.attack_actor(actor_id))

func trade_with(actor_id: int) -> Error:
	return send_frame(EloriaProtocol.trade_with(actor_id))

func put_inventory_on_trade(source_slot: int, quantity: int) -> Error:
	return send_frame(EloriaProtocol.put_inventory_on_trade(source_slot, quantity))

func remove_trade_item(offer_slot: int, quantity: int) -> Error:
	return send_frame(EloriaProtocol.remove_trade_item(offer_slot, quantity))

func accept_trade(destinations: PackedByteArray = PackedByteArray()) -> Error:
	return send_frame(EloriaProtocol.accept_trade(destinations))

func reject_trade() -> Error:
	return send_frame(EloriaProtocol.reject_trade())

func exit_trade() -> Error:
	return send_frame(EloriaProtocol.exit_trade())

func look_at_trade_item(offer_slot: int, other: bool) -> Error:
	return send_frame(EloriaProtocol.look_at_trade_item(offer_slot, other))

func get_storage_category(category_id: int) -> Error:
	return send_frame(EloriaProtocol.get_storage_category(category_id))

func deposit_storage(inventory_slot: int, quantity: int) -> Error:
	return send_frame(EloriaProtocol.deposit_storage(inventory_slot, quantity))

func withdraw_storage(position: int, quantity: int) -> Error:
	return send_frame(EloriaProtocol.withdraw_storage(position, quantity))

func look_at_storage_item(position: int) -> Error:
	return send_frame(EloriaProtocol.look_at_storage_item(position))

func inspect_bag(bag_id: int) -> Error:
	return send_frame(EloriaProtocol.inspect_bag(bag_id))

func close_bag() -> Error:
	return send_frame(EloriaProtocol.close_bag())

func pick_up_ground_item(position: int, quantity: int) -> Error:
	return send_frame(EloriaProtocol.pick_up_ground_item(position, quantity))

func drop_inventory_item(slot: int, quantity: int) -> Error:
	return send_frame(EloriaProtocol.drop_inventory_item(slot, quantity))

func get_knowledge_info(index: int) -> Error:
	return send_frame(EloriaProtocol.get_knowledge_info(index))

func manufacture(ingredients: Array[Dictionary], wanted: int = 1) -> Error:
	return send_frame(EloriaProtocol.manufacture(ingredients, wanted))

func mix_request(recipe_index: int, wanted: int, from_storage: bool) -> Error:
	return send_frame(EloriaProtocol.mix_request(recipe_index, wanted, from_storage))

func tool_request(name: String) -> Error:
	return send_frame(EloriaProtocol.tool_request(name))

func create_character(username: String, password: String, appearance: Dictionary,
		class_id := 0) -> Error:
	return send_frame(EloriaProtocol.create_character(
		username, password, appearance, class_id), true)

func _process(_delta: float) -> void:
	if _reconnect_at_msec > 0 and Time.get_ticks_msec() >= _reconnect_at_msec:
		_reset_coordinate_session()
		_reconnect_at_msec = 0
		_set_state("connecting")
		# A reconnect gets a fresh TLS session. Reusing the old one would try
		# to resume a handshake against a socket that no longer exists.
		_handshaking = false
		if _secure:
			_tls.disconnect_from_stream()
		if _peer.connect_to_host(_host, _port) != OK:
			_set_state("disconnected")
			_schedule_reconnect()
			return
	_peer.poll()
	var status := _peer.get_status()
	if status == StreamPeerTCP.STATUS_ERROR:
		_drop_connection("socket_error")
		return
	if status != StreamPeerTCP.STATUS_CONNECTED:
		if _state == "connected" or _state == "securing":
			# The peer closed the socket without an error status.
			_drop_connection("connection_closed")
		return

	# TCP is up. A secure session is not usable until the handshake finishes,
	# so the opening frames wait behind it rather than being written in the
	# clear onto a socket that is about to become a TLS stream.
	if _secure:
		if not _handshaking and _state != "connected":
			if not _begin_handshake():
				return
		_tls.poll()
		match _tls.get_status():
			StreamPeerTLS.STATUS_HANDSHAKING:
				return
			StreamPeerTLS.STATUS_ERROR:
				_drop_connection("tls_handshake_failed")
				return
			StreamPeerTLS.STATUS_ERROR_HOSTNAME_MISMATCH:
				# Never retried: a certificate for the wrong host is the exact
				# case encryption exists to catch, so reconnecting into it
				# would be answering the alarm by silencing it.
				_reconnect_enabled = false
				_drop_connection("tls_hostname_mismatch")
				return
			StreamPeerTLS.STATUS_DISCONNECTED:
				if _state == "connected":
					_drop_connection("connection_closed")
				return

	if _state != "connected":
		_reconnect_attempt = 0
		_reconnect_enabled = true
		_handshaking = false
		_last_heartbeat_msec = Time.get_ticks_msec()
		# Matches the legacy connection lifecycle. Server currently tolerates/ignores version metadata.
		send_frame(EloriaProtocol.version(PROTOCOL_MAJOR, PROTOCOL_MINOR, client_version))
		_send_release_identity()
		send_frame(EloriaProtocol.encode(EloriaProtocol.ClientMessage.SEND_OPENING_SCREEN))
		_set_state("connected")
	_send_due_heartbeat()
	var link := _link()
	var available := link.get_available_bytes()
	if available > 0:
		var result := link.get_data(available)
		if result[0] != OK:
			protocol_error.emit("socket_read_failed")
			return
		_rx.append_array(result[1])
		_drain_packets()

func _drain_packets() -> void:
	# Slicing the receive buffer after every packet copied the whole remainder
	# once per packet, which is quadratic across a burst. The buffer is now
	# trimmed once, after the burst has been decoded.
	var consumed := 0
	var generation: int = coordinates.generation
	while true:
		var decoded := EloriaProtocol.try_decode(_rx, consumed)
		match decoded.status:
			"incomplete":
				_trim_receive_buffer(consumed)
				return
			"error":
				_trim_receive_buffer(consumed)
				_drop_connection(decoded.error)
				return
			"ok":
				consumed += int(decoded.consumed)
				packet_received.emit(decoded.command, decoded.payload)
				# A synchronous reducer may close/reset the link. Do not decode
				# another row from this burst or trim a replacement connection.
				if generation != coordinates.generation:
					return

func _send_due_heartbeat() -> void:
	var now: int = Time.get_ticks_msec()
	if now - _last_heartbeat_msec < HEARTBEAT_INTERVAL_MSEC:
		return
	_last_heartbeat_msec = now
	send_frame(EloriaProtocol.encode(EloriaProtocol.ClientMessage.HEART_BEAT))

func _trim_receive_buffer(consumed: int) -> void:
	if consumed <= 0:
		return
	_rx = _rx.slice(consumed)

func _set_state(value: String) -> void:
	if _state == value:
		return
	_state = value
	Diagnostics.record("connection_state", {"state": value, "tls": _secure})
	connection_state_changed.emit(value)
