extends SceneTree
var output := "res://test-artifacts/magic-casting"
var failures := 0
func _init() -> void: call_deferred("run")

func run() -> void:
	root.size = Vector2i(1280, 720)
	DirAccess.make_dir_recursive_absolute(output)
	var lab := (load("res://src/dev/magic_practice.tscn") as PackedScene).instantiate()
	root.add_child(lab)
	lab.set_wheel_variant("baseline")
	lab.loadout.profile = ""
	lab.loadout.set_wheel_power(1)
	await process_frame
	await capture("prepared-practice.png")
	lab.loadout.set_mode("aimed")
	lab.selector.begin(1, 4, 2)
	await capture("aimed-practice.png")
	lab.selector.cancel()
	lab.book.toggle()
	lab.book.call("_on_spell_pressed", 1)
	await capture("family-browser.png")
	check_bounds(lab.book.panel, "spellbook with family and preparation controls")
	check_bounds(lab.bar.panel, "casting bar")
	lab.book.browser_picker.select(0)
	lab.book.call("_filter_spells")
	await capture("grid-browser.png")
	lab.book.close()
	lab.selector.begin(69, 3)
	await capture("area-targeting.png")
	lab.selector.cancel()
	lab.loadout.set_mode("wheel")
	lab.wheel.open_wheel(true)
	await capture("wheel-classes.png")
	check_wheel(lab.wheel)
	lab.wheel.choose(0)
	await capture("wheel-healing.png")
	check_wheel(lab.wheel)
	lab.wheel.choose(0)
	lab.wheel.change_power(3)
	await capture("wheel-targets.png")
	check_wheel(lab.wheel)
	lab.wheel.open_wheel()
	lab.wheel.choose(2)
	await capture("wheel-offense.png")
	check_wheel(lab.wheel)
	lab.wheel.change_page(1)
	await capture("wheel-offense-page2.png")
	check_wheel(lab.wheel)
	lab.actors[1].tile = Vector2i(0, 0)
	await capture("wheel-edge.png")
	check_wheel(lab.wheel)
	lab.wheel.reset()
	lab.free()
	await process_frame
	print("magic casting rendered: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func capture(filename: String) -> void:
	for frame in range(5): await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(output.path_join(filename))

func check_bounds(control: Control, label: String) -> void:
	var rect := control.get_global_rect()
	if rect.position.x < 0 or rect.position.y < 0 or rect.end.x > 1280 or rect.end.y > 720:
		failures += 1
		push_error("Out of bounds: %s %s" % [label, rect])

func check_wheel(wheel: Control) -> void:
	var controls: Array[Control] = []
	for control in [wheel._heading, wheel._power_label, wheel._hint, wheel._back, wheel._close, wheel._previous, wheel._next]:
		if control.visible: controls.append(control)
	for button in wheel.buttons: controls.append(button)
	for index in range(controls.size()):
		check_bounds(controls[index], "wheel control")
		for other in range(index):
			if controls[index].get_global_rect().intersects(controls[other].get_global_rect()):
				failures += 1
				push_error("Overlapping wheel controls: %s and %s" % [controls[index].text, controls[other].text])
