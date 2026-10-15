"""Manymouth's surveyed timber roads, working waterfront and content districts."""
from __future__ import annotations
import math
import numpy as np
from amberwood import waterfront as WF, routecraft as RC, terrain as TER
from amberwood import stonework as SW, props as P
import region as REG
import deltakit as DK
import stiltkit as SK

# Existing platforms own their floor. Routes end at that rectangle's edge.
PLATFORMS={
    "town_hall":(5.1,5.1,18.), "market_hall":(8.1,5.1,20.),
    "town_quay":(7.5,5.5,34.), "great_arch":(9.,7.,28.),
    "overlook":(5.5,4.,-58.),
}
POINTS=dict(REG.ANCHORS,green_temple=(281.,-293.),cave_mouth=(207.,-2.5),lore_court=(326.,-106.))
WIDTH=3.8

def _section(centre,toward,width,radius,rectangle=None):
    """Two edge points, left/right relative to travel out of a landing."""
    c=np.asarray(centre,dtype=float);d=np.asarray(toward)-c[[0,2]]
    d/=np.linalg.norm(d);n=np.array([-d[1],d[0]])
    out=[]
    if rectangle:
        hx,hz,yaw=rectangle;yaw=math.radians(yaw)
        rot=np.array([[math.cos(yaw),-math.sin(yaw)],[math.sin(yaw),math.cos(yaw)]])
        local_d=rot@d
        spans=np.array([hx,hz])
        axis=int(np.argmin(np.where(abs(local_d)>1e-8,spans/np.maximum(abs(local_d),1e-8),np.inf)))
        hit=local_d*spans[axis]/abs(local_d[axis])
        side=1-axis
        hit[side]=np.clip(hit[side],-spans[side]+width/2+.05,spans[side]-width/2-.05)
        edge=np.zeros(2);edge[side]=width/2
        candidates=[rot.T@(hit-edge),rot.T@(hit+edge)]
        candidates.sort(key=lambda p:float(np.dot(p,n)))
        for point in candidates:
            p=c.copy();p[[0,2]]+=point;out.append(p)
    else:
        along=math.sqrt(radius*radius-width*width/4)
        for sign in (-1,1):
            p=c.copy();p[[0,2]]+=d*along+n*sign*width/2;out.append(p)
    return out

