# -*- coding: utf-8 -*-
"""Native Abaqus/CAE 2024 backend. Import state through an InitialState field."""
from __future__ import division, print_function
import copy
import hashlib
import json
import os
import shutil
import time
import re

from cai_config import load, dump, angles, api_path
from cai_inherit import DERIVED_KEYS,output_text
from cai_mesh import SurfaceSampler, patch_mesh, footprint
from cai_source import preflight, read_state, inspect_source, log, REQUIRED_FILES


def _set_nodes(part, name, labels):
    if not labels:
        raise ValueError('Empty boundary node set: '+name)
    return part.Set(name=name, nodes=part.nodes.sequenceFromLabels(tuple(labels)))


def _surface(part, name, groups):
    kwargs = {}
    for side, labels in groups.items():
        if labels:
            kwargs['face%dElements' % side] = part.elements.sequenceFromLabels(tuple(labels))
    if not kwargs:
        raise ValueError('Empty surface: '+name)
    return part.Surface(name=name, **kwargs)


def _materials(model, cfg, info):
    from abaqusConstants import TRACTION, ENERGY, BK, TRACTION_SEPARATION, SPECIFY, GEOMETRY
    source = info['deck']['materials'][cfg['base_material'].upper()]
    mat = model.Material(name='CAIR_PLY')
    mat.Density(table=((source['density'],),))
    mat.Depvar(n=source['depvar'], deleteVar=source['delete'])
    mat.UserMaterial(mechanicalConstants=tuple(source['constants']))
    model.HomogeneousSolidSection(name='CAIR_PLY', material='CAIR_PLY', thickness=None)
    inter = info['deck']['materials'][cfg['interply_material'].upper()]
    for name, elastic, strength, energy, density, power, geometry in (
        ('CAIR_INTERPLY', inter['elastic'], inter['strengths'], inter['energies'],
         inter['density'], float(inter['evolution']['power']), False),
        ('CAIR_FILM', (cfg['adhesive_E'],cfg['adhesive_G'],cfg['adhesive_G']),
         (cfg['adhesive_tn'],cfg['adhesive_ts'],cfg['adhesive_ts']),
         (cfg['adhesive_GIc'],cfg['adhesive_GIIc'],cfg['adhesive_GIIc']),
         cfg['adhesive_density'], cfg['adhesive_BK'], True)):
        mat = model.Material(name=name)
        mat.Density(table=((density,),))
        mat.Elastic(type=TRACTION, table=(tuple(elastic),))
        mat.QuadsDamageInitiation(table=(tuple(strength),))
        mat.quadsDamageInitiation.DamageEvolution(type=ENERGY,
            mixedModeBehavior=BK, power=power, table=(tuple(energy),))
        if geometry:
            model.CohesiveSection(name=name, material=name, response=TRACTION_SEPARATION,
                                 initialThicknessType=GEOMETRY)
        else:
            model.CohesiveSection(name=name, material=name, response=TRACTION_SEPARATION,
                                 initialThicknessType=SPECIFY, initialThickness=1.0)


