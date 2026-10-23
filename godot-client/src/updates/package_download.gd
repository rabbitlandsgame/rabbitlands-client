extends RefCounted
const Release = preload("res://src/updates/release.gd")
const Packages = preload("res://src/updates/package_updates.gd")

static func prepare(root: String, release: Dictionary, fetch: Callable, worker: Callable, progress := Callable(), cancelled := Callable()) -> String:
	var cache := Release.cache_for(root)
	if Release.is_link(cache) or Release.is_link(cache.path_join("packages")) or DirAccess.make_dir_recursive_absolute(cache.path_join("packages")) != OK:
		return "The package cache is not writable."
	Release.report_progress(progress, "Checking installed packages", 0, 1)
	var needed: Variant = await worker.call(func() -> Array: return Packages.plan(root, release))
	if not needed is Array:
		return "The package verification could not start."
	var total := 0
	var completed := 0
	for package: Dictionary in needed:
		if Release.is_link(Packages.package_path(cache, package)) or Release.is_link(Packages.package_path(cache, package) + ".tmp"):
			return "The package cache files must not be links."
		total += int(package.size)
	for package: Dictionary in needed:
		if cancelled.is_valid() and cancelled.call():
			return "Update cancelled."
		var ready: Variant = await worker.call(func() -> bool: return Release.check_file(Packages.package_path(cache, package), int(package.size), package.sha256))
		if ready != true:
			for part: Dictionary in package.parts:
				Release.report_progress(progress, "Downloading changed packages", completed, total, package.id)
				var path := cache.path_join("packages/" + part.sha256 + ".part")
				if Release.is_link(path) or Release.is_link(path + ".tmp"):
					return "The package cache files must not be links."
				var valid: Variant = await worker.call(func() -> bool: return Release.check_file(path, int(part.size), part.sha256))
				if valid != true:
					var result: Dictionary = await fetch.call(part.url, path + ".tmp", int(part.size))
					if cancelled.is_valid() and cancelled.call():
						return "Update cancelled."
					if result.has("error"):
						return result.error
					valid = await worker.call(func() -> bool: return Release.check_file(path + ".tmp", int(part.size), part.sha256))
					if valid != true or DirAccess.rename_absolute(path + ".tmp", path) != OK:
						return "A downloaded package failed verification."
				completed += int(part.size)
			var error: String = await worker.call(func() -> String: return Packages.assemble(cache, package))
			if error != "":
				return error
		else:
			completed += int(package.size)
	Release.report_progress(progress, "Changed packages ready", 1, 1, "%d of %d packages needed downloads" % [needed.size(), release.packages.size()])
	return ""
