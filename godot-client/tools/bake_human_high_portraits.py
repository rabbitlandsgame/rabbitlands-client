"""Offline Human portrait paint and detail bake; never edits source GLBs.

Pass --sources the ignored human_bodies_2026-10 authoring directory and --stage
an ignored versioned output directory. Only --install writes the six reviewed
runtime maps and descriptors under the selected client's data directory.
No service or generator runs.
"""
from __future__ import annotations
import argparse
import hashlib
import gzip
import io
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter, map_coordinates
from scipy.spatial import cKDTree

SIZE = 1024
X_MIN, X_MAX, Y_MIN, Y_MAX = -.105, .105, -.075, .205


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def load_tools(root):
    sys.path.insert(0, str(root / "eloria-assets/tools/tpose_bodies/vendor"))
    sys.path.insert(0, str(root / "eloria-assets/tools"))
    import glbkit
    import equipment_authoring
    return glbkit, equipment_authoring


def embedded_image(d, b, image_id):
    image = d["images"][image_id]
    view = d["bufferViews"][image["bufferView"]]
    start = view.get("byteOffset", 0)
    return np.asarray(Image.open(io.BytesIO(b[start:start+view["byteLength"]])).convert("RGB"), dtype=float) / 255


def sample(image, uv):
    # glTF texture coordinates use the same top-left image convention as Godot.
    coordinates = np.array([np.clip(uv[..., 1], 0, 1) * (image.shape[0]-1),
                            np.clip(uv[..., 0], 0, 1) * (image.shape[1]-1)])
    return np.stack([map_coordinates(image[..., c], coordinates, order=1, mode="nearest")
                     for c in range(image.shape[2])], axis=-1)


