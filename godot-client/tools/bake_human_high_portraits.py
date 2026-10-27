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
from scipy.ndimage import distance_transform_edt, gaussian_filter, map_coordinates, median_filter
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


def repair_source_pigment(stage, sex, paint, regions, source_projection):
    """Remove a verified false cut glyph, without filtering surrounding skin.

    GPU isolation established that these neutral-dark source texels form the
    dashed lower-eye cut in the male paint, independently of geometry/normals.
    The predicate is limited to its audited one-pixel path, checks both local
    value and lost skin chroma, and must match the exact reviewed footprint.
    """
    if sex != "male":
        return paint, None
    luminance = source_projection @ np.array([.2126, .7152, .0722])
    chroma = source_projection[..., 0]-source_projection[..., 1]
    yy, xx = np.indices(luminance.shape)
    cut_y = 491+(xx-303)*(13/31)
    mask = (xx >= 302) & (xx <= 335) & (abs(yy-cut_y) < .70)
    mask &= median_filter(luminance, size=7, mode="nearest")-luminance > .015
    mask &= median_filter(chroma, size=7, mode="nearest")-chroma > .04
    expected = {(491,303),(494,310),(495,312),(496,315),(497,317),
                (498,319),(498,320),(499,321),(499,322),(500,324),
                (501,326),(501,327),(502,328),(502,329),(503,330),
                (503,331),(503,332),(504,333),(504,334)}
    pixels = np.argwhere(mask)
    if {tuple(pixel) for pixel in pixels} != expected:
        raise ValueError("Male false-cut pigment footprint changed; re-audit source art before repair")
    if np.max(regions[..., 0][mask]) > .01 or np.max(regions[..., 2][mask]) > .01:
        raise ValueError("False-cut repair unexpectedly reaches an eye or eyebrow")
    # Interpolate across the cut's normal from its immediate clean sides.
    # Only these 19 RGB texels change; alpha and every surrounding texel stay
    # exact. Using the immutable input avoids sequential fill propagation.
    normal_yx = np.array([31., -13.])/np.hypot(31., 13.)
    coordinates = pixels.T.astype(float)
    sides = []
    for side in (-1, 1):
        q = coordinates+normal_yx[:, None]*side*1.7
        sides.append(np.stack([map_coordinates(paint[..., c], q, order=1, mode="nearest")
                               for c in range(3)], axis=-1))
    repaired = paint.copy()
    repaired[mask, :3] = np.mean(sides, axis=0)
    save_png(stage/f"{sex}-pigment-repair-mask.png", mask.astype(float))
    return repaired, {"kind": "verified imported false-cut pigment", "rgb_texels": len(pixels),
                      "bounds_px": [303,491,334,504], "alpha_unchanged": True,
                      "predicate": "audited one-pixel path plus local darkness and lost skin chroma",
                      "fill": "bilinear RGB from clean sides at +/-1.7 texels perpendicular to cut"}


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


