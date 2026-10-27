extends SceneTree
## The real p191 decoder admits a scoped visual record, never network actors.
const Existing := preload("res://tests/test_campaign_rescue.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(value: bool, message: String) -> void:
	checks += 1
	if value: print("PASS: ", message)
	else: failures += 1; push_error(message)

static func snapshot() -> Dictionary:
	var state := Existing.snapshot()
	state.stage = "aftermath"; state.rescue.stage = "aftermath"
	var boss := {"actor_id":31, "actor_type":624, "kind":5, "name":"Goblin captor", "x":83, "y":62,
		"rotation":-16384, "frame":3, "health":0, "max_health":100, "scale":1.0, "appearance":{}, "equipment_visuals":{},
		"death_presentation":{"kind":"actor_death", "actor_id":31, "temporary":false, "hold_for_scene":true,
			"elapsed":3.0, "animation_seconds":3.0, "hold_seconds":3.0, "fade_seconds":4.0}}
	var lich := {"actor_id":32, "actor_type":671, "kind":2, "name":"???", "x":85, "y":64,
		"rotation":0, "frame":7, "health":20, "max_health":20, "scale":1.0, "appearance":{}, "equipment_visuals":{}}
	state.scene = {"id":"measure.rescue.shadow", "token":"rescue-run:measure.rescue.shadow", "actors":{"mother":20,"protagonist":1},
		"cutaway":{"map":"landfall_insides", "actors":{"goblin_boss":boss,"lich":lich},
			"anchors":{"boss_body":[83,62],"lich":[85,64]}}}
	return state

func decode(state: Dictionary) -> Dictionary:
	return EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_CAMPAIGN_STATE, JSON.stringify(state).to_utf8_buffer())

func same_bindings(before: Dictionary, after: Dictionary) -> bool:
	if before.size() != after.size(): return false
	for role: Variant in before:
		if not after.has(role) or int(before[role]) != int(after[role]): return false
	return true

