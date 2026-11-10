import unittest
from PIL import Image
import rrgh_overview_coverage as coverage

class CoverageTests(unittest.TestCase):
    def test_native_and_interior_are_fully_opaque(self):
        left,top,right,bottom=coverage.grid(16)
        for x,y in ((left,top),(right,bottom),((left+right)//2,(top+bottom)//2)):
            self.assertEqual(coverage.alpha(16,x,y),b'\xff'*65536)
        self.assertEqual(coverage.alpha(15,(left+right)//4,(top+bottom)//4),b'\xff'*65536)

    def test_boundary_matches_original_rgba_resampling(self):
        for z in range(10,16):
            left,top,right,bottom=coverage.grid(z)
            for x,y in ((left,top),(right,bottom)):
                canvas=Image.new('RGBA',(512,512),(0,0,0,0))
                for zz,xx,yy in coverage.child_positions(z,x,y):
                    image=Image.new('RGBA',(256,256),(40,110,70,255))
                    image.putalpha(Image.frombytes('L',(256,256),coverage.alpha(zz,xx,yy)))
                    canvas.paste(image,((xx-2*x)*256,(yy-2*y)*256))
                result=canvas.resize((256,256),Image.Resampling.LANCZOS)
                self.assertEqual(result.getchannel('A').tobytes(),coverage.alpha(z,x,y))
                coverage.verify(result,z,x,y)

    def test_missing_interior_and_invented_exterior_are_rejected(self):
        z=14;x,y,_,_=coverage.grid(z);mask=coverage.alpha(z,x,y)
        valid=Image.new('RGBA',(256,256),(80,110,120,255));valid.putalpha(Image.frombytes('L',(256,256),mask))
        for original,new in ((255,0),(0,255)):
            position=mask.index(original);image=valid.copy();image.putpixel((position%256,position//256),(80,110,120,new))
            with self.assertRaises(ValueError):coverage.verify(image,z,x,y)

    def test_known_northern_edge_has_only_two_required_children(self):
        self.assertEqual(coverage.child_positions(14,4378,6322),[(15,8756,12645),(15,8757,12645)])
        mask=coverage.alpha(14,4378,6322)
        self.assertEqual(mask[:120*256],bytes(120*256))
        self.assertEqual(mask[136*256:],b'\xff'*(120*256))

    def test_only_required_children_are_selected(self):
        for z in range(10,16):
            left,top,right,bottom=coverage.grid(z)
            for x,y in ((left,top),(right,bottom)):
                wanted=coverage.child_positions(z,x,y)
                self.assertTrue(wanted)
                self.assertEqual(len(wanted),len(set(wanted)))
                for dx in range(2):
                    for dy in range(2):
                        child=(z+1,2*x+dx,2*y+dy)
                        self.assertEqual(child in wanted,coverage.inside(*child))

if __name__=='__main__':unittest.main()
