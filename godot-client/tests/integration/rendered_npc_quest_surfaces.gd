extends SceneTree
## Deterministic rendered evidence for Eloria's Oldcraft-inspired NPC surfaces.
##
## Both frames use the production main scene and the authoritative dialogue
## state seam. They prove that ordinary conversation and quest offers share the
## same readable stone/brass/parchment hierarchy while retaining distinct state
## cues. No server, actor, or frame-time worker is involved.

const SCREEN_SIZE := Vector2i(1280, 720)
const DialogueStyle := preload("res://src/ui/oldcraft_dialogue_style.gd")

var _artifacts := ""
var _failures := 0
var _checks := 0
var _main: Control
var _app_state: Node
var _saved_dialogue: Dictionary
var _saved_authenticated := false


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path(
			"res://test-artifacts/npc-quest-surfaces")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"NPC/quest artifact directory is writable")
	root.size = SCREEN_SIZE
	_app_state = root.get_node("/root/AppState")
	_saved_dialogue = (_app_state.get("npc_dialogue") as Dictionary).duplicate(true)
	_saved_authenticated = bool(_app_state.get("authenticated"))

	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	for unused: int in range(5):
		await process_frame
	_prepare_game_view()
	_assert_production_hierarchy()

	await _show_dialogue({
		"open": true,
		"name": "Archivist Nym",
		"text": "The tide-ledgers remember every ship that crossed the pale bay.\n\n"
			+ "What would you ask of the archives?",
		"quest": false,
		"quest_id": 0,
		"options": [
			{"label": "Tell me about the lantern road.", "actor_id": 41,
				"response_id": 7},
			{"label": "I should return to the quay.", "actor_id": 41,
				"response_id": 8},
		],
	})
	_assert_conversation_state()
	await _capture("npc-conversation.png", false)

	await _show_dialogue({
		"open": true,
		"name": "Warden Elowen",
		"text": "The lantern road has gone dark, and the westward caravans are "
			+ "turning back. Carry our flame beyond the old bridge.\n\n"
			+ "QUEST OBJECTIVES\n◆ Rekindle both waystones along the lantern road.\n\n"
			+ "REWARDS\n12 gold crowns  ·  Warden's favor",
		"quest": true,
		"quest_id": 17,
		"options": [
			{"label": "Accept the lantern charge", "actor_id": 81,
				"response_id": 2},
			{"label": "Ask me again later", "actor_id": 81,
				"response_id": 3},
		],
	})
	_assert_quest_state()
	await _capture("quest-offer.png", true)

	var saved_merchant: Dictionary = (_app_state.get("merchant") as Dictionary).duplicate(true)
	_app_state.set("npc_dialogue", {"open": false})
	_main.call("_sync_dialogue")
	_app_state.set("merchant", {"open": true, "actor_id": 91,
		"npc_name": "Bettany Orl", "gold": 500, "carried": 12, "capacity": 80,
		"items": [{"index": 0, "name": "Bread", "buy_price": 8,
			"sell_price": 2, "owned": 40}]})
	var windows: Control = _main.get("extension_windows") as Control
	windows.call("_sync_merchant")
	(windows.get("merchant_quantity") as LineEdit).text = "37"
	for unused: int in range(5):
		await process_frame
	_expect((windows.get("merchant_quantity") as LineEdit).is_visible_in_tree(),
		"merchant shows the exact-quantity entry field")
	_expect(root.get_texture().get_image().save_png(
		_artifacts.path_join("merchant-quantity.png")) == OK,
		"merchant quantity preview is saved")
	_app_state.set("merchant", saved_merchant)

	_app_state.set("npc_dialogue", _saved_dialogue)
	_app_state.set("authenticated", _saved_authenticated)
	_main.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	print("rendered NPC/quest surfaces: %s (%d checks)" % [
		"PASS" if _failures == 0 else "FAIL", _checks])
	quit(1 if _failures else 0)


