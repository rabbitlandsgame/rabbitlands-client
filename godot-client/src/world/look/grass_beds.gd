class_name LookGrassBeds
extends Node3D
## Look pass layer L4: grass beds in the wind. Grows procedural tufts over
## the grassy ground around the camera's focus - along every road's verge and
## in slow beds across open grass, with bare ground between them - and never
## on a road, paving, a yard, water, under a wall or up a cliff. Grows nothing
## unless LookProfile.enabled() and the graphics quality has grass (`tend`).
##
## Where grass may grow is read off the ground itself, not guessed from names
## alone. Every candidate spot casts one ray down the walk collision (the
## loader gives every walk surface a trimesh on layer 8, a visible
## neighbour's on the preview layer 16, and walls, buildings and props their
## own on layer 1), and the surface it lands on says what the ground is there:
##
## - a road deck (Walk_*): road where its coverage (the vertex alpha the
##   exporter wrote, which the ground layer cuts at 0.5) is high, verge where
##   it has run out; a bridge's timber or cobble is road;
## - the continent's terrain: road where the exporter painted its worn colour
##   into the terrain's vertex colour; else whatever the authored patches
##   drawn over it say (pale paving, its seams and worn cobble: none, a yard
##   or leaf litter: LookProfile.GRASS_ON_PATCH, their rim: verge - and a
##   road deck's rim over paving is paving), unless water lies over it; else
##   grass as grassy as the biome blend's layers there (grass and meadow
##   fully, moss and heather partly, gravel barely, scree, snow and sand not
##   at all);
## - a map outside the continent colours its ground by vertex colour: a pale
##   trail is road, its blend into the grass is verge, green is grass;
## - authored collision (layer 1) above the ground: nothing.
## The ray's face index finds the triangle it hit, whose vertex colours are
## read back once per mesh and interpolated at the hit.
##
## A tuft is coloured from its region's palette and then takes the ground
## paint's own mottle at its foot (the value, warmth and fine mottle that
## painted_ground_paint.gdshaderinc lays over the verge, worked out here from
## the same noise), so a bed darkens and lightens with the ground it grows
## from instead of standing out of it as a flat colour.
##
## Placement is deterministic: a candidate's spot, and every tuft it carries,
## comes from a hash of its cell in the ground's own frame (the continent
## frame on the continent), so the same ground always grows the same grass
## and nothing shimmers as the bed is rebuilt. The work is split into tiles
## (LookProfile.GRASS_TILE_METRES) placed nearest-first within a time budget
## per frame, kept while they stay in reach and redone when the ground under
## them changes (a chunk or neighbour streams in or out). The tufts are held
## in the frame, so a seam crossing's rebase only moves this node.
##
## Three tuft meshes (verge, bed and tall scatter) are each one MultiMesh, so
## the whole bed costs three draw calls, casts no shadow, and draws on the
## main camera's gameplay layer only (the map cameras never see it).

const SHADER := preload("res://src/world/look/grass_beds.gdshader")
const NODE_NAME := "LookGrassBeds"

## WorldLoader.WORLD_COLLISION_LAYER, NAVIGATION_SURFACE_LAYER and
## ExteriorRegionStream.PREVIEW_SURFACE_LAYER.
const WORLD_LAYER := 1
const WALK_LAYER := 8
const PREVIEW_LAYER := 16
## How far above and below the focus a candidate's ray looks for ground.
const RAY_METRES := 90.0
## A tuft in a MultiMesh buffer: a 3x4 transform, row by row, its colour
## (its tint) and its custom data (palette, -, -, wind phase).
const FLOATS_PER_TUFT := 20
const VARIANTS := 3
## How often the ground's make-up (resident chunks and neighbours) is checked.
const SIGNATURE_MSEC := 250
## While tiles are still being placed, the MultiMeshes are refilled no more
## often than this.
const ASSEMBLE_MSEC := 120
## How far past the bed's reach the ground's patches, water and biome cells
## are collected, so a short walk does not need them collected again.
const COLLECT_MARGIN_METRES := 24.0
## Let newly available coverage grow into view instead of revealing a tile
## each time a build batch finishes. Contractions must hide missing ground now.
const FADE_GROW_METRES_PER_SECOND := 24.0

enum Ground { NONE = 0, PATH = 1, VERGE = 2, GRASS = 3 }
const GROUND_NAMES := ["none", "path", "verge", "grass"]
## What a walk surface is to the grass: the continent's terrain, a road deck
## with coverage, a bridge or solid deck (road throughout), an invisible walk
## threshold (the ground beneath shows), or a vertex-coloured island.
enum Surface { NONE = 0, TERRAIN = 1, DECK = 2, BRIDGE = 3, THRESHOLD = 4, VERTEX = 5 }
## How many invisible thresholds a candidate's ray looks through for the ground beneath.
const THRESHOLD_DEPTH := 2

static var _tuft_meshes: Array[ArrayMesh] = []

var _active: Node3D
var _continent := false
var _region := ""
var _frame_node: Node3D
var _frame_retry_msec := 0
var _signature := ""
var _signature_msec := 0
## Every root the grass grows on (the active map and each resident chunk or
## neighbour), by instance id, with the region whose file it reads.
var _roots: Dictionary = {}
## The palette slot each region's grass was given (see `_slot`), and the
## palettes the slots hold, as the shader's arrays take them.
var _slots: Dictionary = {}
var _slots_taken := 1
var _slot_roots := PackedVector3Array()
var _slot_tips := PackedVector3Array()
var _surfaces: Dictionary = {}
var _meshes: Dictionary = {}
var _images: Dictionary = {}
var _patches: Array[Dictionary] = []
var _waters: Array[Dictionary] = []
var _biomes: Array[Dictionary] = []
var _collected_at := Vector3.INF
var _tiles: Dictionary = {}
var _queue: Array[Vector2i] = []
var _focus := Vector3.INF
var _refocus := true
var _dirty := false
var _assembled_msec := 0
## The circle completely covered by the last uploaded tiles, before the
## configured distance fade. Budget cuts and tiles still loading bound it.
var _coverage_focus := Vector3.ZERO
var _coverage_radius := 0.0
var _fade_radius := 0.0
var _fade_msec := 0
var _query := PhysicsRayQueryParameters3D.new()
var _below := PhysicsRayQueryParameters3D.new()
var _space: PhysicsDirectSpaceState3D
var _material: ShaderMaterial
var _multimeshes: Array[MultiMesh] = []
var _census: Dictionary = {}
var _built_once := false
## The region of the ground the last `_classify` looked at, for the border
## blend of the grass it grows (LookBorders).
var _classified_region := ""

## Grows, extends and trims the grass beds around `focus` (global) on the map
## `active` was loaded from. Called every frame by main while the game view
## is up; `residents` is ExteriorRegionStream.residents, the neighbours
## streamed beside the map. Grows nothing unless LookProfile.enabled() and
## the graphics quality has grass, and takes away a bed already grown the
## frame either stops being true, so the settings window's switch and quality
## reach the grass with nothing else to call.
static func tend(parent: Node3D, active: Node3D, manifest: WorldManifest,
		residents: Dictionary, focus: Vector3) -> void:
	if parent == null:
		return
	var beds := parent.get_node_or_null(NODE_NAME) as LookGrassBeds
	if not LookProfile.enabled() or not bool(LookProfile.quality_value("grass")) \
			or OS.get_environment(LookProfile.GRASS_DEBUG_VARIABLE) == "none":
		if beds != null:
			clear(parent)
		return
	if beds == null:
		beds = LookGrassBeds.new()
		beds.name = NODE_NAME
		parent.add_child(beds)
	beds.update(active, manifest, residents, focus)

## Takes every grass bed out of `parent` at once and frees it: out of the tree
## this frame, so the next `tend` can never find a bed on its way out and grow
## a second one beside it. Returns how many went.
static func clear(parent: Node) -> int:
	if parent == null:
		return 0
	var removed := 0
	var beds := parent.get_node_or_null(NODE_NAME)
	while beds != null:
		parent.remove_child(beds)
		beds.queue_free()
		removed += 1
		beds = parent.get_node_or_null(NODE_NAME)
	return removed

## The tuft mesh for `variant` (0 verge, 1 bed, 2 tall scatter): its
## LookProfile.GRASS_TUFTS blades, each a tapered strip of two segments that
## arcs outward from the tuft's foot. Vertex colour is the blade's shade,
## darker at the root; its alpha and UV.y are the height up the blade (0 at
## the root, 1 at the tip), UV.x the blade's own wind phase. Built once.
static func tuft_mesh(variant: int) -> ArrayMesh:
	if _tuft_meshes.is_empty():
		for index: int in LookProfile.GRASS_TUFTS.size():
			_tuft_meshes.append(_build_tuft(LookProfile.GRASS_TUFTS[index], index))
	return _tuft_meshes[clampi(variant, 0, _tuft_meshes.size() - 1)]

