# -*- coding: utf-8 -*-
"""Read-only source job checks. No remeshing or SDV reinterpretation."""
from __future__ import division, print_function
import os
import re
import sys
import time
import atexit
from cai_config import api_path
from cai_inherit import derive_geometry,source_outputs

HEX_FACES = ((0,1,2,3), (4,7,6,5), (0,4,5,1),
             (1,5,6,2), (2,6,7,3), (3,7,4,0))
REQUIRED_FILES = ('.odb', '.abq', '.res', '.mdl', '.stt', '.pac', '.prt')


def validate_source_version(version):
    """ODB upgrades alone do not migrate the associated Explicit state files."""
    if not re.search(r'\b2024\b', str(version)):
        raise ValueError(
            'Abaqus 2024 source analysis required; found %s. Regenerate the '
            'impact job and its complete saved-state files in Abaqus 2024; '
            'upgrading only the ODB does not convert the Explicit state library.'
            % version)


def _source_fingerprint(cfg):
    """Invalidate the single read-only handle when any source input/state changes."""
    base = os.path.splitext(cfg['source_odb'])[0]
    if os.path.isfile(base+'.lck'):
        raise ValueError('Source ODB is locked; wait for the impact job to close')
    paths = set([cfg['source_inp']] + [base+ext for ext in REQUIRED_FILES+('.sta',)])
    result = []
    for path in sorted(paths):
        stat = os.stat(path)
        result.append((os.path.normcase(os.path.abspath(path)), stat.st_size,
                       stat.st_mtime, stat.st_ctime))
    return tuple(result)


class ReadOnlyOdbCache(object):
    """Keep at most one open source ODB, never CAE parts or material-state copies.

    State selection, U/STATUS and all geometry checks still run for each build.
    A fresh process or a changed source always opens a new handle.
    """
    def __init__(self):
        self.odb = None
        self.fingerprint = None

    def close(self):
        odb = self.odb
        self.odb = None
        self.fingerprint = None
        if odb is not None:
            try: odb.close()
            except Exception: pass

    def acquire(self, cfg, opener):
        try:
            fingerprint = _source_fingerprint(cfg)
            if self.odb is not None and fingerprint == self.fingerprint:
                # Abaqus can return the same native handle to another script;
                # that script (or a user action) may subsequently close it.
                try: self.odb.jobData.version
                except Exception: self.close()
                else:
                    log('Reusing unchanged source ODB (read-only, same CAE session).')
                    return self.odb
            self.close()
            self.odb = opener(path=api_path(cfg['source_odb']), readOnly=True)
            self.fingerprint = fingerprint
            self.verify(cfg)
            return self.odb
        except Exception:
            self.close()
            raise

    def verify(self, cfg):
        try:
            if _source_fingerprint(cfg) != self.fingerprint:
                raise ValueError('Source files changed while reading; retry with a stable source')
        except Exception:
            self.close()
            raise


_SOURCE_ODB_CACHE = ReadOnlyOdbCache()


def close_source_cache():
    """Release the optional source handle before replacing/deleting source files."""
    _SOURCE_ODB_CACHE.close()


atexit.register(close_source_cache)


def log(message):
    print('[ImpactRepairCAI] ' + message)
    sys.stdout.flush()


def blocks(path):
    """Yield keyword plus data; node/element blocks are skipped when requested."""
    key, data, skip = None, [], False
    mesh_keyword = re.compile(r'^\*(node|element|nset|elset|surface)\s*(,|$)', re.I)
    with open(path, 'r') as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith('**'):
                continue
            if line.startswith('*'):
                if key is not None:
                    yield key, data
                key, data = line, []
                skip = bool(mesh_keyword.match(key))
            elif key and not skip:
                data.append(line)
        if key is not None:
            yield key, data


def options(key):
    result = {}
    for item in key.split(',')[1:]:
        if '=' in item:
            name, value = item.split('=', 1)
            result[name.strip().lower()] = value.strip()
        else:
            result[item.strip().lower()] = True
    return result


def numbers(lines):
    return [float(x.strip()) for line in lines for x in line.split(',') if x.strip()]


