#region blinfo
bl_info = {
    "name": 'MESH Curl Flow',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Creates mesh geometry with curl flow patterns',
    "status": 'wip',
    "approved": False,
    "group": 'Mesh',
    "group_prefix": 'MESH',
    "group_order": 50,
    "addon_order": 50,
    "location": 'View3D > ZENV',
    "tags": ['mesh', 'curl', 'flow', 'noise', 'generator'],
    "description_short": 'Creates mesh geometry with curl flow patterns.',
    "description_medium": 'Generates flow lines on plane, sphere, or cylinder surfaces using '
                          'curl noise. Lines are created as bezier curves with optional '
                          'color gradient materials.',
    "description_long": 'Curl Flow Generator creates mesh geometry with curl flow patterns. '
                        'Uses curl noise to generate flow lines on parametric surfaces '
                        '(plane, sphere, cylinder). Lines are rendered as bezier curves '
                        'with configurable thickness, convergence, and color gradients.',
    "image_overview": '',
    "addon_image": '',
    "warning": '',
    "doc_url": '',
}
#endregion

#region imports
import bpy
import math
import random
import logging
from mathutils import Vector, noise
from bpy.props import FloatProperty, IntProperty, PointerProperty, BoolProperty, EnumProperty
from bpy.types import PropertyGroup, Operator, Panel
#endregion

#region logging
logger = logging.getLogger(__name__)
_log_handler = None


def _install_logger():
    """Install a stream handler on the module logger (idempotent)."""
    global _log_handler
    if _log_handler is not None:
        return
    _log_handler = logging.StreamHandler()
    _log_handler.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_log_handler)
    logger.setLevel(logging.INFO)


def _uninstall_logger():
    """Remove the stream handler from the module logger (idempotent)."""
    global _log_handler
    if _log_handler is not None:
        logger.removeHandler(_log_handler)
        _log_handler = None
#endregion

#region props
# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_CurlFlowProperties(PropertyGroup):
    """Properties for the Curl Flow Generator"""
    num_lines: IntProperty(
        name="Number of Lines",
        description="Number of flow lines to generate",
        default=20,
        min=1,
        max=100
    )
    line_length: IntProperty(
        name="Line Length",
        description="Number of segments per line",
        default=50,
        min=10,
        max=200
    )
    curl_scale: FloatProperty(
        name="Curl Scale",
        description="Scale of the curl noise",
        default=1.0,
        min=0.1,
        max=5.0
    )
    curl_strength: FloatProperty(
        name="Curl Strength",
        description="Strength of the curl effect",
        default=0.5,
        min=0.1,
        max=2.0
    )
    flow_speed: FloatProperty(
        name="Flow Speed",
        description="Step size multiplier for line integration",
        default=1.0,
        min=0.1,
        max=5.0
    )
    convergence: FloatProperty(
        name="Convergence",
        description="How much lines tend to converge",
        default=0.3,
        min=0.0,
        max=1.0
    )
    surface_type: EnumProperty(
        name="Surface Type",
        description="Type of surface to generate lines on",
        items=[
            ('PLANE', "Plane", "Generate on a plane"),
            ('SPHERE', "Sphere", "Generate on a sphere"),
            ('CYLINDER', "Cylinder", "Generate on a cylinder")
        ],
        default='PLANE'
    )
    surface_scale: FloatProperty(
        name="Surface Scale",
        description="Scale of the base surface",
        default=2.0,
        min=0.1,
        max=10.0
    )
    line_thickness: FloatProperty(
        name="Line Thickness",
        description="Thickness of the flow lines",
        default=0.02,
        min=0.001,
        max=0.1
    )
    random_seed: IntProperty(
        name="Random Seed",
        description="Seed for random generation",
        default=1,
        min=1,
        max=1000
    )
    use_color_gradient: BoolProperty(
        name="Use Color Gradient",
        description="Apply color gradient to lines",
        default=True
    )
#endregion