static func _build_tuft(spec: Dictionary, variant: int) -> ArrayMesh:
	var random := RandomNumberGenerator.new()
	random.seed = 7919 + variant * 104729
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var colours := PackedColorArray()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	var blades := int(spec.blades)
	var lengths: Vector2 = spec.length
	var splays: Vector2 = spec.splay
	for blade: int in blades:
		var angle := TAU * (float(blade) + random.randf_range(-0.35, 0.35)) / float(blades)
		var out := Vector3(cos(angle), 0.0, sin(angle))
		var side := Vector3(-out.z, 0.0, out.x)
		var length := random.randf_range(lengths.x, lengths.y)
		var splay := deg_to_rad(random.randf_range(splays.x, splays.y))
		var width := float(spec.width) * random.randf_range(0.8, 1.2)
		var foot := out * random.randf_range(0.0, float(spec.spread))
		# The lower segment leans a little, the upper one more: an arc.
		var middle := foot + (out * sin(splay * 0.6) + Vector3.UP * cos(splay * 0.6)) * length * 0.55
		var tip := middle + (out * sin(splay * 1.5) + Vector3.UP * cos(splay * 1.5)) * length * 0.45
		var shade := random.randf_range(0.82, 1.0)
		var phase := random.randf()
		var base := vertices.size()
		var points := [foot - side * width * 0.5, foot + side * width * 0.5,
			middle - side * width * 0.32, middle + side * width * 0.32, tip]
		var heights := [0.0, 0.0, 0.55, 0.55, 1.0]
		for point: int in 5:
			var height: float = heights[point]
			var value := shade * lerpf(LookProfile.GRASS_ROOT_SHADE, 1.0, height)
			vertices.append(points[point])
			normals.append(Vector3.UP)
			colours.append(Color(value, value, value, height))
			uvs.append(Vector2(phase, height))
		indices.append_array([base, base + 1, base + 2, base + 2, base + 1, base + 3,
			base + 2, base + 3, base + 4])
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_COLOR] = colours
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.resource_name = "look_grass_tuft_%d" % variant
	return mesh

func _init() -> void:
	_query.collision_mask = WORLD_LAYER | WALK_LAYER | PREVIEW_LAYER
	_query.hit_back_faces = false
	_below.collision_mask = WALK_LAYER | PREVIEW_LAYER
	_below.hit_back_faces = false
	_material = ShaderMaterial.new()
	_material.resource_name = "look_grass_beds"
	_material.shader = SHADER
	# Slot 0 is the default palette; the others are handed out by `_slot`.
	_slot_roots.resize(LookProfile.GRASS_PALETTE_SLOTS)
	_slot_tips.resize(LookProfile.GRASS_PALETTE_SLOTS)
	_fill_slot(0, LookProfile.GRASS_PALETTE_DEFAULT)
	_material.set_shader_parameter(&"look_gradient_power", LookProfile.GRASS_GRADIENT_POWER)
	_material.set_shader_parameter(&"look_contrast", LookProfile.GRASS_CONTRAST)
	var forward := LookProfile.forward_plus()
	_material.set_shader_parameter(&"look_value", LookProfile.GRASS_VALUE_FORWARD
		if forward else LookProfile.GRASS_VALUE_COMPAT)
	_material.set_shader_parameter(&"look_chroma", LookProfile.GRASS_CHROMA_FORWARD
		if forward else LookProfile.GRASS_CHROMA_COMPAT)
	_material.set_shader_parameter(&"look_specular", LookProfile.GRASS_SPECULAR)
	_material.set_shader_parameter(&"look_wind_direction",
		LookProfile.GRASS_WIND_DIRECTION.normalized())
	_material.set_shader_parameter(&"look_wind_metres", LookProfile.GRASS_WIND_METRES)
	_material.set_shader_parameter(&"look_wind_speed", LookProfile.GRASS_WIND_SPEED)
	_material.set_shader_parameter(&"look_gust_speed", LookProfile.GRASS_GUST_SPEED)
	_material.set_shader_parameter(&"look_fade_metres", Vector2(0.0, 0.001))
	_material.set_shader_parameter(&"look_soften_metres", LookProfile.GRASS_SOFTEN_METRES)
	_material.set_shader_parameter(&"look_soften", LookProfile.GRASS_SOFTEN)
	_material.set_shader_parameter(&"look_soften_shrink", LookProfile.GRASS_SOFTEN_SHRINK)
	for variant: int in VARIANTS:
		var multimesh := MultiMesh.new()
		multimesh.transform_format = MultiMesh.TRANSFORM_3D
		# Instance colours even though custom data could carry every tint:
		# the compatibility renderer multiplies vertex colour by an instance
		# colour whether there is one or not (see grass_beds.gdshader).
		multimesh.use_colors = true
		multimesh.use_custom_data = true
		multimesh.mesh = tuft_mesh(variant)
		_multimeshes.append(multimesh)
		var drawn := MultiMeshInstance3D.new()
		drawn.name = "Tufts_%d" % variant
		drawn.multimesh = multimesh
		drawn.material_override = _material
		drawn.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		drawn.layers = LookProfile.GRASS_RENDER_LAYER
		add_child(drawn)

## One frame of tending: follows the frame, notices changed ground, extends
## the bed around the focus within the frame's budget and refills the
## MultiMeshes when the bed changed.
func update(active: Node3D, manifest: WorldManifest, residents: Dictionary,
		focus: Vector3) -> void:
	if not is_instance_valid(active) or manifest == null or not _outdoor(manifest):
		_forget()
		return
	if active != _active:
		_forget()
		_active = active
		_continent = manifest.data.has("continentGeography")
		_region = LookGround.region_of(manifest)
	var now := Time.get_ticks_msec()
	if not is_instance_valid(_frame_node) or not _frame_node.is_inside_tree():
		if now < _frame_retry_msec:
			return
		_frame_retry_msec = now + SIGNATURE_MSEC
		_frame_node = _find_frame(active)
		if _frame_node == null:
			visible = false
			return
	visible = true
	var frame := _frame_node.global_transform
	if not frame.is_equal_approx(global_transform):
		global_transform = frame
	if now >= _signature_msec:
		_signature_msec = now + SIGNATURE_MSEC
		var signature := _signature_of(active, residents)
		if signature != _signature:
			_signature = signature
			_changed_ground(residents)
	var local_focus := frame.affine_inverse() * focus
	if _collected_at.distance_to(local_focus) > COLLECT_MARGIN_METRES * 0.5:
		_collect(local_focus)
	if _refocus or Vector2(local_focus.x - _focus.x, local_focus.z - _focus.z).length() \
			> LookProfile.GRASS_REFOCUS_METRES:
		_plan(local_focus)
	_material.set_shader_parameter(&"look_focus", focus)
	_place(now)
	if _dirty and (_queue.is_empty() or now >= _assembled_msec + ASSEMBLE_MSEC):
		_assemble(now)
	_update_fade(now, local_focus)

## Places every queued tile now, whatever the budget: for tests and probes.
func settle() -> void:
	while not _queue.is_empty():
		_place_tile(_queue.pop_back())
	if _dirty:
		_assemble(Time.get_ticks_msec())
	_fade_radius = _coverage_radius
	_update_fade(Time.get_ticks_msec(), _focus)

## How many tufts are drawn, per variant.
func tuft_counts() -> PackedInt32Array:
	var counts := PackedInt32Array()
	for multimesh: MultiMesh in _multimeshes:
		counts.append(multimesh.instance_count)
	return counts

## Every placed tuft's position in the ground's frame (for tests), nearest
## tiles first, as the MultiMeshes hold them.
func tuft_positions() -> PackedVector3Array:
	var positions := PackedVector3Array()
	for key: Vector2i in _drawn_tiles():
		var tile: Dictionary = _tiles[key]
		for variant: int in VARIANTS:
			var data: PackedFloat32Array = tile.data[variant]
			for start: int in range(0, data.size(), FLOATS_PER_TUFT):
				positions.append(Vector3(data[start + 3], data[start + 7], data[start + 11]))
	return positions

## What the last finished build found, by ground class, and what it cost.
func census() -> Dictionary:
	return _census.duplicate()

func _forget() -> void:
	_active = null
	_frame_node = null
	_frame_retry_msec = 0
	_signature = ""
	_signature_msec = 0
	_roots.clear()
	_surfaces.clear()
	_meshes.clear()
	_patches.clear()
	_waters.clear()
	_biomes.clear()
	_collected_at = Vector3.INF
	_tiles.clear()
	_queue.clear()
	_focus = Vector3.INF
	_refocus = true
	_built_once = false
	_coverage_radius = 0.0
	_fade_radius = 0.0
	_fade_msec = 0
	for multimesh: MultiMesh in _multimeshes:
		multimesh.instance_count = 0
	visible = false

