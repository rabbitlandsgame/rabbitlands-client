extends SceneTree
var output := "res://test-artifacts/magic-casting"
var failures := 0
func _init() -> void: call_deferred("run")
func run() -> void:
	root.size = Vector2i(1280, 720)
	var lab := (load("res://src/dev/magic_practice.tscn") as PackedScene).instantiate()
	root.add_child(lab)
	lab.trial_preferences_path = ""
	lab.trial_preferences = {"scopes": {}, "powers": {}, "pins": {}}
	lab.loadout.profile = ""
	lab.loadout.set_ring_size(100)
	lab.loadout.set_wheel_power(3)
	root.get_node("AppState").select_actor(2)
	for variant in ["quick", "orbit"]:
		lab.set_wheel_variant(variant)
		lab.wheel.open_wheel(true)
		await capture(variant + "-classes.png")
		if variant == "quick": lab.wheel.enter_class("Healing")
		await capture(variant + "-healing.png")
		lab.wheel.enter_class("Offense")
		await capture(variant + "-offense.png")
		lab.wheel.change_page(1)
		await capture(variant + "-more.png")
		for control in [lab.wheel._scope_bar, lab.wheel._pin, lab.wheel._hint, lab.variant_picker, lab.bar.panel]:
			var rect: Rect2 = control.get_global_rect()
			if rect.position.x < 0 or rect.position.y < 0 or rect.end.x > 1280 or rect.end.y > 720:
				failures += 1
				push_error("Trial control out of bounds: " + str(rect))
	lab.set_wheel_variant("quick")
	for percent in [75,100,125]:
		lab.loadout.set_ring_size(percent)
		lab.wheel.open_wheel(true)
		lab.wheel.enter_class("Healing")
		await capture("ring-size-%d.png" % percent)
	lab.free()
	await process_frame
	print("magic wheel trial renders: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
func capture(filename: String) -> void:
	for frame in range(6): await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(output.path_join(filename))
