extends RefCounted
## Which family the running renderer belongs to, for the code that has to tell
## Godot's three rendering methods apart:
##
## - `forward_plus` (Forward+) and `mobile` (Mobile) are the RenderingDevice
##   renderers. Both light in linear space and share one mesh, texture and
##   material storage, so they take the same colour trims (LookProfile's
##   `_FORWARD` constants and a region file's `_forward` keys) and the same
##   prepared-world and cache keys (`cache_renderer`).
## - `gl_compatibility` (OpenGL: the engine's fallback, the compatibility and
##   safe-mode launchers) lights display-encoded (sRGB) colour, so it keeps its
##   own trims (`_compat`) and its own caches.
##
## Only Forward+ has SSAO and SSIL (`screen_space_effects`). Forward+ clusters
## its lights; Mobile and Compatibility light at most 8 omni and 8 spot lights
## per mesh instance (`per_mesh_light_limit`; Mobile's MAX_RDL_CULL) and drop
## the rest in cull order.
##
## No class_name: callers preload this file, so tools and the loader's worker
## threads need no global class cache. Safe on worker threads: the engine is
## asked once and its answer kept as an index (an int, never a shared String
## written twice), and the rendering method never changes while the client
## runs. A headless run reports the project's method (`forward_plus`) unless the
## command line names another (`--rendering-method mobile`), so tests take the
## Mobile and Compatibility paths through `override_for_tests`.
##
## Godot can run Mobile while reporting `forward_plus` (an RD device with fewer
## than 48 textures per shader stage). Such a GPU still gets the linear trims;
## it asks for SSAO and SSIL, which the engine ignores with a warning.

const FORWARD_PLUS := "forward_plus"
const MOBILE := "mobile"
const COMPATIBILITY := "gl_compatibility"
## The RenderingDevice methods: linear lighting, one content storage.
const RD_METHODS: Array[String] = [FORWARD_PLUS, MOBILE]
## Lights of one kind (omni, spot) that light one mesh instance in Mobile and
## Compatibility; Forward+ has no such limit (0 from `per_mesh_light_limit`).
const PER_MESH_LIGHT_LIMIT := 8

const _METHODS: Array[String] = [FORWARD_PLUS, MOBILE, COMPATIBILITY]

## The engine's method as an index into _METHODS once asked; -1 not yet.
static var _engine := -1
## `override_for_tests`'s method as an index into _METHODS; -1 for none.
static var _override := -1
## `linear_lighting()`'s answer for the method in use: -1 not yet asked, 0 no,
## 1 yes. The look asks it for every trim it reads, on the loader's worker
## threads too, so it costs one comparison once asked.
static var _linear := -1

## The rendering method in use: `forward_plus`, `mobile` or `gl_compatibility`
## (RenderingServer.get_current_rendering_method, asked once), or the one a
## test set with `override_for_tests`.
static func method() -> String:
	if _override >= 0:
		return _METHODS[_override]
	if _engine < 0:
		var reported := RenderingServer.get_current_rendering_method()
		var index := _METHODS.find(reported)
		if index < 0:
			# Not one of the three (Godot 4.7 has no other): answered as
			# reported and not kept. The helpers below then answer as for no
			# family: not linear, no screen-space effects, no light limit.
			return reported
		_engine = index
	return _METHODS[_engine]

## Makes `method` answer `value` (one of the three methods) until called again
## with "", which restores the engine's answer. For tests only: the client's
## renderer is fixed at start, and code that asked before keeps its answer.
static func override_for_tests(value: String) -> void:
	_linear = -1
	if value.is_empty():
		_override = -1
		return
	var index := _METHODS.find(value)
	if index < 0:
		push_error("RendererFamily: unknown rendering method \"%s\"" % value)
		return
	_override = index

# Each helper below answers for the method it is given, or, given none (""),
# for the method in use (`method`).

## True for the renderers that light in linear space, Forward+ and Mobile; the
## compatibility renderer lights display-encoded colour.
static func linear_lighting(rendering_method := "") -> bool:
	if rendering_method.is_empty():
		if _linear < 0:
			var current := method()
			_linear = 1 if current == FORWARD_PLUS or current == MOBILE else 0
		return _linear == 1
	return rendering_method == FORWARD_PLUS or rendering_method == MOBILE

## True when the renderer has SSAO and SSIL: Forward+ only. Mobile and the
## compatibility renderer ignore those settings with a warning.
static func screen_space_effects(rendering_method := "") -> bool:
	return _or_current(rendering_method) == FORWARD_PLUS

## The most omni (and, separately, spot) lights that light one mesh instance:
## PER_MESH_LIGHT_LIMIT in Mobile and Compatibility, 0 (no limit: clustered) in
## Forward+.
static func per_mesh_light_limit(rendering_method := "") -> int:
	var named := _or_current(rendering_method)
	return PER_MESH_LIGHT_LIMIT if named == MOBILE or named == COMPATIBILITY else 0

## The renderer name a prepared-world or content cache is keyed by:
## `forward_plus` for both RenderingDevice methods, which share mesh, texture
## and material storage (so Mobile reads Forward+'s prepared world), else the
## method itself.
static func cache_renderer(rendering_method := "") -> String:
	var named := _or_current(rendering_method)
	return FORWARD_PLUS if named == FORWARD_PLUS or named == MOBILE else named

static func _or_current(rendering_method: String) -> String:
	return method() if rendering_method.is_empty() else rendering_method