def raster_head(root, sources, sex, g, ea):
    runtime = root / f"godot-client/assets/actors/native/races/luminous_{sex}.glb"
    split = sources / f"split2/luminous_{sex}.glb"
    d, b = g.read(runtime)
    sd, sb = g.read(split)
    source_hash = d["asset"]["extras"]["eloriaHumanPack"]["sourceSHA256"]
    if sha(split) != source_hash:
        raise ValueError("The retained split is not the runtime body's exact source")
    skin_id = next(n["mesh"] for n in sd["nodes"] if n.get("name") == "body")
    skin_material = sd["meshes"][skin_id]["primitives"][0]["material"]
    tex = sd["materials"][skin_material]["pbrMetallicRoughness"]["baseColorTexture"]["index"]
    image = embedded_image(sd, sb, sd["textures"][tex]["source"])
    masks = np.asarray(Image.open(root / f"godot-client/assets/actors/native/face_masks/luminous_{sex}.png").convert("RGB"), float) / 255
    matrices = ea.global_matrices(d)
    head_id = next(i for i, n in enumerate(d["nodes"]) if n.get("name") == "Head")
    head = matrices[head_id]
    names = [d["nodes"][j]["name"] for j in d["skins"][0]["joints"]]
    slot = names.index("Head")
    color = np.zeros((SIZE, SIZE, 3))
    region = np.zeros_like(color)
    point_map = np.zeros_like(color)
    normal_map = np.zeros_like(color)
    depth = np.full((SIZE, SIZE), -np.inf)
    eye_points = []
    for node in d["nodes"]:
        if node.get("name") not in ("body", "eyes", "eyebrows", "scalp") or "mesh" not in node:
            continue
        for primitive in d["meshes"][node["mesh"]]["primitives"]:
            a = primitive["attributes"]
            vertices = g.accessor(d, b, a["POSITION"])
            normals = g.accessor(d, b, a["NORMAL"])
            uv = g.accessor(d, b, a["TEXCOORD_0"])
            faces = g.accessor(d, b, primitive["indices"]).astype(int).reshape(-1, 3)
            joints = g.accessor(d, b, a["JOINTS_0"]).astype(int)
            weights = g.accessor(d, b, a["WEIGHTS_0"])
            head_weight = (weights * (joints == slot)).sum(1)
            local = (vertices-head[:3, 3]) @ head[:3, :3]
            local_normal = unit(normals @ head[:3, :3])
            if node["name"] == "eyes":
                eye_points.extend(local[np.unique(faces)].tolist())
            for ids in faces:
                p = local[ids]
                if head_weight[ids].mean() < .45 or p[:, 1].max() < Y_MIN or p[:, 1].min() > Y_MAX or p[:, 2].max() < -.035:
                    continue
                screen = np.stack([(p[:, 0]-X_MIN)/(X_MAX-X_MIN)*(SIZE-1),
                                   (Y_MAX-p[:, 1])/(Y_MAX-Y_MIN)*(SIZE-1)], axis=1)
                lo = np.maximum(np.floor(screen.min(0)).astype(int), 0)
                hi = np.minimum(np.ceil(screen.max(0)).astype(int), SIZE-1)
                if np.any(hi < lo):
                    continue
                xx, yy = np.meshgrid(np.arange(lo[0], hi[0]+1), np.arange(lo[1], hi[1]+1))
                q = np.stack([xx, yy], -1)
                e1, e2 = screen[1]-screen[0], screen[2]-screen[0]
                determinant = e1[0]*e2[1]-e1[1]*e2[0]
                if abs(determinant) < 1e-8:
                    continue
                delta = q-screen[0]
                w1 = (delta[..., 0]*e2[1]-delta[..., 1]*e2[0])/determinant
                w2 = (e1[0]*delta[..., 1]-e1[1]*delta[..., 0])/determinant
                w = np.stack([1-w1-w2, w1, w2], -1)
                z = w @ p[:, 2]
                tile = np.s_[lo[1]:hi[1]+1, lo[0]:hi[0]+1]
                keep = (w.min(-1) >= -1e-5) & (z > depth[tile])
                if not keep.any():
                    continue
                atlas = w @ uv[ids]
                color[tile][keep] = sample(image, atlas)[keep]
                region[tile][keep] = sample(masks, atlas)[keep]
                point_map[tile][keep] = (w @ p)[keep]
                normal_map[tile][keep] = unit(w @ local_normal[ids])[keep]
                depth[tile][keep] = z[keep]
    valid = np.isfinite(depth)
    # Pad source islands before mip generation; the runtime's anatomical mask
    # controls coverage, so transparent fringes never mix with black texels.
    nearest = distance_transform_edt(~valid, return_distances=False, return_indices=True)
    for buffer in (color, region, point_map, normal_map):
        buffer[~valid] = buffer[nearest[0][~valid], nearest[1][~valid]]
    return color, region, point_map, normal_map, valid, head, float(np.mean(np.asarray(eye_points)[:, 1])), runtime, split


