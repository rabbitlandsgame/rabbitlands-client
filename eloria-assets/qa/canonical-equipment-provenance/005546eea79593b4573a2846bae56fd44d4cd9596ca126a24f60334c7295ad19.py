"""Close cut source-cloth boundaries independently of neighbouring limb parts."""
import numpy as np

import conform_equipment as ce


def smooth_skin(points, faces, joints, weights, bone_count, strength=2.0, fixed=None):
    """Regularize sampled cloth weights on welded adjacency, not UV vertices."""
    from scipy.sparse import coo_matrix, diags, eye
    from scipy.sparse.linalg import spsolve
    canonical, edges, count = ce._weld(points, faces)
    dense = np.zeros((count, bone_count))
    repeats = np.bincount(canonical, minlength=count)
    for k in range(4):
        np.add.at(dense, (canonical, joints[:,k]), weights[:,k])
    dense /= repeats[:,None]
    edges = edges[edges[:,0] != edges[:,1]]
    row = np.r_[edges[:,0],edges[:,1]];col = np.r_[edges[:,1],edges[:,0]]
    adjacency = coo_matrix((np.ones(len(row)),(row,col)),shape=(count,count)).tocsr()
    degree = np.asarray(adjacency.sum(axis=1)).ravel()
    laplacian = diags(1/np.maximum(degree,1)) @ (diags(degree)-adjacency)
    matrix = (eye(count,format='csr')+strength*laplacian).tolil()
    if fixed is not None:
        for vertex in np.unique(canonical[fixed]):
            matrix.rows[vertex] = [int(vertex)]
            matrix.data[vertex] = [1.]
    result = np.maximum(spsolve(matrix.tocsr(),dense),0)
    j = np.argsort(-result,axis=1)[:,:4]
    w = np.take_along_axis(result,j,axis=1)
    w /= np.maximum(w.sum(axis=1,keepdims=True),1e-10)
    return j[canonical].astype(np.uint16),w[canonical]


def thickened_sheets(outer, inner, normals, faces, joints, weights):
    """Thicken manifold sheets separately at source non-manifold junctions.

    Meshy body faces can meet three at an edge. Extruding that edge as though
    two faces met there leaves the lining open. Split those faces into sheets
    without moving the source-derived surface, then close every sheet's rim.
    Shared internal rim walls coincide; the visible surface is unchanged.
    """
    sheets, counts = [[]], [{}]
    for face in faces:
        if len(set(face)) < 3:
            continue
        edges = [tuple(sorted((int(face[a]), int(face[b])))) for a,b in ((0,1),(1,2),(2,0))]
        target = next((i for i,c in enumerate(counts) if all(c.get(e,0)<2 for e in edges)), None)
        if target is None:
            target=len(sheets); sheets.append([]); counts.append({})
        sheets[target].append(face)
        for edge in edges:
            counts[target][edge] = counts[target].get(edge,0)+1
    pp,nn,uu,ff,jj,ww = [],[],[],[],[],[]
    for sheet in sheets:
        used, inv = np.unique(sheet,return_inverse=True)
        f=inv.reshape(-1,3); size=len(used)
        edges=np.vstack([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]])
        _, inverse, degree=np.unique(np.sort(edges,axis=1),axis=0,return_inverse=True,return_counts=True)
        border=edges[degree[inverse]==1]
        walls=[(b,a,a+size) for a,b in border]+[(b,a+size,b+size) for a,b in border]
        triangles=np.vstack([f,f[:,::-1]+size,np.asarray(walls,dtype=int).reshape(-1,3)])
        points=np.vstack([outer[used],inner[used]])
        offset=sum(len(p) for p in pp)
        pp.append(points); nn.append(np.vstack([normals[used],-normals[used]]))
        uu.append(points[:,[0,1]]); ff.append(triangles+offset)
        jj.append(np.vstack([joints[used],joints[used]]));ww.append(np.vstack([weights[used],weights[used]]))
    p,n,f=np.vstack(pp),np.vstack(nn),np.vstack(ff)
    # The new lining is constructed as a solid. A tiny disconnected fold at
    # a clipped neckline can extrude opposite to its averaged source normals;
    # orient each closed component after float32 export quantization.
    canonical, edges, count = ce._weld(p, f)
    labels=ce._components(edges,count)[canonical]
    quantized=p.astype(np.float32).astype(np.float64)
    for label in np.unique(labels):
        own=labels==label;mask=own[f].all(axis=1);faces=f[mask]
        pairs=np.sort(canonical[faces[:,[0,1,1,2,2,0]]].reshape(-1,2),axis=1)
        _,degree=np.unique(pairs,axis=0,return_counts=True)
        if not len(faces) or not (degree%2==0).all():continue
        q=quantized-quantized[own].mean(axis=0)
        volume=np.einsum('ij,ij->i',q[faces[:,0]],np.cross(q[faces[:,1]],q[faces[:,2]])).sum()/6.
        if volume<0:
            f[mask]=faces[:,[0,2,1]];n[own]*=-1
    return p,n,np.vstack(uu),f.ravel(),np.vstack(jj),np.vstack(ww)


