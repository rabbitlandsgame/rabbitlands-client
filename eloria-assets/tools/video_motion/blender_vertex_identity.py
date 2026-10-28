"""Prove imported Blender vertex identity before binding frozen motion probes.

Blender is invoked with merge_vertices=False. Position-only nearest neighbours
are unsafe when separate animated pieces coincide in the initial death pose.
This verifies the complete basis, UV, skin and POSITION target payload instead.
The helper imports no bpy or scipy, so its GLB decoding is also usable locally.
The correspondence budget accounts for bind-rest float32 import arithmetic; it
does not replace the independent posed-witness or Godot normal tolerances.
"""

import json
import struct
from pathlib import Path
import numpy as np

_DT = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
_W = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
_C = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])


def document(path):
    raw = Path(path).read_bytes()
    magic, version, size = struct.unpack_from("<III", raw)
    assert magic == 0x46546C67 and version == 2 and size == len(raw)
    chunks = {}
    offset = 12
    while offset < len(raw):
        length, kind = struct.unpack_from("<II", raw, offset)
        chunks[kind] = raw[offset + 8 : offset + 8 + length]
        offset += 8 + length
    return json.loads(chunks[0x4E4F534A]), chunks[0x004E4942]


def array(doc, blob, index):
    a = doc["accessors"][index]
    assert not a.get("sparse"), "Sparse source identity requires explicit support"
    dtype = np.dtype(_DT[a["componentType"]])
    shape = (a["count"], _W[a["type"]])
    if "bufferView" not in a:
        return np.zeros(shape, dtype=float)
    view = doc["bufferViews"][a["bufferView"]]
    assert view.get("buffer", 0) == 0
    result = np.ndarray(
        shape,
        dtype,
        blob,
        view.get("byteOffset", 0) + a.get("byteOffset", 0),
        strides=(view.get("byteStride", dtype.itemsize * shape[1]), dtype.itemsize),
    ).astype(float)
    if a.get("normalized"):
        limit = np.iinfo(dtype)
        result = (
            np.maximum(result / limit.max, -1.0)
            if limit.min < 0
            else result / limit.max
        )
    return result


def worlds(doc):
    nodes = doc["nodes"]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    cache = {}

    def get(i):
        if i in cache:
            return cache[i]
        node = nodes[i]
        if "matrix" in node:
            m = np.array(node["matrix"]).reshape(4, 4).T
        else:
            x, y, z, w = np.array(
                node.get("rotation", [0, 0, 0, 1]), float
            ) / np.linalg.norm(node.get("rotation", [0, 0, 0, 1]))
            r = np.array(
                [
                    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
                ]
            )
            m = np.eye(4)
            m[:3, :3] = r * np.array(node.get("scale", [1, 1, 1]))[None, :]
            m[:3, 3] = node.get("translation", [0, 0, 0])
        cache[i] = get(parent[i]) @ m if i in parent else m
        return cache[i]

    return [get(i) for i in range(len(nodes))]


def source_frames(doc, blob, node_index, node, primitives, world):
    count = sum(
        doc["accessors"][p["attributes"]["POSITION"]]["count"] for p in primitives
    )
    if "skin" not in node:
        return np.broadcast_to(world[node_index], (count, 4, 4)).copy()
    skin = doc["skins"][node["skin"]]
    bind = (
        array(doc, blob, skin["inverseBindMatrices"])
        .reshape(-1, 4, 4)
        .transpose(0, 2, 1)
    )
    matrices = np.array([world[j] for j in skin["joints"]]) @ bind
    result = []
    for primitive in primitives:
        attributes = primitive["attributes"]
        n = doc["accessors"][attributes["POSITION"]]["count"]
        frame = np.zeros((n, 4, 4))
        for si in sorted(
            int(k.split("_")[1]) for k in attributes if k.startswith("JOINTS_")
        ):
            js = array(doc, blob, attributes["JOINTS_" + str(si)]).astype(int)
            ws = array(doc, blob, attributes["WEIGHTS_" + str(si)])
            for slot in range(js.shape[1]):
                frame += matrices[js[:, slot]] * ws[:, slot, None, None]
        result.append(frame)
    return np.concatenate(result)


