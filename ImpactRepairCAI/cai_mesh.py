# -*- coding: utf-8 -*-
"""Deterministic all-hex patch mesh. Planar plies, dent-filling bond film."""
from __future__ import division
import math


def footprint(cfg):
    a = cfg['size_x'] / 2.0
    b = a if cfg['shape'] == 'circle' else cfg['size_y'] / 2.0
    nx = max(2, int(math.ceil(2*a / cfg['mesh_size'])))
    ny = max(2, int(math.ceil(2*b / cfg['mesh_size'])))
    # Even subdivisions include the centre and avoid very skewed cells there.
    nx += nx % 2
    ny += ny % 2
    if (nx + 1) * (ny + 1) * (2 * cfg['ply_count'] + 2) > 1000000:
        raise ValueError('Patch exceeds one million nodes; increase mesh_size')
    theta = math.radians(cfg['rotation'])
    c, s = math.cos(theta), math.sin(theta)
    xy = []
    for j in range(ny+1):
        v = -1.0 + 2.0*j/ny
        for i in range(nx+1):
            u = -1.0 + 2.0*i/nx
            if cfg['shape'] == 'rectangle':
                x, y = a*u, b*v
                r=cfg.get('corner_radius',0.)
                if r>0:
                    dx=max(0.,abs(x)-(a-r)); dy=max(0.,abs(y)-(b-r))
                    if dx>0 and dy>0:
                        x=math.copysign(a-r+dx*math.sqrt(max(0.,1.-.5*(dy/r)**2)),x)
                        y=math.copysign(b-r+dy*math.sqrt(max(0.,1.-.5*(dx/r)**2)),y)
            else:
                x = a*u*math.sqrt(1.0 - 0.5*v*v)
                y = b*v*math.sqrt(1.0 - 0.5*u*u)
            xy.append((cfg['center_x']+c*x-s*y, cfg['center_y']+s*x+c*y))
    quads = []
    for j in range(ny):
        for i in range(nx):
            k = j*(nx+1)+i
            quads.append((k, k+1, k+nx+2, k+nx+1))
    return xy, quads


def patch_mesh(cfg, surface_z, side):
    """surface_z(x,y) samples the CURRENT source outer surface in global XY.

    Layers share nodes through cohesive elements, not across interfaces.
    For the bottom patch reverse stack connectivity, retaining positive volume.
    """
    xy, quads = footprint(cfg)
    heights=[]
    for x,y in xy:
        try: heights.append(surface_z(x,y))
        except ValueError as exc:
            if cfg.get('bond_void_policy','reject')!='bridge' or 'outside an intact' not in str(exc): raise
            heights.append(None)
    bonded=[]
    for q in quads:
        supported=all(heights[i] is not None for i in q)
        if supported and hasattr(surface_z,'covers'):
            supported=surface_z.covers([xy[i] for i in q])
        if not supported and cfg.get('bond_void_policy','reject')=='reject':
            raise ValueError('A film cell spans missing substrate surface; choose a repair void policy')
        bonded.append(supported)
    if not any(bonded): raise ValueError('No fully supported bond cells remain; patch would be unattached')
    sign = 1 if side == 'top' else -1
    candidates=[h for h in heights if h is not None]
    if hasattr(surface_z,'vertices'):
        theta=math.radians(cfg['rotation']); c,s=math.cos(theta),math.sin(theta)
        a=cfg['size_x']/2.; b=a if cfg['shape']=='circle' else cfg['size_y']/2.
        for x,y,z in surface_z.vertices:
            dx,dy=x-cfg['center_x'],y-cfg['center_y']
            u,v=(c*dx+s*dy)/a,(-s*dx+c*dy)/b
            inside=max(abs(u),abs(v))<=1.+1.e-9 if cfg['shape']=='rectangle' else u*u+v*v<=1.+1.e-9
            if inside and cfg['shape']=='rectangle' and cfg.get('corner_radius',0.)>0:
                r=cfg['corner_radius']
                inside=max(abs(u*a)-(a-r),0.)**2+max(abs(v*b)-(b-r),0.)**2<=r*r+1.e-10
            if inside: candidates.append(z)
    plane = (max(candidates) if sign == 1 else min(candidates)) + sign*cfg['adhesive_min_thickness']
    heights=[h if h is not None else plane for h in heights]
    levels = [heights, [plane]*len(xy)]
    kinds = [('adhesive', 0)]
    z = plane
    for ply in range(cfg['ply_count']):
        z += sign*cfg['ply_thickness']
        levels.append([z]*len(xy))
        kinds.append(('ply', ply))
        if ply < cfg['ply_count']-1:
            z += sign*cfg['interply_thickness']
            levels.append([z]*len(xy))
            kinds.append(('interply', ply))
    nodes = []
    for level in levels:
        nodes.extend([(p[0], p[1], h) for p, h in zip(xy, level)])
    elements = []
    count = len(xy)
    for k, (kind, index) in enumerate(kinds):
        for qi,q in enumerate(quads):
            if kind=='adhesive' and not bonded[qi]: continue
            near = tuple(k*count+i+1 for i in q)
            far = tuple((k+1)*count+i+1 for i in q)
            conn = near+far if sign == 1 else far+near
            elements.append((kind, index, conn))
    used_bond_nodes=set(i for qi,q in enumerate(quads) if bonded[qi] for i in q)
    thickness = [abs(plane-heights[i]) for i in used_bond_nodes]
    # Remove unused film-side nodes over voids; the complete solid patch bridges them.
    used=sorted(set(i for k,j,conn in elements for i in conn))
    remap=dict((old,new) for new,old in enumerate(used,1))
    nodes=[nodes[i-1] for i in used]
    elements=[(k,j,tuple(remap[i] for i in conn)) for k,j,conn in elements]
    return dict(nodes=nodes, elements=elements, plane=plane, side=side,
                film_min=min(thickness), film_max=max(thickness),
                footprint_nodes=count, footprint_elements=len(quads),
                bonded_cells=sum(bonded),bridged_cells=len(quads)-sum(bonded))


