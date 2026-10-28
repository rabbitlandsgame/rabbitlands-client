"""Geometric facial landmarks on the hm08 (MPFB) topology. Indices are found once
on the base mesh and reused for any target combination (topology is shared)."""
import numpy as np, mhmesh, collections
def body_info():
    V,VT,F,FT,G=mhmesh.load_base()
    groups={}
    for f,g in zip(F,G): groups.setdefault(g,set()).update(f)
    return V,F,G,groups
def find(V,F,G,groups):
    body=np.array(sorted(groups['body']))
    L={}
    # midline front profile: verts with |x|<1e-3
    mid=body[np.abs(V[body,0])<1e-4]
    mid=mid[V[mid,1]>5.6]
    # front profile: for each y, the max z
    m=mid[np.argsort(V[mid,1])]
    # outer surface only: per 0.015 y-bin keep the max-z midline vertex
    bins={}
    for i in m:
        if V[i,2]<0.2: continue
        b=int(V[i,1]/0.015)
        if b not in bins or V[i,2]>V[bins[b],2]: bins[b]=i
    front=[bins[b] for b in sorted(bins)]
    P=V[front]
    ys=P[:,1]
    nose=front[int(np.argmax(P[:,2]))]; L['nose_tip']=nose
    # subnasale: min z between nose tip and 0.45 below
    def argz(lo,hi,fn):
        sel=[i for i in front if lo<V[i,1]<hi]
        return sel[int(fn([V[i,2] for i in sel]))]
    yn=V[nose,1]
    L['subnasale']=argz(yn-0.35,yn-0.05,np.argmin)
    ys_=V[L['subnasale'],1]
    L['labrale_sup']=argz(ys_-0.35,ys_-0.02,np.argmax)
    yls=V[L['labrale_sup'],1]
    L['stomion']=argz(yls-0.25,yls-0.02,np.argmin)
    yst=V[L['stomion'],1]
    L['labrale_inf']=argz(yst-0.3,yst-0.02,np.argmax)
    yli=V[L['labrale_inf'],1]
    L['sulcus']=argz(yli-0.35,yli-0.03,np.argmin)
    ysu=V[L['sulcus'],1]
    L['pogonion']=argz(ysu-0.45,ysu-0.03,np.argmax)
    # menton: lowest midline vertex of the chin before throat (z still > pogonion z - 0.45)
    yp=V[L['pogonion'],1]; zp=V[L['pogonion'],2]
    cand=[i for i in front if yp-0.6<V[i,1]<yp and V[i,2]>zp-0.5]
    L['menton']=min(cand,key=lambda i:V[i,1])
    L['nasion']=argz(yn+0.2,yn+1.0,np.argmin)
    yna=V[L['nasion'],1]
    L['glabella']=argz(yna+0.05,yna+0.6,np.argmax)
    # vertex: top of head
    L['vertex']=int(body[np.argmax(V[body,1])])
    # back of head: min z among midline verts above ear level
    back=[i for i in m if V[i,1]>yna-0.4]
    L['opisthocranion']=min(back,key=lambda i:V[i,2])
    # eyes
    for side,sx in (('l',1),('r',-1)):
        he=V[sorted(groups[f'helper-{side}-eye'])]; c=he.mean(0); r=np.linalg.norm(he-c,axis=1).mean()
        B=body[(np.sign(V[body,0])==sx)]
        d=np.linalg.norm(V[B]-c,axis=1)
        rim=B[(d<r*1.06)&(V[B,2]>c[2])]
        L[f'eye_{side}_center']=c
        L[f'eye_{side}_outer']=int(rim[np.argmax(V[rim,0]*sx)])
        L[f'eye_{side}_inner']=int(rim[np.argmin(V[rim,0]*sx)])
        L[f'eye_{side}_top']=int(rim[np.argmax(V[rim,1])])
        L[f'eye_{side}_bottom']=int(rim[np.argmin(V[rim,1])])
        L[f'_rim_{side}']=rim
        # ear: verts with |x| beyond cheek, near eye height
        ear=B[(np.abs(V[B,0])>0.62)&(V[B,1]>yn-0.9)&(V[B,1]<yna+0.8)&(V[B,2]<0.9)&(V[B,2]>-0.6)]
        L[f'ear_{side}_top']=int(ear[np.argmax(V[ear,1])]); L[f'ear_{side}_bottom']=int(ear[np.argmin(V[ear,1])])
        L[f'ear_{side}_out']=int(ear[np.argmax(np.abs(V[ear,0]))])
        # mouth corner: lip-level verts (between labrale_sup and labrale_inf heights) near front, max |x| where z still high
        lip=B[(V[B,1]<V[L['labrale_sup'],1])&(V[B,1]>V[L['labrale_inf'],1])&(V[B,2]>V[L['stomion'],2]-0.35)]
        L[f'mouth_{side}']=int(lip[np.argmax(np.abs(V[lip,0]))]) if len(lip) else -1
        # alar: nose-width verts around subnasale height, front-ish
        al=B[(np.abs(V[B,1]-V[L['subnasale'],1]-0.07)<0.1)&(V[B,2]>V[L['subnasale'],2]-0.25)]
        L[f'alar_{side}']=int(al[np.argmax(np.abs(V[al,0]))])
        # cheekbone width at ~eye bottom height: max |x| with z>0.2 (front half)
        cz=B[(np.abs(V[B,1]-(c[1]-0.25))<0.06)&(V[B,2]>0.0)]
        L[f'zygion_{side}']=int(cz[np.argmax(np.abs(V[cz,0]))])
        # jaw width at mouth height
        jz=B[(np.abs(V[B,1]-V[L['stomion'],1])<0.06)&(V[B,2]>-0.2)&(np.abs(V[B,0])<0.75)]
        L[f'jaw_{side}']=int(jz[np.argmax(np.abs(V[jz,0]))])
        # gonion: jaw angle - at menton+0.35 height, max |x| with z between -0.2 and 0.5
        gz=B[(np.abs(V[B,1]-(V[L['menton'],1]+0.45))<0.06)&(V[B,2]>-0.3)&(np.abs(V[B,0])<0.75)]
        L[f'gonion_{side}']=int(gz[np.argmax(np.abs(V[gz,0]))])
    return L
