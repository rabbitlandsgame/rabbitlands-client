"""Author the Lantern Reach blockout and its quest from one set of targets.

Pure Python. Rebuild with `python build_map.py`. Outputs a native world package,
an EWCG walk grid, an ESCG server grid, and the prototype's quest data. Nothing
is added to the live map registry or server configuration.
"""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
import random
import struct

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "package"
SIZE = 120
AREAS = [
    ("arrival", "Grounded ferry", 17, 19, 10, 8),
    ("shelter", "Caldus's boathouse", 32, 32, 10, 9),
    ("garden", "Tidal garden", 24, 54, 10, 12),
    ("workshop", "Repair shed", 46, 70, 11, 10),
    ("causeway", "Hold the path", 67, 53, 9, 8),
    ("rest", "Beacon steps", 83, 70, 9, 8),
    ("beacon", "Lantern room", 95, 96, 11, 10),
    ("dock", "Return dock", 102, 24, 9, 8),
]
ROUTE = [(17, 19), (32, 32), (30, 44), (24, 54), (29, 65),
         (46, 70), (55, 65), (61, 57), (67, 53), (76, 60),
         (83, 70), (85, 84), (95, 96)]
SHORTCUT = [(95, 96), (108, 91), (109, 73), (109, 49), (102, 24)]
# Each gate spans the entire narrow connector. The walk grid stays static;
# gate cells are additional blockers until their corresponding fact is true.
GATES = [
    {"id": "causeway_gate", "label": "The causeway", "at": [57, 62],
     "bounds": [53, 60, 61, 64], "requires": "crafted"},
    {"id": "beacon_gate", "label": "The upper climb", "at": [85, 82],
     "bounds": [80, 81, 90, 84], "requires": "prepared"},
    {"id": "return_gate", "label": "The return stair", "at": [109, 85],
     "bounds": [104, 83, 114, 86], "requires": "lit"},
]


def target(key, label, kind, at, approach, **extra):
    return {"id": key, "label": label, "kind": kind, "tile": list(at),
            "approach": list(approach), **extra}


TARGETS = [
    target("nesh", "Nesh's lantern", "guide", (22, 24), (21, 23)),
    target("caldus", "Ferryman Caldus", "npc", (34, 34), (33, 32)),
    target("chart", "The keeper's chart", "information", (36, 37), (36, 35)),
    target("reed", "Reed", "harvest", (21, 54), (23, 54), item="Reed", quota=3, objectId=7001),
    target("quartz", "Quartz", "harvest", (28, 59), (27, 57), item="Quartz", quota=1, objectId=7002),
    target("lower_cache", "Keeper's cache", "storage", (44, 72), (44, 70), objectId=7010),
    target("bench", "Repair bench", "manufacturing", (49, 73), (49, 71), objectId=7011),
    target("boar", "Storm-frightened boar", "combat", (68, 54), (66, 53), objectId=7020),
    target("bag", "Supplies on the path", "loot", (68, 54), (66, 53), objectId=7021),
    target("rest", "Catch your breath", "rest", (83, 70), (82, 70)),
    target("upper_cache", "Lantern cache", "storage", (91, 95), (89, 94), objectId=7030),
    target("housing", "The dark beacon", "beacon", (97, 98), (95, 97), objectId=7031),
    target("dock", "Caldus's galley counter", "merchant", (103, 26), (101, 26), objectId=7040),
    target("dock_cache", "Dock cache", "storage", (105, 29), (103, 28), objectId=7042),
    target("ferry", "The boat you saved", "departure", (106, 21), (104, 22), objectId=7041),
]


def step(key, scene, objective, destination, condition, hint, voice="", **extra):
    return {"id": key, "scene": scene, "objective": objective, "target": destination,
            "condition": condition, "hint": hint, "voice": voice, **extra}