def walkway_network(build,seed):
    import populate as POP
    t=build.terrain;points=dict(POINTS);routes=[(a, "temple_quay" if a=="ruin_stelae" and b=="green_temple" else b) for a,b in POP.ROUTES]
    routes.append(("east_hamlet","lore_court"))
    # A water landing needs a visible connection to its bar. Choose the nearest
    # naturally dry patch; grading below only touches that existing dry land.
    original=t.height.copy()
    for name,p in list(points.items()):
        if name not in {v for edge in routes for v in edge}:continue
        if name in PLATFORMS or name=="green_temple":continue
        if float(t.height_at(*p))>=1.1:continue
        candidates=[]
        for radius in (16.,22.,28.):
            for angle in np.linspace(0,2*math.pi,24,endpoint=False):
                q=np.array(p)+radius*np.array([math.cos(angle),math.sin(angle)])
                direction=(q-p)/radius
                neighbours=[np.array(points[b if a==name else a])-p for a,b in routes if name in (a,b)]
                if any(np.dot(direction,v/np.linalg.norm(v))>.70 for v in neighbours):continue
                hs=[float(t.height_at(q[0]+dx,q[1]+dz)) for dx,dz in ((0,0),(2,0),(-2,0),(0,2),(0,-2))]
                if min(hs)>1.0 and max(hs)-min(hs)<1.0:
                    candidates.append((radius+max(hs)-min(hs),q))
        if candidates:
            q=min(candidates,key=lambda v:v[0])[1]
            key="shore_"+name;points[key]=tuple(q);routes.append((name,key))
    levels={name:max(1.75,float(t.height_at(*p))+.2) for name,p in points.items()}
    for name in ("stilt_town","town_hall","market_hall","town_quay","floating_market"):
        levels[name]=2.2
    levels["great_arch"]=.55
    levels["green_temple"]=float(t.height_at(*REG.ANCHORS["green_temple"]))
    for name in points:
        if name.startswith("shore_"):levels[name]=float(t.height_at(*points[name]))+.18
    centres={name:np.array([p[0],levels[name],p[1]]) for name,p in points.items()}
    radii={name:(7.5 if name=="stilt_town" else 2.5 if name.startswith("shore_") else 4.8) for name in points}
    for name in points:
        dirs=[math.atan2(points[b if a==name else a][1]-points[name][1],
                         points[b if a==name else a][0]-points[name][0])
              for a,b in routes if name in (a,b)]
        if len(dirs)>1 and name not in PLATFORMS:
            angles=np.sort(dirs);gap=min(np.diff(np.r_[angles,angles[0]+2*math.pi]))
            radii[name]=max(radii[name],WIDTH/(2*math.sin(gap/2))+.25)
    ports={name:[] for name in points};surveys=[];segments=[]
    for i,(a,b) in enumerate(routes):
        plan=np.array(POP._segments(points[a],points[b],seed+i*17),dtype=float)
        # The temple approach follows its southwest stair axis.
        distances=np.r_[0,np.cumsum(np.linalg.norm(np.diff(plan,axis=0),axis=1))]
        heights=np.interp(distances,[0,distances[-1]],[levels[a],levels[b]])
        stations=np.c_[plan[:,0],heights,plan[:,1]]
        first=_section(centres[a],plan[1],WIDTH,radii[a],PLATFORMS.get(a))
        last=_section(centres[b],plan[-2],WIDTH,radii[b],PLATFORMS.get(b))
        ports[a].append(first);ports[b].append(last)
        stations[0]=np.mean(first,axis=0);stations[-1]=np.mean(last,axis=0)
        if np.dot(stations[-1,[0,2]]-stations[0,[0,2]],plan[-1]-plan[0])<=0:
            raise ValueError("landing overlap: "+a+" to "+b)
        surveys.append((a,b,stations,(first,list(reversed(last)))))
        for p,q in zip(stations,stations[1:]):
            segments.append({"a":tuple(p[[0,2]]),"b":tuple(q[[0,2]]),
                             "level":float((p[1]+q[1])/2),
                             "angle":math.atan2(q[2]-p[2],q[0]-p[0]),"route":(a,b)})
    # Ramp the shore up to its landing, keeping every formerly wet cell wet.
    dry=original>.55
    for name,c in centres.items():
        radius=radii[name] if name not in PLATFORMS else max(PLATFORMS[name][:2])
        distance=np.hypot(t.gx-c[0],t.gz-c[2])
        blend=np.clip((radius+7-distance)/6,0,1);blend=blend*blend*(3-2*blend)
        t.height=np.where(dry,t.height*(1-blend)+(c[1]-.18)*blend,t.height)
        t.tree_block|=distance<radius+4
    # Recess the substrate. The deck skin and the terrain never share a plane.
    for a,b,stations,ends in surveys:
        plan=stations[:,[0,2]]
        lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(plan,axis=0),axis=1))]
        distance,along=TER._polyline_distance(t.gx,t.gz,plan)
        target=np.interp(along,lengths/lengths[-1],stations[:,1])-.40
        mask=distance<WIDTH/2+2.8
        t.height=np.where(mask,np.minimum(t.height,target),t.height)
        t.tree_block|=distance<WIDTH/2+4
        key="Survey_"+a+"__"+b
        build.add_mesh(key,WF.piled_route(stations,WIDTH,DK.TEAK,SK.ROPE,bed=t.height_at,ends=ends))
        build.place(REG.Placement(node=key,mesh=key,position=(0,0,0),kind="structure"))
    for name,c in centres.items():
        radius=radii[name]
        mask=np.hypot(t.gx-c[0],t.gz-c[2])<radius+1.2
        t.height=np.where(mask,np.minimum(t.height,c[1]-.32),t.height)
        if name in PLATFORMS:continue
        key="Landing_"+name
        build.add_mesh(key,WF.junction(c,ports[name],radius,DK.TEAK,
                                      foot=min(float(t.height_at(c[0],c[2]))-.5,-1)))
        build.place(REG.Placement(node=key,mesh=key,position=(0,0,0),kind="structure"))
    build.notes.append(f"Surveyed {len(surveys)} timber routes with {len(centres)} shared landing levels.")
    return {"levels":levels,"segments":segments,"points":points,"centres":centres,
            "surveys":surveys,"radii":radii}

