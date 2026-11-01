extends SceneTree
var checks := 0
var failures := 0
func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)
func _initialize() -> void:
	var base := {"origin":[0.,1.7,0.],"axis":[0.,1.,0.],"cos":[1.02,.01],"sin":[.005]}
	var active := base.duplicate(true)
	active.upperSideInset={"insetMm":15.,"heightMm":[14.,22.],"sectorDegrees":[45.,65.,115.,135.]}
	for p: Vector3 in [Vector3(.1,1.7,0),Vector3(.1,1.714,0),Vector3(0,1.75,.1),Vector3(0,1.75,-.1)]:
		check(RLHeadwearFit._warp(p,active)==RLHeadwearFit._warp(p,base),"Band and front/back ornament must stay exact")
	var symmetric := {"origin":[0.,1.7,0.],"axis":[0.,1.,0.],"cos":[1.]}
	var fit := symmetric.duplicate(true);fit.upperSideInset=active.upperSideInset
	var right:=RLHeadwearFit._warp(Vector3(.1,1.73,0),fit)
	var left:=RLHeadwearFit._warp(Vector3(-.1,1.73,0),fit)
	check(right.is_equal_approx(Vector3(.085,1.73,0)),"Full inset must be physical and bounded")
	check(left.is_equal_approx(Vector3(-right.x,right.y,right.z)),"Both side sectors must be symmetric")
	var middle:=RLHeadwearFit._warp(Vector3(.1,1.718,0),fit)
	check(middle.x>.085 and middle.x<.1 and is_equal_approx(middle.y,1.718),"Height blend must be gradual and preserve axial height")
	var floor_fit:=fit.duplicate(true)
	floor_fit.upperSideInset.minRadiusMm=95.
	check(RLHeadwearFit._warp(Vector3(.1,1.73,0),floor_fit).is_equal_approx(Vector3(.095,1.73,0)),"Explicit skull radius floor must cap the inset")
	check(RLHeadwearFit._warp(Vector3(.09,1.73,0),floor_fit).is_equal_approx(Vector3(.09,1.73,0)),"The radius floor must never expand existing geometry")
	for config: Variant in [null,{},15.,{"insetMm":21,"heightMm":[14,22],"sectorDegrees":[45,65,115,135]}, {"insetMm":-1,"heightMm":[14,22],"sectorDegrees":[45,65,115,135]}, {"insetMm":15,"heightMm":[22,14],"sectorDegrees":[45,65,115,135]}, {"insetMm":15,"heightMm":[-1,22],"sectorDegrees":[45,65,115,135]}, {"insetMm":15,"heightMm":[14,22],"sectorDegrees":[65,45,115,135]}, {"insetMm":NAN,"heightMm":[14,22],"sectorDegrees":[45,65,115,135]}, {"insetMm":15,"heightMm":[14,INF],"sectorDegrees":[45,65,115,135]}, {"insetMm":15,"heightMm":[14,22],"sectorDegrees":[45,65,"bad",135]}]:
		var invalid:=base.duplicate(true);invalid.upperSideInset=config
		var p:=Vector3(.1,1.73,0)
		check(RLHeadwearFit._warp(p,invalid)==RLHeadwearFit._warp(p,base),"Invalid optional configuration must preserve old fit")
	for invalid_floor: Variant in [NAN,INF,-1.,201.,"bad"]:
		var invalid:=base.duplicate(true);invalid.upperSideInset=active.upperSideInset.duplicate(true);invalid.upperSideInset.minRadiusMm=invalid_floor
		var p:=Vector3(.1,1.73,0)
		check(RLHeadwearFit._warp(p,invalid)==RLHeadwearFit._warp(p,base),"Invalid radius floor must fail closed")
	for degrees: int in range(-180,181,15):
		for height: float in [-.02,0.,.01,.02,.04]:
			var p:=Vector3(sin(deg_to_rad(float(degrees)))*.1,1.7+height,cos(deg_to_rad(float(degrees)))*.1)
			var old:=RLHeadwearFit._warp(p,base)
			var r:=RLHeadwearFit._warp(p,active)
			check(old.distance_to(r)<=.015001,"Inset exceeded its configured displacement")
			var no_op:=base.duplicate(true);no_op.upperSideInset={}
			check(RLHeadwearFit._warp(p,no_op)==old,"Existing path must remain bit exact")
	print("HEADWEAR_UPPER_SIDE_INSET_TESTS ",checks," checks, ",failures," failures")
	quit(0 if failures==0 else 1)