STEPS = [
    step("first_steps", 1, "Follow Nesh's lantern", "nesh", ["flag", "arrived"],
         "Click the ground to walk. Right-drag rotates the camera; scroll to zoom.",
         "Nesh: Over here. Follow my lantern."),
    step("ask_caldus", 2, "Talk to Caldus in the boathouse", "caldus", ["flag", "supplied"],
         "Click Caldus. He has the supplies for the climb.",
         "Caldus: That boat will follow our light. There isn't a light."),
    step("chart", 2, "Read the keeper's chart", "chart", ["flag", "chart_read"],
         "Click the chart beside Caldus. Your quest log keeps the current instruction.",
         "Nesh: Reeds for the shutters. Quartz for the lantern. The shore kept enough."),
    step("map", 2, "Open the map", "chart", ["flag", "map_opened"],
         "Press Tab or click Map. The gold marker matches the lantern in the world."),
    step("reeds", 3, "Gather 3 Reed", "reed", ["harvest", "Reed", 3],
         "Click the exposed Reed patch. Harvesting repeats and stops at three."),
    step("quartz", 3, "Mine 1 Quartz", "quartz", ["harvest", "Quartz", 1],
         "Your Pickaxe is in your pack. Minerals require the right tool."),
    step("store_reed", 4, "Store the 3 Reed in the keeper's cache", "lower_cache", ["storage", "Reed", 3],
         "Click the cache. Select Reed in your pack, then Deposit.",
         "Nesh: The lantern upstairs uses the same cache seal. Leave the repair parts here."),
    step("store_quartz", 4, "Store the Quartz", "lower_cache", ["storage", "Quartz", 1],
         "Deposit the Quartz too. Both caches share the same contents."),
    step("take_plank", 4, "Withdraw 1 Wood Plank", "lower_cache", ["inventory", "Wood Plank", 1],
         "Take the plank from the cache's crafting supplies."),
    step("take_cloth", 4, "Withdraw 1 Cloth Roll", "lower_cache", ["inventory", "Cloth Roll", 1],
         "Take the cloth for your torch."),
    step("take_hatchet", 4, "Withdraw the Hatchet", "lower_cache", ["inventory", "Hatchet", 1],
         "The Hatchet is a tool. Crafting uses the materials but keeps the tool."),
    step("torch", 4, "Make a Torch", "bench", ["flag", "crafted"],
         "Open Manufacturing at the bench: 1 Wood Plank + 1 Cloth Roll, with a Hatchet.",
         "Nesh: Plank, cloth and a steady hand. I'll help you with the first one."),
    step("sword", 5, "Equip your Sword", "boar", ["equipped", "Sword"],
         "Open Inventory and equip the Sword before approaching the boar.",
         "Nesh: Shield up. I'll keep him clear."),
    step("shield", 5, "Equip your Shield", "boar", ["equipped", "Shield"],
         "Equip the Shield in your other hand. Attacks and defense happen automatically."),
    step("hold_path", 5, "Clear the causeway", "boar", ["flag", "defeated"],
         "Click the boar to attack. Click open ground to retreat. Nesh can help you recover."),
    step("loot", 5, "Take the boar's supplies", "bag", ["flag", "looted"],
         "Take the Raw Meat from the bag. Auto-gather also completes this step."),
    step("landing", 6, "Reach the sheltered landing", "rest", ["flag", "rested"],
         "Follow the path up to Nesh's lantern.", "Nesh: Eat. You did the hard part."),
    step("food", 6, "Recover your food to 35 or more", "rest", ["food", 35],
         "Open Inventory and eat Bread. Positive food supports health and ether recovery."),
    step("attribute", 6, "Spend a pickpoint on Matter or Carry", "rest", ["flag", "spent"],
         "Open Statistics. Matter increases health; Carry increases pack capacity. Either advances.",
         "Nesh: Decide what will help you on the road. Then we'll finish the climb."),
    step("retrieve_reed", 7, "Withdraw your 3 Reed from the upper cache", "upper_cache", ["inventory", "Reed", 3],
         "The same seal. The same supplies. Take the Reed upstairs."),
    step("retrieve_quartz", 7, "Withdraw your Quartz", "upper_cache", ["inventory", "Quartz", 1],
         "Take the Quartz, then approach the beacon housing."),
    step("repair", 7, "Repair the beacon housing", "housing", ["flag", "repaired"],
         "Use the housing to fit the shutters and Quartz. This uses 3 Reed and 1 Quartz.",
         "Caldus, below: The bell! They're nearly on the rocks!"),
    step("light", 7, "Light the beacon with your Torch", "housing", ["flag", "lit"],
         "Use your crafted Torch. The boat is waiting for your light.",
         "Nesh: Your flame. Go on."),
    step("return", 8, "Take the return stair to the dock", "dock", ["flag", "returned"],
         "The eastern shortcut is open. Follow it down to the saved boat.",
         "Nesh: This seal was cut, not broken by the storm. We'll show Ilyon."),
    step("sell", 8, "Sell 1 Raw Meat to Caldus", "dock", ["flag", "sold"],
         "The galley pays 10 gold for this meat. Sell once at Caldus's counter.",
         "Caldus: Fresh meat for the galley? Take bread for the crossing."),
    step("buy", 8, "Buy Bread for the crossing", "dock", ["flag", "bought"],
         "Bread costs 8 gold, leaving you 2. This is a normal NPC trade, without another player."),
    step("depart", 8, "Board the boat to Four Gates", "ferry", ["flag", "departed"],
         "Choose Ready for Four Gates, or take one more look. The beacon will stay lit.",
         "Caldus: You got them home. Come on. The road is yours."),
]


def distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0, min(1, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / (dx*dx+dy*dy)))
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)


def road_distance(p, route=ROUTE):
    return min(distance(p, a, b) for a, b in zip(route, route[1:]))


def ground(x, y):
    # The upper route gains height gradually; the return stair descends with it.
    return round((0.4 + max(0, y-67)*0.085) / 0.2) * 0.2


def is_land(x, y):
    return (any(((x-cx)/rx)**2 + ((y-cy)/ry)**2 <= 1 for _, _, cx, cy, rx, ry in AREAS)
            or road_distance((x, y)) <= 3.5 or road_distance((x, y), SHORTCUT) <= 3)


class GLB:
    def __init__(self):
        self.blob = bytearray()
        self.group = ""
        self.batches = {}
        self.uv_scales = {}
        self.doc = {"asset": {"version": "2.0", "generator": "Eloria Lantern Reach coastal art"},
                    "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [],
                    "materials": [], "accessors": [], "bufferViews": [], "buffers": []}

    def material(self, name, color, glow=False, texture=None, normal=None, uv_scale=.5, roughness=.88, metallic=0):
        m = {"name": name, "doubleSided": True,
             "pbrMetallicRoughness": {"baseColorFactor": [*color, 1], "metallicFactor": metallic, "roughnessFactor": roughness}}
        if texture:
            m["pbrMetallicRoughness"]["baseColorTexture"] = {"index": self.texture(texture)}
        if normal:
            m["normalTexture"] = {"index": self.texture(normal), "scale": .65}
        if glow:
            m["emissiveFactor"] = color
        self.doc["materials"].append(m)
        index = len(self.doc["materials"])-1
        self.uv_scales[index] = uv_scale
        return index

    def texture(self, path):
        while len(self.blob) % 4:
            self.blob.append(0)
        content = Path(path).read_bytes()
        view = len(self.doc["bufferViews"])
        self.doc["bufferViews"].append({"buffer":0,"byteOffset":len(self.blob),"byteLength":len(content)})
        self.blob.extend(content)
        image = len(self.doc.setdefault("images",[]))
        self.doc["images"].append({"bufferView":view,"mimeType":"image/png","name":Path(path).stem})
        self.doc.setdefault("samplers",[{"magFilter":9729,"minFilter":9987,"wrapS":10497,"wrapT":10497}])
        textures = self.doc.setdefault("textures",[])
        textures.append({"source":image,"sampler":0})
        return len(textures)-1

    def accessor(self, data, width, component=5126):
        while len(self.blob) % 4:
            self.blob.append(0)
        start = len(self.blob)
        flat = [v for row in data for v in row] if width > 1 else data
        self.blob.extend(struct.pack("<" + ("f" if component == 5126 else "I") * len(flat), *flat))
        view = len(self.doc["bufferViews"])
        self.doc["bufferViews"].append({"buffer": 0, "byteOffset": start, "byteLength": len(self.blob)-start})
        acc = {"bufferView": view, "componentType": component, "count": len(data),
               "type": {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4"}[width]}
        if width == 3:
            acc.update(min=[min(row[i] for row in data) for i in range(3)],
                       max=[max(row[i] for row in data) for i in range(3)])
        self.doc["accessors"].append(acc)
        return len(self.doc["accessors"])-1

    def mesh(self, name, vertices, faces, material, colors=None):
        normals = []
        expanded = []
        uv, tint = [], []
        for face in faces:
            a, b, c = [vertices[i] for i in face]
            u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
            n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
            length = math.sqrt(sum(t*t for t in n)) or 1
            expanded.extend((a, b, c))
            normals.extend([[t/length for t in n]]*3)
            axis = max(range(3), key=lambda i: abs(n[i]))
            axes = (0,2) if axis == 1 else ((0,1) if axis == 2 else (2,1))
            scale = self.uv_scales.get(material,.5)
            uv.extend([(vertices[i][axes[0]]*scale,vertices[i][axes[1]]*scale) for i in face])
            tint.extend([colors[i] if colors else (1,1,1,1) for i in face])
        if not expanded:
            return
        if self.group:
            batch = self.batches.setdefault((self.group,material), [[],[],[],[]])
            for dest, values in zip(batch,[expanded,normals,uv,tint]):
                dest.extend(values)
            return
        self.emit_mesh(name,expanded,normals,uv,tint,material)

    def emit_mesh(self,name,expanded,normals,uv,tint,material):
        primitive = {"attributes": {"POSITION": self.accessor(expanded, 3),
                                    "NORMAL": self.accessor(normals, 3),
                                    "TEXCOORD_0":self.accessor(uv,2),
                                    "COLOR_0":self.accessor(tint,4)}, "material": material}
        index = len(self.doc["meshes"])
        self.doc["meshes"].append({"name": name, "primitives": [primitive]})
        self.doc["scenes"][0]["nodes"].append(len(self.doc["nodes"]))
        self.doc["nodes"].append({"name": name, "mesh": index})

    def box(self, name, x, y, z, w, h, d, material):
        v = [(x+sx*w/2, y+sy*h/2, z+sz*d/2) for sx, sy, sz in
             [(-1,-1,-1),(1,-1,-1),(1,-1,1),(-1,-1,1),(-1,1,-1),(1,1,-1),(1,1,1),(-1,1,1)]]
        self.mesh(name, v, [(1,2,0),(2,3,0),(6,5,4),(7,6,4),(5,1,0),(4,5,0),
                            (6,2,1),(5,6,1),(7,3,2),(6,7,2),(4,0,3),(7,4,3)], material)

    def cylinder(self, name, x, y, z, radius, height, material, sides=12, top=None):
        top = radius if top is None else top
        v = [(x+math.cos(i*math.tau/sides)*r, y+up, z+math.sin(i*math.tau/sides)*r)
             for r, up in [(radius, 0), (top, height)] for i in range(sides)]
        v.extend([(x,y,z),(x,y+height,z)])
        f = []
        for i in range(sides):
            j = (i+1) % sides
            f += [(i,j,sides+j),(i,sides+j,sides+i),(2*sides,j,i),(2*sides+1,sides+i,sides+j)]
        self.mesh(name,v,[(c,b,a) for a,b,c in f],material)

    def write(self, path):
        for (group,material),values in self.batches.items():
            self.emit_mesh(group+"_"+str(material),*values,material)
        self.batches.clear()
        self.doc["buffers"] = [{"byteLength": len(self.blob)}]
        encoded = json.dumps(self.doc, separators=(",", ":")).encode()
        encoded += b" " * (-len(encoded)%4)
        self.blob += b"\0" * (-len(self.blob)%4)
        path.write_bytes(struct.pack("<4sII", b"glTF", 2, 28+len(encoded)+len(self.blob))
                         + struct.pack("<I4s", len(encoded), b"JSON") + encoded
                         + struct.pack("<I4s", len(self.blob), b"BIN\0") + self.blob)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    from types import SimpleNamespace
    from art_authoring import author_world, runtime_assets
    g = GLB()
    spec = SimpleNamespace(SIZE=SIZE, ROUTE=ROUTE, SHORTCUT=SHORTCUT, TARGETS=TARGETS, GATES=GATES,
                           ground=ground, is_land=is_land, road_distance=road_distance)
    grid, blockers, art = author_world(g, spec)
    # Targets use ground-level approach tiles, never the scenery's center.
    for t in TARGETS:
        x,y=t["approach"]
        assert grid[y*SIZE+x], f"blocked approach: {t['id']}"
    g.write(OUT/"world.glb")
    art["provenance"] = runtime_assets(OUT, GLB)
    art["worldTriangles"] = sum(a["count"] for a in g.doc["accessors"] if a.get("type") == "VEC3" and "min" in a) // 6
    art["worldMeshNodes"] = len(g.doc["nodes"])
    (OUT/"art.json").write_text(json.dumps(art, indent=2)+"\n")
    # Native EWCG-v2 uses half-metre cells. Duplicate each server tile into its
    # four authored cells so the existing resampler can consume this package.
    fine = bytearray()
    for y in range(SIZE):
        row = bytes(v for v in grid[y*SIZE:(y+1)*SIZE] for _ in range(2))
        fine.extend(row+row)
    collision=struct.pack("<4sHHII",b"EWCG",2,0,SIZE*2,SIZE*2)+fine
    (OUT/"collision.bin").write_bytes(collision)
    (OUT/"lantern_reach.escg.gz").write_bytes(gzip.compress(
        struct.pack("<4sHHI",b"ESCG",1,200,SIZE)+grid,mtime=0))
    layout={"id":"lantern_reach","name":"Lantern Reach","size":SIZE,
            "draft":True,"spawn":[17,20],"areas":[{"id":a,"name":b,"at":[x,y],"radii":[rx,ry]}
            for a,b,x,y,rx,ry in AREAS],"route":ROUTE,"shortcut":SHORTCUT,
            "gates":GATES,"targets":TARGETS,"blockers":blockers,
            "walkGrid":list(grid),"heightOrigin":-2.2,"heightStep":.2}
    (OUT/"layout.json").write_text(json.dumps(layout,indent=2)+"\n")
    quest={"id":"the_last_lantern","version":1,"status":"playable design prototype",
           "map":"lantern_reach","durationMinutes":[18,22],"private":True,
           "steps":STEPS,"starterKit":{"Sword":1,"Shield":1,"Pickaxe":1,"Bread":3},
           "cacheStock":{"Wood Plank":1,"Cloth Roll":1,"Hatchet":1},
           "recipe":{"output":"Torch","ingredients":{"Wood Plank":1,"Cloth Roll":1},"tools":["Hatchet"],"food":1},
           "trade":{"sellItem":"Raw Meat","sellQuantity":1,"sellPrice":10,"buyItem":"Bread","buyPrice":8},
           "reward":{"achievement":"Keeper of the First Light","repeatable":False},
           "handoff":{"map":"four_gates","npc":"Gate Warden Ilyon","objective":"Talk to Gate Warden Ilyon", "repeatOldIntro":False},
           "assistance":{"firstCraftGuaranteed":True,"toolBreakage":False,"lossOnDefeat":False,"noTimer":True},
           "notes":["The prototype simulates UI, combat and XP. Production World handlers are not connected.",
                    "Bread's 8-gold price and the Torch recipe match current server content. Meat's 10-gold galley sale is a one-time quest offer.",
                    "The handoff ends at a preview card; this draft never writes a live character or changes a server map."]}
    (OUT/"quest.json").write_text(json.dumps(quest,indent=2)+"\n")
    manifest={"schemaVersion":"1.0.0","assetVersion":"0.2.0",
              "asset":{"id":"lantern_reach","name":"Lantern Reach — draft","glb":"world.glb","units":"meters",
                       "coordinateSystem":{"handedness":"right","upAxis":"Y","northAxis":"-Z"},
                       "bounds":{"min":[-190,-2,-310],"max":[310,20,190]},
                       "playableBounds":{"min":[-.5,.4,-119.5],"max":[119.5,4,.5]},"serverCells":SIZE},
              "coordinateTransform":{"metresPerTile":1.0,"serverOrigin":[0,0],"origin":[-.5,0,.5],"walkingHeight":.4,"invertServerY":True},
              "spawnPoints":[{"id":"default","position":[17,.4,-20],"rotationDegrees":0}],
              "collision":{"binary":"collision.bin","format":"EWCG-v2","width":SIZE*2,"height":SIZE*2,
                           "cellMetres":.5,"heightEncoding":{"origin":-2.2,"step":.2,"zeroMeansBlocked":True}},
              "navigation":{"surfaceNodePrefixes":["Walk_"],"agentRadius":.4,"agentHeight":1.9,"maxSlopeDegrees":45},
              "landmarks":[{"id":a,"name":b,"position":[x,ground(x,y),-y]} for a,b,x,y,_,_ in AREAS],
              "interactives":[{"id":t["id"],"kind":t["kind"],"objectId":t.get("objectId"),
                               "position":[t["tile"][0],ground(*t["tile"]),-t["tile"][1]],
                               "serverTile":t["tile"],"approachTile":t["approach"]} for t in TARGETS],
              "draft":{"quest":"quest.json","layout":"layout.json","runtimeRegistration":False,
                       "collisionNote":"Native half-metre EWCG-v2. Four authored cells per one-metre server tile."}}
    (OUT/"world.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(f"Built Lantern Reach: {sum(bool(v) for v in grid)} walkable tiles; {len(STEPS)} objectives; {len(g.doc['nodes'])} mesh nodes.")


if __name__ == "__main__":
    build()
