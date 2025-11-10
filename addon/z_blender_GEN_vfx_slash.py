bl_info = {
    "name": 'GEN VFX Slash',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250302',
    "description": 'Parabola Slash Mesh Generator',
    "status": 'wip',
    "approved": True,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "description_long": """
VFX SLASH GENERATOR
generates a parabola mesh for vfx slash effects
useful for game vfx
""",
    "location": 'View3D > ZENV',
}

import bpy
import bmesh
import math
from mathutils import Vector, Matrix
from bpy.props import FloatProperty, IntProperty, PointerProperty, BoolProperty
from bpy.types import PropertyGroup, Operator, Panel

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_VFXSlashProperties(PropertyGroup):
    """Properties for the VFX Slash Generator"""
    angle: FloatProperty(
        name="Angle",
        description="Angle of the parabola",
        default=45.0,
        min=0.0,
        max=360.0
    )
    height: FloatProperty(
        name="Height",
        description="Height of the parabola",
        default=2.0,
        min=0.1,
        max=10.0
    )
    width: FloatProperty(
        name="Width",
        description="Width of the parabola",
        default=4.0,
        min=0.1,
        max=10.0
    )
    segments: IntProperty(
        name="Segments",
        description="Number of segments in the parabola",
        default=32,
        min=4,
        max=64
    )
    use_gradient: BoolProperty(
        name="Gradient Width",
        description="Create mesh with gradient width for sharp beginning and end",
        default=True
    )
    gradient_width: FloatProperty(
        name="Max Width",
        description="Maximum width at the center of the gradient",
        default=0.35,
        min=0.01,
        max=1.0
    )
    use_curve: BoolProperty(
        name="Curved Mesh",
        description="Create a curved mesh along the slash line",
        default=False
    )
    curve_radius: FloatProperty(
        name="Curve Radius",
        description="Radius of the curved mesh",
        default=0.1,
        min=0.01,
        max=0.5
    )

# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_VFXSlashAdd(Operator):
    """Create a new VFX slash parabola mesh"""
    bl_idname = "zenv.vfx_slash_add"
    bl_label = "Add VFX Slash"
    bl_options = {'REGISTER', 'UNDO'}

    @staticmethod
    def create_parabola_points(props):
        """Generate points for the parabola based on properties"""
        points = []
        angle_rad = math.radians(props.angle)
        
        for i in range(props.segments):
            t = i / (props.segments - 1)
            x = t * props.width
            y = 4 * props.height * t * (1 - t)
            
            # Rotate points based on angle
            rotated_x = x * math.cos(angle_rad) - y * math.sin(angle_rad)
            rotated_y = x * math.sin(angle_rad) + y * math.cos(angle_rad)
            
            points.append(Vector((rotated_x, rotated_y, 0)))
        
        return points

    @staticmethod
    def create_gradient_mesh(name, points, props):
        """Create mesh with gradient width"""
        mesh = bpy.data.meshes.new(name)
        bm = bmesh.new()

        # Create vertices for both sides of the gradient
        verts_left = []
        verts_right = []
        
        for i, point in enumerate(points):
            t = i / (len(points) - 1)
            # Calculate gradient width (maximum at center, minimum at ends)
            width = props.gradient_width * math.sin(t * math.pi)
            
            # Calculate normal vector perpendicular to curve
            if i < len(points) - 1:
                tangent = (points[i + 1] - point).normalized()
            else:
                tangent = (point - points[i - 1]).normalized()
            normal = Vector((-tangent.y, tangent.x, 0))
            
            # Create vertices on both sides
            vert_left = bm.verts.new(point + normal * width)
            vert_right = bm.verts.new(point - normal * width)
            verts_left.append(vert_left)
            verts_right.append(vert_right)

        bm.verts.ensure_lookup_table()

        # Create faces
        for i in range(len(points) - 1):
            bm.faces.new((verts_left[i], verts_left[i + 1], 
                         verts_right[i + 1], verts_right[i]))

        bm.to_mesh(mesh)
        bm.free()
        return mesh

    @staticmethod
    def create_curved_mesh(name, points, props):
        """Create curved mesh along the line"""
        mesh = bpy.data.meshes.new(name)
        bm = bmesh.new()

        segments_circle = 8  # Number of segments in the circular cross-section
        
        # Create vertices for the tube
        for i, point in enumerate(points):
            # Calculate orientation
            if i < len(points) - 1:
                forward = (points[i + 1] - point).normalized()
            else:
                forward = (point - points[i - 1]).normalized()
            up = Vector((0, 0, 1))
            right = forward.cross(up).normalized()
            
            # Create circle vertices
            for j in range(segments_circle):
                angle = (j / segments_circle) * 2 * math.pi
                circle_pos = (right * math.cos(angle) + up * math.sin(angle)) * props.curve_radius
                vert = bm.verts.new(point + circle_pos)

        bm.verts.ensure_lookup_table()

        # Create faces
        verts_per_ring = segments_circle
        for i in range(len(points) - 1):
            for j in range(segments_circle):
                j1 = (j + 1) % segments_circle
                idx1 = i * segments_circle + j
                idx2 = i * segments_circle + j1
                idx3 = (i + 1) * segments_circle + j1
                idx4 = (i + 1) * segments_circle + j
                bm.faces.new((bm.verts[idx1], bm.verts[idx2], 
                            bm.verts[idx3], bm.verts[idx4]))

        bm.to_mesh(mesh)
        bm.free()
        return mesh

    @staticmethod
    def create_mesh_data(name, points):
        """Create mesh data from points"""
        mesh = bpy.data.meshes.new(name)
        bm = bmesh.new()

        # Add vertices
        for point in points:
            bm.verts.new(point)
        bm.verts.ensure_lookup_table()

        # Create edges
        for i in range(len(points) - 1):
            bm.edges.new((bm.verts[i], bm.verts[i + 1]))

        bm.to_mesh(mesh)
        bm.free()
        return mesh

    @staticmethod
    def add_uv_mapping(mesh, is_gradient=False, is_curved=False):
        """Add UV mapping to the mesh"""
        if mesh.uv_layers:
            uv_layer = mesh.uv_layers.active
        else:
            uv_layer = mesh.uv_layers.new()

        if is_gradient:
            # Map UVs for gradient mesh
            for face in mesh.polygons:
                for i, loop_index in enumerate(face.loop_indices):
                    if i in (0, 1):  # Top vertices
                        uv_layer.data[loop_index].uv.y = 1
                    else:  # Bottom vertices
                        uv_layer.data[loop_index].uv.y = 0
                    if i in (0, 3):  # Left vertices
                        uv_layer.data[loop_index].uv.x = face.index / (len(mesh.polygons))
                    else:  # Right vertices
                        uv_layer.data[loop_index].uv.x = (face.index + 1) / (len(mesh.polygons))
        elif is_curved:
            # Map UVs for curved mesh
            segments_circle = 8
            for face in mesh.polygons:
                for i, loop_index in enumerate(face.loop_indices):
                    v = i % 2
                    u = (face.index // segments_circle) / (len(mesh.polygons) // segments_circle)
                    uv_layer.data[loop_index].uv = Vector((u, v))
        else:
            # Map UVs for line mesh
            for i, loop in enumerate(mesh.loops):
                uv_layer.data[i].uv = Vector((float(i) / len(mesh.edges), 0.5))

    def execute(self, context):
        props = context.scene.zenv_vfx_slash_props

        # Generate parabola points
        points = self.create_parabola_points(props)

        # Create mesh based on options
        if props.use_gradient:
            mesh = self.create_gradient_mesh("VFX_Slash", points, props)
            self.add_uv_mapping(mesh, is_gradient=True)
        elif props.use_curve:
            mesh = self.create_curved_mesh("VFX_Slash", points, props)
            self.add_uv_mapping(mesh, is_curved=True)
        else:
            mesh = self.create_mesh_data("VFX_Slash", points)
            self.add_uv_mapping(mesh)

        # Create object and link to scene
        obj = bpy.data.objects.new("VFX_Slash", mesh)
        context.collection.objects.link(obj)

        # Select and make active
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj

        return {'FINISHED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_VFXSlashPanel(Panel):
    """Panel for VFX Slash Generator"""
    bl_label = "GEN VFX Slash Generator"
    bl_idname = "ZENV_PT_vfx_slash"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_vfx_slash_props
        
        # Draw properties
        col = layout.column(align=True)
        col.prop(props, "angle")
        col.prop(props, "height")
        col.prop(props, "width")
        col.prop(props, "segments")
        
        # Gradient options
        box = layout.box()
        box.prop(props, "use_gradient")
        if props.use_gradient:
            col = box.column()
            col.prop(props, "gradient_width")
            
        # Curve options
        box = layout.box()
        box.prop(props, "use_curve")
        if props.use_curve:
            col = box.column()
            col.prop(props, "curve_radius")
        
        # Draw operator
        layout.operator("zenv.vfx_slash_add", text="Add VFX Slash")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_VFXSlashProperties,
    ZENV_OT_VFXSlashAdd,
    ZENV_PT_VFXSlashPanel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_vfx_slash_props = PointerProperty(type=ZENV_PG_VFXSlashProperties)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_vfx_slash_props

if __name__ == "__main__":
    register()
