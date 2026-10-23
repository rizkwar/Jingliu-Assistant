import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from companion.avatar_assets import AvatarAssets, assigned_avatar


class AvatarAssetTests(unittest.TestCase):
    def test_assignment_matches_profile_path_not_display_name(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'data').mkdir()
            (root / 'data/avatars.json').write_text(json.dumps({'characters': {
                'character.toml': 'data/portrait.mavatar'}}), encoding='utf-8-sig')
            self.assertEqual(assigned_avatar(str(root / 'character.toml'), root), (root / 'data/portrait.mavatar').resolve())
            self.assertIsNone(assigned_avatar(str(root / 'other.toml'), root))
            (root / 'data/avatars.json').write_text('broken', encoding='utf-8')
            with self.assertRaises(ValueError):
                assigned_avatar(str(root / 'character.toml'), root)

    def test_service_only_exposes_explicit_assets_and_closes_socket(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            web = root / 'companion/avatar_web'
            (web / 'vendor').mkdir(parents=True)
            for name in ['index.html', 'viewer.js', 'conversation-state.js', 'render-quality.js', 'style.css', 'vendor/mesh-avatar.js']:
                (web / name).write_text('test', encoding='utf-8')
            model = root / 'portrait.mavatar'
            model.write_bytes(b'avatar')
            (root / '.env').write_text('private fixture', encoding='utf-8')
            server = AvatarAssets(model, root)
            url = server.url
            try:
                with urlopen(url, timeout=2) as response:
                    self.assertEqual(response.read(), b'test')
                    self.assertIn("default-src 'none'", response.headers['Content-Security-Policy'])
                base = url.rsplit('/', 1)[0] + '/'
                for path in ['.env', '../.env', '%2e%2e/.env', 'source.png']:
                    with self.assertRaises(HTTPError):
                        urlopen(base + path, timeout=2)
                with self.assertRaises(HTTPError):
                    urlopen(Request(url, headers={'Host': 'example.org'}), timeout=2)
                with self.assertRaises(HTTPError):
                    urlopen(Request(url, method='POST'), timeout=2)
                with urlopen(base + 'avatar.mavatar', timeout=2) as response:
                    self.assertEqual(response.read(), b'avatar')
            finally:
                server.close()
            with self.assertRaises(URLError):
                urlopen(url, timeout=1)

    def test_missing_assets_fail_before_starting_server(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                AvatarAssets(Path(folder) / 'missing.mavatar', Path(folder))
