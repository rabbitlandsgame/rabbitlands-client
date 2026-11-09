extends Node3D
## Essential encounter warnings. Geometry is the server's affected tile set;
## this node only draws it and never decides hits or changes actor movement.
const Geometry = preload("res://src/world/combat_effect_mesh.gd")
const STYLES := ["frontal_cleave", "shared_impact", "expanding_shockwave", "line_charge",
	"chain_lightning", "elemental_attunement", "stagger_window", "true_reflections",
	"breakable_tether", "protect_keeper"]
const MAX_TILES := 512
var event: Dictionary = {}
var remaining := 0.0
var actor_nodes: Dictionary = {}
var adapter: RefCounted
var surface: Callable
var mesh := ImmediateMesh.new()
var geometry: MeshInstance3D
var material := Geometry.material()
var labels: Dictionary = {}
var heights: Dictionary = {}
var redraw_in := 0.0
var vertex_count := 0
var source_life: WeakRef
var cached_origin := Vector3(INF, INF, INF)
var friendly_lives: Dictionary = {}

static func accepts(data: Dictionary) -> bool:
	return str(data.get("style", "")) in STYLES and str(data.get("id", "")).length() in range(1, 65) \
		and str(data.get("phase", "")) in ["warning", "impact", "clear"] \
		and is_finite(float(data.get("seconds", 0.0)))

func configure(data: Dictionary, coordinate_adapter: RefCounted, actors: Dictionary, height_sample: Callable) -> void:
	adapter = coordinate_adapter
	actor_nodes = actors
	surface = height_sample
	top_level = true
	global_transform = Transform3D.IDENTITY
	var source := actors.get(int(data.get("actor_id", -1))) as Node3D
	source_life = weakref(source) if is_instance_valid(source) else null
	geometry = MeshInstance3D.new()
	geometry.mesh = mesh
	geometry.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	geometry.layers = 1
	add_child(geometry)
	add_to_group("boss_mechanic_cues")
	apply_event(data)

func apply_event(data: Dictionary) -> void:
	if not accepts(data): return
	event = data.duplicate(true)
	remaining = clampf(float(data.get("seconds", 0.0)), 0.05, 30.0)
	if heights.size() > MAX_TILES * 2: heights.clear()
	for row: Variant in labels.values():
		if is_instance_valid(row.node): row.node.queue_free()
	labels.clear()
	friendly_lives.clear()
	var rows: Array = data.get("actors", []) if data.get("actors", []) is Array else []
	rows = rows.slice(0, 8)
	var source_id := int(data.get("actor_id", -1))
	var title := str(data.get("label", "")).left(160)
	if not title.is_empty(): _label(source_id, title, true)
	for row: Variant in rows:
		if row is Dictionary:
			var actor_id := int(row.get("id", -1))
			_label(actor_id, str(row.get("label", "")).left(80), false)
			var actor := actor_nodes.get(actor_id) as Node3D
			if event.get("style") == "protect_keeper" and bool(row.get("friendly", false)) and is_instance_valid(actor):
				friendly_lives[actor_id] = weakref(actor)
	redraw_in = 0.0
	redraw()

func friendly_actor(actor_id: int) -> bool:
	if remaining <= 0.0 or is_queued_for_deletion() or not friendly_lives.has(actor_id): return false
	var source := source_life.get_ref() as Node3D if source_life != null else null
	if not is_instance_valid(source) or actor_nodes.get(int(event.get("actor_id", -1))) != source \
			or source.get("current_action") == &"death": return false
	var actor := friendly_lives[actor_id].get_ref() as Node3D
	return is_instance_valid(actor) and actor_nodes.get(actor_id) == actor and actor.get("current_action") != &"death"

func _label(actor_id: int, text: String, countdown: bool) -> void:
	var label := Label3D.new()
	label.text = text
	label.font_size = 20 if countdown else 22
	label.outline_size = 5
	label.pixel_size = 0.0012953
	label.fixed_size = true
	label.width = 320
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	if countdown: label.offset.y = 32
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.modulate = Color(1.0, 0.94, 0.72) if countdown else Color.WHITE
	label.no_depth_test = true
	add_child(label)
	labels[str(actor_id) + (":title" if countdown else ":marker")] = {
		"node": label, "id": actor_id, "text": text, "countdown": countdown}

