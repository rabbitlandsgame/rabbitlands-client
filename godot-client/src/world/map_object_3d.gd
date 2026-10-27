class_name MapObject3D
extends StaticBody3D
const WORLD_LABEL_STYLE := preload("res://src/ui/world_label_style.gd")
const TextColors := preload("res://src/ui/text_colors.gd")
const STORAGE_GLOW_SHADER := preload("res://src/world/storage_glow.gdshader")
const SPELL_MATERIALS := preload("res://src/world/spell_visual_material.gd")
## A clickable world object: a harvest node or an interactive.
##
## The world package renders the surrounding scenery as ordinary map geometry,
## and the client has no way to tell which mesh is a resource - the legacy
## client tried to match object basenames against a lowercase harvestable list
## and matched nothing, because the packs wrote relative paths. So the server
## states which object ids exist and where they are, and this places the object
## at each one rather than guessing from the scene.
##
## What stands on the tile is the thing itself: the reed bed, the ore seam, the
## notice board, the well. Both were a plain unshaded ring before, green for a
## harvest node and blue for an interactive, which said "this is clickable" and
## nothing else - a plaza of service points and a hillside of ore read as the
## same row of circles. The models are authored per resource and per role in
## `data/world/objects.json`; the ring survives only as the fallback for an
## object the registry does not describe, and as the mark on a node the player
## is currently harvesting.
##
## The map cameras keep their coloured discs. A whole map at once is too small a
## scale for a prop to read at, and the legend names the colours.
##
## A continent-v2 package may present its harvest nodes (the harvest
## presentation, owner-approved 2026-10-14; `presentation`): a node is then a
## whole natural unit - a crop-row segment at the row's exact yaw, picked over
## its footprint, one of its label's model variants - or promoted scenery, a
## kit tree already standing in its chunk whose mesh is bound as its pick
## (`bind_placement`). A grouped node leaves its map marker to its grouping,
## which main marks once.

const PICK_LAYER := 32
## The disc's radius in metres. The full map frames 1600 metres at once, so
## a disc sized for the world is a pixel there; this is sized for the map.
const MAP_MARKER_RADIUS := 7.0
## Harvest nodes and interactives are told apart on the map by colour rather
## than by a label the player has to read before every click. The legend in the
## full map's sidebar names both.
const HARVEST_COLOUR := Color(0.42, 0.86, 0.44)
const INTERACTIVE_COLOUR := Color(0.95, 0.62, 0.24)
const ACTIVE_COLOUR := Color(1.0, 0.86, 0.36)
## A waygate and a way off the map, the two the legend has always named and
## neither map drew: the cyan P and the red X, in the legend's own colours.
## Both are drawn as glyphs by the map overlays rather than as discs, so
## they read as what they are at any zoom.
const PORTAL_COLOUR := Color("58e1ff")
const EXIT_COLOUR := Color("ff4747")
const PORTAL_GLYPH := "P"
const EXIT_GLYPH := "X"
const STORAGE_COLOUR := Color("d6bb7a")
## The camera can orbit 90 m from the player; nearby storage still draws there.
const STORAGE_WORLD_RANGE := 120.0
## Draw after transparent paving, whose distance sort changes as we approach.
const STORAGE_EFFECT_PRIORITY := 2
## Decorative plaza paving sits above the navigation mesh (6.5 cm in Landfall).
## Leave room for it while preserving the halo's normal scene occlusion.
const STORAGE_GLOW_CLEARANCE := 0.12
const GAMEPLAY_LAYER := 2
## The waygate texts the continent tool writes name where the gate leads in
## these words, and a boat's text where it sails; the label beside the P on the
## full map is that name (the rest of its sentence).
const PORTAL_DESTINATION_PHRASE := "Beyond it lies "
const BOAT_DESTINATION_PHRASE := "Bound for "
## An underground passage's end names the section it leads into in these words
## (underground.py): "A way leads on into <section>. <danger>."
const PASSAGE_DESTINATION_PHRASE := "A way leads on into "
## The ring drawn under a node while the player is harvesting it, and under any
## object the registry could not place a model for.
const RING_INNER_RADIUS := 0.62
const RING_OUTER_RADIUS := 0.78
## A building's street door (objects.json `building: true`, Landfall Town)
## names itself within this many metres of the player, or under the pointer:
## six doors stand within 45 m along one avenue, and labels drawn to 80 m
## through the walls covered the street. Its interior exit follows the same
## rule. Cave mouths keep their permanent labels.
const BUILDING_LABEL_METRES := 12.0
## A building door's label never draws beyond this distance from the camera,
## whatever the player's distance: it is a door's name, not a landmark.
const BUILDING_LABEL_RANGE := 45.0

