extends RefCounted
## Short-lived render membership for a real speaker in a shared World3D.
## Bits 12-19 are reserved here; layer 20 belongs to world labels. Each live
## dialogue leases its own bit, so simultaneous portraits remain isolated.
## While bound, the speaker also holds its portrait pose (ReplicatedActor3D
## hold_portrait_pose): an RL head keeps its first level of detail, a neutral
## face and open eyes however far the gameplay camera is.
const MASKS := [1 << 18, 1 << 17, 1 << 16, 1 << 15, 1 << 14, 1 << 13, 1 << 12, 1 << 11]
static var _leases: Dictionary = {}
var mask := 0
var _actor: WeakRef
var _meshes: Dictionary = {}

func bind(actor: Node3D) -> int:
	var previous := _actor.get_ref() as Node3D if _actor != null else null
	if previous != actor or not is_instance_valid(actor):
		clear()
		if not is_instance_valid(actor): return 0
		for candidate: int in MASKS:
			var lease: WeakRef = _leases.get(candidate)
			if lease == null or not is_instance_valid(lease.get_ref()):
				mask = candidate
				_leases[mask] = weakref(self)
				_actor = weakref(actor)
				if actor.has_method("hold_portrait_pose"):
					actor.call("hold_portrait_pose", self)
				break
	refresh()
	return mask

func refresh() -> void:
	var actor := _actor.get_ref() as Node3D if _actor != null else null
	if not is_instance_valid(actor):
		clear()
		return
	# Only the actor's actual native mesh layer joins the portrait. Nameplates,
	# map dots, range stand-ins, and gameplay-only silhouettes never join it.
	for key: int in _meshes.keys():
		var node := (_meshes[key].node as WeakRef).get_ref() as MeshInstance3D
		if not is_instance_valid(node):
			_meshes.erase(key)
		elif not actor.is_ancestor_of(node) or (node.layers & 1) == 0:
			_restore(node, _meshes[key])
			_meshes.erase(key)
	for node: MeshInstance3D in actor.find_children("*", "MeshInstance3D", true, false):
		if (node.layers & 1) == 0: continue
		var key := node.get_instance_id()
		if not _meshes.has(key):
			_meshes[key] = {"node": weakref(node), "already_set": (node.layers & mask) != 0}
		node.layers |= mask

func _restore(node: MeshInstance3D, entry: Dictionary) -> void:
	# Remove just our membership. Another system may have legitimately changed
	# gameplay layers while this line was on screen; retain those changes.
	if not bool(entry.already_set): node.layers &= ~mask

func clear() -> void:
	var bound := _actor.get_ref() as Node3D if _actor != null else null
	if is_instance_valid(bound) and bound.has_method("release_portrait_pose"):
		bound.call("release_portrait_pose", self)
	for entry: Dictionary in _meshes.values():
		var node := (entry.node as WeakRef).get_ref() as MeshInstance3D
		if is_instance_valid(node): _restore(node, entry)
	_meshes.clear()
	if mask != 0:
		var lease: WeakRef = _leases.get(mask)
		if lease != null and lease.get_ref() == self: _leases.erase(mask)
	mask = 0
	_actor = null