def read_deck(path):
    mats, steps, current = {}, [], None
    output=None
    for key, data in blocks(path):
        name = key.split(',')[0].lower()
        opts = options(key)
        if name == '*include':
            raise ValueError('Flatten *INCLUDE files before using this source deck')
        if name == '*material':
            current = {}
            mats[opts['name'].upper()] = current
        elif name in ('*surface interaction', '*step'):
            current = None
        if current is not None:
            if name == '*density': current['density'] = numbers(data)[0]
            elif name == '*user material': current['constants'] = numbers(data)
            elif name == '*depvar':
                current['depvar'] = int(numbers(data)[0])
                current['delete'] = int(opts.get('delete', 0))
            elif name == '*elastic':
                current['elastic'] = numbers(data)
                current['elastic_type'] = opts.get('type', 'ISOTROPIC').upper()
            elif name == '*damage initiation':
                current['initiation'] = opts.get('criterion', '').upper()
                current['strengths'] = numbers(data)
            elif name == '*damage evolution':
                current['evolution'] = opts
                current['energies'] = numbers(data)
        if name == '*step':
            steps.append({'name': opts.get('name', 'Step-%d' % (len(steps)+1)), 'outputs':[]})
            output=None
        elif name == '*dynamic' and steps:
            steps[-1]['explicit'] = 'explicit' in opts
            steps[-1]['duration'] = numbers(data)[-1]
        elif name == '*restart' and steps:
            steps[-1]['restart'] = opts
        if name=='*output' and steps:
            output={'keyword':key,'options':opts,'blocks':[]}
            steps[-1]['outputs'].append(output)
        elif output is not None and name in ('*node output','*element output','*contact output','*energy output'):
            output['blocks'].append({'keyword':key,'options':opts,'data':data})
        elif name=='*end step': output=None
    return dict(materials=mats, steps=steps)


def saved_states(path):
    """Read actual state-file record numbers and STEP-relative times from .sta.

    Restart Number can be 1 at every write under OVERLAY. The printed time
    is total analysis time, so subtract the current STEP ORIGIN.
    """
    records={}; number=None; origin=0.
    if not os.path.isfile(path): return records
    with open(path,'r') as handle:
        for line in handle:
            m=re.search(r'^\s*STEP\s+(\d+)\s+ORIGIN\s+([\d.EeDd+\-]+)',line)
            if m:
                number=int(m.group(1)); origin=float(m.group(2).replace('D','E').replace('d','e'))
            m=re.search(r'Restart Number\s+(\d+)\s+at\s+([\d.EeDd+\-]+)',line)
            if m and number is not None:
                t=float(m.group(2).replace('D','E').replace('d','e'))-origin
                records.setdefault(number,[]).append((int(m.group(1)),t))
    return records


class FrameTimes(object):
    """Lazy time view: do not materialize every large ODB frame to read its time."""
    def __init__(self, frames):
        self.frames = frames
        self.times = {}

    def __len__(self): return len(self.frames)

    def __getitem__(self, index):
        if index < 0: index += len(self)
        if index < 0 or index >= len(self): raise IndexError(index)
        if index not in self.times:
            self.times[index] = float(self.frames[index].frameValue)
        return self.times[index]


def closest_frame_index(frame_times, target):
    """Nearest time in chronological Explicit frames; ties keep the first frame."""
    if not frame_times: raise ValueError('Selected ODB step has no frames')
    def lower_bound(value, high):
        low = 0
        while low < high:
            middle = (low+high)//2
            if frame_times[middle] < value: low = middle+1
            else: high = middle
        return low
    right = lower_bound(target, len(frame_times))
    if right == 0: return 0
    left = right-1
    if right < len(frame_times) and abs(frame_times[right]-target) < abs(frame_times[left]-target):
        return right
    # The original linear search returned the earliest index for duplicate times.
    if left and frame_times[left-1] == frame_times[left]:
        return lower_bound(frame_times[left], left)
    return left


