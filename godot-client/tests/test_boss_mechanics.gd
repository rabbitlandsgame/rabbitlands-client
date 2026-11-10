extends SceneTree
const Cue = preload("res://src/world/boss_mechanic_3d.gd")
const Adapter = preload("res://src/world/coordinate_adapter.gd")
var failures := 0

func _init() -> void:
	create_timer(30).timeout.connect(func(): push_error("Boss cues timed out"); quit(98))
	call_deferred("run")

func check(ok: bool, message: String) -> void:
	if not ok:
		push_error(message)
		failures += 1

func frame(style := "frontal_cleave") -> Dictionary:
	return {"kind":"boss_mechanic", "id":"trial", "style":style, "phase":"warning",
		"actor_id":1, "map_id":"arena", "seconds":1.5, "tiles":[[1,1],[2,1]],
		"links":[], "actors":[], "label":"Dodge the cone"}

func method(source: String, name: String) -> String:
	var begin := source.find("func " + name + "(")
	var end := source.find("\nfunc ", begin+1)
	return source.substr(begin, end-begin if end >= 0 else -1)

func run() -> void:
	var world := Node3D.new()
	root.add_child(world)
	var a := Node3D.new()
	var b := Node3D.new()
	world.add_child(a)
	world.add_child(b)
	b.position.x = 4
	var actors := {1:a, 2:b}
	var adapter := Adapter.new()
	var sample := func(_point: Vector3) -> float: return 2.0
	for style: String in Cue.STYLES:
		var event := frame(style)
		check(Cue.accepts(event), "all ten styles are supported")
		var cue := Cue.new()
		world.add_child(cue)
		cue.configure(event, adapter, actors, sample)
		check(cue.vertex_count == 60, "each server tile has fill and four borders")
		check(is_equal_approx(cue.ground(Vector2i(1,1)).y, 2.065), "warnings follow sampled terrain")
		event.actors = [{"id":1,"label":"◆ TRUE"},{"id":2,"label":"○ DECOY", "friendly":true}]
		event.links = [[1,2]]
		cue.apply_event(event)
		cue.apply_event(JSON.parse_string(JSON.stringify(event)))
		cue._process(0.1)
		check(cue.labels.size() == 3 and cue.vertex_count == 66, "true-target labels and tethers are drawn")
		check(cue.friendly_actor(2) == (style == "protect_keeper"), "only the keeper is a friendly spell target")
		var replacement := Node3D.new()
		world.add_child(replacement)
		actors[2] = replacement
		check(not cue.friendly_actor(2), "reused actor IDs do not inherit objective targeting")
		actors[2] = b
		replacement.queue_free()
		event.tiles = [[-1,1],[NAN,2],["bad",3],{}]
		event.links = [[9999,2],{}]
		cue.apply_event(event)
		check(cue.vertex_count == 0, "invalid tiles and missing actors do not draw bogus hazards")
		cue._process(30.0)
		await process_frame
		check(not is_instance_valid(cue), "expired server warning is removed")
	var invalid := frame()
	invalid.style = "unknown"
	check(not Cue.accepts(invalid), "unknown styles are rejected")
	invalid = frame()
	invalid.seconds = INF
	check(not Cue.accepts(invalid), "unbounded duration is rejected")
	# Compile the actual live dispatch functions with only their external
	# dependencies supplied. This exercises the shipped handler, not a copy.
	var source := FileAccess.get_file_as_string("res://src/app/main.gd")
	var harness := GDScript.new()
	harness.source_code = """extends Node
class BossTestMapRegistry:
	static func normalize_server_map_id(value: String) -> String: return value
var AppState := {"current_map":"arena"}
var adapter = preload("res://src/world/coordinate_adapter.gd").new()
var actor_nodes: Dictionary = {}
var world_root: Node3D
var _boss_mechanic_cues: Dictionary = {}
var _effects_enabled := false
func _campaign_surface_height(_point: Vector3) -> float: return 0.0
""" + method(source, "_on_boss_mechanic") + "\n" + method(source, "_clear_boss_mechanic_cues") \
		+ "\n" + method(source, "_is_boss_objective")
	# Keep the dependency shim distinct from the imported global script class.
	harness.source_code = harness.source_code.replace("MapRegistry.", "BossTestMapRegistry.")
	var loaded := harness.reload()
	check(loaded == OK, "live boss-warning dispatch compiles")
	if loaded == OK:
		var main: Node = harness.new()
		root.add_child(main)
		main.world_root = world
		main.actor_nodes = actors
		var event := frame()
		main._on_boss_mechanic(JSON.parse_string(JSON.stringify(event)))
		check(main._boss_mechanic_cues.size() == 1, "network data reaches essential warning even with particles disabled")
		var keeper_event := frame("protect_keeper")
		keeper_event.id = "keeper"
		keeper_event.actors = [{"id":2, "label":"KEEPER", "friendly":true}]
		main._on_boss_mechanic(keeper_event)
		check(main._is_boss_objective(2), "live dispatch exposes the keeper to support targeting")
		keeper_event.phase = "clear"
		main._on_boss_mechanic(keeper_event)
		check(not main._is_boss_objective(2), "clear retires friendly targeting")
		event.map_id = "other_map"
		event.id = "foreign"
		main._on_boss_mechanic(event)
		check(main._boss_mechanic_cues.size() == 1, "foreign-map warning is ignored")
		event = frame()
		event.phase = "impact"
		main._on_boss_mechanic(event)
		event.phase = "clear"
		main._on_boss_mechanic(event)
		check(main._boss_mechanic_cues.has("trial:impact"), "impact flash survives authoritative warning clear")
		main._clear_boss_mechanic_cues()
		check(main._boss_mechanic_cues.is_empty(), "map/session teardown clears cues")
		main.queue_free()
	world.queue_free()
	await process_frame
	print("Boss cue checks: ", "passed" if failures == 0 else str(failures) + " failures")
	quit(0 if failures == 0 else 1)