#region operator
# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_CurlFlowAdd(Operator):
    """Create new curl flow lines"""
    bl_idname = "zenv.curl_flow_add"
    bl_label = "Add Curl Flow"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    #region surface
    def get_surface_point(self, u, v, props):
        """Get point on surface based on UV coordinates"""
        if props.surface_type == 'PLANE':
            x = (u - 0.5) * props.surface_scale
            y = (v - 0.5) * props.surface_scale
            return Vector((x, y, 0))
        elif props.surface_type == 'SPHERE':
            phi = u * 2 * math.pi
            theta = v * math.pi
            x = math.sin(theta) * math.cos(phi)
            y = math.sin(theta) * math.sin(phi)
            z = math.cos(theta)
            return Vector((x, y, z)) * props.surface_scale
        else:  # CYLINDER
            phi = u * 2 * math.pi
            h = (v - 0.5) * props.surface_scale
            x = math.cos(phi)
            y = math.sin(phi)
            return Vector((x, y, h)) * props.surface_scale

    def get_surface_normal(self, u, v, props):
        """Get normal vector at surface point"""
        if props.surface_type == 'PLANE':
            return Vector((0, 0, 1))
        elif props.surface_type == 'SPHERE':
            point = self.get_surface_point(u, v, props)
            return point.normalized()
        else:  # CYLINDER
            phi = u * 2 * math.pi
            # Normalize for safety - the vector (cos, sin, 0) already has
            # length 1, but make it explicit so future modifications that
            # add scale don't produce un-normalized normals (review (section)3.3).
            return Vector((math.cos(phi), math.sin(phi), 0)).normalized()
    #endregion

    #region curl
    def curl_noise(self, p, props):
        """Generate a true curl-noise vector.

        Uses 3 independent scalar noise fields (n1, n2, n3) and computes
        the curl of the vector potential F = (n1, n2, n3):

            curl = (dn3/dy - dn2/dz,
                    dn1/dz - dn3/dx,
                    dn2/dx - dn1/dy)

        This produces a divergence-free field, which is the key property
        of curl noise that prevents flow lines from clumping or spreading
        (review (section)3.1: the old formula was an arbitrary permutation of a
        single noise field's gradient, not a true curl).
        """
        eps = 0.0001
        # Offset samples for each of the 3 independent noise fields.
        # 12 evaluations total (3 fields x 2 samples per axis used).
        n1_xp = noise.noise(Vector((p.x + eps, p.y, p.z)))
        n1_xm = noise.noise(Vector((p.x - eps, p.y, p.z)))
        n1_yp = noise.noise(Vector((p.x, p.y + eps, p.z)))
        n1_ym = noise.noise(Vector((p.x, p.y - eps, p.z)))
        n1_zp = noise.noise(Vector((p.x, p.y, p.z + eps)))
        n1_zm = noise.noise(Vector((p.x, p.y, p.z - eps)))

        # Use different offsets for fields 2 and 3 so they are independent.
        offset2 = 100.0
        offset3 = 200.0
        n2_xp = noise.noise(Vector((p.x + eps, p.y + offset2, p.z)))
        n2_xm = noise.noise(Vector((p.x - eps, p.y + offset2, p.z)))
        n2_yp = noise.noise(Vector((p.x, p.y + eps + offset2, p.z)))
        n2_ym = noise.noise(Vector((p.x, p.y - eps + offset2, p.z)))
        n2_zp = noise.noise(Vector((p.x, p.y + offset2, p.z + eps)))
        n2_zm = noise.noise(Vector((p.x, p.y + offset2, p.z - eps)))

        n3_xp = noise.noise(Vector((p.x + eps, p.y + offset3, p.z + offset3)))
        n3_xm = noise.noise(Vector((p.x - eps, p.y + offset3, p.z + offset3)))
        n3_yp = noise.noise(Vector((p.x, p.y + eps + offset3, p.z + offset3)))
        n3_ym = noise.noise(Vector((p.x, p.y - eps + offset3, p.z + offset3)))
        n3_zp = noise.noise(Vector((p.x, p.y + offset3, p.z + eps + offset3)))
        n3_zm = noise.noise(Vector((p.x, p.y + offset3, p.z - eps + offset3)))

        inv = 1.0 / (2.0 * eps)
        d_n1_dx = (n1_xp - n1_xm) * inv
        d_n1_dy = (n1_yp - n1_ym) * inv
        d_n1_dz = (n1_zp - n1_zm) * inv
        d_n2_dx = (n2_xp - n2_xm) * inv
        d_n2_dy = (n2_yp - n2_ym) * inv
        d_n2_dz = (n2_zp - n2_zm) * inv
        d_n3_dx = (n3_xp - n3_xm) * inv
        d_n3_dy = (n3_yp - n3_ym) * inv
        d_n3_dz = (n3_zp - n3_zm) * inv

        curl = Vector((
            (d_n3_dy - d_n2_dz) * props.curl_strength,
            (d_n1_dz - d_n3_dx) * props.curl_strength,
            (d_n2_dx - d_n1_dy) * props.curl_strength,
        ))
        return curl
    #endregion

    #region flowline
    def generate_flow_line(self, start_u, start_v, props):
        """Generate a single flow line"""
        points = []
        u, v = start_u, start_v
        
        for i in range(props.line_length):
            # Get current point on surface
            point = self.get_surface_point(u, v, props)
            normal = self.get_surface_normal(u, v, props)
            points.append(point)
            
            # Calculate curl noise
            curl = self.curl_noise(point * props.curl_scale, props)
            
            # Project curl vector onto surface
            if props.surface_type != 'PLANE':
                curl = curl - curl.dot(normal) * normal
            
            # Update UV coordinates
            step = props.flow_speed * 0.01
            u += curl.x * step
            v += curl.y * step

            # Apply convergence BEFORE wrapping so the pull toward center
            # is computed on the continuous coordinate, not the wrapped
            # one. This prevents discontinuities where a line near the
            # edge wraps to the opposite side and then converges from
            # the wrong direction (review (section)3.2).
            if props.convergence > 0:
                center_u, center_v = 0.5, 0.5
                u = u + (center_u - u) * props.convergence * 0.01
                v = v + (center_v - v) * props.convergence * 0.01

            # Wrap UV coordinates after convergence
            u = u % 1.0
            v = v % 1.0
        
        return points
    #endregion

    #region curve
    def create_curve_from_points(self, context, points, name, props):
        """Create curve object from points.

        The curve is NOT linked to any collection here; the caller is
        responsible for linking it to the flow collection (review (section)2.4).
        """
        if not points:
            return None

        # Create curve data
        curve_data = bpy.data.curves.new(name=name, type='CURVE')
        curve_data.dimensions = '3D'

        # Create spline
        spline = curve_data.splines.new('BEZIER')
        spline.bezier_points.add(len(points) - 1)

        # Set points with smooth handles based on neighbor tangents (review (section)3.6)
        n = len(points)
        for i, point in enumerate(points):
            bp = spline.bezier_points[i]
            bp.co = point
            if n > 2 and 0 < i < n - 1:
                tangent = (points[i + 1] - points[i - 1]).normalized()
                seg_len = (points[i + 1] - points[i - 1]).length * 0.3
                bp.handle_left = point - tangent * seg_len
                bp.handle_right = point + tangent * seg_len
            else:
                bp.handle_left = point
                bp.handle_right = point

        # Create object - do NOT link to bpy.context.collection (review (section)2.4)
        curve_obj = bpy.data.objects.new(name, curve_data)

        # Set curve properties from passed props (review (section)3.7)
        curve_data.bevel_depth = props.line_thickness
        curve_data.bevel_resolution = 2

        return curve_obj
    #endregion

    #region material
    def create_material(self, props):
        """Create material for flow lines"""
        mat = bpy.data.materials.new(name="Flow_Line_Material")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()

        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        emission = nodes.new('ShaderNodeEmission')

        # Link nodes
        links = mat.node_tree.links

        if props.use_color_gradient:
            # Setup color gradient driven by Generated Z coordinate (review (section)4.10)
            color_ramp = nodes.new('ShaderNodeValToRGB')
            tex_coord = nodes.new('ShaderNodeTexCoord')
            separate = nodes.new('ShaderNodeSeparateXYZ')

            color_ramp.color_ramp.elements[0].position = 0.0
            color_ramp.color_ramp.elements[0].color = (0.0, 0.5, 1.0, 1)
            color_ramp.color_ramp.elements[1].position = 1.0
            color_ramp.color_ramp.elements[1].color = (1.0, 0.2, 0.0, 1)

            links.new(tex_coord.outputs["Generated"], separate.inputs[0])
            links.new(separate.outputs["Z"], color_ramp.inputs["Fac"])
            links.new(color_ramp.outputs[0], emission.inputs[0])
        else:
            # Single color
            emission.inputs[0].default_value = (0.0, 0.8, 1.0, 1)

        links.new(emission.outputs[0], output.inputs[0])

        return mat
    #endregion

    #region execute
    def execute(self, context):
        props = context.scene.curl_flow_props
        # Use a local RNG to avoid polluting the global random state (review (section)2.1)
        rng = random.Random(props.random_seed)

        # Track created curves for cleanup on failure (review (section)2.2)
        created_curves = []
        material_created = False

        try:
            # Reuse or recreate collection for flow lines (review (section)2.3)
            flow_collection = bpy.data.collections.get("Flow_Lines")
            if flow_collection:
                # Clear existing objects from previous runs
                for obj in list(flow_collection.objects):
                    bpy.data.objects.remove(obj, do_unlink=True)
            else:
                flow_collection = bpy.data.collections.new("Flow_Lines")
                context.scene.collection.children.link(flow_collection)

            # Reuse or recreate material (review (section)2.3/(section)3.5)
            mat_name = "Flow_Line_Material"
            material = bpy.data.materials.get(mat_name)
            if not material:
                material = self.create_material(props)
                material.name = mat_name
                material_created = True

            # Generate flow lines
            for i in range(props.num_lines):
                # Random starting position
                start_u = rng.random()
                start_v = rng.random()

                # Generate line points
                points = self.generate_flow_line(start_u, start_v, props)

                # Create curve object - pass context and props (review (section)2.4/(section)3.7)
                curve = self.create_curve_from_points(context, points, f"Flow_Line_{i}", props)
                if curve is None:
                    continue
                curve.data.materials.append(material)
                created_curves.append(curve)

                # Add to collection
                flow_collection.objects.link(curve)

            return {'FINISHED'}

        except Exception as e:
            # Clean up partial results on failure (review (section)2.2)
            for curve in created_curves:
                try:
                    bpy.data.objects.remove(curve, do_unlink=True)
                except Exception:
                    pass
            if material_created and material and material.users == 0:
                try:
                    bpy.data.materials.remove(material)
                except Exception:
                    pass
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
    #endregion