def latest_frame_selection(frame_times, records, duration):
    """Match the latest retained state to an ODB frame; never mix geometries."""
    if not frame_times: raise ValueError('Last ODB step has no frames')
    last=float(frame_times[-1]); tolerance=max(1.e-10,float(duration)*1.e-6)
    if not records:
        raise ValueError('Cannot identify the last saved Explicit state from .sta; retain the source status file')
    interval,t=records[-1]
    index=closest_frame_index(frame_times,t)
    if t>last+tolerance or abs(float(frame_times[index])-t)>tolerance:
        raise ValueError('Last saved Explicit state has no matching ODB frame; geometry and state cannot be combined')
    return dict(restart_interval=int(interval),restart_time=float(t),frame_index=index,
                requested_last_frame_time=last,used_last_frame=abs(last-t)<=tolerance)


def preflight(cfg):
    base = os.path.splitext(cfg['source_odb'])[0]
    missing = [base+ext for ext in REQUIRED_FILES if not os.path.isfile(base+ext)]
    for path in (cfg['source_inp'], cfg['vumat']):
        if not os.path.isfile(path): missing.append(path)
    if missing:
        raise ValueError('Missing source files: ' + '; '.join(missing))
    if os.path.isfile(base+'.lck'):
        raise ValueError('Source ODB is locked; wait for the impact job to close')
    if os.path.normcase(os.path.splitext(cfg['source_inp'])[0]) != os.path.normcase(base):
        raise ValueError('INP and ODB must have the same directory and job basename')
    deck = read_deck(cfg['source_inp'])
    if not deck['steps']: raise ValueError('Source deck has no analysis steps')
    if cfg['state_selection']=='manual' and cfg['source_step'] > len(deck['steps']):
        raise ValueError('Source step is outside the input deck')
    step = deck['steps'][-1] if cfg['state_selection']=='auto' else deck['steps'][cfg['source_step']-1]
    if cfg['state_selection']=='manual' and not step.get('explicit'):
        raise ValueError('This version supports Explicit -> Explicit state import')
    records=saved_states(base+'.sta')
    expected=None
    if cfg['state_selection']=='manual':
        matches=[t for n,t in records.get(cfg['source_step'],[]) if n==cfg['source_interval']]
        if not matches:
            raise ValueError('Requested Explicit record is absent from .sta; use automatic state selection')
        expected=matches[-1]
        if abs(expected-cfg['source_time'])>max(1.e-10,step['duration']*1.e-6):
            raise ValueError('source_time differs from the actual saved record: %.12g s'%expected)
    bm = deck['materials'].get(cfg['base_material'].upper(), {})
    cm = deck['materials'].get(cfg['interply_material'].upper(), {})
    if not bm.get('constants') or 'density' not in bm or 'depvar' not in bm:
        raise ValueError('Base material must define density, DEPVAR and VUMAT constants')
    if (cm.get('elastic_type') != 'TRACTION' or cm.get('initiation') != 'QUADS'
            or cm.get('evolution', {}).get('type', '').upper() != 'ENERGY'
            or cm.get('evolution', {}).get('mixed mode behavior', '').upper() != 'BK'):
        raise ValueError('Source interply material must use TRACTION + QUADS + ENERGY/BK')
    warnings = []
    status_file = base+'.sta'
    if os.path.isfile(status_file):
        with open(status_file, 'rb') as handle:
            status = handle.read().decode('ascii', 'replace')
        release = re.search(r'Abaqus/Explicit\s+(\d{4})', status, re.I)
        if release:
            validate_source_version(release.group(1))
        if 'THE ANALYSIS HAS COMPLETED SUCCESSFULLY' not in status:
            warnings.append('Source impact did not complete successfully; using an available saved state.')
    else:
        warnings.append('Source completion status is unavailable.')
    com_path = base+'.com'
    if os.path.isfile(com_path):
        with open(com_path, 'r') as handle:
            match = re.search(r"'user'\s*:\s*'([^']+)'", handle.read())
        if match:
            recorded = match.group(1).replace('\\\\', '\\')
            if os.path.normcase(os.path.abspath(recorded)) != os.path.normcase(cfg['vumat']):
                raise ValueError('VUMAT differs from source job: ' + recorded)
    return {'source_base': base, 'deck': deck, 'warnings': warnings,
            'restart_time': expected, 'restart_interval': cfg['source_interval'],
            'saved_states':records}


