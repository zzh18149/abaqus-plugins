from __future__ import division
import copy
import os
import sys
import tempfile
import unittest
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cai_config import load,validate,angles
from cai_mesh import footprint,patch_mesh,SurfaceSampler
from cai_source import read_deck,preflight,saved_states,latest_frame_selection,resolve_state,FrameTimes,closest_frame_index
from cai_results import evaluate,_sum_history


class Configuration(unittest.TestCase):
    def test_invalid_angles_and_source_directory(self):
        with self.assertRaises(ValueError): load(overrides={'angles':'0/90'})
        with self.assertRaises(ValueError): load(overrides={'mesh_size':float('nan')})
        with self.assertRaises(ValueError): load(overrides={'output_dir':r'F:\FEM\Impact\temp'})
        with self.assertRaises(ValueError): load(overrides={'job_name':'../bad'})
        with self.assertRaises(ValueError): load(overrides={'unknown_option':1})
        self.assertNotIn('source_equilibrated',load(overrides={'source_equilibrated':False}))

    def test_angles_are_data_not_executable(self):
        with self.assertRaises(ValueError): angles('__import__("os")')
        self.assertEqual(angles('0, 45/-45;90'),[0,45,-45,90])


class AutomaticState(unittest.TestCase):
    def test_binary_selection_matches_linear_including_duplicates(self):
        rows = [0., .03, .03, .09, .2, .2]
        for target in [-.1, 0., .015, .03, .04, .06, .1, .199999, .2, .3]:
            self.assertEqual(closest_frame_index(rows,target),
                             min(range(len(rows)),key=lambda i:abs(rows[i]-target)))

    def test_large_frame_sequence_is_accessed_lazily(self):
        class Frame(object):
            def __init__(self,t): self.frameValue=t
        class Frames(object):
            def __init__(self): self.reads=[]
            def __len__(self): return 4097
            def __getitem__(self,i):
                self.reads.append(i)
                return Frame(i*.001)
        frames=Frames()
        selected=latest_frame_selection(FrameTimes(frames),[(1,3.75)],4.096)
        self.assertEqual(selected['frame_index'],3750)
        self.assertLess(len(frames.reads),20)

    def test_complete_last_frame(self):
        r=latest_frame_selection([0.,.05,.1],[(1,.05),(2,.1)],.1)
        self.assertTrue(r['used_last_frame']); self.assertEqual(r['frame_index'],2)
        self.assertEqual(r['restart_interval'],2)

    def test_aborted_last_frame_falls_back(self):
        r=latest_frame_selection([0.,.004,.005,.0052],[(1,.001),(1,.005)],.01)
        self.assertFalse(r['used_last_frame']); self.assertEqual(r['frame_index'],2)
        self.assertEqual(r['restart_interval'],1)

    def test_missing_state_or_mismatched_frame_rejected(self):
        with self.assertRaises(ValueError): latest_frame_selection([0.,.0052],[],.01)
        with self.assertRaises(ValueError): latest_frame_selection([0.,.0052],[(1,.005)],.01)

    def test_restart_time_is_step_relative_and_overlay_number_preserved(self):
        fd,path=tempfile.mkstemp(suffix='.sta'); os.close(fd)
        try:
            with open(path,'w') as f:
                f.write(' STEP 1 ORIGIN 0.0\nRestart Number 1 at 2.0E-3\n'
                        ' STEP 2 ORIGIN 2.0E-3\nRestart Number 1 at 3.0E-3\n'
                        'Restart Number 1 at 4.0E-3\n')
            records=saved_states(path)
            self.assertAlmostEqual(records[2][-1][1],.002)
            self.assertEqual(records[2][-1][0],1)
        finally: os.remove(path)

    def test_legacy_manual_config_and_new_auto_default(self):
        self.assertEqual(load()['state_selection'],'auto')
        self.assertEqual(load(overrides={'source_step':1})['state_selection'],'manual')
        self.assertEqual(load(overrides={'source_step':1,'state_selection':'auto'})['state_selection'],'auto')

    def test_last_step_used_and_config_resolved(self):
        class Obj(object): pass
        a=Obj(); a.frameValue=0.; b=Obj(); b.frameValue=.002
        step=Obj(); step.frames=[a,b]
        odb=Obj(); odb.steps={'LAST':step}
        info={'deck':{'steps':[{'name':'LAST','duration':.002,'explicit':True}]},
              'saved_states':{1:[(1,.002)]},'warnings':[]}
        cfg=load(); selected,index=resolve_state(cfg,info,odb)
        self.assertEqual(index,1); self.assertEqual(cfg['source_interval'],1)
        self.assertAlmostEqual(cfg['source_time'],.002)


