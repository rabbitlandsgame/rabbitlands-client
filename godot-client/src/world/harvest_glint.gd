extends RefCounted
## The cave glint (map polish, owner-approved 2026-11-16): a harvest node on a
## dark interior map - Landfall's underground and every other cave, barrow or
## vault - wears a few faint warm flares on its model that wink in turn.
##
## Harvestables are found by looking at the world, never by reading the map
## (owner 2026-11-14). Under a sunlit sky a reed bed or an ore seam reads at
## the game camera; in a cave lit at a quarter of the sun's energy the same
## seam is a dark lump on a dark floor, and "find it in the world" became
## "can't find it" for the underground's 739 nodes. The glint is drawn by the
## gameplay camera only (layer 2, as the storage halo is): neither map camera
## draws a 3D layer and neither map's overlay lists a harvest node, so it is no
## map marker. It is depth tested, so a seam behind a wall stays hidden, and it
## fades out beyond ~30 m, so it marks what is near rather than lighting a cave
## of beacons. Exterior maps never take it.
##
## One mesh and one material serve every node: the flares are placed in a unit
## box that the node's MeshInstance3D stretches over its model's bounds, and the
## shader (harvest_glint.gdshader) opens each flare in view space at a fixed
## size, so a node costs one culled draw and nothing per frame on the CPU.

const SHADER := preload("res://src/world/harvest_glint.gdshader")
const SPARKLE := preload("res://src/world/harvest_sparkle_3d.gd")

const NODE_NAME := "CaveGlint"
## The gameplay camera's layer (MapObject3D.GAMEPLAY_LAYER); the map cameras
## cull every 3D layer.
const LAYER := 2
## Beyond this the shader has already faded every flare out; the instance is
## culled there too.
const VISIBLE_METRES := 38.0
## An interior whose declared sun is at least this bright, or whose ambient
## light is, is lit well enough to find a node by eye (a gauntlet's arena, a
## sunlit archive hall): it takes no glint.
const BRIGHT_SUN_ENERGY := 0.5
const BRIGHT_AMBIENT_ENERGY := 0.9
## The flares in the unit box (x and z across the model's bounds, -0.5..0.5;
## y up its height, 0..1), and each one's share of the wink cycle (COLOR.r).
## A floor node's flares stand over its top; a wall node's (a vein set into the
## rock, whose +Z faces out of the face) on the face in front.
const FLOOR_FLARES := [Vector4(-0.22, 0.82, 0.16, 0.0), Vector4(0.24, 0.62, -0.18, 0.333),
	Vector4(0.04, 0.98, -0.04, 0.667)]
const WALL_FLARES := [Vector4(-0.22, 0.7, 0.46, 0.0), Vector4(0.2, 0.45, 0.48, 0.333),
	Vector4(0.02, 0.88, 0.44, 0.667)]
## The smallest side the flares spread over, so a flat mat's flares do not
## stand in one point.
const MINIMUM_SPREAD := 0.35
const MINIMUM_HEIGHT := 0.25

static var _floor_mesh: ArrayMesh
static var _wall_mesh: ArrayMesh
static var _material: ShaderMaterial

## Whether the harvest nodes of the map whose package is `manifest` (its
## world.json, parsed) glint: an interior (its `asset.interiorClass`, or the
## registry's `interiorOf`/`insidesOf` in `registry_entry`) that is dark - its
## declared sun weaker than BRIGHT_SUN_ENERGY and its ambient light weaker than
## BRIGHT_AMBIENT_ENERGY, or a cave profile. An exterior map never does.
static func wanted_for(manifest: Dictionary, registry_entry: Dictionary = {}) -> bool:
	var asset: Dictionary = manifest.get("asset", {}) if manifest.get("asset") is Dictionary else {}
	var interior := not str(asset.get("interiorClass", "")).is_empty() \
		or registry_entry.has("interiorOf") or registry_entry.has("insidesOf")
	if not interior:
		return false
	var environment: Dictionary = manifest.get("environment", {}) \
		if manifest.get("environment") is Dictionary else {}
	if str(environment.get("profile", "")).begins_with("cave"):
		return true
	return _energy(environment, "sun") < BRIGHT_SUN_ENERGY \
		and _energy(environment, "ambient") < BRIGHT_AMBIENT_ENERGY

static func _energy(environment: Dictionary, key: String) -> float:
	var light: Variant = environment.get(key)
	if light is not Dictionary:
		return 0.0
	var energy: Variant = (light as Dictionary).get("energy", 0.0)
	return float(energy) if energy is float or energy is int else 0.0

## The glint for a model whose bounds (in the model's own space) are `bounds`,
## to be added under that model so it takes the model's yaw, scale and seat.
## `wall` places the flares on the face in front of a wall seam.
static func build(bounds: AABB, wall := false) -> MeshInstance3D:
	var glint := MeshInstance3D.new()
	glint.name = NODE_NAME
	glint.mesh = _mesh(wall)
	glint.material_override = _shared_material()
	glint.layers = LAYER
	glint.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	glint.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	glint.visibility_range_end = VISIBLE_METRES
	var size := Vector3(maxf(bounds.size.x, MINIMUM_SPREAD), maxf(bounds.size.y, MINIMUM_HEIGHT),
		maxf(bounds.size.z, MINIMUM_SPREAD))
	var bottom := Vector3(bounds.get_center().x, bounds.position.y, bounds.get_center().z)
	glint.transform = Transform3D(Basis.from_scale(size), bottom)
	return glint

## The shared material (one for every node; the shader staggers them).
static func _shared_material() -> ShaderMaterial:
	if _material == null:
		_material = ShaderMaterial.new()
		_material.shader = SHADER
		_material.set_shader_parameter("flare_texture", SPARKLE._flare())
	return _material

static func _mesh(wall: bool) -> ArrayMesh:
	if wall and _wall_mesh != null:
		return _wall_mesh
	if not wall and _floor_mesh != null:
		return _floor_mesh
	var vertices := PackedVector3Array()
	var uvs := PackedVector2Array()
	var colours := PackedColorArray()
	var indices := PackedInt32Array()
	for flare: Vector4 in (WALL_FLARES if wall else FLOOR_FLARES):
		var base := vertices.size()
		for corner: Vector2 in [Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)]:
			vertices.append(Vector3(flare.x, flare.y, flare.z))
			uvs.append(corner)
			colours.append(Color(flare.w, 0.0, 0.0, 1.0))
		indices.append_array([base, base + 1, base + 2, base, base + 2, base + 3])
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_COLOR] = colours
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	# The flares open in view space beyond their centres; keep the instance
	# from being culled while a flare's edge is still on screen.
	mesh.custom_aabb = AABB(Vector3(-2.0, -1.0, -2.0), Vector3(4.0, 4.0, 4.0))
	if wall:
		_wall_mesh = mesh
	else:
		_floor_mesh = mesh
	return mesh
