# Read-only resource census for the crowd benchmark. Keep this outside the
# timed benchmark interval and preload it only from diagnostics.
extends RefCounted

## Count native skinned equipment without registering, attaching, or changing
## any actor or resource. `nodes` is the benchmark's actor-id to actor map.
static func census(nodes: Dictionary) -> Dictionary:
	var total_mesh_instances := 0
	var total_actor_distinct_skins := 0
	var total_actor_deduplicated_bind_count := 0
	var total_actor_distinct_skin_contents := 0
	var total_actor_deduplicated_content_bind_count := 0
	var unique_skins: Dictionary = {}
	var unique_skin_contents: Dictionary = {}
	var skin_content_keys: Dictionary = {}
	var per_actor: Array[Dictionary] = []

	for key: Variant in nodes:
		var value: Variant = nodes[key]
		if not is_instance_valid(value) or not value is ReplicatedActor3D:
			continue
		var actor := value as ReplicatedActor3D
		if actor.is_queued_for_deletion():
			continue
		var actor_skins: Dictionary = {}
		var actor_skin_contents: Dictionary = {}
		var actor_mesh_instances := 0
		var actor_deduplicated_bind_count := 0
		var actor_deduplicated_content_bind_count := 0

		# This is the only subtree walk for this actor. Call the census outside
		# the benchmark's sampled timing interval.
		for child: Node in actor.find_children("*", "MeshInstance3D", true, false):
			var mesh_instance := child as MeshInstance3D
			if mesh_instance == null or mesh_instance.is_queued_for_deletion():
				continue
			if not mesh_instance.has_meta("native_equipment"):
				continue
			var skin: Skin = mesh_instance.skin
			if skin == null:
				continue

			actor_mesh_instances += 1
			total_mesh_instances += 1
			var skin_id := skin.get_instance_id()
			unique_skins[skin_id] = true
			if not skin_content_keys.has(skin_id):
				skin_content_keys[skin_id] = _skin_content_key(skin)
			var content_key: String = skin_content_keys[skin_id]
			unique_skin_contents[content_key] = true
			if not actor_skins.has(skin_id):
				actor_skins[skin_id] = true
				actor_deduplicated_bind_count += skin.get_bind_count()
			if actor_skin_contents.has(content_key):
				continue
			actor_skin_contents[content_key] = true
			actor_deduplicated_content_bind_count += skin.get_bind_count()

		total_actor_distinct_skins += actor_skins.size()
		total_actor_deduplicated_bind_count += actor_deduplicated_bind_count
		total_actor_distinct_skin_contents += actor_skin_contents.size()
		total_actor_deduplicated_content_bind_count += actor_deduplicated_content_bind_count
		per_actor.append({
			"actor": actor.name,
			"meshInstances": actor_mesh_instances,
			"distinctSkins": actor_skins.size(),
			"deduplicatedBindCount": actor_deduplicated_bind_count,
			"distinctSkinContents": actor_skin_contents.size(),
			"deduplicatedContentBindCount": actor_deduplicated_content_bind_count,
		})

	return {
		"perActor": per_actor,
		"total": {
			"actors": per_actor.size(),
			"meshInstances": total_mesh_instances,
			"distinctSkins": unique_skins.size(),
			"distinctSkinContents": unique_skin_contents.size(),
			"sumActorDistinctSkins": total_actor_distinct_skins,
			"sumActorDeduplicatedBindCount": total_actor_deduplicated_bind_count,
			"sumActorDistinctSkinContents": total_actor_distinct_skin_contents,
			"sumActorDeduplicatedContentBindCount": total_actor_deduplicated_content_bind_count,
		},
		"skinReferences": {
			"available": false,
			"count": null,
			"note": "Skeleton3D skin_bindings is engine-internal; this census counts Skin resources only.",
		},
	}

## Full, ordered bind content. The hexadecimal form keeps the complete
## var_to_bytes payload as the key: no float formatting, epsilon, or hash-only
## aliasing is involved.
static func _skin_content_key(skin: Skin) -> String:
	var binds: Array = [skin.get_bind_count()]
	for index: int in range(skin.get_bind_count()):
		binds.append([
			skin.get_bind_name(index),
			skin.get_bind_bone(index),
			skin.get_bind_pose(index),
		])
	return var_to_bytes(binds).hex_encode()