## The ground mesh whose own space the bed is kept in: on the continent every
## terrain mesh's space is the continent frame, elsewhere the island's mesh.
func _find_frame(active: Node3D) -> Node3D:
	for pattern: String in ["Terrain_*", "Walk_Terrain*"]:
		for node: Node in active.find_children(pattern, "MeshInstance3D", true, false):
			if (node as MeshInstance3D).is_visible_in_tree():
				return node as Node3D
	return null

## Changes when a chunk or neighbour streams in or out, a neighbour's
## collision is switched, or a neighbour is moved.
func _signature_of(active: Node3D, residents: Dictionary) -> String:
	var parts := PackedStringArray([str(active.get_instance_id()), str(_revision(active))])
	for map_id: Variant in residents:
		var resident: Variant = residents[map_id]
		var root: Node3D = (resident as Dictionary).get("root") as Node3D \
			if resident is Dictionary else null
		if is_instance_valid(root):
			parts.append("%s:%d:%s:%s:%d:%s" % [map_id, root.get_instance_id(),
				root.visible, root.get_meta("stream_physics", ""), _revision(root),
				root.position.snapped(Vector3.ONE * 0.5)])
	return ",".join(parts)

static func _revision(root: Node3D) -> int:
	return (root as ContinentChunkStream).revision if root is ContinentChunkStream else 0

## The ground changed: which root is which region is looked at again, the
## patches, water and biome cells are collected again, and every tile is
## redone (it keeps drawing until it is).
func _changed_ground(residents: Dictionary) -> void:
	_roots.clear()
	_roots[_active.get_instance_id()] = _region
	for map_id: Variant in residents:
		var resident: Variant = residents[map_id]
		var root: Node3D = (resident as Dictionary).get("root") as Node3D \
			if resident is Dictionary else null
		if is_instance_valid(root):
			_roots[root.get_instance_id()] = String(map_id).get_slice("__chunk_", 0)
	_surfaces.clear()
	_collected_at = Vector3.INF
	for tile: Dictionary in _tiles.values():
		tile["stale"] = true
	_refocus = true

## The palette slot `region`'s grass is drawn with: 0, the default palette,
## unless its region file has a grass palette, which takes the next free slot
## the first time the region is met and keeps it for as long as this node
## lives, so a slot never changes under tufts already placed. Past
## LookProfile.GRASS_PALETTE_SLOTS the rest grow the default grass, with a
## warning.
func _slot(region: String) -> int:
	if _slots.has(region):
		return int(_slots[region])
	var slot := 0
	var palette := LookProfile.grass_palette(region)
	if not palette.is_empty():
		if _slots_taken < LookProfile.GRASS_PALETTE_SLOTS:
			slot = _slots_taken
			_slots_taken += 1
			_fill_slot(slot, palette)
		else:
			push_warning("look grass: every palette slot is taken; %s grows the default grass"
				% region)
	_slots[region] = slot
	return slot

func _fill_slot(slot: int, palette: Dictionary) -> void:
	var root_colour: Color = palette.root
	var tip_colour: Color = palette.tip
	_slot_roots[slot] = Vector3(root_colour.r, root_colour.g, root_colour.b)
	_slot_tips[slot] = Vector3(tip_colour.r, tip_colour.g, tip_colour.b)
	_material.set_shader_parameter(&"look_roots", _slot_roots)
	_material.set_shader_parameter(&"look_tips", _slot_tips)

## Collects, around `local_focus`, the ground a ray cannot see: the authored
## patches drawn over the terrain, the water, and the biome blend's cells.
func _collect(local_focus: Vector3) -> void:
	_collected_at = local_focus
	_patches.clear()
	_waters.clear()
	_biomes.clear()
	var centre := global_transform * local_focus
	var reach := LookProfile.GRASS_RADIUS + COLLECT_MARGIN_METRES
	var area := Rect2(centre.x - reach, centre.z - reach, reach * 2.0, reach * 2.0)
	for root_id: int in _roots:
		var root := instance_from_id(root_id) as Node3D
		if not is_instance_valid(root) or not root.is_visible_in_tree():
			continue
		var region := String(_roots[root_id])
		for node: Node in root.find_children("*", "MeshInstance3D", true, false):
			var mesh_instance := node as MeshInstance3D
			if mesh_instance.mesh == null or not mesh_instance.is_visible_in_tree():
				continue
			var node_name := _plain_name(String(mesh_instance.name))
			var water := node_name.begins_with("Water_") or node_name.begins_with("Scenery_Water")
			var ground := node_name.begins_with("AuthoredGround_")
			if not water and not ground:
				# By a word of its material's name, as the ground layer judges
				# it (LookGround.water_named): "crownwater" is not water.
				var material := mesh_instance.get_active_material(0)
				water = material != null and LookGround.water_named(material.resource_name)
				if not water:
					continue
			var xform := mesh_instance.global_transform
			var box := xform * mesh_instance.get_aabb()
			var rect := Rect2(box.position.x, box.position.z, box.size.x, box.size.z)
			if not rect.intersects(area):
				continue
			if water:
				_waters.append({"node": mesh_instance, "inverse": xform.affine_inverse(),
					"rect": rect, "surface": mesh_instance.mesh.generate_triangle_mesh()})
			elif node_name.contains("Base_"):
				var biome := _biome(mesh_instance, region)
				if not biome.is_empty():
					_biomes.append(biome)
			else:
				var patch := _patch(mesh_instance, xform, rect)
				if not patch.is_empty():
					_patches.append(patch)

## An authored patch as the grass sees it: its footprint, a triangle mesh to
## find where a spot falls on it, its coverage, and whether it is paving.
func _patch(node: MeshInstance3D, xform: Transform3D, rect: Rect2) -> Dictionary:
	var facts := _material_facts(node)
	if facts.is_empty() or not bool(facts.blended):
		return {}
	var tint: Color = facts.tint
	# Paving, cobble and sand by the ground layer's own tests (LookGround), so
	# the grass and the paint agree on what a patch is.
	var stone := LookGround.stone_tint(tint)
	var sand := LookGround.sand_tint(tint)
	var paving := tint.v >= LookProfile.PAVING_TINT_VALUE \
		and tint.s <= LookProfile.PAVING_TINT_SATURATION and stone and not sand
	var bare := sand or (tint.v >= LookProfile.GRASS_BARE_PATCH.x \
		and tint.s <= LookProfile.GRASS_BARE_PATCH.y and stone)
	var grass := not paving and not bare and LookProfile.green_tint(tint)
	return {"inverse": xform.affine_inverse(), "rect": rect, "paving": paving, "bare": bare,
		"grass": grass, "surface": node.mesh.generate_triangle_mesh(),
		"mesh": _mesh_data(node.mesh)}

## A biome blend cell: its masks, where they lie in the continent, and how
## grassy each of its layers is (by `region`'s words first).
func _biome(node: MeshInstance3D, region: String) -> Dictionary:
	var material := node.get_active_material(0) as ShaderMaterial
	if material == null:
		return {}
	var base := material.get_shader_parameter(&"base_mask") as Texture2D
	var secondary := material.get_shader_parameter(&"secondary_mask") as Texture2D
	var base_image := _image(base)
	if base_image == null:
		return {}
	var to_continent := Transform3D.IDENTITY
	var matrix: Variant = material.get_shader_parameter(&"terrain_to_continent")
	if matrix is Projection:
		to_continent = Transform3D(matrix as Projection)
	elif matrix is Transform3D:
		to_continent = matrix as Transform3D
	var grass_base := PackedFloat32Array()
	var grass_secondary := PackedFloat32Array()
	for layer: int in 4:
		grass_base.append(grassiness(material.get_shader_parameter("base_albedo_%d" % layer),
			region))
		grass_secondary.append(grassiness(
			material.get_shader_parameter("secondary_albedo_%d" % layer), region))
	var origin: Variant = material.get_shader_parameter(&"mask_origin")
	var metres: Variant = material.get_shader_parameter(&"mask_metres_per_pixel")
	return {"to_local": to_continent * node.global_transform.affine_inverse(),
		"origin": origin if origin is Vector2 else Vector2.ZERO,
		"metres": float(metres) if metres != null else 1.5,
		"base": base_image, "secondary": _image(secondary),
		"grass_base": grass_base, "grass_secondary": grass_secondary}

## How grassy a biome layer is, by the words in its texture's file name:
## `region`'s own (its region file's `grass.layers`), then every map's
## (LookProfile.GRASS_LAYER_WORDS).
static func grassiness(texture: Variant, region := "") -> float:
	if texture is not Texture2D:
		return LookProfile.GRASS_LAYER_DEFAULT
	return LookProfile.grass_layer_value(region,
		(texture as Texture2D).resource_path.get_file().to_lower())

