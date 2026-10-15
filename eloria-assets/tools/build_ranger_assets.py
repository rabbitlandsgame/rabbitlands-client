"""Build original, editable low-poly ranger props; no external art dependencies.

Metres, Y up. Bow origin is the grip, +Z points toward the drawing hand.
Arrow origin is the nock, its point faces -Z. Flat facets, warm wood, leather,
antler tips and aged brass match the native fantasy equipment palette.
"""
from pathlib import Path
import json
import math
import struct

OUT = Path(__file__).resolve().parents[2] / "godot-client/assets/actors/native/equipment"


class Asset:
    def __init__(self, colors):
        self.data = bytearray()
        self.doc = {"asset": {"version": "2.0", "generator": "Eloria ranger asset authoring"},
                    "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [],
                    "bufferViews": [], "accessors": [], "materials": []}
        for name, color, metal in colors:
            self.doc["materials"].append({"name": name, "doubleSided": True,
                "pbrMetallicRoughness": {"baseColorFactor": [*color, 1],
                    "metallicFactor": metal, "roughnessFactor": .48 if metal else .82}})

    def array(self, values, kind):
        while len(self.data) % 4:
            self.data.append(0)
        packed = struct.pack("<" + "f" * sum(map(len, values)), *(v for row in values for v in row))
        view = len(self.doc["bufferViews"])
        self.doc["bufferViews"].append({"buffer": 0, "byteOffset": len(self.data), "byteLength": len(packed)})
        self.data.extend(packed)
        index = len(self.doc["accessors"])
        self.doc["accessors"].append({"bufferView": view, "componentType": 5126,
            "count": len(values), "type": kind,
            "min": list(map(min, zip(*values))), "max": list(map(max, zip(*values)))})
        return index

    def mesh(self, name, triangles, material):
        vertices, normals = [], []
        for a, b, c in triangles:
            u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
            n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
            length = math.sqrt(sum(x*x for x in n)) or 1
            vertices.extend([a, b, c])
            normals.extend([[x/length for x in n]] * 3)
        primitive = {"attributes": {"POSITION": self.array(vertices, "VEC3"),
            "NORMAL": self.array(normals, "VEC3")}, "material": material}
        self.doc["scenes"][0]["nodes"].append(len(self.doc["nodes"]))
        self.doc["nodes"].append({"name": name, "mesh": len(self.doc["meshes"])})
        self.doc["meshes"].append({"name": name, "primitives": [primitive]})

    def save(self, name):
        self.doc["buffers"] = [{"byteLength": len(self.data)}]
        raw = json.dumps(self.doc, separators=(",", ":")).encode()
        raw += b" " * (-len(raw) % 4)
        self.data.extend(b"\0" * (-len(self.data) % 4))
        result = struct.pack("<4sII", b"glTF", 2, 28 + len(raw) + len(self.data))
        result += struct.pack("<I4s", len(raw), b"JSON") + raw
        result += struct.pack("<I4s", len(self.data), b"BIN\0") + self.data
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / name).write_bytes(result)
        print(name, len(result), "bytes")


def tube(points, radii, sides=8):
    """Swept elliptical section, with flat faces and closed end caps."""
    rings = []
    for i, (x, y, z) in enumerate(points):
        previous, following = points[max(0, i-1)], points[min(len(points)-1, i+1)]
        dy, dz = following[1]-previous[1], following[2]-previous[2]
        length = math.hypot(dy, dz) or 1
        rx, ry = radii[i]
        rings.append([(x + rx*math.cos(t*math.tau/sides),
                       y - dz/length*ry*math.sin(t*math.tau/sides),
                       z + dy/length*ry*math.sin(t*math.tau/sides)) for t in range(sides)])
    triangles = []
    for first, second in zip(rings, rings[1:]):
        for i in range(sides):
            j = (i+1) % sides
            triangles.extend([(first[i], first[j], second[j]), (first[i], second[j], second[i])])
    for ring, centre in [(rings[0], points[0]), (rings[-1][::-1], points[-1])]:
        for i in range(sides):
            triangles.append((centre, ring[(i+1) % sides], ring[i]))
    return triangles


PALETTE = [("Yew heartwood", (.25, .115, .055), 0), ("Honey sapwood", (.60, .36, .14), 0),
           ("Wrapped oxhide", (.13, .072, .043), 0), ("Aged brass", (.54, .40, .19), .65),
           ("Antler tips", (.80, .73, .53), 0), ("Linen bowstring", (.71, .66, .50), 0),
           ("Forged steel", (.43, .51, .55), .8), ("Teal fletching", (.14, .37, .34), 0)]


def bow(name, recurve=False):
    asset = Asset(PALETTE)
    for sign, label in [(1, "Upper"), (-1, "Lower")]:
        points = [(0, sign*y, z) for y,z in [(.07,0),(.18,.025),(.32,.09),(.47,.18),(.59,.24),(.68,.18)]]
        if recurve:
            points[-2] = (0, sign*.57, .28)
            points[-1] = (0, sign*.64, .16)
        asset.mesh(label+"Limb", tube(points, [(.034,.021),(.035,.019),(.032,.016),(.025,.014),(.018,.012),(.011,.009)]), 0)
        asset.mesh(label+"Inlay", tube([(x,y,z-.018) for x,y,z in points[:-1]], [( .010,.002)]*5, 6), 1)
        asset.mesh(label+"Antler", tube(points[-2:], [(.020,.014),(.011,.010)]), 4)
    asset.mesh("Grip", tube([(0,-.09,0),(0,.09,0)], [(.039,.031)]*2), 2)
    for i in range(11):
        y = -.084+i*.016
        asset.mesh("GripWrap%02d" % i, tube([(0,y,0),(0,y+.005,0)], [(.040,.033)]*2), 1 if i in [0,10] else 2)
    for sign in [-1, 1]:
        asset.mesh("BrassCollar"+str(sign), tube([(0,sign*.085,0),(0,sign*.116,.005)], [(.040,.028)]*2), 3)
    tip_y, tip_z = (.64,.16) if recurve else (.68,.18)
    asset.mesh("RestString", tube([(0,-tip_y,tip_z),(0,0,tip_z),(0,tip_y,tip_z)], [(.002,.002)]*3, 4), 5)
    asset.save(name)


def arrow():
    asset = Asset(PALETTE)
    asset.mesh("Shaft", tube([(0,0,0),(0,0,-.99)], [(.009,.009),(.007,.007)]), 1)
    asset.mesh("Nock", tube([(0,0,.015),(0,0,-.045)], [(.012,.012)]*2), 4)
    tip, base = (0,0,-1.15), (0,0,-.98)
    edge = [(-.033,0,-1.0),(0,.009,-.98),(.033,0,-1.0),(0,-.009,-.98)]
    asset.mesh("Broadhead", [(tip,edge[i],edge[(i+1)%4]) for i in range(4)] +
               [(base,edge[(i+1)%4],edge[i]) for i in range(4)], 6)
    feathers = []
    for angle in [0, math.tau/3, math.tau*2/3]:
        x,y = math.cos(angle),math.sin(angle)
        a,b,c,d = (x*.009,y*.009,-.04),(x*.044,y*.044,-.065),(x*.04,y*.04,-.12),(x*.009,y*.009,-.19)
        feathers.extend([(a,b,c),(a,c,d)])
    asset.mesh("Fletching", feathers, 7)
    asset.save("ranger_arrow.glb")


if __name__ == "__main__":
    bow("amberwood_ranger_bow.glb")
    bow("sunmane_ranger_bow.glb", True)
    arrow()
