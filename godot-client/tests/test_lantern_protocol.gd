extends SceneTree

var failures := 0
var checks := 0

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func decode(value: Variant) -> Dictionary:
	return EloriaProtocol.decode_server(207,JSON.stringify(value).to_utf8_buffer())

func _init() -> void:
	var valid := {"version":1,"active":true,"stage":7,"total":28,"scene":4,
		"key":"store_reed","title":"Store the Reed","hint":"Select Reed and Deposit.",
		"control":"deposit","item":"Reed","map":"lantern_reach","target_id":"lower_cache",
		"target":[44,70],"required":3,"count":0,
		"flags":{"crafted":false,"prepared":false,"repaired":false,"lit":false}}
	expect(decode(valid).get("type")=="lantern_tutorial","server guide decodes")
	expect(decode({"version":1,"active":false}).state.active==false,"completion removes guide")
	for version: Variant in [2, "1", [], true, null]:
		var broken: Dictionary=valid.duplicate(true)
		broken.version=version
		expect(decode(broken).get("type")=="invalid","bad version "+var_to_str(version))
	for key in ["stage","total","scene","count","required","hint","target","flags"]:
		var broken: Dictionary=valid.duplicate(true)
		broken.erase(key)
		expect(decode(broken).get("type")=="invalid","missing "+key)
	for number: Variant in [-1, 1.5, 999999, "7", {}, null]:
		var broken: Dictionary=valid.duplicate(true)
		broken.stage=number
		expect(decode(broken).get("type")=="invalid","bad stage "+str(number))
	for coordinates: Variant in [[],[1],[1,2,3],["44",70],[-1,70],[1.5,70]]:
		var broken: Dictionary=valid.duplicate(true)
		broken.target=coordinates
		expect(decode(broken).get("type")=="invalid","bad target "+str(coordinates))
	var broken: Dictionary=valid.duplicate(true)
	broken.flags.lit="true"
	expect(decode(broken).get("type")=="invalid","flags are booleans")
	expect(EloriaProtocol.decode_lantern("{".to_utf8_buffer()).type=="invalid","invalid JSON")
	expect(EloriaProtocol.CLIENT_CAPABILITIES.has("lantern_tutorial_v1"),"capability declared")
	var bell: Dictionary=valid.duplicate(true)
	bell.tutorial="second_bell";bell.chapter="THE SECOND BELL";bell.map="bellwatch"
	bell.remaining=3;bell.pending=true;bell.assisted=false
	for gate in ["north","east","south","west","rung"]:bell.flags[gate]=false
	expect(decode(bell).get("type")=="lantern_tutorial","Bellwatch uses the native guide protocol")
	for field in ["remaining","pending","assisted","chapter"]:
		var bad: Dictionary=bell.duplicate(true)
		bad[field]="untrusted"
		expect(decode(bad).get("type")=="invalid","reject malformed Bellwatch "+field)
	for chapter: Variant in [1, [], true]:
		var bad: Dictionary=bell.duplicate(true)
		bad.chapter=chapter
		expect(decode(bad).get("type")=="invalid","reject Bellwatch chapter "+str(chapter))
	var bad_gate: Dictionary=bell.duplicate(true)
	bad_gate.flags.west=1
	expect(decode(bad_gate).get("type")=="invalid","gate flags are authoritative booleans")
	var unknown: Dictionary=bell.duplicate(true)
	unknown.tutorial="unknown"
	expect(decode(unknown).get("type")=="invalid","unknown tutorial is rejected")
	expect(EloriaProtocol.CLIENT_CAPABILITIES.has("second_bell_v1"),"Bellwatch capability declared")
	var sky: Dictionary=bell.duplicate(true)
	sky.tutorial="borrowed_sky";sky.chapter="THE BORROWED SKY";sky.map="stillglass"
	expect(decode(sky).get("type")=="lantern_tutorial","Stillglass uses the native guide")
	expect(EloriaProtocol.CLIENT_CAPABILITIES.has("borrowed_sky_v1"),"Stillglass capability declared")
	sky.chapter="THE SECOND BELL"
	expect(decode(sky).get("type")=="invalid","tutorial and chapter must agree")
	var road: Dictionary=valid.duplicate(true)
	road.tutorial="followup";road.adventure="The Missing Caravan";road.guide="Toma"
	road.flags={"north":true,"east":false,"south":false,"west":false}
	expect(decode(road).get("type")=="lantern_tutorial","follow-up adventure guide decodes")
	road.flags.east="open"
	expect(decode(road).get("type")=="invalid","follow-up gates require booleans")
	road.flags.east=false;road.guide=42
	expect(decode(road).get("type")=="invalid","guide name requires text")
	road.guide="Master Edda"
	for flag in ["forge_lit", "sword_ready", "pump_repaired", "order_ready",
			"caravan_north_open", "caravan_east_home", "caravan_south_home", "caravan_west_home"]:
		road.flags[flag]=true
		expect(decode(road).get("type")=="lantern_tutorial", "Workshop outcome decodes: "+flag)
		road.flags[flag]="true"
		expect(decode(road).get("type")=="invalid", "Workshop outcome requires boolean: "+flag)
		road.flags[flag]=false
	expect(decode({"version":1,"active":false,"tutorial":"followup"}).get("type")=="lantern_tutorial","leaving removes adventure guide")
	# Signed Ashore, the landing isle's chapter: the Lantern's frame with its
	# own chapter name and four countersigns instead of the Lantern's flags.
	var ashore: Dictionary=valid.duplicate(true)
	ashore.tutorial="signed_ashore";ashore.chapter="SIGNED ASHORE";ashore.map="landfall"
	ashore.stage=2;ashore.total=10;ashore.scene=2;ashore.key="grove";ashore.title="The Palace Grove"
	ashore.hint="Click an olive bush once.";ashore.control="world";ashore.item="Olive"
	ashore.target_id="olive_grove";ashore.target=[124,262];ashore.required=5;ashore.count=2
	ashore.flags={"grove":false,"temple":false,"gate":false,"light":false}
	expect(decode(ashore).get("type")=="lantern_tutorial","Signed Ashore uses the native guide protocol")
	expect(decode(ashore).get("state",{}).get("chapter")=="SIGNED ASHORE","Signed Ashore state keeps its chapter")
	expect(EloriaProtocol.CLIENT_CAPABILITIES.has("signed_ashore_v1"),"Signed Ashore capability declared")
	# A chapter that is not text at all is refused as invalid, not a script error.
	for chapter: Variant in ["THE LAST LANTERN", "THE SECOND BELL", "signed ashore", "", null, 1, 1.5, [], {}, true]:
		var wrong: Dictionary=ashore.duplicate(true)
		wrong.chapter=chapter
		expect(decode(wrong).get("type")=="invalid","reject Signed Ashore under chapter "+str(chapter))
	var unnamed: Dictionary=ashore.duplicate(true)
	unnamed.erase("chapter")
	expect(decode(unnamed).get("type")=="invalid","Signed Ashore requires its chapter")
	for countersign in ["grove","temple","gate","light"]:
		for bad: Variant in ["true", 1, null]:
			var unsigned: Dictionary=ashore.duplicate(true)
			unsigned.flags[countersign]=bad
			expect(decode(unsigned).get("type")=="invalid","countersign "+countersign+" requires a boolean, not "+str(bad))
		var missing: Dictionary=ashore.duplicate(true)
		missing.flags.erase(countersign)
		expect(decode(missing).get("type")=="invalid","countersign "+countersign+" is required")
	var lantern_flags: Dictionary=ashore.duplicate(true)
	lantern_flags.flags={"crafted":false,"prepared":false,"repaired":false,"lit":false}
	expect(decode(lantern_flags).get("type")=="invalid","the Lantern's flags do not stand in for the countersigns")
	ashore.flags.grove=true
	expect(decode(ashore).get("type")=="lantern_tutorial","a signed countersign decodes")
	expect(decode({"version":1,"active":false,"tutorial":"signed_ashore"}).get("type")=="lantern_tutorial","leaving removes the Signed Ashore guide")
	var watchpost: Dictionary=valid.duplicate(true)
	watchpost.tutorial="watchpost";watchpost.chapter="HELP FOR THE WATCHPOST";watchpost.paused=false
	watchpost.stage=4;watchpost.total=6;watchpost.key="sage";watchpost.item="Sage"
	expect(decode(watchpost).get("type")=="lantern_tutorial","medicine quest guide decodes")
	watchpost.chapter="THE LAST LANTERN"
	expect(decode(watchpost).get("type")=="invalid","medicine quest chapter must match")
	watchpost.chapter="HELP FOR THE WATCHPOST";watchpost.paused="false"
	expect(decode(watchpost).get("type")=="invalid","medicine quest pause flag is boolean")
	watchpost.paused=false
	for chapter: Variant in ["", null, 1, 1.5, [], {}, true]:
		watchpost.chapter=chapter
		expect(decode(watchpost).get("type")=="invalid","medicine quest rejects nonmatching chapter "+str(chapter))
	print("Lantern protocol: %d checks, %d failures" % [checks,failures])
	quit(failures)
