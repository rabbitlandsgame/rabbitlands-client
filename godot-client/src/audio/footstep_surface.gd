extends RefCounted
## Resolves the material under the player's feet using the same navigation
## layer as actor grounding. Works with freshly imported and cached maps.

const SURFACES := {
	"snow": ["snow", "frost"],
	"wood": ["timber", "wood", "plank", "board", "bamboo", "teak", "bark"],
	"stone": ["stone", "rock", "paving", "paver", "cobble", "ashlar", "marble", "slate", "granite", "brick", "mosaic", "scree", "shingle", "ice", "crystal", "plaza", "metal", "iron", "gilt", "sett", "causeway", "resonant_road", "vault_floor", "cave_floor", "jade_scale"],
	"sand": ["sand", "dust", "ash", "badland"],
	"grass": ["grass", "turf", "meadow", "forest_floor", "jungle_floor", "jungle_trail", "fern", "pasture", "leaf", "heather", "moss", "steppe"],
	"dirt": ["dirt", "earth", "soil", "mud", "clay", "path", "road", "ground", "clearing"],
}

static func from_name(label: String) -> String:
	var lower := label.to_lower()
	# Solid surfaces precede loose cover: sandstone and mossy stone are stone.
	for surface: String in SURFACES:
		for keyword: String in SURFACES[surface]:
			if keyword in lower:
				return surface
	return "dirt"

static func at_position(space: PhysicsDirectSpaceState3D, position: Vector3) -> String:
	if space == null:
		return "dirt"
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(position.x, 400.0, position.z),
		Vector3(position.x, -100.0, position.z), WorldLoader.NAVIGATION_SURFACE_LAYER)
	var hit := space.intersect_ray(query)
	if hit.is_empty():
		# Round tile centres can fall exactly on a triangle seam.
		query.from += Vector3(0.0001, 0.0, 0.0001)
		query.to += Vector3(0.0001, 0.0, 0.0001)
		hit = space.intersect_ray(query)
	var collider := hit.get("collider") as CollisionObject3D
	if collider != null and collider.get_parent() is not MeshInstance3D:
		# Some maps place a navigation proxy just above their rendered terrain.
		# Prefer that terrain's material, but never a floor far below a bridge.
		query.exclude = [collider.get_rid()]
		var rendered := space.intersect_ray(query)
		if not rendered.is_empty() and absf(
				(hit["position"] as Vector3).y - (rendered["position"] as Vector3).y) <= 0.5:
			return from_hit(rendered)
	return from_hit(hit)

static func from_hit(hit: Dictionary) -> String:
	var collider := hit.get("collider") as CollisionObject3D
	if collider == null:
		return "dirt"
	var instance := collider.get_parent() as MeshInstance3D
	if instance != null and instance.mesh != null:
		var mesh := instance.mesh
		var face: int = int(hit.get("face_index", -1))
		# A terrain mesh can contain grass, sand and paving in separate surfaces.
		# Trimesh face indices follow their order; use counts, not vertex readback.
		for surface: int in mesh.get_surface_count():
			if mesh.get_surface_count() > 1:
				if face < 0 or mesh is not ArrayMesh:
					break
				var array_mesh := mesh as ArrayMesh
				if array_mesh.surface_get_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES:
					continue
				var indices := array_mesh.surface_get_array_index_len(surface)
				var count := indices if indices > 0 else array_mesh.surface_get_array_len(surface)
				if face >= count / 3:
					face -= count / 3
					continue
			var material := instance.get_active_material(surface)
			if material != null and not material.resource_name.is_empty():
				return from_name(material.resource_name)
			break
		return from_name(str(instance.name))
	var shape_index: int = int(hit.get("shape", -1))
	if shape_index >= 0:
		var owner := collider.shape_owner_get_owner(collider.shape_find_owner(shape_index)) as Node
		if owner != null:
			return from_name(str(owner.name))
	return "dirt"