var object_id: int = -1
var kind: int = 0
var server_tile: Vector2i = Vector2i.ZERO
var label: String = ""
var detail: String = ""
var model_id: String = ""
## Set by map presentation when a server-owned departure is available.
var departure_available := false
## The ring as built, before any ground was laid under it. Kept so an object
## re-draped after a map's walk surface arrives is shaped by the ground it
## stands on rather than by whatever it was draped over before.
var _ring_flat: Mesh = null
var _storage_glow: MeshInstance3D
var _storage_glow_flat: Mesh
var _storage_sparks: GPUParticles3D
## True when the registry hands this object's art to the map package rather
## than standing a model on it; see `interactives.mapAuthored`.
var _map_authored: bool = false
## How the map's own package presents this object, scoped to that map by the
## caller (object ids repeat across maps): the harvest presentation of a
## continent-v2 package's `harvestables` entry (eloria-assets/.../
## harvest_presentation.py: `variant`, `yaw` in degrees, `footprint` [length,
## width] metres, `grouping`, `bind` {node, chunk, height}), and a lantern
## map's authored pick (`pick` {height, radius}). Empty for every package
## published before the harvest presentation, which keeps the random yaw and
## scale, one model per label, the 0.9 m pick and one map mark per node.
##
## A wall node (the underground's veins, pass 2: `placement` "wall") stands its
## label's wall seam art (objects.json `harvestables.wallVariants[label]`,
## picked by `variant`) set into the rock face: `yaw` turns its +Z out of the
## rock and `inset` (metres) moves it from the tile's centre back along that
## facing to the face (tools/prepare_underground_scenery.py writes both from
## build_underground.vein_faces). Its pick and name go with it.
var presentation: Dictionary = {}
## The harvest grouping this node belongs to, or "".
var grouping: String = ""
## True when the maps mark this node's grouping instead of the node: it then
## has no map marker of its own.
var grouped := false
## Promoted scenery: the name of the placed kit node in the map's own chunk
## whose mesh is this node's art (`presentation.bind.node`), or "". Nothing is
## stood on the tile; `bind_pick_model` makes the placed mesh clickable once
## its chunk is resident.
var bound_node_name: String = ""
## The yaw the model stands at (the package's, or the seeded random one), so
## a footprint's pick box turns with it.
var _model_yaw := 0.0
## Where the model stands relative to the tile's centre: zero, except for a wall
## node, whose model is set back into the rock face (`presentation.inset`).
var _model_offset := Vector3.ZERO
var _bound_body: WeakRef = null
## A building's street door, standing on its exterior tile: picked, named near
## the player or under the pointer, no ring (`BUILDING_LABEL_METRES`).
var building_door := false
## The same door object on the interior's exit tile (one object id serves both
## ends): named by the record's `exitLabel` under the same rule.
var building_exit := false
## The name a building door or exit gives itself (the record's `label` or
## `exitLabel`), without the "Click to enter" line.
var door_label := ""
## Where the door's own label stands relative to the tile's centre: the
## painted door on the facade (`modelOffset`), or the tile.
var _door_point := Vector3.ZERO
## A way on inside an interior map: a passage end (objects.json
## `passage: true`), and its record's label: the end's own for the town's
## stairs ("Upstairs: the guest rooms"), the section it leads into for a cave
## passage (retarget_underground.py). Empty for every other object.
var _passage_end := false
var _passage_label := ""

## The smallest side a footprint pick box is given, so a thin hedge or a kelp
## strand is still a target a player can hit.
const FOOTPRINT_PICK_MINIMUM := 0.6

## `catalog` is `data/world/objects.json`, whole. It has no default: this took
## a release standing every node in the world on a bare ring because the one
## caller left the argument off and an empty registry is a legal one.
## `map_presentation` is this object's entry in its map's presentation (see
## `presentation`); empty when the map's package states none.
func configure(dto: Dictionary, adapter: CoordinateAdapter,
		catalog: Dictionary, authored_presentation: bool = false,
		map_presentation: Dictionary = {}) -> void:
	object_id = int(dto.get("object_id", -1))
	kind = int(dto.get("kind", 0))
	server_tile = Vector2i(int(dto.get("x", 0)), int(dto.get("y", 0)))
	label = str(dto.get("label", ""))
	detail = str(dto.get("detail", ""))
	name = "MapObject_%d" % object_id
	collision_layer = PICK_LAYER
	collision_mask = 0
	position = adapter.tile_center(server_tile.x, server_tile.y)
	_map_authored = authored_presentation
	presentation = map_presentation.duplicate(true)
	grouping = str(presentation.get("grouping", ""))
	grouped = bool(presentation.get("grouped", false)) and not grouping.is_empty()
	_build_visual(catalog)

func is_harvestable() -> bool:
	return kind == EloriaProtocol.MAP_OBJECT_HARVEST

## A harvest node set into a rock face (`presentation.placement` "wall").
func is_wall_placed() -> bool:
	return is_harvestable() and str(presentation.get("placement", "")) == "wall"

