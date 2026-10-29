extends SceneTree
## The colour model's pure resolver (colour model spec revision 3; C16-C18,
## C20-C22 and the resolver half of R1-R4, R7 and R8): AppearanceColours and
## HairFinish against frozen vectors from an independent OKLab/OKHSL reference
## (tools/colour_calibration/okcolor.py, a port of Ottosson's ok_color.h).
## No actor is built and no asset is imported.
const Colours = preload("res://src/actors/appearance_colours.gd")
const Finish = preload("res://src/actors/hair_finish.gd")
const Custom = preload("res://src/actors/portrait_customization.gd")
const FEMALE := {"culture": "luminous", "bodyTemplate": "luminous_female", "gender": "female"}
const MALE := {"culture": "luminous", "bodyTemplate": "luminous_male", "gender": "male"}
const VOTARY := {"culture": "votary", "bodyTemplate": "votary_male", "gender": "male"}
## Frozen OKHSL vectors: wire hue, saturation, lightness -> sRGB.
const OKHSL_VECTORS := [
	[1, 1, 1, 0.0000000, 0.0000000, 0.0000000], [1, 1, 101, 1.0000000, 1.0000000, 1.0000000], [1, 101, 51, 0.8419489, -0.0000000, 0.4449380],
	[121, 101, 51, 0.0000000, 0.5428960, 0.4756529], [240, 101, 51, 0.8393309, 0.0000000, 0.4595521], [61, 51, 26, 0.2640311, 0.2229885, 0.1095823],
	[181, 51, 76, 0.6620741, 0.7204904, 0.8896707], [240, 1, 51, 0.4661808, 0.4661808, 0.4661808], [1, 101, 1, 0.0000000, 0.0000000, 0.0000000],
	[120, 101, 101, 1.0000000, 1.0000000, 1.0000000], [159, 72, 89, 0.7555989, 0.8881220, 0.9756447], [186, 75, 6, 0.0206005, 0.0202698, 0.1121279],
	[149, 88, 28, 0.0346719, 0.2737018, 0.3393650], [10, 64, 70, 0.9006143, 0.5436374, 0.5805739], [37, 34, 1, 0.0000000, 0.0000000, 0.0000000],
	[118, 30, 77, 0.6241761, 0.7741052, 0.7304307], [212, 28, 75, 0.7588264, 0.6834830, 0.7884056], [169, 100, 95, 0.8873923, 0.9394546, 0.9997494],
	[199, 5, 75, 0.7153268, 0.7113316, 0.7283501], [218, 1, 28, 0.2452111, 0.2452111, 0.2452111], [118, 53, 46, 0.2417604, 0.4660731, 0.4100786],
	[176, 85, 27, 0.0848185, 0.2155002, 0.4852469], [55, 60, 12, 0.1268775, 0.0905598, 0.0249189], [157, 27, 5, 0.0126595, 0.0245647, 0.0335770],
	[175, 11, 26, 0.2116632, 0.2279475, 0.2554721], [125, 8, 84, 0.7904942, 0.8184533, 0.8141149], [238, 69, 45, 0.6517820, 0.2290127, 0.4212794],
	[40, 20, 97, 0.9659211, 0.9523331, 0.9425547], [37, 100, 95, 0.9998122, 0.9144742, 0.8615825], [101, 92, 23, 0.0621994, 0.2391289, 0.1157834],
	[207, 32, 64, 0.6428909, 0.5595684, 0.7150029], [44, 31, 38, 0.4069954, 0.3209951, 0.2405432], [99, 81, 54, 0.2701526, 0.5735501, 0.3163305],
	[79, 89, 48, 0.4202599, 0.4686855, 0.0905141], [203, 21, 30, 0.2769824, 0.2490146, 0.3195932], [86, 13, 43, 0.3748841, 0.3973158, 0.3489272],
	[125, 97, 54, 0.0538339, 0.5725434, 0.5322619], [192, 15, 9, 0.0650113, 0.0644893, 0.0843408], [230, 64, 65, 0.8415568, 0.4593413, 0.6961554],
	[131, 40, 82, 0.6374057, 0.8338158, 0.8307346], [35, 7, 81, 0.7958008, 0.7738984, 0.7618962], [202, 4, 39, 0.3507858, 0.3466354, 0.3589290],
	[48, 68, 46, 0.5451322, 0.3790349, 0.1639861], [35, 39, 2, 0.0022295, 0.0010012, 0.0005332], [219, 15, 34, 0.3295345, 0.2851521, 0.3280635],
	[104, 93, 54, 0.1583704, 0.5845650, 0.3515275], [202, 43, 94, 0.9292000, 0.9121596, 0.9622196], [145, 95, 95, 0.8242744, 0.9612319, 0.9985352],
	[171, 49, 70, 0.5353871, 0.6722629, 0.8487199], [71, 80, 97, 0.9740956, 0.9662268, 0.8076050], [57, 45, 80, 0.8476966, 0.7570717, 0.5791047],
	[220, 20, 2, 0.0016525, 0.0010690, 0.0016051], [91, 20, 52, 0.4429102, 0.4960329, 0.4158670], [189, 58, 16, 0.1176715, 0.1118545, 0.2603386],
	[79, 76, 5, 0.0207391, 0.0257715, 0.0028367], [203, 8, 86, 0.8363343, 0.8293257, 0.8482113], [28, 69, 9, 0.1241951, 0.0383847, 0.0139546],
	[49, 77, 87, 0.9749261, 0.8139209, 0.6178179], [98, 27, 46, 0.3564637, 0.4447510, 0.3584277], [161, 91, 36, 0.0367200, 0.3429825, 0.5060013],
	[193, 52, 36, 0.3133071, 0.2782012, 0.5248614], [115, 75, 34, 0.1171604, 0.3480200, 0.2823243], [34, 72, 50, 0.6688829, 0.3642511, 0.1798074],
	[61, 28, 14, 0.1303665, 0.1150059, 0.0737698], [57, 41, 16, 0.1611542, 0.1305142, 0.0689242], [235, 66, 70, 0.8932228, 0.5275282, 0.6994083],
	[2, 83, 50, 0.7835209, 0.1796114, 0.4259867], [25, 39, 20, 0.2420059, 0.1423888, 0.1151968], [54, 11, 35, 0.3285522, 0.3082397, 0.2760107],
	[116, 92, 27, 0.0398265, 0.2782050, 0.2223506], [231, 3, 95, 0.9342790, 0.9317425, 0.9330189], [136, 72, 1, 0.0000000, 0.0000000, 0.0000000],
	[25, 16, 34, 0.3485897, 0.2852287, 0.2676532], [171, 97, 90, 0.8001633, 0.8862410, 0.9980211], [223, 17, 75, 0.7556261, 0.6925354, 0.7421430],
	[124, 58, 75, 0.4469490, 0.7862209, 0.7405087], [77, 70, 82, 0.7856149, 0.8265527, 0.4291844], [225, 25, 88, 0.8912744, 0.8370301, 0.8753744],
	[59, 11, 24, 0.2187242, 0.2075629, 0.1822969], [141, 44, 85, 0.6806615, 0.8595298, 0.8923330], [189, 76, 88, 0.8333612, 0.8434943, 0.9789192],
	[134, 58, 60, 0.3032782, 0.6149075, 0.6295900], [52, 1, 82, 0.7892852, 0.7892852, 0.7892852], [41, 2, 46, 0.4201450, 0.4159736, 0.4128102],
	[126, 91, 58, 0.1149358, 0.6154696, 0.5806321], [46, 95, 58, 0.7451110, 0.4645735, 0.0523572], [47, 60, 97, 0.9850167, 0.9489872, 0.9111389],
	[175, 41, 7, 0.0239276, 0.0448264, 0.0849426], [238, 61, 65, 0.8496058, 0.4695128, 0.6220772], [6, 88, 18, 0.2984324, 0.0215395, 0.1176880],
	[130, 7, 43, 0.3636061, 0.3954099, 0.3939473], [236, 51, 100, 0.9954346, 0.9859358, 0.9894438], [90, 64, 3, 0.0035642, 0.0074836, 0.0017142],
	[107, 59, 66, 0.3963122, 0.6928937, 0.5334449], [87, 35, 62, 0.5315375, 0.6095458, 0.4484832], [17, 64, 15, 0.2184453, 0.0719802, 0.0683523],
	[77, 91, 11, 0.0867503, 0.0948659, 0.0047011], [199, 25, 13, 0.1106553, 0.0981460, 0.1440427], [33, 10, 50, 0.4912056, 0.4462248, 0.4240976],
	[101, 50, 37, 0.2253960, 0.3695119, 0.2561984], [102, 74, 12, 0.0338287, 0.1173881, 0.0591464], [28, 6, 47, 0.4468730, 0.4205176, 0.4112418],
	[134, 19, 25, 0.1729993, 0.2303048, 0.2327267], [167, 38, 42, 0.2715296, 0.3898061, 0.5074150], [85, 60, 95, 0.9042957, 0.9560382, 0.8341180],
	[160, 13, 46, 0.3755520, 0.4251878, 0.4600736], [120, 55, 70, 0.4182660, 0.7299799, 0.6633199], [171, 36, 93, 0.8839225, 0.9139251, 0.9530956],
	[142, 79, 66, 0.2230130, 0.6875737, 0.7676326], [132, 82, 8, 0.0055358, 0.0691499, 0.0703974], [223, 71, 75, 0.8921148, 0.6015344, 0.8418472],
	[42, 45, 42, 0.4824010, 0.3452671, 0.2259499], [114, 73, 99, 0.9373839, 0.9934575, 0.9704132], [85, 44, 25, 0.1947447, 0.2347567, 0.1317579],
	[199, 50, 40, 0.3844974, 0.3046288, 0.5553482], [34, 90, 69, 0.9559716, 0.5152263, 0.2416614], [42, 66, 44, 0.5420195, 0.3468349, 0.1634547],
	[11, 54, 38, 0.5144998, 0.2427117, 0.2716550], [67, 35, 75, 0.7479209, 0.7192948, 0.5603957], [190, 29, 20, 0.1621779, 0.1630298, 0.2392730],
	[118, 93, 87, 0.2554158, 0.9704485, 0.8260234], [142, 2, 45, 0.4027548, 0.4082343, 0.4093680], [40, 88, 24, 0.3160230, 0.1647077, 0.0173587],
	[145, 52, 39, 0.1876495, 0.3809085, 0.4288552], [210, 52, 95, 0.9512843, 0.9194916, 0.9696530], [1, 84, 99, 0.9980328, 0.9693273, 0.9765479],
	[80, 75, 42, 0.3583028, 0.4059545, 0.1353560], [189, 31, 86, 0.8208943, 0.8271562, 0.9014172], [4, 46, 15, 0.1953767, 0.0865125, 0.1147497],
	[182, 74, 72, 0.5910845, 0.6684545, 0.9383435], [106, 67, 8, 0.0160164, 0.0701999, 0.0373647], [226, 61, 32, 0.4230966, 0.1751087, 0.3644452],
	[73, 76, 81, 0.8139514, 0.8046542, 0.3455548], [185, 38, 36, 0.2805636, 0.3071937, 0.4671294], [204, 79, 86, 0.8716543, 0.7930504, 0.9764927],
	[209, 58, 15, 0.1663995, 0.0824927, 0.2135709], [193, 95, 60, 0.5494219, 0.4527763, 0.9874136], [181, 70, 93, 0.8838929, 0.9096164, 0.9809488],
	[51, 48, 2, 0.0019603, 0.0011272, 0.0003733], [71, 38, 16, 0.1423965, 0.1382390, 0.0749179], [169, 50, 74, 0.5792078, 0.7176999, 0.8754202],
	[224, 36, 3, 0.0099425, 0.0040376, 0.0084524], [226, 39, 95, 0.9593597, 0.9197328, 0.9462068], [150, 79, 29, 0.0647980, 0.2819960, 0.3497937],
	[72, 56, 14, 0.1239010, 0.1203303, 0.0400466], [84, 29, 21, 0.1685475, 0.1911986, 0.1297587], [211, 60, 70, 0.7672108, 0.5749488, 0.8538904],
	[32, 53, 75, 0.8827460, 0.6556243, 0.5476996], [125, 23, 11, 0.0597574, 0.0954366, 0.0906865], [10, 55, 49, 0.6636948, 0.3268921, 0.3698991],
	[77, 21, 99, 0.9771382, 0.9786549, 0.9694021], [127, 65, 17, 0.0467551, 0.1662370, 0.1580405], [135, 91, 99, 0.9270763, 0.9933837, 0.9971729],
	[183, 17, 28, 0.2287980, 0.2432939, 0.2955386], [71, 44, 38, 0.3570625, 0.3471591, 0.2015529], [60, 99, 61, 0.6981804, 0.5454108, 0.0205939],
	[164, 89, 24, 0.0193545, 0.2204177, 0.3531969], [167, 94, 17, 0.0055713, 0.1491392, 0.2708060], [100, 46, 1, 0.0000000, 0.0000000, 0.0000000],
	[214, 79, 20, 0.2641863, 0.0600958, 0.3101394], [17, 39, 23, 0.2835085, 0.1605236, 0.1526459], [215, 62, 59, 0.7033806, 0.4177259, 0.7581088],
	[93, 44, 54, 0.4097357, 0.5396627, 0.3661233], [88, 56, 80, 0.6825568, 0.8214143, 0.5521236], [178, 24, 15, 0.1051684, 0.1252590, 0.1690141],
	[234, 3, 8, 0.0578880, 0.0551288, 0.0562977], [158, 92, 85, 0.6310935, 0.8568568, 0.9940109], [35, 21, 25, 0.2593675, 0.2046145, 0.1737270],
	[216, 64, 92, 0.9478464, 0.8700466, 0.9573462], [86, 5, 4, 0.0128836, 0.0135031, 0.0122094], [38, 26, 77, 0.8118007, 0.7144837, 0.6503071],
	[168, 23, 64, 0.5285388, 0.6082747, 0.6946407], [63, 27, 63, 0.6256410, 0.5879670, 0.4653616], [91, 69, 13, 0.0706393, 0.1240032, 0.0386504],
	[17, 60, 88, 0.9579485, 0.8173977, 0.8047993], [86, 61, 101, 1.0000000, 1.0000000, 1.0000000], [131, 54, 53, 0.2719920, 0.5375580, 0.5362000],
	[33, 96, 49, 0.7044268, 0.3170615, 0.0330546], [72, 55, 14, 0.1237868, 0.1203016, 0.0412750], [154, 60, 83, 0.6329729, 0.8348749, 0.9336205],
	[69, 14, 67, 0.6401174, 0.6333521, 0.5698195], [109, 1, 22, 0.1899016, 0.1899016, 0.1899016], [130, 51, 101, 1.0000000, 1.0000000, 1.0000000],
	[62, 62, 23, 0.2353950, 0.1957412, 0.0731662], [78, 67, 53, 0.4774884, 0.5143573, 0.2193380], [231, 69, 32, 0.4545219, 0.1451238, 0.3422625],
	[111, 82, 72, 0.2795364, 0.7857119, 0.5999365], [198, 47, 91, 0.8924397, 0.8764147, 0.9526945], [82, 20, 30, 0.2552472, 0.2731380, 0.2150843],
	[142, 54, 97, 0.9111855, 0.9677949, 0.9795027], [202, 44, 76, 0.7523320, 0.6904203, 0.8612648], [10, 97, 2, 0.0048053, 0.0000367, 0.0005400],
	[110, 40, 91, 0.8106357, 0.9192526, 0.8636437], [100, 40, 62, 0.4616269, 0.6267155, 0.4849255], [126, 7, 46, 0.3923293, 0.4252386, 0.4209637],
	[159, 75, 83, 0.6225223, 0.8320661, 0.9669445], [17, 5, 101, 1.0000000, 1.0000000, 1.0000000], [236, 63, 1, 0.0000000, 0.0000000, 0.0000000],
	[46, 55, 36, 0.4152171, 0.2921940, 0.1556859], [227, 72, 62, 0.8380082, 0.3848398, 0.7154088],
]
## Undertone landmarks per sex (U 1, 51, 101, 151, 201 by row; the six stops
## by column), from the reference implementation (OKLab, Ottosson).
const UNDERTONE_FEMALE := [
	[Color(0.884766, 0.695863, 0.609680), Color(0.890832, 0.591667, 0.499472), Color(0.844689, 0.547777, 0.374549), Color(0.683710, 0.376096, 0.266274), Color(0.459042, 0.219531, 0.154912), Color(0.268603, 0.147100, 0.116030)],
	[Color(0.876896, 0.702676, 0.586527), Color(0.880656, 0.602107, 0.463306), Color(0.826322, 0.562657, 0.338035), Color(0.672891, 0.388320, 0.221243), Color(0.452160, 0.228665, 0.118339), Color(0.264788, 0.151421, 0.100940)],
	[Color(0.827451, 0.721569, 0.631372), Color(0.813873, 0.633185, 0.532314), Color(0.768627, 0.592157, 0.388235), Color(0.619608, 0.419608, 0.286274), Color(0.403922, 0.258824, 0.184314), Color(0.239216, 0.164706, 0.129412)],
	[Color(0.829496, 0.724799, 0.595303), Color(0.817038, 0.637432, 0.476795), Color(0.773528, 0.596085, 0.296970), Color(0.623795, 0.423125, 0.204700), Color(0.406677, 0.261393, 0.131773), Color(0.240505, 0.166300, 0.106528)],
	[Color(0.788067, 0.740557, 0.617759), Color(0.760317, 0.662071, 0.511399), Color(0.700437, 0.628159, 0.354125), Color(0.561578, 0.454517, 0.256485), Color(0.365110, 0.283082, 0.165016), Color(0.218664, 0.176506, 0.120824)]]