class Meshing(unittest.TestCase):
    def cfg(self,**kwargs):
        settings={'size_x':20.,'size_y':10.,'ply_count':3,'angles':'0/45/90','mesh_size':2.}
        settings.update(kwargs)
        return load(overrides=settings)

    def test_footprints_respect_analytic_contours(self):
        for shape in ('circle','rectangle','ellipse'):
            cfg=self.cfg(shape=shape)
            nodes,quads=footprint(cfg)
            for q in quads:
                p=[nodes[i] for i in q]
                area=sum(p[i][0]*p[(i+1)%4][1]-p[(i+1)%4][0]*p[i][1] for i in range(4))/2
                self.assertGreater(area,0.)
            for x,y in nodes:
                if shape=='rectangle': self.assertTrue(abs(x)<=10 and abs(y)<=5)
                else: self.assertLessEqual((x/10.)**2+(y/(10. if shape=='circle' else 5.))**2,1.+1.e-12)

    def test_bottom_connectivity_and_flat_plies(self):
        for side in ('top','bottom'):
            mesh=patch_mesh(self.cfg(),lambda x,y:-0.5*(1-(x/10.)**2),side)
            self.assertAlmostEqual(mesh['film_min'],0.12)
            self.assertGreater(mesh['film_max'],mesh['film_min'])
            for kind,index,conn in mesh['elements']:
                points=[mesh['nodes'][n-1] for n in conn]
                for a,b in zip(points[:4],points[4:]): self.assertGreater(b[2],a[2])
                if kind=='ply':
                    self.assertAlmostEqual(max(p[2] for p in points[:4]),min(p[2] for p in points[:4]))
                    self.assertAlmostEqual(max(p[2] for p in points[4:]),min(p[2] for p in points[4:]))
            self.assertEqual(sum(k=='interply' for k,i,c in mesh['elements']),2*mesh['footprint_elements'])

    def test_surface_interpolation_and_holes(self):
        sample=SurfaceSampler([((0,0,0),(1,0,1),(1,1,3),(0,1,2))])
        self.assertAlmostEqual(sample(0.25,0.75),1.75)
        with self.assertRaises(ValueError): sample(2,0)
        folded=SurfaceSampler([((0,0,0),(1,0,0),(1,1,0),(0,1,0)),
                               ((0,0,1),(1,0,1),(1,1,1),(0,1,1))])
        with self.assertRaises(ValueError): folded(0.5,0.5)

    def test_subgrid_void_is_not_bonded(self):
        # Intact corners, but the centre contains a hole smaller than one film cell.
        faces=[((-1,-1,0),(1,-1,0),(1,-.1,0),(-1,-.1,0)),
               ((-1,.1,0),(1,.1,0),(1,1,0),(-1,1,0))]
        sample=SurfaceSampler(faces)
        self.assertFalse(sample.covers([(-1,-1),(1,-1),(1,1),(-1,1)]))
        self.assertTrue(sample.covers([(-.5,-.9),(.5,-.9),(.5,-.2),(-.5,-.2)]))

    def test_bridge_removes_film_but_keeps_patch(self):
        faces=[((-10,-10,0),(-1,-10,0),(-1,10,0),(-10,10,0)),
               ((1,-10,0),(10,-10,0),(10,10,0),(1,10,0))]
        sample=SurfaceSampler(faces)
        cfg=self.cfg(shape='rectangle',bond_void_policy='bridge')
        mesh=patch_mesh(cfg,sample,'top')
        self.assertGreater(mesh['bridged_cells'],0)
        self.assertGreater(mesh['bonded_cells'],0)
        self.assertEqual(sum(k=='ply' for k,i,c in mesh['elements']),3*mesh['footprint_elements'])
        self.assertEqual(sum(k=='adhesive' for k,i,c in mesh['elements']),mesh['bonded_cells'])
        used=set(i for k,j,c in mesh['elements'] for i in c)
        self.assertEqual(used,set(range(1,len(mesh['nodes'])+1)))


class Strength(unittest.TestCase):
    def test_history_sum_and_empty_step(self):
        class Item(object): pass
        step=Item(); step.historyRegions={}
        for label in (1,2):
            region=Item(); f=Item(); u=Item()
            f.data=((0.,-label*10.),(1.,-label*20.))
            u.data=((0.,0.),(1.,-0.1*label))
            region.historyOutputs={'RF1':f,'U1':u}
            step.historyRegions['Node PLATE-1.%d'%label]=region
        t,f,u=_sum_history(step,'PLATE-1',set((1,2)),1)
        self.assertEqual(f,[-30.,-60.]); self.assertAlmostEqual(u[-1],-.15)
        region.historyOutputs['RF1'].data=None
        with self.assertRaises(ValueError): _sum_history(step,'PLATE-1',set((1,2)),1)

    def run_curve(self,forces,**changes):
        cfg=load(overrides={'source_equilibrated':True,'post_peak_points':3})
        cfg.update(changes)
        rows=[dict(time_s=i,displacement_mm=i*.01,force_N=f,
                   loaded_RF_N=-f,fixed_RF_N=f,balance_error=0.) for i,f in enumerate(forces)]
        e={'ALLKE':[(0,1),(len(rows),1)],'ALLIE':[(0,100),(len(rows),100)],'ALLAE':[(0,1),(len(rows),1)]}
        return evaluate(rows,e,cfg,True,0.01)

    def test_nominal_area_excludes_patch(self):
        r=self.run_curve([0,100,200,300,400,300,290,280,200])
        self.assertTrue(r['valid_strength'])
        self.assertAlmostEqual(r['cai_strength_MPa'],400/460.)

    def test_increasing_curve_is_not_a_strength(self):
        r=self.run_curve([0,100,200,300,400])
        self.assertFalse(r['valid_strength']); self.assertIsNone(r['cai_strength_MPa'])
        self.assertGreater(r['observed_nominal_peak_MPa'],0)

    def test_impact_readiness_and_energy_gate(self):
        f=[0,100,200,300,400,300,290,280,200]
        self.assertTrue(self.run_curve(f,source_equilibrated=False)['valid_strength'])
        self.assertFalse(self.run_curve(f,ke_ie_limit=.001)['valid_strength'])

    def test_tension_not_reported_as_compression(self):
        r=self.run_curve([0,-100,-200,-150,-100,-50])
        self.assertFalse(r['valid_strength']); self.assertEqual(r['peak_force_N'],0)


if __name__=='__main__': unittest.main()
