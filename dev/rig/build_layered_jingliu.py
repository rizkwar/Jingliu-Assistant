"""Install the optional v5 layered rig; originals and selected model stay intact.

The generated underpainting is only revealed behind moving original cutouts.
This script copies assets; raster preparation/compositing happens in the renderer.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from companion.avatar.models import AvatarModels


def build(project, underpaint, library, profile, back_hair=None):
    with tempfile.TemporaryDirectory() as folder:
        destination = Path(folder)
        import shutil
        textures = {}
        files = {'source': project / 'source.png', 'base': project / 'built/base.png',
                 'hairmask': project / 'built/hairmask.png', 'underpaint': underpaint,
                 'backhair': back_hair or underpaint.with_name('back-hair.png')}
        layers = json.loads((project / 'built/layers.json').read_text(encoding='utf-8'))
        sprites = json.loads((project / 'built/sprites/sprites.json').read_text(encoding='utf-8'))
        for name in layers['layers']:
            files[name] = project / 'built' / (name + '.png')
        for name in sprites['layers']:
            files[name] = project / 'built/sprites' / (name + '.png')
        for name, source in files.items():
            textures[name] = name + '.png'
            shutil.copyfile(source, destination / textures[name])
        manifest = {'format': 'assistant-layered', 'version': 1, 'size': [1254, 1254],
                    'textures': textures, 'eyes': layers['eyes'],
                    'rects': {**layers['layers'], **sprites['layers']},
                    'underpaintOffset': [0, 12],
                    'credit': 'AI-assisted Jingliu v5 fan artwork. Original visible art retained; generated hidden underpainting.'}
        (destination / 'layered.json').write_text(json.dumps(manifest), encoding='utf-8')
        return library.import_layered(profile, destination / 'layered.json', 'AI v5 layered rig (experimental)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=ROOT / '.cache/mesh-avatar-studio/projects/jingliu')
    parser.add_argument('--underpaint', type=Path, default=ROOT / '.cache/avatar-rigs/jingliu-layered/underpaint.png')
    args = parser.parse_args()
    model = build(args.project, args.underpaint, AvatarModels(), str(ROOT / 'character.toml'))
    print('Installed:', model['name'], model['id'])
    print('Choose it in Settings > Jingliu visual model. Your current choice has not changed.')