const UNDERTONE_MALE_STOP1 := [Color(0.909490, 0.590728, 0.482848), Color(0.898660, 0.602031, 0.442372),
	Color(0.826773, 0.636414, 0.519142), Color(0.830301, 0.640798, 0.457376), Color(0.769062, 0.667751, 0.495886)]
var failures := 0
var checks := 0

func _init() -> void:
	run.call_deferred()

func expect(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(label)

func near(a: Color, b: Color, tolerance: float) -> bool:
	return absf(a.r - b.r) <= tolerance and absf(a.g - b.g) <= tolerance and absf(a.b - b.b) <= tolerance

func run() -> void:
	check_okhsl()
	check_palette_coordinates()
	check_slider()
	check_undertone()
	check_snap_and_guard()
	check_neutral_is_develop()
	check_custom_values()
	check_garment_limits()
	check_hair_tables()
	check_canonical()
	check_npc_catalogue()
	check_clearing()
	check_listed_bytes()
	print("Appearance colours: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

# C16: Godot's OKHSL against the frozen reference vectors, and quantising back.
func check_okhsl() -> void:
	var worst := 0.0
	for row: Array in OKHSL_VECTORS:
		var triple := Vector3i(row[0], row[1], row[2])
		var got := Colours.triple_colour(triple)
		var want := Color(row[3], row[4], row[5])
		worst = maxf(worst, maxf(absf(got.r - want.r), maxf(absf(got.g - want.g), absf(got.b - want.b))))
		expect(near(got, want, 1e-5), "OKHSL %s -> %s (want %s)" % [triple, got, want])
		if triple.z > 1 and triple.z < 101 and triple.y > 1:
			var back := Colours.quantise(got)
			expect(back == triple or (absi(back.x - triple.x) <= 1 and back.y == triple.y and back.z == triple.z and triple.y <= 3),
				"quantise(OKHSL %s) round trips (%s)" % [triple, back])
	print("OKHSL worst channel difference %.9f over %d vectors" % [worst, OKHSL_VECTORS.size()])

# C16: palette round trips to the Appendix A triples.
func check_palette_coordinates() -> void:
	for index: int in 12:
		expect(Colours.quantise(AppearanceVariants.eye_color(index)) == Colours.EYE_FROZEN[index],
			"eye %d quantises to its frozen triple %s" % [index, Colours.quantise(AppearanceVariants.eye_color(index))])
	for part: String in Colours.PARTS:
		for index: int in 12:
			var dye := AppearanceVariants.wardrobe_color("luminous", Colours.PARTS[part], index)
			expect(Colours.quantise(dye) == Colours.frozen_dye(part, index), "%s dye %d quantises to %s (%s)" % [part, index,
				Colours.frozen_dye(part, index), Colours.quantise(dye)])
	for sex: String in ["female", "male"]:
		var seen := {}
		for index: int in 20:
			var frozen := Colours.frozen_hair(index, sex)
			expect(Colours.quantise(Colours.palette_apparent(index, sex)) == frozen,
				"%s hair %d apparent quantises to %s (%s)" % [sex, index, frozen, Colours.quantise(Colours.palette_apparent(index, sex))])
			expect(not seen.has(frozen), "%s hair %d frozen triple unique" % [sex, index])
			seen[frozen] = true
			expect(Colours.nearest_hair_index(Colours.triple_colour(frozen), sex) == index,
				"%s hair %d frozen triple is nearest its own entry" % [sex, index])
	for index: int in 12:
		expect(Colours.nearest_eye_index(Colours.triple_colour(Colours.EYE_FROZEN[index])) == index, "eye %d snaps back" % index)
		for part: String in Colours.PARTS:
			var nearest := Colours.nearest_dye_index(Colours.triple_colour(Colours.frozen_dye(part, index)), part)
			if Colours.listed_dyes(part).has(index):
				expect(nearest == index, "%s dye %d snaps back" % [part, index])
			else:
				expect(nearest != index and Colours.listed_dyes(part).has(nearest),
					"%s dye %d (merged in the dropdown) is nearest a listed dye (%d)" % [part, index, nearest])

# C17: the skin tone slider.
func check_slider() -> void:
	expect(Colours.SKIN_STOP_POSITION == [1, 23, 43, 95, 156, 201] and Colours.SKIN_STOP_INDEX == [1, 0, 2, 3, 4, 5],
		"frozen stop positions")
	# Soft tan (index 0) is not a legacy byte: develop's Human list lacks it.
	var expected := {1: 1, 12: 1, 13: 1, 22: 1, 23: 2, 33: 2, 34: 2, 69: 2, 70: 3, 125: 3, 126: 4, 178: 4, 179: 5, 201: 5}
	for position: int in expected:
		expect(Colours.nearest_skin_index(position) == expected[position], "position %d -> skin %d" % [position, expected[position]])
	for sex: String in ["female", "male"]:
		var config := FEMALE if sex == "female" else MALE
		for stop: int in 6:
			var index: int = Colours.SKIN_STOP_INDEX[stop]
			var path := Colours.from_oklab(Colours.skin_path(Colours.SKIN_STOP_POSITION[stop], sex, config))
			expect(near(path, Colours.skin_stop_colour(index, sex, config), 2e-5), "%s stop %d is skin %d" % [sex, stop, index])
		var largest := 0.0
		var smallest := INF
		for position: int in range(1, 201):
			var step := Colours.skin_path(position, sex, config).distance_to(Colours.skin_path(position + 1, sex, config))
			largest = maxf(largest, step)
			smallest = minf(smallest, step)
			var colour := Colours.oklab_to_linear(Colours.skin_path(position, sex, config))
			expect(colour.x >= -1e-6 and colour.y >= -1e-6 and colour.z >= -1e-6 and colour.x <= 1.000001
				and colour.y <= 1.000001 and colour.z <= 1.000001, "%s position %d in gamut" % [sex, position])
		expect(largest <= 0.0030 and smallest >= 0.0020, "%s slider steps dE %.4f-%.4f" % [sex, smallest, largest])
	expect(near(Colours.skin_reference("female", {}), Color(0.8138729394650926, 0.6331850101745203, 0.5323137669781451), 1e-6),
		"female Soft tan reference")

# C21: the undertone.
func check_undertone() -> void:
	expect(Colours.undertone_t(0) == 0.0 and Colours.undertone_t(101) == 0.0 and Colours.undertone_t(1) == -1.0
		and Colours.undertone_t(201) == 1.0 and is_equal_approx(Colours.undertone_t(51), -0.5), "undertone wire values")
	expect(Colours.undertone_offset(-1.0).is_equal_approx(Vector2(0.55, 0.15)) and Colours.undertone_offset(-0.5).is_equal_approx(Vector2(0.384, 0.331))
		and Colours.undertone_offset(0.0) == Vector2.ZERO and Colours.undertone_offset(0.5).is_equal_approx(Vector2(-0.1, 0.28))
		and Colours.undertone_offset(1.0).is_equal_approx(Vector2(-0.45, 0.12)), "the five frozen anchors")
	var wires := [1, 51, 101, 151, 201]
	for row: int in 5:
		for stop: int in 6:
			var lab: Vector3 = Colours.skin_lab(Colours.SKIN_STOP_POSITION[stop], Colours.undertone_t(wires[row]), "female", FEMALE).lab
			var want: Color = UNDERTONE_FEMALE[row][stop]
			expect(near(Colours.from_oklab(lab), want, 2e-5), "female U %d stop %d %s (want %s)" % [wires[row], stop,
				Colours.from_oklab(lab), want])
		var male: Vector3 = Colours.skin_lab(23, Colours.undertone_t(wires[row]), "male", MALE).lab
		expect(near(Colours.from_oklab(male), UNDERTONE_MALE_STOP1[row], 2e-5), "male Soft tan U %d" % wires[row])
	var mira := Colours.skin({"skin": 1, "skin_tone": 10, "skin_undertone": 51}, FEMALE)
	expect(mira.custom and Colours.delta_e(mira.colour, Color8(224, 169, 137)) <= 0.001,
		"Mira (10, 51) within dE 0.001 of (224,169,137): %.5f" % Colours.delta_e(mira.colour, Color8(224, 169, 137)))
	var limited := 0
	var worst_step := 0.0
	for sex: String in ["female", "male"]:
		var config := FEMALE if sex == "female" else MALE
		for position: int in range(1, 202, 4):
			var previous := Vector3.INF
			for wire: int in range(1, 202):
				var result := Colours.skin_lab(position, Colours.undertone_t(wire), sex, config)
				var lab: Vector3 = result.lab
				var path := Colours.skin_path(position, sex, config)
				expect(absf(lab.x - path.x) < 1e-6, "%s p %d U %d keeps lightness" % [sex, position, wire])
				var chroma := Vector2(lab.y, lab.z).length()
				var hue := rad_to_deg(atan2(lab.z, lab.y))
				if wire != 101:
					expect(chroma <= 0.11 + 1e-6 and hue >= 30.0 - 1e-3 and hue <= 95.0 + 1e-3,
						"%s p %d U %d inside hue 30-95 and chroma 0.11 (%.1f, %.4f)" % [sex, position, wire, hue, chroma])
				var linear := Colours.oklab_to_linear(lab)
				expect(linear.x >= -1e-5 and linear.y >= -1e-5 and linear.z >= -1e-5 and linear.x <= 1.00001
					and linear.y <= 1.00001 and linear.z <= 1.00001, "%s p %d U %d in gamut" % [sex, position, wire])
				if result.limited:
					limited += 1
				if previous != Vector3.INF and wire != 102 and wire != 101:
					worst_step = maxf(worst_step, previous.distance_to(lab))
				previous = lab
	expect(worst_step <= 0.001, "undertone byte steps dE <= 0.001 (%.5f)" % worst_step)
	print("undertone: %d limited samples, worst step %.5f" % [limited, worst_step])

# C18: Rule B/C snap and the guard.
func check_snap_and_guard() -> void:
	for sex: String in ["female", "male"]:
		var config := FEMALE if sex == "female" else MALE
		for index: int in 20:
			var frozen := Colours.frozen_hair(index, sex)
			var look := {"hair": AppearanceVariants.pack_hair(1, index), "hair_hue": frozen.x, "hair_sat": frozen.y, "hair_light": frozen.z}
			expect(not Colours.hair(look, config).custom, "%s hair %d typed frozen draws the palette (Rule C)" % [sex, index])
		# A custom hair colour near chestnut on a chestnut byte is drawn; on a
		# blond byte it is guarded.
		var near_chestnut := Colours.frozen_hair(2, sex) + Vector3i(0, 0, 2)
		var custom := {"hair": AppearanceVariants.pack_hair(1, 2), "hair_hue": near_chestnut.x, "hair_sat": near_chestnut.y, "hair_light": near_chestnut.z}
		expect(Colours.hair(custom, config).custom, "%s custom hair near its byte is drawn" % sex)
		custom["hair"] = AppearanceVariants.pack_hair(1, 3)
		expect(not Colours.hair(custom, config).custom, "%s custom hair on another byte is guarded" % sex)
	for index: int in 6:
		var position := Colours.skin_position(index)
		expect(not Colours.skin({"skin": index, "skin_tone": position}, FEMALE).custom, "skin %d typed on its stop is the palette" % index)
		expect(not Colours.skin({"skin": index, "skin_tone": position, "skin_undertone": 101}, FEMALE).custom,
			"undertone 101 is neutral on skin %d" % index)
		expect(Colours.skin({"skin": index, "skin_undertone": 60}, FEMALE).custom, "an undertone on palette skin %d is drawn" % index)
	for index: int in range(6, 10):
		expect(not Colours.skin({"skin": index, "skin_undertone": 30}, FEMALE).custom
			and not Colours.skin({"skin": index, "skin_tone": 100, "skin_undertone": 30}, FEMALE).custom,
			"an undertone or tone on Eloria skin %d is ignored" % index)
	expect(Colours.skin({"skin": 2, "skin_tone": 50}, FEMALE).custom, "tone 50 on golden tan (nearest 2) is drawn")
	expect(not Colours.skin({"skin": 3, "skin_tone": 50}, FEMALE).custom, "tone 50 on warm brown (nearest 2) is guarded")
	for index: int in 12:
		var frozen: Vector3i = Colours.EYE_FROZEN[index]
		expect(not Colours.eyes({"eyes": index, "eye_hue": frozen.x, "eye_sat": frozen.y, "eye_light": frozen.z}, FEMALE).custom,
			"eye %d typed frozen is the palette" % index)
		for part: String in Colours.PARTS:
			var dye := Colours.frozen_dye(part, index)
			expect(not Colours.garment({part: index, part + "_hue": dye.x, part + "_sat": dye.y, part + "_light": dye.z}, MALE, part).custom,
				"%s %d typed frozen is the palette" % [part, index])
	var emerald: Vector3i = Colours.EYE_FROZEN[1]
	expect(not Colours.eyes({"eyes": 0, "eye_hue": emerald.x, "eye_sat": emerald.y, "eye_light": emerald.z}, FEMALE).custom,
		"an emerald pigment on a sky-blue byte is guarded")
	expect(Colours.eyes({"eyes": 1, "eye_hue": emerald.x + 2, "eye_sat": emerald.y, "eye_light": emerald.z}, FEMALE).custom,
		"a custom pigment near emerald on an emerald byte is drawn")
	# Rule A: a partly set triple is the palette.
	expect(not Colours.eyes({"eyes": 1, "eye_hue": 106, "eye_sat": 0, "eye_light": 63}, FEMALE).custom, "Rule A at render time")

# R1, R2: neutral and non-Human values are develop's, exactly.
func check_neutral_is_develop() -> void:
	for config: Dictionary in [FEMALE, MALE, VOTARY]:
		var culture := str(config.culture)
		for skin: int in 10:
			for eyes: int in 12:
				var look := {"skin": skin, "eyes": eyes}
				var resolved := Colours.resolve(look, config)
				expect(not resolved.skin.custom and resolved.skin.colour == AppearanceVariants.skin_color(skin)
					and not resolved.eyes.custom and resolved.eyes.pigment == AppearanceVariants.eye_color(eyes),
					"%s skin %d eyes %d are develop's" % [config.bodyTemplate, skin, eyes])
		for hair: int in 300:
			var resolved := Colours.hair({"hair": hair}, config)
			var palette := AppearanceVariants.hair_color(hair)
			expect(not resolved.custom and resolved.dye == palette and resolved.brow == palette
				and Colours.hair_dye({"hair": hair}, config, "P4", 1, 75.0) == palette, "%s hair byte %d is develop's" % [config.bodyTemplate, hair])
		for part: String in Colours.PARTS:
			for index: int in 12:
				var resolved := Colours.garment({part: index}, config, part)
				expect(not resolved.custom and resolved.colour == AppearanceVariants.wardrobe_color(culture, Colours.PARTS[part], index),
					"%s %s %d is develop's" % [config.bodyTemplate, part, index])
	# R2: colour fields on a non-Human change nothing.
	var full := {"skin": 2, "skin_tone": 60, "skin_undertone": 30, "hair": 111, "hair_hue": 100, "hair_sat": 50, "hair_light": 50,
		"eyes": 3, "eye_hue": 60, "eye_sat": 80, "eye_light": 70, "shirt": 4, "shirt_hue": 10, "shirt_sat": 80, "shirt_light": 40,
		"hair_detail": 1, "hair_finish": 90}
	var resolved := Colours.resolve(full, VOTARY)
	expect(not resolved.human and not resolved.skin.custom and not resolved.hair.custom and not resolved.eyes.custom
		and not resolved.shirt.custom and not resolved.finish.custom, "a non-Human draws every colour field as the palette")

# R4: custom values give the specified parameters.
func check_custom_values() -> void:
	var look := {"skin": 2, "skin_tone": 60, "skin_undertone": 140}
	var skin := Colours.skin(look, FEMALE)
	var want := Colours.from_oklab(Colours.skin_lab(60, Colours.undertone_t(140), "female", FEMALE).lab)
	expect(skin.custom and near(skin.colour, want, 1e-6) and skin.position == 60.0, "custom skin is the final slider colour")
	for sex: String in ["female", "male"]:
		var config := FEMALE if sex == "female" else MALE
		var wire := Vector3i(40, 60, 30)
		var index := Colours.nearest_hair_index(Colours.triple_colour(wire), sex)
		var hair := Colours.hair({"hair": AppearanceVariants.pack_hair(1, index), "hair_hue": wire.x, "hair_sat": wire.y, "hair_light": wire.z}, config)
		var apparent := Colours.to_linear(Colours.triple_colour(wire))
		var reference: Dictionary = Colours.hair_table(sex, "R", 0, 50.0)
		var shown := (reference.gain as Vector3) * Colours.to_linear(hair.dye) / (Colours.SKIN_GAIN[sex] as Vector3)
		expect(hair.custom and shown.distance_to(apparent) < 1e-5, "%s custom hair: R shows the apparent colour" % sex)
		var bright := Vector3i(60, 20, 96)
		var light := Colours.hair({"hair": AppearanceVariants.pack_hair(3, Colours.nearest_hair_index(Colours.triple_colour(bright), sex)),
			"hair_hue": bright.x, "hair_sat": bright.y, "hair_light": bright.z}, config)
		var dye := Colours.to_linear(light.dye)
		var brow := Colours.to_linear(light.brow)
		expect(light.custom and light.reach < 1.0 and is_equal_approx(maxf(dye.x, maxf(dye.y, dye.z)), Colours.D_MAX)
			and maxf(brow.x, maxf(brow.y, brow.z)) <= 1.00001, "%s: out-of-reach hair scales to D_MAX, brows to 1" % sex)
		var target := Colours.oklab(Colours.triple_colour(bright))
		var reached := Colours.linear_to_oklab(Colours.hair_ratio(sex) * dye)
		var hue_change := absf(rad_to_deg(atan2(target.z, target.y) - atan2(reached.z, reached.y)))
		expect(hue_change <= 0.5, "%s: reach scaling keeps the hue (%.3f deg)" % [sex, hue_change])
	var eyes := Colours.eyes({"eyes": 7, "eye_hue": 1, "eye_sat": 1, "eye_light": 101}, FEMALE)
	expect(eyes.custom or Colours.nearest_eye_index(Colours.triple_colour(Vector3i(1, 1, 101))) != 7, "white pigment on silver grey")
	var bright_eye := Vector3i(150, 101, 95)
	var bright_index := Colours.nearest_eye_index(Colours.triple_colour(bright_eye))
	var limited := Colours.eyes({"eyes": bright_index, "eye_hue": bright_eye.x, "eye_sat": bright_eye.y, "eye_light": bright_eye.z}, FEMALE)
	expect(limited.custom and limited.limited and limited.pigment.ok_hsl_l <= Colours.EYE_LIGHT_MAX + 1e-4
		and limited.pigment.ok_hsl_s <= Colours.EYE_SAT_MAX + 1e-4, "eye limits: lightness <= 0.80, saturation <= 0.92")

# R7: the garment window and the contrast floor, undertone-shifted skins too.
func check_garment_limits() -> void:
	var cases := 0
	for skin_look: Dictionary in [{"skin": 1}, {"skin": 2, "skin_tone": 60, "skin_undertone": 1}, {"skin": 4, "skin_tone": 150, "skin_undertone": 201}, {"skin": 0}]:
		var skin := Colours.skin_shown(skin_look, FEMALE)
		var skin_wire := Colours.quantise(skin)
		for part: String in Colours.PARTS:
			for offset: Vector3i in [Vector3i.ZERO, Vector3i(0, 0, 3), Vector3i(4, 0, -2), Vector3i(0, 0, 60), Vector3i(0, 0, -60)]:
				var wire := Vector3i(posmod(skin_wire.x - 1 + offset.x, 240) + 1, skin_wire.y, clampi(skin_wire.z + offset.z, 1, 101))
				var index := Colours.nearest_dye_index(Colours.triple_colour(wire), part)
				var look := skin_look.merged({part: index, part + "_hue": wire.x, part + "_sat": wire.y, part + "_light": wire.z})
				var resolved := Colours.garment(look, FEMALE, part)
				if not resolved.custom:
					continue
				cases += 1
				var lightness: float = (resolved.colour as Color).ok_hsl_l
				expect(lightness >= Colours.GARMENT_LIGHT_MIN - 1e-4 and lightness <= Colours.GARMENT_LIGHT_MAX + 1e-4,
					"%s lightness window (%.3f)" % [part, lightness])
				if part != "boots":
					expect(Colours.delta_e(resolved.colour, skin) >= Colours.GARMENT_CONTRAST - 1e-4,
						"%s stands out from skin %s by %.3f" % [part, str(skin_look), Colours.delta_e(resolved.colour, skin)])
	expect(cases >= 20, "garment limit cases exercised (%d)" % cases)

# C22: the measured hair tables (data/actors/hair_apparent.json): their source
# files unchanged (SHA-256), every path present for both sexes and all nine
# styles, the inverses exact on their own entries, out-of-reach scaling
# keeping the hue; then the forward-table form on a synthetic table.
func check_hair_tables() -> void:
	expect(FileAccess.file_exists(Colours.HAIR_TABLES_PATH), "hair_apparent.json is present")
	var file: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(Colours.HAIR_TABLES_PATH))
	var sources: Dictionary = file.get("sources", {})
	expect(sources.size() >= 20, "hair_apparent.json records its source files (%d)" % sources.size())
	for path: String in sources:
		var digest := _sha256(path)
		expect(digest == str(sources[path]), "%s is unchanged since the hair calibration (re-run tests/integration/hair_apparent_calibration.gd and tools/colour_calibration/fit_hair.py if not)" % path)
	var paths: Dictionary = file.get("paths", {})
	for raw: Variant in paths.values():
		for source: Variant in (raw as Dictionary).get("sources", []):
			expect(sources.has(source), "every entry's sources are hashed (%s)" % source)
	var shapes: Dictionary = file.get("shapes", {})
	for sex: String in ["female", "male"]:
		for style: int in range(1, 10):
			for s: int in [0, 25, 50, 75, 100]:
				expect(paths.has("%s/P3/%d/%d" % [sex, style, s]) and paths.has("%s/P4/%d/%d" % [sex, style, s]),
					"%s style %d: P3 and P4 measured at finish %d" % [sex, style, s])
			expect(paths.has("%s/P1/%d/50" % [sex, style]) and paths.has("%s/P2/%d/50" % [sex, style]),
				"%s style %d: P1 and P2 present" % [sex, style])
			for s: int in [0, 25, 50, 75, 100]:
				expect(shapes.has("%s/medium/%d/%d" % [sex, style, s]) and shapes.has("%s/high/%d/%d" % [sex, style, s]),
					"%s style %d: length and volume shape factors at finish %d" % [sex, style, s])
			for s: int in [12, 37, 49, 51, 63, 88]:
				expect(paths.has("%s/P3/%d/%d" % [sex, style, s]) and paths.has("%s/P4/%d/%d" % [sex, style, s]),
					"%s style %d: P3 and P4 measured at custom finish %d" % [sex, style, s])
		for beard: int in range(2, 6):
			expect(paths.has("%s/B1/%d/50" % [sex, beard]) and paths.has("%s/B2/%d/50" % [sex, beard]),
				"%s beard %d: B1 and B2 present" % [sex, beard])
	Colours.set_hair_tables({})
	var linear_worst := 0.0
	var model_worst := 0.0
	var hue_worst := 0.0
	var reached := 0
	var targets: Array[Vector3] = [Vector3(0.002, 0.0015, 0.001), Vector3(0.03, 0.012, 0.004), Vector3(0.09, 0.06, 0.02),
		Vector3(0.01, 0.04, 0.12), Vector3(0.2, 0.18, 0.15), Vector3(0.05, 0.13, 0.08)]
	for key: String in paths:
		var parts := key.split("/")
		var sex := parts[0]
		var path := parts[1]
		var style := int(parts[2])
		var s := float(parts[3])
		var entry := Colours.hair_table(sex, path, style, s)
		var skin_gain: Vector3 = Colours.SKIN_GAIN[sex]
		for target: Vector3 in targets:
			var result: Dictionary = Colours.hair_dye_linear(target, sex, path, style, s)
			var want := target * float(result.reach)
			if entry.has("model"):
				var shown := (Colours.model_mu(entry, result.dye) - (entry.floor as Vector3)) / skin_gain
				model_worst = maxf(model_worst, shown.distance_to(want))
			else:
				linear_worst = maxf(linear_worst, ((entry.gain as Vector3) * (result.dye as Vector3) / skin_gain).distance_to(want))
		var far: Dictionary = Colours.hair_dye_linear(Vector3(0.9, 0.55, 0.25), sex, path, style, s)
		if float(far.reach) < 1.0:
			reached += 1
			var shown_far := (Colours.model_mu(entry, far.dye) - (entry.floor as Vector3)) / skin_gain if entry.has("model") \
				else (entry.gain as Vector3) * (far.dye as Vector3) / skin_gain
			var a := Colours.linear_to_oklab(shown_far)
			var b := Colours.linear_to_oklab(Vector3(0.9, 0.55, 0.25))
			hue_worst = maxf(hue_worst, absf(rad_to_deg(atan2(a.z, a.y) - atan2(b.z, b.y))))
	expect(linear_worst < 1e-6, "linear inverses are exact on every measured entry (%.9f)" % linear_worst)
	expect(model_worst <= 1e-4, "the pigment model's inverse converges on every P4 entry (%.9f)" % model_worst)
	expect(reached > 0 and hue_worst <= 0.5, "out-of-reach scaling keeps hue on %d entries (%.3f deg)" % [reached, hue_worst])
	# Shape factors: 1 at 50 / 50, bilinear, used by every legacy hair path.
	expect(Colours.shape_factor("female", false, 3, 50, 50) == Vector3.ONE, "no shape correction at length and volume 50")
	var short := Colours.hair_dye_linear(Vector3(0.05, 0.03, 0.02), "female", "P2", 3, 50.0, 0, 0)
	var plain := Colours.hair_dye_linear(Vector3(0.05, 0.03, 0.02), "female", "P2", 3, 50.0, 50, 50)
	expect(not (short.dye as Vector3).is_equal_approx(plain.dye), "length and volume change a hairstyle's dye")
	# P2 is P1's response: at length and volume 50 it draws P1's dye, and off 50
	# only the shape factor scales it (a P2 gain of its own as well would count
	# the reshaping twice).
	for sex: String in ["female", "male"]:
		for style: int in range(1, 10):
			var a := Vector3(0.05, 0.03, 0.02)
			var p1_dye: Vector3 = Colours.hair_dye_linear(a, sex, "P1", style, 50.0).dye
			var p2_dye: Vector3 = Colours.hair_dye_linear(a, sex, "P2", style, 50.0, 50, 50).dye
			expect(p2_dye.is_equal_approx(p1_dye), "%s style %d: P2 at length and volume 50 is P1" % [sex, style])
			var shaped_dye: Vector3 = Colours.hair_dye_linear(a, sex, "P2", style, 50.0, 20, 80).dye
			var factor := Colours.shape_factor(sex, false, style, 20, 80, 50.0)
			expect((shaped_dye * factor).is_equal_approx(p1_dye),
				"%s style %d: a reshaped Classic hairstyle is P1 scaled by its shape factor once" % [sex, style])
	# A coarse grid (the finish positions other than Classic) takes the Classic
	# grid's curvature between its nodes, so it stays exact on its own nodes.
	for group: String in ["female/medium/3", "male/high/1"]:
		var coarse: Dictionary = shapes.get(group + "/25", {})
		var parts := group.split("/")
		var node := Colours._vector((coarse.get("factor", []) as Array)[0 * 3 + 2], Vector3.ONE)
		var drawn := Colours.shape_factor(parts[0], parts[1] == "high", int(parts[2]), 0, 100, 25.0)
		expect(drawn.is_equal_approx(node), "%s: the coarse grid at finish 25 is exact on its node (0, 100)" % group)
		var between := Colours.shape_factor(parts[0], parts[1] == "high", int(parts[2]), 20, 80, 25.0)
		var coarse_only := Colours._shape_grid(coarse, 20, 80)
		expect(not between.is_equal_approx(coarse_only), "%s: between its nodes it follows the Classic grid's curvature" % group)
	# The reference path R is P1 on the sex's module slot style.
	var reference := Colours.hair_dye_linear(Vector3(0.05, 0.03, 0.02), "male", "R")
	var p1 := Colours.hair_dye_linear(Vector3(0.05, 0.03, 0.02), "male", "P1", 1, 50.0)
	expect((reference.dye as Vector3).is_equal_approx(p1.dye), "R is male Parted P1")
	# A forward table (the other entry form): A(d) = 0.25 d^0.8 per channel on 7^3 nodes.
	var apparent := Vector3(0.05, 0.03, 0.02)
	Colours.set_hair_tables({"female/P1/3/50": {"gain": [0.30, 0.31, 0.32], "floor": [0.01, 0.01, 0.01]},
		"female/P3/3/25": {"gain": [0.20, 0.21, 0.22], "floor": [0.0, 0.0, 0.0]},
		"female/P3/3/50": {"gain": [0.40, 0.41, 0.42], "floor": [0.0, 0.0, 0.0]}})
	var dye: Vector3 = Colours.hair_dye_linear(apparent, "female", "P1", 3, 50.0).dye
	var skin_gain: Vector3 = Colours.SKIN_GAIN["female"]
	var shown := Vector3(0.30, 0.31, 0.32) * dye / skin_gain
	expect(shown.distance_to(apparent) < 1e-7, "linear inverse is exact")
	var between: Dictionary = Colours.hair_table("female", "P3", 3, 37.5)
	expect((between.gain as Vector3).is_equal_approx(Vector3(0.30, 0.31, 0.32)), "linear tables interpolate in s")
	var nodes := 7
	var table: Array = []
	for r: int in nodes:
		for g: int in nodes:
			for b: int in nodes:
				var node := Vector3(r, g, b) / float(nodes - 1)
				var d := Vector3(Colours._lin(node.x), Colours._lin(node.y), Colours._lin(node.z)) * Colours.D_MAX
				table.append([0.25 * pow(d.x, 0.8), 0.25 * pow(d.y, 0.8), 0.25 * pow(d.z, 0.8)])
	Colours.set_hair_tables({"male/P4/1/50": {"nodes": nodes, "dmax": Colours.D_MAX, "table": table}})
	var entry := Colours.hair_table("male", "P4", 1, 50.0)
	var worst := 0.0
	for target: Vector3 in [Vector3(0.02, 0.01, 0.005), Vector3(0.1, 0.08, 0.05), Vector3(0.2, 0.2, 0.2), Vector3(0.005, 0.03, 0.09)]:
		var result: Dictionary = Colours.hair_dye_linear(target, "male", "P4", 1, 50.0)
		worst = maxf(worst, Colours.table_apparent(entry, result.dye).distance_to(target * float(result.reach)))
	expect(worst <= 1e-4, "iterative inverse converges on its own table (%.9f)" % worst)
	Colours.set_hair_tables({})
	# A dye above 1 keeps its own material cache key.
	expect(Colours.colour_key(Color(1.2, 0.5, 0.3)) != Colours.colour_key(Color(1.4, 0.5, 0.3))
		and Colours.colour_key(Color(0.4, 0.5, 0.3)) == Color(0.4, 0.5, 0.3).to_html(), "colour keys: exact above 1, to_html below")


func _sha256(path: String) -> String:
	var bytes := FileAccess.get_file_as_bytes(path)
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(bytes)
	return context.finish().hex_encode()

# Rule B and the nearest legacy bytes older recipients see (R8).
func check_canonical() -> void:
	var look := {"skin": 1, "skin_tone": 43, "skin_undertone": 101, "hair": AppearanceVariants.pack_hair(3, 0),
		"hair_hue": 36, "hair_sat": 79, "hair_light": 19, "eyes": 0, "eye_hue": 104, "eye_sat": 87, "eye_light": 63,
		"shirt": 0, "shirt_hue": 19, "shirt_sat": 84, "shirt_light": 37, "hair_detail": 0, "hair_finish": 76}
	var saved := Colours.canonical(look, "female")
	expect(saved.skin == 2 and saved.skin_tone == 0 and saved.skin_undertone == 0, "a stop position saves as its palette skin")
	expect(AppearanceVariants.hair_color_index(saved.hair) == 2 and AppearanceVariants.hair_style(saved.hair) == 3
		and saved.hair_hue == 0, "a frozen hair triple saves as its palette colour, style kept")
	expect(saved.eyes == 1 and saved.eye_hue == 0 and saved.shirt == 4 and saved.shirt_hue == 0, "frozen eye and dye triples snap")
	expect(saved.hair_detail == 1 and saved.hair_finish == 0, "a finish on 75 saves as Tousled")
	var custom := {"skin": 1, "skin_tone": 60, "skin_undertone": 140, "hair": AppearanceVariants.pack_hair(1, 0),
		"hair_hue": 35, "hair_sat": 45, "hair_light": 19, "eyes": 0, "eye_hue": 110, "eye_sat": 80, "eye_light": 55,
		"pants": 0, "pants_hue": 20, "pants_sat": 70, "pants_light": 40, "hair_detail": 0, "hair_finish": 91}
	saved = Colours.canonical(custom, "male")
	expect(saved.skin == 2 and saved.skin_tone == 60 and saved.skin_undertone == 140, "a custom tone keeps its fields and the nearest skin")
	expect(AppearanceVariants.hair_color_index(saved.hair) == Colours.nearest_hair_index(Colours.triple_colour(Vector3i(35, 45, 19)), "male")
		and saved.hair_hue == 35, "a custom hair writes the nearest palette colour")
	expect(saved.hair_detail == 1 and saved.hair_finish == 91, "a custom finish writes the nearest enum")
	expect(saved.eyes == Colours.nearest_eye_index(Colours.triple_colour(Vector3i(110, 80, 55))), "a custom eye writes the nearest eye")
	expect(saved.pants == Colours.nearest_dye_index(Colours.triple_colour(Vector3i(20, 70, 40)), "pants"), "a custom dye writes the nearest dye")
	# What a develop-shaped (PC/2) recipient sees: the legacy bytes, and the guard
	# keeps the canonical look drawing its custom values.
	var resolved := Colours.resolve(saved, MALE)
	expect(resolved.skin.custom and resolved.hair.custom and resolved.eyes.custom and resolved.pants.custom and resolved.finish.custom,
		"the saved custom look draws its custom values")
	var v2 := Custom.decode(Custom.encode(saved, 2), 0)
	expect(v2.hair_detail == 1 and v2.hair_finish == 0 and v2.skin_tone == 0, "a PC/2 recipient sees the nearest enum, no colour fields")
	var eloria := Colours.canonical({"skin": 7, "skin_tone": 50, "skin_undertone": 30}, "female")
	expect(eloria.skin == 7 and eloria.skin_tone == 0 and eloria.skin_undertone == 0, "an Eloria swatch drops tone and undertone")

# Every legacy byte the client writes is one develop's pickers list (Human skin
# 1-9, the garment dropdowns without merged dyes; every eye and hair colour),
# so an older dressing room shows it and its Apply keeps it (cross-version
# review: Human pants 11 and Soft tan were rewritten, clearing the custom
# value). Soft tan's stop is golden tan's byte with its position, drawn as the
# authored skin.
func check_listed_bytes() -> void:
	var develop_skins := [1, 2, 3, 4, 5, 6, 7, 8, 9]
	var skin_list: Array = []
	for entry: Dictionary in AppearanceChoices.options("skin", "luminous"):
		skin_list.append(int(entry.id))
	skin_list.sort()
	expect(skin_list == develop_skins, "the Human skin list is develop's (%s)" % [skin_list])
	for part: String in Colours.PARTS:
		var listed: Array = []
		for entry: Dictionary in AppearanceChoices.options("wardrobe", "luminous", Colours.PARTS[part]):
			listed.append(int(entry.id))
		listed.sort()
		expect(Array(Colours.listed_dyes(part)) == listed, "%s listed dyes are the dropdown's (%s)" % [part, listed])
		var outside := 0
		var points := 0
		for hue: int in range(1, 241, 4):
			for sat: int in range(1, 102, 5):
				for light: int in range(1, 102, 5):
					var saved := Colours.canonical({part: 0, part + "_hue": hue, part + "_sat": sat, part + "_light": light}, "male")
					points += 1
					if not listed.has(int(saved[part])):
						outside += 1
		for index: int in 12:
			var frozen := Colours.frozen_dye(part, index)
			var saved := Colours.canonical({part: 0, part + "_hue": frozen.x, part + "_sat": frozen.y, part + "_light": frozen.z}, "male")
			points += 1
			if not listed.has(int(saved[part])):
				outside += 1
			if not listed.has(index):
				expect(saved[part + "_hue"] == frozen.x and Colours.garment(saved, MALE, part).custom,
					"%s dye %d's frozen value (merged) stays a drawn custom value" % [part, index])
		expect(outside == 0, "%s: every byte canonical writes is listed (%d of %d outside)" % [part, outside, points])
	var unlisted_skin := 0
	for tone: int in range(1, 202):
		for undertone: int in [0, 1, 60, 101, 140, 201]:
			var saved := Colours.canonical({"skin": 1, "skin_tone": tone, "skin_undertone": undertone}, "female")
			if not develop_skins.has(int(saved.skin)):
				unlisted_skin += 1
			# The guard keeps every canonical tone drawn custom (or as its stop).
			var drawn := Colours.skin(saved, FEMALE)
			if int(saved.skin_tone) >= 1 and not drawn.custom and not bool(drawn.get("authored", false)):
				unlisted_skin += 1
	expect(unlisted_skin == 0, "every skin tone saves a listed skin byte its guard draws (%d bad)" % unlisted_skin)
	for sex: String in ["female", "male"]:
		var config := FEMALE if sex == "female" else MALE
		var saved := Colours.canonical({"skin": 1, "skin_tone": Colours.SOFT_TAN_POSITION}, sex)
		expect(saved.skin == 2 and saved.skin_tone == Colours.SOFT_TAN_POSITION and saved.skin_undertone == 0,
			"%s: the Soft tan stop saves as its position on golden tan" % sex)
		var drawn := Colours.skin(saved, config)
		expect(not drawn.custom and drawn.authored and drawn.index == 0 and Colours.skin_shown(saved, config) == Colours.skin_shown({"skin": 0}, config),
			"%s: the saved Soft tan stop draws the authored skin (index 0)" % sex)
		expect(Colours.skin({"skin": 2, "skin_tone": 23, "skin_undertone": 60}, config).custom,
			"%s: Soft tan with an undertone is a custom tone" % sex)
		expect(not Colours.skin({"skin": 0, "skin_tone": 20}, config).custom and Colours.skin({"skin": 1, "skin_tone": 20}, config).custom,
			"%s: tone 20 is drawn on pale beige's byte, guarded on skin 0" % sex)
	var untouched := Colours.canonical({"skin": 0}, "male")
	expect(untouched.skin == 0 and untouched.skin_tone == 0, "a save's own Soft tan (skin 0, no tone) is kept")

# C20: the NPC catalogue's looks stay palette looks (no colour key, or one whose
# legacy byte is its nearest value), so NPCs draw as on develop.
func check_npc_catalogue() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/npc_characters.json"))
	expect(parsed is Dictionary or parsed is Array, "NPC catalogue loads")
	var entries: Array = []
	if parsed is Dictionary:
		for value: Variant in (parsed as Dictionary).values():
			if value is Array:
				entries.append_array(value as Array)
			elif value is Dictionary:
				for item: Variant in (value as Dictionary).values():
					if item is Dictionary:
						entries.append(item)
	elif parsed is Array:
		entries = parsed
	var looks := 0
	for entry: Variant in entries:
		if entry is not Dictionary:
			continue
		var look: Variant = (entry as Dictionary).get("appearance", (entry as Dictionary).get("look"))
		if look is not Dictionary:
			continue
		looks += 1
		var appearance := look as Dictionary
		for field: String in Custom.V3_COLOURS:
			if appearance.has(field) and int(appearance[field]) != 0:
				var config := MALE if int((entry as Dictionary).get("actor_type", 1)) == 1 else FEMALE
				expect(Colours.canonical(appearance, str(config.gender)).hash() == appearance.hash(),
					"NPC %s colour keys are canonical (legacy byte nearest)" % str((entry as Dictionary).get("name", "?")))
				break
	print("NPC catalogue: %d looks checked" % looks)

# The client's mirror of the server's clearing rule (colour model spec 3.4).
func check_clearing() -> void:
	var before := {"skin": 2, "skin_tone": 60, "skin_undertone": 30, "hair": AppearanceVariants.pack_hair(1, 2),
		"hair_hue": 35, "hair_sat": 45, "hair_light": 19, "eyes": 1, "eye_hue": 110, "eye_sat": 80, "eye_light": 55,
		"shirt": 4, "shirt_hue": 20, "shirt_sat": 80, "shirt_light": 40, "hair_detail": 1, "hair_finish": 91}
	var after := Colours.clear_replaced(before, before.merged({"hair": AppearanceVariants.pack_hair(3, 2)}, true))
	expect(after.hair_hue == 35, "a style-only hair change keeps the custom colour")
	after = Colours.clear_replaced(before, before.merged({"hair": AppearanceVariants.pack_hair(1, 3)}, true))
	expect(after.hair_hue == 0 and after.hair_sat == 0 and after.hair_light == 0, "a hair colour change clears the hair triple")
	after = Colours.clear_replaced(before, before.merged({"skin": 3}, true))
	expect(after.skin_tone == 0 and after.skin_undertone == 0 and after.eye_hue == 110, "a skin change clears tone and undertone only")
	after = Colours.clear_replaced(before, before.merged({"eyes": 2, "shirt": 5}, true))
	expect(after.eye_hue == 0 and after.shirt_hue == 0, "eye and shirt changes clear their triples")
	after = Colours.clear_replaced(before, before.merged({"hair_detail": 2}, true))
	expect(after.hair_finish == 0, "a hair_detail change clears hair_finish")
	after = Colours.clear_replaced(before, before.duplicate())
	expect(after == before, "an unchanged look keeps everything")
	after = Colours.clear_replaced(before, before.merged({"eyes": 2, "eye_hue": 112}, true))
	expect(after.eye_hue == 112, "a changed custom value with its byte is kept")
