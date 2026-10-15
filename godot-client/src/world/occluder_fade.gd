class_name OccluderFade
extends RefCounted

## Turns whatever stands between the camera and the local player translucent.
##
## The isometric rig looks down through the world, so a rock, a tree trunk or a
## roof regularly parks itself on the line from the camera to the player. Each
## mesh that lands on that line is blended towards glass and blended back when
## it clears, which leaves the player looking at their own character properly
## lit, properly animated and wearing the equipment they chose, rather than at a
## flat cutout painted over the obstacle.
##
## Only the local player's line of sight is probed. Fading every obstacle in
## front of every actor would strip the map bare and would be a wallhack rather
## than a convenience.
##
## Detection is geometric, not physical. Most of the world carries no collision
## at all - the loader builds bodies only for declared nodes and walk surfaces,
## and batched props deliberately have none - so a physics ray would sail
## straight through the very rocks this exists to fade. The loaded meshes are
## instead indexed once into a flat XZ grid, and each probe tests the
## camera-to-player segment against the oriented box of every mesh registered in
## the cells that segment crosses, then checks real triangles around the chest.
## The geometry is static, so the index is built
## once per imported root. Its grid stays in that root's coordinates, so a
## streamed root can move or become active without rebuilding it.

## Cell size of the lookup grid. Large enough that a probe touches a handful of
## cells, small enough that a cell holds a handful of meshes.
const CELL_METRES := 16.0
## The probe is a segment, but a player is not. Boxes are grown by this much, so
## an obstacle covering a shoulder counts as covering the player.
const PROBE_RADIUS := 0.25
## Where on the actor the probe aims: chest height, so a low wall the player can
## be seen over does not fade and a doorway pillar does.
const PROBE_HEIGHT := 1.0
## How far in front of the camera the probe starts, keeping geometry the near
## plane already clipped out of it.
const PROBE_NEAR := 0.1
## Opacity an obstacle settles at while it covers the player: enough to read the
## character through, enough to keep the obstacle's own shape legible.
const FADED_ALPHA := 0.5
## Seconds for a full fade towards transparency. Short enough to feel immediate,
## long enough that walking past a fence post does not strobe.
const FADE_SECONDS := 0.24
## Restore more gently and hold briefly through gaps between probe samples.
const RESTORE_SECONDS := 0.32
const RELEASE_HOLD_SECONDS := 0.12
## Probes per second. The camera and the player both move smoothly, so the set
## of obstacles changes far more slowly than the frame rate does; the fades
## themselves are still animated on every frame.
const PROBES_PER_SECOND := 12.0
## Meshes wider than this are scenery rather than obstacles. Terrain is already
## excluded by its walk-surface collision, but a map may carry an undeclared
## ground slab or a distant cliff shell, and fading one of those would blank
## half the screen. Overridable per map as `rendering.occluderFadeMaxExtentMetres`.
const MAX_EXTENT_METRES := 60.0
## Node names that are ground whatever their size or collision: exported
## terrain, walk decks, and the authored ground patches painted over them.
const GROUND_NAME_PREFIXES: Array[String] = ["AuthoredGround_", "Terrain_", "Walk_"]

