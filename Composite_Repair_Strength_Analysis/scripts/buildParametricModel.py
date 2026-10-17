# -*- coding: utf-8 -*-
"""Build the revised parametric repair model.

Design rules:
* the laminate total thickness is not increased by artificial inter-ply
  adhesive solids;
* double-sided patch repairs use two finite-thickness, isotropic,
  linear-elastic annular adhesive solids tied to the holed parent laminate
  and the upper/lower circular repair patches;
* staircase repairs use a finite-thickness, isotropic, linear-elastic solid
  adhesive tied to the parent laminate and repair patch;
* the staircase patch is translated outward by the adhesive thickness, so
  its top surface is allowed to protrude above the parent laminate;
* scarf repairs use a geometrically smooth cone represented by deterministic ply-wise O-grid blocks, C3D8R/C3D6 elements, a physical finite-thickness adhesive and two Tie interfaces;
* base and repair ply counts are independent of staircase level count.

This script is executed by RSGen_Master inside Abaqus/CAE 2024.
"""

import math

from abaqus import *
from abaqusConstants import *
from caeModules import *
import mesh
import regionToolset


modelData = globals()['modelData']
model = mdb.models['Model-1']
repairData = modelData['modify']
repairType = int(repairData['type'])
buildStage = str(modelData.get('buildStage', 'full')).lower()
if buildStage not in ('full', 'geometry', 'mesh'):
    raise ValueError('Unknown build stage: %s' % buildStage)
if buildStage in ('geometry', 'mesh') and repairType != 2:
    raise ValueError(
        'Separated geometry/mesh stages are currently available only for '
        'the true smooth scarf repair')

length = float(modelData['length'])
width = float(modelData['height'])
totalThickness = float(modelData['depth'])
baseLayerCount = int(modelData['nlayers'])
basePlyThickness = totalThickness / float(baseLayerCount)
damageRadius = float(modelData['r'])
repairLayerCount = int(repairData['n'])
repairDepth = float(repairData['repairDepth'])
repairBottom = totalThickness - repairDepth
repairOuterRadius = float(repairData['outerDiameter']) / 2.0
adhesiveThickness = float(repairData.get('cohesive', 0.0))