def refine_features_v4(stage, sex, paint, regions, normal, geometry, mouth_y, concept_art=False, male_cheek_planes=False):
    """Authored eye/lip finish in the existing canonical atlas, not an upscale.

    The iris carries neutral radial pigment so the selected eye hue remains
    independent. The normal map supplies a curved corneal response; no floating
    eye overlay or extra draw is needed. Lip relief joins the same position-only
    CPU field as the earlier sculpt, preserving seam and morph coherence.
    """
    x, y = np.meshgrid(np.linspace(X_MIN, X_MAX, SIZE), np.linspace(Y_MAX, Y_MIN, SIZE))
    base = paint[..., :3].copy()
    source_pigment = base.copy()
    eye, iris = regions[..., 0].copy(), regions[..., 1].copy()
    skin = (1-eye)*(1-regions[..., 2])
    denominator = gaussian_filter(1-eye, 15)
    skin_fill = np.stack([gaussian_filter(base[..., channel]*(1-eye), 15)/np.maximum(denominator,.001)
                          for channel in range(3)], -1)
    lid_relief = np.zeros(x.shape)
    def glaze(rgb, weight):
        nonlocal base
        weight = np.clip(weight, 0, 1)[..., None]
        base = base*(1-weight)+np.asarray(rgb)*weight
    eyes = []
    for side in (-1, 1):
        selected = iris*(x*side > 0)
        cx, cy = (x*selected).sum()/selected.sum(), (y*selected).sum()/selected.sum()
        native_eye = eye*(x*side > 0)
        aperture_pixels = native_eye > .20
        width = np.clip((np.percentile(x[aperture_pixels],98)-np.percentile(x[aperture_pixels],2))*.48,.014,.022)
        along = (x-cx)/width
        arch = np.maximum(1-along*along,0)**(.80 if concept_art else .65)
        upper = min(np.percentile(y[aperture_pixels],98)-cy,.0080)*(.70 if concept_art else .72)
        lower = min(cy-np.percentile(y[aperture_pixels],2),.0065)*.96
        top = cy+upper*arch+side*(x-cx)*.035
        bottom = cy-lower*arch+side*(x-cx)*.035
        opening = smoothstep(bottom-.0003,bottom+.00025,y)*(1-smoothstep(top-.00025,top+.0003,y))
        opening *= 1-smoothstep(.96,1.04,abs(along))
        shaped_eye = np.minimum(native_eye,opening)
        covered = np.clip(native_eye-shaped_eye,0,1)[...,None]
        base = base*(1-covered)+skin_fill*covered
        regions[...,3] = regions[...,3]*(1-covered[...,0])+.78*covered[...,0]
        regions[...,0] = np.where(x*side>0,shaped_eye,regions[...,0])
        inside = selected > .2
        source_radius = float(np.percentile(abs(x[inside]-cx), 98))/.96
        source_cy = cy
        radius = source_radius
        # The source masks overfill the aperture. A smaller iris tucked under
        # the upper lid exposes readable sclera without a round doll-eye disc.
        radius *= .81 if sex == "female" else .84
        cy += .0015
        dx, dy = (x-cx)/radius, (y-cy)/radius
        r, angle = np.hypot(dx, dy), np.arctan2(dy, dx)
        fibres = (.41+.055*np.sin(angle*31+r*21+np.sin(angle*7)*1.4)
                  +.035*np.sin(angle*57-r*15)+.020*np.sin(angle*83+np.sin(angle*13)*2+r*34)
                  +.050*np.sin(angle*9+r*8))
        # Retain the source's irregular crypts and stromal mottling. Radial
        # remapping reduces its oversized pupil without replacing organic
        # pigment with identical synthetic spokes on both eyes.
        source_r = .60*r+.40*np.sqrt(np.maximum(r,0))
        source_x = cx+np.cos(angle)*source_r*source_radius
        source_y = source_cy+np.sin(angle)*source_r*source_radius
        coordinates = [(Y_MAX-source_y)/(Y_MAX-Y_MIN)*(SIZE-1),
                       (source_x-X_MIN)/(X_MAX-X_MIN)*(SIZE-1)]
        old_value = source_pigment @ np.array([.2126,.7152,.0722])
        organic = map_coordinates(old_value, coordinates, order=1, mode="nearest")
        organic = np.clip(organic,.025,.58)
        fibres = fibres*.30+organic*.70
        if concept_art:
            # Small branching crypts break up the even spokes. These are
            # neutral pigment, leaving every selected iris hue editable.
            crypts = np.maximum(np.sin(angle*19+np.sin(angle*7)*1.8+r*15),0)**9
            crypts *= np.exp(-((r-.52)/.21)**2)
            fibres = fibres*.93-crypts*.042
            fibres += .025*np.sin(angle*43+r*11)*np.exp(-((r-.70)/.25)**2)
        # A defined pupil/limbus with a softly variegated mid iris. Its upper
        # shadow belongs to the lid, rather than a uniformly luminous circle.
        pupil = smoothstep(.25, .36, r)
        limbus = 1-smoothstep(.79, 1.02, r)
        value = (.025+(fibres-.025)*pupil)*(.23+.77*limbus)
        value *= .72+.28*(1-smoothstep(.15, .80, dy))
        glint=np.exp(-((dx+.26)/.050)**2-((dy-.34)/.070)**2)
        value=value*(1-glint*.70)+glint*.70
        # Replace the old oversized iris with a warm scleral surround. Keep
        # the precise aperture, while the principal glint moves with the light.
        new_iris = (1-smoothstep(.95,1.035,r))*shaped_eye
        glaze([.77,.745,.705], np.clip(selected-new_iris,0,1)*shaped_eye)
        weight = np.clip(new_iris, 0, 1)[..., None]
        base = base*(1-weight)+value[..., None]*weight
        regions[...,1] = np.where(x*side > 0,new_iris,regions[...,1])
        # Moist scleral rim and warm inner corner, shaded beneath upper lid.
        eye_side = shaped_eye
        sclera = np.clip(eye_side-selected, 0, 1)
        glaze([.72, .69, .63], sclera*.16)
        upper_shadow = np.exp(-((y-cy-radius*.48)/(radius*.34))**2)
        glaze([.18, .115, .105], eye_side*upper_shadow*.18)
        inner_x = cx-side*(width*.91 if concept_art else radius*1.65)
        tear = np.exp(-((x-inner_x)/.0018)**2-((y-cy+.0007)/.0011)**2)
        glaze([.52, .255, .235], tear*eye_side*(.47 if concept_art else .30))
        rim_extent=(1-smoothstep(.87,1.04,abs(along)))*(x*side>0)
        rim=np.exp(-((y-top)/(.00053 if concept_art else .00050))**2)*rim_extent
        crease=np.exp(-((y-top-(.0025 if concept_art else .0021))/.0008)**2)*rim_extent
        waterline=np.exp(-((y-bottom-.00015)/.00038)**2)*rim_extent
        glaze([.15,.09,.08],rim*((.73 if sex=="female" else .51) if concept_art else (.45 if sex=="female" else .30)))
        glaze([.43,.29,.26],crease*(.18 if concept_art else .10))
        glaze([.84,.62,.53],waterline*(.22 if concept_art else .13))
        if concept_art:
            lower_roll=np.exp(-((y-bottom+.0011)/.0009)**2)*rim_extent
            outer_lash=np.exp(-((y-top-.00015)/.00060)**2)*rim_extent*smoothstep(.12,.80,side*along)
            glaze([.78,.57,.47],lower_roll*.10)
            glaze([.12,.075,.065],outer_lash*(.26 if sex=="female" else .10))
        lid_relief += (rim*.00060+waterline*.00030-crease*.00022)*native_eye
        if concept_art:
            # Ease the source's swollen lower orbital roll while retaining
            # the waterline itself. The same bounded field updates geometry
            # and coherent normals; it is not a painted shadow correction.
            under_roll=np.exp(-((y-bottom+.0030)/.0033)**2)
            under_roll*=(1-smoothstep(.65,1.10,abs(along)))*(x*side>0)
            lid_relief-=under_roll*(1-native_eye)*.00065
        # Tangent-space corneal curvature is restricted to the eye pigment.
        # Map Y runs down the atlas; canonical Y runs upward.
        curve = np.stack([np.clip(dx, -1, 1)*.53, -np.clip(dy, -1, 1)*.53,
                          np.sqrt(np.maximum(1-.53**2*np.minimum(r*r, 1.8), .15))], -1)
        curve = unit(curve)*.5+.5
        normal = normal*(1-weight)+curve*weight
        regions[..., 3] = regions[..., 3]*(1-new_iris)+.12*new_iris
        eyes.append({"center_m": [float(cx), float(cy)], "iris_radius_m": radius})
    width = .027 if sex == "female" else .028
    arch = np.maximum(1-(x/width)**2, 0)
    seam = mouth_y-.0007*arch
    upper = seam+(.0022+.0018*np.exp(-((abs(x)-.007)/.005)**2))*arch
    lower = seam-.0037*arch
    extent = 1-smoothstep(.93, 1.04, abs(x)/width)
    upper_pigment = np.exp(-((y-upper)/.0020)**2)*extent
    lower_pigment = np.exp(-((y-lower)/.0025)**2)*extent
    if concept_art:
        # A bounded vermilion shape gives the Cupid bow and the rolled lower
        # lip definite borders; translucent layers retain the source pigment.
        upper_border=seam+(.0041+.0019*np.exp(-((abs(x)-.0065)/.0042)**2))*arch
        lower_border=seam-.0065*arch
        upper_pigment=smoothstep(seam-.00035,seam+.00035,y)*(1-smoothstep(upper_border-.00023,upper_border+.00028,y))*extent
        lower_pigment=smoothstep(lower_border-.00045,lower_border+.00040,y)*(1-smoothstep(seam-.00035,seam+.00035,y))*extent
        upper=np.minimum(upper_border-.0010,seam+.0035)
        lower=seam-.0032*arch
    seam_line = np.exp(-((y-seam)/.00065)**2)*extent
    corners = np.exp(-((abs(x)-width*.96)/.0020)**2-((y-mouth_y+.0002)/.0012)**2)
    glaze([.49, .225, .215] if sex == "female" else [.43, .255, .23], upper_pigment*skin*(.42 if concept_art else .34))
    glaze([.66, .345, .31] if sex == "female" else [.58, .34, .29], lower_pigment*skin*(.39 if concept_art else .28))
    glaze([.235, .095, .09], seam_line*skin*((.68 if sex == "female" else .57) if concept_art else (.57 if sex == "female" else .46)))
    glaze([.27, .125, .115], corners*skin*.47)
    cupid_center = upper_border+.00035 if concept_art else upper+.0015
    cupid_width = .00055 if concept_art else .00065
    cupid = np.exp(-((y-cupid_center)/cupid_width)**2)*extent
    glaze([.87, .63, .52], cupid*skin*(.20 if concept_art else .13))
    if concept_art:
        vermilion_edge=np.exp(-((y-upper_border+.00012)/.00038)**2)*extent
        glaze([.46,.205,.18] if sex=="female" else [.42,.24,.20],vermilion_edge*skin*(.24 if sex=="female" else .13))
        # The lower lip catches a soft horizontal sheen, with irregular fine
        # vertical furrows instead of a broad pale band around the mouth.
        roll=np.exp(-((y-(seam-.0037*arch))/.0012)**2)*np.exp(-(x/(width*.70))**4)*lower_pigment
        furrows=(.5+.5*np.sin(x*3700+np.sin(x*530)*1.7))**5
        glaze([.86,.56,.45] if sex=="female" else [.74,.48,.36],roll*skin*.22)
        glaze([.39,.19,.17],furrows*(upper_pigment+lower_pigment)*skin*.045)
    philtrum = np.exp(-(x/.004)**2-((y-mouth_y-.010)/.006)**2)
    glaze([.49, .32, .28], philtrum*skin*.065)
    lip = np.maximum(upper_pigment, lower_pigment)*skin
    regions[..., 3] = np.minimum(regions[..., 3], .80-lip*.28)
    paint[..., :3] = np.clip(base, 0, 1)
    # Refine the actual vermilion form and corner indentation. This bounded
    # addition never reaches the skull, neck or helmet/hair seam protections.
    relief = (.00035*upper_pigment+.00040*lower_pigment-.00070*seam_line-.00055*corners)*skin+lid_relief
    lip_lid_relief_max = float(abs(relief).max())
    cheek_report = None
    if concept_art and male_cheek_planes and sex == "male":
        # Broad lateral planes give the retained imported male face a malar
        # crest and buccal hollow. The central features, orbit, ears and neck
        # have exact zero influence; no crease or new topology is introduced.
        eye_y = geometry["eye_y_m"]
        lateral = smoothstep(.030,.041,abs(x))*(1-smoothstep(.065,.077,abs(x)))
        vertical = smoothstep(-.012,.002,y)*(1-smoothstep(eye_y-.024,eye_y-.014,y))
        crest = np.exp(-((abs(x)-.052)/.013)**2-((y-eye_y+.031)/.010)**2)
        hollow = np.exp(-((abs(x)-.055)/.014)**2-((y-mouth_y-.005)/.016)**2)
        planes = (crest*.0010-hollow*.00125)*lateral*vertical
        relief += planes
        cheek_report = {"max_rise_m": float(planes.max()), "max_hollow_m": float(planes.min()),
                        "central_zero_half_width_m": .030, "outer_zero_x_m": .077}
    size, stride, max_delta = geometry["size"], geometry["stride"], geometry["max_delta_m"]
    path = stage/f"{sex}-sculpt.bin"
    field = np.frombuffer(gzip.decompress(path.read_bytes()), np.uint8).reshape(size, size, stride).astype(float)/127.5-1
    reduced = np.asarray(Image.fromarray(relief.astype(np.float32)).resize((size, size), Image.Resampling.BILINEAR))
    field[..., 2] += reduced/max_delta
    delta = field[..., :3]*max_delta
    delta *= np.minimum(1, .0055/np.maximum(np.linalg.norm(delta, axis=-1, keepdims=True), 1e-9))
    field[..., :3] = delta/max_delta
    ry, rx = np.gradient(reduced, -(Y_MAX-Y_MIN)/(size-1), (X_MAX-X_MIN)/(size-1))
    n = field[..., 3:6]
    n = unit(np.stack([n[..., 0]-rx*n[..., 2], n[..., 1]-ry*n[..., 2], n[..., 2]], -1))
    field[..., 3:6] = n
    path.write_bytes(gzip.compress(np.round(np.clip(field*.5+.5, 0, 1)*255).astype(np.uint8).tobytes(), compresslevel=9, mtime=0))
    geometry.update(bytes=path.stat().st_size, sha256=sha(path), baked_max_displacement_m=float(np.linalg.norm(delta, axis=-1).max()))
    features = {"version": 5 if concept_art else 4, "eyes": eyes,
        "max_lip_relief_addition_m": lip_lid_relief_max,
        "description": "Neutral iris fibres, pupil/limbus and curved corneal normals; measured vermilion seam/corners and bounded lip relief"}
    if cheek_report:
        features["male_cheek_planes"] = cheek_report
    return paint, regions, normal, features