def _patch(model, cfg, side, sampler):
    from abaqusConstants import (THREE_D, DEFORMABLE_BODY, C3D8R, COH3D8,
                                EXPLICIT, SYSTEM, AXIS_3, ROTATION_ANGLE, STACK_3)
    import mesh
    data = patch_mesh(cfg, sampler, side)
    groups = {}
    internal = {1: [], 2: []}
    element_blocks = {'C3D8R': ([], []), 'COH3D8': ([], [])}
    for label, (kind, index, conn) in enumerate(data['elements'], 1):
        labels, conns = element_blocks['C3D8R' if kind == 'ply' else 'COH3D8']
        labels.append(label); conns.append(conn)
        groups.setdefault((kind,index),[]).append(label)
        if kind == 'ply':
            internal[1].append(label); internal[2].append(label)
    # One native mesh import instead of thousands of per-node/element CAE calls.
    # Keep original labels/connectivity so surfaces, sections and bottom stacking
    # retain exactly the same meaning even when the native arrays are reordered.
    part = model.PartFromNodesAndElements(name='CAIR_'+side.upper(),
        dimensionality=THREE_D, type=DEFORMABLE_BODY,
        nodes=(tuple(range(1,len(data['nodes'])+1)), tuple(data['nodes'])),
        elements=tuple((kind,tuple(element_blocks[kind][0]),tuple(element_blocks[kind][1]))
                       for kind in ('C3D8R','COH3D8') if element_blocks[kind][0]))
    for (kind,index), labels in groups.items():
        region = part.Set(name='%s_%03d' % (kind.upper(),index+1),
                          elements=part.elements.sequenceFromLabels(tuple(labels)))
        etype = C3D8R if kind == 'ply' else COH3D8
        part.setElementType(regions=(region.elements,), elemTypes=(mesh.ElemType(elemCode=etype,elemLibrary=EXPLICIT),))
        section = {'ply':'CAIR_PLY','adhesive':'CAIR_FILM','interply':'CAIR_INTERPLY'}[kind]
        part.SectionAssignment(region=region, sectionName=section)
        if kind == 'ply':
            # Angles are global XY; list order runs from the plate outward on both sides.
            part.MaterialOrientation(region=region, orientationType=SYSTEM,
                axis=AXIS_3, localCsys=None, additionalRotationType=ROTATION_ANGLE,
                angle=angles(cfg['angles'])[index], stackDirection=STACK_3)
    film = groups[('adhesive',0)]
    _surface(part,'BOND_TO_BASE',{1 if side=='top' else 2:film})
    _surface(part,'PLY_FACES',internal)
    part.Set(name='ALL_NODES',nodes=part.nodes)
    return part, {k:data[k] for k in ('side','plane','film_min','film_max','footprint_elements','bonded_cells','bridged_cells')}


def _base_sets(part, reference, bounds, cfg):
    axis = cfg['load_axis']; transverse = 1-axis
    lo, hi = bounds
    tol = max(1.e-5,(hi[axis]-lo[axis])*1.e-6)
    if cfg['end_support_width']*2 >= hi[axis]-lo[axis]:
        raise ValueError('End support bands cover the entire plate')
    if cfg['side_support_width']*2 >= hi[transverse]-lo[transverse]:
        raise ValueError('Side support bands cover the entire plate')
    loaded=[]; fixed=[]; supports=[]
    for label, xyz in reference.items():
        if abs(xyz[axis]-lo[axis])<tol: fixed.append(label)
        if abs(xyz[axis]-hi[axis])<tol: loaded.append(label)
        at_edge = (xyz[axis] <= lo[axis]+cfg['end_support_width']+tol or
                   xyz[axis] >= hi[axis]-cfg['end_support_width']-tol or
                   xyz[transverse] <= lo[transverse]+cfg['side_support_width']+tol or
                   xyz[transverse] >= hi[transverse]-cfg['side_support_width']-tol)
        # Equivalent edge supports; see README for departure from a physical fixture.
        if at_edge: supports.append(label)
    anchor = min(fixed, key=lambda n: abs(reference[n][transverse]-(lo[transverse]+hi[transverse])/2.) + abs(reference[n][2]-(lo[2]+hi[2])/2.))
    _set_nodes(part,'CAIR_FIXED',fixed); _set_nodes(part,'CAIR_LOADED',loaded)
    _set_nodes(part,'CAIR_SUPPORT',supports); _set_nodes(part,'CAIR_ANCHOR',[anchor])
    part.Set(name='CAIR_ALL',nodes=part.nodes)
    return {'CAIR_FIXED':fixed,'CAIR_LOADED':loaded,'CAIR_SUPPORT':supports,
            'CAIR_ANCHOR':[anchor],'CAIR_ALL':list(reference)}


