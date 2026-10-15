class_name MapSceneCache
extends RefCounted

## The built form of a region, kept on the player's own disk.
##
## A map load is a freeze. `WorldLoader` got the worst region from 7.9 s to
## 1.2 s by bucketing wide sibling lists, and what is left is the glTF parse,
## the walk-surface collision and the mip chains - work that produces the same
## tree every time from bytes that do not change between one launch and the
## next. So the first visit to a region packs the tree the loader built into a
## `PackedScene` and writes it under `user://`, and every visit after that
## reads it back instead of parsing the package again.
##
## Nothing here ships in the repository. The cache is built on the machine that
## plays the game, from the package that machine has, and it is keyed on that
## package's own bytes: a client update that changes a map rebuilds its cache
## the first time the map is entered, without anyone having to remember to.
##
## ## The key
##
## `package_digest()` is sha256 over the region's `world.glb` and its
## `world.json`, in that order, wrapped in a version string. The manifest is
## normalised to LF first, because it is a text file that git and Python both
## rewrite the line endings of, and a digest that changed with the checkout
## would be worthless as the cross-check the server sends (see
## `ELORIA_MAP_DIGEST` in `src/network/protocol.gd`). The glb is binary and is
## hashed exactly as it sits.
##
## The cache file name folds `CACHE_FORMAT_VERSION` into that digest, so the
## two ways a cache entry can go stale are the same mechanism: change the
## package and the digest moves, change what the loader builds and the version
## moves. Either way the name the loader looks for is not the name on disk, the
## entry is a miss, and the stale file is removed when the new one lands. The
## failure the doc warned about - a loader change with no version bump, leaving
## a map that is subtly wrong and silent - is a code review away rather than a
## debugging session away, and `format_version_note()` is what a reviewer is
## pointed at.
##
## ## What this is not
##
## It is not a content-distribution mechanism and it is not authoritative. If
## the file is missing, unreadable, truncated or built by another version, the
## loader parses the package exactly as it did before. Every path through here
## degrades to "load it the slow way".

## Bumped whenever `WorldLoader` would build a different tree from the same
## package: a new pass, a changed pass, a different name, a different layer, a
## different piece of metadata. A bump invalidates every entry on every
## player's disk at once, which costs them one slow load per region and is the
## cheap half of the bargain.
##
## 1 - first version: collision bodies, walk surfaces, navigation collision,
##     static batching, mip chains and the batch links as node paths.
## 2 - batches use imported-root coordinates, including detached preloads.
## 5 - continent-owned scenery uses shared-cell grouping and hidden thresholds.
## 6 - shared-continent chunks, external textures and opaque vertex colours.
## 7 - shared elevated/sloping drainage uses the common continent water shader.
##
## VRAM-compressed sidecar textures did not bump it: they change the tree only
## for a package with external images, and such a package folds
## VramTextures.cache_token into its key (`cache_path`), so its entries are
## already apart from the ones a client without sidecars wrote, in both
## directions. Every other package builds exactly as before and keeps its
## entry. (Live continent chunks are detached builds, which read the cache but
## never write it, so this reaches whole-map loads today.)
const CACHE_FORMAT_VERSION := 7

## Wrapped into the digest so the hash of a package cannot be confused with the
## hash of anything else, and so the digest itself can be revised without
## colliding with the values a previous client wrote. This string is part of
## the contract with the server: `eloria-assets/tools/sync_package_content.py`
## computes the same digest the same way.
const PACKAGE_DIGEST_VERSION := "eloria-map-package-v1"

const CACHE_DIRECTORY := "user://map-cache"
const CACHE_EXTENSION := ".scn"

## An entry is written under this prefix and renamed into place, so a write
## that does not finish - the player quits, the disk fills - cannot leave half
## a region behind for the next launch to read as a whole one. The name still
## ends in `.scn`, because `ResourceSaver` chooses its format from the
## extension and refuses to write a file it does not recognise.
const STAGING_PREFIX := "writing-"