#endregion

#region panel
# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_CurlFlowPanel(Panel):
    """Panel for Curl Flow Generator"""
    bl_label = "MESH Curl Flow"
    bl_idname = "ZENV_PT_curl_flow"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def draw(self, context):
        layout = self.layout
        props = context.scene.curl_flow_props

        # Surface parameters
        box = layout.box()
        box.label(text="Surface:")
        box.prop(props, "surface_type")
        box.prop(props, "surface_scale")
        
        # Line parameters
        box = layout.box()
        box.label(text="Lines:")
        box.prop(props, "num_lines")
        box.prop(props, "line_length")
        box.prop(props, "line_thickness")
        box.prop(props, "use_color_gradient")
        
        # Flow parameters
        box = layout.box()
        box.label(text="Flow:")
        box.prop(props, "curl_scale")
        box.prop(props, "curl_strength")
        box.prop(props, "flow_speed")
        box.prop(props, "convergence")
        
        # Generation parameters
        box = layout.box()
        box.label(text="Generation:")
        box.prop(props, "random_seed")
        
        # Generate button
        layout.operator("zenv.curl_flow_add")
#endregion

#region register
# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_CurlFlowProperties,
    ZENV_OT_CurlFlowAdd,
    ZENV_PT_CurlFlowPanel
)

def register():
    _install_logger()
    for current_class_to_register in classes:
        try:
            bpy.utils.register_class(current_class_to_register)
        except ValueError:
            pass
    if not hasattr(bpy.types.Scene, 'curl_flow_props'):
        bpy.types.Scene.curl_flow_props = PointerProperty(type=ZENV_PG_CurlFlowProperties)

def unregister():
    for current_class_to_unregister in reversed(classes):
        try:
            bpy.utils.unregister_class(current_class_to_unregister)
        except RuntimeError:
            pass
    if hasattr(bpy.types.Scene, 'curl_flow_props'):
        delattr(bpy.types.Scene, 'curl_flow_props')
    _uninstall_logger()
#endregion

#region main
if __name__ == "__main__":
    register()
#endregion