## One indexed mesh, plus whatever it takes to put it back the way it was.
class Occluder extends RefCounted:
	var node: MeshInstance3D
	## The mesh's own AABB grown by the probe radius, in the mesh's local space.
	## Testing there rather than against a world AABB means a wall at 45 degrees
	## is tested as the thin slab it is instead of the fat box enclosing it.
	var box: AABB
	## Set when the loader collapsed this mesh into a MultiMeshInstance3D. The
	## batch draws it and the node itself is hidden, so fading it means lifting
	## this one instance out of the batch for as long as the fade lasts.
	var batch: MultiMeshInstance3D
	var batch_index := -1
	var fade := 0.0
	var target := 0.0
	var applied := false
	var faded_alpha := FADED_ALPHA
	var release_hold := 0.0

	var _saved_override: Material
	var _saved_surfaces: Array[Material] = []
	var _saved_instance: Transform3D = Transform3D.IDENTITY
	var _faded: Array[BaseMaterial3D] = []
	var _opacity: PackedFloat32Array = PackedFloat32Array()
	# Look pass (not with the look off; see LookFade): the dithered copies swapped
	# in instead of blended ones, and the twin casting the mesh's shadow while
	# it fades. Both stay empty with the pass off.
	var _dithered: Array[ShaderMaterial] = []
	var _shadow: MeshInstance3D

	## True while the mesh is actually drawing. A collision proxy is hidden for
	## good and an interior wall is hidden by the cutaway while the camera looks
	## through it; neither should fade while it is not on screen. A batched mesh
	## is the exception - its node is hidden by design, and while it is faded
	## this class is the thing holding it visible.
	func is_drawing() -> bool:
		if not is_instance_valid(node):
			return false
		if batch != null:
			return is_instance_valid(batch) and batch.is_visible_in_tree()
		return node.is_visible_in_tree()

	## Swaps in duplicated materials that can carry an alpha. Duplicates rather
	## than edits, because the imported materials are shared between every copy
	## of a mesh and writing alpha onto one would fade every rock in the region.
	func apply() -> void:
		if applied or not is_instance_valid(node):
			return
		applied = true
		if batch != null:
			_lift_from_batch()
		# Look pass (not with the look off): the faded mesh stops casting, a wall
		# or roof handing its shadow to a solid twin, taken before the faded
		# copies go in.
		if LookProfile.enabled():
			_shadow = LookFade.hold_shadow(node)
		if node.material_override is BaseMaterial3D:
			var original: BaseMaterial3D = node.material_override as BaseMaterial3D
			_saved_override = original
			# Look pass (not with the look off): a dithered stand-in where it has one.
			var dithered_override := _look_dithered(original)
			if dithered_override != null:
				node.material_override = dithered_override
			else:
				var single := _fade_copy(original)
				_faded.append(single)
				_opacity.append(original.albedo_color.a)
				node.material_override = single
		else:
			var mesh: Mesh = node.mesh
			var surfaces: int = 0 if mesh == null else mesh.get_surface_count()
			for surface: int in surfaces:
				_saved_surfaces.append(node.get_surface_override_material(surface))
				var active: Material = node.get_active_material(surface)
				# Look pass (not with the look off): a dithered stand-in where it has one.
				var dithered := _look_dithered(active)
				if dithered != null:
					_faded.append(null)
					_opacity.append(1.0)
					node.set_surface_override_material(surface, dithered)
				elif active is BaseMaterial3D:
					var copy := _fade_copy(active as BaseMaterial3D)
					_faded.append(copy)
					_opacity.append((active as BaseMaterial3D).albedo_color.a)
					node.set_surface_override_material(surface, copy)
				else:
					# A ShaderMaterial owns its own transparency and there is no
					# general way to reach in and dim it. Left alone, so the
					# surface stays solid rather than breaking.
					_faded.append(null)
					_opacity.append(1.0)
		write_alpha()

	## Look pass (not with the look off): the copy LookFade dithers `material` out
	## with, kept for write_alpha. Null with the pass off, and for a material
	## LookFade has no dithered copy of (it then fades as on develop).
	func _look_dithered(material: Material) -> ShaderMaterial:
		if not LookProfile.enabled():
			return null
		var dithered := LookFade.dither_copy(material, node)
		if dithered != null:
			_dithered.append(dithered)
		return dithered

	## Puts the original materials back, and hands a batched mesh back to the
	## MultiMesh that owns it.
	func restore() -> void:
		if not applied:
			return
		applied = false
		if is_instance_valid(node):
			if _saved_surfaces.is_empty():
				node.material_override = _saved_override
			else:
				for surface: int in _saved_surfaces.size():
					node.set_surface_override_material(surface, _saved_surfaces[surface])
		_saved_override = null
		_saved_surfaces.clear()
		_faded.clear()
		_opacity.clear()
		# Look pass: nothing to undo for a fade that began with the pass off. Asked
		# of the node rather than the switch, which the player may have turned
		# since this fade began. The node may already be freed with its map, and
		# a freed object must not reach a typed parameter.
		_dithered.clear()
		if is_instance_valid(_shadow) or (is_instance_valid(node)
				and (node.has_meta(LookFade.SHADOW_META) or node.has_meta(LookFade.MODE_META))):
			LookFade.release_shadow(node if is_instance_valid(node) else null,
				_shadow if is_instance_valid(_shadow) else null)
		_shadow = null
		if batch != null:
			_return_to_batch()

	## Pushes the current fade onto the duplicated materials.
	func write_alpha() -> void:
		var scale: float = lerpf(1.0, faded_alpha, clampf(fade, 0.0, 1.0))
		for index: int in _faded.size():
			var material: BaseMaterial3D = _faded[index]
			if material == null:
				continue
			var colour: Color = material.albedo_color
			colour.a = _opacity[index] * scale
			material.albedo_color = colour
		# Look pass (not with the look off): the fade's progress opens the hole.
		for material: ShaderMaterial in _dithered:
			LookFade.write(material, scale, fade)

	## The batch holds this mesh's transform relative to its imported root, so collapsing that instance
	## to zero scale drops it from the draw without disturbing the others.
	## Keeping its origin leaves the batch's bounds, and so its culling, alone.
	func _lift_from_batch() -> void:
		if not is_instance_valid(batch) or batch.multimesh == null:
			return
		if batch_index < 0 or batch_index >= batch.multimesh.instance_count:
			return
		_saved_instance = batch.multimesh.get_instance_transform(batch_index)
		batch.multimesh.set_instance_transform(batch_index,
			Transform3D(Basis().scaled(Vector3.ZERO), _saved_instance.origin))
		node.visible = true

	func _return_to_batch() -> void:
		if is_instance_valid(node):
			node.visible = false
		if not is_instance_valid(batch) or batch.multimesh == null:
			return
		if batch_index < 0 or batch_index >= batch.multimesh.instance_count:
			return
		batch.multimesh.set_instance_transform(batch_index, _saved_instance)

	## Alpha blending regardless of what the original did. A cutout leaf keeps
	## its cutout - the texture's alpha still multiplies through - it simply
	## blends instead of clipping, and a material that was writing depth stops,
	## which is the whole point of the exercise.
	static func _fade_copy(source: BaseMaterial3D) -> BaseMaterial3D:
		var copy: BaseMaterial3D = source.duplicate() as BaseMaterial3D
		copy.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		return copy

