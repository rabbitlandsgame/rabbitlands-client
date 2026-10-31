"""Explicit material roles shared by authoring checks and the RL runtime.

Concrete names remain the keys for metadata, textures and material caches.
Unknown names are not accepted by prefix or substring matching.
"""
CLUMP_ROLES={
    'rl_hair_clump_crest':'rl_hair_clump',
    'rl_hair_clump_crest_lod1':'rl_hair_clump',
    'rl_hair_clump_crest_lod2':'rl_hair_clump',
}

def material_role(name):return CLUMP_ROLES.get(name,name)

def validate_roles(materials):
    errors=[]
    for material in materials:
        name=material.get('name','')
        if name not in CLUMP_ROLES:continue
        texture=(material.get('extras') or {}).get('texture')
        if not isinstance(texture,str) or not texture.strip():
            errors.append(f'{name}: explicit crest clump requires its own declared texture')
    return errors