def bake_high_normals(sources, sex, points, low_normal, valid, head, runtime, g, ea):
    high = sources / f"meshy_bodies_v3/human_{sex}_v3.glb"
    d, b = g.read(high)
    positions, normals = [], []
    matrices = ea.global_matrices(d)
    for index, node in enumerate(d["nodes"]):
        if "mesh" not in node:
            continue
        for q in d["meshes"][node["mesh"]]["primitives"]:
            v = g.accessor(d, b, q["attributes"]["POSITION"])
            n = g.accessor(d, b, q["attributes"]["NORMAL"])
            matrix = matrices[index]
            positions.append(v @ matrix[:3, :3].T + matrix[:3, 3])
            normals.append(unit(n @ np.linalg.inv(matrix[:3, :3])))
    v, n = np.concatenate(positions), np.concatenate(normals)
    rd, rb = g.read(runtime)
    target = np.concatenate([g.accessor(rd, rb, q["attributes"]["POSITION"]) for m in rd["meshes"] for q in m["primitives"]])
    scale = (target[:, 1].max()-target[:, 1].min()) / (v[:, 1].max()-v[:, 1].min())
    v[:, 1] -= v[:, 1].min()
    v *= scale
    v[:, 1] += target[:, 1].min()
    v = (v-head[:3, 3]) @ head[:3, :3]
    n = unit(n @ head[:3, :3])
    keep = (v[:, 1] > -.08) & (v[:, 1] < .23) & (abs(v[:, 0]) < .15) & (v[:, 2] > -.07)
    v, n = v[keep], n[keep]
    # A small translation registration leaves all runtime geometry untouched.
    reference = points[valid][::32]
    offset = np.zeros(3)
    for _ in range(5):
        tree = cKDTree(v+offset)
        distance, ids = tree.query(reference)
        good = distance < .018
        if good.any():
            offset += np.median(reference[good]-(v[ids[good]]+offset), axis=0) * .65
    tree = cKDTree(v+offset)
    distance, ids = tree.query(points.reshape(-1, 3), k=4, workers=4)
    chosen = n[ids]
    low = low_normal.reshape(-1, 3)
    compatible = (chosen * low[:, None, :]).sum(-1) > .35
    weights = compatible / np.maximum(distance, .0008)**2
    total = weights.sum(1)
    transferred = unit((chosen*weights[..., None]).sum(1))
    transferred[total < 1e-8] = low[total < 1e-8]
    influence = np.clip((.014-distance[:, 0])/.009, 0, 1) * .48
    result = unit(low*(1-influence[:, None]) + transferred*influence[:, None]).reshape(points.shape)
    target = (v+offset)[ids]
    target = (target*weights[..., None]).sum(1) / np.maximum(total[:, None], 1e-9)
    delta = target-points.reshape(-1, 3)
    delta[total < 1e-8] = 0
    return result, {"high_source_sha256": sha(high), "registration_offset_m": offset.tolist(),
                    "nearest_median_m": float(np.median(distance[valid.reshape(-1), 0])),
                    "normal_bake_coverage": float(np.mean(influence[valid.reshape(-1)] > .05))}, delta.reshape(points.shape), transferred.reshape(points.shape)


