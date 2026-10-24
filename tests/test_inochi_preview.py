import copy
import os
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from render_inochi_rig import decode_tga, interpolate, render
from PySide6.QtGui import QColor,QImage


class InochiPreviewTests(unittest.TestCase):
    def test_tga_rle_and_bottom_origin_preserve_colors(self):
        header=struct.pack('<BBBHHBHHHHBB',0,0,10,0,0,0,0,0,2,2,32,8)
        # Bottom row blue, top row red. Each packet repeats two pixels.
        image=decode_tga(header+b'\x81'+bytes([255,0,0,255])+b'\x81'+bytes([0,0,255,255]))
        self.assertEqual(image.pixelColor(0,0).getRgb(),(255,0,0,255))
        self.assertEqual(image.pixelColor(1,1).getRgb(),(0,0,255,255))

    def test_tga_premultiplied_alpha_is_not_multiplied_twice(self):
        header=struct.pack('<BBBHHBHHHHBB',0,0,2,0,0,0,0,0,1,1,32,40)
        image=decode_tga(header+bytes([0,0,64,128]))
        color=image.pixelColor(0,0)
        self.assertEqual(color.alpha(),128)
        self.assertLessEqual(abs(color.red()-128),1)
        with self.assertRaises(ValueError):decode_tga(header+b'\x00')

    def test_bilinear_pose_interpolation_and_range_rejection(self):
        p={'name':'Head','min':[-1,-1],'max':[1,1],'defaults':[0,0],'axis_points':[[0,1],[0,1]]}
        b={'values':[[[[0,0]],[[0,10]]],[[[10,0]],[[10,10]]]]}
        self.assertEqual(interpolate(p,b,{}),[[5,5]])
        self.assertEqual(interpolate(p,b,{'Head':[.5,-.5]}),[[7.5,2.5]])
        with self.assertRaises(ValueError):interpolate(p,b,{'Head':[2,0]})

    def test_triangle_render_uses_premultiplied_alpha_and_rejects_unsupported_features(self):
        image=QImage(2,2,QImage.Format.Format_RGBA8888_Premultiplied);image.fill(QColor(255,0,0,128))
        part={'type':'Part','uuid':2,'enabled':True,'transform':{'trans':[0,0,0],'rot':[0,0,0],'scale':[1,1]},
              'mesh':{'verts':[-627,-627,627,-627,-627,627,627,627],'uvs':[0,0,1,0,0,1,1,1],
                      'indices':[0,2,1,1,2,3]},'textures':[0]}
        data={'nodes':{'type':'Node','uuid':1,'children':[part]},'param':[]}
        output=render(data,[image],{},64)
        expected=(144,17,19)
        for x,y in [(16,16),(32,32),(48,48),(16,48)]:
            actual=output.pixelColor(x,y)
            self.assertTrue(all(abs(a-b)<=1 for a,b in zip(actual.getRgb()[:3],expected)),(x,y,actual.getRgb()))
        bad=copy.deepcopy(data);bad['nodes']['children'][0]['blend_mode']='Multiply'
        with self.assertRaisesRegex(ValueError,'Normal'):render(bad,[image],{},64)

    @staticmethod
    def full_part(uuid,texture):
        return {'type':'Part','uuid':uuid,'enabled':True,'transform':{'trans':[0,0,0],'rot':[0,0,0],'scale':[1,1]},
                'mesh':{'verts':[-627,-627,627,-627,-627,627,627,627],'uvs':[0,0,1,0,0,1,1,1],
                        'indices':[0,2,1,1,2,3]},'textures':[texture]}

    def test_clipping_uses_binary_source_alpha_and_ignores_source_opacity(self):
        mask=QImage(2,2,QImage.Format.Format_RGBA8888_Premultiplied);mask.fill(QColor(0,0,0,0))
        mask.setPixelColor(0,0,QColor('white'));mask.setPixelColor(0,1,QColor('white'))
        red=QImage(2,2,QImage.Format.Format_RGBA8888_Premultiplied);red.fill(QColor('red'))
        source=self.full_part(2,0);source.update(opacity=0,mask_threshold=.5,zsort=1)
        iris=self.full_part(3,1);iris['masks']=[{'source':2,'mode':'Mask'}]
        data={'nodes':{'type':'Node','uuid':1,'children':[source,iris]},'param':[]}
        result=render(data,[mask,red],{},64)
        self.assertEqual(result.pixelColor(16,32),QColor('red'))
        self.assertEqual(result.pixelColor(48,32),QColor('#202227'))
        iris['masks'][0]['source']=99
        with self.assertRaisesRegex(ValueError,'mask source'):render(data,[mask,red],{},64)

    def test_scalar_opacity_multiplies_base_and_other_bindings(self):
        image=QImage(2,2,QImage.Format.Format_RGBA8888_Premultiplied);image.fill(QColor('red'))
        part=self.full_part(2,0);part['opacity']=.5
        parameter={'name':'Open','min':[0,0],'max':[1,1],'defaults':[.5,0],'axis_points':[[0,1],[0]],
                   'bindings':[{'node':2,'param_name':'opacity','values':[[0],[1]]}]}
        other=copy.deepcopy(parameter);other['name']='Fade'
        data={'nodes':{'type':'Node','uuid':1,'children':[part]},'param':[parameter,other]}
        result=render(data,[image],{},64)
        # .5 base * .5 Open * .5 Fade = .125, matching Part.setValue.
        for a,b in zip(result.pixelColor(32,32).getRgb()[:3],(60,30,34)):
            self.assertLessEqual(abs(a-b),1)
        self.assertEqual(render(data,[image],{'Open':[0,0]},64).pixelColor(32,32),QColor('#202227'))

    def test_preview_regions_reject_out_of_canvas_or_noninteger_coordinates(self):
        data={'nodes':{'type':'Node','uuid':1,'children':[]},'param':[]}
        for region in ([0,0,1255,2],[-1,0,1,1],[0,0,0,1],[0,0,1.5,2]):
            with self.assertRaises(ValueError):render(data,[],{},64,region)


if __name__=='__main__':unittest.main()