var _enabled := false
var _grid: Dictionary = {}
## Built lazily after a bounds hit and shared by instances of the same mesh.
var _triangle_meshes: Dictionary = {}
var _occluders: Array[Occluder] = []
var _active: Array[Occluder] = []
var _max_extent := MAX_EXTENT_METRES
var _faded_alpha := FADED_ALPHA
var _probe_countdown := 0.0
var _root: Node3D

func indexed_count() -> int:
	return _occluders.size()

func is_active() -> bool:
	return not _occluders.is_empty()

func is_enabled() -> bool:
	return _enabled

## Indexes the meshes of a freshly loaded map. Returns how many of them are
## eligible to fade.
func configure(manifest: WorldManifest, imported_world: Node3D) -> int:
	reset()
	if imported_world == null:
		return 0
	_root = imported_world
	_max_extent = MAX_EXTENT_METRES
	_faded_alpha = FADED_ALPHA
	var proxy_names: Dictionary = {}
	if manifest != null:
		var rendering_value: Variant = manifest.data.get("rendering", {})
		if rendering_value is Dictionary:
			_max_extent = maxf(1.0, float((rendering_value as Dictionary).get(
				"occluderFadeMaxExtentMetres", MAX_EXTENT_METRES)))
			# Layered monumental gates need less opacity than a single tree.
			_faded_alpha = clampf(float((rendering_value as Dictionary).get(
				"occluderFadeAlpha", FADED_ALPHA)), 0.0, 1.0)
		var collision: Dictionary = manifest.data.get("collision", {})
		if bool(collision.get("nodesAreProxies", false)):
			for node_name: String in collision.get("nodeNames", []):
				proxy_names[node_name] = true
	for node: Node in imported_world.find_children("*", "MeshInstance3D", true, false):
		if proxy_names.has(str(node.name)):
			continue
		var occluder := _index(node as MeshInstance3D)
		if occluder != null:
			_occluders.append(occluder)
	return _occluders.size()

