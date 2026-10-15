extends "res://tests/integration/rendered_bell.gd"
## Focused TCP test with an ordinary character fixture placed at ranged practice.
## A shot, hit, experience update and panel opening all use real gameplay.
func run() -> void:
	output=OS.get_environment("ELORIA_ARTIFACT_DIR")
	DirAccess.make_dir_recursive_absolute(output)
	root.size=Vector2i(1280,720)
	main=load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	state=root.get_node("AppState");net=root.get_node("Network")
	main.host_edit.text="127.0.0.1"
	main.port_edit.value=int(OS.get_environment("ELORIA_INTEGRATION_PORT"))
	main.secure_check.button_pressed=false
	main._on_connect_pressed()
	await wait_until(func():return state.connection_state=="connected","connect")
	main.user_edit.text="BellQA";main.password_edit.text="BellReview42"
	main._on_login_pressed()
	await wait_until(func():return state.authenticated,"login")
	await stage("shot")
	await wait_until(func():return main.lantern_scene!=null and enemy()>=0,"practice sentry")
	await create_timer(1).timeout
	main._send_attack(enemy())
	await stage("ranging")
	await wait_until(func():return main.ranging_window.hits>=1,"real hit counted")
	main._on_ranging_button_pressed()
	await stage("sentry")
	await create_timer(.3).timeout
	assert(main.ranging_window.shots>=main.ranging_window.hits)
	assert(main.ranging_window.ranging_exp>0)
	assert(not main.lantern_guide.card.get_global_rect().intersects(main.ranging_window.panel.get_global_rect()))
	await capture("ranging-counted")
	print("BELLWATCH RANGING: PASS; shots=",main.ranging_window.shots," hits=",main.ranging_window.hits," xp=",main.ranging_window.ranging_exp)
	net.disconnect_from_server()
	quit(0)