func _image(texture: Texture2D) -> Image:
	if texture == null:
		return null
	var key := texture.get_instance_id()
	if _images.has(key):
		return _images[key]
	var image := texture.get_image()
	if image != null:
		image = image.duplicate() as Image
		if image.is_compressed():
			image.decompress()
	_images[key] = image
	return image

## Which tiles the bed wants around `local_focus`: those within reach are
## queued nearest-last (the queue is popped from its back), those left well
## behind are dropped.
func _plan(local_focus: Vector3) -> void:
	_focus = local_focus
	_refocus = false
	# Moving can change which tiles fit the instance budget even when every
	# tile is already resident, so the uploaded selection must follow too.
	_dirty = true
	var reach := LookProfile.GRASS_RADIUS
	var size := LookProfile.GRASS_TILE_METRES
	for key: Vector2i in _tiles.keys():
		if _tile_distance(key, local_focus) > reach + size:
			_tiles.erase(key)
			_dirty = true
	_queue.clear()
	var low := Vector2i(floori((local_focus.x - reach) / size), floori((local_focus.z - reach) / size))
	var high := Vector2i(floori((local_focus.x + reach) / size), floori((local_focus.z + reach) / size))
	for x: int in range(low.x, high.x + 1):
		for z: int in range(low.y, high.y + 1):
			var key := Vector2i(x, z)
			if _tile_distance(key, local_focus) > reach:
				continue
			if not _tiles.has(key) or bool(_tiles[key].stale):
				_queue.append(key)
	_queue.sort_custom(func(a: Vector2i, b: Vector2i) -> bool:
		return _tile_distance(a, local_focus) > _tile_distance(b, local_focus))

static func _tile_distance(key: Vector2i, local_focus: Vector3) -> float:
	var size := LookProfile.GRASS_TILE_METRES
	var nearest := Vector2(clampf(local_focus.x, key.x * size, (key.x + 1) * size),
		clampf(local_focus.z, key.y * size, (key.y + 1) * size))
	return nearest.distance_to(Vector2(local_focus.x, local_focus.z))

## Places queued tiles until this frame's budget runs out: the larger budget
## while ground the camera frames is still bare or out of date.
func _place(now: int) -> void:
	if _queue.is_empty():
		return
	var bare := _tile_distance(_queue.back(), _focus) <= LookProfile.GRASS_BARE_METRES
	var budget := LookProfile.GRASS_BUILD_USEC_BARE if bare else LookProfile.GRASS_BUILD_USEC
	var began := Time.get_ticks_usec()
	while not _queue.is_empty() and Time.get_ticks_usec() - began < budget:
		_place_tile(_queue.pop_back())
	_census["usec"] = int(_census.get("usec", 0)) + Time.get_ticks_usec() - began
	if _queue.is_empty():
		_finish_census(now)

func _finish_census(_now: int) -> void:
	var tufts := 0
	for tile: Dictionary in _tiles.values():
		tufts += int(tile.count)
	_census["tiles"] = _tiles.size()
	_census["tufts"] = tufts
	var debug := OS.get_environment(LookProfile.GRASS_DEBUG_VARIABLE) == "1"
	if debug or not _built_once:
		print("look_grass stage=built region=%s %s" % [_region, JSON.stringify(_census)])
	_built_once = true
	_census = {}

## Casts a tile's candidates and keeps the tufts they carry, per variant.
func _place_tile(key: Vector2i) -> void:
	var space := get_world_3d().direct_space_state if is_inside_tree() else null
	var data: Array[PackedFloat32Array] = []
	for variant: int in VARIANTS:
		data.append(PackedFloat32Array())
	var tile := {"data": data, "count": 0, "stale": false}
	_tiles[key] = tile
	_dirty = true
	if space == null:
		return
	_space = space
	var cells := LookProfile.GRASS_TILE_CELLS
	var step := LookProfile.GRASS_TILE_METRES / float(cells)
	var frame := global_transform
	var inverse := frame.affine_inverse()
	var up := frame.basis.y.normalized()
	var corner_a := frame * Vector3(key.x * LookProfile.GRASS_TILE_METRES, _focus.y,
		key.y * LookProfile.GRASS_TILE_METRES)
	var corner_b := frame * Vector3((key.x + 1) * LookProfile.GRASS_TILE_METRES, _focus.y,
		(key.y + 1) * LookProfile.GRASS_TILE_METRES)
	var tile_rect := Rect2(Vector2(minf(corner_a.x, corner_b.x), minf(corner_a.z, corner_b.z)),
		(Vector2(corner_b.x, corner_b.z) - Vector2(corner_a.x, corner_a.z)).abs())
	var patches: Array[Dictionary] = []
	for patch: Dictionary in _patches:
		if (patch.rect as Rect2).intersects(tile_rect):
			patches.append(patch)
	var waters: Array[Dictionary] = []
	for water: Dictionary in _waters:
		if (water.rect as Rect2).intersects(tile_rect):
			waters.append(water)
	var count := 0
	# The region borders near this tile, per region, for the palette blend.
	var area := Rect2(key.x * LookProfile.GRASS_TILE_METRES, key.y * LookProfile.GRASS_TILE_METRES,
		LookProfile.GRASS_TILE_METRES, LookProfile.GRASS_TILE_METRES)
	var borders := {}
	for i: int in cells:
		for j: int in cells:
			var cell := Vector2i(key.x * cells + i, key.y * cells + j)
			var cell_hash := hash(cell)
			var spot := Vector3((cell.x + _unit(cell_hash, 0)) * step, _focus.y,
				(cell.y + _unit(cell_hash, 1)) * step)
			var point := frame * spot
			_query.from = point + up * RAY_METRES
			_query.to = point - up * RAY_METRES
			var hit := space.intersect_ray(_query)
			_count("rays")
			if hit.is_empty():
				_count("misses")
				continue
			var ground := _classify(hit, up, patches, waters, cell_hash)
			var kind := int(ground.x)
			_count(GROUND_NAMES[kind])
			if kind == Ground.NONE or kind == Ground.PATH:
				continue
			var local_hit := inverse * (hit.position as Vector3)
			var local_normal := (inverse.basis * (hit.normal as Vector3)).normalized()
			count += _grow(data, local_hit, local_normal, kind, ground.y, int(ground.z),
				cell, cell_hash, step, _border_blend(_classified_region, area, borders, local_hit))
	tile["count"] = count