## Restores everything currently faded and drops the index. Safe on a freed map:
## every occluder checks its node before touching it.
func reset() -> void:
	for occluder: Occluder in _active:
		occluder.restore()
	_active.clear()
	_occluders.clear()
	_grid.clear()
	_triangle_meshes.clear()
	_probe_countdown = 0.0
	_root = null

## Puts every faded mesh back to rest at once and keeps the index: the next
## probe fades whatever still covers the player again, from solid, with
## whatever materials it then rests on. For the look's switch (LookSwitch),
## which swaps the resting materials a fade holds on to; the index itself does
## not depend on the look. The fade's progress and target are cleared too: a
## probe skips an occluder whose target is already set, so one released at
## full fade was never faded again (the live-switch captures showed an
## Amberwood ruin standing solid in front of the player).
func release() -> void:
	for occluder: Occluder in _active:
		occluder.restore()
		occluder.fade = 0.0
		occluder.target = 0.0
	_active.clear()
	_probe_countdown = 0.0

## Turning it off does not snap: the targets go to zero and the next few frames
## blend the obstacles back to solid.
func set_enabled(enabled: bool) -> void:
	if enabled == _enabled:
		return
	_enabled = enabled
	if not enabled:
		for occluder: Occluder in _active:
			occluder.target = 0.0
			occluder.release_hold = 0.0

## Called every frame. The probe runs on its own slower clock; the fades it
## decided are animated on every one of them.
func update(delta: float, camera: Camera3D, player: Node3D) -> void:
	if not is_instance_valid(_root) or not _root.is_inside_tree():
		reset()
		return
	if _occluders.is_empty():
		return
	# Look pass (not with the look off): the faded look materials cut their hole
	# round the player's chest, where the probe aims.
	if LookProfile.enabled() and is_instance_valid(player):
		LookFade.focus = player.global_position + Vector3(0.0, PROBE_HEIGHT, 0.0)
	_probe_countdown -= delta
	if _probe_countdown <= 0.0:
		_probe_countdown = 1.0 / PROBES_PER_SECOND
		_probe(camera, player)
	_advance(delta)

## Marks everything the camera-to-player segment passes through, and unmarks
## whatever it no longer does.
func _probe(camera: Camera3D, player: Node3D) -> void:
	for occluder: Occluder in _active:
		occluder.target = 0.0
	if not _enabled or not _root.is_visible_in_tree() or not is_instance_valid(camera) or not is_instance_valid(player):
		return
	var to: Vector3 = player.global_position + Vector3(0.0, PROBE_HEIGHT, 0.0)
	var from: Vector3 = camera.global_position
	var along: Vector3 = to - from
	var length: float = along.length()
	if length <= PROBE_NEAR:
		return
	from += along / length * PROBE_NEAR
	var into_root := _root.global_transform.affine_inverse()
	for occluder: Occluder in _candidates(into_root * from, into_root * to):
		if occluder.target > 0.0 or not occluder.is_drawing():
			continue
		var into_local: Transform3D = occluder.node.global_transform.affine_inverse()
		if not _segment_hits_box(occluder.box, into_local * from, into_local * to):
			continue
		if not _blocks_body(occluder, into_local, from, to, camera):
			continue
		occluder.target = 1.0
		occluder.release_hold = RELEASE_HOLD_SECONDS
		if not occluder.applied:
			occluder.apply()
			_active.append(occluder)

