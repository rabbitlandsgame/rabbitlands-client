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
##
## The rest of each row is the Low actor tier (owner decision 2026-11-02:
## Low and the Performance preset only; Medium and High unchanged).  Each
## value is read through its accessor below by the code that owns the
## behaviour; MEDIUM and HIGH carry the value that code used before the tier,
## so they behave exactly as they did.
##   body_cap_default       crowd bodies drawn while the player's crowd setting
##                          follows the quality (CrowdPresentation.BODY_CAP_DEFAULT
##                          is 160).
##   full_rate_metres       camera distance beyond which a body is never on the
##                          full animation rate (AnimationGate.HALF_RATE_METRES
##                          is 45 m).
##   hand_detail_metres     a remote humanoid nearer the camera than this gets
##                          finger animation ...
##   hand_detail_release_metres  ... and keeps it until it is farther than
##                          this (hysteresis).  INF: fingers at any distance.
##   combat_cues_full_rate_only  per-body hand cues (arcs, sparks, trails) only
##                          for full-rate and priority bodies.
##   effect_scale           share of LiveEffectBudget.LIMITS drawn at once
##                          (0.5 / 0.75 / 1.0 before the tier).
##   overhead_cap           shown non-priority overhead banners; 0 = no cap.
##   local_cape_step_hz     the local player's cape solver rate
##                          (CapeCloth.FIXED_STEP is 1/60 s).
##   remote_body_finish     per-vertex body refinement and face sculpt for
##                          remote actors.
##   frame_driven_motion    remote actors step once per drawn frame instead of
##                          on the physics tick.
## Key order is the same in every row (tests compare the rows' keys).
const QUALITY_PRESETS := {
	Quality.LOW: {
		"lod_bias_scale": 0.35,
		"cast_shadows": false,
		"non_local_cape": false,
		"body_cap_default": 60,
		"full_rate_metres": 35.0,
		"hand_detail_metres": 12.0,
		"hand_detail_release_metres": 15.0,
		"combat_cues_full_rate_only": true,
		"effect_scale": 0.25,
		"overhead_cap": 24,
		"local_cape_step_hz": 30,
		"remote_body_finish": false,
		"frame_driven_motion": true,
	},
	Quality.MEDIUM: {
		"lod_bias_scale": 0.65,
		"cast_shadows": true,
		"non_local_cape": false,
		"body_cap_default": 160,
		"full_rate_metres": 45.0,
		"hand_detail_metres": INF,
		"hand_detail_release_metres": INF,
		"combat_cues_full_rate_only": false,
		"effect_scale": 0.75,
		"overhead_cap": 0,
		"local_cape_step_hz": 60,
		"remote_body_finish": true,
		"frame_driven_motion": false,
	},
	Quality.HIGH: {
		"lod_bias_scale": 1.0,
		"cast_shadows": true,
		"non_local_cape": true,
		"body_cap_default": 160,
		"full_rate_metres": 45.0,
		"hand_detail_metres": INF,
		"hand_detail_release_metres": INF,
		"combat_cues_full_rate_only": false,
		"effect_scale": 1.0,
		"overhead_cap": 0,
		"local_cape_step_hz": 60,
		"remote_body_finish": true,
		"frame_driven_motion": false,
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


## Low actor tier accessors (see QUALITY_PRESETS).  Each answers only the
## graphics-quality part; the caller still applies its own exemptions (the
## local player, the target, previews, an explicit player setting).
static func body_cap_default(level: int) -> int:
	return int(QUALITY_PRESETS[normalized_quality(level)].body_cap_default)


static func full_rate_metres(level: int) -> float:
	return float(QUALITY_PRESETS[normalized_quality(level)].full_rate_metres)


static func hand_detail_metres(level: int) -> float:
	return float(QUALITY_PRESETS[normalized_quality(level)].hand_detail_metres)


static func hand_detail_release_metres(level: int) -> float:
	return float(QUALITY_PRESETS[normalized_quality(level)].hand_detail_release_metres)


static func combat_cues_full_rate_only(level: int) -> bool:
	return bool(QUALITY_PRESETS[normalized_quality(level)].combat_cues_full_rate_only)


static func effect_scale(level: int) -> float:
	return float(QUALITY_PRESETS[normalized_quality(level)].effect_scale)


static func overhead_cap(level: int) -> int:
	return int(QUALITY_PRESETS[normalized_quality(level)].overhead_cap)


static func local_cape_step_hz(level: int) -> int:
	return int(QUALITY_PRESETS[normalized_quality(level)].local_cape_step_hz)


static func remote_body_finish(level: int) -> bool:
	return bool(QUALITY_PRESETS[normalized_quality(level)].remote_body_finish)


static func frame_driven_motion(level: int) -> bool:
	return bool(QUALITY_PRESETS[normalized_quality(level)].frame_driven_motion)


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