## How much of the key goes in the file name. 16 hex characters is 64 bits;
## the whole digest is kept inside the file's own metadata, so this only has to
## be long enough that two packages of the same map do not collide by accident,
## and short enough to leave a readable name.
const KEY_CHARACTERS := 16

## Where the setting lives, beside every other client setting.
const SETTINGS_PATH := "user://eloria_hud.cfg"
const SETTINGS_SECTION := "graphics"
const SETTINGS_KEY := "map_cache"

## Turns the cache off for a run without touching the setting: `--no-map-cache`
## on the command line, or `ELORIA_NO_MAP_CACHE=1` in the environment. Fixtures
## that must measure or compare a genuinely fresh load use these rather than
## writing to the player's config file.
const DISABLE_ARGUMENT := "--no-map-cache"
const DISABLE_ENVIRONMENT := "ELORIA_NO_MAP_CACHE"

## Read once. The setting is a checkbox in a window that is not open during a
## map load, and re-reading a ConfigFile on the load path would be a file open
## per map change for a value that changes when a player clicks it.
static var _enabled_cache: Variant = null

## The digest the server said it built this map against, per map id, and
## whatever the client computed for the same map. Filled by the map-digest
## packet and by the loader; read by the settings window so a mismatch is
## visible somewhere other than the console.
static var _server_digests: Dictionary = {}
static var _local_digests: Dictionary = {}
static var _mismatches: Dictionary = {}

## Where a mismatch is announced, beyond the log. The two halves of the
## comparison arrive in either order - the server's digest can land before the
## map has finished hashing, or long after - so whichever completes the pair
## is the one that has to speak. A sink rather than a signal because this class
## is a bag of statics with no instance to connect to, and installed by
## `AppState` rather than reached for, so the world layer does not have to know
## the interface layer exists.
static var _mismatch_sink: Callable = Callable()

static func set_mismatch_sink(sink: Callable) -> void:
	_mismatch_sink = sink

# --------------------------------------------------------------------------
# The key
# --------------------------------------------------------------------------

## sha256 over the package's own bytes: the glb as it sits, then the manifest
## with its line endings normalised, wrapped in `PACKAGE_DIGEST_VERSION`.
##
## Returns "" when either file cannot be read, which every caller treats as
## "no cache and no cross-check" rather than as an error: a package that cannot
## be hashed is a package that is about to fail to load anyway, and the loader
## should be the one to say so.
static func package_digest(manifest_path: String, glb_path: String) -> String:
	var glb_hash: String = FileAccess.get_sha256(glb_path)
	if glb_hash.is_empty():
		return ""
	var manifest_hash: String = _normalised_sha256(manifest_path)
	if manifest_hash.is_empty():
		return ""
	return _sha256_text("%s\n%s\n%s\n" % [
		PACKAGE_DIGEST_VERSION, glb_hash, manifest_hash])

## The manifest hashed with CRLF folded to LF.
##
## `world.json` is written by Python on Windows and read back through git, so
## the same package is CRLF in one checkout and LF in another. The bytes differ
## and the map does not, so hashing them raw would make the server's digest
## disagree with the client's for a reason that has nothing to do with the
## content. The server's own catalog digests already normalise the same way.
static func _normalised_sha256(path: String) -> String:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return ""
	var raw: PackedByteArray = file.get_buffer(file.get_length())
	file.close()
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(_strip_carriage_returns(raw))
	return context.finish().hex_encode()

## CRLF to LF over a byte buffer. A lone CR is left alone: it is not a line
## ending any of these writers produces, and dropping it would fold two
## different files onto one hash.
static func _strip_carriage_returns(raw: PackedByteArray) -> PackedByteArray:
	var out := PackedByteArray()
	var size: int = raw.size()
	out.resize(size)
	var written: int = 0
	for index: int in size:
		var byte: int = raw[index]
		if byte == 13 and index + 1 < size and raw[index + 1] == 10:
			continue
		out[written] = byte
		written += 1
	out.resize(written)
	return out

static func _sha256_text(text: String) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(text.to_utf8_buffer())
	return context.finish().hex_encode()

