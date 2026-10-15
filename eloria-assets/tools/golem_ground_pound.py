"""Append a kneeling right-hand attack to the thirteen shipped golem rigs.

Run with Python + numpy. The original mesh, rig, materials and animation bytes
are retained. --output-dir stages GLBs for review; omit it to update the client.
The explicit limb maps cover the authored, UniRig and quadruped skeletons.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "tpose_bodies" / "vendor"))
import glbkit as g

CLIENT = Path(__file__).resolve().parents[2] / "godot-client"
CLIP = "Attack_Ground_Pound"
DURATION = 2.4
IMPACT = 0.88

# Arms and legs are anatomical right, left. Each chain is proximal to distal.
RIGS = {
    "amethyst_stone_golem": dict(root=24, pelvis=23, spine=[12, 10], head=1,
        arms=[[5, 4, 3, 2], [9, 8, 7, 6]], legs=[[22, 21, 20], [17, 16, 15]], forward=1),
    "frost_stone_golem": dict(root=23, pelvis=13, spine=[22, 3], head=2,
        arms=[[21, 20, 19, 18], [17, 16, 15, 14]], legs=[[7, 6, 5], [11, 10, 9]], forward=1),
    "river_stone_golem": dict(root=53, pelvis=52, spine=[41, 38], head=3,
        arms=[[37, 36, 35, 34], [27, 26, 25, 24]], legs=[[51, 50, 49], [46, 45, 44]], forward=1),
    "rune_stone_golem": dict(root=46, pelvis=44, spine=[35, 34], head=1,
        arms=[[17, 16, 15, 14], [33, 32, 31, 30]], legs=[[39, 38, 37], [43, 42, 41]], forward=1),
    "mossbound_stone_golem": dict(root=24, pelvis=24, spine=[13, 11], head=9,
        arms=[[6, 5, 4], [2, 1, 0]], legs=[[23, 22, 21], [18, 17, 16]], forward=1),
}


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / max(np.linalg.norm(v), 1e-12)


def rot(axis, angle):
    x, y, z = unit(axis)
    k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + np.sin(angle) * k + (1 - np.cos(angle)) * (k @ k)


def aim(a, b):
    a, b = unit(a), unit(b)
    dot = np.clip(a @ b, -1, 1)
    if dot > 1 - 1e-10:
        return np.eye(3)
    if dot < -1 + 1e-8:
        return rot(np.cross(a, [1, 0, 0] if abs(a[0]) < .9 else [0, 1, 0]), np.pi)
    return rot(np.cross(a, b), np.arccos(dot))


def cue(t, a, b):
    u = np.clip((t - a) / (b - a), 0, 1)
    return u * u * (3 - 2 * u)


def mix(a, b, u):
    return np.asarray(a) * (1 - u) + np.asarray(b) * u


def sample_local(j, blob, clip, time):
    trs = [dict(translation=n.get("translation", [0, 0, 0]),
                rotation=n.get("rotation", [0, 0, 0, 1]),
                scale=n.get("scale", [1, 1, 1])) for n in j["nodes"]]
    for channel in next(a for a in j["animations"] if a["name"] == clip)["channels"]:
        animation = next(a for a in j["animations"] if a["name"] == clip)
        sampler = animation["samplers"][channel["sampler"]]
        times = g.accessor(j, blob, sampler["input"]).ravel()
        values = g.accessor(j, blob, sampler["output"])
        i = max(0, min(int(np.searchsorted(times, time, side="right")) - 1, len(times) - 2))
        u = float(np.clip((time - times[i]) / max(times[min(i + 1, len(times)-1)] - times[i], 1e-8), 0, 1))
        path = channel["target"]["path"]
        if sampler.get("interpolation") == "CUBICSPLINE":
            dt = times[i+1] - times[i]
            value = ((2*u**3-3*u**2+1)*values[3*i+1] + (u**3-2*u**2+u)*dt*values[3*i+2]
                     + (-2*u**3+3*u**2)*values[3*i+4] + (u**3-u**2)*dt*values[3*i+3])
            if path == "rotation":
                value /= np.linalg.norm(value)
        elif len(times) == 1 or sampler.get("interpolation") == "STEP":
            value = values[i]
        elif path == "rotation":
            value = g.slerp(values[i], values[i+1], u)
        else:
            value = mix(values[i], values[i+1], u)
        trs[channel["target"]["node"]][path] = value
    return np.array([g.node_matrix(n) if "matrix" in n else g.trs_matrix(**trs[i])
                     for i, n in enumerate(j["nodes"])])


class Rig:
    def __init__(self, name, j, blob):
        self.name = name
        self.j, self.blob = j, blob
        by_name = {n.get("name"): i for i, n in enumerate(j["nodes"])}
        if name in RIGS:
            self.cfg = RIGS[name]
        elif name == "reefplate_golem":
            self.cfg = dict(root=0, pelvis=1, spine=[2], head=4,
                arms=[[13, 14, 15], [10, 11, 12]], legs=[[19, 20, 21], [16, 17, 18]], forward=-1)
        else:
            self.cfg = dict(root=by_name["body"], pelvis=by_name["body"],
                spine=[by_name["spine"], by_name["chest"]], head=by_name["head"],
                arms=[[by_name[f"upper_arm_{s}"], by_name[f"forearm_{s}"], by_name[f"hand_{s}"]] for s in ["r", "l"]],
                legs=[[by_name[f"thigh_{s}"], by_name[f"shin_{s}"], by_name[f"foot_{s}"]] for s in ["r", "l"]], forward=-1)
        self.parents = g.parents_of(j)
        self.order = g.topological(j, range(len(j["nodes"])))
        self.base = np.array([g.node_matrix(n) for n in j["nodes"]])
        self.guard = sample_local(j, blob, "Fighting_Idle", 0)
        self.joints = set(n for skin in j["skins"] for n in skin["joints"])
        # Mossbound carries its ground-normalizing offset on the Armature node.
        # Keep the scene transforms used by its other clips during this attack.
        for i in range(len(self.base)):
            if i not in self.joints:
                self.base[i] = self.guard[i]
        self.local = self.base.copy()
        self.fk()
        self.rest = self.world.copy()
        self.pos = self.rest[:, :3, 3]
        self.R = g.rotations_of(self.rest)
        self.surfaces = []
        for node in j["nodes"]:
            if "mesh" not in node or "skin" not in node:
                continue
            skin = j["skins"][node["skin"]]
            ibm = g.accessor(j, blob, skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
            for p in j["meshes"][node["mesh"]]["primitives"]:
                attrs = p["attributes"]
                v = g.accessor(j, blob, attrs["POSITION"])
                sets = sorted(int(k.split("_")[1]) for k in attrs if k.startswith("JOINTS_"))
                ji = np.concatenate([g.accessor(j, blob, attrs[f"JOINTS_{s}"]) for s in sets], axis=1).astype(int)
                weights = np.concatenate([g.accessor(j, blob, attrs[f"WEIGHTS_{s}"]) for s in sets], axis=1)
                self.surfaces.append((np.c_[v, np.ones(len(v))], np.array(skin["joints"])[ji], weights, np.array(skin["joints"]), ibm))
        self.vertices = self.skin()
        self.floor = self.vertices[:, 1].min()
        self.height = np.ptp(self.vertices[:, 1])
        self.influence = np.concatenate([np.sum(np.isin(s[1], self.descendants(self.cfg["arms"][0][2])) * s[2], axis=1) for s in self.surfaces])
        self.fist_ids = np.where(self.influence > .45)[0]
        if not len(self.fist_ids):
            raise ValueError(f"No right hand vertices for {name}")
        self.forward = self.cfg["forward"]
        self.right = -self.forward
        self.foot_ids = [np.where(np.concatenate([np.sum(np.isin(s[1], self.descendants(chain[2])) * s[2], axis=1) for s in self.surfaces]) > .4)[0] for chain in self.cfg["legs"]]
        self.shin_ids = [np.where(np.concatenate([np.sum(np.isin(s[1], self.descendants(chain[1])) * s[2], axis=1) for s in self.surfaces]) > .4)[0] for chain in self.cfg["legs"]]

    def descendants(self, node):
        return [node] + [x for c in self.j["nodes"][node].get("children", []) for x in self.descendants(c)]

    def fk(self):
        self.world = np.zeros_like(self.local)
        for i in self.order:
            self.world[i] = (self.world[self.parents[i]] if i in self.parents else np.eye(4)) @ self.local[i]

    def set_rot(self, node, rotation):
        parent = self.parents.get(node)
        pr = g.rotations_of(self.world[parent]) if parent is not None else np.eye(3)
        self.local[node, :3, :3] = (pr.T @ rotation) * np.linalg.norm(self.base[node, :3, :3], axis=0)
        self.fk()

    def delta(self, node, rotation):
        self.set_rot(node, rotation @ g.rotations_of(self.world[node]))

    def ik(self, chain, target, pole):
        a, b, c = chain[:3]
        pa, pb, pc = self.world[[a, b, c], :3, 3].copy()
        l1, l2 = np.linalg.norm(pb-pa), np.linalg.norm(pc-pb)
        dv = np.asarray(target) - pa
        d = np.clip(np.linalg.norm(dv), abs(l1-l2)+1e-6, (l1+l2)*.998)
        axis = unit(dv)
        side = unit(np.asarray(pole) - axis * np.dot(pole, axis))
        along = (l1*l1-l2*l2+d*d)/(2*d)
        elbow = pa + axis*along + side*np.sqrt(max(l1*l1-along*along, 0))
        self.delta(a, aim(pb-pa, elbow-pa))
        pb, pc = self.world[[b, c], :3, 3].copy()
        self.delta(b, aim(pc-pb, pa+axis*d-pb))

    def skin(self):
        result = []
        for v, nodes, weights, joints, ibm in self.surfaces:
            lookup = {n: k for k, n in enumerate(joints)}
            slots = np.vectorize(lookup.get)(nodes)
            matrices = self.world[joints] @ ibm
            # Accumulate one influence at a time to bound memory for dense skins.
            out = np.zeros((len(v), 3))
            for k in range(weights.shape[1]):
                out += np.einsum("nij,nj->ni", matrices[slots[:, k]], v)[:, :3] * weights[:, k, None]
            result.append(out)
        return np.concatenate(result)

    def pose(self, t, contact=True):
        self.local = self.base.copy()
        self.fk()
        h, f, r, cfg = self.height, self.forward, self.right, self.cfg
        kneel = cue(t, .38, IMPACT) * (1 - cue(t, 1.36, 2.20))
        step = cue(t, .10, .42) * (1 - cue(t, 1.80, 2.28))
        windup = cue(t, .04, .48)
        slam = cue(t, .62, IMPACT)
        release = cue(t, 1.12, 1.75)
        recovery = cue(t, 1.75, DURATION)
        hip, knee, foot = cfg["legs"][0]
        thigh_length = np.linalg.norm(self.pos[knee] - self.pos[hip])
        knee_padding = .145 if self.name == "amethyst_stone_golem" else .095
        kneel_hip_y = self.floor + h*knee_padding + thigh_length*.97
        offset = np.array([r*h*.035*kneel, (kneel_hip_y-self.pos[hip, 1])*kneel, f*h*.025*kneel])
        root = cfg["root"]
        parent_matrix = self.world[self.parents[root]] if root in self.parents else np.eye(4)
        self.local[root, :3, 3] += np.linalg.solve(parent_matrix[:3, :3], offset)
        self.fk()
        body_lean = (.12 if self.name == "waterwheel_golem" else .30)*kneel
        root_rotation = rot([1, 0, 0], f*body_lean)
        self.set_rot(root, root_rotation @ self.R[root])
        for node in cfg["spine"]:
            self.delta(node, rot([1, 0, 0], f*(.32*kneel-.045*windup*(1-slam))) @ rot([0, 1, 0], -.055*windup*(1-slam)))
        # Some UniRig skeletons parent the hips under the torso.
        self.set_rot(cfg["pelvis"], root_rotation @ self.R[cfg["pelvis"]])
        self.delta(cfg["head"], rot([1, 0, 0], f*.12*kneel))
        if self.name == "waterwheel_golem":
            # Its rigid wheel housing reaches below the hips. Limit the body
            # drop at housing contact, while the limbs still fold and strike.
            housing = np.concatenate([np.sum((s[1] == cfg["pelvis"]) * s[2], axis=1) for s in self.surfaces]) > .5
            low = self.skin()[housing, 1].min()
            lift = max(0, self.floor-low)
            self.local[root, :3, 3] += np.linalg.solve(parent_matrix[:3, :3], [0, lift, 0])
            self.fk()
        for s, chain in enumerate(cfg["legs"]):
            a, b, c = chain
            target = self.pos[c].copy()
            if s == 0:
                # A kneeling thigh points down; its shin folds back and its heel
                # rises. Solve this explicitly so short rigs do not just squat.
                upper = self.pos[b]-self.pos[a]
                lower = self.pos[c]-self.pos[b]
                upper = mix(upper, unit([r*.04, -.97, f*.23])*np.linalg.norm(upper), kneel)
                lower = mix(lower, unit([r*.05, .6, -f*.80])*np.linalg.norm(lower), kneel)
                pa, pb, pc = self.world[[a, b, c], :3, 3].copy()
                self.delta(a, aim(pb-pa, upper))
                pb, pc = self.world[[b, c], :3, 3].copy()
                self.delta(b, aim(pc-pb, lower))
                foot_rot = rot([1, 0, 0], f*1.10*kneel) @ self.R[c]
                self.set_rot(c, foot_rot)
                for _ in range(5):
                    clearance = self.skin()[self.foot_ids[s], 1].min()-self.floor
                    if clearance >= -.001*h:
                        break
                    pb, pc = self.world[[b, c], :3, 3].copy()
                    raised = pc-pb
                    length = np.linalg.norm(raised)
                    raised_y = np.clip(raised[1]-clearance*1.15, -length*.995, length*.97)
                    horizontal = np.array([raised[0], 0, raised[2]])
                    if np.linalg.norm(horizontal) < 1e-5:
                        horizontal = np.array([r*.05, 0, -f])
                    raised = unit(horizontal)*np.sqrt(max(0, length*length-raised_y*raised_y))
                    raised[1] = raised_y
                    self.delta(b, aim(pc-pb, raised))
                    self.set_rot(c, foot_rot)
            else:
                target[2] += f*h*.17*step
                target[1] += h*.055*np.sin(np.pi*step)
                foot_rot = self.R[c]
                self.ik(chain, target, [-r*.06, .05, f])
                self.set_rot(c, foot_rot)
                for _ in range(3):
                    clearance = self.skin()[self.foot_ids[s], 1].min()-self.floor
                    target[1] += h*.055*np.sin(np.pi*step)-clearance
                    self.ik(chain, target, [-r*.06, .05, f])
                    self.set_rot(c, foot_rot)
                clearance = self.skin()[self.shin_ids[s], 1].min()-self.floor
                if clearance < 0:
                    target[1] -= clearance
                    self.ik(chain, target, [-r*.06, .05, f])
                    self.set_rot(c, foot_rot)
        for s, chain in enumerate(cfg["arms"]):
            a, b, c = chain[:3]
            if s == 0:
                shoulder = self.world[a, :3, 3]
                lifted = shoulder + np.array([r*h*.065, h*.23, -f*h*.045])
                target = mix(self.pos[c], lifted, windup)
                hit = np.array([r*h*.065, self.floor+h*.10, f*h*.39])
                target = mix(target, hit, slam)
                guard = shoulder + np.array([r*h*.07, -h*.17, f*h*.16])
                target = mix(target, guard, release)
                pole = [r, .15, -f*.35]
                self.ik(chain, target, pole)
                hand_direction = self.pos[chain[3]]-self.pos[c] if len(chain)>3 else self.pos[c]-self.pos[b]
                raised_rot = aim(hand_direction, [r*.08, 1, -f*.1]) @ self.R[c]
                strike_rot = aim(hand_direction, [r*.08, -1, f*.2]) @ self.R[c]
                hand_rot = g.quat_to_matrix(g.slerp(g.matrix_to_quat(raised_rot), g.matrix_to_quat(strike_rot), slam))
                self.set_rot(c, hand_rot)
                # Use the skinned striking surface, not the wrist pivot, for contact.
                if contact and .62 <= t <= 1.85:
                    for _ in range(10):
                        low = self.skin()[self.fist_ids, 1].min()
                        correction = self.floor+h*.004-low
                        if correction <= 0 and not (IMPACT <= t <= 1.12):
                            break
                        if abs(correction) < h*.0005:
                            break
                        target[1] += correction
                        self.ik(chain, target, pole)
                        self.set_rot(c, hand_rot)
            else:
                target = self.world[a, :3, 3] + np.array([-r*h*.09, -h*.10, f*h*.17])
                if cfg.get("forward") == -1 and len(cfg["spine"]) == 1:
                    target = self.pos[c].copy()  # Reefplate braces its left forelimb.
                self.ik(chain, target, [-r, -.1, -f*.25])
                self.set_rot(c, self.R[c])
        active = cue(t, 0, .18) * (1-recovery)
        for i in range(len(self.local)):
            scale = np.linalg.norm(self.local[i, :3, :3], axis=0)
            q = g.slerp(g.matrix_to_quat(g.rotations_of(self.guard[i])), g.matrix_to_quat(g.rotations_of(self.local[i])), active)
            self.local[i, :3, :3] = g.quat_to_matrix(q) * scale
            self.local[i, :3, 3] = mix(self.guard[i, :3, 3], self.local[i, :3, 3], active)
        self.fk()
        # Quaternion blending back to guard can dip a rounded sole slightly
        # between the two solved poses. Keep that final blend above the floor.
        for _ in range(2):
            low = self.skin()[:, 1].min()
            if low >= self.floor-h*.001:
                break
            parent = self.world[self.parents[root]] if root in self.parents else np.eye(4)
            self.local[root, :3, 3] += np.linalg.solve(parent[:3, :3], [0, self.floor-low, 0])
            self.fk()
        return self.local.copy()


def build(name, source, output):
    j, blob = g.read(source)
    if any(a["name"] == CLIP for a in j.get("animations", [])):
        # Regeneration replaces our clip and drops its orphaned buffers.
        j["animations"] = [a for a in j["animations"] if a["name"] != CLIP]
        j, blob = g.compact(j, blob)
    original = copy.deepcopy(j)
    rig = Rig(name, j, blob)
    times = np.linspace(0, DURATION, round(DURATION*60)+1)
    frames = np.array([rig.pose(float(t)) for t in times])
    # The quadruped's scene root is an unweighted placement bone. Carry its
    # visual motion on the body instead, keeping the actor root in place.
    if name == "reefplate_golem":
        root = rig.cfg["root"]
        stationary = rig.base[root]
        for child in j["nodes"][root].get("children", []):
            if child in rig.joints:
                frames[:, child] = np.linalg.inv(stationary) @ frames[:, root] @ frames[:, child]
        frames[:, root] = stationary
    app = g.BufferAppender(j, blob)
    ti = app.add(times, "SCALAR")
    clip = dict(name=CLIP, samplers=[], channels=[], extras=dict(impactTime=IMPACT, loop=False, description="Right knee down, right fist ground strike, recover to combat guard"))
    animated_nodes = rig.joints | {c["target"]["node"] for a in original["animations"] for c in a["channels"]}
    for i in sorted(animated_nodes):
        for path, values, kind in [
            ("rotation", g.unroll(np.array([g.matrix_to_quat(g.rotations_of(m)) for m in frames[:, i]])), "VEC4"),
            ("translation", frames[:, i, :3, 3], "VEC3"),
            ("scale", np.linalg.norm(frames[:, i, :3, :3], axis=1), "VEC3"),
        ]:
            if path == "scale" and np.allclose(values, np.linalg.norm(rig.base[i, :3, :3], axis=0), atol=1e-6):
                continue
            # Constant tracks reset channels left by the previous attack.
            vt, vi = (app.add(np.array([0, DURATION]), "SCALAR"), [0, -1]) if np.max(np.abs(values-values[0])) < 1e-7 else (ti, slice(None))
            oi = app.add(values[vi], kind)
            clip["channels"].append(dict(sampler=len(clip["samplers"]), target=dict(node=i, path=path)))
            clip["samplers"].append(dict(input=vt, output=oi, interpolation="LINEAR"))
    j["animations"] = [a for a in j["animations"] if a["name"] != CLIP] + [clip]
    output.parent.mkdir(parents=True, exist_ok=True)
    g.write(output, j, app.blob)
    # The appended clip must leave existing animation and geometry payloads intact.
    saved, saved_blob = g.read(output)
    assert saved_blob[:len(blob)] == blob
    for key in ["nodes", "skins", "meshes", "materials", "textures", "images"]:
        assert saved.get(key) == original.get(key), key
    assert [a for a in saved["animations"] if a["name"] != CLIP] == [a for a in original["animations"] if a["name"] != CLIP]
    assert np.isfinite(frames).all()
    assert np.max(np.abs(frames[0]-frames[-1])) < 1e-6
    rig.pose(IMPACT)
    skin = rig.skin()
    return dict(model=name, height=rig.height, floor=rig.floor, duration=DURATION, impact=IMPACT,
                rightHandNode=j["nodes"][rig.cfg["arms"][0][2]]["name"],
                rightKneeNode=j["nodes"][rig.cfg["legs"][0][1]]["name"],
                fistClearance=float(skin[rig.fist_ids, 1].min()-rig.floor),
                minimumClearance=float(skin[:, 1].min()-rig.floor),
                kneeHeight=float(rig.world[rig.cfg["legs"][0][1], 1, 3]-rig.floor),
                fistForward=float(np.mean(skin[rig.fist_ids, 2])*rig.forward),
                originalPayloadPreserved=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--models", nargs="+")
    args = parser.parse_args()
    catalog = json.loads((CLIENT / "data/actors/models.json").read_text())
    rows = []
    for name, config in catalog["models"].items():
        if "golem" not in name or (args.models and name not in args.models):
            continue
        source = CLIENT / config["scene"].removeprefix("res://")
        output = args.output_dir / source.name if args.output_dir else source
        row = build(name, source, output)
        rows.append(row)
        print(json.dumps(row), flush=True)
    if args.output_dir:
        (args.output_dir / "validation.json").write_text(json.dumps(rows, indent=2)+"\n")


if __name__ == "__main__":
    main()
