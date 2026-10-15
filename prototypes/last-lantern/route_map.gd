extends Control

var q

func point(at: Array) -> Vector2:
	return Vector2(22+float(at[0])*4.4,558-float(at[1])*4.4)

func _draw() -> void:
	if q == null:
		return
	draw_rect(Rect2(Vector2.ZERO,size),Color("112c38"))
	for y in range(120):
		for x in range(120):
			if int(q.layout.walkGrid[y*120+x]) > 0:
				draw_rect(Rect2(point([x,y]),Vector2(4.5,-4.5)),Color("3b5a51"))
	for route: Array in [q.layout.route,q.layout.shortcut]:
		for i in range(route.size()-1):
			draw_line(point(route[i]),point(route[i+1]),Color("84958a"),3,true)
	for i in range(q.layout.areas.size()):
		var area: Dictionary = q.layout.areas[i]
		var p := point(area.at)
		draw_circle(p,13,Color("1b3238"))
		draw_string(ThemeDB.fallback_font,p+Vector2(-5,5),str(i+1),HORIZONTAL_ALIGNMENT_LEFT,-1,16,Color("dce4d4"))
	for gate: Dictionary in q.layout.gates:
		var p := point(gate.at)
		draw_line(p-Vector2(10,0),p+Vector2(10,0),Color("719784") if q.has_flag(gate.requires) else Color("d79366"),5)
	var target: Dictionary = q.target(q.current().target)
	draw_circle(point(target.approach),8,Color("f0c47c"))
	draw_circle(point(q.state.tile),5,Color.WHITE)
	var names := ["1  Grounded ferry", "2  Boathouse", "3  Tidal garden", "4  Repair shed",
		"5  Causeway", "6  Beacon steps", "7  Lantern room", "8  Return dock"]
	for i in range(names.size()):
		draw_string(ThemeDB.fallback_font,Vector2(20,23+i*21),names[i],HORIZONTAL_ALIGNMENT_LEFT,-1,15,Color("d6e2e0"))
	draw_string(ThemeDB.fallback_font,Vector2(546,27),"N",HORIZONTAL_ALIGNMENT_LEFT,-1,17,Color("f0c47c"))
