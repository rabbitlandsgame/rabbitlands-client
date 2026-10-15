extends SceneTree
## Build machine only. Private keys never enter the client or release assets.
func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() == 3 and args[0] == "generate":
		if FileAccess.file_exists(args[1]) or FileAccess.file_exists(args[2]):
			push_error("Refusing to overwrite an existing signing key.")
			quit(1)
			return
		var key := Crypto.new().generate_rsa(4096)
		quit(0 if key.save(args[1]) == OK and key.save(args[2], true) == OK else 1)
		return
	if args.size() != 4 or args[0] != "sign":
		push_error("Usage: generate private.pem public.pem | sign private.pem payload.json output.json")
		quit(1)
		return
	var key := CryptoKey.new()
	if key.load(args[1]) != OK:
		quit(1)
		return
	var payload := FileAccess.get_file_as_bytes(args[2])
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(payload)
	var signature := Crypto.new().sign(HashingContext.HASH_SHA256, hash.finish(), key)
	var file := FileAccess.open(args[3], FileAccess.WRITE)
	if file == null or signature.is_empty():
		quit(1)
		return
	file.store_string(JSON.stringify({"payload": Marshalls.raw_to_base64(payload), "signature": Marshalls.raw_to_base64(signature)}))
	file.close()
	quit()