func _prepare_game_view() -> void:
	_app_state.set("authenticated", true)
	(_main.get_node("%LoginPanel") as Control).hide()
	(_main.get_node("%LoginBackground") as Control).hide()
	(_main.get_node("%CreationPanel") as Control).hide()
	(_main.get_node("%GameView") as Control).show()
	var banner := _main.get_node_or_null("%ConnectionBanner") as Control
	if banner != null:
		banner.hide()
	# Re-apply the production layout after fixing the headless reference size.
	DialogueStyle.layout(_main)


func _assert_production_hierarchy() -> void:
	var panel := _main.get_node_or_null("%DialoguePanel") as PanelContainer
	var kicker := _main.get_node_or_null("%DialogueKicker") as Label
	var speaker := _main.get_node_or_null("%DialogueName") as Label
	var divider := _main.get_node_or_null("%DialogueDivider") as HSeparator
	var page := _main.get_node_or_null("%DialogueText") as RichTextLabel
	var instruction := _main.get_node_or_null("%DialogueInstruction") as Label
	var frame_art := _main.get_node_or_null("%DialogueFrameTexture") as TextureRect
	var choices := _main.get_node_or_null("%DialogueOptions") as VBoxContainer
	var footer := _main.get_node_or_null("%DialogueFooter") as Label
	_expect(panel != null and kicker != null and speaker != null
		and divider != null and page != null and instruction != null
		and choices != null and footer != null,
		"production dialogue keeps frame, state header, speaker plaque, parchment, choices and footer")
	_expect(_main.has_meta(DialogueStyle.STYLE_META),
		"the cached Oldcraft-inspired style hook is installed")
	if panel == null or speaker == null or page == null:
		return
	var backdrop := _main.get_node("%DialogueBackdrop") as Panel
	var parchment := backdrop.get_theme_stylebox("panel") as StyleBoxTexture
	_expect(frame_art != null and not frame_art.visible,
		"the wide decorative frame is replaced by a compact border")
	_expect(speaker.get_theme_stylebox("normal") is StyleBoxEmpty,
		"NPC identity shares the parchment background")
	_expect(parchment != null and parchment.texture != null
		and parchment.texture.resource_path.ends_with(
			"/assets/ui/oldcraft_inspired/eloria_parchment.png")
		and page.get_theme_color("default_color").is_equal_approx(DialogueStyle.INK),
		"the reading surface is tactile parchment with dark ink")
	_expect(panel.position.x >= 16.0 and panel.position.x <= 64.0
		and panel.position.y >= 80.0 and panel.position.y <= 160.0
		and panel.size.x >= 420.0 and panel.size.y >= 430.0,
		"the upper-left layout leaves the world and speaking NPC visible")


func _show_dialogue(dialogue: Dictionary) -> void:
	_app_state.set("npc_dialogue", dialogue.duplicate(true))
	_app_state.emit_signal("state_changed", &"npc_dialogue")
	for unused: int in range(5):
		await process_frame


func _assert_conversation_state() -> void:
	var panel := _main.get_node("%DialoguePanel") as PanelContainer
	var kicker := _main.get_node("%DialogueKicker") as Label
	var speaker := _main.get_node("%DialogueName") as Label
	var instruction := _main.get_node("%DialogueInstruction") as Label
	var choices := _main.get_node("%DialogueOptions") as VBoxContainer
	_expect(panel.visible and speaker.text == "Archivist Nym",
		"ordinary NPC communication shows its named speaker")
	_expect(kicker.text.contains("VOICE OF ELORIA")
		and kicker.get_theme_color("font_color").is_equal_approx(
			DialogueStyle.TALK_GOLD),
		"ordinary communication uses the subdued talk-state heading")
	_expect(instruction.visible and instruction.text.contains("RESPONSE")
		and choices.get_child_count() == 2,
		"ordinary communication exposes both authored responses")
	if choices.get_child_count() > 0:
		var first := choices.get_child(0) as Button
		_expect(first != null and first.text.begins_with("›")
			and first.alignment == HORIZONTAL_ALIGNMENT_LEFT
			and first.custom_minimum_size.y == 32.0,
			"conversation responses use compact readable icon-led rows")


