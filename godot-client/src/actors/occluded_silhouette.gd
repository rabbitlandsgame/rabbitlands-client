class_name OccludedSilhouette
extends RefCounted

## Keeps the player's own actor findable when the world covers it.
##
## The isometric rig looks down through whatever stands between it and the
## player, and in a wooded region that is usually a canopy. Two passes solve it:
##
##  - a marker overlay on the actor's own meshes, which draws nothing and stamps
##    the stencil wherever the actor survives the depth test - that is, wherever
##    it is genuinely visible;
##  - a clone of each mesh drawn with no depth test, which paints a tinted
##    silhouette only where the stencil was *not* stamped.
##
## The result is per-pixel: a player half behind a trunk is half normal and half
## silhouette. The clones sit on the gameplay-only visual layer, so the minimap
## and full-map cameras never see them.
##
## Scoped to the local player on purpose. Silhouetting every actor through every
## wall would be a wallhack, not a convenience.

const MARKER_SHADER := preload("res://src/actors/silhouette_stencil_marker.gdshader")
const SILHOUETTE_SHADER := preload("res://src/actors/occluded_silhouette.gdshader")

## Visual layer 2, matching ReplicatedActor3D: the gameplay camera renders
## layers 1 and 2, the full-map camera renders layers 1 and 3, and the minimap
## camera renders layer 1 alone. No map camera renders this one.
const GAMEPLAY_ONLY_VISUAL_LAYER := 2
const CLONE_META := "occlusion_silhouette_clone"
const CLONE_PREFIX := "OcclusionSilhouette_"

static var _marker_material: ShaderMaterial
static var _silhouette_material: ShaderMaterial

var _actor: Node3D
var _skeleton: Skeleton3D
var _pairs: Array[Dictionary] = []
var _enabled := false

func _init(actor: Node3D, skeleton: Skeleton3D = null) -> void:
	_actor = actor
	_skeleton = skeleton

func is_enabled() -> bool:
	return _enabled

## Turns the effect on or off. Building is deferred until it is first enabled,
## so an actor that never switches it on pays nothing.
func set_enabled(enabled: bool) -> void:
	if enabled == _enabled:
		return
	_enabled = enabled
	if enabled:
		rebuild()
	else:
		_teardown()

## Rebuilds the clone set from the actor's current meshes. Equipment and
## appearance add and remove mesh instances at runtime, so this is called again
## whenever they change.
func rebuild() -> void:
	_teardown()
	if not _enabled or not is_instance_valid(_actor):
		return
	for source: MeshInstance3D in _sources():
		var clone := _clone_of(source)
		if clone != null:
			_pairs.append({"source": source, "clone": clone})
		source.material_overlay = _marker()

## Mirrors source visibility onto the clones. Equipment hides body surfaces it
## covers and appearance hides wardrobe pieces the character never chose; the
## silhouette has to hide them too, or a helmet would leave a bare head showing
## through the wall it is behind.
func sync() -> void:
	if not _enabled:
		return
	var stale := false
	for pair: Dictionary in _pairs:
		# Read untyped and check first: equipment frees the meshes it owns, and
		# binding a freed instance to a typed local is itself the error we are
		# trying to survive.
		var source_ref: Variant = pair["source"]
		var clone_ref: Variant = pair["clone"]
		if not is_instance_valid(source_ref) or not is_instance_valid(clone_ref):
			stale = true
			continue
		var source: MeshInstance3D = source_ref
		var clone: MeshInstance3D = clone_ref
		clone.visible = source.visible
	if stale:
		rebuild()

func _teardown() -> void:
	for pair: Dictionary in _pairs:
		var source_ref: Variant = pair["source"]
		var clone_ref: Variant = pair["clone"]
		if is_instance_valid(source_ref):
			(source_ref as MeshInstance3D).material_overlay = null
		if is_instance_valid(clone_ref):
			(clone_ref as MeshInstance3D).queue_free()
	_pairs.clear()

## Every mesh that makes up the actor's body: not the clones themselves, and not
## the selection ring or anything else already confined to the gameplay-only
## layer, which is UI rather than a body.
func _sources() -> Array[MeshInstance3D]:
	var out: Array[MeshInstance3D] = []
	if not is_instance_valid(_actor):
		return out
	for node: Node in _actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_node: MeshInstance3D = node as MeshInstance3D
		if mesh_node.has_meta(CLONE_META):
			continue
		# Unequipping queue_frees its meshes, and a node waiting to be deleted is
		# still a child this frame. Cloning it would only produce a stale pair.
		if mesh_node.is_queued_for_deletion():
			continue
		if mesh_node.layers == GAMEPLAY_ONLY_VISUAL_LAYER:
			continue
		if mesh_node.mesh == null or mesh_node.mesh.get_surface_count() == 0:
			continue
		out.append(mesh_node)
	return out

func _clone_of(source: MeshInstance3D) -> MeshInstance3D:
	var clone := MeshInstance3D.new()
	clone.name = CLONE_PREFIX + source.name
	clone.mesh = source.mesh
	clone.material_override = _silhouette()
	clone.layers = GAMEPLAY_ONLY_VISUAL_LAYER
	clone.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	clone.visible = source.visible
	clone.set_meta(CLONE_META, true)

	if source.skin != null and _skeleton != null:
		# Skinned: hang it off the skeleton and give it the same skin, the way
		# skinned equipment is attached, so it deforms with the animation.
		clone.skin = source.skin
		_skeleton.add_child(clone)
		clone.skeleton = NodePath("..")
	else:
		# Unskinned: a child of the source inherits its transform for free,
		# including a BoneAttachment3D driving it from above.
		source.add_child(clone)
		clone.transform = Transform3D.IDENTITY
	return clone

static func _marker() -> ShaderMaterial:
	if _marker_material == null:
		_marker_material = ShaderMaterial.new()
		_marker_material.shader = MARKER_SHADER
		# Stamp before the silhouette reads.
		_marker_material.render_priority = 0
	return _marker_material

static func _silhouette() -> ShaderMaterial:
	if _silhouette_material == null:
		_silhouette_material = ShaderMaterial.new()
		_silhouette_material.shader = SILHOUETTE_SHADER
		_silhouette_material.render_priority = 1
	return _silhouette_material
