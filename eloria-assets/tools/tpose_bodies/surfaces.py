"""Geometry-preserving appearance partitions, adapted from split_race_surfaces.

Each source face occurs once. All partitions reuse the unsplit attributes.
Bald source skulls are partitioned as scalp; no fake sculpted hair is added.
Only the two optional headwear meshes are new geometry.
"""

from __future__ import annotations
import argparse
import copy
import io
import json
from pathlib import Path
import numpy as np
from PIL import Image
from build import split, append
from audit import g, digest
import split_reference

CLASSES = (
    "body",
    "eyes",
    "eyebrows",
    "scalp",
    "wardrobe_shirt",
    "wardrobe_pants",
    "wardrobe_boots",
)


def calibration(slug):
    c = {"calibrated_eyes": False, "omit_eyebrows": slug.startswith("mycelari_")}
    # Painted-eye centres measured on the fitted source atlas, then checked
    # with saturated tint in Godot. Reptilian snouts defeat the human nose prior.
    eyes = {
        "ssarathi_female": (0.052, 1.686, 0.012, 0.014, 0.040),
        "ssarathi_male": (0.059, 1.664, 0.014, 0.009, 0.070),
        "stoneborn_male": (0.035, 1.633, 0.020, 0.004, 0.035),
        "glasswarden_male": (0.038, 1.660, 0.014, 0.007, 0.045),
    }
    if slug in eyes:
        x, y, rx, ry, z = eyes[slug]
        c.update(
            eye_override=True,
            eye_x=x,
            eye_y=y - 1.568490,
            eye_rx=rx,
            eye_ry=ry,
            eye_z_min=z,
        )
    return c


def texture(d, b, p):
    mi = p.get("material", 0)
    idx = d["materials"][mi]["pbrMetallicRoughness"]["baseColorTexture"]["index"]
    im = d["images"][d["textures"][idx]["source"]]
    v = d["bufferViews"][im["bufferView"]]
    start = 8 + v.get("byteOffset", 0)
    return Image.open(io.BytesIO(bytes(b[start : start + v["byteLength"]]))).convert(
        "RGB"
    )