func _assert_quest_state() -> void:
	var panel := _main.get_node("%DialoguePanel") as PanelContainer
	var kicker := _main.get_node("%DialogueKicker") as Label
	var speaker := _main.get_node("%DialogueName") as Label
	var page := _main.get_node("%DialogueText") as RichTextLabel
	var instruction := _main.get_node("%DialogueInstruction") as Label
	var choices := _main.get_node("%DialogueOptions") as VBoxContainer
	_expect(panel.visible and speaker.text.contains("Warden Elowen")
		and speaker.text.contains("Quest 17"),
		"quest offer identifies the giver and server quest id")
	_expect(kicker.text.contains("QUEST MISSIVE") and kicker.text.contains("17")
		and kicker.get_theme_color("font_color").is_equal_approx(
			DialogueStyle.QUEST_YELLOW),
		"quest offers receive their distinct bright-gold state hierarchy")
	_expect(page.get_parsed_text().contains("QUEST OBJECTIVES")
		and page.get_parsed_text().contains("REWARDS"),
		"the parchment carries objective and reward sections")
	_expect(instruction.visible and instruction.text.contains("COURSE")
		and choices.get_child_count() == 2,
		"quest choices retain both accept and defer paths")
	if choices.get_child_count() >= 2:
		var primary := choices.get_child(0) as Button
		var secondary := choices.get_child(1) as Button
		var primary_box := primary.get_theme_stylebox("normal") as StyleBoxFlat
		var secondary_box := secondary.get_theme_stylebox("normal") as StyleBoxFlat
		_expect(primary.text.begins_with("◆") and primary_box != null
			and secondary_box != null
			and primary_box.border_width_left > secondary_box.border_width_left,
			"the primary quest action has stronger icon and frame emphasis")


func _capture(file_name: String, quest_state: bool) -> void:
	for unused: int in range(4):
		await process_frame
	var image: Image = root.get_texture().get_image()
	_expect(image != null and not image.is_empty()
		and image.get_size() == SCREEN_SIZE,
		file_name + " renders at the 1280x720 review size")
	if image == null or image.is_empty():
		return
	_expect(_has_colour_variation(image),
		file_name + " contains real rendered colour variation")
	_expect(_count_warm_paper(image) > 500,
		file_name + " visibly contains the textured parchment reading surface")
	var state_colour: Color = (DialogueStyle.QUEST_YELLOW if quest_state
		else DialogueStyle.TALK_GOLD)
	_expect(_count_colour(image, state_colour, 0.07) > 3,
		file_name + " visibly contains its communication-state accent")
	_expect(image.save_png(_artifacts.path_join(file_name)) == OK,
		file_name + " is saved")


func _count_colour(image: Image, target: Color, tolerance: float) -> int:
	var count := 0
	for y: int in range(0, image.get_height(), 4):
		for x: int in range(0, image.get_width(), 4):
			var colour := image.get_pixel(x, y)
			if (absf(colour.r - target.r) <= tolerance
					and absf(colour.g - target.g) <= tolerance
					and absf(colour.b - target.b) <= tolerance):
				count += 1
	return count


func _count_warm_paper(image: Image) -> int:
	var count := 0
	for y: int in range(0, image.get_height(), 4):
		for x: int in range(0, image.get_width(), 4):
			var colour := image.get_pixel(x, y)
			if (colour.r > 0.68 and colour.g > 0.52 and colour.b > 0.28
					and colour.r > colour.g and colour.g > colour.b):
				count += 1
	return count


func _has_colour_variation(image: Image) -> bool:
	var lowest := 2.0
	var highest := -1.0
	for y: int in range(0, image.get_height(), 8):
		for x: int in range(0, image.get_width(), 8):
			var luminance := image.get_pixel(x, y).get_luminance()
			lowest = minf(lowest, luminance)
			highest = maxf(highest, luminance)
	return highest - lowest > 0.10


func _expect(condition: bool, message: String) -> bool:
	_checks += 1
	if not condition:
		_failures += 1
		push_error("FAIL: " + message)
	return condition
