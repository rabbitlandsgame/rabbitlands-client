extends SceneTree
## Exercise startup without a server or any changes to player preferences.
var failures := 0
var checks := 0

func _init() -> void:
	_run.call_deferred()

func expect(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(message)

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	expect(main.login_panel.is_visible_in_tree(), "startup shows login")
	expect(main.preview_actor == null, "login does not construct an unused character")
	expect(main.preview_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"login does not render the hidden character viewport")
	expect(main.create_gender.get_selected_id() == 1, "initial character is Human Male")
	expect(main.create_race.get_selected_metadata() == "luminous", "initial race is Human")
	var expected := {"skin": 1, "hair": AppearanceVariants.pack_hair(4, 1),
		"eyes": 2, "head": 0, "shirt": 0, "pants": 0, "boots": 0}
	expected.merge(PortraitCustomization.DEFAULTS)
	expect(main.call("_creation_appearance") == expected, "all initial appearance bytes are fixed")
	expect(main.selected_creation_class == 0 and main.creation_class_gear_visible,
		"initial class and equipment preview are fixed")
	var notifications := {"count": 0}
	main.theme.changed.connect(func() -> void: notifications.count += 1)
	main.call("_apply_shared_text_theme")
	expect(notifications.count == 1, "text colours publish one complete theme update")
	main.creation_panel.show()
	expect(is_instance_valid(main.preview_actor), "opening creation constructs the preview")
	var preview_id: int = main.preview_actor.get_instance_id()
	expect(main.preview_viewport.render_target_update_mode == SubViewport.UPDATE_ALWAYS,
		"visible character preview renders")
	main.creation_panel.hide()
	expect(main.preview_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"closing creation stops its viewport")
	main.creation_panel.show()
	expect(main.preview_actor.get_instance_id() == preview_id,
		"reopening creation reuses the unchanged character")
	expect(main.call("_creation_appearance") == expected, "opening creation preserves fixed choices")
	main.creation_panel.hide()
	main.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("STARTUP_ENTRY: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