## What the ground is where `hit` landed: (Ground, grassiness 0..1, palette).
func _classify(hit: Dictionary, up: Vector3, patches: Array[Dictionary],
		waters: Array[Dictionary], cell_hash: int, depth := 0) -> Vector3:
	var collider := hit.collider as CollisionObject3D
	if collider == null:
		return Vector3(Ground.NONE, 0.0, 0.0)
	if (collider.collision_layer & (WALK_LAYER | PREVIEW_LAYER)) == 0:
		# Authored collision above the ground: a wall, a roof, a prop.
		return Vector3(Ground.NONE, 0.0, 0.0)
	var body := _surface_of(collider)
	var kind := int(body.get("kind", Surface.NONE))
	if kind == Surface.NONE or kind == Surface.BRIDGE:
		return Vector3(Ground.PATH if kind == Surface.BRIDGE else Ground.NONE, 0.0, 0.0)
	if kind == Surface.THRESHOLD:
		# An invisible walk threshold: the ground beneath shows, so the ground
		# beneath decides (nothing beneath, or water, grows nothing). Judged at
		# the threshold itself, the grass took it for open ground and grew a bed
		# on sw_isle's pier, whose bridge deck is drawn by a kit span over the
		# sea (its framework slab is alpha 0).
		if depth >= THRESHOLD_DEPTH:
			return Vector3(Ground.NONE, 0.0, 0.0)
		var beneath := _beneath(hit, collider, up)
		if beneath.is_empty():
			return Vector3(Ground.NONE, 0.0, 0.0)
		return _classify(beneath, up, patches, waters, cell_hash, depth + 1)
	var slope := smoothstep(LookProfile.GRASS_SLOPE_UP.x, LookProfile.GRASS_SLOPE_UP.y,
		(hit.normal as Vector3).dot(up))
	if slope <= 0.0:
		return Vector3(Ground.NONE, 0.0, 0.0)
	var point: Vector3 = hit.position
	var palette := float(body.palette)
	_classified_region = String(body.get("region", ""))
	# What the authored patches drawn over the ground say here: (0 grass,
	# 1 road or paving, 2 verge along a patch's rim; the grass share left;
	# how much of a green meadow patch covers it).
	var cover := _patch_cover(point, patches) if kind != Surface.VERTEX \
		else Vector3(0.0, 1.0, 0.0)
	if int(cover.x) == 1:
		return Vector3(Ground.PATH, 0.0, palette)
	if kind == Surface.DECK:
		var alpha := _vertex_colour(body, hit).a
		if alpha >= LookProfile.GRASS_VERGE_ALPHA.y or _road_beneath(hit, collider, up):
			return Vector3(Ground.PATH, 0.0, palette)
		return Vector3(Ground.VERGE, verge_strength(alpha, cell_hash) * slope
			* _rim_grass(point, cell_hash), palette)
	if _under_water(point, waters):
		return Vector3(Ground.NONE, 0.0, 0.0)
	if kind == Surface.VERTEX:
		var colour := _vertex_colour(body, hit)
		var ground := vertex_ground(colour)
		return Vector3(ground.x, ground.y * slope, palette)
	var verge := false
	if kind == Surface.TERRAIN and bool(body.road_detect):
		var road := road_weight(_vertex_colour(body, hit), bool(body.srgb))
		if road >= LookProfile.GRASS_TERRAIN_ROAD.y:
			return Vector3(Ground.PATH, 0.0, palette)
		verge = road >= LookProfile.GRASS_TERRAIN_ROAD.x
	verge = verge or int(cover.x) == 2
	# A meadow patch is as grassy as its region's file says its meadows are
	# (`grass.meadow`, 1 unless it says otherwise).
	var meadow := cover.z * float(LookProfile.region_value(_classified_region, "grass",
		"meadow", 1.0))
	var open := _biome_grass(point, cell_hash)
	# `grass.open_green`: where no biome blend covers the terrain, open ground
	# is as grassy as its vertex colour is green (sw_isle's opaque base also
	# covers its beaches and grey cut faces, which grew tufts at grass.open).
	var green_share := float(LookProfile.region_value(_classified_region, "grass", "open_green", 0.0))
	if green_share > 0.0 and kind == Surface.TERRAIN and not _has_biome(point):
		open *= lerpf(1.0, open_green(_vertex_colour(body, hit), bool(body.srgb)), green_share)
	var grass := maxf(open * cover.y, meadow) * slope
	if verge:
		return Vector3(Ground.VERGE, maxf(grass, 0.5 * slope * _rim_grass(point, cell_hash)),
			palette)
	return Vector3(Ground.GRASS, grass, palette)

## How much of its verge bed a road's or a patch's rim keeps over the biome
## beneath it: all of it on grass, heather or moss (grassiness 0.5 and up),
## down to LookProfile.GRASS_BARE_RIM on bare scree, snow or sand. A rim grew
## its bed whatever lay under it, and 70 % of Mirrorhold's tufts were verge
## beds strung along its roads across bare grey scree (hf95 27-28 against
## develop's 14-17); Whitehorn's roads were lined with grass over the snow.
func _rim_grass(point: Vector3, cell_hash: int) -> float:
	return clampf(_biome_grass(point, cell_hash) * 2.0, LookProfile.GRASS_BARE_RIM, 1.0)

## How much of a verge bed a road deck's rim carries at coverage `alpha`: none
## at the deck's outer edge (LookProfile.GRASS_VERGE_ALPHA.x), rising over
## LookProfile.GRASS_VERGE_FEATHER with a jitter so the bed's back edge is
## broken rather than the straight line the deck's geometry ends on, and
## thinning again towards the road (LookProfile.GRASS_VERGE_ROADSIDE) so the
## tufts stand back from it.
static func verge_strength(alpha: float, cell_hash: int) -> float:
	var jitter := (_unit(cell_hash, 5) - 0.5) * LookProfile.GRASS_VERGE_FEATHER
	var outer := smoothstep(LookProfile.GRASS_VERGE_ALPHA.x,
		LookProfile.GRASS_VERGE_ALPHA.x + LookProfile.GRASS_VERGE_FEATHER, alpha + jitter)
	var roadside := smoothstep(LookProfile.GRASS_VERGE_ROADSIDE.x,
		LookProfile.GRASS_VERGE_ALPHA.y, alpha)
	return outer * (1.0 - roadside * LookProfile.GRASS_VERGE_ROADSIDE.y)

## The walk surface under `hit` (the collider it landed on left out), or {}
## when there is none within RAY_METRES.
func _beneath(hit: Dictionary, collider: CollisionObject3D, up: Vector3) -> Dictionary:
	var point: Vector3 = hit.position
	_below.from = point - up * 0.01
	_below.to = point - up * RAY_METRES
	_below.exclude = [collider.get_rid()]
	return _space.intersect_ray(_below)

## True when another road deck lies within a hand's breadth under the rim of
## the one `hit` landed on and covers the spot: where two road decks overlap
## (a fork, a junction, a road meeting a door's pad) the ray finds whichever
## is on top, and its rim is no verge when the other is road there.
func _road_beneath(hit: Dictionary, collider: CollisionObject3D, up: Vector3) -> bool:
	var point: Vector3 = hit.position
	_below.from = point + up * 0.3
	_below.to = point - up * 0.3
	_below.exclude = [collider.get_rid()]
	var beneath := _space.intersect_ray(_below)
	if beneath.is_empty():
		return false
	var other := beneath.collider as CollisionObject3D
	if other == null:
		return false
	var body := _surface_of(other)
	var kind := int(body.get("kind", Surface.NONE))
	if kind == Surface.BRIDGE:
		return true
	return kind == Surface.DECK \
		and _vertex_colour(body, beneath).a >= LookProfile.GRASS_VERGE_ALPHA.y

## What the authored patches over `point` make of it: (0, share) grass that
## keeps `share` of its tufts (a yard or leaf litter keeps GRASS_ON_PATCH),
## (1, 0) no grass - pale paving's footprint and its seams, or worn cobble or
## sand where it covers the ground (thinning out towards a broken edge, see
## LookProfile.GRASS_BARE_EDGE_*) - and (2, 1) verge along a patch's rim. The
## third value is how much a green meadow patch covers the spot, as grassy
## as it is whatever the biome beneath (LookProfile.GRASS_PATCH_GREEN).
## Paving is judged by its bounds rather than its coverage: its low weights
## are the seams between two plaza patches, where the grass beneath shows
## through as thin lines the grass must not pick out.
func _patch_cover(point: Vector3, patches: Array[Dictionary]) -> Vector3:
	var spot := Vector2(point.x, point.z)
	var share := 1.0
	var rim := false
	var green := 0.0
	for patch: Dictionary in patches:
		var rect: Rect2 = patch.rect
		if bool(patch.paving):
			if rect.grow(LookProfile.GRASS_PAVING_MARGIN).has_point(spot):
				return Vector3(1.0, 0.0, 0.0)
			continue
		if not rect.has_point(spot):
			continue
		var coverage := _patch_coverage(patch, point)
		if bool(patch.get("grass", false)):
			# A green meadow patch is grass however bare the biome beneath it
			# (Mirrorhold's meadows over scree, Manymouth's over silt), and its
			# edge melts into the ground rather than growing a verge ring.
			if coverage >= 0.0:
				green = maxf(green, smoothstep(LookProfile.MEADOW_RIM.x - LookProfile.MEADOW_RIM.y * 2.0,
					LookProfile.MEADOW_RIM.x + LookProfile.MEADOW_RIM.y * 2.0, coverage))
			continue
		if bool(patch.bare) and coverage >= 0.0:
			# Worn cobble ends along a broken line, not the exported patch's
			# straight edge: the coverage the grass stops at wanders either
			# side of the paint's cut with a slow noise, and the tufts thin
			# out over the last stretch before it rather than standing in a
			# dense row along it.
			var edge := LookProfile.PATCH_RIM.x + (value_noise(
				point.x / LookProfile.GRASS_BARE_EDGE_METRES,
				point.z / LookProfile.GRASS_BARE_EDGE_METRES, 31) - 0.5) \
				* 2.0 * LookProfile.GRASS_BARE_EDGE_JITTER
			if coverage >= edge:
				return Vector3(1.0, 0.0, 0.0)
			share = minf(share, smoothstep(edge, edge - LookProfile.GRASS_BARE_EDGE_FEATHER,
				coverage))
			continue
		if coverage >= LookProfile.PATCH_RIM.x:
			share = minf(share, LookProfile.GRASS_ON_PATCH)
		elif coverage >= LookProfile.GRASS_PATCH_RIM_FROM:
			rim = true
	return Vector3(2.0 if rim else 0.0, share, green)

