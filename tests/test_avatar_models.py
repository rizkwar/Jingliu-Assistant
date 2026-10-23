import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from companion.avatar_models import AvatarModels, live2d_bundle


def fixture(folder):
    folder.mkdir(parents=True, exist_ok=True)
    document = {'Version': 3, 'FileReferences': {'Moc': 'avatar.moc3', 'Textures': ['texture.png'],
        'Physics': 'physics.json', 'Motions': {'Idle': [{'File': 'idle.json', 'Sound': 'private.wav'}]}},
        'Custom': {'File': 'private.txt'}}
    (folder / 'avatar.model3.json').write_text(json.dumps(document), encoding='utf-8')
    (folder / 'avatar.moc3').write_bytes(b'MOC3-test')
    (folder / 'texture.png').write_bytes(b'fixture texture')
    (folder / 'physics.json').write_text('{"PhysicsSettings": []}', encoding='utf-8')
    return folder / 'avatar.model3.json'


class AvatarModelTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = fixture(self.root / 'source')
        self.library = AvatarModels(self.root)
        self.profile = str(self.root / 'character.toml')

    def test_import_is_visual_only_preserves_source_and_defaults_to_current(self):
        original = {p.name: p.read_bytes() for p in self.source.parent.iterdir()}
        model = self.library.import_live2d(self.profile, self.source, 'Rigged model')
        self.assertEqual(self.library.selected(self.profile)['id'], 'current')
        self.assertEqual({p.name: p.read_bytes() for p in self.source.parent.iterdir()}, original)
        self.library.select(self.profile, model['id'])
        reopened = AvatarModels(self.root)
        self.assertEqual(reopened.selected(self.profile)['name'], 'Rigged model')
        self.assertEqual(reopened.selected(str(self.root / 'other.toml'))['id'], 'current')
        self.library.select(self.profile, 'current')
        self.assertEqual(self.library.selected(self.profile)['kind'], 'mesh')
        # No profile, voice, preferences or conversation files are created.
        self.assertFalse(Path(self.profile).exists())
        self.assertFalse((self.root / 'data/preferences.json').exists())

    def test_only_required_rig_resources_are_retained_without_audio_or_motions(self):
        bundle = live2d_bundle(self.source)
        document = json.loads(bundle['model3.json'])
        self.assertEqual(set(document['FileReferences']), {'Moc', 'Textures', 'Physics'})
        self.assertNotIn(b'private', b''.join(bundle.values()))
        self.assertEqual(len(bundle), 4)
        self.assertTrue(all(name.isascii() for name in bundle))

    def test_zip_with_legacy_chinese_names_resolves_manifest_resources(self):
        source = self.root / 'legacy.zip'
        name = '\u955c\u6d41'
        garbled = name.encode('gbk').decode('cp437')
        document = {'Version': 3, 'FileReferences': {'Moc': name + '.moc3', 'Textures': ['texture.png']}}
        class LegacyInfo(zipfile.ZipInfo):
            def _encodeFilenameFlags(self):
                return self.filename.encode('cp437'), self.flag_bits & ~0x800
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr(LegacyInfo(garbled + '/' + garbled + '.model3.json'), json.dumps(document))
            archive.writestr(LegacyInfo(garbled + '/' + garbled + '.moc3'), b'MOC3-test')
            archive.writestr(LegacyInfo(garbled + '/texture.png'), b'image')
        bundle = live2d_bundle(source)
        self.assertEqual(len(bundle), 3)
        manifest = json.loads(bundle['model3.json'])
        self.assertEqual(bundle[manifest['FileReferences']['Moc']], b'MOC3-test')

    def test_unsafe_manifest_paths_are_rejected_without_reading_secrets(self):
        for path in ('../secret.moc3', 'https://example.org/a.moc3', '/etc/a.moc3',
                     'C:\\secret.moc3', '\\\\host\\share\\a.moc3'):
            with self.subTest(path=path):
                document = {'Version': 3, 'FileReferences': {'Moc': path, 'Textures': ['texture.png']}}
                self.source.write_text(json.dumps(document))
                with self.assertRaises(ValueError):
                    live2d_bundle(self.source)

    def test_zip_traversal_and_multiple_models_are_rejected(self):
        for names in (['../avatar.model3.json'], ['a.model3.json', 'b.model3.json']):
            source = self.root / 'bad.zip'
            with zipfile.ZipFile(source, 'w') as archive:
                for name in names:
                    archive.writestr(name, '{}')
            with self.assertRaises(ValueError):
                live2d_bundle(source)

    def test_invalid_reimport_keeps_installed_model_and_selected_option(self):
        model = self.library.import_live2d(self.profile, self.source)
        self.library.select(self.profile, model['id'])
        original = self.library.path.read_bytes()
        (self.source.parent / 'avatar.moc3').write_bytes(b'not a model')
        with self.assertRaises(ValueError):
            self.library.import_live2d(self.profile, self.source)
        self.assertEqual(self.library.path.read_bytes(), original)
        self.assertTrue(self.library.model_path(model).exists())

    def test_duplicate_import_deduplicates_and_views_are_per_model(self):
        first = self.library.import_live2d(self.profile, self.source, blindfold_parameter='Param100')
        second = self.library.import_live2d(self.profile, self.source, blindfold_parameter='Param100')
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(self.library.models(self.profile)), 2)
        self.library.set_framing(self.profile, first['id'], 'full')
        self.library.set_blindfold(self.profile, first['id'], True)
        self.library.select(self.profile, first['id'])
        selected = self.library.selected(self.profile)
        self.assertEqual(selected['framing'], 'full')
        self.assertEqual(selected['appearance'], {'Param100': 0})
        with self.assertRaises(ValueError):
            self.library.select(str(self.root / 'other.toml'), first['id'])

    def test_failed_registry_save_keeps_previous_selection(self):
        model = self.library.import_live2d(self.profile, self.source)
        before = self.library.path.read_bytes()
        with patch('companion.avatar_models.os.replace', side_effect=PermissionError('busy')):
            with self.assertRaises(OSError):
                self.library.select(self.profile, model['id'])
        self.assertEqual(self.library.path.read_bytes(), before)
        self.assertEqual(list(self.library.path.parent.glob('*.tmp')), [])
