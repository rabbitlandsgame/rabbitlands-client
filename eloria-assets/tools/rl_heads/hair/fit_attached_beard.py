"""Build a continuous attached short beard on the canonical head skin.

The approved beard supplies painted texture and fine whiskers. The connected
foundation uses the head's own surface, weights and morphs, with a narrow lip
opening and feathered cheek/neck margins. No source file is overwritten.
"""
import argparse,copy,hashlib,json
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from scipy.spatial import ConvexHull
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import rlglb,headref,assemble,build_beard

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def attributes(g,b,p):return {k:rlglb.accessor(g,b,v) for k,v in p['attributes'].items()}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',required=True);ap.add_argument('--texture',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    source=Path(a.source);dest=Path(a.out);assert source.resolve()!=dest.resolve();dest.parent.mkdir(parents=True,exist_ok=True)
    g,b=rlglb.read(str(source));head=headref.Head('male');hg,hb=head.gltf,head.blob
    spec=json.loads((Path(__file__).parent/'beards/short_beard.json').read_text());B=build_beard.beard_center(head)
    lips=head.P[head.vgroups['lips']];lip_tree=cKDTree(lips);lip_boundary=ConvexHull(lips[:,:2]).equations
    top=build_beard.boundary_fn([[0,4.5],[8,4.5],[12,4.5],[18,2.5],[25,-1],[34,2],[48,12],[58,25],[64,30]])
    bottom=build_beard.boundary_fn(spec['region']['bottom'])
    def field(P):
        lon,lat=build_beard.frame_lonlat(B,P);lo=abs(lon)
        angle=np.minimum(np.minimum(top(lo)-lat,lat-bottom(lo)),64-lo)*.0025
        lip_margin=(P[:,:2]@lip_boundary[:,:2].T+lip_boundary[:,2]).max(1)-.00025
        density=np.minimum(assemble.smoothstep(angle/.004),assemble.smoothstep(lip_margin/.0008))
        return np.minimum(angle,lip_margin),density
    src=g['meshes'][0]['primitives'][0];s=attributes(g,b,src);ST=rlglb.accessor(g,b,src['indices']).astype(int).reshape(-1,3)
    mass=ST[(s['TEXCOORD_0'][ST,1]<.6505).all(1)];mass=mass[np.linalg.norm(headref.tri_normals(s['POSITION'],mass),axis=1)>1e-12];reference=trimesh.Trimesh(s['POSITION'],mass,process=False)
    writer=assemble.Writer('Rabbit Lands continuous skin-attached short beard');mat=writer.material('rl_beard',[1,1,1,1],cutoff=.35,double=True,extras={'texture':'short_beard.png','referenceSurface':True,'softHairline':True,'featheredRoots':True,'skinAttachedFoundation':True});writer.embed_texture(mat,a.texture)
    report={'source_sha256':digest(source),'texture_sha256':digest(a.texture),'head_sha256':digest(head.glb_path),'tool_sha256':digest(__file__),'lods':{},'edge_feather_mm':4.0,'lip_gap_mm':.25,'lip_feather_mm':.8}
    for lod in range(3):
        hm=next(m for m in hg['meshes'] if m['name']==f'rl_head_lod{lod}');hp=hm['primitives'][0];ha=attributes(hg,hb,hp);HP=ha['POSITION'];HT=rlglb.accessor(hg,hb,hp['indices']).astype(int).reshape(-1,3);names=hm['extras']['targetNames'];HD=[rlglb.accessor(hg,hb,t['POSITION']) for t in hp['targets']]
        sdf,_=field(HP);keep=(sdf[HT].max(1)>-.004)&(HP[HT,1].min(1)>1.495)&(HP[HT,2].max(1)>-.04)
        if lod==0:keep &= ~head.vgroups['ears'][HT].any(1) & ~head.mouth_interior
        used,inv=np.unique(HT[keep],return_inverse=True);P0=HP[used];T0=inv.reshape(-1,3)
        # The narrow moustache and edge feather need intermediate coverage
        # samples at every LOD; a single coarse triangle can fade them away.
        P0,T0=trimesh.remesh.subdivide(P0,T0)
        for _ in range(min(lod,1)):
            margin,_=field(P0);edge=(margin[T0].min(1)<.006)&(margin[T0].max(1)>-.001)
            P0,T0=trimesh.remesh.subdivide(P0,T0,face_index=np.flatnonzero(edge))
        sd,_=field(P0);points=[];triangles=[]
        for t in T0:
            poly=[(P0[i],sd[i]) for i in t];clipped=[]
            for k,(v,fv) in enumerate(poly):
                u,fu=poly[(k+1)%3]
                if fv>=0:clipped.append(v)
                if (fv<0)!=(fu<0):clipped.append(v+(u-v)*(fv/(fv-fu)))
            start=len(points);points.extend(clipped)
            for k in range(1,len(clipped)-1):triangles.append([start,start+k,start+k+1])
        P=np.asarray(points);T=np.asarray(triangles,int);_,first,remap=np.unique(np.round(P,8),axis=0,return_index=True,return_inverse=True);P=P[first];T=remap[T];T=T[np.linalg.norm(headref.tri_normals(P,T),axis=1)>1e-12]
        edges=T[:,[0,1,1,2,2,0]].reshape(-1,2);graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(P),len(P))).tocsr();_,labels=connected_components(graph,directed=False);groups=labels[T[:,0]];values,counts=np.unique(groups,return_counts=True);T=T[groups==values[np.argmax(counts)]]
        surface=trimesh.Trimesh(HP,HT,process=False);cp,_,ti=trimesh.proximity.closest_point(surface,P);bc=headref.barycentric(cp,HP[HT[ti,0]],HP[HT[ti,1]],HP[HT[ti,2]])
        _,head_weld=np.unique(np.round(HP,6),axis=0,return_inverse=True);HN=headref.vertex_normals(HP,HT,head_weld);N=headref.unit((HN[HT[ti]]*bc[:,:,None]).sum(1));_,coverage=field(cp);thickness=.0004+.00285*coverage**3
        P=cp+N*thickness[:,None]
        # Each triangle samples one reference UV island; neighbouring source
        # islands must not create dark seams through interpolation.
        centre=P[T].mean(1);_,_,rt=trimesh.proximity.closest_point(reference,centre)
        flat=P[T].reshape(-1,3);reftri=np.repeat(mass[rt],3,axis=0);buv=headref.barycentric(flat,s['POSITION'][reftri[:,0]],s['POSITION'][reftri[:,1]],s['POSITION'][reftri[:,2]])
        UV=(s['TEXCOORD_0'][reftri]*buv[:,:,None]).sum(1)
        ids=T.reshape(-1);P=P[ids];N=N[ids];coverage=coverage[ids];thickness=thickness[ids];cp=cp[ids];ti=ti[ids];bc=bc[ids];T=np.arange(len(ids)).reshape(-1,3)
        dense=np.zeros((len(P),len(head.skin_joints)))
        for corner in range(3):
            for slot in range(4):np.add.at(dense,(np.arange(len(P)),ha['JOINTS_0'][HT[ti,corner],slot].astype(int)),bc[:,corner]*ha['WEIGHTS_0'][HT[ti,corner],slot])
        J,W=assemble.top4(dense);COL=np.ones((len(P),4));COL[:,0]=coverage*.5;COL[:,1]=.65;COL[:,2]=.93
        D=[];morphed_normals=[headref.vertex_normals(HP+hd,HT,head_weld) for hd in HD]
        for hd,normal_m in zip(HD,morphed_normals):
            move=(hd[HT[ti]]*bc[:,:,None]).sum(1);nm=headref.unit((normal_m[HT[ti]]*bc[:,:,None]).sum(1));D.append(move+(nm-N)*thickness[:,None])
        cap_count=len(P);cap_tris=len(T)
        # Preserve the previous finish as short attached whiskers. Cards are
        # re-rooted on the new foundation, not on the floating old mass.
        old=g['meshes'][lod]['primitives'][0];ca=attributes(g,b,old);CT=rlglb.accessor(g,b,old['indices']).astype(int).reshape(-1,3);CT=CT[(ca['TEXCOORD_0'][CT,1]>.6505).all(1)]
        card_triangles=0
        if len(CT):
            edges=CT[:,[0,1,1,2,2,0]].reshape(-1,2);graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(ca['POSITION']),len(ca['POSITION']))).tocsr();_,labels=connected_components(graph,directed=False)
            rows=[];cards=[];cardd=[[] for _ in names];budget=[1000,350,80][lod]
            for group in np.unique(labels[CT[:,0]]):
                tt=CT[labels[CT[:,0]]==group];vv,inv=np.unique(tt,return_inverse=True)
                if card_triangles+len(tt)>budget:continue
                q=ca['POSITION'][vv];v=ca['COLOR_0'][vv,1];roots=np.flatnonzero(v<=v.min()+.05);root=q[roots].mean(0)
                rootcp,_,rti=trimesh.proximity.closest_point(surface,root[None]);rbc=headref.barycentric(rootcp,HP[HT[rti,0]],HP[HT[rti,1]],HP[HT[rti,2]]);_,cw=field(rootcp)
                if cw[0]<.35:continue
                rn=headref.unit((HN[HT[rti]]*rbc[:,:,None]).sum(1))[0];rh=.0004+.00285*cw[0]**3
                residual=(q-root)*.65;q=rootcp[0]+rn*rh+residual
                if lip_tree.query(q)[0].min()<.00015:continue
                base=len(rows);cards.extend((inv.reshape(-1,3)+base).tolist());card_triangles+=len(tt)
                rw=np.zeros(len(head.skin_joints))
                for k in range(3):
                    for j,weight in zip(ha['JOINTS_0'][HT[rti[0],k]].astype(int),ha['WEIGHTS_0'][HT[rti[0],k]]):rw[j]+=rbc[0,k]*weight
                rJ,rW=assemble.top4(rw[None]);col=ca['COLOR_0'][vv].copy();col[:,0]=1;col[:,2]=.93;col[:,3]=1
                for k in range(len(vv)):rows.append((q[k],ca['NORMAL'][vv[k]],ca['TEXCOORD_0'][vv[k]],rJ[0],rW[0],col[k]))
                for k,hd in enumerate(HD):
                    dr=(hd[HT[rti]]*rbc[:,:,None]).sum(1)[0];rnm=headref.unit((morphed_normals[k][HT[rti]]*rbc[:,:,None]).sum(1))[0];cardd[k].extend(np.tile(dr+(rnm-rn)*rh,(len(vv),1)))
            # A fine rooted fringe softens the visible silhouette. It grows
            # into the dense foundation instead of exposing a polygon rim.
            candidates=np.flatnonzero((coverage>.01)&(coverage<.45)&(lip_tree.query(cp)[0]>.002))
            _,pick=np.unique(np.round(cp[candidates],5),axis=0,return_index=True);candidates=candidates[pick]
            maximum=[260,75,0][lod]
            if len(candidates)>maximum and maximum:
                from hairgen import farthest_order
                candidates=candidates[farthest_order(cp[candidates])[:maximum]]
            elif not maximum:candidates=[]
            for i in candidates:
                normal=N[i];flow=np.array([0.,-1.,.1]);flow-=normal*np.dot(flow,normal)
                if np.linalg.norm(flow)<.1:flow=np.array([0.,0.,1.])-normal*normal[2]
                flow=headref.unit(flow);across=headref.unit(np.cross(normal,flow));length=.0018+.0007*((i*13)%19)/19;width=.00065
                centre=cp[i]+normal*.00045;quad=np.array([centre-across*width*.5,centre+across*width*.5,centre+flow*length-across*width*.25+normal*.0002,centre+flow*length+across*width*.25+normal*.0002])
                if lip_tree.query(quad)[0].min()<.0002:continue
                base=len(rows);cards.extend([[base,base+1,base+2],[base+1,base+3,base+2]]);card_triangles+=2
                uv=np.array([[.001,.652],[.249,.652],[.001,.998],[.249,.998]])
                for j in range(4):rows.append((quad[j],normal,uv[j],J[i],W[i],np.array([1.,j//2,.93,1.])))
                for k,hd in enumerate(HD):
                    dr=(hd[HT[ti[i]]]*bc[i,:,None]).sum(0);rnm=headref.unit((morphed_normals[k][HT[ti[i]]]*bc[i,:,None]).sum(0));cardd[k].extend(np.tile(dr+(rnm-normal)*.00045,(4,1)))
            if rows:
                P=np.vstack([P,np.array([x[0] for x in rows])]);N=np.vstack([N,headref.unit(np.array([x[1] for x in rows]))]);UV=np.vstack([UV,np.array([x[2] for x in rows])]);J=np.vstack([J,np.array([x[3] for x in rows])]);W=np.vstack([W,np.array([x[4] for x in rows])]);COL=np.vstack([COL,np.array([x[5] for x in rows])]);T=np.vstack([T,np.array(cards)+cap_count]);D=[np.vstack([d,np.array(c)]) for d,c in zip(D,cardd)]
        primitive=writer.primitive(P.astype('f4'),N.astype('f4'),UV.astype('f4'),T,np.rint(COL*255).astype('u1'),J.astype('u1'),W.astype('f4'),mat,[(x,None) for x in D]);writer.mesh(f'beard_lod{lod}',[primitive],names)
        root=coverage<.5;chin=(cp[:,1]<1.565)&(abs(cp[:,0])<.045)
        _,weld=np.unique(np.round(P[:cap_count],6),axis=0,return_inverse=True);ct=weld[T[:cap_tris]];edges=ct[:,[0,1,1,2,2,0]].reshape(-1,2);graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(int(weld.max())+1,int(weld.max())+1)).tocsr();components,_=connected_components(graph,directed=False)
        report['lods'][f'lod{lod}']={'tris':len(T),'foundation_tris':cap_tris,'whisker_tris':card_triangles,'foundation_components':int(components),'root_gap_mm':[float(thickness[root].min()*1000),float(thickness[root].max()*1000)],'chin_gap_mm':[float(thickness[chin].min()*1000),float(thickness[chin].max()*1000)]}
        print('ATTACHED_BEARD',lod,report['lods'][f'lod{lod}'],flush=True)
    writer.g.g['nodes']=copy.deepcopy(g['nodes']);writer.g.g['scenes']=copy.deepcopy(g['scenes']);skin=copy.deepcopy(g['skins'][0]);skin['inverseBindMatrices']=writer.g.accessor(rlglb.accessor(g,b,skin['inverseBindMatrices']).astype('f4'),'MAT4');writer.g.g['skins']=[skin];writer.g.g['asset']['extras']=copy.deepcopy(g['asset']['extras']);info=writer.g.g['asset']['extras']['rlBeard'];info['tris']={k:v['tris'] for k,v in report['lods'].items()};info['skinAttachedFoundation']=True
    info['colour']={'R':'foundation: 0..0.5 feather coverage; whiskers: 1', 'G':'foundation: 0.65; whiskers: root-to-tip progression', 'B':'0.93 beard shade', 'A':'1; texture and root coverage supply the edge alpha'}
    writer.save(str(dest));report['output_sha256']=digest(dest);dest.with_suffix('.attachment.json').write_text(json.dumps(report,indent=2));print('ATTACHED_BEARD_WRITTEN',dest,flush=True)

if __name__=='__main__':main()