## Bounds only select candidates: gaps in a canopy or doorway must not fade
## the whole object. Probe a small cross around the chest against real faces.
func _blocks_body(occluder: Occluder, into_local: Transform3D,
		from: Vector3, to: Vector3, camera: Camera3D) -> bool:
	var mesh: Mesh = occluder.node.mesh
	if not _triangle_meshes.has(mesh):
		_triangle_meshes[mesh] = mesh.generate_triangle_mesh()
	var triangles: TriangleMesh = _triangle_meshes[mesh] as TriangleMesh
	if triangles == null:
		return false
	var right := camera.global_transform.basis.x.normalized() * PROBE_RADIUS
	var up := camera.global_transform.basis.y.normalized() * PROBE_RADIUS
	for offset: Vector3 in [Vector3.ZERO, right, -right, up, -up]:
		if not triangles.intersect_segment(into_local * from,
				into_local * (to + offset)).is_empty():
			return true
	return false

## Every mesh registered in a grid cell the segment's footprint covers. The
## footprint is used rather than a walked line because the rig never looks from
## further away than its maximum zoom, which is a handful of cells across.
func _candidates(from: Vector3, to: Vector3) -> Array[Occluder]:
	var found: Array[Occluder] = []
	var seen: Dictionary = {}
	var min_x: int = floori(minf(from.x, to.x) / CELL_METRES)
	var max_x: int = floori(maxf(from.x, to.x) / CELL_METRES)
	var min_z: int = floori(minf(from.z, to.z) / CELL_METRES)
	var max_z: int = floori(maxf(from.z, to.z) / CELL_METRES)
	for x: int in range(min_x, max_x + 1):
		for z: int in range(min_z, max_z + 1):
			var bucket_value: Variant = _grid.get(Vector2i(x, z))
			if bucket_value == null:
				continue
			for occluder: Occluder in bucket_value as Array:
				if seen.has(occluder):
					continue
				seen[occluder] = true
				found.append(occluder)
	return found

## Moves every fade towards its target and retires the ones that reached solid.
func _advance(delta: float) -> void:
	if _active.is_empty():
		return
	var settled: Array[Occluder] = []
	for occluder: Occluder in _active:
		var elapsed := delta
		if occluder.target <= 0.0:
			var held := minf(elapsed, occluder.release_hold)
			occluder.release_hold -= held
			elapsed -= held
		var duration := FADE_SECONDS if occluder.target > 0.0 else RESTORE_SECONDS
		var step := elapsed / duration
		occluder.fade = move_toward(occluder.fade, occluder.target, step)
		if occluder.fade <= 0.0 and occluder.target <= 0.0:
			occluder.restore()
			settled.append(occluder)
		else:
			occluder.write_alpha()
	for occluder: Occluder in settled:
		_active.erase(occluder)

