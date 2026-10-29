"""Minimal MakeHuman hm08 base mesh + target loader (numpy, no Blender)."""
import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)))))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import gzip, json, os, numpy as np
DATA = os.path.join(paths.LOCAL, 'mpfb_ext', 'data')
def load_base():
    V=[];VT=[];F=[];FT=[];G=[];g=None
    with open(os.path.join(DATA,'3dobjs','base.obj')) as fh:
        for line in fh:
            if line.startswith('v '): V.append([float(x) for x in line.split()[1:4]])
            elif line.startswith('vt '): VT.append([float(x) for x in line.split()[1:3]])
            elif line.startswith('g '): g=line.split()[1]
            elif line.startswith('f '):
                vs=[];ts=[]
                for tok in line.split()[1:]:
                    p=tok.split('/'); vs.append(int(p[0])-1); ts.append(int(p[1])-1 if len(p)>1 and p[1] else -1)
                F.append(vs);FT.append(ts);G.append(g)
    return np.array(V),np.array(VT),F,FT,G
def load_target(rel):
    p=os.path.join(DATA,'targets',rel)
    if not p.endswith('.gz'): p+='.target.gz'
    idx=[];d=[]
    with gzip.open(p,'rt') as fh:
        for line in fh:
            if not line.strip() or line.startswith('#'): continue
            s=line.split(); idx.append(int(s[0])); d.append([float(x) for x in s[1:4]])
    return np.array(idx,dtype=int),np.array(d)