func _process(delta: float) -> void:
	var source := source_life.get_ref() as Node3D if source_life != null else null
	if not is_instance_valid(source) or actor_nodes.get(int(event.get("actor_id", -1))) != source \
			or source.get("current_action") == &"death":
		queue_free()
		return
	remaining -= delta
	if remaining <= 0.0:
		queue_free()
		return
	for raw: Variant in labels.values():
		var row: Dictionary = raw
		var node: Label3D = row.node
		var actor := actor_nodes.get(int(row.id)) as Node3D
		node.visible = is_instance_valid(actor)
		if node.visible:
			node.global_position = actor.global_position + Vector3.UP * (4.1 if row.countdown else 3.0)
			if row.countdown:
				node.text = "%s  %.1fs" % [row.text, remaining]
	redraw_in -= delta
	if redraw_in <= 0.0: redraw()

func ground(tile: Vector2i) -> Vector3:
	var point: Vector3 = adapter.tile_center(tile.x, tile.y)
	if not heights.has(tile):
		var sampled: float = surface.call(point) if surface.is_valid() else NAN
		heights[tile] = sampled if is_finite(sampled) else point.y
	point.y = float(heights[tile]) + 0.065
	return point

func redraw() -> void:
	redraw_in = 0.1
	if cached_origin != adapter.origin:
		cached_origin = adapter.origin
		heights.clear()
	mesh.clear_surfaces()
	vertex_count = 0
	var raw_tiles: Variant = event.get("tiles", [])
	var tiles: Array = raw_tiles if raw_tiles is Array else []
	var raw_links: Variant = event.get("links", [])
	var links: Array = raw_links if raw_links is Array else []
	tiles = tiles.slice(0, MAX_TILES).filter(func(raw: Variant) -> bool:
		return raw is Array and raw.size() == 2 and typeof(raw[0]) in [TYPE_INT, TYPE_FLOAT] \
			and typeof(raw[1]) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(raw[0])) \
			and is_finite(float(raw[1])) and float(raw[0]) >= 0 and float(raw[0]) <= 65535 \
			and float(raw[1]) >= 0 and float(raw[1]) <= 65535)
	links = links.slice(0, 8).filter(func(raw: Variant) -> bool:
		return raw is Array and raw.size() == 2 and typeof(raw[0]) in [TYPE_INT, TYPE_FLOAT] \
			and typeof(raw[1]) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(raw[0])) \
			and is_finite(float(raw[1])) and float(raw[0]) == floor(float(raw[0])) \
			and float(raw[1]) == floor(float(raw[1])) and is_instance_valid(actor_nodes.get(int(raw[0]))) \
			and is_instance_valid(actor_nodes.get(int(raw[1]))))
	if tiles.is_empty() and links.is_empty(): return
	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES, material)
	var tint := Color(1.0, 0.34, 0.12, 0.3)
	if event.get("style") == "shared_impact": tint = Color(0.1, 0.75, 1.0, 0.3)
	if event.get("style") == "chain_lightning": tint = Color(0.72, 0.35, 1.0, 0.3)
	if event.get("phase") == "impact": tint = Color(1.0, 0.95, 0.7, 0.55)
	var half: float = float(adapter.metres_per_tile) * 0.48
	for raw: Variant in tiles.slice(0, MAX_TILES):
		if not raw is Array or raw.size() != 2: continue
		var x := float(raw[0])
		var y := float(raw[1])
		if not is_finite(x) or not is_finite(y) or x < 0 or x > 65535 or y < 0 or y > 65535: continue
		var point := ground(Vector2i(int(x), int(y)))
		var corners := [point + Vector3(-half, 0, -half), point + Vector3(half, 0, -half),
			point + Vector3(half, 0, half), point + Vector3(-half, 0, half)]
		mesh.surface_set_color(tint)
		for index: int in [0, 1, 2, 0, 2, 3]:
			mesh.surface_add_vertex(corners[index])
			vertex_count += 1
		for index: int in 4:
			Geometry.line(mesh, corners[index], corners[(index+1)%4], half*0.065, Color(tint, 0.85))
			vertex_count += 6
	for raw: Variant in links.slice(0, 8):
		if not raw is Array or raw.size() != 2: continue
		var a := actor_nodes.get(int(raw[0])) as Node3D
		var b := actor_nodes.get(int(raw[1])) as Node3D
		if is_instance_valid(a) and is_instance_valid(b):
			Geometry.line(mesh, a.global_position+Vector3.UP, b.global_position+Vector3.UP,
				0.12, Color(0.9, 0.65, 1.0, 0.9), Vector3.UP)
			vertex_count += 6
	# Empty/invalid messages must not leave an unfinished mesh surface.
	if vertex_count > 0: mesh.surface_end()
	else: mesh.clear_surfaces()