## A way off the map the server stated from its portal tiles. Nothing stands
## on the tile and nothing is clicked; the tiles do the work when a player
## walks onto them, and the maps draw the X.
func is_exit() -> bool:
	return kind == EloriaProtocol.MAP_OBJECT_EXIT

## A waygate: the clickable object standing at a march.
func is_portal() -> bool:
	return not is_exit() and (label == "Portal" or model_id == "portal")

func is_storage() -> bool:
	return not is_harvestable() and not is_exit() and (label == "Storage" or model_id == "storage")

func offers_map_change() -> bool:
	return is_portal() or departure_available

## Bind authored scenery to this object's normal server action. Exact mesh
## shapes include thin sails without making the empty space around a boat
## clickable. Parenting to the model keeps the target on moving scenery.
func bind_pick_model(model: Node3D) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = "MapObjectPickProxy"
	body.collision_layer = 0
	body.collision_mask = 0
	body.set_meta("map_object_target", weakref(self))
	model.add_child(body)
	var meshes: Array[Node] = model.find_children("*", "MeshInstance3D", true, false)
	if model is MeshInstance3D:
		meshes.append(model)
	for node: Node in meshes:
		var mesh_instance := node as MeshInstance3D
		if mesh_instance.mesh == null or not _drawn(mesh_instance):
			continue
		var shape := mesh_instance.mesh.create_trimesh_shape()
		if shape == null:
			continue
		shape.backface_collision = true
		var collision := CollisionShape3D.new()
		collision.shape = shape
		body.add_child(collision)
		collision.global_transform = mesh_instance.global_transform
	# A refreshed server object must not leave an orphaned pick body behind.
	tree_exiting.connect(body.queue_free)
	return body

## A mesh the world draws: visible in the tree, or a member the loader's
## static batching hid because its MultiMesh draws it (WorldLoader.BATCH_META)
## - a grove of one kit olive tree is batched, and its trees are still there.
static func _drawn(mesh_instance: MeshInstance3D) -> bool:
	if mesh_instance.is_visible_in_tree():
		return true
	if not mesh_instance.has_meta(WorldLoader.BATCH_META):
		return false
	var parent := mesh_instance.get_parent() as Node3D
	return parent == null or parent.is_visible_in_tree()

## Promoted scenery: binds this node's pick to `model`, the placed kit node its
## package names (`bound_node_name`), and makes it clickable. Returns false
## when there is nothing to bind. Called again whenever the model's chunk
## comes back after being streamed out.
func bind_placement(model: Node3D) -> bool:
	if model == null or bound_node_name.is_empty():
		return false
	release_placement()
	var body := bind_pick_model(model)
	body.collision_layer = PICK_LAYER
	_bound_body = weakref(body)
	return body.get_child_count() > 0

## True while the placed kit node this node presents is bound and clickable.
func placement_bound() -> bool:
	if _bound_body == null:
		return false
	var body := _bound_body.get_ref() as StaticBody3D
	return is_instance_valid(body) and not body.is_queued_for_deletion()

## Lets go of the placed kit node, as its chunk streams out.
func release_placement() -> void:
	if not placement_bound():
		_bound_body = null
		return
	var body := _bound_body.get_ref() as StaticBody3D
	body.collision_layer = 0
	body.queue_free()
	_bound_body = null

static func from_pick_collider(collider: Variant) -> MapObject3D:
	if collider is MapObject3D:
		return collider as MapObject3D
	if collider is StaticBody3D:
		var target: Variant = collider.get_meta("map_object_target", null)
		if target is WeakRef:
			var object := target.get_ref() as MapObject3D
			if is_instance_valid(object) and not object.is_queued_for_deletion():
				return object
	return null

## Where this leads, as far as the server said: an exit is named for its
## destination, and a waygate's, a boat's or a cave passage's text names it in
## a fixed phrase; a building door and a town stair end are named by their
## objects.json records. Empty when none of these applies.
func destination() -> String:
	if is_exit():
		return label
	if is_portal():
		for phrase: String in [PORTAL_DESTINATION_PHRASE, BOAT_DESTINATION_PHRASE, PASSAGE_DESTINATION_PHRASE]:
			if detail.contains(phrase):
				return detail.get_slice(phrase, 1).get_slice(". ", 0).trim_suffix(".").strip_edges()
		# A building's door says what it is ("The Unlit Boat. Open to all."),
		# not where it leads in the gates' phrase: its record names it.
		if (building_door or building_exit) and not door_label.is_empty():
			return door_label
		# A town stair end's text is its own label ("Upstairs: the guest
		# rooms."), not the caves' phrase: its passage record names it, else
		# the text's first sentence. A cave passage end's text always holds
		# the phrase, so it is answered above, as it always was.
		if _passage_end and not detail.strip_edges().is_empty():
			if not _passage_label.is_empty():
				return _passage_label
			return detail.get_slice(". ", 0).trim_suffix(".").strip_edges()
	return ""

