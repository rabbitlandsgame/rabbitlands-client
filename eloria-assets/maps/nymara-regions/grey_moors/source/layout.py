"""Grey Moors settlement, shore surveys and content geography."""
from __future__ import annotations
import math
import numpy as np
from amberwood import terrain as TER, routecraft as RC, civiccraft as CIV
from amberwood import moorcraft as MC, props as PROP
from region import Placement
import region as REG

# This court is on the west bank before the first wet crossing. Its low roof
# leaves the barrow's crowned ridge visible beyond the road.
REFUGE = (-16.0,-11.0)
DOORS = {"great-barrow-mouth":(114,-237),
         "peat-croft-door":(124,85), "warm-stone-door":(118,-216),
         "fifth-chamber-mouth":(371,-183)}
CONTENT_LAYOUT = {
    "services":[{"role":"information","position":[-7,3,3]},
                {"role":"storage","position":[-20,3,-10]},
                {"role":"crafting_station","position":[-12,3,-10]},
                {"role":"training","position":[-25,3,4]}],
    "npcs":{
        "Mora Fen":[-4,3,-6], "Pell Wick":[-16,3,-7],
        "Barrow Warden Cassa Loom":[108,4,-237],
        "Stone-Court Speaker Hurn":[118,9,-259],
        "Peat Reeve Ollam Skarr":[-66,3,-21],
        "Debt-Reader Maun Pell":[168,4,-194],
        "Crypt Sexton Ivar Coombe":[-84,3,-246],
        "Moorlight Watcher Sisi Farrow":[12,3,-315],
        "Pony Drover Teg Halloran":[-38,3,5],
        "Bog-Iron Smith Nella Doust":[-10,3,-7],
        "Orchid Gatherer Wenna Slee":[-83,5,53],
        "Standing-Stone Mason Colm Rethe":[341,3,-64],
        "Moor Chandler Perrin Wisk":[-23,3,-6],
        "Widow Carrow":[158,4,-239]},
    "roadClearance":4.0,
    "harvest":{
        "Peat":[[-78,-18,16],[144,-24,17],[258,-42,17]],
        "Orchid":[[-73,52,18],[93,25,19]],
        "Sap":[[-112,-47,17],[57,-167,19]],
        "Silverleaf":[[144,-124,22],[236,-206,22]],
        "Moss":[[35,-330,24]], "Reed":[[-39,62,17]]},
    "wildlife":{}
}
# Retain species and counts; their habitat supplies the danger gradient.
for species in ("amberhart","moor_pony","amber_lantern_moth","mossback_badger"):
    CONTENT_LAYOUT["wildlife"][species]=[[-110,-21,24],[20,31,22]]
for species in ("moor_heron","giant_mole","berry_bramble_boar","autumn_crown_stag"):
    CONTENT_LAYOUT["wildlife"][species]=[[130,55,25],[206,-31,24]]
for species in ("cobalt_ibex","frosthorn_elk","moss_horn_ram"):
    CONTENT_LAYOUT["wildlife"][species]=[[-121,-280,26],[335,-324,28]]
for species in ("moor_wisp_hound","moorland_dire_wolf","moss_armored_hound",
                "mossbound_hound","briarhide_wolf","mire_goblin","moonlit_unicorn"):
    CONTENT_LAYOUT["wildlife"][species]=[[-43,-178,29],[277,-117,29]]
for species in ("mossbound_stone_golem","spectral_forest_knight","shadow_warg",
                "nightweave_spider","black_iron_death_knight","moors_spectral_knight",
                "spectral_moors_knight"):
    CONTENT_LAYOUT["wildlife"][species]=[[219,-278,30],[75,-328,28]]

def prepare(t):
    # Smooth shoulders preserve the low natural relief outside the worked yard.
    level=float(t.height_at(0,0))
    RC.grade_road(t,[(-27,-9),(-5,-9)],[level,level],width=20,shoulder=6,
                  surface=TER.CAUSEWAY,clearance=3)
    # The barrow court belongs on the crown; the ceremonial approach reaches
    # a door on the south flank instead of flattening a road through the mound.
    RC.grade_road(t,[(114,-224),(114,-242)],[4.6,5.5],width=6,shoulder=4,
                  surface=TER.CAUSEWAY,clearance=3)
    crown=float(t.height_at(*REG.ANCHORS["great_barrow"]))
    RC.grade_road(t,REG.ROUTES["crown_ascent"],
                  [5.8,7.8,9.2,12.8,crown,crown],width=3.4,shoulder=7,
                  surface=TER.MOOR_TRACK,clearance=2)
    t._moor_spans={}
    for name,points in {**REG.BOARDWALK_ROUTES,**REG.BRIDGE_ROUTES,
                        "ferry_jetty":np.array([[-60,72],[-60,89]])}.items():
        pts=np.asarray(points,dtype=float)
        height=[max(2.3,float(t.height_at(*p))+0.18) for p in pts]
        if name=="ferry_jetty":height=[2.7,1.65]
        t._moor_spans[name]=(pts,height)
    # All through roads use their real stations and preserve dry ground. The
    # deck rebate below removes only ground under the surveyed walking skin.
    for name,points in REG.ROUTES.items():
        heights=[max(1.8,float(t.height_at(*p))) for p in points]
        if name=="jetty_track":continue
        RC.grade_road(t,points,heights,width=4.6 if "road" in name else 3.6,
                      shoulder=3.5,surface=TER.CAUSEWAY if "causeway" in name
                      or name=="haven_road" else TER.MOOR_TRACK,clearance=2)
    for name,(pts,heights) in t._moor_spans.items():
        a,b=pts;run=b-a;length=float(np.linalg.norm(run));direction=run/length
        width=4.2 if name in REG.BRIDGE_ROUTES else 3.0
        for point,h,sign in ((a,heights[0],-1),(b,heights[1],1)):
            if name=="ferry_jetty" and sign==1:continue
            back=point+direction*sign*7
            RC.grade_road(t,[back,point],[max(1.8,float(t.height_at(*back))),h-0.16],
                          width=width+1.5,shoulder=3,surface=TER.MOOR_TRACK,clearance=2)
        along=((t.gx-a[0])*run[0]+(t.gz-a[1])*run[1])/length**2
        across=np.abs((t.gx-a[0])*run[1]-(t.gz-a[1])*run[0])/length
        mask=(along>=-2.5/length)&(along<=1+2.5/length)&(across<=width/2+3.0)
        seat=heights[0]+(heights[1]-heights[0])*along-0.18
        t.height=np.where(mask,np.minimum(t.height,seat),t.height)
        t.tree_block|=mask
    for x,z in DOORS.values():
        RC.grade_road(t,[(x,z+3),(x,z-2)],
                      [float(t.height_at(x,z))]*2,width=4,shoulder=2,
                      surface=TER.MOOR_TRACK,clearance=2)

