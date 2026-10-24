import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from avatar_rig_data import RigStore
from prepare_inochi_viewer import export_bundle, validate_supported
from render_inochi_rig import encoded_png
from PySide6.QtGui import QColor, QImage


class InochiViewerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.store = RigStore(self.root)
        self.image = QImage(2, 2, QImage.Format.Format_RGBA8888_Premultiplied)
        self.image.fill(QColor(128, 64, 0, 128))
        self.data = {'meta': {'artist': 'Local private author'}, 'physics': {'gravity': 9.8, 'pixelsPerMeter': 1000},
            'nodes': {'uuid': 1, 'type': 'Node', 'children': [
                {'uuid': 2, 'name': 'Art', 'type': 'Part', 'psdLayerPath': '/private/source',
                 'transform': {'trans': [0, 0, 0], 'rot': [0, 0, 0], 'scale': [1, 1]},
                 'mesh': {'verts': [-627, -627, 627, -627, -627, 627], 'uvs': [0, 0, 1, 0, 0, 1], 'indices': [0, 1, 2]},
                 'textures': [0, 2**32-1, 2**32-1]},
                {'uuid': 3, 'type': 'SimplePhysics', 'param': 5, 'model_type': 'Pendulum', 'map_mode': 'AngleLength',
                 'transform': {'trans': [0, 0, 0], 'rot': [0, 0, 0], 'scale': [1, 1]},
                 'length': 180, 'frequency': 1, 'gravity': .15, 'angle_damping': .85, 'length_damping': 1, 'output_scale': [5, 0]}]},
            'param': [{'uuid': 5, 'name': 'Hair', 'is_vec2': False, 'min': [-1, 0], 'max': [1, 1],
                       'defaults': [0, 0], 'axis_points': [[0, 1], [0]], 'bindings': []}],
            'animations': {'Idle': {'timestep': 1/60, 'length': 60, 'lanes': []}}}
        native = self.image.copy()
        native.reinterpretAsFormat(QImage.Format.Format_RGBA8888)
        png = encoded_png(native); self.tail = b'TEX_SECT' + struct.pack('>IIB', 1, len(png), 0) + png
        self.store.save_new('source.inx', self.data, self.tail)

    def test_export_preserves_source_and_excludes_private_author_metadata(self):
        before = (self.root / 'source.inx').read_bytes()
        report = export_bundle(self.store, 'source.inx', 'viewer/test')
        self.assertTrue(report['sourceUnchanged']); self.assertEqual(report['parts'], 1)
        model = json.loads((self.root / 'viewer/test/model.json').read_text())
        self.assertNotIn('meta', model['puppet'])
        self.assertNotIn('psdLayerPath', model['puppet']['nodes']['children'][0])
        self.assertEqual((self.root / 'source.inx').read_bytes(), before)
        # The browser receives straight-alpha PNGs; it premultiplies at upload.
        converted = QImage(str(self.root / 'viewer/test/texture-00.png')).pixelColor(0, 0)
        self.assertLessEqual(abs(converted.red() - 128), 1); self.assertEqual(converted.alpha(), 128)
        with self.assertRaises(FileExistsError): export_bundle(self.store, 'source.inx', 'viewer/test')
        with self.assertRaises(ValueError): export_bundle(self.store, 'source.inx', '../escape')

    def test_unimplemented_native_features_are_rejected_before_any_export(self):
        for change in ('nested', 'blend', 'physics', 'texture', 'mixing', 'automation', 'mask'):
            d = copy.deepcopy(self.data); part, driver = d['nodes']['children']
            if change == 'nested': part['children'] = [{'uuid': 90, 'type': 'Node'}]
            elif change == 'blend': part['blend_mode'] = 'Multiply'
            elif change == 'physics': driver['model_type'] = 'SpringPendulum'
            elif change == 'texture': part['textures'][1] = 0
            elif change == 'mixing': d['animations']['Idle']['additive'] = True
            elif change == 'automation': d['automation'] = [{'name': 'script'}]
            elif change == 'mask': part['masks'] = [{'source': 2, 'mode': 'DodgeMask'}]
            with self.subTest(change=change), self.assertRaises(ValueError): validate_supported(d, [self.image])


if __name__ == '__main__': unittest.main()