## Whether main should keep this object's label in step with the player's
## distance and the pointer (`update_label_focus`): a building door or exit.
func wants_label_focus() -> bool:
	return (building_door or building_exit) and get_node_or_null("EntranceLabel") != null

## Shows a building door's or exit's name while the player stands within
## BUILDING_LABEL_METRES of the door (measured flat, from the painted door) or
## while the pointer is on it. `player_position` is the local character's
## world position (INF when there is none).
func update_label_focus(player_position: Vector3, hovered: bool) -> void:
	var title := get_node_or_null("EntranceLabel") as Label3D
	if title == null:
		return
	var near := false
	if player_position.is_finite() and is_inside_tree():
		var door := global_position + _door_point
		near = Vector2(player_position.x - door.x, player_position.z - door.z).length() \
			<= BUILDING_LABEL_METRES
	var shown := hovered or near
	if title.visible != shown:
		title.visible = shown

## The glyph the maps draw for this object, or "" for one drawn as a disc.
func map_glyph() -> String:
	if is_exit():
		return EXIT_GLYPH
	if is_portal():
		return PORTAL_GLYPH
	return ""

func set_surface_height(height: float) -> void:
	global_position.y = height + 0.05
	_drape_ring()
	if is_instance_valid(_storage_glow):
		var draped := GroundDrape.drape(_storage_glow, _storage_glow_flat,
			STORAGE_GLOW_CLEARANCE)
		_storage_glow.mesh = _storage_glow_flat if draped == null else draped

func set_particles_enabled(enabled: bool) -> void:
	if is_instance_valid(_storage_sparks):
		_storage_sparks.visible = enabled
		_storage_sparks.emitting = enabled

## Marks the node the player is currently harvesting. The ring is hidden while
## an object is merely standing there, so this is the only thing that draws it
## on an object whose model loaded.
func set_active(active: bool) -> void:
	var ring: MeshInstance3D = get_node_or_null("Ring") as MeshInstance3D
	if not is_instance_valid(ring):
		return
	ring.visible = active or model_id.is_empty()
	var material: StandardMaterial3D = ring.material_override as StandardMaterial3D
	if material == null:
		return
	material.albedo_color = ACTIVE_COLOUR if active else _marker_colour()
	material.albedo_color.a = 0.75
	_drape_ring()

## Lay the ring over the ground it is drawn on.
##
## The ring is a flat circle a metre and a half across, and the ground under it
## is not flat: on a region such as Whitehorn Range most of it disappeared into
## the slope, leaving a crescent that grew and shrank as the camera moved past.
## Draping it holds the whole circle the same height over the ground all the
## way round, so what is drawn stays the ring the node is marked with.
func _drape_ring() -> void:
	var ring: MeshInstance3D = get_node_or_null("Ring") as MeshInstance3D
	if not is_instance_valid(ring) or not ring.visible:
		return
	if _ring_flat == null:
		_ring_flat = ring.mesh
	var draped: ArrayMesh = GroundDrape.drape(ring, _ring_flat)
	ring.mesh = _ring_flat if draped == null else draped

func _marker_colour() -> Color:
	if is_exit():
		return EXIT_COLOUR
	if is_portal():
		return PORTAL_COLOUR
	if is_storage():
		return STORAGE_COLOUR
	return HARVEST_COLOUR if is_harvestable() else INTERACTIVE_COLOUR

## The colour this object is marked in on either map. The full map draws the
## modelled disc below; the minimap draws its own mark and asks for the colour
## here, so both maps mark an ore seam in one green rather than two.
func map_dot_colour() -> Color:
	return _marker_colour()

