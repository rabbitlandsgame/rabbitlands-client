extends SceneTree
## Login lays out the banner while the game view is still hidden. Once its
## rich text has the real width, the background must fit the settled content.
var main: Control
var checks := 0
var failures := 0

func _init() -> void: call_deferred("run")

func frames(count := 8) -> void:
	for index: int in count: await process_frame

func expect(value: bool, label: String) -> void:
	checks += 1
	if value: print("PASS: ", label)
	else:
		failures += 1
		push_error(label)

func expect_fitted(label: String) -> void:
	var banner: Control = main.actor_resource_overlay
	expect(banner.size.is_equal_approx(banner.get_combined_minimum_size()),
		label + ": background fits content (%s / %s)" % [banner.size, banner.get_combined_minimum_size()])

func run() -> void:
	create_timer(70).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 720)
	main = load("res://src/app/main.tscn").instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = "res://test-artifacts/banner-login-%d.cfg" % Time.get_ticks_usec()
	root.add_child(main)
	await frames()
	main.set_process(false)
	var app: Node = root.get_node("AppState")
	app.stats = {"health":40, "max_health":40, "ether":124, "max_ether":124,
		"food":-30, "action_points":80, "max_action_points":80}
	# Match first login: data arrives before the hidden game view is shown.
	main._sync_stats()
	main._sync_local_name_colors({"name":"Rabbitman", "name_colour":0})
	main.login_panel.hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	main.actor_resource_overlay.show()
	await frames(15)
	expect_fitted("first login without another stats packet")
	expect(main.overhead_player_name.size.y < 30, "the normal player name fits on one line")
	var compact_height: float = main.actor_resource_overlay.get_combined_minimum_size().y
	main._sync_local_name_colors({"name":"Silverbranch", "guild_tag":"KEEPERS", "name_colour":0})
	await frames()
	expect_fitted("longer player name and guild tag")
	main._sync_local_name_colors({"name":"Rabbitman", "name_colour":0})
	await frames()
	expect_fitted("shorter player name without a stats update")
	expect(is_equal_approx(main.actor_resource_overlay.size.y, compact_height),
		"removing wrapped name content restores the compact height")
	main.game_view.hide()
	main._sync_stats()
	main.game_view.show()
	await frames()
	expect_fitted("returning to the game view")
	main.queue_free()
	await frames(2)
	print("PLAYER_BANNER_LAYOUT: ", checks, " checks, ", failures, " failures")
	quit(1 if failures else 0)
