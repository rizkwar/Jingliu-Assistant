import json
from pathlib import Path
import struct
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from companion.avatar_assets import AvatarAssets
from companion.avatar_models import AvatarModels
from companion.layered_assets import layered_bundle


def fixture(folder):
    folder.mkdir(parents=True, exist_ok=True)
    # Validation needs the PNG signature and dimensions, not a rendering fixture.
    (folder / 'image.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + struct.pack('>II', 1254, 1254))
    names = ('source', 'base', 'hairmask', 'underpaint', 'backhair', 'eye0_ball', 'eye1_ball',
             'eyes_closed_0', 'eyes_closed_1', 'eyes_half_0', 'eyes_half_1', 'mouth_a', 'mouth_a_half', 'mouth_i')
    manifest = {'format': 'assistant-layered', 'version': 1, 'size': [1254, 1254],
                'textures': {n: 'image.png' for n in names},
                'eyes': [{'x0': 0, 'x1': 10, 'top': [0, 1], 'bot': [2, 3]}] * 2,
                'rects': {n: [0, 0, 10, 10] for n in names[5:]}, 'underpaintOffset': [0, 12]}
    path = folder / 'layered.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    return path


class LayeredAssetsTests(unittest.TestCase):
    def test_install_is_per_character_deduplicated_and_does_not_change_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);path = fixture(root / 'source');library = AvatarModels(root)
            profile = str(root / 'character.toml')
            model = library.import_layered(profile, path)
            duplicate = library.import_layered(profile, path)
            self.assertEqual(model['id'], duplicate['id'])
            self.assertEqual(library.selected(profile)['id'], 'current')
            library.select(profile, model['id'])
            self.assertEqual(AvatarModels(root).selected(profile)['kind'], 'layered')
            self.assertEqual(len(library.models(profile)), 2)
            self.assertEqual(len(library.models(str(root / 'other.toml'))), 1)
            self.assertEqual(set(layered_bundle(library.model_path(model))), {'image.png', 'layered.json'})

    def test_external_traversal_and_invalid_metadata_do_not_install_or_change_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);path = fixture(root / 'source');document = json.loads(path.read_text())
            library = AvatarModels(root);profile = str(root / 'character.toml')
            for resource in ['../image.png', '/image.png', 'https://example.org/image.png', 'C:/private.png', 'sub\\image.png']:
                bad = {**document, 'textures': {**document['textures'], 'source': resource}}
                path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    library.import_layered(profile, path)
                self.assertEqual(library.selected(profile)['id'], 'current')
            path.write_text(json.dumps({**document, 'eyes': [{'top': [float('nan')]}, {}]}))
            with self.assertRaises(ValueError):
                layered_bundle(path)
            self.assertFalse(library.path.exists())

    def test_layered_service_has_explicit_image_routes_and_needs_no_live2d_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);source = fixture(root / 'source')
            web = root / 'companion/avatar_web';(web / 'vendor').mkdir(parents=True)
            for name in ['index.html', 'viewer.js', 'conversation-state.js', 'render-quality.js', 'render-cadence.js',
                         'assistant-motion.js', 'motion-preview.js', 'idle-attention.js', 'stable-step.js', 'style.css',
                         'vendor/mesh-avatar.js', 'layered-avatar.js', 'layered-rig.js', 'live2d-rig.js', 'rig-preview.js']:
                (web / name).write_text('fixture')
            (source.parent / 'private.txt').write_text('private fixture')
            server = AvatarAssets(source, root, kind='layered')
            try:
                base = server.url.rsplit('/', 1)[0] + '/'
                with urlopen(base + 'model/image.png') as response:
                    self.assertEqual(response.headers['Content-Type'], 'image/png')
                    self.assertNotIn('unsafe-eval', response.headers['Content-Security-Policy'])
                    self.assertTrue(response.read().startswith(b'\x89PNG'))
                with urlopen(base + 'renderer.json') as response:
                    self.assertEqual(json.load(response), {'kind': 'layered'})
                for name in ['model/private.txt', 'model/../private.txt', '.env', 'runtime/cubism4.min.js']:
                    with self.assertRaises(HTTPError):
                        urlopen(base + name)
            finally:
                server.close()


if __name__ == '__main__':
    unittest.main()