def paint_portrait(base, region, points, low_normal, high_normal, valid, eye_y, sex, source_iris=False, reference=False, mouth_y=None):
    x, y, z = points[..., 0], points[..., 1], points[..., 2]
    yy = y-eye_y
    def brush(cx, cy, sx, sy):
        return np.exp(-((x-cx)/sx)**2-((yy-cy)/sy)**2)
    def glaze(rgb, mask, amount):
        nonlocal base
        weight = np.clip(mask * amount, 0, 1)[..., None]
        base = base*(1-weight) + np.asarray(rgb)*weight
    skin = 1-region[..., 0]
    skin *= 1-np.clip(region[..., 2]*2, 0, 1)
    # Deliberately authored warm/cool planes, muted lips and small asymmetric
    # pigment variation. These are new paint layers, not a texture upscale.
    cheeks = brush(-.042, -.030, .022, .018) + brush(.041, -.031, .022, .018)
    temples = brush(-.070, .013, .016, .043) + brush(.071, .013, .016, .043)
    under_eye = brush(-.034, -.013, .023, .007) + brush(.034, -.013, .023, .007)
    nose = brush(-.001, -.030, .012, .027)
    lip_y = -.064 - .002*np.cos(x*95)
    lips = np.exp(-(x/.027)**4-((yy-lip_y)/.0065)**2)
    lower_lip = np.exp(-(x/.022)**4-((yy+.069)/.0033)**2)
    if reference:
        mouth_offset=y-mouth_y
        arch=np.maximum(1-(x/.028)**2,0)
        upper=(.0038-.0009*np.cos(x*180))*arch
        lips=np.exp(-(x/.027)**4-((mouth_offset-upper)/.0030)**2)
        lips+=np.exp(-(x/.026)**4-((mouth_offset+.0038*arch)/.0030)**2)
        lips=np.clip(lips,0,1)
        lower_lip=np.exp(-(x/.023)**4-((mouth_offset+.0040*arch)/.0028)**2)
    glaze([.72, .40, .34], cheeks*skin, .12 if sex == "female" else .075)
    glaze([.37, .42, .49], temples*skin, .085)
    glaze([.51, .35, .35], under_eye*skin, .13)
    glaze([.75, .43, .34], nose*skin, .055)
    glaze([.55, .285, .27], lips*skin, (.48 if sex == "female" else .30) if reference else (.30 if sex == "female" else .23))
    glaze([.77, .47, .41], lower_lip*skin, .18 if reference else .12)
    if reference:
        cupid = np.exp(-(x/.023)**4-((mouth_offset-upper-.0010)/.0012)**2)
        glaze([.84,.54,.47], cupid*skin, .15 if sex == "female" else .075)
    forehead = brush(-.008, .068, .050, .025)
    glaze([.89, .735, .61], forehead*skin, .045)
    # Preserve the source's strong tapered brow silhouette and add restrained
    # directional strokes. Sparse replacement hairs lost density after mips.
    brow = region[..., 2].copy()
    hair_stroke = .5 + .5*np.sin(x*3900 + yy*740 + np.sin(x*370)*.8)
    base *= 1.0 - (brow * hair_stroke * .05)[..., None]
    # Sparse authored freckles: 0.3–0.6mm dots, irregular opacity and placement.
    rng = np.random.default_rng(1701 if sex == "female" else 2309)
    freckle = np.zeros(x.shape)
    for _ in range(52 if sex == "female" else 23):
        cx = rng.uniform(-.058, .058)
        cy = rng.uniform(-.044, -.014)
        width = rng.uniform(.00022, .00055)
        freckle += brush(cx, cy, width, width*.7) * rng.uniform(.10, .25)
    glaze([.40, .235, .15], freckle*skin, .65)
    # Repaint the iris fibres on a coherent head atlas, retaining the exact
    # existing iris boundaries and the player's independently selected dye.
    corneal_x = np.zeros(x.shape)
    corneal_y = np.zeros(x.shape)
    for side in (() if source_iris else (-1, 1)):
        iris = region[..., 1] * (x*side > 0)
        if iris.sum() < 1:
            continue
        cx, cy = (x*iris).sum()/iris.sum(), (y*iris).sum()/iris.sum()
        pixel_area = (X_MAX-X_MIN)*(Y_MAX-Y_MIN)/(SIZE*SIZE)
        radius = max(np.sqrt(np.count_nonzero(iris > .12)*pixel_area/np.pi), .003)
        dx, dy = (x-cx)/radius, (y-cy)/radius
        # Give the whites breathing room instead of filling the eye patch
        # with a luminous colour disc. Keep the original eyelid boundary.
        raw_radius = np.sqrt(dx*dx+dy*dy)
        new_iris = np.minimum(np.clip(iris*1.4, 0, 1), np.clip((.88-raw_radius)/.075, 0, 1))
        side_mask = x*side > 0
        region[..., 1][side_mask] = new_iris[side_mask]
        dx, dy = dx/.88, dy/.88
        r, theta = np.sqrt(dx*dx+dy*dy), np.arctan2(dy, dx)
        fibre = .53 + .12*np.sin(theta*17 + r*7) + .06*np.sin(theta*29-r*9)
        fibre *= .50 + .50*np.clip((1.00-r)/.22, 0, 1)
        fibre *= .035 + .965*np.clip((r-.34)/.10, 0, 1)
        catch = np.exp(-((dx+.30)/.18)**2-((dy-.33)/.18)**2)
        fibre = np.clip(fibre + catch*.72, .014, .98)
        old_weight = np.clip(iris, 0, 1)[..., None]
        base = base*(1-old_weight) + np.array([.78, .78, .74])*old_weight
        weight = np.clip(new_iris, 0, 1)[..., None]
        base = base*(1-weight) + fibre[..., None]*weight
        corneal_x += dx*.22*new_iris
        corneal_y -= dy*.22*new_iris
    # Fine, coherent relief: high-poly facial normals plus small lip/skin
    # strokes. No pore geometry, extra bones or runtime simulation is added.
    rng = np.random.default_rng(1985)
    height = gaussian_filter(rng.normal(0, 1, x.shape), .65) * .000008 * skin
    height += lips*np.sin(x*3600 + yy*80)*.000045
    height -= under_eye * .000040
    height += lower_lip*.000060
    dy, dx = np.gradient(height, (Y_MAX-Y_MIN)/(SIZE-1), (X_MAX-X_MIN)/(SIZE-1))
    n = low_normal
    tangent = unit(np.stack([np.ones(x.shape), np.zeros(x.shape), -n[..., 0]/np.maximum(n[..., 2], .12)], -1))
    tangent = unit(tangent-n*(tangent*n).sum(-1, keepdims=True))
    bitangent = -unit(np.cross(n, tangent))
    normal = np.stack([(high_normal*tangent).sum(-1)-dx,
                       (high_normal*bitangent).sum(-1)-dy,
                       (high_normal*n).sum(-1)], -1)
    normal[..., 0] += corneal_x
    normal[..., 1] += corneal_y
    normal = unit(normal)
    roughness = np.full(x.shape, .80)
    roughness -= np.clip(nose*.08 + lower_lip*.20, 0, .24)
    if reference:
        roughness -= lips*.17
    roughness = roughness*(1-region[..., 0]) + (.38 if source_iris else .20)*region[..., 0]
    if source_iris:
        roughness = roughness*(1-region[..., 1]) + .29*region[..., 1]
    coverage = gaussian_filter(valid.astype(float), .6)
    rgba = np.concatenate([np.clip(base, 0, 1), coverage[..., None]], -1)
    regions = np.concatenate([np.clip(region, 0, 1), np.clip(roughness, .18, .88)[..., None]], -1)
    return rgba, regions, np.clip(normal*.5+.5, 0, 1)


