#region META
bl_info = {
    "name": 'GEN Cable Route',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Generate cable routes with proper overlapping',
    "status": 'working',
    "approved": True,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "group_order": 30,
    "addon_order": 30,
    "tags": ['curve', 'cable', 'procedural', 'routing', 'projection'],
    "description_short": 'Generate cable routes with proper overlapping',
    "description_medium": 'Projects and routes cables along surfaces with proper overlapping and stacking behavior based on cable priority.',
    "description_long": """
    CABLE ROUTE GENERATOR
    Projects and routes cables along surfaces with proper overlapping and stacking behavior.
    Supports per-cable thickness, color, priority, and subdivision. Detects intersections
    between projected curves and offsets higher-priority cables above lower-priority ones.""",
    "location": 'View3D > ZENV',
    "image_overview": 'zenv_blender_GEN_cable_route.png',
    "addon_image": 'zenv_blender_GEN_cable_route.png',
    "warning": '',
    "doc_url": '',
}

#endregion
#region IMPORT
import bpy
import bmesh
import logging
import math
import random
from mathutils import Vector
from mathutils.geometry import intersect_line_line
from bpy.props import (
    FloatProperty, IntProperty, PointerProperty, BoolProperty,
    EnumProperty, CollectionProperty, FloatVectorProperty, StringProperty,
)
from bpy.types import PropertyGroup, Operator, Panel

logger = logging.getLogger(__name__)
_zenv_cable_route_console_handler = None


def _install_logger():
    """Attach a single StreamHandler to the addon logger (idempotent)."""
    global _zenv_cable_route_console_handler
    if _zenv_cable_route_console_handler is not None:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _zenv_cable_route_console_handler = handler


def _uninstall_logger():
    """Remove the handler added by :func:`_install_logger`."""
    global _zenv_cable_route_console_handler
    if _zenv_cable_route_console_handler is None:
        return
    try:
        logger.removeHandler(_zenv_cable_route_console_handler)
    except ValueError:
        pass
    _zenv_cable_route_console_handler = None

#endregion
#region PROPS
class ZENV_PG_Cable(PropertyGroup):
    """Properties for individual cables (attached to Curve data-blocks)."""
    thickness: FloatProperty(
        name="Cable Thickness",
        description="Thickness of the cable",
        default=0.02,
        min=0.001,
        max=0.1
    )
    color: FloatVectorProperty(
        name="Cable Color",
        subtype='COLOR',
        default=(0.8, 0.8, 0.8),
        min=0,
        max=1
    )
    subdivision: IntProperty(
        name="Subdivision",
        description="Number of subdivisions along cable",
        default=50,
        min=2,
        max=200
    )
    priority: IntProperty(
        name="Priority",
        description="Cable stacking priority (higher numbers stack on top)",
        default=1,
        min=1,
        max=100
    )


class ZENV_PG_CableRoute(PropertyGroup):
    """Properties for the Cable Route Generator (scene-level)."""
    floor_object: PointerProperty(
        name="Floor Object",
        description="Object to project cables onto",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH',
    )
    spacing_factor: FloatProperty(
        name="Spacing Factor",
        description="Factor for spacing between overlapping cables",
        default=1.2,
        min=1.0,
        max=2.0
    )
    smooth_iterations: IntProperty(
        name="Smooth Iterations",
        description="Number of smoothing iterations for cable paths",
        default=5,
        min=0,
        max=20
    )
    bevel_resolution: IntProperty(
        name="Bevel Resolution",
        description="Resolution of cable beveling",
        default=6,
        min=2,
        max=12
    )

