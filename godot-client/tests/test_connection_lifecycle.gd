extends SceneTree
## Guards the keepalive, reconnect and resync behaviour.
##
## The client answered PING_REQUEST but never initiated a heartbeat, and had no
## reconnect or relogin path at all: any dropped socket ended the session with
## a bare "Disconnected" and no way back except retyping everything. The server
## now closes a logged-in connection that has gone silent, so the heartbeat is
## also what keeps a parked client alive.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var scene: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(scene)
	await process_frame

	var network: Node = root.get_node("/root/Network")
	var app_state: Node = root.get_node("/root/AppState")
	var banner: Label = scene.get_node("GameView/ConnectionBanner") as Label
	var game_view: Control = scene.get_node("GameView") as Control

	# The heartbeat cadence has to leave room under the server's idle timeout.
	_expect(network.HEARTBEAT_INTERVAL_MSEC == 25000,
		"the heartbeat matches the legacy 25-second cadence")
	_expect(network.RECONNECT_DELAYS_MSEC.size() >= 3,
		"reconnect gives up only after several attempts")
	var previous := 0
	for delay: int in network.RECONNECT_DELAYS_MSEC:
		_expect(delay > previous, "reconnect delays back off rather than repeating")
		previous = delay
	_expect(previous * network.RECONNECT_DELAYS_MSEC.size() < 120000,
		"the whole reconnect sequence stays inside a couple of minutes")

	# A deliberate disconnect must never reconnect behind the player's back.
	network.call("connect_to_server", "127.0.0.1", 1)
	network.call("disconnect_from_server")
	await process_frame
	_expect(not bool(network.call("is_reconnecting")),
		"a disconnect the player asked for schedules no reconnect")
	_expect(int(network.call("reconnect_attempt")) == 0,
		"a deliberate disconnect leaves no reconnect attempt pending")

	# An unexpected drop schedules one, with backoff, and says so.
	var announced: Array[Array] = []
	network.reconnect_progress.connect(
		func(attempt: int, total: int, delay: int) -> void:
			announced.append([attempt, total, delay]))
	network.set("_host", "127.0.0.1")
	network.set("_port", 1)
	network.set("_reconnect_enabled", true)
	network.call("_drop_connection", "socket_error")
	await process_frame
	_expect(bool(network.call("is_reconnecting")),
		"an unexpected drop schedules a reconnect")
	_expect(announced.size() == 1 and int(announced[0][0]) == 1
		and int(announced[0][2]) == int(network.RECONNECT_DELAYS_MSEC[0]),
		"the first reconnect is announced with its attempt number and delay")
	_expect(str(app_state.get("connection_state")) == "reconnecting",
		"the reducer carries the reconnecting state")

	# The banner reports it wherever the player is looking.
	game_view.show()
	scene.call("_sync_connection_banner")
	_expect(banner.visible and banner.text.contains("reconnecting")
		and banner.text.contains("1"),
		"the HUD banner names the reconnect attempt: " + banner.text)
	_expect(banner.get_global_rect().end.x <= 1280.0
		and banner.get_global_rect().end.y <= 720.0
		and banner.get_global_rect().position.y >= 0.0,
		"the connection banner fits within 1280x720")
	var resource_rail: Control = scene.get_node("GameView/ResourceHud") as Control
	_expect(not banner.get_global_rect().intersects(resource_rail.get_global_rect()),
		"the connection banner does not cover the fixed resource rail")

	# Reaching "connected" again marks the session for a resync, because
	# nothing received before the drop can be trusted.
	_expect(bool(scene.get("_resync_after_reconnect")),
		"a dropped connection marks the next session for resynchronisation")

	# Exhausting the attempts stops rather than retrying forever.
	for _attempt: int in range(network.RECONNECT_DELAYS_MSEC.size() + 2):
		network.set("_reconnect_at_msec", 0)
		network.call("_schedule_reconnect")
	_expect(not bool(network.call("is_reconnecting")),
		"reconnect gives up after its configured attempts")

	network.call("disconnect_from_server")
	app_state.set("connection_state", "connected")
	app_state.set("authenticated", true)
	scene.call("_sync_connection_banner")
	_expect(not banner.visible,
		"a live authenticated session shows no connection banner")
	app_state.set("authenticated", false)

	print("connection lifecycle tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	scene.queue_free()
	await process_frame
	quit(failures)

func _expect(value: bool, label: String) -> void:
	if value:
		return
	failures += 1
	push_error("FAIL: " + label)
