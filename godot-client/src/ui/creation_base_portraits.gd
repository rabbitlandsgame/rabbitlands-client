class_name CreationBasePortraits
extends RefCounted
## Offline-baked starting-look images only. No viewport, actor or render queue.
## A missing/stale image leaves the card's static placeholder visible.

const MANIFEST_PATH := "res://data/ui/creation_base_portraits.json"
const IMAGE_EXTENSIONS := ["png", "webp", "jpg", "jpeg"]
var _manifest_path := ""
var _entries: Dictionary = {}
var _textures: Dictionary = {}


## Share this canonical fingerprint with the offline baker. Appearance protocol
## variants can reuse an image only when their complete look dictionaries match.
static func look_hash(look: Dictionary) -> String:
	return JSON.stringify(look, "", true).sha256_text()


func configure(manifest_path: String = MANIFEST_PATH) -> void:
	if _manifest_path == manifest_path:
		return
	_manifest_path = manifest_path
	_entries.clear()
	_textures.clear()
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path)) \
		if FileAccess.file_exists(manifest_path) else null
	if parsed is Dictionary and int(parsed.get("schema_version", 0)) == 1 \
			and parsed.get("portraits") is Dictionary:
		_entries = (parsed.portraits as Dictionary).duplicate(true)


## Resolve by stable catalog ID and exact look, including protocol variants.
func texture_path(id: String, look: Dictionary) -> String:
	var value: Variant = _entries.get(id)
	if value is not Dictionary:
		return ""
	var entry: Dictionary = value
	var candidates: Array = [entry]
	if entry.get("variants") is Array:
		candidates.append_array(entry.variants)
	var fingerprint := look_hash(look)
	for candidate: Variant in candidates:
		if candidate is not Dictionary or str(candidate.get("look_sha256", "")) != fingerprint:
			continue
		var path := str(candidate.get("texture", ""))
		# Only static image resources qualify, even if a malformed manifest names
		# a scene or another kind of Texture2D resource.
		if path.begins_with("res://") and path.get_extension().to_lower() in IMAGE_EXTENSIONS:
			return path
	return ""


func texture(id: String, look: Dictionary) -> Texture2D:
	var path := texture_path(id, look)
	if path.is_empty():
		return null
	if _textures.has(path):
		return _textures[path] as Texture2D
	if not ResourceLoader.exists(path, "Texture2D"):
		return null
	var resource := load(path)
	if resource is not Texture2D:
		return null
	_textures[path] = resource
	return resource as Texture2D
