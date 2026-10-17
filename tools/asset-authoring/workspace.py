"""Locations and literal-path relocation for the ignored asset-authoring archive."""
import json
import re
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[2]


def authoring_root():
    return CLIENT / '.local/asset-authoring'


def location_rules():
    config = authoring_root() / 'location-map.json'
    data = json.loads(config.read_text(encoding='utf-8'))
    pairs=[(data['original_workspace'].rstrip('/\\'), str(authoring_root() / 'workspace'))]
    # Earlier public tools used a flat Rabbit Lands workspace layout.
    for folder in ['generate_models','work-output','highpoly_actors','base_animations',
                   'concept_art','oldcraft_style_concept_art','updated_creature_models',
                   'lowpoly_rigged','rigged_races','eloria_creatures_separated','archive']:
        pairs.append((str(CLIENT.parent / folder),str(authoring_root() / 'workspace' / folder)))
    pairs.extend((item['source'],item['target']) for item in data.get('referenced_input_paths',[]))
    rules=[]
    for source,target in pairs:
        source,target=source.replace('\\','/'),target.replace('\\','/')
        rules.extend([(source, target), (source.replace('/', '\\'), target.replace('/', '\\')),
                     (source.replace('/', '\\\\'), target.replace('/', '\\\\'))])
        if re.match(r'^[A-Za-z]:/', source):
            rules.append(('/mnt/' + source[0].lower() + source[2:],
                          '/mnt/' + target[0].lower() + target[2:]))
    return rules


def relocate_text(text, rules):
    """Replace full known workspace prefixes, preserving each slash style."""
    folded=text.casefold()
    for old, new in sorted(rules, key=lambda item:len(item[0]), reverse=True):
        if old.casefold() not in folded:
            continue
        text = re.sub(re.escape(old) + r'(?![A-Za-z0-9_.-])', lambda _:new, text, flags=re.IGNORECASE)
        folded=text.casefold()
    return text


def relocate_json(value, rules, original_directory=None, key=''):
    if isinstance(value, dict):
        return {k:relocate_json(v,rules,original_directory,k) for k,v in value.items()}
    if isinstance(value, list):
        return [relocate_json(v,rules,original_directory,key) for v in value]
    if isinstance(value, str):
        result = relocate_text(value, rules)
        # Moving a profile must also preserve its declared relative source GLB.
        if key == 'source_glb' and original_directory and not re.match(r'^(?:[A-Za-z]:[/\\]|/)', result):
            result = str((Path(original_directory) / result).resolve())
        return result
    return value