## A vertex-coloured map's ground (Lantern Reach): (Ground, grassiness). Its
## colour is judged as stored, which is how the island's scene draws it.
static func vertex_ground(colour: Color) -> Vector2:
	var value := maxf(colour.r, maxf(colour.g, colour.b))
	if value >= LookProfile.GRASS_VERTEX_PATH_VALUE.y:
		return Vector2(Ground.PATH, 0.0)
	if value >= LookProfile.GRASS_VERTEX_PATH_VALUE.x:
		return Vector2(Ground.VERGE, 1.0)
	var green := colour.g - maxf(colour.r, colour.b)
	if green < LookProfile.GRASS_VERTEX_GREEN:
		return Vector2(Ground.NONE, 0.0)
	return Vector2(Ground.GRASS, smoothstep(LookProfile.GRASS_VERTEX_GREEN,
		LookProfile.GRASS_VERTEX_GREEN * 2.5, green))

## How much a terrain vertex colour is the exporter's worn road, as the
## ground layer's shader judges it (look_road_weight in
## painted_ground_paint.gdshaderinc).
static func road_weight(colour: Color, srgb: bool) -> float:
	var linear := colour.srgb_to_linear() if srgb else colour
	var road := LookProfile.TERRAIN_ROAD_COLOUR
	var reference := Vector3(road.r, road.g, road.b) / 0.92
	var distance := Vector3(linear.r, linear.g, linear.b).distance_to(reference) / reference.length()
	return 1.0 - smoothstep(LookProfile.TERRAIN_ROAD_TOLERANCE.x,
		LookProfile.TERRAIN_ROAD_TOLERANCE.y, distance)

func _under_water(point: Vector3, waters: Array[Dictionary]) -> bool:
	for water: Dictionary in waters:
		if not (water.rect as Rect2).has_point(Vector2(point.x, point.z)):
			continue
		var surface := water.surface as TriangleMesh
		if surface == null:
			continue
		var inverse: Transform3D = water.inverse
		var local := inverse * point
		var found := surface.intersect_ray(local + Vector3.UP * RAY_METRES, Vector3.DOWN)
		if found.is_empty():
			continue
		var node := water.node as Node3D
		if not is_instance_valid(node):
			continue
		var level := node.global_transform * (found.position as Vector3)
		if level.y >= point.y - 0.05:
			return true
	return false

## The coverage of `patch` at `point`, or -1 where the spot is off it.
func _patch_coverage(patch: Dictionary, point: Vector3) -> float:
	var surface := patch.surface as TriangleMesh
	if surface == null:
		return -1.0
	var inverse: Transform3D = patch.inverse
	var local := inverse * point
	var found := surface.intersect_ray(local + Vector3.UP * RAY_METRES, Vector3.DOWN)
	if found.is_empty():
		return -1.0
	return _interpolate(patch.mesh, int(found.face_index), found.position as Vector3).a

## The ground mesh a walk collision body stands for, what kind of ground it
## is, and which region's palette its grass takes.
func _surface_of(collider: CollisionObject3D) -> Dictionary:
	var id := collider.get_instance_id()
	if _surfaces.has(id):
		return _surfaces[id]
	var info := {}
	var node := collider.get_parent() as MeshInstance3D
	if node != null and node.mesh != null:
		var node_name := _plain_name(String(node.name))
		var ground := LookGround.kind_of(node_name)
		var facts := _material_facts(node)
		var kind := Surface.NONE
		if ground == LookGround.Kind.DECK and not facts.is_empty():
			# A deck draws its coverage only when it blends and carries vertex
			# colour; drawn solid, it is road (a bridge's timber, a cobble
			# deck) wherever it lies.
			if float(facts.alpha) <= 0.01:
				kind = Surface.THRESHOLD
			elif bool(facts.blended) and bool(facts.coloured):
				kind = Surface.DECK
			else:
				kind = Surface.BRIDGE
		elif ground == LookGround.Kind.TERRAIN:
			kind = Surface.TERRAIN if _continent else Surface.VERTEX
		if kind != Surface.NONE:
			info = {"kind": kind, "mesh": _mesh_data(node.mesh), "node": node,
				"palette": _palette_of(node), "region": _region_of(node),
				"srgb": bool(facts.get("srgb", false)),
				"road_detect": bool(facts.get("vertex_albedo", false))}
	_surfaces[id] = info
	return info

## The facts about a ground mesh's own material the grass needs, whether the
## ground layer has painted it or not: its tint, whether it blends (a patch or
## deck with coverage) or is opaque, whether its vertex colour is its colour.
static func _material_facts(node: MeshInstance3D) -> Dictionary:
	var material := node.get_active_material(0)
	var coloured: bool = (int(node.mesh.surface_get_format(0)) & Mesh.ARRAY_FORMAT_COLOR) != 0
	if material is ShaderMaterial and material.has_meta(LookGround.PAINTED_META):
		var painted := material as ShaderMaterial
		var tint: Variant = painted.get_shader_parameter(&"albedo_color")
		var shader := painted.shader
		return {"tint": tint if tint is Color else Color.WHITE,
			"alpha": (tint as Color).a if tint is Color else 1.0,
			"blended": shader != LookGround.SHADER_OPAQUE and shader != LookGround.SHADER_TWO_SIDED,
			"vertex_albedo": bool(painted.get_shader_parameter(&"use_vertex_albedo")),
			"srgb": bool(painted.get_shader_parameter(&"vertex_albedo_srgb")),
			"coloured": coloured}
	var standard := material as BaseMaterial3D
	if standard == null:
		return {}
	return {"tint": standard.albedo_color, "alpha": standard.albedo_color.a,
		"blended": standard.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED,
		"vertex_albedo": standard.vertex_color_use_as_albedo,
		"srgb": standard.vertex_color_is_srgb, "coloured": coloured}

## The palette slot of the region the node belongs to: its nearest ancestor
## that is the active map or a resident neighbour.
func _palette_of(node: Node) -> int:
	return _slot(_region_of(node))

## The region the node belongs to: that of its nearest ancestor that is the
## active map or a resident neighbour.
func _region_of(node: Node) -> String:
	var walker := node
	while walker != null:
		var id := walker.get_instance_id()
		if _roots.has(id):
			return String(_roots[id])
		walker = walker.get_parent()
	return _region

## Near a region border the grass fades into the neighbour's palette as the
## ground paint's trims do (LookBorders): (the neighbour's palette slot, how
## much of it), for the neighbour whose share is largest at `local_hit` (the
## grass frame is the continent frame). `borders` caches the tile's borders
## per region. (0, 0) away from every border and off the continent.
func _border_blend(region: String, area: Rect2, borders: Dictionary,
		local_hit: Vector3) -> Vector2:
	if not _continent or region.is_empty():
		return Vector2.ZERO
	if not borders.has(region):
		borders[region] = LookBorders.near(region, area, LookProfile.BORDER_FEATHER_METRES)
	var selection: Dictionary = borders[region]
	var neighbours: PackedStringArray = selection.neighbours
	if neighbours.is_empty():
		return Vector2.ZERO
	var weights := LookBorders.weights(Vector2(local_hit.x, local_hit.z), selection)
	var best := -1
	var weight := 0.001
	for slot: int in weights.size():
		if weights[slot] > weight:
			weight = weights[slot]
			best = slot
	if best < 0:
		return Vector2.ZERO
	return Vector2(_slot(neighbours[best]), weight)

## A mesh's triangles, read back once: per surface, its positions, colours
## and indices, and the index of its first triangle among the mesh's (the
## order the collision trimesh and TriangleMesh number their faces in).
func _mesh_data(mesh: Mesh) -> Array[Dictionary]:
	var key := mesh.get_instance_id()
	if _meshes.has(key):
		return _meshes[key]
	var surfaces: Array[Dictionary] = []
	var first := 0
	for surface: int in mesh.get_surface_count():
		if mesh.surface_get_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES:
			continue
		var arrays := mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var colours: PackedColorArray = arrays[Mesh.ARRAY_COLOR] \
			if arrays[Mesh.ARRAY_COLOR] != null else PackedColorArray()
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] \
			if arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
		var triangles := (indices.size() if not indices.is_empty() else vertices.size()) / 3
		surfaces.append({"first": first, "triangles": triangles, "vertices": vertices,
			"colours": colours, "indices": indices})
		first += triangles
	_meshes[key] = surfaces
	return surfaces

func _vertex_colour(body: Dictionary, hit: Dictionary) -> Color:
	var node := body.node as MeshInstance3D
	if not is_instance_valid(node):
		return Color.WHITE
	var local := node.global_transform.affine_inverse() * (hit.position as Vector3)
	var face := int(hit.get("face_index", -1))
	if face < 0 and node.mesh != null:
		# A physics engine that reports no face index (Jolt, unless its ray
		# cast face index setting is on): find the face on the mesh instead.
		var found := node.mesh.generate_triangle_mesh().intersect_ray(
			local + Vector3.UP, Vector3.DOWN)
		face = int(found.get("face_index", -1))
	return _interpolate(body.mesh, face, local)

