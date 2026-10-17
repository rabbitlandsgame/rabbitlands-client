"""Create a relocated working profile without modifying hash-bound source records."""
import argparse
import hashlib
import json
from pathlib import Path
from workspace import authoring_root, location_rules, relocate_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source, output = args.input.resolve(), args.output.resolve()
    working = (authoring_root() / 'working').resolve()
    if source == output or not output.is_relative_to(working):
        parser.error('Output must be a new profile under .local/asset-authoring/working')
    original = source.read_bytes()
    data = json.loads(original)
    localized = relocate_json(data, location_rules(), source.parent)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes((json.dumps(localized, indent=2) + '\n').encode('utf-8'))
    receipt = {'source_profile_sha256':hashlib.sha256(original).hexdigest(),
               'working_profile_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
               'policy':'Only known filesystem prefixes/relative source location changed; authoring input preserved.'}
    output.with_suffix(output.suffix + '.relocation.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode())
    print('Localized profile:', output)


if __name__ == '__main__': main()
