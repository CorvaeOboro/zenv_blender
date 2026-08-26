#region META
bl_info = {
    "name": 'CURVE Helix Along Curve',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Generate helical curves that follow a base curve',
    "status": 'wip',
    "approved": False,
    "group": 'Curve',
    "group_prefix": 'CURVE',
    "group_order": 60,
    "addon_order": 20,
    "tags": ['curve', 'helix', 'generative', 'spiral'],
    "description_short": 'Generate helical curves that follow a base curve',
    "description_medium": 'Creates evenly distributed helical curves that follow a selected base curve, with configurable radius, rotation length, resolution, and bevel depth.',
    "description_long": """
    Helix Along Curve Generator
Creates evenly distributed helical curves that follow a base curve.
Useful for generating coils, vines, or decorative patterns.""",
    "location": 'View3D > Sidebar > ZENV > CURVE Helix Generator',
    "image_overview": 'zenv_blender_CURVE_helix_along_curve.png',
    "addon_image": 'zenv_blender_CURVE_helix_along_curve.png',
    "warning": '',
    "doc_url": '',
}

#region IMPORT
import bpy
import logging
from bpy.props import (
    FloatProperty,
    IntProperty,
    BoolProperty,
    FloatVectorProperty,
    PointerProperty,
)
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector, Matrix
from math import pi

logger = logging.getLogger(__name__)
_log_handler = None


def _install_logger():
    """Install a stream handler on the module logger (idempotent)."""
    global _log_handler
    if _log_handler is not None:
        return
    _log_handler = logging.StreamHandler()
    _log_handler.setFormatter(logging.Formatter('%(name)s: %(levelname)s: %(message)s'))
    logger.addHandler(_log_handler)
    logger.setLevel(logging.INFO)


def _uninstall_logger():
    """Remove the stream handler from the module logger (idempotent)."""
    global _log_handler
    if _log_handler is not None:
        logger.removeHandler(_log_handler)
        _log_handler = None

#endregion
#region PROPS
class ZENV_PG_HelixAlongCurve(PropertyGroup):
    """Properties for helix generation"""

    num_curves: IntProperty(
        name="Number of Curves",
        description="Number of helical curves to generate",
        default=1,
        min=1,
        max=12
    )

    rotation_length: FloatProperty(
        name="Length per Rotation",
        description="Length of curve for one complete rotation (in meters)",
        default=1.0,
        min=0.01,
        soft_max=10.0,
        unit='LENGTH'
    )

    radius: FloatProperty(
        name="Helix Radius",
        description="Radius of the helical curves",
        default=0.1,
        min=0.001,
        soft_max=1.0,
        unit='LENGTH'
    )

    resolution: IntProperty(
        name="Resolution",
        description="Number of points per rotation",
        default=12,
        min=4,
        max=64
    )

    smooth_curve: BoolProperty(
        name="Smooth Curve",
        description="Convert to NURBS and smooth the output curves",
        default=True
    )

    convert_to_mesh: BoolProperty(
        name="Convert to Mesh",
        description="Convert the output to mesh instead of keeping it as a curve",
        default=False
    )

    bevel_depth: FloatProperty(
        name="Curve Thickness",
        description="Thickness of the generated curves",
        default=0.01,
        min=0.0001,
        soft_max=0.1,
        unit='LENGTH'
    )