def close_cuts(points, faces, original_faces, joints, weights, rig, owners=None, source_points=None, region="torso"):
    """Return cloth panels only for boundaries introduced by the source split.

    Never bridge a sleeve back to a distant flank. Each connected cut boundary
    receives its own panel, with short edges so the panel can follow elbows.
    Existing source openings, such as collars and cuffs, are left alone.
    """
    canonical, _, count = ce._weld(points, original_faces)
    first = np.full(count, -1, dtype=int)
    first[canonical] = np.arange(len(points))
    old = canonical[original_faces]
    old_edges = np.sort(np.vstack([old[:, [0, 1]], old[:, [1, 2]], old[:, [2, 0]]]), axis=1)
    oe, oc = np.unique(old_edges, axis=0, return_counts=True)
    original_boundary = {tuple(e) for e in oe[oc == 1]}
    ff = canonical[faces]
    directed = np.vstack([ff[:, [0, 1]], ff[:, [1, 2]], ff[:, [2, 0]]])
    _, inv, counts = np.unique(np.sort(directed, axis=1), axis=0, return_inverse=True, return_counts=True)
    border = directed[counts[inv] == 1]
    if not len(border):
        return None
    if owners is not None:
        own = owners[first]
        border = border[own[border[:, 0]] == own[border[:, 1]]]
    labels = ce._components(border, count)
    patch_points, patch_joints, patch_weights, patch_faces, patch_source = [], [], [], [], []
    for group in np.unique(labels[border.ravel()]):
        edges = border[labels[border[:, 0]] == group]
        if all(tuple(sorted(e)) in original_boundary for e in edges):
            continue
        used = np.unique(edges)
        # An open chain touching an intentional source rim is not a cap.
        vertices, degree = np.unique(edges, return_counts=True)
        ends = vertices[degree == 1]
        if owners is not None and len(ends) == 2 and (degree <= 2).all():
            outgoing = set(edges[:, 0]); incoming = set(edges[:, 1])
            start = next((int(v) for v in ends if v not in incoming), int(ends[0]))
            finish = next((int(v) for v in ends if v not in outgoing), int(ends[1]))
            edges = np.vstack([edges, [finish, start]])
        elif (degree != 2).any():
            continue
        indices = first[used]
        block = points[indices]
        mid = block.mean(axis=0)
        p = np.vstack([block, mid])
        w = np.zeros((len(p), len(rig.joint_names)))
        for k in range(4):
            w[np.arange(len(block)), joints[indices, k]] += weights[indices, k]
        w[-1] = w[:-1].mean(axis=0)
        lookup = {int(v): i for i, v in enumerate(used)}
        f = np.array([(lookup[int(b)], lookup[int(a)], len(block)) for a, b in edges])
        # Concentric rings share every edge, including the original boundary.
        # A per-triangle refinement would leave T-junctions between panels.
        rings = max(1, min(32, int(np.ceil(np.linalg.norm(block-mid, axis=1).max()/.025))))
        ring_points, ring_weights, ring_source = [], [], []
        source_block = source_points[indices] if source_points is not None else block
        source_mid = source_block.mean(axis=0)
        for row in range(rings):
            t = row / rings
            ring_points.append(block*(1-t)+mid*t)
            ring_source.append(source_block*(1-t)+source_mid*t)
            ring_weights.append(w[:-1]*(1-t)+w[-1]*t)
        p = np.vstack([*ring_points, mid])
        w = np.vstack([*ring_weights, w[-1]])
        center = len(p)-1
        f = []
        n = len(block)
        for aa, bb in edges:
            a, b = lookup[int(aa)], lookup[int(bb)]
            for row in range(rings-1):
                x,y = a+row*n,b+row*n
                f.extend([(y,x,x+n),(y,x+n,y+n)])
            f.append((b+(rings-1)*n,a+(rings-1)*n,center))
        f = np.asarray(f)
        if region == 'legs':
            side = 'l' if bool(owners[indices[0]]) else 'r'
            candidates = ['pelvis'] + [b+'_'+side for b in ['thigh','calf']]
        elif owners is not None and owners[indices[0]] != 0:
            side = 'l' if owners[indices[0]] == 1 else 'r'
            candidates = ['upperarm_'+side,'lowerarm_'+side]
        else:
            candidates = list(ce.ea.TORSO_BONES) + ['pelvis']
        inherited_j, inherited_w = rig.weights_for(p, candidates)
        w[:] = 0.
        for k in range(4):
            w[np.arange(len(p)), inherited_j[:,k]] += inherited_w[:,k]
        w[:len(block)] = 0.
        for k in range(4):
            w[np.arange(len(block)), joints[indices,k]] += weights[indices,k]
        j = np.argsort(-w, axis=1)[:, :4]
        ww = np.take_along_axis(w, j, axis=1)
        ww /= np.maximum(ww.sum(axis=1, keepdims=True), 1e-9)
        j, ww = smooth_skin(p, f, j, ww, len(rig.joint_names), strength=12., fixed=np.arange(len(block)))
        if region == 'legs':
            from equipment_skinning import constrain_legs
            j, ww = constrain_legs(p, j, ww, rig)
        base = sum(len(v) for v in patch_points)
        patch_source.append(np.vstack([*ring_source, source_mid]))
        patch_points.append(p); patch_joints.append(j); patch_weights.append(ww); patch_faces.append(f+base)
    if not patch_points:
        return None
    result = tuple(np.vstack(v) for v in (patch_points, patch_faces, patch_joints, patch_weights))
    return result + (np.vstack(patch_source),) if source_points is not None else result
