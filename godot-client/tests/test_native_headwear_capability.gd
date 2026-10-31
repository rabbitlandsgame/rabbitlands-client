extends SceneTree
var checks := 0
var failures := 0

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)

func _initialize() -> void:
	var previous := OS.get_environment("RL_HEADWEAR_FIT")
	OS.set_environment("RL_HEADWEAR_FIT", "")
	RLHeadwearFit.reload()
	RLHeadwearFit._loaded = true
	RLHeadwearFit._shipped = false
	RLHeadwearFit._data = {"shippedBodies": ["luminous_female", "luminous_male"],
		"pieces": {"111": {"fits": {
			"luminous_female/tested_style": {"nativeQualified": true},
			"luminous_female/other_style": {},
			"luminous_female/invalid_flag": {"nativeQualified": 1},
			"luminous_female": {"nativeQualified": true},
			"luminous_female/*": {"nativeQualified": true},
			"greyhaven_female/tested_style": {"nativeQualified": true}}}}}
	check(RLHeadwearFit.fits_shipped_body("luminous_female", 111, "tested_style"), "Only the reviewed exact pairing opts in")
	check(not RLHeadwearFit.fits_shipped_body("luminous_female"), "Global shipped-body default remains off")
	check(not RLHeadwearFit.fits_shipped_body("luminous_male"), "Other shipped-body default remains off")
	check(not RLHeadwearFit.fits_shipped_body("luminous_female", 111, ""), "A bald fit cannot opt in")
	check(not RLHeadwearFit.fits_shipped_body("luminous_female", 111, "other_style"), "Unqualified exact fits remain off")
	check(not RLHeadwearFit.fits_shipped_body("luminous_female", 111, "unknown_style"), "A wildcard cannot opt another hairstyle in")
	check(not RLHeadwearFit.fits_shipped_body("luminous_female", 111, "*"), "A literal wildcard cannot act as a reviewed hairstyle")
	check(not RLHeadwearFit.fits_shipped_body("luminous_female", 111, "invalid_flag"), "A capability requires an explicit boolean flag")
	check(not RLHeadwearFit.fits_shipped_body("luminous_female", 170, "tested_style"), "Another item cannot reuse the capability")
	check(not RLHeadwearFit.fits_shipped_body("luminous_male", 111, "tested_style"), "Another sex cannot reuse the capability")
	check(not RLHeadwearFit.fits_shipped_body("greyhaven_female", 111, "tested_style"), "An unlisted race remains outside this feature")
	check(RLHeadwearFit.fit_name(RLHeadwearFit.piece(111), "luminous_female", "tested_style") == "luminous_female/tested_style", "The accepted pairing resolves to its exact reviewed key")
	RLHeadwearFit._shipped = true
	check(RLHeadwearFit.fits_shipped_body("luminous_male"), "The existing developer comparison switch is preserved")
	check(not RLHeadwearFit.fits_shipped_body("greyhaven_female", 111, "tested_style"), "The developer switch does not broaden race support")
	OS.set_environment("RL_HEADWEAR_FIT", "off")
	RLHeadwearFit.reload()
	check(not RLHeadwearFit.fits_shipped_body("luminous_female", 111, "tested_style"), "The explicit off switch still disables all fits")
	OS.set_environment("RL_HEADWEAR_FIT", previous)
	RLHeadwearFit.reload()
	print("NATIVE_HEADWEAR_CAPABILITY_TESTS ", checks, " checks, ", failures, " failures")
	quit(0 if failures == 0 else 1)
