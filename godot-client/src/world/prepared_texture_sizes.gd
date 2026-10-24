extends RefCounted
## ImageTexture binary storage omits set_size_override. A compressed readback
## can be block padded; logical dimensions therefore travel as verified data.
## No image readback, resize, decode, recompress, Node or retained cache.
const LOGICAL_SIZE := &"rl_prepared_texture_logical_size"
const PUBLISHED_SIZE := &"rl_prepared_texture_published_size"
static var _mutex := Mutex.new()

## Offline producer, after conversion/duplication. Logical size comes from the
## actual source Texture2D, never the padded Image returned by get_image().
static func prepare(source: Texture2D, candidate: ImageTexture) -> bool:
	if source == null or candidate == null:
		return false
	var size := Vector2i(source.get_width(), source.get_height())
	if size.x <= 0 or size.y <= 0:
		return false
	if candidate.has_meta(PUBLISHED_SIZE):
		candidate.remove_meta(PUBLISHED_SIZE)
	candidate.set_meta(LOGICAL_SIZE, size)
	candidate.set_size_override(size)
	return true

## Only after acquire has verified all native payload bytes. The dedicated
## lock serializes first publication of a shared ResourceLoader cache object.
## set_size_override emits no changed signal and its rendering call is a void
## queued setter; this never waits for GPU readback/main-thread servicing.
static func restore_verified(texture: ImageTexture) -> bool:
	if texture == null or texture.get_script() != null:
		return false
	_mutex.lock()
	if not texture.has_meta(LOGICAL_SIZE):
		_mutex.unlock()
		return false
	var declared: Variant = texture.get_meta(LOGICAL_SIZE)
	if not declared is Vector2i or declared.x <= 0 or declared.y <= 0:
		_mutex.unlock()
		return false
	var size: Vector2i = declared
	if texture.has_meta(PUBLISHED_SIZE):
		# An active shared resource is immutable. Reject a later mutation rather
		# than silently rewriting a texture that another scene can be using.
		var valid: bool = texture.get_meta(PUBLISHED_SIZE) == size \
			and texture.get_width() == size.x and texture.get_height() == size.y
		_mutex.unlock()
		return valid
	if texture.get_width() != size.x or texture.get_height() != size.y:
		texture.set_size_override(size)
	texture.set_meta(PUBLISHED_SIZE, size)
	_mutex.unlock()
	return true