## The file name a package's digest maps to under the current format version.
##
## `token` is what else decides the tree the loader builds from the same
## bytes: VramTextures.cache_token, which names the texture formats a package
## with external images was built with (sidecars on or off, which formats the
## renderer samples, which index). A cache keeps the textures it was packed
## with, so an entry built from decoded images must not be read once sidecars
## apply, nor the reverse. Empty for every other package, whose key it leaves
## as it was.
static func cache_key(digest: String, token := "") -> String:
	return cache_key_for(digest, CACHE_FORMAT_VERSION, token)

## The same, under a stated format version. Split out so a test can ask what
## the next version's key would be and prove that a bump misses every entry on
## disk rather than reading one the previous loader wrote.
static func cache_key_for(digest: String, version: int, token := "") -> String:
	if digest.is_empty():
		return ""
	if token.is_empty():
		return _sha256_text("%s\n%d\n" % [digest, version]).substr(0, KEY_CHARACTERS)
	return _sha256_text("%s\n%d\n%s\n" % [digest, version, token]).substr(0, KEY_CHARACTERS)

static func cache_path(map_id: String, digest: String, token := "") -> String:
	var key: String = cache_key(digest, token)
	if key.is_empty():
		return ""
	return "%s/%s-%s%s" % [
		CACHE_DIRECTORY, _safe_name(map_id), key, CACHE_EXTENSION]

## A map id reduced to something a file system will take. Every shipped asset
## id is already lower-case ASCII with underscores; this is a guard rather than
## a transformation, and it is deliberately not reversible - the digest, not
## the name, is what identifies an entry.
static func _safe_name(map_id: String) -> String:
	var out := ""
	for index: int in map_id.length():
		var character: String = map_id[index]
		if character.is_valid_identifier() or character.is_valid_int() \
				or character == "-" or character == "_":
			out += character
		else:
			out += "_"
	if out.is_empty():
		out = "map"
	return out.to_lower()

## What a reviewer is pointed at from `CACHE_FORMAT_VERSION`. Kept as a
## function rather than a comment so a test can assert the two agree.
static func format_version_note() -> String:
	return ("A change to what WorldLoader builds needs CACHE_FORMAT_VERSION "
		+ "raised, or players keep the tree the previous version built.")

# --------------------------------------------------------------------------
# The setting
# --------------------------------------------------------------------------

static func is_enabled() -> bool:
	if OS.get_environment(DISABLE_ENVIRONMENT).strip_edges() not in ["", "0"]:
		return false
	if DISABLE_ARGUMENT in OS.get_cmdline_args():
		return false
	if DISABLE_ARGUMENT in OS.get_cmdline_user_args():
		return false
	if _enabled_cache == null:
		var config := ConfigFile.new()
		var stored: Variant = true
		if config.load(SETTINGS_PATH) == OK:
			stored = config.get_value(SETTINGS_SECTION, SETTINGS_KEY, true)
		_enabled_cache = bool(stored)
	return bool(_enabled_cache)

static func set_enabled(enabled: bool) -> void:
	_enabled_cache = enabled
	var config := ConfigFile.new()
	config.load(SETTINGS_PATH)
	config.set_value(SETTINGS_SECTION, SETTINGS_KEY, enabled)
	var error: Error = config.save(SETTINGS_PATH)
	if error != OK:
		push_warning("map cache: could not save the setting (%s)" % error_string(error))

## Drops the remembered setting so the next `is_enabled()` reads the file
## again. For tests, and for anything that writes the config behind this class.
static func forget_setting() -> void:
	_enabled_cache = null

# --------------------------------------------------------------------------
# The directory
# --------------------------------------------------------------------------

static func ensure_directory() -> bool:
	if DirAccess.dir_exists_absolute(CACHE_DIRECTORY):
		return true
	var error: Error = DirAccess.make_dir_recursive_absolute(CACHE_DIRECTORY)
	if error != OK:
		push_warning("map cache: could not create %s (%s)" % [
			CACHE_DIRECTORY, error_string(error)])
		return false
	return true

## Where an entry is written before it is renamed into place.
static func staging_path(path: String) -> String:
	return "%s/%s%s" % [path.get_base_dir(), STAGING_PREFIX, path.get_file()]

