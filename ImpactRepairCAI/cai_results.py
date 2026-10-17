# -*- coding: utf-8 -*-
"""CAI force extraction and auditable qualification; Python 3.10."""
from __future__ import division, print_function
import bisect
import csv
import json
import math
import os
import re
from cai_config import dump,api_path,load
from cai_source import log


def interpolate(history, t):
    if not history: return None
    times = [row[0] for row in history]
    i = bisect.bisect_left(times,t)
    if i == 0: return history[0][1]
    if i == len(history): return history[-1][1]
    a,b = history[i-1],history[i]
    return a[1]+(b[1]-a[1])*(t-a[0])/(b[0]-a[0])


def evaluate(rows, energies, cfg, completed, settle_ratio=None):
    if len(rows)<3: raise ValueError('Too few compression samples to evaluate')
    if any(not all(math.isfinite(float(v)) if hasattr(math,'isfinite') else
                   not(math.isnan(float(v)) or math.isinf(float(v))) for v in row.values()) for row in rows):
        raise ValueError('Curve contains non-finite values')
    index=max(range(len(rows)),key=lambda i:rows[i]['force_N'])
    peak=rows[index]; maximum=peak['force_N']
    area=cfg['nominal_width']*cfg['nominal_thickness']
    threshold=maximum*(1-cfg['peak_drop'])
    run=0; demonstrated=False
    for row in rows[index+1:]:
        run=run+1 if row['force_N']<threshold else 0
        if run>=cfg['post_peak_points']: demonstrated=True
    warnings=[]
    if not completed: warnings.append('CAI job has not completed successfully.')
    if maximum<=0: warnings.append('No positive compressive force was recorded; check the load direction.')
    if not demonstrated: warnings.append('A sustained post-peak load drop has not been demonstrated.')
    if index>=len(rows)-cfg['post_peak_points']: warnings.append('Peak is too close to the end of the record.')
    ke_ratios=[]; ae_ratios=[]; balance=[]
    # Evaluate a load window, not a single favourable frame at the peak.
    for row in rows:
        if row['force_N']<0.8*maximum or maximum<=0: continue
        ie=interpolate(energies.get('ALLIE',[]),row['time_s'])
        ke=interpolate(energies.get('ALLKE',[]),row['time_s'])
        ae=interpolate(energies.get('ALLAE',[]),row['time_s'])
        if ie is not None and abs(ie)>1.e-12:
            if ke is not None: ke_ratios.append(abs(ke/ie))
            if ae is not None: ae_ratios.append(abs(ae/ie))
        balance.append(row['balance_error'])
    kr=max(ke_ratios) if ke_ratios else None
    ar=max(ae_ratios) if ae_ratios else None
    fr=max(balance) if balance else None
    if kr is None or kr>cfg['ke_ie_limit']: warnings.append('Kinetic/internal energy check failed or is unavailable.')
    if ar is None or ar>cfg['ae_ie_limit']: warnings.append('Artificial/internal energy check failed or is unavailable.')
    if fr is None or fr>cfg['force_balance_limit']: warnings.append('Loaded/fixed end force balance check failed.')
    if settle_ratio is None or settle_ratio>cfg['ke_ie_limit']: warnings.append('Pre-compression settling check failed or is unavailable.')
    valid=not warnings
    return dict(valid_strength=valid,cai_strength_MPa=(maximum/area if valid else None),
        observed_nominal_peak_MPa=maximum/area,peak_force_N=maximum,
        peak_displacement_mm=peak['displacement_mm'],peak_time_s=peak['time_s'],
        reference_area_mm2=area,area_definition='original plate nominal width * nominal thickness; excludes patch',
        post_peak_demonstrated=demonstrated,max_KE_IE_near_peak=kr,max_AE_IE_near_peak=ar,
        max_force_balance_error_near_peak=fr,settle_KE_IE=settle_ratio,
        job_completed=completed,warnings=warnings,material_status=cfg['material_status'],
        fixture_status=cfg['fixture_status'],engineering_validated=False)


def _labels(region):
    result=set()
    for item in region.nodes:
        if hasattr(item,'label'): result.add(item.label)
        else: result.update(n.label for n in item)
    return result


def _sum_history(step,instance,labels,axis):
    grid=None; forces=None; displacements=None; found=set()
    prefix='Node '+instance.upper()+'.'
    for name,region in step.historyRegions.items():
        if not name.upper().startswith(prefix.upper()): continue
        try: label=int(name.rsplit('.',1)[1])
        except ValueError: continue
        if label not in labels: continue
        f=region.historyOutputs['RF%d'%axis] if 'RF%d'%axis in region.historyOutputs else None
        u=region.historyOutputs['U%d'%axis] if 'U%d'%axis in region.historyOutputs else None
        if f is None or u is None: raise ValueError('End node history is incomplete: '+name)
        fd=list(f.data or ()); ud=list(u.data or ())
        if not fd or not ud:
            raise ValueError('End node history has no samples: '+name)
        times=[r[0] for r in fd]
        if grid is None:
            grid=times; forces=[0.]*len(grid); displacements=[0.]*len(grid)
        if len(times)!=len(grid) or any(abs(a-b)>1.e-10 for a,b in zip(times,grid)):
            raise ValueError('End reaction histories have inconsistent time grids')
        if len(ud)!=len(grid) or any(abs(a-b[0])>1.e-10 for a,b in zip(grid,ud)):
            raise ValueError('End displacement histories have inconsistent time grids')
        for i,(frow,urow) in enumerate(zip(fd,ud)):
            forces[i]+=frow[1]; displacements[i]+=urow[1]
        found.add(label)
    if found!=labels:
        raise ValueError('Missing history for %d of %d end nodes' % (len(labels-found),len(labels)))
    return grid,forces,[v/len(labels) for v in displacements]