def _steps(model, base, patch_instances, cfg, base_sets=None, base_surfaces=None):
    import step
    base_sets=base_sets or base.sets
    base_surfaces=base_surfaces or base.surfaces
    from abaqusConstants import (ON, OFF, UNSET, STEP, GLOBAL, SELF, HARD,
                                PENALTY, ISOTROPIC, DEFAULT, FRACTION)
    model.ExplicitDynamicsStep(name='CAIR_SETTLE', previous='Initial',
                              timePeriod=cfg['relax_time'], nlgeom=ON)
    model.ExplicitDynamicsStep(name='CAIR_COMPRESSION', previous='CAIR_SETTLE',
                              timePeriod=cfg['compression_time'], nlgeom=ON)
    axis = cfg['load_axis']+1; transverse = 2 if axis==1 else 1
    model.DisplacementBC(name='CAIR_FIXED',createStepName='Initial',
                         region=base_sets['CAIR_FIXED'], **{'u%d'%axis:0.0})
    model.DisplacementBC(name='CAIR_SUPPORT',createStepName='Initial',
                         region=base_sets['CAIR_SUPPORT'],u3=0.0)
    model.DisplacementBC(name='CAIR_ANCHOR',createStepName='Initial',
                         region=base_sets['CAIR_ANCHOR'],**{'u%d'%transverse:0.0})
    model.DisplacementBC(name='CAIR_LOAD',createStepName='Initial',
                         region=base_sets['CAIR_LOADED'],**{'u%d'%axis:0.0})
    model.SmoothStepAmplitude(name='CAIR_RAMP',timeSpan=STEP,
                             data=((0.,0.),(cfg['compression_time'],1.)))
    model.boundaryConditions['CAIR_LOAD'].setValuesInStep(stepName='CAIR_COMPRESSION',
        amplitude='CAIR_RAMP', **{'u%d'%axis:-cfg['displacement']})
    # A repaired specimen is initially at rest, unlike the impact simulation.
    # The 2022 CAE Velocity object rejects exactly zero velocity. The solver
    # accepts it; build() inserts this one documented keyword after CAE setup.
    prop = model.ContactProperty('CAIR_CONTACT')
    prop.NormalBehavior(pressureOverclosure=HARD, allowSeparation=ON)
    prop.TangentialBehavior(formulation=PENALTY,directionality=ISOTROPIC,
        table=((0.3,),),maximumElasticSlip=FRACTION,fraction=0.005)
    # Define imported-model general contact as step data. Model-level contact
    # triggered an Explicit/2022 internal error at the next step in our smoke case.
    contact=model.ContactExp(name='CAIR_CONTACT',createStepName='CAIR_SETTLE')
    contact.contactPropertyAssignments.appendInStep(stepName='CAIR_SETTLE',
                                                    assignments=((GLOBAL,SELF,'CAIR_CONTACT'),))
    pairs=[(ins.surfaces['PLY_FACES'],ins.surfaces['PLY_FACES']) for ins in patch_instances]
    # Source inner ply faces are explicitly included so delaminated plies cannot interpenetrate.
    if 'CAIR_PLY_FACES' in base_surfaces:
        pairs.append((base_surfaces['CAIR_PLY_FACES'],base_surfaces['CAIR_PLY_FACES']))
    contact.includedPairs.setValuesInStep(stepName='CAIR_SETTLE',useAllstar=OFF,
                                        addPairs=((GLOBAL,SELF),)+tuple(pairs))
    for name in list(model.fieldOutputRequests.keys()): del model.fieldOutputRequests[name]
    for name in list(model.historyOutputRequests.keys()): del model.historyOutputRequests[name]
    model.FieldOutputRequest(name='CAIR_FIELDS',createStepName='CAIR_SETTLE',
        variables=('U','RF','S','LE','SDV','SDEG','STATUS'),numIntervals=cfg['field_intervals'])
    model.HistoryOutputRequest(name='CAIR_ENERGY',createStepName='CAIR_SETTLE',
        variables=('ALLKE','ALLIE','ALLAE','ALLVD','ALLWK','ETOTAL'),
        numIntervals=cfg['history_intervals'])
    for name,region in (('LOAD',base_sets['CAIR_LOADED']),('FIXED',base_sets['CAIR_FIXED'])):
        model.HistoryOutputRequest(name='CAIR_'+name,createStepName='CAIR_SETTLE',
            variables=('RF%d'%axis,'U%d'%axis),region=region,
            numIntervals=cfg['history_intervals'])
    for step_name in ('CAIR_SETTLE','CAIR_COMPRESSION'):
        model.steps[step_name].Restart(numberIntervals=1,timeMarks=ON)