## The registry entry for this object, or an empty dictionary.
##
## A harvest node is named by its resource label and an interactive by the label
## the server derives from its role, because that is all either of them carries
## on the wire. The registry holds both maps, written by the same generator that
## writes the models, so a resource whose id is not its slugified name - Slate
## and Deep Coal both keep their bootstrap model names - resolves without the
## client guessing at a filename.
##
## A harvest label may also name several models (`harvestables.variants`, a
## list per label, generated with the registry): a field of one crop-row
## segment reads as a stamped lattice. The package's `variant` picks one
## (modulo the list), else the object id does (`variant_index`), so every
## client stands the same model on the same node without it being sent.
func _catalog_entry(catalog: Dictionary) -> Dictionary:
	var section: Dictionary = catalog.get(
		"harvestables" if is_harvestable() else "interactives", {}) as Dictionary
	var keys: Dictionary = section.get(
		"resources" if is_harvestable() else "roles", {}) as Dictionary
	var id: String = str(keys.get(label, ""))
	var models: Dictionary = section.get("models", {}) as Dictionary
	if is_harvestable():
		var listed: Variant = (section.get("variants", {}) as Dictionary).get(label)
		# A wall node chooses among its label's wall seam models instead; a label
		# with none keeps its own art (and its usual variants) on the wall tile.
		if is_wall_placed():
			var walls: Variant = (section.get("wallVariants", {}) as Dictionary).get(label)
			if walls is Array and not (walls as Array).is_empty():
				listed = walls
		# Only a node laid out for them stands the variants: a label's variants
		# are patch models shaped for a stated footprint (a crop-row segment
		# needs its row's yaw, a seam its face), so a node that states neither a
		# footprint nor a variant - an older lattice node, or any node of an
		# older package - keeps the label's own model. Where that model is
		# retired, only a variant marked `standsAlone` may stand in for it
		# (below); the rest are never stood at a random yaw.
		if listed is Array and not (listed as Array).is_empty() \
				and (presentation.has("footprint") or presentation.has("variant")):
			var choices: Array = listed as Array
			var chosen := str(choices[variant_index(object_id, choices.size(),
				presentation.get("variant"))])
			# A variant the registry lists but does not describe falls back to
			# the label's own model rather than to nothing.
			if models.has(chosen):
				id = chosen
	if id.is_empty():
		return {}
	var entry: Dictionary = models.get(id, {}) as Dictionary
	# The approved ironbound storage chest also represents a reward strongbox.
	# Its geometry is grounded at the origin; the old cache prop is retired.
	if label == "Cache" and bool(entry.get("retired", false)):
		var strongbox: Dictionary = models.get("storage", {})
		if bool(strongbox.get("imported", false)) and not bool(strongbox.get("retired", false)):
			entry = strongbox
	# A node no package lays out, of a label whose own model is retired,
	# stands one of the label's variants that reads right at its seeded yaw
	# and scale: `standsAlone`, a whole clump or mat (imported_world_objects.py
	# ImportedHarvestable.stands_alone). A row, hedge, seam, bank, drift or pan
	# needs the footprint and yaw its package states, so a label with none of
	# those keeps the retired model's bare ring and name until it is laid out.
	if is_harvestable() and bool(entry.get("retired", false)):
		var choices: Array = []
		for candidate: Variant in (section.get("variants", {}) as Dictionary).get(label, []):
			var variant: Dictionary = models.get(str(candidate), {})
			if bool(variant.get("imported", false)) and not bool(variant.get("retired", false)) \
					and bool(variant.get("standsAlone", false)):
				choices.append(str(candidate))
		if not choices.is_empty():
			id = choices[variant_index(object_id, choices.size())]
			entry = models[id]
	if entry.is_empty():
		return {}
	var described: Dictionary = entry.duplicate(true)
	described["id"] = id
	return described

## Which of `count` model variants node `object_id` stands: `stated` (the
## package's `variant`) modulo `count` when it is a number, else the third draw
## of the generator the object id seeds, after the two that vary its yaw and
## scale (so stating no variant leaves both where they always were).
static func variant_index(identity: int, count: int, stated: Variant = null) -> int:
	if count <= 1:
		return 0
	if stated is int or stated is float:
		return posmod(int(stated), count)
	var rng := RandomNumberGenerator.new()
	rng.seed = identity
	rng.randf()
	rng.randf()
	return rng.randi_range(0, count - 1)