def save_png(path, array):
    Image.fromarray(np.round(array*255).astype(np.uint8)).save(path, optimize=True)


def smoothstep(a, b, x):
    value = np.clip((x-a)/(b-a), 0, 1)
    return value*value*(3-2*value)


def geometry_v2(stage, sex, base, region, points, low_normal, raw_delta, high_normal, valid, eye_y, reference=False, mouth_y=None):
    x, y, z = points[..., 0], points[..., 1], points[..., 2]
    weight = smoothstep(-.060, -.030, y)*(1-smoothstep(.120, .145, y))
    weight *= (1-smoothstep(.067, .083, abs(x)))*smoothstep(-.004, .014, z)
    # Conform the low-poly front to the retained high-poly surface, rather than
    # displacing along potentially different UV-seam normals.
    delta = np.stack([gaussian_filter(raw_delta[..., c], 1.2) for c in range(3)], -1) * .80
    delta *= np.minimum(1, .0045/np.maximum(np.linalg.norm(delta, axis=-1, keepdims=True), 1e-9))
    def brush(cx, cy, sx, sy):
        return np.exp(-((x-cx)/sx)**2-((y-eye_y-cy)/sy)**2)
    # Small sex-specific sculpt finishing on the source lip/nose planes.
    delta[..., 2] += brush(0, -.064, .022, .007) * (.00065 if sex == "female" else .00045)
    delta[..., 2] += brush(0, -.035, .010, .018) * .00035
    delta *= weight[..., None]
    delta *= np.minimum(1, .0055/np.maximum(np.linalg.norm(delta, axis=-1, keepdims=True), 1e-9))
    # The shared field normal is independent of source UV and source normals.
    # This also repairs neutral-slider head seams, not just custom faces.
    coherent = unit(np.stack([gaussian_filter(high_normal[..., c], .8) for c in range(3)], -1))
    if reference:
        yy = y-eye_y
        finish = np.zeros_like(delta)
        mouth_offset=y-mouth_y
        arch=np.maximum(1-(x/.028)**2,0)
        upper=(.0038-.0009*np.cos(x*180))*arch
        upper_lip = np.exp(-(x/.025)**4-((mouth_offset-upper)/.0028)**2)
        lower_lip = np.exp(-(x/.024)**4-((mouth_offset+.0040*arch)/.0030)**2)
        philtrum = np.exp(-(x/.0055)**2-((mouth_offset-.013)/.007)**2)
        finish[..., 2] += upper_lip*(.0017 if sex == "female" else .0010)
        finish[..., 2] += lower_lip*(.0017 if sex == "female" else .0011)-philtrum*.00045
        tip = np.exp(-(x/.011)**2-((yy+.034)/.010)**2)
        bridge = np.exp(-(x/.008)**2-((yy+.012)/.020)**2)
        finish[..., 2] += bridge*.00055-tip*(.0009 if sex == "female" else .0004)
        finish[..., 1] += tip*(.0012 if sex == "female" else .00045)
        eye_boundary = distance_transform_edt(region[...,0] < .35, sampling=((Y_MAX-Y_MIN)/(SIZE-1),(X_MAX-X_MIN)/(SIZE-1)))
        lid_rim = np.exp(-((eye_boundary-.00075)/.0009)**2)*(region[...,0] < .35)
        lid_rim *= np.exp(-((yy-.001)/.019)**4)*(abs(x) > .010)*(abs(x) < .065)
        finish[...,2] += lid_rim*.0009
        for side in (-1,1):
            iris=region[...,1]*(x*side>0)
            if iris.sum()>1:
                cx,cy=(x*iris).sum()/iris.sum(),(y*iris).sum()/iris.sum()
                along=(x-cx)/.022
                orbit=np.exp(-((x-cx)/.029)**4-((y-cy)/.022)**4)
                orbit*=smoothstep(.006,.020,abs(x))
                finish[...,1] += (-(y-cy)*.28*np.minimum(abs(along),1.15)**1.5+side*(x-cx)*.032)*orbit
            # Retain each source brow's arch, but taper the outer third and
            # reduce its uniformly thick block silhouette in actual geometry.
            brow=(region[...,2]>.25)&(x*side>0)&(y>eye_y+.005)&(y<eye_y+.050)
            columns=np.flatnonzero(brow.any(axis=0))
            if len(columns)<4:
                continue
            centers=np.array([np.mean(y[brow[:,column],column]) for column in columns])
            centerline=np.interp(np.arange(SIZE),columns,centers)[None,:]
            inner,outer=np.percentile(abs(x[brow]),[2,98])
            t=np.clip((abs(x)-inner)/max(outer-inner,.005),0,1)
            taper=.65+.20*np.sin(np.pi*t)-.40*t*t
            influence=np.exp(-((y-centerline)/.010)**4)
            influence*=smoothstep(inner-.002,inner+.001,abs(x))*(1-smoothstep(outer,outer+.003,abs(x)))*(x*side>0)
            finish[...,1] += ((y-centerline)*(taper-1)+.0008*np.sin(np.pi*t)+.0006*t)*influence
            finish[...,2] -= .0004*(1-taper)*influence
        finish *= weight[...,None]
        delta += finish
        delta *= np.minimum(1,.0055/np.maximum(np.linalg.norm(delta,axis=-1,keepdims=True),1e-9))
        # Move the coherent source normals through the authored plane field.
        fy, fx = np.gradient(finish,-(Y_MAX-Y_MIN)/(SIZE-1),(X_MAX-X_MIN)/(SIZE-1),axis=(0,1))
        a,b,c,d=1+fx[...,0],fy[...,0],fx[...,1],1+fy[...,1]
        nx=coherent[...,0]-fx[...,2]*coherent[...,2]
        ny=coherent[...,1]-fy[...,2]*coherent[...,2]
        determinant=np.maximum(a*d-b*c,.1)
        coherent=unit(np.stack([(d*nx-c*ny)/determinant,(-b*nx+a*ny)/determinant,coherent[...,2]],-1))
    size, max_delta = 256, .006
    channels = np.concatenate([np.clip(delta/max_delta*.5+.5, 0, 1), coherent*.5+.5], -1)
    reduced = np.stack([np.asarray(Image.fromarray(np.round(channels[..., c]*255).astype(np.uint8)).resize((size, size), Image.Resampling.BILINEAR)) for c in range(6)], -1)
    blob = gzip.compress(reduced.astype(np.uint8).tobytes(), compresslevel=9, mtime=0)
    path = stage/f"{sex}-sculpt.bin"
    path.write_bytes(blob)
    # Retain source iris/pupil/limbal artwork. Narrow the aperture into an
    # anatomical lid opening and paint lid skin outside it, not a coloured disc.
    native_eye = region[..., 0].copy()
    native_iris = region[..., 1].copy()
    skin_weight = 1-np.clip(native_eye, 0, 1)
    denominator = gaussian_filter(skin_weight, 10)
    skin_fill = np.stack([gaussian_filter(base[..., c]*skin_weight, 10)/np.maximum(denominator, .001) for c in range(3)], -1)
    openings = np.zeros(x.shape)
    for side in (-1, 1):
        iris = native_iris*(x*side > 0)
        if iris.sum() < 1:
            continue
        cx, cy = (x*iris).sum()/iris.sum(), (y*iris).sum()/iris.sum()
        old = (native_eye > .20) & (x*side > 0)
        if not old.any():
            continue
        width = np.clip((np.percentile(x[old], 98)-np.percentile(x[old], 2))*.48, .014, .022)
        upper = min(np.percentile(y[old], 98)-cy, .0080)*.88
        lower = min(cy-np.percentile(y[old], 2), .0065)*.90
        along = np.clip((x-cx)/width, -1.5, 1.5)
        arch = np.maximum(1-along*along, 0)**.65
        top = cy + upper*arch + side*(x-cx)*.025
        bottom = cy - lower*arch + side*(x-cx)*.025
        aperture = smoothstep(bottom-.0004, bottom+.0003, y)*(1-smoothstep(top-.0003, top+.0004, y))
        aperture *= 1-smoothstep(.96, 1.05, abs(along))
        openings = np.maximum(openings, aperture)
        # A very restrained upper-lid rim provides an actual painted lid edge.
        rim = np.exp(-((y-top)/.00045)**2)*(1-smoothstep(.86, 1.05, abs(along)))
        rim *= native_eye
        base = base*(1-rim[..., None]*.13) + np.array([.38,.245,.23])*rim[..., None]*.13
    outside = np.clip(native_eye-openings, 0, 1)
    base = base*(1-outside[..., None])+skin_fill*outside[..., None]
    region[..., 0] = np.minimum(native_eye, openings)
    region[..., 1] = native_iris*openings
    descriptor = {"path": f"res://data/actors/portraits_high/{sex}-sculpt.bin", "size": size,
                         "stride": 6, "max_delta_m": max_delta, "edge_length_m": .0065,
                         "bytes": len(blob), "sha256": sha(path),
                         "baked_max_displacement_m": float(np.max(np.linalg.norm(delta[valid], axis=-1)))}
    if reference:
        descriptor.update(edge_length_m=.0095,feature_edge_length_m=.0045,subdivision_passes=2,eye_y_m=eye_y,mouth_y_m=mouth_y)
    return base, region, descriptor


