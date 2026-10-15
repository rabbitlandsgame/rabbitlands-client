"""Lossless static-scene partitioning over the shared toolkit glTF reader.

Referenced vertex buffers are copied once, image bytes are content-addressed,
and object hierarchies remain whole. A selection never serialises unselected
mesh buffers. Generated world transforms live on wrappers so animations and
the original authored local transforms remain valid.
"""
from __future__ import annotations
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import numpy as np
from PIL import Image

TOOLKIT=Path(__file__).resolve().parents[1]/'_toolkit'
# GitHub refuses any file over 100 MiB. A region master's binary past
# PACKAGE_PART_BYTES continues in part files, leaving room for its JSON chunk.
PACKAGE_PART_BYTES=90*2**20
PACKAGE_FILE_BYTES=100*2**20
if str(TOOLKIT) not in sys.path: sys.path.insert(0,str(TOOLKIT))
import glb_reader as GR


def dump_glb(path, document, body, part_bytes=None):
    """Write a GLB. Given `part_bytes`, a binary larger than that keeps its first
    part in the GLB and continues, whole buffer views at a time, in sibling files
    `<stem>.part<n>.<sha256>.bin` (standard glTF external buffers). The name pins
    each part's bytes, so the GLB's own digest still covers the whole package.
    Part files beside the GLB that it no longer names are removed."""
    document=copy.deepcopy(document)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    parts=split_parts(document,body,part_bytes) if part_bytes and len(body)>part_bytes else [bytes(body)]
    document['buffers']=[{'byteLength':len(parts[0])}]
    written=set()
    for number,data in enumerate(parts[1:],1):
        name=f'{path.stem}.part{number}.{hashlib.sha256(data).hexdigest()}.bin'
        (path.parent/name).write_bytes(data);written.add(name)
        document['buffers'].append({'uri':name,'byteLength':len(data)})
    for stale in path.parent.glob(f'{path.stem}.part*.bin'):
        if stale.name not in written: stale.unlink()
    raw=json.dumps(document,separators=(',',':'),ensure_ascii=False).encode()
    raw+=b' '*((-len(raw))%4)
    body=parts[0]+b'\0'*((-len(parts[0]))%4)
    header=struct.pack('<4sII',b'glTF',2,12+8+len(raw)+8+len(body))
    path.write_bytes(header+struct.pack('<II',len(raw),0x4E4F534A)+raw+struct.pack('<II',len(body),0x004E4942)+body)


def split_parts(document, body, limit):
    """Deal the buffer views, in buffer order, into parts of at most `limit`
    bytes, rebasing each view onto its part at a 4-byte boundary."""
    parts=[bytearray()]
    for view in sorted(document['bufferViews'],key=lambda v:v.get('byteOffset',0)):
        start=view.get('byteOffset',0);data=body[start:start+view['byteLength']]
        if len(data)>limit: raise ValueError(f'A {len(data)}-byte buffer view cannot fit a {limit}-byte part')
        offset=len(parts[-1])+(-len(parts[-1]))%4
        if parts[-1] and offset+len(data)>limit: parts.append(bytearray());offset=0
        parts[-1].extend(b'\0'*(offset-len(parts[-1])))
        view['buffer']=len(parts)-1;view['byteOffset']=offset
        parts[-1].extend(data)
    return [bytes(part) for part in parts]


def descendants(document, roots):
    included=set()
    def visit(index):
        if index in included: return
        included.add(index)
        for child in document['nodes'][index].get('children',[]): visit(child)
    for root in roots: visit(root)
    return included


def subtree_bounds(document, body, root, matrices=None):
    matrices=GR.hierarchy(document)[0] if matrices is None else matrices
    lo=np.full(3,np.inf);hi=-lo
    for index in descendants(document,[root]):
        node=document['nodes'][index]
        if 'mesh' not in node: continue
        for p in document['meshes'][node['mesh']]['primitives']:
            a=document['accessors'][p['attributes']['POSITION']]
            if 'min' in a and 'max' in a:
                low,high=np.array(a['min']),np.array(a['max'])
                v=np.array([[x,y,z] for x in (low[0],high[0]) for y in (low[1],high[1]) for z in (low[2],high[2])])
            else: v=GR.accessor(document,body,p['attributes']['POSITION'])
            m=matrices[index];v=v@m[:3,:3].T+m[:3,3]
            lo=np.minimum(lo,v.min(axis=0));hi=np.maximum(hi,v.max(axis=0))
    if not np.isfinite(lo).all(): lo=hi=matrices[root][:3,3].copy()
    return lo,hi


