extends SceneTree
## The same visible HUD group must own drawing and pointer dispatch. No
## gameplay or quest state is involved in activation, overlays or docking.
const Stack := preload("res://src/ui/window_stack.gd")
var checks := 0
var failures := 0
var presses := {"guide":0,"map":0,"tracker":0,"menu":0,"window":0,"modal":0,"world":0}
var pointer_events := {"guide":[],"map":[]}

class Surface extends Control:
	var stack: WindowStack
	func _input(event: InputEvent) -> void:
		if stack != null: stack.handle_pointer(event)

func _init() -> void: run.call_deferred()
func expect(value: bool, message: String) -> void:
	checks += 1
	if not value: failures += 1; push_error(message)
func settle() -> void:
	for index in 3: await process_frame
func panel(parent: Node, at: Vector2, dimensions := Vector2(260,180)) -> Panel:
	var result := Panel.new(); parent.add_child(result); result.position = at; result.size = dimensions
	return result
func button(parent: Control, at: Vector2, identity: String) -> Button:
	var result := Button.new(); parent.add_child(result); result.position = at; result.size = Vector2(80,32)
	result.text = identity
	result.pressed.connect(func() -> void: presses[identity] += 1)
	result.gui_input.connect(func(event: InputEvent) -> void:
		if identity in pointer_events and event is InputEventMouseButton and event.pressed:
			pointer_events[identity].append(event.button_index))
	return result
func click(point: Vector2, which := MOUSE_BUTTON_LEFT) -> void:
	var motion := InputEventMouseMotion.new(); motion.position = point; motion.global_position = point
	root.push_input(motion,true)
	for pressed: bool in [true,false]:
		var event := InputEventMouseButton.new(); event.position = point; event.button_index = which
		event.global_position = point
		event.pressed = pressed; root.push_input(event,true)
	await settle()

