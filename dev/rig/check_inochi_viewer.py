"""Opt-in numerical check against the saved local Jingliu rig. No GUI or assistant."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from avatar_rig_data import RigStore
from inochi_idle_motion import motion_samples
from prepare_inochi_viewer import export_bundle
from render_inochi_rig import interpolate


def main():
    workspace = Path(__file__).resolve().parents[2]
    root = workspace / '.cache/avatar-authoring/jingliu'
    store = RigStore(root); source = 'authoring/jingliu-v5-idle-test-v2.inx'
    before = hashlib.sha256(store.path(source).read_bytes()).hexdigest()
    exported = export_bundle(store, source)
    bundle = Path(exported['bundle']); model = json.loads((bundle / 'model.json').read_text())
    data, _ = store.read(source)
    clips = [{'name': name, 'fps': 120, 'poses': motion_samples(data, name, c['timestep'] * c['length'], 120)['poses']}
             for name, c in data['animations'].items()]
    geometry = []
    for sign in (-1, 1):
        values = {p['name']: p['defaults'][:] for p in data['param']}
        values.update({'Head XY - small turn': [sign * .7, sign * .5], 'Head tilt': [sign * .4, 0],
                       'Hair sway - manual test': [-sign * .3, 0], 'Eye gaze XY': [sign * .6, sign * .5],
                       'Eye L open': [.3, 0], 'Eye R open': [.6, 0], 'Mouth open': [.8, 0], 'Mouth form': [sign, 0]})
        offsets = {}
        for p in data['param']:
            for b in p['bindings']:
                if b['param_name'] != 'deform': continue
                value = interpolate(p, b, values)
                target = offsets.setdefault(b['node'], [[0, 0] for _ in value])
                for i, delta in enumerate(value):
                    target[i][0] += delta[0]; target[i][1] += delta[1]
        parts = {}
        for part in data['nodes']['children']:
            if part['type'] != 'Part': continue
            delta = offsets.get(part['uuid'], [[0, 0] for _ in range(len(part['mesh']['verts']) // 2)])
            parts[str(part['uuid'])] = [v + delta[i // 2][i % 2] + part['transform']['trans'][i % 2] + 627
                                       for i, v in enumerate(part['mesh']['verts'])]
        geometry.append({'values': values, 'parts': parts})
    node = shutil.which('node')
    if not node: raise RuntimeError('Node.js is required for this opt-in comparison.')
    result = subprocess.run([node, str(workspace / 'dev/rig/check_inochi_viewer.mjs')],
                            input=json.dumps({'model': model, 'clips': clips, 'geometry': geometry}),
                            text=True, capture_output=True, timeout=60, check=True)
    report = {'source': source, 'sourceSha256': before, **json.loads(result.stdout),
              'sourceUnchanged': hashlib.sha256(store.path(source).read_bytes()).hexdigest() == before,
              'bundle': bundle.relative_to(root).as_posix(),
              'limits': 'Compares two inspection evaluators, not the official native runtime or rasterized pixels.'}
    assert report['sourceUnchanged']
    folder = root / 'review-viewer-v1'; folder.mkdir(exist_ok=True)
    (folder / 'numeric-verification.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__': main()
