"""Hash-bound exact-storage qualification jobs; source-only witnesses stay immutable."""

import os

os.environ["OPENBLAS_NUM_THREADS"] = "2"
os.environ["OMP_NUM_THREADS"] = "2"
import argparse
import copy
import sys
import json
import pathlib
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eloria-assets/tools"))
from video_motion.asset import read_glb, digest
from video_motion.creature_storage import _array
from video_motion.native_shapes import NativeShapeAsset
from video_motion.runtime_validation import surface_sampler
from test_completed_creature_motion import normal_sampler


def same_accessor(ad, ab, old, bd, bb, new):
    """Compare raw retained values and their interpretation, not float tolerances."""
    left, right = ad["accessors"][old], bd["accessors"][new]
    for key in (
        "componentType",
        "type",
        "count",
        "normalized",
        "extensions",
        "min",
        "max",
    ):
        assert left.get(key) == right.get(key), (old, new, key)
    assert _array(ad, ab, old).tobytes() == _array(bd, bb, new).tobytes()


def exact_source(job):
    source = pathlib.Path(job["source"])
    candidate = pathlib.Path(job["candidate"])
    out = pathlib.Path(job["output"])
    out.mkdir(exist_ok=True, parents=True)
    ad, ab = read_glb(source)
    bd, bb = read_glb(candidate)
    build = json.loads(pathlib.Path(job["preparation"]).read_text())
    assert (
        digest(source) == build["source_sha256"]
        and digest(candidate) == build["candidate_sha256"]
    )
    masks = {x["mesh"]: x for x in build["inactive_targets"]["meshes"]}
    assert not build.get(
        "partition"
    ), "Use the partition qualification gate for split surfaces"
    for mi, mesh in enumerate(ad["meshes"]):
        counts = {len(p.get("targets", [])) for p in mesh["primitives"]}
        assert len(counts) == 1
        count = counts.pop()
        if mi not in masks:
            assert count == 0
            masks[mi] = dict(
                mesh=mi,
                targets_before=0,
                targets_after=0,
                retained_target_indices=[],
                removed_target_indices=[],
            )
        mask = masks[mi]
        keep = mask["retained_target_indices"]
        removed = mask["removed_target_indices"]
        assert mask["targets_before"] == count
        assert sorted(keep + removed) == list(range(count))
        assert keep == sorted(keep) and removed == sorted(removed)
        assert mask["targets_after"] == len(keep)
        for obj in [mesh] + [n for n in ad["nodes"] if n.get("mesh") == mi]:
            defaults = np.asarray(obj.get("weights", [0.0] * count))
            assert not defaults[removed].any(), "A removed target has a nonzero default"
    for key in (
        "materials",
        "asset",
        "scenes",
        "scene",
        "textures",
        "samplers",
        "extensions",
        "extensionsUsed",
        "extensionsRequired",
    ):
        assert ad.get(key) == bd.get(key), key
    assert len(ad["meshes"]) == len(bd["meshes"])
    assert len(ad.get("skins", [])) == len(bd.get("skins", []))
    assert len(ad.get("images", [])) == len(bd.get("images", []))
    assert [{k: v for k, v in n.items() if k != "weights"} for n in ad["nodes"]] == [
        {k: v for k, v in n.items() if k != "weights"} for n in bd["nodes"]
    ]
    for ni, (old, new) in enumerate(zip(ad["nodes"], bd["nodes"])):
        if "mesh" in old:
            mask = masks[old["mesh"]]
            assert np.array_equal(
                np.asarray(
                    old.get(
                        "weights",
                        ad["meshes"][old["mesh"]].get(
                            "weights", [0.0] * mask["targets_before"]
                        ),
                    )
                )[mask["retained_target_indices"]],
                new.get(
                    "weights",
                    bd["meshes"][new["mesh"]].get(
                        "weights", [0.0] * mask["targets_after"]
                    ),
                ),
            )
        else:
            assert old.get("weights") == new.get("weights")
    for old, new in zip(ad.get("skins", []), bd.get("skins", [])):
        assert {k: v for k, v in old.items() if k != "inverseBindMatrices"} == {
            k: v for k, v in new.items() if k != "inverseBindMatrices"
        }
        same_accessor(
            ad, ab, old["inverseBindMatrices"], bd, bb, new["inverseBindMatrices"]
        )
    for old, new in zip(ad.get("images", []), bd.get("images", [])):
        assert {k: v for k, v in old.items() if k != "bufferView"} == {
            k: v for k, v in new.items() if k != "bufferView"
        }
        va = ad["bufferViews"][old["bufferView"]]
        vb = bd["bufferViews"][new["bufferView"]]
        assert bytes(
            ab[va.get("byteOffset", 0) : va.get("byteOffset", 0) + va["byteLength"]]
        ) == bytes(
            bb[vb.get("byteOffset", 0) : vb.get("byteOffset", 0) + vb["byteLength"]]
        )
    for mi, (old, new) in enumerate(zip(ad["meshes"], bd["meshes"])):
        keep = masks[mi]["retained_target_indices"]
        remove = masks[mi]["removed_target_indices"]
        assert np.array_equal(
            np.asarray(old.get("weights", [0.0] * masks[mi]["targets_before"]))[keep],
            new.get("weights", [0.0] * len(keep)),
        )
        expected_metadata = copy.deepcopy(
            {k: v for k, v in old.items() if k not in ("weights", "primitives")}
        )
        if masks[mi]["targets_before"] and "targetNames" in expected_metadata.get("extras", {}):
            names = expected_metadata["extras"]["targetNames"]
            if keep:
                expected_metadata["extras"]["targetNames"] = [names[i] for i in keep]
            else:
                expected_metadata["extras"].pop("targetNames")
        bounds = build.get("logical_actor_bounds")
        if bounds is not None:
            assert bounds["source_sha256"] == digest(source)
            for record in bounds["meshes"]:
                if ad["nodes"][int(record["source_node"])].get("mesh") != mi:
                    continue
                extras = expected_metadata.setdefault("extras", {})
                extras["rabbitlands_actor_bounds_v1"] = {
                    key: record[key] for key in ("position", "size")
                }
                if record["size"][1] > 0:
                    extras["rabbitlands_coat_pattern_height"] = record["size"][1]
        assert expected_metadata == {
            k: v for k, v in new.items() if k not in ("weights", "primitives")
        }, "Mesh names/extras or hash-bound logical bounds differ"
        assert len(old["primitives"]) == len(new["primitives"])
        for pa, pb in zip(old["primitives"], new["primitives"]):
            assert {
                k: v
                for k, v in pa.items()
                if k not in ("attributes", "indices", "targets")
            } == {
                k: v
                for k, v in pb.items()
                if k not in ("attributes", "indices", "targets")
            }
            assert set(pa["attributes"]) == set(pb["attributes"])
            for key, ix in pa["attributes"].items():
                same_accessor(ad, ab, ix, bd, bb, pb["attributes"][key])
            assert ("indices" in pa) == ("indices" in pb)
            if "indices" in pa:
                same_accessor(ad, ab, pa["indices"], bd, bb, pb["indices"])
            assert len(pb.get("targets", [])) == len(keep)
            for oldid, newt in zip(keep, pb.get("targets", [])):
                assert set(pa["targets"][oldid]) == set(newt)
                for key, ix in pa["targets"][oldid].items():
                    same_accessor(ad, ab, ix, bd, bb, newt[key])
    clips = {}
    removed_rows = 0
    duplicate_curves = 0
    assert len(ad["animations"]) == len(bd["animations"])
    all_original_targets = {
        (c["target"]["node"], c["target"]["path"])
        for a in ad["animations"]
        for c in a["channels"]
    }
    for old, new in zip(ad["animations"], bd["animations"]):
        assert {k: v for k, v in old.items() if k not in ("channels", "samplers")} == {
            k: v for k, v in new.items() if k not in ("channels", "samplers")
        }
        # Some current legacy imports contain more than one curve for a
        # property. Preserve every occurrence and its relative order: engines
        # may resolve the last occurrence. Never collapse this to a single map
        # entry or deduplicate the authored channels.
        new_channels = {}
        for channel in new["channels"]:
            key = (channel["target"]["node"], channel["target"]["path"])
            new_channels.setdefault(key, []).append(channel)
        duplicate_curves += sum(len(channels)-1 for channels in new_channels.values())
        times = []
        for oc in old["channels"]:
            oa = old["samplers"][oc["sampler"]]
            t = _array(ad, ab, oa["input"])
            assert (
                t.shape[1:] == (1,)
                and len(t) > 0
                and np.isfinite(t).all()
                and np.all(np.diff(t[:, 0]) > 0)
            ), "Source animation clock must increase strictly"
            times.extend(t[:, 0])
            ov = _array(ad, ab, oa["output"])
            key = (oc["target"]["node"], oc["target"]["path"])
            if oc["target"]["path"] == "weights":
                mask = masks[ad["nodes"][oc["target"]["node"]]["mesh"]]
                ov = ov.reshape(len(t), mask["targets_before"])
                assert not ov[:, mask["removed_target_indices"]].any()
                ov = ov[:, mask["retained_target_indices"]]
                if mask["targets_after"] == 0:
                    assert key not in new_channels
                    continue
            nc = new_channels[key].pop(0)
            if not new_channels[key]: del new_channels[key]
            assert {k: v for k, v in oc.items() if k != "sampler"} == {
                k: v for k, v in nc.items() if k != "sampler"
            }
            ba = new["samplers"][nc["sampler"]]
            assert {k: v for k, v in oa.items() if k not in ("input", "output")} == {
                k: v for k, v in ba.items() if k not in ("input", "output")
            }
            for kind in ("input", "output"):
                for field in ("componentType", "type", "normalized", "extensions"):
                    assert ad["accessors"][oa[kind]].get(field) == bd["accessors"][
                        ba[kind]
                    ].get(field)
            mode = oa.get("interpolation", "LINEAR")
            assert mode == ba.get("interpolation", "LINEAR")
            nt = _array(bd, bb, ba["input"])
            assert (
                nt.shape[1:] == (1,)
                and len(nt) > 0
                and np.isfinite(nt).all()
                and np.all(np.diff(nt[:, 0]) > 0)
            ), "Candidate animation clock must increase strictly"
            nv = _array(bd, bb, ba["output"])
            if oc["target"]["path"] == "weights":
                nv = nv.reshape(len(nt), mask["targets_after"])
            if mode not in ("LINEAR", "STEP"):
                assert t.tobytes() == nt.tobytes() and ov.tobytes() == nv.tobytes()
                continue
            indices = np.searchsorted(t[:, 0], nt[:, 0])
            assert np.array_equal(t[indices].view("<u4"), nt.view("<u4"))
            assert ov[indices].tobytes() == nv.tobytes()
            assert indices[0] == 0 and indices[-1] == len(t) - 1
            deleted = np.ones(len(t), bool)
            deleted[indices] = False
            bits = ov.reshape(len(t), -1).view("<u4")
            eligible = np.zeros(len(t), bool)
            if len(t) > 2:
                eligible[1:-1] = np.all(bits[1:-1] == bits[:-2], axis=1) & np.all(
                    bits[1:-1] == bits[2:], axis=1
                )
            assert np.all(eligible[deleted]), (old["name"], oc["target"])
            removed_rows += int(deleted.sum())
        for key, channels in new_channels.items():
            assert len(channels) == 1, "A neutral duration anchor cannot add duplicate curves"
            channel = channels[0]
            assert (
                key not in all_original_targets
            ), "A duration anchor may not change an authored property"
            node, path = key
            assert (
                path in ("translation", "rotation", "scale")
                and path in ad["nodes"][node]
            )
            default = np.asarray(ad["nodes"][node][path], dtype="<f4")
            assert np.array_equal(default.astype(float), ad["nodes"][node][path])
            sampler = new["samplers"][channel["sampler"]]
            assert sampler.get("interpolation", "LINEAR") == "LINEAR"
            assert (
                _array(bd, bb, sampler["output"]).tobytes()
                == np.tile(default, (2, 1)).tobytes()
            )
            clock = _array(bd, bb, sampler["input"]).ravel()
            assert np.array_equal(clock, [min(times), max(times)])
        candidate_times = np.concatenate(
            [_array(bd, bb, s["input"]).ravel() for s in new["samplers"]]
        )
        assert min(candidate_times) == min(times) and max(candidate_times) == max(times)
        knots = np.unique(times)
        test = np.unique(
            np.r_[
                knots,
                (knots[:-1] + knots[1:]) / 2,
                np.array([0.11337, 0.29381, 0.53119, 0.76347, 0.95131]) * knots.max(),
            ]
        )
        clips[old["name"]] = {
            "original_knots": len(knots),
            "all_keys_midpoints_and_offgrid_covered_by_exact_channel_identity": len(
                test
            ),
        }
    report = dict(
        passed=True,
        source_sha256=digest(source),
        candidate_sha256=digest(candidate),
        geometry_skin_binds_rest_topology_uv_material_image_bits_preserved=True,
        retained_key_time_and_value_bits_exact_only_flat_interiors_removed=True,
        every_removed_default_and_key_is_zero=True,
        redundant_flat_key_rows_proved=removed_rows,
        preexisting_duplicate_property_curves_preserved_in_occurrence_order=duplicate_curves,
        meshes=build["inactive_targets"]["meshes"],
        clips=clips,
        proof="Zero defaults and every LINEAR/STEP key zero prove inactive targets remain zero continuously and under crossfades. All retained accessor bytes and retained time/value rows are exact. Deleted key rows sit strictly inside three bit-identical adjacent rows; plateau boundaries and endpoints remain.",
    )
    (out / "exact-source-validation.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return report


def witness(job):
    source = pathlib.Path(job["source"])
    candidate = pathlib.Path(job["candidate"])
    out = pathlib.Path(job["output"])
    a = NativeShapeAsset(source)
    b = NativeShapeAsset(candidate)
    wp = pathlib.Path(job["witness"])
    if wp.exists():
        w = json.loads(wp.read_text())
        assert w["sha256"] == digest(source)
    else:
        count = len(a.vertices)
        ids = np.unique(
            np.r_[
                np.linspace(0, count - 1, min(count, 160), dtype=int),
                a.vertices.argmin(0),
                a.vertices.argmax(0),
            ]
        )
        sample = surface_sampler(a, ids)
        normal = normal_sampler(a, ids)
        height = float(np.ptp(a.vertices, axis=0)[1])
        clips = {}
        for clip in a.animations:
            duration = a.duration(clip)
            ts = np.unique(
                np.r_[
                    np.linspace(0, duration, 13),
                    np.array([0.03713, 0.13947, 0.29381, 0.49913, 0.73129, 0.93317])
                    * duration,
                ]
            )
            t, q, s, m = a.sample(clip, ts)
            entries = []
            for i, tm in enumerate(ts):
                world = a.world(t[i], q[i], s[i])
                mm = {n: v[i] for n, v in m.items()}
                entries.append(
                    dict(
                        time=float(tm),
                        surface=sample(world, mm).tolist(),
                        surface_normals=normal(world, mm).tolist(),
                        bones={
                            a.names[n]: world[n].reshape(-1).tolist() for n in a.joints
                        },
                    )
                )
            clips[clip] = entries
        w = dict(
            sha256=digest(source),
            height=height,
            surface_vertex_ids=ids.tolist(),
            clips=clips,
            durations={c: a.duration(c) for c in a.animations},
            scope="Frozen source-only physical observations captured before candidate import. No artistic approval or motion alteration. Exact source proof and independent fresh Blender/Godot imports are separate checks.",
        )
        wp.write_text(json.dumps(w, indent=2) + "\n")
    ids = np.array(w["surface_vertex_ids"])
    sa, sb = surface_sampler(a, ids), surface_sampler(b, ids)
    na, nb = normal_sampler(a, ids), normal_sampler(b, ids)
    maxpos = maxnorm = wpos = wnorm = wbone = source_wpos = 0.0
    surface_points = []
    for clip, entries in w["clips"].items():
        ts = [e["time"] for e in entries]
        at, aq, asc, am = a.sample(clip, ts)
        bt, bq, bsc, bm = b.sample(clip, ts)
        for i, e in enumerate(entries):
            aw = a.world(at[i], aq[i], asc[i])
            bw = b.world(bt[i], bq[i], bsc[i])
            av = {n: v[i] for n, v in am.items()}
            bv = {n: v[i] for n, v in bm.items()}
            ap = sa(aw, av)
            bp = sb(bw, bv)
            an = na(aw, av)
            bn = nb(bw, bv)
            maxpos = max(maxpos, float(np.linalg.norm(ap - bp, axis=1).max()))
            maxnorm = max(maxnorm, float(np.linalg.norm(an - bn, axis=1).max()))
            wpos = max(
                wpos,
                float(np.linalg.norm(bp - e["surface"], axis=1).max() / w["height"]),
            )
            source_wpos = max(source_wpos, float(np.linalg.norm(ap - e["surface"], axis=1).max() / w["height"]))
            if "surface_normals" in e:
                wnorm = max(
                    wnorm,
                    float(np.linalg.norm(bn - e["surface_normals"], axis=1).max()),
                )
            for name, values in e["bones"].items():
                wbone = max(
                    wbone,
                    float(
                        np.max(abs(bw[b.ids[name]] - np.asarray(values).reshape(4, 4)))
                    ),
                )
            surface_points.append(ap)
    assert (
        maxpos < 1e-12
        and maxnorm < 1e-12
        and source_wpos < .00025
        and wpos <= source_wpos + 1e-12
        and wnorm < 1e-8
        and wbone < 1e-9
    )
    pts = np.concatenate(surface_points)
    report = dict(
        passed=True,
        source_sha256=digest(source),
        candidate_sha256=digest(candidate),
        surface_probes=len(ids),
        poses=sum(map(len, w["clips"].values())),
        clips=len(w["clips"]),
        source_candidate_position_error=maxpos,
        source_candidate_normal_vector_error=maxnorm,
        original_witness_position_error_over_height=wpos,
        original_source_witness_position_error_over_height=source_wpos,
        original_witness_normal_vector_error=wnorm,
        original_witness_bone_matrix_error=wbone,
        witness_sha256=__import__("hashlib").sha256(wp.read_bytes()).hexdigest(),
        sampled_motion_min=pts.min(0).tolist(),
        sampled_motion_max=pts.max(0).tolist(),
    )
    (out / "physical-witness-validation.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=pathlib.Path, required=True)
    parser.add_argument("--phase", choices=("source", "physical"), default="source")
    args = parser.parse_args()
    job = json.loads(args.job.read_text(encoding="utf-8"))
    report = exact_source(job)
    physical = witness(job) if args.phase == "physical" else None
    print(
        json.dumps(
            dict(actor=job["actor"], exact_passed=report["passed"], physical=physical),
            indent=2,
        )
    )
