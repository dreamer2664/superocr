#!/usr/bin/env python3
import pathlib,sys,unittest
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from s56_seam_probe import detected_word_crops,read_mask
from readers.glyphcnn import N_CLASSES
class DummyNet:
    def forward(self,x):
        p=np.zeros((len(x),N_CLASSES));p[:,0]=1
        return p,None
class InterfaceTests(unittest.TestCase):
    def test_h32_xyxy_context_clipped_and_optional_offsets(self):
        mask=np.ones((14,20),bool)
        records=[{'box':[4,3,12,10],'space':False},{'box':[16,3,18,10],'space':False}]
        crops=detected_word_crops(mask,records)
        self.assertEqual(len(crops),1);c=crops[0]
        self.assertEqual(c['word_bbox_xyxy'],[1,0,19,13]);self.assertEqual(c['word_h'],32)
        self.assertEqual(c['word_w'],round(19*32/14));self.assertEqual(c['context'],3)
        self.assertIsNone(c['glyph_offsets'])
    def test_detected_space_not_truth_controls_word_groups(self):
        mask=np.ones((14,20),bool)
        records=[{'box':[4,3,12,10],'space':False},{'box':[16,3,18,10],'space':True}]
        self.assertEqual(len(detected_word_crops(mask,records)),2)
    def test_no_action_is_matched_and_no_mask_mutation(self):
        m=np.zeros((30,30),bool);m[3:27,5:9]=True;m[3:27,21:25]=True;m[13:17,5:25]=True;copy=m.copy()
        a=read_mask(m,DummyNet(),False);b=read_mask(m,DummyNet(),True)
        self.assertEqual(a['text'],b['text']);self.assertEqual(a['glyph_count'],b['glyph_count'])
        self.assertEqual(b['accepted_seams'],[]);self.assertTrue(np.array_equal(m,copy))
    def test_source_cap_applied_equally(self):
        m=np.zeros((20,1000),bool)
        for x in range(2,992,6):m[3:17,x:x+2]=True
        a=read_mask(m,DummyNet(),False);b=read_mask(m,DummyNet(),True)
        self.assertTrue(a['source_glyph_cap_hit']);self.assertTrue(b['source_glyph_cap_hit'])
        self.assertEqual(a['glyph_count'],128);self.assertEqual(b['glyph_count'],128)
if __name__=='__main__':unittest.main(verbosity=2)
