extends SceneTree
func _init() -> void: call_deferred("run")
func run() -> void:
	create_timer(90).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	root.size=Vector2i(1440,900)
	ConfigFile.new().save("res://test-artifacts/hud-launch/manual-dry.cfg")
	var main: Control=load("res://src/app/main.tscn").instantiate()
	main.get_node("GameView/ChatWindow").preferences_path="res://test-artifacts/hud-launch/manual-dry.cfg"
	root.add_child(main)
	for index: int in 8: await process_frame
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	load("res://prototypes/hud_preview_state.gd").populate(main,root.get_node("AppState"))
	var guide:=preload("res://tests/integration/hud_guide_capture.gd").new()
	guide.dry_run=true
	root.add_child(guide)
	await guide.capture(main)
	print("MANUAL HUD RECIPE: PASS; built-in switches while editing: ",guide.preset_switches)
	main.queue_free()
	guide.queue_free()
	for index: int in 3: await process_frame
	quit()
