extends SceneTree

## The shared texture pool must never hold its mutex across a rendering-server
## round trip: a worker importing a neighbour chunk while the main thread primed
## the arrival chunk froze the live client (worker inside set_image under the
## lock, main thread waiting for the lock and no longer serving the renderer).
## Publication is now publish-or-adopt, and concurrent sharers converge on one
## texture per content hash.
const ExternalTexturePool := preload("res://src/world/external_texture_pool.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func _texture(color: Color) -> ImageTexture:
	var image := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	image.fill(color)
	return ImageTexture.create_from_image(image)

func _state(uri: String, texture: ImageTexture) -> GLTFState:
	var state := GLTFState.new()
	state.set_json({"images": [{"uri": uri}]})
	var images: Array[Texture2D] = [texture]
	state.set_images(images)
	return state

func _share(uri: String, key: String, texture: ImageTexture) -> Variant:
	return ExternalTexturePool.share(_state(uri, texture), {uri: key})

func _run() -> void:
	await process_frame
	var key := "content-hash-" + str(Time.get_ticks_usec())
	# 1. The first sharer publishes; a later sharer with the same hash adopts.
	var first := _texture(Color.RED)
	_expect(_share("a.png", key, first) == 0, "first sharer publishes its own texture")
	var second_state := _state("b.png", _texture(Color.BLUE))
	_expect(ExternalTexturePool.share(second_state, {"b.png": key}) == 1, "second sharer adopts the published texture")
	_expect(second_state.get_images()[0] == first, "the adopted image is the first sharer's texture")
	_expect(first.get_image().has_mipmaps(), "the published texture carries a finished mip chain")
	# 2. Concurrent sharers of one new hash converge on a single texture.
	var key2 := key + "-parallel"
	var results: Array = []
	var threads: Array[Thread] = []
	for index: int in range(6):
		var thread := Thread.new()
		var texture := _texture(Color(0.1 * index, 0.2, 0.3))
		var state := _state("p%d.png" % index, texture)
		results.append(state)
		_expect(thread.start(ExternalTexturePool.share.bind(state, {"p%d.png" % index: key2})) == OK, "parallel sharer %d started" % index)
		threads.append(thread)
	var deadline := Time.get_ticks_msec() + 5000
	while threads.any(func(t: Thread) -> bool: return t.is_alive()) and Time.get_ticks_msec() < deadline:
		await process_frame
	_expect(not threads.any(func(t: Thread) -> bool: return t.is_alive()), "parallel sharers finished without blocking the main thread")
	var reused := 0
	for thread: Thread in threads:
		reused += int(thread.wait_to_finish())
	var distinct: Dictionary = {}
	for state: GLTFState in results:
		distinct[state.get_images()[0].get_instance_id()] = true
	_expect(distinct.size() == 1, "six parallel sharers of one hash converge on one texture (%d distinct)" % distinct.size())
	_expect(reused == 5, "exactly one sharer published and five adopted (%d adopted)" % reused)
	print("external texture pool test: %d failures" % failures)
	quit(1 if failures > 0 else 0)