def skin_correspondence(expected, actual, positive_slots, names):
    """Recognize Blender's repeated-slot overwrite only for a single owner.

    Armature deformation must still pass the independent paired posed check.
    No imported groups are edited, and multi-bone distributions stay bit/value
    comparisons. A non-unit original total cannot take this exception.
    """
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    assert (
        expected.shape == actual.shape
        and np.isfinite(expected).all()
        and np.isfinite(actual).all()
    )
    assert np.all(expected >= 0) and np.all(actual >= 0)
    raw_error = float(np.abs(expected - actual).max())
    left, right = expected.copy(), actual.copy()
    records = []
    for vertex in np.flatnonzero(np.max(np.abs(left - right), axis=1) > 2e-6):
        source_bones = np.flatnonzero(left[vertex] > 0)
        imported_bones = np.flatnonzero(right[vertex] > 0)
        source_sum, imported_sum = float(left[vertex].sum()), float(right[vertex].sum())
        if (
            positive_slots[vertex] <= 1
            or len(source_bones) != 1
            or not np.array_equal(source_bones, imported_bones)
            or abs(source_sum - 1.0) > 4 * float(np.spacing(np.float32(1.0)))
            or imported_sum <= 0
        ):
            continue
        left[vertex] /= source_sum
        right[vertex] /= imported_sum
        records.append(
            dict(
                vertex=int(vertex),
                bone=names[int(source_bones[0])],
                source_positive_slots=int(positive_slots[vertex]),
                source_total=source_sum,
                blender_stored_total=imported_sum,
            )
        )
    return float(np.abs(left - right).max()), raw_error, records