## The vertex colour of triangle `face` at `local` (mesh space), weighted by
## where in the triangle it falls across the ground. White when the mesh has
## no colour or the face is unknown.
func _interpolate(surfaces: Array[Dictionary], face: int, local: Vector3) -> Color:
	if face < 0:
		return Color.WHITE
	for surface: Dictionary in surfaces:
		var first := int(surface.first)
		if face < first or face >= first + int(surface.triangles):
			continue
		var colours: PackedColorArray = surface.colours
		if colours.is_empty():
			return Color.WHITE
		var indices: PackedInt32Array = surface.indices
		var vertices: PackedVector3Array = surface.vertices
		var corner := (face - first) * 3
		var a := indices[corner] if not indices.is_empty() else corner
		var b := indices[corner + 1] if not indices.is_empty() else corner + 1
		var c := indices[corner + 2] if not indices.is_empty() else corner + 2
		var weights := barycentric_xz(local, vertices[a], vertices[b], vertices[c])
		if weights.x < -0.05 or weights.y < -0.05 or weights.z < -0.05:
			_count("face_mismatch")
			weights = Vector3.ONE / 3.0
		return colours[a] * weights.x + colours[b] * weights.y + colours[c] * weights.z
	return Color.WHITE

## Where `point` falls in triangle abc seen from above, as weights on a, b, c.
static func barycentric_xz(point: Vector3, a: Vector3, b: Vector3, c: Vector3) -> Vector3:
	var ab := Vector2(b.x - a.x, b.z - a.z)
	var ac := Vector2(c.x - a.x, c.z - a.z)
	var ap := Vector2(point.x - a.x, point.z - a.z)
	var area := ab.x * ac.y - ac.x * ab.y
	if absf(area) < 0.000001:
		return Vector3.ONE / 3.0
	var v := (ap.x * ac.y - ac.x * ap.y) / area
	var w := (ab.x * ap.y - ap.x * ab.y) / area
	return Vector3(1.0 - v - w, v, w)

## How grassy the biome blend is at `point` (global): its layers' weights
## there, each layer counted as grassy as its texture says. A spot outside
## every collected cell counts as grass.
## How green a terrain vertex colour is for the open ground's grass
## (`grass.open_green`): 0 for sand, grey rock and earth (green not leading
## red and blue), 1 for a lawn green, from its display colour.
static func open_green(colour: Color, srgb: bool) -> float:
	var display := colour if srgb else colour.linear_to_srgb()
	return smoothstep(LookProfile.GRASS_OPEN_GREEN.x, LookProfile.GRASS_OPEN_GREEN.y,
		display.g - maxf(display.r, display.b))

## True when a biome blend covers `point` (the ground's own layers decide its
## grass there, not `grass.open`).
func _has_biome(point: Vector3) -> bool:
	for biome: Dictionary in _biomes:
		var continent: Vector3 = (biome.to_local as Transform3D) * point
		var origin: Vector2 = biome.origin
		var metres: float = biome.metres
		var base: Image = biome.base
		var texel := Vector2i(floori((continent.x - origin.x) / metres + 0.5),
			floori((continent.z - origin.y) / metres + 0.5))
		if texel.x >= 0 and texel.y >= 0 and texel.x < base.get_width() and texel.y < base.get_height():
			return true
	return false

func _biome_grass(point: Vector3, cell_hash: int) -> float:
	for biome: Dictionary in _biomes:
		var to_local: Transform3D = biome.to_local
		var continent := to_local * point
		var origin: Vector2 = biome.origin
		var metres: float = biome.metres
		var base: Image = biome.base
		# The candidate's own jitter dithers the nearest texel into a blend.
		var texel := Vector2i(floori((continent.x - origin.x) / metres + 0.5 + _unit(cell_hash, 2)),
			floori((continent.z - origin.y) / metres + 0.5 + _unit(cell_hash, 3)))
		if texel.x < 0 or texel.y < 0 or texel.x >= base.get_width() or texel.y >= base.get_height():
			continue
		var weights := base.get_pixelv(texel)
		var secondary: Image = biome.secondary
		var mixes := secondary.get_pixelv(texel) if secondary != null \
			and texel.x < secondary.get_width() and texel.y < secondary.get_height() else Color(0, 0, 0, 0)
		var grass_base: PackedFloat32Array = biome.grass_base
		var grass_secondary: PackedFloat32Array = biome.grass_secondary
		var total := 0.0
		var grass := 0.0
		for layer: int in 4:
			var weight: float = weights[layer]
			total += weight
			grass += weight * lerpf(grass_base[layer], grass_secondary[layer], mixes[layer])
		return grass / total if total > 0.01 else LookProfile.GRASS_LAYER_DEFAULT
	# No biome blend here: as grassy as the region's file says its open ground
	# is (`grass.open`, 1 unless it says otherwise).
	return float(LookProfile.region_value(_classified_region, "grass", "open", 1.0))

## The tufts a candidate carries: none to GRASS_TUFTS_PER_CELL, as dense as
## its ground's class and grassiness ask, each at its own hashed spot in the
## cell, turned, scaled and tilted halfway to the ground. Returns the count.
func _grow(data: Array[PackedFloat32Array], hit: Vector3, normal: Vector3, kind: int,
		grassiness: float, palette: int, cell: Vector2i, cell_hash: int, step: float,
		blend := Vector2.ZERO) -> int:
	var bed := 0.0
	var density := LookProfile.GRASS_VERGE_DENSITY * grassiness
	if kind == Ground.GRASS:
		bed = smoothstep(LookProfile.GRASS_BED_EDGE.x, LookProfile.GRASS_BED_EDGE.y,
			value_noise(hit.x / LookProfile.GRASS_BED_METRES, hit.z / LookProfile.GRASS_BED_METRES, 11))
		density = (LookProfile.GRASS_BED_DENSITY * bed + LookProfile.GRASS_SCATTER_DENSITY) * grassiness
	# Ground too thin to carry a bed carries nothing: a candidate there grew
	# one tuft now and then, single dark or bright specks on bare silt, peat
	# and snow (hf95 58 at md_horizon, 47 at gm_gorse).
	if density < LookProfile.GRASS_DENSITY_FLOOR:
		return 0
	# Thin ground grows small grass: a bed's fringe and a verge's feathered
	# edges shrink rather than thin out into single tufts.
	var grown := lerpf(LookProfile.GRASS_THIN_SCALE, 1.0, clampf(grassiness, 0.0, 1.0))
	if kind == Ground.GRASS:
		grown *= lerpf(LookProfile.GRASS_THIN_SCALE, 1.0, bed)
	var expected := density * step * step
	var tufts := mini(int(expected) + (1 if _unit(hash(cell_hash + 7), 0) < fposmod(expected, 1.0) else 0),
		LookProfile.GRASS_TUFTS_PER_CELL)
	if tufts <= 0:
		return 0
	var tone := value_noise(hit.x / LookProfile.GRASS_TONE_METRES,
		hit.z / LookProfile.GRASS_TONE_METRES, 23) * 2.0 - 1.0
	var ground := ground_mottle(Vector2(hit.x, hit.z))
	var warm := LookProfile.GRASS_WARM
	var tilt := Vector3.UP.lerp(normal, LookProfile.GRASS_GROUND_TILT).normalized()
	var lean := Basis(Quaternion(Vector3.UP, tilt))
	var wind := LookProfile.GRASS_WIND_DIRECTION.normalized()
	for index: int in tufts:
		var tuft_seed := hash(Vector3i(cell.x, cell.y, index + 1))
		var offset := Vector2(_unit(tuft_seed, 0) - 0.5, _unit(tuft_seed, 1) - 0.5) * step
		var y := hit.y - (normal.x * offset.x + normal.z * offset.y) / maxf(normal.y, 0.3)
		var origin := Vector3(hit.x + offset.x, y, hit.z + offset.y)
		var pick := _unit(tuft_seed, 2)
		var variant := 0
		if kind == Ground.VERGE:
			variant = 0 if pick < 0.7 else 1
		elif bed > 0.15:
			variant = 1 if pick < 0.65 else (0 if pick < 0.85 else 2)
		else:
			variant = 2 if pick < 0.6 else 1
		var yaw := _unit(tuft_seed, 3) * TAU
		var turn_seed := hash(tuft_seed)
		var size := lerpf(LookProfile.GRASS_SCALE.x, LookProfile.GRASS_SCALE.y,
			_unit(turn_seed, 0)) * grown
		var turn := (lean * Basis(Vector3.UP, yaw)).scaled(Vector3.ONE * size)
		var jitter := (_unit(turn_seed, 1) - 0.5) * 2.0 * LookProfile.GRASS_VALUE_JITTER
		var warmth := clampf(tone + (_unit(turn_seed, 2) - 0.5) * 0.4, -1.0, 1.0)
		var tint := Color.WHITE.lerp(warm, warmth) if warmth >= 0.0 \
			else Color.WHITE.lerp(Color(1.0 / warm.r, 1.0 / warm.g, 1.0 / warm.b), -warmth)
		tint *= 1.0 + jitter
		if kind == Ground.VERGE:
			tint *= LookProfile.GRASS_VERGE_SHADE
		tint = Color(tint.r * ground.r, tint.g * ground.g, tint.b * ground.b)
		var phase := fposmod((origin.x * wind.x + origin.z * wind.y)
			/ LookProfile.GRASS_WIND_WAVE_METRES, 1.0)
		data[variant].append_array(PackedFloat32Array([
			turn.x.x, turn.y.x, turn.z.x, origin.x,
			turn.x.y, turn.y.y, turn.z.y, origin.y,
			turn.x.z, turn.y.z, turn.z.z, origin.z,
			tint.r, tint.g, tint.b, 1.0,
			float(palette), blend.x, blend.y, phase]))
	_count("tufts_" + GROUND_NAMES[kind], tufts)
	return tufts