def dress_crossings(build,seed):
    t=build.terrain
    for name,(pts,heights) in t._moor_spans.items():
        a,b=pts;length=float(np.linalg.norm(b-a))
        stone=name in REG.BRIDGE_ROUTES
        width=4.2 if stone else 3.0
        if stone:
            group=RC.graded_causeway([(0,heights[0],0),(0,heights[1],length)],
                    width=width,thickness=0.28,parapet=0.38,foot=-2,
                    stone="grey_drystone",paving="grey_causeway")
        else:
            group=CIV.sloped_boardwalk(length,*heights,width=width,foot=-2,
                    timber="grey_bog_timber",rope="timber_grey")
        node="Landmark_"+name
        group.translate(0,0,-length/2)
        build.add_mesh(name,group)
        build.place(Placement(node,name,(float((a[0]+b[0])/2),0,float((a[1]+b[1])/2)),
                    math.atan2(b[0]-a[0],b[1]-a[1]),kind="landmark"))
        if name in REG.BOARDWALK_ROUTES:
            index=list(REG.BOARDWALK_ROUTES).index(name);landmark=f"grey-boardwalk-{index}"
        elif stone:
            index=list(REG.BRIDGE_ROUTES).index(name);landmark=f"grey-causeway-bridge-{index}"
        else:landmark="grey-ferry-jetty"
        build.landmarks.append({"id":landmark,"node":node,"type":"bridge",
             "name":"Moor Ferry Jetty" if name=="ferry_jetty" else "Grey Moor Crossing",
             "position":[float((a[0]+b[0])/2),sum(heights)/2,float((a[1]+b[1])/2)]})
        ends=[[float(a[0]),heights[0],float(a[1])],[float(b[0]),heights[1],float(b[1])]]
        build.crossings.append({"id":name,"endpoints":ends})

def dress_refuge(build,seed):
    t=build.terrain
    x,z=REFUGE;y=float(t.height_at(x,z))
    refuge=CIV.roadside_shelter(stone="grey_drystone",
                  timber="grey_bog_timber",roof="grey_turf_roof")
    # Each wind wall blocks only its own stone box. The open service floor
    # must not inherit a circular blocker from the whole shelter's roof.
    for i,wall in enumerate(p for p in refuge.parts if p.material=="grey_drystone"):
        key=f"RefugeWall{i}";build.add_mesh(key,wall)
        build.place(Placement(key,key,(x,y,z),collides=True,kind="wall",
                              extras={"solidBox":True}))
    refuge.parts=[p for p in refuge.parts if p.material!="grey_drystone"]
    build.add_mesh("RoadRefuge",refuge)
    build.place(Placement("Landmark_RoadRefuge","RoadRefuge",(x,y,z),kind="landmark"))
    build.landmarks.append({"id":"grey-road-refuge","name":"The Peat Road Refuge",
             "node":"Landmark_RoadRefuge","type":"shelter","position":[x,y,z+4]})
    # Low windscreens frame the gate and a dry holding pen; open sides face
    # the service court so people, carts and ponies never occupy the road.
    for i,(x,z,length,angle) in enumerate([(-30,8,13,0),(-42,1,12,math.pi/2),
                                          (-35,-6,10,0)]):
        key=f"RefugeFence{i}";build.add_mesh(key,MC.peat_fence(length,seed+i))
        build.place(Placement(key,key,(x,float(t.height_at(x,z)),z),angle))
    for i,(x,z) in enumerate([(5,5),(-30,-2),(9,-8)]):
        key=f"RefugeLight{i}";build.add_mesh(key,MC.waymarker(2.7,seed+30+i))
        build.place(Placement(key,key,(x,float(t.height_at(x,z)),z)))
    build.add_mesh("RefugePeat",PROP.log_pile(length=2.2,rows=2,per_row=4,
                                            material="grey_bog_timber"))
    build.place(Placement("Prop_RefugeFuel","RefugePeat",(-23,float(t.height_at(-23,-12)),-12)))
    build.add_mesh("CoveBoat",PROP.rowing_boat(length=4.8,seed=seed+91)
                   .with_material("grey_bog_timber"))
    build.place(Placement("Prop_CoveBoat","CoveBoat",(-56,0.10,88),math.pi/2))
    build.notes.append("Working refuge, 12 surveyed wet crossings and cove ferry; barrow crown kept above the road.")