#endregion
#region OP
class ZENV_OT_CableRoute(Operator):
    """Create cable routes with proper overlapping"""
    bl_idname = "zenv.cable_route_add"
    bl_label = "Generate Cable Routes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def subdivide_curve(self, curve_obj, subdivisions):
        """Subdivide curve by directly sampling spline points.

        Replaces the previous lossy curve->mesh->curve conversion that caused
        exponential edge growth. This method walks the original spline and
        produces a new POLY spline with ``subdivisions`` points per segment.
        Per-cable properties are copied from the source curve data-block.
        """
        src_curve = curve_obj.data
        src_spline = src_curve.splines[0] if src_curve.splines else None
        if src_spline is None:
            logger.warning("Curve %s has no splines, skipping", curve_obj.name)
            return None

        # Collect source points from the first spline.
        src_points = [p.co.xyz.copy() for p in src_spline.points]
        if len(src_points) < 2:
            logger.warning("Curve %s has fewer than 2 points, skipping", curve_obj.name)
            return None

        # Interpolate to the desired number of points.
        total_segments = len(src_points) - 1
        points_per_segment = max(1, subdivisions // total_segments)
        sampled = []
        for seg_idx in range(total_segments):
            p_start = src_points[seg_idx]
            p_end = src_points[seg_idx + 1]
            for t in range(points_per_segment):
                frac = t / points_per_segment
                sampled.append(p_start.lerp(p_end, frac))
        # Always include the final point.
        sampled.append(src_points[-1])

        # Create new curve data-block.
        new_curve = bpy.data.curves.new(name="Dense_Curve", type='CURVE')
        new_curve.dimensions = '3D'

        spline = new_curve.splines.new('POLY')
        spline.points.add(len(sampled) - 1)
        for i, co in enumerate(sampled):
            spline.points[i].co = (co.x, co.y, co.z, 1)

        # Copy per-cable properties from the source curve data-block.
        if hasattr(src_curve, 'zenv_cable_props'):
            new_curve.zenv_cable_props.thickness = src_curve.zenv_cable_props.thickness
            new_curve.zenv_cable_props.color = src_curve.zenv_cable_props.color
            new_curve.zenv_cable_props.priority = src_curve.zenv_cable_props.priority
            new_curve.zenv_cable_props.subdivision = src_curve.zenv_cable_props.subdivision

        return new_curve

    def project_to_surface(self, point, surface_obj):
        """Project point onto surface using raycast.

        The ray starts well above the point and travels downward through the
        full bounding-box height of the target object, ensuring the surface
        is hit even when the curve is far below it.
        """
        # Convert point to surface local space.
        local_point = surface_obj.matrix_world.inverted() @ Vector(point)

        # Derive ray start and length from the object's bounding box.
        bbox = surface_obj.bound_box
        z_vals = [surface_obj.matrix_world @ Vector(c) for c in bbox]
        max_z = max(v.z for v in z_vals)
        min_z = min(v.z for v in z_vals)
        ray_start_z = max_z + 1.0  # Start 1 unit above the highest bbox point.
        ray_length = (ray_start_z - min_z) + 2.0  # Full height plus margin.

        # Cast ray downward from above the point.
        ray_start = Vector((local_point.x, local_point.y, ray_start_z))
        hit, location, normal, _ = surface_obj.ray_cast(
            ray_start,
            Vector((0, 0, -ray_length))
        )

        if hit:
            world_loc = surface_obj.matrix_world @ location
            world_norm = surface_obj.matrix_world.to_3x3() @ normal
            return world_loc, world_norm

        logger.debug("Raycast miss for point %s on %s", point, surface_obj.name)
        return None, None

    def _segments_intersect(self, p1, p2, p3, p4, threshold=1e-6):
        """Check if two 3D line segments actually intersect (or pass very close).

        Uses ``intersect_line_line`` but validates that the closest points
        are within both segments and the distance between them is below
        ``threshold``. Returns the intersection point or ``None``.
        """
        try:
            result = intersect_line_line(p1, p2, p3, p4)
        except Exception:
            return None
        if not result or len(result) < 2:
            return None

        closest_a, closest_b = result[0], result[1]
        # Check that the closest points are nearly coincident.
        if (closest_a - closest_b).length > threshold:
            return None

        # Check that the intersection point lies within both segments.
        seg1_len = (p2 - p1).length
        seg2_len = (p4 - p3).length
        if seg1_len < 1e-12 or seg2_len < 1e-12:
            return None

        t1 = (closest_a - p1).dot(p2 - p1) / (seg1_len * seg1_len)
        t2 = (closest_b - p3).dot(p4 - p3) / (seg2_len * seg2_len)

        if not (0.0 <= t1 <= 1.0 and 0.0 <= t2 <= 1.0):
            return None

        return (closest_a + closest_b) / 2

    def find_intersections(self, curves):
        """Find intersection points between curves.

        Accesses ``curve.splines[0].points`` (not ``curve.points``) and uses
        a proper segment intersection test rather than infinite-line closest
        points.
        """
        intersections = []

        for i, curve1 in enumerate(curves):
            if not curve1.splines:
                continue
            pts1 = curve1.splines[0].points
            for j, curve2 in enumerate(curves):
                if i >= j:
                    continue
                if not curve2.splines:
                    continue
                pts2 = curve2.splines[0].points

                for k in range(len(pts1) - 1):
                    p1 = pts1[k].co.xyz
                    p2 = pts1[k + 1].co.xyz
                    for l in range(len(pts2) - 1):
                        p3 = pts2[l].co.xyz
                        p4 = pts2[l + 1].co.xyz

                        hit_point = self._segments_intersect(p1, p2, p3, p4)
                        if hit_point is not None:
                            intersections.append({
                                'point': hit_point,
                                'curves': (i, j),
                                'segments': (k, l)
                            })

        return intersections

    def adjust_heights(self, curves, intersections, props):
        """Adjust curve heights at intersections.

        Simplified priority comparison: directly compares the ``priority``
        property of the two curves. The higher-priority curve is lifted
        above the lower-priority one by the sum of their thicknesses times
        the spacing factor.
        """
        # Create height map for each curve (plain Python lists, no numpy).
        height_maps = [[0.0] * len(c.splines[0].points) if c.splines else []
                       for c in curves]

        for intersection in intersections:
            point = intersection['point']
            curve1_idx, curve2_idx = intersection['curves']

            # Determine which curve goes on top by direct priority comparison.
            p1 = curves[curve1_idx].zenv_cable_props.priority
            p2 = curves[curve2_idx].zenv_cable_props.priority
            if p1 >= p2:
                top_curve = curve1_idx
                bottom_curve = curve2_idx
            else:
                top_curve = curve2_idx
                bottom_curve = curve1_idx

            # Calculate offset.
            offset = (curves[bottom_curve].zenv_cable_props.thickness +
                      curves[top_curve].zenv_cable_props.thickness) * props.spacing_factor

            # Apply height offset around intersection with falloff.
            radius = max(curves[top_curve].zenv_cable_props.thickness,
                         curves[bottom_curve].zenv_cable_props.thickness) * 5

            top_pts = curves[top_curve].splines[0].points if curves[top_curve].splines else []
            for idx, cp in enumerate(top_pts):
                dist = (cp.co.xyz - point).length
                if dist < radius:
                    falloff = 1 - (dist / radius)
                    height_maps[top_curve][idx] = max(
                        height_maps[top_curve][idx],
                        offset * falloff
                    )

        # Apply height maps to curves.
        for i, curve in enumerate(curves):
            if not curve.splines:
                continue
            for j, point in enumerate(curve.splines[0].points):
                point.co.z += height_maps[i][j]

    def smooth_curves(self, curves, iterations):
        """Smooth curve points using a simple averaging filter."""
        for curve in curves:
            if not curve.splines:
                continue
            spline = curve.splines[0]
            for _ in range(iterations):
                points = [p.co.copy() for p in spline.points]
                for i in range(1, len(spline.points) - 1):
                    spline.points[i].co = (points[i - 1] + points[i] + points[i + 1]) / 3

    def _get_or_create_material(self, color):
        """Get an existing cable material with the same color, or create one.

        Avoids creating duplicate materials for cables with identical colors.
        """
        color_key = (round(color[0], 4), round(color[1], 4), round(color[2], 4))
        mat_name = f"Cable_Mat_{color_key[0]:.2f}_{color_key[1]:.2f}_{color_key[2]:.2f}"

        existing = bpy.data.materials.get(mat_name)
        if existing is not None:
            return existing

        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()

        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')

        # Set material properties (Blender 4.0 compatible).
        principled.inputs['Base Color'].default_value = (color[0], color[1], color[2], 1)
        principled.inputs['Roughness'].default_value = 0.3
        # In Blender 4.0, 'Specular' was replaced by 'Specular IOR Level'.
        if 'Specular IOR Level' in principled.inputs:
            principled.inputs['Specular IOR Level'].default_value = 0.5
        elif 'Specular' in principled.inputs:
            principled.inputs['Specular'].default_value = 0.5

        mat.node_tree.links.new(principled.outputs['BSDF'], output.inputs['Surface'])
        return mat

    def create_cable_mesh(self, curve, props):
        """Create final cable mesh with thickness and material."""
        # Create curve object.
        curve_obj = bpy.data.objects.new("Cable_Curve", curve)
        bpy.context.collection.objects.link(curve_obj)

        # Add bevel from per-cable properties.
        cable_props = curve.zenv_cable_props
        curve.bevel_depth = cable_props.thickness
        curve.bevel_resolution = props.bevel_resolution

        # Get or create material.
        mat = self._get_or_create_material(cable_props.color)
        curve_obj.data.materials.append(mat)

        return curve_obj

    # ------------------------------------------------------------------
    # Auto-creation helpers for missing floor / curves
    # ------------------------------------------------------------------

    def _create_floor_plane(self, context, size_x=10.0, size_y=10.0,
                            location=(0, 0, 0), name="CableRoute_Floor"):
        """Create a flat quad mesh to use as a projection floor."""
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)
        context.scene.collection.objects.link(obj)

        hx = size_x / 2.0
        hy = size_y / 2.0
        verts = [
            (-hx, -hy, 0),
            (hx, -hy, 0),
            (hx, hy, 0),
            (-hx, hy, 0),
        ]
        mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
        mesh.update()

        obj.location = location
        return obj

    def _create_poly_curve(self, context, points, name, cable_props=None):
        """Create a POLY curve object from a list of 3-tuple/Vector points.

        ``cable_props`` is an optional dict with keys: thickness, color,
        priority, subdivision.
        """
        curve_data = bpy.data.curves.new(name=name, type='CURVE')
        curve_data.dimensions = '3D'
        spline = curve_data.splines.new('POLY')
        spline.points.add(len(points) - 1)
        for i, p in enumerate(points):
            spline.points[i].co = (p[0], p[1], p[2], 1)

        cp = curve_data.zenv_cable_props
        if cable_props:
            cp.thickness = cable_props.get('thickness', 0.02)
            cp.color = cable_props.get('color', (0.8, 0.8, 0.8))
            cp.priority = cable_props.get('priority', 1)
            cp.subdivision = cable_props.get('subdivision', 50)

        obj = bpy.data.objects.new(name, curve_data)
        context.scene.collection.objects.link(obj)
        return obj

    def _floor_world_bounds(self, floor_obj):
        """Return (min_x, max_x, min_y, max_y, min_z, max_z) in world space."""
        bbox = [floor_obj.matrix_world @ Vector(c) for c in floor_obj.bound_box]
        xs = [v.x for v in bbox]
        ys = [v.y for v in bbox]
        zs = [v.z for v in bbox]
        return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)

    def _curve_world_bounds(self, curve_objs):
        """Return (min_x, max_x, min_y, max_y, min_z) across all curve points."""
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        min_z = float('inf')

        for obj in curve_objs:
            for spline in obj.data.splines:
                if spline.type == 'BEZIER':
                    pts = spline.bezier_points
                else:
                    pts = spline.points
                for p in pts:
                    co = obj.matrix_world @ p.co.xyz
                    min_x = min(min_x, co.x)
                    max_x = max(max_x, co.x)
                    min_y = min(min_y, co.y)
                    max_y = max(max_y, co.y)
                    min_z = min(min_z, co.z)

        return min_x, max_x, min_y, max_y, min_z

    def _create_example_curves(self, context, floor_obj):
        """Create three overlapping example curves on the floor.

        The curves cross each other with different priorities and colors so
        the stacking/overlap feature is immediately visible.
        """
        min_x, max_x, min_y, max_y, _, max_z = self._floor_world_bounds(floor_obj)
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        extent = min(max_x - min_x, max_y - min_y) * 0.35
        top_z = max_z + 1.0  # place above floor so projection raycast works

        curves = []

        # Curve 1: left-to-right wave (priority 1, red)
        pts1 = [
            (cx - extent, cy - extent, top_z),
            (cx - extent * 0.3, cy, top_z),
            (cx + extent * 0.3, cy, top_z),
            (cx + extent, cy + extent, top_z),
        ]
        curves.append(self._create_poly_curve(
            context, pts1, "Example_Cable_1",
            {'thickness': 0.03, 'color': (0.9, 0.2, 0.2), 'priority': 1, 'subdivision': 60}))

        # Curve 2: top-left to bottom-right diagonal (priority 2, green)
        pts2 = [
            (cx - extent, cy + extent, top_z),
            (cx, cy + extent * 0.2, top_z),
            (cx + extent * 0.2, cy - extent * 0.2, top_z),
            (cx + extent, cy - extent, top_z),
        ]
        curves.append(self._create_poly_curve(
            context, pts2, "Example_Cable_2",
            {'thickness': 0.03, 'color': (0.2, 0.9, 0.2), 'priority': 2, 'subdivision': 60}))

        # Curve 3: vertical line crossing both (priority 3, blue)
        pts3 = [
            (cx, cy - extent, top_z),
            (cx, cy, top_z),
            (cx, cy + extent, top_z),
        ]
        curves.append(self._create_poly_curve(
            context, pts3, "Example_Cable_3",
            {'thickness': 0.03, 'color': (0.2, 0.4, 0.9), 'priority': 3, 'subdivision': 60}))

        # Select the new curves.
        bpy.ops.object.select_all(action='DESELECT')
        for c in curves:
            c.select_set(True)
        context.view_layer.objects.active = curves[0]
        return curves

    def _create_random_curves_on_floor(self, context, floor_obj, count=3):
        """Generate random POLY curves that fit within the floor bounds."""
        min_x, max_x, min_y, max_y, _, max_z = self._floor_world_bounds(floor_obj)
        top_z = max_z + 1.0
        margin = 0.2

        colors = [
            (0.9, 0.2, 0.2), (0.2, 0.9, 0.2), (0.2, 0.4, 0.9),
            (0.9, 0.9, 0.2), (0.9, 0.2, 0.9),
        ]

        curves = []
        for i in range(count):
            n_pts = random.randint(3, 6)
            pts = []
            for _ in range(n_pts):
                x = random.uniform(min_x + margin, max_x - margin)
                y = random.uniform(min_y + margin, max_y - margin)
                pts.append((x, y, top_z))
            curves.append(self._create_poly_curve(
                context, pts, f"Random_Cable_{i + 1}",
                {
                    'thickness': round(random.uniform(0.02, 0.05), 3),
                    'color': colors[i % len(colors)],
                    'priority': i + 1,
                    'subdivision': 60,
                }))

        bpy.ops.object.select_all(action='DESELECT')
        for c in curves:
            c.select_set(True)
        context.view_layer.objects.active = curves[0]
        return curves

    def _create_floor_for_curves(self, context, curve_objs, padding=1.0):
        """Create a floor plane below the given curves, fitting bounds + padding."""
        min_x, max_x, min_y, max_y, min_z = self._curve_world_bounds(curve_objs)

        size_x = (max_x - min_x) + padding * 2
        size_y = (max_y - min_y) + padding * 2
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        floor_z = min_z - padding

        return self._create_floor_plane(
            context, size_x=size_x, size_y=size_y,
            location=(cx, cy, floor_z), name="CableRoute_Floor")

    def execute(self, context):
        """Execute the cable route generation.

        Auto-creates missing components so the operator always succeeds:
          * Neither floor nor curves  -> create a default example setup.
          * Floor only (no curves)    -> generate random curves on the floor.
          * Curves only (no floor)    -> create a fitted floor below them.
          * Both present              -> proceed with the existing pipeline.

        Wraps the pipeline in try/except so failures are reported and
        temporary data is cleaned up.
        """
        props = context.scene.zenv_cable_route_props

        # Get floor object from properties (ignore non-mesh assignments).
        floor_obj = props.floor_object
        if floor_obj and floor_obj.type != 'MESH':
            floor_obj = None

        # Get selected curves (excluding the floor if it somehow is a curve).
        curve_objs = [obj for obj in context.selected_objects
                      if obj.type == 'CURVE' and obj != floor_obj]

        # --- Auto-create missing components -------------------------------
        if not floor_obj and not curve_objs:
            # Neither exists: create the default example setup.
            floor_obj = self._create_floor_plane(
                context, size_x=10.0, size_y=10.0,
                location=(0, 0, 0), name="CableRoute_Floor")
            props.floor_object = floor_obj
            curve_objs = self._create_example_curves(context, floor_obj)
            self.report({'INFO'},
                        "Created default example setup (floor + 3 overlapping cables)")
            logger.info("Auto-created default example setup")

        elif floor_obj and not curve_objs:
            # Floor exists but no curves: generate random curves on the floor.
            curve_objs = self._create_random_curves_on_floor(context, floor_obj)
            self.report({'INFO'},
                        f"Generated {len(curve_objs)} random cables on floor")
            logger.info("Auto-generated %d random curves on floor '%s'",
                        len(curve_objs), floor_obj.name)

        elif not floor_obj and curve_objs:
            # Curves exist but no floor: create a fitted floor below them.
            floor_obj = self._create_floor_for_curves(context, curve_objs, padding=1.0)
            props.floor_object = floor_obj
            self.report({'INFO'},
                        f"Created floor fitted to {len(curve_objs)} curve(s)")
            logger.info("Auto-created floor '%s' for %d curves",
                        floor_obj.name, len(curve_objs))

        # Safety net - should not happen after auto-creation.
        if not floor_obj:
            self.report({'ERROR'}, "No floor object available")
            return {'CANCELLED'}

        if not curve_objs:
            self.report({'ERROR'}, "No curves available")
            return {'CANCELLED'}

        cable_objects = []
        dense_curves = []
        original_selection = list(context.selected_objects)

        try:
            # Process each curve: subdivide and project.
            for curve_obj in curve_objs:
                cable_props = curve_obj.data.zenv_cable_props
                dense_curve = self.subdivide_curve(
                    curve_obj,
                    cable_props.subdivision
                )
                if dense_curve is None:
                    continue

                # Project points onto surface.
                for point in dense_curve.splines[0].points:
                    hit_point, _normal = self.project_to_surface(point.co, floor_obj)
                    if hit_point:
                        point.co = (hit_point.x, hit_point.y, hit_point.z, 1)

                dense_curves.append(dense_curve)

            if not dense_curves:
                self.report({'ERROR'}, "No valid curves after subdivision")
                return {'CANCELLED'}

            # Find intersections.
            intersections = self.find_intersections(dense_curves)

            # Adjust heights at intersections.
            self.adjust_heights(dense_curves, intersections, props)

            # Smooth curves.
            if props.smooth_iterations > 0:
                self.smooth_curves(dense_curves, props.smooth_iterations)

            # Create final cable meshes.
            for curve in dense_curves:
                cable_obj = self.create_cable_mesh(curve, props)
                cable_objects.append(cable_obj)

            if not cable_objects:
                self.report({'ERROR'}, "No cable objects were created")
                return {'CANCELLED'}

            # Hide original input curves.
            for curve_obj in curve_objs:
                curve_obj.hide_viewport = True

            # Select cable objects.
            bpy.ops.object.select_all(action='DESELECT')
            for obj in cable_objects:
                obj.select_set(True)
            context.view_layer.objects.active = cable_objects[0]

            self.report({'INFO'}, f"Generated {len(cable_objects)} cable route(s)")
            logger.info("Cable route generation complete: %d cables", len(cable_objects))
            return {'FINISHED'}

        except Exception as gen_error:
            logger.exception("Cable route generation failed")
            # Clean up partially-created cable objects.
            for obj in cable_objects:
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except (ReferenceError, RuntimeError):
                    pass
            # Clean up orphaned dense curve data-blocks.
            for dc in dense_curves:
                try:
                    if dc.users == 0:
                        bpy.data.curves.remove(dc)
                except (ReferenceError, RuntimeError):
                    pass
            # Restore original selection visibility.
            for curve_obj in curve_objs:
                try:
                    curve_obj.hide_viewport = False
                except (ReferenceError, RuntimeError):
                    pass
            self.report({'ERROR'}, f"Cable route generation failed: {gen_error}")
            return {'CANCELLED'}