## The ground paint's mottle at `xz` (the continent frame, as the paint's own
## mesh space is) as a colour multiplier: its low-frequency value and warmth
## variation and its fine verge mottle (painted_ground_paint.gdshaderinc,
## look_paint), on the colour as the renderer lights it (display-encoded in
## the compatibility renderer, linear in Forward+).
static func ground_mottle(xz: Vector2) -> Color:
	var coarse := xz / LookProfile.VARIATION_METRES
	var variation := 0.65 * paint_noise(coarse) \
		+ 0.35 * paint_noise(coarse * 2.7 + Vector2(13.1, 7.7)) - 0.5
	var value := (1.0 + variation * 2.0 * LookProfile.VARIATION) \
		* (1.0 + (paint_noise(xz / LookProfile.VERGE_FINE_METRES + Vector2(5.3, 2.1)) - 0.5)
			* 2.0 * LookProfile.VERGE_FINE)
	var warm := variation * 2.0 * LookProfile.VARIATION_HUE
	var mottle := Color(value * (1.0 + warm), value, value * (1.0 - warm))
	if not LookProfile.forward_plus():
		var encode := 1.0 / 2.2
		mottle = Color(pow(maxf(mottle.r, 0.0), encode), pow(maxf(mottle.g, 0.0), encode),
			pow(maxf(mottle.b, 0.0), encode))
	return mottle

## The paint's value noise (look_value_noise): Dave Hoskins' hash on the
## lattice, smoothly interpolated. Matches the shader to within its float
## precision.
static func paint_noise(p: Vector2) -> float:
	var cell := p.floor()
	var f := p - cell
	var u := f * f * (Vector2(3.0, 3.0) - 2.0 * f)
	var a := paint_hash(cell)
	var b := paint_hash(cell + Vector2(1.0, 0.0))
	var c := paint_hash(cell + Vector2(0.0, 1.0))
	var d := paint_hash(cell + Vector2(1.0, 1.0))
	return lerpf(lerpf(a, b, u.x), lerpf(c, d, u.x), u.y)

## The paint's look_hash.
static func paint_hash(p: Vector2) -> float:
	var p3 := Vector3(fposmod(p.x * 0.1031, 1.0), fposmod(p.y * 0.1031, 1.0),
		fposmod(p.x * 0.1031, 1.0))
	var lift := p3.dot(Vector3(p3.y + 33.33, p3.z + 33.33, p3.x + 33.33))
	p3 += Vector3(lift, lift, lift)
	return fposmod((p3.x + p3.y) * p3.z, 1.0)

## Fills the MultiMeshes from the tiles nearest the focus until the budget.
func _assemble(now: int) -> void:
	_dirty = false
	_assembled_msec = now
	var buffers: Array[PackedFloat32Array] = []
	for variant: int in VARIANTS:
		buffers.append(PackedFloat32Array())
	var drawn := _drawn_tiles()
	for key: Vector2i in drawn:
		var tile: Dictionary = _tiles[key]
		for variant: int in VARIANTS:
			buffers[variant].append_array(tile.data[variant])
	for variant: int in VARIANTS:
		var multimesh := _multimeshes[variant]
		var count := buffers[variant].size() / FLOATS_PER_TUFT
		if multimesh.instance_count != count:
			multimesh.instance_count = count
		if count > 0:
			multimesh.buffer = buffers[variant]
	_coverage_focus = _focus
	_coverage_radius = _drawn_radius(drawn)

## A distance fade must finish before the first omitted square tile, whether
## omitted by the instance cap or still being built. Tuft placement jitters
## by half a cell beyond its tile, so reserve that margin as well.
func _drawn_radius(drawn: Array[Vector2i]) -> float:
	var included := {}
	for key: Vector2i in drawn:
		included[key] = true
	var radius := LookProfile.GRASS_RADIUS
	var margin := LookProfile.GRASS_TILE_METRES / float(LookProfile.GRASS_TILE_CELLS) \
		* sqrt(0.5)
	for key: Vector2i in _tiles:
		if not included.has(key):
			radius = minf(radius, _tile_distance(key, _focus) - margin)
	for key: Vector2i in _queue:
		if not included.has(key):
			radius = minf(radius, _tile_distance(key, _focus) - margin)
	return maxf(radius, 0.0)

## Keep the fade inside the uploaded coverage while the focus moves between
## builds. Only expansion is eased: no frame may expose an unbuilt tile.
func _update_fade(now: int, local_focus: Vector3) -> void:
	var drift := Vector2(local_focus.x - _coverage_focus.x,
		local_focus.z - _coverage_focus.z).length()
	var available := maxf(0.0, _coverage_radius - drift)
	var elapsed := maxf(0.0, float(now - _fade_msec) / 1000.0) if _fade_msec > 0 else 0.0
	_fade_radius = minf(available, _fade_radius + elapsed * FADE_GROW_METRES_PER_SECOND)
	_fade_msec = now
	# Keep smoothstep's edges distinct even before coverage reaches the focus.
	var end := maxf(_fade_radius, 0.001)
	_material.set_shader_parameter(&"look_fade_metres",
		Vector2(maxf(0.0, end - LookProfile.GRASS_FADE_METRES), end))

## The tiles drawn: nearest the focus first, whole tiles, until the budget.
func _drawn_tiles() -> Array[Vector2i]:
	var keys: Array[Vector2i] = []
	for key: Vector2i in _tiles:
		keys.append(key)
	var focus := _focus
	keys.sort_custom(func(a: Vector2i, b: Vector2i) -> bool:
		return _tile_distance(a, focus) < _tile_distance(b, focus))
	var drawn: Array[Vector2i] = []
	var total := 0
	for key: Vector2i in keys:
		var count := int(_tiles[key].count)
		if total + count > LookProfile.GRASS_INSTANCE_BUDGET:
			break
		total += count
		drawn.append(key)
	return drawn

## Smooth value noise on the unit lattice (0..1), from hashed corners.
static func value_noise(x: float, z: float, salt: int) -> float:
	var cell_x := floori(x)
	var cell_z := floori(z)
	var fx := x - cell_x
	var fz := z - cell_z
	var ux := fx * fx * (3.0 - 2.0 * fx)
	var uz := fz * fz * (3.0 - 2.0 * fz)
	var a := _lattice(cell_x, cell_z, salt)
	var b := _lattice(cell_x + 1, cell_z, salt)
	var c := _lattice(cell_x, cell_z + 1, salt)
	var d := _lattice(cell_x + 1, cell_z + 1, salt)
	return lerpf(lerpf(a, b, ux), lerpf(c, d, ux), uz)

static func _lattice(x: int, z: int, salt: int) -> float:
	return float(hash(Vector3i(x, z, salt)) & 0xFFFF) / 65535.0

## One of four 8-bit lanes of a hash, as 0..1.
static func _unit(value: int, lane: int) -> float:
	return float((value >> (lane * 8)) & 0xFF) / 255.0

func _count(key: String, amount := 1) -> void:
	_census[key] = int(_census.get(key, 0)) + amount

## A neighbour's preview copy is named StreamView_<n>__<original>.
static func _plain_name(node_name: String) -> String:
	if node_name.begins_with("StreamView_"):
		return node_name.get_slice("__", 1)
	return node_name

## An outdoor map declares a sun and does not disable it, as LookGrade reads it.
static func _outdoor(manifest: WorldManifest) -> bool:
	var environment: Variant = manifest.data.get("environment")
	if environment is not Dictionary:
		return false
	var sun: Variant = (environment as Dictionary).get("sun")
	return sun is Dictionary and bool((sun as Dictionary).get("enabled", true))
