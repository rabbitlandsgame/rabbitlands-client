class_name ActorRenderQuality
extends RefCounted
## The actor-only part of the player's graphics quality.
##
## LookProfile owns the frame-level quality switch.  Its Quality values and
## these values deliberately share the same order, so an actor can consume the
## resolved level without depending on the world look implementation.  The
## actor applies this policy when it is built and whenever that level changes.
##
## `lod_bias` does not replace a mesh or material.  It tells Godot to select
## imported mesh LODs earlier: a smaller value is cheaper.  The authored bias
## and shadow mode are saved on the MeshInstance3D itself, then restored at
## HIGH or by restore_mesh().  This keeps intentionally shadowless and
## shadows-only geometry intact, and never duplicates a mesh, material, skin,
## or any of the actor's shared caches.

enum Quality { LOW, MEDIUM, HIGH }

const QUALITY_NAMES: Array[String] = ["low", "medium", "high"]
const QUALITY_DEFAULT := Quality.HIGH
const MIN_LOD_BIAS := 0.001

## LOW moves every imported LOD transition 2.86 times closer and removes actor
## shadows.  MEDIUM moves them 1.54 times closer but keeps authored shadows.
## Cape cloth is per-actor CPU work, so only HIGH simulates it on non-local
## actors; the local player's cape remains available at every quality.
const QUALITY_PRESETS := {
	Quality.LOW: {
		"lod_bias_scale": 0.35,
		"cast_shadows": false,
		"non_local_cape": false,
	},
	Quality.MEDIUM: {
		"lod_bias_scale": 0.65,
		"cast_shadows": true,
		"non_local_cape": false,
	},
	Quality.HIGH: {
		"lod_bias_scale": 1.0,
		"cast_shadows": true,
		"non_local_cape": true,
	},
}

const _BASE_LOD_BIAS := &"_actor_render_quality_base_lod_bias"
const _BASE_SHADOW_MODE := &"_actor_render_quality_base_shadow_mode"


static func normalized_quality(level: int) -> int:
	if level < 0 or level >= QUALITY_NAMES.size():
		return QUALITY_DEFAULT
	return level


static func quality_name(level: int) -> String:
	return QUALITY_NAMES[normalized_quality(level)]


static func lod_bias_scale(level: int) -> float:
	return float(QUALITY_PRESETS[normalized_quality(level)].lod_bias_scale)


static func casts_shadows(level: int) -> bool:
	return bool(QUALITY_PRESETS[normalized_quality(level)].cast_shadows)


static func non_local_cape_enabled(level: int) -> bool:
	return bool(QUALITY_PRESETS[normalized_quality(level)].non_local_cape)


## This answers only the graphics-quality part of cape activation.  The actor
## still combines it with "a cape is worn" and its animation/distance tier.
static func cape_enabled(level: int, is_local_actor: bool) -> bool:
	return is_local_actor or non_local_cape_enabled(level)


## Apply one quality without replacing resources or losing the authored
## values.  Repeated LOW/MEDIUM/HIGH changes always derive from the first
## authored values rather than compounding the LOD multiplier.
static func apply_mesh(mesh: MeshInstance3D, level: int) -> void:
	if mesh == null:
		return
	if not mesh.has_meta(_BASE_LOD_BIAS):
		mesh.set_meta(_BASE_LOD_BIAS, mesh.lod_bias)
	if not mesh.has_meta(_BASE_SHADOW_MODE):
		mesh.set_meta(_BASE_SHADOW_MODE, mesh.cast_shadow)
	var base_bias := float(mesh.get_meta(_BASE_LOD_BIAS))
	mesh.lod_bias = maxf(MIN_LOD_BIAS, base_bias * lod_bias_scale(level))
	if casts_shadows(level):
		mesh.cast_shadow = int(mesh.get_meta(_BASE_SHADOW_MODE))
	else:
		mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF


## Apply the policy to body, hair, and equipment MeshInstance3Ds under an
## actor root.  Runtime children have no scene owner, hence owned=false.
static func apply_actor(root: Node, level: int) -> void:
	if root == null:
		return
	if root is MeshInstance3D:
		apply_mesh(root as MeshInstance3D, level)
	for child: Node in root.find_children("*", "MeshInstance3D", true, false):
		apply_mesh(child as MeshInstance3D, level)


## Remove the runtime overlay and forget its baseline.  A later apply_mesh()
## then treats any newly authored values as the new source of truth.
static func restore_mesh(mesh: MeshInstance3D) -> void:
	if mesh == null:
		return
	if mesh.has_meta(_BASE_LOD_BIAS):
		mesh.lod_bias = float(mesh.get_meta(_BASE_LOD_BIAS))
		mesh.remove_meta(_BASE_LOD_BIAS)
	if mesh.has_meta(_BASE_SHADOW_MODE):
		mesh.cast_shadow = int(mesh.get_meta(_BASE_SHADOW_MODE))
		mesh.remove_meta(_BASE_SHADOW_MODE)


static func restore_actor(root: Node) -> void:
	if root == null:
		return
	if root is MeshInstance3D:
		restore_mesh(root as MeshInstance3D)
	for child: Node in root.find_children("*", "MeshInstance3D", true, false):
		restore_mesh(child as MeshInstance3D)
