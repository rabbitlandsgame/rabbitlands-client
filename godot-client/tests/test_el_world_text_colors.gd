extends SceneTree
const Actor := preload("res://src/actors/replicated_actor_3d.gd")
const Colors := preload("res://src/ui/text_colors.gd")
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	Colors.reset()
	_expect(Actor._nameplate_colour({"kind": 2}) == Color(0.3, 0.8, 1.0), "NPC names use EL cyan")
	_expect(Actor._nameplate_colour({"kind": 1}) == Color.WHITE, "ordinary players remain white")
	_expect(Actor._nameplate_colour({"kind": 1, "map_type": 2}) == Color(0.6, 0.9, 0.9), "special maps use the EL player tint")
	_expect(Actor._nameplate_colour({"kind": 4, "enhanced": true}) == Color.RED, "PKable players use red")
	_expect(Actor._nameplate_colour({"kind": 5}) == Color.YELLOW, "natural creatures remain yellow")
	_expect(Actor._nameplate_colour({"kind": 5, "enhanced": true}) == Color.RED, "enhanced PKable actors use red")
	_expect(Actor._nameplate_colour({"kind": 5, "name_colour": 14}) == EloriaProtocol.EL_TEXT_COLOURS[14], "explicit server names retain their palette shade")
	var actor := Actor.new()
	root.add_child(actor)
	var dto := {"actor_id": 7, "kind": 2, "name": "Keeper", "guild_tag": "RL", "guild_colour": 4,
		"x": 1, "y": 1, "rotation": 0, "health": 20, "max_health": 40}
	actor.configure(dto, CoordinateAdapter.new({"metresPerTile": 1.0}), {}, {}, {}, false)
	var name: Label3D = actor.get_node("Nameplate")
	var tag: Label3D = actor.get_node("GuildTag")
	_expect(name.text == "Keeper" and tag.text == "  [RL]", "name and guild have independent text runs")
	_expect(tag.modulate == EloriaProtocol.EL_TEXT_COLOURS[4], "guild tag keeps the server color")
	_expect(name.offset.x < 0 and tag.offset.x > 0, "independent runs center as one name")
	actor.set_overhead_fade(0.5)
	Colors.set_color("world_npc", Color.MAGENTA)
	Colors.set_color("world_guild", Color.GREEN)
	_expect(name.modulate == Color(1, 0, 1, 0.5) and tag.modulate == Color(0, 1, 0, 0.5), "live name preferences preserve distance fade")
	Colors.set_color("world_npc", Color(1, 0, 1, 0.5))
	Colors.set_color("world_guild", Color(0, 1, 0, 0.5))
	_expect(name.modulate.a == 0.25 and tag.modulate.a == 0.25, "chosen text transparency multiplies distance fade")
	Colors.set_color("world_health", Color.CYAN)
	_expect((actor.get_node("HealthNumbers") as Label3D).modulate.r == 0.0, "other actor health text accepts a custom color")
	actor.show_speech_bubble("Hello", 1000, EloriaProtocol.EL_TEXT_COLOURS[2])
	_expect((actor.get_node("SpeechBubble") as Label3D).modulate == EloriaProtocol.EL_TEXT_COLOURS[2], "speech preserves supplied body color")
	Colors.set_color("world_speech", Color.MAGENTA)
	_expect((actor.get_node("SpeechBubble") as Label3D).modulate == Color.MAGENTA, "overhead speech accepts a live override")
	actor.set_quest_available(true)
	Colors.set_color("world_quest", Color.CYAN)
	_expect((actor.get_node("QuestOfferMarker") as Label3D).modulate == Color.CYAN, "active quest markers update their pulse color immediately")
	Colors.reset()
	var updated := dto.duplicate()
	updated.name = "Keeper Two"
	updated.guild_tag = "NEW"
	updated.guild_colour = 11
	actor._apply_server_state_native(updated, CoordinateAdapter.new({"metresPerTile": 1.0}))
	_expect(name.text == "Keeper Two" and tag.text == "  [NEW]"
		and tag.modulate == Color(EloriaProtocol.EL_TEXT_COLOURS[11], 0.5),
		"native actor updates refresh independent name and guild colors while preserving fade")
	actor.queue_free()
	await process_frame
	print("EL world text colors: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)