func _build_visual(catalog: Dictionary) -> void:
	if get_child_count() > 0:
		return
	if is_exit():
		# Nothing to stand on the tile and nothing to click: the march or the
		# doorway is already there in the world art. The maps draw the X from
		# this node's position; see `Main._collect_map_waypoints`.
		return
	_map_authored = _map_authored or (catalog.get("interactives", {}) as Dictionary).get(
		"mapAuthored", {}).has(label)
	var entry: Dictionary = _catalog_entry(catalog)
	# The map's own authored pick (a lantern map's layout) wins over the
	# registry's, which is keyed by object id alone and so applies on every map.
	var authored: Dictionary = presentation.get("pick", {}) as Dictionary
	if authored.is_empty():
		authored = catalog.get("authoredObjects", {}).get(str(object_id), {})
	var bind: Dictionary = presentation.get("bind", {}) as Dictionary
	bound_node_name = str(bind.get("node", "")) if is_harvestable() else ""
	var height: float
	if not authored.is_empty():
		height = float(authored.get("height", 1.2))
	elif not bound_node_name.is_empty():
		# Promoted scenery: the placed kit model is the art. Nothing stands on
		# the tile; the pick binds to the placed mesh when its chunk arrives.
		height = float(bind.get("height", 1.2))
		model_id = "bound_" + bound_node_name
	else:
		height = 0.0 if _map_authored else _add_model(entry)
	if not authored.is_empty():
		model_id = "map_authored_" + str(object_id)
		# Harvest seams retain their active ring and resource map marker.
		_map_authored = _map_authored or not is_harvestable()
	# A passage end inside an interior map: its record names where it leads
	# (`destination()`, the maps' hover name for its P).
	_passage_end = bool(authored.get("passage", false)) and is_portal()
	_passage_label = str(authored.get("label", "")) if _passage_end else ""
	# The server calls both ends "Portal". Scope the exterior replacement by
	# its authored tile so the same object id does not add a second doorway
	# inside the underground map.
	var exterior_tile: Array = authored.get("exteriorTile", [])
	var entrance := bool(authored.get("entrance", false)) and (
		(exterior_tile.size() == 2 and server_tile == Vector2i(exterior_tile[0], exterior_tile[1]))
		or (exterior_tile.is_empty() and not is_portal()))
	# A building's door (Landfall Town) has no model of its own: the door is
	# painted on the townhouse's facade, and the record says where
	# (`modelOffset`, world metres from the tile's centre). The same object id
	# stands on the interior's exit tile, where `exitLabel` names the way out.
	var building := bool(authored.get("building", false)) and is_portal()
	building_door = entrance and building
	building_exit = building and not entrance and bool(authored.get("entrance", false))
	if building_door or building_exit:
		door_label = str(authored.get("label" if building_door else "exitLabel", ""))
		if door_label.is_empty():
			door_label = "The way out" if building_exit else "A door"
		var offset: Variant = authored.get("modelOffset" if building_door else "exitOffset")
		if offset is Array and (offset as Array).size() == 3:
			_door_point = Vector3(float(offset[0]), 0.0, float(offset[2]))
	if entrance:
		_map_authored = false
		model_id = ""
		_add_entrance_visual(authored)
	# A role the region package authors is already standing in the world art:
	# a secret's door is a `Secret_*` node in the region mesh, on the tile the
	# server states. A ring under one duplicates the door and advertises it.
	# A building's door is the painted door itself: picked, hovered and named,
	# with no ring on the street.
	if not _map_authored and not building_door:
		_add_ring()
	# A waygate is drawn on the maps as its glyph, not as a disc under it, and
	# a grouped node by its grouping's one mark.
	if map_glyph().is_empty() and not grouped:
		_add_map_marker()
	if building_door or building_exit:
		# One pick from the tile to the painted door, so a click on the door
		# itself or on the step in front of it both enter.
		_model_offset = _door_point * 0.5
	_add_pick_shape(height)
	if not authored.is_empty() and $PickShape.shape is CylinderShape3D:
		($PickShape.shape as CylinderShape3D).radius = float(authored.get("radius", .9))
		if building_door or building_exit:
			($PickShape.shape as CylinderShape3D).radius = maxf(float(authored.get("radius", .9)),
				_door_point.length() * 0.5 + 0.6)
	if is_storage():
		_add_storage_visual(height)
	elif entrance or building_exit:
		var title := Label3D.new()
		title.name = "EntranceLabel"
		if building_door or building_exit:
			title.text = door_label + ("\nClick to enter" if building_door else "\nClick to leave")
			title.position = _door_point + Vector3.UP * maxf(1.8,
				float(authored.get("visualHeight", authored.get("height", 0.0))) + .35)
		else:
			title.text = str(authored.get("label", "Underground entrance")) + "\nClick to enter"
			title.position.y = maxf(1.8, float(authored.get("visualHeight", 0.0)) + .35)
		title.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		title.fixed_size = true
		WORLD_LABEL_STYLE.apply(title, 15, .0012953, 5)
		TextColors.bind_property(title, "world_entrance", "modulate")
		title.no_depth_test = true
		title.layers = WORLD_LABEL_STYLE.RENDER_LAYER
		title.visibility_range_end = BUILDING_LABEL_RANGE if building_door or building_exit else 80.0
		# Named only near the player or under the pointer (main keeps it in
		# step: update_label_focus).
		title.visible = not (building_door or building_exit)
		add_child(title)
	elif label == "Cache":
		var title := Label3D.new()
		title.name = "CacheLabel"
		title.text = "Reward cache"
		title.position.y = maxf(height, .8) + .5
		title.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		title.fixed_size = true
		WORLD_LABEL_STYLE.apply(title, 16, .0012953, 5)
		TextColors.bind_property(title, "world_storage", "modulate")
		title.no_depth_test = true
		title.layers = WORLD_LABEL_STYLE.RENDER_LAYER
		title.visibility_range_end = 80
		add_child(title)
	elif is_harvestable() and (model_id.is_empty() or entry.has("resourcePalette")):
		# Name both unmodelled resources and reused mineral forms explicitly;
		# the resource material and the server label must agree.
		var title := Label3D.new()
		title.name = "ResourceLabel"
		title.text = label
		title.position = Vector3(_model_offset.x, maxf(.9,height+.15), _model_offset.z)
		title.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		title.fixed_size = true
		WORLD_LABEL_STYLE.apply(title,14,.0012953,5)
		TextColors.bind_property(title, "world_resource", "modulate")
		title.layers = WORLD_LABEL_STYLE.RENDER_LAYER
		title.visibility_range_end = 35
		add_child(title)