patchLayerCountPerSide = None
patchDepthPerSide = None
if repairType == 0:
    patchLayerCountPerSide = int(repairData.get(
        'nPerSide', repairLayerCount // 2))
    patchDepthPerSide = float(repairData.get(
        'repairDepthPerSide',
        basePlyThickness * patchLayerCountPerSide))


def _face_sequence(part, faces):
    result = None
    for face in faces:
        one = part.faces[face.index:face.index + 1]
        result = one if result is None else result + one
    if result is None:
        raise ValueError('A required geometric surface contains no faces')
    return result


def _cell_sequence(part, cells):
    result = None
    for cell in cells:
        one = part.cells[cell.index:cell.index + 1]
        result = one if result is None else result + one
    if result is None:
        raise ValueError('A required material region contains no cells')
    return result


def _create_plate(partName, withHole=False):
    sketch = model.ConstrainedSketch(
        name='__plate_profile__',
        sheetSize=max(length, width) * 2.0)
    sketch.rectangle(
        point1=(-length / 2.0, -width / 2.0),
        point2=(length / 2.0, width / 2.0))
    if withHole:
        sketch.CircleByCenterPerimeter(
            center=(0.0, 0.0), point1=(damageRadius, 0.0))
    part = model.Part(
        name=partName, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=totalThickness)
    del model.sketches['__plate_profile__']
    return part


def _create_plate_layer(partName, thickness, holeRadius=None):
    sketchName = '__plate_layer_profile__'
    sketch = model.ConstrainedSketch(
        name=sketchName, sheetSize=max(length, width) * 2.0)
    sketch.rectangle(
        point1=(-length / 2.0, -width / 2.0),
        point2=(length / 2.0, width / 2.0))
    if holeRadius is not None and holeRadius > 0.0:
        sketch.CircleByCenterPerimeter(
            center=(0.0, 0.0), point1=(holeRadius, 0.0))
    part = model.Part(
        name=partName, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=thickness)
    del model.sketches[sketchName]
    return part


def _create_disc(partName, radius, depth):
    sketch = model.ConstrainedSketch(
        name='__disc_profile__', sheetSize=max(length, width) * 2.0)
    sketch.CircleByCenterPerimeter(
        center=(0.0, 0.0), point1=(radius, 0.0))
    part = model.Part(
        name=partName, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=depth)
    del model.sketches['__disc_profile__']
    return part


def _create_annulus(partName, innerRadius, outerRadius, depth):
    """Create and quarter-partition a thin annular adhesive solid.

    The two datum-plane partitions make every cell topologically equivalent
    to an extruded curved quadrilateral.  This permits a structured/sweep
    hexahedral mesh instead of the highly distorted free tetrahedral mesh
    produced for a 0.15-mm-thick annulus.
    """
    if innerRadius <= 0.0:
        raise ValueError('Annular adhesive inner radius must be positive')
    if outerRadius <= innerRadius:
        raise ValueError(
            'Annular adhesive outer radius must exceed inner radius')
    sketch = model.ConstrainedSketch(
        name='__annulus_profile__',
        sheetSize=max(length, width) * 2.0)
    sketch.CircleByCenterPerimeter(
        center=(0.0, 0.0), point1=(outerRadius, 0.0))
    sketch.CircleByCenterPerimeter(
        center=(0.0, 0.0), point1=(innerRadius, 0.0))
    part = model.Part(
        name=partName, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=depth)
    del model.sketches['__annulus_profile__']

    yzPlane = part.DatumPlaneByPrincipalPlane(
        principalPlane=YZPLANE, offset=0.0)
    part.PartitionCellByDatumPlane(
        datumPlane=part.datums[yzPlane.id], cells=part.cells)
    xzPlane = part.DatumPlaneByPrincipalPlane(
        principalPlane=XZPLANE, offset=0.0)
    part.PartitionCellByDatumPlane(
        datumPlane=part.datums[xzPlane.id], cells=part.cells)
    return part


def _create_revolved(partName, profile):
    """Create an axisymmetric solid whose local axial direction is +Y."""
    sketch = model.ConstrainedSketch(
        name='__repair_profile__',
        sheetSize=max(length, width) * 2.0)
    sketch.ConstructionLine(
        point1=(0.0, -max(length, width)),
        point2=(0.0, max(length, width)))
    for index in range(len(profile) - 1):
        sketch.Line(point1=profile[index], point2=profile[index + 1])
    part = model.Part(
        name=partName, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidRevolve(
        sketch=sketch, angle=360.0, flipRevolveDirection=OFF)
    del model.sketches['__repair_profile__']
    return part


def _stair_profile():
    levels = int(repairData['jtNum'])
    radialWidth = (
        repairOuterRadius - damageRadius) / float(levels)
    verticalHeight = repairDepth / float(levels)
    points = [(0.0, repairBottom), (damageRadius, repairBottom)]
    currentHeight = repairBottom
    for level in range(1, levels + 1):
        radius = damageRadius + level * radialWidth
        points.append((radius, currentHeight))
        currentHeight = repairBottom + level * verticalHeight
        points.append((radius, currentHeight))
    points.extend([(0.0, totalThickness), (0.0, repairBottom)])
    return points



def _stair_geometry_data():
    """Return the parent-cavity, patch-offset and terrace definitions.

    The parent cavity retains the original staircase geometry.  The repair
    patch is offset by ``adhesiveThickness`` in two ways:

    * every repair terrace radius is reduced by the adhesive thickness;
    * the complete repair patch is translated upward by the adhesive
      thickness at assembly level.

    The finite volume between the original cavity and the offset patch is the
    linear-elastic solid adhesive.  Allowing the patch to protrude preserves
    the original parent excavation depth and all repair-ply thicknesses.
    """
    levels = int(repairData['jtNum'])
    terraceCount = levels + 1
    if repairLayerCount < terraceCount:
        raise ValueError(
            'Repair ply count must be at least staircase levels + 1')
    if adhesiveThickness <= 0.0:
        raise ValueError(
            'Staircase solid adhesive thickness must be greater than zero')

    quotient = repairLayerCount // terraceCount
    remainder = repairLayerCount % terraceCount
    terracePlyCounts = [
        quotient + (1 if index < remainder else 0)
        for index in range(terraceCount)]
    terraceHeights = [
        count * basePlyThickness for count in terracePlyCounts]
    minimumTerraceHeight = min(terraceHeights)
    radialIncrement = (
        repairOuterRadius - damageRadius) / float(levels)

    geometryTolerance = 1.0e-9 * max(
        length, width, totalThickness, repairOuterRadius)
    if adhesiveThickness >= minimumTerraceHeight - geometryTolerance:
        raise ValueError(
            'The solid adhesive thickness (%.6g mm) must be smaller than '
            'the thinnest staircase terrace height (%.6g mm).  Increase '
            'plies per terrace, reduce adhesive thickness, or reduce the '
            'number of staircase levels.'
            % (adhesiveThickness, minimumTerraceHeight))
    if adhesiveThickness >= radialIncrement - geometryTolerance:
        raise ValueError(
            'The solid adhesive thickness (%.6g mm) must be smaller than '
            'the radial staircase width (%.6g mm).'
            % (adhesiveThickness, radialIncrement))
    if adhesiveThickness >= damageRadius - geometryTolerance:
        raise ValueError(
            'The solid adhesive thickness is too large for the centre '
            'repair radius')

    terraceRadii = [
        damageRadius + index * radialIncrement
        for index in range(terraceCount)]
    patchRadii = [
        radius - adhesiveThickness for radius in terraceRadii]
    terraceBounds = [repairBottom]
    for heightValue in terraceHeights:
        terraceBounds.append(terraceBounds[-1] + heightValue)
    # Remove accumulated floating-point drift at the top surface.
    terraceBounds[-1] = totalThickness

    parentRadiusByLayer = {}
    patchRadiusByLayer = {}
    layerIndex = baseLayerCount - repairLayerCount + 1
    for terraceIndex, plyCount in enumerate(terracePlyCounts):
        for unused in range(plyCount):
            parentRadiusByLayer[layerIndex] = terraceRadii[terraceIndex]
            patchRadiusByLayer[layerIndex] = patchRadii[terraceIndex]
            layerIndex += 1

    data = {
        'levels': levels,
        'terraceCount': terraceCount,
        'terracePlyCounts': terracePlyCounts,
        'terraceHeights': terraceHeights,
        'terraceRadii': terraceRadii,
        'patchRadii': patchRadii,
        'terraceBounds': terraceBounds,
        'radialIncrement': radialIncrement,
        'parentRadiusByLayer': parentRadiusByLayer,
        'patchRadiusByLayer': patchRadiusByLayer,
        'patchTranslation': adhesiveThickness,
        'patchTop': totalThickness + adhesiveThickness,
    }
    repairData['stairPlyDistribution'] = terracePlyCounts
    repairData['adhesiveModel'] = 'solid-linear-elastic-tie'
    repairData['trueScarfMeshMode'] = (
        'audit-coarse-v2.2; continuous geometry retained')
    repairData['patchProtrusion'] = adhesiveThickness
    repairData['parentTerraceRadii'] = terraceRadii
    repairData['patchTerraceRadii'] = patchRadii
    repairData['terraceBounds'] = terraceBounds
    return data


def _stair_adhesive_profile(stairData):
    """Create the closed r-z profile of the solid staircase adhesive."""
    radii = stairData['terraceRadii']
    patchRadii = stairData['patchRadii']
    bounds = stairData['terraceBounds']
    last = len(radii) - 1

    # Outer boundary: exactly follows the parent laminate cavity.
    points = [(0.0, bounds[0]), (radii[0], bounds[0])]
    for terraceIndex in range(len(radii)):
        points.append((radii[terraceIndex], bounds[terraceIndex + 1]))
        if terraceIndex < last:
            points.append((
                radii[terraceIndex + 1],
                bounds[terraceIndex + 1]))

    # The top annulus is exposed because the patch is allowed to protrude.
    points.append((patchRadii[last], totalThickness))

    # Inner boundary: follows the smaller patch after its upward translation.
    for terraceIndex in range(last, -1, -1):
        translatedBottom = (
            bounds[terraceIndex] + adhesiveThickness)
        points.append((patchRadii[terraceIndex], translatedBottom))
        if terraceIndex > 0:
            points.append((
                patchRadii[terraceIndex - 1], translatedBottom))
    points.extend([
        (0.0, bounds[0] + adhesiveThickness),
        (0.0, bounds[0]),
    ])
    return points


def _create_stair_adhesive_part(stairData):
    return _create_revolved(
        'Part-Adhesive', _stair_adhesive_profile(stairData))

def _scarf_profile():
    angle = math.radians(float(repairData['xjAngle']))
    outerRadius = damageRadius + repairDepth / math.tan(angle)
    if outerRadius >= min(length, width) / 2.0:
        raise ValueError(
            'The scarf repair exceeds the plate. Increase scarf angle, '
            'reduce repair depth, or enlarge the plate.')
    repairData['outerDiameter'] = 2.0 * outerRadius
    return [
        (0.0, repairBottom),
        (damageRadius, repairBottom),
        (outerRadius, totalThickness),
        (0.0, totalThickness),
        (0.0, repairBottom),
    ]


def _partition_at_z(part, values):
    for value in values:
        part.PartitionCellByPlaneThreePoints(
            cells=part.cells,
            point1=(0.0, 0.0, value),
            point2=(1.0, 0.0, value),
            point3=(0.0, 1.0, value))


def _partition_at_y(part, values):
    for value in values:
        part.PartitionCellByPlaneThreePoints(
            cells=part.cells,
            point1=(0.0, value, 0.0),
            point2=(1.0, value, 0.0),
            point3=(0.0, value, 1.0))


def _layer_groups(part, axisIndex, firstLayer, lastLayer, thickness):
    groups = {}
    for cell in part.cells:
        bounds = part.cells[
            cell.index:cell.index + 1].getBoundingBox()
        coordinate = 0.5 * (
            bounds['low'][axisIndex] + bounds['high'][axisIndex])
        layerIndex = int(math.floor(coordinate / thickness)) + 1
        layerIndex = max(firstLayer, min(lastLayer, layerIndex))
        groups.setdefault(layerIndex, []).append(cell)
    return groups


def _layer_groups_from_origin(
        part, axisIndex, firstLayer, layerCount, thickness, origin):
    """Group cells into plies measured from an arbitrary axial origin."""
    groups = {}
    lastLayer = firstLayer + layerCount - 1
    tolerance = 1.0e-9 * max(
        length, width, totalThickness, repairDepth, 1.0)
    for cell in part.cells:
        bounds = part.cells[
            cell.index:cell.index + 1].getBoundingBox()
        coordinate = 0.5 * (
            bounds['low'][axisIndex] + bounds['high'][axisIndex])
        offset = int(math.floor(
            (coordinate - origin + tolerance) / thickness))
        offset = max(0, min(layerCount - 1, offset))
        layerIndex = firstLayer + offset
        layerIndex = max(firstLayer, min(lastLayer, layerIndex))
        groups.setdefault(layerIndex, []).append(cell)
    return groups


def _create_materials_and_section():
    material = modelData['material']
    base = material['base']
    model.Material(name='Mat-Composite')
    model.materials['Mat-Composite'].Density(
        table=((float(base['density']),),))
    model.materials['Mat-Composite'].Depvar(
        n=int(base['depvar']), deleteVar=1)
    model.materials['Mat-Composite'].UserMaterial(
        mechanicalConstants=tuple(base['data']))
    model.HomogeneousSolidSection(
        name='Section-Composite', material='Mat-Composite', thickness=None)

    # Patch, staircase and scarf modes use the same finite-thickness,
    # isotropic, linear-elastic adhesive assumption.  No adhesive damage,
    # plasticity or element deletion is introduced; both adhesive faces are
    # tied.
    adhesive = material['adhesive']
    engineeringElastic = adhesive.get('engineeringElastic')
    if engineeringElastic is None:
        cohesiveZero = material.get('cohesiveZero', {})
        engineeringElastic = cohesiveZero.get('solidElastic')
    if engineeringElastic is None:
        engineeringElastic = (3000.0, 0.35)
    elasticModulus = float(engineeringElastic[0])
    poisson = float(engineeringElastic[1])
    if elasticModulus <= 0.0:
        raise ValueError('Solid adhesive elastic modulus must be positive')
    if not -1.0 < poisson < 0.5:
        raise ValueError(
            'Solid adhesive Poisson ratio must lie between -1 and 0.5')
    model.Material(name='Mat-Adhesive')
    model.materials['Mat-Adhesive'].Density(
        table=((float(adhesive['density']),),))
    model.materials['Mat-Adhesive'].Elastic(
        table=((elasticModulus, poisson),))
    model.HomogeneousSolidSection(
        name='Section-Adhesive', material='Mat-Adhesive',
        thickness=None)
    repairData['adhesiveElasticModulus'] = elasticModulus
    repairData['adhesivePoisson'] = poisson
    repairData['adhesiveModel'] = 'solid-linear-elastic-tie'


def _assign_layers(
        part, groups, angleByLayer, axisIndex, setPrefix='Set-Ply'):
    allCells = []
    for layerIndex in sorted(groups.keys()):
        cells = _cell_sequence(part, groups[layerIndex])
        setName = '%s-%02d' % (setPrefix, layerIndex)
        part.Set(name=setName, cells=cells)
        region = part.sets[setName]
        part.SectionAssignment(
            region=region, sectionName='Section-Composite',
            offset=0.0, offsetType=MIDDLE_SURFACE, offsetField='',
            thicknessAssignment=FROM_SECTION)
        if axisIndex == 2:
            normalVector = (0.0, 0.0, 1.0)
            normalAxis = AXIS_3
        else:
            normalVector = (0.0, 1.0, 0.0)
            normalAxis = AXIS_2
        part.MaterialOrientation(
            region=region,
            orientationType=DISCRETE,
            axis=normalAxis,
            normalAxisDefinition=VECTOR,
            normalAxisVector=normalVector,
            flipNormalDirection=False,
            normalAxisDirection=normalAxis,
            primaryAxisDefinition=VECTOR,
            primaryAxisVector=(1.0, 0.0, 0.0),
            primaryAxisDirection=AXIS_1,
            flipPrimaryDirection=False,
            additionalRotationType=ROTATION_ANGLE,
            additionalRotationField='',
            angle=float(angleByLayer[layerIndex]),
            stackDirection=STACK_3)
        allCells.extend(groups[layerIndex])
    part.Set(name='Set-VUMAT', cells=_cell_sequence(part, allCells))



def _assign_adhesive_section(part):
    cells = _cell_sequence(part, list(part.cells))
    part.Set(name='Set-Adhesive-All', cells=cells)
    part.SectionAssignment(
        region=part.sets['Set-Adhesive-All'],
        sectionName='Section-Adhesive',
        offset=0.0, offsetType=MIDDLE_SURFACE, offsetField='',
        thicknessAssignment=FROM_SECTION)


def _create_stair_base_surface(part):
    tolerance = 1.0e-5 * max(length, width, totalThickness)
    faces = []
    for face in part.cells.getExteriorFaces():
        point = face.pointOn[0]
        radius = math.sqrt(point[0] ** 2 + point[1] ** 2)
        if (point[2] >= repairBottom - tolerance and
                point[2] < totalThickness - tolerance and
                radius <= repairOuterRadius + tolerance):
            faces.append(face)
    part.Surface(
        name='Surf-Base-Adhesive',
        side1Faces=_face_sequence(part, faces))


def _create_stair_repair_surface(part):
    """Select only the patch boundary that remains inside the cavity."""
    tolerance = 1.0e-5 * max(length, width, totalThickness)
    localCutoff = totalThickness - adhesiveThickness
    faces = []
    for face in part.cells.getExteriorFaces():
        point = face.pointOn[0]
        if point[2] <= localCutoff + tolerance:
            faces.append(face)
    part.Surface(
        name='Surf-Repair-Adhesive',
        side1Faces=_face_sequence(part, faces))


def _coordinate_matches(value, expectedValues, tolerance):
    for expected in expectedValues:
        if abs(value - expected) <= tolerance:
            return True
    return False


def _create_stair_adhesive_surfaces(part, stairData):
    """Create outer parent-side and inner patch-side adhesive surfaces.

    The adhesive part is revolved about its local Y axis.  Local Y becomes
    global Z after the assembly rotation, so horizontal faces are identified
    by their local-Y coordinate and cylindrical faces by their radius about Y.
    """
    tolerance = 1.0e-5 * max(length, width, totalThickness)
    bounds = stairData['terraceBounds']
    outerHorizontal = bounds[:-1]
    innerHorizontal = [
        value + adhesiveThickness for value in bounds[:-1]]
    outerRadii = stairData['terraceRadii']
    innerRadii = stairData['patchRadii']
    outerFaces = []
    innerFaces = []
    foundOuterH = set()
    foundInnerH = set()
    foundOuterV = set()
    foundInnerV = set()

    for face in part.cells.getExteriorFaces():
        point = face.pointOn[0]
        normal = face.getNormal()
        if abs(normal[1]) >= 0.5:
            coordinate = point[1]
            if _coordinate_matches(
                    coordinate, outerHorizontal, tolerance):
                outerFaces.append(face)
                foundOuterH.add(round(coordinate, 8))
            elif _coordinate_matches(
                    coordinate, innerHorizontal, tolerance):
                innerFaces.append(face)
                foundInnerH.add(round(coordinate, 8))
        else:
            radius = math.sqrt(point[0] ** 2 + point[2] ** 2)
            if _coordinate_matches(radius, outerRadii, tolerance):
                outerFaces.append(face)
                foundOuterV.add(round(radius, 8))
            elif _coordinate_matches(radius, innerRadii, tolerance):
                innerFaces.append(face)
                foundInnerV.add(round(radius, 8))

    expectedCount = int(stairData['terraceCount'])
    foundCounts = (
        len(foundOuterH), len(foundInnerH),
        len(foundOuterV), len(foundInnerV))
    if (not outerFaces or not innerFaces or
            any(value != expectedCount for value in foundCounts)):
        raise ValueError(
            'Staircase adhesive surface audit failed. Expected %d horizontal '
            'and %d cylindrical coordinate families on each side; found '
            'outerH=%d, innerH=%d, outerV=%d, innerV=%d.'
            % ((expectedCount, expectedCount) + foundCounts))
    part.Surface(
        name='Surf-Adhesive-Base',
        side1Faces=_face_sequence(part, outerFaces))
    part.Surface(
        name='Surf-Adhesive-Repair',
        side1Faces=_face_sequence(part, innerFaces))

    repairData['adhesiveSurfaceAudit'] = {
        'outerHorizontalCoordinatesFound': len(foundOuterH),
        'innerHorizontalCoordinatesFound': len(foundInnerH),
        'outerCylindricalRadiiFound': len(foundOuterV),
        'innerCylindricalRadiiFound': len(foundInnerV),
        'expectedTerraces': int(stairData['terraceCount']),
    }

def _assign_orphan_mesh_orientations(
        part, setPrefix, angleByLayer):
    """Restore ply axes lost by an orphan-mesh Boolean merge."""
    for layerIndex in sorted(angleByLayer.keys()):
        setName = '%s-%02d' % (setPrefix, layerIndex)
        if setName not in part.sets:
            raise ValueError(
                'Merged mesh lost ply set %s; model creation stopped.'
                % setName)
        part.MaterialOrientation(
            region=part.sets[setName],
            orientationType=DISCRETE,
            axis=AXIS_3,
            normalAxisDefinition=VECTOR,
            normalAxisVector=(0.0, 0.0, 1.0),
            flipNormalDirection=False,
            normalAxisDirection=AXIS_3,
            primaryAxisDefinition=VECTOR,
            primaryAxisVector=(1.0, 0.0, 0.0),
            primaryAxisDirection=AXIS_1,
            flipPrimaryDirection=False,
            additionalRotationType=ROTATION_ANGLE,
            additionalRotationField='',
            angle=float(angleByLayer[layerIndex]),
            stackDirection=STACK_3)


def _create_plate_sets_and_surfaces(part):
    tolerance = 1.0e-6 * max(length, width, totalThickness)
    exteriorFaces = part.cells.getExteriorFaces()
    leftFaces = []
    rightFaces = []
    for face in exteriorFaces:
        x = face.pointOn[0][0]
        if abs(x + length / 2.0) <= tolerance:
            leftFaces.append(face)
        if abs(x - length / 2.0) <= tolerance:
            rightFaces.append(face)
    part.Surface(
        name='Surf-Left', side1Faces=_face_sequence(part, leftFaces))
    part.Surface(
        name='Surf-Right', side1Faces=_face_sequence(part, rightFaces))

    anchorOne = part.vertices.findAt(
        ((-length / 2.0, -width / 2.0, 0.0),))
    anchorTwo = part.vertices.findAt(
        ((-length / 2.0, width / 2.0, 0.0),))
    part.Set(name='Set-Anchor-1', vertices=anchorOne)
    part.Set(name='Set-Anchor-2', vertices=anchorTwo)



def _create_end_node_sets(part):
    """Create complete left/right end node sets for direct axial loading.

    The verified Golden Case applies U1 directly to every node on the two
    plate end faces.  No reference points or kinematic couplings are used.
    """
    tolerance = 1.0e-5 * max(length, width, totalThickness)
    leftNodes = part.nodes.getByBoundingBox(
        xMin=-length / 2.0 - tolerance,
        xMax=-length / 2.0 + tolerance,
        yMin=-width / 2.0 - tolerance,
        yMax=width / 2.0 + tolerance,
        zMin=-tolerance,
        zMax=totalThickness + tolerance)
    rightNodes = part.nodes.getByBoundingBox(
        xMin=length / 2.0 - tolerance,
        xMax=length / 2.0 + tolerance,
        yMin=-width / 2.0 - tolerance,
        yMax=width / 2.0 + tolerance,
        zMin=-tolerance,
        zMax=totalThickness + tolerance)

    if len(leftNodes) == 0 or len(rightNodes) == 0:
        raise ValueError(
            'Direct-BC end-node audit failed: left=%d, right=%d.'
            % (len(leftNodes), len(rightNodes)))
    # Equal left/right node counts are not required for direct end-face
    # loading.  Sweep-dominated meshes with local free-tet fallbacks can be
    # geometrically complete yet contain slightly different nodal
    # discretisations on the two end faces.  What matters is that every node
    # on each complete end face is included in its own set.
    leftCount = len(leftNodes)
    rightCount = len(rightNodes)
    countScale = float(max(leftCount, rightCount))
    countDifferenceRatio = (
        abs(leftCount - rightCount) / countScale
        if countScale > 0.0 else 0.0)

    part.Set(name='Set-Left-End', nodes=leftNodes)
    part.Set(name='Set-Right-End', nodes=rightNodes)
    modelData['leftEndNodeCount'] = leftCount
    modelData['rightEndNodeCount'] = rightCount
    modelData['endNodeCountDifferenceRatio'] = countDifferenceRatio
    modelData['endNodeCountAudit'] = (
        'complete-independent-end-sets; equality not required')

def _create_cavity_bond_surface(part, outerRadius):
    tolerance = 1.0e-5 * max(length, width)
    faces = []
    for face in part.cells.getExteriorFaces():
        point = face.pointOn[0]
        radius = math.sqrt(point[0] ** 2 + point[1] ** 2)
        if (point[2] >= repairBottom - tolerance and
                point[2] < totalThickness - tolerance and
                radius <= outerRadius + tolerance):
            faces.append(face)
    return _create_bond_surface_groups(part, faces)


def _create_repair_bond_surface(part):
    tolerance = 1.0e-5 * max(length, width)
    faces = []
    for face in part.cells.getExteriorFaces():
        point = face.pointOn[0]
        # The revolved repair's local Y axis becomes global Z after assembly
        # rotation. All exterior faces except the top are bonded.
        if point[1] < totalThickness - tolerance:
            faces.append(face)
    part.Surface(
        name='Surf-RepairBond',
        side1Faces=_face_sequence(part, faces))


def _create_repair_bond_surface_z(part):
    tolerance = 1.0e-5 * max(length, width)
    faces = []
    for face in part.cells.getExteriorFaces():
        point = face.pointOn[0]
        if point[2] < totalThickness - tolerance:
            faces.append(face)
    return _create_bond_surface_groups(part, faces)


def _create_bond_surface_groups(part, faces):
    """Create matched horizontal/cylindrical cohesive surface groups.

    A single compound general-contact pair lets a node on a horizontal stair
    face search against adjacent vertical faces (and vice versa).  At sharp
    stair corners this can create duplicate or oblique cohesive constraints.
    Pairing each coplanar/cylindrical group separately preserves the intended
    zero-thickness bond while preventing cross-face bonding.
    """
    faceSequence = _face_sequence(part, faces)
    part.Surface(name='Surf-RepairBond', side1Faces=faceSequence)
    coordinateTolerance = 1.0e-7 * max(length, width, totalThickness)
    groups = {}
    for face in faces:
        point = face.pointOn[0]
        normal = face.getNormal()
        if abs(normal[2]) >= 0.5:
            coordinate = point[2]
            family = 'H'
        else:
            coordinate = math.sqrt(point[0] ** 2 + point[1] ** 2)
            family = 'V'
        coordinateKey = int(round(coordinate / coordinateTolerance))
        key = (family, coordinateKey)
        groups.setdefault(key, []).append(face)
    surfaceNames = {}
    counters = {'H': 0, 'V': 0}
    for key in sorted(groups.keys()):
        family = key[0]
        counters[family] += 1
        surfaceName = 'Surf-RepairBond-%s-%02d' % (
            family, counters[family])
        part.Surface(
            name=surfaceName,
            side1Faces=_face_sequence(part, groups[key]))
        surfaceNames[key] = surfaceName
    return surfaceNames


def _build_stair_layer_stacks(assembly):
    """Build parent, offset patch and finite-thickness adhesive solids."""
    stairData = _stair_geometry_data()
    parentRadiusByLayer = stairData['parentRadiusByLayer']
    patchRadiusByLayer = stairData['patchRadiusByLayer']

    baseTemplates = {}
    repairTemplates = {}
    baseInstances = []
    repairInstances = []
    for layerIndex in range(1, baseLayerCount + 1):
        parentHoleRadius = parentRadiusByLayer.get(layerIndex)
        templateKey = (
            'full' if parentHoleRadius is None
            else 'hole-%.9f' % parentHoleRadius)
        if templateKey not in baseTemplates:
            baseTemplates[templateKey] = _create_plate_layer(
                'Template-Base-%02d' % len(baseTemplates),
                basePlyThickness, parentHoleRadius)
        instanceName = 'Base-Ply-%02d-1' % layerIndex
        instance = assembly.Instance(
            name=instanceName,
            part=baseTemplates[templateKey], dependent=ON)
        if layerIndex > 1:
            assembly.translate(
                instanceList=(instanceName,),
                vector=(0.0, 0.0,
                        (layerIndex - 1) * basePlyThickness))
        baseInstances.append(instance)

        if parentHoleRadius is not None:
            patchRadius = patchRadiusByLayer[layerIndex]
            repairKey = 'disc-%.9f' % patchRadius
            if repairKey not in repairTemplates:
                repairTemplates[repairKey] = _create_disc(
                    'Template-Repair-%02d' % len(repairTemplates),
                    patchRadius, basePlyThickness)
            repairName = 'Repair-Ply-%02d-1' % layerIndex
            repairInstance = assembly.Instance(
                name=repairName,
                part=repairTemplates[repairKey], dependent=ON)
            assembly.translate(
                instanceList=(repairName,),
                vector=(0.0, 0.0,
                        (layerIndex - 1) * basePlyThickness))
            repairInstances.append(repairInstance)

    assembly.InstanceFromBooleanMerge(
        name='Part-Base',
        instances=tuple(baseInstances),
        keepIntersections=ON,
        originalInstances=DELETE,
        domain=GEOMETRY)
    if 'Part-Base-1' in assembly.features:
        del assembly.features['Part-Base-1']
    assembly.InstanceFromBooleanMerge(
        name='Part-Repair',
        instances=tuple(repairInstances),
        keepIntersections=ON,
        originalInstances=DELETE,
        domain=GEOMETRY)
    if 'Part-Repair-1' in assembly.features:
        del assembly.features['Part-Repair-1']

    repairPart = model.parts['Part-Repair']
    # Split the upper cylindrical face at the parent top plane after the patch
    # translation.  This prevents the protruding patch side from entering the
    # repair-to-adhesive Tie surface.
    localTopCut = totalThickness - adhesiveThickness
    existingLayerPlanes = [
        basePlyThickness * index
        for index in range(1, baseLayerCount)]
    if all(abs(localTopCut - value) > 1.0e-8
           for value in existingLayerPlanes):
        _partition_at_z(repairPart, [localTopCut])

    adhesivePart = _create_stair_adhesive_part(stairData)
    return (
        model.parts['Part-Base'], repairPart, adhesivePart, stairData)

def _true_scarf_geometry_data():
    """Return the exact smooth parent, patch and adhesive geometry.

    The parent cavity consists of:
    * a flat circular floor at the top of the four retained parent plies;
    * a continuous 10-degree conical surface reaching the parent top face.

    The repair patch keeps fourteen full-thickness plies.  To preserve those
    ply thicknesses together with a finite adhesive layer, the patch protrudes
    above the parent top surface by ``adhesiveThickness``, exactly as in the
    verified staircase branch.

    The conical patch surface is a true parallel offset of the parent cone by
    ``adhesiveThickness`` in the surface-normal direction.  The flat patch
    floor is offset upward by the same thickness.
    """
    angle = math.radians(float(repairData['xjAngle']))
    if angle <= 0.0 or angle >= 0.5 * math.pi:
        raise ValueError('Scarf angle must lie between 0 and 90 degrees')
    if adhesiveThickness <= 0.0:
        raise ValueError('Scarf solid adhesive thickness must be positive')

    tangent = math.tan(angle)
    sine = math.sin(angle)
    cosine = math.cos(angle)
    outerRadius = damageRadius + repairDepth / tangent
    if outerRadius >= min(length, width) / 2.0:
        raise ValueError(
            'The smooth scarf repair exceeds the plate. Increase scarf '
            'angle, reduce repair depth, or enlarge the plate.')

    # Parent cone: y = m*r + b in the local revolved-part coordinates.
    slope = tangent
    intercept = repairBottom - slope * damageRadius

    # Parallel patch cone offset by the requested normal adhesive thickness.
    normalLineOffset = adhesiveThickness / cosine
    radialEndOffset = adhesiveThickness * math.tan(0.5 * angle)
    patchBottom = repairBottom + adhesiveThickness
    patchTop = totalThickness + adhesiveThickness
    patchBottomRadius = damageRadius - radialEndOffset
    patchTopRadius = outerRadius - radialEndOffset
    patchRadiusAtParentTop = (
        outerRadius - adhesiveThickness / sine)

    if patchBottomRadius <= 0.0:
        raise ValueError(
            'The adhesive offset makes the smooth scarf patch bottom radius '
            'non-positive. Reduce adhesive thickness or increase hole size.')
    if patchRadiusAtParentTop <= patchBottomRadius:
        raise ValueError('The smooth scarf patch cone is geometrically invalid')

    data = {
        'angle_rad': angle,
        'angle_deg': float(repairData['xjAngle']),
        'slope': slope,
        'intercept': intercept,
        'normalLineOffset': normalLineOffset,
        'outerRadius': outerRadius,
        'outerDiameter': 2.0 * outerRadius,
        'patchBottom': patchBottom,
        'patchTop': patchTop,
        'patchBottomRadius': patchBottomRadius,
        'patchTopRadius': patchTopRadius,
        'patchRadiusAtParentTop': patchRadiusAtParentTop,
        'radialSpan': outerRadius - damageRadius,
        # Radial movement of the smooth cone between two adjacent ply planes.
        # This is the controlling local mesh feature, not the full scarf span.
        'radialPlyPitch': basePlyThickness / tangent,
        'patchProtrusion': adhesiveThickness,
    }

    repairData['outerDiameter'] = data['outerDiameter']
    repairData['scarfRepresentation'] = (
        'true-smooth-conical-surface-solid-adhesive')
    repairData['nominalScarfAngle_deg'] = data['angle_deg']
    repairData['scarfOuterRadius'] = outerRadius
    repairData['scarfPatchBottomRadius'] = patchBottomRadius
    repairData['scarfPatchTopRadius'] = patchTopRadius
    repairData['scarfPatchRadiusAtParentTop'] = patchRadiusAtParentTop
    repairData['patchProtrusion'] = adhesiveThickness
    repairData['adhesiveNormalThickness'] = adhesiveThickness
    return data


def _true_scarf_cavity_profile(data):
    """Cutting-tool profile for the smooth parent cavity."""
    overshoot = 1.0e-4 * max(totalThickness, 1.0)
    return [
        (0.0, repairBottom),
        (damageRadius, repairBottom),
        (data['outerRadius'], totalThickness),
        (data['outerRadius'], totalThickness + overshoot),
        (0.0, totalThickness + overshoot),
        (0.0, repairBottom),
    ]


def _true_scarf_patch_profile(data):
    """Full fourteen-ply smooth conical repair profile."""
    return [
        (0.0, data['patchBottom']),
        (data['patchBottomRadius'], data['patchBottom']),
        (data['patchTopRadius'], data['patchTop']),
        (0.0, data['patchTop']),
        (0.0, data['patchBottom']),
    ]


def _true_scarf_adhesive_profile(data):
    """Closed profile of the flat-floor plus conical adhesive layer."""
    return [
        (0.0, repairBottom),
        (damageRadius, repairBottom),
        (data['outerRadius'], totalThickness),
        (data['patchRadiusAtParentTop'], totalThickness),
        (data['patchBottomRadius'], data['patchBottom']),
        (0.0, data['patchBottom']),
        (0.0, repairBottom),
    ]


def _partition_axisymmetric_quarters(part):
    """Partition a part revolved about local Y into four circumferential sectors."""
    yzPlane = part.DatumPlaneByPrincipalPlane(
        principalPlane=YZPLANE, offset=0.0)
    part.PartitionCellByDatumPlane(
        datumPlane=part.datums[yzPlane.id], cells=part.cells)
    xyPlane = part.DatumPlaneByPrincipalPlane(
        principalPlane=XYPLANE, offset=0.0)
    part.PartitionCellByDatumPlane(
        datumPlane=part.datums[xyPlane.id], cells=part.cells)


def _partition_global_z_quarters(part):
    """Partition the parent plate into four sectors about global Z.

    The two vertical symmetry planes pass through the circular scarf axis.
    This prevents the mesher from trying to wrap one very large ply cell
    around the complete conical cavity.
    """
    yzPlane = part.DatumPlaneByPrincipalPlane(
        principalPlane=YZPLANE, offset=0.0)
    part.PartitionCellByDatumPlane(
        datumPlane=part.datums[yzPlane.id], cells=part.cells)
    xzPlane = part.DatumPlaneByPrincipalPlane(
        principalPlane=XZPLANE, offset=0.0)
    part.PartitionCellByDatumPlane(
        datumPlane=part.datums[xzPlane.id], cells=part.cells)


def _build_true_scarf_geometry(assembly):
    """Create the smooth conical parent, repair and adhesive parts."""
    data = _true_scarf_geometry_data()

    baseBlank = _create_plate('Template-Scarf-Base', withHole=False)
    cavityTool = _create_revolved(
        'Template-Scarf-Cavity',
        _true_scarf_cavity_profile(data))

    baseInstance = assembly.Instance(
        name='Template-Scarf-Base-1',
        part=baseBlank, dependent=ON)
    cavityInstance = assembly.Instance(
        name='Template-Scarf-Cavity-1',
        part=cavityTool, dependent=ON)
    assembly.rotate(
        instanceList=('Template-Scarf-Cavity-1',),
        axisPoint=(0.0, 0.0, 0.0),
        axisDirection=(1.0, 0.0, 0.0),
        angle=90.0)
    assembly.regenerate()

    assembly.InstanceFromBooleanCut(
        name='Part-Base',
        instanceToBeCut=baseInstance,
        cuttingInstances=(cavityInstance,),
        originalInstances=DELETE)
    if 'Part-Base-1' in assembly.features:
        del assembly.features['Part-Base-1']

    basePart = model.parts['Part-Base']
    repairPart = _create_revolved(
        'Part-Repair', _true_scarf_patch_profile(data))
    adhesivePart = _create_revolved(
        'Part-Adhesive', _true_scarf_adhesive_profile(data))

    # Parent plies remain horizontal despite the smooth conical cut.
    _partition_at_z(
        basePart,
        [basePlyThickness * index
         for index in range(1, baseLayerCount)])
    _partition_global_z_quarters(basePart)

    # The repair keeps fourteen full-thickness horizontal plies and is split
    # at the parent top plane so only the in-cavity cone enters the Tie.
    repairPlyPlanes = [
        data['patchBottom'] + basePlyThickness * index
        for index in range(1, repairLayerCount)]
    _partition_at_y(repairPart, repairPlyPlanes)
    if all(abs(totalThickness - value) > 1.0e-8
           for value in repairPlyPlanes):
        _partition_at_y(repairPart, [totalThickness])
    _partition_axisymmetric_quarters(repairPart)

    # Split the adhesive into its flat-floor and conical portions, then into
    # four circumferential sectors to improve sweep meshing.
    _partition_at_y(adhesivePart, [data['patchBottom']])
    _partition_axisymmetric_quarters(adhesivePart)

    # Remove obsolete construction parts after the Boolean operation.
    for partName in ('Template-Scarf-Base', 'Template-Scarf-Cavity'):
        if partName in model.parts:
            del model.parts[partName]

    return basePart, repairPart, adhesivePart, data


def _true_scarf_radius_local_y(point):
    return math.sqrt(point[0] ** 2 + point[2] ** 2)


def _create_true_scarf_base_surface(part, data):
    """Create the exact parent-side flat floor and smooth cone surface."""
    tolerance = 2.0e-5 * max(
        length, width, totalThickness, data['outerRadius'])
    equationTolerance = 5.0 * tolerance
    faces = []
    floorCount = 0
    coneCount = 0
    for face in part.cells.getExteriorFaces():
        point = face.pointOn[0]
        normal = face.getNormal()
        radius = math.sqrt(point[0] ** 2 + point[1] ** 2)
        if (abs(point[2] - repairBottom) <= tolerance and
                radius <= damageRadius + tolerance and
                abs(normal[2]) >= 0.5):
            faces.append(face)
            floorCount += 1
            continue
        residual = (
            point[2] -
            (data['slope'] * radius + data['intercept']))
        if (repairBottom - tolerance <= point[2] <=
                totalThickness + tolerance and
                damageRadius - tolerance <= radius <=
                data['outerRadius'] + tolerance and
                abs(residual) <= equationTolerance and
                abs(normal[2]) < 0.99):
            faces.append(face)
            coneCount += 1
    if floorCount == 0 or coneCount == 0:
        raise ValueError(
            'Smooth scarf parent surface audit failed: floor=%d, cone=%d'
            % (floorCount, coneCount))
    part.Surface(
        name='Surf-Base-Adhesive',
        side1Faces=_face_sequence(part, faces))
    repairData['smoothScarfBaseSurfaceFaces'] = {
        'floor': floorCount, 'cone': coneCount}


def _create_true_scarf_repair_surface(part, data):
    """Create the patch-side flat floor and in-cavity smooth cone surface."""
    tolerance = 2.0e-5 * max(
        length, width, totalThickness, data['outerRadius'])
    equationTolerance = 5.0 * tolerance
    faces = []
    floorCount = 0
    coneCount = 0
    for face in part.cells.getExteriorFaces():
        point = face.pointOn[0]
        normal = face.getNormal()
        radius = _true_scarf_radius_local_y(point)
        if (abs(point[1] - data['patchBottom']) <= tolerance and
                radius <= data['patchBottomRadius'] + tolerance and
                abs(normal[1]) >= 0.5):
            faces.append(face)
            floorCount += 1
            continue
        residual = (
            point[1] -
            (data['slope'] * radius + data['intercept'] +
             data['normalLineOffset']))
        if (data['patchBottom'] - tolerance <= point[1] <=
                totalThickness + tolerance and
                data['patchBottomRadius'] - tolerance <= radius <=
                data['patchRadiusAtParentTop'] + tolerance and
                abs(residual) <= equationTolerance and
                abs(normal[1]) < 0.99):
            faces.append(face)
            coneCount += 1
    if floorCount == 0 or coneCount == 0:
        raise ValueError(
            'Smooth scarf repair surface audit failed: floor=%d, cone=%d'
            % (floorCount, coneCount))
    part.Surface(
        name='Surf-Repair-Adhesive',
        side1Faces=_face_sequence(part, faces))
    repairData['smoothScarfRepairSurfaceFaces'] = {
        'floor': floorCount, 'cone': coneCount}


def _create_true_scarf_adhesive_surfaces(part, data):
    """Create coincident parent-side and repair-side adhesive surfaces."""
    tolerance = 2.0e-5 * max(
        length, width, totalThickness, data['outerRadius'])
    equationTolerance = 5.0 * tolerance
    outerFaces = []
    innerFaces = []
    outerFloor = 0
    outerCone = 0
    innerFloor = 0
    innerCone = 0

    for face in part.cells.getExteriorFaces():
        point = face.pointOn[0]
        normal = face.getNormal()
        radius = _true_scarf_radius_local_y(point)

        if (abs(point[1] - repairBottom) <= tolerance and
                radius <= damageRadius + tolerance and
                abs(normal[1]) >= 0.5):
            outerFaces.append(face)
            outerFloor += 1
            continue

        parentResidual = (
            point[1] -
            (data['slope'] * radius + data['intercept']))
        if (repairBottom - tolerance <= point[1] <=
                totalThickness + tolerance and
                damageRadius - tolerance <= radius <=
                data['outerRadius'] + tolerance and
                abs(parentResidual) <= equationTolerance and
                abs(normal[1]) < 0.99):
            outerFaces.append(face)
            outerCone += 1
            continue

        if (abs(point[1] - data['patchBottom']) <= tolerance and
                radius <= data['patchBottomRadius'] + tolerance and
                abs(normal[1]) >= 0.5):
            innerFaces.append(face)
            innerFloor += 1
            continue

        patchResidual = (
            point[1] -
            (data['slope'] * radius + data['intercept'] +
             data['normalLineOffset']))
        if (data['patchBottom'] - tolerance <= point[1] <=
                totalThickness + tolerance and
                data['patchBottomRadius'] - tolerance <= radius <=
                data['patchRadiusAtParentTop'] + tolerance and
                abs(patchResidual) <= equationTolerance and
                abs(normal[1]) < 0.99):
            innerFaces.append(face)
            innerCone += 1

    if (outerFloor == 0 or outerCone == 0 or
            innerFloor == 0 or innerCone == 0):
        raise ValueError(
            'Smooth scarf adhesive surface audit failed: '
            'outerFloor=%d, outerCone=%d, innerFloor=%d, innerCone=%d'
            % (outerFloor, outerCone, innerFloor, innerCone))

    part.Surface(
        name='Surf-Adhesive-Base',
        side1Faces=_face_sequence(part, outerFaces))
    part.Surface(
        name='Surf-Adhesive-Repair',
        side1Faces=_face_sequence(part, innerFaces))
    repairData['smoothScarfAdhesiveSurfaceFaces'] = {
        'outerFloor': outerFloor,
        'outerCone': outerCone,
        'innerFloor': innerFloor,
        'innerCone': innerCone,
    }


def _edge_end_points(part, edge):
    """Return the two end points of an edge when available."""
    try:
        vertexIndices = edge.getVertices()
        if len(vertexIndices) != 2:
            return None
        return (
            part.vertices[vertexIndices[0]].pointOn[0],
            part.vertices[vertexIndices[1]].pointOn[0])
    except Exception:
        return None


def _seed_true_scarf_ply_connectors(part, axisIndex, radialPitch):
    """Enforce one element between adjacent horizontal ply planes.

    The connector edges on a 10-degree cone are much longer than the ply
    thickness because they also move radially by ``radialPitch``.  Selecting
    only geometrically short edges therefore misses them.  This routine uses
    the axial end-coordinate difference instead.
    """
    connectorEdges = []
    axialTolerance = 0.20 * basePlyThickness
    maximumConnectorLength = 1.35 * math.sqrt(
        basePlyThickness ** 2 + float(radialPitch) ** 2)
    for edge in part.edges:
        endPoints = _edge_end_points(part, edge)
        if endPoints is None:
            continue
        axialSpan = abs(
            endPoints[1][axisIndex] - endPoints[0][axisIndex])
        try:
            edgeLength = edge.getSize(printResults=False)
        except TypeError:
            edgeLength = edge.getSize()
        if (abs(axialSpan - basePlyThickness) <= axialTolerance and
                edgeLength <= maximumConnectorLength):
            connectorEdges.append(edge)
    if connectorEdges:
        part.seedEdgeByNumber(
            edges=connectorEdges, number=1, constraint=FIXED)
    repairData['trueScarfPlyConnectorEdgesAxis%d' % axisIndex] = (
        len(connectorEdges))


def _set_true_scarf_cell_controls(part):
    """Assign sweep controls cell-by-cell with a free-tet fallback."""
    freeCells = None
    sweepCount = 0
    freeCount = 0
    for geometryCell in part.cells:
        oneCell = part.cells[
            geometryCell.index:geometryCell.index + 1]
        try:
            part.setMeshControls(
                regions=oneCell,
                elemShape=HEX_DOMINATED,
                technique=SWEEP,
                algorithm=ADVANCING_FRONT,
                minTransition=ON)
            sweepCount += 1
        except Exception:
            freeCells = (
                oneCell if freeCells is None
                else freeCells + oneCell)
            freeCount += 1
    if freeCells is not None:
        part.setMeshControls(
            regions=freeCells, elemShape=TET, technique=FREE)
    return sweepCount, freeCount



class _OrphanMeshBuilder(object):
    """Small deterministic orphan-mesh builder for Abaqus/CAE 2024."""

    def __init__(self, part):
        self.part = part
        self.nodeByKey = {}
        self.nodes = {}
        self.elements = {}
        self.nextElementLabel = 1

    def _key(self, coordinates):
        return tuple([round(float(value), 10) for value in coordinates])

    def node(self, coordinates):
        key = self._key(coordinates)
        if key in self.nodeByKey:
            return self.nodeByKey[key]
        meshNode = self.part.Node(
            coordinates=tuple([float(value) for value in coordinates]))
        self.nodeByKey[key] = meshNode
        self.nodes[meshNode.label] = meshNode
        return meshNode

    def element(self, nodes, shape):
        meshElement = self.part.Element(
            nodes=tuple(nodes), elemShape=shape)
        self.elements[meshElement.label] = meshElement
        self.nextElementLabel = max(
            self.nextElementLabel, meshElement.label + 1)
        return meshElement


def _delete_part_if_present(partName):
    if partName in model.parts:
        del model.parts[partName]


def _element_sequence_from_labels(part, labels):
    labels = tuple(sorted(set([int(label) for label in labels])))
    if not labels:
        raise ValueError('An element-label sequence is empty')
    return part.elements.sequenceFromLabels(labels=labels)


def _node_sequence_from_labels(part, labels):
    labels = tuple(sorted(set([int(label) for label in labels])))
    if not labels:
        raise ValueError('A node-label sequence is empty')
    return part.nodes.sequenceFromLabels(labels=labels)


def _set_orphan_element_types(part, hexLabels, wedgeLabels):
    if hexLabels:
        hexType = mesh.ElemType(
            elemCode=C3D8R, elemLibrary=EXPLICIT,
            kinematicSplit=AVERAGE_STRAIN,
            secondOrderAccuracy=OFF,
            hourglassControl=DEFAULT,
            distortionControl=DEFAULT)
        part.setElementType(
            regions=(_element_sequence_from_labels(
                part, hexLabels),),
            elemTypes=(hexType,))
    if wedgeLabels:
        wedgeType = mesh.ElemType(
            elemCode=C3D6, elemLibrary=EXPLICIT)
        part.setElementType(
            regions=(_element_sequence_from_labels(
                part, wedgeLabels),),
            elemTypes=(wedgeType,))


def _create_orphan_surface(part, name, faceLabels):
    """Create an element-based surface from {faceNumber: labels}."""
    keywordArguments = {}
    for faceNumber in sorted(faceLabels.keys()):
        labels = faceLabels[faceNumber]
        if not labels:
            continue
        keywordArguments[
            'face%dElements' % int(faceNumber)] = (
                _element_sequence_from_labels(part, labels))
    if not keywordArguments:
        raise ValueError('Surface %s contains no element faces' % name)
    part.Surface(name=name, **keywordArguments)


def _assign_orphan_composite(
        part, plyElementLabels, angleByLayer, setPrefix):
    allLabels = []
    for layerIndex in sorted(plyElementLabels.keys()):
        labels = plyElementLabels[layerIndex]
        setName = '%s-%02d' % (setPrefix, layerIndex)
        part.SetFromElementLabels(
            name=setName, elementLabels=tuple(labels))
        part.SectionAssignment(
            region=part.sets[setName],
            sectionName='Section-Composite',
            offset=0.0, offsetType=MIDDLE_SURFACE,
            offsetField='',
            thicknessAssignment=FROM_SECTION)
        part.MaterialOrientation(
            region=part.sets[setName],
            orientationType=DISCRETE,
            axis=AXIS_3,
            normalAxisDefinition=VECTOR,
            normalAxisVector=(0.0, 0.0, 1.0),
            flipNormalDirection=False,
            normalAxisDirection=AXIS_3,
            primaryAxisDefinition=VECTOR,
            primaryAxisVector=(1.0, 0.0, 0.0),
            primaryAxisDirection=AXIS_1,
            flipPrimaryDirection=False,
            additionalRotationType=ROTATION_ANGLE,
            additionalRotationField='',
            angle=float(angleByLayer[layerIndex]),
            stackDirection=STACK_3)
        allLabels.extend(labels)
    part.SetFromElementLabels(
        name='Set-VUMAT', elementLabels=tuple(allLabels))


def _assign_orphan_adhesive(part, allElementLabels):
    part.SetFromElementLabels(
        name='Set-Adhesive-All',
        elementLabels=tuple(allElementLabels))
    part.SectionAssignment(
        region=part.sets['Set-Adhesive-All'],
        sectionName='Section-Adhesive',
        offset=0.0, offsetType=MIDDLE_SURFACE,
        offsetField='',
        thicknessAssignment=FROM_SECTION)


def _square_perimeter_points(halfSize, divisionsPerSide):
    """Uniform points around a square, counter-clockwise, no duplicates."""
    points = []
    count = int(divisionsPerSide)
    for index in range(count):
        value = -halfSize + 2.0 * halfSize * index / float(count)
        points.append((halfSize, value))
    for index in range(count):
        value = halfSize - 2.0 * halfSize * index / float(count)
        points.append((value, halfSize))
    for index in range(count):
        value = halfSize - 2.0 * halfSize * index / float(count)
        points.append((-halfSize, value))
    for index in range(count):
        value = -halfSize + 2.0 * halfSize * index / float(count)
        points.append((value, -halfSize))
    return points


def _linspace(first, last, divisions):
    return [
        first + (last - first) * index / float(divisions)
        for index in range(int(divisions) + 1)]



def _vector_angle_degrees(vectorOne, vectorTwo):
    dotValue = sum([
        vectorOne[index] * vectorTwo[index]
        for index in range(3)])
    normOne = math.sqrt(sum([value * value for value in vectorOne]))
    normTwo = math.sqrt(sum([value * value for value in vectorTwo]))
    if normOne <= 1.0e-14 or normTwo <= 1.0e-14:
        return 0.0
    cosine = max(-1.0, min(1.0, dotValue / (normOne * normTwo)))
    return math.degrees(math.acos(cosine))


def _quad_corner_angles_from_nodes(nodeA, nodeB, nodeC, nodeD):
    """Return the four corner angles of A-B-C-D in degrees."""
    points = [
        tuple(nodeA.coordinates),
        tuple(nodeB.coordinates),
        tuple(nodeC.coordinates),
        tuple(nodeD.coordinates),
    ]
    angles = []
    for index in range(4):
        current = points[index]
        previous = points[(index - 1) % 4]
        following = points[(index + 1) % 4]
        vectorOne = tuple([
            previous[axis] - current[axis]
            for axis in range(3)])
        vectorTwo = tuple([
            following[axis] - current[axis]
            for axis in range(3)])
        angles.append(
            _vector_angle_degrees(vectorOne, vectorTwo))
    return angles


def _scarf_quad_requires_wedge_pair(
        nodeA, nodeB, nodeC, nodeD, meshParameters):
    """Split only a radial-thickness quad that would trigger angle warnings."""
    angles = _quad_corner_angles_from_nodes(
        nodeA, nodeB, nodeC, nodeD)
    return (
        min(angles) <
        float(meshParameters['hybridMinQuadAngle'])
        or max(angles) >
        float(meshParameters['hybridMaxQuadAngle']))


def _create_positive_wedge_pair(
        builder,
        nodeA, nodeB, nodeC, nodeD,
        nodeANext, nodeBNext, nodeCNext, nodeDNext):
    """Split one skew HEX8 cell along the B-D diagonal.

    A-B-C-D is the radial-thickness quadrilateral at the current
    circumferential station.  The B-D diagonal gives much better triangular
    angles than the A-C diagonal for the present 10-degree scarf geometry.

    The node orders below have positive Jacobians for C3D6:
      wedgeOne: A-D-B  ->  A'-D'-B'
      wedgeTwo: B-D-C  ->  B'-D'-C'
    """
    wedgeOne = builder.element((
        nodeA, nodeD, nodeB,
        nodeANext, nodeDNext, nodeBNext),
        WEDGE6)
    wedgeTwo = builder.element((
        nodeB, nodeD, nodeC,
        nodeBNext, nodeDNext, nodeCNext),
        WEDGE6)
    return wedgeOne, wedgeTwo


def _structured_scarf_mesh_parameters(data):
    """Parameters for the all-hex square-core/O-grid scarf topology.

    Level 0 is now a usable audit mesh rather than an intentionally coarse
    mesh.  The in-plane far-field size is kept close to ten times the
    0.1278-mm ply thickness, which removes most generic aspect-ratio flags
    without returning to the former 0.18-mm mesh over the whole plate.
    """
    meshLevel = int(modelData['meshLevel'])

    sideDivisions = (30, 40, 52)[meshLevel]
    radialDivisions = (24, 34, 46)[meshLevel]
    extensionDivisions = (48, 66, 88)[meshLevel]
    transverseStripDivisions = (8, 12, 16)[meshLevel]

    baseCoreTransitionDivisions = (10, 14, 20)[meshLevel]
    baseBlendPower = (3.0, 3.25, 3.5)[meshLevel]
    # Positive linear floor prevents the radial-map derivative from tending
    # to zero at the outer square boundary.
    baseBlendFloor = (0.25, 0.25, 0.30)[meshLevel]

    repairTransitionDivisions = (10, 10, 10)[meshLevel]
    repairFixedRings = (2, 2, 2)[meshLevel]
    repairExpansionPower = (1.5, 1.5, 1.5)[meshLevel]

    # Abaqus reports a quadrilateral warning above 160 degrees or below
    # 10 degrees.  A small numerical margin selects exactly those highly
    # skew radial-thickness cells for conversion to two C3D6 prisms.
    hybridMinQuadAngle = 9.999
    hybridMaxQuadAngle = 159.9

    adhesiveCoreDivisions = (10, 14, 20)[meshLevel]
    adhesiveConeDivisions = (20, 28, 40)[meshLevel]

    maximumHalfSize = width / 2.0 - 1.0
    preferredHalfSize = max(
        data['outerRadius'] + 3.5, 18.0)
    oGridHalfSize = min(maximumHalfSize, preferredHalfSize)
    if oGridHalfSize <= data['outerRadius'] + 1.0:
        raise ValueError(
            'The plate is too narrow for the structured scarf O-grid. '
            'Increase plate width or scarf angle.')

    # The square core is inside the 5-mm bottom repair circle.  Its corners
    # remain well clear of that circle, leaving a regular O-grid transition.
    coreHalfSize = min(
        0.45 * damageRadius,
        damageRadius / math.sqrt(2.0) - 0.25)
    if coreHalfSize <= 0.5:
        raise ValueError('Damage radius is too small for the square O-grid core')

    return {
        'sideDivisions': sideDivisions,
        'thetaDivisions': 4 * sideDivisions,
        'radialDivisions': radialDivisions,
        'extensionDivisions': extensionDivisions,
        'transverseStripDivisions': transverseStripDivisions,
        'baseCoreTransitionDivisions': baseCoreTransitionDivisions,
        'baseBlendPower': baseBlendPower,
        'baseBlendFloor': baseBlendFloor,
        'repairTransitionDivisions': repairTransitionDivisions,
        'repairFixedRings': repairFixedRings,
        'repairExpansionPower': repairExpansionPower,
        'hybridMinQuadAngle': hybridMinQuadAngle,
        'hybridMaxQuadAngle': hybridMaxQuadAngle,
        'adhesiveCoreDivisions': adhesiveCoreDivisions,
        'adhesiveConeDivisions': adhesiveConeDivisions,
        'oGridHalfSize': oGridHalfSize,
        'coreHalfSize': coreHalfSize,
    }


def _build_structured_scarf_base(data, meshParameters):
    """Parent laminate with an all-hex square core and circular O-grid.

    The former centre fan contained one 5-mm-long wedge per sector and gave
    every retained-ply wedge an aspect ratio of about 39.  It is replaced by:
      square core -> square-to-5-mm-circle O-grid -> scarf O-grid -> far field.

    Above the retained four plies, only the true circular scarf cavity and the
    outer O-grid remain.  A nonlinear radial blend confines most cone-induced
    skew to the rings nearest the physical scarf surface.
    """
    _delete_part_if_present('Part-Base')
    part = model.Part(
        name='Part-Base',
        dimensionality=THREE_D,
        type=DEFORMABLE_BODY)
    builder = _OrphanMeshBuilder(part)

    nSide = meshParameters['sideDivisions']
    nTheta = meshParameters['thetaDivisions']
    nRadial = meshParameters['radialDivisions']
    nExtension = meshParameters['extensionDivisions']
    nStrip = meshParameters['transverseStripDivisions']
    nCoreTransition = meshParameters['baseCoreTransitionDivisions']
    blendPower = float(meshParameters['baseBlendPower'])
    blendFloor = float(meshParameters['baseBlendFloor'])
    halfOGrid = meshParameters['oGridHalfSize']
    halfCore = meshParameters['coreHalfSize']

    outerPerimeter = _square_perimeter_points(halfOGrid, nSide)
    outerAngles = [
        math.atan2(point[1], point[0])
        for point in outerPerimeter]
    corePerimeter = _square_perimeter_points(halfCore, nSide)
    coreAngles = [
        math.atan2(point[1], point[0])
        for point in corePerimeter]

    zPlanes = [
        basePlyThickness * index
        for index in range(baseLayerCount + 1)]
    retainedCount = baseLayerCount - repairLayerCount

    coordinateNodes = {}
    mainOGridNodes = {}
    coreTransitionNodes = {}

    def coordinate_node(zIndex, xValue, yValue):
        key = (
            zIndex, round(float(xValue), 10),
            round(float(yValue), 10))
        if key not in coordinateNodes:
            coordinateNodes[key] = builder.node(
                (xValue, yValue, zPlanes[zIndex]))
        return coordinateNodes[key]

    coreAxisValues = _linspace(-halfCore, halfCore, nSide)

    for zIndex, zValue in enumerate(zPlanes):
        if zValue <= repairBottom + 1.0e-10:
            innerRadius = damageRadius

            # Cartesian square core.
            for xValue in coreAxisValues:
                for yValue in coreAxisValues:
                    coordinate_node(zIndex, xValue, yValue)

            # Square core to the fixed 5-mm circle.
            for radialIndex in range(nCoreTransition + 1):
                fraction = radialIndex / float(nCoreTransition)
                for thetaIndex in range(nTheta):
                    squarePoint = corePerimeter[thetaIndex]
                    angle = coreAngles[thetaIndex]
                    circlePoint = (
                        damageRadius * math.cos(angle),
                        damageRadius * math.sin(angle))
                    xValue = (
                        squarePoint[0] +
                        fraction * (circlePoint[0] - squarePoint[0]))
                    yValue = (
                        squarePoint[1] +
                        fraction * (circlePoint[1] - squarePoint[1]))
                    coreTransitionNodes[
                        (zIndex, radialIndex, thetaIndex)] = (
                            coordinate_node(zIndex, xValue, yValue))
        else:
            innerRadius = (
                damageRadius +
                (zValue - repairBottom) /
                math.tan(data['angle_rad']))

        # Circular scarf boundary to outer square O-grid.  The nonlinear
        # fraction keeps only the inner rings strongly influenced by the
        # moving cone.
        for radialIndex in range(nRadial + 1):
            normalized = radialIndex / float(nRadial)
            localizedFraction = (
                1.0 - (1.0 - normalized) ** blendPower)
            fraction = (
                localizedFraction + blendFloor * normalized) / (
                    1.0 + blendFloor)
            for thetaIndex in range(nTheta):
                outerPoint = outerPerimeter[thetaIndex]
                angle = outerAngles[thetaIndex]
                innerPoint = (
                    innerRadius * math.cos(angle),
                    innerRadius * math.sin(angle))
                xValue = (
                    innerPoint[0] +
                    fraction * (outerPoint[0] - innerPoint[0]))
                yValue = (
                    innerPoint[1] +
                    fraction * (outerPoint[1] - innerPoint[1]))
                mainOGridNodes[
                    (zIndex, radialIndex, thetaIndex)] = (
                        coordinate_node(zIndex, xValue, yValue))

        sideValues = _linspace(-halfOGrid, halfOGrid, nSide)
        rightX = _linspace(
            halfOGrid, length / 2.0, nExtension)
        leftX = _linspace(
            -length / 2.0, -halfOGrid, nExtension)
        topY = _linspace(
            halfOGrid, width / 2.0, nStrip)
        bottomY = _linspace(
            -width / 2.0, -halfOGrid, nStrip)

        for xValue in rightX:
            for yValue in sideValues:
                coordinate_node(zIndex, xValue, yValue)
        for xValue in leftX:
            for yValue in sideValues:
                coordinate_node(zIndex, xValue, yValue)
        for yValue in topY:
            for xValue in sideValues:
                coordinate_node(zIndex, xValue, yValue)
        for yValue in bottomY:
            for xValue in sideValues:
                coordinate_node(zIndex, xValue, yValue)
        for xValue in rightX:
            for yValue in topY:
                coordinate_node(zIndex, xValue, yValue)
            for yValue in bottomY:
                coordinate_node(zIndex, xValue, yValue)
        for xValue in leftX:
            for yValue in topY:
                coordinate_node(zIndex, xValue, yValue)
            for yValue in bottomY:
                coordinate_node(zIndex, xValue, yValue)

    hexLabels = []
    wedgeLabels = []
    plyLabels = dict([
        (index, []) for index in range(1, baseLayerCount + 1)])
    floorFace2 = []
    coneFace3 = []

    def add_hex(nodeList, plyIndex):
        element = builder.element(nodeList, HEX8)
        hexLabels.append(element.label)
        plyLabels[plyIndex].append(element.label)
        return element

    for plyOffset in range(baseLayerCount):
        plyIndex = plyOffset + 1
        bottomIndex = plyOffset
        topIndex = plyOffset + 1

        # Retained-ply square core.
        if plyOffset < retainedCount:
            for xIndex in range(nSide):
                for yIndex in range(nSide):
                    x0 = coreAxisValues[xIndex]
                    x1 = coreAxisValues[xIndex + 1]
                    y0 = coreAxisValues[yIndex]
                    y1 = coreAxisValues[yIndex + 1]
                    element = add_hex((
                        coordinate_node(bottomIndex, x0, y0),
                        coordinate_node(bottomIndex, x1, y0),
                        coordinate_node(bottomIndex, x1, y1),
                        coordinate_node(bottomIndex, x0, y1),
                        coordinate_node(topIndex, x0, y0),
                        coordinate_node(topIndex, x1, y0),
                        coordinate_node(topIndex, x1, y1),
                        coordinate_node(topIndex, x0, y1)),
                        plyIndex)
                    if plyOffset == retainedCount - 1:
                        floorFace2.append(element.label)

            # Square-to-circle transition.
            for radialIndex in range(nCoreTransition):
                for thetaIndex in range(nTheta):
                    nextTheta = (thetaIndex + 1) % nTheta
                    element = add_hex((
                        coreTransitionNodes[
                            (bottomIndex, radialIndex, thetaIndex)],
                        coreTransitionNodes[
                            (bottomIndex, radialIndex + 1, thetaIndex)],
                        coreTransitionNodes[
                            (bottomIndex, radialIndex + 1, nextTheta)],
                        coreTransitionNodes[
                            (bottomIndex, radialIndex, nextTheta)],
                        coreTransitionNodes[
                            (topIndex, radialIndex, thetaIndex)],
                        coreTransitionNodes[
                            (topIndex, radialIndex + 1, thetaIndex)],
                        coreTransitionNodes[
                            (topIndex, radialIndex + 1, nextTheta)],
                        coreTransitionNodes[
                            (topIndex, radialIndex, nextTheta)]),
                        plyIndex)
                    if plyOffset == retainedCount - 1:
                        floorFace2.append(element.label)

        # Scarf circle to outer square.
        for radialIndex in range(nRadial):
            for thetaIndex in range(nTheta):
                nextTheta = (thetaIndex + 1) % nTheta

                nodeA = mainOGridNodes[
                    (bottomIndex, radialIndex, thetaIndex)]
                nodeB = mainOGridNodes[
                    (bottomIndex, radialIndex + 1, thetaIndex)]
                nodeC = mainOGridNodes[
                    (topIndex, radialIndex + 1, thetaIndex)]
                nodeD = mainOGridNodes[
                    (topIndex, radialIndex, thetaIndex)]

                nodeANext = mainOGridNodes[
                    (bottomIndex, radialIndex, nextTheta)]
                nodeBNext = mainOGridNodes[
                    (bottomIndex, radialIndex + 1, nextTheta)]
                nodeCNext = mainOGridNodes[
                    (topIndex, radialIndex + 1, nextTheta)]
                nodeDNext = mainOGridNodes[
                    (topIndex, radialIndex, nextTheta)]

                useWedges = (
                    plyOffset >= retainedCount and
                    _scarf_quad_requires_wedge_pair(
                        nodeA, nodeB, nodeC, nodeD,
                        meshParameters))

                if useWedges:
                    wedgeOne, wedgeTwo = (
                        _create_positive_wedge_pair(
                            builder,
                            nodeA, nodeB, nodeC, nodeD,
                            nodeANext, nodeBNext,
                            nodeCNext, nodeDNext))
                    wedgeLabels.extend(
                        (wedgeOne.label, wedgeTwo.label))
                    plyLabels[plyIndex].extend(
                        (wedgeOne.label, wedgeTwo.label))

                    # Wedge one S3 is the inner radial face A-A'-D'-D.
                    if radialIndex == 0:
                        coneFace3.append(wedgeOne.label)
                else:
                    element = add_hex((
                        nodeA, nodeB, nodeBNext, nodeANext,
                        nodeD, nodeC, nodeCNext, nodeDNext),
                        plyIndex)
                    if (plyOffset >= retainedCount and
                            radialIndex == 0):
                        coneFace3.append(element.label)

        sideValues = _linspace(-halfOGrid, halfOGrid, nSide)
        rightX = _linspace(
            halfOGrid, length / 2.0, nExtension)
        leftX = _linspace(
            -length / 2.0, -halfOGrid, nExtension)
        topY = _linspace(
            halfOGrid, width / 2.0, nStrip)
        bottomY = _linspace(
            -width / 2.0, -halfOGrid, nStrip)

        rectangularBlocks = (
            (rightX, sideValues),
            (leftX, sideValues),
            (sideValues, topY),
            (sideValues, bottomY),
            (rightX, topY),
            (rightX, bottomY),
            (leftX, topY),
            (leftX, bottomY),
        )
        for xValues, yValues in rectangularBlocks:
            for xIndex in range(len(xValues) - 1):
                for yIndex in range(len(yValues) - 1):
                    x0 = xValues[xIndex]
                    x1 = xValues[xIndex + 1]
                    y0 = yValues[yIndex]
                    y1 = yValues[yIndex + 1]
                    add_hex((
                        coordinate_node(bottomIndex, x0, y0),
                        coordinate_node(bottomIndex, x1, y0),
                        coordinate_node(bottomIndex, x1, y1),
                        coordinate_node(bottomIndex, x0, y1),
                        coordinate_node(topIndex, x0, y0),
                        coordinate_node(topIndex, x1, y0),
                        coordinate_node(topIndex, x1, y1),
                        coordinate_node(topIndex, x0, y1)),
                        plyIndex)

    _set_orphan_element_types(part, hexLabels, wedgeLabels)

    baseAngleMap = dict([
        (index + 1, modelData['layers'][index])
        for index in range(baseLayerCount)])
    _assign_orphan_composite(
        part, plyLabels, baseAngleMap, 'Set-Base-Ply')

    allBaseLabels = hexLabels + wedgeLabels
    part.SetFromElementLabels(
        name='Set-Base-All',
        elementLabels=tuple(allBaseLabels))

    leftNodeLabels = []
    rightNodeLabels = []
    tolerance = 1.0e-8 * max(length, width, totalThickness)
    for node in part.nodes:
        xValue = node.coordinates[0]
        if abs(xValue + length / 2.0) <= tolerance:
            leftNodeLabels.append(node.label)
        if abs(xValue - length / 2.0) <= tolerance:
            rightNodeLabels.append(node.label)
    part.SetFromNodeLabels(
        name='Set-Left-End',
        nodeLabels=tuple(leftNodeLabels))
    part.SetFromNodeLabels(
        name='Set-Right-End',
        nodeLabels=tuple(rightNodeLabels))

    anchorOne = coordinate_node(0, -length / 2.0, -width / 2.0)
    anchorTwo = coordinate_node(0, -length / 2.0, width / 2.0)
    part.SetFromNodeLabels(
        name='Set-Anchor-1',
        nodeLabels=(anchorOne.label,))
    part.SetFromNodeLabels(
        name='Set-Anchor-2',
        nodeLabels=(anchorTwo.label,))

    _create_orphan_surface(
        part, 'Surf-Base-Adhesive',
        {2: floorFace2, 3: coneFace3})

    repairData['structuredBaseMesh'] = {
        'elements': len(hexLabels) + len(wedgeLabels),
        'hexElements': len(hexLabels),
        'wedgeElements': len(wedgeLabels),
        'leftEndNodes': len(leftNodeLabels),
        'rightEndNodes': len(rightNodeLabels),
        'oGridHalfSize': halfOGrid,
        'coreHalfSize': halfCore,
        'baseBlendPower': blendPower,
        'baseBlendFloor': blendFloor,
    }
    return part


def _build_structured_scarf_repair(data, meshParameters):
    """All-hex square-core repair with outer-ring expansion control.

    The old centre fan is removed.  Interior nodes remain fixed through the
    thickness, while the required cone expansion is introduced progressively
    only in the outer transition rings.  This reduces the number of rings
    carrying the unavoidable 10-degree scarf skew.
    """
    _delete_part_if_present('Part-Repair')
    part = model.Part(
        name='Part-Repair',
        dimensionality=THREE_D,
        type=DEFORMABLE_BODY)
    builder = _OrphanMeshBuilder(part)

    nSide = meshParameters['sideDivisions']
    nTheta = meshParameters['thetaDivisions']
    nTransition = meshParameters['repairTransitionDivisions']
    fixedRings = meshParameters['repairFixedRings']
    expansionPower = float(
        meshParameters['repairExpansionPower'])
    halfCore = meshParameters['coreHalfSize']

    if fixedRings >= nTransition:
        raise ValueError(
            'Repair fixed-ring count must be smaller than '
            'repair transition-ring count')

    coreAxisValues = _linspace(-halfCore, halfCore, nSide)
    corePerimeter = _square_perimeter_points(halfCore, nSide)
    coreAngles = [
        math.atan2(point[1], point[0])
        for point in corePerimeter]

    zPlanes = [
        repairBottom + adhesiveThickness +
        basePlyThickness * index
        for index in range(repairLayerCount + 1)]

    coordinateNodes = {}
    transitionNodes = {}

    def coordinate_node(planeIndex, xValue, yValue):
        key = (
            planeIndex, round(float(xValue), 10),
            round(float(yValue), 10))
        if key not in coordinateNodes:
            coordinateNodes[key] = builder.node(
                (xValue, yValue, zPlanes[planeIndex]))
        return coordinateNodes[key]

    for planeIndex, zValue in enumerate(zPlanes):
        outerRadius = (
            damageRadius +
            planeIndex * basePlyThickness /
            math.tan(data['angle_rad']))
        expansion = outerRadius - damageRadius

        for xValue in coreAxisValues:
            for yValue in coreAxisValues:
                coordinate_node(planeIndex, xValue, yValue)

        for radialIndex in range(nTransition + 1):
            normalized = radialIndex / float(nTransition)
            if radialIndex <= fixedRings:
                expansionWeight = 0.0
            else:
                expansionWeight = (
                    (radialIndex - fixedRings) /
                    float(nTransition - fixedRings)) ** expansionPower

            for thetaIndex in range(nTheta):
                squarePoint = corePerimeter[thetaIndex]
                angle = coreAngles[thetaIndex]
                bottomCirclePoint = (
                    damageRadius * math.cos(angle),
                    damageRadius * math.sin(angle))
                baseX = (
                    squarePoint[0] +
                    normalized *
                    (bottomCirclePoint[0] - squarePoint[0]))
                baseY = (
                    squarePoint[1] +
                    normalized *
                    (bottomCirclePoint[1] - squarePoint[1]))
                xValue = (
                    baseX +
                    expansionWeight * expansion * math.cos(angle))
                yValue = (
                    baseY +
                    expansionWeight * expansion * math.sin(angle))
                transitionNodes[
                    (planeIndex, radialIndex, thetaIndex)] = (
                        coordinate_node(planeIndex, xValue, yValue))

    hexLabels = []
    wedgeLabels = []
    plyLabels = {}
    bottomFace1Hex = []
    bottomFace5Wedge = []
    coneFace5 = []

    for plyOffset in range(repairLayerCount):
        layerIndex = (
            baseLayerCount - repairLayerCount + 1 + plyOffset)
        plyLabels[layerIndex] = []
        bottomIndex = plyOffset
        topIndex = plyOffset + 1

        # Fixed square core.
        for xIndex in range(nSide):
            for yIndex in range(nSide):
                x0 = coreAxisValues[xIndex]
                x1 = coreAxisValues[xIndex + 1]
                y0 = coreAxisValues[yIndex]
                y1 = coreAxisValues[yIndex + 1]
                element = builder.element((
                    coordinate_node(bottomIndex, x0, y0),
                    coordinate_node(bottomIndex, x1, y0),
                    coordinate_node(bottomIndex, x1, y1),
                    coordinate_node(bottomIndex, x0, y1),
                    coordinate_node(topIndex, x0, y0),
                    coordinate_node(topIndex, x1, y0),
                    coordinate_node(topIndex, x1, y1),
                    coordinate_node(topIndex, x0, y1)),
                    HEX8)
                hexLabels.append(element.label)
                plyLabels[layerIndex].append(element.label)
                if plyOffset == 0:
                    bottomFace1Hex.append(element.label)

        # Square core to the true outer cone.
        for radialIndex in range(nTransition):
            for thetaIndex in range(nTheta):
                nextTheta = (thetaIndex + 1) % nTheta

                nodeA = transitionNodes[
                    (bottomIndex, radialIndex, thetaIndex)]
                nodeB = transitionNodes[
                    (bottomIndex, radialIndex + 1, thetaIndex)]
                nodeC = transitionNodes[
                    (topIndex, radialIndex + 1, thetaIndex)]
                nodeD = transitionNodes[
                    (topIndex, radialIndex, thetaIndex)]

                nodeANext = transitionNodes[
                    (bottomIndex, radialIndex, nextTheta)]
                nodeBNext = transitionNodes[
                    (bottomIndex, radialIndex + 1, nextTheta)]
                nodeCNext = transitionNodes[
                    (topIndex, radialIndex + 1, nextTheta)]
                nodeDNext = transitionNodes[
                    (topIndex, radialIndex, nextTheta)]

                useWedges = _scarf_quad_requires_wedge_pair(
                    nodeA, nodeB, nodeC, nodeD,
                    meshParameters)

                if useWedges:
                    wedgeOne, wedgeTwo = (
                        _create_positive_wedge_pair(
                            builder,
                            nodeA, nodeB, nodeC, nodeD,
                            nodeANext, nodeBNext,
                            nodeCNext, nodeDNext))
                    wedgeLabels.extend(
                        (wedgeOne.label, wedgeTwo.label))
                    plyLabels[layerIndex].extend(
                        (wedgeOne.label, wedgeTwo.label))

                    # Wedge one S5 is the horizontal bottom face.
                    if plyOffset == 0:
                        bottomFace5Wedge.append(wedgeOne.label)

                    # Wedge two S5 is the outer radial cone face.
                    if radialIndex == nTransition - 1:
                        coneFace5.append(wedgeTwo.label)
                else:
                    element = builder.element((
                        nodeA, nodeB, nodeBNext, nodeANext,
                        nodeD, nodeC, nodeCNext, nodeDNext),
                        HEX8)
                    hexLabels.append(element.label)
                    plyLabels[layerIndex].append(element.label)
                    if plyOffset == 0:
                        bottomFace1Hex.append(element.label)
                    if radialIndex == nTransition - 1:
                        coneFace5.append(element.label)

    _set_orphan_element_types(part, hexLabels, wedgeLabels)

    firstLayer = baseLayerCount - repairLayerCount + 1
    repairAngleMap = {}
    for offset, angleValue in enumerate(repairData['layers']):
        repairAngleMap[firstLayer + offset] = angleValue
    _assign_orphan_composite(
        part, plyLabels, repairAngleMap, 'Set-Repair-Ply')

    allRepairLabels = hexLabels + wedgeLabels
    part.SetFromElementLabels(
        name='Set-Repair-All',
        elementLabels=tuple(allRepairLabels))
    _create_orphan_surface(
        part, 'Surf-Repair-Adhesive',
        {1: bottomFace1Hex,
         5: bottomFace5Wedge + coneFace5})

    repairData['structuredRepairMesh'] = {
        'elements': len(hexLabels) + len(wedgeLabels),
        'hexElements': len(hexLabels),
        'wedgeElements': len(wedgeLabels),
        'coreHalfSize': halfCore,
        'fixedTransitionRings': fixedRings,
        'transitionDivisions': nTransition,
        'expansionPower': expansionPower,
    }
    return part


def _build_structured_scarf_adhesive(data, meshParameters):
    """All-hex physical adhesive with the same square-core O-grid concept."""
    _delete_part_if_present('Part-Adhesive')
    part = model.Part(
        name='Part-Adhesive',
        dimensionality=THREE_D,
        type=DEFORMABLE_BODY)
    builder = _OrphanMeshBuilder(part)

    nSide = meshParameters['sideDivisions']
    nTheta = meshParameters['thetaDivisions']
    nCore = meshParameters['adhesiveCoreDivisions']
    nCone = meshParameters['adhesiveConeDivisions']
    halfCore = meshParameters['coreHalfSize']

    coreAxisValues = _linspace(-halfCore, halfCore, nSide)
    corePerimeter = _square_perimeter_points(halfCore, nSide)
    coreAngles = [
        math.atan2(point[1], point[0])
        for point in corePerimeter]

    bottomCoordinateNodes = {}
    topCoordinateNodes = {}
    coreTransitionBottom = {}
    coreTransitionTop = {}
    coneBottom = {}
    coneTop = {}

    def bottom_node(xValue, yValue, zValue):
        key = (
            round(float(xValue), 10),
            round(float(yValue), 10),
            round(float(zValue), 10))
        if key not in bottomCoordinateNodes:
            bottomCoordinateNodes[key] = builder.node(
                (xValue, yValue, zValue))
        return bottomCoordinateNodes[key]

    def top_node(xValue, yValue, zValue):
        key = (
            round(float(xValue), 10),
            round(float(yValue), 10),
            round(float(zValue), 10))
        if key not in topCoordinateNodes:
            topCoordinateNodes[key] = builder.node(
                (xValue, yValue, zValue))
        return topCoordinateNodes[key]

    # Flat square core.
    for xValue in coreAxisValues:
        for yValue in coreAxisValues:
            bottom_node(xValue, yValue, repairBottom)
            top_node(
                xValue, yValue,
                repairBottom + adhesiveThickness)

    # Square core to the 5-mm flat-floor circle.
    for radialIndex in range(nCore + 1):
        fraction = radialIndex / float(nCore)
        for thetaIndex in range(nTheta):
            squarePoint = corePerimeter[thetaIndex]
            angle = coreAngles[thetaIndex]
            circlePoint = (
                damageRadius * math.cos(angle),
                damageRadius * math.sin(angle))
            xValue = (
                squarePoint[0] +
                fraction * (circlePoint[0] - squarePoint[0]))
            yValue = (
                squarePoint[1] +
                fraction * (circlePoint[1] - squarePoint[1]))
            coreTransitionBottom[
                (radialIndex, thetaIndex)] = bottom_node(
                    xValue, yValue, repairBottom)
            coreTransitionTop[
                (radialIndex, thetaIndex)] = top_node(
                    xValue, yValue,
                    repairBottom + adhesiveThickness)

    # 5-mm circle to the outer scarf circle.
    for radialIndex in range(nCone + 1):
        fraction = radialIndex / float(nCone)
        radius = (
            damageRadius +
            fraction * (data['outerRadius'] - damageRadius))
        bottomZ = (
            repairBottom +
            (radius - damageRadius) *
            math.tan(data['angle_rad']))
        topZ = bottomZ + adhesiveThickness
        for thetaIndex in range(nTheta):
            angle = (
                2.0 * math.pi * thetaIndex / float(nTheta))
            xValue = radius * math.cos(angle)
            yValue = radius * math.sin(angle)
            coneBottom[
                (radialIndex, thetaIndex)] = bottom_node(
                    xValue, yValue, bottomZ)
            coneTop[
                (radialIndex, thetaIndex)] = top_node(
                    xValue, yValue, topZ)

    hexLabels = []
    bottomFace1 = []
    topFace2 = []

    def add_hex(nodeList):
        element = builder.element(nodeList, HEX8)
        hexLabels.append(element.label)
        bottomFace1.append(element.label)
        topFace2.append(element.label)

    # Square core.
    for xIndex in range(nSide):
        for yIndex in range(nSide):
            x0 = coreAxisValues[xIndex]
            x1 = coreAxisValues[xIndex + 1]
            y0 = coreAxisValues[yIndex]
            y1 = coreAxisValues[yIndex + 1]
            add_hex((
                bottom_node(x0, y0, repairBottom),
                bottom_node(x1, y0, repairBottom),
                bottom_node(x1, y1, repairBottom),
                bottom_node(x0, y1, repairBottom),
                top_node(x0, y0, repairBottom + adhesiveThickness),
                top_node(x1, y0, repairBottom + adhesiveThickness),
                top_node(x1, y1, repairBottom + adhesiveThickness),
                top_node(x0, y1, repairBottom + adhesiveThickness)))

    # Square-to-circle flat floor.
    for radialIndex in range(nCore):
        for thetaIndex in range(nTheta):
            nextTheta = (thetaIndex + 1) % nTheta
            add_hex((
                coreTransitionBottom[
                    (radialIndex, thetaIndex)],
                coreTransitionBottom[
                    (radialIndex + 1, thetaIndex)],
                coreTransitionBottom[
                    (radialIndex + 1, nextTheta)],
                coreTransitionBottom[
                    (radialIndex, nextTheta)],
                coreTransitionTop[
                    (radialIndex, thetaIndex)],
                coreTransitionTop[
                    (radialIndex + 1, thetaIndex)],
                coreTransitionTop[
                    (radialIndex + 1, nextTheta)],
                coreTransitionTop[
                    (radialIndex, nextTheta)]))

    # Continuous conical adhesive.
    for radialIndex in range(nCone):
        for thetaIndex in range(nTheta):
            nextTheta = (thetaIndex + 1) % nTheta
            add_hex((
                coneBottom[(radialIndex, thetaIndex)],
                coneBottom[(radialIndex + 1, thetaIndex)],
                coneBottom[(radialIndex + 1, nextTheta)],
                coneBottom[(radialIndex, nextTheta)],
                coneTop[(radialIndex, thetaIndex)],
                coneTop[(radialIndex + 1, thetaIndex)],
                coneTop[(radialIndex + 1, nextTheta)],
                coneTop[(radialIndex, nextTheta)]))

    _set_orphan_element_types(part, hexLabels, [])
    _assign_orphan_adhesive(part, hexLabels)
    part.SetFromElementLabels(
        name='Set-Adhesive-Elements',
        elementLabels=tuple(hexLabels))

    _create_orphan_surface(
        part, 'Surf-Adhesive-Base',
        {1: bottomFace1})
    _create_orphan_surface(
        part, 'Surf-Adhesive-Repair',
        {2: topFace2})

    repairData['structuredAdhesiveMesh'] = {
        'elements': len(hexLabels),
        'hexElements': len(hexLabels),
        'wedgeElements': 0,
        'physicalThickness': adhesiveThickness,
        'coreHalfSize': halfCore,
    }
    repairData['adhesiveElementFamily'] = (
        'all-C3D8R-square-core-O-grid')
    return part


def _build_structured_true_scarf_parts(data):
    """Replace the visual geometry with deterministic structured mesh parts."""
    viewport = session.viewports['Viewport: 1']
    try:
        viewport.setValues(displayedObject=model.rootAssembly)
    except Exception:
        pass

    for partName in (
            'Part-Base', 'Part-Repair', 'Part-Adhesive'):
        _delete_part_if_present(partName)

    meshParameters = _structured_scarf_mesh_parameters(data)
    basePart = _build_structured_scarf_base(
        data, meshParameters)
    repairPart = _build_structured_scarf_repair(
        data, meshParameters)
    adhesivePart = _build_structured_scarf_adhesive(
        data, meshParameters)

    repairData['trueScarfMeshMode'] = (
        'hybrid-C3D8R-C3D6-scarf-solid-adhesive-v3.4')
    repairData['trueScarfMeshParameters'] = meshParameters
    return basePart, repairPart, adhesivePart


def _mesh_true_scarf_base(part, data):
    """Locally refined parent mesh for a smooth ply-intersecting cone.

    Version 2.0 used the complete scarf radial span as the refinement feature,
    producing a local edge size larger than the 0.724-mm radial movement of
    the cone from one ply to the next.  The resulting elements crossed several
    cone/ply intersections and generated zero or negative volumes.

    Version 2.1 uses four elements across each radial ply pitch and quarters
    the geometry about the scarf axis.
    """
    meshSizes = (3.0, 2.0, 1.2)
    meshSize = meshSizes[int(modelData['meshLevel'])]
    radialPitch = float(data['radialPlyPitch'])
    # Audit-mesh mode: about two elements across one radial ply pitch at
    # mesh level 0.  The quarter partitions and one-element ply connectors
    # are retained, but the former ~0.18-mm local seed is relaxed to
    # approximately 0.36 mm for the 10-degree baseline.
    localDivisions = (2.0, 2.75, 3.5)[int(modelData['meshLevel'])]
    localSeedSize = min(
        meshSize * 0.45,
        radialPitch / localDivisions)

    hexType = mesh.ElemType(
        elemCode=C3D8R, elemLibrary=EXPLICIT,
        kinematicSplit=AVERAGE_STRAIN,
        secondOrderAccuracy=OFF,
        hourglassControl=DEFAULT,
        distortionControl=DEFAULT)
    wedgeType = mesh.ElemType(
        elemCode=C3D6, elemLibrary=EXPLICIT)
    tetType = mesh.ElemType(
        elemCode=C3D4, elemLibrary=EXPLICIT)
    part.setElementType(
        regions=(part.cells,),
        elemTypes=(hexType, wedgeType, tetType))

    sweepCount, freeCount = _set_true_scarf_cell_controls(part)
    part.seedPart(
        size=meshSize, deviationFactor=0.08, minSizeFactor=0.05)

    localEdges = []
    localLimit = data['outerRadius'] + 1.5 * radialPitch
    for edge in part.edges:
        point = edge.pointOn[0]
        radius = math.sqrt(point[0] ** 2 + point[1] ** 2)
        if radius <= localLimit:
            localEdges.append(edge)
    if localEdges:
        part.seedEdgeBySize(
            edges=localEdges,
            size=localSeedSize,
            deviationFactor=0.05,
            minSizeFactor=0.03,
            constraint=FINER)

    _seed_true_scarf_ply_connectors(
        part, axisIndex=2, radialPitch=radialPitch)
    part.generateMesh()
    if len(part.elements) == 0:
        raise RuntimeError('True scarf parent mesh produced no elements')

    repairData['trueScarfBaseMesh'] = {
        'localSeedSize': localSeedSize,
        'sweepCells': sweepCount,
        'freeTetCells': freeCount,
        'elements': len(part.elements),
    }


def _mesh_revolved_composite_part(part, localRadius, localFeatureSize):
    """Quartered, ply-conforming mesh for the true conical repair."""
    meshSizes = (3.0, 2.0, 1.2)
    meshSize = meshSizes[int(modelData['meshLevel'])]
    radialPitch = float(localFeatureSize)
    localDivisions = (2.0, 2.75, 3.5)[int(modelData['meshLevel'])]
    localSeedSize = min(
        meshSize * 0.45,
        radialPitch / localDivisions)

    hexType = mesh.ElemType(
        elemCode=C3D8R, elemLibrary=EXPLICIT,
        kinematicSplit=AVERAGE_STRAIN,
        secondOrderAccuracy=OFF,
        hourglassControl=DEFAULT,
        distortionControl=DEFAULT)
    wedgeType = mesh.ElemType(
        elemCode=C3D6, elemLibrary=EXPLICIT)
    tetType = mesh.ElemType(
        elemCode=C3D4, elemLibrary=EXPLICIT)
    part.setElementType(
        regions=(part.cells,),
        elemTypes=(hexType, wedgeType, tetType))

    sweepCount, freeCount = _set_true_scarf_cell_controls(part)
    part.seedPart(
        size=meshSize, deviationFactor=0.08, minSizeFactor=0.05)

    localEdges = []
    localLimit = float(localRadius) + 1.5 * radialPitch
    for edge in part.edges:
        point = edge.pointOn[0]
        radius = math.sqrt(point[0] ** 2 + point[2] ** 2)
        if radius <= localLimit:
            localEdges.append(edge)
    if localEdges:
        part.seedEdgeBySize(
            edges=localEdges,
            size=localSeedSize,
            deviationFactor=0.05,
            minSizeFactor=0.03,
            constraint=FINER)

    _seed_true_scarf_ply_connectors(
        part, axisIndex=1, radialPitch=radialPitch)
    part.generateMesh()
    if len(part.elements) == 0:
        raise RuntimeError('Smooth scarf repair mesh produced no elements')

    repairData['trueScarfRepairMesh'] = {
        'localSeedSize': localSeedSize,
        'sweepCells': sweepCount,
        'freeTetCells': freeCount,
        'elements': len(part.elements),
    }


def _mesh_true_scarf_adhesive(part, data):
    """Sweep-dominated mesh for the smooth flat-plus-conical adhesive."""
    meshSizes = (3.0, 2.0, 1.2)
    meshSize = meshSizes[int(modelData['meshLevel'])]
    featureDivisions = (2.5, 3.5, 4.5)[
        int(modelData['meshLevel'])]
    inPlaneSize = min(
        meshSize * 0.35,
        data['radialPlyPitch'] / featureDivisions)

    hexType = mesh.ElemType(
        elemCode=C3D8R, elemLibrary=EXPLICIT)
    wedgeType = mesh.ElemType(
        elemCode=C3D6, elemLibrary=EXPLICIT)
    tetType = mesh.ElemType(
        elemCode=C3D4, elemLibrary=EXPLICIT)
    part.setElementType(
        regions=(part.cells,),
        elemTypes=(hexType, wedgeType, tetType))

    freeCells = None
    for geometryCell in part.cells:
        oneCell = part.cells[
            geometryCell.index:geometryCell.index + 1]
        try:
            part.setMeshControls(
                regions=oneCell,
                elemShape=HEX_DOMINATED,
                technique=SWEEP,
                algorithm=ADVANCING_FRONT,
                minTransition=ON)
        except Exception:
            freeCells = oneCell if freeCells is None else freeCells + oneCell
    if freeCells is not None:
        part.setMeshControls(
            regions=freeCells, elemShape=TET, technique=FREE)

    part.seedPart(
        size=inPlaneSize, deviationFactor=0.05, minSizeFactor=0.03)

    shortEdges = []
    shortLimit = 1.35 * adhesiveThickness
    for edge in part.edges:
        try:
            edgeLength = edge.getSize(printResults=False)
        except TypeError:
            edgeLength = edge.getSize()
        if edgeLength <= shortLimit:
            shortEdges.append(edge)
    if shortEdges:
        part.seedEdgeByNumber(
            edges=shortEdges, number=1, constraint=FIXED)

    part.generateMesh()
    if len(part.elements) == 0:
        raise RuntimeError(
            'Smooth scarf solid adhesive mesh produced no elements')

    elementTypes = sorted(set([
        str(element.type).upper() for element in part.elements]))
    repairData['adhesiveElementFamily'] = (
        'smooth-scarf-sweep-dominated-' + '-'.join(elementTypes))
    repairData['trueScarfAdhesiveMesh'] = {
        'inPlaneSize': inPlaneSize,
        'elements': len(part.elements),
        'elementTypes': elementTypes,
    }


def _create_patch_surfaces(part, partDepth):
    tolerance = 1.0e-6 * max(
        totalThickness, repairDepth, float(partDepth))
    bottomFaces = []
    topFaces = []
    for face in part.cells.getExteriorFaces():
        z = face.pointOn[0][2]
        if abs(z) <= tolerance:
            bottomFaces.append(face)
        if abs(z - float(partDepth)) <= tolerance:
            topFaces.append(face)
    part.Surface(
        name='Surf-Bottom',
        side1Faces=_face_sequence(part, bottomFaces))
    part.Surface(
        name='Surf-Top',
        side1Faces=_face_sequence(part, topFaces))


def _create_plate_top_bottom_surfaces(part):
    tolerance = 1.0e-6 * max(totalThickness, repairDepth)
    bottomFaces = []
    topFaces = []
    for face in part.cells.getExteriorFaces():
        z = face.pointOn[0][2]
        if abs(z) <= tolerance:
            bottomFaces.append(face)
        if abs(z - totalThickness) <= tolerance:
            topFaces.append(face)
    part.Surface(
        name='Surf-PlateBottom',
        side1Faces=_face_sequence(part, bottomFaces))
    part.Surface(
        name='Surf-PlateTop',
        side1Faces=_face_sequence(part, topFaces))


def _mesh_part(part, localRadius=None, localFeatureSize=None):
    meshSizes = (3.0, 2.0, 1.2)
    meshSize = meshSizes[int(modelData['meshLevel'])]
    hexType = mesh.ElemType(
        elemCode=C3D8R, elemLibrary=EXPLICIT,
        kinematicSplit=AVERAGE_STRAIN,
        secondOrderAccuracy=OFF,
        hourglassControl=DEFAULT,
        distortionControl=DEFAULT)
    wedgeType = mesh.ElemType(
        elemCode=C3D6, elemLibrary=EXPLICIT)
    tetType = mesh.ElemType(
        elemCode=C3D4, elemLibrary=EXPLICIT)
    part.setElementType(
        regions=(part.cells,),
        elemTypes=(hexType, wedgeType, tetType))
    # Every ply is a thin cell bounded by two parallel ply surfaces. Sweeping
    # that cell produces one well-shaped element through the ply instead of
    # the sliver tetrahedra created by a global free mesh.
    freeCells = None
    for geometryCell in part.cells:
        oneCell = part.cells[
            geometryCell.index:geometryCell.index + 1]
        try:
            part.setMeshControls(
                regions=oneCell,
                elemShape=HEX_DOMINATED,
                technique=SWEEP,
                algorithm=ADVANCING_FRONT,
                minTransition=ON)
        except Exception:
            freeCells = oneCell if freeCells is None else freeCells + oneCell
    if freeCells is not None:
        part.setMeshControls(
            regions=freeCells, elemShape=TET, technique=FREE)
    part.seedPart(
        size=meshSize, deviationFactor=0.1, minSizeFactor=0.15)
    if localRadius is not None:
        localEdges = []
        localLimit = localRadius + 2.0 * meshSize
        for edge in part.edges:
            point = edge.pointOn[0]
            if math.sqrt(point[0] ** 2 + point[1] ** 2) <= localLimit:
                localEdges.append(edge)
        if localEdges:
            localSeedSize = meshSize * 0.55
            if localFeatureSize is not None:
                featureDivisions = (2.0, 3.0, 5.0)[
                    int(modelData['meshLevel'])]
                localSeedSize = min(
                    localSeedSize,
                    float(localFeatureSize) / featureDivisions)
            part.seedEdgeBySize(
                edges=localEdges,
                size=localSeedSize,
                deviationFactor=0.1,
                minSizeFactor=0.15,
                constraint=FINER)
    part.generateMesh()



def _mesh_adhesive_part(part, stairData):
    """Free-tetra mesh the first-version thin solid adhesive.

    The complete stepped adhesive is generated as one revolved cell with a
    re-entrant staircase cross-section.  Abaqus/CAE 2021 does not classify
    this cell as sweepable and raises ``部分区域无法被扫掠/旋转`` when SWEEP is
    assigned.  For the first linear-elastic, no-failure adhesive model, use a
    robust C3D4 free mesh instead.  This keeps the geometry and both Tie
    interfaces intact and is suitable for the initial load-transfer check.

    A later mesh-refinement version can partition the adhesive into simple
    annular cells and recover C3D8R/C3D6.  Do not interpret local adhesive peak
    stresses from this provisional tetrahedral mesh without a convergence
    study.
    """
    meshSizes = (3.0, 2.0, 1.2)
    meshSize = meshSizes[int(modelData['meshLevel'])]
    featureDivisions = (2.0, 3.0, 5.0)[int(modelData['meshLevel'])]
    inPlaneSize = min(
        meshSize * 0.55,
        float(stairData['radialIncrement']) / featureDivisions)

    tetType = mesh.ElemType(
        elemCode=C3D4, elemLibrary=EXPLICIT)
    part.setElementType(
        regions=(part.cells,), elemTypes=(tetType,))
    part.setMeshControls(
        regions=part.cells, elemShape=TET, technique=FREE)
    part.seedPart(
        size=inPlaneSize, deviationFactor=0.1, minSizeFactor=0.10)

    # Force a single division along every true 0.15-mm adhesive-thickness
    # edge.  The free tetra mesher may still introduce internal diagonals, but
    # it will not create an artificial multi-layer seed along these boundaries.
    thinEdges = []
    edgeLimit = 1.25 * adhesiveThickness
    for edge in part.edges:
        try:
            edgeLength = edge.getSize(printResults=False)
        except TypeError:
            edgeLength = edge.getSize()
        if edgeLength <= edgeLimit:
            thinEdges.append(edge)
    if thinEdges:
        part.seedEdgeByNumber(
            edges=thinEdges, number=1, constraint=FIXED)
    part.generateMesh()
    if len(part.elements) == 0:
        raise RuntimeError('Solid adhesive mesh generation produced no elements')
    repairData['adhesiveElementFamily'] = 'C3D4-free-tetra-v1.1'


def _mesh_flat_adhesive_part(part, radialOverlap):
    """Structured C3D8R mesh for a thin annular patch adhesive.

    The annulus is already partitioned into four sweepable sectors.  One
    element is enforced through the 0.15-mm thickness; the radial and
    circumferential mesh density follows the selected global mesh level.
    """
    meshSizes = (3.0, 2.0, 1.2)
    meshSize = meshSizes[int(modelData['meshLevel'])]
    featureDivisions = (3.0, 4.0, 6.0)[int(modelData['meshLevel'])]
    inPlaneSize = min(
        meshSize * 0.55,
        float(radialOverlap) / featureDivisions)

    hexType = mesh.ElemType(
        elemCode=C3D8R, elemLibrary=EXPLICIT)
    part.setElementType(
        regions=(part.cells,), elemTypes=(hexType,))

    try:
        part.setMeshControls(
            regions=part.cells, elemShape=HEX, technique=STRUCTURED)
    except Exception:
        part.setMeshControls(
            regions=part.cells, elemShape=HEX, technique=SWEEP)

    part.seedPart(
        size=inPlaneSize, deviationFactor=0.1, minSizeFactor=0.10)

    thicknessEdges = []
    edgeLimit = 1.25 * adhesiveThickness
    for edge in part.edges:
        try:
            edgeLength = edge.getSize(printResults=False)
        except TypeError:
            edgeLength = edge.getSize()
        if edgeLength <= edgeLimit:
            thicknessEdges.append(edge)
    if not thicknessEdges:
        raise RuntimeError(
            'No through-thickness adhesive edges were identified')
    part.seedEdgeByNumber(
        edges=thicknessEdges, number=1, constraint=FIXED)

    part.generateMesh()
    if len(part.elements) == 0:
        raise RuntimeError(
            'Structured annular adhesive mesh produced no elements')
    # Abaqus returns element.type as a SymbolicConstant in some releases.
    # Its printed form is C3D8R, but it is not equal to the Python string
    # 'C3D8R'.  Normalize to text before validating the generated mesh.
    elementTypes = set([
        str(element.type).upper() for element in part.elements])
    if elementTypes != set(['C3D8R']):
        raise RuntimeError(
            'Annular adhesive mesh must contain only C3D8R elements; '
            'generated types: %s' % sorted(elementTypes))


def _clear_part_mesh(part):
    """Remove a previous or partially generated mesh before a retry."""
    if len(part.elements) == 0 and len(part.nodes) == 0:
        return
    try:
        part.deleteMesh(regions=part.cells)
    except Exception:
        try:
            part.deleteMesh()
        except Exception:
            pass


def _delete_named_repository_items(repository, names):
    for name in names:
        if name in repository:
            del repository[name]


def _clear_scarf_analysis_features():
    """Clear prior scarf instances/interactions/analysis before remeshing."""
    _delete_named_repository_items(
        model.interactions,
        ('Tie-Base-Adhesive', 'Tie-Repair-Adhesive'))
    _delete_named_repository_items(
        model.boundaryConditions,
        ('BC-Left-Axial', 'BC-Anchor-1', 'BC-Anchor-2', 'BC-Right'))
    if 'Amp-Loading' in model.amplitudes:
        del model.amplitudes['Amp-Loading']
    for name in ('F-Output-Damage', 'F-Output-Stress'):
        if name in model.fieldOutputRequests:
            del model.fieldOutputRequests[name]
    if 'H-Energy' in model.historyOutputRequests:
        del model.historyOutputRequests['H-Energy']
    if 'Step-1' in model.steps:
        del model.steps['Step-1']

    localAssembly = model.rootAssembly
    for featureName in (
            'Part-Base-1', 'Part-Repair-1', 'Part-Adhesive-1'):
        if featureName in localAssembly.features:
            del localAssembly.features[featureName]
    if 'Set-VUMAT-All' in localAssembly.sets:
        del localAssembly.sets['Set-VUMAT-All']
    localAssembly.regenerate()


def _create_tie(name, secondarySurface, mainSurface):
    model.Tie(
        name=name,
        main=mainSurface,
        secondary=secondarySurface,
        positionToleranceMethod=COMPUTED,
        adjust=OFF,
        tieRotations=ON,
        thickness=ON)

def _merge_bonded_mesh(assembly, baseInstance, repairInstance):
    """Merge coincident lap nodes for a constraint-free perfect bond."""
    assembly.InstanceFromBooleanMerge(
        name='Part-Bonded',
        instances=(baseInstance, repairInstance),
        keepIntersections=ON,
        originalInstances=DELETE,
        domain=MESH,
        mergeNodes=BOUNDARY_ONLY,
        nodeMergingTolerance=(
            1.0e-6 * max(length, width, totalThickness)))
    return assembly.instances['Part-Bonded-1']


def _create_contact(name, secondary, main):
    # Abaqus/Explicit 2021 supports surface-based cohesive behavior through
    # general contact, not through *CONTACT PAIR.  For cohesive behavior the
    # first surface is the secondary surface and the second is the main
    # surface.  Contact inclusions are restricted to the actual bonded pair.
    # Abaqus/CAE still requires one global default-property assignment before
    # specific assignments; that assignment does not add extra included pairs.
    interactionName = 'Int-General-Cohesive'
    if interactionName not in model.interactions:
        model.ContactExp(
            name=interactionName, createStepName='Initial')
        model.interactions[
            interactionName].contactPropertyAssignments.appendInStep(
                stepName='Initial',
                assignments=((GLOBAL, SELF, 'IntProp-DefaultContact'),))
    interaction = model.interactions[interactionName]
    interaction.includedPairs.setValuesInStep(
        stepName='Initial', addPairs=((secondary, main),))
    interaction.contactPropertyAssignments.appendInStep(
        stepName='Initial',
        assignments=((secondary, main, 'IntProp-CohesiveRepair'),))


def _create_grouped_contacts(
        namePrefix, secondaryInstance, mainInstance,
        secondarySurfaceNames, mainSurfaceNames, activeFamilies=None,
        useTie=False):
    secondaryKeys = set(secondarySurfaceNames.keys())
    mainKeys = set(mainSurfaceNames.keys())
    if activeFamilies is not None:
        activeFamilies = set(activeFamilies)
        secondaryKeys = set([
            key for key in secondaryKeys if key[0] in activeFamilies])
        mainKeys = set([
            key for key in mainKeys if key[0] in activeFamilies])
    matchedKeys = []
    unusedMainKeys = set(mainKeys)
    for secondaryKey in sorted(secondaryKeys):
        candidates = [
            mainKey for mainKey in unusedMainKeys
            if mainKey[0] == secondaryKey[0]]
        if not candidates:
            matchedKeys = []
            break
        mainKey = min(
            candidates,
            key=lambda candidate: abs(candidate[1] - secondaryKey[1]))
        # Boolean merging can move the representative point of coincident
        # faces across one rounding boundary. Adjacent physical stair/scarf
        # faces are many thousands of key units apart, so a two-unit matching
        # tolerance is both safe and insensitive to this CAD round-off.
        if abs(mainKey[1] - secondaryKey[1]) > 2:
            matchedKeys = []
            break
        matchedKeys.append((secondaryKey, mainKey))
        unusedMainKeys.remove(mainKey)
    if (not matchedKeys or len(matchedKeys) != len(secondaryKeys) or
            unusedMainKeys):
        raise ValueError(
            'Repair bond faces do not match within the geometry tolerance. '
            'Repair groups: %s; base groups: %s'
            % (sorted(secondaryKeys), sorted(mainKeys)))
    for index, keyPair in enumerate(matchedKeys):
        secondaryKey, mainKey = keyPair
        secondarySurface = secondaryInstance.surfaces[
            secondarySurfaceNames[secondaryKey]]
        mainSurface = mainInstance.surfaces[mainSurfaceNames[mainKey]]
        interactionName = '%s-%02d' % (namePrefix, index + 1)
        if useTie:
            model.Tie(
                name=interactionName,
                main=mainSurface,
                secondary=secondarySurface,
                positionToleranceMethod=COMPUTED,
                adjust=OFF,
                tieRotations=ON,
                thickness=ON)
        else:
            _create_contact(
                interactionName, secondarySurface, mainSurface)


def _create_step_bc_and_output(assembly, baseInstance):
    """Create the verified direct-end displacement loading definition.

    Both plate end faces are loaded through their complete node sets.  The
    former left/right reference points and axial kinematic couplings are not
    created because their unused degrees of freedom caused singular rigid
    modes in the earlier model.
    """
    stepTime = float(modelData['stepTime'])
    model.ExplicitDynamicsStep(
        name='Step-1', previous='Initial',
        timePeriod=stepTime, nlgeom=OFF, improvedDtMethod=ON)
    model.steps['Step-1'].setValues(
        massScaling=((
            SEMI_AUTOMATIC, MODEL, AT_BEGINNING, 1.0,
            float(modelData['targetTimeIncrement']), BELOW_MIN,
            0, 0, 0.0, 0.0, 0, None),),
        improvedDtMethod=ON)

    if 'Set-Left-End' not in baseInstance.sets:
        raise ValueError('Part-Base-1.Set-Left-End was not created')
    if 'Set-Right-End' not in baseInstance.sets:
        raise ValueError('Part-Base-1.Set-Right-End was not created')

    model.DisplacementBC(
        name='BC-Left-Axial',
        createStepName='Initial',
        region=baseInstance.sets['Set-Left-End'],
        u1=0.0, u2=UNSET, u3=UNSET,
        ur1=UNSET, ur2=UNSET, ur3=UNSET)
    model.DisplacementBC(
        name='BC-Anchor-1',
        createStepName='Initial',
        region=baseInstance.sets['Set-Anchor-1'],
        u1=UNSET, u2=0.0, u3=0.0,
        ur1=UNSET, ur2=UNSET, ur3=UNSET)
    model.DisplacementBC(
        name='BC-Anchor-2',
        createStepName='Initial',
        region=baseInstance.sets['Set-Anchor-2'],
        u1=UNSET, u2=UNSET, u3=0.0,
        ur1=UNSET, ur2=UNSET, ur3=UNSET)

    model.SmoothStepAmplitude(
        name='Amp-Loading', timeSpan=STEP,
        data=((0.0, 0.0), (stepTime, 1.0)))
    loadDisplacement = float(modelData['disValue'])
    if int(modelData['pressBC']):
        loadDisplacement = -loadDisplacement
    model.DisplacementBC(
        name='BC-Right',
        createStepName='Step-1',
        region=baseInstance.sets['Set-Right-End'],
        u1=loadDisplacement,
        u2=UNSET, u3=UNSET,
        ur1=UNSET, ur2=UNSET, ur3=UNSET,
        amplitude='Amp-Loading')

    # Abaqus/CAE 2021-compatible Golden-Case output strategy.
    #
    # CAE 2021 can reject a request containing individual SDV identifiers
    # (SDV1, SDV2, ... SDV34) while the model is being created, even though
    # these identifiers are valid in an input-file *ELEMENT OUTPUT block.
    # Use the aggregate, CAE-validated identifier SDV here.  Selective SDV
    # output will be reintroduced later through controlled keyword editing.
    fieldIntervals = max(5, int(modelData['fieldIntervals']))
    reducedIntervals = max(5, int(round(fieldIntervals / 3.0)))

    model.fieldOutputRequests['F-Output-1'].setValues(
        variables=('U', 'RF', 'STATUS'),
        numIntervals=fieldIntervals)

    allVumatElements = None
    for instance in assembly.instances.values():
        if 'Set-VUMAT' not in instance.sets:
            continue
        elements = instance.sets['Set-VUMAT'].elements
        allVumatElements = (
            elements if allVumatElements is None
            else allVumatElements + elements)
    if allVumatElements is None:
        raise ValueError('No VUMAT element set was found in the assembly')
    assembly.Set(name='Set-VUMAT-All', elements=allVumatElements)

    model.FieldOutputRequest(
        name='F-Output-Damage',
        createStepName='Step-1',
        variables=('SDV',),
        region=assembly.sets['Set-VUMAT-All'],
        numIntervals=reducedIntervals)

    # This validated baseline uses nlgeom=OFF.  Abaqus/Explicit therefore
    # outputs total strain E rather than logarithmic strain LE.  Request E
    # directly to avoid repeated preprocessing warnings.
    model.FieldOutputRequest(
        name='F-Output-Stress',
        createStepName='Step-1',
        variables=('S', 'E'),
        numIntervals=reducedIntervals)

    if 'H-Output-1' in model.historyOutputRequests:
        del model.historyOutputRequests['H-Output-1']

    # The direct-end force/displacement curve will be reconstructed from
    # high-frequency field output by the later post-processing revision.
    # Do not request one history region per right-end node.
    model.HistoryOutputRequest(
        name='H-Energy',
        createStepName='Step-1',
        variables=(
            'ALLIE', 'ALLKE', 'ALLSE', 'ALLAE', 'ALLDMD',
            'ALLVD', 'ALLFD', 'ALLPD', 'ALLPW', 'ALLCW',
            'ALLMW', 'ALLDC', 'ALLWK', 'ETOTAL'),
        numIntervals=max(50, int(modelData['historyIntervals'])))


if buildStage != 'mesh':
    _create_materials_and_section()
assembly = model.rootAssembly
if buildStage != 'mesh':
    assembly.DatumCsysByDefault(CARTESIAN)

basePart = None
repairPart = None
baseInstance = None

if repairType == 1:
    basePart, repairPart, adhesivePart, stairData = (
        _build_stair_layer_stacks(assembly))

    baseGroups = _layer_groups(
        basePart, 2, 1, baseLayerCount, basePlyThickness)
    repairGroups = _layer_groups(
        repairPart, 2,
        baseLayerCount - repairLayerCount + 1,
        baseLayerCount, basePlyThickness)
    baseAngleMap = dict(
        [(index + 1, modelData['layers'][index])
         for index in range(baseLayerCount)])
    repairAngleMap = {}
    firstRepairLayer = baseLayerCount - repairLayerCount + 1
    for offset, angle in enumerate(repairData['layers']):
        repairAngleMap[firstRepairLayer + offset] = angle
    _assign_layers(
        basePart, baseGroups, baseAngleMap, 2,
        setPrefix='Set-Base-Ply')
    _assign_layers(
        repairPart, repairGroups, repairAngleMap, 2,
        setPrefix='Set-Repair-Ply')
    _assign_adhesive_section(adhesivePart)

    _create_plate_sets_and_surfaces(basePart)
    _create_stair_base_surface(basePart)
    _create_stair_repair_surface(repairPart)
    _create_stair_adhesive_surfaces(adhesivePart, stairData)

    stairRadialFeature = stairData['radialIncrement']
    _mesh_part(basePart, repairOuterRadius, stairRadialFeature)
    _create_end_node_sets(basePart)
    _mesh_part(repairPart, repairOuterRadius, stairRadialFeature)
    _mesh_adhesive_part(adhesivePart, stairData)

    basePart.Set(name='Set-Base-All', elements=basePart.elements)
    repairPart.Set(name='Set-Repair-All', elements=repairPart.elements)
    adhesivePart.Set(
        name='Set-Adhesive-Elements', elements=adhesivePart.elements)

    baseInstance = assembly.Instance(
        name='Part-Base-1', part=basePart, dependent=ON)
    repairInstance = assembly.Instance(
        name='Part-Repair-1', part=repairPart, dependent=ON)
    adhesiveInstance = assembly.Instance(
        name='Part-Adhesive-1', part=adhesivePart, dependent=ON)
    assembly.translate(
        instanceList=('Part-Repair-1',),
        vector=(0.0, 0.0, adhesiveThickness))
    # The adhesive was revolved about local Y.  Rotate local Y onto global Z.
    assembly.rotate(
        instanceList=('Part-Adhesive-1',),
        axisPoint=(0.0, 0.0, 0.0),
        axisDirection=(1.0, 0.0, 0.0),
        angle=90.0)
    assembly.regenerate()

    _create_tie(
        'Tie-Base-Adhesive',
        adhesiveInstance.surfaces['Surf-Adhesive-Base'],
        baseInstance.surfaces['Surf-Base-Adhesive'])
    _create_tie(
        'Tie-Repair-Adhesive',
        adhesiveInstance.surfaces['Surf-Adhesive-Repair'],
        repairInstance.surfaces['Surf-Repair-Adhesive'])

elif repairType == 2:
    scarfData = _true_scarf_geometry_data()

    if buildStage in ('full', 'geometry'):
        basePart, repairPart, adhesivePart, scarfData = (
            _build_true_scarf_geometry(assembly))

        baseGroups = _layer_groups(
            basePart, 2, 1, baseLayerCount, basePlyThickness)
        firstRepairLayer = baseLayerCount - repairLayerCount + 1
        repairGroups = _layer_groups_from_origin(
            repairPart, 1, firstRepairLayer, repairLayerCount,
            basePlyThickness, scarfData['patchBottom'])

        baseAngleMap = dict(
            [(index + 1, modelData['layers'][index])
             for index in range(baseLayerCount)])
        repairAngleMap = {}
        for offset, angleValue in enumerate(repairData['layers']):
            repairAngleMap[firstRepairLayer + offset] = angleValue

        _assign_layers(
            basePart, baseGroups, baseAngleMap, 2,
            setPrefix='Set-Base-Ply')
        _assign_layers(
            repairPart, repairGroups, repairAngleMap, 1,
            setPrefix='Set-Repair-Ply')
        _assign_adhesive_section(adhesivePart)

        _create_plate_sets_and_surfaces(basePart)
        _create_true_scarf_base_surface(basePart, scarfData)
        _create_true_scarf_repair_surface(repairPart, scarfData)
        _create_true_scarf_adhesive_surfaces(
            adhesivePart, scarfData)

        modelData['geometryStageComplete'] = True
        modelData['geometryStageParts'] = (
            'Part-Base', 'Part-Repair', 'Part-Adhesive')
    else:
        for partName in (
                'Part-Base', 'Part-Repair', 'Part-Adhesive'):
            if partName not in model.parts:
                raise ValueError(
                    'Required scarf geometry part is missing: %s. '
                    'Create geometry/partitions first.' % partName)
        basePart = model.parts['Part-Base']
        repairPart = model.parts['Part-Repair']
        adhesivePart = model.parts['Part-Adhesive']

    if buildStage in ('full', 'mesh'):
        _clear_scarf_analysis_features()

        # The visual Boolean-cut geometry is deliberately replaced by a
        # deterministic block-structured orphan mesh.  The cone remains
        # geometrically continuous; only the mesh topology changes.
        basePart, repairPart, adhesivePart = (
            _build_structured_true_scarf_parts(scarfData))

        baseInstance = assembly.Instance(
            name='Part-Base-1', part=basePart, dependent=ON)
        repairInstance = assembly.Instance(
            name='Part-Repair-1',
            part=repairPart, dependent=ON)
        adhesiveInstance = assembly.Instance(
            name='Part-Adhesive-1',
            part=adhesivePart, dependent=ON)
        assembly.regenerate()

        _create_tie(
            'Tie-Base-Adhesive',
            adhesiveInstance.surfaces['Surf-Adhesive-Base'],
            baseInstance.surfaces['Surf-Base-Adhesive'])
        _create_tie(
            'Tie-Repair-Adhesive',
            adhesiveInstance.surfaces['Surf-Adhesive-Repair'],
            repairInstance.surfaces['Surf-Repair-Adhesive'])

        repairData['adhesiveModel'] = (
            'solid-linear-elastic-tie')


elif repairType == 0:
    if patchLayerCountPerSide is None or patchLayerCountPerSide < 1:
        raise ValueError(
            'Double-sided patch requires at least one ply per side')
    if repairLayerCount != 2 * patchLayerCountPerSide:
        raise ValueError(
            'Double-sided patch total ply count was not split evenly')
    if repairOuterRadius <= damageRadius:
        raise ValueError('Patch diameter must exceed damage diameter')
    if adhesiveThickness <= 0.0:
        raise ValueError(
            'Double-sided patch solid adhesive thickness must be positive')

    radialOverlap = repairOuterRadius - damageRadius
    patchPlyThickness = (
        patchDepthPerSide / float(patchLayerCountPerSide))

    basePart = _create_plate('Part-Base', withHole=True)
    topRepairPart = _create_disc(
        'Part-Repair-Top', repairOuterRadius, patchDepthPerSide)
    bottomRepairPart = _create_disc(
        'Part-Repair-Bottom', repairOuterRadius, patchDepthPerSide)
    topAdhesivePart = _create_annulus(
        'Part-Adhesive-Top', damageRadius,
        repairOuterRadius, adhesiveThickness)
    bottomAdhesivePart = _create_annulus(
        'Part-Adhesive-Bottom', damageRadius,
        repairOuterRadius, adhesiveThickness)

    _partition_at_z(
        basePart,
        [basePlyThickness * index
         for index in range(1, baseLayerCount)])
    patchPartitionValues = [
        patchPlyThickness * index
        for index in range(1, patchLayerCountPerSide)]
    _partition_at_z(topRepairPart, patchPartitionValues)
    _partition_at_z(bottomRepairPart, patchPartitionValues)

    baseGroups = _layer_groups(
        basePart, 2, 1, baseLayerCount, basePlyThickness)
    topRepairGroups = _layer_groups(
        topRepairPart, 2, 1,
        patchLayerCountPerSide, patchPlyThickness)
    bottomRepairGroups = _layer_groups(
        bottomRepairPart, 2, 1,
        patchLayerCountPerSide, patchPlyThickness)

    baseAngleMap = dict(
        [(index + 1, modelData['layers'][index])
         for index in range(baseLayerCount)])
    topAngles = list(repairData.get('layersTop', []))
    bottomAngles = list(repairData.get('layersBottom', []))
    if len(topAngles) != patchLayerCountPerSide:
        raise ValueError(
            'Top patch angle count does not equal plies per side')
    if len(bottomAngles) != patchLayerCountPerSide:
        raise ValueError(
            'Bottom patch angle count does not equal plies per side')
    topAngleMap = dict(
        [(index + 1, topAngles[index])
         for index in range(patchLayerCountPerSide)])
    bottomAngleMap = dict(
        [(index + 1, bottomAngles[index])
         for index in range(patchLayerCountPerSide)])

    _assign_layers(
        basePart, baseGroups, baseAngleMap, 2,
        setPrefix='Set-Base-Ply')
    _assign_layers(
        topRepairPart, topRepairGroups, topAngleMap, 2,
        setPrefix='Set-Repair-Top-Ply')
    _assign_layers(
        bottomRepairPart, bottomRepairGroups, bottomAngleMap, 2,
        setPrefix='Set-Repair-Bottom-Ply')
    _assign_adhesive_section(topAdhesivePart)
    _assign_adhesive_section(bottomAdhesivePart)

    _create_plate_sets_and_surfaces(basePart)
    _create_plate_top_bottom_surfaces(basePart)
    _create_patch_surfaces(topRepairPart, patchDepthPerSide)
    _create_patch_surfaces(bottomRepairPart, patchDepthPerSide)
    _create_patch_surfaces(topAdhesivePart, adhesiveThickness)
    _create_patch_surfaces(bottomAdhesivePart, adhesiveThickness)

    _mesh_part(basePart, repairOuterRadius, radialOverlap)
    _create_end_node_sets(basePart)
    _mesh_part(topRepairPart, repairOuterRadius, radialOverlap)
    _mesh_part(bottomRepairPart, repairOuterRadius, radialOverlap)
    _mesh_flat_adhesive_part(topAdhesivePart, radialOverlap)
    _mesh_flat_adhesive_part(bottomAdhesivePart, radialOverlap)

    basePart.Set(name='Set-Base-All', elements=basePart.elements)
    topRepairPart.Set(
        name='Set-Repair-Top-All', elements=topRepairPart.elements)
    bottomRepairPart.Set(
        name='Set-Repair-Bottom-All',
        elements=bottomRepairPart.elements)
    topAdhesivePart.Set(
        name='Set-Adhesive-Top-Elements',
        elements=topAdhesivePart.elements)
    bottomAdhesivePart.Set(
        name='Set-Adhesive-Bottom-Elements',
        elements=bottomAdhesivePart.elements)

    baseInstance = assembly.Instance(
        name='Part-Base-1', part=basePart, dependent=ON)
    topPatch = assembly.Instance(
        name='Part-Repair-Top-1',
        part=topRepairPart, dependent=ON)
    bottomPatch = assembly.Instance(
        name='Part-Repair-Bottom-1',
        part=bottomRepairPart, dependent=ON)
    topAdhesive = assembly.Instance(
        name='Part-Adhesive-Top-1',
        part=topAdhesivePart, dependent=ON)
    bottomAdhesive = assembly.Instance(
        name='Part-Adhesive-Bottom-1',
        part=bottomAdhesivePart, dependent=ON)

    assembly.translate(
        instanceList=('Part-Adhesive-Top-1',),
        vector=(0.0, 0.0, totalThickness))
    assembly.translate(
        instanceList=('Part-Repair-Top-1',),
        vector=(
            0.0, 0.0,
            totalThickness + adhesiveThickness))
    assembly.translate(
        instanceList=('Part-Adhesive-Bottom-1',),
        vector=(0.0, 0.0, -adhesiveThickness))
    assembly.translate(
        instanceList=('Part-Repair-Bottom-1',),
        vector=(
            0.0, 0.0,
            -(adhesiveThickness + patchDepthPerSide)))
    assembly.regenerate()

    _create_tie(
        'Tie-Base-TopAdhesive',
        topAdhesive.surfaces['Surf-Bottom'],
        baseInstance.surfaces['Surf-PlateTop'])
    _create_tie(
        'Tie-TopRepair-Adhesive',
        topAdhesive.surfaces['Surf-Top'],
        topPatch.surfaces['Surf-Bottom'])
    _create_tie(
        'Tie-Base-BottomAdhesive',
        bottomAdhesive.surfaces['Surf-Top'],
        baseInstance.surfaces['Surf-PlateBottom'])
    _create_tie(
        'Tie-BottomRepair-Adhesive',
        bottomAdhesive.surfaces['Surf-Bottom'],
        bottomPatch.surfaces['Surf-Top'])

    repairData['patchPlyCountPerSide'] = patchLayerCountPerSide
    repairData['patchDepthPerSide'] = patchDepthPerSide
    repairData['patchRadialOverlap'] = radialOverlap
    repairData['patchGeometry'] = 'double-sided-circular-through-hole'
    repairData['adhesiveElementFamily'] = (
        'two-annular-C3D8R-structured-v1.1')


else:
    raise ValueError('Unknown repair type: %s' % repairType)

if buildStage == 'geometry':
    session.viewports['Viewport: 1'].setValues(displayedObject=basePart)
    modelData['buildStatus'] = (
        'geometry-and-partitions-complete; mesh-not-created')
else:
    _create_step_bc_and_output(assembly, baseInstance)
    session.viewports['Viewport: 1'].setValues(displayedObject=assembly)
    session.viewports['Viewport: 1'].assemblyDisplay.setValues(
        step='Step-1')
    modelData['buildStatus'] = (
        'mesh-assembly-ties-bc-and-step-complete')
