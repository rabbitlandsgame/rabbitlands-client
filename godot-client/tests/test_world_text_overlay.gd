extends SceneTree
## The separate world text pass renders only while overhead text could be
## drawn, and resumes in the same frame that text appears.

const Overlay := preload("res://src/ui/world_text_overlay.gd")
const LabelStyle := preload("res://src/ui/world_label_style.gd")
const Presence := preload("res://src/world/world_text_presence.gd")
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func _label(parent: Node, range_end := 0.0) -> Label3D:
	var label := Label3D.new()
	label.text = "Gate Warden"
	LabelStyle.apply(label, 14, 0.0012953, 5)
	label.visibility_range_end = range_end
	parent.add_child(label)
	return label

func _run() -> void:
	var viewport := SubViewport.new()
	viewport.size = Vector2i(640, 360)
	root.add_child(viewport)
	var world := Node3D.new()
	viewport.add_child(world)
	var camera := Camera3D.new()
	world.add_child(camera)
	camera.make_current()
	var overlay := Overlay.new()
	root.add_child(overlay)
	overlay.configure(viewport)
	var pass_updates := func() -> bool:
		overlay._sync_camera()
		return overlay.drawing and overlay.text_viewport.render_target_update_mode \
			== SubViewport.UPDATE_ALWAYS
	var idle := func() -> bool:
		overlay._sync_camera()
		return not overlay.drawing and overlay.text_viewport.render_target_update_mode \
			== SubViewport.UPDATE_DISABLED

	expect(idle.call(), "with no overhead text the text pass neither renders nor composites")
	expect(overlay.text_viewport.size == viewport.size,
		"an idle pass still follows the world's size, ready to resume")

	var actor := Node3D.new()
	world.add_child(actor)
	var name_label := _label(actor)
	expect(pass_updates.call(), "a name added this frame is drawn this frame")
	expect(overlay.text_camera.global_transform == camera.global_transform,
		"the resumed pass draws from the gameplay camera's view")
	name_label.hide()
	expect(idle.call(), "a name hidden by its owner stops the pass")
	name_label.show()
	actor.hide()
	expect(idle.call(), "hiding the actor hides its name from the count too")
	actor.show()
	expect(pass_updates.call(), "and showing the actor brings it back")

	var bar := MeshInstance3D.new()
	bar.mesh = QuadMesh.new()
	bar.layers = LabelStyle.RENDER_LAYER
	actor.add_child(bar)
	name_label.hide()
	expect(pass_updates.call(), "a health bar quad on the text layer is overhead text too")
	bar.queue_free()
	await process_frame
	expect(idle.call(), "freed text stops counting")

	var scenery := Label3D.new()
	scenery.text = "Not overhead text"
	world.add_child(scenery)
	expect(idle.call(), "text on the world's own layers is not the text pass's")
	var elsewhere := SubViewport.new()
	elsewhere.own_world_3d = true
	root.add_child(elsewhere)
	_label(elsewhere)
	expect(idle.call(), "text in another world is not drawn by this pass")

	camera.position = Vector3.ZERO
	var title := _label(world, 35.0)
	title.position = Vector3(0, 0, -200)
	expect(idle.call(), "a ranged title out of its range does not wake the pass")
	camera.position = Vector3(0, 0, -170)
	expect(pass_updates.call(), "moving within its range does, before the frame is drawn")
	title.visibility_range_end = 0.0
	camera.position = Vector3.ZERO
	expect(pass_updates.call(), "a title whose range is removed is always in range")
	title.visibility_range_end = 35.0
	expect(idle.call(), "and out of range again once it has one")

	# Ranged labels are not all measured every frame while none is in range,
	# but one carried towards the camera no faster than LABEL_SPEED is still
	# drawn the frame it arrives, and one set down in range within HOLD_MSEC.
	var reach := 35.0 + Presence.RANGE_SLACK
	title.position = Vector3(0, 0, -(reach + 2.2))
	OS.delay_msec(Presence.HOLD_MSEC + 20)
	expect(idle.call(), "a title just outside its range leaves the pass idle")
	var on_time := true
	for step: int in 10:
		OS.delay_msec(16)
		title.position.z += 0.4
		var inside := -title.position.z <= reach
		on_time = on_time and (pass_updates.call() if inside else idle.call())
	expect(on_time, "a title carried at 25 m/s is drawn the frame it comes into range")
	title.position = Vector3(0, 0, -200)
	expect(idle.call(), "and the pass idles once it is out of range again")
	title.position = Vector3(0, 0, -20)
	OS.delay_msec(Presence.HOLD_MSEC + 20)
	expect(pass_updates.call(), "a title set down in range is drawn within the hold")
	title.position = Vector3(0, 0, -200)
	expect(idle.call(), "and leaves the pass idle when it goes")

	var holder := Node3D.new()
	world.add_child(holder)
	name_label.show()
	name_label.reparent(holder)
	expect(pass_updates.call(), "a reparented name is still followed")
	name_label.hide()
	expect(idle.call(), "and still counted out when hidden")
	expect(overlay.presence.tracked() == 2, "only text-layer nodes in this world are followed")

	name_label.show()
	overlay.hide()
	expect(idle.call(), "a hidden overlay never renders, whatever text there is")
	overlay.show()
	expect(pass_updates.call(), "and resumes when shown")

	var previous := OS.get_environment(Overlay.IDLE_VARIABLE)
	OS.set_environment(Overlay.IDLE_VARIABLE, "0")
	var always := Overlay.new()
	root.add_child(always)
	always.configure(viewport)
	name_label.hide()
	always._sync_camera()
	expect(always.drawing and not always.presence.watching(),
		"ELORIA_WORLD_TEXT_IDLE=0 renders every frame, as before")
	always.free()
	OS.set_environment(Overlay.IDLE_VARIABLE, previous)

	name_label.hide()
	_measure_ranged(world, overlay.presence)
	_measure_node_added(overlay.presence)
	overlay.queue_free()
	viewport.queue_free()
	elsewhere.queue_free()
	await process_frame
	print("world text overlay tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

## What the per-frame answer costs with 500 ranged titles out of range, the
## first time and while the scan holds: informational.
func _measure_ranged(world: Node3D, presence: Presence) -> void:
	var titles: Array[Label3D] = []
	for index: int in 500:
		var title := _label(world, 35.0)
		title.position = Vector3(500.0 + index * 3.0, 0.0, 0.0)
		titles.append(title)
	var started := Time.get_ticks_usec()
	var any := presence.any_drawable(Vector3.ZERO)
	var first := Time.get_ticks_usec() - started
	started = Time.get_ticks_usec()
	for repeat: int in 200:
		any = presence.any_drawable(Vector3(repeat * 0.01, 0.0, 0.0)) or any
	print("info: 500 ranged titles out of range: %.1f us to scan, %.2f us per frame while it holds (any=%s)" % [
		first, (Time.get_ticks_usec() - started) / 200.0, any])
	for title: Label3D in titles:
		title.free()

## What following the tree costs every node that enters it: informational.
func _measure_node_added(presence: Presence) -> void:
	var holder := Node3D.new()
	root.add_child(holder)
	var nodes: Array[Node3D] = []
	for index: int in 20000:
		nodes.append(Node3D.new())
	var started := Time.get_ticks_usec()
	for node: Node3D in nodes:
		holder.add_child(node)
	var watched := Time.get_ticks_usec() - started
	for node: Node3D in nodes:
		holder.remove_child(node)
	presence.stop()
	started = Time.get_ticks_usec()
	for node: Node3D in nodes:
		holder.add_child(node)
	var unwatched := Time.get_ticks_usec() - started
	print("info: 20000 node adds %.1f ms watched, %.1f ms unwatched (%.2f us per node)" % [
		watched / 1000.0, unwatched / 1000.0, (watched - unwatched) / 20000.0])
	holder.free()
