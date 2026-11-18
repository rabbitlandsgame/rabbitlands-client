extends RefCounted
## Explicit recovery shortcuts for the current encounter's fallen allies.
## The buttons use ordinary Heal Target; snapshots never grant healing proof.

static func patients(snapshot: Dictionary, current_map: String) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if not bool(snapshot.get("active", false)) \
			or str(snapshot.get("run_id", "")).is_empty() or not (snapshot.get("travel", {}) as Dictionary).is_empty() \
			or EloriaProtocol.map_id_from_reference(str(snapshot.get("map", ""))) \
			!= EloriaProtocol.map_id_from_reference(current_map):
		return result
	match str(snapshot.get("kind", "")):
		"shelves":
			var ledger: Dictionary = snapshot.get("shelves", {})
			if str(ledger.get("phase", "")) != "work": return result
			for field: String in ["growers", "fire", "water"]:
				for worker: Dictionary in (ledger.get(field, {}) as Dictionary).get("workers", []):
					var actor_id := int(worker.get("actor_id", 0))
					if actor_id > 0 and bool(worker.get("downed", false)) \
							and not result.any(func(row: Dictionary) -> bool: return int(row.actor_id) == actor_id):
						result.append({"actor_id": actor_id, "name": str(worker.get("name", "Worker"))})
		"rescue":
			var rescue: Dictionary = snapshot.get("rescue", {})
			var mother: Dictionary = rescue.get("mother", {})
			var actor_id := int((snapshot.get("actors", {}) as Dictionary).get("mother", 0))
			# The unnamed road patient retains her existing first-lesson action.
			var stage := str(rescue.get("stage", ""))
			var mine_patient := stage == "injured" and EloriaProtocol.map_id_from_reference(current_map) == "landfall_insides"
			if actor_id > 0 and (stage in ["mine", "boss_confrontation", "boss_defeated"] or mine_patient) \
					and bool(mother.get("configured", false)) \
					and bool(mother.get("downed", false)):
				var patient: Dictionary = rescue.get("patient", {})
				result.append({"actor_id": actor_id, "name": "Elen Reed", "assisted":
					int(patient.get("actor_id", 0)) == actor_id and int(patient.get("lesson_remaining", 0)) > 0})
	return result

static func contains(snapshot: Dictionary, current_map: String, actor_id: int) -> bool:
	return patients(snapshot, current_map).any(func(row: Dictionary) -> bool: return int(row.actor_id) == actor_id)
