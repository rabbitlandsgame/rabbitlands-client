extends GLTFDocumentExtension

## Marks the placements of shared prototype meshes while a map package parses.
##
## `shared_meshes.py` leaves a placement as a node with its usual name and
## transform, no mesh, and `extras.eloria.prototype` naming the prototype's
## sha. glTF extras do not survive into the generated scene, and the node is
## not a MeshInstance3D anyway, so this extension copies the sha onto the node
## as meta while GLTFDocument builds it; `WorldLoader._resolve_shared_meshes`
## then swaps each marked node for a MeshInstance3D drawing the pooled mesh,
## before any pass that walks the import.
##
## Registration is a no-op after the first, like VramTextures.

const ExternalMeshPool := preload("res://src/world/external_mesh_pool.gd")

const EXTRAS_KEY := "eloria"
const PROTOTYPE_FIELD := "prototype"

static var _registered: GLTFDocumentExtension = null


static func ensure_registered() -> void:
	if _registered != null:
		return
	_registered = new()
	GLTFDocument.register_gltf_document_extension(_registered)


func _import_node(_state: GLTFState, _gltf_node: GLTFNode, json: Dictionary, node: Node) -> Error:
	if node == null:
		return OK
	var extras: Variant = json.get("extras")
	if not extras is Dictionary:
		return OK
	var eloria: Variant = (extras as Dictionary).get(EXTRAS_KEY)
	if not eloria is Dictionary:
		return OK
	var prototype: Variant = (eloria as Dictionary).get(PROTOTYPE_FIELD)
	if prototype is String and not (prototype as String).is_empty():
		node.set_meta(ExternalMeshPool.POOLED_META, prototype)
	return OK
