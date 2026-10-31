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

def uses_root_coverage(material):
    """The material-local COLOR.R multiplier selected by RLHeadLibrary."""
    name=material_role(material.get('name',''));extras=material.get('extras') or {}
    beard=name=='rl_beard';card=name!='rl_hair_clump'
    reference=bool(extras.get('referenceSurface',False))
    feathered=beard and bool(extras.get('featheredRoots',False))
    soft_clump=name=='rl_hair_clump' and bool(extras.get('softRootCoverage',False))
    soft=bool(extras.get('softHairline',False))
    if reference:card=True;soft=feathered or (soft_clump and soft)
    return soft and ((not card and not beard) or beard or soft_clump)

def validate_roles(materials):
    errors=[]
    for material in materials:
        name=material.get('name','')
        if name not in CLUMP_ROLES:continue
        texture=(material.get('extras') or {}).get('texture')
        if not isinstance(texture,str) or not texture.strip():
            errors.append(f'{name}: explicit crest clump requires its own declared texture')
    return errors