class SurfaceSampler(object):
    """Exact piecewise planar interpolation on deformed outer hex faces.

    A spatial index avoids an O(N*M) search. No nearest-node extrapolation:
    a hole, deleted face or outside point raises a useful geometry error.
    """
    def __init__(self, faces, cell_size=2.0):
        self.size = max(float(cell_size), 1.e-6)
        self.cells = {}
        self.vertices=set(p for face in faces for p in face)
        for face in faces:
            for tri in ((face[0], face[1], face[2]), (face[0], face[2], face[3])):
                xx = [p[0] for p in tri]; yy = [p[1] for p in tri]
                for ix in range(self.key(min(xx)), self.key(max(xx))+1):
                    for iy in range(self.key(min(yy)), self.key(max(yy))+1):
                        self.cells.setdefault((ix, iy), []).append(tri)

    def key(self, x):
        return int(math.floor(x/self.size))

    def covers(self,quad):
        """Exact projected-area test avoids bonding across sub-grid deleted faces."""
        def area(poly):
            return abs(sum(poly[i][0]*poly[(i+1)%len(poly)][1]-poly[(i+1)%len(poly)][0]*poly[i][1]
                           for i in range(len(poly))))/2. if len(poly)>2 else 0.
        triangles=set()
        for ix in range(self.key(min(p[0] for p in quad)),self.key(max(p[0] for p in quad))+1):
            for iy in range(self.key(min(p[1] for p in quad)),self.key(max(p[1] for p in quad))+1):
                triangles.update(self.cells.get((ix,iy),()))
        covered=0.
        for triangle in triangles:
            polygon=[p[:2] for p in triangle]
            for a,b in zip(quad,quad[1:]+quad[:1]):
                def signed(p): return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
                output=[]
                if not polygon: break
                last=polygon[-1]; ds=signed(last)
                for point in polygon:
                    de=signed(point)
                    if (de>=-1.e-12)!=(ds>=-1.e-12):
                        fraction=ds/(ds-de)
                        output.append(tuple(last[i]+fraction*(point[i]-last[i]) for i in (0,1)))
                    if de>=-1.e-12: output.append(point)
                    last,ds=point,de
                polygon=output
            covered+=area(polygon)
        return covered>=area(quad)*(1.-1.e-7)

    def __call__(self, x, y):
        hits = []
        for a, b, c in self.cells.get((self.key(x), self.key(y)), ()):
            den = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(den) < 1.e-15:
                continue
            u = ((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den
            v = ((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den
            w = 1-u-v
            if min(u, v, w) >= -1.e-7:
                hits.append(u*a[2]+v*b[2]+w*c[2])
        if not hits:
            raise ValueError('Patch point (%.6g, %.6g) is outside an intact bond surface' % (x,y))
        if max(hits)-min(hits) > 1.e-4:
            raise ValueError('Folded/multi-valued bond surface at (%.6g, %.6g)' % (x,y))
        return sum(hits)/len(hits)
