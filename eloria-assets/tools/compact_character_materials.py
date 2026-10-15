"""Remove unused glTF material resources without changing rendered artwork."""
import copy
import hashlib


def texture_references(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.endswith('Texture') and isinstance(child, dict) and 'index' in child:
                yield child
            else:
                yield from texture_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from texture_references(child)


def compact_materials(document, binary):
    d=copy.deepcopy(document)
    materials=sorted({p['material'] for m in d['meshes'] for p in m['primitives'] if 'material' in p})
    remap={old:new for new,old in enumerate(materials)}
    for mesh in d['meshes']:
        for p in mesh['primitives']:
            if 'material' in p:p['material']=remap[p['material']]
    d['materials']=[d['materials'][i] for i in materials]
    references=list(texture_references(d['materials']))
    textures=sorted({v['index'] for v in references})
    remap={old:new for new,old in enumerate(textures)}
    for value in references:value['index']=remap[value['index']]
    d['textures']=[d['textures'][i] for i in textures]
    images=[];known={}
    for texture in d['textures']:
        source=d['images'][texture['source']]
        view=d['bufferViews'][source['bufferView']];start=view.get('byteOffset',0)
        key=(source.get('mimeType'),hashlib.sha256(binary[start:start+view['byteLength']]).hexdigest())
        if key not in known:known[key]=len(images);images.append(source)
        texture['source']=known[key]
    d['images']=images
    return d