def _energy(step):
    for name,region in step.historyRegions.items():
        if name.lower().startswith('assembly') and 'ALLIE' in region.historyOutputs:
            return dict((key,list(val.data)) for key,val in region.historyOutputs.items()
                        if key in ('ALLKE','ALLIE','ALLAE','ALLVD','ALLWK','ETOTAL'))
    return {}


def extract(cfg):
    from odbAccess import openOdb
    name=cfg['job_name']; base=os.path.join(cfg['output_dir'],name)
    if os.path.isfile(base+'.lck'): raise ValueError('CAI is still running; wait before extracting results')
    sta=base+'.sta'
    completed=False
    if os.path.isfile(sta):
        with open(sta) as f: completed='THE ANALYSIS HAS COMPLETED SUCCESSFULLY' in f.read()
    if not completed:
        raise ValueError('CAI has not completed successfully. Check Job Monitor and .log/.sta/.msg before extracting strength.')
    model_path=base+'_model.json'
    if not os.path.isfile(model_path): raise ValueError('Model metadata is missing')
    with open(model_path,'rb') as f: metadata=json.loads(f.read().decode('utf-8'))
    # Use the actual built settings, not later GUI edits (particularly width/thickness).
    cfg=load(overrides=metadata['config'])
    odb=openOdb(path=api_path(base+'.odb'),readOnly=True)
    try:
        step=odb.steps['CAIR_COMPRESSION']
        ins=odb.rootAssembly.instances[cfg['source_instance'].upper()]
        loaded=_labels(odb.rootAssembly.nodeSets['CAIR_LOADED'])
        fixed=_labels(odb.rootAssembly.nodeSets['CAIR_FIXED'])
        lt,lf,lu=_sum_history(step,ins.name,loaded,cfg['load_axis']+1)
        ft,ff,fu=_sum_history(step,ins.name,fixed,cfg['load_axis']+1)
        if len(lt)!=len(ft) or any(abs(a-b)>1.e-10 for a,b in zip(lt,ft)):
            raise ValueError('The two end histories have inconsistent time grids')
        rows=[]
        for t,a,b,u,v in zip(lt,lf,ff,lu,fu):
            rows.append(dict(time_s=t,displacement_mm=-(u-v),force_N=-a,
                             loaded_RF_N=a,fixed_RF_N=b,
                             balance_error=abs(a+b)/max(abs(a),abs(b),1.e-12)))
        energy=_energy(step)
        se=_energy(odb.steps['CAIR_SETTLE'])
        settle_ratio=None
        if se.get('ALLIE') and se.get('ALLKE'):
            # Worst ratio over the final 10% of the settling step.
            last=se['ALLIE'][-1][0]; ratios=[]
            for t,ie in se['ALLIE']:
                if t>=0.9*last and abs(ie)>1.e-12:
                    ratios.append(abs(interpolate(se['ALLKE'],t)/ie))
            if ratios: settle_ratio=max(ratios)
    finally:
        odb.close()
    result=evaluate(rows,energy,cfg,completed,settle_ratio)
    result.update(odb=base+'.odb',source=metadata['source'],config=cfg,patches=metadata['patches'])
    dump(base+'_result.json',result)
    handle=open(base+'_curve.csv','w',encoding='utf-8',newline='')
    try:
        keys=('time_s','displacement_mm','force_N','loaded_RF_N','fixed_RF_N','balance_error')
        writer=csv.DictWriter(handle,fieldnames=keys); writer.writeheader(); writer.writerows(rows)
    finally: handle.close()
    lines=['Impact Repair CAI - numerical result',
        'Peak compressive load: %.8g N'%result['peak_force_N'],
        'Observed nominal peak: %.8g MPa'%result['observed_nominal_peak_MPa'],
        'Qualified CAI strength: '+str(result['cai_strength_MPa'])+' MPa',
        'Numerical qualification passed: '+str(result['valid_strength']),
        'Material status: '+cfg['material_status'],
        'Fixture: '+cfg['fixture_status'],
        'Area = original nominal width * thickness; patches excluded.',
        'Source: '+cfg['source_odb'],
        'Source step/interval/time: %d / %d / %.8g s'%(cfg['source_step'],cfg['source_interval'],cfg['source_time'])]
    lines.extend('WARNING: '+w for w in result['warnings'])
    with open(base+'_report.txt','wb') as f: f.write(('\n'.join(lines)+'\n').encode('utf-8'))
    # Native CAE XY plot for immediate review after extraction.
    try:
        from abaqus import session
        curve_name='CAIR_'+name
        if curve_name in session.xyDataObjects: del session.xyDataObjects[curve_name]
        session.XYData(name=curve_name,data=tuple((r['displacement_mm'],r['force_N']) for r in rows),
            xValuesLabel='Compression displacement (mm)',yValuesLabel='Compression load (N)')
    except Exception: pass
    log('\n'.join(lines))
    return result