def build(cfg):
    import caeModules
    from abaqus import mdb, session
    from abaqusConstants import (ON, OFF, DEFORMED, DEFAULT, COMPUTED, EXPLICIT,
                                DOUBLE_PLUS_PACK, DOMAIN, ODB, PERCENTAGE)
    from odbAccess import openOdb
    started=time.time(); timings={}
    def timed(stage):
        now=time.time()
        timings[stage]=now-checkpoint_box[0]
        checkpoint_box[0]=now
        log('Timing %s: %.2f s'%(stage,timings[stage]))
    checkpoint_box=[started]
    requested=copy.deepcopy(cfg)
    out=cfg['output_dir']; name=cfg['job_name']
    if not os.path.isdir(out): os.makedirs(out)
    for ext in ('.inp','.odb','.cae','.lck'):
        if os.path.exists(os.path.join(out,name+ext)):
            raise ValueError('Output already exists. Choose a new job name/directory: '+name+ext)
    if name in mdb.models or name in mdb.jobs:
        raise ValueError('Model/job name already exists in CAE: '+name)
    # Model is retained on any error for inspection; never remove an existing user's model.
    model=mdb.Model(name=name)
    log('Importing original plate mesh for native InitialState field.')
    imported=[]
    def import_part(odb,frame_index):
        imported.append(model.PartFromOdb(name='CAIR_BASE',odb=odb,instance=cfg['source_instance'],
            shape=DEFORMED,step=cfg['source_step']-1,frame=frame_index))
    info,reference,current,faces,surfaces=read_state(cfg,import_part)
    timed('source_read_and_plate_import')
    part=imported[0]
    import mesh
    from abaqusConstants import C3D8R,COH3D8
    for kind,etype in (('C3D8R',C3D8R),('COH3D8',COH3D8)):
        labels=surfaces['types'].get(kind,[])
        if labels:
            part.setElementType(regions=(part.elements.sequenceFromLabels(tuple(labels)),),
                                elemTypes=(mesh.ElemType(elemCode=etype,elemLibrary=EXPLICIT),))
    if cfg['analysis_mode']==1:
        axis=cfg['load_axis']; transverse=1-axis
        lo,hi=info['bounds']
        xy,_=footprint(cfg)
        for point in xy:
            if not (lo[axis]+cfg['end_support_width']<point[axis]<hi[axis]-cfg['end_support_width']
                and lo[transverse]+cfg['side_support_width']<point[transverse]<hi[transverse]-cfg['side_support_width']):
                raise ValueError('Patch overlaps an equivalent fixture support band or plate edge')
    node_groups=_base_sets(part,reference,info['bounds'],cfg)
    for side in ('top','bottom'):
        if surfaces[side]: _surface(part,'CAIR_'+side.upper(),surfaces[side])
    _surface(part,'CAIR_PLY_FACES',surfaces['inner'])
    assembly=model.rootAssembly
    base=assembly.Instance(name=cfg['source_instance'],part=part,dependent=ON)
    # InitialState suppresses the source *Part definition. New part-level
    # sets/surfaces would therefore disappear from the solver input. Define
    # all new boundary and contact regions at assembly level instead.
    base_sets={}
    for key,labels in node_groups.items():
        base_sets[key]=assembly.Set(name=key,nodes=base.nodes.sequenceFromLabels(tuple(labels)))
    base_surfaces={}
    for key,groups in (('CAIR_TOP',surfaces['top']),('CAIR_BOTTOM',surfaces['bottom']),
                       ('CAIR_PLY_FACES',surfaces['inner'])):
        if not groups: continue
        args=dict(('face%dElements'%side,base.elements.sequenceFromLabels(tuple(labels)))
                  for side,labels in groups.items() if labels)
        base_surfaces[key]=assembly.Surface(name=key,**args)
    selection={}
    if cfg['state_selection']=='manual':
        selection=dict(endStep=cfg['source_step'],endIncrement=cfg['source_interval'])
    model.InitialState(name='CAIR_IMPACT_STATE',createStepName='Initial',instances=(base,),
        fileName=api_path(info['source_base']),updateReferenceConfiguration=ON,**selection)
    if cfg['analysis_mode']==1: _materials(model,cfg,info)
    timed('base_regions_and_materials')
    patches=[]; details=[]
    sides=() if cfg['analysis_mode']==0 else (('top','bottom') if cfg['sides']=='both' else (cfg['sides'],))
    for side in sides:
        log('Creating planar '+side+' patch and variable-thickness cohesive film.')
        sampler=SurfaceSampler(faces[side],cfg['mesh_size'])
        p,detail=_patch(model,cfg,side,sampler)
        ins=assembly.Instance(name=p.name+'-1',part=p,dependent=ON)
        model.Tie(name='CAIR_BOND_'+side,main=base_surfaces['CAIR_'+side.upper()],
            secondary=ins.surfaces['BOND_TO_BASE'],positionToleranceMethod=COMPUTED,
            adjust=OFF,tieRotations=OFF,thickness=ON)
        patches.append(ins); details.append(detail)
        timed('patch_'+side)
    output_regions={}
    for index,(key,record) in enumerate(sorted(info['output_regions'].items())):
        region_name='CAIR_SOURCE_OUTPUT_%d'%index
        if record['kind']=='nset': assembly.Set(name=region_name,nodes=base.nodes.sequenceFromLabels(tuple(record['labels'])))
        else: assembly.Set(name=region_name,elements=base.elements.sequenceFromLabels(tuple(record['labels'])))
        output_regions[key]=region_name
    _steps(model,base,patches,cfg,base_sets,base_surfaces)
    timed('steps_contact_and_output_regions')
    _stage_source(info['source_base'],out)
    timed('source_snapshot_copy')
    _zero_velocity_keyword(model,'CAIR_ALL','CAIR_IMPACT')
    _inherit_output_keywords(model,info,output_regions)
    job=mdb.Job(name=name,model=name,userSubroutine=api_path(cfg['vumat']),
        numCpus=cfg['cpus'],numDomains=cfg['cpus'],memory=60,memoryUnits=PERCENTAGE,
        explicitPrecision=DOUBLE_PLUS_PACK,parallelizationMethodExplicit=DOMAIN,resultsFormat=ODB)
    previous=os.getcwd()
    try:
        os.chdir(out)
        job.writeInput(consistencyChecking=ON)
        mdb.saveAs(pathName=api_path(os.path.join(out,name+'.cae')))
    finally:
        os.chdir(previous)
    timed('keywords_input_and_cae_save')
    timings['total_before_report']=time.time()-started
    metadata=dict(config=cfg,requested_config=requested,source=info,patches=details,
                  source_vumat_sha256=_hash(cfg['vumat']),built_at=time.strftime('%Y-%m-%d %H:%M:%S'),
                  build_timings_seconds=timings)
    dump(os.path.join(out,name+'_model.json'),metadata)
    dump(os.path.join(out,name+'_config.json'),cfg)
    try:
        session.viewports[session.currentViewportName].setValues(displayedObject=assembly)
        session.viewports[session.currentViewportName].view.fitView()
    except Exception:
        pass
    log('Created model, native InitialState, CAE, INP and model report in '+out)
    return metadata


