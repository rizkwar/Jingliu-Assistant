import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from scripts.avatar_rig_data import MAGIC, RigStore


class RigStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = RigStore(self.root)
        part = {'uuid': 2, 'name': 'Test eye', 'type': 'Part', 'enabled': True,
                'mesh': {'verts': [0, 0, 10, 0, 0, 10], 'uvs': [0, 0, 1, 0, 0, 1], 'indices': [0, 1, 2]},
                'textures': [0, 2**32-1, 2**32-1]}
        self.data = {'nodes': {'uuid': 1, 'type': 'Node', 'name': 'Root', 'children': [part]},
                     'param': [{'uuid': 3, 'name': 'Head', 'is_vec2': False, 'min': [-1, 0], 'max': [1, 1],
                                'defaults': [0, 0], 'axis_points': [[0, .5, 1], [0]],
                                'bindings': [{'node': 2, 'param_name': 'deform', 'values': [
                                    [[[0, 0], [0, 0], [0, 0]]], [[[0, 0], [0, 0], [0, 0]]], [[[0, 0], [0, 0], [0, 0]]]],
                                    'isSet': [[True], [True], [True]]}]}]}
        # Opaque texture payload: these tests validate structure, not image decoding.
        self.tail = b'TEX_SECT' + struct.pack('>IIB', 1, 4, 0) + b'fake'
        self.store.save_new('input.inx', self.data, self.tail)
        self.original = (self.root/'input.inx').read_bytes()

    def test_edit_preserves_source_textures_and_other_keyforms(self):
        self.store.edit_keyform('input.inx', 'edited.inx', 'Head', 2, 2, 0, [{'index': 0, 'dx': 1, 'dy': 1}])
        edited, tail = self.store.read('edited.inx')
        self.assertEqual(tail, self.tail)
        self.assertEqual((self.root/'input.inx').read_bytes(), self.original)
        before = self.data['param'][0]['bindings'][0]['values']
        after = edited['param'][0]['bindings'][0]['values']
        self.assertEqual(after[:2], before[:2])
        self.assertEqual(after[2][0][0], [1, 1])

    def test_rejects_triangle_flip_before_writing(self):
        with self.assertRaisesRegex(ValueError, 'inverts'):
            self.store.edit_keyform('input.inx', 'bad.inx', 'Head', 2, 2, 0, [{'index': 1, 'dx': -20, 'dy': 0}])
        self.assertFalse((self.root/'bad.inx').exists())

    def test_paths_are_scoped_and_output_is_exclusive(self):
        for name in ('../escape.inx', '/absolute.inx', 'C:/absolute.inx', 'nested\\bad.inx', '.env', 'a/../input.inx'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.store.path(name)
        with self.assertRaises(FileExistsError):
            self.store.set_defaults('input.inx', 'input.inx', {'Head': [.5, 0]})
        self.assertEqual((self.root/'input.inx').read_bytes(), self.original)

    def test_rejects_nonfinite_and_bad_defaults(self):
        for value in ([float('nan'), 0], [2, 0], [0, 1]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.set_defaults('input.inx', 'bad.inx', {'Head': value})
        self.assertFalse((self.root/'bad.inx').exists())

    def test_truncated_container_is_rejected(self):
        (self.root/'truncated.inx').write_bytes(self.original[:-1])
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            self.store.read('truncated.inx')

    def test_binding_target_and_mesh_indices_are_checked(self):
        data = copy.deepcopy(self.data)
        data['param'][0]['bindings'][0]['node'] = 99
        with self.assertRaisesRegex(ValueError, 'binding target'):
            self.store.save_new('bad.inx', data, self.tail)
        data = copy.deepcopy(self.data)
        data['nodes']['children'][0]['mesh']['indices'][-1] = 99
        with self.assertRaisesRegex(ValueError, 'Triangle index'):
            self.store.save_new('bad.inx', data, self.tail)

    def test_mask_references_modes_and_thresholds_are_checked(self):
        for source in (2,99,True):
            data=copy.deepcopy(self.data)
            data['nodes']['children'][0]['masks']=[{'source':source,'mode':'Mask'}]
            with self.assertRaisesRegex(ValueError,'mask source'):
                self.store.save_new('bad.inx',data,self.tail)
        data=copy.deepcopy(self.data)
        source=copy.deepcopy(data['nodes']['children'][0]);source['uuid']=4
        data['nodes']['children'].append(source)
        part=data['nodes']['children'][0];part['masks']=[{'source':4,'mode':'Mask'}]
        self.store.save_new('masked.inx',data,self.tail)
        part['mask_threshold']=float('nan')
        with self.assertRaisesRegex(ValueError,'mask threshold'):
            self.store.save_new('bad.inx',data,self.tail)

    def test_defaults_roundtrip_and_bounded_inspection(self):
        self.store.set_defaults('input.inx', 'pose.inx', {'Head': [.5, 0]})
        self.assertEqual(self.store.summary('pose.inx')['parameters'][0]['defaults'], [.5, 0])
        self.assertEqual(len(self.store.keyform('pose.inx', 'Head', 2, 2, 0, count=2)['vertices']), 2)
        with self.assertRaises(ValueError):
            self.store.keyform('pose.inx', 'Head', 2, -1, 0)
        with self.assertRaises(ValueError):
            self.store.keyform('pose.inx', 'Head', 2, 2, 0, count=1000)


if __name__ == '__main__':
    unittest.main()