def run(args):
    root = args.root.resolve()
    g, ea = load_tools(args.tools_root.resolve() if args.tools_root else root)
    args.stage.mkdir(parents=True, exist_ok=True)
    reports = []
    for sex in ("male", "female"):
        base, region, points, normal, valid, head, eye_y, runtime, split = raster_head(root, args.sources, sex, g, ea)
        save_png(args.stage/f"{sex}-source-projection.png", base)
        high_normal, bake, delta, coherent = bake_high_normals(args.sources, sex, points, normal, valid, head, runtime, g, ea)
        mouth_y=None
        if args.geometry_v3:
            args.geometry_v2 = True
            rows=np.arange(SIZE)
            row_y=Y_MAX-rows*(Y_MAX-Y_MIN)/(SIZE-1)
            central=abs(points[SIZE//2,:,0])<.018
            profile=gaussian_filter(np.mean(base[:,central] @ np.array([.2126,.7152,.0722]),axis=1),1)
            candidates=(row_y>eye_y-.090)&(row_y<eye_y-.050)
            mouth_row=np.flatnonzero(candidates)[np.argmin(profile[candidates])]
            mouth_y=float(row_y[mouth_row])
        geometry = None
        if args.geometry_v2:
            base, region, geometry = geometry_v2(args.stage, sex, base, region, points, normal, delta, coherent, valid, eye_y,args.geometry_v3,mouth_y)
        painted, regions, detailed_normal = paint_portrait(base.copy(), region, points,
            high_normal if geometry else normal, high_normal, valid, eye_y, sex, source_iris=bool(geometry),reference=args.geometry_v3,mouth_y=mouth_y)
        save_png(args.stage/f"{sex}-paint.png", painted)
        save_png(args.stage/f"{sex}-regions.png", regions)
        save_png(args.stage/f"{sex}-normal.png", detailed_normal)
        descriptor = {"version": 1, "sex": sex, "size": SIZE,
                      "projection": {"x_min": X_MIN, "x_max": X_MAX, "y_min": Y_MIN, "y_max": Y_MAX},
                      "textures": {name: f"res://data/actors/portraits_high/{sex}-{name}.png" for name in ("paint", "regions", "normal")},
                      "runtime_source_sha256": sha(runtime), "authoring_source_sha256": sha(split),
                      "paint_recipe": "Human portrait v1: warm/cool planes, lip pigment, iris fibres, freckles, high-poly normal bake"}
        if geometry:
            descriptor["version"] = 2
            descriptor["geometry"] = geometry
            descriptor["paint_recipe"] = "Human portrait v2: retained source iris, anatomical lid aperture, high-poly head surface and coherent normals"
        if args.geometry_v3:
            descriptor["version"] = 3
            descriptor["paint_recipe"] = "Human portrait v3: preserved 4K source pigment, measured lip landmarks, authored lid/nose/brow planes and refined feature topology"
        (args.stage/f"{sex}.json").write_text(json.dumps(descriptor, indent=2)+"\n", newline="\n")
        report = {"sex": sex, "runtime_triangles_unchanged": not bool(geometry), "valid_head_pixels": int(valid.sum()),
                  "source_albedo_size": [4096, 4096], **bake}
        reports.append(report)
        if args.install:
            destination = root / "godot-client/data/actors/portraits_high"
            destination.mkdir(parents=True, exist_ok=True)
            for suffix in ("paint.png", "regions.png", "normal.png", ".json"):
                source = args.stage/(f"{sex}{suffix}" if suffix == ".json" else f"{sex}-{suffix}")
                (destination/source.name).write_bytes(source.read_bytes())
            if geometry:
                (destination/f"{sex}-sculpt.bin").write_bytes((args.stage/f"{sex}-sculpt.bin").read_bytes())
        print(json.dumps(report), flush=True)
    manifest = {"version": 3 if args.geometry_v3 else (2 if args.geometry_v2 else 1), "heads": reports,
                "outputs": {p.name: {"bytes": p.stat().st_size, "sha256": sha(p)} for p in args.stage.iterdir() if p.suffix in (".png", ".bin", ".json") and p.name != "bake-report.json"}}
    (args.stage/"bake-report.json").write_text(json.dumps(manifest, indent=2)+"\n", newline="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--tools-root", type=Path, help="Reader tools checkout, only needed for a sparse authoring worktree")
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--geometry-v2", action="store_true", help="Bake bounded High-only surface conformance and lid artwork")
    parser.add_argument("--geometry-v3", action="store_true", help="Refine measured lip/lid/brow planes while preserving exact source pigment")
    run(parser.parse_args())