def classify(v, uv, faces, tex, head_y, cal):
    c = v[faces].mean(1)
    tex = np.asarray(tex) / 255.0
    uvc = uv[faces].mean(1)
    x = np.clip((uvc[:, 0] % 1) * (tex.shape[1] - 1), 0, tex.shape[1] - 1).astype(int)
    y = np.clip((uvc[:, 1] % 1) * (tex.shape[0] - 1), 0, tex.shape[0] - 1).astype(int)
    rgb = tex[y, x]
    mx = rgb.max(1)
    mn = rgb.min(1)
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    labels = np.full(len(faces), "body", dtype=object)
    # Learn this body's own wardrobe colours in unambiguous garment regions.
    seeds = {
        "wardrobe_boots": c[:, 1] < 0.3,
        "wardrobe_pants": (c[:, 1] > 0.5) & (c[:, 1] < 0.8),
        "wardrobe_shirt": (c[:, 1] > 1.05) & (c[:, 1] < 1.3) & (abs(c[:, 0]) < 0.14),
    }
    colours = {n: np.median(rgb[sel], axis=0) for n, sel in seeds.items()}
    distances = np.stack(
        [np.linalg.norm(rgb - co, axis=1) for co in colours.values()], axis=1
    )
    choice = np.argmin(distances, axis=1)
    garment_near = distances.min(1) < cal.get("wardrobe_color_radius", 0.30)
    for i, name in enumerate(colours):
        region = (
            (c[:, 1] < 0.5)
            if name == "wardrobe_boots"
            else (
                (c[:, 1] < 1.08)
                if name == "wardrobe_pants"
                else ((c[:, 1] > 0.8) & (c[:, 1] < head_y + 0.015))
            )
        )
        labels[(choice == i) & garment_near & region] = name
    # Keep the head's closed source shell as scalp. This adds no surface or gap.
    labels[(labels == "body") & (c[:, 1] > head_y + cal.get("scalp_offset", 0.105))] = (
        "scalp"
    )
    ex = cal.get("eye_x", 0.035)
    ey = head_y + cal.get("eye_y", 0.060)
    eyes = (
        ((abs(c[:, 0]) - ex) / cal.get("eye_rx", 0.018)) ** 2
        + ((c[:, 1] - ey) / cal.get("eye_ry", 0.006)) ** 2
        < 1
    ) & (c[:, 2] > cal.get("eye_z_min", 0.06))
    labels[eyes] = "eyes"
    by = head_y + cal.get("brow_y", 0.079)
    brow_zone = (
        ((abs(c[:, 0]) - ex) / cal.get("brow_rx", 0.023)) ** 2
        + ((c[:, 1] - by) / cal.get("brow_ry", 0.0035)) ** 2
        < 1
    ) & (c[:, 2] > cal.get("eye_z_min", 0.06))
    surrounding = (
        (abs(abs(c[:, 0]) - ex) < 0.025)
        & (abs(c[:, 1] - by) < 0.018)
        & (c[:, 2] > cal.get("eye_z_min", 0.06))
    )
    skin_level = (
        float(np.percentile(rgb[surrounding].mean(1), 75))
        if surrounding.any()
        else 0.75
    )
    brows = brow_zone & (
        rgb.mean(1) < min(cal.get("brow_luminance_max", 0.61), skin_level * 0.82)
    )
    # Thin/blond painted brows can fall between centroid rows. Locate their
    # darker source triangles independently on each side, keeping the patch
    # small instead of tinting the whole brow ridge as a white stripe.
    if not cal.get("calibrated_eyes", True) and not cal.get("omit_eyebrows", False):
        for sign in (-1, 1):
            side = c[:, 0] * sign > 0
            search = (
                side
                & (abs(abs(c[:, 0]) - ex) < 0.021)
                & (c[:, 1] > ey + 0.008)
                & (c[:, 1] < ey + 0.031)
                & (c[:, 2] > cal.get("eye_z_min", 0.06))
            )
            candidates = np.flatnonzero(search)
            if not len(candidates):
                continue
            lum = rgb[candidates].mean(1)
            darkest = candidates[np.argsort(lum)[: max(2, int(len(candidates) * 0.18))]]
            level = float(np.median(c[darkest, 1]))
            patch = darkest[abs(c[darkest, 1] - level) < 0.005]
            brows[side] = False
            brows[patch] = True
    labels[brows] = "eyebrows"
    return labels, {k: v.tolist() for k, v in colours.items()}