func run() -> void:
	create_timer(45).timeout.connect(func() -> void: push_error("Quest HUD stacking timed out"); quit(1))
	root.get_node("Network").block_for_hud_preview(); root.size = Vector2i(1280,720)
	var surface := Surface.new(); root.add_child(surface)
	surface.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); surface.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var stack := Stack.new(); surface.add_child(stack); stack.configure(surface); surface.stack = stack
	var world := Control.new(); surface.add_child(world)
	world.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); world.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var world_button := button(world,Vector2(900,500),"world")
	var guide := Control.new(); surface.add_child(guide)
	guide.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); guide.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var card := panel(guide,Vector2(100,100))
	var guide_exposed := button(card,Vector2(10,10),"guide")
	var guide_overlap := button(card,Vector2(180,65),"guide")
	var tracker := panel(surface,Vector2(100,380),Vector2(260,100))
	var tracker_button := button(tracker,Vector2(10,10),"tracker")
	var map := panel(surface,Vector2(240,140),Vector2(260,220))
	var map_overlap := button(map,Vector2(40,25),"map")
	var map_exposed := button(map,Vector2(160,150),"map")
	var labels := Node2D.new(); map.add_child(labels); labels.z_index = 1
	var frames := Node2D.new(); surface.add_child(frames); frames.z_index = 21
	stack.register_hud(guide,card); stack.register_hud(tracker,tracker); stack.register_hud(map,map)
	await settle()
	expect(guide.mouse_filter == Control.MOUSE_FILTER_IGNORE and card.get_parent() == guide,
		"HUD registration preserves the guide owner and its ignored empty viewport")
	expect(card.has_meta(Stack.STACK_META) and card.z_as_relative and card.z_index == 0,
		"the concrete quest card inherits its registered HUD drawing group")
	var overlap := guide_overlap.get_global_rect().get_center()
	expect(map_overlap.get_global_rect().has_point(overlap),"the quest and minimap really overlap in the pointer fixture")
	await click(overlap)
	expect(presses.map == 1 and presses.guide == 0,"the initially frontmost minimap receives the overlap click once: %s" % presses)
	await click(guide_exposed.get_global_rect().get_center())
	expect(guide.get_index() > map.get_index() and guide.z_index > map.z_index + labels.z_index,
		"an exposed quest click raises both its GUI order and drawing above map labels")
	await click(overlap)
	expect(presses.guide == 2 and presses.map == 1,"the next overlapping click reaches the newly active quest exactly once")
	await click(map_exposed.get_global_rect().get_center()); await click(overlap)
	expect(map.get_index() > guide.get_index() and map.z_index > guide.z_index and presses.map == 3,
		"an exposed minimap click restores its drawing and pointer priority")
	await click(overlap,MOUSE_BUTTON_WHEEL_DOWN); await click(overlap,MOUSE_BUTTON_RIGHT)
	expect(MOUSE_BUTTON_WHEEL_DOWN in pointer_events.map and MOUSE_BUTTON_RIGHT in pointer_events.map
		and not MOUSE_BUTTON_WHEEL_DOWN in pointer_events.guide and not MOUSE_BUTTON_RIGHT in pointer_events.guide,
		"wheel and right clicks follow the visible HUD instead of leaking through it")
	await click(tracker_button.get_global_rect().get_center())
	expect(presses.tracker == 1 and tracker.get_index() > map.get_index() and tracker.z_index > map.z_index,
		"the ordinary pinned tracker participates in the same HUD order")
	expect(guide.z_index > frames.z_index and tracker.z_index > frames.z_index and map.z_index > frames.z_index,
		"HUD surfaces remain above the existing shared border decoration")
	var menu := panel(card,Vector2.ZERO,Vector2(160,120)); menu.set_as_top_level(true)
	menu.global_position = Vector2(410,140)
	var menu_button := button(menu,Vector2(10,10),"menu")
	stack.attach_overlay(card,menu); Stack.activate(card); await settle()
	var menu_point := menu_button.get_global_rect().get_center()
	expect(not card.get_global_rect().has_point(menu_point) and map.get_global_rect().has_point(menu_point),
		"the open quest menu extends outside its card over the minimap")
	await click(menu_point)
	expect(presses.menu == 1 and presses.map == 3 and menu.z_index == guide.z_index + 1,
		"an attached menu keeps its host's priority and receives an outside-card click once")
	menu.hide()
	var window := panel(surface,Vector2(80,80),Vector2(500,320)); window.hide()
	button(window,overlap-Vector2(80,80)-Vector2(40,16),"window")
	stack.register(window); window.show(); await settle(); Stack.activate(card)
	expect(guide.get_index() < window.get_index() and guide.z_index < window.z_index,
		"HUD activation never jumps above a normal gameplay window")
	await click(overlap)
	expect(presses.window == 1 and presses.guide == 2,"a normal window remains usable over the quest and minimap")
	var modal := panel(surface,Vector2(180,130),Vector2(320,200)); modal.hide()
	button(modal,overlap-Vector2(180,130)-Vector2(40,16),"modal")
	stack.register(modal,true); modal.show(); await settle(); Stack.activate(card); await click(overlap)
	expect(presses.modal == 1 and modal.get_index() > guide.get_index() and modal.z_index > window.z_index,
		"confirmation input and drawing remain above the active HUD and normal windows")
	modal.hide(); window.hide()
	await click(world_button.get_global_rect().get_center())
	expect(presses.world == 1,"the full-screen guide never captures clicks outside its concrete card")
	window.show(); card.reparent(window)
	card.z_as_relative = true; card.z_index = 0
	var child_index := card.get_index()
	Stack.activate(card); await settle()
	expect(card.get_parent() == window and card.get_index() == child_index and stack._hud_hit(guide) == null,
		"docking removes the card from the independent HUD hit region without rearranging window contents")
	menu.show(); menu.global_position = Vector2(650,100); Stack.activate(menu); await settle()
	expect(menu.z_index == window.z_index + 1,"a docked quest menu follows its normal manufacturing window's drawing group")
	await click(menu_button.get_global_rect().get_center())
	expect(presses.menu == 2,"a docked menu outside its window bounds stays usable through the same activation path")
	menu.hide(); window.hide(); card.reparent(guide); card.z_as_relative = true; card.z_index = 0
	Stack.activate(card); await settle()
	expect(card.get_parent() == guide and guide.z_index < window.z_index and menu.z_index == guide.z_index + 1,
		"undocking restores the HUD group and its overlay while normal windows retain their tier")
	var guide_index := guide.get_index(); guide.hide(); await click(world_button.get_global_rect().get_center())
	expect(presses.world == 2 and guide.get_index() == guide_index,"a hidden guide contributes no full-screen activation region")
	guide.show(); window.show(); modal.show(); stack.close_session_windows(); await settle()
	expect(guide.visible and tracker.visible and map.visible and not window.visible and not modal.visible,
		"closing session windows preserves persistent HUD visibility preferences")
	surface.queue_free(); await process_frame; await process_frame
	print("Quest HUD stack: %d checks; %d failures" % [checks,failures])
	quit(1 if failures else 0)
