"""Verify the installed contact clips and their exact reviewed reports."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_undead_gaits import evaluate
from video_motion.asset import digest
from video_motion.native_shapes import NativeShapeAsset

ROOT = Path(__file__).resolve().parents[2]


def test_installed_undead_contact_clips():
    manifest = json.loads((ROOT/'docs/qa/undead-gaits/manifest.json').read_text())
    registry = json.loads((ROOT/'godot-client/data/actors/models.json').read_text())['models']
    for name,profile in manifest['actors'].items():
        path = ROOT/profile['runtime']
        assert digest(path) == profile['sha256']
        asset = NativeShapeAsset(path)
        assert all('uri' not in image for image in asset.d.get('images',[]))
        assert set(asset.animations) == {'Idle_A','Fighting_Idle','Walk','Jog','Sword_Attack','Hit_Chest','Death_A'}
        mapping = json.loads((ROOT/profile['animationMap']).read_text())
        audit = evaluate(path,{'clips':profile['gaits']})
        for action,clip in [('walk','Walk'),('run','Jog')]:
            gait = profile['gaits'][clip]
            assert mapping['actions'][action] == clip and clip in mapping['loopingClips']
            expected = gait['speedNative']*registry[name]['import']['scale']
            assert abs(mapping['strideMetresPerSecond'][action]-expected) < 1e-8
            metrics = audit['clips'][clip]
            assert metrics['fullSkinFloorMin'] >= -.0005
            assert metrics['edgeExcessMax'] < profile.get('edgeExcessLimit',.04)
            assert max(foot['stanceSlipP95'] for foot in metrics['feet'].values()) < .006
            times = np.linspace(0,asset.duration(clip),97)
            t,q,s,m = asset.sample(clip,times)
            worlds = [asset.world(t[i],q[i],s[i]) for i in range(len(times))]
            assert abs(worlds[0]-worlds[-1]).max() < 2e-6
            chains = profile.get('chains') or {suffix:[asset.ids[f'leg_a_{suffix}_{i:02}'] for i in (1,2,3)] for suffix in ('l','r')}
            for nodes in chains.values():
                lengths = np.linalg.norm(np.diff(asset.rest[nodes,:3,3],axis=0),axis=1)
                for world in worlds:
                    actual = np.linalg.norm(np.diff(world[nodes,:3,3],axis=0),axis=1)
                    # Float export and between-key interpolation: <5 microns
                    # at the native one-metre body height.
                    assert abs(actual-lengths).max() < 5e-6


def test_retained_death_knight_contact_and_cadence():
    report = json.loads((ROOT/'docs/qa/undead-gaits/death-knight-retained.audit.json').read_text())
    path = ROOT/'godot-client/assets/actors/native/creatures/black_iron_death_knight.glb'
    assert digest(path) == report['sha256']
    audit = evaluate(path,report['profile'])
    mapping = json.loads((ROOT/'godot-client/data/animations/humanoid/black_iron_death_knight.json').read_text())
    for action,clip in [('walk','Walk'),('run','Jog')]:
        # The original cadence was calibrated and stored to six decimals.
        assert abs(mapping['strideMetresPerSecond'][action]-report['profile']['clips'][clip]['speedNative']*1.117647) < 1e-5
        metrics = audit['clips'][clip]
        assert metrics['fullSkinFloorMin'] >= 0
        # Retained source gait: a broader limit than the newly fitted soles.
        # It bounds central support intervals, excluding lift and landing.
        assert max(foot['stanceSlipP95'] for foot in metrics['feet'].values()) < .03
        assert max(foot['stanceFloorMax'] for foot in metrics['feet'].values()) < .003