def run(args):
    root = args.root.resolve()
    g, ea = load_tools(args.tools_root.resolve() if args.tools_root else root)
    args.stage.mkdir(parents=True, exist_ok=True)
    reports = []
    for sex in ("male", "female"):
        base, region, points, normal, valid, head, eye_y, runtime, split = raster_head(root, args.sources, sex, g, ea)
        source_projection = base.copy()
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
        features = None
        if args.features_v4:
            painted, regions, detailed_normal, features = refine_features_v4(args.stage, sex, painted, regions, detailed_normal, geometry, mouth_y, args.features_v5, args.male_cheek_planes)
        pigment_repair = None
        if args.repair_source_pigment:
            painted, pigment_repair = repair_source_pigment(args.stage, sex, painted, regions, source_projection)
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
        if features:
            descriptor["version"] = 4
            descriptor["features"] = features
            descriptor["paint_recipe"] = "Human portrait v4: articulated iris/cornea response and measured lip seam, vermilion and corner relief"
            if args.features_v5:
                descriptor["paint_recipe"] = "Human portrait v5: concept-guided iris crypts, continuous lid/canthus paint and bounded Cupid bow/vermilion anatomy"
        if pigment_repair:
            descriptor["source_pigment_repairs"] = [pigment_repair]
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
    manifest = {"version": 4 if args.features_v4 else (3 if args.geometry_v3 else (2 if args.geometry_v2 else 1)), "heads": reports,
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
    parser.add_argument("--features-v4", action="store_true", help="Refine eye pigment, corneal response and mouth form over v3")
    parser.add_argument("--features-v5", action="store_true", help="Refine lid/canthus paint and bounded vermilion anatomy against retained concepts")
    parser.add_argument("--male-cheek-planes", action="store_true", help="Add bounded lateral malar/buccal planes to the High male sculpt")
    parser.add_argument("--repair-source-pigment", action="store_true", help="Repair the audited false-cut RGB texels without filtering surrounding art")
    args = parser.parse_args()
    if args.male_cheek_planes or args.repair_source_pigment:
        args.features_v5 = True
    if args.features_v5:
        args.features_v4 = True
    if args.features_v4:
        args.geometry_v3 = True
    run(args)
