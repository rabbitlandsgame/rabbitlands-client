extends SceneTree
## Root-only two-process Godot -> Python -> Godot float-wire regression.
const Prepared := preload("res://src/world/prepared_content.gd")

func _initialize() -> void:
	_run.call_deferred()

func _sha(value: String) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(value.to_utf8_buffer())
	return context.finish().hex_encode()

func _run() -> void:
	var arguments := OS.get_cmdline_user_args()
	if arguments.size() != 2 or not arguments[0] in ["emit", "verify"]:
		push_error("expected -- emit|verify <owned scratch JSON path>")
		quit(1)
		return
	if arguments[0] == "emit":
		# Exact dyadic values from the luminous body/cape drift. Godot's full
		# precision serializer and Python choose different final decimal digits.
		var metadata := {"rigs": [{"rest_affine12": [
			-0.172595977783203125, 0.172595977783203125, 2.98023223876953125e-08]}]}
		var entry := {"kind": "scene", "source": "fixture/body.glb",
			"engine_policy": Prepared.engine_policy(), "metadata_json": Prepared.encode_metadata(metadata)}
		entry["entry_id"] = Prepared.entry_identity(entry)
		var document := {"entry": entry, "expected_id": entry.entry_id,
			"metadata_sha256": _sha(str(entry.metadata_json))}
		var output := FileAccess.open(arguments[1], FileAccess.WRITE)
		if output == null:
			push_error("cannot write owned metadata roundtrip fixture")
			quit(1)
			return
		output.store_string(JSON.stringify(document, "", true, true))
		output.close()
		print("prepared metadata wire emitted")
		quit(0)
		return
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(arguments[1])) != OK or not parser.data is Dictionary:
		push_error("invalid metadata roundtrip fixture")
		quit(1)
		return
	var document: Dictionary = parser.data
	var entry: Dictionary = document.entry
	var metadata: Variant = JSON.parse_string(str(entry.metadata_json))
	if entry.has("metadata") or not metadata is Dictionary \
			or Prepared.entry_identity(entry) != str(document.expected_id) \
			or _sha(str(entry.metadata_json)) != str(document.metadata_sha256):
		push_error("Godot/Python/Godot changed exact authoritative metadata or entry identity")
		quit(1)
		return
	entry["metadata"] = metadata
	if Prepared.entry_identity(entry) != str(document.expected_id):
		push_error("decoded returned-entry alias changed authoritative identity")
		quit(1)
		return
	(metadata as Dictionary)["unexpected_mutation"] = true
	if not Prepared.entry_identity(entry).is_empty():
		push_error("mutated decoded metadata alias retained an entry identity")
		quit(1)
		return
	print("prepared metadata Godot/Python/Godot wire: PASS")
	quit(0)