## Every finished cache entry on disk. A write still in flight is not one: it
## is not readable yet, and counting it would make the settings row jump while
## a region is being packed.
static func entries() -> PackedStringArray:
	return _files(false)

static func _files(include_staging: bool) -> PackedStringArray:
	var out := PackedStringArray()
	var directory := DirAccess.open(CACHE_DIRECTORY)
	if directory == null:
		return out
	for name: String in directory.get_files():
		if not name.ends_with(CACHE_EXTENSION):
			continue
		if not include_staging and name.begins_with(STAGING_PREFIX):
			continue
		out.append(CACHE_DIRECTORY + "/" + name)
	return out

## Total bytes the cache occupies, for the settings row.
static func total_bytes() -> int:
	var total: int = 0
	for path: String in entries():
		var file := FileAccess.open(path, FileAccess.READ)
		if file == null:
			continue
		total += file.get_length()
		file.close()
	return total

## Removes every entry, including anything a previous run left half written.
## Returns how many files went.
static func clear_disk() -> int:
	var removed: int = 0
	for path: String in _files(true):
		if DirAccess.remove_absolute(path) == OK:
			removed += 1
	return removed

## Removes the entries for `map_id` that are not `keep`. A package that changes
## would otherwise leave its previous build on disk for good, and twelve
## regions at 30-40 MB each is not a leak anyone would notice until the disk
## was full.
static func prune(map_id: String, keep: String) -> int:
	var prefix: String = _safe_name(map_id) + "-"
	var removed: int = 0
	for path: String in entries():
		if path == keep or not path.get_file().begins_with(prefix):
			continue
		if DirAccess.remove_absolute(path) == OK:
			removed += 1
	return removed

## A size for the settings row: "48.2 MB", "312 KB", "empty".
static func describe_size(bytes: int) -> String:
	if bytes <= 0:
		return "empty"
	if bytes < 1024:
		return "%d B" % bytes
	if bytes < 1048576:
		return "%.0f KB" % (float(bytes) / 1024.0)
	return "%.1f MB" % (float(bytes) / 1048576.0)

# --------------------------------------------------------------------------
# The digests the server sends
# --------------------------------------------------------------------------

## What the server says it was built against. The client never acts on this:
## the cache is keyed on the package the player actually has, so a mismatch
## cannot make the cache wrong. It means the install disagrees with the server,
## which is worth saying out loud once rather than discovering as a door that
## does not open.
static func note_server_digest(map_id: String, digest: String) -> void:
	var key: String = map_id.strip_edges().to_lower()
	if key.is_empty():
		return
	_server_digests[key] = digest
	_compare(key)

static func note_local_digest(map_id: String, digest: String) -> void:
	var key: String = map_id.strip_edges().to_lower()
	if key.is_empty():
		return
	_local_digests[key] = digest
	_compare(key)

static func _compare(key: String) -> void:
	if not _server_digests.has(key) or not _local_digests.has(key):
		return
	var server: String = str(_server_digests[key])
	var local: String = str(_local_digests[key])
	if server.is_empty() or local.is_empty() or server == local:
		_mismatches.erase(key)
		return
	if _mismatches.has(key):
		return
	_mismatches[key] = [server, local]
	var line: String = ("map_digest stage=mismatch map=%s server=%s client=%s"
		+ " note=the installed package is not the one the server expects") % [
		key, server, local]
	push_warning(line)
	print(line)
	if _mismatch_sink.is_valid():
		_mismatch_sink.call(key, server, local)

static func has_mismatch(map_id: String) -> bool:
	return _mismatches.has(map_id.strip_edges().to_lower())

static func mismatched_maps() -> Array:
	var out: Array = _mismatches.keys()
	out.sort()
	return out

## What the settings row says about the cross-check.
static func digest_summary() -> String:
	if _mismatches.is_empty():
		return "" if _server_digests.is_empty() else "matches the server"
	return "does not match the server: " + ", ".join(mismatched_maps())

static func forget_digests() -> void:
	_server_digests.clear()
	_local_digests.clear()
	_mismatches.clear()