#endregion
#region OP
class ZENV_OT_HelixAlongCurve(Operator):
    """Generate helical curves along the selected curve"""
    bl_idname = "zenv.helix_along_curve_generate"
    bl_label = "Generate Helix"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Check if the operator can be called"""
        obj = context.active_object
        return bool(obj and obj.type == 'CURVE')

    def get_curve_length(self, curve_obj, depsgraph):
        """Calculate the total length of a curve using the provided depsgraph."""
        curve_eval = curve_obj.evaluated_get(depsgraph)
        curve = curve_eval.data

        total_length = 0

        for spline in curve.splines:
            if spline.type == 'BEZIER':
                points = spline.bezier_points
                for i in range(len(points)-1):
                    total_length += (points[i+1].co - points[i].co).length
            else:  # POLY, NURBS
                points = spline.points
                for i in range(len(points)-1):
                    p1 = points[i].co.to_3d()
                    p2 = points[i+1].co.to_3d()
                    total_length += (p2 - p1).length

        return total_length

    def sample_curve(self, curve_obj, num_samples, depsgraph):
        """Sample points and tangents along the curve using the provided depsgraph."""
        curve_eval = curve_obj.evaluated_get(depsgraph)
        curve = curve_eval.data

        points = []
        tangents = []

        # Calculate total curve length for better point distribution
        total_length = self.get_curve_length(curve_obj, depsgraph)
        if total_length <= 0:
            raise ValueError("Curve has zero length")

        # Increase sampling density for better accuracy
        points_per_length = (num_samples * 2) / total_length  # Double the sampling density

        for spline in curve.splines:
            if spline.type == 'BEZIER':
                points_array = []
                tangents_array = []
                for i in range(len(spline.bezier_points) - 1):
                    p1 = spline.bezier_points[i]
                    p2 = spline.bezier_points[i + 1]

                    # Calculate segment length and increase sampling for sharp turns
                    segment_length = (p2.co - p1.co).length
                    handle_angle = (p2.handle_left - p2.co).angle((p1.handle_right - p1.co))
                    angle_factor = 1 + (handle_angle / pi)  # Increase samples for sharper angles
                    num_segments = max(4, int(segment_length * points_per_length * angle_factor))

                    # Sample points along the segment using better Bezier interpolation
                    for t in range(num_segments):
                        factor = t / (num_segments - 1)
                        # Cubic Bezier interpolation
                        h1 = p1.co + (p1.handle_right - p1.co) * factor
                        h2 = p1.handle_right + (p2.handle_left - p1.handle_right) * factor
                        h3 = p2.handle_left + (p2.co - p2.handle_left) * factor

                        # Interpolate between handles
                        h4 = h1 + (h2 - h1) * factor
                        h5 = h2 + (h3 - h2) * factor

                        # Final point
                        co = h4 + (h5 - h4) * factor
                        points_array.append(co)

                        # Calculate more accurate tangent
                        if factor < 0.001:
                            tangent = (p1.handle_right - p1.co).normalized()
                        elif factor > 0.999:
                            tangent = (p2.co - p2.handle_left).normalized()
                        else:
                            # Use derivative of Bezier curve for tangent
                            tangent = (h5 - h4).normalized()
                        tangents_array.append(tangent)

                # Add final Bezier point and tangent
                if len(spline.bezier_points) > 0:
                    last_bp = spline.bezier_points[-1]
                    points_array.append(last_bp.co)
                    if len(spline.bezier_points) >= 2:
                        prev_bp = spline.bezier_points[-2]
                        tangents_array.append((last_bp.co - prev_bp.handle_right).normalized())
                    else:
                        tangents_array.append((last_bp.co - last_bp.handle_left).normalized())

                points.extend(points_array)
                tangents.extend(tangents_array)

            else:  # POLY or NURBS
                if len(spline.points) < 2:
                    continue

                points_array = []
                tangents_array = []
                for i in range(len(spline.points) - 1):
                    p1 = spline.points[i].co.to_3d()
                    p2 = spline.points[i + 1].co.to_3d()

                    # Calculate segment length
                    segment_length = (p2 - p1).length
                    num_segments = max(2, int(segment_length * points_per_length))

                    # Sample points along the segment
                    for t in range(num_segments):
                        factor = t / (num_segments - 1)
                        point = p1.lerp(p2, factor)
                        points_array.append(point)

                        # Calculate tangent
                        tangent = (p2 - p1).normalized()
                        tangents_array.append(tangent)

                # Add final point and tangent
                points_array.append(spline.points[-1].co.to_3d())
                last_tangent = (spline.points[-1].co.to_3d() - spline.points[-2].co.to_3d()).normalized()
                tangents_array.append(last_tangent)

                points.extend(points_array)
                tangents.extend(tangents_array)

        if not points:
            raise ValueError("No valid points found in curve")

        if len(points) != len(tangents):
            raise ValueError(f"Point and tangent count mismatch: {len(points)} points vs {len(tangents)} tangents")

        return points, tangents

    def create_helix_points(self, base_points, base_tangents, props, curve_index):
        """Generate points for a helical curve"""
        if len(base_points) != len(base_tangents):
            raise ValueError(f"Point and tangent count mismatch: {len(base_points)} points vs {len(base_tangents)} tangents")

        points = []
        num_base_points = len(base_points)

        # Calculate curve length more accurately using point distances
        curve_length = sum((base_points[i+1] - base_points[i]).length
                         for i in range(len(base_points)-1))

        # Calculate rotation angle between points (guard against single point)
        total_rotations = curve_length / props.rotation_length
        if num_base_points > 1:
            angle_step = (2 * pi * total_rotations) / (num_base_points - 1)
        else:
            angle_step = 0.0

        # Calculate initial angle offset for this curve
        start_angle = (2 * pi * curve_index) / props.num_curves

        # Use a more stable reference frame calculation
        up_vector = Vector((0, 0, 1))
        prev_tangent = None
        prev_perp = None
        prev_binormal = None

        for i in range(num_base_points):
            # Get base point and tangent
            base_point = base_points[i]
            tangent = base_tangents[i].normalized()

            # Calculate rotation angle with smoother progression
            angle = start_angle + (angle_step * i)

            if i == 0 or prev_tangent is None:
                # Initialize reference frame for first point
                binormal = tangent.cross(up_vector)
                if binormal.length < 0.1:
                    binormal = tangent.cross(Vector((1, 0, 0)))
                binormal.normalize()

                normal = binormal.cross(tangent).normalized()
                prev_binormal = binormal
                prev_perp = normal
            else:
                # Use parallel transport to update reference frame
                # Calculate rotation from previous to current tangent
                rotation_angle = prev_tangent.angle(tangent)
                if rotation_angle > 0.001:  # Only rotate if angle is significant
                    rotation_axis = prev_tangent.cross(tangent).normalized()
                    rotation = Matrix.Rotation(rotation_angle, 4, rotation_axis)

                    # Update reference frame
                    normal = (rotation @ prev_perp).normalized()
                    binormal = tangent.cross(normal).normalized()
                else:
                    # Keep previous frame if angle is small
                    normal = prev_perp
                    binormal = prev_binormal

            # Create rotation matrix around tangent for helix
            rot_matrix = Matrix.Rotation(angle, 4, tangent)

            # Calculate offset using rotated normal vector
            offset = rot_matrix @ (normal * props.radius)

            # Add point
            points.append(base_point + offset)

            # Store current vectors for next iteration
            prev_tangent = tangent
            prev_perp = normal
            prev_binormal = binormal

        return points

    def execute(self, context):
        """Execute the helix generation operation."""
        # Get active object with better error handling
        curve_obj = context.active_object
        if not curve_obj:
            self.report({'ERROR'}, "No active object selected")
            return {'CANCELLED'}

        if curve_obj.type != 'CURVE':
            self.report({'ERROR'}, f"Selected object '{curve_obj.name}' is not a curve (type: {curve_obj.type})")
            return {'CANCELLED'}

        if not curve_obj.data.splines:
            self.report({'ERROR'}, f"Curve '{curve_obj.name}' has no splines")
            return {'CANCELLED'}

        props = context.scene.zenv_helix_generator

        # Store original selection state for restoration
        original_active = context.view_layer.objects.active
        original_selected = [obj for obj in context.selected_objects]

        try:
            # Get depsgraph once and pass it to methods that need it
            depsgraph = context.evaluated_depsgraph_get()

            # Sample points along base curve
            base_points, base_tangents = self.sample_curve(curve_obj, props.resolution * 8, depsgraph)

            # Store original matrix for positioning
            original_matrix = curve_obj.matrix_world.copy()

            # Create curves
            new_objects = []  # Store new objects for potential conversion
            for i in range(props.num_curves):
                # Create new curve
                curve_data = bpy.data.curves.new(name=f'Helix_{i}', type='CURVE')
                curve_data.dimensions = '3D'

                # Set curve properties
                if props.smooth_curve:
                    spline = curve_data.splines.new('NURBS')
                else:
                    spline = curve_data.splines.new('POLY')

                # Generate helix points
                helix_points = self.create_helix_points(base_points, base_tangents, props, i)

                # Create new curve object
                curve_obj_new = bpy.data.objects.new(f'Helix_{i}', curve_data)
                context.scene.collection.objects.link(curve_obj_new)

                # Set points
                if props.smooth_curve:
                    spline.points.add(len(helix_points) - 1)
                    for j, point in enumerate(helix_points):
                        # Transform point to world space
                        world_point = original_matrix @ point
                        spline.points[j].co = (*world_point, 1)  # w=1 for NURBS
                    spline.use_endpoint_u = True
                    spline.order_u = 3
                else:
                    spline.points.add(len(helix_points) - 1)
                    for j, point in enumerate(helix_points):
                        # Transform point to world space
                        world_point = original_matrix @ point
                        spline.points[j].co = (*world_point, 1)

                # Set curve appearance
                curve_data.bevel_depth = props.bevel_depth
                curve_data.use_fill_caps = True
                curve_data.bevel_resolution = 4

                new_objects.append(curve_obj_new)

            # Convert to mesh if requested
            if props.convert_to_mesh:
                for obj in new_objects:
                    # Select the object
                    obj.select_set(True)
                    context.view_layer.objects.active = obj

                    # Convert to mesh
                    bpy.ops.object.convert(target='MESH')

                    # Deselect
                    obj.select_set(False)

            # Restore original selection state
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selected:
                obj.select_set(True)
            context.view_layer.objects.active = original_active

            logger.info("Generated %d helix curves along '%s'", len(new_objects), curve_obj.name)
            self.report({'INFO'}, f"Generated {len(new_objects)} helix curves")
            return {'FINISHED'}

        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        except Exception as e:
            logger.exception("Helix generation failed: %s", e)
            self.report({'ERROR'}, f"Helix generation failed: {e}")
            return {'CANCELLED'}
        finally:
            # Ensure selection is restored even on error
            try:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in original_selected:
                    obj.select_set(True)
                context.view_layer.objects.active = original_active
            except Exception:
                pass

#endregion
#region PANEL
class ZENV_PT_HelixAlongCurve(Panel):
    """Panel for helix generation settings"""
    bl_label = "CURVE Helix Generator"
    bl_idname = "ZENV_PT_helix_along_curve"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ZENV"

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_helix_generator

        # Main generation settings
        layout.prop(props, "num_curves")
        layout.prop(props, "rotation_length")
        layout.prop(props, "radius")

        # Curve appearance settings
        box = layout.box()
        box.label(text="Curve Settings:")
        box.prop(props, "resolution")
        box.prop(props, "smooth_curve")
        box.prop(props, "bevel_depth")
        box.prop(props, "convert_to_mesh")

        # Generate button
        layout.operator("zenv.helix_along_curve_generate")

#endregion
#region REG
classes = (
    ZENV_PG_HelixAlongCurve,
    ZENV_OT_HelixAlongCurve,
    ZENV_PT_HelixAlongCurve,
)

def register():
    """Register all addon classes, the scene property, and configure the logger."""
    _install_logger()
    for current_class_to_register in classes:
        try:
            bpy.utils.register_class(current_class_to_register)
        except ValueError:
            pass
    if not hasattr(bpy.types.Scene, "zenv_helix_generator"):
        bpy.types.Scene.zenv_helix_generator = PointerProperty(type=ZENV_PG_HelixAlongCurve)

def unregister():
    """Unregister all addon classes, remove the scene property, and remove the logger handler."""
    for current_class_to_unregister in reversed(classes):
        try:
            bpy.utils.unregister_class(current_class_to_unregister)
        except RuntimeError:
            pass
    if hasattr(bpy.types.Scene, "zenv_helix_generator"):
        delattr(bpy.types.Scene, "zenv_helix_generator")
    _uninstall_logger()

if __name__ == "__main__":
    register()
#endregion
