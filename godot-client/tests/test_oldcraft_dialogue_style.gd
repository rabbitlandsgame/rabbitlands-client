extends SceneTree

const DialogueStyle := preload("res://src/ui/oldcraft_dialogue_style.gd")

var failures := 0
var checks := 0


func _init() -> void:
	call_deferred("_run")


func _expect(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(message)


func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("%GameView") as Control).show()
	DialogueStyle.apply(main)

	var panel := main.get_node("GameView/DialoguePanel") as PanelContainer
	var content := main.get_node("GameView/DialoguePanel/DialogueContent") as VBoxContainer
	var speaker := main.get_node(
		"GameView/DialoguePanel/DialogueContent/DialogueName") as Label
	var body := main.get_node("%DialogueText") as RichTextLabel
	var frame_art := main.get_node("%DialogueFrameTexture") as TextureRect
	var backdrop := main.get_node("%DialogueBackdrop") as Panel
	var options_scroll := main.get_node("%DialogueOptionsScroll") as ScrollContainer
	var options := main.get_node("%DialogueOptions") as VBoxContainer
	_expect(content != null and speaker != null and body != null
		and options_scroll != null and options != null,
		"established dialogue node paths remain intact")
	var frame := panel.get_theme_stylebox("panel") as StyleBoxFlat
	_expect(frame != null and frame.bg_color.a == 0.0
		and frame.content_margin_left <= 16.0 and not frame_art.visible,
		"a slim border leaves the window available for conversation")
	_expect(speaker.get_theme_stylebox("normal") is StyleBoxEmpty,
		"the speaker shares the document surface")
	var page := backdrop.get_theme_stylebox("panel") as StyleBoxTexture
	_expect(page != null and page.texture != null and page.texture.resource_path.ends_with(
		"/assets/ui/oldcraft_inspired/eloria_parchment.png")
		and body.get_theme_color("default_color").is_equal_approx(DialogueStyle.INK)
		and body.get_theme_stylebox("normal") is StyleBoxEmpty,
		"the whole window is parchment and the reading area has no separate fill")
	_expect(main.has_meta(DialogueStyle.STYLE_META),
		"style application is observable without a frame-time worker")
	_expect(panel.position.x >= 24.0 and panel.position.x <= 36.0
		and panel.position.y >= 110.0 and panel.position.y <= 150.0
		and panel.size.x >= 540.0 and panel.size.x <= 580.0,
		"desktop dialogue is left-weighted while preserving world context")
	_expect(frame_art.position.is_equal_approx(panel.position)
		and frame_art.size.is_equal_approx(panel.size)
		and backdrop.z_index < frame_art.z_index
		and frame_art.z_index < panel.z_index,
		"the decorative frame tracks the responsive dialogue rectangle")
	var original_position := panel.position
	panel.position += Vector2(14.0, 9.0)
	await process_frame
	_expect(frame_art.position.is_equal_approx(panel.position)
		and backdrop.position.is_equal_approx(panel.position)
		and backdrop.size.is_equal_approx(panel.size),
		"event-driven decorations follow the established draggable window")
	panel.position = original_position
	await process_frame

	var app_state := root.get_node("AppState")
	var saved_dialogue: Dictionary = (app_state.get("npc_dialogue") as Dictionary).duplicate(true)
	app_state.set("npc_dialogue", {"open": true, "name": "Warden Elowen",
		"text": "The lantern road has gone dark. Rekindle both waystones.",
		"quest": true, "quest_id": 17,
		"options": [
			{"label": "I will relight them.", "actor_id": 81, "response_id": 2},
			{"label": "Not yet.", "actor_id": 81, "response_id": 3}]})
	main.call("_sync_dialogue")
	await process_frame
	await process_frame
	_expect(panel.visible and speaker.text == "Warden Elowen  [Quest 17]",
		"quest dialogue identifies both speaker and quest without changing its path")
	var kicker := main.get_node("%DialogueKicker") as Label
	_expect(kicker.text.contains("QUEST MISSIVE") and kicker.text.contains("17")
		and kicker.get_theme_color(
		"font_color").is_equal_approx(DialogueStyle.QUEST_YELLOW),
		"quest state has an unmistakable gold hierarchy marker")
	_expect(options.get_child_count() == 2,
		"the response list keeps every server-authored option")
	var primary := options.get_child(0) as Button
	var secondary := options.get_child(1) as Button
	_expect(primary.text.begins_with("◆") and primary.alignment == HORIZONTAL_ALIGNMENT_LEFT,
		"quest responses use a readable icon-led row")
	_expect((primary.get_theme_stylebox("normal") as StyleBoxFlat).border_width_left == 2
		and (secondary.get_theme_stylebox("normal") as StyleBoxFlat).border_width_left == 1,
		"the primary quest response is emphasized without hiding alternatives")
	var primary_box := primary.get_theme_stylebox("normal") as StyleBoxFlat
	_expect(primary.custom_minimum_size.y == 32.0
		and primary_box.content_margin_top <= 5.0,
		"compact response rows keep the quest accent")
	_expect(body.size.x >= 520.0 and body.size.y >= 300.0
		and options.get_combined_minimum_size().y <= options_scroll.size.y,
		"normal conversation fits: body %s, choices %s, choice viewport %s" % [
			body.size, options.get_combined_minimum_size(), options_scroll.size])
	_expect(primary.pressed.is_connected(Callable(main, "_on_dialogue_option").bind(81, 2)),
		"the visual rewrite preserves response wiring")

	app_state.set("npc_dialogue", {"open": true, "name": "Ferrykeeper",
		"text": "Mist is lifting from the western channel.", "quest": false,
		"quest_id": 0, "options": []})
	main.call("_sync_dialogue")
	_expect(speaker.text == "Ferrykeeper" and kicker.text.contains("VOICE OF ELORIA"),
		"ordinary NPC communication stays distinct from quest dialogue")
	_expect(not (main.get_node("%DialogueInstruction") as Label).visible,
		"an empty response list does not leave a misleading prompt")
	_expect(not options_scroll.visible,
		"an empty response list does not reserve a flat response well")

	# A short viewport and a branchy server response must stay within the frame;
	# the response list scrolls instead of pushing the HUD below the screen.
	root.size = Vector2i(800, 480)
	await process_frame
	DialogueStyle.layout(main)
	var many_options: Array[Dictionary] = []
	for option_index: int in range(6):
		many_options.append({"label": "Ask about road %d" % (option_index + 1),
			"actor_id": 90, "response_id": option_index + 1})
	app_state.set("npc_dialogue", {"open": true, "name": "Road Warden",
		"text": "There are several roads through the old wood.", "quest": false,
		"quest_id": 0, "options": many_options})
	main.call("_sync_dialogue")
	await process_frame
	var game_view := main.get_node("%GameView") as Control
	_expect(options.get_child_count() == 6
		and options_scroll.visible
		and options.get_combined_minimum_size().y > options_scroll.size.y,
		"six server-authored responses use the bounded scroll region")
	_expect(panel.get_global_rect().end.y <= game_view.get_global_rect().end.y
		and panel.size.y <= game_view.size.y - 32.0,
		"branchy dialogue remains inside a short viewport")

	app_state.set("npc_dialogue", saved_dialogue)
	main.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	print("oldcraft dialogue style: %s (%d checks)" % [
		"PASS" if failures == 0 else "FAIL", checks])
	quit(1 if failures else 0)
