#!/usr/bin/env python3
import itertools,pathlib,sys,unittest
import numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from s56_topology_seam import minimum_seam,partition,split_piece,STEP_COST

class SeamTests(unittest.TestCase):
    def test_curved_corridor_not_any_straight_column(self):
        h,w=18,16;boundary=np.array([6,7,8,9,10,9,8,7,6]*2)
        x=np.arange(w)[None,:];m=(x<boundary[:,None])|(x>boundary[:,None])
        straight=int((m[:,:-1]&m[:,1:]).sum(axis=0).min())
        seam,energy,crossed=minimum_seam(m)
        self.assertGreater(straight,0);self.assertEqual(crossed,0)
        self.assertGreater(np.abs(np.diff(seam)).sum(),0)
        parts,meta=split_piece(m);self.assertTrue(meta['accepted']);self.assertEqual(len(parts),2)
        left,right=partition(m,seam);self.assertEqual(int(left.sum()+right.sum()),int(m.sum()))
        self.assertFalse((left&right).any())
    def test_thick_H_stays_intact(self):
        m=np.zeros((24,20),bool);m[:,:4]=True;m[:,-4:]=True;m[10:14]=True
        parts,meta=split_piece(m);self.assertFalse(meta['accepted']);self.assertEqual(len(parts),1)
    def test_one_pixel_bridge_partitions_losslessly(self):
        m=np.zeros((24,20),bool);m[:,:7]=True;m[:,-7:]=True;m[12]=True
        parts,meta=split_piece(m);self.assertTrue(meta['accepted']);self.assertEqual(meta['edge_crossings'],1)
        self.assertEqual(sum(int(p.sum()) for p in parts),int(m.sum()))
    def test_tiny_fragment_rejected(self):
        m=np.zeros((24,20),bool);m[:,:12]=True;m[0,-1]=True
        parts,meta=split_piece(m);self.assertFalse(meta['accepted'])
    def test_empty_and_outsize(self):
        for shape in [(0,0),(1,5),(5,1),(257,3),(3,1025)]:
            self.assertIsNone(minimum_seam(np.zeros(shape,bool)))
    def test_flat_ink_not_split(self):
        self.assertFalse(split_piece(np.ones((24,20),bool))[1]['accepted'])
    def test_deterministic(self):
        m=np.random.default_rng(56).random((20,20))<.3
        a=minimum_seam(m);b=minimum_seam(m)
        self.assertTrue(np.array_equal(a[0],b[0]));self.assertEqual(a[1:],b[1:])
    def test_dp_matches_exhaustive_graph_energy(self):
        rng=np.random.default_rng(56)
        for _ in range(20):
            m=rng.random((4,5))<.5
            costs=[]
            for seam in itertools.product(range(1,5),repeat=4):
                if any(abs(a-b)>1 for a,b in zip(seam,seam[1:])):continue
                edges=sum(int(m[y,x-1] and m[y,x]) for y,x in enumerate(seam))
                for y in range(1,4):
                    if seam[y]!=seam[y-1]:
                        x=min(seam[y],seam[y-1]);edges+=int(m[y,x] and m[y-1,x])
                costs.append(edges+STEP_COST*sum(abs(a-b) for a,b in zip(seam,seam[1:])))
            self.assertAlmostEqual(minimum_seam(m)[1],min(costs))
    def test_partition_every_pixel_exactly_once(self):
        m=np.random.default_rng(57).random((30,40))<.6
        seam=minimum_seam(m)[0];a,b=partition(m,seam)
        self.assertTrue(np.array_equal(a|b,m));self.assertFalse((a&b).any())
    def test_no_input_mutation(self):
        m=np.random.default_rng(58).random((10,12))<.5;copy=m.copy()
        split_piece(m);self.assertTrue(np.array_equal(m,copy))

if __name__=='__main__':unittest.main(verbosity=2)