def resolve_state(cfg,info,odb):
    names=list(odb.steps.keys())
    if not names: raise ValueError('Source ODB has no analysis steps')
    if cfg['state_selection']=='auto':
        cfg['source_step']=len(names)
        step=odb.steps[names[-1]]
        deck=info['deck']['steps']
        if len(names)>len(deck) or deck[len(names)-1]['name']!=names[-1]:
            raise ValueError('Last ODB step does not match the source INP')
        if not deck[len(names)-1].get('explicit'):
            raise ValueError('Last ODB step is not Explicit')
        selected=latest_frame_selection(FrameTimes(step.frames),
            info['saved_states'].get(len(names),[]),deck[len(names)-1]['duration'])
        cfg['source_interval']=selected['restart_interval']; cfg['source_time']=selected['restart_time']
        info.update(selected)
        if not selected['used_last_frame']:
            warning='Last ODB frame %.12g s has no saved state; using last saved state %.12g s.'%(selected['requested_last_frame_time'],cfg['source_time'])
            info['warnings'].append(warning); log(warning)
    else:
        if cfg['source_step']>len(names): raise ValueError('Source step is absent from ODB')
        step=odb.steps[names[cfg['source_step']-1]]
        if not step.frames: raise ValueError('Selected ODB step has no frames')
        index=closest_frame_index(FrameTimes(step.frames),cfg['source_time'])
        if abs(step.frames[index].frameValue-cfg['source_time'])>max(1.e-10,cfg['source_time']*1.e-6):
            raise ValueError('ODB has no frame at the saved-state time')
        info['frame_index']=index
    info.update(step_name=names[cfg['source_step']-1],source_step=cfg['source_step'],
                restart_interval=cfg['source_interval'],restart_time=cfg['source_time'])
    log('Selected step %d (%s), frame %d, saved record %d, time %.12g s.'%
        (cfg['source_step'],info['step_name'],info['frame_index'],cfg['source_interval'],cfg['source_time']))
    return odb.steps[info['step_name']],info['frame_index']


def inspect_source(cfg):
    from odbAccess import openOdb
    info=preflight(cfg)
    odb=_SOURCE_ODB_CACHE.acquire(cfg,openOdb)
    try:
        validate_source_version(odb.jobData.version)
        resolve_state(cfg,info,odb)
        _SOURCE_ODB_CACHE.verify(cfg)
    except Exception:
        close_source_cache()
        raise
    return info