## Decides whether one mesh can fade, and files it in the grid if it can.
func _index(mesh_instance: MeshInstance3D) -> Occluder:
	if mesh_instance == null or mesh_instance.mesh == null:
		return null
	if mesh_instance.mesh.get_surface_count() == 0:
		return null
	# Shared causeway structure contains only the slab, piers and 0.4m curbs.
	# Its merged box spans the whole road; growing it by the probe radius can
	# enclose the actor's chest even though none of that geometry obscures it.
	# Keep native and receiving-preview copies opaque across a handoff.
	var node_name := str(mesh_instance.name)
	if node_name.begins_with("StreamView_"):
		node_name = node_name.get_slice("__", 1)
	if node_name.begins_with("Structure_StreamCauseway_"):
		return null
	# The ground is not an obstacle: it is under the player, and fading it would
	# open a hole onto the sky. The loader marks walk surfaces by hanging
	# navigation collision off them, which is a firmer signal than a name - but
	# the continent exporter's authored ground patches (a gate forecourt, a bed
	# of leaf litter) lie over that surface with no collision of their own and
	# fall well inside the extent cap, so their grown box holds the player's
	# chest whenever the player stands on one. Those are known by name.
	for prefix: String in GROUND_NAME_PREFIXES:
		if node_name.begins_with(prefix):
			return null
	if _is_walk_surface(mesh_instance):
		return null
	# Look pass: nor is the rest of the ground the look paints, which develop
	# faded under the player's feet (see LookFade). Asked with the look off
	# too: the index outlives a switch (`release`), so it must not depend on
	# the look. Every name LookGround knows today is caught by the prefixes
	# above already; this keeps a ground name it learns later solid either way.
	if LookFade.keeps_solid(node_name):
		return null
	var transform: Transform3D = mesh_instance.global_transform
	var local_box: AABB = mesh_instance.get_aabb()
	var relative_transform := _root.global_transform.affine_inverse() * transform
	var root_box: AABB = relative_transform * local_box
	if maxf(root_box.size.x, root_box.size.z) > _max_extent:
		return null
	var occluder := Occluder.new()
	occluder.faded_alpha = _faded_alpha
	occluder.node = mesh_instance
	if mesh_instance.has_meta(WorldLoader.BATCH_META):
		var batch_value: Variant = mesh_instance.get_meta(WorldLoader.BATCH_META)
		if batch_value is MultiMeshInstance3D:
			occluder.batch = batch_value as MultiMeshInstance3D
			occluder.batch_index = int(mesh_instance.get_meta(
				WorldLoader.BATCH_INDEX_META, -1))
	# The probe radius is a world-space distance and the box is tested in local
	# space, so it has to be divided back through the node's own scale.
	var scale: Vector3 = transform.basis.get_scale()
	var margin := Vector3(
		PROBE_RADIUS / maxf(absf(scale.x), 0.001),
		PROBE_RADIUS / maxf(absf(scale.y), 0.001),
		PROBE_RADIUS / maxf(absf(scale.z), 0.001))
	local_box.position -= margin
	local_box.size += margin * 2.0
	occluder.box = local_box
	_register(occluder, relative_transform * local_box)
	return occluder

## Files an occluder under every cell its expanded root-local bounds touch, so a probe that
## crosses any part of a mesh finds it in the first cell it looks at.
func _register(occluder: Occluder, root_box: AABB) -> void:
	var min_x: int = floori(root_box.position.x / CELL_METRES)
	var max_x: int = floori(root_box.end.x / CELL_METRES)
	var min_z: int = floori(root_box.position.z / CELL_METRES)
	var max_z: int = floori(root_box.end.z / CELL_METRES)
	for x: int in range(min_x, max_x + 1):
		for z: int in range(min_z, max_z + 1):
			var key := Vector2i(x, z)
			if not _grid.has(key):
				_grid[key] = []
			(_grid[key] as Array).append(occluder)

static func _is_walk_surface(mesh_instance: MeshInstance3D) -> bool:
	for child: Node in mesh_instance.get_children():
		var body: StaticBody3D = child as StaticBody3D
		# Residents use a preview layer (or zero for hidden geometry). The
		# original navigation identity survives both states and promotion.
		if body != null and (int(body.get_meta("stream_collision_layer", body.collision_layer)) & WorldLoader.NAVIGATION_SURFACE_LAYER) != 0:
			return true
	return false

## Slab test: true when the segment from `from` to `to` passes through `box`,
## all three expressed in the same space.
static func _segment_hits_box(box: AABB, from: Vector3, to: Vector3) -> bool:
	var direction: Vector3 = to - from
	var minimum: Vector3 = box.position
	var maximum: Vector3 = box.end
	var enter := 0.0
	var exit := 1.0
	for axis: int in 3:
		var offset: float = direction[axis]
		var origin: float = from[axis]
		if absf(offset) < 0.00001:
			if origin < minimum[axis] or origin > maximum[axis]:
				return false
			continue
		var near: float = (minimum[axis] - origin) / offset
		var far: float = (maximum[axis] - origin) / offset
		if near > far:
			var swap: float = near
			near = far
			far = swap
		enter = maxf(enter, near)
		exit = minf(exit, far)
		if enter > exit:
			return false
	return true