def house_rows(build,seed,network,anchor,count,label):
    """Houses face the road and share its floor height; each has a short porch."""
    t=build.terrain;used=getattr(build,"_house_centres",[])
    available=[]
    for a,b,stations,_ in network["surveys"]:
        if anchor not in (a,b) or a.startswith("shore_") or b.startswith("shore_"):continue
        oriented=stations if a==anchor else stations[::-1]
        distance=0.
        for p,q in zip(oriented,oriented[1:]):
            length=float(np.linalg.norm((q-p)[[0,2]]))
            for along in np.arange(9.,length-5.,11.5):
                if distance+along>55:continue
                available.append((p+(q-p)*along/length,(q-p)/length))
            distance+=length
    placed=0
    for centre,d in available:
        for sign in (-1,1):
            if placed>=count:break
            side=np.array([-d[2]*sign,0,d[0]*sign])
            house=centre+side*7.6
            if any(np.linalg.norm((house-v)[[0,2]])<10.5 for v in used):continue
            if float(t.height_at(house[0],house[2]))>house[1]-.25:continue
            if any(np.linalg.norm(house[[0,2]]-np.array(REG.ANCHORS[k]))<13
                   for k in ("town_hall","market_hall","great_arch","paddy_tower","east_watch")):continue
            # Keep this porch clear of another branch of the network.
            if any(float(TER._polyline_distance(np.array(house[0]),np.array(house[2]),
                    s[:,[0,2]])[0])<6 for _,_,s,_ in network["surveys"]):continue
            key=f"RoadHouse_{placed%3}"
            if key not in build.meshes:
                build.add_mesh(key,SK.stilt_house(4.6,4.0,8.,seed+placed%3*13,storeys=1))
            facing=-side
            build.place(REG.Placement(node=f"{label}_house_{placed:02d}",mesh=key,
                 position=tuple(house),rotation_y=math.atan2(facing[0],facing[2]),
                 collides=True,kind="building"))
            near=centre+side*WIDTH/2;far=house-side*2.3
            porch=f"{label}_porch_{placed:02d}"
            build.add_mesh(porch,WF.piled_route([near,far],2.6,DK.TEAK,SK.ROPE,
                                                bed=t.height_at,rails=False))
            build.place(REG.Placement(node=porch,mesh=porch,position=(0,0,0),kind="structure"))
            used.append(house);placed+=1
    build._house_centres=used
    build.notes.append(f"{label}: {placed} separated houses facing their connected porches.")

def finish(build,seed,network):
    # The route landing replaces the old offset banyan platform. Towers stand
    # beside their landing, leaving the arrival and interior trigger unobstructed.
    kept=[]
    for p in build.placements:
        if p.node=="banyan_deck":continue
        if p.node in ("Landmark_PaddyTower","Landmark_EastWatch","Landmark_SouthShrine"):
            x,y,z=p.position;p.position=(x+8.,y,z+5.)
        if p.node in ("Landmark_MootHall","Landmark_MarketHall","Landmark_GreatArch"):
            p.collides=False
        kept.append(p)
    build.placements=[p for p in kept if not (p.kind in ("tree","foliage") and
        any(math.hypot(p.position[0]-x,p.position[2]-z)<18
            for x,z in (REG.ANCHORS["town_hall"],REG.ANCHORS["stilt_town"],REG.ANCHORS["floating_market"])))]
    lines=[s.tolist() for _,_,s,_ in network["surveys"]]
    RC.clear_walk_corridors(build,lines,{"tree":5.2,"foliage":4.2,"prop":2.6,"rock":3.5})
    # Two orderly mooring rows leave the landing and the through route open.
    build.placements[:]=[p for p in build.placements if not p.node.startswith("market_boat_")]
    fm=np.array(POINTS["floating_market"])
    for i,(dx,dz) in enumerate([(x,z) for x in (-18.,-9.,0.,9.) for z in (-11.,11.)]):
        x,z=fm+(dx,dz)
        if float(build.terrain.height_at(x,z))>-.5:continue
        key=f"awning_boat_{i%5}"
        build.place(REG.Placement(node=f"MooredMarketBoat_{i}",mesh=key,
                                  position=(x,-.16,z),rotation_y=math.pi/2,kind="prop"))
    rig=WF.lateen_rig(7.5,DK.TEAK,SK.CLOTH)
    boat=SW.group(P.rowing_boat(seed=seed+4500,length=7.8,beam_width=2.4),rig)
    build.add_mesh("PacketLateen",boat)
    build.place(REG.Placement(node="PacketLateen",mesh="PacketLateen",
                              position=(62.,-.16,-20.),rotation_y=.6,kind="prop"))
    build.notes.append("Market boats share two mooring rows; a lateen packet marks the working quay.")