def add_plain(d, name, colour):
    d.setdefault("materials", []).append(
        {
            "name": name,
            "doubleSided": True,
            "pbrMetallicRoughness": {
                "baseColorFactor": colour + [1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.85,
            },
        }
    )
    return len(d["materials"]) - 1


def run(source, out, cal):
    if "godot-client" in out.resolve().parts or source.resolve() == out.resolve():
        raise ValueError("Only scratch outputs are allowed")
    d, b = split.read_glb(source)
    nodes = [(i, n) for i, n in enumerate(d["nodes"]) if "mesh" in n]
    if len(nodes) != 1 or len(d["meshes"][nodes[0][1]["mesh"]]["primitives"]) != 1:
        raise ValueError(
            "Expected one unsplit source primitive; refusing partial classification"
        )
    ni, node = nodes[0]
    p = d["meshes"][node["mesh"]]["primitives"][0]
    attrs = p["attributes"]
    v = split.accessor_array(d, b, attrs["POSITION"])
    uv = split.accessor_array(d, b, attrs["TEXCOORD_0"])
    faces = split.accessor_array(d, b, p["indices"]).astype(int).reshape(-1, 3)
    world = g.globals_of(d)
    skin = d["skins"][node["skin"]]
    names = [d["nodes"][j]["name"] for j in skin["joints"]]
    hi = names.index("Head")
    head = world[skin["joints"][hi]][:3, 3]
    tex = texture(d, b, p)
    _, labels = split_reference.classify(
        v, uv, faces.reshape(-1), tex, d, b, node["skin"]
    )
    labels[labels == "skin_accent"] = "body"
    # Horns, facial shading and scales can resemble wardrobe colours. The
    # actual head skin weights give an unambiguous guard against tinting a
    # cheek or ear as shirt fabric.
    jj = split.accessor_array(d, b, attrs["JOINTS_0"]).astype(int)
    ww = split.accessor_array(d, b, attrs["WEIGHTS_0"])
    head_weight = (ww * (jj == hi)).sum(1)[faces].mean(1)
    head_surface = (head_weight > 0.5) & (v[faces].mean(1)[:, 1] > head[1] - 0.025)
    labels[head_surface & (labels != "eyes")] = "body"
    cal = dict(cal)
    if not cal.get("calibrated_eyes", True):
        centres = v[faces[labels == "eyes"]].mean(1)
        if len(centres):
            cal.setdefault("eye_x", float(np.median(abs(centres[:, 0]))))
            cal.setdefault("eye_y", float(np.median(centres[:, 1]) - head[1]))
            cal.setdefault("brow_y", cal["eye_y"] + 0.020)
            cal.setdefault("eye_z_min", float(np.median(centres[:, 2]) - 0.025))
            cal.setdefault("scalp_offset", cal["eye_y"] + 0.045)
    # Inherit the mature palette/UV/island classifier, then add the bald
    # scalp and explicitly calibrated eyebrow/eye patches for this source.
    detail, colours = classify(v, uv, faces, tex, head[1], cal)
    labels[(labels == "body") & (detail == "scalp")] = "scalp"
    if cal.get("calibrated_eyes", True) or cal.get("eye_override", False):
        labels[labels == "eyes"] = "body"
        labels[detail == "eyes"] = "eyes"
    if not cal.get("omit_eyebrows", False):
        brow = detail == "eyebrows"
        if cal.get("eye_override", False):
            brow &= labels != "eyes"
        labels[brow] = "eyebrows"
    else:
        labels[labels == "eyebrows"] = "body"
    # Preserve textures for skin; desaturate only independently tintable parts.
    grey = split.grayscale_texture(tex)
    vi = split.append_view(d, b, grey)
    d["images"].append({"mimeType": "image/png", "bufferView": vi})
    d["textures"].append({"source": len(d["images"]) - 1})
    ti = len(d["textures"]) - 1
    base = copy.deepcopy(d["materials"][p.get("material", 0)])
    # Meshy's full-body emissive basecolour prevents useful tinting. Keep
    # authored basecolour and normal maps, use ordinary lit materials.
    for m in d["materials"]:
        m.pop("emissiveTexture", None)
        m["emissiveFactor"] = [0, 0, 0]
        m.setdefault("pbrMetallicRoughness", {}).update(
            {"metallicFactor": 0.0, "roughnessFactor": 0.85}
        )
    greyidx = add_plain(d, "TintableAtlas", [1, 1, 1])
    d["materials"][greyidx]["pbrMetallicRoughness"]["baseColorTexture"] = {"index": ti}
    plain = add_plain(d, "Headwear", [0.9, 0.9, 0.9])
    eyesmat = add_plain(d, "Eyes", [1, 1, 1])
    parent = next(i for i, n in enumerate(d["nodes"]) if ni in n.get("children", []))
    d["nodes"][parent]["children"].remove(ni)
    node.pop("mesh")
    node.pop("skin", None)
    old_meshes = d["meshes"]
    d["meshes"] = []

    def mesh(name, primitive):
        d["meshes"].append({"name": name, "primitives": [primitive]})
        d["nodes"].append({"name": name, "mesh": len(d["meshes"]) - 1, "skin": 0})
        d["nodes"][parent]["children"].append(len(d["nodes"]) - 1)

    counts = {}
    for name in CLASSES:
        f = faces[labels == name]
        counts[name] = len(f)
        if not len(f):
            continue
        idx = append(d, b, f.astype("<u4").reshape(-1), 5125, "SCALAR", 34963)
        material = (
            greyidx
            if name.startswith("wardrobe_") or name in ("eyebrows", "eyes")
            else p.get("material", 0)
        )
        mesh(name, {"attributes": dict(attrs), "indices": idx, "material": material})
    if sum(counts.values()) != len(faces):
        raise AssertionError("Lost faces")
    # Reuse the splitter's band and cap shapes; fit width/depth to this skull.
    eye_y = head[1] + cal.get("eye_y", 0.060)
    skull = v[(v[:, 1] > eye_y + 0.025) & (v[:, 1] < eye_y + 0.075)]
    rx = float(np.percentile(abs(skull[:, 0] - head[0]), 96))
    rz = float(np.percentile(abs(skull[:, 2] - head[2]), 96))
    core = v[
        (abs(v[:, 0] - head[0]) < 0.045)
        & (abs(v[:, 2] - head[2]) < 0.065)
        & (v[:, 1] > eye_y + 0.045)
    ]
    top = (
        float(np.percentile(core[:, 1], 95))
        if len(core)
        else float(np.max(skull[:, 1]))
    )
    base_y = eye_y + 0.044
    for name, data in [
        ("wardrobe_head_band", split.ring(1, base_y - 0.008, base_y + 0.016)),
        ("wardrobe_head_cap", split.dome(1, 0)),
    ]:
        vertices, normals, uvs, idx = data
        scale = np.array([rx + 0.003, 1.0, rz + 0.003])
        if name.endswith("cap"):
            scale[1] = top - base_y + 0.004
            vertices[:, 1] *= scale[1]
            vertices[:, 1] += base_y
        vertices[:, 0] = vertices[:, 0] * scale[0] + head[0]
        vertices[:, 2] = vertices[:, 2] * scale[2] + head[2]
        normals /= scale
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
        jj = np.zeros((len(vertices), 4), dtype="<u2")
        jj[:, 0] = hi
        ww = np.zeros((len(vertices), 4), dtype="<f4")
        ww[:, 0] = 1
        aa = {
            k: append(d, b, a, c, t, 34962)
            for k, a, c, t in [
                ("POSITION", vertices.astype("<f4"), 5126, "VEC3"),
                ("NORMAL", normals.astype("<f4"), 5126, "VEC3"),
                ("TEXCOORD_0", uvs.astype("<f4"), 5126, "VEC2"),
                ("JOINTS_0", jj, 5123, "VEC4"),
                ("WEIGHTS_0", ww, 5126, "VEC4"),
            ]
        }
        mesh(
            name,
            {
                "attributes": aa,
                "indices": append(d, b, idx.astype("<u4"), 5125, "SCALAR", 34963),
                "material": plain,
            },
        )
    d["asset"].setdefault("extras", {}).update(
        {
            "eloriaTposeSurfaces": 1,
            "baldSource": True,
            "partitionSourceSHA256": digest(source),
        }
    )
    d, blob = g.compact(d, bytes(b[8:]))
    out.parent.mkdir(parents=True, exist_ok=True)
    g.write(out, d, blob)
    # Compare attributes and face multisets against source after serialization.
    src, sb = g.read(source)
    dd, db = g.read(out)
    sp = src["meshes"][0]["primitives"][0]
    collected = []
    for n in dd["nodes"]:
        if n.get("name") not in CLASSES or "mesh" not in n:
            continue
        pp = dd["meshes"][n["mesh"]]["primitives"][0]
        collected.extend(
            g.accessor(dd, db, pp["indices"]).astype(int).reshape(-1, 3).tolist()
        )
        for a in sp["attributes"]:
            if not np.array_equal(
                g.accessor(src, sb, sp["attributes"][a]),
                g.accessor(dd, db, pp["attributes"][a]),
            ):
                raise AssertionError("Changed attribute " + a)
    if sorted(map(tuple, collected)) != sorted(map(tuple, faces.tolist())):
        raise AssertionError("Face partition mismatch")
    report = {
        "source_sha256": digest(source),
        "output_sha256": digest(out),
        "faces": counts,
        "wardrobe_colours": colours,
        "geometry_preserved": True,
        "omitted": {"hair": "Source deliberately bald; omission approved by user"},
        "calibration": cal,
    }
    if cal.get("omit_eyebrows", False):
        report["omitted"][
            "eyebrows"
        ] = "Mycelari source has no painted eyebrows; omission approved by user"
    out.with_suffix(".surfaces.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--calibration", type=Path)
    a = ap.parse_args()
    print(
        json.dumps(
            run(
                a.source,
                a.out,
                json.loads(a.calibration.read_text()) if a.calibration else {},
            ),
            indent=2,
        )
    )
