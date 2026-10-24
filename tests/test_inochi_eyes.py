import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from avatar_rig_data import RigStore
from build_inochi_eyes import blink_offsets


class EyeKeyformTests(unittest.TestCase):
    def part(self):
        # Covers the left eye and its skin. Six-pixel mesh spacing is deliberate:
        # deformation should remain monotone through the aperture and lid roots.
        points=[(x,y) for y in range(550,640,6) for x in range(442,620,6)]
        width=len(range(442,620,6));height=len(range(550,640,6));indices=[]
        for y in range(height-1):
            for x in range(width-1):
                a=y*width+x;indices.extend([a,a+width,a+1,a+1,a+width,a+width+1])
        return {'transform':{'trans':[0,0,0]},'mesh':{'verts':[v-627 for p in points for v in p],'indices':indices}}

    def test_opening_does_not_squash_the_iris_and_rest_lids_are_unchanged(self):
        part=self.part();zero=[[0,0]]*(len(part['mesh']['verts'])//2)
        self.assertEqual(blink_offsets(part,'L','iris',0),zero)
        for component in ('sclera aperture','upper lid','lower lid'):
            self.assertEqual(blink_offsets(part,'L',component,1),zero)

    def test_closed_aperture_has_positive_area_and_lid_keyforms_do_not_flip(self):
        part=self.part()
        for component in ('sclera aperture','upper lid','lower lid'):
            for opening in (0,.05,.1,.3,.5,.8,1):
                offsets=blink_offsets(part,'L',component,opening)
                RigStore.check_orientation(part['mesh'],offsets)
        # Points at the fixed upper root stay fixed during closing.
        upper=blink_offsets(part,'L','upper lid',0)
        self.assertTrue(all(p==[0,0] for p in upper[:30]))


if __name__=='__main__':unittest.main()
