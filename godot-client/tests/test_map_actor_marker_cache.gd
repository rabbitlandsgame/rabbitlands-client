extends SceneTree
## Data/lifetime/style contracts and actual Main collection, without model imports or map loading.
const Cache := preload("res://src/ui/map_actor_marker_cache.gd")
const EXPECTED_KIND_TYPES := {-1: &"npc", 0: &"npc", 1: &"player", 2: &"npc", 3: &"player", 4: &"player", 5: &"creature", 6: &"npc", 99: &"npc"}
var checks := 0
var failures := 0

func _init() -> void:
	call_deferred("_run")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func _run() -> void:
	var cache := Cache.new()
	for kind: int in [-1, 0, 1, 2, 3, 4, 5, 6, 99]:
		for colour: int in [-1, 0, ReplicatedActor3D.INVASION_NAME_COLOUR, ReplicatedActor3D.SUMMON_NAME_COLOUR, 255, 10000]:
			var dto := {"kind": kind, "name_colour": colour, "name": "No style dependency"}
			var row := cache.mark(1, Vector3(kind, colour, 0), dto)
			var expected: StringName = &"invasion" if kind == 5 and colour == 14 else EXPECTED_KIND_TYPES[kind]
			expect(row.type == expected, "type matches independent wire-kind/name-colour table")
			expect(row.colour == ReplicatedActor3D.map_dot_colour(dto), "colour uses canonical actor policy")
			expect(row.size() == 3 and row.has("position") and row.has("type") and row.has("colour"), "public row shape unchanged")
	var original := cache.mark(2, Vector3.ZERO, {})
	var updated := cache.mark(2, Vector3(7, 2, -1), {"kind": 5, "name_colour": ReplicatedActor3D.INVASION_NAME_COLOUR})
	expect(original.position == updated.position and original.type == &"invasion", "same-ID mark dictionary is reused and fully updated")
	cache.mark(2, Vector3.ONE, {"kind": 1, "name_colour": 0})
	expect(original.position == Vector3.ONE and original.type == &"player", "actor-ID reuse replaces prior style and position")
	var retained := cache.mark(3, Vector3(3, 0, 0), {"kind": 5})
	cache.clear()
	for actor_id: int in 100:
		cache.mark(actor_id + 100, Vector3(actor_id, 0, 0), {"kind": 5, "name_colour": actor_id})
	expect(retained.position == Vector3(3, 0, 0) and retained.type == &"creature", "held overlay row is never reused for another actor")
	var current := {1: null, 2: null, 3: null, 4: null, 5: null, 6: null, 7: null}
	cache.retain(current)
	for actor_id: int in 500:
		cache.mark(actor_id, Vector3(actor_id, 0, 0), {"kind": 5, "name_colour": actor_id})
		expect(cache._marks.size() <= current.size() + Cache.ACTOR_GRACE, "actor churn stays bounded")
		expect(cache._styles.size() <= Cache.MAX_STYLES, "style churn stays bounded")
	cache.retain({})
	expect(cache._marks.size() <= Cache.ACTOR_GRACE and cache._style_keys.size() == cache._marks.size(), "departed actors release data within grace")
	cache.clear()
	expect(cache._marks.is_empty() and cache._style_keys.is_empty() and cache._styles.is_empty(), "clear releases all cached data")
	await _main_collection_integration()
	print("map actor marker cache: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)


func _row_at(main: Control, position: Vector3) -> Dictionary:
	for row: Dictionary in main.call("_collect_minimap_marks"):
		if row.get("position") == position:
			return row
	return {}

func _main_collection_integration() -> void:
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.set_process(false)
	root.get_node("Network").set_process(false)
	(main.get("game_view") as Control).show()
	(main.get("login_panel") as Control).hide()
	(main.get("creation_panel") as Control).hide()
	var self_mark := main.get("player_map_marker") as Node3D
	if self_mark != null:
		self_mark.hide()
	var state := root.get_node("AppState")
	state.set("current_map", "landfall_town")
	state.set("local_actor_id", 12000)
	var dto := {"actor_id": 12001, "actor_type": 746, "kind": 5, "name": "Marker cache fixture",
		"x": 1, "y": 1, "rotation": 0, "health": 40, "max_health": 40, "alive": true}
	state.set("actors", {12001: dto})
	var actor := ReplicatedActor3D.new()
	var errors := actor.configure(dto, CoordinateAdapter.new(), {}, {}, {}, false)
	expect(errors.is_empty() and actor.is_model_deferred() and actor.get_node_or_null("NativeModel") == null,
		"fixture uses the actual deferred-body construction path without an imported model")
	(main.get("world_root") as Node3D).add_child(actor)
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.set_drawn(false)
	actor.set_crowd_hidden(true)
	var position := Vector3(17.25, 2.75, -9.5)
	actor.global_position = position
	(main.get("actor_nodes") as Dictionary)[12001] = actor
	var row := _row_at(main, position)
	expect(not row.is_empty() and row.type == &"creature", "Main retains the living deferred/crowd-hidden actor dot")
	position = Vector3(23.75, 4.25, -11.5)
	actor.global_position = position
	var moved := _row_at(main, position)
	expect(not moved.is_empty() and row.position == position and moved.position == position,
		"Main reuses the mark and reads interpolated node position rather than the DTO tile")
	dto["name_colour"] = 14
	var restyled := _row_at(main, position)
	expect(restyled.type == &"invasion" and restyled.colour == ReplicatedActor3D.INVASION_MAP_DOT_COLOUR,
		"Main refreshes cached style when the authoritative name colour changes")
	dto["kind"] = 1
	expect(_row_at(main, position).type == &"player", "Main refreshes cached style when actor kind changes")
	dto["kind"] = 5
	dto["health"] = 0
	dto["alive"] = false
	expect(_row_at(main, position).is_empty(), "Main still omits dead creature marks before consulting the cache")
	dto["health"] = 40
	dto["alive"] = true
	actor.hide()
	expect(_row_at(main, position).is_empty(), "Main still omits actors hidden by visibility/secret-section state")
	actor.show()
	expect(not _row_at(main, position).is_empty(), "a visible living actor returns after filtering changes")
	state.set("local_actor_id", 12001)
	expect(_row_at(main, position).is_empty(), "local-player duplicate filtering stays outside the cache")
	state.set("local_actor_id", 12000)
	var cartography := main.get("_v2_cartography") as Dictionary
	cartography["interiors"] = {"landfall_town": {"serviceMarkers": [{"name": "Cache Merchant", "label": "Fixture shop",
		"category": "general_store", "position": [0.0, 0.0]}]}}
	dto["kind"] = 2
	dto["name"] = "CACHE MERCHANT"
	expect(_row_at(main, position).is_empty(), "Main retains case-insensitive service-NPC duplicate filtering")
	dto["kind"] = 1
	expect(_row_at(main, position).type == &"player", "a player sharing a service name keeps their own mark")
	actor.free()
	expect(_row_at(main, position).is_empty(), "a freed actor entry is safely ignored before its cast/cache lookup")
	var actual_cache := main.get("_map_actor_marker_cache") as RefCounted
	expect(not (actual_cache.get("_marks") as Dictionary).is_empty(), "integration populated the production Main cache")
	main.call("_clear_world_presentation", true)
	expect((actual_cache.get("_marks") as Dictionary).is_empty() and (actual_cache.get("_styles") as Dictionary).is_empty(),
		"actual world-presentation clear releases actor and style data")
	state.set("actors", {})
	main.queue_free()
	await process_frame
	await process_frame