## Keep the service readable above the lid, with a soft animated ground halo.
## Layer 2 belongs to the gameplay camera; the maps keep their storage dot.
func _add_entrance_visual(authored: Dictionary) -> void:
	var scene := str(authored.get("scene", ""))
	if scene.is_empty():
		return
	var model := GlbSceneCache.instantiate(_external_path(scene))
	if model == null:
		return
	model.name = "EntranceModel"
	model.rotation.y = deg_to_rad(float(authored.get("yaw", 0.0)))
	# The art stands behind the portal tile, its opening on it: the served grid
	# closes the rock (export_collision.entrance_art), and the portal needs its
	# four neighbours open.
	var offset: Variant = authored.get("modelOffset")
	if offset is Array and (offset as Array).size() == 3:
		model.position = Vector3(float(offset[0]), float(offset[1]), float(offset[2]))
	add_child(model)
	model_id = "underground_entrance_" + str(object_id)

func _add_storage_visual(height: float) -> void:
	var title := Label3D.new()
	title.name = "StorageLabel"
	title.text = "Storage"
	title.position.y = maxf(height, 0.75) + 0.85
	title.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	title.fixed_size = true
	WORLD_LABEL_STYLE.apply(title, 16, 0.0012953, 5)
	TextColors.bind_property(title, "world_storage", "modulate")
	title.no_depth_test = true
	title.layers = WORLD_LABEL_STYLE.RENDER_LAYER
	title.visibility_range_end = STORAGE_WORLD_RANGE
	add_child(title)

	var material := ShaderMaterial.new()
	material.shader = STORAGE_GLOW_SHADER
	material.render_priority = STORAGE_EFFECT_PRIORITY
	material.set_shader_parameter("glow_colour", STORAGE_COLOUR)
	material.set_shader_parameter("phase", float(posmod(object_id, 17)) * 0.37)
	var plane := PlaneMesh.new()
	plane.size = Vector2(2.8, 2.8)
	plane.subdivide_width = 12
	plane.subdivide_depth = 12
	_storage_glow_flat = plane
	_storage_glow = MeshInstance3D.new()
	_storage_glow.name = "StorageGlow"
	_storage_glow.mesh = _storage_glow_flat
	_storage_glow.material_override = material
	_storage_glow.layers = GAMEPLAY_LAYER
	_storage_glow.visibility_range_end = STORAGE_WORLD_RANGE
	_storage_glow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_storage_glow)
	_add_storage_particles()

## A continuous, low ring of gold motes; approaching never restarts the stream.
func _add_storage_particles() -> void:
	var material := SPELL_MATERIALS.particle(Color("ffc764"), 5)
	material.render_priority = STORAGE_EFFECT_PRIORITY + 1
	material.next_pass.render_priority = STORAGE_EFFECT_PRIORITY + 2
	var quad := QuadMesh.new()
	quad.size = Vector2(0.24, 0.28)
	quad.material = material
	var process := ParticleProcessMaterial.new()
	process.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_RING
	process.emission_ring_axis = Vector3.UP
	process.emission_ring_radius = 1.12
	process.emission_ring_inner_radius = 0.98
	process.emission_ring_height = 0.08
	process.direction = Vector3.UP
	process.spread = 10.0
	process.gravity = Vector3.ZERO
	process.initial_velocity_min = 0.18
	process.initial_velocity_max = 0.32
	process.tangential_accel_min = 0.06
	process.tangential_accel_max = 0.14
	process.scale_min = 0.65
	process.scale_max = 1.1
	var fade := Gradient.new()
	fade.colors = PackedColorArray([Color(1, 1, 1, 0), Color.WHITE,
		Color(1, 1, 1, 0.7), Color(1, 1, 1, 0)])
	fade.offsets = PackedFloat32Array([0.0, 0.15, 0.55, 1.0])
	var ramp := GradientTexture1D.new()
	ramp.gradient = fade
	process.color_ramp = ramp
	_storage_sparks = GPUParticles3D.new()
	_storage_sparks.name = "StorageSparks"
	_storage_sparks.amount = 24
	_storage_sparks.lifetime = 2.2
	_storage_sparks.preprocess = 2.2
	_storage_sparks.randomness = 0.25
	_storage_sparks.fixed_fps = 60
	_storage_sparks.interpolate = true
	_storage_sparks.local_coords = true
	_storage_sparks.position.y = STORAGE_GLOW_CLEARANCE + 0.1
	_storage_sparks.process_material = process
	_storage_sparks.draw_pass_1 = quad
	_storage_sparks.layers = GAMEPLAY_LAYER
	_storage_sparks.visibility_range_end = STORAGE_WORLD_RANGE
	_storage_sparks.visibility_aabb = AABB(Vector3(-1.7, -0.3, -1.7), Vector3(3.4, 1.8, 3.4))
	_storage_sparks.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_storage_sparks)