class Exporter:
    def __init__(self, path, shared_images=None, part_bytes=None):
        """`part_bytes` is for region masters only: the streaming client never
        loads a master's geometry (it hashes it), while chunks and every other
        runtime GLB must stay self-contained."""
        self.path=Path(path)
        self.shared_images=Path(shared_images) if shared_images else None
        self.part_bytes=part_bytes
        self.doc={'asset':{'version':'2.0','generator':'Eloria shared continent partitioner'},
                  'scene':0,'scenes':[{'nodes':[]}],'nodes':[],'meshes':[],
                  'materials':[],'textures':[],'images':[],'samplers':[],
                  'accessors':[],'bufferViews':[]}
        self.body=bytearray()
        self.memo={}
        self.image_memo={}
        self.dependencies={}
        self.resource_bytes={}

    def view(self, data, template=None):
        self.body.extend(b'\0'*((-len(self.body))%4))
        out=copy.deepcopy(template or {})
        out.update(buffer=0,byteOffset=len(self.body),byteLength=len(data))
        self.body.extend(data)
        self.doc['bufferViews'].append(out)
        return len(self.doc['bufferViews'])-1

    def add(self, source, body, roots, *, transforms=None, matrices=None, root_names=None,
            prefix='', node_prefix=''):
        """Add selected root subtrees under placement wrappers.

        Normal continent partitioning supplies XYZ ``transforms``.  Godot
        authoring snapshots instead supply unambiguous glTF column-major
        ``matrices`` and stable ``root_names``.  A root may use only one
        transform representation.
        """
        identity=id(source)
        def transfer(kind,index):
            key=(identity,kind,index)
            if key in self.memo: return self.memo[key]
            old=source[kind][index]
            out=copy.deepcopy(old)
            if kind=='bufferViews':
                start=old.get('byteOffset',0)
                result=self.view(body[start:start+old['byteLength']],old)
                self.memo[key]=result;return result
            if kind=='accessors':
                if 'sparse' in old: raise ValueError('Sparse accessors need explicit partition support')
                if 'bufferView' in old: out['bufferView']=transfer('bufferViews',old['bufferView'])
            elif kind=='meshes':
                for part in out['primitives']:
                    part['attributes']={k:transfer('accessors',v) for k,v in part['attributes'].items()}
                    if 'indices' in part: part['indices']=transfer('accessors',part['indices'])
                    if 'material' in part: part['material']=transfer('materials',part['material'])
                    if 'targets' in part: part['targets']=[{k:transfer('accessors',v) for k,v in t.items()} for t in part['targets']]
            elif kind=='materials':
                def textures(item):
                    if isinstance(item,dict):
                        for k,v in item.items():
                            if k.endswith('Texture') and isinstance(v,dict) and 'index' in v: v['index']=transfer('textures',v['index'])
                            else: textures(v)
                    elif isinstance(item,list):
                        for v in item: textures(v)
                textures(out)
            elif kind=='textures':
                if 'source' in out: out['source']=transfer('images',out['source'])
                if 'sampler' in out: out['sampler']=transfer('samplers',out['sampler'])
            elif kind=='images':
                if 'bufferView' not in old: raise ValueError('Library images must be embedded and certified')
                view=source['bufferViews'][old['bufferView']]
                start=view.get('byteOffset',0);data=body[start:start+view['byteLength']]
                sha=hashlib.sha256(data).hexdigest()
                if sha not in self.resource_bytes:
                    with Image.open(io.BytesIO(data)) as picture:
                        self.resource_bytes[sha]=int(np.ceil(picture.width*picture.height*4*4/3))
                if sha in self.image_memo:
                    result=self.image_memo[sha];self.memo[key]=result;return result
                if self.shared_images:
                    self.shared_images.mkdir(parents=True,exist_ok=True)
                    suffix='.png' if old.get('mimeType','image/png')=='image/png' else '.jpg'
                    target=self.shared_images/(sha+suffix)
                    if not target.exists(): target.write_bytes(data)
                    elif hashlib.sha256(target.read_bytes()).hexdigest()!=sha: raise ValueError('Shared image digest mismatch')
                    uri=os.path.relpath(target,self.path.parent).replace('\\','/')
                    out={'uri':uri,'name':old.get('name',sha)}
                    self.dependencies[uri]=sha
                else: out['bufferView']=self.view(data)
            result=len(self.doc[kind]);self.doc[kind].append(out);self.memo[key]=result
            if kind=='images': self.image_memo[sha]=result
            return result
        chosen=descendants(source,roots)
        mapping={old:len(self.doc['nodes'])+i for i,old in enumerate(sorted(chosen))}
        for old_index in sorted(chosen):
            node=copy.deepcopy(source['nodes'][old_index])
            if node_prefix and 'name' in node:
                name=node['name']
                node['name']=('Walk_'+node_prefix+name[5:]) if name.startswith('Walk_') else node_prefix+name
            if 'skin' in node: raise ValueError('World scenery must not contain character skins')
            if 'mesh' in node: node['mesh']=transfer('meshes',node['mesh'])
            if 'children' in node: node['children']=[mapping[c] for c in node['children'] if c in chosen]
            self.doc['nodes'].append(node)
        wrappers=[]
        for root in roots:
            child=mapping[root]
            if root in (transforms or {}) and root in (matrices or {}):
                raise ValueError('A placement root cannot have both translation and matrix transforms')
            name=(root_names or {}).get(root,
                prefix+node_prefix+source['nodes'][root].get('name',str(root))+'_WorldPlacement')
            wrapper={'name':name,'children':[child]}
            if root in (matrices or {}):
                matrix=list(map(float,matrices[root]))
                if len(matrix)!=16 or not np.isfinite(matrix).all():
                    raise ValueError('Placement matrix must contain sixteen finite glTF column-major numbers')
                wrapper['matrix']=matrix
            else:
                shift=(transforms or {}).get(root,[0,0,0])
                wrapper['translation']=list(map(float,shift))
            wrapper_index=len(self.doc['nodes'])
            self.doc['scenes'][0]['nodes'].append(wrapper_index)
            self.doc['nodes'].append(wrapper)
            wrappers.append(wrapper_index)
        for animation in source.get('animations',[]):
            channels=[copy.deepcopy(c) for c in animation.get('channels',[]) if c['target'].get('node') in mapping]
            if not channels: continue
            out={'name':animation.get('name','Motion'),'channels':channels,'samplers':[]}
            for c in channels:
                c['target']['node']=mapping[c['target']['node']]
                s=copy.deepcopy(animation['samplers'][c['sampler']])
                s['input']=transfer('accessors',s['input']);s['output']=transfer('accessors',s['output'])
                c['sampler']=len(out['samplers']);out['samplers'].append(s)
            self.doc.setdefault('animations',[]).append(out)
        for field in ('extensionsUsed','extensionsRequired'):
            if source.get(field): self.doc[field]=sorted(set(self.doc.get(field,[]))|set(source[field]))
        return wrappers

    def write(self):
        dump_glb(self.path,self.doc,self.body,self.part_bytes)
        if self.part_bytes and self.path.stat().st_size>PACKAGE_FILE_BYTES:
            raise ValueError(f'{self.path}: {self.path.stat().st_size} bytes is over the {PACKAGE_FILE_BYTES}-byte file limit')
        return {'glbBytes':self.path.stat().st_size,'nodes':len(self.doc['nodes']),
                'meshes':len(self.doc['meshes']),'externalResources':self.dependencies,
                'sharedResourceResidentBytes':self.resource_bytes}
