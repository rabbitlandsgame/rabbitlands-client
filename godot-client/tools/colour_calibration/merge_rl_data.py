"""Insert the calibrated custom-colour data into data/actors/rl_head_wire_defaults.json
`colours` (skinTone, eyeLut, hairLut, beardLut, customSources), replacing earlier
copies of those keys and leaving every other line byte-identical.

usage: python merge_rl_data.py <rl_hair_luts.json> <rl_skin_eye_luts.json>
"""
import json, sys
from pathlib import Path
from calib_lib import CLIENT

hair = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
skin_eye = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
path = CLIENT / 'data/actors/rl_head_wire_defaults.json'
text = path.read_bytes().decode('utf-8')
lines = text.split('\n')
start = lines.index('\t"colours": {')
end = next(i for i in range(start + 1, len(lines)) if lines[i] == '\t},')
KEYS = ('"skinTone"', '"eyeLut"', '"hairLut"', '"beardLut"', '"customSources"')
body = [l for l in lines[start + 1:end] if not l.lstrip().startswith(KEYS)]
# The last kept line must end with a comma before the new keys.
if not body[-1].endswith(','):
    body[-1] = body[-1] + ','

sources = dict(sorted({**hair['sources'], **skin_eye['sources']}.items()))
skin = skin_eye['skinTone']
eyes = skin_eye['eyeLut']


def compact(value):
    return json.dumps(value, separators=(', ', ': '))


new = [
    '\t\t"skinTone": {"about": "PC/3 custom skin tone and undertone (colour model spec revision 3, 4.3): the RL skin is the final skin (linear) times this per-channel gain, bilinear in slider position and undertone t between the knots (gains listed position-major, then undertone). Measured by tests/integration/rl_head_colour_calibration.gd --part=skin (the Medium cheeks with that custom skin as the target, 3 linear-light corrections); the knots at the six stops with t = 0 are the palette table\'s own gains (skin / stop colour), so the custom model meets the table there.", '
    '"positions": %s, "undertones": %s, "female": %s, "male": %s},' % (
        compact(skin['positions']), compact(skin['undertones']), compact(skin['female']), compact(skin['male'])),
    '\t\t"eyeLut": {"about": "PC/3 custom iris pigment (4.3): RL eye colour (linear) for a pigment (linear) on %d nodes per channel spaced evenly over 0..1, index (r * n + g) * n + b, trilinear; then the inverse-distance-weighted (OKLab) residual of the 12 palette entries (table - LUT) is added, so the LUT is exact at each. Both irises are affine in the colour (face_appearance natural_iris, rl_eye), so the nodes are the composition of their affine fits (rl_head_colour_calibration --part=eyes: 20 custom pigments through the Medium path, 20 RL eye colours), clamped to 0..1.", '
    '"nodes": %d, "spacing": "linear", "female": %s, "male": %s},' % (
        eyes['nodes'], eyes['nodes'], compact(eyes['female']), compact(eyes['male'])),
    '\t\t"hairLut": {"about": "PC/3 custom apparent hair colour on the RL module (4.4, P5): its lit hair mean (linear) mu = gain * d + hue * d / max(d) + floor for RL hair colour d (rl_hair.gdshader: the diffuse and the hue-normalised sheen), per fine-detail level (linear between levels), fitted to tests/integration/hair_apparent_calibration.gd. The RL colour is the d in 0..1 whose mu is targetFloor + skinGain * A: the reference path\'s look (Medium, Classic, the module\'s slot style; targetFloor is its black) for apparent colour A, out of reach scaled uniformly.", '
    '"female": %s, "male": %s},' % (compact(hair['hairLut'].get('female', {})), compact(hair['hairLut'].get('male', {}))),
    '\t\t"beardLut": {"about": "PC/3 custom apparent colour on the RL beards (4.4, B3; owner Q-N4: custom beards show the hair\'s apparent colour): per beard, the RL response as for hairLut, with targetFloor the Low/Medium beard shell\'s black (B1, same facial_hair), so a custom RL beard looks like the Low/Medium beard of that apparent colour.", '
    '"male": %s},' % compact(hair['beardLut'].get('male', {})),
    '\t\t"customSources": %s' % compact(sources),
]
out = lines[:start + 1] + body + new + lines[end:]
path.write_bytes('\n'.join(out).encode('utf-8'))
json.loads(path.read_text(encoding='utf-8'))
print('merged', len(new), 'keys;', len(sources), 'sources')
