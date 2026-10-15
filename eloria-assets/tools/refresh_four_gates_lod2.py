import json, struct
from pathlib import Path

P=Path('four-gates-city-package');src=P/'four-gates-city.glb';raw=src.read_bytes();jl,_=struct.unpack_from('<I4s',raw,12);g=json.loads(raw[20:20+jl]);bo=20+jl;bl,_=struct.unpack_from('<I4s',raw,bo);buf=bytearray(raw[bo+8:bo+8+bl])
nodes=g['nodes'];drop=('Battlement_','Plaza_Bench_','Plaza_Lamp_','Market_','Farm_Fence_','Residence_','Civic_Hall_','Farmhouse_','Granary_','Irrigation_','Service_','Ring_','Vegetation_')
keep=[not n.get('name','').endswith('_LOD0') and not n.get('name','').startswith(drop) and '_Authored_Arch_' not in n.get('name','') and '_Energy_Inlay_' not in n.get('name','') for n in nodes]
remap={old:new for new,old in enumerate(i for i,k in enumerate(keep) if k)};lodnodes=[]
for old,k in enumerate(keep):
 if not k:continue
 d=dict(nodes[old]);
 if 'children'in d:d['children']=[remap[c] for c in d['children'] if c in remap]
 lodnodes.append(d)
lod=dict(g);lod['nodes']=lodnodes;lod['scenes']=[{'name':'Four Gates City LOD2','nodes':[remap[0]]}];lod.pop('animations',None);lod['asset']=dict(g['asset']);lod['asset']['generator']='Eloria Four Gates authored reduced-node LOD2 0.5'
while len(buf)%4:buf.append(0)
lod['buffers'][0]['byteLength']=len(buf);jb=json.dumps(lod,separators=(',',':')).encode();jb+=b' '*((-len(jb))%4);out=P/'four-gates-city-lod2.glb';out.write_bytes(struct.pack('<4sII',b'glTF',2,12+8+len(jb)+8+len(buf))+struct.pack('<I4s',len(jb),b'JSON')+jb+struct.pack('<I4s',len(buf),b'BIN\0')+buf)
m=json.loads((P/'four-gates-city.json').read_text());m['lodGroups'][0]['levels'][2].update({'glb':'four-gates-city-lod2.glb','nodeCount':len(lodnodes),'animations':0});(P/'four-gates-city.json').write_text(json.dumps(m,indent=2)+'\n');lm=json.loads(json.dumps(m));lm['asset']['glb']='four-gates-city-lod2.glb';lm['assetVersion']='0.5.0-lod2';lm['animations']=[];(P/'four-gates-city-lod2.json').write_text(json.dumps(lm,indent=2)+'\n')
print(json.dumps({'lod2Nodes':len(lodnodes),'lod2Bytes':out.stat().st_size},indent=2))
