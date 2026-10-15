#!/usr/bin/env python3
"""Import the CC0 Quaternius base characters and Universal animations.

This is an authoring-only importer.  It writes compact, dependency-free source
files consumed by ``generate_authored_players.py``; the original distribution
archives are deliberately not checked into the repository.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import zlib

import numpy as np
from PIL import Image

COMPONENT_DTYPES = {5121: "<u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
TYPE_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
CLIPS = {
    "idle": "Idle_A", "idle2": "Idle_Subtle", "walk": "Walk", "run": "Jog",
    "combat_idle": "Fighting_Idle", "attack": "Sword_Attack",
    "cast": "Spell_Simple_Shoot", "pain": "Hit_Chest", "die": "Death_A",
    "sit_down": "Sitting_Enter", "sit": "Sitting_Idle", "stand_up": "Sitting_Exit",
    "harvest": "Farm_Harvest", "pick": "PickUp_Table", "drop": "Throw_Object",
}
TARGET_BONES = {
    "root": 0, "pelvis": 1, "spine_01": 2, "head": 3,
    "upperarm_l": 4, "lowerarm_l": 5, "upperarm_r": 6, "lowerarm_r": 7,
    "thigh_l": 8, "calf_l": 9, "foot_l": 10,
    "thigh_r": 11, "calf_r": 12, "foot_r": 13,
    "hand_l": 16, "hand_r": 17, "spine_03": 25, "neck_01": 26,
    "clavicle_l": 27, "clavicle_r": 28,
    "thumb_01_l": 31, "index_01_l": 32,
    "thumb_01_r": 33, "index_01_r": 34,
    "ball_l": 35, "ball_r": 36,
}
TARGET_PARENTS = {
    0:-1, 1:0, 2:1, 3:2, 4:2, 5:4, 6:2, 7:6, 8:1, 9:8, 10:9,
    11:1, 12:11, 13:12, 16:5, 17:7, 25:2, 26:25, 27:25, 28:25,
    32:16, 33:16, 34:17, 35:10, 36:13,
}
REFERENCE_POSE = "Idle_A"
SOURCE_TEXTURE_SIZE = (512, 512)


def read_document(path: Path):
    if path.suffix.lower() == ".gltf":
        document = json.loads(path.read_text(encoding="utf-8"))
        uri = document["buffers"][0]["uri"]
        return document, (path.parent / uri).read_bytes()
    data = path.read_bytes(); offset = 12; chunks = {}
    if data[:4] != b"glTF": raise ValueError(f"not a glTF 2 file: {path}")
    while offset < len(data):
        length, kind = struct.unpack_from("<II", data, offset); offset += 8
        chunks[kind] = data[offset:offset + length]; offset += length
    return json.loads(chunks[0x4E4F534A]), chunks[0x004E4942]


def accessor(document, binary, index):
    spec = document["accessors"][index]; view = document["bufferViews"][spec["bufferView"]]
    dtype = np.dtype(COMPONENT_DTYPES[spec["componentType"]]); width = TYPE_WIDTHS[spec["type"]]
    start = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
    stride = view.get("byteStride", dtype.itemsize * width)
    shape = (spec["count"],) if width == 1 else (spec["count"], width)
    strides = (stride,) if width == 1 else (stride, dtype.itemsize)
    return np.ndarray(shape, dtype=dtype, buffer=binary, offset=start, strides=strides).copy()


def body_primitive(document):
    nodes = [node for node in document["nodes"] if "mesh" in node]
    body = max(nodes, key=lambda node: document["accessors"][
        document["meshes"][node["mesh"]]["primitives"][0]["attributes"]["POSITION"]]["count"])
    return document["meshes"][body["mesh"]]["primitives"][0]


def quat_mul(a, b):
    ax,ay,az,aw=a; bx,by,bz,bw=b
    return (aw*bx+ax*bw+ay*bz-az*by, aw*by-ax*bz+ay*bw+az*bx,
            aw*bz+ax*by-ay*bx+az*bw, aw*bw-ax*bx-ay*by-az*bz)


def quat_inverse(value):
    x,y,z,w=value; length=x*x+y*y+z*z+w*w
    return (-x/length,-y/length,-z/length,w/length)


def runtime_quaternion(value):
    # Conjugate by +90 degrees around X: source Y-up/+Z-forward to EL Z-up/-Y-forward.
    half = 2 ** -.5; change=(half,0.,0.,half); inverse=(-half,0.,0.,half)
    result=quat_mul(quat_mul(change, tuple(map(float,value))), inverse)
    if result[3] < 0: result=tuple(-v for v in result)
    return [round(v,7) for v in result]


def global_rotations(document, local_rotations):
    parents={child:parent for parent,node in enumerate(document["nodes"])
             for child in node.get("children", [])}
    result={}
    def resolve(node):
        if node not in result:
            local=local_rotations.get(node,tuple(document["nodes"][node].get("rotation",(0.,0.,0.,1.))))
            result[node]=quat_mul(resolve(parents[node]),local) if node in parents else local
        return result[node]
    for node in range(len(document["nodes"])): resolve(node)
    return result


def sample_quaternion(times, values, time):
    index=int(np.searchsorted(times,time,side="left"))
    if index<=0: return tuple(map(float,values[0]))
    if index>=len(times): return tuple(map(float,values[-1]))
    if abs(float(times[index])-time)<1e-7: return tuple(map(float,values[index]))
    a=np.asarray(values[index-1],dtype=np.float64); b=np.asarray(values[index],dtype=np.float64)
    if np.dot(a,b)<0: b=-b
    amount=(time-float(times[index-1]))/(float(times[index])-float(times[index-1]))
    value=a+(b-a)*amount; value/=np.linalg.norm(value)
    return tuple(map(float,value))


def matrix_trs(node, rotation=None, translation=None):
    if "matrix" in node and rotation is None and translation is None:
        return np.asarray(node["matrix"],dtype=np.float64).reshape(4,4).T
    x,y,z,w=rotation or node.get("rotation",(0.,0.,0.,1.)); scale=node.get("scale",(1.,1.,1.))
    xx,yy,zz=x*x,y*y,z*z; xy,xz,yz=x*y,x*z,y*z; wx,wy,wz=w*x,w*y,w*z
    result=np.array([[1-2*(yy+zz),2*(xy-wz),2*(xz+wy),0.],
                     [2*(xy+wz),1-2*(xx+zz),2*(yz-wx),0.],
                     [2*(xz-wy),2*(yz+wx),1-2*(xx+yy),0.],
                     [0.,0.,0.,1.]],dtype=np.float64)
    result[:3,:3] *= np.asarray(scale,dtype=np.float64)[None,:]
    result[:3,3]=translation or node.get("translation",(0.,0.,0.))
    return result


def global_matrices(document, local_overrides=None):
    local_overrides=local_overrides or {}; parents={child:parent for parent,node in enumerate(document["nodes"])
                                                    for child in node.get("children", [])}; result={}
    def resolve(index):
        if index not in result:
            rotation,translation=local_overrides.get(index,(None,None))
            local=matrix_trs(document["nodes"][index],rotation,translation)
            result[index]=resolve(parents[index])@local if index in parents else local
        return result[index]
    for index in range(len(document["nodes"])): resolve(index)
    return result


def reference_pose(animation_document, animation_binary):
    animation=next((item for item in animation_document["animations"]
                    if item.get("name")==REFERENCE_POSE),None)
    if animation is None: raise ValueError(f"missing Universal reference pose: {REFERENCE_POSE}")
    overrides={}
    for channel in animation["channels"]:
        path=channel["target"]["path"]
        if path not in ("rotation","translation"): continue
        sampler=animation["samplers"][channel["sampler"]]
        values=accessor(animation_document,animation_binary,sampler["output"])
        node=channel["target"]["node"]; rotation,translation=overrides.get(node,(None,None))
        if path=="rotation": rotation=tuple(map(float,values[0]))
        else: translation=tuple(map(float,values[0]))
        overrides[node]=(rotation,translation)
    globals_by_index=global_matrices(animation_document,overrides)
    return {(node.get("name") or "").lower():globals_by_index[index]
            for index,node in enumerate(animation_document["nodes"])}


def mapped_bone(document, node_index):
    parents={child:parent for parent,node in enumerate(document["nodes"])
             for child in node.get("children", [])}
    while True:
        bone=TARGET_BONES.get((document["nodes"][node_index].get("name") or "").lower())
        if bone is not None: return bone
        if node_index not in parents: return 0
        node_index=parents[node_index]


def import_model(document,binary,pose_by_name):
    primitive=body_primitive(document); attributes=primitive["attributes"]
    positions=accessor(document,binary,attributes["POSITION"]).astype(np.float64)
    normals=accessor(document,binary,attributes["NORMAL"]).astype(np.float64)
    uvs=accessor(document,binary,attributes["TEXCOORD_0"]).astype(np.float64)
    joints=accessor(document,binary,attributes["JOINTS_0"]).astype(np.int64)
    weights=accessor(document,binary,attributes["WEIGHTS_0"]).astype(np.float64)
    faces=accessor(document,binary,primitive["indices"]).astype(np.int64).reshape(-1,3)
    skin=document["skins"][0]; inverse_bind=accessor(document,binary,skin["inverseBindMatrices"])
    inverse_bind=inverse_bind.reshape(-1,4,4).transpose(0,2,1)
    joint_nodes=skin["joints"]; matrices=[]; normal_matrices=[]
    for joint,node_index in enumerate(joint_nodes):
        name=document["nodes"][node_index].get("name")
        posed=pose_by_name.get((name or "").lower())
        if posed is None: raise ValueError(f"reference pose lacks joint: {name}")
        matrix=posed@inverse_bind[joint]; matrices.append(matrix)
        normal_matrices.append(np.linalg.inv(matrix[:3,:3]).T)
    posed_positions=np.zeros_like(positions); posed_normals=np.zeros_like(normals)
    mapped_weights=[]
    for index,(position,normal) in enumerate(zip(positions,normals)):
        homogeneous=np.append(position,1.); combined={}
        for slot,(joint,weight) in enumerate(zip(joints[index],weights[index])):
            if weight<=1e-6: continue
            posed_positions[index]+=weight*(matrices[joint]@homogeneous)[:3]
            posed_normals[index]+=weight*(normal_matrices[joint]@normal)
            bone=mapped_bone(document,joint_nodes[joint]); combined[bone]=combined.get(bone,0.)+float(weight)
        length=np.linalg.norm(posed_normals[index]) or 1.; posed_normals[index]/=length
        selected=sorted(combined.items(),key=lambda item:item[1],reverse=True)[:4]
        total=sum(weight for _,weight in selected) or 1.; mapped_weights.append([(bone,weight/total) for bone,weight in selected])
    low,high=posed_positions.min(axis=0),posed_positions.max(axis=0); uniform=1.82/(high[1]-low[1])
    runtime_positions=np.column_stack((posed_positions[:,0]*uniform,-posed_positions[:,2]*uniform,
                                       (posed_positions[:,1]-low[1])*uniform))
    runtime_normals=np.column_stack((posed_normals[:,0],-posed_normals[:,2],posed_normals[:,1]))
    return runtime_positions.astype("<f4"),runtime_normals.astype("<f4"),uvs.astype("<f4"),faces.astype("<u4"),mapped_weights


def write_weighted_emesh(path,positions,normals,uvs,faces,weights):
    payload=bytearray(struct.pack("<II",len(positions),len(faces)))
    payload.extend(positions.tobytes());payload.extend(normals.tobytes());payload.extend(uvs.tobytes())
    for influences in weights:
        padded=influences+[(0,0.)]*(4-len(influences))
        payload.extend(struct.pack("<4H4f",*(bone for bone,_ in padded),*(weight for _,weight in padded)))
    payload.extend(faces.tobytes()); compressed=zlib.compress(bytes(payload),9)
    path.write_bytes(b"EMSH\x02\0\0\0"+struct.pack("<II",len(payload),len(compressed))+compressed)


def import_animations(path: Path, output: Path):
    document, binary = read_document(path)
    by_name={animation.get("name"): animation for animation in document.get("animations", [])}
    node_names={index:node.get("name", "") for index,node in enumerate(document["nodes"])}
    reference=next(item for item in document["animations"] if item.get("name")==REFERENCE_POSE)
    reference_local={}
    for channel in reference["channels"]:
        if channel["target"]["path"]!="rotation": continue
        sampler=reference["samplers"][channel["sampler"]]
        reference_local[channel["target"]["node"]]=tuple(accessor(document,binary,sampler["output"])[0])
    rest_global=global_rotations(document,reference_local)
    result={"schema":2,"source":"Quaternius Universal Animation Library","clips":{}}
    for target, source in CLIPS.items():
        animation=by_name.get(source)
        if animation is None: raise ValueError(f"missing Universal animation: {source}")
        source_tracks={}; duration=0.
        for channel in animation["channels"]:
            if channel["target"]["path"] != "rotation": continue
            node=channel["target"]["node"]
            if node_names[node] not in TARGET_BONES: continue
            sampler=animation["samplers"][channel["sampler"]]
            channel_times=accessor(document,binary,sampler["input"]); values=accessor(document,binary,sampler["output"])
            duration=max(duration,float(channel_times[-1])); source_tracks[node]=(channel_times,values)
        times=sorted({round(float(time),6) for channel_times,_ in source_tracks.values()
                      for time in channel_times})
        tracks={str(bone):[] for bone in TARGET_BONES.values()}
        source_for_bone={bone:node for node,name in node_names.items()
                         if (bone:=TARGET_BONES.get(name)) is not None}
        for time in times:
            local={node:sample_quaternion(channel_times,values,time)
                   for node,(channel_times,values) in source_tracks.items()}
            animated_global=global_rotations(document,local); target_global={}
            for bone,node in source_for_bone.items():
                delta=quat_mul(animated_global[node],quat_inverse(rest_global[node]))
                target_global[bone]=tuple(runtime_quaternion(delta))
            for bone in sorted(source_for_bone):
                parent=TARGET_PARENTS[bone]
                parent_global=target_global.get(parent,(0.,0.,0.,1.))
                rotation=quat_mul(quat_inverse(parent_global),target_global[bone])
                if rotation[3]<0: rotation=tuple(-value for value in rotation)
                tracks[str(bone)].append([round(float(time),6),[round(float(value),7) for value in rotation]])
        result["clips"][target]={"source":source,"duration":round(duration,6),"tracks":tracks}
    raw=json.dumps(result,separators=(",", ":"),sort_keys=True).encode("utf-8")
    output.write_bytes(b"EANM\x01\0\0\0"+struct.pack("<I",len(raw))+zlib.compress(raw,9))


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("characters",type=Path)
    parser.add_argument("animations",type=Path); parser.add_argument("output",type=Path)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    animation_document,animation_binary=read_document(args.animations)
    pose_by_name=reference_pose(animation_document,animation_binary)
    manifest={"schema":2,"license":"CC0-1.0","author":"Quaternius","models":{}}
    for gender,filename in (("female","Superhero_Female_FullBody.gltf"),
                            ("male","Superhero_Male_FullBody.gltf")):
        source=next(args.characters.rglob(filename)); document,binary=read_document(source)
        positions,normals,uvs,faces,weights=import_model(document,binary,pose_by_name)
        name=f"luminous_{gender}"; write_weighted_emesh(args.output/f"{name}.emesh",positions,normals,uvs,faces,weights)
        texture_name="T_Superhero_Female_Light_BaseColor.png" if gender=="female" else "T_Superhero_Male_Ligh.png"
        texture=next(args.characters.rglob(texture_name))
        # Runtime compositor inputs top out at 216 px.  A losslessly encoded
        # 2048 RGBA source exceeds the repository API's binary upload limit;
        # retain more than 2x oversampling for the largest compositor input
        # while keeping each checked-in PNG complete.
        image=Image.open(texture).convert("RGBA").resize(SOURCE_TEXTURE_SIZE,Image.Resampling.LANCZOS)
        image.save(args.output/f"{name}.png",optimize=True,compress_level=9)
        manifest["models"][name]={"source":filename,"vertices":len(positions),"triangles":len(faces),
                                  "cell":.006,"uv_bins":96}
        print(f"{name}: {len(positions)} vertices, {len(faces)} triangles")
    import_animations(args.animations,args.output/"luminous_universal.eanim")
    (args.output/"quaternius_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")


if __name__ == "__main__": main()
