extends SceneTree
const Curtain := preload("res://src/ui/arrival_curtain.gd")
const Bootstrap := preload("res://src/platform/web_bootstrap.gd")
const Intro := preload("res://src/camera/new_character_intro.gd")

class Service extends Node:
	var retries := 0
	func retry_failed() -> int:
		retries += 1
		return 1

func _initialize() -> void: call_deferred("_run")

func _run() -> void:
	var curtain := Curtain.new()
	root.add_child(curtain)
	curtain.begin("Entering…")
	assert(curtain.layer == Curtain.LAYER and not curtain._retry.visible)
	curtain._began_msec = Time.get_ticks_msec() - 120000
	curtain._shown = 0.4
	curtain._target = 0.7
	curtain._drawn_frames = 7
	curtain.hold_asset_wait()
	assert(curtain.elapsed_msec() < 100 and curtain.progress() == 0.4)
	assert(curtain._target == 0.7 and curtain.has_drawn() and curtain.blocks_input())
	var intro := Intro.new()
	intro.pending = true
	intro._wait_started = Time.get_ticks_msec() - 120000
	intro.hold_asset_wait()
	assert(Time.get_ticks_msec() - intro._wait_started < 100)
	intro.pending = false
	intro._wait_started = -120000
	intro.hold_asset_wait()
	assert(intro._wait_started == -120000, "Ordinary/non-pending intro timing is unchanged")
	intro.free()
	var requests := [0]
	curtain.retry_requested.connect(func(): requests[0] += 1)
	curtain.offer_retry("Check your connection and try again.", "Retry", 125)
	assert(curtain.layer == 125 and curtain._retry.visible and curtain.blocks_input())
	curtain._retry.pressed.emit()
	assert(requests[0] == 1 and not curtain._retry.visible)
	assert(curtain.layer == Curtain.LAYER and curtain.blocks_input())
	curtain._retry.pressed.emit()
	assert(requests[0] == 1, "Repeated events cannot restart a hidden action")
	curtain.offer_retry("Try again", "Retry", 125)
	curtain.finish()
	assert(not curtain._retry.visible and curtain.layer == Curtain.LAYER)
	curtain.cancel()
	curtain.begin("Ordinary desktop arrival")
	assert(not curtain._retry.visible and curtain.layer == Curtain.LAYER)
	curtain.free()
	var bootstrap := Bootstrap.new()
	root.add_child(bootstrap)
	var service := Service.new()
	bootstrap.add_child(service)
	bootstrap.service = service
	var resumed := [0]
	bootstrap.retry_requested.connect(func(): resumed[0] += 1)
	bootstrap._show_failure(false)
	assert(bootstrap.retry_button.visible and bootstrap.retry_button.text == "Retry")
	assert(not bootstrap.is_processing())
	bootstrap.retry_button.pressed.emit()
	assert(service.retries == 1 and resumed[0] == 1 and not bootstrap.retry_button.visible)
	bootstrap.retry_button.pressed.emit()
	assert(service.retries == 1 and resumed[0] == 1)
	bootstrap._show_failure(true)
	assert(bootstrap.retry_button.text == "Reload")
	bootstrap.free()
	await process_frame
	print("browser download retry UI: PASS")
	quit()