def read_state(cfg, part_loader=None):
    from odbAccess import openOdb
    info = preflight(cfg)
    started=time.time()
    log('Accessing source ODB read-only; first open can take several minutes.')
    odb = _SOURCE_ODB_CACHE.acquire(cfg,openOdb)
    log('Source ODB ready in %.2f s.'%(time.time()-started))
    try:
        validate_source_version(odb.jobData.version)
        if cfg['source_instance'] not in odb.rootAssembly.instances:
            raise ValueError('Source instance not found: ' + cfg['source_instance'])
        part = odb.rootAssembly.instances[cfg['source_instance']]
        selection_started=time.time()
        log('Resolving saved state and ODB frames; first access may load the ODB index.')
        step,frame_index=resolve_state(cfg,info,odb)
        log('State/frame selection completed in %.2f s.'%(time.time()-selection_started))
        step_name=info['step_name']
        frame = step.frames[frame_index]
        if abs(frame.frameValue-cfg['source_time']) > max(1.e-10, cfg['source_time']*1.e-6):
            raise ValueError('ODB has no frame at the requested saved-state time')
        if 'U' not in frame.fieldOutputs or 'STATUS' not in frame.fieldOutputs:
            raise ValueError('Source must output U and STATUS at the selected state')
        log('Reading displacement and element status at %.8g s.' % frame.frameValue)
        field_started=time.time()
        u = {}
        for block in frame.fieldOutputs['U'].getSubset(region=part).bulkDataBlocks:
            for label, row in zip(block.nodeLabels, block.data): u[int(label)] = tuple(float(v) for v in row)
        deleted = set()
        for block in frame.fieldOutputs['STATUS'].getSubset(region=part).bulkDataBlocks:
            for label, row in zip(block.elementLabels, block.data):
                if row[0] < 0.5: deleted.add(label)
        log('Read U and STATUS in %.2f s.'%(time.time()-field_started))
        reference = dict((int(n.label), tuple(float(v) for v in n.coordinates)) for n in part.nodes)
        if set(reference) - set(u):
            raise ValueError('Displacement is missing for source nodes')
        current = dict((label, tuple(x+d for x,d in zip(p,u[label]))) for label,p in reference.items())
        mins = [min(p[i] for p in reference.values()) for i in range(3)]
        maxs = [max(p[i] for p in reference.values()) for i in range(3)]
        faces = {'top': [], 'bottom': []}
        surfaces = {'top': {}, 'bottom': {}, 'inner': {}, 'types': {}}
        tol = max(1.e-6, (maxs[2]-mins[2])*1.e-5)
        types = {}
        spans={'C3D8R':set(),'COH3D8':set()}
        scan_started=time.time()
        for element in part.elements:
            # ODB proxy attribute access crosses the Python/native boundary.
            # Read each attribute once and reuse the eight reference heights.
            kind=element.type; label=int(element.label); conn=element.connectivity
            types[kind] = types.get(kind,0)+1
            surfaces['types'].setdefault(kind,[]).append(label)
            if kind not in ('C3D8R', 'COH3D8'):
                raise ValueError('Unsupported source element type: '+kind)
            zz=[reference[n][2] for n in conn]
            spans[kind].add((min(zz),max(zz)))
            if kind != 'C3D8R' or label in deleted: continue
            for face_number, face in enumerate(HEX_FACES, 1):
                face_z=[zz[i] for i in face]
                if max(face_z)-min(face_z)<tol:
                    surfaces['inner'].setdefault(face_number,[]).append(label)
                for side, z in (('top',maxs[2]), ('bottom',mins[2])):
                    if all(abs(value-z)<tol for value in face_z):
                        faces[side].append(tuple(current[conn[i]] for i in face))
                        surfaces[side].setdefault(face_number,[]).append(label)
        log('Scanned %d source elements in %.2f s.'%(sum(types.values()),time.time()-scan_started))
        if cfg['analysis_mode']==1 and (not faces['top'] or not faces['bottom']):
            raise ValueError('Source must be a flat XY laminate with thickness along Z')
        info.update(version=version, step_name=step_name, frame_index=frame_index,
                    frame_time=float(frame.frameValue), bounds=[mins,maxs], element_types=types,
                    nodes=len(reference), deleted_elements=len(deleted))
        derive_geometry(cfg,info,spans)
        info['output_requests']=source_outputs(info['deck']['steps'],cfg['source_step'])
        info['output_regions']={}
        # Map retained plate output regions to new assembly sets. Requests for
        # removed impactor/fixture regions are omitted and listed in the report.
        info['omitted_output_regions']=[]
        for request in info['output_requests']:
            for block in request['blocks']:
                for key,repo in (('nset',part.nodeSets),('elset',part.elementSets)):
                    name=block['options'].get(key)
                    if not name: continue
                    prefix=cfg['source_instance'].upper()+'.'
                    local=name.upper()[len(prefix):] if name.upper().startswith(prefix) else name.upper()
                    if local in repo and ('.' not in name or name.upper().startswith(prefix)):
                        region=repo[local]
                        values=region.nodes if key=='nset' else region.elements
                        info['output_regions'][key+':'+name]=dict(kind=key,labels=[int(x.label) for x in values])
                    else: info['omitted_output_regions'].append(name)
        if part_loader is not None:
            import_started=time.time()
            part_loader(odb,frame_index)
            log('Imported plate into CAE in %.2f s.'%(time.time()-import_started))
        _SOURCE_ODB_CACHE.verify(cfg)
        return info, reference, current, faces, surfaces
    except Exception:
        close_source_cache()
        raise
