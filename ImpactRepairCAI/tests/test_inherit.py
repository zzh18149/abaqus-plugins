from __future__ import division
import os,sys,tempfile,unittest
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cai_config import load
from cai_inherit import derive_geometry,source_outputs,output_text
from cai_source import read_deck
from cai_mesh import footprint


class Inheritance(unittest.TestCase):
    def test_defaults_and_unpatched_ignores_layup(self):
        c=load()
        self.assertEqual((c['side_support_width'],c['compression_time'],c['displacement'],c['cpus']),(5.,.1,2.,16))
        c=load(overrides={'analysis_mode':0,'angles':'unused invalid input'})
        self.assertEqual(c['analysis_mode'],0)

    def test_geometry_center_thickness_and_major_axis(self):
        c=load(overrides={'shape':'ellipse','size_x':10.,'size_y':4.})
        info={'bounds':[[20.,30.,0.],[40.,80.,.401]]}
        spans={'C3D8R':set(((0.,.1),(.1,.2),(.201,.401))), 'COH3D8':set(((.2,.201),))}
        derive_geometry(c,info,spans)
        self.assertAlmostEqual(c['ply_thickness'],.2)
        self.assertAlmostEqual(c['interply_thickness'],.001)
        self.assertAlmostEqual(c['nominal_thickness'],.4)
        self.assertEqual((c['center_x'],c['center_y'],c['rotation'],c['load_axis']),(30.,55.,90.,0))
        points,_=footprint(c)
        self.assertAlmostEqual(max(y for x,y in points)-min(y for x,y in points),10.)
        self.assertAlmostEqual(max(x for x,y in points)-min(x for x,y in points),4.)

    def test_ambiguous_thickness_rejected_only_for_repair(self):
        info={'bounds':[[0.,0.,0.],[20.,10.,.501]]}
        spans={'C3D8R':set(((0.,.2),(.201,.501))), 'COH3D8':set(((.2,.201),))}
        with self.assertRaises(ValueError): derive_geometry(load(),info,spans)
        c=load(overrides={'analysis_mode':0})
        derive_geometry(c,info,spans)
        self.assertAlmostEqual(c['nominal_thickness'],.5)

    def test_rounded_rectangle_boundary_and_positive_cells(self):
        for radius in (0.,1.,5.):
            cfg=load(overrides={'shape':'rectangle','size_x':20.,'size_y':10.,'corner_radius':radius,'mesh_size':.5})
            xy,quads=footprint(cfg)
            for x,y in xy:
                self.assertLessEqual(abs(x),10.+1.e-10); self.assertLessEqual(abs(y),5.+1.e-10)
                if radius:
                    self.assertLessEqual(max(abs(x)-(10-radius),0)**2+max(abs(y)-(5-radius),0)**2,radius**2+1.e-9)
            for q in quads:
                p=[xy[i] for i in q]
                self.assertGreater(sum(p[i][0]*p[(i+1)%4][1]-p[(i+1)%4][0]*p[i][1] for i in range(4)),0.)
        with self.assertRaises(ValueError): load(overrides={'shape':'rectangle','size_x':20.,'size_y':10.,'corner_radius':6.})

    def test_source_output_propagation_mapping_and_cadence(self):
        deck='''*Step, name=Impact
*Dynamic, Explicit
,0.01
*Output, field, number interval=200
*Element Output, directions=YES
E, LE, S, SDV, SDEG, STATUS
*Contact Output
CFORCE
*Output, history, time interval=0.0002, variable=PRESELECT
*Output, history, time interval=0.0002
*Node Output, nset=IMPACTOR.RP
U3, V3
*Energy Output, elset=PLATE-1.ALL
ALLIE
*End Step
*Step, name=Last
*Dynamic, Explicit
,0.02
*End Step
'''
        fd,path=tempfile.mkstemp(suffix='.inp'); os.close(fd)
        try:
            with open(path,'w') as f:f.write(deck)
            info=read_deck(path)
        finally: os.remove(path)
        requests=source_outputs(info['steps'],2)
        txt=output_text({'output_requests':requests},{'elset:PLATE-1.ALL':'CAIR_SOURCE_OUTPUT_0'})
        self.assertIn('number interval=200',txt)
        self.assertIn('time interval=0.0002',txt)
        self.assertIn('CFORCE',txt); self.assertIn('E, LE, S',txt)
        self.assertIn('elset=CAIR_SOURCE_OUTPUT_0',txt)
        self.assertNotIn('IMPACTOR',txt)
        self.assertIn('nset=CAIR_LOADED',txt)
        self.assertIn('variable=PRESELECT',txt)


if __name__=='__main__': unittest.main()
