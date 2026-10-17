# -*- coding: utf-8 -*-
"""Source-derived geometry and output requests; no Abaqus imports."""
from __future__ import division
import copy
import re

DERIVED_KEYS=set(('center_x','center_y','rotation','ply_thickness','interply_thickness',
    'nominal_width','nominal_thickness','load_axis','field_intervals','history_intervals',
    'source_equilibrated'))


def source_outputs(steps,number):
    active={}
    for step in steps[:number]:
        for kind in ('field','history'):
            requests=[x for x in step.get('outputs',[]) if kind in x['options']]
            if requests: active[kind]=copy.deepcopy(requests)
    if not active.get('field') or not active.get('history'):
        raise ValueError('Source INP must define field and history output requests')
    return active['field']+active['history']


def derive_geometry(cfg,info,spans):
    def merged(rows):
        result=[]
        for low,high in sorted(rows):
            if high<=low: raise ValueError('Source has zero-thickness solid/cohesive elements')
            if result and low<=result[-1][1]+1.e-9:
                result[-1][1]=max(high,result[-1][1])
            else: result.append([low,high])
        return result
    plies=merged(spans['C3D8R']); interfaces=merged(spans['COH3D8'])
    if not plies: raise ValueError('No solid plate plies found')
    solid=[b-a for a,b in plies]; coh=[b-a for a,b in interfaces]
    thickness=sum(solid)
    if cfg['analysis_mode']==1:
        if max(solid)-min(solid)>max(2.e-6,thickness/len(solid)*1.e-3):
            raise ValueError('Source plies have different thicknesses; one inherited patch ply thickness is ambiguous')
        if not coh and cfg['ply_count']>1:
            raise ValueError('Source has no geometric cohesive layer from which to inherit patch interply thickness')
        if coh and max(coh)-min(coh)>max(1.e-6,sum(coh)/len(coh)*.1):
            raise ValueError('Source cohesive layer thicknesses differ; automatic inheritance is ambiguous')
    lo,hi=info['bounds']; lx,ly=hi[0]-lo[0],hi[1]-lo[1]
    cfg.update(center_x=(lo[0]+hi[0])/2.,center_y=(lo[1]+hi[1])/2.,
        load_axis=0,nominal_width=ly,nominal_thickness=thickness,
        ply_thickness=thickness/len(solid),rotation=0.)
    if coh: cfg['interply_thickness']=sum(coh)/len(coh)
    # size_x/size_y are the two full ellipse axes; either may be longer.
    if cfg['shape']=='ellipse' and ((ly>lx)!=(cfg['size_y']>cfg['size_x'])):
        cfg['rotation']=90.
    info['inherited_geometry']=dict((k,cfg[k]) for k in
        ('center_x','center_y','rotation','load_axis','nominal_width','nominal_thickness','ply_thickness','interply_thickness'))
    info['source_ply_count']=len(plies)


def output_text(info,region_names):
    lines=[]
    for request in info['output_requests']:
        kept=[]
        for block in request['blocks']:
            key=block['keyword']; retain=True
            for kind in ('nset','elset'):
                name=block['options'].get(kind)
                if name:
                    mapped=region_names.get(kind+':'+name)
                    if mapped is None: retain=False; break
                    key=re.sub(r'(?i)('+kind+r'\s*=\s*)[^,\n]+',lambda m:m.group(1)+mapped,key)
            if retain: kept.extend([key]+block['data'])
        if kept or 'variable' in request['options']:
            lines.extend([request['keyword']]+kept)
    # Supplemental CAI measurements use the source global output cadence.
    for kind,body in (
        ('field',['*Node Output','U, RF','*Element Output','S, SDV, SDEG, STATUS']),
        ('history',['*Energy Output','ALLKE, ALLIE, ALLAE, ALLVD, ALLWK, ETOTAL',
                    '*Node Output, nset=CAIR_LOADED','RF1, U1',
                    '*Node Output, nset=CAIR_FIXED','RF1, U1'])):
        matches=[r for r in info['output_requests'] if kind in r['options']]
        global_requests=[r for r in matches if not any(k in r['options'] for k in ('nset','elset','tracer set'))]
        header=(global_requests or matches)[0]['keyword']
        header=re.sub(r'(?i),\s*variable\s*=\s*[^,\n]+','',header)
        lines.extend([header]+body)
    return '\n'.join(lines)