## Returns the height of the model that was placed, or 0.0 for none.
func _add_model(entry: Dictionary) -> float:
	if entry.is_empty():
		return 0.0
	if bool(entry.get("retired", false)):
		# Keep the service's existing interaction ring visible when its former
		# prop was retired. A nonempty model id would hide that ring as well.
		return 0.0
	var model: Node3D = GlbSceneCache.instantiate(
		_external_path(str(entry.get("scene", ""))))
	if model == null:
		push_warning("map object %d: model %s failed to load" % [
			object_id, entry.get("scene", "")])
		return 0.0
	model.name = "Model"
	add_child(model)
	if entry.has("resourcePalette"):
		preload("res://src/world/mineral_appearance.gd").apply(model,entry.resourcePalette)
	model_id = str(entry.get("id", ""))
	# The same node id stands on every map that declares it, so an unvaried
	# model reads as a stamped copy wherever two are in view of each other.
	# The object id is the server's own stable name for this one, which is what
	# makes the variation the same on every client without being sent.
	var rng := RandomNumberGenerator.new()
	rng.seed = object_id
	var random_yaw := rng.randf() * TAU
	var random_scale := rng.randf_range(0.92, 1.08)
	# A package's yaw is exact: a crop-row segment follows its row. A stated
	# footprint is the patch's size, so its model stands at scale 1, where
	# butted row segments meet end to end.
	_model_yaw = deg_to_rad(float(presentation.yaw)) if _stated_number("yaw") else random_yaw
	model.rotation.y = _model_yaw
	model.scale = Vector3.ONE * (1.0 if not _footprint().is_empty() else random_scale)
	# A wall node's model stands in the rock face, `inset` metres back from the
	# tile's centre against its facing (the yaw's +Z points out of the rock).
	if is_wall_placed() and _stated_number("inset"):
		_model_offset = -Vector3(sin(_model_yaw), 0.0, cos(_model_yaw)) * float(presentation.inset)
		model.position = _model_offset
	return float(entry.get("height", 1.0)) * model.scale.y

func _stated_number(key: String) -> bool:
	var value: Variant = presentation.get(key)
	return value is float or value is int

## The package's footprint as [length, width] metres, or [] for none.
func _footprint() -> Array:
	var value: Variant = presentation.get("footprint")
	if value is not Array or (value as Array).size() != 2:
		return []
	var sides: Array = value as Array
	for side: Variant in sides:
		if (side is not float and side is not int) or float(side) <= 0.0:
			return []
	return [float(sides[0]), float(sides[1])]

func _add_ring() -> void:
	var material := StandardMaterial3D.new()
	material.albedo_color = _marker_colour()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.albedo_color.a = 0.75
	var ring_mesh := TorusMesh.new()
	ring_mesh.inner_radius = RING_INNER_RADIUS
	ring_mesh.outer_radius = RING_OUTER_RADIUS
	ring_mesh.rings = 24
	ring_mesh.ring_segments = 8
	var ring := MeshInstance3D.new()
	ring.name = "Ring"
	ring.mesh = ring_mesh
	ring.material_override = material
	ring.visible = model_id.is_empty()
	add_child(ring)

func _add_map_marker() -> void:
	# An entrance the map package draws is found by looking, not by reading
	# the map: it gets its pick shape and nothing on either map.
	if _map_authored:
		return
	# Sized for the map cameras, not the world: 0.6 metres was a third of a
	# pixel on the full map.
	var map_marker: MeshInstance3D = MapMarkerDisc.build(
		"MapMarker", MAP_MARKER_RADIUS, _marker_colour())
	map_marker.position.y = 4.0
	add_child(map_marker)

## The click target. A pick shape cut to the ring rather than to the object was
## fine while every object was a ring; a notice board is two metres of board a
## player aims at, and an ore seam is knee high, so the shape follows the model
## the registry measured.
##
## A patch node states its footprint, and is picked over the patch rather than
## a 0.9 m cylinder at its centre: a box of that length and width, turned with
## the model, so a 3 m row segment is clickable end to end and the row beside
## it is not.
func _add_pick_shape(height: float) -> void:
	var standing: float = maxf(height, 1.2)
	var collision := CollisionShape3D.new()
	collision.name = "PickShape"
	var footprint := _footprint()
	if footprint.is_empty():
		var shape := CylinderShape3D.new()
		shape.radius = 0.9
		shape.height = standing
		collision.shape = shape
	else:
		var box := BoxShape3D.new()
		box.size = Vector3(maxf(float(footprint[0]), FOOTPRINT_PICK_MINIMUM), standing,
			maxf(float(footprint[1]), FOOTPRINT_PICK_MINIMUM))
		collision.shape = box
		collision.rotation.y = deg_to_rad(float(presentation.yaw)) if _stated_number("yaw") \
			else _model_yaw
	collision.position = Vector3(_model_offset.x, standing * 0.5, _model_offset.z)
	add_child(collision)

static func _external_path(path: String) -> String:
	return ProjectSettings.globalize_path(path) if path.begins_with("res://") else path