def imported_bindings(path, objects):
    doc, blob = document(path)
    world = worlds(doc)
    bindings = []
    defaults = {}
    records = []
    used = set()
    meshes = [o for o in objects if o.type == "MESH"]
    for node_index, node in enumerate(doc["nodes"]):
        if "mesh" not in node:
            continue
        mesh = doc["meshes"][node["mesh"]]
        primitives = mesh["primitives"]
        positions = np.concatenate(
            [array(doc, blob, p["attributes"]["POSITION"]) for p in primitives]
        )
        count = len(positions)
        frame = source_frames(doc, blob, node_index, node, primitives, world)
        expected = (
            np.einsum("vij,vj->vi", frame[:, :3, :3], positions) + frame[:, :3, 3]
        ) @ _C.T
        extent = max(1.0, float(np.abs(expected).max()))
        # The importer accumulates rest transforms and skin influences in
        # float32 before storing its mesh. Account for those operations when
        # proving an ordinal; the independent posed comparison has its own
        # much tighter total-error gate.
        parents = {
            child: i
            for i, n in enumerate(doc["nodes"])
            for child in n.get("children", [])
        }

        def depth(index):
            steps = 1
            while index in parents:
                steps += 1
                index = parents[index]
            return steps

        # Unskinned attachments still inherit every authored parent transform
        # (including bone and grip nodes), rounded by Blender to float32.
        # Their local vertex rows remain exact and are checked below; only
        # this initial world-space identity comparison has composition error.
        composition_steps = depth(node_index)
        if "skin" in node:
            joint_depth = max(depth(i) for i in doc["skins"][node["skin"]]["joints"])
            influences = max(
                sum(4 for key in p["attributes"] if key.startswith("JOINTS_"))
                for p in primitives
            )
            composition_steps = joint_depth + influences
        budget = 16 * composition_steps * float(np.spacing(np.float32(extent)))
        candidates = []
        basis_strategy = "authored_joint_rest_skin"
        rest_skin_errors = []
        for ob in meshes:
            if ob.as_pointer() in used or len(ob.data.vertices) != count:
                continue
            values = np.empty((count, 3), np.float32)
            ob.data.vertices.foreach_get("co", values.ravel())
            if "skin" not in node and not np.array_equal(
                values, (positions @ _C.T).astype(np.float32)
            ):
                continue
            matrix = np.array(ob.matrix_world)
            actual = values @ matrix[:3, :3].T + matrix[:3, 3]
            difference = actual - expected
            error = float(np.linalg.norm(difference, axis=1).max())
            component_error = float(np.abs(difference).max())
            rest_skin_errors.append(component_error)
            # A coordinate ULP allowance applies to each coordinate. Retain
            # Euclidean error for diagnostics without comparing different units.
            if component_error <= budget:
                candidates.append((ob, error, component_error))
        if not candidates and "skin" in node:
            # Blender can choose the inverse-bind rest instead of the authored
            # joint rest. Its undeformed mesh then retains the original node's
            # raw basis. Prove every original row in that explicit space; UV,
            # skin, all POSITION targets and posed comparisons remain required.
            raw_frame = np.broadcast_to(world[node_index], (count, 4, 4)).copy()
            raw_expected = (
                positions @ world[node_index][:3, :3].T + world[node_index][:3, 3]
            ) @ _C.T
            raw_extent = max(1.0, float(np.abs(raw_expected).max()))
            raw_budget = 16 * composition_steps * float(np.spacing(np.float32(raw_extent)))
            for ob in meshes:
                if ob.as_pointer() in used or len(ob.data.vertices) != count:
                    continue
                values = np.empty((count, 3), np.float32)
                ob.data.vertices.foreach_get("co", values.ravel())
                matrix = np.array(ob.matrix_world)
                actual = values @ matrix[:3, :3].T + matrix[:3, 3]
                difference = actual - raw_expected
                error = float(np.linalg.norm(difference, axis=1).max())
                component_error = float(np.abs(difference).max())
                if component_error <= raw_budget:
                    candidates.append((ob, error, component_error))
            if candidates:
                frame, budget = raw_frame, raw_budget
                basis_strategy = "authored_mesh_node_raw_basis"
        named = [
            row
            for row in candidates
            if row[0].name == node.get("name")
            or row[0].name.startswith(str(node.get("name", "")) + ".")
        ]
        if named:
            candidates = named
        assert len(candidates) == 1, (
            "Unproved Blender mesh identity",
            node_index,
            node.get("name"),
            [(o.name, e, c) for o, e, c in candidates],
        )
        ob, basis_error, basis_component_error = candidates[0]
        used.add(ob.as_pointer())
        data = ob.data
        matrix = np.array(ob.matrix_world)
        normal_error = 0.0
        uv_error = 0.0
        skin_error = 0.0
        skin_raw_error = 0.0
        skin_normalizations = []
        shape_error = 0.0
        loop_ids = np.empty(len(data.loops), np.int32)
        data.loops.foreach_get("vertex_index", loop_ids)
        for uv_index in sorted(
            {
                int(k.split("_")[-1])
                for p in primitives
                for k in p["attributes"]
                if k.startswith("TEXCOORD_")
            }
        ):
            expected_uv = np.concatenate(
                [
                    (
                        array(doc, blob, p["attributes"]["TEXCOORD_" + str(uv_index)])
                        if "TEXCOORD_" + str(uv_index) in p["attributes"]
                        else np.zeros(
                            (doc["accessors"][p["attributes"]["POSITION"]]["count"], 2)
                        )
                    )
                    for p in primitives
                ]
            )
            actual_uv = np.empty((len(data.loops), 2), np.float32)
            data.uv_layers[uv_index].data.foreach_get("uv", actual_uv.ravel())
            expected_uv[:, 1] = 1.0 - expected_uv[:, 1]
            uv_error = max(
                uv_error, float(np.abs(actual_uv - expected_uv[loop_ids]).max())
            )
        if all("NORMAL" in p["attributes"] for p in primitives):
            normal = np.concatenate(
                [array(doc, blob, p["attributes"]["NORMAL"]) for p in primitives]
            )
            normal = np.einsum("vij,vj->vi", frame[:, :3, :3], normal) @ _C.T
            normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-30)
            actual_normal = np.empty((len(data.loops), 3), np.float32)
            data.corner_normals.foreach_get("vector", actual_normal.ravel())
            actual_normal = actual_normal @ np.linalg.inv(matrix[:3, :3])
            actual_normal /= np.maximum(
                np.linalg.norm(actual_normal, axis=1, keepdims=True), 1e-30
            )
            normal_error = float(
                np.linalg.norm(actual_normal - normal[loop_ids], axis=1).max()
            )
        if "skin" in node:
            skin = doc["skins"][node["skin"]]
            names = [doc["nodes"][i]["name"] for i in skin["joints"]]
            assert len(names) == len(set(names))
            expected_skin = np.zeros((count, len(names)))
            positive_slots = np.zeros(count, dtype=int)
            offset = 0
            for primitive in primitives:
                attributes = primitive["attributes"]
                n = doc["accessors"][attributes["POSITION"]]["count"]
                for si in sorted(
                    int(k.split("_")[1]) for k in attributes if k.startswith("JOINTS_")
                ):
                    js = array(doc, blob, attributes["JOINTS_" + str(si)]).astype(int)
                    ws = array(doc, blob, attributes["WEIGHTS_" + str(si)])
                    positive_slots[offset : offset + n] += np.count_nonzero(
                        ws > 0, axis=1
                    )
                    for slot in range(js.shape[1]):
                        np.add.at(
                            expected_skin,
                            (np.arange(n) + offset, js[:, slot]),
                            ws[:, slot],
                        )
                offset += n
            actual_skin = np.zeros_like(expected_skin)
            name_to_id = {n: i for i, n in enumerate(names)}
            for vertex in data.vertices:
                for group in vertex.groups:
                    name = ob.vertex_groups[group.group].name
                    assert name in name_to_id or group.weight == 0.0, (
                        "Unexpected source skin group",
                        name,
                    )
                    if name in name_to_id:
                        actual_skin[vertex.index, name_to_id[name]] += group.weight
            skin_error, skin_raw_error, skin_normalizations = skin_correspondence(
                expected_skin, actual_skin, positive_slots, names
            )
        counts = {len(p.get("targets", [])) for p in primitives}
        assert len(counts) == 1
        targets = counts.pop()
        key = data.shape_keys
        if targets:
            assert key is not None and len(key.key_blocks) == targets + 1
            basis = np.empty((count, 3), np.float32)
            key.key_blocks[0].data.foreach_get("co", basis.ravel())
            for target_index in range(targets):
                delta = np.concatenate(
                    [
                        (
                            array(doc, blob, p["targets"][target_index]["POSITION"])
                            if "POSITION" in p["targets"][target_index]
                            else np.zeros(
                                (
                                    doc["accessors"][p["attributes"]["POSITION"]][
                                        "count"
                                    ],
                                    3,
                                )
                            )
                        )
                        for p in primitives
                    ]
                )
                delta = np.einsum("vij,vj->vi", frame[:, :3, :3], delta) @ _C.T
                actual_delta = np.empty((count, 3), np.float32)
                key.key_blocks[target_index + 1].data.foreach_get(
                    "co", actual_delta.ravel()
                )
                actual_delta = (actual_delta - basis) @ matrix[:3, :3].T
                shape_error = max(
                    shape_error,
                    float(np.linalg.norm(delta - actual_delta, axis=1).max()),
                )
            defaults[key.as_pointer()] = node.get(
                "weights", mesh.get("weights", [0.0] * targets)
            )
        else:
            assert key is None or len(key.key_blocks) == 1
        assert uv_error < 2e-6 and skin_error < 2e-6 and shape_error <= budget, (
            "Blender vertex payload differs",
            node_index,
            basis_error,
            uv_error,
            skin_error,
            normal_error,
            shape_error,
            budget,
        )
        bindings.extend((ob, i) for i in range(count))
        records.append(
            {
                "source_node": node_index,
                "object": ob.name,
                "vertices": count,
                "position_targets": targets,
                "basis_world_error": basis_error,
                "basis_world_component_error": basis_component_error,
                "basis_strategy": basis_strategy,
                "authored_rest_skin_component_error": min(rest_skin_errors),
                "uv_error": uv_error,
                "skin_error": skin_error,
                "skin_raw_group_error": skin_raw_error,
                "skin_lone_group_normalizations": skin_normalizations,
                "normal_vector_error": normal_error,
                "normal_scope": "Recorded only; Blender custom-normal packing is not the authority for source/Godot shading. Vertex motion identity is proved by basis,UV,skin and every POSITION shape.",
                "all_target_position_error": shape_error,
                "position_budget": budget,
                "rest_composition_steps": composition_steps,
            }
        )
    return bindings, defaults, records