def _inherit_output_keywords(model,info,regions):
    text=output_text(info,regions)
    first=True
    for i,block in enumerate(model.keywordBlock.sieBlocks):
        key=block.strip().split(',')[0].split('\n')[0].lower()
        if key=='*step': first=True
        if key in ('*output','*node output','*element output','*contact output','*energy output'):
            model.keywordBlock.replace(i,text if first else '** CAIR: inherited source output above')
            first=False


def _zero_velocity_keyword(model,node_set,source_base=None):
    model.keywordBlock.synchVersions(storeNodesAndElements=False)
    blocks=model.keywordBlock.sieBlocks
    if source_base is not None:
        # CAE/2022 requires the previous analysis files in the run directory.
        path=source_base.replace('\\','/')
        if '"' in path: raise ValueError('Source path cannot contain a quote')
        for i,block in enumerate(blocks):
            if block.lower().startswith('*instance') and 'library=' in block.lower():
                replacement=re.sub(r'library=[^,\n]+',lambda m:'library='+path,block,flags=re.I)
                model.keywordBlock.replace(i,api_path(replacement))
    index=next(i for i,b in enumerate(blocks) if b.strip().lower().startswith('*step'))
    lines=['** CAIR: start repaired specimen at rest', '*Initial Conditions, type=VELOCITY']
    lines.extend('%s, %d, 0.' % (node_set,i) for i in (1,2,3))
    model.keywordBlock.insert(index-1,'\n'.join(lines))


