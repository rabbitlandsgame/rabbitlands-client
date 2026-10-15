extends SceneTree
func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var key := CryptoKey.new()
	if key.load(args[0]) != OK:
		quit(1)
		return
	var certificate := Crypto.new().generate_self_signed_certificate(key, "CN=localhost,O=Eloria Test,C=US")
	quit(0 if certificate.save(args[1]) == OK else 1)
