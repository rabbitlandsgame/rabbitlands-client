extends SceneTree
## Read-only layout check of current native quest snapshots, not a playthrough.
const Guidance := preload("res://src/world/campaign_guidance.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures += 1; push_error(message)

func run() -> void:
	Engine.max_fps = 30
	var output := OS.get_environment("RL_READINESS_RENDER_OUT")
	var input := OS.get_environment("RL_READINESS_RENDER_EVIDENCE")
	if output.is_empty() or input.is_empty(): quit(1); return
	DirAccess.make_dir_recursive_absolute(output)
	root.get_node("Network").block_for_hud_preview()
	root.get_node("AppState").authenticated = true
	var backdrop := ColorRect.new(); root.add_child(backdrop)
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); backdrop.color = Color("152126")
	var banner := Label.new(); root.add_child(banner); banner.position = Vector2(12,12)
	banner.text = "AUTOMATED NATIVE-STATE UI FIXTURE\nLayout only · no live quest actions"
	var hud: Control = load("res://src/ui/campaign_hud.gd").new(); root.add_child(hud)
	var owner := Control.new(); root.add_child(owner)
	var guide: Control = load("res://src/ui/lantern_guide.gd").new(); root.add_child(guide)
	guide.configure(owner); guide.attach_campaign(hud)
	var records: Array = JSON.parse_string(FileAccess.get_file_as_string(input))
	var captures: Array = []
	for dimensions: Vector2i in [Vector2i(1280,720), Vector2i(900,460)]:
		root.size = dimensions
		for record: Dictionary in records:
			var state: Dictionary = record.snapshot
			var original := JSON.stringify(state)
			var decoded := EloriaProtocol.decode_campaign(original.to_utf8_buffer())
			expect(decoded.type == "campaign", "native readiness state decodes")
			if decoded.type != "campaign": quit(1); return
			hud.apply_state(decoded.state,Vector2i.ZERO,str(state.map))
			guide.apply_campaign(decoded.state); guide._process(0)
			for _frame in 5: await process_frame
			var button: Button
			for child: Node in hud._targets.get_children():
				if child is Button and child.disabled and child.text.begins_with("Not ready · "):
					button = child; break
			expect(button != null, "native checkpoint exposes a blocked action")
			if button == null: quit(1); return
			hud._scroll.ensure_control_visible(button)
			for _frame in 3: await process_frame
			hud._body_scroll.ensure_control_visible(button)
			for _frame in 5: await process_frame
			expect(button.is_visible_in_tree() and button.text.contains("\n") and button.tooltip_text in button.text,
				"the blocked action and native reason are both visible")
			expect(hud._body_scroll.get_global_rect().encloses(button.get_global_rect()), "the action fits its scrollable card")
			expect(hud._scroll.get_global_rect().encloses(button.get_global_rect()), "the inner action list does not clip the explanation")
			expect(root.get_visible_rect().encloses(button.get_global_rect()), "the entire explanation fits the logical viewport")
			expect(root.get_visible_rect().encloses(guide.card.get_global_rect()) \
				and root.get_visible_rect().encloses(guide._buttons.get_global_rect()), "the normal quest card and footer remain on screen")
			expect(JSON.stringify(state) == original, "rendering changes no native proof or quest state")
			await RenderingServer.frame_post_draw
			var filename := "%s-%dx%d.png" % [record.label,dimensions.x,dimensions.y]
			expect(root.get_texture().get_image().save_png(output.path_join(filename)) == OK,"captured native readiness card")
			captures.append(filename)
	var report := FileAccess.open(output.path_join("report.json"),FileAccess.WRITE)
	report.store_string(JSON.stringify({"checks":checks,"failures":failures,"captures":captures,
		"scope":"Read-only current native quest-card layout; not gameplay or cinematic acceptance"},"  "))
	report.close(); guide.queue_free(); owner.queue_free()
	for _frame in 3: await process_frame
	print("Quest readiness rendering: %d checks; %d failures" % [checks,failures])
	quit(1 if failures else 0)
