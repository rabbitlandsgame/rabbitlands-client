extends SceneTree
const Presets := preload("res://src/ui/hud_presets.gd")
var failures := 0
var checks := 0
func _init() -> void: call_deferred("run")
func run() -> void:
	create_timer(120).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1440, 900)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = "res://test-artifacts/hud-launch/alignment.cfg"
	root.add_child(main)
	for index: int in 8: await process_frame
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var w: Control = main.hud_workspace
	for viewport: Vector2i in [Vector2i(1440,900), Vector2i(1920,1080), Vector2i(800,600)]:
		root.size = viewport
		for id: String in Presets.BUILT_INS:
			w.choose_preset(id,true)
			for index: int in 8: await process_frame
			for key: String in Presets.PARTS:
				var config: Dictionary = w.model.working.parts[key]
				if config.enabled and config.dock_target!="none" and w._root(key).is_visible_in_tree():
					if config.dock_side in ["top","bottom"] and config.dock_align in ["center","stretch"] and absf(config.dock_offset.x)<0.01:
						var actual: float = w._visual_rect(key).get_center().x
						if key=="medallion": actual=w.parts.medallion.position.x+w.parts.medallion.center_point().x*w.parts.medallion.scale.x
						check(absf(actual-w._visual_rect(config.dock_target).get_center().x)<1.1,
							"%s %s centered on dock target at %s"%[id,key,viewport])
				if not config.enabled or key == "nameplate" or config.dock_target != "none": continue
				if config.anchor not in ["top_center","bottom_center"] or absf(config.offset.x) > 0.01: continue
				check(absf(w._visual_rect(key).get_center().x-main.game_view.size.x/2)<1.1,
					"%s %s center at %s" % [id,key,viewport])
			if id == "adventure":
				var center: Vector2 = w.parts.medallion.position+w.parts.medallion.center_point()*w.parts.medallion.scale
				check(absf(center.x-main.game_view.size.x/2)<1.1,"Adventure circle center at %s"%viewport)
				check(w.model.working.parts.spells.dock_target=="medallion" and w.model.working.parts.items.dock_target=="medallion",
					"Adventure quick bars remain attached at %s"%viewport)
	main.queue_free()
	for index: int in 3: await process_frame
	print("HUD ALIGNMENT: %d checks, %d failures"%[checks,failures])
	quit(0 if failures==0 else 1)
func check(value: bool,label: String) -> void:
	checks+=1
	if value: print("PASS: ",label)
	else:
		failures+=1
		push_error(label)