def _stage_source(source_base,out):
    """Independent copies: no hard links, no writes to the original job."""
    required=sum(os.path.getsize(source_base+ext) for ext in REQUIRED_FILES
                 if not os.path.exists(os.path.join(out,'CAIR_IMPACT'+ext)))
    if os.name=='nt':
        import ctypes
        free=ctypes.c_ulonglong(0)
        folder=os.fsdecode(out)
        if ctypes.windll.kernel32.GetDiskFreeSpaceExW(folder,ctypes.byref(free),None,None):
            if free.value<required+1024**3:
                raise ValueError('Insufficient free disk space for source snapshots plus 1 GB working reserve')
    for ext in REQUIRED_FILES:
        source=source_base+ext
        target=os.path.join(out,'CAIR_IMPACT'+ext)
        before=os.stat(source)
        if os.path.exists(target):
            if os.path.getsize(target)!=before.st_size or abs(os.path.getmtime(target)-before.st_mtime)>1.:
                raise ValueError('A different source snapshot exists in '+out+'; use a new output directory')
            continue
        temporary=target+'.copying'
        if os.path.exists(temporary):
            raise ValueError('An interrupted source copy exists; use a new output directory: '+temporary)
        log('Preparing source snapshot '+ext+' (%.1f MB)'%(before.st_size/1048576.))
        copy_started=time.time()
        with open(source,'rb') as original:
            with open(temporary,'wb') as destination:
                shutil.copyfileobj(original,destination,16*1024*1024)
        after=os.stat(source)
        if before.st_size!=after.st_size or before.st_mtime!=after.st_mtime or os.path.isfile(source_base+'.lck'):
            raise ValueError('Source changed while copying; use a stable source and a new output directory')
        shutil.copystat(source,temporary)
        os.rename(temporary,target)
        elapsed=max(time.time()-copy_started,1.e-6)
        log('Snapshot %s ready: %.2f s, %.1f MB/s'%(ext,elapsed,before.st_size/1048576./elapsed))


def _hash(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def solve(cfg,datacheck=False):
    from abaqus import mdb
    from abaqusConstants import ON, DOUBLE_PLUS_PACK, DOMAIN, PERCENTAGE
    name=cfg['job_name']; out=cfg['output_dir']
    inp=os.path.join(out,name+'.inp')
    if not os.path.isfile(inp): raise ValueError('Build the model before submitting')
    with open(os.path.join(out,name+'_model.json'),'rb') as f:
        metadata=json.loads(f.read().decode('utf-8'))
    stored=load(overrides=metadata.get('requested_config',metadata['config']))
    ignored=DERIVED_KEYS|{'cpus'}
    if cfg['state_selection']==stored['state_selection']=='auto':
        ignored.update(('source_step','source_interval','source_time'))
    changed=[k for k in cfg if k not in ignored and cfg[k]!=stored[k]]
    if changed:
        raise ValueError('Settings changed since build; reload saved config or build a new job: '+', '.join(changed))
    if _hash(cfg['vumat'])!=metadata['source_vumat_sha256']:
        raise ValueError('VUMAT has changed since model generation')
    if any(os.path.isfile(os.path.join(out,n+'.lck')) for n in (name,name+'_check')):
        raise ValueError('Job or input check is already running')
    if not datacheck and os.path.isfile(os.path.join(out,name+'.odb')):
        # A successful data-check can leave an ODB; keep that diagnostic separately.
        sta=os.path.join(out,name+'.sta')
        status=open(sta).read() if os.path.isfile(sta) else ''
        if 'THE ANALYSIS HAS COMPLETED SUCCESSFULLY' in status or 'INCREMENT' in status:
            raise ValueError('Existing analysis results are protected; use a new job name')
    previous=os.getcwd()
    try:
        os.chdir(out)
        # Use the saved input as the single source of truth for the submitted job.
        jobname=name+('_check' if datacheck else '')
        if jobname in mdb.jobs:
            old=mdb.jobs[jobname]
            if getattr(old,'model',None)!=name and getattr(old,'inputFileName',None)!=inp:
                raise ValueError('An unrelated CAE job already uses the name '+jobname)
            del mdb.jobs[jobname]
        job=mdb.JobFromInputFile(name=jobname,inputFileName=api_path(inp),userSubroutine=api_path(cfg['vumat']),
            numCpus=cfg['cpus'],numDomains=cfg['cpus'],memory=60,memoryUnits=PERCENTAGE,
            explicitPrecision=DOUBLE_PLUS_PACK,parallelizationMethodExplicit=DOMAIN)
        if datacheck: job.submit(consistencyChecking=ON,datacheckJob=ON)
        else: job.submit(consistencyChecking=ON)
    finally:
        os.chdir(previous)
    log('Submitted '+jobname+'. Use Job Monitor; extract results after completion.')
    return job


def execute(config_path='',action='inspect',overrides_json='{}'):
    cfg=load(config_path or None,json.loads(overrides_json))
    if action=='inspect':
        result=inspect_source(cfg)
        log(json.dumps(result,indent=2))
        return result
    if action=='build': return build(cfg)
    if action=='datacheck': return solve(cfg,True)
    if action=='submit': return solve(cfg,False)
    if action=='results':
        from cai_results import extract
        return extract(cfg)
    raise ValueError('Unknown action: '+action)