def standing(build,anchor):
    c=build.network["centres"][anchor]
    if anchor=="town_hall":
        yaw=math.radians(18);return tuple(c+np.array([math.sin(yaw)*4.5,0,math.cos(yaw)*4.5]))
    return tuple(c)

CONTENT_LAYOUT={
    "services":[{"role":"information","position":[32,2.2,-46]},
                {"role":"storage","position":[31,2.2,-50]},
                {"role":"crafting_station","position":[39,2.2,-43]},
                {"role":"training","position":[41,2.2,-49]}],
    "roadClearance":2.2,
    "wildlife":{
        "mangrove_crab":[[-115,-130,34],[-117,39,30]],
        "delta_crocodile":[[83,-174,35],[172,94,35]],
        "floodmaw":[[209,-139,32],[252,-259,38]],
        "delta_mud_crab":[[-85,-231,30],[91,-353,30]],
        "manymouth_crab":[[-121,-324,28],[344,-175,30]],
        "swamp_heron":[[-42,-260,36],[49,-329,28]],
        "bronze_diving_beetle":[[-43,-267,38]],
        "saltmarsh_crocodile":[[171,94,38]],
        "viridian_basilisk":[[293,-300,38],[217,-229,30]],
        "drowned_pirate":[[-126,-321,55],[99,-348,55],[-115,-145,40]],
        "reed_mask_hunter":[[343,-174,38],[207,-138,34]],
        "drowned_lich_king":[[290,-309,44],[218,-229,34],[214,-18,32]],
        "mire_kelpie":[[82,-176,36],[-111,-144,34]]},
    "harvest":{
        "Pearl":[[-125,-326,35],[97,-351,32]],
        "Clay":[[-82,-230,32],[-42,-255,33]],
        "Lotus":[[-42,-263,38],[43,-329,30]],
        "Sap":[[78,-175,34],[207,-139,32]],
        "Lichen":[[221,-226,32],[301,-305,38]],
        "Venom Bulb":[[219,-140,35],[306,-311,38]],
        "Riverflax":[[-42,-261,36]],
        "Toadstool":[[79,-180,36],[204,-138,36]],
        "Kelp":[[-121,-323,40],[91,-354,34]],
        "Shell":[[-123,39,34],[288,58,35]],
        "Bog Iron":[[-118,-147,35],[220,-225,35]],
        "Watercress":[[-40,-260,38]]},

    "npcs":{
        "Mara Tide":[34,2.2,-43],"Jori Reed":[39,2.2,-52],
        "Tide Hall Speaker Nen-Ilsa":[30,2.2,-56],
        "Long Market Broker Cass Merrow":[13.5,2.2,-27],
        "Ferry Post Pilot Ruk-Tal":[54,2.2,-33],
        "Root Landing Elder Ba-Nuun":[81,2,-180],
        "Paddy Watch Sentry Ossa-Kel":[-12,2,-276],
        "Silt Measurer Ives Kanton":[-51,2,-258],
        "Labyrinth Guide Hess-Uru":[207,2,-2.5],
        "Green Temple Warden Vashi-Lo":[281,14.8,-293],
        "South Shrine Cantor Tem-Ossa":[72,2,123],
        "East Watch Runner Bel Kiddow":[363,2,-36],
        "Stelae Court Scribe Ann-Sesh":[326,2,-106],
        "Bund Warden Ilse":[-84,2,-234]},
}