#endregion
#region PANEL
class ZENV_PT_CableRoute(Panel):
    """Panel for Cable Route Generator"""
    bl_label = "GEN Cable Route"
    bl_idname = "ZENV_PT_CableRoute"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_cable_route_props

        # Floor object selection.
        layout.prop(props, "floor_object")

        # Selected curve properties.
        box = layout.box()
        box.label(text="Selected Cable Properties:")

        for obj in context.selected_objects:
            if obj.type == 'CURVE':
                row = box.row()
                row.label(text=obj.name)
                col = row.column()
                cable_props = obj.data.zenv_cable_props
                col.prop(cable_props, "thickness")
                col.prop(cable_props, "color")
                col.prop(cable_props, "priority")
                col.prop(cable_props, "subdivision")

        # Route parameters.
        box = layout.box()
        box.label(text="Route Parameters:")
        box.prop(props, "spacing_factor")
        box.prop(props, "smooth_iterations")
        box.prop(props, "bevel_resolution")

        # Generate button.
        layout.operator("zenv.cable_route_add")

#endregion
#region REG
classes = (
    ZENV_PG_Cable,
    ZENV_PG_CableRoute,
    ZENV_OT_CableRoute,
    ZENV_PT_CableRoute,
)


def menu_func(self, context):
    """Add menu item to Add menu."""
    self.layout.operator("zenv.cable_route_add", text="Cable Route", icon='CURVE_BEZCURVE')


def register():
    """Register all addon classes, scene/curve properties, menu entry, and logger."""
    _install_logger()
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.zenv_cable_route_props = PointerProperty(type=ZENV_PG_CableRoute)
    bpy.types.Curve.zenv_cable_props = PointerProperty(type=ZENV_PG_Cable)
    try:
        bpy.types.VIEW3D_MT_add.append(menu_func)
    except Exception:
        pass


def unregister():
    """Unregister all addon classes, remove scene/curve properties, menu entry, and logger."""
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    if hasattr(bpy.types.Scene, "zenv_cable_route_props"):
        delattr(bpy.types.Scene, "zenv_cable_route_props")
    if hasattr(bpy.types.Curve, "zenv_cable_props"):
        delattr(bpy.types.Curve, "zenv_cable_props")
    try:
        bpy.types.VIEW3D_MT_add.remove(menu_func)
    except Exception:
        pass
    _uninstall_logger()


if __name__ == "__main__":
    register()
#endregion