func run() -> void:
	create_timer(45).timeout.connect(func() -> void: push_error("Cutaway protocol checks timed out"); quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	var state := snapshot()
	var decoded := decode(state)
	expect(decoded.type == "campaign" and decoded.state.scene.cutaway.actors.lich.name == "???",
		"the real p191 decoder accepts the outdoor ending's exact native held boss and masked Lich")
	expect(not decoded.state.scene.actors.has("goblin_boss") and not decoded.state.scene.actors.has("lich"),
		"cutaway visual IDs stay separate from the real scene actor bindings")
	var appearance := snapshot(); appearance.scene.cutaway.actors.lich.appearance = {"skin":1,"hair":205,"eyes":2}
	appearance.scene.cutaway.actors.lich.equipment_visuals = {"0":163,"1":160}
	expect(decode(appearance).type == "campaign", "bounded native appearance and coherent equipment dictionaries remain valid DTO fields")
	var legacy := snapshot(); legacy.map = "landfall_insides"
	legacy.scene.erase("cutaway")
	legacy.scene.actors.goblin_boss = 31
	legacy.scene.corpse_template = state.scene.cutaway.actors.goblin_boss.duplicate(true)
	legacy.scene.corpse_template.erase("appearance"); legacy.scene.corpse_template.erase("equipment_visuals")
	expect(decode(legacy).type == "campaign", "legacy in-mine Shadow retains the existing bound held-corpse template contract")
	legacy.scene.id = "measure.rescue.captive"
	expect(decode(legacy).type == "campaign", "the earlier in-mine captive scene also retains its held-corpse template")
	for invalid: String in ["missing", "null", "array", "map_missing", "map_path", "map_other", "map_nonstring", "extra_key",
		"kind", "scene", "top_map", "top_path", "top_nonstring", "inactive", "missing_cast", "third_actor", "renamed_role",
		"missing_anchor", "third_anchor", "body_anchor", "lich_anchor", "fractional_anchor", "infinite_anchor", "anchors_array",
		"body_null", "lich_array", "body_alive", "body_type", "body_kind", "body_scale", "body_max", "death_id", "death_extra",
		"not_held", "double_template", "lich_dead", "lich_overheal", "lich_type", "lich_kind", "lich_name", "lich_name_array",
		"lich_scale", "lich_infinite_scale", "duplicate_ids", "large_id",
		"body_outside", "lich_other_section", "fractional_coordinate", "infinite_coordinate", "fractional_rotation", "missing_field",
		"model_path", "equipment_array", "equipment_empty_array", "equipment_slot", "equipment_value", "appearance_array",
		"appearance_field", "appearance_value", "oversized_name", "oversized_dto"]:
		var bad := snapshot()
		var cut: Dictionary = bad.scene.cutaway
		var boss: Dictionary = cut.actors.goblin_boss
		var lich: Dictionary = cut.actors.lich
		match invalid:
			"missing": bad.scene.erase("cutaway")
			"null": bad.scene.cutaway = null
			"array": bad.scene.cutaway = []
			"map_missing": cut.erase("map")
			"map_path": cut.map = "maps/landfall_insides.elm"
			"map_other": cut.map = "greenlight"
			"map_nonstring": cut.map = ["landfall_insides"]
			"extra_key": cut.script = "res://other.gd"
			"kind": bad.kind = "road"
			"scene": bad.scene.id = "measure.rescue.resolved"
			"top_map": bad.map = "landfall_insides"
			"top_path": bad.map = "maps/landfall.elm"
			"top_nonstring": bad.map = ["landfall"]
			"inactive": bad.active = false
			"missing_cast": cut.actors.erase("lich")
			"third_actor": cut.actors.spectator = lich.duplicate(true)
			"renamed_role": cut.actors.raider = cut.actors.goblin_boss; cut.actors.erase("goblin_boss")
			"missing_anchor": cut.anchors.erase("lich")
			"third_anchor": cut.anchors.player = [55,32]
			"body_anchor": cut.anchors.boss_body[0] = 82
			"lich_anchor": cut.anchors.lich[1] = 65
			"fractional_anchor": cut.anchors.lich[0] = 85.5
			"infinite_anchor": cut.anchors.lich[0] = INF
			"anchors_array": cut.anchors = []
			"body_null": cut.actors.goblin_boss = null
			"lich_array": cut.actors.lich = []
			"body_alive": boss.health = 1
			"body_type": boss.actor_type = 671
			"body_kind": boss.kind = 2
			"body_scale": boss.scale = -1
			"body_max": boss.max_health = 0
			"death_id": boss.death_presentation.actor_id = 32
			"death_extra": boss.death_presentation.extra = {"script":"res://other.gd"}
			"not_held": boss.death_presentation.hold_for_scene = false
			"double_template": bad.scene.corpse_template = boss.duplicate(true)
			"lich_dead": lich.health = 0
			"lich_overheal": lich.health = 21
			"lich_type": lich.actor_type = 624
			"lich_kind": lich.kind = 5
			"lich_name": lich.name = "The named villain"
			"lich_name_array": lich.name = ["???"]
			"lich_scale": lich.scale = 0
			"lich_infinite_scale": lich.scale = INF
			"duplicate_ids": lich.actor_id = 31
			"large_id": lich.actor_id = 65536
			"body_outside": boss.x = 18; cut.anchors.boss_body[0] = 18
			"lich_other_section": lich.x = 177; cut.anchors.lich[0] = 177
			"fractional_coordinate": lich.y = 64.5
			"infinite_coordinate": boss.y = INF
			"fractional_rotation": lich.rotation = 0.5
			"missing_field": lich.erase("frame")
			"model_path": lich.model_path = "res://other.glb"
			"equipment_array": lich.equipment_visuals = [163]
			"equipment_empty_array": lich.equipment_visuals = []
			"equipment_slot": lich.equipment_visuals = {"99":163}
			"equipment_value": lich.equipment_visuals = {"0":256}
			"appearance_array": lich.appearance = []
			"appearance_field": lich.appearance = {"script":"res://other.gd"}
			"appearance_value": lich.appearance = {"hair":1.5}
			"oversized_name": boss.name = "x".repeat(129)
			"oversized_dto": lich.padding = "x".repeat(4096)
		expect(decode(bad).type == "invalid", "wire decode rejects cutaway " + invalid)
	for scope: String in ["scene", "outer"]:
		var reused := snapshot()
		var bindings: Dictionary = reused.scene.actors if scope == "scene" else reused.actors
		bindings.daughter = 31 if scope == "outer" else 32
		var before_bindings := bindings.duplicate(true)
		var admitted := decode(reused)
		expect(admitted.type == "campaign" and bindings == before_bindings \
			and same_bindings(admitted.state.scene.actors, reused.scene.actors) and same_bindings(admitted.state.actors, reused.actors),
			"a legitimately reused " + scope + " raw ID is accepted without inserting remote roles into live bindings")
	var direct := snapshot()
	direct.scene.cutaway.actors.lich.scale = NAN
	expect(not EloriaProtocol.campaign_cutaway_valid(direct.scene.cutaway, direct, direct.scene),
		"direct native DTO validation rejects NaN before JSON conversion")
	var app := root.get_node("AppState")
	var previous_actors: Dictionary = app.actors.duplicate(true)
	var previous_campaign: Dictionary = app.campaign.duplicate(true)
	app.actors = {1:{"actor_id":1,"kind":1,"health":20},20:{"actor_id":20,"kind":2,"health":70}}
	var before: Dictionary = app.actors.duplicate(true)
	app.call("_on_packet", EloriaProtocol.ServerMessage.ELORIA_CAMPAIGN_STATE, JSON.stringify(state).to_utf8_buffer())
	expect(app.campaign.get("scene",{}).has("cutaway") and app.actors == before,
		"actual AppState p191 dispatch stores cutaway only as campaign data and admits no remote network actors")
	check_actual_reuse(app)
	app.actors = previous_actors; app.campaign = previous_campaign
	await process_frame
	print("Campaign cutaway protocol: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

func check_actual_reuse(app: Node) -> void:
	# Private native captures stay outside Git. Supply the real allocator-reuse
	# recording for local regression; deterministic reuse is covered above too.
	var path := OS.get_environment("RL_RESCUE_REUSED_ID_FIXTURE")
	if path.is_empty(): return
	var record: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	expect(record is Dictionary and record.get("state") is Dictionary and record.get("packet191_base64") is String,
		"the supplied actual allocator-reuse capture contains its native p191 frame")
	if not record is Dictionary or not record.get("state") is Dictionary or not record.get("packet191_base64") is String: return
	var actual: Dictionary = record.state
	var frame := Marshalls.base64_to_raw(record.packet191_base64)
	expect(frame.size() > 3 and frame[0] == EloriaProtocol.ServerMessage.ELORIA_CAMPAIGN_STATE,
		"the actual reuse recording retains the native campaign command")
	if frame.size() <= 3: return
	var admitted := EloriaProtocol.decode_server(frame[0], frame.slice(3))
	expect(admitted.type == "campaign" and admitted.state == actual,
		"the actual cached-boss/live-daughter ID collision decodes unchanged on the wire")
	var daughter_id := int(actual.actors.daughter)
	var body: Dictionary = actual.scene.cutaway.actors.goblin_boss
	expect(daughter_id == int(body.actor_id) and int(body.death_presentation.actor_id) == daughter_id,
		"the real capture reproduces allocator reuse while preserving the corpse's own death identity")
	app.actors = {daughter_id:{"actor_id":daughter_id,"actor_type":0,"kind":2,"name":record.live_actor_name,"health":50}}
	var before: Dictionary = app.actors.duplicate(true)
	app.call("_on_packet", frame[0], frame.slice(3))
	expect(app.campaign == actual and app.actors == before \
		and not app.campaign.scene.actors.has("goblin_boss") and not app.campaign.scene.actors.has("lich"),
		"actual reused-ID dispatch preserves live Liora and never adds remote cutaway roles or actors")
