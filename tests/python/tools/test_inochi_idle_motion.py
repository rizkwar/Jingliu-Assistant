import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'dev'/'rig'))
from avatar_rig_data import RigStore
from inochi_idle_motion import blink_keys,lane,lane_value,Pendulum,inspection_data


class IdleMotionTests(unittest.TestCase):
    def test_blink_is_bounded_asymmetric_and_restores_open_eyes(self):
        track=lane({'uuid':1},0,blink_keys(600,[90,282,476]))
        samples=[lane_value(track,i/4) for i in range(600*4)]
        self.assertEqual(min(samples),0);self.assertEqual(max(samples),1)
        self.assertEqual(lane_value(track,89),1)
        self.assertEqual(lane_value(track,94),0)
        self.assertEqual(lane_value(track,96),0)
        self.assertEqual(lane_value(track,104),1)
        self.assertEqual(lane_value(track,599),1)
        self.assertGreater(1-lane_value(track,92),lane_value(track,98))

    def test_bezier_loop_seam_has_matching_values_and_zero_endpoint_slope(self):
        track=lane({'uuid':1},0,[(0,0),(100,.5),(200,0)])
        self.assertEqual(lane_value(track,0),lane_value(track,200))
        self.assertLess(abs(lane_value(track,.01)),1e-6)
        self.assertLess(abs(lane_value(track,199.99)),1e-6)

    def test_pendulum_lags_a_turn_then_settles_without_length_drift(self):
        p=Pendulum([0,0],180,1470,.85,5);samples=[]
        for i in range(1440):
            anchor=[30 if i>=60 else 0,0]
            samples.append(p.step(anchor,1/120))
            self.assertAlmostEqual(math_distance(p.bob,anchor),180,places=8)
        self.assertGreater(max(samples),.1)
        self.assertLess(abs(samples[-1]),1e-7)
        self.assertLess(max(abs(b-a) for a,b in zip(samples[60:],samples[61:])),.02)

    def test_pendulum_is_stable_at_multiple_frame_rates_and_rejects_bad_steps(self):
        final=[]
        for fps in (30,60,120):
            p=Pendulum([0,0],180,1470,.85,5)
            for i in range(12*fps):
                anchor=[25 if i>=fps else 0,0];value=p.step(anchor,1/fps)
            final.append(value)
        self.assertTrue(all(abs(v)<1e-6 for v in final))
        with self.assertRaises(ValueError):p.step([0,0],float('nan'))
        with self.assertRaises(ValueError):p.step([0,0],1)

    def test_inspection_view_does_not_mutate_the_rig_or_strip_artwork(self):
        part={'uuid':2,'type':'Part','name':'hair'};driver={'uuid':4,'type':'SimplePhysics'}
        data={'nodes':{'uuid':1,'type':'Node','children':[part,driver]},'param':[{'bindings':[{'node':2},{'node':4}]}]}
        original=copy.deepcopy(data);view=inspection_data(data)
        self.assertEqual(data,original)
        self.assertEqual(view['nodes']['children'],[part])
        self.assertEqual(view['param'][0]['bindings'],[{'node':2}])

    def test_validator_rejects_missing_physics_targets_and_bad_animation_keys(self):
        param={'uuid':3,'name':'Sway','is_vec2':False,'min':[-1,0],'max':[1,1],
               'defaults':[0,0],'axis_points':[[0,1],[0]],'bindings':[]}
        driver={'uuid':2,'type':'SimplePhysics','param':3,'model_type':'Pendulum','map_mode':'AngleLength',
                'length':180,'frequency':1,'gravity':.15,'angle_damping':.85,'length_damping':1,'output_scale':[5,0]}
        data={'nodes':{'uuid':1,'type':'Node','children':[driver]},'param':[param]}
        RigStore.validate_data(data,0)
        bad=copy.deepcopy(data);bad['nodes']['children'][0]['model_type']='pendulum'
        with self.assertRaisesRegex(ValueError,'physics driver'):RigStore.validate_data(bad,0)
        bad=copy.deepcopy(data);bad['nodes']['children'][0]['param']=99
        with self.assertRaisesRegex(ValueError,'physics driver'):RigStore.validate_data(bad,0)
        bad=copy.deepcopy(data);bad['animations']={'Bad':{'timestep':1/60,'length':100,
            'lanes':[lane(param,0,[(0,0),(50,2)])]}}
        with self.assertRaisesRegex(ValueError,'keyframe'):RigStore.validate_data(bad,0)
        bad['animations']['Bad']['lanes'][0]['keyframes'][1]['value']=0
        bad['animations']['Bad']['lanes'][0]['keyframes'][1]['frame']=0
        with self.assertRaisesRegex(ValueError,'keyframe'):RigStore.validate_data(bad,0)


def math_distance(a,b):return ((a[0]-b[0])**2+(a[1]-b[1])**2)**.5


if __name__=='__main__':unittest.main()
