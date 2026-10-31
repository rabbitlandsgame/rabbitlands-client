"""Optional topological separation of measured nonmanifold reference contacts."""
import hashlib
from pathlib import Path

def split_contacts(bm,uv_layer,normal_layer,face_id_layer):
    import bmesh
    bm.edges.ensure_lookup_table();bm.faces.ensure_lookup_table()
    selected=[edge for edge in bm.edges if len(edge.link_faces)>2]
    def corners(face):
        return sorted(tuple(loop.vert.co)+tuple(loop[uv_layer].uv)+tuple(loop[normal_layer]) for loop in face.loops)
    before={int(face[face_id_layer]):corners(face) for face in bm.faces}
    faces=len(bm.faces);vertices=len(bm.verts)
    if selected:bmesh.ops.split_edges(bm,edges=selected)
    assert len(bm.faces)==faces,'Contact splitting must preserve every source face'
    after={int(face[face_id_layer]):corners(face) for face in bm.faces}
    assert before==after,'Contact splitting changed source positions, UVs or normals'
    return {'enabled':True,'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'selected_edges':len(selected),'selection':'more than two incident faces only','vertices_before':vertices,'vertices_after':len(bm.verts),'faces_before':faces,'faces_after':len(bm.faces),'face_corner_positions_uv_normals_exact':True,'remaining_nonmanifold_edges':sum(len(edge.link_faces)>2 for edge in bm.edges)}
