extends SceneTree
const Release = preload("res://src/updates/release.gd")
func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1:
		quit(1)
		return
	var request := Release.read_json(args[0])
	if not request.has("manifest") or not request.has("identity"):
		quit(1)
		return
	var result := Release.verify_manifest(Release.read_json(request.manifest), request.identity, request.identity.commit)
	if result.has("error"):
		push_error(result.error)
		quit(1)
		return
	quit()
