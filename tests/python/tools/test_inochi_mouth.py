import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'dev'/'rig'))
from avatar_rig_data import RigStore
from build_inochi_mouth import mesh_for,open_offsets,form_offsets,jaw_offsets,points,transfer_affine


class MouthRigTests(unittest.TestCase):
    def part(self):
        part={'transform':{'trans':[11,96,0]}}
        part['mesh']=mesh_for(part)
        return part

    def test_combined_open_and_form_keep_area_positive(self):
        part=self.part()
        for opening in (0,.04,.1,.5,1):
            for form in (-1,-.5,0,.5,1):
                a,b=open_offsets(part,opening),form_offsets(part,form)
                RigStore.check_orientation(part['mesh'],[[x[0]+y[0],x[1]+y[1]] for x,y in zip(a,b)])
        zero=[[0,0] for _ in points(part)]
        self.assertEqual(open_offsets(part,1),zero)
        self.assertEqual(form_offsets(part,0),zero)

    def test_affine_head_transfer_extends_saved_offsets_and_rejects_sculpting(self):
        source={'transform':{'trans':[0,0,0]},'mesh':{'verts':[-20,-10,20,-10,-20,10,20,10]}}
        values=[[x*.1+2,y*.05-3] for x,y in points(source)]
        target=self.part();transferred=transfer_affine(source,values,target)
        for (x,y),actual in zip(points(target),transferred):
            self.assertAlmostEqual(actual[0],x*.1+2,places=5)
            self.assertAlmostEqual(actual[1],y*.05-3,places=5)
        bad=copy.deepcopy(values);bad[-1][0]+=1
        with self.assertRaisesRegex(ValueError,'not affine'):transfer_affine(source,bad,target)

    def test_jaw_motion_is_local_and_returns_to_zero_on_close(self):
        face={'transform':{'trans':[0,0,0]},'mesh':{'verts':[v for y in (580,710,770,840) for v in (638-627,y-627)]}}
        self.assertEqual(jaw_offsets(face,0),[[0,0]]*4)
        opened=jaw_offsets(face,1)
        self.assertEqual(opened[:2],[[0,0],[0,0]])
        self.assertGreater(opened[2][1],1)
        self.assertLessEqual(opened[2][1],2)
        self.assertEqual(opened[3],[0,0])


if __name__=='__main__':unittest.main()
