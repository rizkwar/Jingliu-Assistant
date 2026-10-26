"""Export a read-only WebGL inspection bundle from the saved Inochi 0.8 rig.

This does not create an INP, change the source, or load assistant credentials.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import secrets
import sys

from avatar_rig_data import RigStore
from inochi_idle_motion import inspection_data, MotionPlayer
from render_inochi_rig import textures, encoded_png, render
from PySide6.QtGui import QImage


def validate_supported(data, images):
    """Fail closed on features the inspection renderer cannot reproduce."""
    render(inspection_data(data), images, {}, 8)
    drivers = [n for n in data['nodes']['children'] if n['type'] == 'SimplePhysics']
    if len(drivers) != 1:
        raise ValueError('The viewer requires exactly one configured hair pendulum.')
    if data.get('automation'):
        raise ValueError('The viewer does not run automation scripts.')
    for part in data['nodes']['children']:
        if part.get('children'):
            raise ValueError('Nested nodes need a native runtime.')
        if part['type'] == 'SimplePhysics':
            if part.get('local_only') or part['model_type'] != 'Pendulum' or part['map_mode'] != 'AngleLength' or part['output_scale'][1] != 0:
                raise ValueError('Unsupported pendulum configuration.')
            continue
        if len(part['mesh']['verts']) // 2 > 65535:
            raise ValueError('Mesh exceeds the viewer index limit.')
        if part['textures'][1:] != [2**32 - 1, 2**32 - 1]:
            raise ValueError('Emission/bump textures need a native runtime.')
        if any(m['mode'] != 'Mask' for m in part.get('masks', [])):
            raise ValueError('This viewer supports ordinary clipping masks only.')
    for p in data['param']:
        for b in p['bindings']:
            if b.get('isSet') and not all(all(row) for row in b['isSet']):
                raise ValueError('Unset keyforms need a native runtime.')
    if not data.get('animations'):
        raise ValueError('Start with the saved idle-motion checkpoint.')
    for name, clip in data['animations'].items():
        if clip.get('additive') or clip.get('animationWeight', 1) != 1 or clip.get('leadIn', -1) != -1 or clip.get('leadOut', -1) != -1:
            raise ValueError('Animation mixing and lead-in/out need a native runtime.')
        if any(l.get('merge_mode', 'Forced') != 'Forced' or l['interpolation'] not in ('Linear', 'Bezier') for l in clip['lanes']):
            raise ValueError('Unsupported animation lane mode.')
        MotionPlayer(data, name).pose(0)


def export_bundle(store, filename, output=None):
    source = store.path(filename)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    data, tail = store.read(filename)
    images = textures(tail)
    validate_supported(data, images)
    output = output or f'viewer/inspection-v1-{before[:12]}-{secrets.token_hex(3)}'
    directory = store.path(output + '/model.json', extensions=('.json',)).parent
    if directory.exists():
        raise FileExistsError('Choose a new viewer bundle directory.')
    puppet = copy.deepcopy({k: data[k] for k in ('physics', 'nodes', 'param', 'animations')})
    for part in puppet['nodes']['children']:
        part.pop('psdLayerPath', None)
    model = {'format': 'jingliu-inochi-inspection-1', 'sourceSha256': before,
             'canvasSize': 1254, 'puppet': puppet,
             'textures': [f'/texture-{i:02d}.png' for i in range(len(images))]}
    # Validate and encode everything before creating any output directory.
    pngs = [encoded_png(img.convertToFormat(QImage.Format.Format_RGBA8888)) for img in images]
    report = {'source': filename, 'sourceSha256': before, 'textureSlots': len(images),
              'parts': len(data['nodes']['children']) - 1, 'parameters': len(data['param']),
              'animations': {k: v['length'] * v['timestep'] for k, v in data['animations'].items()},
              'renderer': 'WebGL inspection of the configured flat Inochi 0.8 subset; not the official SDK.',
              'sourceUnchanged': hashlib.sha256(source.read_bytes()).hexdigest() == before,
              'textureConversion': 'Premultiplied source pixels converted to ordinary PNG for browser upload.',
              'unsupported': ['Nested transforms', 'Composite nodes', 'Non-Normal blending',
                              'Other physics models', 'Animation mixing', 'Arbitrary Inochi models']}
    if not report['sourceUnchanged']:
        raise ValueError('Source changed while preparing the viewer; retry with a stable saved file.')
    directory.mkdir(parents=True, exist_ok=False)
    for i, png in enumerate(pngs):
        (directory / f'texture-{i:02d}.png').write_bytes(png)
    (directory / 'model.json').write_text(json.dumps(model, separators=(',', ':')), encoding='utf8')
    (directory / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    return {'bundle': str(directory), **report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='authoring/jingliu-v5-idle-test-v2.inx')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2] / '.cache/avatar-authoring/jingliu')
    parser.add_argument('--output', help='New relative directory inside the artwork root')
    args = parser.parse_args()
    try:
        print(json.dumps(export_bundle(RigStore(args.root), args.model, args.output)))
    except (OSError, ValueError, KeyError, StopIteration) as error:
        print(f'Could not prepare the rig viewer: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
